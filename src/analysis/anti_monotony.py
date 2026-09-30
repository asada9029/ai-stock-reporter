"""脱マンネリ（本編の型繰り返し防止）。

売買推奨ではない。台本の多様性・差分駆動のための文脈付与と軽い検査。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- チェック3点の定型語（これだけで埋めない／台本でも避ける） ---
_CHECKLIST_STEREOTYPE_TERMS = (
    "金利",
    "為替",
    "ドル円",
    "半導体",
    "地合い",
    "指数反応",
    "寄り付き",
    "オープニング",
    "要人発言",
)

# 日替わりコーナー（骨格は固定、1枠だけローテ）
_CORNER_ROTATION: Tuple[Dict[str, str], ...] = (
    {
        "id": "priced_in",
        "label": "織り込み注意",
        "hint": "材料が出たあとの反応が選別になりやすいか、1シーンだけ短く。",
    },
    {
        "id": "sector_why",
        "label": "業種なぜ",
        "hint": "騰落上位／下位でいちばん違和感のある業種を1つ選び、「なぜ」を一言。",
    },
    {
        "id": "earnings_watch",
        "label": "決算ウォッチ",
        "hint": "直近決算があれば最大2件を監視ラベルで。無ければこの枠は省略可。",
    },
    {
        "id": "weak_theme",
        "label": "弱テーマ参考",
        "hint": "related の weak を『参考』として1語だけ。本命結論にしない。",
    },
    {
        "id": "diff_focus",
        "label": "昨日との違い",
        "hint": "資金の向きや本命材料が昨日と同じなら短く、違う点だけ厚く。",
    },
)

_RELATED_HISTORY_LIMIT = 12
_SECTOR_HISTORY_LIMIT = 10
_HOOK_HISTORY_LIMIT = 8


def _project_data_dir() -> Path:
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data


def _history_path(name: str) -> Path:
    return _project_data_dir() / name


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_daily_corner(*, today: Optional[date] = None) -> Dict[str, str]:
    d = today or date.today()
    idx = d.toordinal() % len(_CORNER_ROTATION)
    return dict(_CORNER_ROTATION[idx])


def checklist_stereotype_hits(texts: Sequence[str]) -> List[str]:
    blob = " ".join(str(t) for t in texts if t)
    return [t for t in _CHECKLIST_STEREOTYPE_TERMS if t in blob]


def is_stereotype_checklist(items: Sequence[str], *, min_hits: int = 2) -> bool:
    """3点のうち定型語が min_hits 以上ならマンネリ寄り。"""
    return len(checklist_stereotype_hits(items)) >= min_hits


def prefer_concrete_checklist_items(
    news: Sequence[Dict],
    outlook: Sequence[Dict],
    *,
    is_morning: bool,
    limit: int = 3,
) -> List[str]:
    """ニュース固有名詞優先のチェック項目。定型語だけの埋めは最後の手段。"""
    items: List[str] = []

    def _push(text: str) -> None:
        t = str(text or "").strip()
        if not t or t in items:
            return
        # 長すぎる見出しは短く
        if len(t) > 28:
            t = t[:27] + "…"
        items.append(t)

    for n in list(outlook)[:5]:
        if len(items) >= limit:
            break
        _push((n or {}).get("title") or "")

    for n in list(news)[:8]:
        if len(items) >= limit:
            break
        company = str((n or {}).get("related_company_name") or "").strip()
        tip = str((n or {}).get("why_now") or "").strip()
        title = str((n or {}).get("title_ja") or (n or {}).get("title") or "").strip()
        if company and tip:
            _push(f"{company}の反応")
        elif company:
            _push(f"{company}の寄り付き")
        elif tip:
            _push(tip)
        else:
            _push(title)

    # まだ足りないときだけ、定型ではなく「今日の固有」寄りフォールバック
    soft_defaults = (
        ["本命ニュースの個別反応", "為替より材料銘柄の選別", "今朝いちばん動いたテーマ"]
        if is_morning
        else ["今夜の本命イベント反応", "明日の材料銘柄の初動", "今日と違う資金の向き"]
    )
    for d in soft_defaults:
        if len(items) >= limit:
            break
        if d not in items:
            items.append(d)
    return items[:limit]


def load_recent_related_themes(*, limit: int = 8) -> List[str]:
    data = _load_json(_history_path("recent_related_themes.json"))
    themes: List[str] = []
    for e in (data.get("entries") or [])[:limit]:
        for t in e.get("themes") or []:
            if t and t not in themes:
                themes.append(str(t))
    return themes


def save_related_themes_for_video(
    themes: Sequence[str],
    *,
    video_type: str = "",
) -> None:
    cleaned = [str(t).strip() for t in themes if t and str(t).strip()]
    if not cleaned:
        return
    path = _history_path("recent_related_themes.json")
    data = _load_json(path)
    entries = list(data.get("entries") or [])
    now = datetime.now()
    row = {
        "saved_at": now.isoformat(timespec="seconds"),
        "video_type": video_type,
        "themes": cleaned,
    }
    # main の同日再実行で同じ履歴を水増ししない。
    if entries and (
        str(entries[0].get("saved_at") or "")[:10] == now.date().isoformat()
        and entries[0].get("video_type") == video_type
        and entries[0].get("themes") == cleaned
    ):
        entries[0] = row
    else:
        entries.insert(0, row)
    data["entries"] = entries[:_RELATED_HISTORY_LIMIT]
    _save_json(path, data)


def extract_related_themes_from_scenes(
    scenes: Sequence[Dict],
    known_themes: Sequence[str],
) -> List[str]:
    """台本テキストから、known テーマ名の出現を拾う。"""
    if not known_themes:
        return []
    blob = " ".join(
        str(sc.get("speech_text") or sc.get("text") or "") for sc in scenes
    )
    found: List[str] = []
    # 長いテーマ名優先（電力・送電 > 電力）
    ordered = sorted({str(t) for t in known_themes if t}, key=len, reverse=True)
    for theme in ordered:
        if theme in blob and theme not in found:
            found.append(theme)
    return found


def load_recent_hooks(*, limit: int = 6) -> List[str]:
    data = _load_json(_history_path("recent_script_hooks.json"))
    hooks: List[str] = []
    for e in (data.get("entries") or [])[:limit]:
        h = str(e.get("hook") or "").strip()
        if h and h not in hooks:
            hooks.append(h)
    return hooks


def save_script_hook(hook: str, *, video_type: str = "") -> None:
    h = str(hook or "").strip()
    if not h:
        return
    path = _history_path("recent_script_hooks.json")
    data = _load_json(path)
    entries = list(data.get("entries") or [])
    now = datetime.now()
    row = {
        "saved_at": now.isoformat(timespec="seconds"),
        "video_type": video_type,
        "hook": h[:80],
    }
    if entries and (
        str(entries[0].get("saved_at") or "")[:10] == now.date().isoformat()
        and entries[0].get("video_type") == video_type
        and entries[0].get("hook") == row["hook"]
    ):
        entries[0] = row
    else:
        entries.insert(0, row)
    data["entries"] = entries[:_HOOK_HISTORY_LIMIT]
    _save_json(path, data)


def load_previous_sector_snapshot(
    *,
    video_type: str = "",
    before_date: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """同じ配信種別の直近スナップショット（当日分は除外）を返す。"""
    data = _load_json(_history_path("recent_sector_flow.json"))
    entries = data.get("entries") or []
    cutoff = (before_date or date.today()).isoformat()
    for prev in entries:
        if not isinstance(prev, dict):
            continue
        if video_type and prev.get("video_type") != video_type:
            continue
        snapshot_date = str(
            prev.get("snapshot_date") or prev.get("saved_at") or ""
        )[:10]
        if snapshot_date and snapshot_date < cutoff:
            return prev
    return None


def save_sector_snapshot(
    *,
    top: Sequence[str],
    bottom: Sequence[str],
    video_type: str = "",
    snapshot_date: Optional[date] = None,
) -> None:
    path = _history_path("recent_sector_flow.json")
    data = _load_json(path)
    entries = list(data.get("entries") or [])
    day = snapshot_date or date.today()
    row = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_date": day.isoformat(),
        "video_type": video_type,
        "top": [str(x) for x in top if x][:5],
        "bottom": [str(x) for x in bottom if x][:5],
    }
    # 朝・夜それぞれ同日1件。再実行時は最新版へ置換する。
    entries = [
        e
        for e in entries
        if not (
            isinstance(e, dict)
            and str(e.get("snapshot_date") or e.get("saved_at") or "")[:10]
            == day.isoformat()
            and e.get("video_type") == video_type
        )
    ]
    entries.insert(0, row)
    data["entries"] = entries[:_SECTOR_HISTORY_LIMIT]
    _save_json(path, data)


def compare_sector_flow(
    top: Sequence[str],
    bottom: Sequence[str],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """昨日と似ていれば thin、違えば thick。"""
    cur_top = [str(x) for x in top if x][:3]
    cur_bot = [str(x) for x in bottom if x][:3]
    if not previous:
        return {
            "depth": "normal",
            "changed": True,
            "note": "比較対象なし。今日の違和感業種を優先。",
            "current_top": cur_top,
            "current_bottom": cur_bot,
        }
    prev_top = set(previous.get("top") or [])
    prev_bot = set(previous.get("bottom") or [])
    same_top = len(prev_top & set(cur_top))
    same_bot = len(prev_bot & set(cur_bot))
    # 上位下位合わせて2つ以上重なれば「似ている」
    similar = (same_top + same_bot) >= 2
    return {
        "depth": "thin" if similar else "thick",
        "changed": not similar,
        "note": (
            "資金の向きが昨日と近い。業種パートは短く、差分だけ。"
            if similar
            else "資金の向きが昨日と違う。違和感のある業種を厚めに。"
        ),
        "overlap_top": same_top,
        "overlap_bottom": same_bot,
        "current_top": cur_top,
        "current_bottom": cur_bot,
        "previous_top": list(prev_top)[:3],
        "previous_bottom": list(prev_bot)[:3],
    }


def _sector_names_from_analysis(aggregated: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    sectors = ((aggregated.get("sector_analysis") or {}).get("sectors") or [])
    top: List[str] = []
    bottom: List[str] = []
    for s in sectors:
        if not isinstance(s, dict):
            continue
        name = str(s.get("sector_name") or "").strip()
        if not name:
            continue
        if s.get("type") == "top":
            top.append(name)
        elif s.get("type") == "bottom":
            bottom.append(name)
    return top, bottom


def build_daily_question_hint(attention_news: Sequence[Dict]) -> str:
    """今日の問いの種（LLMが最終文にする）。"""
    for n in attention_news:
        company = str((n or {}).get("related_company_name") or "").strip()
        title = str((n or {}).get("title_ja") or (n or {}).get("title") or "").strip()
        if company:
            return f"{company}の初動は材料通りか、選別か？"
        if title:
            short = title[:24]
            return f"「{short}」は寄り付きで続くか？"
    return "今日の本命材料は、寄り付きで続くか選別か？"


def attach_anti_monotony_context(
    aggregated_data: Dict[str, Any],
    *,
    video_type: str = "",
    recent_topics: Optional[Sequence[str]] = None,
    persist_history: bool = True,
) -> Dict[str, Any]:
    """analysis_data に anti_monotony を付与。"""
    is_morning = "morning" in (video_type or "")
    corner = pick_daily_corner()
    theme_bridge = aggregated_data.get("theme_bridge") or {}
    known_themes = list((theme_bridge.get("themes") or {}).keys())
    recent_related = load_recent_related_themes(limit=6)
    # 連投抑制: 直近で出したテーマは弱めに扱う
    avoid_related = [t for t in recent_related if t in known_themes][:5]

    top, bottom = _sector_names_from_analysis(aggregated_data)
    today = date.today()
    prev_sector = load_previous_sector_snapshot(
        video_type=video_type,
        before_date=today,
    )
    sector_delta = compare_sector_flow(top, bottom, prev_sector)
    if persist_history and (top or bottom):
        save_sector_snapshot(
            top=top,
            bottom=bottom,
            video_type=video_type,
            snapshot_date=today,
        )

    news = aggregated_data.get("attention_news") or []
    topics = list(recent_topics or [])[:12]
    hooks = load_recent_hooks(limit=5)
    thumb = str(aggregated_data.get("selected_thumbnail_title") or "").strip()

    ctx = {
        "corner": corner,
        "avoid_related_themes": avoid_related,
        "recent_topics_avoid_deep": topics[:8],
        "recent_hooks_avoid": hooks,
        "sector_flow_delta": sector_delta,
        "daily_question_seed": build_daily_question_hint(news),
        "rules": {
            "related_max_mentions": 2,
            "checklist_no_stereotype": True,
            "require_today_diff_line": True,
            "require_daily_question": True,
            "shorts_vs_main": (
                "本編は因果と展望。ショートは用語1つ or 銘柄1本だけ。"
                "本編の全文要約をショートで繰り返さない。"
            ),
        },
        "is_morning": is_morning,
        "thumbnail_title": thumb or None,
    }
    aggregated_data["anti_monotony"] = ctx
    aggregated_data["recent_topics_for_script"] = topics[:8]
    return aggregated_data


def build_anti_monotony_prompt_block(analysis_data: Dict[str, Any]) -> str:
    """台本プロンプト末尾／共通に差し込むブロック。"""
    ctx = analysis_data.get("anti_monotony") or {}
    if not ctx:
        return ""

    corner = ctx.get("corner") or {}
    avoid = ctx.get("avoid_related_themes") or []
    topics = ctx.get("recent_topics_avoid_deep") or analysis_data.get("recent_topics_for_script") or []
    hooks = ctx.get("recent_hooks_avoid") or []
    delta = ctx.get("sector_flow_delta") or {}
    qseed = ctx.get("daily_question_seed") or ""
    rules = ctx.get("rules") or {}

    avoid_s = "、".join(avoid) if avoid else "（なし）"
    topics_s = " / ".join(str(t)[:28] for t in topics[:6]) if topics else "（なし）"
    hooks_s = " / ".join(str(h)[:24] for h in hooks[:4]) if hooks else "（なし）"

    return f"""

