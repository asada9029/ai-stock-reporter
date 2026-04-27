from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os
from datetime import datetime
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

def _wrap_text_jp(text: str, max_chars_per_line: int) -> str:
    """
    日本語テキストを「文字数ベース」で折り返す。
    - 既存の改行は保持
    - 半角/全角の厳密幅ではなく、レイアウト崩れ防止のための簡易ラップ
    """
    if not text:
        return ""
    lines = str(text).split("\n")
    out_lines: list[str] = []
    for ln in lines:
        s = ln.rstrip()
        if not s:
            out_lines.append("")
            continue
        if len(s) <= max_chars_per_line:
            out_lines.append(s)
            continue
        for i in range(0, len(s), max_chars_per_line):
            out_lines.append(s[i : i + max_chars_per_line])
    return "\n".join(out_lines).strip("\n")

def _asset_for_emotion(assets_dir: Path, emotion: str, is_shorts: bool = False) -> Optional[Path]:
    if is_shorts:
        # ショート動画専用：mini.png を優先
        candidates = [
            assets_dir / "mini.png",
            assets_dir / f"character_{emotion}.png",
            assets_dir / "character_normal.png",
        ]
    else:
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

def _load_image_clip(path: Path, size: Tuple[int, int], crop_to_aspect: bool = False) -> ImageClip:
    """画像を読み込み、リサイズする。crop_to_aspect=True の場合はアスペクト比に合わせてクロップする。"""
    clip = ImageClip(str(path))
    if crop_to_aspect:
        # ターゲットのアスペクト比 (w/h)
        target_ratio = size[0] / size[1]
        current_ratio = clip.w / clip.h
        
        if current_ratio > target_ratio:
            # 元画像の方が横長 -> 左右をカット
            new_w = int(clip.h * target_ratio)
            x_center = clip.w / 2
            clip = clip.cropped(x1=x_center - new_w/2, y1=0, x2=x_center + new_w/2, y2=clip.h)
        else:
            # 元画像の方が縦長（または同じ） -> 上下をカット
            new_h = int(clip.w / target_ratio)
            y_center = clip.h / 2
            clip = clip.cropped(x1=0, y1=y_center - new_h/2, x2=clip.w, y2=y_center + new_h/2)
            
    return clip.resized(new_size=size)

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
    is_shorts = sw < sh
    
    if is_shorts:
        # --- ショート動画（縦型）のレイアウト ---
        # 案B（注目銘柄）を想定：上に画像、下に要約、さらに下にキャラ
        margin = 40
        available_w = sw - (margin * 2)
        
        # 画像は最上部に配置
        img_h = int(sh * 0.45)
        # ここを増やすと「案Bの画像」が下にズレる（=余白が増える）
        start_y = 150
        
        positions = []
        if count >= 1:
            # 1枚目をメインとして配置
            positions.append({"x": margin, "y": start_y, "w": available_w, "h": img_h})
        return positions

    # --- 横型動画のレイアウト（既存） ---
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
        is_shorts = size[0] < size[1] # 縦長ならショート
        
        if bg_name == "bg_subscribe":
            # チャンネル登録シーンは単色（目に優しいクリーム色）
            bg_clip = ColorClip(size, color=(255, 253, 208))
        elif is_shorts:
            # ショート動画は縦型専用背景を使用（必要に応じてクロップしてフィット）
            bg_path = _asset_for_visual(images_dir, "tate_bg_illust.png")
            if bg_path:
                try:
                    bg_clip = _load_image_clip(bg_path, size, crop_to_aspect=True)
                except Exception as e:
                    print(f"⚠️ ショート背景画像読み込み失敗 (tate_bg_illust.png): {e}")
                    bg_clip = ColorClip(size, color=(255, 253, 208))
            else:
                print("⚠️ ショート背景が見つからないため、クリーム色で代替します (tate_bg_illust.png)")
                bg_clip = ColorClip(size, color=(255, 253, 208))
        else:
            bg_path = _asset_for_visual(images_dir, bg_name)
            if bg_path:
                try:
                    # ショートの場合はクロップして中央部分を使用
                    bg_clip = _load_image_clip(bg_path, size, crop_to_aspect=is_shorts)
                except Exception as e:
                    print(f"⚠️ 背景画像読み込み失敗 ({bg_name}): {e}")
                    bg_clip = ColorClip(size, color=(30, 30, 40))
            else:
                bg_clip = ColorClip(size, color=(30, 30, 40))

        # 各シーンの背景は必ずシーン区間に合わせる（未設定だと t=0 に重なり全面を覆う）
        bg_clip = bg_clip.with_duration(total_scene_duration).with_start(cumulative_time)
        all_clips.append(bg_clip)

        # --- 2. セクションタイトル (動的リサイズ) ---
        section_title = sc.get("section_title")
        # ショートではタイトル表示をしない
        if (not is_shorts) and section_title and section_title != "subscribe":
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

        # --- 2.5 ショート案Aのタイトル（title_frame） ---
        is_shorts_a = bool(is_shorts and (not sc.get("target_files")) and sc.get("on_screen_text"))
        if is_shorts_a and sc.get("section_title") != "subscribe":
            try:
                # 案AのタイトルはAIに作らせず、コード側で固定生成して安定させる
                now = datetime.now()
                title_text = f"{now.month}/{now.day}の3大ニュース"

                title_clip = TextClip(
                    text=title_text,
                    font=font_to_use,
                    font_size=64,
                    color="#4A2711",
                    method="label",
                    size=(None, 90),
                ).with_duration(total_scene_duration).with_start(cumulative_time)

                frame_w = min(size[0] - 80, title_clip.w + 220)
                frame_h = title_clip.h + 150
                frame_path = images_dir / "title_frame.png"
                # ここを変えると「フレームと文字」をまとめて上下に動かせる
                title_frame_y = 160
                if frame_path.exists():
                    t_frame = _load_frame_with_chromakey(frame_path, (frame_w, frame_h))
                    all_clips.append(
                        t_frame.with_position(("center", title_frame_y))
                        .with_duration(total_scene_duration)
                        .with_start(cumulative_time)
                    )

                title_x = (size[0] - frame_w) // 2 + 95
                # 文字のYはフレーム位置と連動させる（title_y だけ動いてフレームがズレない問題の対策）
                title_y = title_frame_y + (frame_h - title_clip.h) // 2 - 20
                all_clips.append(title_clip.with_position((title_x, title_y)))
            except Exception as e:
                print(f"⚠️ ショート案Aタイトル生成失敗: {e}")

        # --- 3. メインビジュアルレイヤー (既存の1〜4枚ロジック) ---
        target_files = sc.get("target_files", [])
        on_screen_text = sc.get("on_screen_text", [])
        if target_files:
            # 画像パスを解決
            resolved_paths = []
            valid_target_files = []
            for img_name in target_files:
                p = _asset_for_visual(images_dir, img_name)
                if p: 
                    resolved_paths.append(p)
                    valid_target_files.append(img_name)
            
            # 実際に存在するファイルのみを対象にする
            target_files = valid_target_files

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
                # 豆腐文字（サロゲートペアや特殊記号）対策として、安全な文字に置換
                formatted_lines = []
                # on_screen_text が文字列単体の場合はリストに変換
                text_list = [on_screen_text] if isinstance(on_screen_text, str) else on_screen_text
                
                for t in text_list:
                    # on_screen_text が完全に消える事故を避けるため、cp932 で空になった場合は原文を使う
                    raw_t = str(t).strip()
                    safe_t = raw_t.encode("cp932", errors="ignore").decode("cp932").strip()
                    if not safe_t and raw_t:
                        safe_t = raw_t
                    if safe_t:
                        formatted_lines.append(safe_t)

                # ショートは「文字数で確実に折り返し」して横はみ出しを防ぐ
                if is_shorts:
                    is_a = bool(not target_files)
                    # 案Aはタイトルを別枠（title_frame）で表示するため、本文は全行をそのまま使う
                    body_lines = formatted_lines
                    wrap_n = 17 if is_a else 16
                    wrapped = []
                    for ln in body_lines:
                        wrapped.append(_wrap_text_jp(ln, wrap_n))
                    summary_text = "\n".join(wrapped).strip()
                else:
                    summary_text = "\n".join(formatted_lines)
                
                # 画像がある場合は、画像の下に配置するためのサイズと座標を調整
                if is_shorts:
                    # 【ショート動画：縦型レイアウト】
                    # 案A: テキストのみ（中央付近）
                    # 案B: 上にチャート、チャートの下に要約テキスト
                    if target_files:
                        # --- 案B（画像あり）の設定 ---
                        text_w = size[0] - 20
                        img_y = 150
                        img_h = int(size[1] * 0.45)
                        text_y_base = img_y + img_h - 20
                        text_h_max = int(size[1] * 0.25)
                        base_font_size = 48
                        frame_padding_h = 90
                        frame_offset_y = 50
                        frame_name = "main_frame.png"
                    else:
                        # --- 案A（テキストのみ）の設定 ---
                        text_w = size[0] + 180
                        text_y_base = 300
                        text_h_max = int(size[1] * 0.6)
                        base_font_size = 68

                        frame_padding_h = 10
                        frame_offset_y = 0
                        # 案A専用の縦長フレームを使用
                        frame_name = "tate_main_flame.png"
                    
                    reduction_per_line = 4
                    text_offset_y = 0
                elif target_files:
                    # 【画像あり：以前の完璧なレイアウトを維持】
                    text_h_max = int(available_h * 0.5)
                    text_y_base = start_y + int(available_h * 0.6) + margin*2 - 10
                    text_w = main_area_w - margin*4
                    
                    base_font_size = 40
                    reduction_per_line = 4
                    
                    frame_padding_h = -20 # 以前の数値
                    frame_offset_y = 30   # 以前の数値
                    text_offset_y = 50    # 以前の数値
                    # 横動画（画像あり）の要約枠
                    frame_name = "main_frame.png"
                else:
                    # 【画像なし：今回調整したゆったりレイアウトを適用】
                    text_h_max = available_h - 200
                    text_y_base = margin + 220
                    text_w = main_area_w + 100
                    
                    base_font_size = 54
                    reduction_per_line = 6
                    
                    frame_padding_h = 270  # 今回の数値
                    frame_offset_y = 90   # 今回の数値
                    text_offset_y = -25    # 今回の数値
                    # 横動画（画像なし）の要約枠
                    frame_name = "main_frame.png"

                # 行数に応じてフォントサイズを調整
                line_count = len(summary_text.split('\n'))
                if line_count > 6:
                    font_size = max(24, base_font_size - (line_count - 6) * reduction_per_line)
                else:
                    font_size = base_font_size

                # 先にテキストクリップを作成して、実際の高さを取得
                summary_clip = TextClip(
                    text=summary_text, font=font_to_use, font_size=font_size,
                    color="#1A237E", method="caption",
                    size=(text_w, text_h_max),
                    text_align="left" # 左揃えに変更
                ).with_duration(total_scene_duration).with_start(cumulative_time)
                
                # テキストの高さに合わせて枠をリサイズ
                actual_text_h = summary_clip.h
                frame_path = images_dir / frame_name
                if frame_path.exists():
                    # 各ケースに最適化されたパディングを適用
                    if is_shorts:
                        m_frame = _load_frame_with_chromakey(frame_path, (text_w + 100, actual_text_h + frame_padding_h))
                        all_clips.append(m_frame.with_position(("center", text_y_base - frame_offset_y)).with_duration(total_scene_duration).with_start(cumulative_time))
                    else:
                        m_frame = _load_frame_with_chromakey(frame_path, (text_w + 275, actual_text_h + frame_padding_h))
                        # 各ケースに最適化されたオフセットで配置
                        all_clips.append(m_frame.with_position((-100, text_y_base - frame_offset_y)).with_duration(total_scene_duration).with_start(cumulative_time))

                # テキストの位置を調整
                if is_shorts:
                    summary_clip = summary_clip.with_position(("center", text_y_base))
                else:
                    summary_clip = summary_clip.with_position((-90, text_y_base - text_offset_y))
                if video_cross > 0:
                    summary_clip = summary_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(summary_clip)
            except Exception as e:
                print(f"⚠️ 要約テキスト生成失敗: {e}")

        # --- 5. キャラクターレイヤー ---
        emotion = sc.get("emotion", "normal")
        char_path = _asset_for_emotion(images_dir, emotion, is_shorts=is_shorts)
        if char_path and sc.get("section_title") != "subscribe":
            try:
                if is_shorts:
                    # ショート：mini.png をテキストの左下に配置
                    char_h = int(size[1] * 0.25)
                    with Image.open(str(char_path)) as img:
                        img_rgba = img.convert("RGBA")
                        # 左右反転
                        img_flipped = img_rgba.transpose(Image.FLIP_LEFT_RIGHT)
                        char_clip = ImageClip(np.array(img_flipped)).resized(height=char_h)
                    
                    # テキストの位置（text_y_base）と高さ（actual_text_h）から相対的に配置
                    if on_screen_text:
                        is_shorts_a = bool(is_shorts and (not sc.get("target_files")) and sc.get("on_screen_text"))
                        char_x = 30
                        # テキストの開始位置 + テキストの高さ + 調整
                        # 案Aだけ、キャラを少し上に寄せる（他レイアウトに影響させない）
                        char_y_offset = 160 if is_shorts_a else 100
                        char_y = text_y_base + actual_text_h - char_y_offset
                        # 画面外にはみ出さないように制限
                        char_y = min(char_y, size[1] - char_clip.h - 10)
                    else:
                        char_x = 30
                        char_y = size[1] - char_clip.h - 170
                else:
                    # 横型：右端に配置
                    char_max_w = int(size[0] * 0.25)
                    char_h = int(size[1] * 0.7)
                    
                    # 警告対策と透過維持のため、RGBAに変換して読み込む
                    with Image.open(str(char_path)) as img:
                        img_rgba = img.convert("RGBA")
                        char_clip = ImageClip(np.array(img_rgba)).resized(height=char_h)
                    
                    if char_clip.w > char_max_w:
                        char_clip = char_clip.resized(width=char_max_w)
                    
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
        # ショートでは字幕（segments）を表示しない
        if (not is_shorts) and segments and sc.get("section_title") != "subscribe":
            frame_path = images_dir / "telop_frame.png"
            # 横型（既存）
            if frame_path.exists():
                # 横幅を画面幅に近く(1920に対して1900)、縦幅を動画下端に寄せる
                telop_w_full = 2200
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
                    if is_shorts:
                        # 縦型（ショート）の場合：引き伸ばさず、横幅に合わせてアスペクト比を維持
                        # 上下に余白ができても良い
                        anim_clip = VideoFileClip(str(anim_path)).resized(width=size[0])
                        # 透過処理
                        anim_clip = _load_video_with_chromakey(anim_path, (size[0], anim_clip.h))
                        # 画面中央に配置
                        anim_clip = anim_clip.with_position(("center", "center"))
                    else:
                        # 横型（通常）：画面全体に表示
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

    # 画質改善: bitrate と CRF を指定（ショートで「ボケる」問題が出やすい）
    is_shorts_output = size[0] < size[1]
    bitrate = "12000k" if is_shorts_output else "9000k"
    ffmpeg_params = ["-crf", "18", "-preset", "slow"]
    final.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio=False,
        bitrate=bitrate,
        ffmpeg_params=ffmpeg_params,
        threads=max(1, (os.cpu_count() or 2) - 1),
        logger=None,
    )
    return str(out_path)
