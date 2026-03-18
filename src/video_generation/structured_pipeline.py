from pathlib import Path
from typing import Dict, Optional, List, Tuple
import os
import re
import traceback

from src.analysis.script_generator import ScriptGenerator
from src.video_generation.structured_video_composer import render_scenes_to_video
from src.video_generation.thumbnail_generator import ThumbnailGenerator
from src.voice_generation.voice_client import VOICEVOXClient
from moviepy import AudioFileClip, VideoFileClip, AudioClip, CompositeAudioClip, afx
# v2.0系での正しい音声エフェクトインポート
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, MultiplyVolume

def compose_video_from_analysis(
    video_structure: Dict,
    analysis_data: Dict,
    enriched_data: Optional[Dict] = None,
    output_video: str = "output/structured_video.mp4",
    assets_dir: str = "src/assets",
    size=(1920, 1080),
    fps: int = 24,
    video_type: str = "evening"
) -> Tuple[str, str, str, List[str]]:
    """
    Returns: (video_path, thumbnail_path, thumbnail_title, thumbnail_highlights)
    """
    out_path = Path(output_video)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- 1. サムネイル生成とニュース選定 (順序を先に持ってくる) ---
    thumb_path, thumb_title, thumb_highlights = "", "", []
    main_news_index, highlight_indices = 0, []
    try:
        print("➡️ サムネイル生成とニュース選定を開始...")
        tg = ThumbnailGenerator()
        thumb_out = str(out_path.parent / f"thumbnail_{out_path.stem}.png")
        thumb_path, thumb_title, thumb_highlights, main_news_index, highlight_indices = tg.create_thumbnail_from_analysis(
            analysis_result=analysis_data,
            video_type=video_type,
            output_path=thumb_out
        )
        # 選定された情報を analysis_data に統合して ScriptGenerator に渡す
        analysis_data["selected_thumbnail_title"] = thumb_title
        analysis_data["selected_highlights"] = thumb_highlights
        analysis_data["main_news_index"] = main_news_index
        analysis_data["highlight_indices"] = highlight_indices
        print(f"✅ サムネイル完成 & ニュース選定完了: {thumb_title}")
    except Exception as e:
        print(f"⚠️ サムネイル生成・選定失敗: {e}")

    # --- 2. シーン構成と台本の生成 ---
    sg = ScriptGenerator()
    print("➡️ 生成: 構造化シーンをLLMで作成します...")
    scenes = sg.generate_structured_scenes(
        video_structure=video_structure, 
        analysis_data=analysis_data, 
        enriched_data=enriched_data
    )

    # --- 3. チャンネル登録お願いシーンを末尾に強制追加 ---
    is_morning = "morning" in video_type
    closing_text = "この動画が少しでも役に立ったら、チャンネル登録、高評価、そしてハイプでの応援をよろしくお願いします！皆さんの応援が、みのりの励みになります。それでは、今日も一日頑張りましょう！" if is_morning else "この動画が少しでも役に立ったら、チャンネル登録、高評価、そしてハイプでの応援をよろしくお願いします！皆さんの応援が、みのりの励みになります。それでは、また明日お会いしましょう！"
    
    subscribe_scene = {
        "scene": len(scenes) + 1,
        "section_title": "subscribe",
        "text": closing_text,
        "on_screen_text": [], # テキスト表示なし
        "emotion": "happy",
        "image_type": "bg_only", # キャラクターも非表示にして動画を主役にする
        "bg_name": "bg_subscribe", # 専用の背景色を指定するための識別子
        "target_files": []
    }
    scenes.append(subscribe_scene)

    print(f"➡️ 音声生成: 各シーンの音声を生成してシーン長を調整します...")
    try:
        vv = VOICEVOXClient()
        audio_dir = Path("data/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        def _split_text_segments(s: str, max_c: int):
            if not s: return []
            s = s.strip()
            
            # 句読点で分割するための正規表現（句読点自体を保持する）
            # 。、！？ ! ? などを区切り文字とする
            parts = re.split(r'([。、！？!?])', s)
            
            # 分割した記号を直前の文字列と結合する
            combined_parts = []
            for i in range(0, len(parts)-1, 2):
                combined_parts.append(parts[i] + parts[i+1])
            if len(parts) % 2 == 1:
                combined_parts.append(parts[-1])
            
            # 空の要素を除去
            combined_parts = [p.strip() for p in combined_parts if p.strip()]
            
            segs, cur = [], ""
            for p in combined_parts:
                # 現在のセグメントに次のパーツを足しても上限以下なら結合
                if len(cur) + len(p) <= max_c:
                    cur += p
                else:
                    # 上限を超える場合、現在のセグメントを保存して新しく開始
                    if cur:
                        segs.append(cur)
                    
                    # パーツ単体で上限を超えている場合は強制分割
                    if len(p) > max_c:
                        while len(p) > max_c:
                            segs.append(p[:max_c])
                            p = p[max_c:]
                        cur = p
                    else:
                        cur = p
            
            if cur:
                segs.append(cur)
            return segs

        # --- シーンごとの音声生成と時間計算 ---
        for i, sc in enumerate(scenes):
            idx = sc.get("scene", i + 1)
            text = sc.get("text", "")
            padding_before = float(sc.get("padding_before", 0.3))
            padding_after = float(sc.get("padding_after", 0.3))
            max_chars = int(sc.get("max_chars_per_segment", 50))

            segments_texts = _split_text_segments(text, max_chars)
            segments = []
            
            cursor = padding_before 
            scene_audio_only_duration = 0.0

            for j, seg_text in enumerate(segments_texts):
                audio_path = audio_dir / f"scene_{idx}_seg_{j+1}.wav"
                try:
                    vv.generate_and_save(seg_text, str(audio_path))
                    with AudioFileClip(str(audio_path)) as ac:
                        seg_dur = max(0.05, ac.duration)
                    
                    segments.append({
                        "text": seg_text,
                        "duration": round(seg_dur, 3),
                        "start": round(cursor, 3),
                        "audio_path": str(audio_path)
                    })
                    cursor += seg_dur
                    scene_audio_only_duration += seg_dur
                    print(f"  - シーン{idx} セグメント{j+1}: dur={seg_dur:.2f}s start={segments[-1]['start']:.2f}s")
                except Exception as e:
                    print(f"⚠️ 音声生成失敗: {e}")
                    est = max(0.5, len(seg_text) / 4.0)
                    segments.append({
                        "text": seg_text, "duration": round(est, 3),
                        "start": round(cursor, 3), "audio_path": None
                    })
                    cursor += est
                    scene_audio_only_duration += est

            sc["segments"] = segments
            sc["duration"] = round(padding_before + scene_audio_only_duration + padding_after, 3)
            print(f"  => シーン{idx} 確定期間: {sc['duration']}s")

        # --- 動画レンダリング (無音) ---
        print(f"➡️ レンダリング中...")
        final_video_noaudio = str(out_path.parent / (out_path.stem + "_noaudio.mp4"))
        video_path = render_scenes_to_video(
            scenes=scenes, 
            output_path=final_video_noaudio, 
            assets_dir=assets_dir, 
            size=size, 
            fps=fps
        )

        # --- 音声の合成 ---
        audio_clips_for_composite = []
        cumulative_scene_start = 0.0

        for sc in scenes:
            audio_f = float(sc.get("audio_fade", 0.05))
            
            for seg in sc.get("segments", []):
                ap = seg.get("audio_path")
                absolute_start = cumulative_scene_start + float(seg.get("start", 0.0))
                
                if ap:
                    ac = AudioFileClip(ap)
                    # MoviePy v2.0+ の AudioFadeIn / AudioFadeOut クラスを使用
                    if audio_f > 0:
                        try:
                            ac = ac.with_effects([
                                AudioFadeIn(audio_f), 
                                AudioFadeOut(audio_f)
                            ])
                        except Exception as e:
                            print(f"⚠️ 音声フェード適用エラー: {e}")
                    
                    ac = ac.with_start(absolute_start)
                    audio_clips_for_composite.append(ac)
                else:
                    dur = float(seg.get("duration", 0.5))
                    # AudioClipの戻り値はリスト（ステレオ対応）
                    silence = AudioClip(lambda t: [0.0, 0.0], duration=dur, fps=44100).with_start(absolute_start)
                    audio_clips_for_composite.append(silence)
            
            cumulative_scene_start += float(sc.get("duration", 0.0))

        # 最終オーディオ合成
        voice_audio = CompositeAudioClip(audio_clips_for_composite)
        
        # --- BGMの追加 ---
        bgm_path = Path(assets_dir) / "BGM" / "BGM_garden_party.mp3"
        final_audio = voice_audio
        
        if bgm_path.exists():
            try:
                print(f"🎵 BGMを追加中: {bgm_path.name}")
                bgm_clip = AudioFileClip(str(bgm_path))
                
                # 動画の長さに合わせてループ
                bgm_clip = bgm_clip.with_effects([afx.AudioLoop(duration=cumulative_scene_start)])
                
                # 音量調整（ボイスを邪魔しない程度に下げる）とフェード
                bgm_clip = bgm_clip.with_effects([
                    MultiplyVolume(0.03),
                    AudioFadeIn(5.0),
                    AudioFadeOut(5.0)
                ])
                
                # ボイスとBGMを合成
                final_audio = CompositeAudioClip([bgm_clip, voice_audio])
            except Exception as e:
                print(f"⚠️ BGM合成失敗: {e}")
        
        with VideoFileClip(video_path) as video_clip:
            video_clip_with_audio = video_clip.with_audio(final_audio)
            final_out = str(out_path)
            
            video_clip_with_audio.write_videofile(
                final_out,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=max(1, (os.cpu_count() or 2) - 1),
                logger=None
            )
        
        # クリーンアップ
        final_audio.close()
        for ac in audio_clips_for_composite:
            ac.close()
        
        print(f"✅ 完成: {final_out}")

        return final_out, thumb_path, thumb_title, thumb_highlights

    except Exception as e:
        print(f"❌ エラー発生: {e}")
        traceback.print_exc()
        return "", "", "", []

__all__ = ["compose_video_from_analysis"]
