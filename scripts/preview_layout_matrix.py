"""immersive レイアウトの文字量・チャート枚数マトリクス確認。

opening / テキストのみ（短・中・長）/ 1チャート+テキスト / 2チャート+テキスト を
1本の無音MP4に並べ、1080p で本番に近い見え方を確認する。

使い方:
  python scripts/preview_layout_matrix.py
  python scripts/preview_layout_matrix.py --draft
  python scripts/preview_layout_matrix.py --frames-only
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "output" / "fix_preview"
CHART_DIR = OUT_DIR / "matrix_charts"
SCENES_JSON = OUT_DIR / "layout_matrix_scenes.json"
MP4_OUT = OUT_DIR / "layout_matrix.mp4"
FRAMES_DIR = OUT_DIR / "matrix_frames"


def _seg(text: str, *, duration: float = 3.0) -> list:
    return [
        {
            "text": text,
            "duration": duration,
            "start": 0.25,
            "speaker": "minori",
            "emotion": "normal",
        }
    ]


def _make_dummy_chart(path: Path, *, label: str, seed: int) -> str:
    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    w, h = 960, 540
    img = Image.new("RGB", (w, h), (252, 252, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 44), fill=(245, 248, 252))
    draw.text((16, 10), label[:24], fill=(40, 60, 90))
    draw.line((24, 480, w - 24, 480), fill=(180, 190, 205), width=2)

    x = 36
    price = 100.0
    for i in range(36):
        o = price
        c = o + rng.uniform(-2.8, 3.2)
        hi = max(o, c) + rng.uniform(0.2, 1.4)
        lo = min(o, c) - rng.uniform(0.2, 1.4)
        price = c
        cx = x + 8
        color = (210, 70, 70) if c >= o else (60, 130, 210)
        draw.line((cx, 480 - hi * 3.2, cx, 480 - lo * 3.2), fill=color, width=2)
        body_top = 480 - max(o, c) * 3.2
        body_bot = 480 - min(o, c) * 3.2
        draw.rectangle((cx - 5, body_top, cx + 5, body_bot), fill=color)
        vol_h = rng.randint(8, 36)
        draw.rectangle((cx - 4, 480 - vol_h, cx + 4, 480), fill=(170, 180, 195))
        x += 24

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return str(path.resolve())


def ensure_matrix_charts() -> tuple[str, str]:
    chart_a = _make_dummy_chart(CHART_DIR / "chart_inpex.png", label="1605 INPEX", seed=11)
    chart_b = _make_dummy_chart(CHART_DIR / "chart_eneos.png", label="5020 ENEOS HD", seed=23)
    return chart_a, chart_b


def build_matrix_scenes() -> list[dict]:
    chart_a, chart_b = ensure_matrix_charts()
    common = {
        "duration": 3.5,
        "emotion": "normal",
        "image_type": "bg_only",
        "bg_name": "bg_illust.png",
        "target_files": [],
        "speaker": "minori",
    }

    return [
        {
            **common,
            "scene": 1,
            "section_title": "本日のトピック",
            "text": "本日のトピックです。",
            "on_screen_text": [
                "・市場：ベッセント発言で円高警戒",
                "・注目：スクエニHD急伸・非公開化思惑",
                "・材料：デルタフライ・ブレインズ買われる",
                "・セクター：電力・エネルギーへ資金集中",
                "・今夜：米8月ISM景況感・JOLTS注目",
            ],
            "segments": _seg("本日のトピックを5項目で確認します。"),
        },
        {
            **common,
            "scene": 2,
            "section_title": "米国セクター分析：ハイテク・サービス",
            "text": "短い箇条書きの密度確認です。",
            "on_screen_text": [
                "・半導体に買い殺到",
                "・クラウド需要堅調",
                "・AI支援投資拡大",
            ],
            "segments": _seg("短い3行テキストの見え方を確認します。"),
        },
        {
            **common,
            "scene": 3,
            "section_title": "米国セクター分析：買われたハイテク・サービス分野",
            "text": "中程度の文字量です。",
            "on_screen_text": [
                "・半導体全般に買い注文が殺到",
                "・KyndrylがBroadcomと提携強化",
                "・企業向けクラウド需要の堅調さ確認",
                "・AI導入支援サービスへの投資拡大",
            ],
            "segments": _seg("4行・中程度の文字量でカードの余白を確認します。"),
        },
        {
            **common,
            "scene": 4,
            "section_title": "セクター概要：資金フローと選別の動き",
            "text": "長めの箇条書きです。",
            "on_screen_text": [
                "・米国ハイテク・サービス分野で資金が集中し買い優勢",
                "・半導体関連は決算期待とAI需要の追い風で全般高",
                "・クラウドインフラ需要は堅調で関連銘柄に買い継続",
                "・エンタープライズ向けAI導入支援への投資拡大が続く",
                "・日本株も連れ高期待だが選別姿勢は維持",
            ],
            "segments": _seg("5行・長文で折返しと縦幅のバランスを確認します。"),
        },
        {
            **common,
            "scene": 5,
            "section_title": "セクター概要：鉱業・石油セクター買われる",
            "text": "1チャートと右テキストの配置確認です。",
            "image_type": "chart",
            "target_files": [chart_a],
            "on_screen_text": [
                "INPEXが4000円台回復",
                "ENEOSなど石油元売りに買い",
                "原油高で鉱業・石油セクター強い",
            ],
            "segments": _seg("1枚チャートの下に要約テキストが来る上下レイアウトを確認します。"),
        },
        {
            **common,
            "scene": 6,
            "section_title": "セクター概要：鉱業・石油セクター買われる",
            "text": "2チャートと右テキストの配置確認です。",
            "image_type": "chart",
            "target_files": [chart_a, chart_b],
            "on_screen_text": [
                "INPEXが4000円台を回復",
                "ENEOSホールディングスなど石油元売り各社にも買い",
                "原油高で資源セクター全体に資金流入",
            ],
            "segments": _seg("左に2枚縦並びチャート、右に要約テキストのレイアウトを確認します。"),
        },
    ]


def write_scenes_json(scenes: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_JSON.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    return SCENES_JSON


def render_matrix(*, draft: bool) -> int:
    scenes = build_matrix_scenes()
    scenes_path = write_scenes_json(scenes)
    cmd = [
        sys.executable,
        str(ROOT / "test_render_cached_preview.py"),
        "--scenes-json",
        str(scenes_path.relative_to(ROOT)),
        "--scene-duration",
        "3.5",
        "--presentation",
        "immersive",
        "--out",
        str(MP4_OUT.relative_to(ROOT)),
    ]
    if draft:
        cmd.append("--draft")
    print("[Run]", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def extract_frames() -> None:
    if not MP4_OUT.exists():
        print(f"[Skip] MP4 がありません: {MP4_OUT}")
        return
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    labels = [
        "01_opening",
        "02_text_short",
        "03_text_medium",
        "04_text_long",
        "05_chart1_text",
        "06_chart2_text",
    ]
    scene_dur = 3.5
    try:
        from moviepy import VideoFileClip

        clip = VideoFileClip(str(MP4_OUT))
        for i, label in enumerate(labels):
            t = min(scene_dur * i + scene_dur * 0.55, max(0.0, clip.duration - 0.05))
            out = FRAMES_DIR / f"{label}.png"
            clip.save_frame(str(out), t=t)
            print(f"[Frame] {out} @ {t:.1f}s")
        clip.close()
    except Exception as e:
        print(f"[WARN] frame extract: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="immersive レイアウトマトリクスプレビュー")
    parser.add_argument("--draft", action="store_true", help="1280x720（本番確認は省略）")
    parser.add_argument(
        "--frames-only",
        action="store_true",
        help="既存 MP4 から静止画のみ抽出",
    )
    args = parser.parse_args()

    if args.frames_only:
        extract_frames()
        return 0

    rc = render_matrix(draft=args.draft)
    if rc == 0:
        extract_frames()
        print(f"[OK] {MP4_OUT}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
