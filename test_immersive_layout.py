"""
ステップ1: immersive / classic レイアウト比較（無音・LLM不要・VOICEVOX不要）

使い方:
  python test_immersive_layout.py
  python test_immersive_layout.py --mode immersive
"""

from __future__ import annotations

import argparse
import sys

from immersive_test_utils import (
    build_layout_scenes,
    ensure_output_dir,
    print_step1_checklist,
)
from src.video_generation.structured_video_composer import render_scenes_to_video


def run_layout_test(mode: str = "both") -> int:
    ensure_output_dir()
    modes = ["classic", "immersive"] if mode == "both" else [mode]
    ok = True

    for m in modes:
        out = ensure_output_dir() / f"step1_layout_{m}.mp4"
        scenes = build_layout_scenes(m)
        print(f"\n[Step1] {m} をレンダリング ({len(scenes)} シーン) -> {out}")
        result = render_scenes_to_video(
            scenes=scenes,
            output_path=str(out),
            assets_dir="src/assets",
            size=(1920, 1080),
            fps=24,
            show_subtitles=False,
            presentation_mode=m,
        )
        if result:
            print(f"  [OK] {result}")
        else:
            print(f"  [NG] 失敗: {m}")
            ok = False

    print_step1_checklist()
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="immersive レイアウト比較（ステップ1）")
    parser.add_argument(
        "--mode",
        choices=["both", "classic", "immersive"],
        default="both",
        help="生成するモード（default: both）",
    )
    args = parser.parse_args()
    sys.exit(run_layout_test(args.mode))


if __name__ == "__main__":
    main()
