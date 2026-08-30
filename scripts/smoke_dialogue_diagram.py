"""
immersive スモーク: 図解UI + 二人掛け合い（声切替）。
VOICEVOX (127.0.0.1:50021) が起動していること。
"""
from __future__ import annotations

import wave
from pathlib import Path

from moviepy import AudioFileClip

from src.analysis.dialogue_util import expand_scene_speech_units, resolve_voicevox_id
from src.video_generation.diagram_generator import (
    generate_impact_flow_diagram,
    generate_market_board_diagram,
    generate_news_bundle_diagram,
)
from src.video_generation.structured_video_composer import render_scenes_to_video
from src.voice_generation.voice_client import VOICEVOXClient


def _write_silent_wav(path: Path, duration: float = 0.3, rate: int = 24000) -> None:
    n = max(1, int(duration * rate))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)


def main() -> None:
    root = Path("output/quality_smoke")
    audio_dir = root / "audio"
    root.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    diagram_dir = root / "diagrams"
    diagram_dir.mkdir(parents=True, exist_ok=True)
    news_path = generate_news_bundle_diagram(
        [
            {"title": "米金利低下でハイテク買い", "slot": "honmei"},
            {"title": "急騰の半導体", "slot": "heat"},
        ],
        output_path=diagram_dir / "news_bundle.png",
    )
    board_path = generate_market_board_diagram(
        {
            "NIKKEI": {"name": "日経平均", "current_price": 38500, "change_percent": 0.8},
            "NASDAQ": {"name": "NASDAQ", "current_price": 17800, "change_percent": -0.3},
            "SP500": {"name": "S&P500", "current_price": 5200, "change_percent": 0.1},
        },
        output_path=diagram_dir / "market_board.png",
    )
    flow_path = generate_impact_flow_diagram(
        left_label="金利低下",
        mid_label="半導体",
        right_label="日本株",
        output_path=diagram_dir / "impact_flow.png",
    )

    scenes = [
        {
            "scene": 1,
            "section_title": "本日のトピック",
            "duration": 8,
            "text": "みのりとカリンの掛け合いオープニング",
            "speech_text": "みのりとカリンのかけあいオープニング",
            "on_screen_text": ["地合いボード", "今日の見どころ"],
            "emotion": "happy",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [board_path],
            "speaker": "minori",
            "dialogue": [
                {
                    "speaker": "minori",
                    "text": "おはようございます。今日の地合いはこちらです。",
                    "speech_text": "おはようございます。きょうのじあいはこちらです。",
                },
                {
                    "speaker": "karin",
                    "text": "え、半導体また動いてる？飛びついちゃう！",
                    "speech_text": "え、はんどうたいまたうごいてる？とびついちゃう！",
                },
                {
                    "speaker": "minori",
                    "text": "まず流れを見てから、ね。",
                    "speech_text": "まずながれをみてから、ね。",
                },
            ],
            "padding_before": 0.2,
            "padding_after": 0.2,
        },
        {
            "scene": 2,
            "section_title": "注目ニュース",
            "duration": 8,
            "text": "ニュース束の図解",
            "speech_text": "ニュースたばのずかい",
            "on_screen_text": ["ニュース地図", "本命と旬"],
            "emotion": "confident",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [news_path],
            "speaker": "minori",
            "dialogue": [
                {
                    "speaker": "minori",
                    "text": "本命は金利、旬は半導体です。",
                    "speech_text": "ほんめいはきんり、しゅんははんどうたいです。",
                },
                {
                    "speaker": "karin",
                    "text": "旬のほう、めっちゃ気になる！",
                    "speech_text": "しゅんのほう、めっちゃきになる！",
                },
            ],
            "padding_before": 0.2,
            "padding_after": 0.2,
        },
        {
            "scene": 3,
            "section_title": "まとめ",
            "duration": 6,
            "text": "締めの掛け合い",
            "speech_text": "しめのかけあい",
            "on_screen_text": ["影響の流れ", "明日チェック"],
            "emotion": "happy",
            "image_type": "chart",
            "bg_name": "bg_illust.png",
            "target_files": [flow_path],
            "speaker": "minori",
            "dialogue": [
                {
                    "speaker": "minori",
                    "text": "流れは金利から日本株へ、です。",
                    "speech_text": "ながれはきんりからにほんかぶへ、です。",
                },
                {
                    "speaker": "karin",
                    "text": "じゃあ明日もチェックだね！",
                    "speech_text": "じゃああしたもチェックだね！",
                },
            ],
            "padding_before": 0.2,
            "padding_after": 0.2,
        },
    ]

    vv = VOICEVOXClient()
    used_speakers = set()
    for sc in scenes:
        units = expand_scene_speech_units(sc)
        segments = []
        cursor = float(sc.get("padding_before", 0.2))
        audio_only = 0.0
        for i, unit in enumerate(units, start=1):
            speaker = unit["speaker"]
            voice_id = resolve_voicevox_id(speaker)
            used_speakers.add((speaker, voice_id))
            ap = audio_dir / f"scene{sc['scene']}_u{i}_{speaker}.wav"
            vv.generate_and_save(unit["speech_text"], str(ap), speaker=voice_id, speed=0.95)
            with AudioFileClip(str(ap)) as ac:
                dur = max(0.05, float(ac.duration))
            segments.append(
                {
                    "text": unit["text"],
                    "duration": round(dur, 3),
                    "start": round(cursor, 3),
                    "audio_path": str(ap),
                    "speaker": speaker,
                    "voicevox_speaker_id": voice_id,
                    "emotion": sc.get("emotion", "normal"),
                }
            )
            cursor += dur
            audio_only += dur
        sc["segments"] = segments
        sc["duration"] = round(
            float(sc.get("padding_before", 0.2)) + audio_only + float(sc.get("padding_after", 0.2)),
            3,
        )
        print(f"scene{sc['scene']} duration={sc['duration']} speakers={[s['speaker'] for s in segments]}")

    print("voice_map", sorted(used_speakers))
    assert {s for s, _ in used_speakers} >= {"minori", "karin"}
    assert {vid for _, vid in used_speakers} >= {2, 3}

    noaudio = str(root / "smoke_noaudio.mp4")
    render_scenes_to_video(
        scenes,
        output_path=noaudio,
        assets_dir="src/assets",
        presentation_mode="immersive",
    )

    # 音声合成（pipeline と同じ要領）
    from moviepy import VideoFileClip, CompositeAudioClip, AudioClip
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

    video = VideoFileClip(noaudio)
    audio_clips = []
    t0 = 0.0
    for sc in scenes:
        pad_b = float(sc.get("padding_before", 0.2))
        for seg in sc["segments"]:
            ap = seg.get("audio_path")
            start = t0 + float(seg["start"])
            ac = AudioFileClip(ap).with_start(start)
            ac = ac.with_effects([AudioFadeIn(0.05), AudioFadeOut(0.05)])
            audio_clips.append(ac)
        t0 += float(sc["duration"])

    final_audio = CompositeAudioClip(audio_clips)
    out = str(root / "smoke_dialogue_diagram.mp4")
    video.with_audio(final_audio).write_videofile(
        out, fps=24, codec="libx264", audio_codec="aac", logger=None
    )
    video.close()
    final_audio.close()
    for ac in audio_clips:
        ac.close()
    print("OK", out)


if __name__ == "__main__":
    main()
