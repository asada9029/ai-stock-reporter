"""Studio Soft 見た目トークン（やわらかスタジオ向け）。"""

from __future__ import annotations

from typing import Dict, Tuple

# RGB
InkBrown = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

STUDIO_SOFT = {
    "ink": (44, 36, 32),
    "mute": (110, 100, 94),
    "surface_cream": (255, 248, 240, 248),
    "surface_cream_solid": (255, 248, 240),
    "soft_blue": (140, 180, 210),
    "soft_green": (70, 150, 110),
    "soft_coral": (210, 100, 90),
    "morning_overlay": (255, 220, 190, 110),
    "night_overlay": (40, 60, 100, 120),
    "bridge_shadow": (44, 36, 32),
    "band_radius": 18,
    "safe_margin": 48,
    # 前面カードの可読性（背景と差をつける）
    "panel_cream_alpha": 250,
    "panel_outline": (120, 155, 185, 200),
    "panel_shadow_alpha": 72,
    "scrim_overall_alpha": 14,
    "scrim_vignette_alpha": 36,
    # 字幕は立ち絵のイメージカラー（クリーム帯でも読める濃度）
    # みのり=ホストのネイビー、カリン=シャツのコーラル
    "speaker_minori": (47, 78, 122),
    "speaker_karin": (196, 78, 88),
    # immersive: 左右キャラ用ガター（中央を厚く・背景露出を抑える）
    "gutter_left_ratio": 0.10,
    "gutter_right_ratio": 0.11,
    # キャラ帯（テロップは左右キャラの間＝この内側）
    "char_slot_ratio": 0.155,
    "char_visible_h_ratio": 0.32,
    # 指・肩に被らない余白（ぎりぎりより少し内側）
    "telop_side_gap": 56,
}


def overlay_for_category(video_category: str) -> RGBA:
    if video_category == "morning":
        return STUDIO_SOFT["morning_overlay"]  # type: ignore[return-value]
    return STUDIO_SOFT["night_overlay"]  # type: ignore[return-value]


def ink_color() -> InkBrown:
    return STUDIO_SOFT["ink"]  # type: ignore[return-value]


def speaker_subtitle_color(speaker: str) -> InkBrown:
    sp = (speaker or "minori").strip().lower()
    if sp == "karin":
        return STUDIO_SOFT["speaker_karin"]  # type: ignore[return-value]
    return STUDIO_SOFT["speaker_minori"]  # type: ignore[return-value]


def immersive_content_box(screen_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """(x, y=0, w, h) 中央コンテンツ領域。左右はキャラ用ガター。"""
    sw, sh = screen_size
    gl = int(sw * float(STUDIO_SOFT["gutter_left_ratio"]))
    gr = int(sw * float(STUDIO_SOFT["gutter_right_ratio"]))
    return gl, 0, max(400, sw - gl - gr), sh


def immersive_char_band(screen_size: Tuple[int, int]) -> Tuple[int, int, int]:
    """左右キャラ帯。(slot_w, visible_h, band_top_y)"""
    sw, sh = screen_size
    slot_w = int(sw * float(STUDIO_SOFT["char_slot_ratio"]))
    visible_h = int(sh * float(STUDIO_SOFT["char_visible_h_ratio"]))
    return slot_w, visible_h, sh - visible_h


def immersive_telop_box(screen_size: Tuple[int, int]) -> Tuple[int, int]:
    """キャラ（指さし含む）に被らないテロップ枠。(x, max_width)"""
    sw, _sh = screen_size
    slot_w, _vh, _top = immersive_char_band(screen_size)
    # 指・肩が slot より内側に出るので、画面比でも下限を取る
    inset = max(int(sw * 0.175), slot_w + 24)
    x = inset
    w = max(400, sw - inset * 2)
    return x, w


def immersive_density_score(scene: Dict, *, has_chart: bool = False) -> float:
    """
    メイン情報量のざっくりスコア。高いほどタイトル縮小・セーフ帯を強める。
    0.0 = 通常、1.0+ = 密度高め。
    """
    ost = scene.get("on_screen_text") or []
    if isinstance(ost, str):
        ost = [ost]
    lines = [str(x).strip() for x in ost if str(x).strip()]
    score = 0.0
    score += min(1.2, len(lines) * 0.18)
    score += min(0.6, sum(len(x) for x in lines) / 220.0)
    if has_chart:
        score += 0.25
    if scene.get("ticker") or scene.get("related_ticker"):
        score += 0.1
    return score


__all__ = [
    "STUDIO_SOFT",
    "overlay_for_category",
    "ink_color",
    "speaker_subtitle_color",
    "immersive_content_box",
    "immersive_char_band",
    "immersive_telop_box",
    "immersive_density_score",
]
