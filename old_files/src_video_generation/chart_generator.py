"""
データ可視化（グラフ生成）モジュール
株価チャート・ランキング表などを生成
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import matplotlib
matplotlib.use('Agg')  # GUIなし環境用
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image
from moviepy import ImageClip


class ChartGenerator:
    """グラフ生成クラス"""
    
    # グラフ設定
    FIGURE_SIZE = (12, 6)
    DPI = 150
    BACKGROUND_COLOR = '#1a1f3a'  # ダークブルー
    TEXT_COLOR = '#ffffff'
    GRID_COLOR = '#2a3f5f'
    
    # 色設定
    COLOR_UP = '#22c55e'      # 緑（上昇）
    COLOR_DOWN = '#ef4444'    # 赤（下落）
    COLOR_NEUTRAL = '#6b7280' # グレー（変化なし）
    
    def __init__(self):
        """初期化"""
        # 日本語フォント設定
        self._setup_japanese_font()
        
        # matplotlibのスタイル設定
        plt.style.use('dark_background')
        
        print("✅ ChartGenerator 初期化完了")
    
    def _setup_japanese_font(self):
        """日本語フォントの設定"""
        font_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts', 'NotoSansJP-Regular.ttf'),
            '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc',  # macOS
            'C:\\Windows\\Fonts\\msgothic.ttc',  # Windows
            '/usr/share/fonts/truetype/takao-gothic/TakaoGothic.ttf',  # Linux
        ]
        
        for font_path in font_paths:
            if Path(font_path).exists():
                fm.fontManager.addfont(font_path)
                font_name = fm.FontProperties(fname=font_path).get_name()
                plt.rcParams['font.family'] = font_name
                print(f"   日本語フォント: {font_name}")
                return
        
        print("⚠️ 日本語フォントが見つかりません")
    
    def create_market_overview_chart(
        self,
        market_data: Dict,
        output_path: str
    ) -> str:
        """
        市場概況チャートを作成
        
        Args:
            market_data: 市場データ
            output_path: 出力パス
        
        Returns:
            str: 保存したファイルパス
        """
        fig, axes = plt.subplots(1, 2, figsize=self.FIGURE_SIZE)
        fig.patch.set_facecolor(self.BACKGROUND_COLOR)
        
        # 日本市場
        ax1 = axes[0]
        self._plot_index_bars(
            ax1,
            market_data.get('market', {}).get('japan', {}),
            title="日本市場"
        )
        
        # 米国市場
        ax2 = axes[1]
        self._plot_index_bars(
            ax2,
            market_data.get('market', {}).get('us', {}),
            title="米国市場"
        )
        
        plt.tight_layout()
        
        # 保存
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_file, dpi=self.DPI, facecolor=self.BACKGROUND_COLOR)
        plt.close()
        
        print(f"💾 市場概況チャート保存: {output_file}")
        return str(output_file)
    
    def _plot_index_bars(self, ax, market_data: Dict, title: str):
        """指数の棒グラフをプロット"""
        ax.set_facecolor(self.BACKGROUND_COLOR)
        ax.set_title(title, color=self.TEXT_COLOR, fontsize=16, pad=20)
        
        indices = []
        changes = []
        colors = []
        
        for key, data in market_data.items():
            if data and isinstance(data, dict):
                name = data.get('name', key)
                change_percent = data.get('change_percent', 0)
                
                indices.append(name)
                changes.append(change_percent)
                
                # 色決定
                if change_percent > 0:
                    colors.append(self.COLOR_UP)
                elif change_percent < 0:
                    colors.append(self.COLOR_DOWN)
                else:
                    colors.append(self.COLOR_NEUTRAL)
        
        if not indices:
            ax.text(0.5, 0.5, 'データなし', ha='center', va='center',
                   color=self.TEXT_COLOR, transform=ax.transAxes)
            return
        
        # 棒グラフ
        y_pos = np.arange(len(indices))
        bars = ax.barh(y_pos, changes, color=colors, alpha=0.8)
        
        # ラベル
        ax.set_yticks(y_pos)
        ax.set_yticklabels(indices, color=self.TEXT_COLOR)
        ax.set_xlabel('変動率 (%)', color=self.TEXT_COLOR)
        ax.tick_params(colors=self.TEXT_COLOR)
        
        # グリッド
        ax.grid(True, color=self.GRID_COLOR, alpha=0.3, axis='x')
        ax.axvline(x=0, color=self.TEXT_COLOR, linewidth=0.5)
        
        # 数値ラベル
        for i, (bar, change) in enumerate(zip(bars, changes)):
            width = bar.get_width()
            x_pos = width + (0.1 if width > 0 else -0.1)
            ax.text(x_pos, bar.get_y() + bar.get_height()/2,
                   f'{change:+.2f}%',
                   ha='left' if width > 0 else 'right',
                   va='center',
                   color=self.TEXT_COLOR,
                   fontsize=10)
    
    def create_sector_ranking_chart(
        self,
        sectors: List[Dict],
        output_path: str,
        top_n: int = 10
    ) -> str:
        """
        セクター別ランキングチャートを作成
        
        Args:
            sectors: セクターデータのリスト
            output_path: 出力パス
            top_n: 表示する件数
        
        Returns:
            str: 保存したファイルパス
        """
        # 変動率でソート
        sorted_sectors = sorted(
            sectors,
            key=lambda x: x.get('change_percent', 0),
            reverse=True
        )[:top_n]
        
        fig, ax = plt.subplots(figsize=self.FIGURE_SIZE)
        fig.patch.set_facecolor(self.BACKGROUND_COLOR)
        ax.set_facecolor(self.BACKGROUND_COLOR)
        
        # データ準備
        names = [s.get('name', '') for s in sorted_sectors]
        changes = [s.get('change_percent', 0) for s in sorted_sectors]
        colors = [self.COLOR_UP if c > 0 else self.COLOR_DOWN for c in changes]
        
        # 棒グラフ
        y_pos = np.arange(len(names))
        bars = ax.barh(y_pos, changes, color=colors, alpha=0.8)
        
        # ラベル
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, color=self.TEXT_COLOR, fontsize=11)
        ax.set_xlabel('変動率 (%)', color=self.TEXT_COLOR, fontsize=12)
        ax.set_title('セクター別パフォーマンス TOP10', 
                    color=self.TEXT_COLOR, fontsize=16, pad=20)
        ax.tick_params(colors=self.TEXT_COLOR)
        
        # グリッド
        ax.grid(True, color=self.GRID_COLOR, alpha=0.3, axis='x')
        ax.axvline(x=0, color=self.TEXT_COLOR, linewidth=0.5)
        
        # 数値ラベル
        for bar, change in zip(bars, changes):
            width = bar.get_width()
            x_pos = width + (0.15 if width > 0 else -0.15)
            ax.text(x_pos, bar.get_y() + bar.get_height()/2,
                   f'{change:+.2f}%',
                   ha='left' if width > 0 else 'right',
                   va='center',
                   color=self.TEXT_COLOR,
                   fontsize=10,
                   fontweight='bold')
        
        plt.tight_layout()
        
        # 保存
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_file, dpi=self.DPI, facecolor=self.BACKGROUND_COLOR)
        plt.close()
        
        print(f"💾 セクターランキング保存: {output_file}")
        return str(output_file)
    
    def create_ranking_table(
        self,
        data: List[Dict],
        columns: List[str],
        title: str,
        output_path: str,
        top_n: int = 10
    ) -> str:
        """
        ランキング表を作成
        
        Args:
            data: データのリスト
            columns: 表示するカラム名のリスト
            title: タイトル
            output_path: 出力パス
            top_n: 表示する件数
        
        Returns:
            str: 保存したファイルパス
        """
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.patch.set_facecolor(self.BACKGROUND_COLOR)
        ax.axis('tight')
        ax.axis('off')
        
        # データ準備
        table_data = []
        for i, item in enumerate(data[:top_n], 1):
            row = [str(i)]  # ランキング番号
            for col in columns:
                value = item.get(col, '-')
                if isinstance(value, (int, float)):
                    if 'percent' in col or '率' in col:
                        row.append(f'{value:+.2f}%')
                    else:
                        row.append(f'{value:,.0f}')
                else:
                    row.append(str(value))
            table_data.append(row)
        
        # ヘッダー
        headers = ['順位'] + columns
        
        # テーブル作成
        table = ax.table(
            cellText=table_data,
            colLabels=headers,
            cellLoc='center',
            loc='center',
            colWidths=[0.08] + [0.92 / len(columns)] * len(columns)
        )
        
        # スタイル設定
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 2)
        
        # ヘッダー行
        for i in range(len(headers)):
            cell = table[(0, i)]
            cell.set_facecolor('#2a3f5f')
            cell.set_text_props(weight='bold', color=self.TEXT_COLOR)
        
        # データ行
        for i in range(1, len(table_data) + 1):
            for j in range(len(headers)):
                cell = table[(i, j)]
                cell.set_facecolor('#1a1f3a' if i % 2 == 0 else '#1f2640')
                cell.set_text_props(color=self.TEXT_COLOR)
        
        # タイトル
        plt.title(title, color=self.TEXT_COLOR, fontsize=18, pad=20, fontweight='bold')
        
        # 保存
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_file, dpi=self.DPI, facecolor=self.BACKGROUND_COLOR, bbox_inches='tight')
        plt.close()
        
        print(f"💾 ランキング表保存: {output_file}")
        return str(output_file)
    
    def create_chart_clip(
        self,
        chart_path: str,
        duration: float,
        position: Tuple = ('center', 'center')
    ) -> ImageClip:
        """
        グラフ画像を動画クリップに変換
        
        Args:
            chart_path: グラフ画像のパス
            duration: 表示時間（秒）
            position: 表示位置
        
        Returns:
            ImageClip: グラフクリップ
        """
        if not Path(chart_path).exists():
            raise FileNotFoundError(f"グラフ画像が見つかりません: {chart_path}")
        
        # 画像読み込み
        img = Image.open(chart_path)
        img_array = np.array(img)
        
        # クリップ作成
        clip = ImageClip(img_array, duration=duration)
        clip = clip.with_position(position)
        
        return clip
    
    def overlay_chart_on_video(
        self,
        video_clip,
        chart_path: str,
        start_time: float,
        duration: float,
        position: Tuple = ('center', 'center'),
        scale: float = 0.8
    ):
        """
        動画にグラフをオーバーレイ
        
        Args:
            video_clip: 動画クリップ
            chart_path: グラフ画像のパス
            start_time: 開始時刻（秒）
            duration: 表示時間（秒）
            position: 表示位置
            scale: スケール（0.0-1.0）
        
        Returns:
            CompositeVideoClip: グラフ付き動画
        """
        from moviepy import CompositeVideoClip
        
        # グラフクリップ作成
        chart_clip = self.create_chart_clip(chart_path, duration, position)
        chart_clip = chart_clip.with_start(start_time)
        
        # スケール調整
        if scale != 1.0:
            chart_clip = chart_clip.resized(scale)
        
        # 合成
        composite = CompositeVideoClip([video_clip, chart_clip])
        
        return composite


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("📊 ChartGenerator テスト")
    print("="*60 + "\n")
    
    try:
        generator = ChartGenerator()
        
        # テスト1: 市場概況チャート
        print("\n=== テスト1: 市場概況チャート ===")
        
        sample_market_data = {
            "market": {
                "japan": {
                    "nikkei": {"name": "日経平均", "change_percent": 1.2},
                    "topix": {"name": "TOPIX", "change_percent": 0.8}
                },
                "us": {
                    "dow": {"name": "ダウ", "change_percent": 0.5},
                    "nasdaq": {"name": "ナスダック", "change_percent": 1.8},
                    "sp500": {"name": "S&P500", "change_percent": 0.9}
                }
            }
        }
        
        chart1 = generator.create_market_overview_chart(
            sample_market_data,
            "data/test_charts/market_overview.png"
        )
        
        # テスト2: セクターランキング
        print("\n=== テスト2: セクターランキング ===")
        
        sample_sectors = [
            {"name": "半導体", "change_percent": 3.2},
            {"name": "自動車", "change_percent": -1.5},
            {"name": "銀行", "change_percent": 2.1},
            {"name": "医薬品", "change_percent": 1.8},
            {"name": "情報通信", "change_percent": 2.8},
            {"name": "小売", "change_percent": 0.5},
            {"name": "電気機器", "change_percent": 3.5},
            {"name": "化学", "change_percent": -0.8},
            {"name": "不動産", "change_percent": 1.2},
            {"name": "食品", "change_percent": 0.3}
        ]
        
        chart2 = generator.create_sector_ranking_chart(
            sample_sectors,
            "data/test_charts/sector_ranking.png"
        )
        
        # テスト3: ランキング表
        print("\n=== テスト3: ランキング表 ===")
        
        sample_stocks = [
            {"name": "トヨタ", "code": "7203", "change_percent": 2.5, "volume": 15000000},
            {"name": "ソニー", "code": "6758", "change_percent": 3.2, "volume": 8000000},
            {"name": "日立", "code": "6501", "change_percent": 1.8, "volume": 12000000},
            {"name": "キーエンス", "code": "6861", "change_percent": 2.1, "volume": 500000},
            {"name": "任天堂", "code": "7974", "change_percent": -1.2, "volume": 3000000}
        ]
        
        chart3 = generator.create_ranking_table(
            sample_stocks,
            columns=["name", "code", "change_percent", "volume"],
            title="注目銘柄ランキング",
            output_path="data/test_charts/stock_ranking.png"
        )
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - data/test_charts/market_overview.png")
        print("  - data/test_charts/sector_ranking.png")
        print("  - data/test_charts/stock_ranking.png")
        print("\n📊 画像を確認してください！")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
