"""
統合市場データコレクター
株価、セクター指数、為替など数値データを一括収集
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import requests
from bs4 import BeautifulSoup
import re
import os
from src.data_collection.market_index_capturer import MarketIndexCapturer
from src.data_collection.sector_chart_capturer import SectorChartCapturer
from src.data_collection.llm_news_collector import LlmNewsCollector


class MarketDataCollector:
    """市場データ統合収集クラス"""
    
    # 主要指数のティッカーシンボル
    INDICES = {}

    def __init__(self, output_base_dir: str = "output"):
        """初期化"""
        self.cache = {}
        self.cache_timeout = 300  # 5分
        self.output_base_dir = output_base_dir
        
        # 各モジュールのインスタンスを保持
        self.market_index_capturer = MarketIndexCapturer(output_dir=os.path.join(self.output_base_dir, "market_charts"))
        self.sector_chart_capturer = SectorChartCapturer(output_dir=os.path.join(self.output_base_dir, "sector_charts"))
        self.llm_news_collector = LlmNewsCollector() # LlmNewsCollectorのインスタンスを追加
    
    def collect_all(self, video_type: str = "evening") -> Dict:
        """
        全データを一括収集（AIに渡す用）
        
        Args:
            video_type: "morning" または "evening"
            
        Returns:
            dict: {
                'timestamp': '2025-11-16 15:00:00',
                'market_indices': {
                    'NIKKEI': {...},
                    'DOW': {...},
                    'NASDAQ': {...},
                    'USDJPY': {...}
                },
                'sector_rankings': {
                    'screenshot': {...},
                    'ranking': {...},
                    'collected_at': {...}
                },
                'attention_news': [
                    {'title': '...', 'url': '...', 'snippet': '...', 'source': '...', 'published_at': '...'},
                    ...
                ],
                'upcoming_events': []
            }
        """
        
        print("\n" + "="*70)
        print("📊 市場データ収集開始")
        print("="*70)
        
        if video_type == "morning":
            print("朝動画用の市場データ収集開始...")
            # 1. 主要指数（チャート画像含む）
            print("\n🌍 主要指数＆チャート画像取得中...")
            market_indices_data = self.market_index_capturer.capture_all_market_charts_and_data(video_type=video_type)

            # 2. 業種別ランキング（スクリーンショット含む）
            print("\n📈 業種別ランキング＆スクリーンショット取得中...")
            sector_rankings_data = self.sector_chart_capturer.capture_ranking_with_screenshot(video_type=video_type)

            # 3. 一般ニュースの取得（LLM Web Search）
            print("\n📰 注目ニュース取得中（LLM Web Search）...")
            
            # 月曜日の朝は週末のニュースも含めるように調整
            time_range_str = "過去72時間" if datetime.now().weekday() == 0 else "過去12時間"
            
            attention_news_query = f"""
            {time_range_str}で、米国の株式市場全体に影響を与えそうな重要な経済ニュース、政治ニュース、国際情勢、技術動向に関する米国の一般ニュースを10個教えてください。
            
            【選定基準（重要）】
            - 投資家（株・資産形成層）の「財布に直結する」ニュースを最優先してください。
            - 単なる政治ニュースではなく、「どのセクターが儲かるか」「どの銘柄にチャンスがあるか」などの投資の文脈に直結しそうなものを選んでください。
            - 日本の投資家にも馴染みのある大手企業（NVIDIA, Apple, Tesla等）や、分かりやすい景気動向を優先してください。
            - 専門用語（ISM, CPI等）は、検索結果に含まれていても、後の工程で「物価」「景気」など分かりやすい言葉に翻訳できるよう、内容を詳しく把握しておいてください。
            """
            attention_news_data = self.llm_news_collector.search_news(query=attention_news_query, num_results=10)

        else:
            print("夜動画用の市場データ収集開始...")
            # 1. 主要指数（チャート画像含む）
            print("\n🌍 主要指数＆チャート画像取得中...")
            market_indices_data = self.market_index_capturer.capture_all_market_charts_and_data(video_type=video_type)
            
            # 2. 業種別ランキング（スクリーンショット含む）
            print("\n📈 業種別ランキング＆スクリーンショット取得中...")
            sector_rankings_data = self.sector_chart_capturer.capture_ranking_with_screenshot(video_type=video_type)

            # 3. 一般ニュースの取得（LLM Web Search）
            print("\n📰 注目ニュース取得中（LLM Web Search）...")
            attention_news_query = """
            過去12時間で、日本の株式市場全体に影響を与えそうな重要な経済ニュース、政治ニュース、国際情勢、技術動向に関する一般ニュースを10個教えてください。
            
            【選定基準（重要）】
            - 投資家（株・資産形成層）の「財布に直結する」ニュースを最優先してください。
            - 「どのセクターが儲かるか」「どの銘柄にチャンスがあるか」などの投資の文脈に直結しそうなものを選んでください。
            - 日本の投資家が関心の高い話題（円安・円高の影響、大手企業の決算、政府の経済対策、半導体関連など）を優先してください。
            - 専門用語（日銀短観、GDP等）は、検索結果に含まれていても、後の工程で「景気」「国の成長」など分かりやすい言葉に翻訳できるよう、内容を詳しく把握しておいてください。
            """
            attention_news_data = self.llm_news_collector.search_news(query=attention_news_query, num_results=10)
            
        # 統合
        all_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'market_indices': market_indices_data, # 主要指数の数値とチャート画像パス
            'sector_rankings': sector_rankings_data, # 業種別ランキングとスクリーンショット
            'attention_news': attention_news_data, # 注目ニュース
            'upcoming_events': []
        }
        
        print(f"\n✅ データ収集完了")
        
        return all_data
    

    
    def _get_index_display_name(self, index_name: str) -> str:
        """指数名の表示用名称を取得"""
        
        names = {
            'nikkei': '日経平均',
            'topix': 'TOPIX',
            'dow': 'ダウ平均',
            'nasdaq': 'ナスダック',
            'sp500': 'S&P 500',
            'usdjpy': 'ドル円'
        }
        
        return names.get(index_name, index_name)
    
    def format_for_display(self, data: Dict) -> str:
        """データを見やすく整形（デバッグ用）"""
        
        output = []
        
        output.append("\n" + "="*70)
        output.append(f"📊 市場データ ({data['timestamp']})")
        output.append("="*70)
        
        # 主要市場指数
        output.append("\n🌍 主要市場指数（チャート画像含む）")
        for market_key, market_data in data['market_indices'].items():
            current_price = market_data['current_price']
            change = market_data['change']
            change_percent = market_data['change_percent']

            # USDJPYの場合、yfinanceから取得した数値に符号を付ける
            if market_key == "USDJPY":
                try:
                    change_float = float(change)
                    change_percent_float = float(change_percent)
                    change = f"{change_float:+.2f}"
                    change_percent = f"{change_percent_float:+.2f}%"
                except ValueError:
                    pass # 数値変換できない場合はそのまま
            
            sign_char = "" # ここでは '+' を二重に付けないように初期化
            arrow = "" # ここでは矢印を付けないように初期化

            # 既存のchangeが'+'または'-'で始まらない場合のみ、符号と矢印を追加
            if not (change.startswith('+') or change.startswith('-')):
                try:
                    change_float = float(change.replace(',', '')) # カンマを除去して数値化を試みる
                    if change_float >= 0:
                        sign_char = "+"
                        arrow = "📈"
                    else:
                        arrow = "📉"
                except ValueError:
                    pass # 数値変換できない場合は何もしない
            else: # 既に符号が含まれている場合
                if change.startswith('+'):
                    arrow = "📈"
                elif change.startswith('-'):
                    arrow = "📉"

            output.append(
                f"  {arrow} {market_data['name']}: {current_price} "
                f"({sign_char}{change}, {sign_char}{change_percent})"
            )
            if market_data['chart_image_path']:
                output.append(f"    チャート画像: {market_data['chart_image_path']}")
            else:
                output.append(f"    チャート画像: (取得なし)")
        
        # 業種別ランキング
        output.append("\n📈 業種別株価指数ランキング")
        output.append(f"  スクリーンショット: {data['sector_rankings']['screenshot']}")
        output.append("  --- 値上がり率 TOP10 ---")
        for i, sector in enumerate(data['sector_rankings']['ranking']['top'], 1):
            output.append(f"  {i}. {sector['sector']}: {sector['change']}% 指数:{sector['index_value']}")
        output.append("  --- 値下がり率 TOP10 ---")
        for i, sector in enumerate(data['sector_rankings']['ranking']['bottom'], 1):
            output.append(f"  {i}. {sector['sector']}: {sector['change']}% 指数:{sector['index_value']}")

        # 注目ニュース
        output.append("\n📰 注目ニュース")
        if data.get('attention_news'):
            for i, news in enumerate(data['attention_news'][:10], 1): # 最大10件表示
                output.append(f"  {i}. {news['title']}")
                output.append(f"     要約: {news['snippet'][:80]}...") # 要約は一部のみ表示
                output.append(f"     情報源: {news.get('source', '不明')}")
                output.append(f"     URL: {news['url']}")
        else:
            output.append("  (ニュースなし)")

        output.append("\n" + "="*70)
        
        return "\n".join(output)
    
    def get_summary_stats(self, data: Dict) -> Dict:
        """
        市場の統計情報を取得
        （主要指数とセクターランキングのデータを利用）
        
        Returns:
            dict: {
                'overall_sentiment': 'bullish/bearish/neutral',
                'top_sector': 'セクター名',
                'worst_sector': 'セクター名',
                'market_breadth': 0.6  # 上昇セクターの割合
            }
        """
        
        # 主要指数の平均変動率
        changes = []
        for market_key, market_data in data['market_indices'].items():
            if market_data['change_percent'] != '-': # データがある場合のみ
                try:
                    changes.append(float(market_data['change_percent'].replace('%', '')))
                except ValueError:
                    pass
        
        avg_change = sum(changes) / len(changes) if changes else 0
        
        # センチメント判定
        if avg_change > 0.5:
            sentiment = 'bullish'
        elif avg_change < -0.5:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'
        
        # セクター分析
        sectors_top = data['sector_rankings']['ranking']['top']
        sectors_bottom = data['sector_rankings']['ranking']['bottom']
        all_sectors_for_stats = sectors_top + sectors_bottom # TOP10/BOTTOM10を合算して統計に利用

        top_sector = max(all_sectors_for_stats, key=lambda x: x['change'])['sector'] if all_sectors_for_stats else None
        worst_sector = min(all_sectors_for_stats, key=lambda x: x['change'])['sector'] if all_sectors_for_stats else None
        
        # 上昇セクターの割合 (TOP10とBOTTOM10だけでは正確ではないが、暫定的に利用)
        up_sectors = sum(1 for s in all_sectors_for_stats if s['change'] is not None and s['change'] > 0)
        market_breadth = up_sectors / len(all_sectors_for_stats) if all_sectors_for_stats else 0.5
        
        return {
            'overall_sentiment': sentiment,
            'average_change': round(avg_change, 2),
            'top_sector': top_sector,
            'worst_sector': worst_sector,
            'market_breadth': round(market_breadth, 2)
        }


# テスト・デモ用
if __name__ == "__main__":
    print("="*70)
    print("📊 Market Data Collector テスト")
    print("="*70)
    
    # インスタンス作成
    collector = MarketDataCollector()
    
    # 全データ収集
    all_data = collector.collect_all()
    
    # 結果表示
    print(collector.format_for_display(all_data))
    
    # 統計情報
    stats = collector.get_summary_stats(all_data)
    
    print("\n" + "="*70)
    print("📊 市場統計")
    print("="*70)
    print(f"市場センチメント: {stats['overall_sentiment'].upper()}")
    print(f"平均変動率: {stats['average_change']:+.2f}%") # 主要指数（日経、ダウ平均、ナスダック、S＆P）の変動率の平均
    print(f"最強セクター: {stats['top_sector']}")
    print(f"最弱セクター: {stats['worst_sector']}")
    print(f"市場の広がり: {stats['market_breadth']:.0%}") # 上昇セクターの割合
    print("="*70)
    
    # AIに渡すデータのサンプル表示
    print("\n" + "="*70)
    print("🤖 AIに渡すデータ（サンプル）")
    print("="*70)
    
    import json
    print(json.dumps(all_data, ensure_ascii=False, indent=2))
