"""
Studio Soft 用のUI素材を Pillow で生成する。
視聴しやすい・ほのぼの番組感。暗い光沢テロップや重い枠は使わない。
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter

from src.config.studio_soft import STUDIO_SOFT


def _assets_images_dir(assets_dir: Path | None = None) -> Path:
    if assets_dir is None:
        assets_dir = Path(__file__).resolve().parent.parent / "assets"
    return Path(assets_dir) / "images"


def generate_title_pill(
    size: Tuple[int, int] = (900, 140),
    *,
    assets_dir: Path | None = None,
) -> Path:
    """左上セクションラベル用。柔らかいピル。緑背景（クロマキー用）。"""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 255, 0, 255))
    draw = ImageDraw.Draw(img)
    cream = STUDIO_SOFT["surface_cream_solid"]
    blue = STUDIO_SOFT["soft_blue"]
    pad = 8
    # soft shadow
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((pad + 4, pad + 6, w - pad, h - pad), radius=h // 2, fill=(44, 36, 32, 50))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img.convert("RGBA"), shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (pad, pad, w - pad - 4, h - pad - 4),
        radius=h // 2,
        fill=(*cream, 245),
        outline=(*blue, 180),
        width=3,
    )
    # left accent dot bar
    draw.ellipse((pad + 22, h // 2 - 10, pad + 42, h // 2 + 10), fill=(*blue, 255))
    out = _assets_images_dir(assets_dir) / "studio_soft_title_pill.png"
    img.convert("RGB").save(out, "PNG")
    return out


def generate_telop_band(
    size: Tuple[int, int] = (1600, 160),
    *,
    assets_dir: Path | None = None,
) -> Path:
    """字幕用の明るいクリーム帯（暗い光沢テロップの代替）。緑背景。"""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 255, 0, 255))
    cream = STUDIO_SOFT["surface_cream_solid"]
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((10, 14, w - 4, h - 4), radius=28, fill=(44, 36, 32, 55))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img.convert("RGBA"), shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (6, 6, w - 14, h - 16),
        radius=28,
        fill=(*cream, 240),
        outline=(255, 255, 255, 90),
        width=2,
    )
    # soft top highlight
    draw.rounded_rectangle(
        (24, 14, w - 32, 28),
        radius=8,
        fill=(255, 255, 255, 70),
    )
    out = _assets_images_dir(assets_dir) / "studio_soft_telop.png"
    img.convert("RGB").save(out, "PNG")
    return out


def generate_lower_band_template(
    size: Tuple[int, int] = (1800, 280),
    *,
    assets_dir: Path | None = None,
) -> Path:
    """下部情報帯のテンプレ（参考用 / フォールバック）。緑背景。"""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 255, 0, 255))
    cream = STUDIO_SOFT["surface_cream_solid"]
    coral = STUDIO_SOFT["soft_coral"]
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((8, 12, w - 2, h - 2), radius=22, fill=(44, 36, 32, 50))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    img = Image.alpha_composite(img.convert("RGBA"), shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (4, 4, w - 12, h - 14),
        radius=22,
        fill=(*cream, 242),
        outline=(255, 255, 255, 80),
        width=2,
    )
    # left accent strip
    draw.rounded_rectangle((18, 28, 30, h - 36), radius=6, fill=(*coral, 200))
    out = _assets_images_dir(assets_dir) / "studio_soft_lower_band.png"
    img.convert("RGB").save(out, "PNG")
    return out


def generate_all_studio_soft_assets(assets_dir: Path | None = None) -> list[str]:
    paths = [
        generate_title_pill(assets_dir=assets_dir),
        generate_telop_band(assets_dir=assets_dir),
        generate_lower_band_template(assets_dir=assets_dir),
    ]
    return [str(p) for p in paths]


if __name__ == "__main__":
    for p in generate_all_studio_soft_assets():
        print(p)
