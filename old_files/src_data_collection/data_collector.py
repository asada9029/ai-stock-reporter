"""
データ収集統合モジュール
全てのデータ収集機能を統合し、AIに渡すデータと人間確認用データを分離
"""

import json
import time
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

# 既存モジュールのインポート
from src.data_collection.market_data_collector import MarketDataCollector
from src.data_collection.event_calender import (
    get_event_search_hints,
    format_for_ai_prompt,
    get_beginner_friendly_summary
)


class DataCollector:
    """統合データコレクター"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        """
        初期化
        
        Args:
            cache_dir: キャッシュディレクトリのパス
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.market_collector = MarketDataCollector()
        
        # キャッシュの有効期限（秒）
        self.cache_duration = {
            "market_data": 300,  # 5分
            "event_hints": 3600,  # 1時間
        }
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """キャッシュファイルのパスを取得"""
        today = datetime.now().strftime("%Y%m%d")
        return self.cache_dir / f"{cache_key}_{today}.json"
    
    def _load_cache(self, cache_key: str) -> Optional[Dict]:
        """
        キャッシュを読み込む
        
        Args:
            cache_key: キャッシュのキー
            
        Returns:
            キャッシュデータ（有効期限内の場合）、なければNone
        """
        cache_path = self._get_cache_path(cache_key)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 有効期限チェック
            cached_time = datetime.fromisoformat(cache_data['cached_at'])
            elapsed = (datetime.now() - cached_time).total_seconds()
            
            if elapsed < self.cache_duration.get(cache_key, 300):
                print(f"✅ キャッシュを使用: {cache_key} (経過時間: {int(elapsed)}秒)")
                return cache_data['data']
            else:
                print(f"⏰ キャッシュ期限切れ: {cache_key}")
                return None
                
        except Exception as e:
            print(f"⚠️ キャッシュ読み込みエラー: {e}")
            return None
    
    def _save_cache(self, cache_key: str, data: Dict) -> None:
        """
        キャッシュを保存
        
        Args:
            cache_key: キャッシュのキー
            data: 保存するデータ
        """
        cache_path = self._get_cache_path(cache_key)
        
        cache_data = {
            'cached_at': datetime.now().isoformat(),
            'data': data
        }
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            print(f"💾 キャッシュ保存: {cache_key}")
        except Exception as e:
            print(f"⚠️ キャッシュ保存エラー: {e}")
    
    def collect_market_data(self, use_cache: bool = True) -> Dict:
        """
        市場データを収集
        
        Args:
            use_cache: キャッシュを使用するか
            
        Returns:
            市場データ
        """
        cache_key = "market_data"
        
        # キャッシュチェック
        if use_cache:
            cached_data = self._load_cache(cache_key)
            if cached_data:
                return cached_data
        
        print("📊 市場データを取得中...")
        try:
            market_data = self.market_collector.collect_all()
            
            # キャッシュ保存
            self._save_cache(cache_key, market_data)
            
            return market_data
            
        except Exception as e:
            print(f"❌ 市場データ取得エラー: {e}")
            raise
    
    def collect_event_hints(self, use_cache: bool = True) -> Dict:
        """
        イベントヒント情報を収集
        
        Args:
            use_cache: キャッシュを使用するか
            
        Returns:
            イベントヒント
        """
        cache_key = "event_hints"
        
        # キャッシュチェック
        if use_cache:
            cached_data = self._load_cache(cache_key)
            if cached_data:
                return cached_data
        
        print("📅 イベントヒントを生成中...")
        try:
            event_hints = get_event_search_hints()
            
            # キャッシュ保存
            self._save_cache(cache_key, event_hints)
            
            return event_hints
            
        except Exception as e:
            print(f"❌ イベントヒント生成エラー: {e}")
            raise
    
    def collect_all(self, use_cache: bool = True) -> Dict:
        """
        全データを統合して収集
        
        Args:
            use_cache: キャッシュを使用するか
            
        Returns:
            統合データ（AIに渡すデータと人間確認用データに分離）
        """
        print("\n" + "="*60)
        print("🚀 データ収集開始")
        print("="*60)
        
        start_time = time.time()
        
        try:
            # 1. 市場データ取得
            market_data = self.collect_market_data(use_cache)
            
            # 2. イベントヒント取得
            event_hints = self.collect_event_hints(use_cache)
            
            # 3. 初心者向けサマリー取得
            beginner_summary = get_beginner_friendly_summary()
            
            # 4. データ統合
            integrated_data = {
                # === AIに渡すデータ（数値と検索ヒントのみ）===
                "for_ai": {
                    "timestamp": datetime.now().isoformat(),
                    "market_data": market_data,  # 株価・指数の数値データ
                    "event_search_hints": event_hints,  # 検索すべきキーワード
                    "beginner_context": beginner_summary,  # 初心者向けコンテキスト
                    "ai_prompt": format_for_ai_prompt()  # AIプロンプト用フォーマット
                },
                
                # === 人間確認用データ（将来拡張用）===
                "for_human": {
                    "timestamp": datetime.now().isoformat(),
                    "notes": "人間が確認すべき情報（RSS、IR情報など）は将来ここに追加",
                    "news_headlines": [],  # Phase 2-2で追加予定
                    "ir_announcements": []  # Phase 2-3で追加予定
                }
            }
            
            elapsed_time = time.time() - start_time
            
            print("\n" + "="*60)
            print(f"✅ データ収集完了（所要時間: {elapsed_time:.2f}秒）")
            print("="*60)
            print(f"📊 市場データ: 取得済み")
            print(f"📅 イベントヒント: 取得済み")
            print(f"💡 初心者向けサマリー: 取得済み")
            print("="*60 + "\n")
            
            return integrated_data
            
        except Exception as e:
            print(f"\n❌ データ収集エラー: {e}")
            raise
    
    def get_ai_data_only(self, use_cache: bool = True) -> Dict:
        """
        AIに渡すデータのみを取得（簡易版）
        
        Args:
            use_cache: キャッシュを使用するか
            
        Returns:
            AIに渡すデータ
        """
        integrated_data = self.collect_all(use_cache)
        return integrated_data["for_ai"]
    
    def save_collected_data(self, data: Dict, output_dir: str = "data/collected") -> str:
        """
        収集したデータをファイルに保存
        
        Args:
            data: 保存するデータ
            output_dir: 出力ディレクトリ
            
        Returns:
            保存したファイルのパス
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"collected_data_{timestamp}.json"
        filepath = output_path / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 データ保存完了: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"❌ データ保存エラー: {e}")
            raise
    
    def clear_cache(self, cache_key: Optional[str] = None) -> None:
        """
        キャッシュをクリア
        
        Args:
            cache_key: クリアするキャッシュのキー（Noneの場合は全てクリア）
        """
        if cache_key:
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                cache_path.unlink()
                print(f"🗑️ キャッシュクリア: {cache_key}")
        else:
            # 全キャッシュクリア
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            print("🗑️ 全キャッシュクリア完了")


# テスト・デバッグ用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("📦 データ収集統合モジュール テスト")
    print("="*60 + "\n")
    
    # コレクター初期化
    collector = DataCollector()
    
    # 全データ収集
    try:
        all_data = collector.collect_all(use_cache=True)
        
        print("\n【収集データサマリー】")
        print(f"- AIデータ: {len(all_data['for_ai'])} 項目")
        print(f"- 人間確認用データ: {len(all_data['for_human'])} 項目")
        
        # AIに渡すデータのみ取得
        ai_data = collector.get_ai_data_only(use_cache=True)
        
        print("\n【AIに渡すデータの内容】")
        print(f"- タイムスタンプ: {ai_data['timestamp']}")
        print(f"- 市場データ: 日経平均={ai_data['market_data']['market']['japan']['nikkei']['current']}")
        print(f"- セクター数: {len(ai_data['market_data']['sectors'])}")
        print(f"- イベント検索ヒント: {len(ai_data['event_search_hints']['search_keywords']['earnings'])} 件")
        
        # データ保存
        saved_path = collector.save_collected_data(all_data)
        print(f"\n💾 保存先: {saved_path}")
        
        # 初心者向けサマリー表示
        print("\n【初心者向けサマリー】")
        summary = ai_data['beginner_context']
        
        if summary['today_focus']:
            print("\n🔴 今日の注目:")
            for item in summary['today_focus']:
                print(f"  {item['event']}: {item['explanation']}")
        
        print("\n📌 今週の注目:")
        for item in summary['this_week_focus']:
            print(f"  - {item}")
        
        print("\n💡 初心者向けTips:")
        for tip in summary['beginner_tips']:
            print(f"  {tip}")
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
