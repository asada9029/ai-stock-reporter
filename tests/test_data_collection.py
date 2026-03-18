import yfinance as yf
import feedparser

def test_stock_data():
    """株価データ取得テスト"""
    print("=== 株価データ取得テスト ===")
    
    try:
        # 日経平均
        nikkei = yf.Ticker("^N225")
        data = nikkei.history(period="1d")
        
        if not data.empty:
            close = data['Close'].iloc[-1]
            print(f"✅ 日経平均取得成功: {close:.2f}")
            return True
        else:
            print("❌ データが空です")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

def test_rss_feed():
    """RSSフィード取得テスト"""
    print("\n=== RSSフィード取得テスト ===")
    
    try:
        feed = feedparser.parse(
            'https://news.yahoo.co.jp/rss/topics/business.xml'
        )
        
        if feed.entries:
            print(f"✅ RSS取得成功: {len(feed.entries)}件")
            print(f"最新記事: {feed.entries[0].title}")
            return True
        else:
            print("❌ 記事が取得できません")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

if __name__ == "__main__":
    test_stock_data()
    test_rss_feed()
