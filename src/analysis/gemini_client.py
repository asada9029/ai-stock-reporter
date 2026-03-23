import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone


load_dotenv()


class GeminiClient:
    """Gemini API クライアント（Web Search対応）"""
    
    # モデル定数
    MODEL_FLASH = "gemini-3-flash-preview"           # バランス型
    MODEL_PRO = "gemini-3-pro-preview"               # 最高品質
    MODEL_TEST = "gemini-2.5-flash"             # テスト：激安・爆速版

    # クラス共有のクライアントインスタンス（無駄な初期化を防止）
    _shared_client = None
    
    def __init__(self, model_name: str = MODEL_FLASH, enable_search: bool = True):
        """
        Args:
            model_name: 使用するモデル
                - gemini-3-flash-preview (推奨)
                - gemini-3-pro-preview (高品質・高コスト)
            enable_search: Web Search機能を有効にするか
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY が設定されていません")
        
        # クライアントのシングルトン化
        if GeminiClient._shared_client is None:
            GeminiClient._shared_client = genai.Client(api_key=api_key)
        
        self.client = GeminiClient._shared_client
        self.model_name = model_name
        self.enable_search = enable_search
        
        # 設定の作成
        self.search_config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ) if enable_search else None
        self.no_search_config = types.GenerateContentConfig(tools=[])
        
        print(f"✅ Gemini クライアント初期化完了: {model_name} (Search: {enable_search})")
    
    def generate_content(
        self,
        prompt: str,
        max_retries: int = 10,
        retry_delay: int = 30,  # デフォルトの待ち時間を短縮
        use_search: bool = True
    ) -> str:
        """
        コンテンツ生成（リトライ機能付き）
        
        Args:
            prompt: プロンプト
            max_retries: 最大リトライ回数
            retry_delay: リトライ間隔（秒）
            use_search: Web Searchを使用するか
        
        Returns:
            str: 生成されたテキスト
        """
        config = self.search_config if use_search and self.enable_search else self.no_search_config
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return response.text
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # 指数バックオフ的な待ち時間の計算 (30s, 60s, 120s...)
                current_delay = retry_delay * (2 ** attempt)
                
                # 503 (Overloaded) または 429 (Rate Limit) の場合
                if "503" in error_msg or "overloaded" in error_msg or "429" in error_msg or "quota" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"⚠️ モデル混雑または制限中 (Attempt {attempt+1})。{current_delay}秒後にリトライ...")
                        time.sleep(current_delay)
                        continue
                
                # ブロックエラー
                if "block" in error_msg:
                    raise Exception(f"コンテンツがブロックされました: {e}")
                
                # その他のエラー
                if attempt < max_retries - 1:
                    print(f"⚠️ エラー発生: {e}。{current_delay}秒後にリトライ...")
                    time.sleep(current_delay)
                    continue
                
                raise Exception(f"Gemini API エラー: {e}")
        
        raise Exception("最大リトライ回数を超えました")
    
    def generate_content_with_search(
        self,
        prompt: str,
        max_retries: int = 8,
        retry_delay: int = 90
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
        
        print("🔍 Web Searchを使用してコンテンツ生成中...")

        try:
            response_text = self.generate_content(
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
                use_search=True
            )

            result = {
                "text": response_text,
                "search_used": True,
                # 'raw_response' の取得は generate_content の修正が必要
                "raw_response": None 
            }
            
            print("✅ Web Search結果が含まれている可能性があります")
            
            return result

        except Exception as e:
                error_msg = str(e)
                raise Exception(f"Web Search生成エラー: {error_msg}")
    
    def generate_json(
        self,
        prompt: str,
        max_retries: int = 5,
        use_search: bool = False
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
        
        response = self.generate_content(json_prompt, max_retries, use_search=use_search)
        
        # JSONパース
        return self._parse_json_response(response, prompt, max_retries)
    
    def generate_json_with_search(
        self,
        prompt: str,
        max_retries: int = 5
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
        
        result = self.generate_content_with_search(json_prompt, max_retries)
        
        # JSONパース
        return self._parse_json_response(result["text"], prompt, max_retries)
    
    def _parse_json_response(
        self,
        response: str,
        original_prompt: str,
        max_retries: int
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
        try:
            # ```json ``` などを削除
            cleaned = re.sub(r'```json\s*|```\s*', '', response).strip()
            
            # 前後の不要な文字を削除
            cleaned = cleaned.strip()
            
            return json.loads(cleaned)
            
        except json.JSONDecodeError as e:
            print(f"⚠️ JSONパース失敗: {e}")
            print(f"レスポンス（最初の300文字）: {response[:300]}...")
            
            # フォールバック: 再試行
            if max_retries > 0:
                print(f"再試行します... (残り{max_retries}回)")
                time.sleep(5)
                return self.generate_json(original_prompt, max_retries - 1)
            
            raise Exception(f"JSONパースに失敗しました: {e}\nレスポンス: {response[:500]}")
    
    def search_news(
        self,
        query: str,
        time_range: str = "12時間以内"
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
      "url": "URL（あれば）"
    }}
  ],
  "total_count": 件数,
  "search_timestamp": "検索時刻"
}}

重要な情報のみを抽出し、信頼性の高い情報源を優先してください。
【超重要】found_articles の各要素の "date" は必ず「対象開始（JST）〜現在時刻（JST）」の範囲に入っているものだけを返してください。
範囲外の記事が混ざる場合は、混ざらないように捨ててください（古い記事を返さないでください）。
"""
        
        return self.generate_json_with_search(prompt)
    
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
        
        return self.generate_json(prompt)
    
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
        
        return self.generate_content(prompt)


# テスト用
if __name__ == "__main__":
    print("="*60)
    print("Gemini Client テスト（Web Search対応版）")
    print("="*60 + "\n")
    
    # クライアント初期化
    client = GeminiClient(
        model_name=GeminiClient.MODEL_FLASH,
        enable_search=True
    )
    
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
    print("✅ テスト完了")
    print("="*60)
