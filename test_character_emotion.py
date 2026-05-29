"""
キャラ感情アニメーションの確認（VOICEVOX / LLM 不要）。

使い方:
  python test_character_emotion.py --all          # 全8感情を順番に（推奨）
  python test_character_emotion.py --all --draft  # 720p 高速
  python test_character_emotion.py --emotions happy,angry,surprised
  python test_character_emotion.py --with-voice   # VOICEVOX で尺計算（要エンジン）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.analysis.scene_schema import ALLOWED_EMOTIONS
from src.video_generation.character_emotion import assign_segment_emotions
from src.video_generation.structured_video_composer import render_scenes_to_video

EMOTION_HINTS = {
    "normal": "（アニメなし・基準位置）",
    "happy": "ぴょんぴょん ×2〜3（ゆっくり）",
    "excited": "ぴょんぴょん ×3（やや大きめ）",
    "sad": "ずーん → 戻る",
    "disappointed": "ずーん（小）→ 戻る",
    "surprised": "右に引く → 戻る",
    "angry": "ぷるぷる → 静止",
    "confident": "ゆらゆら → 静止",
}

ALL_EMOTION_ORDER = [
    "normal",
    "happy",
    "excited",
    "sad",
    "disappointed",
    "surprised",
    "angry",
    "confident",
]


def _build_all_emotions_scenes(seg_duration: float = 3.5) -> list:
    """感情1種類 = 1シーン。ラベル付きで全感情を確認。"""
    scenes = []
    for i, em in enumerate(ALL_EMOTION_ORDER):
        label = EMOTION_HINTS.get(em, "")
        scenes.append(
            {
                "scene": i + 1,
                "section_title": f"感情テスト: {em}",
                "duration": seg_duration,
                "text": "",
                "speech_text": "",
                "on_screen_text": [f"emotion: {em}", label],
                "emotion": em,
                "image_type": "character_only",
                "bg_name": "bg_illust.png",
                "target_files": [],
                "segments": [
                    {
                        "text": em,
                        "duration": round(seg_duration - 0.6, 3),
                        "start": 0.3,
                        "emotion": em,
                    }
                ],
            }
        )
    return scenes


def _build_demo_scenes(emotions: list[str], *, with_voice: bool) -> list:
    speech_parts = [
        "本日の米国市場は小幅ながら続伸です。",
        "一方でハイテク株には利益確定の売りが出ました。",
        "明日の日本市場は様子見になりそうです。",
    ]
    speech = "".join(speech_parts[: len(emotions)])
    scene = {
        "scene": 1,
        "section_title": "感情アニメ確認",
        "duration": 12.0,
        "text": speech,
        "speech_text": speech,
        "on_screen_text": ["米国: 小幅続伸", "ハイテク: 売り優勢"],
        "emotion": emotions[0],
        "emotion_timeline": [
            {"segment_index": i, "emotion": em} for i, em in enumerate(emotions)
        ],
        "image_type": "character_only",
        "bg_name": "bg_illust.png",
        "target_files": [],
        "padding_before": 0.3,
        "padding_after": 0.3,
    }

    if with_voice:
        from moviepy import AudioFileClip

        from src.voice_generation.voice_client import VOICEVOXClient

        vv = VOICEVOXClient()
        audio_dir = Path("data/audio/emotion_test")
        audio_dir.mkdir(parents=True, exist_ok=True)
        segments = []
        cursor = scene["padding_before"]
        for i, part in enumerate(speech_parts[: len(emotions)]):
            wav = audio_dir / f"seg_{i+1}.wav"
            vv.generate_and_save(part, str(wav), speed=0.95)
            with AudioFileClip(str(wav)) as ac:
                dur = max(0.2, ac.duration)
            segments.append(
                {
                    "text": part,
                    "duration": round(dur, 3),
                    "start": round(cursor, 3),
                    "audio_path": str(wav),
                }
            )
            cursor += dur
        scene["segments"] = segments
        scene["duration"] = round(cursor + scene["padding_after"], 3)
        assign_segment_emotions(scene)
    else:
        segments = []
        t = 0.5
        for part, em in zip(speech_parts[: len(emotions)], emotions):
            segments.append(
                {
                    "text": part,
                    "duration": 3.0,
                    "start": t,
                    "emotion": em,
                }
            )
            t += 3.0
        scene["segments"] = segments
        scene["duration"] = t + 0.5

    return [scene]


def main() -> None:
    parser = argparse.ArgumentParser(description="キャラ感情アニメーション確認")
    parser.add_argument(
        "--all",
        action="store_true",
        help="全8感情を1本の動画で順番に確認（推奨）",
    )
    parser.add_argument(
        "--seg-duration",
        type=float,
        default=3.5,
        help="--all 時の各感情シーンの秒数",
    )
    parser.add_argument(
        "--emotions",
        default="happy,sad,excited",
        help=f"カンマ区切り（allowed: {','.join(sorted(ALLOWED_EMOTIONS))}）",
    )
    parser.add_argument(
        "--with-voice",
        action="store_true",
        help="VOICEVOXでセグメント長を計算（エンジン要）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="出力MP4（--all 時デフォルト: output/test_character_emotion_all.mp4）",
    )
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()

    if args.all:
        scenes = _build_all_emotions_scenes(seg_duration=args.seg_duration)
        out_default = "output/test_character_emotion_all.mp4"
    else:
        emotions = [e.strip() for e in args.emotions.split(",") if e.strip()]
        scenes = _build_demo_scenes(emotions, with_voice=args.with_voice)
        out_default = "output/test_character_emotion.mp4"

    out = Path(args.out or out_default)
    if not out.is_absolute():
        out = project_root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    size = (1280, 720) if args.draft else (1920, 1080)
    fps = 12 if args.draft else 24
    if args.draft:
        os.environ["DRAFT_RENDER"] = "1"
    else:
        os.environ.pop("DRAFT_RENDER", None)

    meta_path = out.with_suffix(".json")
    meta_path.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[Scenes] {len(scenes)} シーン -> {out}")
    print(f"[Meta] {meta_path}")
    render_scenes_to_video(
        scenes=scenes,
        output_path=str(out),
        assets_dir="src/assets",
        size=size,
        fps=fps,
        show_subtitles=False,
        presentation_mode="immersive",
    )
    print(f"[OK] {out}")


if __name__ == "__main__":
    main()
