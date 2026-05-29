"""
横動画（16:9）のレイアウト確認（LLM不要・VOICEVOX不要）。

ショート用の相対配置変更が横動画に波及していないかを確認するためのスクリプト。
`render_scenes_to_video` を直接呼び、本番と同じ 1920x1080 で無音MP4を出力します。

使い方:
  python test_horizontal_layout.py
  python test_horizontal_layout.py --mode classic
  python test_horizontal_layout.py --mode immersive

出力:
  output/layout_check_horizontal_classic.mp4
  output/layout_check_horizontal_immersive.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

from immersive_test_utils import build_layout_scenes, ensure_output_dir
from src.video_generation.structured_video_composer import render_scenes_to_video


def run_horizontal_layout_check(mode: str = "both") -> int:
    ensure_output_dir()
    out_dir = project_root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = ["classic", "immersive"] if mode == "both" else [mode]
    ok = True

    for m in modes:
        out_path = out_dir / f"layout_check_horizontal_{m}.mp4"
        scenes = build_layout_scenes(m)
        print(f"\n[Layout] 横動画 ({m}) / {len(scenes)} シーン -> {out_path}")
        result = render_scenes_to_video(
            scenes=scenes,
            output_path=str(out_path),
            assets_dir="src/assets",
            size=(1920, 1080),
            fps=24,
            show_subtitles=False,
            presentation_mode=m,
        )
        if result and Path(result).exists():
            print(f"[OK] {result}")
        else:
            print(f"[NG] 生成失敗: {m}")
            ok = False

    if ok:
        print("\n[確認ポイント]")
        print("1. セクションタイトル帯が上部に表示されているか")
        print("2. チャートシーン: 画像と on_screen_text が重ならず配置されているか")
        print("3. テキストのみシーン: パネルがメイン領域に収まっているか")
        print("4. キャラ・ミニキャラの位置がショート調整前と同様か")
        print("5. immersive 利用時: ブリッジ/没入レイアウトが崩れていないか")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="横動画レイアウト確認（LLM不要）")
    parser.add_argument(
        "--mode",
        choices=["both", "classic", "immersive"],
        default="both",
        help="classic=本番既定 / immersive=没入モード（default: both）",
    )
    args = parser.parse_args()
    sys.exit(run_horizontal_layout_check(args.mode))


if __name__ == "__main__":
    main()
