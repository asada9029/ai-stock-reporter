import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
import sys

# .envファイルの読み込み（必要に応じて）
load_dotenv()

class StockChartCapturer:
    def __init__(self, output_dir="output/stock_charts"):
        """
        保存先ディレクトリの初期化
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.driver = None
        # CI/headless では要素出現が遅いケースがあるため、待機時間を環境変数で調整可能にする
        self.chart_wait_timeout = int(os.getenv("STOCK_CHART_WAIT_TIMEOUT_SEC", "35"))
        self.chart_render_wait_sec = int(os.getenv("STOCK_CHART_RENDER_WAIT_SEC", "4"))

    def _initialize_driver(self):
        """
        WebDriverの初期化（最新のヘッドレスモードとボット検知回避設定）
        """
        if self.driver:
            return

        chrome_options = Options()
        # 最新のヘッドレスモード（ブラウザを表示させない）
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # 画面サイズ（チャート全体が収まる十分な高さに設定）
        chrome_options.add_argument("--window-size=1280,1200")
        
        # ボット検知回避用：一般的なブラウザのUser-Agentを設定
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def _close_driver(self):
        """
        WebDriverを安全に終了
        """
        if self.driver:
            self.driver.quit()
            self.driver = None

    def capture_chart_screenshot(self, ticker: str, stock_name: str) -> str | None:
        """
        指定した銘柄のチャート部分のみをキャプチャする
        """
        try:
            self._initialize_driver()
            
            # テクニカル指標（移動平均線など）を反映させたURL
            url = f"https://finance.yahoo.co.jp/quote/{ticker}/chart?frm=dly&trm=6m&scl=stndrd&styl=cndl&evnts=volume&ovrIndctr=sma%2Cmma%2Clma"
            
            print(f"--- 取得開始: {stock_name} ({ticker}) ---")
            self.driver.get(url)
            
            # 要素の読み込みを待つ（既定値35秒）
            wait = WebDriverWait(self.driver, self.chart_wait_timeout)
            
            # ユーザーが確認したクラス名を含むセレクタを最優先にする
            selectors = [
                'div[class*="InteractiveChart__"]', # 1FaO などの動的な接尾辞に対応
                'div[class*="_InteractiveChart_"]',
                '#chart',
                'canvas'
            ]
            
            chart_element = None
            for selector in selectors:
                try:
                    chart_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
                    if chart_element:
                        print(f"  - 要素発見: {selector}")
                        break
                except:
                    continue

            if not chart_element:
                print(f"⚠️ チャート要素が見つかりませんでした。ページ全体のスクリーンショットを試みます。")
                # フォールバック：要素が見つからない場合はボディ全体を撮る
                chart_element = self.driver.find_element(By.TAG_NAME, "body")

            # 描画バッファ（これがないとグラフの中身が空になることがあります）
            time.sleep(self.chart_render_wait_sec)

            # チャートを画面中央にスクロール（キャプチャミス防止）
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chart_element)
            time.sleep(1)

            # 保存ファイル名の生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticker}_{stock_name}_{timestamp}.png"
            filepath = os.path.join(self.output_dir, filename)
            
            # 要素単体のスクリーンショットを実行
            chart_element.screenshot(filepath)
            
            print(f"✅ 保存成功: {filepath}")
            return filepath

        except Exception as e:
            print(f"❌ エラーが発生しました ({ticker}): {e}")
            # エラー時はドライバを一旦リセットして次回に備える
            self._close_driver()
            return None
        # DataAggregator側で一括処理が終わった後に閉じるようにするため、ここでは閉じない

# 実行ブロック
if __name__ == "__main__":
    capturer = StockChartCapturer()
    
    # 取得したい銘柄リスト
    stock_list = [
        {"code": "9201.T", "name": "日本航空"},
        {"code": "7203.T", "name": "トヨタ"},
        {"code": "9984.T", "name": "ソフトバンクグループ"}
    ]

    print("🚀 チャートキャプチャ処理を開始します...")
    
    for stock in stock_list:
        path = capturer.capture_chart_screenshot(stock["code"], stock["name"])
        if path:
            print(f"→ 保存完了: {path}")
        else:
            print(f"→ {stock['name']} の取得に失敗しました。")

    print("\n✨ すべての処理が終了しました。")
    