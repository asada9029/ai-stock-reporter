import os
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

import sys
# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# GeminiClient が src/analysis にあると仮定
from src.analysis.gemini_client import GeminiClient
from src.utils.logger import log_kv, timed

class LlmNewsCollector:
    """
    LLM (Gemini) の Web Search 機能を活用して注目ニュースを収集するモジュール
    """

    def __init__(self):
        self.gemini_client = GeminiClient() # GeminiClient のインスタンスを保持

    def _parse_news_datetime_jst(self, date_str: str) -> Optional[datetime]:
        """
        Geminiが返す date 文字列をできるだけJSTのdatetimeに変換する。
        パースできない場合は None。
        """
        if not date_str:
            return None
        s = str(date_str).strip()

        # ISOっぽいもの
        try:
            s2 = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
            jst = timezone(timedelta(hours=9))
            if dt.tzinfo is None:
                # tzなしはJST扱い
                return dt
            return dt.astimezone(jst).replace(tzinfo=None)
        except Exception:
            pass

        # よくあるフォーマット
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%Y.%m.%d",
        ):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue

        return None

    @staticmethod
    def _clean_ticker(raw) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or s.lower() in ("null", "none", "n/a"):
            return None
        return s

    @staticmethod
    def _default_candidate_hours() -> List[int]:
        """
        検索時間窓のデフォルト。
        月曜朝は米国市場が金曜引け以来のため72時間、それ以外は12→24時間と段階延長。
        """
        if datetime.now().weekday() == 0:
            return [72]
        return [12, 24]

    def search_news(
        self,
        query: str,
        num_results: int = 5,
        candidate_hours: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        指定されたクエリでWeb検索を行い、ニュース記事を収集します。
        
        Args:
            query (str): 検索クエリ（例: "今日の株式市場の注目ニュース"）
            num_results (int): 取得する検索結果の最大数
            candidate_hours (Optional[List[int]]): 試行する時間窓（時間）。未指定時は曜日で自動決定。
            
        Returns:
            List[Dict]: ニュース記事のリスト。各辞書には 'title', 'url', 'snippet' などが含まれる。
        """
        log_kv("🔍 search_news:start", {"num_results": num_results})
        
        try:
            if candidate_hours is None:
                candidate_hours = self._default_candidate_hours()

            for hours in candidate_hours:
                time_range = f"{hours}時間以内"
                log_kv("🕒 search_news:try", {"time_range": time_range})

                # クエリ内の「過去XX時間」「XX時間以内」という表現を現在の hours に置換する
                # これにより、再試行時にクエリと検索窓の矛盾を解消する
                current_query = re.sub(r'(\d+)\s*時間', f'{hours}時間', query)

                # GeminiClient の search_news メソッドを呼び出す
                with timed("🔍 search_news:gemini"):
                    search_results_json = self.gemini_client.search_news(
                        query=current_query, time_range=time_range
                    )

                if not search_results_json or not search_results_json.get("found_articles"):
                    print(f"        ⚠️ found_articles が空: '{current_query}'")
                    continue

                # 検索結果から必要な情報を抽出（日時フィルタで古い記事を落とす）
                jst = timezone(timedelta(hours=9))
                # フィルタに2時間のバッファを持たせる（Geminiの検索結果が境界線上の場合に救うため）
                cutoff_jst = (datetime.now(jst) - timedelta(hours=hours + 2)).replace(tzinfo=None)

                news_items: List[Dict] = []
                undated_items: List[Dict] = []
                now_str = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")
                for article in search_results_json["found_articles"]:
                    if len(news_items) >= num_results:
                        break

                    # Gemini のキー揺れに備えて複数候補を見る
                    date_str = (
                        article.get("date")
                        or article.get("published_at")
                        or article.get("published")
                        or article.get("published_str")
                        or ""
                    )
                    dt = self._parse_news_datetime_jst(date_str)

                    # パースできないものは誤爆防止で除外
                    if not dt:
                        # date パース不能だと全落ちしやすいので、全滅時の救済用に退避
                        if len(undated_items) < num_results:
                            undated_items.append(
                                {
                                    "title": article.get("title", "タイトルなし"),
                                    "url": article.get("url", "#"),
                                    "snippet": article.get("summary", "要約なし"),
                                    "source": article.get("source", "不明"),
                                    "published_at": now_str,
                                    "related_ticker": self._clean_ticker(article.get("primary_ticker")),
                                    "related_company_name": (article.get("company_name") or "").strip(),
                                }
                            )
                        continue
                    if dt < cutoff_jst:
                        continue

                    news_item = {
                        "title": article.get("title", "タイトルなし"),
                        "url": article.get("url", "#"),
                        "snippet": article.get("summary", "要約なし"),  # summary を snippet として扱う
                        "source": article.get("source", "不明"),
                        "published_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "related_ticker": self._clean_ticker(article.get("primary_ticker")),
                        "related_company_name": (article.get("company_name") or "").strip(),
                    }
                    news_items.append(news_item)

                # parsed が0件なら undated から補完
                if not news_items and undated_items:
                    print(
                        f"        ⚠️ dateパース不能が多く、0件防止のため無日付を採用: {len(undated_items)} 件"
                    )
                    news_items = undated_items[:num_results]

                log_kv("✅ search_news:done", {"count": len(news_items), "time_range": time_range})
                if news_items:
                    return news_items

            print(
                f"    ⚠️ ニュースが見つかりませんでした"
                f"（試行窓: {', '.join(str(h) + '時間' for h in candidate_hours)}）: '{query}'"
            )
            return []

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

