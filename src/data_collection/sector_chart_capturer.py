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
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

from src.video_generation.table_image_generator import TableImageGenerator

class SectorChartCapturer:
    """
    業種別指数ページのチャート画像保存＆主要データ取得
    """
    JP_SECTOR_RANKING_URL = "https://nikkei225jp.com/chart/gyoushu.php"
    US_SECTOR_RANKING_URL = "https://jp.tradingview.com/markets/stocks-usa/sectorandindustry-sector/"

    def __init__(self, output_dir: str = "output/sector_charts"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.table_generator = TableImageGenerator(output_dir=self.output_dir)

    def fetch_index_ranking(self, video_type: str = "evening") -> Dict:
        """
        業種別株価指数ランキング（値上がりTOP10・値下がりTOP10）を取得
        （SeleniumでページをレンダリングしてからBeautifulSoupで解析）
        Args:
            video_type: "morning" または "evening"
        Returns:
            dict: {"top": [...], "bottom": [...], "collected_at": ...}
        """
        if video_type == "morning":
            url = self.US_SECTOR_RANKING_URL
            # 修正: データの入っていない固定ヘッダー用テーブルを避けるため、クラス名の一部で柔軟にマッチング
            target_selector = "div[class*='tableWrap-'] table[class*='table-']"
        else:
            url = self.JP_SECTOR_RANKING_URL
            target_selector = "gyornk"

        if video_type == "morning":
            # TradingViewの業種テーブルから10業種を%でソートして上・下位5件ずつ取得する
            result = {"top": [], "bottom": []}
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1800,2000')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ja-JP')
            chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ja,ja-JP'})
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            try:
                driver.get(url)
                wait = WebDriverWait(driver, 15)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, target_selector)))
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, 'lxml')
                table = soup.select_one(target_selector)
                
                if not table:
                    print(f"⚠️ 米国セクターランキングのテーブルが見つかりませんでした。")
                    return result
                
                # すべての tr を取得してから td を持つもの（データ行）に絞り込む
                all_rows = table.find_all("tr")
                rows = [r for r in all_rows if r.find_all("td")]
                print(f"🔍 取得したデータ行数: {len(rows)}")

                sector_list = []
                for i, row in enumerate(rows):
                    cells = row.find_all("td")
                    if len(cells) < 4:
                        continue
                    # セクター名
                    a = cells[0].find("a")
                    sector = a.get_text(strip=True) if a else cells[0].get_text(strip=True)
                    # 変動%
                    change_span = cells[3].find("span")
                    change_text = change_span.get_text(strip=True) if change_span else cells[3].get_text(strip=True)
                    # +1.23% 形式なので、+/-除去してfloat化
                    try:
                        change_val = float(change_text.replace("+", "").replace("−", "-").replace("%", "").replace("–", "-"))
                    except Exception:
                        change_val = None
                    # 時価総額などは必要であれば同様に取得できる
                    sector_list.append({
                        "sector": sector,
                        "change": change_val,
                        "change_text": change_text
                    })
                # changeで降順→上位5件がトップ, 昇順→下位5件がボトム
                sorted_sectors = sorted([s for s in sector_list if s["change"] is not None], key=lambda x: x["change"], reverse=True)
                result["top"] = sorted_sectors[:5]
                result["bottom"] = sorted_sectors[-5:][::-1]  # 下位5件は負方向
            finally:
                driver.quit()
            
        else:
            result = {"top": [], "bottom": []}
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1800,2000') # 十分なサイズを確保
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--lang=ja-JP')
            chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ja,ja-JP'})

            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            try:
                driver.get(url)
                time.sleep(5)
                
                soup = BeautifulSoup(driver.page_source, 'lxml')
                table = soup.find('table', {'id': target_selector})
                
                if not table:
                    print(f"⚠️ {target_selector}テーブルが見つかりませんでした。")
                    return result

                tds = table.find_all('td', class_='tptd')
                if len(tds) < 2:
                    print("⚠️ 値上がり/値下がりランキングのtd要素が見つかりませんでした。")
                    return result

                for idx, key in enumerate(["top", "bottom"]):
                    this_td = tds[idx]
                    inner_table = this_td.find('table')
                    if not inner_table:
                        print(f"⚠️ {key}ランキングのinner_tableが見つかりませんでした。")
                        continue
                    rows = inner_table.find_all('tr', class_='trG')
                    for row in rows:
                        cell = row.find('td')
                        if not cell:
                            continue

                        change_val = None
                        change_div = cell.find('div', class_="perG")
                        if change_div:
                            change = change_div.get_text("", strip=True).replace("▲", "+").replace("▼", "-")
                            try:
                                change_val = float(change.replace("%", "").replace(",", ""))
                            except ValueError:
                                change_val = None # 変換失敗時はNone

                        sector = ""
                        s = cell.find('span', class_='texG')
                        if s:
                            sector = s.get_text(strip=True)

                        index = ""
                        v = cell.find('div', class_='valG')
                        if v:
                            index = v.get_text(strip=True)

                        result[key].append({
                            "sector": sector,
                            "change": change_val,
                            "index_value": index
                        })
            finally:
                driver.quit()

        result["collected_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return result

    def save_chart_screenshot(self, video_type: str = "evening", filename: Optional[str] = None, wait_sec: int = 5):
        """
        業種別指数ランキングのテーブル部分のみスクリーンショット
        Args:
            video_type: "morning" または "evening"
        """
        if video_type == "morning":
            url = self.US_SECTOR_RANKING_URL
            # 修正: スクショもデータ本体のテーブルをターゲットにする
            target_selector = ".tableWrap-nKRZ9M5o table.table-Ngq2xrcG"
        else:
            url = self.JP_SECTOR_RANKING_URL
            target_selector = "#gyornk"
        if filename is None:
            dt = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sector_chart_{video_type}_{dt}.png"
        filepath = os.path.join(self.output_dir, filename)

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--window-size=1800,2000')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ja-JP')
        chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ja,ja-JP'})

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        try:
            print(f"🌐 セクターランキングページにアクセス中: {url}")
            driver.get(url)
            
            # 修正: WebDriverWaitを使用して要素が出現するまで待機
            wait = WebDriverWait(driver, 15)
            try:
                elem = driver.find_element(By.CSS_SELECTOR, target_selector)
                elem.screenshot(filepath)
                print(f"✅ 部分スクリーンショット保存: {filepath}")
            except Exception as e:
                print(f"❌ 要素 {target_selector} の待機中にタイムアウトしました: {e}")
                raise
        finally:
            driver.quit()
        return filepath

    def capture_ranking_with_screenshot(self, video_type: str = "evening") -> Dict:
        """
        ランキングJSON+テーブル部分スクリーンショットをまとめて返す
        Args:
            video_type: "morning" または "evening"
        Returns:
            dict: {'screenshot': png_path, 'ranking': ranking_dict, 'collected_at': ...}
        """
        ranking = self.fetch_index_ranking(video_type=video_type)
        
        if video_type == "morning":
            # 朝動画の場合は、スクショの代わりに（または補完として）表画像を生成する
            print("📊 米国セクター騰落率の表画像を生成中...")
            
            # TOP5とBOTTOM5を結合して1つの表にする
            combined_data = []
            for s in ranking.get("top", []):
                combined_data.append({**s, "type": "値上がり"})
            for s in ranking.get("bottom", []):
                combined_data.append({**s, "type": "値下がり"})
            
            dt = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sector_table_morning_{dt}.png"
            
            img_path = self.table_generator.generate_table_image(
                data=combined_data,
                title="米国市場 セクター別騰落率 (TOP5 / BOTTOM5)",
                filename=filename,
                columns=['sector', 'change_text'],
                column_mapping={'sector': 'セクター', 'change_text': '騰落率'}
            )
            
            # もしスクショも撮りたい場合は、ここで save_chart_screenshot を呼ぶことも可能
            # 現状は表画像のみを返す
        else:
            # 夜動画（日本市場）は従来通りスクショを撮る
            img_path = self.save_chart_screenshot(video_type=video_type)
            
        return {
            'screenshot': img_path,
            'ranking': ranking,
            'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

# デモ実行
if __name__ == '__main__':
    # 業種別株価指数ランキング（値上がりTOP10・値下がりTOP10）を取得
    capturer = SectorChartCapturer()
    img_path = capturer.save_chart_screenshot(target_selector='#gyornk')
    ranking = capturer.fetch_index_ranking()
    top_bottom_result = {
        'screenshot': img_path,
        'ranking': ranking,
        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    # top_bottom_result = capturer.capture_ranking_with_screenshot()
    print("\n【値上がり率TOP10】")
    for d in top_bottom_result['ranking']['top']:
        print(f"{d['sector']} : {d['change']}% 指数:{d['index_value']}")
    print("\n【値下がり率TOP10】")
    for d in top_bottom_result['ranking']['bottom']:
        print(f"{d['sector']} : {d['change']}% 指数:{d['index_value']}")
    print(f"\nテーブル領域スクリーンショット: {top_bottom_result['screenshot']}")

    # 業種別株価指数ランキング（変化率一覧）を取得
    # img_path = capturer.save_chart_screenshot(target_selector='#gtbl')
    # print(img_path)
    # ranking = capturer.fetch_index_ranking()
    # change_rate_result = {
    #     'screenshot': img_path,
    #     'ranking': ranking,
    #     'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # }
