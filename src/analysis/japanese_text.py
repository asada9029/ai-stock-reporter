"""画面表示テキストの日本語判定・正規化。

字幕・OST が英語全文になると視聴体験が壊れるため、
表示用 `text` が英語寄りなら `speech_text`（日本語）へフォールバックする。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

# ティッカー・指数略称など、英字のまま許容する短いトークン
_ALLOWED_LATIN_TOKEN = re.compile(
    r"^(?:S&P500|NASDAQ|NYSE|DOW|VIX|CPI|GDP|FOMC|ISM|JOLTS|ETF|ADR|"
    r"[A-Z]{1,5}|[A-Z]{1,5}\.[A-Z]|[0-9]{3,4})$",
    re.IGNORECASE,
)
_SPEAKER_EN_PREFIX = re.compile(
    r"^\s*(?:Minori|Karin|Host|Narrator)\s*[:：]\s*",
    re.IGNORECASE,
)


def cjk_ratio(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    cjk = sum(
        1
        for ch in t
        if ("\u3040" <= ch <= "\u30ff")
        or ("\u4e00" <= ch <= "\u9fff")
        or ("\uff66" <= ch <= "\uff9d")  # 半角カナ
    )
    return cjk / max(1, len(t))


def _latin_letter_count(text: str) -> int:
    return sum(1 for ch in text if ("a" <= ch.lower() <= "z"))


def looks_like_ticker_label(text: str) -> bool:
    """短い指数・ティッカー表記（S&P500 +0.3% 等）は英語混在を許容。"""
    t = (text or "").strip()
    if not t or len(t) > 28:
        return False
    # 数字/%が中心で短い
    if re.fullmatch(r"[A-Za-z0-9&+\-.%/\s()（）]+", t) and len(t) <= 20:
        return True
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&.]*", t)
    if not tokens:
        return False
    return all(_ALLOWED_LATIN_TOKEN.match(tok) for tok in tokens) and len(t) <= 28


def is_mostly_english_display(text: str, *, min_len: int = 12) -> bool:
    """
    字幕・本文として「英語全文」とみなすか。
    「NVIDIAが急騰」のような日英混在は False。
    「Hello, everyone! Welcome...」のような英語全文は True。
    """
    t = _SPEAKER_EN_PREFIX.sub("", str(text or "").strip())
    if len(t) < min_len:
        return False
    if looks_like_ticker_label(t):
        return False

    cjk = sum(
        1
        for ch in t
        if ("\u3040" <= ch <= "\u30ff")
        or ("\u4e00" <= ch <= "\u9fff")
        or ("\uff66" <= ch <= "\uff9d")
    )
    latin = _latin_letter_count(t)
    if latin < 8:
        return False

    # 日本語が1文字以上入っている見出し・説明は、英語全文とはみなさない
    # （例: NVIDIA (NVDA): 8.74%急騰）
    if cjk >= 2:
        # ただし英語長文に日本語が少し添えられている場合は英語扱い
        if latin >= max(28, cjk * 8):
            return True
        return False

    # ほぼラテン文字のみ
    return True


def prefer_japanese_display(display: str, speech: str) -> str:
    """表示用が英語なら読み上げ用（日本語）を優先。"""
    d = str(display or "").strip()
    s = str(speech or "").strip()
    if not d:
        return s
    if is_mostly_english_display(d) and s and not is_mostly_english_display(s, min_len=8):
        return s
    if is_mostly_english_display(d) and s:
        # speech も英語っぽい場合はそのまま（保険なし）
        return s if cjk_ratio(s) >= cjk_ratio(d) else d
    return d


def _normalize_ost_line(line: str) -> str:
    t = str(line or "").strip()
    if not t:
        return ""
    # 英語話者プレフィックス除去
    t = _SPEAKER_EN_PREFIX.sub("", t).strip()
    if is_mostly_english_display(t, min_len=10) and not looks_like_ticker_label(t):
        return ""
    return t


def normalize_scene_japanese_display(scene: Dict[str, Any]) -> bool:
    """
    1シーンの text / dialogue / on_screen_text を日本語表示向けに正規化。
    変更があれば True。
    """
    changed = False
    speech = str(scene.get("speech_text") or "").strip()
    text = str(scene.get("text") or "").strip()
    preferred = prefer_japanese_display(text, speech)
    if preferred and preferred != text:
        scene["text"] = preferred
        changed = True

    dialogue = scene.get("dialogue")
    if isinstance(dialogue, list):
        for line in dialogue:
            if not isinstance(line, dict):
                continue
            d_text = str(line.get("text") or "").strip()
            d_speech = str(line.get("speech_text") or "").strip()
            d_pref = prefer_japanese_display(d_text, d_speech)
            if d_pref and d_pref != d_text:
                line["text"] = d_pref
                changed = True

    ost = scene.get("on_screen_text")
    if isinstance(ost, str):
        ost = [ost]
    if isinstance(ost, list):
        new_ost: List[str] = []
        for ln in ost:
            fixed = _normalize_ost_line(str(ln))
            if fixed:
                new_ost.append(fixed)
            elif str(ln).strip() and fixed != str(ln).strip():
                changed = True
        if new_ost != [str(x).strip() for x in ost if str(x).strip()]:
            scene["on_screen_text"] = new_ost
            changed = True

    return changed


def normalize_scenes_japanese_display(scenes: Sequence[Dict[str, Any]]) -> int:
    """全シーンを正規化し、変更したシーン数を返す。"""
    n = 0
    for sc in scenes:
        if isinstance(sc, dict) and normalize_scene_japanese_display(sc):
            n += 1
    return n


def count_english_display_issues(scenes: Sequence[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """品質チェック用: 英語表示が残っている箇所を数える。"""
    issues: List[str] = []
    count = 0
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        scene_no = sc.get("scene", i + 1)
        text = str(sc.get("text") or "")
        if is_mostly_english_display(text):
            count += 1
            issues.append(f"scene{scene_no}: text が英語寄り")
        ost = sc.get("on_screen_text") or []
        if isinstance(ost, str):
            ost = [ost]
        for ln in ost:
            if is_mostly_english_display(str(ln), min_len=14):
                count += 1
                issues.append(f"scene{scene_no}: on_screen_text が英語寄り ({str(ln)[:24]}…)")
                break
        dialogue = sc.get("dialogue")
        if isinstance(dialogue, list):
            for line in dialogue:
                if isinstance(line, dict) and is_mostly_english_display(str(line.get("text") or "")):
                    count += 1
                    issues.append(f"scene{scene_no}: dialogue.text が英語寄り")
                    break
    return count, issues
