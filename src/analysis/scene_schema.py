from typing import List, Dict, Tuple

ALLOWED_EMOTIONS = {"normal", "happy", "surprised", "sad", "confident", "angry", "disappointed", "excited"}
ALLOWED_IMAGE_TYPES = {"chart", "character_only", "bg_only", "news_panel", "chart_with_annotation"}
ALLOWED_SPEAKERS = {"minori", "karin"}


def validate_scene(scene: Dict) -> Tuple[bool, str]:
    """
    単一シーンのバリデーション。
    戻り値: (is_valid, error_message)
    """
    if not isinstance(scene, dict):
        return False, "scene must be an object"
    required = ["scene", "duration", "text", "emotion", "image_type"]
    # section_title と on_screen_text はオプションだが、LLMには出力を促しているためバリデーションは通す
    for k in required:
        if k not in scene:
            return False, f"missing required key: {k}"
    if not isinstance(scene["scene"], int):
        return False, "scene must be integer"
    if not (isinstance(scene["duration"], int) or isinstance(scene["duration"], float)):
        return False, "duration must be number"
    if not isinstance(scene["text"], str):
        return False, "text must be string"
    if scene["emotion"] not in ALLOWED_EMOTIONS:
        return False, f"emotion must be one of {sorted(ALLOWED_EMOTIONS)}"
    if scene["image_type"] not in ALLOWED_IMAGE_TYPES:
        return False, f"image_type must be one of {sorted(ALLOWED_IMAGE_TYPES)}"
    # speaker / dialogue は任意（掛け合い拡張）
    if "speaker" in scene and scene["speaker"] is not None:
        sp = str(scene["speaker"]).strip().lower()
        if sp and sp not in ALLOWED_SPEAKERS:
            return False, f"speaker must be one of {sorted(ALLOWED_SPEAKERS)}"
    if "dialogue" in scene and scene["dialogue"] is not None:
        if not isinstance(scene["dialogue"], list):
            return False, "dialogue must be an array"
        for di, line in enumerate(scene["dialogue"]):
            if not isinstance(line, dict):
                return False, f"dialogue[{di}] must be an object"
            lsp = str(line.get("speaker") or "").strip().lower()
            if lsp and lsp not in ALLOWED_SPEAKERS:
                return False, f"dialogue[{di}].speaker must be one of {sorted(ALLOWED_SPEAKERS)}"
            if not (line.get("text") or line.get("speech_text")):
                return False, f"dialogue[{di}] needs text or speech_text"
    return True, ""


def validate_scene_list(scenes) -> Tuple[bool, List[str]]:
    """
    シーン配列のバリデーション。エラーリストを返す。
    """
    errors: List[str] = []
    if not isinstance(scenes, list):
        return False, ["root must be a JSON array"]
    for idx, sc in enumerate(scenes):
        ok, err = validate_scene(sc)
        if not ok:
            errors.append(f"index {idx}: {err}")
    return (len(errors) == 0), errors


__all__ = [
    "validate_scene_list",
    "validate_scene",
    "ALLOWED_EMOTIONS",
    "ALLOWED_IMAGE_TYPES",
    "ALLOWED_SPEAKERS",
]

