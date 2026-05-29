"""
一般注目ニュース取得の単体テスト（LLM Web Search / JSONパース経路）。

本番の evening 動画と同じプロンプトで LlmNewsCollector.search_news を呼び、
0件頻発が解消しているかを確認する。

使い方:
  python test_general_attention_news.py
  python test_general_attention_news.py --market japan
  python test_general_attention_news.py --min-count 5

Windows で絵文字ログが落ちる場合:
  $env:PYTHONIOENCODING="utf-8"
  python test_general_attention_news.py

必要な環境変数:
  GEMINI_API_KEY（必須）
  GEMINI_API_KEY_SEARCH（Web Search 用・推奨）

結果JSON（任意）: output/news_test_*.json （.gitignore 対象）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.data_collection.llm_news_collector import LlmNewsCollector


def build_evening_japan_query() -> str:
    """market_data_collector.py（夜動画）と同一のクエリ。"""
    return """
            過去12時間で、日本の株式市場全体に影響を与えそうな重要な経済ニュース、政治ニュース、国際情勢、技術動向に関する一般ニュースを10個教えてください。
            
            【選定基準（重要）】
            - 投資家（株・資産形成層）の「財布に直結する」ニュースを最優先してください。
            - 「どのセクターが儲かるか」「どの銘柄にチャンスがあるか」などの投資の文脈に直結しそうなものを選んでください。
            - 日本の投資家が関心の高い話題（円安・円高の影響、大手企業の決算、政府の経済対策、半導体関連など）を優先してください。
            - 専門用語（日銀短観、GDP等）は、検索結果に含まれていても、後の工程で「景気」「国の成長」など分かりやすい言葉に翻訳できるよう、内容を詳しく把握しておいてください。
            """


def build_morning_us_query() -> str:
    """market_data_collector.py（朝動画・米国）と同一のクエリ。"""
    time_range_str = "過去72時間" if datetime.now().weekday() == 0 else "過去12時間"
    return f"""
            {time_range_str}で、米国の株式市場全体に影響を与えそうな重要な経済ニュース、政治ニュース、国際情勢、技術動向に関する米国の一般ニュースを10個教えてください。
            
            【選定基準（重要）】
            - 投資家（株・資産形成層）の「財布に直結する」ニュースを最優先してください。
            - 単なる政治ニュースではなく、「どのセクターが儲かるか」「どの銘柄にチャンスがあるか」などの投資の文脈に直結しそうなものを選んでください。
            - 日本の投資家にも馴染みのある大手企業（NVIDIA, Apple, Tesla等）や、分かりやすい景気動向を優先してください。
            - 専門用語（ISM, CPI等）は、検索結果に含まれていても、後の工程で「物価」「景気」など分かりやすい言葉に翻訳できるよう、内容を詳しく把握しておいてください。
            """


def run_test(market: str, num_results: int, min_count: int, save: bool) -> int:
    query = build_evening_japan_query() if market == "japan" else build_morning_us_query()
    label = "evening_japan" if market == "japan" else "morning_us"

    print("=" * 60)
    print(f"[NewsTest] 一般注目ニュース取得: {label}")
    print(f"  num_results={num_results}  min_count={min_count}")
    print("=" * 60)

    collector = LlmNewsCollector()
    articles = collector.search_news(query=query.strip(), num_results=num_results)

    print(f"\n[結果] 取得件数: {len(articles)} / 目標 {num_results}")
    for i, item in enumerate(articles, 1):
        print(f"\n--- {i} ---")
        print(f"  title: {item.get('title')}")
        print(f"  source: {item.get('source')}")
        print(f"  published_at: {item.get('published_at')}")
        print(f"  url: {item.get('url')}")
        snippet = (item.get("snippet") or "")[:120]
        if snippet:
            print(f"  snippet: {snippet}...")

    if hasattr(collector.gemini_client, "print_stats"):
        print()
        collector.gemini_client.print_stats()

    if save and articles:
        out_dir = project_root / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"news_test_{label}_{ts}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"\n[保存] {out_path}")

    if len(articles) >= min_count:
        print(f"\n[OK] {min_count} 件以上取得できました。")
        return 0

    print(f"\n[NG] {min_count} 件未満です（一般ニュース0件問題の再発の可能性）。")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="一般注目ニュース取得テスト")
    parser.add_argument(
        "--market",
        choices=["japan", "us"],
        default="japan",
        help="japan=夜動画の日本一般ニュース（default）, us=朝動画の米国一般ニュース",
    )
    parser.add_argument("--num-results", type=int, default=10)
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="この件数未満なら exit 1（default: 1）",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="output/news_test_*.json に保存（gitignore対象）",
    )
    args = parser.parse_args()
    sys.exit(
        run_test(
            market=args.market,
            num_results=args.num_results,
            min_count=args.min_count,
            save=args.save,
        )
    )


if __name__ == "__main__":
    main()
