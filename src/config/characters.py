"""キャラ設定の読み込み。VOICEVOX speaker_id はここだけ変えれば差し替え可能。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def characters_config_path() -> Path:
    return Path(__file__).resolve().parent / "characters.json"


def load_characters() -> Dict[str, Any]:
    path = characters_config_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_character(character_id: str) -> Dict[str, Any]:
    chars = load_characters()
    if character_id not in chars:
        raise KeyError(f"unknown character_id: {character_id}")
    return chars[character_id]


def get_voicevox_speaker_id(character_id: str, default: Optional[int] = None) -> int:
    char = get_character(character_id)
    voice = char.get("voicevox") or {}
    if "speaker_id" in voice:
        return int(voice["speaker_id"])
    if default is not None:
        return default
    raise KeyError(f"speaker_id missing for {character_id}")


def get_character_image_name(character_id: str, emotion: str = "normal") -> Optional[str]:
    """characters.json の images マップからファイル名を返す。未定義なら None（みのり従来アセットへフォールバック）。"""
    try:
        char = get_character(character_id)
    except KeyError:
        return None
    images = char.get("images") or {}
    if not images:
        return None
    if emotion in images:
        return str(images[emotion])
    if "normal" in images:
        return str(images["normal"])
    # 最初の定義を使う
    for val in images.values():
        if val:
            return str(val)
    return None


__all__ = [
    "characters_config_path",
    "load_characters",
    "get_character",
    "get_voicevox_speaker_id",
    "get_character_image_name",
]
