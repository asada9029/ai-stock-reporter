import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict

class SectorCrawler:
    """
    業種別指数（33業種）のデータを取得するクローラ
    https://nikkei225jp.com/chart/gyoushu.php
    """
    BASE_URL = "https://nikkei225jp.com/chart/gyoushu.php"

    def fetch_sector_data(self) -> List[Dict]:
        """
        主要業種別データ（業種名・変化率・売買代金・出来高）をリストで返す
        Returns:
            list of dict: 各業種ごとのデータ
        """
        res = requests.get(self.BASE_URL)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, 'html.parser')

        sector_list = []
        # 「業種別指数」テーブルの特定
        table = soup.find('table', {'id': 'gyoushu_list'})
        if not table:
            raise RuntimeError("業種別テーブルが見つかりません")

        for row in table.find_all('tr')[1:]:  # ヘッダー行スキップ
            cols = row.find_all(['td', 'th'])
            if len(cols) < 6:
                continue
            name = cols[0].get_text(strip=True)
            change = cols[2].get_text(strip=True)  # 変化率
            amount = cols[4].get_text(strip=True)  # 売買代金
            volume = cols[5].get_text(strip=True)  # 出来高
            
            # 変化率を数値化
            try:
                change_num = float(change.replace('%','').replace('+','').replace(',',''))
            except:
                change_num = 0.0
            sector_list.append({
                "name": name,
                "change": change_num,
                "amount": amount,
                "volume": volume
            })
        return sector_list

    def get_sector_ranking(self, top_n: int = 3) -> Dict:
        """
        上昇・下落ランキングを抽出（全体リストもセットで返す）
        Returns:
            dict with keys: "top", "bottom", "all", "date"
        """
        all_sectors = self.fetch_sector_data()
        sorted_sectors = sorted(all_sectors, key=lambda x: x['change'], reverse=True)
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top": sorted_sectors[:top_n],
            "bottom": sorted_sectors[-top_n:],
            "all": all_sectors
        }


# デモ用実行（単体テストOK）
if __name__ == '__main__':
    crawler = SectorCrawler()
    ranking = crawler.get_sector_ranking(top_n=5)
    print("\n【業種別指数 上昇TOP5】")
    for s in ranking['top']:
        print(f"{s['name']} : {s['change']}% 売買代金:{s['amount']} 出来高:{s['volume']}")

    print("\n【業種別指数 下落BOTTOM5】")
    for s in ranking['bottom']:
        print(f"{s['name']} : {s['change']}% 売買代金:{s['amount']} 出来高:{s['volume']}")
