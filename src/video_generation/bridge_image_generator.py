"""
セクションブリッジ用の全画面カード（Pillow）を生成する。

Studio Soft:
- 背景: bg_illust.png + 朝ピーチ / 夜インディゴの半透明オーバーレイ
- 文字: 濃い茶グレー + 太い影1層（細い多重縁は使わない）
- キャラは載せない（レンダラー側で透過キャラを重ねる）
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.video_generation.thumbnail_generator import ThumbnailGenerator
from src.config.studio_soft import STUDIO_SOFT, overlay_for_category, ink_color

# 横型本編と同じ解像度
BRIDGE_SIZE = (1920, 1080)

# ThumbnailGenerator.COLORS['band'] と同じ（band 未定義時のフォールバック）
_FALLBACK_BAND_RGB = {
    "morning": (200, 0, 0),
    "evening": (0, 30, 80),
}


def resolve_bridge_image_path(
    images_dir: Path, video_type: str, section_key: str
) -> Path:
    """存在するブリッジ画像パスを返す（無ければカテゴリ付きパス）。"""
    cat = _video_category(video_type)
    candidates = [
        images_dir / f"bridge_{cat}_{section_key}.png",
        images_dir / f"bridge_{section_key}.png",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _video_category(video_type: str) -> str:
    return "morning" if "morning" in (video_type or "").lower() else "evening"


def band_background_rgb(video_category: str) -> Tuple[int, int, int]:
    """サムネのタイトル帯（band）と同じ RGB。"""
    colors = ThumbnailGenerator.COLORS.get(
        video_category, ThumbnailGenerator.COLORS["evening"]
    )
    band = colors.get("band")
    if band and len(band) >= 3:
        return (int(band[0]), int(band[1]), int(band[2]))
    return _FALLBACK_BAND_RGB.get(video_category, _FALLBACK_BAND_RGB["evening"])


def load_sections_from_structure(
    structure_path: Path, video_type: str
) -> List[Tuple[str, str]]:
    """
    (section_key, display_title) のリスト。
    section_key は bridge_{key}.png の key（video_structure の name）。
    """
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    block = structures.get(video_type)
    if not block:
        raise KeyError(f"video_structure.json に {video_type} がありません")

    out: List[Tuple[str, str]] = []
    for sec in block.get("sections", []):
        name = (sec.get("name") or "").strip()
        if not name:
            continue
        content = sec.get("content") or {}
        title = (content.get("title") or name).strip()
        out.append((name, title))
    return out


def _fit_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Optional[str],
    max_width: int,
    start_size: int,
    min_size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(start_size, min_size - 1, -4):
        if font_path:
            try:
                font = ImageFont.truetype(font_path, size)
            except Exception:
                font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    if font_path:
        try:
            return ImageFont.truetype(font_path, min_size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_title(title: str, *, max_chars_per_line: int = 16) -> List[str]:
    """長いセクション名を2行までに収める。"""
    title = title.strip()
    if len(title) <= max_chars_per_line:
        return [title]
    lines = textwrap.wrap(title, width=max_chars_per_line)
    if len(lines) > 2:
        lines = lines[:2]
        lines[-1] = lines[-1][: max_chars_per_line - 1] + "…"
    return lines


class BridgeImageGenerator:
    def __init__(self, assets_dir: str = "src/assets"):
        self.assets_dir = Path(assets_dir)
        self.images_dir = self.assets_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._thumb = ThumbnailGenerator()
        self.font_path = self._thumb.font_path

    def create_bridge_image(
        self,
        title: str,
        *,
        video_category: str = "evening",
        output_path: Optional[Path] = None,
        subtitle: Optional[str] = None,
    ) -> str:
        """
        Studio Soft ブリッジ PNG（番組感・見たくなる転換カード）。
        背景イラストは残しつつ、中央にフロストカード＋特大タイトル。
        """
        w, h = BRIDGE_SIZE

        bg_path = self.assets_dir / "images" / "bg_illust.png"
        if bg_path.exists():
            img = Image.open(bg_path).convert("RGBA")
            if img.size != (w, h):
                img = img.resize((w, h), Image.Resampling.LANCZOS)
        else:
            img = Image.new("RGBA", (w, h), (240, 240, 240, 255))

        # 朝/夜の色味
        if video_category == "morning":
            tint = (255, 200, 150, 70)
            accent = STUDIO_SOFT["soft_coral"]
            badge = "MORNING"
        else:
            tint = (60, 90, 140, 85)
            accent = STUDIO_SOFT["soft_blue"]
            badge = "EVENING"

        img = Image.alpha_composite(img, Image.new("RGBA", (w, h), tint))
        # 端を少し暗くして中央に視線を集める
        vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        vd = ImageDraw.Draw(vignette)
        for i, a in enumerate((50, 35, 20)):
            inset = 20 + i * 40
            vd.rectangle((0, 0, w, inset), fill=(30, 24, 20, a))
            vd.rectangle((0, h - inset, w, h), fill=(30, 24, 20, a))
            vd.rectangle((0, 0, inset, h), fill=(30, 24, 20, a // 2))
            vd.rectangle((w - inset, 0, w, h), fill=(30, 24, 20, a // 2))
        img = Image.alpha_composite(img, vignette)

        # 中央フロストカード
        card_w, card_h = int(w * 0.78), int(h * 0.42)
        card_x = (w - card_w) // 2
        card_y = (h - card_h) // 2 - 40
        card_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card_layer)
        # soft shadow under card
        cd.rounded_rectangle(
            (card_x + 10, card_y + 16, card_x + card_w, card_y + card_h),
            radius=36,
            fill=(44, 36, 32, 55),
        )
        card_layer = card_layer.filter(ImageFilter.GaussianBlur(18))
        img = Image.alpha_composite(img, card_layer)
        card_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card_layer)
        cream = STUDIO_SOFT["surface_cream_solid"]
        cd.rounded_rectangle(
            (card_x, card_y, card_x + card_w, card_y + card_h),
            radius=36,
            fill=(*cream, 220),
            outline=(255, 255, 255, 160),
            width=3,
        )
        # left accent bar
        cd.rounded_rectangle(
            (card_x + 28, card_y + 48, card_x + 44, card_y + card_h - 48),
            radius=8,
            fill=(*accent, 230),
        )
        img = Image.alpha_composite(img, card_layer)
        draw = ImageDraw.Draw(img)

        # 小さな番組バッジ
        badge_font = _fit_font_size(draw, badge, self.font_path, 280, start_size=28, min_size=18)
        bb = draw.textbbox((0, 0), badge, font=badge_font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        bx, by = card_x + 70, card_y + 36
        draw.rounded_rectangle(
            (bx - 16, by - 8, bx + bw + 16, by + bh + 8),
            radius=16,
            fill=(*accent, 210),
        )
        draw.text((bx, by), badge, font=badge_font, fill=(255, 255, 255, 255))

        text_color = ink_color()
        shadow_color = STUDIO_SOFT["bridge_shadow"]
        lines = _wrap_title(title, max_chars_per_line=14)
        text_max_w = card_w - 140
        longest = max(lines, key=len)
        font = _fit_font_size(
            draw, longest, self.font_path, text_max_w, start_size=150, min_size=72
        )

        line_metrics: List[Tuple[int, int]] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_metrics.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

        line_gap = 28
        total_text_h = sum(lh for _, lh in line_metrics) + max(0, len(lines) - 1) * line_gap
        current_y = card_y + (card_h - total_text_h) // 2 + 10

        for i, line in enumerate(lines):
            lw, lh = line_metrics[i]
            x = card_x + (card_w - lw) // 2 + 10
            draw.text((x + 5, current_y + 5), line, font=font, fill=(*shadow_color, 70))
            draw.text((x, current_y), line, font=font, fill=text_color)
            current_y += lh + line_gap

        sub = subtitle or "マイカブ｜やさしくわかる今日の株"
        sub_font = _fit_font_size(draw, sub, self.font_path, int(card_w * 0.7), start_size=36, min_size=22)
        sb = draw.textbbox((0, 0), sub, font=sub_font)
        sx = card_x + (card_w - (sb[2] - sb[0])) // 2
        sy = card_y + card_h + 28
        draw.rounded_rectangle(
            (sx - 24, sy - 10, sx + (sb[2] - sb[0]) + 24, sy + (sb[3] - sb[1]) + 10),
            radius=18,
            fill=(255, 248, 240, 200),
        )
        draw.text((sx, sy), sub, font=sub_font, fill=STUDIO_SOFT["mute"])

        if output_path is None:
            safe = re.sub(r"[^\w\-]+", "_", title)[:40]
            output_path = self.images_dir / f"bridge_custom_{safe}.png"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(output_path, "PNG")
        return str(output_path)

    def generate_for_video_type(
        self,
        video_type: str,
        *,
        structure_path: Optional[Path] = None,
        skip_opening: bool = False,
    ) -> List[str]:
        """video_structure に基づき bridge_{section_key}.png を一括生成。"""
        structure_path = structure_path or (
            Path(__file__).resolve().parent.parent / "config" / "video_structure.json"
        )
        category = _video_category(video_type)
        paths: List[str] = []

        for section_key, title in load_sections_from_structure(structure_path, video_type):
            if skip_opening and section_key == "opening":
                continue
            out = self.images_dir / f"bridge_{category}_{section_key}.png"
            legacy = self.images_dir / f"bridge_{section_key}.png"
            path = self.create_bridge_image(
                title,
                video_category=category,
                output_path=out,
            )
            paths.append(path)
            if category == "evening":
                Image.open(out).save(legacy, "PNG")
            print(f"  [Bridge] {section_key} → {out.name}  「{title}」")
        return paths
