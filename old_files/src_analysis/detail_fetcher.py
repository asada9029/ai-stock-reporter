"""
詳細情報取得モジュール
AIが選んだ銘柄の詳細データを取得
"""

import yfinance as yf
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import time


class DetailFetcher:
    """詳細情報取得クラス（完全AI主導対応版）"""
    
    def __init__(self):
        """初期化"""
        print("✅ DetailFetcher 初期化完了（AI主導モード）")
    
    def get_stocks_details(
        self,
        stock_codes: List[str],
        include_dividend: bool = False
    ) -> List[Dict]:
        """
        複数銘柄の詳細情報を一括取得
        
        Args:
            stock_codes: 銘柄コードのリスト（例: ["7203.T", "6758.T"]）
            include_dividend: 配当情報を含めるか
        
        Returns:
            List[Dict]: 銘柄詳細情報のリスト
        """
        print(f"\n📊 銘柄詳細一括取得: {len(stock_codes)}銘柄")
        
        results = []
        for code in stock_codes:
            try:
                detail = self.get_stock_detail(code, include_dividend)
                if detail and not detail.get('error'):
                    results.append(detail)
                time.sleep(0.3)  # レート制限対策
            except Exception as e:
                print(f"⚠️ {code} のエラー: {e}")
                continue
        
        print(f"✅ {len(results)}/{len(stock_codes)} 銘柄取得完了")
        return results
    
    def get_stock_detail(
        self,
        stock_code: str,
        include_dividend: bool = False
    ) -> Dict:
        """
        個別銘柄の詳細情報を取得
        
        Args:
            stock_code: 銘柄コード（例: "7203.T" or "AAPL"）
            include_dividend: 配当情報を含めるか
        
        Returns:
            Dict: 銘柄詳細情報
        """
        try:
            ticker = yf.Ticker(stock_code)
            info = ticker.info
            
            # 基本情報
            detail = {
                "code": stock_code,
                "name": info.get('longName') or info.get('shortName', 'N/A'),
                "current_price": info.get('currentPrice') or info.get('regularMarketPrice'),
                "previous_close": info.get('previousClose'),
                "open": info.get('open'),
                "high": info.get('dayHigh'),
                "low": info.get('dayLow'),
                "volume": info.get('volume'),
                "market_cap": info.get('marketCap'),
                "sector": info.get('sector'),
                "industry": info.get('industry'),
            }
            
            # 変動率計算
            if detail['current_price'] and detail['previous_close']:
                change = detail['current_price'] - detail['previous_close']
                change_percent = (change / detail['previous_close']) * 100
                detail['change'] = round(change, 2)
                detail['change_percent'] = round(change_percent, 2)
            
            # 売買代金計算
            if detail['volume'] and detail['current_price']:
                detail['volume_value'] = detail['volume'] * detail['current_price']
            
            # 配当情報（オプション）
            if include_dividend:
                dividend_yield = info.get('dividendYield')
                
                # yfinanceは配当利回りを100倍で返すので補正
                if dividend_yield:
                    dividend_yield = dividend_yield / 100
                
                detail['dividend_yield'] = dividend_yield
                detail['dividend_rate'] = info.get('dividendRate')
                detail['ex_dividend_date'] = info.get('exDividendDate')
            
            # 新NISA対象判定（簡易版）
            detail['nisa_eligible'] = self._check_nisa_eligible(stock_code, info)
            
            return detail
            
        except Exception as e:
            print(f"❌ {stock_code} 取得エラー: {e}")
            return {
                "code": stock_code,
                "error": str(e)
            }
    
    def _check_nisa_eligible(self, stock_code: str, info: Dict) -> bool:
        """
        新NISA対象かどうかを判定（簡易版）
        
        Args:
            stock_code: 銘柄コード
            info: 銘柄情報
        
        Returns:
            bool: 新NISA対象かどうか
        """
        # 簡易判定：東証上場かつ一定の時価総額がある
        exchange = info.get('exchange', '')
        market_cap = info.get('marketCap', 0)
        
        # 東証（Tokyo）かつ時価総額100億円以上
        is_tokyo = 'tokyo' in exchange.lower() or '.T' in stock_code
        has_market_cap = market_cap and market_cap > 10_000_000_000
        
        return is_tokyo and has_market_cap
    
    def create_ranking(
        self,
        stocks_details: List[Dict],
        ranking_type: str = "change_percent",
        limit: int = 10,
        ascending: bool = False
    ) -> List[Dict]:
        """
        銘柄リストからランキングを作成
        
        Args:
            stocks_details: 銘柄詳細情報のリスト
            ranking_type: ランキング種類
                - "change_percent": 変動率
                - "volume": 出来高
                - "volume_value": 売買代金
                - "dividend_yield": 配当利回り
                - "market_cap": 時価総額
            limit: 取得数
            ascending: 昇順か（Falseで降順）
        
        Returns:
            List[Dict]: ランキング
        """
        # エラーのある銘柄を除外
        valid_stocks = [s for s in stocks_details if not s.get('error')]
        
        # 指定フィールドが存在する銘柄のみ
        valid_stocks = [
            s for s in valid_stocks 
            if s.get(ranking_type) is not None
        ]
        
        # ソート
        sorted_stocks = sorted(
            valid_stocks,
            key=lambda x: x.get(ranking_type, 0),
            reverse=not ascending
        )
        
        return sorted_stocks[:limit]
    
    def enrich_ai_selected_stocks(
        self,
        ai_analysis_result: Dict,
        include_dividend: bool = False
    ) -> Dict:
        """
        AIが選んだ銘柄に詳細情報を追加（メインメソッド）
        
        Args:
            ai_analysis_result: AIディレクターの分析結果
            include_dividend: 配当情報を含めるか
        
        Returns:
            Dict: 詳細情報を追加した分析結果
        """
        print("\n" + "="*60)
        print("🔍 AIが選んだ銘柄の詳細情報取得")
        print("="*60)
        
        enriched = ai_analysis_result.copy()
        
        # 注目銘柄の詳細取得
        if 'featured_stocks' in enriched:
            stock_codes = self._extract_stock_codes(
                enriched['featured_stocks']
            )
            
            print(f"\n📌 注目銘柄: {len(stock_codes)}銘柄")
            details = self.get_stocks_details(stock_codes, include_dividend)
            
            # 詳細情報をマージ
            enriched['featured_stocks_details'] = details
        
        # 選定セクター内の主要銘柄詳細取得
        if 'selected_sectors' in enriched:
            for sector in enriched['selected_sectors']:
                if 'key_stocks' in sector:
                    stock_codes = self._extract_stock_codes(
                        sector['key_stocks']
                    )
                    
                    print(f"\n📊 {sector['sector']}セクター: {len(stock_codes)}銘柄")
                    details = self.get_stocks_details(stock_codes, include_dividend)
                    
                    sector['key_stocks_details'] = details
        
        print("\n" + "="*60)
        print("✅ 詳細情報追加完了")
        print("="*60)
        
        return enriched
    
    def _extract_stock_codes(self, stock_list: List) -> List[str]:
        """
        銘柄リストから銘柄コードを抽出
        
        Args:
            stock_list: 銘柄リスト
                文字列リスト（例: ["トヨタ(7203)", "ソニー(6758)"]）
                または辞書リスト（例: [{"stock": "トヨタ(7203)"}]）
        
        Returns:
            List[str]: 銘柄コードのリスト（例: ["7203.T", "6758.T"]）
        """
        codes = []
        
        for item in stock_list:
            # 文字列の場合
            if isinstance(item, str):
                code = self._parse_stock_code(item)
                if code:
                    codes.append(code)
            
            # 辞書の場合
            elif isinstance(item, dict):
                stock_str = item.get('stock') or item.get('code')
                if stock_str:
                    code = self._parse_stock_code(stock_str)
                    if code:
                        codes.append(code)
        
        return codes
    
    def _parse_stock_code(self, stock_str: str) -> Optional[str]:
        """
        文字列から銘柄コードを抽出
        
        Args:
            stock_str: 銘柄文字列（例: "トヨタ(7203)" or "7203" or "7203.T"）
        
        Returns:
            Optional[str]: 銘柄コード（例: "7203.T"）
        """
        import re
        
        # 既に .T が付いている場合
        if '.T' in stock_str:
            match = re.search(r'(\d{4}\.T)', stock_str)
            if match:
                return match.group(1)
        
        # 括弧内のコード抽出（例: "トヨタ(7203)"）
        match = re.search(r'\((\d{4})\)', stock_str)
        if match:
            return f"{match.group(1)}.T"
        
        # 4桁の数字のみ（例: "7203"）
        match = re.search(r'(\d{4})', stock_str)
        if match:
            return f"{match.group(1)}.T"
        
        # 米国株の場合（例: "AAPL"）
        if stock_str.isupper() and len(stock_str) <= 5:
            return stock_str
        
        return None
    
    def get_summary_statistics(
        self,
        stocks_details: List[Dict]
    ) -> Dict:
        """
        銘柄リストの統計情報を取得
        
        Args:
            stocks_details: 銘柄詳細情報のリスト
        
        Returns:
            Dict: 統計情報
        """
        valid_stocks = [s for s in stocks_details if not s.get('error')]
        
        if not valid_stocks:
            return {"error": "有効な銘柄がありません"}
        
        # 変動率の統計
        changes = [s.get('change_percent', 0) for s in valid_stocks if s.get('change_percent')]
        
        # 出来高の統計
        volumes = [s.get('volume', 0) for s in valid_stocks if s.get('volume')]
        
        return {
            "total_stocks": len(valid_stocks),
            "gainers": len([c for c in changes if c > 0]),
            "losers": len([c for c in changes if c < 0]),
            "unchanged": len([c for c in changes if c == 0]),
            "avg_change_percent": round(sum(changes) / len(changes), 2) if changes else 0,
            "max_gain": round(max(changes), 2) if changes else 0,
            "max_loss": round(min(changes), 2) if changes else 0,
            "total_volume": sum(volumes) if volumes else 0,
            "timestamp": datetime.now().isoformat()
        }


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("📊 DetailFetcher テスト（AI主導版）")
    print("="*60 + "\n")
    
    fetcher = DetailFetcher()
    
    # テスト1: AIが選んだ銘柄リストから詳細取得
    print("\n=== テスト1: AIが選んだ銘柄の詳細取得 ===")
    ai_selected = ["トヨタ(7203)", "ソニー(6758)", "日立(6501)"]
    stock_codes = fetcher._extract_stock_codes(ai_selected)
    print(f"抽出されたコード: {stock_codes}")
    
    details = fetcher.get_stocks_details(stock_codes, include_dividend=True)
    for stock in details:
        print(f"  - {stock.get('name')} ({stock.get('code')})")
        print(f"    現在値: ¥{stock.get('current_price')}, 変動率: {stock.get('change_percent')}%")
        if stock.get('dividend_yield'):
            print(f"    配当利回り: {stock.get('dividend_yield')*100:.2f}%")
    
    # テスト2: ランキング作成
    print("\n=== テスト2: 変動率ランキング ===")
    ranking = fetcher.create_ranking(details, "change_percent", limit=5)
    for i, stock in enumerate(ranking, 1):
        print(f"  {i}位: {stock.get('name')} ({stock.get('change_percent')}%)")
    
    # テスト3: 統計情報
    print("\n=== テスト3: 統計情報 ===")
    stats = fetcher.get_summary_statistics(details)
    print(f"  総銘柄数: {stats['total_stocks']}")
    print(f"  値上がり: {stats['gainers']}銘柄")
    print(f"  値下がり: {stats['losers']}銘柄")
    print(f"  平均変動率: {stats['avg_change_percent']}%")
    
    # テスト4: AIディレクターの結果に詳細追加
    print("\n=== テスト4: AI分析結果への詳細追加 ===")
    mock_ai_result = {
        "featured_stocks": [
            {"stock": "トヨタ(7203)", "reason": "増配発表"},
            {"stock": "ソニー(6758)", "reason": "業績好調"}
        ],
        "selected_sectors": [
            {
                "sector": "輸送用機器",
                "key_stocks": ["トヨタ(7203)", "ホンダ(7267)"]
            }
        ]
    }
    
    enriched = fetcher.enrich_ai_selected_stocks(mock_ai_result, include_dividend=True)
    print(f"  注目銘柄詳細: {len(enriched.get('featured_stocks_details', []))}銘柄")
    print(f"  セクター内銘柄詳細追加: ✅")
    
    print("\n" + "="*60)
    print("✅ テスト完了")
    print("="*60)
