import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from src.data_collection.ir_movement_analyzer import IRMovementAnalyzer
from src.data_collection.market_data_collector import MarketDataCollector
from src.data_collection.ir_event_collector import IrEventCollector
from src.data_collection.stock_chart_capturer import StockChartCapturer
from src.data_collection.llm_news_collector import LlmNewsCollector

def test_ir_batch_analysis():
    print("🔍 前回IR銘柄の一括解析テスト開始")
    
    # 1. 依存モジュールの準備
    market_collector = MarketDataCollector()
    ir_collector = IrEventCollector()
    stock_chart_capturer = StockChartCapturer()
    news_collector = LlmNewsCollector()
    
    analyzer = IRMovementAnalyzer(
        market_collector=market_collector,
        ir_collector=ir_collector,
        stock_chart_capturer=stock_chart_capturer,
        news_collector=news_collector
    )

    # 2. テスト用データの作成（複数銘柄）
    # 実際の前回動画メタデータを模倣
    published_at = (datetime.now() - timedelta(days=3)).isoformat()
    ir_stocks = [
        {"name": "トヨタ自動車", "ticker": "7203.T", "noted_ir": "決算発表", "ir_date": published_at},
        {"name": "ソニーグループ", "ticker": "6758.T", "noted_ir": "新製品発表", "ir_date": published_at},
        {"name": "ソフトバンクグループ", "ticker": "9984.T", "noted_ir": "投資利益", "ir_date": published_at}
    ]

    print(f"📊 解析対象銘柄数: {len(ir_stocks)}")
    print("📡 LLM一括リクエストを実行中...")

    # 3. 解析実行
    # 内部で generate_json_with_search が1回だけ呼ばれるはず
    results = analyzer.analyze_prev_ir_movements(
        published_at_iso=published_at,
        ir_stocks=ir_stocks
    )

    # 4. 結果の検証
    print("\n--- 📈 解析結果サマリー ---")
    if not results:
        print("❌ 結果が空です。")
        return

    for res in results:
        name = res.get("company_name")
        ticker = res.get("ticker")
        change = res.get("change_percent")
        news_count = len(res.get("recent_news", []))
        reason = res.get("reason_summary")
        
        print(f"✅ {name} ({ticker})")
        print(f"   - 株価変化率: {change}%")
        print(f"   - 取得ニュース数: {news_count}件")
        print(f"   - 推定理由: {reason[:100]}..." if reason else "   - 推定理由: 取得失敗")
        
        # 個別銘柄ごとにニュースが正しく入っているか
        if news_count > 0:
            for i, news in enumerate(res["recent_news"]):
                print(f"     ニュース{i+1}: {news.get('title')}")

    # 5. 一括処理の証跡確認
    print("\n--- 🛠️ 動作確認 ---")
    if all(res.get("reason_summary") for res in results):
        print("✅ 全銘柄に対して理由がマッピングされています。")
    else:
        print("⚠️ 一部の銘柄で理由の取得に失敗しています（LLMの回答漏れなど）。")

    if len(results) == len(ir_stocks):
        print(f"✅ 入力した {len(ir_stocks)} 銘柄すべてに対して結果が生成されました。")
    else:
        print(f"❌ 銘柄数が一致しません。入力: {len(ir_stocks)}, 出力: {len(results)}")

if __name__ == "__main__":
    test_ir_batch_analysis()
