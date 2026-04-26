import os
import json
from datetime import datetime
from typing import List, Dict, Optional


def _default_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(here, "..", ".."))
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "previous_videos.json")


def load_all_metadata(path: Optional[str] = None) -> Dict:
    """
    全履歴を読み込む。ファイルがなければ空の構造を返す。
    """
    if path is None:
        path = _default_path()
    if not os.path.exists(path):
        return {"latest": None, "history": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"latest": None, "history": []}


def load_latest_metadata(path: Optional[str] = None) -> Optional[Dict]:
    data = load_all_metadata(path)
    return data.get("latest")


def save_video_metadata(video_id: str, published_at: str, ir_stocks: List[Dict], path: Optional[str] = None) -> None:
    """
    video_id: 任意のID（例: タイムスタンプ）
    published_at: ISO形式の日時文字列
    ir_stocks: [{"name": "...", "ticker": "...", "noted_ir": "...", "ir_date": "..."} , ...]
    """
    if path is None:
        path = _default_path()

    data = load_all_metadata(path)
    entry = {
        "video_id": video_id,
        "published_at": published_at,
        "ir_stocks": ir_stocks
    }

    # 最新を更新して履歴に追加（履歴は上書きで先頭に追加）
    history = data.get("history", [])
    if data.get("latest"):
        history.insert(0, data["latest"])
    data["latest"] = entry
    data["history"] = history

    # 履歴の上限設定（直近14件 = 約1週間分、朝夜2回想定）
    MAX_HISTORY = 14
    if len(data["history"]) > MAX_HISTORY:
        data["history"] = data["history"][:MAX_HISTORY]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


__all__ = ["load_all_metadata", "load_latest_metadata", "save_video_metadata"]

