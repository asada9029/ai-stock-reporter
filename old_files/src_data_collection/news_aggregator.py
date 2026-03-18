"""
ニュース収集モジュール
複数のRSSフィードから株式・経済ニュースを取得
"""

import feedparser
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
from urllib.parse import urlparse


class NewsAggregator:
    """ニュース収集クラス"""
    
    def __init__(self):
        """初期化"""
        
        # RSSフィードのURL
        self.feed_sources = {
            'yahoo_business': {
                'url': 'https://news.yahoo.co.jp/rss/topics/business.xml',
                'name': 'Yahoo!ニュース - ビジネス',
                'category': 'business'
            },
            'yahoo_economy': {
                'url': 'https://news.yahoo.co.jp/rss/topics/economy.xml',
                'name': 'Yahoo!ニュース - 経済',
                'category': 'economy'
            },
            'nikkei': {
                'url': 'https://www.nikkei.com/rss/',
                'name': '日本経済新聞',
                'category': 'general'
            },
            'reuters_business': {
                'url': 'https://jp.reuters.com/rss/businessNews',
                'name': 'ロイター - ビジネス',
                'category': 'business'
            },
            'reuters_markets': {
                'url': 'https://jp.reuters.com/rss/marketsNews',
                'name': 'ロイター - マーケット',
                'category': 'markets'
            }
        }
        
        self.cache = {}  # 重複チェック用キャッシュ
        self.seen_hashes = set()  # 重複記事のハッシュ
    
    def fetch_feed(
        self,
        feed_url: str,
        feed_name: str,
        category: str
    ) -> List[Dict]:
        """
        単一のRSSフィードを取得
        
        Args:
            feed_url: RSSフィードのURL
            feed_name: フィード名
            category: カテゴリ
        
        Returns:
            list: ニュース記事のリスト
        """
        
        try:
            print(f"📡 取得中: {feed_name}")
            
            feed = feedparser.parse(feed_url)
            
            if not feed.entries:
                print(f"⚠️ 記事が見つかりません: {feed_name}")
                return []
            
            articles = []
            
            for entry in feed.entries:
                # 記事データを整形
                article = self._parse_entry(entry, feed_name, category)
                
                if article:
                    articles.append(article)
            
            print(f"✅ {len(articles)}件取得: {feed_name}")
            return articles
            
        except Exception as e:
            print(f"❌ エラー ({feed_name}): {e}")
            return []
    
    def _parse_entry(
        self,
        entry,
        source_name: str,
        category: str
    ) -> Optional[Dict]:
        """
        RSSエントリーを解析して記事データに変換
        
        Args:
            entry: feedparserのエントリー
            source_name: ソース名
            category: カテゴリ
        
        Returns:
            dict: 記事データ
        """
        
        try:
            # タイトル
            title = entry.get('title', '').strip()
            if not title:
                return None
            
            # リンク
            link = entry.get('link', '')
            
            # 要約・本文
            summary = entry.get('summary', entry.get('description', '')).strip()
            
            # 公開日時
            published = self._parse_published_date(entry)
            
            # 記事のハッシュを生成（重複チェック用）
            article_hash = self._generate_hash(title, link)
            
            # 記事データ
            article = {
                'title': title,
                'link': link,
                'summary': summary,
                'published': published,
                'published_str': published.strftime('%Y-%m-%d %H:%M:%S') if published else None,
                'source': source_name,
                'category': category,
                'hash': article_hash,
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return article
            
        except Exception as e:
            print(f"⚠️ エントリー解析エラー: {e}")
            return None
    
    def _parse_published_date(self, entry) -> Optional[datetime]:
        """公開日時をパース"""
        
        # published_parsed を優先
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                return datetime(*entry.published_parsed[:6])
            except:
                pass
        
        # updated_parsed を次に試す
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                return datetime(*entry.updated_parsed[:6])
            except:
                pass
        
        # パースできない場合は現在時刻
        return datetime.now()
    
    def _generate_hash(self, title: str, link: str) -> str:
        """記事のハッシュを生成（重複チェック用）"""
        
        content = f"{title}_{link}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def fetch_all_feeds(self) -> List[Dict]:
        """
        全てのRSSフィードを取得
        
        Returns:
            list: 全ニュース記事のリスト
        """
        
        print("\n" + "="*60)
        print("📰 ニュース収集開始")
        print("="*60 + "\n")
        
        all_articles = []
        
        for feed_id, feed_info in self.feed_sources.items():
            articles = self.fetch_feed(
                feed_info['url'],
                feed_info['name'],
                feed_info['category']
            )
            
            all_articles.extend(articles)
            
            # 負荷軽減のため少し待機
            time.sleep(1)
        
        print(f"\n✅ 合計 {len(all_articles)} 件のニュース取得完了")
        
        return all_articles
    
    def remove_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """
        重複記事を削除
        
        Args:
            articles: 記事リスト
        
        Returns:
            list: 重複削除後の記事リスト
        """
        
        print("\n🔍 重複記事をチェック中...")
        
        unique_articles = []
        seen_hashes = set()
        
        for article in articles:
            article_hash = article['hash']
            
            if article_hash not in seen_hashes:
                unique_articles.append(article)
                seen_hashes.add(article_hash)
        
        removed_count = len(articles) - len(unique_articles)
        
        if removed_count > 0:
            print(f"✅ {removed_count} 件の重複記事を削除")
        else:
            print("✅ 重複記事なし")
        
        return unique_articles
    
    def filter_by_time(
        self,
        articles: List[Dict],
        hours: int = 24
    ) -> List[Dict]:
        """
        指定時間内の記事のみをフィルタリング
        
        Args:
            articles: 記事リスト
            hours: 何時間以内の記事か
        
        Returns:
            list: フィルタリング後の記事リスト
        """
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered = [
            article for article in articles
            if article['published'] and article['published'] >= cutoff_time
        ]
        
        print(f"🕐 過去{hours}時間以内の記事: {len(filtered)} 件")
        
        return filtered
    
    def sort_by_published(
        self,
        articles: List[Dict],
        reverse: bool = True
    ) -> List[Dict]:
        """
        公開日時で記事をソート
        
        Args:
            articles: 記事リスト
            reverse: True=新しい順, False=古い順
        
        Returns:
            list: ソート済み記事リスト
        """
        
        return sorted(
            articles,
            key=lambda x: x['published'] if x['published'] else datetime.min,
            reverse=reverse
        )
    
    def filter_by_keywords(
        self,
        articles: List[Dict],
        keywords: List[str],
        exclude: bool = False
    ) -> List[Dict]:
        """
        キーワードで記事をフィルタリング
        
        Args:
            articles: 記事リスト
            keywords: キーワードリスト
            exclude: True=除外, False=含む記事のみ
        
        Returns:
            list: フィルタリング後の記事リスト
        """
        
        if not keywords:
            return articles
        
        filtered = []
        
        for article in articles:
            text = f"{article['title']} {article['summary']}".lower()
            
            has_keyword = any(keyword.lower() in text for keyword in keywords)
            
            if (has_keyword and not exclude) or (not has_keyword and exclude):
                filtered.append(article)
        
        keyword_str = ', '.join(keywords)
        action = "除外" if exclude else "含む"
        print(f"🔍 キーワード「{keyword_str}」を{action}記事: {len(filtered)} 件")
        
        return filtered
    
    def get_stock_related_news(
        self,
        hours: int = 24,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        株式関連ニュースを取得（メイン処理）
        
        Args:
            hours: 何時間以内のニュースか
            limit: 取得件数上限（Noneは無制限）
        
        Returns:
            list: ニュース記事リスト（整理済み）
        """
        
        # 全フィード取得
        articles = self.fetch_all_feeds()
        
        # 重複削除
        articles = self.remove_duplicates(articles)
        
        # 時間でフィルタリング
        articles = self.filter_by_time(articles, hours=hours)
        
        # 新しい順にソート
        articles = self.sort_by_published(articles, reverse=True)
        
        # 件数制限
        if limit and len(articles) > limit:
            articles = articles[:limit]
            print(f"📊 上位 {limit} 件に絞り込み")
        
        return articles
    
    def format_article(self, article: Dict) -> str:
        """
        記事を見やすく整形
        
        Args:
            article: 記事データ
        
        Returns:
            str: 整形されたテキスト
        """
        
        return (
            f"📰 {article['title']}\n"
            f"   ソース: {article['source']}\n"
            f"   カテゴリ: {article['category']}\n"
            f"   公開: {article['published_str']}\n"
            f"   URL: {article['link']}\n"
            f"   要約: {article['summary'][:100]}...\n"
        )
    
    def get_summary_stats(self, articles: List[Dict]) -> Dict:
        """
        記事の統計情報を取得
        
        Args:
            articles: 記事リスト
        
        Returns:
            dict: 統計情報
        """
        
        stats = {
            'total': len(articles),
            'by_source': {},
            'by_category': {},
            'latest': None,
            'oldest': None
        }
        
        if not articles:
            return stats
        
        # ソース別
        for article in articles:
            source = article['source']
            stats['by_source'][source] = stats['by_source'].get(source, 0) + 1
        
        # カテゴリ別
        for article in articles:
            category = article['category']
            stats['by_category'][category] = stats['by_category'].get(category, 0) + 1
        
        # 最新・最古
        sorted_articles = self.sort_by_published(articles, reverse=True)
        stats['latest'] = sorted_articles[0]['published_str'] if sorted_articles else None
        stats['oldest'] = sorted_articles[-1]['published_str'] if sorted_articles else None
        
        return stats


# テスト・デモ用
if __name__ == "__main__":
    print("="*70)
    print("📰 News Aggregator テスト")
    print("="*70)
    
    # インスタンス作成
    aggregator = NewsAggregator()
    
    # ニュース取得（過去24時間、上位10件）
    articles = aggregator.get_stock_related_news(hours=24, limit=10)

    # # 15時以降のみフィルタリング
    # after_market_articles = [
    #     article for article in articles
    #     if article['published'].time() >= time(15, 0)
    # ]
    
    # 統計情報
    stats = aggregator.get_summary_stats(articles)
    
    print("\n" + "="*70)
    print("📊 取得結果サマリー")
    print("="*70)
    
    print(f"\n合計記事数: {stats['total']} 件")
    
    print(f"\n【ソース別】")
    for source, count in stats['by_source'].items():
        print(f"  - {source}: {count}件")
    
    print(f"\n【カテゴリ別】")
    for category, count in stats['by_category'].items():
        print(f"  - {category}: {count}件")
    
    if stats['latest'] and stats['oldest']:
        print(f"\n最新記事: {stats['latest']}")
        print(f"最古記事: {stats['oldest']}")
    
    # 記事の詳細表示
    print("\n" + "="*70)
    print("📰 取得記事一覧（上位5件）")
    print("="*70 + "\n")
    
    for i, article in enumerate(articles[:5], 1):
        print(f"【記事 {i}】")
        print(aggregator.format_article(article))
        print()
    
    # キーワードフィルタリングのテスト
    print("\n" + "="*70)
    print("🔍 キーワードフィルタリングテスト")
    print("="*70 + "\n")
    
    # 「株価」「日経」を含む記事
    stock_articles = aggregator.filter_by_keywords(
        articles,
        keywords=['株価', '日経', '市場']
    )
    
    print(f"\n株式関連キーワードを含む記事: {len(stock_articles)} 件")
    
    if stock_articles:
        print("\n【サンプル】")
        print(aggregator.format_article(stock_articles[0]))
