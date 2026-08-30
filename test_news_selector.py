"""news_selector のユニットテスト（外部API不要）。"""

from datetime import datetime, timedelta

from src.analysis.news_selector import (
    select_attention_news,
    score_freshness,
    score_novelty,
    score_news_item,
    infer_lane,
    infer_scope,
    apply_related_ticker_guard,
    annotate_news_roles,
)


def test_freshness_prefers_recent():
    now = datetime(2026, 8, 5, 21, 0, 0)
    fresh = {"published_at": (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")}
    old = {"published_at": (now - timedelta(hours=40)).strftime("%Y-%m-%d %H:%M:%S")}
    assert score_freshness(fresh, now=now) > score_freshness(old, now=now)


def test_novelty_penalizes_recent_topics():
    news = {"title": "NVIDIAが急騰、半導体相場が過熱"}
    low = score_novelty(news, ["NVIDIAが急騰、半導体相場が過熱"])
    high = score_novelty(news, ["日銀が追加利上げを示唆"])
    assert low < high


def test_select_assigns_honmei_and_heat_slots():
    now = datetime(2026, 8, 5, 21, 0, 0)
    candidates = [
        {
            "title": "FRBが利下げ観測を後退、米金利上昇",
            "snippet": "指数全体に波及する金利ニュース。S&Pやナスダックへの影響。",
            "published_at": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "url": "https://example.com/1",
            "pool": "impact",
        },
        {
            "title": "某成長株がストップ高、急騰で話題",
            "snippet": "ストップ高・急騰の話題性ニュース。",
            "published_at": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "url": "https://example.com/2",
            "pool": "heat",
        },
        {
            "title": "AIから銀行へ資金ローテーションの兆し",
            "snippet": "セクターローテーション、資金流入の違和感。",
            "published_at": (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
            "url": "https://example.com/3",
        },
        {
            "title": "地味な事務連絡",
            "snippet": "特に市場インパクトは小さい。",
            "published_at": (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "url": "https://example.com/4",
        },
    ]
    for c in candidates:
        c["scores"] = score_news_item(c, recent_topics=[], now=now, use_price_heat=False)

    ordered, meta = select_attention_news(
        candidates,
        recent_topics=["昨日の半導体祭り"],
        max_keep=4,
        heat_slots=1,
        use_price_heat=False,
        enrich_with_llm=False,
    )
    assert len(ordered) >= 3
    assert ordered[0]["slot"] == "honmei"
    assert ordered[0].get("lane") == "macro"
    slots = [n["slot"] for n in ordered]
    assert "heat" in slots or any("急騰" in (n.get("title") or "") for n in ordered)
    heat_items = [n for n in ordered if n.get("slot") == "heat"]
    if heat_items:
        assert heat_items[0].get("lane") == "local"
    assert meta["kept"] == len(ordered)
    assert all(n.get("lane") for n in ordered)
    assert all(n.get("scope") for n in ordered)


def test_lane_from_pool():
    assert infer_lane({"pool": "impact", "title": "金利"}) == "macro"
    assert infer_lane({"pool": "heat", "title": "某社が急騰"}) == "local"


def test_scope_issuer_from_company_in_title():
    news = {
        "title": "スクウェア・エニックスが上方修正",
        "snippet": "決算で営業益が増益。",
        "related_company_name": "スクウェア・エニックス",
        "related_ticker": "9684.T",
    }
    assert infer_scope(news) == "issuer"


def test_macro_clears_unrelated_ticker():
    news = {
        "title": "FRBが利下げ観測を後退、米金利上昇",
        "snippet": "指数全体に波及する金利ニュース。",
        "pool": "impact",
        "related_ticker": "AAPL",
        "related_company_name": "FRBが利下げ観測を後退、米金利上昇",
        "scores": {"impact": 0.9, "heat": 0.2},
    }
    guarded = apply_related_ticker_guard(annotate_news_roles(news))
    assert guarded["lane"] == "macro"
    assert guarded.get("related_ticker") in (None, "")


if __name__ == "__main__":
    test_freshness_prefers_recent()
    test_novelty_penalizes_recent_topics()
    test_select_assigns_honmei_and_heat_slots()
    test_lane_from_pool()
    test_scope_issuer_from_company_in_title()
    test_macro_clears_unrelated_ticker()
    print("OK")
