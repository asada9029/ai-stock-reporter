"""
台本JSON（LLM生成済み）を読み込み、無音で画面だけレンダリングする。

VOICEVOX / Gemini 不要。emphasis・ティッカーカード・ブリッジ（任意）の見え方確認用。

使い方:
  # 最新の scenes_*.json を使う
  python test_immersive_render_script.py

  # 指定ファイル（例: ステップ2で保存したもの）
  python test_immersive_render_script.py --scenes-json data/scripts/scenes_20260527_225000.json

  # ブリッジも挿入して確認（ダミーブリッジは自動ON）
  python test_immersive_render_script.py --scenes-json data/scripts/scenes_20260527_225000.json --with-bridges
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from immersive_test_utils import ensure_output_dir, resolve_test_image
from src.video_generation.structured_pipeline import _inject_section_bridges
from src.video_generation.structured_video_composer import render_scenes_to_video


def main() -> None:
    parser = argparse.ArgumentParser(description="台本JSONから無音レンダリング")
    parser.add_argument(
        "--scenes-json",
        default=None,
        help="台本JSONパス（未指定時は data/scripts/scenes_*.json の最新）",
    )
    parser.add_argument(
        "--presentation",
        choices=["classic", "immersive"],
        default="immersive",
    )
    parser.add_argument(
        "--with-bridges",
        action="store_true",
        help="immersive 時、セクション切替前にブリッジを挿入（画像があれば）",
    )
    parser.add_argument(
        "--dummy-emphasis",
        action="store_true",
        help="emphasis確認用のダミー1シーンを生成（JSON不要）",
    )
    parser.add_argument(
        "--dummy-chart",
        action="store_true",
        help="チャート演出確認用のダミー1シーンを生成（JSON不要）",
    )
    parser.add_argument(
        "--dummy-ticker-card",
        action="store_true",
        help="画像なしニュースのティッカーカード確認用（JSON不要）",
    )
    parser.add_argument(
        "--dummy-event-calendar",
        action="store_true",
        help="イベントカレンダー画像の見切れ防止確認用（JSON不要）",
    )
    parser.add_argument(
        "--match-step1",
        action="store_true",
        help="step1_layout_immersive と同じ解像度/fpsで出力（比較用）",
    )
    parser.add_argument(
        "--max-scenes",
        type=int,
        default=0,
        help="先頭Nシーンだけ描画（0=全シーン）。長いJSONのプレビュー用",
    )
    parser.add_argument(
        "--force-duration",
        type=float,
        default=0.0,
        help="全シーンのdurationを強制上書き（例: 1.0）。0=上書きしない",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="高速プレビュー（低fps/低解像度 + ultrafast）。画面確認用",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="出力mp4パス（未指定時は output/immersive_validation/step_render_script_<mode>.mp4）",
    )
    args = parser.parse_args()

    os.environ.setdefault("USE_DUMMY_BRIDGES", "true")
    if args.draft:
        os.environ["DRAFT_RENDER"] = "true"

    # 台本読み込み or ダミー生成
    path: Path | None = None
    if args.dummy_ticker_card:
        scenes = [
            {
                "scene": 1,
                "section_title": "注目ニュース：テスト",
                "duration": 3.0,
                "text": "",
                "speech_text": "",
                "on_screen_text": ["材料: 画像なしニュース", "表示: ティッカー/社名カード"],
                "emotion": "confident",
                "image_type": "news_panel",
                "bg_name": "bg_illust.png",
                "target_files": [],
                "related_ticker": "INTC",
                "related_company_name": "Intel Corporation",
            }
        ]
        print("[Load] dummy-ticker-card: 1 シーン")
    elif args.dummy_event_calendar:
        img = resolve_test_image()
        scenes = [
            {
                "scene": 1,
                "section_title": "イベントカレンダー：決算発表",
                "duration": 3.0,
                "text": "",
                "speech_text": "",
                "on_screen_text": ["決算発表: 今週の予定", "注目: 半導体", "ポイント: 週後半に集中"],
                "emotion": "normal",
                "image_type": "chart",
                "bg_name": "bg_illust.png",
                # section_title 側で event_calendar 判定されるので、実在ファイルのまま使う
                "target_files": [img],
            }
        ]
        print("[Load] dummy-event-calendar: 1 シーン")
    elif args.dummy_chart:
        img = resolve_test_image()
        scenes = [
            {
                "scene": 1,
                # step1_layout_immersive の「市場指数シーン」と揃える
                "section_title": "市場指数：日経平均",
                "duration": 3.0,
                "text": "",
                "speech_text": "",
                "on_screen_text": [
                    "日経平均: +1.2%",
                    "S&P500: 最高値更新",
                    "ナスダック: -0.5%",
                    "ダウ: +0.8%",
                ],
                "emotion": "happy",
                "image_type": "chart",
                "bg_name": "bg_illust.png",
                "target_files": [img],
            }
        ]
        print("[Load] dummy-chart: 1 シーン")
    elif args.dummy_emphasis:
        scenes = [
            {
                "scene": 1,
                "section_title": "本日のトピック",
                "duration": 1.2,
                "text": "",
                "speech_text": "",
                "on_screen_text": [
                    "米国: 史上最高値",
                    "注目: インテル好決算",
                    "主要指数: そろって最高値",
                ],
                "emotion": "happy",
                "image_type": "character_only",
                "bg_name": "bg_illust.png",
                "target_files": [],
                "emphasis": [
                    {"text": "インテル", "style": "key"},
                    {"text": "最高値", "style": "up"},
                ],
            }
        ]
        print("[Load] dummy-emphasis: 1 シーン")
    else:
        # JSONから読む
        if args.scenes_json:
            path = Path(args.scenes_json)
            if not path.is_absolute():
                path = Path.cwd() / path
        else:
            scripts_dir = Path("data/scripts")
            files = sorted(
                list(scripts_dir.glob("scenes_*.json"))
                + list(scripts_dir.glob("scenes_validation_*.json")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not files:
                print("[NG] data/scripts に台本JSONがありません")
                print("  先に: python test_immersive_script.py --type evening --presentation immersive")
                sys.exit(1)
            path = files[0]

        if not path.exists():
            print(f"[NG] ファイルがありません: {path}")
            sys.exit(1)

        with open(path, "r", encoding="utf-8") as f:
            scenes = json.load(f)

        if not isinstance(scenes, list):
            print("[NG] JSON は配列である必要があります")
            sys.exit(1)

        print(f"[Load] {path} ({len(scenes)} シーン)")

    if args.max_scenes > 0:
        scenes = scenes[: args.max_scenes]
        print(f"[Preview] 先頭 {len(scenes)} シーンのみレンダリング")

    video_type = "evening_video"
    if args.with_bridges and args.presentation == "immersive":
        scenes = _inject_section_bridges(
            scenes, video_type=video_type, assets_dir="src/assets", bridge_duration=3.0
        )
        print(f"[Bridge] 挿入後 {len(scenes)} シーン")

    # duration が無いシーンには仮の秒数
    for i, sc in enumerate(scenes):
        if args.force_duration and args.force_duration > 0:
            sc["duration"] = float(args.force_duration)
        if "duration" not in sc or not sc.get("duration"):
            sc["duration"] = 5.0
        sc["scene"] = i + 1
        if sc.get("mute") or sc.get("visual_template") == "bridge":
            sc.setdefault("segments", [])

    out_dir = ensure_output_dir()
    out_path = Path(args.out) if args.out else out_dir / f"step_render_script_{args.presentation}.mp4"

    print(f"[Render] presentation={args.presentation} -> {out_path}")
    match_step1 = bool(args.match_step1)
    result = render_scenes_to_video(
        scenes=scenes,
        output_path=str(out_path),
        assets_dir="src/assets",
        size=(1920, 1080) if match_step1 else ((1280, 720) if args.draft else (1920, 1080)),
        fps=24 if match_step1 else (12 if args.draft else 24),
        show_subtitles=False,
        presentation_mode=args.presentation,
    )

    if result and Path(result).exists():
        print(f"[OK] {result}")
        print("\n確認ポイント:")
        print("  - emphasis（色付き強調語）の位置")
        print("  - related_ticker / 社名（画像なしニュース）")
        print("  - ブリッジ（--with-bridges 時、約3秒・全画面）")
    else:
        print("[NG] レンダリング失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
