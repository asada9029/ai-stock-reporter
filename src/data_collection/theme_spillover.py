"""動画向けテーマ波及ナレッジ（薄い自前正本）。

いいとこどり:
  - related 強弱（波及の根拠）
  - aliases（ニュースがどのテーマか当てる補助）

やらないこと:
  - watchflow の巨大 themes / 決算カレンダーを正本にしない
  - 売買推奨
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_PATH = PROJECT_ROOT / "data" / "knowledge" / "theme_spillover.json"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def load_theme_spillover_master() -> Optional[Dict[str, Any]]:
    """動画側正本。無ければ None。"""
    return _load_json(KNOWLEDGE_PATH)


def build_theme_bridge_for_script(
    raw: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """台本用の薄い theme_bridge。正本は data/knowledge/theme_spillover.json。"""
    data = raw if raw is not None else load_theme_spillover_master()
    if not data:
        return None

    edges = data.get("related_edges")
    if not isinstance(edges, list):
        edges = []
    clean_edges: List[Dict[str, str]] = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        frm = str(e.get("from") or "").strip()
        to = str(e.get("to") or "").strip()
        weight = str(e.get("weight") or "").strip()
        if frm and to and weight in ("strong", "weak"):
            clean_edges.append({"from": frm, "to": to, "weight": weight})

    themes_in = data.get("themes") or {}
    themes_out: Dict[str, Any] = {}
    if isinstance(themes_in, dict):
        for name, meta in themes_in.items():
            row: Dict[str, Any] = {}
            if isinstance(meta, dict):
                if meta.get("label"):
                    row["label"] = str(meta["label"])
                # 代表銘柄は任意。正本に無くてもよい（メンテ負荷を増やさない）
                core = meta.get("core_members") or []
                if isinstance(core, list) and core:
                    row["core_members"] = [
                        {
                            "code": str(m.get("code") or ""),
                            "name": str(m.get("name") or ""),
                        }
                        for m in core[:6]
                        if isinstance(m, dict) and m.get("code")
                    ]
            themes_out[str(name)] = row

    aliases = data.get("aliases") or {}
    if not isinstance(aliases, dict):
        aliases = {}

    if not clean_edges and not themes_out:
        return None

    return {
        "note": data.get("note")
        or "動画側正本。related.strong のみ本命波及、weak は参考。売買推奨ではない。",
        "source": "data/knowledge/theme_spillover.json",
        "owner": data.get("owner") or "ai-stock-reporter",
        "updated_at": data.get("updated_at"),
        "related_edges": clean_edges,
        "themes": themes_out,
        "aliases": {str(k): list(v) for k, v in aliases.items() if isinstance(v, list)},
    }


def load_theme_aliases() -> Dict[str, List[str]]:
    """news_selector 向け。テーマ名 → 別名リスト。"""
    master = load_theme_spillover_master() or {}
    aliases = master.get("aliases") or {}
    out: Dict[str, List[str]] = {}
    if isinstance(aliases, dict):
        for k, v in aliases.items():
            if isinstance(v, list) and k:
                cleaned = [str(x).strip().lower() for x in v if str(x).strip()]
                if cleaned:
                    out[str(k)] = cleaned
    return out


def attach_theme_spillover(aggregated_data: Dict[str, Any]) -> Dict[str, Any]:
    """analysis_data に theme_bridge を付与。earnings は付けない（動画側で自前収集済み）。"""
    theme = build_theme_bridge_for_script()
    if theme:
        aggregated_data["theme_bridge"] = theme
    # 旧キーが残っていたら落とす（古決算スナップショットを台本に混ぜない）
    aggregated_data.pop("earnings_bridge", None)
    return aggregated_data


# 後方互換
attach_watchflow_bridges = attach_theme_spillover


__all__ = [
    "attach_theme_spillover",
    "attach_watchflow_bridges",
    "build_theme_bridge_for_script",
    "load_theme_aliases",
    "load_theme_spillover_master",
]
