"""直近動画で扱ったニューストピックを保存し、Novelty（重複排除）に使う。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional


def _default_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(here, "..", ".."))
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "recent_news_topics.json")


def load_recent_topics(path: Optional[str] = None, *, limit: int = 30) -> List[str]:
    """直近トピック文字列のリスト（新しい順）。"""
    if path is None:
        path = _default_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries") or []
        topics: List[str] = []
        for e in entries[:limit]:
            for t in e.get("topics") or []:
                if t and t not in topics:
                    topics.append(t)
        return topics
    except Exception:
        return []


def save_topics_for_video(
    topics: List[str],
    *,
    video_type: str = "",
    path: Optional[str] = None,
) -> None:
    """今回採用したトピックを履歴先頭に保存。"""
    if path is None:
        path = _default_path()
    cleaned = [str(t).strip() for t in topics if t and str(t).strip()]
    if not cleaned:
        return

    data: Dict = {"entries": []}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"entries": []}

    entries = data.get("entries") or []
    entries.insert(
        0,
        {
            "saved_at": datetime.now().isoformat(),
            "video_type": video_type,
            "topics": cleaned,
        },
    )
    data["entries"] = entries[:20]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


__all__ = ["load_recent_topics", "save_topics_for_video"]
