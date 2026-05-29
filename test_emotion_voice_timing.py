"""
VOICEVOX 実音声の長さ × emotion_timeline で、感情切替タイミングをぱっと確認。

使い方（VOICEVOX エンジン起動済み）:
  python test_emotion_voice_timing.py
  python test_emotion_voice_timing.py --draft
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from moviepy import AudioFileClip

from src.video_generation.character_emotion import assign_segment_emotions
from src.video_generation.structured_video_composer import render_scenes_to_video
from src.voice_generation.voice_client import VOICEVOXClient


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="感情×音声タイミング統合テスト")
    parser.add_argument("--draft", action="store_true", help="720p 高速")
    parser.add_argument(
        "--out",
        default="output/test_emotion_voice_timing.mp4",
    )
    args = parser.parse_args()

    # 句ごとにトーンが変わる短文（約10〜15秒想定）
    parts = [
        ("happy", "本日の米国株は、小幅ながら続伸となりました。"),
        ("sad", "一方、ハイテク株には利益確定の売りが出ています。"),
        ("confident", "明日の日本市場は、様子見になりそうです。"),
    ]

    scene = {
        "scene": 1,
        "section_title": "感情タイミング検証",
        "text": "".join(p[1] for p in parts),
        "speech_text": "".join(p[1] for p in parts),
        "on_screen_text": ["VOICEVOX実尺", "句ごとに表情切替"],
        "emotion": "normal",
        "emotion_timeline": [
            {"segment_index": i, "emotion": em} for i, (em, _) in enumerate(parts)
        ],
        "image_type": "character_only",
        "bg_name": "bg_illust.png",
        "target_files": [],
        "padding_before": 0.25,
        "padding_after": 0.35,
    }

    print("[VOICEVOX] 音声生成中...")
    vv = VOICEVOXClient()
    audio_dir = Path("data/audio/emotion_voice_test")
    audio_dir.mkdir(parents=True, exist_ok=True)

    segments = []
    cursor = scene["padding_before"]
    for i, (em, speech) in enumerate(parts):
        wav = audio_dir / f"seg_{i+1}_{em}.wav"
        vv.generate_and_save(speech, str(wav), speed=0.95)
        with AudioFileClip(str(wav)) as ac:
            dur = max(0.15, ac.duration)
        segments.append(
            {
                "text": f"[{em}] {speech[:18]}…",
                "speech_text": speech,
                "duration": round(dur, 3),
                "start": round(cursor, 3),
                "audio_path": str(wav),
            }
        )
        cursor += dur

    scene["segments"] = segments
    scene["duration"] = round(cursor + scene["padding_after"], 3)
    assign_segment_emotions(scene)

    print("\n[Timing] segment -> emotion (VOICEVOX実尺)")
    print("-" * 56)
    for j, seg in enumerate(scene["segments"], 1):
        print(
            f"  #{j} start={seg['start']:5.2f}s  dur={seg['duration']:4.2f}s  "
            f"emotion={seg.get('emotion', '?'):12}  {seg['speech_text'][:24]}…"
        )
    print(f"  合計シーン尺: {scene['duration']:.2f}s\n")

    out = Path(args.out)
    if not out.is_absolute():
        out = project_root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = out.with_suffix(".json")
    meta.write_text(json.dumps([scene], ensure_ascii=False, indent=2), encoding="utf-8")

    size = (1280, 720) if args.draft else (1920, 1080)
    fps = 12 if args.draft else 24
    if args.draft:
        os.environ["DRAFT_RENDER"] = "1"
    else:
        os.environ.pop("DRAFT_RENDER", None)

    print(f"[Render] {size[0]}x{size[1]} -> {out}")
    render_scenes_to_video(
        scenes=[scene],
        output_path=str(out),
        assets_dir="src/assets",
        size=size,
        fps=fps,
        show_subtitles=False,
        presentation_mode="immersive",
    )

    # 無音版のあと、音声を載せた版も作る（確認しやすい）
    from moviepy import CompositeVideoClip, VideoFileClip

    video = VideoFileClip(str(out))
    audio_clips = []
    for seg in segments:
        ap = seg.get("audio_path")
        if ap:
            ac = AudioFileClip(ap).with_start(seg["start"])
            audio_clips.append(ac)
    if audio_clips:
        from moviepy import CompositeAudioClip

        final = video.with_audio(CompositeAudioClip(audio_clips))
        out_audio = out.with_name(out.stem + "_with_audio.mp4")
        final.write_videofile(
            str(out_audio),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            logger="bar" if args.draft else None,
        )
        print(f"[OK] 音声付き: {out_audio}")
    print(f"[OK] 無音: {out}")


if __name__ == "__main__":
    main()
