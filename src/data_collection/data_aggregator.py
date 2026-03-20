import os
from datetime import datetime
from src.data_collection.market_data_collector import MarketDataCollector
from src.data_collection.llm_news_collector import LlmNewsCollector
from src.data_collection.ir_event_collector import IrEventCollector
from src.video_generation.table_image_generator import TableImageGenerator
from src.data_collection.stock_chart_capturer import StockChartCapturer # 追加
import json
import sys
import re # 追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.data_collection.previous_videos import load_latest_metadata, save_video_metadata
from src.data_collection.ir_movement_analyzer import IRMovementAnalyzer

class DataAggregator:
    def __init__(self, output_dir="data/collected_data"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.market_collector = MarketDataCollector()
        self.news_collector = LlmNewsCollector()
        self.ir_collector = IrEventCollector()
        self.table_image_generator = TableImageGenerator()
        self.stock_chart_capturer = StockChartCapturer() # 追加

    def _get_companies_for_sector(self, sector_name: str, num_companies: int = 3) -> list[dict]: # 戻り値の型を修正
        """
        LLMを使用して指定されたセクターの主要企業名と銘柄コードのリストを生成する。
        """
        print(f"LLMで'{sector_name}'セクターの主要企業名と銘柄コードを生成中...")
        # プロンプトを修正して銘柄コードも要求
        prompt = f"日本の株式市場における'{sector_name}'セクターの代表的な主要企業を{num_companies}社、会社名とその銘柄コード（例: トヨタ(7203.T)）の形式で、各企業を新しい行で区切って教えてください。余計な記号や前置きは付けないでください。"
        try:
            response_dict = self.news_collector.gemini_client.generate_content_with_search(
                prompt=prompt
            )
            print(response_dict) # 後で消す
            response_text = response_dict.get("text")

            companies_with_tickers = []
            if response_text:
                for line in response_text.split('\n'):
                    line = line.strip()
                    # 例: 1. トヨタ(7203.T) の形式から抽出
                    match = re.search(r'([0-9]+\.\s*)?(.+?)\((\d{4}\.T)\)', line) # 正規表現を追加
                    if match:
                        company_name = match.group(2).strip()
                        ticker = match.group(3).strip()
                        companies_with_tickers.append({"name": company_name, "ticker": ticker})
                    # elif line: # マッチしない行もとりあえず追加しておく（後で調整）
                    #     companies_with_tickers.append({"name": line, "ticker": None}) # ティッカーが取得できない場合
                # 重複を削除し、指定数に制限
                # ティッカーが異なる場合は別企業とみなすため、nameとtickerのペアで重複判定
                unique_companies = []
                seen = set()
                for company in companies_with_tickers:
                    key = (company["name"], company["ticker"])
                    if key not in seen:
                        unique_companies.append(company)
                        seen.add(key)
                companies_with_tickers = unique_companies[:num_companies]
            print(companies_with_tickers)
            return companies_with_tickers
        except Exception as e:
            print(f"'{sector_name}'セクターの企業名と銘柄コード生成中にエラーが発生しました: {e}")
            return []

    def _filter_important_ir_events(self, events: list[dict], event_type: str, limit: int = 8) -> list[dict]:
        """
        LLMを使用して、収集されたIRイベントの中から重要なもの（時価総額が大きい、注目度が高いなど）を厳選する。
        """
        if not events:
            return []
        
        print(f"LLMで重要な{event_type}を厳選中（全{len(events)}件 -> 最大{limit}件）...")
        
        # イベントのリストをテキスト形式にまとめる
        events_summary = "\n".join([f"- {e['company']} ({e['security_code']}): {e['industry']}" for e in events])
        
        prompt = f"""以下の日本の株式市場における{event_type}予定リストの中から、投資家にとって特に重要と思われる企業を最大{limit}社厳選し、その「証券コード」のみをカンマ区切りで返してください。
選定基準：時価総額が大きい、業界大手である、または市場への影響力が強い企業を優先してください。余計な説明は一切不要です。

リスト：
{events_summary}
"""
        try:
            # Geminiを使用して厳選
            response_text = self.news_collector.gemini_client.generate_content(prompt=prompt, use_search=False)
            
            # カンマ区切りの証券コードを抽出
            important_codes = [code.strip() for code in re.split(r'[,\s\n]+', response_text) if re.search(r'\d{4}', code)]
            
            # 元のイベントリストから該当するものを抽出（証券コードでマッチング）
            filtered_events = []
            seen_codes = set()
            for code in important_codes:
                # 4桁の数字のみを抽出
                m = re.search(r'(\d{4})', code)
                if m:
                    clean_code = m.group(1)
                    for e in events:
                        if e['security_code'] == clean_code and clean_code not in seen_codes:
                            filtered_events.append(e)
                            seen_codes.add(clean_code)
                            break
            
            # もしLLMの結果が空、または少なすぎる場合のフォールバック
            if not filtered_events:
                print(f"⚠️ LLMによる{event_type}の厳選に失敗したため、先頭のデータを使用します。")
                return events[:limit]
                
            print(f"✅ {len(filtered_events)}件の重要な{event_type}を抽出しました。")
            return filtered_events
        except Exception as e:
            print(f"{event_type}の厳選中にエラーが発生しました: {e}")
            return events[:limit]

    def aggregate_all_data(self, video_type: str = "evening"):
        """
        必要な全てのデータを収集し、集約する。
        Args:
            video_type: "morning" または "evening"
        """
        print(f"データ集約を開始します... (タイプ: {video_type})")
        aggregated_data = {}
        is_morning = "morning" in video_type

        # 1. 市場指標とセクターデータの取得
        print("市場指標とセクターデータを収集中...")
        raw_data = self.market_collector.collect_all(video_type=video_type)
        
        # 注目ニュースをルート直下に移動
        aggregated_data["attention_news"] = raw_data.get("attention_news", [])
        
        # 主要指数のみを market_indices として保持 (旧 market_and_sector)
        aggregated_data["market_indices"] = raw_data.get("market_indices", {})
        
        # セクターランキング情報を一時保持
        sector_rankings_raw = raw_data.get("sector_rankings", {})
        print("市場指標とセクターデータの収集完了。")

        # 2. 注目ニュースの取得完了ログ
        print(f"注目ニュースの取得完了（{len(aggregated_data.get('attention_news', []))}件）")

        # --- 朝動画の場合はここで終了（重い処理をスキップ） ---
        if is_morning:
            # 3. 注目セクターのニュースをLLMで取得 (一括リクエスト)
            print("注目セクターのニュースをLLMで一括取得中...")
            
            ranking_data = sector_rankings_raw.get("ranking", {})
            target_sectors = []
            # 上位・下位からそれぞれ最大3つずつピックアップ
            for sector_info in ranking_data.get("top", [])[:3]:
                target_sectors.append({"name": sector_info.get("sector"), "type": "top", "change": sector_info.get("change")})
            for sector_info in ranking_data.get("bottom", [])[:3]:
                target_sectors.append({"name": sector_info.get("sector"), "type": "bottom", "change": sector_info.get("change")})

            sector_analysis_list = []
            if target_sectors:
                sector_names_str = ", ".join([s["name"] for s in target_sectors if s["name"]])
                prompt = f"""米国の株式市場における、以下のセクターの過去12時間の最新ニュースをそれぞれ3件ずつ、タイトルと要約を含めてJSON形式で教えてください。
    出力は、セクター名をキーとし、その値はニュースのリスト（各ニュースは辞書形式で "title" と "summary" を含む）としてください。余計な説明や```json```などのマークダウンは不要です。

セクターリスト: [{sector_names_str}]

出力例:
{{
    "情報技術": [
        {{
            "title": "エヌビディア、AI需要の底堅さから続伸",
            "summary": "データセンター向けチップの需要拡大が改めて意識され、ハイテク株全体の牽引役となりました。"
        }},
        {{
            "title": "米長期金利の低下が大型ハイテク株の支援材料に",
            "summary": "朝方発表された経済指標を受けて金利が低下。割安感が意識されたマイクロソフトやアップルなど、金利感応度の高い銘柄に買いが先行しました。"
        }}
    ],
    "金融": [
        {{
            "title": "JPモルガンなど大手銀行株が軟調、利下げ観測が重石",
            "summary": "FRBによる早期利下げ観測が強まったことで、利ざや縮小への懸念から売りが優勢となりました。"
        }}
    ]
}}
"""
                try:
                    llm_response = self.news_collector.gemini_client.generate_json_with_search(prompt=prompt)
                    
                    sector_analysis_list = []
                    for sector in target_sectors:
                        sector_name = sector["name"]
                        news = llm_response.get(sector_name, [])
                        sector_analysis_list.append({
                                "sector_name": sector_name,
                                "type": sector["type"],
                                "change": sector["change"],
                                "news": news
                        })
                except Exception as e:
                    print(f"注目セクターの解析データ生成中にエラーが発生しました: {e}")
                
                # セクター分析データを統合
                aggregated_data["sector_analysis"] = {
                    "rankings_screenshot": sector_rankings_raw.get("screenshot"),
                    "sectors": sector_analysis_list
                }
                print("注目セクターの騰落原因分析完了。")

                # 4. 日本市場への波及効果・影響予測
                print("今日の日本市場への波及効果を検索中...")
                try:
                    impact_jp_query = "昨晩の米国市場を受けた今日の日本株展望 注目される日本株の予測（例：エヌビディア高による東エレクへの波及） 為替ドル円の影響 取引戦略"
                    impact_jp_data = self.news_collector.search_news(query=impact_jp_query, num_results=5)
                    aggregated_data["jp_tomorrow_outlook"] = impact_jp_data
                    print("日本市場への影響予測データの取得完了。")
                except Exception as e:
                    print(f"日本市場への影響予測データの取得中にエラー: {e}")
                    aggregated_data["jp_tomorrow_outlook"] = []

        else: # --- 以下、夜動画専用処理 ---
            # 3. 決算発表スケジュールの取得と画像生成
            print("決算発表スケジュールを収集し、画像を生成中...")
            kessan_events_raw = self.ir_collector.fetch_ir_events(event_type='kessan', days_ahead=3)
            if kessan_events_raw["status"] == "success" and kessan_events_raw["data"]:
                # LLMで重要なものに絞り込む
                kessan_events_filtered = self._filter_important_ir_events(kessan_events_raw["data"], "決算発表")
                
                kessan_image_path = self.table_image_generator.generate_table_image(
                    data=kessan_events_filtered,
                    title="直近の注目決算発表スケジュール",
                    filename="kessan_schedule.png"
                )
                aggregated_data["kessan_schedule"] = {
                    "data": kessan_events_filtered,
                    "image_path": kessan_image_path
                }
            else:
                aggregated_data["kessan_schedule"] = {"data": [], "image_path": None}
                print("決算発表のデータまたは画像生成に失敗しました。")
            print("決算発表スケジュールの収集と画像生成完了。")

            # 4. 株主総会スケジュールの取得と画像生成
            print("株主総会スケジュールを収集し、画像を生成中...")
            soukai_events_raw = self.ir_collector.fetch_ir_events(event_type='soukai', days_ahead=3)
            if soukai_events_raw["status"] == "success" and soukai_events_raw["data"]:
                # LLMで重要なものに絞り込む
                soukai_events_filtered = self._filter_important_ir_events(soukai_events_raw["data"], "株主総会")
                
                soukai_image_path = self.table_image_generator.generate_table_image(
                    data=soukai_events_filtered,
                    title="直近の注目株主総会スケジュール",
                    filename="soukai_schedule.png"
                )
                aggregated_data["soukai_schedule"] = {
                    "data": soukai_events_filtered,
                    "image_path": soukai_image_path
                }
            else:
                aggregated_data["soukai_schedule"] = {"data": [], "image_path": None}
                print("株主総会イベントのデータまたは画像生成に失敗しました。")
            print("株主総会スケジュールの収集と画像生成完了。")

            # 5. 注目セクターの主要企業名リストをLLMで生成 (一括リクエスト)
            print("注目セクターの主要企業名と銘柄コードをLLMで一括生成中...")
            
            ranking_data = sector_rankings_raw.get("ranking", {})
            target_sectors = []
            # 上位・下位からそれぞれ最大3つずつピックアップ
            for sector_info in ranking_data.get("top", [])[:3]:
                target_sectors.append({"name": sector_info.get("sector"), "type": "top", "change": sector_info.get("change")})
            for sector_info in ranking_data.get("bottom", [])[:3]:
                target_sectors.append({"name": sector_info.get("sector"), "type": "bottom", "change": sector_info.get("change")})

            sector_analysis_list = []
            if target_sectors:
                sector_names_str = ", ".join([s["name"] for s in target_sectors if s["name"]])
                prompt = f"""日本の株式市場における、以下のセクターの代表的な主要企業をそれぞれ3社、会社名とその銘柄コード（例: トヨタ(7203.T)）の形式でJSON形式で教えてください。
    出力は、セクター名をキーとし、その値は企業のリスト（各企業は辞書形式で "name" と "ticker" を含む）としてください。
    余計な説明や```json```などのマークダウンは不要です。

    セクターリスト: [{sector_names_str}]

    出力例:
    {{
        "非鉄金属": [
            {{"name": "住友電気工業", "ticker": "5802.T"}},
            {{"name": "住友金属鉱山", "ticker": "5713.T"}}
        ],
        "建設業": [
            {{"name": "大林組", "ticker": "1802.T"}},
            {{"name": "鹿島建設", "ticker": "1812.T"}}
        ]
    }}
    """
                try:
                    llm_response = self.news_collector.gemini_client.generate_json_with_search(prompt=prompt)
                    
                    # 全企業のニュースを一括取得するための準備
                    all_companies_for_news = []
                    for sector in target_sectors:
                        sector_name = sector["name"]
                        companies = llm_response.get(sector_name, [])
                        for c in companies:
                            if c.get("name") and c.get("ticker"):
                                all_companies_for_news.append(c)

                    # 全企業のニュースを一括でLLMに問い合わせ
                    all_companies_news = {}
                    if all_companies_for_news:
                        print(f"注目企業（全{len(all_companies_for_news)}社）のニュースを一括取得中...")
                        companies_str = ", ".join([f"{c['name']}({c['ticker']})" for c in all_companies_for_news])
                        news_prompt = f"""以下の企業について、それぞれ過去12時間の最新ニュースを3件ずつ、タイトルと要約を含めてJSON形式で教えてください。
    出力は、提供されたリストの「証券コード（例: 7203.T）」をそのままキーとし、その値はニュースのリスト（各ニュースは辞書形式で "title" と "summary" を含む）としてください。
    銘柄名や余計な文字をキーに含めないでください。
    余計な説明や```json```などのマークダウンは不要です。

    出力例:
    {{
        "7203.T": [
            {{"title": "ニュース見出し1", "summary": "ニュースの要約1"}},
            {{"title": "ニュース見出し2", "summary": "ニュースの要約2"}}
        ],
        "6758.T": [
            {{"title": "ニュース見出しA", "summary": "ニュースの要約A"}}
        ]
    }}

    企業リスト: [{companies_str}]
    """
                        all_companies_news = self.news_collector.gemini_client.generate_json_with_search(prompt=news_prompt)

                    # データを構造化して集約
                    for sector in target_sectors:
                        sector_name = sector["name"]
                        companies_in_sector = llm_response.get(sector_name, [])
                        
                        structured_companies = []
                        for c in companies_in_sector:
                            c_name = c.get("name")
                            c_ticker = c.get("ticker")
                            if c_name and c_ticker:
                                print(f"  企業: {c_name} ({c_ticker}) のチャート取得中...")
                                chart_path = self.stock_chart_capturer.capture_chart_screenshot(c_ticker, c_name)
                                
                                # ニュースは一括取得したものから取得（証券コードをキーに使用）
                                company_news_list = all_companies_news.get(c_ticker, [])
                                
                                structured_companies.append({
                                    "company_name": c_name,
                                    "ticker": c_ticker,
                                    "news": company_news_list,
                                    "chart_image_path": chart_path
                                })
                        
                        sector_analysis_list.append({
                            "sector_name": sector_name,
                            "type": sector["type"],
                            "change": sector["change"],
                            "companies": structured_companies
                        })

                except Exception as e:
                    print(f"注目セクターの解析データ生成中にエラーが発生しました: {e}")
            
            # ブラウザを閉じる
            self.stock_chart_capturer._close_driver()
            
            # セクター分析データを統合
            aggregated_data["sector_analysis"] = {
                "rankings_screenshot": sector_rankings_raw.get("screenshot"),
                "sectors": sector_analysis_list
            }
            print("注目セクターと個別銘柄の構造化データ収集完了。")

            # 7. 前回動画のIR銘柄の動向解析（存在する場合）
            try:
                latest_meta = load_latest_metadata()
                if latest_meta:
                    published_at = latest_meta.get("published_at")
                    prev_ir_stocks = latest_meta.get("ir_stocks", [])
                    if published_at and prev_ir_stocks:
                        print("前回動画のIR銘柄の動向を解析中...")
                        analyzer = IRMovementAnalyzer(
                            market_collector=self.market_collector,
                            ir_collector=self.ir_collector,
                            stock_chart_capturer=self.stock_chart_capturer,
                            news_collector=self.news_collector,
                            output_dir=self.output_dir
                        )
                        prev_ir_analysis = analyzer.analyze_prev_ir_movements(
                            published_at_iso=published_at,
                            ir_stocks=prev_ir_stocks
                        )
                        aggregated_data["prev_ir_analysis"] = prev_ir_analysis
                        print("前回動画のIR銘柄解析完了。")
                    else:
                        aggregated_data["prev_ir_analysis"] = []
                else:
                    aggregated_data["prev_ir_analysis"] = []
            except Exception as e:
                print(f"前回動画のIR銘柄解析中にエラー: {e}")
                aggregated_data["prev_ir_analysis"] = []

            # 8. 今夜の米国市場の見通しと明日の重要イベントを検索（追加）
            print("今夜の米国市場の注目イベントと明日の世界的な重要スケジュールを検索中...")
            try:
                us_outlook_query = "今夜の米国市場 注目指標 決算 経済イベント 予想 日本市場への影響 明日の世界的な重要経済スケジュール"
                us_outlook_data = self.news_collector.search_news(query=us_outlook_query, num_results=5)
                aggregated_data["us_tonight_outlook"] = us_outlook_data
                print("今夜の米国市場見通しの取得完了。")
            except Exception as e:
                print(f"今夜の米国市場見通しの取得中にエラー: {e}")
                aggregated_data["us_tonight_outlook"] = []

            # 9. 今回の注目IR銘柄メタを保存（動画生成時に使用するための永続化）
            try:
                video_meta_ir_stocks = []
                for sector in sector_analysis_list:
                    for st in sector.get("companies", []):
                        video_meta_ir_stocks.append({
                            "name": st.get("company_name"),
                            "ticker": st.get("ticker"),
                            "noted_ir": None,
                            "ir_date": None
                        })
                now_iso = datetime.now().isoformat()
                save_video_metadata(video_id=f"auto_{now_iso}", published_at=now_iso, ir_stocks=video_meta_ir_stocks)
                print("今回の注目IR銘柄メタを保存しました。")
            except Exception as e:
                print(f"今回の注目IR銘柄メタ保存に失敗しました: {e}")

        # 収集したデータをJSONファイルとして保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filepath = os.path.join(self.output_dir, f"aggregated_data_{video_type}_{timestamp}.json")
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(aggregated_data, f, ensure_ascii=False, indent=4)
        print(f"夜動画用データの集約が完了し、'{output_filepath}' に保存されました。")

        return aggregated_data

# デモ実行
if __name__ == "__main__":
    # モジュールパスの設定
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
    if project_root not in sys.path:
        sys.path.append(project_root)

    print("="*50)
    print("📦 Data Aggregator デモ")
    print("="*50)

    aggregator = DataAggregator()
    all_collected_data = aggregator.aggregate_all_data()

    if all_collected_data:
        print("\n--- 集約されたデータの一部表示 ---")
        # 例: 市場指標のサマリーを表示
        if "market_indices" in all_collected_data:
            market_indices = all_collected_data["market_indices"]
            if market_indices and "NIKKEI" in market_indices:
                nikkei_data = market_indices["NIKKEI"]
                print(f"市場指標 (日経平均): {nikkei_data.get('current_price')} ({nikkei_data.get('change')} {nikkei_data.get('change_percent')}%)")
        # 例: ニュースの最初の項目を表示
        if "attention_news" in all_collected_data and all_collected_data["attention_news"]:
            print("ニュースタイトル:", all_collected_data["attention_news"][0].get("title"))
        # 例: 決算発表の画像パスを表示
        if "kessan_schedule" in all_collected_data:
            print("決算発表画像パス:", all_collected_data["kessan_schedule"].get("image_path"))
        # 例: 注目セクターとその企業名を表示
        if "sector_analysis" in all_collected_data:
            print("\n--- 注目セクターと企業名 ---")
            for sector_info in all_collected_data["sector_analysis"]["sectors"]:
                print(f"セクター: {sector_info['sector_name']} (タイプ: {sector_info['type']})")
                for company in sector_info["companies"]:
                    print(f"  企業名: {company.get('name')} (ティッカー: {company.get('ticker')})")
    else:
        print("データの集約に失敗しました。")
