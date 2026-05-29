"""動画の演出モード（classic = 現行 / immersive = 聞き中心・短い画面ラベル）"""

from typing import Optional

PRESENTATION_CLASSIC = "classic"
PRESENTATION_IMMERSIVE = "immersive"

VALID_PRESENTATION_MODES = {PRESENTATION_CLASSIC, PRESENTATION_IMMERSIVE}


def normalize_presentation_mode(mode: Optional[str]) -> str:
    if not mode or mode not in VALID_PRESENTATION_MODES:
        return PRESENTATION_CLASSIC
    return mode


def is_immersive_mode(mode: Optional[str], *, video_type: str = "") -> bool:
    """横型本編のみ immersive を適用（ショートは常に従来）。"""
    if "shorts" in (video_type or ""):
        return False
    return normalize_presentation_mode(mode) == PRESENTATION_IMMERSIVE
