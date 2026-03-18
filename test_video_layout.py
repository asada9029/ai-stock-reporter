import os
import json
from pathlib import Path
from src.video_generation.structured_video_composer import render_scenes_to_video

def create_test_video():
    print("🚀 レイアウト・データ対応 全パターン総合テスト開始")
    
    # テスト用の出力パス
    output_path = "output/layout_test.mp4"
    assets_dir = "src/assets"
    
    # テスト用のダミー画像
    valid_images = ["src/assets/images/studio_main.png"]

    # シーン構成のモック
    scenes = [
        {
            "scene": 1,
            "section_title": "■ パターン1：テキストのみ（画像なし）",
            "duration": 5.0,
            "text": "画像がないシーンです。テキストパネルがメイン領域の中央に大きく表示されます。",
            "on_screen_text": [
                "見出し：テキストのみのレイアウト",
                "  └ 画像がない場合は、タイトルと字幕の間のスペース"
            ],
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
            "segments": [{"text": "画像がないシーンのテストです。", "start": 0.0, "duration": 5.0}]
        },
        {
            "scene": 2,
            "section_title": "■ パターン1：テキストのみ（画像なし）",
            "duration": 5.0,
            "text": "画像がないシーンです。テキストパネルがメイン領域の中央に大きく表示されます。",
            "on_screen_text": [
                "・市場の動向",
                "・決算・株主総会スケジュール",
                "・注目ニュース紹介（MetaとAMDの巨額契約 など）",
                "・セクター分析",
                "・注目銘柄のIR",
                "・前回紹介銘柄の動向",
                "・今夜の米国市場と明日の展望",
                "・まとめ"
            ],
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
            "segments": [{"text": "画像がないシーンのテストです。", "start": 0.0, "duration": 5.0}]
        },
        {
            "scene": 2,
            "section_title": "■ パターン2：画像1枚のみ（テキストなし）",
            "duration": 5.0,
            "text": "画像1枚のみのシーンです。画面いっぱいに大きく表示される",
            "on_screen_text": [],
            "emotion": "normal",
            "image_type": "chart",
            "target_files": [valid_images[0]],
            "segments": [{"text": "画像1枚のみのテストです。", "start": 0.0, "duration": 5.0}]
        },
        {
            "scene": 8,
            "section_title": "■ パターン8：2行にわたる長い字幕",
            "duration": 6.0,
            "text": "この字幕は非常に長いため、2行にわたって表示されるはずです。下の文字が画面外にはみ出さず、綺麗に収まっているかを確認してください。",
            "on_screen_text": [
                "見出し：字幕位置の調整確認",
                "  └ y_posを上げたことで、2行になっても余裕を持って映ってるはず",
                "見出し：2つ目以降の見出しがインデントされていないことを確認して",
                "  └ こちらはインデントされていることを確認して"
            ],
            "emotion": "normal",
            "image_type": "bg_only",
            "target_files": [],
            "segments": [{"text": "この字幕は非常に長いため、2行にわたって表示されるはずです。下の文字が画面外にはみ出さず、綺麗に収まっているかを確認してください。", "start": 0.0, "duration": 6.0}]
        },
        {
            "scene": 3,
            "section_title": "■ パターン3：画像1枚 ＋ テキスト（併用）",
            "duration": 5.0,
            "text": "画像とテキストを併用するシーンです。画像が上に寄り、下にテキストが表示されます。",
            "on_screen_text": [
                "見出し：画像とテキストの併用",
                "  └ 画像の下にスペースが空き、解説テキストが収まる"
            ],
            "emotion": "confident",
            "image_type": "chart",
            "target_files": [valid_images[0]],
            "segments": [{"text": "画像とテキストの併用テストです。", "start": 0.0, "duration": 5.0}]
        },
        # {
        #     "scene": 4,
        #     "section_title": "■ パターン4：画像2枚（上下並列）",
        #     "duration": 5.0,
        #     "text": "画像2枚のシーンです。テキストがないため、上下に大きく並びます。",
        #     "on_screen_text": [],
        #     "emotion": "surprised",
        #     "image_type": "chart",
        #     "target_files": [valid_images[0], valid_images[0]],
        #     "segments": [{"text": "画像2枚のテストです。", "start": 0.0, "duration": 5.0}]
        # },
        # {
        #     "scene": 5,
        #     "section_title": "■ パターン5：画像2枚 ＋ テキスト（併用）",
        #     "duration": 5.0,
        #     "text": "画像2枚とテキストを併用します。画像エリアが縮小され、下にテキストが入ります。",
        #     "on_screen_text": [
        #         "見出し：複数画像とテキストの併用",
        #         "  └ 画像枚数が増えても、テキスト用のスペースは死守"
        #     ],
        #     "emotion": "excited",
        #     "image_type": "chart",
        #     "target_files": [valid_images[0], valid_images[0]],
        #     "segments": [{"text": "画像2枚とテキストの併用テストです。", "start": 0.0, "duration": 5.0}]
        # },
        # {
        #     "scene": 6,
        #     "section_title": "■ パターン6：画像3枚（逆三角形）",
        #     "duration": 5.0,
        #     "text": "画像3枚のシーンです。上段に1枚、下段に2枚の逆三角形レイアウトになります。",
        #     "on_screen_text": [],
        #     "emotion": "surprised",
        #     "image_type": "chart",
        #     "target_files": [valid_images[0], valid_images[0], valid_images[0]],
        #     "segments": [{"text": "画像3枚のレイアウトテストです。", "start": 0.0, "duration": 5.0}]
        # },
        # {
        #     "scene": 7,
        #     "section_title": "■ パターン7：画像4枚（グリッド）",
        #     "duration": 5.0,
        #     "text": "画像4枚のシーンです。2x2のグリッド状に並び、多くの情報を一度に提示できます。",
        #     "on_screen_text": [],
        #     "emotion": "excited",
        #     "image_type": "chart",
        #     "target_files": [valid_images[0], valid_images[0], valid_images[0], valid_images[0]],
        #     "segments": [{"text": "画像4枚のグリッドレイアウトテストです。", "start": 0.0, "duration": 5.0}]
        # },
        # {
        #     "scene": 8,
        #     "section_title": "■ パターン8：2行にわたる長い字幕",
        #     "duration": 6.0,
        #     "text": "この字幕は非常に長いため、2行にわたって表示されるはずです。下の文字が画面外にはみ出さず、綺麗に収まっているかを確認してください。",
        #     "on_screen_text": [
        #         "見出し：字幕位置の調整確認",
        #         "  └ y_posを上げたことで、2行になっても余裕を持って表示されるはずです。"
        #     ],
        #     "emotion": "normal",
        #     "image_type": "bg_only",
        #     "target_files": [],
        #     "segments": [{"text": "この字幕は非常に長いため、2行にわたって表示されるはずです。下の文字が画面外にはみ出さず、綺麗に収まっているかを確認してください。", "start": 0.0, "duration": 6.0}]
        # }
    ]

    print(f"🎬 シーン数: {len(scenes)} をレンダリング中...")
    
    # レンダリング実行
    result = render_scenes_to_video(
        scenes=scenes,
        output_path=output_path,
        assets_dir=assets_dir
    )
    
    if result:
        print(f"✅ 総合テスト動画が生成されました: {result}")
        print("\n【確認ポイント】")
        print("1. パターン1: テキストパネルが中央に大きく表示されているか")
        print("2. パターン2: 画像が画面いっぱいに表示されているか")
        print("3. パターン3: 画像が上、テキストが下に「重ならず」並んでいるか")
        print("4. パターン5: 複数画像でもテキスト用のスペースが確保されているか")
        print("5. パターン6: 画像3枚が逆三角形（上1、下2）に並んでいるか")
        print("6. パターン7: 画像4枚が2x2のグリッドに並んでいるか")
        print("7. パターン8: 2行の字幕が画面下部から浮いていて読みやすいか")
    else:
        print("❌ 動画生成に失敗しました。")

if __name__ == "__main__":
    create_test_video()
