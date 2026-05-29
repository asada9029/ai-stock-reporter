"""
シーン内の感情切り替えタイミング（音声セグメント基準）とキャラクターアニメーション。
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from src.analysis.scene_schema import ALLOWED_EMOTIONS

# 読み上げ文からの感情推定（音声認識は使わない。句ごとのテキスト＋VOICEVOXの start/duration で同期）
_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "好調", "続伸", "上昇", "反発", "堅調", "好決算", "追い風", "明るい", "改善",
        "最高値", "上値", "買い優勢", "好材料", "増益", "回復",
    ],
    "excited": [
        "急騰", "大幅高", "歴史的", "史上", "サプライズ好材料", "爆発", "過去最高",
    ],
    "sad": [
        "下落", "急落", "大幅安", "低迷", "悪化", "売り優勢", "不安", "懸念", "慎重",
        "減益", "赤字", "苦戦", "売り", "押し下げ",
    ],
    "disappointed": [
        "失望", "想定下振れ", "材料不足", "後退", "弱含み", "伸び悩", "失速", "利益確定",
    ],
    "surprised": [
        "意外", "想定外", "サプライズ", "突如", "急変", "まさか", "びっくり",
    ],
    "angry": [
        "許せない", "強く批判", "怒り", "問題視", "非難",
    ],
    "confident": [
        "見込み", "と見ています", "期待", "見通し", "おそらく", "可能性が高い",
        "押し上げ", "牽引", "主役",
    ],
}

# この秒数未満のセグメントはアニメを出さず normal 扱い（音声が極端に短い句）
MIN_SEGMENT_EMOTION_DURATION = 0.75

# 感情ごとのアニメーション再生時間（秒）。終了後は base 位置に戻る。
_ANIM_DURATION: Dict[str, float] = {
    "happy": 1.5,
    "excited": 1.6,
    "sad": 1.4,
    "disappointed": 1.2,
    "surprised": 0.95,
    "angry": 1.0,
    "confident": 1.2,
    "normal": 0.0,
}


def normalize_emotion(emotion: Optional[str], default: str = "normal") -> str:
    if emotion in ALLOWED_EMOTIONS:
        return emotion
    return default if default in ALLOWED_EMOTIONS else "normal"


def _bounce_dy(t: float, *, amp: float, bounces: float, duration: float) -> float:
    """ゆっくり 2〜3 回跳ねて、終了時に y=0 へ戻る。"""
    if t >= duration:
        return 0.0
    p = t / duration
    envelope = math.sin(math.pi * p)
    wave = abs(math.sin(2 * math.pi * bounces * p))
    return -amp * wave * envelope


def _sink_dy(t: float, *, cap: float, duration: float) -> float:
    """ずーん（下へ）→ 自然に元の高さへ。"""
    if t >= duration:
        return 0.0
    p = t / duration
    if p < 0.4:
        sink_p = p / 0.4
        return cap * (1.0 - math.cos(math.pi * sink_p / 2))
    ret_p = (p - 0.4) / 0.6
    peak = cap
    return peak * (1.0 - ret_p) ** 2


def _surprise_dx(t: float, *, pull: float, duration: float) -> float:
    """驚き: 右へ引く → 元位置へ。"""
    if t >= duration:
        return 0.0
    p = t / duration
    if p < 0.3:
        return pull * (p / 0.3)
    ret_p = (p - 0.3) / 0.7
    return pull * (1.0 - ret_p ** 2)


def _purupuru(t: float, *, amp: float, duration: float) -> Tuple[float, float]:
    """怒り: ぷるぷる（減衰振動）→ 静止。"""
    if t >= duration:
        return 0.0, 0.0
    decay = math.exp(-5.0 * t / duration)
    wx = math.sin(2 * math.pi * 16 * t)
    wy = math.sin(2 * math.pi * 20 * t + 0.6)
    return amp * decay * wx, amp * 0.55 * decay * wy


def _sway_dy(t: float, *, amp: float, duration: float) -> float:
    """自信: 短いゆらゆら → 静止。"""
    if t >= duration:
        return 0.0
    p = t / duration
    envelope = math.sin(math.pi * p)
    return -amp * math.sin(2 * math.pi * 1.0 * p) * envelope


def emotion_offset(t: float, emotion: str) -> Tuple[float, float]:
    """clip ローカル時間 t における (dx, dy)。アニメ終了後は (0, 0)。"""
    emotion = normalize_emotion(emotion)
    t = float(t)

    if emotion == "happy":
        dy = _bounce_dy(t, amp=18, bounces=2.5, duration=_ANIM_DURATION["happy"])
        return 0.0, dy
    if emotion == "excited":
        dy = _bounce_dy(t, amp=24, bounces=3.0, duration=_ANIM_DURATION["excited"])
        return 0.0, dy
    if emotion == "sad":
        dy = _sink_dy(t, cap=48, duration=_ANIM_DURATION["sad"])
        return 0.0, dy
    if emotion == "disappointed":
        dy = _sink_dy(t, cap=36, duration=_ANIM_DURATION["disappointed"])
        return 0.0, dy
    if emotion == "surprised":
        dx = _surprise_dx(t, pull=42, duration=_ANIM_DURATION["surprised"])
        return dx, 0.0
    if emotion == "angry":
        return _purupuru(t, amp=6.5, duration=_ANIM_DURATION["angry"])
    if emotion == "confident":
        dy = _sway_dy(t, amp=5, duration=_ANIM_DURATION["confident"])
        return 0.0, dy
    return 0.0, 0.0


def apply_emotion_motion(clip, emotion: str, base_x: int, base_y: int):
    """感情に応じた位置アニメーション（終了後は base に戻る）。"""

    def pos(t):
        dx, dy = emotion_offset(float(t), emotion)
        return (base_x + dx, base_y + dy)

    return clip.with_position(pos)


def rough_speech_clauses(speech: str) -> List[str]:
    """VOICEVOX 分割と同系統の句切れ（台本段階の timeline 目安）。"""
    speech = (speech or "").strip()
    if not speech:
        return []
    parts = re.split(r"([。、！？!?])", speech)
    combined: List[str] = []
    for i in range(0, len(parts) - 1, 2):
        combined.append(parts[i] + parts[i + 1])
    if len(parts) % 2 == 1 and parts[-1].strip():
        combined.append(parts[-1])
    return [p.strip() for p in combined if p.strip()]


def infer_emotion_from_text(text: str, *, default: str = "normal") -> str:
    """読み上げテキスト1句から感情を推定。該当なしは normal。"""
    text = (text or "").strip()
    if not text:
        return normalize_emotion(default)

    scores: Dict[str, int] = {k: 0 for k in _EMOTION_KEYWORDS}
    for em, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[em] += 1

    best_em = max(scores, key=lambda k: scores[k])
    if scores[best_em] < 1:
        return "normal"
    return normalize_emotion(best_em, default)


def build_emotion_timeline_from_speech(
    speech: str, *, scene_default: str = "normal"
) -> List[Dict]:
    """句ごとに推定し、変化点だけ emotion_timeline を作る。"""
    clauses = rough_speech_clauses(speech)
    if len(clauses) < 2:
        return []

    timeline: List[Dict] = []
    prev: Optional[str] = None
    for i, clause in enumerate(clauses):
        em = infer_emotion_from_text(clause, default=scene_default)
        if em != prev:
            timeline.append({"segment_index": i, "emotion": em})
            prev = em
    return timeline


def enrich_emotion_timelines(scenes: List[Dict]) -> int:
    """
    LLM が timeline を出さなかったシーンに、speech_text から補完する。
    戻り値: 補完したシーン数。
    """
    enriched = 0
    for sc in scenes:
        if sc.get("mute") or sc.get("section_title") == "subscribe":
            continue
        if sc.get("emotion_timeline") or sc.get("segment_emotions"):
            continue

        speech = (sc.get("speech_text") or sc.get("text") or "").strip()
        if not speech:
            continue

        base = normalize_emotion(sc.get("emotion"))

        clauses = rough_speech_clauses(speech)
        if len(clauses) < 2:
            if base == "normal":
                inferred = infer_emotion_from_text(speech)
                if inferred != "normal":
                    sc["emotion"] = inferred
                    enriched += 1
            continue

        timeline = build_emotion_timeline_from_speech(speech, scene_default=base)
        if not timeline:
            if base == "normal":
                whole = infer_emotion_from_text(speech)
                if whole != "normal":
                    sc["emotion"] = whole
                    enriched += 1
            continue

        # 全体が normal だけの timeline は付けない
        emotions_used = {c["emotion"] for c in timeline}
        if emotions_used == {"normal"}:
            continue

        sc["emotion_timeline"] = timeline
        if base == "normal" and timeline[0]["emotion"] != "normal":
            sc["emotion"] = timeline[0]["emotion"]
        enriched += 1

    return enriched


def infer_segment_emotions_from_text(
    segments: List[Dict], *, scene_default: str = "normal"
) -> None:
    """音声生成後: 各 segment の読み上げ文から感情を付与（timeline 未指定時のフォールバック）。"""
    for seg in segments:
        if seg.get("emotion") in ALLOWED_EMOTIONS:
            continue
        text = (seg.get("text") or seg.get("speech_text") or "").strip()
        dur = float(seg.get("duration", 0.0))
        if dur > 0 and dur < MIN_SEGMENT_EMOTION_DURATION:
            seg["emotion"] = "normal"
            continue
        seg["emotion"] = infer_emotion_from_text(text, default=scene_default)


def _align_emotion_list(items: List, count: int, default: str) -> List[str]:
    if count <= 0:
        return []
    if not items:
        return [default] * count
    out: List[str] = []
    for i in range(count):
        em = items[i] if i < len(items) else items[-1]
        out.append(normalize_emotion(em, default))
    return out


def assign_segment_emotions(scene: Dict) -> None:
    """
    音声分割後の segments[] に emotion を付与する。
    優先: 各 segment 既存 emotion > segment_emotions > emotion_timeline > scene.emotion
    """
    segments = scene.get("segments") or []
    if not segments:
        return

    default = normalize_emotion(scene.get("emotion"))
    n = len(segments)

    if all(seg.get("emotion") in ALLOWED_EMOTIONS for seg in segments):
        return

    seg_list = scene.get("segment_emotions")
    if isinstance(seg_list, list) and seg_list:
        aligned = _align_emotion_list(seg_list, n, default)
        for seg, em in zip(segments, aligned):
            seg["emotion"] = em
        return

    timeline = scene.get("emotion_timeline")
    if isinstance(timeline, list) and timeline:
        emotions = _emotions_from_timeline(timeline, segments, default)
        for seg, em in zip(segments, emotions):
            seg["emotion"] = em
        return

    infer_segment_emotions_from_text(segments, scene_default=default)


def _emotions_from_timeline(
    timeline: List,
    segments: List[Dict],
    default: str,
) -> List[str]:
    n = len(segments)
    emotions = [default] * n

    indexed: List[Tuple[int, str]] = []
    for cue in timeline:
        if not isinstance(cue, dict):
            continue
        em = normalize_emotion(cue.get("emotion"), default)
        if "segment_index" in cue:
            try:
                idx = int(cue["segment_index"])
            except (TypeError, ValueError):
                continue
            if 0 <= idx < n:
                indexed.append((idx, em))
        elif cue.get("text"):
            hint = str(cue["text"]).strip()
            if not hint:
                continue
            for i, seg in enumerate(segments):
                hay = (seg.get("text") or "") + (seg.get("speech_text") or "")
                if hint in hay:
                    indexed.append((i, em))
                    break

    if not indexed:
        return emotions

    indexed.sort(key=lambda x: x[0])
    for seg_idx in range(n):
        em = default
        for start_idx, e in indexed:
            if seg_idx >= start_idx:
                em = e
        emotions[seg_idx] = em
    return emotions


def merge_emotion_beats(
    segments: List[Dict],
    default_emotion: str,
    padding_before: float = 0.0,
) -> List[Tuple[float, float, str]]:
    """(scene内相対開始秒, 尺, emotion) のリスト。連続同一感情はマージ。"""
    if not segments:
        return [(padding_before, 0.0, default_emotion)]

    beats: List[Tuple[float, float, str]] = []
    for seg in segments:
        start = float(seg.get("start", 0.0))
        dur = float(seg.get("duration", 0.0))
        if dur <= 0:
            continue
        em = normalize_emotion(seg.get("emotion"), default_emotion)
        beats.append((start, dur, em))

    if not beats:
        return [(0.0, 0.0, default_emotion)]

    merged: List[Tuple[float, float, str]] = []
    for start, dur, em in beats:
        if merged and merged[-1][2] == em:
            prev_start, prev_dur, _ = merged[-1]
            merged[-1] = (prev_start, prev_dur + dur, em)
        else:
            merged.append((start, dur, em))
    return merged


def merge_emotion_beats_for_scene(
    segments: List[Dict],
    default_emotion: str,
    total_scene_duration: float,
) -> List[Tuple[float, float, str]]:
    """シーン全体を覆うビート列（セグメント間の無音区間もデフォルト感情で埋める）。"""
    inner = merge_emotion_beats(segments, default_emotion)
    if not inner:
        return [(0.0, max(0.05, total_scene_duration), default_emotion)]

    out: List[Tuple[float, float, str]] = []
    cursor = 0.0
    for start, dur, em in inner:
        if start > cursor + 0.02:
            out.append((cursor, start - cursor, default_emotion))
        out.append((start, dur, em))
        cursor = start + dur

    if cursor < total_scene_duration - 0.02:
        tail_em = inner[-1][2]
        out.append((cursor, total_scene_duration - cursor, tail_em))

    merged_out: List[Tuple[float, float, str]] = []
    for start, dur, em in out:
        if merged_out and merged_out[-1][2] == em:
            ps, pd, _ = merged_out[-1]
            merged_out[-1] = (ps, pd + dur, em)
        else:
            merged_out.append((start, dur, em))
    return merged_out