# 脱マンネリ（重要・視聴維持）
- 毎回同じ型の説明で終わらせない。**今日の差分**を1文、opening か展望のどちらかに必ず入れる。
- 日替わりコーナー（本日）: **{corner.get('label', '')}**（id=`{corner.get('id', '')}`）
  - 指示: {corner.get('hint', '')}
  - このコーナーは本編で最大1シーン。無理なら省略可（無理に定型で埋めない）。
- related 波及は本編全体で最大 {rules.get('related_max_mentions', 2)} 回。
- 直近で出しすぎのテーマ（連投抑制・弱めに扱う）: {avoid_s}
- 直近で触れたトピック（深掘りしすぎない／同じ話の再熱禁止）: {topics_s}
- 直近の冒頭フック（似た言い回し禁止）: {hooks_s}
- 業種フロー: depth=`{delta.get('depth', 'normal')}` — {delta.get('note', '')}
- **今日の問い**（closing か展望の締めに1つ）: 種「{qseed}」を、今日の固有名詞で具体化して問いかける。答えを決めつけない。
- チェック3点: 金利・為替・半導体・地合いだけの定型は禁止。今日のニュース固有名詞で作る。
- 本編とショートの役割: {rules.get('shorts_vs_main', '')}
"""


def _outlook_scene_texts(scenes: Sequence[Dict]) -> List[str]:
    texts: List[str] = []
    keys = ("チェック", "展望", "影響予測", "tomorrow", "japan_impact", "tonight")
    for sc in scenes:
        title = str(sc.get("section_title") or "")
        if any(k.lower() in title.lower() for k in keys) or any(
            k in title for k in ("チェック", "展望", "影響", "明日", "今夜")
        ):
            texts.append(str(sc.get("speech_text") or sc.get("text") or ""))
            for line in sc.get("on_screen_text") or []:
                texts.append(str(line))
    return texts


def evaluate_anti_monotony(
    scenes: Sequence[Dict],
    analysis_data: Dict[str, Any],
) -> List[str]:
    """品質不足としてリトライ材料にする issue 文字列。"""
    issues: List[str] = []
    ctx = analysis_data.get("anti_monotony") or {}
    blob = " ".join(
        str(sc.get("speech_text") or sc.get("text") or "") for sc in scenes
    )

    # 1) チェック定型
    outlook_texts = _outlook_scene_texts(scenes) or [blob]
    hits = checklist_stereotype_hits(outlook_texts)
    # 定型が3つ以上かつ固有の社名っぽいものが薄い → マンネリ
    if len(hits) >= 3 and not re.search(r"[一-龥]{2,}(株|工業|電機|銀行|商事)", blob):
        issues.append(
            f"チェック／展望が定型語に寄りすぎ（{', '.join(hits[:5])}）。今日の固有名詞で書き直す。"
        )

    # 2) 今日の差分
    diff_markers = (
        "昨日と",
        "前回と",
        "きょう違う",
        "今日違う",
        "差分",
        "これまでと違い",
        "昨日から",
        "前回から",
        "変わった点",
        "違う点",
        "本日のポイントは",
    )
    if not any(m in blob for m in diff_markers):
        issues.append("『今日の差分』が1文も無い。openingか展望に差分を1文入れる。")

    # 3) 今日の問い
    q_markers = ("？", "か？", "でしょうか", "どうなる", "続くか", "選別か")
    closing_blob = " ".join(
        str(sc.get("speech_text") or sc.get("text") or "")
        for sc in scenes
        if "まと" in str(sc.get("section_title") or "")
        or "closing" in str(sc.get("section_title") or "").lower()
        or "展望" in str(sc.get("section_title") or "")
        or "チェック" in str(sc.get("section_title") or "")
    )
    if closing_blob and not any(m in closing_blob for m in q_markers):
        issues.append("締めに『今日の問い』（疑問形）が無い。答えを断定せず1つ問いかける。")

    # 4) related 連投
    avoid = ctx.get("avoid_related_themes") or []
    theme_bridge = analysis_data.get("theme_bridge") or {}
    known = list((theme_bridge.get("themes") or {}).keys())
    used = extract_related_themes_from_scenes(scenes, known)
    reused = [t for t in used if t in avoid]
    if len(reused) >= 2:
        issues.append(
            f"直近で出した波及テーマの連投（{', '.join(reused)}）。別の差分か省略に切り替える。"
        )

    return issues


def persist_after_script(
    scenes: Sequence[Dict],
    analysis_data: Dict[str, Any],
    *,
    video_type: str = "",
) -> None:
    """生成成功後に履歴を更新。"""
    theme_bridge = analysis_data.get("theme_bridge") or {}
    known = list((theme_bridge.get("themes") or {}).keys())
    used = extract_related_themes_from_scenes(scenes, known)
    if used:
        save_related_themes_for_video(used, video_type=video_type)

    # opening の冒頭フック
    for sc in scenes[:3]:
        title = str(sc.get("section_title") or "")
        if "opening" in title.lower() or "トピック" in title or "本日" in title:
            hook = str(sc.get("speech_text") or sc.get("text") or "")[:60]
            save_script_hook(hook, video_type=video_type)
            break
    else:
        thumb = str(analysis_data.get("selected_thumbnail_title") or "").strip()
        if thumb:
            save_script_hook(thumb, video_type=video_type)


def shorts_role_prompt_appendix() -> str:
    return """
# 本編との役割分離（脱マンネリ）
- ショートは本編の要約コピーにしない。
- 案A: 用語を1つだけ、かみ砕いて終わり。本編のニュース列挙は禁止。
- 案B: 銘柄を1本だけ。因果の長い展望・業種網羅は本編に任せる。
- 「詳しくは本編で」は結びで1回まで。
"""


__all__ = [
    "attach_anti_monotony_context",
    "build_anti_monotony_prompt_block",
    "checklist_stereotype_hits",
    "compare_sector_flow",
    "evaluate_anti_monotony",
    "extract_related_themes_from_scenes",
    "is_stereotype_checklist",
    "persist_after_script",
    "pick_daily_corner",
    "prefer_concrete_checklist_items",
    "shorts_role_prompt_appendix",
]
