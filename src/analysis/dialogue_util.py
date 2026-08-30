"""二人掛け合い台本の正規化。声IDは characters.json 経由で差し替え可能。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.config.characters import get_voicevox_speaker_id

ALLOWED_SPEAKERS = ("minori", "karin")


def normalize_speaker_id(raw: Any, default: str = "minori") -> str:
    s = str(raw or "").strip().lower()
    if s in ("みのり", "minori", "host"):
        return "minori"
    if s in ("カリン", "かりん", "karin", "partner"):
        return "karin"
    if s in ALLOWED_SPEAKERS:
        return s
    return default if default in ALLOWED_SPEAKERS else "minori"


def resolve_voicevox_id(character_id: str) -> int:
    try:
        return get_voicevox_speaker_id(character_id)
    except Exception:
        return 2 if character_id == "minori" else 8


def expand_scene_speech_units(scene: Dict) -> List[Dict[str, Any]]:
    """
    シーンから読み上げ単位のリストを返す。
    各要素: {speaker, text, speech_text}
    dialogue があればそれを優先。なければ scene 単位。
    """
    dialogue = scene.get("dialogue")
    units: List[Dict[str, Any]] = []
    if isinstance(dialogue, list) and dialogue:
        for line in dialogue:
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            speech = str(line.get("speech_text") or text).strip()
            if not speech and not text:
                continue
            units.append(
                {
                    "speaker": normalize_speaker_id(line.get("speaker"), scene.get("speaker") or "minori"),
                    "text": text or speech,
                    "speech_text": speech or text,
                }
            )
    if units:
        return units

    text = str(scene.get("text") or "").strip()
    speech = str(scene.get("speech_text") or text).strip()
    if not speech and not text:
        return []
    return [
        {
            "speaker": normalize_speaker_id(scene.get("speaker"), "minori"),
            "text": text or speech,
            "speech_text": speech or text,
        }
    ]


def primary_speaker_for_scene(scene: Dict) -> str:
    units = expand_scene_speech_units(scene)
    if not units:
        return normalize_speaker_id(scene.get("speaker"), "minori")
    # 最後に話した人（掛け合いの反応側）より、発話量が多い方を優先
    counts: Dict[str, int] = {}
    for u in units:
        sp = u["speaker"]
        counts[sp] = counts.get(sp, 0) + len(u.get("speech_text") or "")
    return max(counts.items(), key=lambda kv: kv[1])[0]


__all__ = [
    "ALLOWED_SPEAKERS",
    "normalize_speaker_id",
    "resolve_voicevox_id",
    "expand_scene_speech_units",
    "primary_speaker_for_scene",
]
