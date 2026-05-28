"""
ショート動画のレイアウト確認（LLM不要・固定ダミー台本）。

使い方:
  $env:SKIP_VOICE="1"
  $env:DRAFT_RENDER="1"
  python test_shorts_layout.py
  python test_shorts_layout.py --type shorts_b
"""
import os
import sys
import json
import argparse
from pathlib import Path

project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.video_generation.structured_pipeline import compose_video_from_analysis


def _ensure_placeholder() -> str:
    p = Path("data/images/placeholder.png")
    if p.exists():
        return str(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw

    w, h = 1280, 720
    img = Image.new("RGB", (w, h), (235, 245, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, w - 40, h - 40), outline=(120, 150, 190), width=6)
    img.save(p, "PNG")
    return str(p)


def _dummy_scenes(shorts_type: str) -> list:
    placeholder = _ensure_placeholder()
    if shorts_type == "shorts_a":
        return [
            {
                "scene": 1,
                "section_title": "",
                "duration": 5.0,
                "text": "こんにちは、株野みのりです！今日の株用語をやさしく解説します。",
                "on_screen_text": [
                    "■テスト用語",
                    "・かみ砕いた解説1行目",
                    "・かみ砕いた解説2行目",
                    "・初心者へのアドバイス",
                ],
                "explained_term": "テスト用語",
                "emotion": "normal",
                "image_type": "chart",
                "bg_name": "bg_illust.png",
                "target_files": [placeholder],
            }
        ]
    # shorts_b
    dummy_chart = "output/stock_charts/dummy_square.png"
    os.makedirs("output/stock_charts", exist_ok=True)
    from PIL import Image

    img = Image.new("RGB", (800, 600), color=(73, 109, 137))
    img.save(dummy_chart)
    return [
        {
            "scene": 1,
            "section_title": "",
            "duration": 5.0,
            "text": "注目銘柄のチャートを見てみましょう。",
            "on_screen_text": [
                "■ダミー企業A",
                "・直近1ヶ月で20%の上昇",
                "・好決算を受けて買いが加速",
                "・さらなる高値更新に期待",
            ],
            "emotion": "normal",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [dummy_chart],
        }
    ]


def test_shorts_layout_dummy(shorts_type: str = "shorts_a") -> None:
    print(f"[Layout] ショート動画レイアウト確認（ダミー台本）: {shorts_type}")

    pre_generated_scenes = _dummy_scenes(shorts_type)
    analysis_data = {
        "selected_thumbnail_title": "テスト",
        "selected_highlights": ["要点"],
        "main_news_index": 0,
        "highlight_indices": [0],
        "attention_news": [{"title": "ニュース", "snippet": "テスト"}],
        "sector_analysis": {"sectors": []},
    }

    structure_path = project_root / "src/config/video_structure.json"
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    video_structure = structures.get(shorts_type)

    draft = os.getenv("DRAFT_RENDER", "").strip().lower() in ("1", "true", "yes")
    video_size = (540, 960) if draft else (1080, 1920)
    video_path = f"output/layout_check_{shorts_type}_noaudio.mp4"

    result_path, _, _, _, _ = compose_video_from_analysis(
        video_structure=video_structure,
        analysis_data=analysis_data,
        enriched_data={},
        output_video=video_path,
        assets_dir="src/assets",
        video_type=shorts_type,
        size=video_size,
        pre_generated_scenes=pre_generated_scenes,
    )

    if result_path and os.path.exists(result_path):
        print(f"[OK] レイアウト確認用動画: {result_path}")
    else:
        print("[NG] 動画生成失敗")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ショートレイアウト確認（LLM不要）")
    parser.add_argument("--type", choices=["shorts_a", "shorts_b", "both"], default="both")
    args = parser.parse_args()
    if args.type == "both":
        test_shorts_layout_dummy("shorts_a")
        test_shorts_layout_dummy("shorts_b")
    else:
        test_shorts_layout_dummy(args.type)
