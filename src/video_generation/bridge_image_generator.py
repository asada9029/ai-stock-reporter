"""
セクションブリッジ用の全画面カード（Pillow）を生成する。

- 背景: サムネのタイトル帯（band）と同じ色を全面に使用
  - 朝: 赤 (200, 0, 0) / 夜: 青 (0, 30, 80)
- 文字: 白・画面中央・大きめ（video_structure.json の content.title）
- キャラは載せない（レンダラー側で透過キャラを重ねる）
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.video_generation.thumbnail_generator import ThumbnailGenerator

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
    ) -> str:
        """
        1枚のブリッジ PNG を生成。
        - 背景: bg_illust.png
        - 前面: 癒やし系のクリーム色全画面オーバーレイ
        - 文字: テーマカラー（濃色）・中央・巨大
        """
        w, h = BRIDGE_SIZE
        
        # 1. 背景イラストの読み込み
        bg_path = self.assets_dir / "images" / "bg_illust.png"
        if bg_path.exists():
            img = Image.open(bg_path).convert("RGBA")
            if img.size != (w, h):
                img = img.resize((w, h), Image.Resampling.LANCZOS)
        else:
            img = Image.new("RGBA", (w, h), (240, 240, 240, 255))

        # 2. クリーム色オーバーレイ（癒やし系・暖かいトーン）
        # 背景をほぼ覆いつつ、イラストをわずかに透かす (不透明度 240/255)
        # 少しオレンジ・黄色寄りの暖かいクリーム色 (#FFF4E1 相当)
        overlay = Image.new("RGBA", (w, h), (255, 244, 225, 240))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        colors = ThumbnailGenerator.COLORS.get(
            video_category, ThumbnailGenerator.COLORS["evening"]
        )
        
        # 文字色はテーマの「縁取り色（濃色）」をメインに据える
        text_color = colors.get("outline", (40, 40, 40))
        # 逆に縁取りを白にして、文字を浮かせる
        outline_color = (255, 255, 255)

        # 3. テキストの描画
        lines = _wrap_title(title, max_chars_per_line=18)
        text_max_w = int(w * 0.85)
        longest = max(lines, key=len)
        font = _fit_font_size(
            draw,
            longest,
            self.font_path,
            text_max_w,
            start_size=180,
            min_size=100,
        )

        line_metrics: List[Tuple[int, int]] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_metrics.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

        line_gap = 40
        total_text_h = sum(lh for _, lh in line_metrics) + max(0, len(lines) - 1) * line_gap
        # 少し上に配置 (中央から 100px 上へ)
        current_y = (h - total_text_h) // 2 - 100

        # 縁取り色の選定
        if video_category == "morning":
            # 朝：濃い茶色の文字に、温かいピーチ系の外枠
            outer_outline = (255, 210, 180) 
        else:
            # 夜：濃い紺色の文字に、落ち着いた水色グレーの外枠
            outer_outline = (180, 200, 230)

        for i, line in enumerate(lines):
            lw, lh = line_metrics[i]
            x = (w - lw) // 2
            
            # 二重縁取りで「目立たせる」かつ「なごませる」
            # 1. 大外（淡色）
            self._thumb._draw_text_with_outline(
                draw, (x, current_y), line, font,
                fill_color=outer_outline,
                outline_color=outer_outline,
                outline_width=12,
            )
            # 2. 内側（白：境界をくっきりさせる）
            self._thumb._draw_text_with_outline(
                draw, (x, current_y), line, font,
                fill_color=(255, 255, 255),
                outline_color=(255, 255, 255),
                outline_width=6,
            )
            # 3. 文字本体（濃色）
            draw.text((x, current_y), line, font=font, fill=text_color)
            
            current_y += lh + line_gap

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
