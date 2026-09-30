"""脱マンネリモジュールのスモークテスト。"""

import json
from datetime import date

import src.analysis.anti_monotony as anti_monotony
from src.analysis.anti_monotony import (
    attach_anti_monotony_context,
    build_anti_monotony_prompt_block,
    compare_sector_flow,
    evaluate_anti_monotony,
    is_stereotype_checklist,
    pick_daily_corner,
    prefer_concrete_checklist_items,
    load_previous_sector_snapshot,
    save_sector_snapshot,
)


def test_pick_daily_corner_rotates():
    a = pick_daily_corner(today=date(2026, 9, 30))
    b = pick_daily_corner(today=date(2026, 10, 1))
    assert a["id"] != b["id"]
    assert a["label"]


def test_checklist_prefers_news_not_stereotype():
    news = [
        {"related_company_name": "トヨタ", "title": "トヨタが上方修正", "why_now": "業績上振れ"},
        {"related_company_name": "ソニーG", "title": "エンタメ好調"},
    ]
    items = prefer_concrete_checklist_items(news, [], is_morning=True, limit=3)
    assert any("トヨタ" in x or "ソニー" in x for x in items)
    assert not is_stereotype_checklist(items, min_hits=3)


def test_sector_flow_thin_when_similar():
    prev = {"top": ["情報・通信業", "電気機器"], "bottom": ["銀行業", "建設業"]}
    delta = compare_sector_flow(
        ["情報・通信業", "電気機器", "精密機器"],
        ["銀行業", "建設業", "水産・農林業"],
        prev,
    )
    assert delta["depth"] == "thin"


def test_sector_history_upserts_same_run_date_and_reads_previous_day(
    tmp_path, monkeypatch
):
    history = tmp_path / "recent_sector_flow.json"
    monkeypatch.setattr(
        anti_monotony,
        "_history_path",
        lambda _name: history,
    )
    save_sector_snapshot(
        top=["電気機器"],
        bottom=["銀行業"],
        video_type="evening",
        snapshot_date=date(2026, 9, 29),
    )
    save_sector_snapshot(
        top=["情報・通信業"],
        bottom=["建設業"],
        video_type="evening",
        snapshot_date=date(2026, 9, 30),
    )
    save_sector_snapshot(
        top=["精密機器"],
        bottom=["海運業"],
        video_type="evening",
        snapshot_date=date(2026, 9, 30),
    )

    entries = json.loads(history.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 2
    assert entries[0]["top"] == ["精密機器"]
    previous = load_previous_sector_snapshot(
        video_type="evening",
        before_date=date(2026, 9, 30),
    )
    assert previous is not None
    assert previous["top"] == ["電気機器"]


def test_attach_and_prompt():
    data = {
        "attention_news": [
            {"title": "NVIDIA好決算", "related_company_name": "エヌビディア", "scope": "theme"}
        ],
        "theme_bridge": {
            "themes": {"AI": {"core_members": []}, "電線": {"core_members": []}},
            "related_edges": [{"from": "AI", "to": "電線", "weight": "strong"}],
        },
        "sector_analysis": {
            "sectors": [
                {"sector_name": "電気機器", "type": "top"},
                {"sector_name": "銀行業", "type": "bottom"},
            ]
        },
    }
    attach_anti_monotony_context(
        data,
        video_type="evening",
        recent_topics=["昨日の半導体話"],
        persist_history=False,
    )
    assert "anti_monotony" in data
    block = build_anti_monotony_prompt_block(data)
    assert "脱マンネリ" in block
    assert "日替わりコーナー" in block


def test_evaluate_flags_stereotype_outlook():
    scenes = [
        {
            "section_title": "明日の展望",
            "speech_text": "金利と為替と地合いと半導体をチェックしましょう。",
            "text": "金利と為替と地合いと半導体をチェックしましょう。",
        },
        {
            "section_title": "まとめ",
            "speech_text": "以上です。",
            "text": "以上です。",
        },
    ]
    issues = evaluate_anti_monotony(scenes, {"anti_monotony": {}})
    assert any("定型" in x or "差分" in x or "問い" in x for x in issues)


if __name__ == "__main__":
    test_pick_daily_corner_rotates()
    test_checklist_prefers_news_not_stereotype()
    test_sector_flow_thin_when_similar()
    test_attach_and_prompt()
    test_evaluate_flags_stereotype_outlook()
    print("OK")
