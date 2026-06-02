import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
import json
import re
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime, timedelta, timezone


load_dotenv()

ModelRole = Literal["heavy", "lite", "search"]


class GeminiClient:
    """Gemini API クライアント（Web Search対応）"""
    
    # モデル定数
    MODEL_FLASH = "gemini-3.1-flash-lite"      # 通常生成・Web Search（優先）
    MODEL_FLASH_LITE = "gemini-3.1-flash-lite"  # 通常生成（フォールバック）
    MODEL_SEARCH = "gemini-3.1-flash-lite"     # Web Search（GEMINI_API_KEY_SEARCH / 有料枠）
    MODEL_HEAVY = "gemini-3.5-flash"           # 高性能が必要な場合（フォールバック）
    MODEL_PRO = "gemini-3-pro-preview"
    MODEL_TEST = "gemini-2.5-flash"

    # テキスト用 / Search用で API キーを分離可能（Search のみ有料キーを使う場合）
    _shared_text_client = None
    _shared_search_client = None

    @classmethod
    def _text_api_key(cls) -> str:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        return key

    @classmethod
    def _search_api_key(cls) -> str:
        # 3.5 の Grounding は有料枠のみ。本番は GEMINI_API_KEY_SEARCH を推奨
        key = os.getenv("GEMINI_API_KEY_SEARCH") or cls._text_api_key()
        if not os.getenv("GEMINI_API_KEY_SEARCH"):
            print(
                "[WARN] GEMINI_API_KEY_SEARCH 未設定: "
                "3.5 Flash の Web Search は有料枠が必要なため、検索が失敗する可能性があります"
            )
        return key

    @classmethod
    def _get_text_client(cls) -> genai.Client:
        if cls._shared_text_client is None:
            cls._shared_text_client = genai.Client(api_key=cls._text_api_key())
        return cls._shared_text_client

    @classmethod
    def _get_search_client(cls) -> genai.Client:
        if cls._shared_search_client is None:
            cls._shared_search_client = genai.Client(api_key=cls._search_api_key())
        return cls._shared_search_client

    def __init__(self, enable_search: bool = True):
        """
        Args:
            enable_search: Web Search機能を有効にするか
        """
        self._get_text_client()
        self._get_search_client()
        self.client = self._get_text_client()
        self.enable_search = enable_search

        # 設定の作成
        self.search_config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ) if enable_search else None
        self.no_search_config = types.GenerateContentConfig(tools=[])

        search_key_mode = (
            "専用キー(GEMINI_API_KEY_SEARCH)"
            if os.getenv("GEMINI_API_KEY_SEARCH")
            else "GEMINI_API_KEYと共通"
        )
        print(
            f"[OK] Gemini クライアント初期化完了 (Search: {enable_search}) "
            f"[text={self.MODEL_FLASH}->{self.MODEL_HEAVY}, "
            f"search={self.MODEL_SEARCH}->{self.MODEL_HEAVY}, key={search_key_mode}]"
        )
        self._stats = {
            "calls_text": 0,
            "calls_search": 0,
            "json_repair_ok": 0,
            "json_reparse_ok": 0,
            "json_retry_search": 0,
        }

    @staticmethod
    def _models_for_role(model_role: ModelRole, *, use_search: bool = False) -> tuple[str, ...]:
        """使用するモデル列（優先順）。"""
        if use_search:
            # 検索時は Lite を優先し、失敗時に 3.5 Flash へ
            return (GeminiClient.MODEL_SEARCH, GeminiClient.MODEL_HEAVY)
        
        if model_role == "heavy":
            return (GeminiClient.MODEL_HEAVY, GeminiClient.MODEL_FLASH_LITE)
            
        return (GeminiClient.MODEL_FLASH, GeminiClient.MODEL_HEAVY)

    @staticmethod
    def _is_rate_or_quota_error(e: Exception) -> bool:
        msg = str(e).lower()
        if "429" in msg:
            return True
        if "quota" in msg:
            return True
        if "resource exhausted" in msg:
            return True
        if "rate" in msg and "limit" in msg:
            return True
        return False

    @staticmethod
    def _is_overloaded_error(e: Exception) -> bool:
        msg = str(e).lower()
        return "503" in msg or "overloaded" in msg or "unavailable" in msg

    @staticmethod
    def _is_quota_exhausted(e: Exception) -> bool:
        """日次クォータ等。長時間リトライしても回復しない。"""
        msg = str(e).lower()
        return "resource_exhausted" in msg or (
            "quota" in msg and ("exceeded" in msg or "limit" in msg)
        )
    
    def generate_content(
        self,
        prompt: str,
        max_retries: int = 5,
        retry_delay: int = 10,
        use_search: bool = True,
        model_role: ModelRole = "lite",
    ) -> str:
        """
        コンテンツ生成（サイクル制リトライ: 3.1 -> 3.5 -> 指数バックオフ -> 3.1 -> 3.5 ...）

        Args:
            prompt: プロンプト
            max_retries: 最大サイクル数（デフォルト3）
            retry_delay: サイクル間のバックオフ基数（秒）
            use_search: Web Searchを使用するか
            model_role: モデルの役割
        """
        config = self.search_config if use_search and self.enable_search else self.no_search_config
        search_active = use_search and self.enable_search
        models = list(self._models_for_role(model_role, use_search=search_active))

        api_client = (
            self._get_search_client() if search_active else self._get_text_client()
        )
        if search_active:
            self._stats["calls_search"] += 1
        else:
            self._stats["calls_text"] += 1

        last_exc: Optional[Exception] = None
        for cycle in range(max_retries):
            for model in models:
                try:
                    response = api_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config,
                    )
                    return response.text

                except Exception as e:
                    last_exc = e
                    error_msg = str(e).lower()

                    if "block" in error_msg:
                        raise Exception(f"コンテンツがブロックされました: {e}") from e

                    # クォータ切れや一時的なエラー（503/429等）はログを出して次のモデル/サイクルへ
                    print(f"[WARN] {model} 失敗 (サイクル {cycle + 1}/{max_retries}): {e}")
                    
                    # ハードなクォータ制限（Resource Exhausted）の場合は、
                    # 別のAPIキーを使っている可能性がある search_client/text_client の切り替えに期待して続行
            
            # 1サイクル（全モデル試行）終わっても成功しなかった場合、指数バックオフを入れて次のサイクルへ
            if cycle < max_retries - 1:
                current_delay = retry_delay * (2 ** cycle)
                print(f"   -> サイクル {cycle + 1} 失敗。{current_delay}秒待機して次のサイクルを開始します...")
                time.sleep(current_delay)

        raise Exception(f"全 {max_retries} サイクルが失敗しました。最後のエラー: {last_exc}")
    
    def generate_content_with_search(
        self,
        prompt: str,
        max_retries: int = 3,
        retry_delay: int = 20,
        model_role: ModelRole = "search",
    ) -> Dict[str, Any]:
        """
        Web Searchを使用してコンテンツを生成（最重要メソッド）
        
        Args:
            prompt: プロンプト（検索クエリを含む）
            max_retries: 最大リトライ回数
            retry_delay: リトライ間隔（秒）
        
        Returns:
            Dict: {
                "text": "生成されたテキスト",
                "search_used": True/False,
                "raw_response": 生のレスポンスオブジェクト
            }
        """
        
        if not self.enable_search:
            raise Exception("Web Search機能が有効になっていません")
        
        print("[Search] Web Searchを使用してコンテンツ生成中...")

        try:
            response_text = self.generate_content(
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
                use_search=True,
                model_role="search",
            )

            result = {
                "text": response_text,
                "search_used": True,
                # 'raw_response' の取得は generate_content の修正が必要
                "raw_response": None 
            }
            
            print("[OK] Web Search結果が含まれている可能性があります")
            
            return result

        except Exception as e:
                error_msg = str(e)
                raise Exception(f"Web Search生成エラー: {error_msg}")
    
    def generate_json(
        self,
        prompt: str,
        max_retries: int = 5,
        use_search: bool = False,
        model_role: ModelRole = "lite",
    ) -> dict:
        """
        JSON形式でコンテンツを生成
        
        Args:
            prompt: プロンプト（JSON形式を要求する内容）
            max_retries: 最大リトライ回数
            use_search: Web Searchを使用するか
        
        Returns:
            dict: パースされたJSON
        """
        
        # プロンプトにJSON形式を明示
        json_prompt = f"""{prompt}

【重要】
- 必ずJSON形式のみで返してください
- 余計な説明や```json```などのマークダウンは不要です
- 純粋なJSONのみを出力してください
"""
        
        response = self.generate_content(
            json_prompt, max_retries, use_search=use_search, model_role=model_role
        )

        # JSONパース
        return self._parse_json_response(
            response, prompt, max_retries, use_search, model_role
        )
    
    def generate_json_with_search(
        self,
        prompt: str,
        max_retries: int = 3,
        model_role: ModelRole = "search",
    ) -> dict:
        """
        Web Searchを使用してJSON形式でコンテンツを生成
        
        Args:
            prompt: プロンプト
            max_retries: 最大リトライ回数
        
        Returns:
            dict: パースされたJSON
        """
        
        json_prompt = f"""{prompt}

【重要】
- 必ずJSON形式のみで返してください
- 余計な説明や```json```などのマークダウンは不要です
- 純粋なJSONのみを出力してください
- Web検索で見つけた情報を必ず含めてください
"""
        
        result = self.generate_content_with_search(
            json_prompt, max_retries, model_role=model_role
        )

        # JSONパース
        return self._parse_json_response(
            result["text"], prompt, max_retries, use_search=True, model_role=model_role
        )
    
    def _parse_json_response(
        self,
        response: str,
        original_prompt: str,
        max_retries: int,
        use_search: bool = False,
        model_role: ModelRole = "lite",
    ) -> dict:
        """
        レスポンスをJSONとしてパース（内部メソッド）
        
        Args:
            response: レスポンステキスト
            original_prompt: 元のプロンプト
            max_retries: 残りリトライ回数
        
        Returns:
            dict: パースされたJSON
        """
        def _clean(s: str) -> str:
            s2 = re.sub(r"```json\s*|```\s*", "", s).strip()
            return s2.strip()

        def _extract_json_candidate(s: str) -> Optional[str]:
            """
            LLM が前後に説明文/引用を付けた場合でも JSON 本体を救出する。
            - まず配列 [..] を探す
            - 次にオブジェクト {..} を探す
            """
            # 配列優先
            m = re.search(r"(\[[\s\S]*\])", s)
            if m:
                return m.group(1).strip()
            m = re.search(r"(\{[\s\S]*\})", s)
            if m:
                return m.group(1).strip()
            return None

        def _repair_json_with_text_llm(raw: str) -> Optional[dict]:
            """
            Search の生レスポンスが崩れて JSON parse できない場合に、
            Searchなしのモデルで「JSONだけを抽出/修復」してもらう。
            ※Search再実行を避けてコストを抑える狙い。
            """
            try:
                # 入力が長すぎると失敗しやすいので上限を設ける（必要なら調整）
                max_chars = 12000
                clipped = raw if len(raw) <= max_chars else raw[:max_chars] + "\n...(truncated)\n"

                repair_prompt = f"""次のテキストは、LLMが返した「JSONのつもりの出力」ですが、壊れていて JSON パースに失敗しました。
あなたの仕事は、内容をできるだけ保持したまま、**純粋なJSON**（オブジェクトまたは配列）だけを出力することです。

ルール:
- 出力は JSON のみ（前後の説明、Markdown、コードフェンス禁止）
- 文字列は必ずダブルクォート
- 不正なトークン（例: 参照番号や脚注）を除去
- どうしても復元できない部分は null / 空配列 / 空文字 で整合を取る

入力テキスト:
{clipped}
"""
                repaired = self.generate_content(
                    repair_prompt,
                    max_retries=2,
                    retry_delay=5,
                    use_search=False,
                    model_role="heavy",
                )
                repaired_clean = _clean(repaired)
                cand = _extract_json_candidate(repaired_clean) or repaired_clean
                return json.loads(cand)
            except Exception:
                return None

        try:
            cleaned = _clean(response)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                cand = _extract_json_candidate(cleaned)
                if cand:
                    parsed = json.loads(cand)
                    self._stats["json_reparse_ok"] += 1
                    return parsed
                raise

        except json.JSONDecodeError as e:
            print(f"[WARN] JSONパース失敗: {e}")
            print(f"レスポンス（最初の300文字）: {response[:300]}...")

            # まずは Searchなしモデルで JSON修復を試す（再検索より安い）
            repaired = _repair_json_with_text_llm(response)
            if repaired is not None:
                print("[OK] SearchなしモデルでJSON修復に成功（再検索なし）")
                self._stats["json_repair_ok"] += 1
                return repaired
            
            # フォールバック: 再試行
            if max_retries > 0:
                print(f"再試行します... (残り{max_retries}回)")
                time.sleep(5)
                if use_search:
                    self._stats["json_retry_search"] += 1
                    return self.generate_json_with_search(
                        original_prompt, max_retries - 1, model_role=model_role
                    )
                return self.generate_json(
                    original_prompt,
                    max_retries - 1,
                    use_search=False,
                    model_role=model_role,
                )

            raise Exception(f"JSONパースに失敗しました: {e}\nレスポンス: {response[:500]}")
    
    def search_news(
        self,
        query: str,
        time_range: str = "12時間以内",
        model_role: ModelRole = "search",
    ) -> Dict[str, Any]:
        """
        ニュース検索（専用メソッド）
        
        Args:
            query: 検索クエリ
            time_range: 時間範囲（例: "12時間以内", "今日"）
        
        Returns:
            Dict: 検索結果
        """
        
        # JST（UTC+9）での現在時刻と対象期間を明示して、古い記事が混ざるのを抑える
        jst = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst)
        # time_range は "12時間以内" などの想定。フォーマットが崩れたら 12時間扱い。
        hours = 12
        m = re.search(r'(\d+)\s*時間', time_range)
        if m:
            hours = int(m.group(1))
        start_jst = now_jst - timedelta(hours=hours)

        now_str = now_jst.strftime("%Y-%m-%d %H:%M")
        start_str = start_jst.strftime("%Y-%m-%d %H:%M")

        prompt = f"""
以下の条件でニュースを検索し、JSON形式で返してください。

検索クエリ: {query}
時間範囲: {time_range}
現在時刻（JST）: {now_str}
対象開始（JST）: {start_str}

出力形式:
{{
  "query": "{query}",
  "found_articles": [
    {{
      "title": "記事タイトル",
      "summary": "要約",
      "source": "情報源",
      "date": "日付",
      "url": "URL（あれば）",
      "primary_ticker": "7203.T または NVDA など（該当なしは null）",
      "company_name": "主役企業名（該当なしは空文字）"
    }}
  ],
  "total_count": 件数,
  "search_timestamp": "検索時刻"
}}

【銘柄推定ルール】
- ニュースの主役が1社に絞れるときだけ primary_ticker を付ける。指数・政策・宏观のみなら null。
- 日本株は 7203.T 形式、米国株は NVDA / AAPL 形式。
- 複数社なら最も中心の1社のみ。

重要な情報のみを抽出し、信頼性の高い情報源を優先してください。
【超重要】found_articles の各要素の "date" は必ず「対象開始（JST）〜現在時刻（JST）」の範囲に入っているものだけを返してください。
範囲外の記事が混ざる場合は、混ざらないように捨ててください（古い記事を返さないでください）。
"""
        
        return self.generate_json_with_search(prompt, model_role=model_role)
    
    def analyze_news(self, news_data: dict) -> dict:
        """ニュース分析"""
        
        prompt = f"""
以下のニュースを分析し、JSON形式で返してください。

ニュースデータ:
{json.dumps(news_data, ensure_ascii=False, indent=2)}

出力形式:
{{
  "summary": "要約（100文字以内）",
  "importance_score": 85,
  "affected_sectors": ["半導体", "自動車"],
  "affected_stocks": ["トヨタ(7203)", "ソニー(6758)"],
  "sentiment": "positive",
  "key_points": ["ポイント1", "ポイント2", "ポイント3"]
}}
"""
        
        return self.generate_json(prompt, model_role="lite")

    def print_stats(self) -> None:
        """実行中のAPI呼び出し統計を表示（目安）。"""
        try:
            s = getattr(self, "_stats", None) or {}
            print(
                "📊 Gemini stats "
                + " ".join([f"{k}={v}" for k, v in s.items()])
            )
        except Exception:
            pass
    
    def generate_script(
        self,
        section: str,
        duration: int,
        data: dict
    ) -> str:
        """
        動画台本を生成
        
        Args:
            section: セクション名（opening, us_market等）
            duration: 目標時間（秒）
            data: データ
        
        Returns:
            str: 台本（間を含む）
        """
        
        # 1文字あたり約0.25秒として計算
        target_chars = int(duration / 0.25)
        
        prompt = f"""
株ニュースAI VTuberの{section}セクションの台本を生成してください。

【条件】
- 文字数: {target_chars}文字程度
- 時間: {duration}秒
- 適切な位置に「（間）」を挿入
- 重要な情報の前には「（長めの間）」
- 初心者向けにわかりやすく
- 四国めたんの声（落ち着いた女性）に合う口調

【データ】
{json.dumps(data, ensure_ascii=False, indent=2)}

【出力例】
おはようございます。（間）
今日は2025年11月16日です。（長めの間）
それでは、昨夜の米国市場を見ていきましょう。（3秒間）
"""
        
        return self.generate_content(prompt, use_search=False, model_role="lite")


