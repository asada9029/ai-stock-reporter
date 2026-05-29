"""
ステップ3: 短縮パイプライン（VOICEVOX + BGM + セクションSE）

使い方:
  python test_immersive_pipeline.py
  python test_immersive_pipeline.py --presentation immersive
  python test_immersive_pipeline.py --scenes-json data/scripts/scenes_validation_evening_immersive_xxx.json
  python test_immersive_pipeline.py --presentation both
"""

from __future__ import annotations

import argparse
import os
import sys

from immersive_test_utils import (
    build_pipeline_scenes,
    ensure_output_dir,
    load_scenes_json,
    load_video_structure,
    minimal_analysis_data,
    patch_pipeline_no_thumbnail,
    print_step3_checklist,
)
from src.video_generation.structured_pipeline import compose_video_from_analysis


def run_pipeline_test(
    *,
    presentation: str = "immersive",
    video_category: str = "evening",
    scenes_json: str | None = None,
    use_builtin_scenes: bool = True,
) -> int:
    video_type = f"{video_category}_video"
    ensure_output_dir()

    if scenes_json:
        scenes, scenes_path = load_scenes_json(scenes_json)
        print(f"台本JSONを使用: {scenes_path} ({len(scenes)} シーン、subscribe 前)")
        # パイプラインが subscribe を足すため、JSON に含まれていればそのまま
        pre_generated = scenes
    elif use_builtin_scenes:
        pre_generated = None
        print("内蔵の短い台本（3シーン）を使用")
    else:
        pre_generated = None

    video_structure = load_video_structure(video_type)
    analysis_data = minimal_analysis_data()

    modes = ["classic", "immersive"] if presentation == "both" else [presentation]
    ok = True

    for mode in modes:
        out = ensure_output_dir() / f"step3_pipeline_{video_category}_{mode}.mp4"
        scenes = pre_generated
        if scenes is None:
            scenes = build_pipeline_scenes(mode)

        print(f"\n[Step3] {mode} パイプライン -> {out}")
        print("  (要) VOICEVOX http://localhost:50021")

        with patch_pipeline_no_thumbnail():
            try:
                result = compose_video_from_analysis(
                    video_structure=video_structure,
                    analysis_data=analysis_data,
                    enriched_data={},
                    output_video=str(out),
                    assets_dir="src/assets",
                    size=(1920, 1080),
                    fps=24,
                    video_type=video_type,
                    pre_generated_scenes=scenes,
                    presentation_mode=mode,
                )
            except Exception as e:
                print(f"  [NG] エラー: {e}")
                import traceback

                traceback.print_exc()
                ok = False
                continue

        video_path, thumb_path, thumb_title, highlights, chapters = result
        if video_path and os.path.exists(video_path):
            print(f"  [OK] 動画: {video_path}")
            if chapters:
                print("  チャプター（先頭のみ）:")
                for line in chapters.splitlines()[:5]:
                    print(f"     {line}")
        else:
            print("  [NG] 動画生成失敗")
            ok = False

        print_step3_checklist(mode)

    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="immersive 短縮パイプライン（ステップ3）")
    parser.add_argument("--type", choices=["evening", "morning"], default="evening")
    parser.add_argument(
        "--presentation",
        choices=["classic", "immersive", "both"],
        default="immersive",
    )
    parser.add_argument(
        "--scenes-json",
        default=None,
        help="ステップ2で保存した台本JSON（未指定時は内蔵3シーン）",
    )
    args = parser.parse_args()
    sys.exit(
        run_pipeline_test(
            presentation=args.presentation,
            video_category=args.type,
            scenes_json=args.scenes_json,
            use_builtin_scenes=args.scenes_json is None,
        )
    )


if __name__ == "__main__":
    main()
