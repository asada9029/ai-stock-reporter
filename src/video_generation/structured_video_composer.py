from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os
import re
import unicodedata
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.config.presentation import is_immersive_mode, normalize_presentation_mode
from src.video_generation.character_emotion import (
    assign_segment_emotions,
    apply_emotion_motion,
    merge_emotion_beats_for_scene,
    normalize_emotion,
)

from moviepy import (
    ImageClip,
    TextClip,
    CompositeVideoClip,
    ColorClip,
    VideoFileClip
)
# v2.0系でのエフェクトクラス
from moviepy.video.fx import FadeIn, FadeOut, MaskColor

def _rounded_plate_clip(size: Tuple[int, int], *, radius: int = 26, color=(255, 255, 255), alpha: int = 210) -> ImageClip:
    """半透明の角丸プレート（tickerカード等）"""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = (int(color[0]), int(color[1]), int(color[2]), int(alpha))
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill, outline=(255, 255, 255, 140), width=2)
    return ImageClip(np.array(img))

def _shadow_clip(size: Tuple[int, int], *, radius: int = 18, blur: int = 14, alpha: int = 80) -> ImageClip:
    """チャート等の背面に置くソフトシャドウ"""
    w, h = size
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=(0, 0, 0, int(alpha)))
    if blur > 0:
        base = base.filter(ImageFilter.GaussianBlur(radius=float(blur)))
    return ImageClip(np.array(base))

def _load_pil_font(font_path: Optional[str], font_size: int) -> ImageFont.FreeTypeFont:
    """
    PILで日本語を含むテキストを描画するためのフォントをロードする。
    font_path が無い場合は PIL のデフォルトにフォールバック（環境によっては豆腐化する）。
    """
    try:
        if font_path and Path(font_path).exists():
            return ImageFont.truetype(font_path, font_size)
    except Exception:
        pass
    return ImageFont.load_default()


def _build_emphasis_spans(line: str, emphasis_items: List[Dict[str, str]]) -> List[Tuple[str, Optional[str]]]:
    """
    1行の文字列を、emphasis語に一致する部分だけ分割して返す。
    戻り値: [(text, style_or_none), ...]
    - style_or_none が None の部分は通常色
    - 複数語が重なる場合は「長い語優先」
    """
    if not line:
        return [("", None)]
    if not emphasis_items:
        return [(line, None)]

    items: list[tuple[str, str]] = []
    for it in emphasis_items:
        if not isinstance(it, dict):
            continue
        t = str(it.get("text", "")).strip()
        s = str(it.get("style", "")).strip() or "key"
        if t:
            items.append((t, s))
    if not items:
        return [(line, None)]

    # 長い語から順にマッチさせて、重複を避ける
    items.sort(key=lambda x: len(x[0]), reverse=True)

    spans: list[tuple[int, int, str]] = []
    for word, style in items:
        start = 0
        while True:
            idx = line.find(word, start)
            if idx < 0:
                break
            s_idx, e_idx = idx, idx + len(word)
            # 既存spanと重なるならスキップ（長い語優先のため）
            if any(not (e_idx <= s0 or e0 <= s_idx) for s0, e0, _ in spans):
                start = idx + 1
                continue
            spans.append((s_idx, e_idx, style))
            start = e_idx

    if not spans:
        return [(line, None)]
    spans.sort(key=lambda x: x[0])

    out: list[tuple[str, Optional[str]]] = []
    cur = 0
    for s_idx, e_idx, style in spans:
        if s_idx > cur:
            out.append((line[cur:s_idx], None))
        out.append((line[s_idx:e_idx], style))
        cur = e_idx
    if cur < len(line):
        out.append((line[cur:], None))
    return out


def _render_text_panel_with_emphasis(
    *,
    text: str,
    emphasis_items: List[Dict[str, str]],
    font_path: Optional[str],
    font_size: int,
    size: Tuple[int, int],
    base_color: str,
    style_color: Dict[str, str],
    line_spacing: int = 10,
    # NOTE: main_frame.png の可読領域に合わせ、左を広めに取る（TextClip時の見え方に寄せる）
    padding: Tuple[int, int] = (120, 14),
) -> ImageClip:
    """
    要約パネル用の文字を PIL で描画し、emphasis語だけ色分けして ImageClip にする。
    - size=(w,h) は「文字領域」サイズ（枠画像とは別）
    """
    w, h = size
    pad_x, pad_y = padding
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_pil_font(font_path, font_size)

    # PILは色をRGBで扱うので、#RRGGBB を変換
    def _hex_to_rgba(hexstr: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        hs = hexstr.lstrip("#")
        if len(hs) != 6:
            return (26, 35, 126, alpha)
        return (int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16), alpha)

    normal_rgba = _hex_to_rgba(base_color)

    # 行単位で描画（wrapは既に済んだ前提）
    y = pad_y
    for raw_line in (text or "").split("\n"):
        line = str(raw_line)
        spans = _build_emphasis_spans(line, emphasis_items)

        # 行の高さ（fontのbboxから概算）
        bbox = draw.textbbox((0, 0), "あ", font=font)
        line_h = (bbox[3] - bbox[1]) + line_spacing
        if y + line_h > h:
            break

        x = pad_x
        for seg_text, seg_style in spans:
            if not seg_text:
                continue
            color_hex = style_color.get(seg_style or "", base_color)
            seg_rgba = _hex_to_rgba(color_hex)
            draw.text((x, y), seg_text, font=font, fill=seg_rgba)
            seg_bbox = draw.textbbox((x, y), seg_text, font=font)
            x = seg_bbox[2]  # 次の開始位置
            if x > w - pad_x:
                break
        y += line_h

    return ImageClip(np.array(img))


