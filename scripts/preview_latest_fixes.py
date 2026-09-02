"""今回の修正点をフル本番なしでざっくり確認するラッパー。

1) 図解PNG（日本語・省略長）… 数秒
2) 代表シーンの無音MP4（字幕・レイアウト）… 1〜3分

使い方:
  python scripts/preview_latest_fixes.py
  python scripts/preview_latest_fixes.py --diagrams-only
  python scripts/preview_latest_fixes.py --layout-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 今回の修正確認に効く代表シーン（opening を必ず含める）
KEY_SCENES = "1,6,7,9,13"


def _find_opening_scene_number(scenes_path: Path) -> int | None:
    try:
        data = json.loads(scenes_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for sc in data:
        if not isinstance(sc, dict):
            continue
        title = str(sc.get("section_title") or "")
        if "トピック" in title or "opening" in title.lower():
            num = sc.get("scene")
            if isinstance(num, int):
                return num
    return None


def _production_like_opening_scene() -> dict:
    """本番 opening に近い固定フィクスチャ（台本JSONが無いとき用）。"""
    return {
        "scene": 0,
        "section_title": "本日のトピック",
        "duration": 8.0,
        "text": "みなさん、こんにちは。株野みのりです。",
        "speech_text": "みなさん、こんにちは。かぶのみのりです。",
        "on_screen_text": [
            "・市場：ベッセント発言で円高警戒",
            "・注目：【スクエニHD急伸】非公開化思惑",
            "・材料：デルタフライ・ブレインズ買われる",
            "・セクター：電力・エネルギーへ資金集中",
            "・今夜：米8月ISM景況感・JOLTS注目",
        ],
        "emotion": "happy",
        "image_type": "character_only",
        "bg_name": "bg_illust.png",
        "target_files": [],
        "speaker": "minori",
        "segments": [
            {
                "text": "みなさん、本日もお疲れ様です。",
                "duration": 2.5,
                "start": 0.3,
                "speaker": "minori",
            },
            {
                "text": "株野みのりです。",
                "duration": 1.8,
                "start": 2.9,
                "speaker": "minori",
            },
        ],
    }


def _latest(path_glob: str) -> Path | None:
    files = sorted(ROOT.glob(path_glob), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def preview_diagrams_from_data() -> int:
    agg = _latest("data/collected_data/aggregated_data_morning_*.json")
    if not agg:
        print("[Skip] aggregated_data_morning_*.json がありません（図解のみダミー）")
        return subprocess.call([sys.executable, str(ROOT / "scripts/preview_diagrams.py")])

    from src.data_collection.data_aggregator import DataAggregator
    from src.video_generation.diagram_generator import (
        generate_impact_flow_diagram,
        generate_news_bundle_diagram,
        _prefer_ja_text,
    )
    import shutil

    data = json.loads(agg.read_text(encoding="utf-8"))
    news = data.get("attention_news") or []
    out = ROOT / "output" / "fix_preview" / "diagrams"
    out.mkdir(parents=True, exist_ok=True)

    agg_obj = DataAggregator()
    try:
        agg_obj._enrich_news_display_ja(news)
    except Exception as e:
        print(f"[WARN] title_ja enrich: {e}")

    bundle = generate_news_bundle_diagram(
        news,
        output_path=out / "news_bundle.png",
        title="本日の主要ニュース",
    )
    honmei = next((n for n in news if n.get("slot") == "honmei"), news[0] if news else {})
    heat = next((n for n in news if n.get("slot") == "heat"), None)

    def _ja(n: dict, fallback: str = "", limit: int = 64) -> str:
        if not n:
            return fallback
        raw = _prefer_ja_text(
            str(n.get("title_ja") or ""),
            str(n.get("snippet") or ""),
            str(n.get("summary") or ""),
            str(n.get("title") or ""),
            min_len=2,
        )
        text = (raw or fallback).strip()
        return text[:limit] if limit else text

    bullets = []
    for n in news[:3]:
        tip = _prefer_ja_text(
            str(n.get("snippet") or ""),
            str(n.get("title_ja") or ""),
            str(n.get("title") or ""),
            min_len=4,
        )
        if tip:
            bullets.append(tip[:80])
    flow = generate_impact_flow_diagram(
        left_label=_ja(honmei, "本命ニュース", 40),
        mid_label=_ja(heat or {}, "市場・セクター", 36),
        right_label="日本株への影響",
        output_path=out / "impact_flow.png",
        left_sub="",
        mid_sub="金利・業績・需給",
        right_sub="個別より選別",
        bullets=bullets,
    )
    print(f"[OK] diagrams -> {out}")
    print("  bundle:", bundle)
    print("  flow:", flow)

    # 動画プレビューが古い英語PNGを見ないよう collected 側も上書き
    collected = ROOT / "output" / "collected" / "diagrams" / "morning"
    collected.mkdir(parents=True, exist_ok=True)
    if bundle:
        shutil.copy2(bundle, collected / "news_bundle.png")
    if flow:
        shutil.copy2(flow, collected / "impact_flow.png")
    print(f"[OK] copied to {collected}")
    return 0


def preview_layout_clips(draft: bool = True) -> int:
    scenes = _latest("data/scripts/scenes_*.json")
    out = ROOT / "output" / "fix_preview" / "layout_check.mp4"

    if scenes:
        opening_num = _find_opening_scene_number(scenes)
        parts = [p.strip() for p in KEY_SCENES.split(",") if p.strip()]
        if opening_num is not None and str(opening_num) not in parts:
            parts.insert(0, str(opening_num))
        scene_numbers = ",".join(dict.fromkeys(parts))
        cmd = [
            sys.executable,
            str(ROOT / "test_render_cached_preview.py"),
            "--scenes-json",
            str(scenes.relative_to(ROOT)),
            "--scene-numbers",
            scene_numbers,
            "--scene-duration",
            "3",
            "--presentation",
            "immersive",
            "--out",
            str(out.relative_to(ROOT)),
        ]
    else:
        print("[WARN] scenes_*.json なし → opening 固定フィクスチャでプレビュー")
        fixture_path = ROOT / "output" / "fix_preview" / "opening_fixture.json"
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(
            json.dumps([_production_like_opening_scene()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cmd = [
            sys.executable,
            str(ROOT / "test_render_cached_preview.py"),
            "--scenes-json",
            str(fixture_path.relative_to(ROOT)),
            "--scene-duration",
            "5",
            "--presentation",
            "immersive",
            "--out",
            str(out.relative_to(ROOT)),
        ]

    if draft:
        cmd.append("--draft")
    print("[Run]", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc == 0:
        _extract_preview_frames(out)
    return rc


def _extract_preview_frames(mp4: Path) -> None:
    dest = ROOT / "output" / "fix_preview" / "frames"
    dest.mkdir(parents=True, exist_ok=True)
    times = [1.2, 4.2, 7.5, 10.5, 13.2]
    try:
        from moviepy import VideoFileClip

        clip = VideoFileClip(str(mp4))
        for i, t in enumerate(times, 1):
            t = min(float(t), max(0.0, float(clip.duration) - 0.05))
            clip.save_frame(str(dest / f"scene_{i}.png"), t=t)
            print(f"[Frame] {dest / f'scene_{i}.png'} @ {t:.1f}s")
        clip.close()
    except Exception as e:
        print(f"[WARN] frame extract: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="修正点の軽量プレビュー")
    parser.add_argument("--diagrams-only", action="store_true")
    parser.add_argument("--layout-only", action="store_true")
    parser.add_argument("--full-res", action="store_true", help="720p draft をやめて 1080p")
    args = parser.parse_args()

    rc = 0
    if args.layout_only:
        rc = preview_layout_clips(draft=not args.full_res)
    elif args.diagrams_only:
        rc = preview_diagrams_from_data()
    else:
        print("[1/2] diagrams", flush=True)
        rc = preview_diagrams_from_data()
        if rc == 0:
            print("[2/2] layout", flush=True)
            rc = preview_layout_clips(draft=not args.full_res)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
