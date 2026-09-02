from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os
import re
import unicodedata
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.config.presentation import is_immersive_mode, normalize_presentation_mode
from src.config.studio_soft import (
    STUDIO_SOFT,
    ink_color,
    speaker_subtitle_color,
    immersive_content_box,
    immersive_char_band,
    immersive_telop_box,
    immersive_density_score,
)
from src.video_generation.character_emotion import (
    assign_segment_emotions,
    apply_emotion_motion,
    merge_speaker_emotion_beats_for_scene,
    normalize_emotion,
)
from src.config.characters import get_character_image_name
from src.analysis.dialogue_util import primary_speaker_for_scene

from moviepy import (
    ImageClip,
    TextClip,
    CompositeVideoClip,
    ColorClip,
    VideoFileClip
)
# v2.0系でのエフェクトクラス
from moviepy.video.fx import FadeIn, FadeOut, MaskColor

def _resolve_jp_font_path(font_path: Optional[str] = None) -> Optional[str]:
    if font_path and Path(font_path).exists():
        return font_path
    here = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    for name in (
        "SourceHanSans-Heavy.otf",
        "MPLUS1-Bold.ttf",
        "NotoSansJP-Regular.ttf",
        "NotoSansJP-Regular.otf",
    ):
        p = here / name
        if p.exists():
            return str(p)
    for p in (
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("C:/Windows/Fonts/YuGothB.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ):
        if p.exists():
            return str(p)
    return None


def _pil_font(font_path: Optional[str], size: int):
    fp = _resolve_jp_font_path(font_path)
    if fp:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _rgba_image_clip(
    img: Image.Image,
    *,
    duration: float,
    start: float = 0.0,
) -> ImageClip:
    """RGBA を MoviePy ImageClip(+mask) に変換。"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.array(img)
    rgb = ImageClip(arr[:, :, :3]).with_duration(duration).with_start(start)
    mask = (
        ImageClip(arr[:, :, 3].astype("float") / 255.0, is_mask=True)
        .with_duration(duration)
        .with_start(start)
    )
    return rgb.with_mask(mask)


def _draw_cream_rounded_band(
    size: Tuple[int, int],
    *,
    radius: int = 22,
    cream_alpha: Optional[int] = None,
    stage: bool = False,
) -> Image.Image:
    """影つきクリーム帯の RGBA 画像。stage=True で背景と区別しやすい下地。"""
    w, h = size
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    outline = STUDIO_SOFT.get("panel_outline", (*blue, 170))
    if cream_alpha is None:
        cream_alpha = int(STUDIO_SOFT.get("panel_cream_alpha", 248))
    shadow_a = int(STUDIO_SOFT.get("panel_shadow_alpha", 56))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        (5, 8, w - 1, h - 1),
        radius=radius,
        fill=(44, 36, 32, shadow_a + (18 if stage else 0)),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=12 if stage else 9))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, w - 5, h - 7),
        radius=radius,
        fill=(*cream, int(cream_alpha)),
        outline=(outline if isinstance(outline, tuple) else (*blue, 200)),
        width=3 if stage else 2,
    )
    return img


def _make_immersive_scrim_clip(
    size: Tuple[int, int],
    *,
    duration: float,
    start: float,
) -> ImageClip:
    """
    背景と前面の差をつけるソフト暗幕＋ビネット。
    背景を白く薄めるのではなく、手前にピントが来るようにする。
    """
    w, h = size
    overall = int(STUDIO_SOFT.get("scrim_overall_alpha", 28))
    vmax = int(STUDIO_SOFT.get("scrim_vignette_alpha", 58))
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    # 端を少し落とす（中央コンテンツは相対的に浮く）
    dx = (xs - 0.5) / 0.62
    dy = (ys - 0.45) / 0.78
    d = np.sqrt(dx * dx + dy * dy)
    vignette = np.clip((d - 0.42) / 0.75, 0.0, 1.0) * float(vmax)
    # メイン帯の背後だけごく薄いインク（クリーム枠の下地）
    band = np.clip((ys - 0.10) * (0.78 - ys) * 4.2, 0.0, 1.0) * 8.0
    alpha = np.clip(overall + vignette + band, 0, 70).astype(np.uint8)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 0] = 36
    rgba[:, :, 1] = 30
    rgba[:, :, 2] = 28
    rgba[:, :, 3] = alpha
    return _rgba_image_clip(Image.fromarray(rgba, "RGBA"), duration=duration, start=start)


def _rounded_plate_clip(size: Tuple[int, int], *, radius: int = 26, color=(255, 255, 255), alpha: int = 210) -> ImageClip:
    """半透明の角丸プレート（tickerカード等）"""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = (int(color[0]), int(color[1]), int(color[2]), int(alpha))
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill, outline=(255, 255, 255, 140), width=2)
    return _rgba_image_clip(img, duration=1.0, start=0.0)


def _studio_soft_band_clip(size: Tuple[int, int], *, radius: Optional[int] = None) -> ImageClip:
    """枠レス寄りのクリーム情報帯（Studio Soft）。細い装飾枠は付けない。"""
    radius = int(radius if radius is not None else STUDIO_SOFT["band_radius"])
    img = _draw_cream_rounded_band(size, radius=radius)
    return _rgba_image_clip(img, duration=1.0, start=0.0)


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


def _wrap_text_to_px(
    text: str,
    font: ImageFont.ImageFont,
    max_px: int,
    *,
    max_lines: int = 2,
    ellipsis: bool = True,
) -> List[str]:
    """実ピクセル幅で折り返す（全角幅の見積もり誤差で見切れないようにする）。"""
    pages, _leftover = _paginate_text_px(
        text, font, max_px, max_lines=max_lines, ellipsis=ellipsis
    )
    return pages[0] if pages else [" "]


def _paginate_text_px(
    text: str,
    font: ImageFont.ImageFont,
    max_px: int,
    *,
    max_lines: int = 2,
    ellipsis: bool = True,
) -> Tuple[List[List[str]], str]:
    """2行ページに分割。ellipsis=False なら余りは次ページへ（省略しない）。"""
    remaining = str(text or "").strip()
    if not remaining:
        return [[" "]], ""
    tmp = Image.new("RGBA", (8, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)

    def _w(s: str) -> int:
        bb = td.textbbox((0, 0), s, font=font)
        return bb[2] - bb[0]

    def _break_at(src: str) -> int:
        if _w(src) <= max_px:
            return len(src)
        lo, hi, best = 1, len(src), 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if _w(src[:mid]) <= max_px:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        # 句読点優先だが、行が短すぎる位置では切らない（「みのりさん、」だけで終わらない）
        # カタカナなどの単語境界まで安全に戻れるよう、min_keep を少し緩める
        min_keep = max(1, int(best * 0.30))
        n = best
        for i in range(best, min_keep, -1):
            if src[i - 1] in "。、．，,!！?？ ":
                if _w(src[:i]) <= max_px:
                    n = i
                    break
        # カタカナ語の途中で切らない。次行が「ィ」「ー」で始まらないよう調整。
        def _is_kata(ch: str) -> bool:
            o = ord(ch)
            return ch == "ー" or 0x30A1 <= o <= 0x30FA

        if 0 < n < len(src) and _is_kata(src[n]) and _is_kata(src[n - 1]):
            s = n
            while s > 0 and _is_kata(src[s - 1]):
                s -= 1
            e = n
            while e < len(src) and _is_kata(src[e]):
                e += 1
            if _w(src[:e]) <= max_px:
                n = e
            elif s >= min_keep and _w(src[s:e]) <= max_px:
                n = s
        no_start = set("ァィゥェォャュョッぁぃぅぇぉゃゅょっー、。．，,)]）】」』")
        while n < len(src) and n > 1 and src[n] in no_start:
            if _w(src[: n + 1]) <= max_px:
                n += 1
            else:
                while n > 1 and n < len(src) and src[n] in no_start:
                    n -= 1
                break
        # 次行が1文字だけにならない（本格加|速 を防ぐ）
        if 0 < len(src) - n == 1:
            if _w(src) <= max_px:
                n = len(src)
            else:
                n = max(min_keep, n - 1)
        return max(1, n)

    pages: List[List[str]] = []
    while remaining:
        lines: List[str] = []
        for _ in range(max_lines):
            if not remaining:
                break
            n = _break_at(remaining)
            if n >= len(remaining):
                lines.append(remaining)
                remaining = ""
                break
            last_slot = len(lines) == max_lines - 1
            if last_slot and ellipsis:
                chunk = remaining[:n]
                while chunk and _w(chunk + "…") > max_px:
                    chunk = chunk[:-1]
                lines.append((chunk + "…") if chunk else "…")
                remaining = ""
                break
            lines.append(remaining[:n])
            remaining = remaining[n:].lstrip()
        if lines:
            pages.append(lines)
        else:
            break
        if ellipsis:
            break
    return pages or [[" "]], remaining


def _caption_font_size(screen_h: int) -> int:
    """720p で 40、1080p で 48。"""
    return max(40, min(48, int(round(screen_h * 0.044))))


def _is_opening_scene(sc: dict) -> bool:
    sec = str(sc.get("section_title") or "")
    return ("opening" in sec.lower()) or ("トピック" in sec)


def _parse_opening_topic_line(line: str) -> Tuple[str, str]:
    """「・東京市場：円高警戒」→ (タグ, 本文)。"""
    s = str(line or "").strip().lstrip("・•").strip()
    for sep in ("：", ":"):
        if sep in s:
            tag, body = s.split(sep, 1)
            return tag.strip()[:8], body.strip()
    return "トピック", s


def _opening_tag_color(tag: str) -> Tuple[int, int, int]:
    t = str(tag or "").strip()
    palette = {
        "東京市場": (47, 78, 122),
        "市場": (47, 78, 122),
        "米国": (47, 78, 122),
        "注目": (196, 78, 88),
        "材料": (70, 150, 110),
        "セクター": (120, 90, 170),
        "今夜": (70, 110, 150),
        "チェック": (200, 130, 55),
    }
    for key, rgb in palette.items():
        if key in t:
            return rgb
    return STUDIO_SOFT["soft_blue"]  # type: ignore[return-value]


def _is_spoken_filler_line(text: str) -> bool:
    """挨拶・読み上げ専用行は画面テキスト（OST）に混ぜない。"""
    t = str(text or "").strip()
    if len(t) < 6:
        return True
    markers = (
        "おはよう",
        "こんばんは",
        "お疲れ",
        "マイカブ",
        "みのり",
        "株野",
        "カリン",
        "皆さん",
        "よろしく",
        "それでは",
        "いってらっしゃい",
        "チャンネル登録",
    )
    return any(m in t for m in markers)


def _path_looks_like_chart(path_str: str, sc: dict) -> bool:
    """チャートPNGか（図解は除外）。"""
    if _is_studio_diagram_path(path_str):
        return False
    name = str(path_str or "").lower().replace("\\", "/")
    img_type = str(sc.get("image_type", "") or "")
    return (
        img_type.startswith("chart")
        or "chart" in name
        or "stock_charts" in name
        or "market_charts" in name
    )


def _is_studio_diagram_path(path_str: str) -> bool:
    name = str(path_str or "").lower().replace("\\", "/")
    return any(
        k in name
        for k in (
            "/diagrams/",
            "news_bundle",
            "impact_flow",
            "market_board",
            "capital_flow",
            "checklist",
        )
    )


def _lines_have_category_markers(lines: List[str]) -> bool:
    """「・市場：…」形式の行があるか。"""
    for ln in lines:
        s = str(ln).strip().lstrip("・•")
        if "：" in s:
            return True
        if ":" in s and not s.lower().startswith("http"):
            return True
    return False


def _densify_on_screen_lines(
    sc: dict,
    *,
    min_lines: int = 3,
    max_lines: int = 5,
) -> List[str]:
    """文字中心シーンの OST を最低行数まで補完（画面が寂しくならないように）。"""
    raw = sc.get("on_screen_text") or []
    if isinstance(raw, str):
        raw = [raw]
    lines: List[str] = []
    for t in raw:
        s = str(t).strip()
        if s and s not in lines and not _is_spoken_filler_line(s):
            lines.append(s)
    if len(lines) >= min_lines:
        return lines[:max_lines]

    extras: List[str] = []
    # 読み上げ文・字幕(segments)は OST に混ぜない（挨拶が画面に出るのを防ぐ）
    company = str(sc.get("company_name") or sc.get("related_company_name") or "").strip()
    ticker = str(sc.get("ticker") or sc.get("related_ticker") or "").strip()
    if company:
        extras.append(f"{company}の材料を確認")
    if ticker:
        extras.append(f"{ticker} の値動きに注意")
    extras.extend(
        [
            "地合いと切り分けて見る",
            "関連セクターの波及を確認",
            "寄り付きの反応を要チェック",
            "個別より選別の姿勢を維持",
            "指数とニュースの整合を確認",
        ]
    )
    for ex in extras:
        if len(lines) >= min_lines:
            break
        if ex and ex not in lines and not _is_spoken_filler_line(ex):
            lines.append(ex)
    return lines[:max_lines]


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


def _render_title_pill_clip(
    section_title: str,
    *,
    font_path: Optional[str],
    max_width: int,
    duration: float,
    start: float,
    scale: float = 1.0,
) -> Tuple[ImageClip, int, int]:
    """
    タイトルピルをPillowで一体生成（枠と文字の垂直ずれを防ぐ）。
    scale<1 で情報量が多いシーン向けにコンパクト化。
    returns: (clip, width, height)
    """
    ink = ink_color()
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    s = max(0.62, min(1.0, float(scale)))
    pad_x, pad_y = int(56 * s), int(18 * s)
    display = section_title
    font_size = max(36, int(56 * s))
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    inner_max = max_width - int(pad_x * 2) - 48
    font = _pil_font(font_path, font_size)
    wrap_units = max(8, inner_max // max(1, font_size // 2))

    def _title_lines_for_size(fs: int) -> List[str]:
        f = _pil_font(font_path, fs)
        wrapped = _wrap_text_jp(display, wrap_units)
        lines = [ln for ln in wrapped.split("\n") if ln.strip()]
        if len(lines) > 2:
            lines = lines[:2]
            if lines[-1]:
                lines[-1] = lines[-1][: max(6, len(lines[-1]) - 1)] + "…"
        return lines or [display[:20]]

    title_lines = _title_lines_for_size(font_size)
    min_fs = max(30, int(34 * s))
    metrics = []
    while font_size >= min_fs:
        font = _pil_font(font_path, font_size)
        title_lines = _title_lines_for_size(font_size)
        metrics = []
        max_tw = 0
        total_th = 0
        for i, ln in enumerate(title_lines):
            bb = td.textbbox((0, 0), ln, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            metrics.append((ln, bb, tw, th))
            max_tw = max(max_tw, tw)
            total_th += th
            if i:
                total_th += 6
        if max_tw + pad_x * 2 + 48 <= max_width:
            break
        font_size -= 2
    tw = max(m[2] for m in metrics)
    th = total_th

    w = min(max_width, tw + pad_x * 2 + 48)
    h = max(int(84 * s), th + pad_y * 2)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (5, 8, w - 2, h - 2),
        radius=max(20, h // 2),
        fill=(44, 36, 32, int(STUDIO_SOFT.get("panel_shadow_alpha", 72))),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    outline = STUDIO_SOFT.get("panel_outline", (*blue, 200))
    draw.rounded_rectangle(
        (2, 2, w - 7, h - 6),
        radius=max(18, (h - 8) // 2),
        fill=(*cream, int(STUDIO_SOFT.get("panel_cream_alpha", 250))),
        outline=outline if isinstance(outline, tuple) else (*blue, 200),
        width=3,
    )
    box_top, box_bottom = 2, h - 6
    cy = (box_top + box_bottom) // 2 - 1
    draw.ellipse((22, cy - 8, 40, cy + 8), fill=(*blue, 255))
    tx = 56 + tw // 2
    y_cursor = cy - th // 2
    for i, (ln, bb, _ltw, lth) in enumerate(metrics):
        try:
            draw.text((tx, y_cursor + lth // 2), ln, font=font, fill=(*ink, 255), anchor="mm")
        except TypeError:
            draw.text((56, y_cursor - bb[1]), ln, font=font, fill=(*ink, 255))
        y_cursor += lth + (6 if i < len(metrics) - 1 else 0)

    clip = _rgba_image_clip(img, duration=duration, start=start)
    return clip, w, h


def _render_summary_band_clip(
    lines: List[str],
    *,
    font_path: Optional[str],
    max_width: int,
    fill_rgb: Tuple[int, int, int],
    duration: float,
    start: float,
    font_size: int = 42,
    force_width: Optional[int] = None,
    pad_y: int = 22,
    min_height: int = 0,
    align: str = "center",
    pad_x: int = 36,
) -> Tuple[ImageClip, int, int]:
    """要約帯を Pillow 一体描画（枠内垂直中央）。帯幅は max_width を超えない。"""
    clean = [str(x).strip() for x in lines if str(x).strip()]
    if not clean:
        clean = [" "]
    font = _pil_font(font_path, font_size)
    line_gap = max(6, font_size // 6)
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    metrics = []
    max_tw = 0
    total_th = 0
    for i, ln in enumerate(clean):
        bb = td.textbbox((0, 0), ln, font=font)
        tw = bb[2] - bb[0]
        th = bb[3] - bb[1]
        metrics.append((ln, bb, tw, th))
        max_tw = max(max_tw, tw)
        total_th += th
        if i:
            total_th += line_gap

    pad_x, pad_y = int(pad_x), int(pad_y)
    content_w = max(280, max_tw + pad_x * 2)
    if force_width is not None:
        w = min(int(max_width), max(280, int(force_width)))
    else:
        w = min(int(max_width), content_w)
    h = max(76, int(min_height or 0), total_th + pad_y * 2)
    img = _draw_cream_rounded_band(
        (w, h),
        radius=22,
        cream_alpha=int(STUDIO_SOFT.get("panel_cream_alpha", 250)),
        stage=True,
    )
    draw = ImageDraw.Draw(img)
    usable_h = h - 7
    usable_w = w - 5
    y_cursor = (usable_h - total_th) // 2
    for i, (ln, bb, tw, th) in enumerate(metrics):
        cy = y_cursor + th // 2
        if align == "left":
            x = pad_x
            try:
                draw.text((x, cy), ln, font=font, fill=(*fill_rgb, 255), anchor="lm")
            except TypeError:
                draw.text((x, y_cursor - bb[1]), ln, font=font, fill=(*fill_rgb, 255))
        else:
            cx = usable_w // 2
            try:
                draw.text((cx, cy), ln, font=font, fill=(*fill_rgb, 255), anchor="mm")
            except TypeError:
                draw.text((cx - tw // 2, y_cursor - bb[1]), ln, font=font, fill=(*fill_rgb, 255))
        y_cursor += th + (line_gap if i < len(metrics) - 1 else 0)

    return _rgba_image_clip(img, duration=duration, start=start), w, h


def _render_caption_band_clip(
    text: str,
    *,
    font_path: Optional[str],
    max_width: int,
    fill_rgb: Tuple[int, int, int],
    duration: float,
    start: float,
    font_size: int = 36,
    lines: Optional[List[str]] = None,
) -> Tuple[ImageClip, int, int]:
    """話者色つき字幕帯。キャラ間幅いっぱいにし、常に2行分の縦を確保する。"""
    font = _pil_font(font_path, font_size)
    text_max_px = max(80, int(max_width) - 80)
    if lines is None:
        lines = _wrap_text_to_px(
            str(text or "").strip(),
            font,
            text_max_px,
            max_lines=2,
            ellipsis=False,
        )
    line_gap = max(8, font_size // 5)
    tmp = Image.new("RGBA", (8, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    line_hs = []
    for ln in lines:
        bb = td.textbbox((0, 0), ln, font=font)
        line_hs.append(bb[3] - bb[1])
    while len(line_hs) < 2:
        line_hs.append(int(font_size * 1.35))
    pad_y = 28
    two_line_h = pad_y * 2 + sum(line_hs[:2]) + line_gap + 14
    return _render_summary_band_clip(
        lines,
        font_path=font_path,
        max_width=max_width,
        fill_rgb=fill_rgb,
        duration=duration,
        start=start,
        font_size=font_size,
        force_width=int(max_width),
        pad_y=pad_y,
        min_height=two_line_h,
    )

def _asset_for_emotion(
    assets_dir: Path,
    emotion: str,
    is_shorts: bool = False,
    speaker: str = "minori",
) -> Optional[Path]:
    """話者ごとの立ち絵。カリンは characters.json の images を優先。"""
    sp = (speaker or "minori").strip().lower()
    if sp == "karin":
        named = get_character_image_name("karin", emotion)
        if named:
            p = assets_dir / named
            if p.exists():
                return p
            # emotion 専用が無くても normal にフォールバック済みのはずだが念のため
            p_n = assets_dir / (get_character_image_name("karin", "normal") or "")
            if p_n.exists():
                return p_n
    if is_shorts:
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


def _load_rgba_image_clip(path: Path) -> ImageClip:
    """PNG（透過含む）を ImageClip(+mask) として読む。"""
    with Image.open(str(path)) as img:
        img = img.convert("RGBA")
        arr = np.array(img)
    rgb = ImageClip(arr[:, :, :3])
    mask = ImageClip(arr[:, :, 3].astype("float") / 255.0, is_mask=True)
    return rgb.with_mask(mask)


def _render_opening_topics_clip(
    *,
    lines: List[str],
    font_path: Optional[str],
    max_width: int,
    duration: float,
    start: float,
) -> Tuple[ImageClip, int, int]:
    """opening「本日のトピック」専用。カテゴリタグ付きで視認性を上げる。"""
    clean_lines = [str(x).strip() for x in lines if str(x).strip()][:5]
    ink = ink_color()
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    tag_font = _pil_font(font_path, 32)
    body_font = _pil_font(font_path, 46)

    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)

    def _m(text: str, font) -> Tuple[int, int, Tuple[int, int, int, int]]:
        bb = td.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1], bb

    pad_x, pad_y = 44, 42
    tag_w = 172
    tag_pad_x, tag_pad_y = 16, 12
    row_gap = 20
    body_x = pad_x + tag_w + 20
    wrap_w = max(260, int(max_width) - body_x - pad_x)

    rows: List[Tuple[str, str, List[str], int]] = []
    total_h = pad_y
    max_body_w = 0
    for ln in clean_lines:
        tag, body = _parse_opening_topic_line(ln)
        wrapped = _wrap_text_to_px(body, body_font, wrap_w, max_lines=2, ellipsis=False)
        block_h = 0
        for wln in wrapped:
            _, lh, _ = _m(wln, body_font)
            block_h += lh + 6
        if wrapped:
            block_h -= 6
        _, tag_h, _ = _m(tag[:8], tag_font)
        row_h = max(tag_h + tag_pad_y * 2, block_h, 56)
        rows.append((tag, body, wrapped, row_h))
        max_body_w = max(max_body_w, wrap_w)
        total_h += row_h + row_gap
    if rows:
        total_h -= row_gap
    total_h += pad_y

    w = int(max_width)
    h = max(360, total_h)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (6, 10, w - 2, h - 2),
        radius=30,
        fill=(44, 36, 32, int(STUDIO_SOFT.get("panel_shadow_alpha", 72))),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    outline = STUDIO_SOFT.get("panel_outline", (*blue, 200))
    draw.rounded_rectangle(
        (2, 2, w - 6, h - 6),
        radius=28,
        fill=(*cream, int(STUDIO_SOFT.get("panel_cream_alpha", 250))),
        outline=outline if isinstance(outline, tuple) else (*blue, 200),
        width=3,
    )
    draw.rounded_rectangle(
        (2, 2, 14, h - 6),
        radius=8,
        fill=(*blue, 220),
    )

    y = pad_y
    for tag, _body, wrapped, row_h in rows:
        tag_rgb = _opening_tag_color(tag)
        pill_h = max(52, row_h - 4)
        draw.rounded_rectangle(
            (pad_x, y + (row_h - pill_h) // 2, pad_x + tag_w, y + (row_h - pill_h) // 2 + pill_h),
            radius=16,
            fill=(*tag_rgb, 255),
        )
        _, tag_h, tag_bb = _m(tag[:8], tag_font)
        tag_cy = y + row_h // 2
        try:
            draw.text(
                (pad_x + tag_w // 2, tag_cy),
                tag[:8],
                font=tag_font,
                fill=(255, 255, 255, 255),
                anchor="mm",
            )
        except TypeError:
            draw.text(
                (pad_x + tag_pad_x, tag_cy - tag_h // 2 - tag_bb[1]),
                tag[:8],
                font=tag_font,
                fill=(255, 255, 255, 255),
            )

        text_y = y + max(0, (row_h - sum(_m(wln, body_font)[1] + 6 for wln in wrapped) + 6) // 2)
        for wln in wrapped:
            _, lh, bb = _m(wln, body_font)
            try:
                draw.text((body_x, text_y + lh // 2), wln, font=body_font, fill=(*ink, 255), anchor="lm")
            except TypeError:
                draw.text((body_x, text_y - bb[1]), wln, font=body_font, fill=(*ink, 255))
            text_y += lh + 6
        y += row_h + row_gap

    return _rgba_image_clip(img, duration=duration, start=start), w, h


def _render_news_focus_clip(
    *,
    ticker: str,
    company: str,
    lines: List[str],
    font_path: Optional[str],
    max_width: int,
    duration: float,
    start: float,
    min_height: int = 420,
) -> Tuple[ImageClip, int, int]:
    """チャート無しニュース向けの中央フォーカスカード（余白埋め）。"""
    clean_lines = [str(x).strip() for x in lines if str(x).strip()][:6]
    ink = ink_color()
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    ticker_font = _pil_font(font_path, 88)
    company_font = _pil_font(font_path, 42)
    # チャート無しの箇条書きは opening 並みの視認性を確保
    body_font = _pil_font(font_path, 46 if not ticker else 40)

    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)

    def _m(text: str, font) -> Tuple[int, int, Tuple[int, int, int, int]]:
        bb = td.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1], bb

    pad_x, pad_y = 48, 36
    company_disp = company[:36] + ("…" if len(company) > 36 else "")
    tw, th, _ = _m(ticker[:10] or "NEWS", ticker_font) if ticker else (0, 0, (0, 0, 0, 0))
    cw, ch, _ = _m(company_disp, company_font) if company_disp else (0, 0, (0, 0, 0, 0))
    wrap_w = max(280, int(max_width) - pad_x * 2)
    inner_line_gap = 6
    bullet_item_gap = 20
    bullet_blocks: List[List[Tuple[str, int, int, Tuple[int, int, int, int]]]] = []
    max_line_w = 0
    lines_h = 0
    for ln in clean_lines:
        disp = ln if ln.startswith("・") or ln.startswith("•") else f"・{ln}"
        wrapped = _wrap_text_to_px(disp, body_font, wrap_w, max_lines=2, ellipsis=False)
        block = []
        for i, wln in enumerate(wrapped):
            if i > 0 and not wln.startswith("　"):
                wln = "　" + wln
            lw, lh, bb = _m(wln, body_font)
            block.append((wln, lw, lh, bb))
            max_line_w = max(max_line_w, lw)
            lines_h += lh + inner_line_gap
        if block:
            lines_h -= inner_line_gap
            lines_h += bullet_item_gap
            bullet_blocks.append(block)
    if lines_h:
        lines_h -= bullet_item_gap

    header_w = tw + (28 + cw if company_disp else 0)
    inner_w = max(header_w, max_line_w)
    if ticker:
        w = int(max_width)
    else:
        w = int(min(max_width, max(inner_w + pad_x * 2 + 64, 540)))
    content_h = pad_y * 2 + max(th, ch, 1) + (36 + lines_h if bullet_blocks else 0)
    h = max(content_h, 240 if ticker else 200)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (6, 10, w - 2, h - 2),
        radius=28,
        fill=(44, 36, 32, int(STUDIO_SOFT.get("panel_shadow_alpha", 72))),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    outline = STUDIO_SOFT.get("panel_outline", (*blue, 200))
    draw.rounded_rectangle(
        (2, 2, w - 6, h - 6),
        radius=26,
        fill=(*cream, int(STUDIO_SOFT.get("panel_cream_alpha", 250))),
        outline=outline if isinstance(outline, tuple) else (*blue, 200),
        width=3,
    )

    # 中身は上から詰める
    y = pad_y
    if ticker:
        pill_pad_x, pill_pad_y = 28, 18
        pill_w = tw + pill_pad_x * 2
        pill_h = max(th + pill_pad_y * 2, 72)
        draw.rounded_rectangle(
            (pad_x, y, pad_x + pill_w, y + pill_h),
            radius=18,
            fill=(255, 255, 255, 255),
            outline=(*blue, 180),
            width=3,
        )
        cx = pad_x + pill_w / 2
        cy = y + pill_h / 2 - 2
        try:
            draw.text((cx, cy), ticker[:10], font=ticker_font, fill=(26, 35, 126, 255), anchor="mm")
        except TypeError:
            draw.text(
                (pad_x + pill_pad_x, y + (pill_h - th) // 2),
                ticker[:10],
                font=ticker_font,
                fill=(26, 35, 126, 255),
            )
        if company_disp:
            draw.text(
                (pad_x + pill_w + 20, y + (pill_h - ch) // 2),
                company_disp,
                font=company_font,
                fill=(*ink, 255),
            )
        y += max(pill_h, ch) + 28
    elif company_disp:
        draw.text((pad_x, y), company_disp, font=company_font, fill=(*ink, 255))
        y += ch + 28

    for bi, block in enumerate(bullet_blocks):
        for ln, lw, lh, bb in block:
            try:
                draw.text((pad_x, y + lh / 2), ln, font=body_font, fill=(*ink, 255), anchor="lm")
            except TypeError:
                draw.text((pad_x, y - bb[1]), ln, font=body_font, fill=(*ink, 255))
            y += lh + inner_line_gap
        y -= inner_line_gap
        if bi < len(bullet_blocks) - 1:
            y += bullet_item_gap

    return _rgba_image_clip(img, duration=duration, start=start), w, h


def _split_section_title(section_title: str) -> Tuple[str, str]:
    """「米国セクター分析：買われたハイテク」→ (左, 右)。"""
    s = str(section_title or "").strip()
    for sep in ("：", ":"):
        if sep in s:
            left, right = s.split(sep, 1)
            return left.strip(), right.strip()
    return "", s


def _bullet_body_font_size(line_count: int, avail_height: int) -> int:
    """行数が少ないほど大きく、縦余白があればさらに拡大。"""
    n = max(1, min(6, int(line_count)))
    base = {1: 58, 2: 56, 3: 54, 4: 50, 5: 46, 6: 44}.get(n, 44)
    if avail_height >= 540 and n <= 3:
        base += 4
    elif avail_height >= 500 and n <= 4:
        base += 2
    return base


def _render_immersive_bullet_clip(
    *,
    lines: List[str],
    section_title: str,
    font_path: Optional[str],
    max_width: int,
    avail_height: int,
    duration: float,
    start: float,
) -> Tuple[ImageClip, int, int]:
    """チャート無しの箇条書きシーン。行数に応じてカードと文字を拡大して余白感を抑える。"""
    clean_lines = [str(x).strip() for x in lines if str(x).strip()][:6]
    if not clean_lines:
        clean_lines = ["要点を確認"]

    kicker, headline = _split_section_title(section_title)
    if kicker.lower().startswith("opening") or "トピック" in kicker:
        kicker, headline = "", headline or kicker

    ink = ink_color()
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    n = len(clean_lines)
    body_fs = _bullet_body_font_size(n, avail_height)
    body_font = _pil_font(font_path, body_fs)
    kicker_font = _pil_font(font_path, 30)
    headline_font = _pil_font(font_path, 40)

    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)

    def _m(text: str, font) -> Tuple[int, int, Tuple[int, int, int, int]]:
        bb = td.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1], bb

    pad_x, pad_y = 56, 52
    w = int(max(620, min(int(max_width), int(max_width * 0.92))))
    wrap_w = max(320, w - pad_x * 2)
    inner_line_gap = 8
    bullet_item_gap = 32 if n <= 3 else (26 if n == 4 else 20)

    header_h = 0
    if kicker:
        _, kh, _ = _m(kicker[:20], kicker_font)
        header_h += kh + 10
    if headline:
        headline_wrapped = _wrap_text_to_px(headline, headline_font, wrap_w, max_lines=2, ellipsis=True)
        for hln in headline_wrapped:
            _, hh, _ = _m(hln, headline_font)
            header_h += hh + 6
        if headline_wrapped:
            header_h -= 6
        header_h += 18

    bullet_blocks: List[List[Tuple[str, int, int, Tuple[int, int, int, int]]]] = []
    max_line_w = 0
    lines_h = 0
    for ln in clean_lines:
        disp = ln if ln.startswith("・") or ln.startswith("•") else f"・{ln}"
        wrapped = _wrap_text_to_px(disp, body_font, wrap_w, max_lines=2, ellipsis=False)
        block = []
        for i, wln in enumerate(wrapped):
            if i > 0 and not wln.startswith("　"):
                wln = "　" + wln
            lw, lh, bb = _m(wln, body_font)
            block.append((wln, lw, lh, bb))
            max_line_w = max(max_line_w, lw)
            lines_h += lh + inner_line_gap
        if block:
            lines_h -= inner_line_gap
            lines_h += bullet_item_gap
            bullet_blocks.append(block)
    if lines_h:
        lines_h -= bullet_item_gap

    content_h = pad_y * 2 + header_h + lines_h
    min_h = max(content_h, int(max(360, avail_height) * 0.62))
    h = int(min_h)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (6, 10, w - 2, h - 2),
        radius=30,
        fill=(44, 36, 32, int(STUDIO_SOFT.get("panel_shadow_alpha", 72))),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    outline = STUDIO_SOFT.get("panel_outline", (*blue, 200))
    draw.rounded_rectangle(
        (2, 2, w - 6, h - 6),
        radius=28,
        fill=(*cream, int(STUDIO_SOFT.get("panel_cream_alpha", 250))),
        outline=outline if isinstance(outline, tuple) else (*blue, 200),
        width=3,
    )
    draw.rounded_rectangle((2, 2, 14, h - 6), radius=8, fill=(*blue, 220))

    block_total_h = header_h + lines_h
    y = pad_y + max(0, (h - pad_y * 2 - block_total_h) // 2)

    if kicker:
        draw.rounded_rectangle(
            (pad_x, y, pad_x + min(wrap_w, 260), y + 40),
            radius=14,
            fill=(*blue, 230),
        )
        try:
            draw.text((pad_x + 18, y + 20), kicker[:16], font=kicker_font, fill=(255, 255, 255, 255), anchor="lm")
        except TypeError:
            _, kh, kb = _m(kicker[:16], kicker_font)
            draw.text((pad_x + 18, y + 20 - kh // 2 - kb[1]), kicker[:16], font=kicker_font, fill=(255, 255, 255, 255))
        y += 48

    if headline:
        for hln in _wrap_text_to_px(headline, headline_font, wrap_w, max_lines=2, ellipsis=True):
            _, hh, hb = _m(hln, headline_font)
            try:
                draw.text((pad_x, y + hh // 2), hln, font=headline_font, fill=(26, 35, 126, 255), anchor="lm")
            except TypeError:
                draw.text((pad_x, y - hb[1]), hln, font=headline_font, fill=(26, 35, 126, 255))
            y += hh + 8
        y += 12

    for bi, block in enumerate(bullet_blocks):
        for ln, _lw, lh, bb in block:
            try:
                draw.text((pad_x, y + lh // 2), ln, font=body_font, fill=(*ink, 255), anchor="lm")
            except TypeError:
                draw.text((pad_x, y - bb[1]), ln, font=body_font, fill=(*ink, 255))
            y += lh + inner_line_gap
        y -= inner_line_gap
        if bi < len(bullet_blocks) - 1:
            y += bullet_item_gap

    return _rgba_image_clip(img, duration=duration, start=start), w, h


def _load_char_with_chromakey(
    path: Path,
    *,
    height: Optional[int] = None,
    width: Optional[int] = None,
    flip_h: bool = False,
    max_width: Optional[int] = None,
    keep_top: Optional[int] = None,
    crop_from: str = "center",
) -> ImageClip:
    """キャラ画像のグリーンバックを透過させて読み込む。幅超過は縮小せず左右クロップ。"""
    with Image.open(str(path)) as img:
        img = img.convert("RGBA")
        if flip_h:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        data = np.array(img)
        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
        mask = (g > 100) & (g > r) & (g > b)
        data[mask] = [0, 0, 0, 0]

        alpha = data[:, :, 3]
        ys, xs = np.where(alpha > 8)
        if len(xs) > 0 and len(ys) > 0:
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            data = data[y0:y1, x0:x1]

        im = Image.fromarray(data, "RGBA")
        if height:
            nh = int(height)
            nw = max(1, int(im.width * nh / max(im.height, 1)))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        elif width:
            nw = int(width)
            nh = max(1, int(im.height * nw / max(im.width, 1)))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)

        if keep_top and im.height > int(keep_top):
            im = im.crop((0, 0, im.width, int(keep_top)))

        if max_width and im.width > int(max_width):
            mw = int(max_width)
            if crop_from == "left":
                im = im.crop((0, 0, mw, im.height))
            elif crop_from == "right":
                im = im.crop((im.width - mw, 0, im.width, im.height))
            else:
                x0 = (im.width - mw) // 2
                im = im.crop((x0, 0, x0 + mw, im.height))

        return ImageClip(np.array(im))

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
    content_x: Optional[int] = None,
    content_w: Optional[int] = None,
    bottom_reserved_h: Optional[int] = None,
) -> List[Dict]:
    """
    画像数に応じて、キャラクター（左右ガター）や字幕（下部）、セクションタイトル（上部）を避けた最適な座標とサイズを計算する。
    has_text が True の場合は、画像の下にテキストを表示するためのスペースを確保する。
    two_image_layout: 2枚の場合のレイアウト ("horizontal" または "vertical")
    """
    sw, sh = screen_size
    is_shorts = sw < sh
    
    if is_shorts:
        margin = 40
        available_w = sw - (margin * 2)
        img_h = int(sh * 0.45)
        start_y = 110
        positions = []
        if count >= 1:
            positions.append({"x": margin, "y": start_y, "w": available_w, "h": img_h})
        return positions

    text_area_h = int(bottom_reserved_h) if bottom_reserved_h is not None else (200 if show_subtitles else 40)
    title_area_h = top_reserved_h if top_reserved_h is not None else 128
    margin = 22

    if content_x is not None and content_w is not None:
        start_x = int(content_x) + margin
        main_area_w = max(360, int(content_w) - margin * 2)
    else:
        main_area_w = int(sw * 0.8)
        start_x = margin

    available_h = sh - text_area_h - title_area_h - (margin * 2)
    # immersive（bottom_reserved指定時）はタイトル直下から詰める
    start_y = title_area_h + (8 if bottom_reserved_h is not None else margin)
    img_available_h = int(available_h * float(image_ratio_when_text)) if has_text else available_h

    positions = []
    if count == 1:
        w = main_area_w
        h = img_available_h
        positions.append({"x": start_x, "y": start_y, "w": w, "h": h})
    elif count == 2:
        gap = 10 if bottom_reserved_h is not None else margin
        w = max(280, (main_area_w - gap) // 2)
        h = img_available_h
        positions.append({"x": start_x, "y": start_y, "w": w, "h": h})
        positions.append({"x": start_x + w + gap, "y": start_y, "w": w, "h": h})
    elif count == 3:
        h = (img_available_h // 2) - (margin // 2)
        w_half = (main_area_w // 2) - (margin // 2)
        positions.append({"x": start_x + (main_area_w - w_half)//2, "y": start_y, "w": w_half, "h": h})
        positions.append({"x": start_x, "y": start_y + h + margin, "w": w_half, "h": h})
        positions.append({"x": start_x + w_half + margin, "y": start_y + h + margin, "w": w_half, "h": h})
    elif count >= 4:
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
    
    # ブリッジ用キャラ画像の選択状態をリセット（動画ごとにランダム化するため）
    if hasattr(render_scenes_to_video, "_bridge_chars"):
        delattr(render_scenes_to_video, "_bridge_chars")
    if hasattr(render_scenes_to_video, "_bridge_char_idx"):
        delattr(render_scenes_to_video, "_bridge_char_idx")
    
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
        immersive_chart_bottom: Optional[int] = None
        immersive_chart_right: Optional[int] = None
        immersive_chart_top: Optional[int] = None
        immersive_chart_h: Optional[int] = None
        chart_caption_lines: List[str] = []
        dual_chart_with_text = False
        single_chart_with_text = False
        
        # --- 1. 背景レイヤー ---
        bg_name = sc.get("bg_name", "bg_illust.png")
        is_shorts = size[0] < size[1] # 縦長ならショート
        use_immersive = is_immersive_mode(presentation_mode, video_type="shorts" if is_shorts else "horizontal")
        # immersive: 左右キャラ用ガターを空け、中央に図解・要約・字幕を寄せる
        if use_immersive and (not is_shorts):
            cx, _, cw, _ = immersive_content_box(size)
            content_x, content_w = cx, cw
            char_slot_w, char_visible_h, char_band_top = immersive_char_band(size)
            telop_x, telop_w = immersive_telop_box(size)
            cap_font = _caption_font_size(size[1])
            # 2行字幕 + 下余白。チャート要約はこの上に別枠で確保する
            caption_slot_h = 52 + cap_font * 2 + max(10, cap_font // 4) + 28
            bottom_reserved_h = max(caption_slot_h + 32, int(char_visible_h * 0.42) + 32)
        else:
            content_x, content_w = None, None
            bottom_reserved_h = None
            char_slot_w, char_visible_h, char_band_top = 0, 0, size[1]
            telop_x, telop_w = 0, size[0]

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
        # immersive: 背景を少しぼかして暗めにし、前面カードの可読性を上げる
        if use_immersive and (not is_shorts) and sc.get("section_title") != "subscribe":
            try:
                fr = bg_clip.get_frame(0)
                im = Image.fromarray(fr).filter(ImageFilter.GaussianBlur(radius=1.2))
                arr = np.clip(np.array(im, dtype=np.float32) * 0.97, 0, 255).astype(np.uint8)
                bg_clip = (
                    ImageClip(arr)
                    .with_duration(total_scene_duration)
                    .with_start(cumulative_time)
                )
            except Exception as e:
                print(f"[WARN] immersive bg soften failed: {e}")
        all_clips.append(bg_clip)
        if use_immersive and (not is_shorts) and sc.get("section_title") != "subscribe":
            try:
                scrim = _make_immersive_scrim_clip(
                    size, duration=total_scene_duration, start=cumulative_time
                )
                all_clips.append(scrim)
            except Exception as e:
                print(f"[WARN] immersive scrim failed: {e}")

        # --- 2. セクションタイトル (動的リサイズ) ---
        section_title = sc.get("section_title")
        # ショートではタイトル表示をしない
        if (not is_shorts) and section_title and section_title != "subscribe":
            try:
                if use_immersive:
                    # 情報量が多いときだけタイトルをコンパクト化（opening は大きめ固定）
                    tfs_early = sc.get("target_files") or []
                    has_chart_early = bool(tfs_early) or str(sc.get("image_type", "")).startswith(
                        "chart"
                    )
                    is_opening_title = ("トピック" in section_title) or (
                        "opening" in section_title.lower()
                    )
                    density = immersive_density_score(sc, has_chart=has_chart_early)
                    if is_opening_title:
                        title_scale = 1.1
                    else:
                        title_scale = 0.84 if has_chart_early else 0.92
                        if density >= 0.75:
                            title_scale = max(0.72, title_scale - (density - 0.7) * 0.25)
                    max_w = max(520, (content_w or int(size[0] * 0.72)) - 16)
                    title_pill, frame_w, frame_h = _render_title_pill_clip(
                        section_title,
                        font_path=font_to_use if isinstance(font_to_use, str) else None,
                        max_width=max_w,
                        duration=total_scene_duration,
                        start=cumulative_time,
                        scale=title_scale,
                    )
                    frame_x = (content_x or 0) + max(0, ((content_w or size[0]) - frame_w) // 2)
                    if is_opening_title:
                        frame_y = 44
                    else:
                        frame_y = 56 if title_scale >= 0.88 else max(32, int(56 - (0.92 - title_scale) * 80))
                    all_clips.append(title_pill.with_position((frame_x, frame_y)))
                    top_reserved_h_for_scene = frame_y + frame_h + 12
                    # 後段（メイン配置）でタイトル／テロップ／キャラに被らないよう参照
                    sc["_immersive_density"] = density
                    sc["_immersive_title_scale"] = title_scale
                else:
                    title_clip = TextClip(
                        text=section_title,
                        font=font_to_use,
                        font_size=54,
                        color="#4A2711",
                        method="label",
                        size=(None, 90),
                    ).with_duration(total_scene_duration).with_start(cumulative_time)
                    frame_w = title_clip.w + 200
                    frame_h = title_clip.h + 120
                    frame_path = images_dir / "title_frame.png"
                    if frame_path.exists():
                        t_frame = _load_frame_with_chromakey(frame_path, (frame_w, frame_h))
                        all_clips.append(
                            t_frame.with_position((0, 15))
                            .with_duration(total_scene_duration)
                            .with_start(cumulative_time)
                        )
                        top_reserved_h_for_scene = max(title_area_h, 15 + int(frame_h) + 10)
                    text_y = (frame_h - title_clip.h) // 2 - 5
                    title_clip = title_clip.with_position((95, text_y))
                    all_clips.append(title_clip)
            except Exception as e:
                print(f"[WARN] section title failed: {e}")

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

            diagram_only = bool(
                target_files
                and all(_is_studio_diagram_path(str(p)) for p in target_files)
            )
            ost_preview = [on_screen_text] if isinstance(on_screen_text, str) else (on_screen_text or [])
            chart_side_by_side = bool(
                (not is_shorts)
                and use_immersive
                and (not diagram_only)
                and any(str(t).strip() for t in ost_preview)
            )
            dual_chart_with_text = bool(
                chart_side_by_side
                and len(target_files) == 2
                and all(_path_looks_like_chart(str(p), sc) for p in resolved_paths)
            )
            single_chart_with_text = bool(
                chart_side_by_side
                and len(target_files) == 1
                and resolved_paths
                and _path_looks_like_chart(str(resolved_paths[0]), sc)
            )
            layout_has_text = bool(on_screen_text) and (not diagram_only) and (not chart_side_by_side)

            # テキストがあるかどうか、および画像の向きをレイアウト計算に伝える
            layout_x, layout_w = content_x, content_w
            if (not is_shorts) and use_immersive and diagram_only:
                layout_x = int(size[0] * 0.035)
                layout_w = int(size[0] * 0.93)
            layout_configs = _calculate_smart_layout(
                len(target_files), size, 
                has_text=layout_has_text,
                image_paths=resolved_paths,
                two_image_layout=sc.get("two_image_layout", "horizontal"),
                show_subtitles=show_subtitles,
                top_reserved_h=top_reserved_h_for_scene,
                image_ratio_when_text=0.88 if is_event_calendar_scene else (1.0 if use_immersive and diagram_only else (0.98 if use_immersive else 0.68)),
                content_x=layout_x,
                content_w=layout_w,
                bottom_reserved_h=bottom_reserved_h,
            )
            if single_chart_with_text:
                base_x = int(layout_x or content_x or margin) + margin
                usable_w = max(720, int(layout_w or content_w or main_area_w) - margin * 2)
                avail_top = int(top_reserved_h_for_scene or start_y) + 8
                avail_bot = size[1] - int(bottom_reserved_h or 168) - 16
                total_h = max(320, avail_bot - avail_top)
                caption_reserve = max(130, min(200, int(total_h * 0.30)))
                chart_h = max(240, total_h - caption_reserve - 12)
                layout_configs = [{"x": base_x, "y": avail_top, "w": usable_w, "h": chart_h}]
                immersive_chart_right = None
            elif dual_chart_with_text:
                base_x = int(layout_x or content_x or margin) + margin
                usable_w = max(720, int(layout_w or content_w or main_area_w) - margin * 2)
                text_col_w = max(380, min(520, int(usable_w * 0.42)))
                charts_col_w = max(440, usable_w - text_col_w - 14)
                avail_top = int(top_reserved_h_for_scene or start_y) + 8
                avail_bot = size[1] - int(bottom_reserved_h or 168) - 16
                total_h = max(300, avail_bot - avail_top)
                chart_gap = 10
                slot_h = max(180, (total_h - chart_gap) // 2)
                layout_configs = [
                    {"x": base_x, "y": avail_top, "w": charts_col_w, "h": slot_h},
                    {
                        "x": base_x,
                        "y": avail_top + slot_h + chart_gap,
                        "w": charts_col_w,
                        "h": slot_h,
                    },
                ]
                immersive_chart_right = base_x + charts_col_w
                immersive_chart_top = avail_top
                immersive_chart_h = total_h
            for idx, img_name in enumerate(target_files):
                if idx >= len(layout_configs): break
                conf = layout_configs[idx]
                visual_path = _asset_for_visual(images_dir, img_name)
                if visual_path:
                    try:
                        v_clip = _load_rgba_image_clip(visual_path)
                        section_title = str(sc.get("section_title", "") or "")
                        img_name_l = str(img_name).lower()
                        is_event_calendar = (
                            ("イベントカレンダー" in section_title)
                            or ("event_calendar" in section_title.lower())
                            or ("kessan_schedule" in img_name_l)
                            or ("soukai_schedule" in img_name_l)
                        )
                        is_chart = _path_looks_like_chart(str(visual_path or img_name), sc)
                        # 図解は横幅優先。チャート横並びは後段で左列に contain（先に全体へ縮めない）
                        skip_pre_fit = bool(
                            (not is_shorts) and use_immersive and is_chart and chart_side_by_side
                        )
                        if not skip_pre_fit:
                            if (not is_shorts) and use_immersive and diagram_only:
                                v_clip = v_clip.resized(width=conf["w"])
                            else:
                                v_clip = v_clip.resized(width=conf["w"])
                                if v_clip.h > conf["h"]:
                                    v_clip = v_clip.resized(height=conf["h"])

                        # immersive: チャート系だけ“軽いズーム”で番組感を出す（classicは維持）
                        # 画面からはみ出さないよう、最初に少しだけ小さくしてからズームする。
                        # immersive は枠埋め拡大済み。classic のみ軽いズーム。
                        if (not is_shorts) and (not use_immersive) and is_chart and (not is_event_calendar) and total_scene_duration >= 2.0:
                            base_shrink = 0.95
                            zoom_max = 1.05
                            zoom_dur = min(2.0, max(0.8, total_scene_duration * 0.35))
                            v_clip = v_clip.resized(base_shrink)

                            def _zoom_factor(t: float) -> float:
                                if t <= 0:
                                    return 1.0
                                if t >= zoom_dur:
                                    return zoom_max
                                u = t / zoom_dur
                                return 1.0 + (zoom_max - 1.0) * (1.0 - (1.0 - u) * (1.0 - u))

                            v_clip = v_clip.resized(lambda t: _zoom_factor(float(t)))

                        # event_calendar は “contain” をより厳密に（見切れ防止の安全策）
                        if (not is_shorts) and use_immersive and is_event_calendar:
                            # すでに枠内に収める処理はあるが、表画像は横長になりがちなので少し余裕を見て縮める
                            v_clip = v_clip.resized(0.97)
                        
                        # immersive: 画面中央やや下寄り（タイトル直下に張り付かない）
                        # 密度高のときはタイトル／テロップ／キャラ帯に被らないよう縦を締める
                        pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                        if (not is_shorts) and use_immersive:
                            density = float(sc.get("_immersive_density") or 0.0)
                            avail_top = int(conf["y"]) + 6
                            # チャート＋要約は横並びなので、下スロットは取らない
                            summary_slot = 0 if (is_chart and chart_side_by_side) else (176 if is_chart else 0)
                            avail_bot = size[1] - int(bottom_reserved_h or 140) - summary_slot - 16
                            if diagram_only:
                                avail_bot = size[1] - int(bottom_reserved_h or 140) - 18
                            if density >= 0.9 and char_visible_h and (not is_chart) and (not diagram_only):
                                avail_bot = min(
                                    avail_bot, size[1] - int(char_visible_h * 0.82) - 10
                                )
                            max_main_h = max(120, avail_bot - avail_top)
                            if is_chart and chart_side_by_side:
                                if dual_chart_with_text:
                                    scale = min(
                                        conf["w"] / max(v_clip.w, 1),
                                        conf["h"] / max(v_clip.h, 1),
                                    )
                                    v_clip = v_clip.resized(scale)
                                    pos_x = conf["x"] + max(0, (conf["w"] - v_clip.w) // 2)
                                    pos_y = conf["y"] + max(0, (conf["h"] - v_clip.h) // 2)
                                elif single_chart_with_text:
                                    scale = min(
                                        conf["w"] / max(v_clip.w, 1),
                                        conf["h"] / max(v_clip.h, 1),
                                    )
                                    v_clip = v_clip.resized(scale)
                                    pos_x = conf["x"] + max(0, (conf["w"] - v_clip.w) // 2)
                                    pos_y = conf["y"] + max(0, (conf["h"] - v_clip.h) // 2)
                                    immersive_chart_right = None
                                    immersive_chart_top = int(pos_y)
                                    immersive_chart_h = int(v_clip.h)
                                else:
                                    chart_col_w = max(280, int(conf["w"] * 0.55))
                                    scale = min(
                                        chart_col_w / max(v_clip.w, 1),
                                        max_main_h / max(v_clip.h, 1),
                                    )
                                    v_clip = v_clip.resized(scale)
                                    pos_x = int(conf["x"])
                                    leftover = max(0, avail_bot - avail_top - int(v_clip.h))
                                    pos_y = avail_top + leftover // 5
                                    immersive_chart_right = int(pos_x + v_clip.w)
                                    immersive_chart_top = int(pos_y)
                                    immersive_chart_h = int(v_clip.h)
                            elif is_chart:
                                scale = min(
                                    conf["w"] / max(v_clip.w, 1),
                                    max_main_h / max(v_clip.h, 1),
                                )
                                v_clip = v_clip.resized(scale)
                                pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                                pos_y = avail_top
                            elif diagram_only and int(v_clip.h) > max_main_h:
                                v_clip = v_clip.resized(height=max_main_h)
                                pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                                leftover = max(0, avail_bot - avail_top - int(v_clip.h))
                                pos_y = avail_top + leftover // 2
                            elif (not diagram_only) and int(v_clip.h) > max_main_h:
                                v_clip = v_clip.resized(height=max_main_h)
                                pos_x = conf["x"] + (conf["w"] - v_clip.w) // 2
                                leftover = max(0, avail_bot - avail_top - int(v_clip.h))
                                pos_y = avail_top + leftover // 2
                            elif diagram_only:
                                leftover = max(0, avail_bot - avail_top - int(v_clip.h))
                                pos_y = avail_top + leftover // 2
                            else:
                                band_mid = avail_top + max(0, (avail_bot - avail_top - int(v_clip.h)) // 2)
                                screen_mid = max(avail_top, size[1] // 2 - int(v_clip.h) // 2 + 24)
                                pos_y = int(0.4 * band_mid + 0.6 * screen_mid)
                                pos_y = max(avail_top, min(pos_y, avail_bot - int(v_clip.h)))
                        else:
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
                        if (not is_shorts) and use_immersive:
                            immersive_chart_bottom = int(pos_y + v_clip.h)
                        if video_cross > 0:
                            v_clip = v_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                        # immersive: 図解側が角丸カードなので二重のクリーム板は置かない（影のみ）
                        if (not is_shorts) and use_immersive and is_chart and (not is_event_calendar):
                            try:
                                box_w, box_h = int(v_clip.w), int(v_clip.h)
                                shadow = (
                                    _shadow_clip(
                                        (box_w + 20, box_h + 20),
                                        radius=28,
                                        blur=14,
                                        alpha=28,
                                    )
                                    .with_position((pos_x - 6, pos_y + 4))
                                    .with_duration(total_scene_duration)
                                    .with_start(cumulative_time)
                                )
                                if video_cross > 0:
                                    shadow = shadow.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                                all_clips.append(shadow)
                            except Exception as e:
                                print(f"[WARN] chart shadow failed: {e}")

                        all_clips.append(v_clip)
                    except Exception as e:
                        print(f"⚠️ ビジュアル表示失敗 ({img_name}): {e}")
        
        # --- 4. 要約テキストパネル (動的リサイズ) ---
        # immersive + ニュース中央: 要約帯は出さない（中央カードと二重）
        # immersive + 図解: 図の直下に短い補足だけ出す（話しテロップとは別）
        immersive_news_center = bool(
            (not is_shorts) and use_immersive and (not target_files) and on_screen_text
        )
        skip_summary_band = bool(
            (not is_shorts) and use_immersive and immersive_news_center
        )
        if (not is_shorts) and use_immersive and target_files and on_screen_text:
            if not all(_is_studio_diagram_path(str(p)) for p in target_files):
                text_list = [on_screen_text] if isinstance(on_screen_text, str) else on_screen_text
                for t in text_list:
                    s = str(t).strip()
                    if s:
                        chart_caption_lines.append(s)
                chart_caption_lines = chart_caption_lines[:6]
            skip_summary_band = True  # 通常の要約帯ではなく図直下キャプションへ（図解のみは非表示）

        if on_screen_text and (not immersive_news_center) and (not skip_summary_band):
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
                        section_title_str = str(sc.get("section_title", "") or "")
                        tf_names = [str(x).lower() for x in (target_files or [])]
                        is_event_calendar = (
                            ("イベントカレンダー" in section_title_str)
                            or ("event_calendar" in section_title_str.lower())
                            or any(("kessan_schedule" in n) or ("soukai_schedule" in n) for n in tf_names)
                        )
                        # 下帯（字幕）の直上にコンパクトな要約を置く → 下余白を埋める
                        text_w = max(420, (content_w or main_area_w) - 48)
                        text_h_max = 110 if is_event_calendar else 130
                        base_font_size = 40 if is_event_calendar else 44
                        reduction_per_line = 2
                        frame_padding_h = 28
                        frame_offset_y = 0
                        text_offset_y = 0
                        # 字幕帯の上端付近
                        telop_top = size[1] - int(bottom_reserved_h or 220) + 8
                        text_y_base = max(
                            (top_reserved_h_for_scene or start_y) + 40,
                            telop_top - text_h_max - 24,
                        )
                    else:
                        text_h_max = int(available_h * 0.4)
                        text_y_base = start_y + int(available_h * 0.70) + margin - 10
                        text_w = main_area_w - margin * 4
                        base_font_size = 40
                        reduction_per_line = 4
                        frame_padding_h = -20
                        frame_offset_y = 30
                        text_offset_y = 50
                    frame_name = "main_frame.png"
                else:
                    if use_immersive:
                        # 画像なし: 中央コンテンツに短いラベル帯（巨大な空枠をやめる）
                        text_w = max(480, (content_w or main_area_w) - 48)
                        text_h_max = 140
                        base_font_size = 48
                        reduction_per_line = 3
                        frame_padding_h = 36
                        frame_offset_y = 0
                        text_offset_y = 0
                        telop_top = size[1] - int(bottom_reserved_h or 220) + 8
                        text_y_base = max(
                            (top_reserved_h_for_scene or start_y) + 80,
                            telop_top - text_h_max - 28,
                        )
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

                if use_immersive and (not is_shorts):
                    # Pillow 一体描画で枠内垂直中央（TextClip caption の下寄りを回避）
                    ink = ink_color()
                    fill_rgb: Tuple[int, int, int] = ink
                    if formatted_lines:
                        immersive_sign = _immersive_price_change_sign(formatted_lines)
                        if immersive_sign == "+":
                            fill_rgb = STUDIO_SOFT["soft_green"]  # type: ignore[assignment]
                        elif immersive_sign == "-":
                            fill_rgb = STUDIO_SOFT["soft_coral"]  # type: ignore[assignment]
                    band_w_max = min((content_w or (size[0] - 2 * margin)) - 24, text_w + 40)
                    summary_clip, band_w, band_h = _render_summary_band_clip(
                        formatted_lines[:3],
                        font_path=font_to_use if isinstance(font_to_use, str) else None,
                        max_width=band_w_max,
                        fill_rgb=fill_rgb,
                        duration=total_scene_duration,
                        start=cumulative_time,
                        font_size=font_size,
                    )
                    band_x = (content_x or margin) + max(0, ((content_w or main_area_w) - band_w) // 2)
                    # 図解の直下（話しテロップとは別物の要約帯）
                    if immersive_chart_bottom is not None:
                        band_y = min(
                            int(immersive_chart_bottom) + 10,
                            size[1] - int(bottom_reserved_h or 168) - band_h - 12,
                        )
                        band_y = max(int(top_reserved_h_for_scene or start_y) + 16, band_y)
                    else:
                        band_y = max(
                            (top_reserved_h_for_scene or start_y) + 28,
                            size[1] - int(bottom_reserved_h or 168) - band_h - 12,
                        )
                    summary_clip = summary_clip.with_position((band_x, band_y))
                    actual_text_h = band_h
                else:
                    summary_clip = TextClip(
                        text=summary_text,
                        font=font_to_use,
                        font_size=font_size,
                        color=label_color,
                        method="caption",
                        size=(text_w, text_h_max),
                        text_align="left",
                    ).with_duration(total_scene_duration).with_start(cumulative_time)
                    actual_text_h = summary_clip.h
                    frame_path = images_dir / frame_name
                    if frame_path.exists():
                        if is_shorts:
                            m_frame = _load_frame_with_chromakey(
                                frame_path, (text_w + 100, actual_text_h + frame_padding_h)
                            )
                            all_clips.append(
                                m_frame.with_position(("center", text_y_base - frame_offset_y))
                                .with_duration(total_scene_duration)
                                .with_start(cumulative_time)
                            )
                        else:
                            m_frame = _load_frame_with_chromakey(
                                frame_path, (text_w + 275, actual_text_h + frame_padding_h)
                            )
                            all_clips.append(
                                m_frame.with_position((-100, text_y_base - frame_offset_y))
                                .with_duration(total_scene_duration)
                                .with_start(cumulative_time)
                            )

                # テキストの位置を調整（immersive は上で配置済み）
                if is_shorts:
                    summary_clip = summary_clip.with_position(("center", text_y_base))
                    shorts_text_bottom_y = (
                        (text_y_base - frame_offset_y) + actual_text_h + frame_padding_h
                    )
                elif not use_immersive:
                    base_pos = (0, text_y_base - text_offset_y)
                    summary_clip = summary_clip.with_position(base_pos)
                if video_cross > 0:
                    summary_clip = summary_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(summary_clip)
            except Exception as e:
                print(f"[WARN] 要約テキスト生成失敗: {e}")

        # immersive: 1枚チャート=上下、2枚チャート=左縦並び+右要約
        if (
            (not is_shorts)
            and use_immersive
            and chart_caption_lines
            and immersive_chart_bottom is not None
        ):
            try:
                font_path_s = font_to_use if isinstance(font_to_use, str) else None
                side_layout = bool(dual_chart_with_text and immersive_chart_right is not None)
                below_layout = bool(single_chart_with_text)
                if side_layout:
                    gap = 12
                    right_x = int(immersive_chart_right) + gap
                    right_max = int((content_x or 0) + (content_w or size[0]) - 8)
                    cap_w_max = max(340, right_max - right_x)
                    # 長文が含まれる場合は 40px、短ければ 44px に調整して変な改行を防ぐ
                    max_line_len = max(len(str(ln)) for ln in chart_caption_lines[:4]) if chart_caption_lines else 0
                    cap_font_sz = 40 if max_line_len >= 14 else 44
                    wrap_font = _pil_font(font_path_s, cap_font_sz)
                    wrap_px = max(160, cap_w_max - 40)
                    wrapped: List[str] = []
                    for src in chart_caption_lines[:4]:
                        pages, _rest = _paginate_text_px(
                            src, wrap_font, wrap_px, max_lines=2, ellipsis=False
                        )
                        if pages:
                            wrapped.extend(ln for ln in pages[0] if str(ln).strip())
                    if not wrapped:
                        wrapped = chart_caption_lines[:4]
                    chart_h = int(immersive_chart_h or 0)
                    tip_clip, tip_w, tip_h = _render_summary_band_clip(
                        wrapped,
                        font_path=font_path_s,
                        max_width=cap_w_max,
                        fill_rgb=ink_color(),
                        duration=total_scene_duration,
                        start=cumulative_time,
                        font_size=cap_font_sz,
                        force_width=cap_w_max,
                        pad_x=20,
                        pad_y=28,
                        min_height=max(180, int(chart_h * 0.90)) if chart_h else 0,
                        align="left",
                    )
                    tip_x = right_x
                    tip_y = int(immersive_chart_top or 0) + max(0, (chart_h - tip_h) // 2)
                    max_tip_y = size[1] - int(bottom_reserved_h or 140) - tip_h - 8
                    tip_y = max(int(immersive_chart_top or 0), min(tip_y, max_tip_y))
                elif below_layout:
                    cap_w_max = max(
                        560,
                        min(int(content_w or main_area_w) - 48, int((content_w or size[0]) * 0.88)),
                    )
                    cap_font_sz = 34
                    wrap_font = _pil_font(font_path_s, cap_font_sz)
                    wrap_px = max(200, cap_w_max - 48)
                    wrapped: List[str] = []
                    for src in chart_caption_lines[:4]:
                        pages, _rest = _paginate_text_px(
                            src, wrap_font, wrap_px, max_lines=2, ellipsis=False
                        )
                        if pages:
                            wrapped.extend(ln for ln in pages[0] if str(ln).strip())
                    if not wrapped:
                        wrapped = chart_caption_lines[:4]
                    tip_clip, tip_w, tip_h = _render_summary_band_clip(
                        wrapped,
                        font_path=font_path_s,
                        max_width=cap_w_max,
                        fill_rgb=ink_color(),
                        duration=total_scene_duration,
                        start=cumulative_time,
                        font_size=cap_font_sz,
                        force_width=cap_w_max,
                        pad_x=26,
                        align="left",
                    )
                    tip_x = int(content_x or margin) + max(0, ((content_w or main_area_w) - tip_w) // 2)
                    tip_y = int(immersive_chart_bottom) + 14
                    max_tip_y = size[1] - int(bottom_reserved_h or 140) - tip_h - 8
                    tip_y = max(int(immersive_chart_top or top_reserved_h_for_scene or start_y), min(tip_y, max_tip_y))
                else:
                    cap_w_max = max(400, int(telop_w or (content_w or size[0] * 0.55)) - 8)
                    tip_clip, tip_w, tip_h = _render_summary_band_clip(
                        chart_caption_lines[:2],
                        font_path=font_path_s,
                        max_width=cap_w_max,
                        fill_rgb=ink_color(),
                        duration=total_scene_duration,
                        start=cumulative_time,
                        font_size=36,
                        force_width=None,
                    )
                    tip_x = (content_x or 0) + max(0, ((content_w or size[0]) - tip_w) // 2)
                    tip_y = size[1] - int(bottom_reserved_h or 140) - tip_h - 12
                tip_clip = tip_clip.with_position((tip_x, tip_y))
                if video_cross > 0:
                    tip_clip = tip_clip.with_effects([FadeIn(video_cross), FadeOut(video_cross)])
                all_clips.append(tip_clip)
            except Exception as e:
                print(f"[WARN] chart caption failed: {e}")

        # --- 4.5. immersive: チャート無しニュースの中央フォーカス（中身サイズ＋縦中央） ---
        if (not is_shorts) and use_immersive and (not target_files):
            ticker = str(sc.get("ticker") or sc.get("related_ticker") or "").strip()
            company = str(sc.get("company_name") or sc.get("related_company_name") or "").strip()
            focus_lines: List[str] = []
            raw_ost = sc.get("on_screen_text") or []
            if isinstance(raw_ost, str):
                raw_ost = [raw_ost]
            for t in raw_ost:
                s = str(t).strip()
                if s and not _is_spoken_filler_line(s):
                    focus_lines.append(s)
            is_opening = _is_opening_scene(sc)
            focus_lines = _densify_on_screen_lines(
                sc,
                min_lines=4 if is_opening else 3,
                max_lines=5,
            )
            if ticker or company or focus_lines:
                try:
                    base_top = (
                        top_reserved_h_for_scene
                        if top_reserved_h_for_scene is not None
                        else start_y
                    )
                    plate_x = int(content_x or margin)
                    plate_w = int(content_w or main_area_w)
                    max_w = max(520, plate_w - 40)
                    density = float(sc.get("_immersive_density") or 0.0)
                    avail_top = int(base_top) + (12 if is_opening else 16)
                    avail_bot = size[1] - int(bottom_reserved_h or 168) - 16
                    if density >= 0.9 and char_visible_h and (not is_opening):
                        avail_bot = min(avail_bot, size[1] - int(char_visible_h * 0.82) - 10)
                    max_main_h = max(120, avail_bot - avail_top)
                    use_topics_card = is_opening or (
                        (not ticker and not company)
                        and _lines_have_category_markers(focus_lines)
                    )
                    use_bullet_panel = bool(
                        (not use_topics_card)
                        and (not ticker)
                        and (not company)
                        and focus_lines
                    )
                    if use_topics_card and focus_lines:
                        focus_clip, fw, fh = _render_opening_topics_clip(
                            lines=focus_lines,
                            font_path=font_to_use if isinstance(font_to_use, str) else None,
                            max_width=max_w,
                            duration=total_scene_duration,
                            start=cumulative_time,
                        )
                    elif use_bullet_panel:
                        focus_clip, fw, fh = _render_immersive_bullet_clip(
                            lines=focus_lines,
                            section_title=str(sc.get("section_title") or ""),
                            font_path=font_to_use if isinstance(font_to_use, str) else None,
                            max_width=max_w,
                            avail_height=max_main_h,
                            duration=total_scene_duration,
                            start=cumulative_time,
                        )
                    else:
                        focus_clip, fw, fh = _render_news_focus_clip(
                            ticker=ticker,
                            company=company,
                            lines=focus_lines,
                            font_path=font_to_use if isinstance(font_to_use, str) else None,
                            max_width=max_w,
                            duration=total_scene_duration,
                            start=cumulative_time,
                            min_height=0,
                        )
                    fx = plate_x + max(0, (plate_w - fw) // 2)
                    # 画面中央寄り。密度高のときはキャラ／テロップ帯を避けて収める
                    if fh > max_main_h:
                        # フォーカスカードは縮小（中身優先で高さ制限）
                        focus_clip = focus_clip.resized(height=max_main_h)
                        fw, fh = int(focus_clip.w), int(focus_clip.h)
                        fx = plate_x + max(0, (plate_w - fw) // 2)
                    band_mid = avail_top + max(0, (avail_bot - avail_top - fh) // 2)
                    screen_mid = max(avail_top, size[1] // 2 - fh // 2 + (8 if is_opening else 20))
                    if is_opening:
                        fy = int(0.2 * band_mid + 0.8 * screen_mid)
                    elif use_topics_card or use_bullet_panel:
                        fy = int(0.15 * band_mid + 0.85 * screen_mid)
                    else:
                        fy = int(0.35 * band_mid + 0.65 * screen_mid)
                    fy = max(avail_top, min(fy, avail_bot - fh))
                    focus_clip = focus_clip.with_position((fx, fy))
                    if video_cross > 0:
                        focus_clip = focus_clip.with_effects(
                            [FadeIn(video_cross), FadeOut(video_cross)]
                        )
                    all_clips.append(focus_clip)
                except Exception as e:
                    print(f"[WARN] ニュースフォーカスカード生成失敗: {e}")

        # --- 4.6. immersive: 強調ワード（旧: 左上に浮かせる表示） ---
        # 案Aでは「要約枠内に統合」するため、ここでの単独表示は行わない。

        # --- 5. キャラクターレイヤー（感情別画像 + セグメントタイミングでアニメ） ---
        if sc.get("section_title") != "subscribe":
            scene_emotion = normalize_emotion(sc.get("emotion"))
            scene_speaker = primary_speaker_for_scene(sc) if sc.get("dialogue") or sc.get("speaker") else "minori"
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
                        merge_speaker_emotion_beats_for_scene(
                            segments_for_char, scene_emotion, total_scene_duration, scene_speaker
                        )
                        if segments_for_char
                        else [(0.0, total_scene_duration, scene_emotion, scene_speaker)]
                    )
                    for rel_start, beat_dur, beat_emotion, beat_speaker in beats:
                        beat_path = _asset_for_emotion(
                            images_dir, beat_emotion, is_shorts=True, speaker=beat_speaker
                        )
                        if not beat_path:
                            continue
                        
                        char_clip = _load_char_with_chromakey(beat_path, height=char_h, flip_h=True)
                        
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
                    # --- ブリッジ用キャラ画像のランダム選択 ---
                    # bridge_1.png, bridge_2.png ... の形式を検索
                    if not hasattr(render_scenes_to_video, "_bridge_chars"):
                        import random
                        all_bridge_chars = sorted(list(images_dir.glob("bridge_[0-9]*.png")))
                        # ランダムにシャッフル
                        random.shuffle(all_bridge_chars)
                        render_scenes_to_video._bridge_chars = all_bridge_chars
                        render_scenes_to_video._bridge_char_idx = 0

                    char_path = None
                    if render_scenes_to_video._bridge_chars:
                        # 使用可能な画像から選択
                        idx = render_scenes_to_video._bridge_char_idx
                        char_path = render_scenes_to_video._bridge_chars[idx]
                        
                        # インデックスを進める（最後まで行ったらシャッフルし直してループ）
                        render_scenes_to_video._bridge_char_idx += 1
                        if render_scenes_to_video._bridge_char_idx >= len(render_scenes_to_video._bridge_chars):
                            import random
                            random.shuffle(render_scenes_to_video._bridge_chars)
                            render_scenes_to_video._bridge_char_idx = 0
                    else:
                        # 見つからない場合は従来の mini.png
                        char_path = images_dir / "mini.png"

                    if char_path and char_path.exists():
                        char_h = int(size[1] * 0.42)
                        char_clip = _load_char_with_chromakey(char_path, height=char_h)
                        
                        pad_x, pad_y = 40, 70
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
                    # immersive: 常時二人。下端接地。テロップはキャラ間に差し込む。
                    # みのり=上半身アセット、カリン=全身アセット → 見え頭が揃うようズーム率を分ける。
                    if use_immersive:
                        density = float(sc.get("_immersive_density") or 0.0)
                        # 密度高: キャラを少し小さくしてメイン被りを避ける
                        vis_scale = 0.90 if density >= 1.0 else (0.95 if density >= 0.9 else 1.0)
                        char_max_w = int(char_slot_w * vis_scale) if char_slot_w else int(size[0] * 0.13)
                        visible_h = int((char_visible_h or int(size[1] * 0.32)) * vis_scale)
                        for side_speaker, flip in (("minori", True), ("karin", False)):
                            side_emotion = scene_emotion
                            for seg in segments_for_char:
                                if str(seg.get("speaker") or "").lower() == side_speaker:
                                    side_emotion = normalize_emotion(
                                        seg.get("emotion") or scene_emotion
                                    )
                                    break
                            beat_path = _asset_for_emotion(
                                images_dir, side_emotion, is_shorts=False, speaker=side_speaker
                            )
                            if not beat_path:
                                continue
                            # 全身アセットは強くズーム、上半身アセットは弱め
                            body_keep = 0.34 if side_speaker == "karin" else 0.58
                            full_h = int(visible_h / body_keep)
                            # 内側（テロップ側）を切って、キャラは端に残す
                            crop_from = "left" if side_speaker == "minori" else "right"
                            char_clip = _load_char_with_chromakey(
                                beat_path,
                                height=full_h,
                                flip_h=flip,
                                keep_top=visible_h,
                                max_width=char_max_w,
                                crop_from=crop_from,
                            )
                            if int(char_clip.h) != visible_h:
                                char_clip = char_clip.resized(height=visible_h)
                            if side_speaker == "minori":
                                char_x = 0
                            else:
                                char_x = size[0] - int(char_clip.w)
                            char_y = size[1] - visible_h
                            char_clip = (
                                char_clip.with_duration(total_scene_duration)
                                .with_start(cumulative_time)
                                .with_position((char_x, char_y))
                            )
                            if video_cross > 0:
                                char_clip = char_clip.with_effects(
                                    [FadeIn(video_cross), FadeOut(video_cross)]
                                )
                            all_clips.append(char_clip)
                    else:
                        char_max_w = int(size[0] * 0.25)
                        char_h = int(size[1] * 0.7)
                        beats = (
                            merge_speaker_emotion_beats_for_scene(
                                segments_for_char, scene_emotion, total_scene_duration, scene_speaker
                            )
                            if segments_for_char
                            else [(0.0, total_scene_duration, scene_emotion, scene_speaker)]
                        )
                        for rel_start, beat_dur, beat_emotion, beat_speaker in beats:
                            beat_path = _asset_for_emotion(
                                images_dir, beat_emotion, is_shorts=False, speaker=beat_speaker
                            )
                            if not beat_path:
                                continue
                            char_clip = _load_char_with_chromakey(beat_path, height=char_h)
                            if char_clip.w > char_max_w:
                                char_clip = char_clip.resized(width=char_max_w)
                            char_x = size[0] - char_clip.w - 10
                            char_y = size[1] - char_clip.h
                            char_clip = char_clip.with_duration(beat_dur).with_start(
                                cumulative_time + rel_start
                            )
                            char_clip = apply_emotion_motion(char_clip, beat_emotion, char_x, char_y)
                            if video_cross > 0:
                                char_clip = char_clip.with_effects(
                                    [FadeIn(video_cross), FadeOut(video_cross)]
                                )
                            all_clips.append(char_clip)
            except Exception as e:
                print(f"[WARN] character layer failed: {e}")

        # --- 6. 字幕レイヤー (Studio Soft telop / 従来 telop_frame) ---
        segments = sc.get("segments", [])
        # ショートまたは show_subtitles=False では字幕（segments）を表示しない
        if (not is_shorts) and show_subtitles and segments and sc.get("section_title") != "subscribe":
            soft_telop = images_dir / "studio_soft_telop.png"
            use_soft_telop = bool(use_immersive and soft_telop.exists())
            frame_path = soft_telop if use_soft_telop else (images_dir / "telop_frame.png")
            telop_y_bottom = size[1] - 156
            telop_h_full = 150
            if (not use_immersive) and frame_path.exists():
                telop_w_full = 2200
                telop_h_full = 550
                telop_y_bottom = size[1] - telop_h_full + 180
                telop_frame = _load_frame_with_chromakey(frame_path, (telop_w_full, telop_h_full))
                all_clips.append(
                    telop_frame.with_position(("center", telop_y_bottom))
                    .with_duration(total_scene_duration)
                    .with_start(cumulative_time)
                )

            for seg in segments:
                seg_text = str(seg.get("text", "") or "").strip()
                if not seg_text:
                    continue
                seg_dur = float(seg.get("duration", 0.5))
                seg_start_in_total = cumulative_time + float(seg.get("start", 0.0))
                try:
                    if use_immersive:
                        sp = str(seg.get("speaker") or sc.get("speaker") or "minori")
                        fill_rgb = speaker_subtitle_color(sp)
                        corridor_x, corridor_w = (
                            (telop_x, telop_w)
                            if telop_w
                            else immersive_telop_box(size)
                        )
                        cap_font = _caption_font_size(size[1])
                        wrap_font = _pil_font(
                            font_to_use if isinstance(font_to_use, str) else None,
                            cap_font,
                        )
                        text_max_px = max(80, int(corridor_w) - 80)
                        pages, _rest = _paginate_text_px(
                            seg_text,
                            wrap_font,
                            text_max_px,
                            max_lines=2,
                            ellipsis=False,
                        )
                        n_pages = max(1, len(pages))
                        page_dur = seg_dur / n_pages
                        for i, page_lines in enumerate(pages):
                            cap_clip, cap_w, cap_h = _render_caption_band_clip(
                                "",
                                font_path=font_to_use if isinstance(font_to_use, str) else None,
                                max_width=max(360, corridor_w),
                                fill_rgb=fill_rgb,
                                duration=page_dur,
                                start=seg_start_in_total + i * page_dur,
                                font_size=cap_font,
                                lines=page_lines,
                            )
                            ty = size[1] - cap_h - 36
                            tx = corridor_x + max(0, (corridor_w - cap_w) // 2)
                            all_clips.append(cap_clip.with_position((tx, ty)))
                    else:
                        txt_clip = TextClip(
                            text=seg_text, font=font_to_use, font_size=48,
                            color="white", stroke_color="black", stroke_width=1.5,
                            method="caption", size=(1700, 160), text_align="center"
                        ).with_duration(seg_dur).with_start(seg_start_in_total).with_position(("center", size[1] - 195))
                        all_clips.append(txt_clip)
                except Exception as e:
                    print(f"[WARN] subtitle failed: {e}")

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
