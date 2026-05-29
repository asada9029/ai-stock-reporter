"""
セクションブリッジ画像（Pillow）を一括生成する。

出力: src/assets/images/bridge_{section_key}.png
  （structured_pipeline の _inject_section_bridges とファイル名が一致）

使い方:
  python generate_bridge_images.py
  python generate_bridge_images.py --type evening_video
  python generate_bridge_images.py --type morning_video --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.video_generation.bridge_image_generator import BridgeImageGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description="ブリッジ画像（Pillow）一括生成")
    parser.add_argument(
        "--type",
        choices=["morning_video", "evening_video"],
        default="evening_video",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="朝・夜両方を生成",
    )
    parser.add_argument(
        "--assets-dir",
        default="src/assets",
    )
    parser.add_argument(
        "--skip-opening",
        action="store_true",
        help="opening 用 bridge_opening.png は作らない（章頭カード不要な場合）",
    )
    args = parser.parse_args()

    gen = BridgeImageGenerator(assets_dir=args.assets_dir)
    types = ["morning_video", "evening_video"] if args.all else [args.type]

    print(f"[Bridge] 出力先: {gen.images_dir}")
    for vt in types:
        print(f"\n=== {vt} ===")
        gen.generate_for_video_type(
            vt,
            skip_opening=args.skip_opening,
        )

    print("\n[OK] 完了。本番で使う場合は USE_SECTION_BRIDGES=1 でパイプラインを実行してください。")


if __name__ == "__main__":
    main()
