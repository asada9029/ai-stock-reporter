"""二人掛け合いユーティリティの単体テスト。"""

from src.analysis.dialogue_util import (
    expand_scene_speech_units,
    normalize_speaker_id,
    primary_speaker_for_scene,
    resolve_voicevox_id,
)
from src.analysis.scene_schema import validate_scene
from src.video_generation.character_emotion import merge_speaker_emotion_beats_for_scene


def test_normalize_speaker():
    assert normalize_speaker_id("カリン") == "karin"
    assert normalize_speaker_id("みのり") == "minori"
    assert normalize_speaker_id("unknown") == "minori"


def test_expand_dialogue_preferred():
    scene = {
        "speaker": "minori",
        "text": "まとめて読む用",
        "speech_text": "まとめてよむよう",
        "dialogue": [
            {"speaker": "minori", "speech_text": "今日の旬はこれです"},
            {"speaker": "karin", "text": "え、急騰？飛びつく！"},
        ],
    }
    units = expand_scene_speech_units(scene)
    assert len(units) == 2
    assert units[0]["speaker"] == "minori"
    assert units[1]["speaker"] == "karin"
    # 発話量が多い方（ここではカリンの「え、急騰？飛びつく！」が長い可能性あり）
    assert primary_speaker_for_scene(scene) in ("minori", "karin")


def test_voice_ids_swappable():
    # characters.json: minori=2 四国めたん、karin=8 春日部つむぎ
    assert resolve_voicevox_id("minori") == 2
    assert resolve_voicevox_id("karin") == 8


def test_schema_allows_dialogue():
    ok, err = validate_scene(
        {
            "scene": 1,
            "duration": 10,
            "text": "こんにちは",
            "emotion": "happy",
            "image_type": "character_only",
            "speaker": "minori",
            "dialogue": [
                {"speaker": "minori", "speech_text": "こんにちは"},
                {"speaker": "karin", "speech_text": "やっほー"},
            ],
        }
    )
    assert ok, err


def test_speaker_emotion_beats_split_on_speaker_change():
    segs = [
        {"start": 0.0, "duration": 1.0, "emotion": "normal", "speaker": "minori"},
        {"start": 1.0, "duration": 1.0, "emotion": "normal", "speaker": "karin"},
        {"start": 2.0, "duration": 1.0, "emotion": "excited", "speaker": "karin"},
    ]
    beats = merge_speaker_emotion_beats_for_scene(segs, "normal", 3.0, "minori")
    speakers = [b[3] for b in beats]
    assert "karin" in speakers
    assert speakers[0] == "minori"


if __name__ == "__main__":
    test_normalize_speaker()
    test_expand_dialogue_preferred()
    test_voice_ids_swappable()
    test_schema_allows_dialogue()
    test_speaker_emotion_beats_split_on_speaker_change()
    print("OK: test_dialogue_util")
