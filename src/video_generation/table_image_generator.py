import matplotlib.pyplot as plt
import pandas as pd
import os
import matplotlib.font_manager as fm

# 日本語フォントの設定
# プロジェクト内の 'src/assets/fonts' ディレクトリに 'NotoSansJP-Regular.ttf' を配置することを想定
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts', 'NotoSansJP-Regular.ttf')

# フォントが利用可能かチェックし、matplotlibに登録
if os.path.exists(FONT_PATH):
    fm.fontManager.addfont(FONT_PATH)
    # フォント名を正確に指定
    plt.rcParams['font.family'] = 'Noto Sans JP'
    plt.rcParams['axes.unicode_minus'] = False # マイナス記号の文字化け防止
    print(f"日本語フォント '{os.path.basename(FONT_PATH)}' を設定しました。")
else:
    print(f"警告: 日本語フォントファイルが見つかりません: {FONT_PATH}")
    print("日本語が正しく表示されない可能性があります。'fonts' ディレクトリに 'NotoSansJP-Regular.ttf' を配置してください。")


class TableImageGenerator:
    def __init__(self, output_dir="data/images"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_table_image(self, data: list[dict], title: str, filename: str, columns: list[str] = None, column_mapping: dict = None):
        """
        データを元に表形式の画像を生成する。
        data: データのリスト
        title: 画像のタイトル
        filename: 保存する画像ファイル名
        columns: 表示する列名のリスト
        column_mapping: 列名の表示名マッピング
        """
        if not data:
            print(f"警告: {title} のデータがありません。画像を生成しません。")
            return None

        df = pd.DataFrame(data)

        if columns is None:
            columns = ['date', 'company', 'security_code', 'event_type']
        
        if column_mapping is None:
            column_mapping = {
                'date': '日付',
                'company': '企業名',
                'security_code': 'コード',
                'settlement_term': '決算期',
                'industry': '業種',
                'event_type': 'イベント',
                'sector': 'セクター',
                'change': '騰落率(%)',
                'change_text': '騰落率',
                'index_value': '指数値'
            }
        
        actual_display_columns = [col for col in columns if col in df.columns]
        df_display = df[actual_display_columns]
        df_display = df_display.rename(columns=column_mapping)

        # figsizeを調整。余白を最小限にするため、係数を調整
        fig, ax = plt.subplots(figsize=(10, len(df_display) * 0.3)) 
        ax.axis('off')

        # 表の作成
        table = ax.table(cellText=df_display.values,
                         colLabels=df_display.columns,
                         loc='center',
                         cellLoc='center') # 中央寄せに変更

        # スタイルの調整
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1.0, 1.5) # セルの高さを広げる

        # ヘッダーの色付け
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#404040') # 濃いグレー
            else:
                # 騰落率に応じた色付け
                # '騰落率' という文字列が含まれる列、または 'change' という元の列名がある場合
                target_col_idx = -1
                for i, col_name in enumerate(df_display.columns):
                    if '騰落率' in col_name or '前日比' in col_name:
                        target_col_idx = i
                        break
                
                if target_col_idx != -1 and col == target_col_idx:
                    # 数値データを取得（元のdfから取得するのが確実）
                    val = None
                    if 'change' in df.columns:
                        val = df.iloc[row-1]['change']
                    elif 'change_percent' in df.columns:
                        val = df.iloc[row-1]['change_percent']
                    
                    if val is not None:
                        try:
                            val_float = float(val)
                            if val_float > 0:
                                cell.set_text_props(color='red', weight='bold')
                            elif val_float < 0:
                                cell.set_text_props(color='green', weight='bold')
                        except:
                            pass

        # ax.set_title(title, fontsize=16, loc='center', pad=20) # タイトルを非表示に

        output_path = os.path.join(self.output_dir, filename)
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0.05, dpi=120)
        plt.close(fig)
        print(f"表画像を生成しました: {output_path}")
        return output_path

# デモ実行（ir_event_collectorと連携させる）
if __name__ == "__main__":
    print("="*50)
    print("🖼️ Table Image Generator デモ")
    print("="*50)

    # ir_event_collectorを使ってダミーデータを生成
    # 実際のデータはir_event_collectorから取得します
    sample_kessan_data = [
        {'date': '2025-12-20', 'security_code': '3359', 'company': 'ｃｏｔｔａ', 'settlement_term': '9月期', 'industry': '商社', 'event_type': '決算発表'},
        {'date': '2025-12-20', 'security_code': '4243', 'company': 'ニックス', 'settlement_term': '9月期', 'industry': '化学', 'event_type': '決算発表'},
        {'date': '2025-12-21', 'security_code': '9438', 'company': 'はにかみハンムラビコーポーレーチオン', 'settlement_term': '9月期', 'industry': '通信', 'event_type': '決算発表'},
    ]

    sample_soukai_data = [
        {'date': '2025-12-20', 'security_code': '1234', 'company': 'サンプルA', 'settlement_term': '3月期', 'industry': 'サービス', 'event_type': '株主総会'},
        {'date': '2025-12-21', 'security_code': '5678', 'company': 'サンプルB', 'settlement_term': '3月期', 'industry': '製造', 'event_type': '株主総会'},
    ]

    generator = TableImageGenerator()

    # 決算発表の表画像を生成
    kessan_image_path = generator.generate_table_image(
        data=sample_kessan_data,
        title="直近の決算発表スケジュール",
        filename="test_kessan_schedule.png"
    )
    if kessan_image_path:
        print(f"決算発表画像パス: {kessan_image_path}")

    # 株主総会の表画像を生成
    soukai_image_path = generator.generate_table_image(
        data=sample_soukai_data,
        title="直近の株主総会スケジュール",
        filename="test_soukai_schedule.png"
    )
    if soukai_image_path:
        print(f"株主総会画像パス: {soukai_image_path}")

