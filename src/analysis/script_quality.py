"""
台本 JSON の推定尺・セクション網羅チェックと、リトライ用プロンプト追記の生成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from src.config.video_duration import (
    VideoDurationPolicy,
    format_duration_prompt_rule,
    get_duration_policy,
    target_minutes,
)

# ScriptGenerator / structured_pipeline と同じ目安
_CHARS_PER_SECOND = 3.5
_DEFAULT_PADDING_BEFORE = 0.3
_DEFAULT_PADDING_AFTER = 0.3


@dataclass
class ScriptQualityReport:
    passed: bool
    estimated_seconds: float
    scene_count: int
    speech_char_count: int
    missing_sections: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = [
            f"推定尺={self.estimated_seconds:.0f}s",
            f"シーン数={self.scene_count}",
            f"speech文字数={self.speech_char_count}",
        ]
        if self.missing_sections:
            parts.append(f"欠落セクション={','.join(self.missing_sections)}")
        if self.issues:
            parts.append("; ".join(self.issues))
        return " / ".join(parts)

    def build_retry_appendix(self, policy: VideoDurationPolicy) -> str:
        """尺・構造不足時にプロンプト末尾へ足す追記。"""
        deficit_sec = max(0, policy.min_publish_seconds - self.estimated_seconds)
        deficit_min = deficit_sec / 60.0
        missing = self.missing_sections or ["（自動判定できず）"]
        return f"""

# 【前回出力の品質不足 — 以下を厳守して作り直してください】
- 前回の台本は推定読み上げ時間が約 {self.estimated_seconds:.0f} 秒で、最低ライン {policy.min_publish_seconds} 秒（{policy.min_publish_seconds // 60}分）を下回っていました。
- 不足分の目安: あと約 {deficit_min:.1f} 分以上の speech_text が必要です。
- シーン数: 前回 {self.scene_count} シーン → 最低 {policy.min_scenes} シーン以上に増やしてください。
- speech_text 合計文字数: 前回 {self.speech_char_count} 字 → 最低 {policy.min_speech_chars} 字以上にしてください。
- 動画全体の目標は引き続き **{target_minutes()}分（{policy.target_seconds}秒）** です。構成案の全セクションを省略せず、各セクションを複数シーンに分割してください。
- 特に次のセクションが不足または薄すぎます: {", ".join(missing)}
- 前回の JSON は捨てて、最初からフルの台本を生成し直してください。
{format_duration_prompt_rule()}
"""


def _speech_text_of(scene: dict) -> str:
    return str(scene.get("speech_text") or scene.get("text") or "")


def estimate_script_duration_seconds(
    scenes: Sequence[dict],
    *,
    chars_per_second: float = _CHARS_PER_SECOND,
    default_padding_before: float = _DEFAULT_PADDING_BEFORE,
    default_padding_after: float = _DEFAULT_PADDING_AFTER,
) -> float:
    """VOICEVOX 前の推定尺（speech_text 文字数 + シーン padding）。"""
    total = 0.0
    for sc in scenes:
        if sc.get("mute"):
            total += float(sc.get("duration", 0.0) or 0.0)
            continue
        speech = _speech_text_of(sc)
        pad_b = float(sc.get("padding_before", default_padding_before))
        pad_a = float(sc.get("padding_after", default_padding_after))
        speech_sec = len(speech) / chars_per_second if speech else 0.0
        total += pad_b + speech_sec + pad_a
    return total


def _detect_present_section_keys(
    scenes: Sequence[dict],
    policy: VideoDurationPolicy,
    *,
    skip_optional_keys: Optional[Set[str]] = None,
) -> Set[str]:
    skip = skip_optional_keys or set()
    present: Set[str] = set()
    for sc in scenes:
        title = str(sc.get("section_title", "") or "")
        title_lower = title.lower()
        for req in policy.required_sections:
            if req.key in skip and req.optional:
                continue
            if any(kw.lower() in title_lower for kw in req.keywords):
                present.add(req.key)
    return present


def evaluate_script_quality(
    scenes: Sequence[dict],
    video_type: str,
    *,
    skip_optional_section_keys: Optional[Set[str]] = None,
) -> Optional[ScriptQualityReport]:
    """
    横型本編向けの品質評価。ショート等は None（チェック不要）。
    """
    policy = get_duration_policy(video_type)
    if not policy:
        return None

    scene_list = list(scenes)
    estimated = estimate_script_duration_seconds(scene_list)
    speech_chars = sum(len(_speech_text_of(sc)) for sc in scene_list)
    scene_count = len(scene_list)

    skip_keys = skip_optional_section_keys or set()
    present = _detect_present_section_keys(
        scene_list, policy, skip_optional_keys=skip_keys
    )

    missing: List[str] = []
    for req in policy.required_sections:
        if req.optional and req.key in skip_keys:
            continue
        if req.key not in present:
            missing.append(req.label)

    issues: List[str] = []
    if estimated < policy.min_publish_seconds:
        issues.append(
            f"推定尺が不足（{estimated:.0f}s < 最低{policy.min_publish_seconds}s）"
        )
    if scene_count < policy.min_scenes:
        issues.append(
            f"シーン数が不足（{scene_count} < 最低{policy.min_scenes}）"
        )
    if speech_chars < policy.min_speech_chars:
        issues.append(
            f"speech_text 文字数が不足（{speech_chars} < 最低{policy.min_speech_chars}）"
        )
    if missing:
        issues.append(f"必須セクション欠落: {', '.join(missing)}")

    passed = not issues
    return ScriptQualityReport(
        passed=passed,
        estimated_seconds=estimated,
        scene_count=scene_count,
        speech_char_count=speech_chars,
        missing_sections=missing,
        issues=issues,
    )


def optional_section_keys_to_skip(analysis_data: dict, video_type: str) -> Set[str]:
    """データが無い、または台本に含めなくてよいセクションをチェック対象外にする。"""
    skip: Set[str] = set()
    if "evening" in video_type:
        # prev_ir はデータがあっても LLM が省略しがちなため常に任意扱い
        skip.add("prev_ir_tracking")
        prev = analysis_data.get("prev_ir_analysis") or []
        if not prev:
            pass  # 上記で既にスキップ
    return skip


__all__ = [
    "ScriptQualityReport",
    "estimate_script_duration_seconds",
    "evaluate_script_quality",
    "optional_section_keys_to_skip",
]