# テスト用
if __name__ == "__main__":
    print("="*60)
    print("Gemini Client テスト（Web Search対応版）")
    print("="*60 + "\n")
    
    # クライアント初期化
    client = GeminiClient(enable_search=True)
    
    # テスト1: 基本生成（検索なし）
    print("\n=== テスト1: 基本生成（検索なし） ===")
    result = client.generate_content("こんにちは、Gemini!", use_search=False)
    print(result)
    
    # テスト2: Web Search生成
    print("\n=== テスト2: Web Search生成 ===")
    search_result = client.generate_content_with_search(
        "過去24時間の日本株市場の主要ニュースを3つ教えてください"
    )
    print(f"検索使用: {search_result['search_used']}")
    print(f"結果:\n{search_result['text']}")
    
    # テスト3: ニュース検索（JSON形式）
    print("\n=== テスト3: ニュース検索（JSON形式） ===")
    news_result = client.search_news(
        query="日経平均 今日",
        time_range="24時間以内"
    )
    print(json.dumps(news_result, ensure_ascii=False, indent=2))
    
    # テスト4: 引け後IR検索
    print("\n=== テスト4: 引け後IR検索 ===")
    ir_result = client.generate_content_with_search(
        "本日15時以降に発表された日本企業の重要なIR情報を検索してください"
    )
    print(ir_result['text'])
    
    print("\n" + "="*60)
    print("[OK] テスト完了")
    print("="*60)
