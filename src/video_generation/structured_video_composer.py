from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os
import numpy as np
from PIL import Image

from moviepy import (
    ImageClip,
    TextClip,
    CompositeVideoClip,
    ColorClip,
    VideoFileClip
)
# v2.0系でのエフェクトクラス
from moviepy.video.fx import FadeIn, FadeOut, MaskColor

def _asset_for_emotion(assets_dir: Path, emotion: str) -> Optional[Path]:
    candidates = [
        assets_dir / f"character_{emotion}.png",
        assets_dir / f"{emotion}.png",
        assets_dir / "character_normal.png", 
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def _asset_for_visual(assets_dir: Path, name: str) -> Optional[Path]:
    if not name:
        return None
    
    # 1. 絶対パスまたはカレントディレクトリからの相対パス
    p = Path(name)
    if p.exists():
        return p
    
    # 2. assets/images 直下
    p_assets = assets_dir / name
    if p_assets.exists():
        return p_assets
        
    # 3. assets/images/images (ネストしている可能性)
    p_nested = assets_dir / "images" / name
    if p_nested.exists():
        return p_nested
        
    print(f"⚠️ 資産が見つかりません: {name} (検索先: {p}, {p_assets})")
    return None

def _find_font_path(fonts_dir: Path) -> Optional[str]:
    candidates = [
        fonts_dir / "NotoSansJP-Regular.ttf",
        fonts_dir / "NotoSansJP-Regular.otf",
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ]
    for p in candidates:
        if p and p.exists():
            return str(p)
    return None

def _load_image_clip(path: Path, size: Tuple[int, int]) -> ImageClip:
    return ImageClip(str(path)).resized(new_size=size)

def _load_frame_with_chromakey(path: Path, size: Tuple[int, int]) -> ImageClip:
    """グリーンバック(#00FF00)を透過させてImageClipとして読み込む"""
    with Image.open(str(path)) as img:
        img = img.convert("RGBA")
        data = np.array(img)
        
        # グリーンバック (#00FF00) を特定してアルファ値を0にする
        r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
        # 緑色の判定範囲を広げる (gがr,bより一定以上大きければ緑とみなす)
        mask = (g > 100) & (g > r) & (g > b)
        data[mask] = [0, 0, 0, 0]
        
        return ImageClip(data).resized(new_size=size)

def _load_video_with_chromakey(path: Path, size: Tuple[int, int]) -> VideoFileClip:
    """動画のグリーンバックを透過させて読み込む"""
    # 動画を読み込み、リサイズ
    clip = VideoFileClip(str(path)).resized(new_size=size)
    
    # MoviePy v2.0系では MaskColor の引数が color, threshold, stiffness になっている可能性がある
    # または thr, s ではなく threshold, stiffness
    try:
        # まずは一般的な名称で試行
        clip = clip.with_effects([MaskColor(color=[0, 255, 0], threshold=100, stiffness=5)])
    except TypeError:
        try:
            # 失敗した場合は v1.0 系の引数名に近いものを試行
            clip = clip.with_effects([MaskColor(color=[0, 255, 0], thr=100, s=5)])
        except TypeError:
            # それでもダメな場合は color のみで試行
            print("⚠️ MaskColor の詳細引数が不明なため、color のみで実行します")
            clip = clip.with_effects([MaskColor(color=[0, 255, 0])])
    
    return clip

def _calculate_smart_layout(count: int, screen_size: Tuple[int, int], has_text: bool = False, image_paths: List[Path] = None, two_image_layout: str = "horizontal") -> List[Dict]:
    """
    画像数に応じて、キャラクター（右側20%）や字幕（下部）、セクションタイトル（上部）を避けた最適な座標とサイズを計算する。
    has_text が True の場合は、画像の下にテキストを表示するためのスペースを確保する。
    two_image_layout: 2枚の場合のレイアウト ("horizontal" または "vertical")
    """
    sw, sh = screen_size
    # 1080p用に定数をスケールアップ (720p時の1.5倍)
    text_area_h = 165
    title_area_h = 180
    margin = 22
    
    # メイン 80%, キャラ 20%
    main_area_w = int(sw * 0.8)
    
    # 有効な高さ（タイトルの下から字幕の上まで）
    available_h = sh - text_area_h - title_area_h - (margin * 2)
    start_x = margin
    start_y = title_area_h + margin

    # テキスト併用時は、画像エリアの最大高さを制限する（例：上部60%）
    img_available_h = int(available_h * 0.6) if has_text else available_h

    positions = []
    if count == 1:
        # 1枚ならメイン領域内で最大化
        w = main_area_w - (margin * 2)
        h = img_available_h
        positions.append({"x": start_x, "y": start_y, "w": w, "h": h})
    elif count == 2:
        # 2枚の場合：左右並列 (horizontal) のみとする
        w = (main_area_w // 2) - margin
        h = img_available_h
        positions.append({"x": start_x, "y": start_y, "w": w, "h": h})
        positions.append({"x": start_x + w + margin, "y": start_y, "w": w, "h": h})
    elif count == 3:
        # 3枚なら逆三角形（上1枚、下2枚）
        h = (img_available_h // 2) - (margin // 2)
        w_half = (main_area_w // 2) - (margin // 2)
        # 上段中央
        positions.append({"x": start_x + (main_area_w - w_half)//2, "y": start_y, "w": w_half, "h": h})
        # 下段左右
        positions.append({"x": start_x, "y": start_y + h + margin, "w": w_half, "h": h})
        positions.append({"x": start_x + w_half + margin, "y": start_y + h + margin, "w": w_half, "h": h})
    elif count >= 4:
        # 4枚以上ならグリッド状
        w = (main_area_w // 2) - (margin // 2)
        h = (img_available_h // 2) - (margin // 2)
        positions.append({"x": start_x, "y": start_y, "w": w, "h": h})
        positions.append({"x": start_x + w + margin, "y": start_y, "w": w, "h": h})
        positions.append({"x": start_x, "y": start_y + h + margin, "w": w, "h": h})
        positions.append({"x": start_x + w + margin, "y": start_y + h + margin, "w": w, "h": h})
            
    return positions

def render_scenes_to_video(
    scenes: List[Dict],
    output_path: str,
    assets_dir: str = "src/assets",
    size: Tuple[int, int] = (1920, 1080),
    fps: int = 24,
    font: str = "DejaVu-Sans"
) -> str:
    assets = Path(assets_dir)
    images_dir = assets / "images"
    fonts_dir = assets / "fonts"
    font_path_found = _find_font_path(fonts_dir)
    font_to_use = font_path_found if font_path_found else font
    
    all_clips = []
    cumulative_time = 0.0
    
    # 1080p用レイアウト定数
    text_area_h = 165
    title_area_h = 128
    margin = 22
    main_area_w = int(size[0] * 0.8)
    start_y = title_area_h + margin
    available_h = size[1] - text_area_h - title_area_h - (margin * 2)
    bottom_y = size[1] - text_area_h - margin

    for sc in scenes:
        total_scene_duration = float(sc.get("duration", 5.0))
        video_cross = float(sc.get("video_crossfade", 0.2))
        
        # --- 1. 背景レイヤー ---
        bg_name = sc.get("bg_name", "bg_illust.png")
        if bg_name == "bg_subscribe":
            # チャンネル登録シーン用の背景色（目に優しいクリーム色）
            bg_clip = ColorClip(size, color=(255, 249, 225)) # クリーム色
        else:
            bg_path = _asset_for_visual(images_dir, bg_name)
            if bg_path:
                try:
                    bg_clip = _load_image_clip(bg_path, size)
                except Exception as e:
                    print(f"⚠️ 背景画像読み込み失敗 ({bg_name}): {e}")
                    bg_clip = ColorClip(size, color=(30, 30, 40))
            else:
                bg_clip = ColorClip(size, color=(30, 30, 40))

        bg_clip = bg_clip.with_duration(total_scene_duration).with_start(cumulative_time)
        all_clips.append(bg_clip)

        # --- 2. セクションタイトル (動的リサイズ) ---
        section_title = sc.get("section_title")
        if section_title and section_title != "subscribe":
            try:
                # 先にテキストクリップを作成してサイズを取得
                title_clip = TextClip(
                    text=section_title, font=font_to_use, font_size=54,
                    color="#4A2711", method="label", size=(None, 90)
                ).with_duration(total_scene_duration).with_start(cumulative_time)
                
                # テキストサイズに合わせて枠をリサイズ (パディングを追加)
                frame_w = title_clip.w + 200
                frame_h = title_clip.h + 120
                
                frame_path = images_dir / "title_frame.png"
                if frame_path.exists():
                    t_frame = _load_frame_with_chromakey(frame_path, (frame_w, frame_h))
                    all_clips.append(t_frame.with_position((0, 15)).with_duration(total_scene_duration).with_start(cumulative_time))

                # テキストを枠の中央に配置 (垂直方向のオフセットを調整)
                text_y = (frame_h - title_clip.h) // 2 - 5
                title_clip = title_clip.with_position((95, text_y))
                all_clips.append(title_clip)
            except Exception as e:
                print(f"⚠️ セクションタイトル生成失敗: {e}")

        # --- 3. メインビジュアルレイヤー (既存の1〜4枚ロジック) ---
        target_files = sc.get("target_files", [])
        on_screen_text = sc.get("on_screen_text", [])
        if target_files:
            # 画像パスを解決
            resolved_paths = []
            for img_name in target_files:
                p = _asset_for_visual(images_dir, img_name)
                if p: resolved_paths.append(p)

            # テキストがあるかどうか、および画像の向きをレイアウト計算に伝える
            layout_configs = _calculate_smart_layout(
                len(target_files), size, 
                has_text=bool(on_screen_text),
                image_paths=resolved_paths,
                two_image_layout=sc.get("two_image_layout", "horizontal")
            )
            for idx, img_name in enumerate(target_files):
                if idx >= len(layout_configs): break
                conf = layout_configs[idx]
                visual_path = _asset_for_visual(images_dir, img_name)
                if visual_path:
                    try:
                        v_clip = ImageClip(str(visual_path))
                        # アスペクト比維持しつつ枠内に収める
                        v_clip = v_clip.resized(width=conf["w"])
                        if v_clip.h > conf["h"]:
                            v_clip = v_clip.resized(height=conf["h"])
                        
                        # 領域内での中央寄せ
                        pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                        pos_y = conf["y"] + (conf["h"] - v_clip.h) // 2
                        
                        v_clip = v_clip.with_position((pos_x, pos_y))
                        v_clip = v_clip.with_duration(total_scene_duration).with_start(cumulative_time)
                        if video_cross > 0:
                            v_clip = v_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        all_clips.append(v_clip)
                    except Exception as e:
                        print(f"⚠️ ビジュアル表示失敗 ({img_name}): {e}")
        
        # --- 4. 要約テキストパネル (動的リサイズ) ---
        if on_screen_text:
            try:
                # 奇数番目を「事実・見出し」、偶数番目を「考察」として処理する
                formatted_lines = []
                for i, t in enumerate(on_screen_text):
                    # 豆腐文字（サロゲートペアや特殊記号）対策として、安全な文字に置換
                    safe_t = t.encode('cp932', errors='ignore').decode('cp932').strip()
                    
                    # if i % 2 == 0:
                    #     # 事実・見出し (0, 2, 4...)
                    #     if not safe_t.startswith("■"): safe_t = f"■ {safe_t}"
                    #     formatted_lines.append(safe_t)
                    # else:
                    #     # 考察・注意点 (1, 3, 5...)
                    #     if "└" not in safe_t: safe_t = f"  └ {safe_t}"
                    #     formatted_lines.append(safe_t)

                    formatted_lines.append(safe_t)
                
                # 行間が広すぎないよう、ダブル改行(\n\n)からシングル改行(\n)に変更
                summary_text = "\n".join(formatted_lines)
                
                # 画像がある場合は、画像の下に配置するためのサイズと座標を調整
                if target_files:
                    # 【画像あり：以前の完璧なレイアウトを維持】
                    text_h_max = int(available_h * 0.5)
                    text_y_base = start_y + int(available_h * 0.6) + margin*2 - 10
                    text_w = main_area_w - margin*4
                    
                    base_font_size = 40
                    reduction_per_line = 4
                    
                    frame_padding_h = -20 # 以前の数値
                    frame_offset_y = 30   # 以前の数値
                    text_offset_y = 50    # 以前の数値
                else:
                    # 【画像なし：今回調整したゆったりレイアウトを適用】
                    text_h_max = available_h - 200
                    text_y_base = margin + 220
                    text_w = main_area_w + 100
                    
                    base_font_size = 54
                    reduction_per_line = 5
                    
                    frame_padding_h = 270  # 今回の数値
                    frame_offset_y = 90   # 今回の数値
                    text_offset_y = -25    # 今回の数値

                # 行数に応じてフォントサイズを調整
                line_count = len(summary_text.split('\n'))
                if line_count > 6:
                    font_size = max(24, base_font_size - (line_count - 6) * reduction_per_line)
                else:
                    font_size = base_font_size

                # 先にテキストクリップを作成して、実際の高さを取得
                summary_clip = TextClip(
                    text=summary_text, font=font_to_use, font_size=font_size,
                    color="#1A237E", method="caption", size=(text_w + 200, text_h_max),
                    text_align="left"
                ).with_duration(total_scene_duration).with_start(cumulative_time)
                
                # テキストの高さに合わせて枠をリサイズ
                actual_text_h = summary_clip.h
                frame_path = images_dir / "main_frame.png"
                if frame_path.exists():
                    # 各ケースに最適化されたパディングを適用
                    m_frame = _load_frame_with_chromakey(frame_path, (text_w + 275, actual_text_h + frame_padding_h))
                    # 各ケースに最適化されたオフセットで配置
                    all_clips.append(m_frame.with_position((-100, text_y_base - frame_offset_y)).with_duration(total_scene_duration).with_start(cumulative_time))

                # テキストの位置を調整
                summary_clip = summary_clip.with_position((-90, text_y_base - text_offset_y))
                if video_cross > 0:
                    summary_clip = summary_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(summary_clip)
            except Exception as e:
                print(f"⚠️ 要約テキスト生成失敗: {e}")

        # --- 5. キャラクターレイヤー ---
        emotion = sc.get("emotion", "normal")
        char_path = _asset_for_emotion(images_dir, emotion)
        if char_path and sc.get("section_title") != "subscribe":
            try:
                # キャラクターは右側 20% の幅に収める
                char_max_w = int(size[0] * 0.25)
                char_h = int(size[1] * 0.7)
                
                # 警告対策と透過維持のため、RGBAに変換して読み込む
                with Image.open(str(char_path)) as img:
                    img_rgba = img.convert("RGBA")
                    char_clip = ImageClip(np.array(img_rgba)).resized(height=char_h)
                
                if char_clip.w > char_max_w:
                    char_clip = char_clip.resized(width=char_max_w)
                
                # # 下端をメインビジュアルの下端（bottom_yに合わせる）
                # char_x = size[0] - char_clip.w - 20
                # char_y = bottom_y - char_clip.h
                # 下端を画面の最下部に合わせる（字幕の後ろに配置）
                char_x = size[0] - char_clip.w - 10
                char_y = size[1] - char_clip.h
                
                char_clip = char_clip.with_duration(total_scene_duration).with_start(cumulative_time).with_position((char_x, char_y))
                if video_cross > 0:
                    char_clip = char_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(char_clip)
            except Exception as e:
                print(f"⚠️ キャラクター表示失敗: {e}")

        # --- 6. 字幕レイヤー (telop_frame.png 背面) ---
        segments = sc.get("segments", [])
        if segments and sc.get("section_title") != "subscribe":
            frame_path = images_dir / "telop_frame.png"
            if frame_path.exists():
                # 横幅を画面幅に近く(1920に対して1900)、縦幅を動画下端に寄せる
                telop_w_full = 2200
                # telop_h_full = 500
                # telop_y_bottom = size[1] - telop_h_full + 150 # 下端に寄せる
                telop_h_full = 550
                telop_y_bottom = size[1] - telop_h_full + 180 # 下端に寄せる
                telop_frame = _load_frame_with_chromakey(frame_path, (telop_w_full, telop_h_full))
                all_clips.append(telop_frame.with_position(("center", telop_y_bottom)).with_duration(total_scene_duration).with_start(cumulative_time))

            for seg in segments:
                seg_text = seg.get("text", "")
                seg_dur = float(seg.get("duration", 0.5))
                seg_start_in_total = cumulative_time + float(seg.get("start", 0.0))
                
                try:
                    txt_clip = TextClip(
                        text=seg_text, font=font_to_use, font_size=48,
                        color="white", stroke_color="black", stroke_width=1.5,
                        method="caption", size=(1700, 160), text_align="center"
                    ).with_duration(seg_dur).with_start(seg_start_in_total).with_position(("center", size[1] - 195))
                    all_clips.append(txt_clip)
                except Exception as e:
                    print(f"⚠️ 字幕生成失敗: {e}")

        # --- 7. チャンネル登録アニメーション (subscribeセクションのみ) ---
        if sc.get("section_title") == "subscribe":
            anim_path = assets / "animations" / "subscribe01-ja.mp4"
            if anim_path.exists():
                try:
                    # アニメーションを読み込み
                    anim_clip = _load_video_with_chromakey(anim_path, size)
                    
                    # セクション全体で表示
                    anim_duration = min(anim_clip.duration, total_scene_duration)
                    anim_clip = anim_clip.with_start(cumulative_time).with_duration(anim_duration)
                    
                    # 他のクリップより前面に表示するために最後に追加
                    all_clips.append(anim_clip)
                    print(f"🎬 登録アニメーションを配置: {anim_duration}s (start={cumulative_time})")
                except Exception as e:
                    print(f"⚠️ アニメーション合成失敗: {e}")
            else:
                print(f"⚠️ アニメーションファイルが見つかりません: {anim_path}")

        cumulative_time += total_scene_duration

    final = CompositeVideoClip(all_clips, size=size).with_duration(cumulative_time)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    final.write_videofile(
        str(out_path), fps=fps, codec="libx264", audio=False,
        threads=max(1, (os.cpu_count() or 2) - 1), logger=None
    )
    return str(out_path)
