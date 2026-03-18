"""
株価データ取得モジュール
Yahoo Finance から主要な株価データを取得
"""

import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Optional
import time


class StockDataCollector:
    """株価データ収集クラス"""
    
    # ティッカーシンボル定数（海外ティッカーしか引っかからない模様）
    NIKKEI = "^N225"      # 日経平均
    TOPIX = "^TOPX"        # TOPIX https://finance.yahoo.com/quote/%5ETOPX/　どうやら更新されていない模様
    SP500 = "^GSPC"       # S&P 500
    NASDAQ = "^IXIC"      # ナスダック
    DOW = "^DJI"          # ダウ平均
    USDJPY = "JPY=X"      # ドル円
    
    def __init__(self):
        """初期化"""
        self.cache = {}  # キャッシュ（同じデータの重複取得を防ぐ）
        self.cache_timeout = 300  # キャッシュの有効期限（秒）
    
    def get_stock_data(
        self,
        ticker: str,
        period: str = "5d"
    ) -> Optional[Dict]:
        """
        指定したティッカーの株価データを取得
        
        Args:
            ticker: ティッカーシンボル（例: "^N225"）
            period: 取得期間（"1d", "5d", "1mo" など）
        
        Returns:
            dict: 株価データ
                {
                    'ticker': '^N225',
                    'name': '日経平均',
                    'current': 38500.0,
                    'previous': 38200.0,
                    'change': 300.0,
                    'change_percent': 0.785,
                    'timestamp': '2025-11-16 15:00:00'
                }
            失敗時は None
        """
        
        # キャッシュチェック
        cache_key = f"{ticker}_{period}"
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                print(f"📦 キャッシュから取得: {ticker}")
                return cached_data
        
        try:
            print(f"📡 Yahoo Finance からデータ取得中: {ticker}")
            
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            if hist.empty:
                print(f"⚠️ データが空です: {ticker}")
                return None
            
            # 最新の終値と前日の終値を取得
            current_price = hist['Close'].iloc[-1]
            
            if len(hist) >= 2:
                previous_price = hist['Close'].iloc[-2]
            else:
                previous_price = current_price
            
            # 変動額と変動率を計算
            change = current_price - previous_price
            change_percent = (change / previous_price) * 100 if previous_price != 0 else 0
            
            # データをまとめる
            data = {
                'ticker': ticker,
                'name': self._get_ticker_name(ticker),
                'current': round(float(current_price), 2),
                'previous': round(float(previous_price), 2),
                'change': round(float(change), 2),
                'change_percent': round(float(change_percent), 2),
                'timestamp': hist.index[-1].strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # キャッシュに保存
            self.cache[cache_key] = (data, time.time())
            
            return data
            
        except Exception as e:
            print(f"❌ エラー ({ticker}): {e}")
            return None
    
    def get_nikkei(self) -> Optional[Dict]:
        """日経平均を取得"""
        return self.get_stock_data(self.NIKKEI)
    
    def get_topix(self) -> Optional[Dict]:
        """TOPIXを取得"""
        return self.get_stock_data(self.TOPIX)
    
    def get_sp500(self) -> Optional[Dict]:
        """S&P 500を取得"""
        return self.get_stock_data(self.SP500)
    
    def get_nasdaq(self) -> Optional[Dict]:
        """ナスダックを取得"""
        return self.get_stock_data(self.NASDAQ)
    
    def get_dow(self) -> Optional[Dict]:
        """ダウ平均を取得"""
        return self.get_stock_data(self.DOW)
    
    def get_usdjpy(self) -> Optional[Dict]:
        """ドル円レートを取得"""
        return self.get_stock_data(self.USDJPY)
    
    def get_all_market_data(self) -> Dict:
        """
        全ての主要市場データを一括取得
        
        Returns:
            dict: 全市場データ
                {
                    'japan': {...},
                    'us': {...},
                    'forex': {...}
                }
        """
        
        print("\n" + "="*50)
        print("📊 主要市場データ取得開始")
        print("="*50 + "\n")
        
        # 日本市場
        print("🇯🇵 日本市場")
        japan_data = {
            'nikkei': self.get_nikkei(),
            'topix': self.get_topix()
        }
        
        # 米国市場
        print("\n🇺🇸 米国市場")
        us_data = {
            'sp500': self.get_sp500(),
            'nasdaq': self.get_nasdaq(),
            'dow': self.get_dow()
        }
        
        # 為替
        print("\n💱 為替")
        forex_data = {
            'usdjpy': self.get_usdjpy()
        }
        
        all_data = {
            'japan': japan_data,
            'us': us_data,
            'forex': forex_data,
            'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        print("\n✅ データ取得完了")
        
        return all_data
    
    def format_for_display(self, data: Dict) -> str:
        """
        データを見やすく整形
        
        Args:
            data: 株価データ
        
        Returns:
            str: 整形されたテキスト
        """
        
        if not data:
            return "データなし"
        
        sign = "+" if data['change'] >= 0 else ""
        arrow = "📈" if data['change'] >= 0 else "📉"
        
        return (
            f"{arrow} {data['name']}\n"
            f"   現在値: {data['current']:,.2f}\n"
            f"   前日比: {sign}{data['change']:,.2f} ({sign}{data['change_percent']:.2f}%)\n"
            f"   時刻: {data['timestamp']}"
        )
    
    def _get_ticker_name(self, ticker: str) -> str:
        """ティッカーシンボルから日本語名を取得"""
        
        names = {
            self.NIKKEI: "日経平均",
            self.TOPIX: "TOPIX",
            self.SP500: "S&P 500",
            self.NASDAQ: "ナスダック",
            self.DOW: "ダウ平均",
            self.USDJPY: "ドル円"
        }
        
        return names.get(ticker, ticker)
    
    def calculate_market_sentiment(self, market_data: Dict) -> str:
        """
        市場全体のセンチメントを判定
        
        Args:
            market_data: get_all_market_data() の返り値
        
        Returns:
            str: "bullish" (強気), "bearish" (弱気), "neutral" (中立)
        """
        
        changes = []
        
        # 日本市場
        if market_data['japan']['nikkei']:
            changes.append(market_data['japan']['nikkei']['change_percent'])
        
        # 米国市場
        for key in ['sp500', 'nasdaq', 'dow']:
            if market_data['us'][key]:
                changes.append(market_data['us'][key]['change_percent'])
        
        if not changes:
            return "neutral"
        
        avg_change = sum(changes) / len(changes)
        
        if avg_change > 0.5:
            return "bullish"
        elif avg_change < -0.5:
            return "bearish"
        else:
            return "neutral"


# ユーティリティ関数
def format_price(price: float) -> str:
    """価格をカンマ区切りで整形"""
    return f"{price:,.2f}"


def format_change(change: float) -> str:
    """変動額を整形（符号付き）"""
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:,.2f}"


def format_percent(percent: float) -> str:
    """変動率を整形（符号付き）"""
    sign = "+" if percent >= 0 else ""
    return f"{sign}{percent:.2f}%"


# テスト・デモ用
if __name__ == "__main__":
    print("="*60)
    print("📊 Stock Data Collector テスト")
    print("="*60)
    
    # インスタンス作成
    collector = StockDataCollector()
    
    # 個別取得テスト
    print("\n【個別取得テスト】")
    print("-" * 60)
    
    print("\n1. 日経平均")
    nikkei = collector.get_nikkei()
    if nikkei:
        print(collector.format_for_display(nikkei))
    
    print("\n2. S&P 500")
    sp500 = collector.get_sp500()
    if sp500:
        print(collector.format_for_display(sp500))
    
    print("\n3. ドル円")
    usdjpy = collector.get_usdjpy()
    if usdjpy:
        print(collector.format_for_display(usdjpy))
    
    # 一括取得テスト
    print("\n\n【一括取得テスト】")
    print("-" * 60)
    
    all_data = collector.get_all_market_data()
    
    # 結果の表示
    print("\n" + "="*60)
    print("📋 取得結果サマリー")
    print("="*60)
    
    print("\n🇯🇵 日本市場")
    for key, data in all_data['japan'].items():
        if data:
            print(collector.format_for_display(data))
            print()
    
    print("🇺🇸 米国市場")
    for key, data in all_data['us'].items():
        if data:
            print(collector.format_for_display(data))
            print()
    
    print("💱 為替")
    for key, data in all_data['forex'].items():
        if data:
            print(collector.format_for_display(data))
            print()
    
    # センチメント判定
    sentiment = collector.calculate_market_sentiment(all_data)
    sentiment_emoji = {
        "bullish": "🚀",
        "bearish": "📉",
        "neutral": "➡️"
    }
    
    print("="*60)
    print(f"市場センチメント: {sentiment_emoji[sentiment]} {sentiment.upper()}")
    print("="*60)
