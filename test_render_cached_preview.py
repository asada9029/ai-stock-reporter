"""
前回の本番/検証で生成済みの台本JSONから、無音で画面だけぱっと確認する。

- LLM / VOICEVOX / データ収集 不要
- 最新の data/scripts/scenes_*.json を自動選択（--scenes-json で指定可）
- セクションブリッジ（旧: 章頭の全画面カード）はデフォルトで除外
- segments が空でも dialogue から字幕用 segments を合成（レイアウト確認向け）

使い方:
  python test_render_cached_preview.py
  python test_render_cached_preview.py --scenes-json data/scripts/scenes_20260528_234003.json
  python test_render_cached_preview.py --max-scenes 8 --scene-duration 2
  python test_render_cached_preview.py --draft
  python test_render_cached_preview.py --scene-numbers 1,6,7,13 --scene-duration 3 --draft
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.analysis.dialogue_util import expand_scene_speech_units
from src.video_generation.structured_video_composer import render_scenes_to_video


def _find_latest_scenes_json() -> Path:
    scripts_dir = project_root / "data" / "scripts"
    candidates = sorted(
        list(scripts_dir.glob("scenes_*.json"))
        + list(scripts_dir.glob("scenes_validation_*.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"台本JSONがありません: {scripts_dir}/scenes_*.json\n"
            "先に main.py または test_immersive_script.py で台本を生成してください。"
        )
    return candidates[0]


def _load_scenes(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"台本JSONは配列である必要があります: {path}")
    return data


def _drop_bridge_scenes(scenes: list) -> tuple[list, int]:
    """visual_template=bridge の章頭カードを除く（プレビュー用）。"""
    kept = [sc for sc in scenes if sc.get("visual_template") != "bridge"]
    removed = len(scenes) - len(kept)
    return kept, removed


def _hydrate_preview_segments(sc: dict) -> bool:
    """segments 未生成JSON向け: dialogue/text から字幕タイミングを合成。"""
    if sc.get("segments"):
        return False
    if sc.get("section_title") == "subscribe":
        return False

    units = expand_scene_speech_units(sc)
    if not units:
        return False

    padding_before = float(sc.get("padding_before", 0.3))
    padding_after = float(sc.get("padding_after", 0.3))
    cursor = padding_before
    segments = []
    for unit in units:
        display = str(unit.get("text") or unit.get("speech_text") or "").strip()
        speech = str(unit.get("speech_text") or display).strip()
        if not display and not speech:
            continue
        # 長文はざっくり2分割（テロップ折返し確認用）
        parts = [display]
        if len(display) > 42:
            mid = len(display) // 2
            cut = display.rfind("、", 0, mid + 8)
            if cut < 12:
                cut = display.rfind("。", 0, mid + 8)
            if cut >= 12:
                parts = [display[: cut + 1].strip(), display[cut + 1 :].strip()]
        for part in parts:
            if not part:
                continue
            est = max(1.2, len(speech or part) / 5.5)
            segments.append(
                {
                    "text": part,
                    "duration": round(est, 3),
                    "start": round(cursor, 3),
                    "speaker": unit.get("speaker") or sc.get("speaker") or "minori",
                }
            )
            cursor += est

    if not segments:
        return False

    sc["segments"] = segments
    sc["duration"] = round(cursor + padding_after, 3)
    return True


def _filter_scene_numbers(scenes: list, numbers: str) -> list:
    wanted = {int(x.strip()) for x in numbers.split(",") if x.strip().isdigit()}
    if not wanted:
        return scenes
    return [sc for sc in scenes if int(sc.get("scene") or 0) in wanted]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成済み台本JSONから無音プレビュー（素材確認用）"
    )
    parser.add_argument(
        "--scenes-json",
        default=None,
        help="台本JSON（未指定時は data/scripts の最新）",
    )
    parser.add_argument(
        "--presentation",
        choices=["classic", "immersive"],
        default="immersive",
    )
    parser.add_argument(
        "--out",
        default="output/render_cached_preview.mp4",
        help="出力MP4パス",
    )
    parser.add_argument(
        "--max-scenes",
        type=int,
        default=0,
        help="先頭Nシーンのみ（0=全シーン）",
    )
    parser.add_argument(
        "--scene-duration",
        type=float,
        default=0.0,
        help="全シーンの尺を上書き（例: 2.0）。0=JSONのまま",
    )
    parser.add_argument(
        "--scene-numbers",
        default="",
        help="指定シーン番号のみ（例: 1,6,7,13）。今回の修正確認向け",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="字幕（segments）を非表示",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="1280x720・低ビットレートで高速化（本番と見た目がずれる）",
    )
    parser.add_argument(
        "--keep-bridges",
        action="store_true",
        help="章頭ブリッジシーンも含める（通常は除外）",
    )
    args = parser.parse_args()

    path = Path(args.scenes_json) if args.scenes_json else _find_latest_scenes_json()
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        print(f"[NG] ファイルがありません: {path}")
        sys.exit(1)

    scenes = _load_scenes(path)
    print(f"[Load] {path} ({len(scenes)} シーン)")

    if not args.keep_bridges:
        scenes, removed = _drop_bridge_scenes(scenes)
        if removed:
            print(f"[Filter] 章頭ブリッジ {removed} シーンを除外（--keep-bridges で復活）")

    if args.max_scenes > 0:
        scenes = scenes[: args.max_scenes]
        print(f"[Preview] 先頭 {len(scenes)} シーンのみ")

    if args.scene_numbers.strip():
        scenes = _filter_scene_numbers(scenes, args.scene_numbers)
        print(f"[Preview] 指定シーンのみ: {args.scene_numbers} -> {len(scenes)} シーン")

    hydrated = 0
    from src.analysis.japanese_text import (
        is_mostly_english_display,
        normalize_scenes_japanese_display,
        prefer_japanese_display,
    )

    n_ja = normalize_scenes_japanese_display(scenes)
    if n_ja:
        print(f"[JA] 表示テキストを日本語寄りに正規化: {n_ja} シーン")

    for i, sc in enumerate(scenes):
        if _hydrate_preview_segments(sc):
            hydrated += 1
        # 既存 segments の英語テロップも保険で差し替え
        speech = str(sc.get("speech_text") or "")
        for seg in sc.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            seg_text = str(seg.get("text") or "")
            if is_mostly_english_display(seg_text):
                seg["text"] = prefer_japanese_display(seg_text, speech) or speech or seg_text
        if args.scene_duration > 0:
            sc["duration"] = float(args.scene_duration)
            segs = sc.get("segments") or []
            if segs:
                pad = 0.6
                usable = max(0.5, float(args.scene_duration) - pad)
                each = usable / len(segs)
                t = 0.3
                for seg in segs:
                    seg["duration"] = round(each, 3)
                    seg["start"] = round(t, 3)
                    t += each
        elif not sc.get("duration"):
            sc["duration"] = 5.0
        sc["scene"] = i + 1
        sc.setdefault("segments", [])
    if hydrated:
        print(f"[Preview] dialogue から字幕 segments を合成: {hydrated} シーン")

    # 本番 main.py と同じ 1920x1080 がデフォルト（720p だと文字が相対的に大きく画像が小さく見える）
    size = (1920, 1080)
    fps = 24
    if args.draft:
        size = (1280, 720)
        fps = 12
        os.environ["DRAFT_RENDER"] = "1"
    else:
        os.environ.pop("DRAFT_RENDER", None)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = project_root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"[Render] {args.presentation} / {size[0]}x{size[1]} @{fps}fps -> {out_path}"
    )
    result = render_scenes_to_video(
        scenes=scenes,
        output_path=str(out_path),
        assets_dir="src/assets",
        size=size,
        fps=fps,
        show_subtitles=not args.no_subtitles,
        presentation_mode=args.presentation,
    )

    if result and Path(result).exists():
        print(f"[OK] {result}")
    else:
        print("[NG] レンダリング失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
