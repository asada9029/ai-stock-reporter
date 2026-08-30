"""immersive レイアウト確認用。静止フレームを output/layout_preview/ に書き出す。"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DRAFT_RENDER", "1")

from src.video_generation.diagram_generator import (
    generate_capital_flow_diagram,
    generate_impact_flow_diagram,
    generate_market_board_diagram,
)
from src.video_generation.structured_video_composer import render_scenes_to_video


def main() -> None:
    out = Path("output/layout_preview")
    out.mkdir(parents=True, exist_ok=True)
    diagrams = out / "diagrams"
    diagrams.mkdir(exist_ok=True)

    board = generate_market_board_diagram(
        {
            "NIKKEI": {"name": "日経平均", "current_price": 38500, "change_percent": 0.8},
            "NASDAQ": {"name": "NASDAQ", "current_price": 17800, "change_percent": -0.3},
            "SP500": {"name": "S&P500", "current_price": 5200, "change_percent": 0.1},
        },
        output_path=diagrams / "market_board.png",
    )
    capital = generate_capital_flow_diagram(
        [
            {"name": "半導体", "change_percent": 1.9},
            {"name": "通信", "change_percent": 1.2},
            {"name": "ソフトウェア", "change_percent": 0.9},
        ],
        [
            {"name": "エネルギー", "change_percent": -2.0},
            {"name": "小売", "change_percent": -1.1},
            {"name": "銀行", "change_percent": -0.8},
        ],
        output_path=diagrams / "capital_flow.png",
    )
    flow = generate_impact_flow_diagram(
        left_label="米重要指標",
        mid_label="Moderna",
        right_label="日本株への影響",
        output_path=diagrams / "impact_flow.png",
    )

    scenes = [
        {
            "scene": 1,
            "section_title": "米国セクター分析：資金フロー全体像",
            "duration": 2.5,
            "text": "資金循環がはっきりと見える",
            "speech_text": "しきんじゅんかんがはっきりとみえる",
            "on_screen_text": ["資金循環がはっきりと見える", "金利動向と個別業績が主導権握る"],
            "emotion": "confident",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [capital],
            "speaker": "minori",
            "segments": [
                {
                    "text": "資金循環がはっきりと見えるね",
                    "duration": 2.0,
                    "start": 0.2,
                    "speaker": "minori",
                    "emotion": "confident",
                }
            ],
        },
        {
            "scene": 2,
            "section_title": "米国注目ニュース：Dick's Sporting Goods 記録的下落",
            "duration": 2.5,
            "text": "個別材料の急落です",
            "speech_text": "こべつざいりょうのきゅうらくです",
            "on_screen_text": [
                "決算後に急落・見通し下方修正",
                "地合い全体とは切り離して見る",
                "同業・小売セクターへの波及に注意",
                "翌営業日の寄り付き反応を要確認",
                "出来高急増は短期の需給悪化サイン",
                "関連ETFの資金流出も併せて確認",
            ],
            "emotion": "surprised",
            "image_type": "character_only",
            "bg_name": "bg_illust.png",
            "target_files": [],
            "related_ticker": "DKS",
            "related_company_name": "Dick's Sporting Goods",
            "speaker": "karin",
            "dialogue": [
                {"speaker": "karin", "speech_text": "え、急落じゃん"},
                {"speaker": "minori", "speech_text": "個別材料として見てね"},
            ],
            "segments": [
                {
                    "text": "え、急落じゃん",
                    "duration": 1.0,
                    "start": 0.2,
                    "speaker": "karin",
                    "emotion": "surprised",
                },
                {
                    "text": "個別材料として見てね",
                    "duration": 1.2,
                    "start": 1.2,
                    "speaker": "minori",
                    "emotion": "confident",
                },
            ],
        },
        {
            "scene": 3,
            "section_title": "日本市場への影響予測：影響の因果関係フロー",
            "duration": 2.5,
            "text": "米国高から日本市場への波及経路",
            "speech_text": "べいこくこうからにほんしじょうへのはきゅうけいろ",
            "on_screen_text": ["米国高から日本市場への波及経路", "銘柄ごとの選別が投資を左右する"],
            "emotion": "normal",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [flow],
            "speaker": "minori",
            "segments": [
                {
                    "text": "まずは流れを目で追ってみましょう",
                    "duration": 2.0,
                    "start": 0.2,
                    "speaker": "minori",
                    "emotion": "normal",
                }
            ],
        },
        {
            "scene": 4,
            "section_title": "米国市場指数：今日の地合いボード",
            "duration": 2.0,
            "text": "地合いを一目で",
            "speech_text": "じあいをいちもくで",
            "on_screen_text": ["地合いボード", "指数の温度感"],
            "emotion": "happy",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [board],
            "speaker": "minori",
            "segments": [
                {
                    "text": "まずは地合いボードから",
                    "duration": 1.6,
                    "start": 0.2,
                    "speaker": "minori",
                    "emotion": "happy",
                }
            ],
        },
    ]

    mp4 = str(out / "layout_check.mp4")
    render_scenes_to_video(
        scenes,
        output_path=mp4,
        assets_dir="src/assets",
        presentation_mode="immersive",
        show_subtitles=True,
    )
    print("wrote", mp4)

    # フレーム抽出（moviepy）
    from moviepy import VideoFileClip

    clip = VideoFileClip(mp4)
    times = [0.4, 2.8, 5.5, 8.0]
    for i, t in enumerate(times, start=1):
        if t < clip.duration:
            frame_path = out / f"frame_{i}.png"
            clip.save_frame(str(frame_path), t=t)
            print("frame", frame_path)
    clip.close()


if __name__ == "__main__":
    main()
