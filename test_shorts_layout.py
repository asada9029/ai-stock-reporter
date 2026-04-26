import os
import sys
import json
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.video_generation.structured_pipeline import compose_video_from_analysis

def test_shorts_layout_dummy(shorts_type="shorts_a"):
    print(f"🚀 ショート動画レイアウト確認（完全ダミー台本）: {shorts_type}")
    
    # 1. 案B用のダミーチャート画像準備
    dummy_img_path = "output/stock_charts/dummy_square.png"
    if shorts_type == "shorts_b":
        os.makedirs("output/stock_charts", exist_ok=True)
        from PIL import Image
        img = Image.new('RGB', (800, 600), color=(73, 109, 137))
        img.save(dummy_img_path)

    # 2. 完全ダミーの台本（シーン配列）を定義
    if shorts_type == "shorts_a":
                # 案A: テキストのみ
                pre_generated_scenes = [
                    {
                        "scene": 1,
                        "section_title": "",
                        "duration": 5.0,
                        "text": "こんにちは、株野みのりです！今日の重要ニュースを3つ、爆速でお伝えしますね。",
                        "on_screen_text": [
                            "■ 今日の3大ニュース",
                            "1. 日経平均が史上最高値を更新！\n   半導体株中心に買いが加速しています。\n",
                            "2. 米国株もハイテク中心に強い動き\n   利下げ期待が相場を支えています。\n",
                            "3. 円安が進行し、輸出関連株に買い\n   為替の動きに注目が集まっています。"
                        ],
                        "emotion": "happy",
                        "image_type": "bg_only",
                        "bg_name": "bg_illust.png",
                        "target_files": []
                    }
                ]
    else:
        # 案B: 画像＋テキスト
        pre_generated_scenes = [
            {
                "scene": 1,
                "section_title": "",
                "duration": 5.0,
                "text": "注目銘柄のチャートを見てみましょう。こちらの銘柄、強い上昇トレンドが続いていますね。",
                "on_screen_text": ["■ 注目銘柄：ダミー企業A", "・直近1ヶ月で20%の上昇", "・好決算を受けて買いが加速", "・さらなる高値更新に期待です"],
                "emotion": "confident",
                "image_type": "chart",
                "bg_name": "bg_illust.png",
                "target_files": [dummy_img_path]
            }
        ]

    # 3. 最小限の分析データ（pipelineのバリデーション回避用）
    analysis_data = {
        "selected_thumbnail_title": "テスト",
        "selected_highlights": ["要点"],
        "main_news_index": 0,
        "highlight_indices": [0],
        "attention_news": [{"title": "ニュース", "snippet": "テスト"}],
        "sector_analysis": {"sectors": []}
    }
    
    # 4. 構成の読み込み
    structure_path = project_root / "src/config/video_structure.json"
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    video_structure = structures.get(shorts_type)
    
    # 5. 動画生成
    video_path = f"output/layout_check_{shorts_type}.mp4"
    video_size = (1080, 1920)
    
    result_path, thumb_path, thumb_title, thumb_highlights = compose_video_from_analysis(
        video_structure=video_structure,
        analysis_data=analysis_data,
        enriched_data={},
        output_video=video_path,
        assets_dir="src/assets",
        video_type=shorts_type,
        size=video_size,
        pre_generated_scenes=pre_generated_scenes # ダミー台本を直接渡す
    )
    
    if result_path and os.path.exists(result_path):
        print(f"✅ レイアウト確認用動画生成成功: {result_path}")
    else:
        print("❌ 動画生成失敗")

if __name__ == "__main__":
    # 案Aのレイアウト確認
    test_shorts_layout_dummy("shorts_a")
    # 案Bのレイアウト確認
    test_shorts_layout_dummy("shorts_b")
