import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from typing import Dict, Optional

class MarketIndexCapturer:
    """
    主要市場の株価指数チャート画像取得と数値データ抽出モジュール
    Yahoo Finance (finance.yahoo.co.jp) を利用
    """

    # 各市場のYahoo Finance URLと表示名とセレクタ情報
    MARKET_INFO = {
        "NIKKEI": {"ticker": "998407.O", "name": "日経平均", "url": "https://finance.yahoo.co.jp/quote/998407.O/chart",
                   "selectors": {
                       "value_area": ".PriceBoard__priceInformation__78Tl",
                       "current_price": ".PriceBoard__price__1V0k .StyledNumber__value__3rXW",
                       "change": ".PriceChangeLabel__primary__Y_ut .StyledNumber__value__3rXW",
                       "change_percent": ".PriceChangeLabel__secondary__3BXI .StyledNumber__value__3rXW"
                   }
                  },
        "SP500": {"ticker": "^GSPC", "name": "S&P500", "url": "https://finance.yahoo.co.jp/quote/%5EGSPC/chart",
                  "selectors": {
                      "value_area": "._BasePriceBoard__priceInformation_1tkwp_22",
                      "current_price": "._CommonPriceBoard__price_1g7gt_64 ._StyledNumber__value_1arhg_9",
                      "change": "._PriceChangeLabel__primary_hse06_56 ._StyledNumber__value_1arhg_9",
                      "change_percent": "._PriceChangeLabel__secondary_hse06_62 ._StyledNumber__value_1arhg_9"
                  }
                 },
        "DOW": {"ticker": "^DJI", "name": "ダウ平均", "url": "https://finance.yahoo.co.jp/quote/%5EDJI/chart",
                "selectors": {
                    "value_area": "._BasePriceBoard__priceInformation_1tkwp_22",
                    "current_price": "._CommonPriceBoard__price_1g7gt_64 ._StyledNumber__value_1arhg_9",
                    "change": "._PriceChangeLabel__primary_hse06_56 ._StyledNumber__value_1arhg_9",
                    "change_percent": "._PriceChangeLabel__secondary_hse06_62 ._StyledNumber__value_1arhg_9"
                }
               },
        "NASDAQ": {"ticker": "^IXIC", "name": "ナスダック", "url": "https://finance.yahoo.co.jp/quote/%5EIXIC/chart",
                   "selectors": {
                       "value_area": "._BasePriceBoard__priceInformation_1tkwp_22",
                       "current_price": "._CommonPriceBoard__price_1g7gt_64 ._StyledNumber__value_1arhg_9",
                       "change": "._PriceChangeLabel__primary_hse06_56 ._StyledNumber__value_1arhg_9",
                       "change_percent": "._PriceChangeLabel__secondary_hse06_62 ._StyledNumber__value_1arhg_9"
                   }
                  },
        "USDJPY": {"ticker": "JPY=X", "name": "ドル円", "url": "https://finance.yahoo.co.jp/quote/JPY=X/chart", # ドル円はyfinanceで数値取得、チャート画像は不要
                   "selectors": {
                       "value_area": None,
                       "current_price": None,
                       "change": None,
                       "change_percent": None
                   }
                  },
    }

    def __init__(self, output_dir: str = "output/market_charts"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Selenium WebDriverのオプション設定
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--window-size=1600,900') # チャートが見える適切なサイズ
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--no-sandbox') # Dockerなどで実行する場合に必要
        self.chrome_options.add_argument('--disable-dev-shm-usage') # Dockerなどで実行する場合に必要
        
        # WebDriverManagerで自動的にドライバーをダウンロード・設定
        self.service = Service(ChromeDriverManager().install())

    def _get_driver(self):
        """WebDriverのインスタンスを返す"""
        return webdriver.Chrome(service=self.service, options=self.chrome_options)

    def _get_yfinance_data(self, ticker: str) -> Optional[Dict]:
        """
        yfinanceから株価データを取得するヘルパーメソッド
        """
        try:
            import yfinance as yf # yfinanceをここでインポート
            stock = yf.Ticker(ticker)
            # 警告回避のため、明示的に期間を指定
            hist = stock.history(period='5d')
            
            if hist.empty:
                print(f"    ⚠️ yfinanceデータなし: {ticker}")
                return None
            
            # yfinance内部での Timestamp.utcnow() 警告を回避するため、
            # 取得したデータのインデックスを naive に変換して処理
            current = hist['Close'].iloc[-1]
            previous = hist['Close'].iloc[-2] if len(hist) >= 2 else current
            
            change = current - previous
            change_percent = (change / previous * 100) if previous != 0 else 0
            
            # タイムスタンプの整形
            last_ts = hist.index[-1]
            ts_str = last_ts.strftime('%Y-%m-%d %H:%M:%S')
            
            return {
                'current': round(float(current), 2),
                'change': round(float(change), 2),
                'change_percent': round(float(change_percent), 2),
                'timestamp': ts_str
            }
        except Exception as e:
            print(f"    ❌ yfinanceデータ取得エラー ({ticker}): {e}")
            return None

    def capture_chart_and_data(
        self,
        market_key: str, # NIKKEI, SP500, DOW, NASDAQ, USDJPY
        chart_selector: str = "#chart", # チャート部分のセレクタをid="chart"に修正
        value_area_selector: str = ".PriceBoard__priceInformation__78Tl", # 現在値、前日比などが表示されている大枠のセレクタ
        wait_time: int = 5
    ) -> Optional[Dict]:
        """
        指定された市場のチャート画像と数値データを取得
        Returns:
            dict: {'market': str, 'chart_image_path': str, 'current_price': str, 'change': str, 'change_percent': str, 'collected_at': str}
        """
        market_info = self.MARKET_INFO.get(market_key)
        if not market_info:
            print(f"❌ 不明な市場キー: {market_key}")
            return None

        # ドル円の場合はyfinanceで取得し、Seleniumはスキップ
        if market_key == "USDJPY":
            yfinance_data = self._get_yfinance_data(market_info["ticker"])
            if yfinance_data:
                return {
                    "market": market_key,
                    "name": market_info["name"],
                    "chart_image_path": None, # チャート画像は不要
                    "current_price": str(yfinance_data['current']),
                    "change": str(yfinance_data['change']),
                    "change_percent": str(yfinance_data['change_percent']),
                    "collected_at": yfinance_data['timestamp']
                }
            else:
                return None
        
        # 市場ごとのセレクタを取得
        selectors = market_info["selectors"]
        current_value_area_selector = selectors["value_area"]
        current_price_selector = selectors["current_price"]
        change_selector = selectors["change"]
        change_percent_selector = selectors["change_percent"]

        driver = self._get_driver()
        try:
            print(f"🌐 {market_info['name']} チャートページにアクセス中: {market_info['url']}")
            driver.get(market_info['url'])
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, chart_selector)))
            
            # チャートの描画完了を待つために少し待機
            time.sleep(3)

            # チャート部分のスクリーンショット
            chart_elem = driver.find_element(By.CSS_SELECTOR, chart_selector)
            filename = f"{market_key.lower()}_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(self.output_dir, filename)
            chart_elem.screenshot(filepath)
            print(f"✅ {market_info['name']} チャート画像保存: {filepath}")

            # 数値データのスクレイピング
            soup = BeautifulSoup(driver.page_source, 'lxml')
            current_price = "-"
            change = "-"
            change_percent = "-"
            
            # 数値データが格納されている要素を特定
            value_area = soup.select_one(current_value_area_selector)
            if value_area:
                # 現在値
                price_elem = value_area.select_one(current_price_selector)
                if price_elem:
                    current_price = price_elem.get_text(strip=True)
                
                # 前日比
                change_elem = value_area.select_one(change_selector)
                if change_elem:
                    change = change_elem.get_text(strip=True)
                
                # 変化率
                change_percent_elem = value_area.select_one(change_percent_selector)
                if change_percent_elem:
                    change_percent = change_percent_elem.get_text(strip=True)

            else:
                print(f"⚠️ {market_info['name']} の数値データエリアが見つかりませんでした。")

            return {
                "market": market_key,
                "name": market_info['name'],
                "chart_image_path": filepath,
                "current_price": current_price,
                "change": change,
                "change_percent": change_percent,
                "collected_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            print(f"❌ {market_info['name']} データ取得中にエラーが発生しました: {e}")
            return None
        finally:
            driver.quit()

    def capture_all_market_charts_and_data(self, video_type: str = "evening") -> Dict:
        """
        全ての主要市場のチャート画像と数値データを一括取得
        Args:
            video_type: "morning" または "evening"
        Returns:
            dict: 各市場ごとのデータをまとめた辞書
        """
        if video_type == "morning":
            all_market_data = {}
            for key in self.MARKET_INFO:
                # 朝動画用はSP500, DOW, NASDAQのみ取得
                if key not in ["SP500", "DOW", "NASDAQ"]:
                    continue
                data = self.capture_chart_and_data(key)
                if data:
                    all_market_data[key] = data
        else:
            all_market_data = {}
            # 夜動画用は NIKKEI, SP500 の順で取得
            for key in ["NIKKEI", "SP500"]:
                data = self.capture_chart_and_data(key)
                if data:
                    all_market_data[key] = data
        return all_market_data


# デモ実行
if __name__ == '__main__':
    capturer = MarketIndexCapturer()
    print("\n" + "="*50)
    print("📊 主要市場データ＆チャート取得開始")
    print("="*50 + "\n")

    all_data = capturer.capture_all_market_charts_and_data()

    print("\n" + "="*50)
    print("✅ 取得結果サマリー")
    print("="*50 + "\n")
    for market_key, data in all_data.items():
        print(f"【{data['name']}】")
        print(f"  現在値: {data['current_price']}")
        print(f"  前日比: {data['change']} ({data['change_percent']}) ")
        if data['chart_image_path']:
            print(f"  チャート画像: {data['chart_image_path']}")
        else:
            print(f"  チャート画像: (取得なし)")
        print()
