from pathlib import Path
from typing import Dict, Optional, List, Tuple
import os
import re
import unicodedata
import traceback

from src.analysis.script_generator import ScriptGenerator
from src.video_generation.structured_video_composer import render_scenes_to_video
from src.video_generation.thumbnail_generator import ThumbnailGenerator
from src.voice_generation.voice_client import VOICEVOXClient
from moviepy import AudioFileClip, VideoFileClip, AudioClip, CompositeAudioClip, afx
# v2.0系での正しい音声エフェクトインポート
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, MultiplyVolume

from src.config.presentation import is_immersive_mode, normalize_presentation_mode


def _section_display_name(section_title: str) -> str:
    """チャプター・SE用のセクション表示名。"""
    if not section_title:
        return ""
    if section_title == "subscribe":
        return "まとめ"
    if "：" in section_title:
        return section_title.split("：", 1)[0]
    if ":" in section_title:
        return section_title.split(":", 1)[0]
    return section_title

def _section_key_for_bridge(video_type: str, section_title: str) -> str:
    """
    ブリッジ画像のファイル名に使うキーを返す。
    例: bridge_market_indices.png
    """
    # 基本は「セクション表示名（タイトルの前半）」を見てマップする
    name = _section_display_name(section_title)
    vt = (video_type or "").lower()

    # morning
    if "morning" in vt:
        mapping = {
            "本日のトピック": "opening",
            "米国市場指数": "us_market_summary",
            "米国注目ニュース": "us_news_highlights",
            "米国セクター分析": "us_sector_analysis",
            "日本市場への影響予測": "japan_impact_prediction",
            "まとめ": "closing",
        }
        return mapping.get(name, "")

    # evening
    mapping = {
        "本日のトピック": "opening",
        "主要市場指数": "market_indices",
        "市場指数": "market_indices",
        "注目ニュース": "news_highlights",
        "イベントカレンダー": "event_calendar",
        "セクター概要": "sector_overview",
        "注目セクター": "sector_attention",
        "前回紹介銘柄の追跡": "prev_ir_tracking",
        "今夜の米国市場と明日の展望": "tomorrow_strategy",
        "まとめ": "closing",
    }
    return mapping.get(name, "")


def _inject_section_bridges(
    scenes: List[Dict],
    *,
    video_type: str,
    assets_dir: str,
    bridge_duration: float = 3.0,
) -> List[Dict]:
    """
    immersive のときだけ、セクション切替の直前にブリッジ（無音）シーンを挿入する。
    - 動画構成（セクション順・尺配分）は崩さず、画面だけ番組感を出す目的。
    - ブリッジ画像が無い場合は挿入しない（ただし開発用にダミーを使うオプションあり）。
    """
    assets = Path(assets_dir)
    images_dir = assets / "images"
    allow_dummy = (os.getenv("USE_DUMMY_BRIDGES", "").strip().lower() in ("1", "true", "yes"))
    dummy_path = images_dir / "tate_bg_illust.png"

    out: List[Dict] = []
    last_section = None
    for sc in scenes:
        section_title = sc.get("section_title", "")
        display_section_name = _section_display_name(section_title)
        is_new_section = bool(display_section_name and display_section_name != last_section)

        if is_new_section and last_section is not None and section_title != "subscribe":
            key = _section_key_for_bridge(video_type, section_title)
            if key:
                bridge_path = images_dir / f"bridge_{key}.png"
                if bridge_path.exists() or (allow_dummy and dummy_path.exists()):
                    use_path = bridge_path if bridge_path.exists() else dummy_path
                    # ブリッジを「新セクションの一部」として扱う（章頭タイミングに載る）
                    out.append(
                        {
                            "scene": 0,  # 後で振り直す
                            "section_title": section_title,
                            "duration": float(bridge_duration),
                            "text": "",  # 無音
                            "speech_text": "",
                            "on_screen_text": [],
                            "emotion": "happy",
                            "image_type": "chart",
                            "target_files": [str(use_path)],
                            "visual_template": "bridge",
                            "mute": True,
                        }
                    )

        out.append(sc)
        if display_section_name:
            last_section = display_section_name

    # scene番号を振り直す
    for i, sc in enumerate(out):
        sc["scene"] = i + 1
    return out


