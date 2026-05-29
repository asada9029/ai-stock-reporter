"""
ショート台本（LLM）だけを生成して確認する（VOICEVOX不要）。

使い方:
  python test_shorts_script.py --type shorts_a --category evening
  python test_shorts_script.py --type shorts_a --category morning

出力:
  data/scripts/shorts_script_<type>_<category>_<ts>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.analysis.script_generator import ScriptGenerator


def load_latest_aggregated(category: str) -> tuple[dict, Path]:
    data_dir = Path("data/collected_data")
    files = sorted(data_dir.glob(f"aggregated_data_{category}_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(f"集約データがありません: {data_dir}/aggregated_data_{category}_*.json")
    p = files[0]
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f), p


def load_video_structure(video_type: str) -> dict:
    structure_path = Path("src/config/video_structure.json")
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    vs = structures.get(video_type)
    if not vs:
        raise KeyError(f"video_structure.json に {video_type} がありません")
    return vs


def main() -> None:
    parser = argparse.ArgumentParser(description="ショート台本生成（VOICEVOX不要）")
    parser.add_argument("--type", choices=["shorts_a", "shorts_b"], default="shorts_a")
    parser.add_argument("--category", choices=["morning", "evening"], default="evening")
    args = parser.parse_args()

    analysis_data, p = load_latest_aggregated(args.category)
    print(f"[Data] {p}")

    video_structure = load_video_structure(args.type)
    sg = ScriptGenerator()
    scenes = sg.generate_structured_scenes(video_structure=video_structure, analysis_data=analysis_data)

    # 簡易表示
    print(f"[OK] scenes={len(scenes)}")
    if scenes:
        s0 = scenes[0]
        print("--- Scene0 on_screen_text ---")
        ost = s0.get("on_screen_text") or []
        if isinstance(ost, str):
            ost = [ost]
        for line in ost:
            print(f"  {line}")

    out_dir = Path("data/scripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"shorts_script_{args.type}_{args.category}_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)
    print(f"[Save] {out}")


if __name__ == "__main__":
    sys.exit(main())

