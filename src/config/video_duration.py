"""
横型本編（朝・夜）の尺ポリシー。

video_structure.json の total_duration / セクション配分と
LLM 台本プロンプトの「尺の確保」指示は、このモジュールの値を単一の真実源とする。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# 本編共通: LLM・構成案に渡す目標尺（実際の動画はこれより短くなりがちなため 20 分で指示）
TARGET_SECONDS_HORIZONTAL = 1200  # 20分

# 台本生成の LLM 呼び出し上限（尺不足リトライ含む）
SCRIPT_GENERATION_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class SectionRequirement:
    """section_title に含まれるべきキーワードのいずれかでセクション出現を判定。"""

    key: str
    label: str
    keywords: Tuple[str, ...]
    optional: bool = False


@dataclass(frozen=True)
class VideoDurationPolicy:
    video_type: str
    target_seconds: int
    min_publish_seconds: int
    min_scenes: int
    min_speech_chars: int
    required_sections: Tuple[SectionRequirement, ...]


def target_minutes() -> int:
    return TARGET_SECONDS_HORIZONTAL // 60


def format_duration_prompt_rule() -> str:
    """LLM プロンプト用の「尺の確保」1行。"""
    sec = TARGET_SECONDS_HORIZONTAL
    mins = sec // 60
    return (
        f"- 【尺の確保】: 動画構成案の total_duration（{sec}秒＝{mins}分）に沿い、"
        f"全体で **{mins}分（{sec}秒）** の読み上げ量を目標にしてください。"
        f"各セクションの duration 配分も構成案どおりにシーンを十分な数だけ分割してください。"
        f"長すぎる冗長な繰り返しは避け、重要論点を優先して密度高くまとめてください。"
    )


def scale_section_durations(
    sections: List[dict], target_total: int = TARGET_SECONDS_HORIZONTAL
) -> List[dict]:
    """既存セクションの比率を保ったまま total を target_total に再スケール。"""
    if not sections:
        return sections
    old_total = sum(int(s.get("duration", 0)) for s in sections)
    if old_total <= 0:
        return sections
    scaled: List[dict] = []
    remain = target_total
    for i, sec in enumerate(sections):
        if i == len(sections) - 1:
            new_dur = max(1, remain)
        else:
            new_dur = max(1, round(int(sec.get("duration", 0)) * target_total / old_total))
            remain -= new_dur
        scaled.append({**sec, "duration": new_dur})
    return scaled


_MORNING_SECTIONS: Tuple[SectionRequirement, ...] = (
    SectionRequirement("opening", "opening（本日のトピック）", ("本日のトピック", "opening")),
    SectionRequirement(
        "us_market_summary",
        "米国市場指数",
        ("米国市場指数", "us_market", "market_summary", "S&P", "ナスダック", "ダウ"),
    ),
    SectionRequirement(
        "us_news_highlights",
        "米国注目ニュース",
        ("米国注目ニュース", "us_news", "news_highlights", "注目ニュース"),
    ),
    SectionRequirement(
        "us_sector_analysis",
        "米国セクター分析",
        ("米国セクター", "us_sector", "sector_analysis", "セクター分析"),
    ),
    SectionRequirement(
        "japan_impact_prediction",
        "日本市場への影響予測",
        ("日本市場", "japan_impact", "影響予測"),
    ),
    SectionRequirement("closing", "まとめ（closing）", ("まとめ", "closing")),
)

_EVENING_SECTIONS: Tuple[SectionRequirement, ...] = (
    SectionRequirement("opening", "opening（本日のトピック）", ("本日のトピック", "opening")),
    SectionRequirement(
        "market_indices",
        "市場指数",
        ("市場指数", "market_indices", "日経", "NIKKEI", "S&P"),
    ),
    SectionRequirement(
        "news_highlights",
        "注目ニュース",
        ("注目ニュース", "news_highlights"),
    ),
    SectionRequirement(
        "event_calendar",
        "決算・株主総会スケジュール",
        ("決算", "株主総会", "event_calendar", "スケジュール", "カレンダー"),
    ),
    SectionRequirement(
        "sector_overview",
        "セクター概要",
        ("セクター概要", "sector_overview"),
    ),
    SectionRequirement(
        "sector_attention",
        "注目セクター・銘柄",
        ("注目セクター", "sector_attention", "注目銘柄"),
    ),
    SectionRequirement(
        "prev_ir_tracking",
        "前回紹介銘柄の動向",
        ("前回紹介", "prev_ir", "ir_tracking", "紹介銘柄"),
        optional=True,
    ),
    SectionRequirement(
        "tomorrow_strategy",
        "今夜の米国市場と明日の展望",
        ("明日の展望", "tomorrow", "米国市場", "展望", "strategy"),
    ),
    SectionRequirement("closing", "まとめ（closing）", ("まとめ", "closing")),
)

_POLICIES: Dict[str, VideoDurationPolicy] = {
    "morning_video": VideoDurationPolicy(
        video_type="morning_video",
        target_seconds=TARGET_SECONDS_HORIZONTAL,
        min_publish_seconds=420,  # 7分未満は再生成
        min_scenes=20,
        min_speech_chars=6000,
        required_sections=_MORNING_SECTIONS,
    ),
    "evening_video": VideoDurationPolicy(
        video_type="evening_video",
        target_seconds=TARGET_SECONDS_HORIZONTAL,
        min_publish_seconds=540,  # 9分未満は再生成
        min_scenes=25,
        min_speech_chars=8000,
        required_sections=_EVENING_SECTIONS,
    ),
}


def get_duration_policy(video_type: str) -> Optional[VideoDurationPolicy]:
    if "morning" in video_type:
        return _POLICIES["morning_video"]
    if "evening" in video_type and "shorts" not in video_type:
        return _POLICIES["evening_video"]
    return None


def apply_duration_policy_to_structure(video_structure: dict) -> dict:
    """video_structure の total_duration と各セクション duration をポリシーに合わせる。"""
    policy = get_duration_policy(video_structure.get("video_type", ""))
    if not policy:
        return video_structure
    sections = video_structure.get("sections") or []
    return {
        **video_structure,
        "total_duration": policy.target_seconds,
        "sections": scale_section_durations(sections, policy.target_seconds),
    }
