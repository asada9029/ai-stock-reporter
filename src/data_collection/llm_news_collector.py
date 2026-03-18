import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import sys
# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# GeminiClient が src/analysis にあると仮定
from src.analysis.gemini_client import GeminiClient

class LlmNewsCollector:
    """
    LLM (Gemini) の Web Search 機能を活用して注目ニュースを収集するモジュール
    """

    def __init__(self):
        self.gemini_client = GeminiClient() # GeminiClient のインスタンスを保持

    def search_news(self, query: str, num_results: int = 5) -> List[Dict]:
        """
        指定されたクエリでWeb検索を行い、ニュース記事を収集します。
        
        Args:
            query (str): 検索クエリ（例: "今日の株式市場の注目ニュース"）
            num_results (int): 取得する検索結果の最大数
            
        Returns:
            List[Dict]: ニュース記事のリスト。各辞書には 'title', 'url', 'snippet' などが含まれる。
        """
        print(f"🔍 LLM Web Search でニュースを検索中: '{query}'")
        
        try:
            # GeminiClient の search_news メソッドを呼び出す
            search_results_json = self.gemini_client.search_news(query=query, time_range="24時間以内")

            if not search_results_json or not search_results_json.get("found_articles"):
                print(f"    ⚠️ ニュースが見つかりませんでした: '{query}'")
                return []

            # 検索結果から必要な情報を抽出
            news_items = []
            for i, article in enumerate(search_results_json["found_articles"]):
                if i >= num_results:
                    break
                
                news_item = {
                    "title": article.get("title", "タイトルなし"),
                    "url": article.get("url", "#"),
                    "snippet": article.get("summary", "要約なし"), # summary を snippet として扱う
                    "source": article.get("source", "不明"),
                    "published_at": article.get("date", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                }
                news_items.append(news_item)
            
            print(f"✅ ニュース取得完了: {len(news_items)} 件")
            return news_items

        except Exception as e:
            print(f"❌ ニュース検索中にエラーが発生しました: {e}")
            return []

# デモ実行
if __name__ == "__main__":
    print("="*50)
    print("📰 LLM News Collector デモ")
    print("="*50)

    collector = LlmNewsCollector()

    # 例1: 株価に関わりそうな一般ニュース
    print("\n--- 株価に関わりそうな一般ニュース ---")
    general_market_news = collector.search_news(
        "過去24時間で、日本の株式市場全体に影響を与えそうな重要な経済ニュース、政治ニュース、国際情勢、技術動向に関する一般ニュースを10個教えてください。それぞれのニュースが株式市場に与える可能性のある影響についても簡潔に述べてください。",
        num_results=10 # より多くの結果を取得
    )
    for i, news in enumerate(general_market_news):
        print(f"{i+1}. {news['title']}")
        print(f"   URL: {news['url']}")
        print(f"   要約: {news['snippet']}")
        print(f"   情報源: {news['source']}")
        print()

    # 例2: 特定のキーワードに関するニュース (既存のものはコメントアウトまたは削除)
    # print("\n--- 特定のキーワード (半導体) に関するニュース ---")
    # tech_news = collector.search_news("半導体 関連ニュース", num_results=2)
    # for i, news in enumerate(tech_news):
    #     print(f"{i+1}. {news['title']}")
    #     print(f"   URL: {news['url']}")
    #     print(f"   要約: {news['snippet']}")
    #     print()