def _append_section_change_se_clips(
    audio_clips: List,
    section_se_times: List[float],
    assets_dir: Path,
    *,
    volume: float = 0.35,
    max_duration: float = 0.7,
) -> None:
    """セクション切り替え時のみ SE_section_change を重ねる。"""
    se_path = assets_dir / "SE" / "SE_section_change.mp3"
    if not se_path.exists() or not section_se_times:
        return
    try:
        for t in section_se_times:
            se = AudioFileClip(str(se_path))
            dur = min(float(se.duration), max_duration)
            if dur <= 0:
                se.close()
                continue
            se = se.subclipped(0, dur)
            se = se.with_effects([MultiplyVolume(volume)])
            se = se.with_start(max(0.0, t))
            audio_clips.append(se)
        print(f"[SE] セクション切替SE: {len(section_se_times)} 箇所")
    except Exception as e:
        print(f"[WARN] セクション切替SEの読み込み失敗: {e}")


def compose_video_from_analysis(
    video_structure: Dict,
    analysis_data: Dict,
    enriched_data: Optional[Dict] = None,
    output_video: str = "output/structured_video.mp4",
    assets_dir: str = "src/assets",
    size=(1920, 1080),
    fps: int = 24,
    video_type: str = "evening",
    pre_generated_scenes: Optional[List[Dict]] = None,
    presentation_mode: str = "classic",
) -> Tuple[str, str, str, List[str], str]:
    """
    Returns: (video_path, thumbnail_path, thumbnail_title, thumbnail_highlights, chapters_text)
    """
    out_path = Path(output_video)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- 1. サムネイル生成とニュース選定 (順序を先に持ってくる) ---
    thumb_path, thumb_title, thumb_highlights = "", "", []
    main_news_index, highlight_indices = 0, []
    
    is_shorts = "shorts" in video_type
    presentation_mode = normalize_presentation_mode(presentation_mode)
    use_immersive = is_immersive_mode(presentation_mode, video_type=video_type)
    if use_immersive:
        print("[Mode] presentation=immersive（classic とは別経路）")
    
    if not is_shorts:
        try:
            print("-> サムネイル生成とニュース選定を開始...")
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
            print(f"[OK] サムネイル完成 & ニュース選定完了: {thumb_title}")
        except Exception as e:
            print(f"[WARN] サムネイル生成・選定失敗: {e}")
    else:
        print("-> ショート動画のためサムネイル生成をスキップします。")

    # --- 2. シーン構成と台本の生成 ---
    if pre_generated_scenes:
        print("-> 既存の台本（シーン配列）を使用します...")
        scenes = pre_generated_scenes
    else:
        sg = ScriptGenerator()
        print("-> 生成: 構造化シーンをLLMで作成します...")
        scenes = sg.generate_structured_scenes(
            video_structure=video_structure, 
            analysis_data=analysis_data, 
            enriched_data=enriched_data,
            presentation_mode=presentation_mode,
        )

    # --- 2.5. immersive: セクションブリッジを挿入（構成は崩さず画面だけ改善） ---
    if use_immersive:
        scenes = _inject_section_bridges(scenes, video_type=video_type, assets_dir=assets_dir)

    # --- 3. チャンネル登録お願いシーンを末尾に強制追加 ---
    is_morning = "morning" in video_type
    is_shorts = "shorts" in video_type
    
    if is_shorts:
        closing_text = "詳しくは本編動画をチェック！チャンネル登録、高評価もよろしくお願いします！"
    elif is_morning:
        closing_text = "この動画が少しでも役に立ったら、チャンネル登録、高評価、そしてハイプでの応援をよろしくお願いします！皆さんの応援が、みのりの励みになります。それでは、今日も一日頑張りましょう！"
    else:
        closing_text = "この動画が少しでも役に立ったら、チャンネル登録、高評価、そしてハイプでの応援をよろしくお願いします！皆さんの応援が、みのりの励みになります。それでは、また明日お会いしましょう！"
    
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

    # --- VOICEVOXなしで「無音プレビュー」だけ作る ---
    # 開発中のレイアウト確認を優先するための逃げ道。
    # - VOICEVOXエンジン未起動でも落とさず、無音mp4だけ生成して返す
    if (os.getenv("SKIP_VOICE", "").strip().lower() in ("1", "true", "yes")):
        print("-> 音声生成をスキップして無音プレビューを出力します (SKIP_VOICE=1)")
        print("-> レンダリング中...")
        final_video_noaudio = str(out_path.parent / (out_path.stem + "_noaudio.mp4"))
        video_path = render_scenes_to_video(
            scenes=scenes,
            output_path=final_video_noaudio,
            assets_dir=assets_dir,
            size=size,
            fps=fps,
            show_subtitles=False,
            presentation_mode=presentation_mode,
        )
        return video_path, thumb_path, thumb_title, thumb_highlights, ""

    print("-> 音声生成: 各シーンの音声を生成してシーン長を調整します...")
    try:
        vv = VOICEVOXClient()
        audio_dir = Path("data/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        def _align_segments_to_count(s: str, count: int) -> List[str]:
            """読み上げ分割数に合わせて字幕用テキストを割り当てる（視覚的幅ベース）。"""
            if count <= 0:
                return []
            if count == 1:
                return [s]
            
            total_w = _get_visual_width(s)
            parts: List[str] = []
            current_s = s
            for i in range(count):
                if i == count - 1:
                    parts.append(current_s)
                    break
                
                target_w = total_w / count
                temp_s = ""
                temp_w = 0.0
                for char in current_s:
                    char_w = 1.0 if unicodedata.east_asian_width(char) in ('W', 'F', 'A') else 0.5
                    if temp_s and temp_w + char_w > target_w:
                        break
                    temp_s += char
                    temp_w += char_w
                
                parts.append(temp_s)
                current_s = current_s[len(temp_s):]
            return parts

        def _get_visual_width(text: str) -> float:
            return sum(1.0 if unicodedata.east_asian_width(c) in ('W', 'F', 'A') else 0.5 for c in text)

        def _split_text_segments_aligned(speech: str, display: str, max_w: float):
            """speech_text と display_text を同じ位置で分割する"""
            if not speech: return [], []
            speech = speech.strip()
            display = display.strip()
            
            # 句読点で分割。speech側を基準にする
            # re.split で記号を保持
            speech_parts = re.split(r'([。、！？!?])', speech)
            display_parts = re.split(r'([。、！？!?])', display)
            
            def _combine(parts):
                combined = []
                for i in range(0, len(parts)-1, 2):
                    combined.append(parts[i] + parts[i+1])
                if len(parts) % 2 == 1:
                    combined.append(parts[-1])
                return [p.strip() for p in combined if p.strip()]

            s_parts = _combine(speech_parts)
            d_parts = _combine(display_parts)
            
            # パーツ数が合わない場合は、speech 側を基準にして display 側を無理やり合わせる
            if len(s_parts) != len(d_parts):
                d_parts = _align_segments_to_count(display, len(s_parts))

            s_segs, d_segs = [], []
            cur_s, cur_d = "", ""
            cur_w = 0.0
            
            # 基本的に s_parts と d_parts を並行して処理
            for i in range(max(len(s_parts), len(d_parts))):
                p_s = s_parts[i] if i < len(s_parts) else ""
                p_d = d_parts[i] if i < len(d_parts) else ""
                p_w = _get_visual_width(p_s)
                
                if cur_w + p_w <= max_w:
                    cur_s += p_s
                    cur_d += p_d
                    cur_w += p_w
                else:
                    if cur_s:
                        s_segs.append(cur_s)
                        d_segs.append(cur_d)
                    
                    if p_w > max_w:
                        # 強制分割
                        while _get_visual_width(p_s) > max_w:
                            temp_s, temp_d = "", ""
                            temp_w = 0.0
                            # 文字数比で display 側も削る
                            ratio = len(p_d) / len(p_s) if len(p_s) > 0 else 1.0
                            for char in p_s:
                                char_w = 1.0 if unicodedata.east_asian_width(char) in ('W', 'F', 'A') else 0.5
                                if temp_s and temp_w + char_w > max_w:
                                    break
                                temp_s += char
                                temp_w += char_w
                            
                            cut_len_d = int(len(temp_s) * ratio)
                            temp_d = p_d[:cut_len_d]
                            
                            s_segs.append(temp_s)
                            d_segs.append(temp_d)
                            p_s = p_s[len(temp_s):]
                            p_d = p_d[len(temp_d):]
                        cur_s, cur_d = p_s, p_d
                        cur_w = _get_visual_width(p_s)
                    else:
                        cur_s, cur_d = p_s, p_d
                        cur_w = p_w
            
            if cur_s:
                s_segs.append(cur_s)
                d_segs.append(cur_d)
            
            return s_segs, d_segs

        # --- シーンごとの音声生成と時間計算 ---
        chapters = []
        last_section = None
        cumulative_time_for_chapters = 0.0
        section_se_times: List[float] = []

        for i, sc in enumerate(scenes):
            idx = sc.get("scene", i + 1)
            display_text = sc.get("text", "")
            speech_text = sc.get("speech_text") or display_text
            padding_before = float(sc.get("padding_before", 0.3))
            padding_after = float(sc.get("padding_after", 0.3))
            max_chars = int(sc.get("max_chars_per_segment", 80))

            section_title = sc.get("section_title", "")
            display_section_name = _section_display_name(section_title)
            is_new_section = bool(display_section_name and display_section_name != last_section)
            play_section_se = (
                use_immersive
                and is_new_section
                and last_section is not None
                and section_title != "subscribe"
            )

            if is_new_section:
                minutes = int(cumulative_time_for_chapters // 60)
                seconds = int(cumulative_time_for_chapters % 60)
                chapters.append(f"{minutes:02d}:{seconds:02d} {display_section_name}")
                if play_section_se:
                    section_se_times.append(cumulative_time_for_chapters)
                last_section = display_section_name

            if play_section_se:
                padding_before += 0.45

            # ブリッジ等の「無音シーン」は音声生成をスキップして、指定durationのまま進める
            if sc.get("mute"):
                sc["segments"] = []
                sc["duration"] = round(float(sc.get("duration", 1.0)), 3)
                cumulative_time_for_chapters += sc["duration"]
                print(f"  => シーン{idx} (mute) 期間: {sc['duration']}s")
                continue

            speech_segments, display_segments = _split_text_segments_aligned(speech_text, display_text, max_chars)
            
            segments = []
            
            cursor = padding_before 
            scene_audio_only_duration = 0.0

            for j, (seg_speech, seg_display) in enumerate(
                zip(speech_segments, display_segments)
            ):
                audio_path = audio_dir / f"scene_{idx}_seg_{j+1}.wav"
                try:
                    # 話速を少し落とす (speed=0.95)
                    vv.generate_and_save(seg_speech, str(audio_path), speed=0.95)
                    with AudioFileClip(str(audio_path)) as ac:
                        seg_dur = max(0.05, ac.duration)
                    
                    segments.append({
                        "text": seg_display,
                        "duration": round(seg_dur, 3),
                        "start": round(cursor, 3),
                        "audio_path": str(audio_path)
                    })
                    cursor += seg_dur
                    scene_audio_only_duration += seg_dur
                    print(f"  - シーン{idx} セグメント{j+1}: dur={seg_dur:.2f}s start={segments[-1]['start']:.2f}s")
                except Exception as e:
                    print(f"[WARN] 音声生成失敗: {e}")
                    est = max(0.5, len(seg_speech) / 4.0)
                    segments.append({
                        "text": seg_display, "duration": round(est, 3),
                        "start": round(cursor, 3), "audio_path": None
                    })
                    cursor += est
                    scene_audio_only_duration += est

            sc["segments"] = segments
            sc["duration"] = round(padding_before + scene_audio_only_duration + padding_after, 3)
            cumulative_time_for_chapters += sc["duration"]
            print(f"  => シーン{idx} 確定期間: {sc['duration']}s")

        chapters_text = "\n".join(chapters)

        # --- 動画レンダリング (無音) ---
        print("-> レンダリング中...")
        final_video_noaudio = str(out_path.parent / (out_path.stem + "_noaudio.mp4"))
        video_path = render_scenes_to_video(
            scenes=scenes, 
            output_path=final_video_noaudio, 
            assets_dir=assets_dir, 
            size=size, 
            fps=fps,
            show_subtitles=False,
            presentation_mode=presentation_mode,
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
                            print(f"[WARN] 音声フェード適用エラー: {e}")
                    
                    ac = ac.with_start(absolute_start)
                    audio_clips_for_composite.append(ac)
                else:
                    dur = float(seg.get("duration", 0.5))
                    # AudioClipの戻り値はリスト（ステレオ対応）
                    silence = AudioClip(lambda t: [0.0, 0.0], duration=dur, fps=44100).with_start(absolute_start)
                    audio_clips_for_composite.append(silence)
            
            cumulative_scene_start += float(sc.get("duration", 0.0))

        assets_path = Path(assets_dir)
        _append_section_change_se_clips(
            audio_clips_for_composite,
            section_se_times if use_immersive else [],
            assets_path,
        )

        # 最終オーディオ合成
        voice_audio = CompositeAudioClip(audio_clips_for_composite)
        
        # --- BGMの追加 ---
        bgm_path = Path(assets_dir) / "BGM" / "BGM_garden_party.mp3"
        final_audio = voice_audio
        
        if bgm_path.exists():
            try:
                print(f"[BGM] 追加中: {bgm_path.name}")
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
                print(f"[WARN] BGM合成失敗: {e}")
        
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
        
        print(f"[OK] 完成: {final_out}")

        return final_out, thumb_path, thumb_title, thumb_highlights, chapters_text

    except Exception as e:
        print(f"[NG] エラー発生: {e}")
        traceback.print_exc()
        return "", "", "", [], ""

__all__ = ["compose_video_from_analysis"]