def _render_text_panel_plain(
    *,
    text: str,
    font_path: Optional[str],
    font_size: int,
    size: Tuple[int, int],
    color: str,
    line_spacing: int = 10,
    # main_frame.png に合わせた余白（左を広めに）
    padding: Tuple[int, int] = (120, 14),
) -> ImageClip:
    """PILで単色テキストを描画して ImageClip にする（枠内統合のベース用）。"""
    w, h = size
    pad_x, pad_y = padding
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_pil_font(font_path, font_size)

    def _hex_to_rgba(hexstr: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        hs = hexstr.lstrip("#")
        if len(hs) != 6:
            return (26, 35, 126, alpha)
        return (int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16), alpha)

    rgba = _hex_to_rgba(color)
    bbox = draw.textbbox((0, 0), "あ", font=font)
    line_h = (bbox[3] - bbox[1]) + line_spacing

    y = pad_y
    for raw_line in (text or "").split("\n"):
        if y + line_h > h:
            break
        draw.text((pad_x, y), str(raw_line), font=font, fill=rgba)
        y += line_h
    return ImageClip(np.array(img))


def _compute_emphasis_overlays(
    *,
    text: str,
    emphasis_items: List[Dict[str, str]],
    font_path: Optional[str],
    font_size: int,
    size: Tuple[int, int],
    base_color: str,
    style_color: Dict[str, str],
    line_spacing: int = 10,
    padding: Tuple[int, int] = (120, 14),
) -> List[Tuple[ImageClip, Tuple[int, int], str]]:
    """
    emphasis語だけを透明背景に描画したオーバーレイを生成する。
    戻り値: [(clip, (x,y), style), ...]  (x,y はパネル内相対座標)
    """
    w, h = size
    pad_x, pad_y = padding
    font = _load_pil_font(font_path, font_size)
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)

    def _hex_to_rgba(hexstr: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        hs = hexstr.lstrip("#")
        if len(hs) != 6:
            return (26, 35, 126, alpha)
        return (int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16), alpha)

    bbox = draw.textbbox((0, 0), "あ", font=font)
    line_h = (bbox[3] - bbox[1]) + line_spacing

    overlays: list[Tuple[ImageClip, Tuple[int, int], str]] = []
    y = pad_y
    for raw_line in (text or "").split("\n"):
        if y + line_h > h:
            break
        line = str(raw_line)
        spans = _build_emphasis_spans(line, emphasis_items)
        x = pad_x
        for seg_text, seg_style in spans:
            if not seg_text:
                continue
            seg_bbox = draw.textbbox((0, 0), seg_text, font=font)
            seg_w = max(1, seg_bbox[2] - seg_bbox[0])
            seg_h = max(1, seg_bbox[3] - seg_bbox[1])
            if seg_style:
                # 強調部分だけ透明背景で描画
                img = Image.new("RGBA", (seg_w + 4, seg_h + 4), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                color_hex = style_color.get(seg_style, base_color)
                d.text((2, 2), seg_text, font=font, fill=_hex_to_rgba(color_hex))
                overlays.append((ImageClip(np.array(img)), (x, y), seg_style))
            x += seg_w
            if x > w - pad_x:
                break
        y += line_h

    return overlays

def _wrap_text_jp(text: str, max_width_per_line: float) -> str:
    """
    日本語テキストを「視覚的な幅」ベースで折り返す。
    - 全角文字を 1.0、半角文字を 0.5 としてカウント
    - 既存の改行は保持
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
        
        current_line = ""
        current_width = 0.0
        for char in s:
            # 全角(W, F, A)は1.0、それ以外(半角)は0.5としてカウント
            char_width = 1.0 if unicodedata.east_asian_width(char) in ('W', 'F', 'A') else 0.5
            
            if current_width + char_width > max_width_per_line:
                out_lines.append(current_line)
                current_line = char
                current_width = char_width
            else:
                current_line += char
                current_width += char_width
        
        if current_line:
            out_lines.append(current_line)
            
    return "\n".join(out_lines).strip("\n")


def _immersive_price_change_sign(lines: List[str]) -> Optional[str]:
    """on_screen_text 全体から騰落符号を推定（枠色・文字色を一致させる）。"""
    for ln in lines[:6]:
        s = str(ln).replace("％", "%").replace("＋", "+").replace("－", "-")
        m = re.search(r"([+\-])\s*\d", s)
        if m:
            return m.group(1)
    combined = " ".join(str(x) for x in lines[:6])
    if re.search(r"[-－]|下落|急落|下げ|マイナス", combined):
        return "-"
    if re.search(r"[+＋]|上昇|急騰|上げ|プラス", combined):
        return "+"
    return None


def _label_text_color_for_immersive(line: str, *, change_sign: Optional[str] = None) -> str:
    """immersive 用: 騰落のニュアンスに応じたラベル色。"""
    if change_sign == "-":
        return "#B71C1C"
    if change_sign == "+":
        return "#1B5E20"
    if re.search(r"[-－％%]|下落|急落|下げ|マイナス", line):
        return "#B71C1C"
    if re.search(r"[+＋]|上昇|急騰|上げ|プラス", line):
        return "#1B5E20"
    return "#1A237E"


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
        
    # Windows(cp932) 対策: 絵文字を含めない
    print(f"[WARN] 資産が見つかりません: {name} (検索先: {p}, {p_assets})")
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

def _calculate_smart_layout(
    count: int,
    screen_size: Tuple[int, int],
    has_text: bool = False,
    image_paths: List[Path] = None,
    two_image_layout: str = "horizontal",
    show_subtitles: bool = True,
    *,
    top_reserved_h: Optional[int] = None,
    image_ratio_when_text: float = 0.68,
) -> List[Dict]:
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
        start_y = 110
        
        positions = []
        if count >= 1:
            # 1枚目をメインとして配置
            positions.append({"x": margin, "y": start_y, "w": available_w, "h": img_h})
        return positions

    # --- 横型動画のレイアウト（既存） ---
    # 1080p用に定数をスケールアップ
    text_area_h = 165 if show_subtitles else 40
    title_area_h = top_reserved_h if top_reserved_h is not None else 128
    margin = 22
    
    # メイン 80%, キャラ 20%
    main_area_w = int(sw * 0.8)
    
    # 有効な高さ（タイトルの下から字幕の上まで）
    available_h = sh - text_area_h - title_area_h - (margin * 2)
    start_x = margin
    start_y = title_area_h + margin

    # テキスト併用時は、画像エリアの最大高さを制限する
    # （event_calendar 等は表が主役なので比率を上げられる）
    img_available_h = int(available_h * float(image_ratio_when_text)) if has_text else available_h

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
    font: str = "DejaVu-Sans",
    show_subtitles: bool = True,
    presentation_mode: str = "classic",
) -> str:
    assets = Path(assets_dir)
    images_dir = assets / "images"
    fonts_dir = assets / "fonts"
    font_path_found = _find_font_path(fonts_dir)
    font_to_use = font_path_found if font_path_found else font
    presentation_mode = normalize_presentation_mode(presentation_mode)
    
    all_clips = []
    cumulative_time = 0.0
    
    # 1080p用レイアウト定数
    # 字幕を表示しない場合は、下部のエリアを0にしてメイン領域を広げる
    text_area_h = 165 if show_subtitles else 40
    title_area_h = 128
    margin = 22
    main_area_w = int(size[0] * 0.8)
    start_y = title_area_h + margin
    available_h = size[1] - text_area_h - title_area_h - (margin * 2)
    bottom_y = size[1] - text_area_h - margin

    for sc in scenes:
        total_scene_duration = float(sc.get("duration", 5.0))
        video_cross = float(sc.get("video_crossfade", 0.2))
        # タイトル枠の実サイズに応じて、画像の上側予約領域を相対化する
        top_reserved_h_for_scene: Optional[int] = None
        # ショート: 画像下端・テキスト枠下端（相対配置用）
        shorts_img_bottom_y: Optional[int] = None
        shorts_text_bottom_y: Optional[int] = None
        
        # --- 1. 背景レイヤー ---
        bg_name = sc.get("bg_name", "bg_illust.png")
        is_shorts = size[0] < size[1] # 縦長ならショート
        use_immersive = is_immersive_mode(presentation_mode, video_type="shorts" if is_shorts else "horizontal")
        
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
                    text=section_title,
                    font=font_to_use,
                    # レイアウトテスト(step1)と同等の見え方に揃える
                    font_size=54,
                    color="#4A2711",
                    method="label",
                    size=(None, 90),
                ).with_duration(total_scene_duration).with_start(cumulative_time)
                
                # テキストサイズに合わせて枠をリサイズ (パディングを追加)
                frame_w = title_clip.w + 200
                frame_h = title_clip.h + 120
                
                frame_path = images_dir / "title_frame.png"
                if frame_path.exists():
                    t_frame = _load_frame_with_chromakey(frame_path, (frame_w, frame_h))
                    all_clips.append(t_frame.with_position((0, 15)).with_duration(total_scene_duration).with_start(cumulative_time))
                    # タイトル枠の下端 + 少しの余白を、画像レイアウトの予約領域として使う
                    top_reserved_h_for_scene = max(title_area_h, 15 + int(frame_h) + 10)

                # テキストを枠の中央に配置 (垂直方向のオフセットを調整)
                text_y = (frame_h - title_clip.h) // 2 - 5
                title_clip = title_clip.with_position((95, text_y))
                all_clips.append(title_clip)
            except Exception as e:
                print(f"⚠️ セクションタイトル生成失敗: {e}")

        # --- 2.25 ショートB 上部タイトル（黒帯＋白文字） ---
        # ※Shorts B のみ対象（explained_term が無い＝用語解説ではない）
        if is_shorts and sc.get("section_title") != "subscribe":
            try:
                tfs = sc.get("target_files") or []
                tf0 = str(tfs[0]) if isinstance(tfs, list) and tfs else ""
                is_shorts_b_like = (not sc.get("explained_term"))
                if is_shorts_b_like:
                    tomorrow = datetime.now() + timedelta(days=1)
                    header_text = f"明日{tomorrow.month}/{tomorrow.day}注目の銘柄"
                    header_font_size = int(size[1] * 0.05)
                    header_font_size = max(44, min(96, header_font_size))
                    band_y = int(size[1] * 0.03) - 30
                    band_h = int(size[1] * 0.13)
                    band = (
                        ColorClip((size[0], band_h), color=(0, 0, 0))
                        .with_duration(total_scene_duration)
                        .with_start(cumulative_time)
                        .with_position((0, band_y))
                    )
                    all_clips.append(band)
                    # 帯の縦真ん中に来るように、labelで実寸を取って手動センタリング
                    title_label = TextClip(
                        text=header_text,
                        font=font_to_use,
                        font_size=header_font_size,
                        color="#FFFFFF",
                        method="label",
                        size = (None, 100)
                    )
                    title_y = band_y + max(0, int((band_h - title_label.h) / 2))
                    header_clip = (
                        title_label.with_duration(total_scene_duration)
                        .with_start(cumulative_time)
                        .with_position(("center", title_y))
                    )
                    all_clips.append(header_clip)
            except Exception as e:
                print(f"[WARN] shorts_b header title failed: {e}")

        # --- 2.5 ショート案Aのタイトル（title_frame） ---
        is_shorts_a = bool(is_shorts and (not sc.get("target_files")) and sc.get("on_screen_text"))
        if is_shorts_a and sc.get("section_title") != "subscribe":
            try:
                # 案AのタイトルはAIに作らせず、コード側で固定生成して安定させる
                now = datetime.now()
                title_text = f"{now.month}/{now.day}のやさしい用語解説"

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
            # event_calendar 判定（表画像はズーム/枠/影を抑制し、レイアウト比率も表優先にする）
            section_title_str = str(sc.get("section_title", "") or "")
            tf_names = [str(x).lower() for x in (target_files or [])]
            is_event_calendar_scene = (
                ("イベントカレンダー" in section_title_str)
                or ("event_calendar" in section_title_str.lower())
                or any(("kessan_schedule" in n) or ("soukai_schedule" in n) for n in tf_names)
            )
            # ブリッジは「全画面一枚絵」として扱う（番組感のため）
            if (not is_shorts) and sc.get("visual_template") == "bridge":
                img_name = target_files[0]
                visual_path = _asset_for_visual(images_dir, img_name)
                if visual_path:
                    try:
                        bridge_clip = _load_image_clip(visual_path, size, crop_to_aspect=True)
                        bridge_clip = (
                            bridge_clip.with_position((0, 0))
                            .with_duration(total_scene_duration)
                            .with_start(cumulative_time)
                        )
                        if video_cross > 0:
                            bridge_clip = bridge_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        all_clips.append(bridge_clip)
                    except Exception as e:
                        print(f"[WARN] ブリッジ表示失敗 ({img_name}): {e}")
                # ブリッジは他の画像レイアウトを通さない
                target_files = []

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
                two_image_layout=sc.get("two_image_layout", "horizontal"),
                show_subtitles=show_subtitles,
                top_reserved_h=top_reserved_h_for_scene,
                image_ratio_when_text=0.82 if is_event_calendar_scene else 0.68,
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

                        # immersive: チャート系だけ“軽いズーム”で番組感を出す（classicは維持）
                        # 画面からはみ出さないよう、最初に少しだけ小さくしてからズームする。
                        section_title = str(sc.get("section_title", "") or "")
                        img_name_l = str(img_name).lower()
                        # イベントカレンダー（決算/株主総会の表）はズーム厳禁・見切れ厳禁
                        is_event_calendar = (
                            ("イベントカレンダー" in section_title)
                            or ("event_calendar" in section_title.lower())
                            or ("kessan_schedule" in img_name_l)
                            or ("soukai_schedule" in img_name_l)
                        )
                        # チャート系のみ軽いズーム（表やパネルは対象外）
                        is_chart = str(sc.get("image_type", "")).startswith("chart") or ("chart" in img_name_l)
                        if (not is_shorts) and use_immersive and is_chart and (not is_event_calendar) and total_scene_duration >= 2.0:
                            base_shrink = 0.95
                            zoom_max = 1.05  # base_shrink * zoom_max <= 1.0 を想定
                            zoom_dur = min(2.0, max(0.8, total_scene_duration * 0.35))
                            v_clip = v_clip.resized(base_shrink)

                            def _zoom_factor(t: float) -> float:
                                if t <= 0:
                                    return 1.0
                                if t >= zoom_dur:
                                    return zoom_max
                                u = t / zoom_dur
                                # easeOutQuad
                                return 1.0 + (zoom_max - 1.0) * (1.0 - (1.0 - u) * (1.0 - u))

                            # moviepy v2: resized() は係数関数を受け取れる
                            v_clip = v_clip.resized(lambda t: _zoom_factor(float(t)))

                        # event_calendar は “contain” をより厳密に（見切れ防止の安全策）
                        if (not is_shorts) and use_immersive and is_event_calendar:
                            # すでに枠内に収める処理はあるが、表画像は横長になりがちなので少し余裕を見て縮める
                            v_clip = v_clip.resized(0.97)
                        
                        # 領域内での中央寄せ
                        pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                        pos_y = conf["y"] + (conf["h"] - v_clip.h) // 2
                        if is_shorts:
                            img_bottom = int(pos_y + v_clip.h)
                            shorts_img_bottom_y = (
                                img_bottom
                                if shorts_img_bottom_y is None
                                else max(shorts_img_bottom_y, img_bottom)
                            )
                        
                        v_clip = v_clip.with_position((pos_x, pos_y))
                        v_clip = v_clip.with_duration(total_scene_duration).with_start(cumulative_time)
                        if video_cross > 0:
                            v_clip = v_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        # immersive: チャートはレイアウト枠(conf)基準で影のみ（色枠は使わない）
                        if (not is_shorts) and use_immersive and is_chart and (not is_event_calendar):
                            try:
                                box_w, box_h = int(conf["w"]), int(conf["h"])
                                box_x, box_y = int(conf["x"]), int(conf["y"])
                                shadow = (
                                    _shadow_clip(
                                        (box_w + 28, box_h + 28),
                                        radius=20,
                                        blur=14,
                                        alpha=70,
                                    )
                                    .with_position((box_x - 6, box_y - 4))
                                    .with_duration(total_scene_duration)
                                    .with_start(cumulative_time)
                                )
                                if video_cross > 0:
                                    shadow = shadow.with_effects(
                                        [FadeIn(video_cross), FadeOut(video_cross)]
                                    )
                                all_clips.append(shadow)
                            except Exception as e:
                                print(f"[WARN] チャート影生成失敗: {e}")

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

                # immersive は「短いラベル」を維持しつつ、簡素すぎて品質が下がって見えないよう最大3行まで許容
                if use_immersive and len(formatted_lines) > 3:
                    print(
                        f"[WARN] immersive: on_screen_text を3行に制限（シーン{sc.get('scene', '?')}）"
                    )
                    formatted_lines = formatted_lines[:3]

                # ショートは「文字数で確実に折り返し」して横はみ出しを防ぐ
                if is_shorts:
                    # 常に16文字で折り返し（Shorts Bと完全に同一）
                    wrap_n = 16
                    wrapped = []
                    for ln in formatted_lines:
                        wrapped.append(_wrap_text_jp(ln, wrap_n))
                    summary_text = "\n".join(wrapped).strip()
                else:
                    # 横動画の折り返しロジック
                    is_with_image = bool(target_files)
                    if use_immersive:
                        wrap_n = 20
                    else:
                        initial_lines = len(formatted_lines)
                        if initial_lines > 6:
                            wrap_n = 40 if is_with_image else 36
                        else:
                            wrap_n = 30 if is_with_image else 23
                    
                    wrapped = []
                    for ln in formatted_lines:
                        wrapped.append(_wrap_text_jp(ln, wrap_n))
                    summary_text = "\n".join(wrapped).strip()
                
                # 画像がある場合は、画像の下に配置するためのサイズと座標を調整
                # 縦動画レイアウト
                if is_shorts:
                    # 【ショート動画：縦型レイアウト】
                    # テキスト枠は「画像の下端」からの相対位置（サイズは変更しない）
                    text_w = size[0] - 20
                    _gap_img_to_text = 10
                    if shorts_img_bottom_y is not None:
                        text_y_base = shorts_img_bottom_y + _gap_img_to_text
                    else:
                        _fallback_layout = _calculate_smart_layout(
                            max(1, len(target_files or [])),
                            size,
                            has_text=True,
                        )
                        if _fallback_layout:
                            text_y_base = _fallback_layout[0]["y"] + _fallback_layout[0]["h"] + _gap_img_to_text
                        else:
                            text_y_base = int(size[1] * 0.52)
                    text_h_max = int(size[1] * 0.25)
                    base_font_size = 36
                    frame_padding_h = 60
                    frame_offset_y = 25
                    frame_name = "main_frame.png"
                    
                    reduction_per_line = 4
                    text_offset_y = 0
                # 横動画レイアウト
                elif target_files:
                    if use_immersive:
                        # event_calendar 判定（表は画像主役）
                        section_title_str = str(sc.get("section_title", "") or "")
                        tf_names = [str(x).lower() for x in (target_files or [])]
                        is_event_calendar = (
                            ("イベントカレンダー" in section_title_str)
                            or ("event_calendar" in section_title_str.lower())
                            or any(("kessan_schedule" in n) or ("soukai_schedule" in n) for n in tf_names)
                        )
                        # event_calendar は表画像が主役なので、テキスト枠は控えめに
                        text_h_max = int(available_h * (0.22 if is_event_calendar else 0.32))
                        # 位置決めは classic を基準に揃える（ズレが出やすいため）
                        text_y_base = start_y + int(available_h * (0.79 if is_event_calendar else 0.70)) + margin
                        text_w = main_area_w - margin * 4
                        # 画像あり(チャート等)は枠が大きく見えやすいので、文字を少し大きめにする
                        base_font_size = 48 if is_event_calendar else 52
                        reduction_per_line = 3
                        # 短い2行でも枠が小さく見えないよう余白を確保する
                        frame_padding_h = 60 if is_event_calendar else 80
                    else:
                        text_h_max = int(available_h * 0.4)
                        text_y_base = start_y + int(available_h * 0.70) + margin - 10
                        text_w = main_area_w - margin * 4
                        base_font_size = 40
                        reduction_per_line = 4
                        frame_padding_h = -20
                    frame_offset_y = 30
                    # text_offset_y は「引く値」なので、値を大きくすると上に上がる。
                    # classic の見栄えが良いので、immersive も同等以上に「上寄せ」する。
                    # frame_padding_h を増やした場合、既存の上寄せだと文字が上に詰まりすぎて見える。
                    # 画像ありの immersive は少し下げて、枠内の視覚中心に寄せる。
                    text_offset_y = 15 if use_immersive else 50
                    frame_name = "main_frame.png"
                else:
                    if use_immersive:
                        text_h_max = int(available_h * 0.55)
                        # 位置決めは classic を基準に揃える（テキストのみが下にズレるため）
                        text_y_base = margin + 280
                        text_w = main_area_w - 100
                        base_font_size = 58
                        reduction_per_line = 4
                        frame_padding_h = 270
                    else:
                        text_h_max = int(available_h * 0.75)
                        text_y_base = margin + 280
                        text_w = main_area_w - 100
                        base_font_size = 54
                        reduction_per_line = 6
                        frame_padding_h = 270
                    frame_offset_y = 90
                    text_offset_y = -25
                    frame_name = "main_frame.png"

                # 行数に応じてフォントサイズを調整
                line_count = len(summary_text.split('\n'))
                if is_shorts:
                    # ショート動画：縦型用にフォントサイズを厳格に制御して枠内はみ出しを防ぐ
                    if line_count <= 3:
                        font_size = base_font_size
                    elif line_count == 4:
                        font_size = max(30, base_font_size - 6)
                    else:
                        font_size = max(26, base_font_size - 10)
                elif use_immersive:
                    if line_count <= 2:
                        font_size = min(56, base_font_size + 2)
                    elif line_count == 3:
                        font_size = min(54, base_font_size)
                    else:
                        font_size = max(36, base_font_size - 4)
                elif line_count > 6:
                    font_size = max(24, base_font_size - (line_count - 6) * reduction_per_line)
                else:
                    font_size = base_font_size

                label_color = "#1A237E"
                if use_immersive and formatted_lines:
                    immersive_sign = _immersive_price_change_sign(formatted_lines)
                    label_color = _label_text_color_for_immersive(
                        formatted_lines[0], change_sign=immersive_sign
                    )

                # --- immersive: 方法1（行ごとのTextClipで自前レイアウト） ---
                # ・captionは使わず、3行を固定座標で並べる
                # ・emphasis語を含む行だけ色＋短いフェード
                # emphasis は不安定になりやすいため無効化（表示/アニメしない）。
                # 以降は全モードで従来の caption で安定表示する。
                summary_text_for_layout = summary_text
                summary_clip = TextClip(
                    text=summary_text_for_layout,
                    font=font_to_use,
                    font_size=font_size,
                    color=label_color,
                    method="caption",
                    size=(text_w, text_h_max),
                    text_align="left",  # 左揃えに変更
                ).with_duration(total_scene_duration).with_start(cumulative_time)
                
                # テキストの高さに合わせて枠をリサイズ
                actual_text_h = summary_clip.h
                frame_path = images_dir / frame_name
                if frame_path.exists():
                    # 各ケースに最適化されたパディングを適用
                    if is_shorts:
                        m_frame = _load_frame_with_chromakey(frame_path, (text_w + 100, actual_text_h + frame_padding_h))
                        all_clips.append(
                            m_frame.with_position(("center", text_y_base - frame_offset_y))
                            .with_duration(total_scene_duration)
                            .with_start(cumulative_time)
                        )
                    else:
                        m_frame = _load_frame_with_chromakey(frame_path, (text_w + 275, actual_text_h + frame_padding_h))
                        # 各ケースに最適化されたオフセットで配置
                        all_clips.append(
                            m_frame.with_position((-100, text_y_base - frame_offset_y))
                            .with_duration(total_scene_duration)
                            .with_start(cumulative_time)
                        )

                # テキストの位置を調整
                if is_shorts:
                    summary_clip = summary_clip.with_position(("center", text_y_base))
                    shorts_text_bottom_y = (
                        (text_y_base - frame_offset_y) + actual_text_h + frame_padding_h
                    )
                else:
                    base_pos = (0, text_y_base - text_offset_y)
                    summary_clip = summary_clip.with_position(base_pos)
                if video_cross > 0:
                    summary_clip = summary_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(summary_clip)
            except Exception as e:
                print(f"[WARN] 要約テキスト生成失敗: {e}")

        # --- 4.5. immersive: ティッカー/社名カード（画像が無いニュースのフォールバック） ---
        # OG画像に頼らず「何の話か」を明確にして番組感を出す
        if (not is_shorts) and use_immersive and (not target_files):
            ticker = sc.get("ticker") or sc.get("related_ticker") or ""
            company = sc.get("company_name") or sc.get("related_company_name") or ""
            # Ticker は英数中心なので cp932 事故が少ないが、念のため安全化
            ticker = str(ticker).strip()
            company = str(company).strip()
            if ticker:
                try:
                    # タイトル枠と近すぎると詰まって見えるので、少し下げて余白を作る
                    plate_x = margin + 26
                    # タイトル枠の実サイズに追従して、常に下に余白を確保
                    base_top = top_reserved_h_for_scene if top_reserved_h_for_scene is not None else start_y
                    plate_y = max(start_y + 90, int(base_top) + 22)

                    # Ticker（大きく）
                    t_font = 92 if len(ticker) <= 6 else 82
                    t_clip = TextClip(
                        text=ticker[:10],
                        font=font_to_use,
                        font_size=t_font,
                        color="#1A237E",
                        method="label",
                        # label下切れ対策（タイトルと同様）
                        size=(None, int(t_font * 1.6)),
                    ).with_duration(total_scene_duration).with_start(cumulative_time)

                    # 会社名（Tickerの右に横並び）
                    c_clip = None
                    if company:
                        c_clip = TextClip(
                            text=(company[:27] + "…") if len(company) > 28 else company,
                            font=font_to_use,
                            font_size=50,
                            color="#4A2711",
                            method="label",
                            # label下切れ対策
                            size=(None, 64),
                        ).with_duration(total_scene_duration).with_start(cumulative_time)

                    pad_x = 22
                    pad_y = 16
                    gap_x = 40
                    content_w = int(t_clip.w) + (gap_x + int(c_clip.w) if c_clip else 0)
                    content_h = max(int(t_clip.h), int(c_clip.h) if c_clip else 0)

                    plate_w = min(760, max(420, content_w + pad_x * 2))
                    plate_h = max(104, content_h + pad_y * 2)

                    plate = (
                        _rounded_plate_clip((plate_w, plate_h), radius=28, color=(255, 255, 255), alpha=210)
                        .with_position((plate_x, plate_y))
                        .with_duration(total_scene_duration)
                        .with_start(cumulative_time)
                    )
                    if video_cross > 0:
                        plate = plate.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                    all_clips.append(plate)

                    # ベースラインっぽく揃える（tickerの方が大きいので会社名は少しだけ下げる）
                    tx = plate_x + pad_x
                    ty = plate_y + (plate_h - int(t_clip.h)) // 2 - 30
                    t_clip = t_clip.with_position((tx, ty))
                    all_clips.append(t_clip)

                    if c_clip:
                        cx = tx + int(t_clip.w) + gap_x
                        cy = plate_y + (plate_h - int(c_clip.h)) // 2 - 10
                        c_clip = c_clip.with_position((cx, cy))
                        all_clips.append(c_clip)
                except Exception as e:
                    print(f"[WARN] ティッカーカード生成失敗: {e}")

        # --- 4.6. immersive: 強調ワード（旧: 左上に浮かせる表示） ---
        # 案Aでは「要約枠内に統合」するため、ここでの単独表示は行わない。

        # --- 5. キャラクターレイヤー（感情別画像 + セグメントタイミングでアニメ） ---
        if sc.get("section_title") != "subscribe":
            scene_emotion = normalize_emotion(sc.get("emotion"))
            segments_for_char = sc.get("segments") or []
            if segments_for_char:
                assign_segment_emotions(sc)
            try:
                if is_shorts:
                    char_h = int(size[1] * 0.25)
                    char_max_w = None
                    if on_screen_text:
                        char_x = 30
                        _gap_text_to_char = -70
                        char_y_placeholder = (
                            shorts_text_bottom_y + _gap_text_to_char
                            if shorts_text_bottom_y is not None
                            else size[1] - int(size[1] * 0.25) - 170
                        )
                    else:
                        char_x = 30
                        char_y_placeholder = size[1] - int(size[1] * 0.25) - 170
                    beats = (
                        merge_emotion_beats_for_scene(
                            segments_for_char, scene_emotion, total_scene_duration
                        )
                        if segments_for_char
                        else [(0.0, total_scene_duration, scene_emotion)]
                    )
                    for rel_start, beat_dur, beat_emotion in beats:
                        beat_path = _asset_for_emotion(images_dir, beat_emotion, is_shorts=True)
                        if not beat_path:
                            continue
                        with Image.open(str(beat_path)) as img:
                            img_rgba = img.convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
                            char_clip = ImageClip(np.array(img_rgba)).resized(height=char_h)
                        char_y = char_y_placeholder
                        if on_screen_text and shorts_text_bottom_y is not None:
                            char_y = shorts_text_bottom_y + _gap_text_to_char
                        else:
                            char_y = size[1] - char_clip.h - 170
                        char_clip = char_clip.with_duration(beat_dur).with_start(cumulative_time + rel_start)
                        char_clip = apply_emotion_motion(char_clip, beat_emotion, char_x, char_y)
                        if video_cross > 0:
                            char_clip = char_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        all_clips.append(char_clip)
                elif sc.get("visual_template") == "bridge":
                    char_path = images_dir / "mini.png"
                    if char_path.exists():
                        char_h = int(size[1] * 0.42)
                        with Image.open(str(char_path)) as img:
                            char_clip = ImageClip(np.array(img.convert("RGBA"))).resized(height=char_h)
                        pad_x, pad_y = 120, 70
                        char_x = size[0] - char_clip.w - pad_x
                        char_y = size[1] - char_clip.h - pad_y
                        char_clip = (
                            char_clip.with_duration(total_scene_duration)
                            .with_start(cumulative_time)
                        )
                        char_clip = apply_emotion_motion(char_clip, scene_emotion, char_x, char_y)
                        if video_cross > 0:
                            char_clip = char_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        all_clips.append(char_clip)
                else:
                    char_max_w = int(size[0] * 0.25)
                    char_h = int(size[1] * 0.7)
                    beats = (
                        merge_emotion_beats_for_scene(
                            segments_for_char, scene_emotion, total_scene_duration
                        )
                        if segments_for_char
                        else [(0.0, total_scene_duration, scene_emotion)]
                    )
                    for rel_start, beat_dur, beat_emotion in beats:
                        beat_path = _asset_for_emotion(images_dir, beat_emotion, is_shorts=False)
                        if not beat_path:
                            continue
                        with Image.open(str(beat_path)) as img:
                            char_clip = ImageClip(np.array(img.convert("RGBA"))).resized(height=char_h)
                        if char_clip.w > char_max_w:
                            char_clip = char_clip.resized(width=char_max_w)
                        char_x = size[0] - char_clip.w - 10
                        char_y = size[1] - char_clip.h
                        char_clip = char_clip.with_duration(beat_dur).with_start(cumulative_time + rel_start)
                        char_clip = apply_emotion_motion(char_clip, beat_emotion, char_x, char_y)
                        if video_cross > 0:
                            char_clip = char_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        all_clips.append(char_clip)
            except Exception as e:
                print(f"⚠️ キャラクター表示失敗: {e}")

        # --- 6. 字幕レイヤー (telop_frame.png 背面) ---
        segments = sc.get("segments", [])
        # ショートまたは show_subtitles=False では字幕（segments）を表示しない
        if (not is_shorts) and show_subtitles and segments and sc.get("section_title") != "subscribe":
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
            # 画面確認用のドラフトでは重いのでスキップ
            draft = os.getenv("DRAFT_RENDER", "").strip().lower() in ("1", "true", "yes")
            if draft:
                cumulative_time += total_scene_duration
                continue
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
                    print(f"[Movie] 登録アニメーションを配置: {anim_duration}s (start={cumulative_time})")
                except Exception as e:
                    print(f"[WARN] アニメーション合成失敗: {e}")
            else:
                print(f"[WARN] アニメーションファイルが見つかりません: {anim_path}")

        cumulative_time += total_scene_duration

    final = CompositeVideoClip(all_clips, size=size).with_duration(cumulative_time)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 画質改善: bitrate と CRF を指定（ショートで「ボケる」問題が出やすい）
    is_shorts_output = size[0] < size[1]
    bitrate = "12000k" if is_shorts_output else "9000k"
    # 開発用の高速プレビュー（確認を早く回す）
    draft = os.getenv("DRAFT_RENDER", "").strip().lower() in ("1", "true", "yes")
    if draft:
        bitrate = "2500k" if is_shorts_output else "2200k"
        ffmpeg_params = ["-crf", "28", "-preset", "ultrafast"]
    else:
        ffmpeg_params = ["-crf", "18", "-preset", "slow"]
    logger = "bar" if draft else None
    final.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio=False,
        bitrate=bitrate,
        ffmpeg_params=ffmpeg_params,
        threads=max(1, (os.cpu_count() or 2) - 1),
        logger=logger,
    )
    return str(out_path)
