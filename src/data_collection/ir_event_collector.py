import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

class IrEventCollector:
    """
    日経新聞のサイトから決算・株主総会スケジュールを取得するクラス
    """
    def __init__(self):
        self.base_url = "https://www.nikkei.com"

    def _generate_nikkei_url(self, event_type: str, target_date: datetime):
        """
        日経の決算・株主総会スケジュールのURLを生成する。
        """
        year = target_date.year
        month = target_date.month
        day = target_date.day
        
        # 月・日を2桁にフォーマット
        month_str = f"{month:02d}"
        day_str = f"{day:02d}"
        search_date1 = f"{year}年{month_str}"
        search_date2 = day_str
        
        # URLエンコーディングはrequestsが自動で行うため、ここでは未エンコードの文字列で構築
        return f"{self.base_url}/markets/kigyo/money-schedule/{event_type}/?ResultFlag=1&SearchDate1={search_date1}&SearchDate2={search_date2}"

    def fetch_ir_events(self, event_type: str, days_ahead: int = 3):
        """
        日経から指定されたイベントタイプ（決算、株主総会）のIR情報を取得する。
        当日からdays_ahead日後までの情報を取得する。
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) # 時刻情報をクリア
        all_events = []

        for i in range(days_ahead + 1):
            target_date = today + timedelta(days=i)
            url = self._generate_nikkei_url(event_type, target_date)
            print(f"{event_type}情報を取得中 ({target_date.strftime('%Y-%m-%d')}): {url}")

            try:
                response = requests.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'lxml')

                # 提供されたHTML構造に基づいてテーブルを特定
                table = soup.find('table', class_='cmn-table_style2')
                
                if table:
                    rows = table.find_all('tr', class_='tr2') # データ行はclass="tr2"
                    for row in rows:
                        # <th>タグと<td>タグからデータを抽出
                        # 最初の要素は<th>になっているが、後の要素は<td>
                        
                        # 定時株主総会日（または決算発表日）は<th>タグ
                        date_cell = row.find('th')
                        # その他の情報は<td>タグ
                        cols = row.find_all('td')

                        if date_cell and len(cols) >= 5: # 最低限のデータがあることを確認
                            date_str = date_cell.get_text(strip=True)
                            
                            # 日付パースはURL生成時のtarget_dateを使用するため不要
                            # 念のため取得した日付文字列の年を現在の年に合わせる (例: 12/20 -> 2025/12/20)
                            # 厳密には `date_str` をパースして `target_date` と比較すべきだが、
                            # URLで日付を絞っているので、ここでは `target_date` を信頼する。
                            
                            # 証券コード: cols[0] のaタグのテキスト
                            security_code = cols[0].find('a').get_text(strip=True) if cols[0].find('a') else ''
                            # 会社名: cols[1] のaタグのテキスト (class="cam-name")
                            company_name = cols[1].find('a').get_text(strip=True) if cols[1].find('a') else ''
                            # 決算期: cols[3]
                            settlement_term = cols[3].get_text(strip=True)
                            # 業種: cols[4]
                            industry = cols[4].get_text(strip=True)

                            all_events.append({
                                "date": target_date.strftime("%Y-%m-%d"), # URLで指定した日付をそのまま使用
                                "security_code": security_code,
                                "company": company_name,
                                "settlement_term": settlement_term,
                                "industry": industry,
                                "event_type": "決算発表" if event_type == 'kessan' else "株主総会",
                                "source": url
                            })
                else:
                    print(f"警告: {target_date.strftime('%Y-%m-%d')} のテーブルが見つかりませんでした。")

            except requests.exceptions.RequestException as e:
                print(f"ウェブサイトへのアクセス中にエラーが発生しました: {e}")

        return {"status": "success", "data": all_events}

# デモ実行
if __name__ == "__main__":
    print("="*50)
    print("🗓️ IR Event Collector デモ")
    print("="*50)

    collector = IrEventCollector()

    print("\n--- 直近3日間の決算発表 ---")
    kessan_events = collector.fetch_ir_events(event_type='kessan', days_ahead=3)
    if kessan_events["status"] == "success":
        if kessan_events["data"]:
            for event in kessan_events["data"]:
                print(f"日付: {event['date']}, 企業: {event['company']} ({event['security_code']}), 決算期: {event['settlement_term']}, 業種: {event['industry']}, イベント: {event['event_type']}")
        else:
            print("該当する決算発表は見つかりませんでした。")
    else:
        print(f"決算発表の取得失敗: {kessan_events['message']}")

    print("\n--- 直近3日間の株主総会 ---")
    soukai_events = collector.fetch_ir_events(event_type='soukai', days_ahead=3)
    if soukai_events["status"] == "success":
        if soukai_events["data"]:
            for event in soukai_events["data"]:
                print(f"日付: {event['date']}, 企業: {event['company']} ({event['security_code']}), 決算期: {event['settlement_term']}, 業種: {event['industry']}, イベント: {event['event_type']}")
        else:
            print("該当する株主総会は見つかりませんでした。")
    else:
        print(f"株主総会の取得失敗: {soukai_events['message']}")
