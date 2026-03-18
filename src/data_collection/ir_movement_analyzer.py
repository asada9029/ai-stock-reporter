import os
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional


class IRMovementAnalyzer:
    """
    前回動画で取り上げたIR銘柄のその後の動向を解析するユーティリティクラス。
    LLMのWeb検索能力を活用し、株価の変化率、変動理由、関連ニュースを一括で解析します。
    """

    def __init__(self, market_collector, ir_collector, stock_chart_capturer, news_collector, output_dir: str = "data/collected_data"):
        """
        初期化
        Args:
            market_collector: 市場データ取得用インスタンス
            ir_collector: IR情報取得用インスタンス（現在はスケジュール取得が主）
            stock_chart_capturer: 個別銘柄チャート取得用インスタンス
            news_collector: ニュース取得用インスタンス（GeminiClientを内包）
            output_dir: 解析結果の保存先
        """
        self.market_collector = market_collector
        self.ir_collector = ir_collector
        self.stock_chart_capturer = stock_chart_capturer
        self.news_collector = news_collector
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def analyze_prev_ir_movements(
        self,
        published_at_iso: str,
        ir_stocks: List[Dict],
        lookback_days: int = 7,
        price_history_days: int = 7,
    ) -> List[Dict]:
        """
        前回動画の銘柄のその後の動きを解析します。
        
        Args:
            published_at_iso: 前回動画の公開日時(ISO文字列)
            ir_stocks: 対象銘柄リスト [{"name": "...", "ticker": "...", "ir_date": "..."} , ...]
            
        Returns:
            List[Dict]: 解析結果のリスト。株価変動、チャートパス、LLMによる理由推定を含む。
        """
        results: List[Dict] = []
        try:
            published_at = datetime.fromisoformat(published_at_iso)
        except Exception:
            published_at = datetime.now(timezone.utc)

        to_ts = datetime.now(timezone.utc)
        
        # 1. 各銘柄の基礎データ（チャート画像のみ）を収集
        stocks_data_for_llm = []
        for stock in ir_stocks:
            company_name = stock.get("name")
            ticker = stock.get("ticker")
            
            # 比較開始日時の決定
            try:
                if stock.get("ir_date"):
                    from_ts = datetime.fromisoformat(stock.get("ir_date"))
                else:
                    from_ts = published_at
            except Exception:
                from_ts = published_at

            # チャート画像のキャプチャ（視覚的な補助として残す）
            chart_image_path = None
            try:
                chart_image_path = self.stock_chart_capturer.capture_chart_screenshot(ticker, company_name)
            except Exception:
                chart_image_path = None

            # 解析結果のベース構造を作成
            stock_res = {
                "company_name": company_name,
                "ticker": ticker,
                "from_ts": from_ts.isoformat() if hasattr(from_ts, "isoformat") else str(from_ts),
                "to_ts": to_ts.isoformat(),
                "change_percent": None, # LLMが埋める
                "chart_image_path": chart_image_path,
                "recent_news": [],
                "reason_summary": None
            }
            results.append(stock_res)
            
            # LLMに渡すための情報を整理
            stocks_data_for_llm.append({
                "name": company_name,
                "ticker": ticker,
                "period": f"{from_ts.date()} から {to_ts.date()}（本日）まで"
            })

        # 2. LLMによる一括解析（株価変化率・理由・ニュースをすべてWeb検索で調査）
        if results:
            print(f"📡 {len(results)} 銘柄の動向（騰落率含む）をLLMで一括解析中...")
            try:
                prompt = f"""以下の日本企業について、指定された期間内の【株価の変化率（%）】と、その変動理由となった【新規IR発表】や【主要ニュース】をWeb検索で徹底的に調査し、JSON形式で教えてください。

# 解析のルール（怪しさ満点の抽象的表現は禁止）:
1. 株価変化率: 指定された期間における「終値ベース」の騰落率を具体的に調べてください。不明な場合は「不明」としてください。
2. 具体性：材料（決算、提携、受注、不祥事など）がある場合は、必ず具体的な内容と数値を含めてください。
3. 論理性：なぜその株価変化が起きたのか、ニュースや市場環境と論理的に結びつけて解説してください。
4. 誠実さ：明確な材料が見当たらない場合は、無理にこじつけず「需給の乱れ」「利益確定売り」「材料出尽くし」「外部環境（米国株安など）への連動」など、市場の動向に基づいた妥当な推論を行ってください。
5. 各企業につき、関連ニュースを最大3件（title, summary, urlを含む）含めてください。
6. 回答は必ず指定されたJSON形式のみとし、余計な解説は含めないでください。

# 企業リストと対象期間:
{json.dumps(stocks_data_for_llm, ensure_ascii=False, indent=2)}

# 出力形式例:
{{
  "トヨタ自動車": {{
    "change_percent": "+2.5",
    "news": [
      {{"title": "...", "summary": "...", "url": "..."}}
    ],
    "reason": "株価が2.5%上昇したのは、〇〇の発表が好感されたためと推定されます。出典：〇〇新聞。"
  }}
}}
"""
                llm_response = self.news_collector.gemini_client.generate_json_with_search(prompt=prompt)
                
                # LLMの回答を各銘柄の結果にマッピング
                for res in results:
                    name = res["company_name"]
                    ticker = res["ticker"]
                    analysis = llm_response.get(name) or llm_response.get(ticker)
                    if analysis:
                        res["change_percent"] = analysis.get("change_percent")
                        res["recent_news"] = analysis.get("news", [])
                        res["reason_summary"] = analysis.get("reason")
            except Exception as e:
                print(f"⚠️ 前回IR銘柄の一括解析中にエラーが発生しました: {e}")

        return results


__all__ = ["IRMovementAnalyzer"]
