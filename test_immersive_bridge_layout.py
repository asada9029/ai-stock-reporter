"""
VOICEVOX不要のブリッジ表示テスト（無音レンダリング）。

目的:
  - `video_structure.json` 粒度の「セクションブリッジ（1枚絵）」が、
    immersive で挿入されると画面がどう変わるかを最短で確認する。
  - ブリッジ画像が未用意でも、`USE_DUMMY_BRIDGES=true` でダミー画像を差し込んで確認する。

使い方:
  python test_immersive_bridge_layout.py
  $env:USE_DUMMY_BRIDGES="true"; python test_immersive_bridge_layout.py
"""

from __future__ import annotations

import os
from pathlib import Path

from src.video_generation.structured_video_composer import render_scenes_to_video
from src.video_generation.structured_pipeline import _inject_section_bridges


def main() -> None:
    out_dir = Path("output/immersive_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "step_bridge_layout_immersive.mp4"

    # このテストは「ブリッジ未作成でも確認できる」ことが目的なので、
    # 未指定ならダミーブリッジを有効化する。
    os.environ.setdefault("USE_DUMMY_BRIDGES", "true")

    # セクションタイトルだけ変えた最小シーン（各2秒）
    # ※実際の構成（尺）は変えず「画面の切り替わり」だけ確認するためのテスト
    scenes = [
        {
            "scene": 1,
            "section_title": "本日のトピック：テスト",
            "duration": 2.0,
            "text": "オープニング",
            "on_screen_text": ["米国: 小幅安", "注目: テスト"],
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
        },
        {
            "scene": 2,
            "section_title": "主要市場指数：テスト",
            "duration": 2.0,
            "text": "指数",
            "on_screen_text": ["日経 -0.8%"],
            "emotion": "normal",
            "image_type": "bg_only",
            "target_files": [],
        },
        {
            "scene": 3,
            "section_title": "注目ニュース：テスト",
            "duration": 2.0,
            "text": "ニュース",
            "on_screen_text": ["NVDA +2.1%", "材料: 決算"],
            "emotion": "surprised",
            "image_type": "bg_only",
            "target_files": [],
            "ticker": "NVDA",
            "company_name": "NVIDIA",
            "emphasis": [{"text": "+2.1%", "style": "up"}, {"text": "決算", "style": "key"}],
        },
        {
            "scene": 4,
            "section_title": "イベントカレンダー：テスト",
            "duration": 2.0,
            "text": "イベント",
            "on_screen_text": ["明日: 決算"],
            "emotion": "confident",
            "image_type": "bg_only",
            "target_files": [],
        },
        {
            "scene": 5,
            "section_title": "まとめ：テスト",
            "duration": 2.0,
            "text": "まとめ",
            "on_screen_text": ["明日の注目", "1) 指数", "2) 決算"],
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
        },
    ]

    video_type = "evening_video"
    # ブリッジ挿入（ブリッジ画像が無ければ、USE_DUMMY_BRIDGES=trueでダミー）
    scenes = _inject_section_bridges(
        scenes, video_type=video_type, assets_dir="src/assets", bridge_duration=3.0
    )

    print(f"[BridgeTest] USE_DUMMY_BRIDGES={os.getenv('USE_DUMMY_BRIDGES')}")
    print(f"[BridgeTest] scenes={len(scenes)} -> {out_path}")

    render_scenes_to_video(
        scenes=scenes,
        output_path=str(out_path),
        assets_dir="src/assets",
        size=(1920, 1080),
        fps=24,
        show_subtitles=False,
        presentation_mode="immersive",
    )

    print(f"[OK] 出力: {out_path}")


if __name__ == "__main__":
    main()

