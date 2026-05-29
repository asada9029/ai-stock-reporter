"""
ステップ2: 台本生成のみ（LLM・集約JSON再利用）

使い方:
  python test_immersive_script.py --type evening --presentation immersive
  python test_immersive_script.py --type evening --presentation both
  python test_immersive_script.py --type evening --presentation classic --no-save
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from immersive_test_utils import (
    SCRIPTS_DIR,
    load_aggregated_data,
    load_video_structure,
    print_step2_checklist,
)
from src.analysis.script_generator import ScriptGenerator


def _analyze_scenes(scenes: list, presentation: str) -> None:
    has_block = False
    long_lines = 0
    for i, sc in enumerate(scenes):
        on_screen = sc.get("on_screen_text") or []
        if isinstance(on_screen, str):
            on_screen = [on_screen]
        for line in on_screen:
            s = str(line)
            if "■" in s or "└" in s:
                has_block = True
            if len(s) > 18:
                long_lines += 1
        section = sc.get("section_title", "")
        if i < 3:
            print(f"\n--- Scene {sc.get('scene', i+1)}: {section} ---")
            speech = sc.get("speech_text") or sc.get("text", "")
            print(f"  speech(先頭80字): {str(speech)[:80]}...")
            print(f"  on_screen_text: {on_screen}")

    print(f"\n[Check] 自動チェック ({presentation}):")
    if presentation == "immersive":
        print(f"  ■/└ を含む行: {'あり [WARN]' if has_block else 'なし [OK]'}")
        print(f"  18文字超の行数: {long_lines} {'[WARN]' if long_lines else '[OK]'}")
    print(f"  シーン数: {len(scenes)}")


def run_script_test(
    video_category: str,
    presentation: str,
    *,
    save: bool = True,
) -> int:
    video_type = f"{video_category}_video"
    print(f"[Step2] 台本生成 ({video_type}, presentation={presentation})")

    try:
        analysis_data, data_path = load_aggregated_data(video_category)
        print(f"  集約データ: {data_path}")
    except FileNotFoundError as e:
        print(f"[NG] {e}")
        return 1

    analysis_data.setdefault("selected_thumbnail_title", "【検証】サムネ未生成")
    analysis_data.setdefault("selected_highlights", [])
    analysis_data.setdefault("main_news_index", 0)
    analysis_data.setdefault("highlight_indices", [])

    video_structure = load_video_structure(video_type)
    enriched = {"prev_ir_analysis": analysis_data.get("prev_ir_analysis", [])}

    modes = ["classic", "immersive"] if presentation == "both" else [presentation]
    sg = ScriptGenerator()
    exit_code = 0

    for mode in modes:
        print(f"\n  LLM 台本生成中... ({mode})")
        try:
            scenes = sg.generate_structured_scenes(
                video_structure=video_structure,
                analysis_data=analysis_data,
                enriched_data=enriched,
                presentation_mode=mode,
            )
        except Exception as e:
            print(f"[NG] {mode}: {e}")
            exit_code = 1
            continue

        _analyze_scenes(scenes, mode)
        print_step2_checklist(mode)

        if save:
            SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = SCRIPTS_DIR / f"scenes_validation_{video_category}_{mode}_{ts}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"  保存: {out_path}")
            print(f"  → ステップ3: python test_immersive_pipeline.py --scenes-json {out_path}")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="immersive 台本検証（ステップ2）")
    parser.add_argument("--type", choices=["evening", "morning"], default="evening")
    parser.add_argument(
        "--presentation",
        choices=["classic", "immersive", "both"],
        default="immersive",
    )
    parser.add_argument("--no-save", action="store_true", help="JSON を保存しない")
    args = parser.parse_args()
    sys.exit(
        run_script_test(
            args.type,
            args.presentation,
            save=not args.no_save,
        )
    )


if __name__ == "__main__":
    main()
