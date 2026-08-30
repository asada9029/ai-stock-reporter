"""
注目ニュースの重みづけ選定。

優先順: 鮮度 → 旬(Heat) → 波及(Impact) → 行動(Action) → 新規性(Novelty)
枠: 本命1 / 旬1〜2 / 循環サイン0〜1 / 残りは補助

追加メタ（動画向け）:
- lane: macro（大局）| local（局所）
- scope: issuer（当事者1社）| theme（テーマ）| unclear
- polarity: pos | neg | mixed
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils.logger import log_kv

# 加重（合計1.0）。設計の優先順を反映。
WEIGHTS = {
    "freshness": 0.35,
    "heat": 0.25,
    "impact": 0.20,
    "action": 0.12,
    "novelty": 0.08,
}

HEAT_KEYWORDS = (
    "急騰", "急落", "暴騰", "暴落", "ストップ高", "ストップ安", "大幅高", "大幅安",
    "最高値", "最安値", "サプライズ", "上方修正", "下方修正", "決算", "好決算", "赤字転落",
    "話題", "注目", "急伸", "急反発", "急反落", "売られ", "買われ",
    "surge", "plunge", "soar", "crash", "record high", "selloff",
)

IMPACT_KEYWORDS = (
    "FRB", "FOMC", "日銀", "金利", "利上げ", "利下げ", "CPI", "雇用統計", "GDP",
    "為替", "ドル円", "円安", "円高", "原油", "地政学", "関税", "大統領",
    "NVIDIA", "エヌビディア", "半導体", "SOX", "ナスダック", "S&P", "日経",
    "テーパリング", "バランスシート",
)

ACTION_KEYWORDS = (
    "注目", "明日", "今夜", "寄り付き", "チェック", "見通し", "影響", "波及",
    "買い", "売り", "押し目", "警戒", "戦略",
)

ROTATION_KEYWORDS = (
    "ローテーション", "資金移動", "資金流入", "資金流出", "セクターローテ",
    "乖離", "織り込み", "利益確定", "内需", "ディフェンシブ", "バリュー",
    "グロースから", "から銀行", "から小売", "逃げた",
)

ISSUER_HINTS = (
    "決算", "上方修正", "下方修正", "増益", "減益", "赤字", "黒字", "IR",
    "自社株買い", "公募", "増資", "買収", "提携", "受注", "出荷停止",
    "earnings", "guidance", "buyback",
)

POS_KEYWORDS = (
    "急騰", "大幅高", "続伸", "最高値", "上方修正", "増益", "好決算", "買い",
    "上昇", "反発", "追い風", "surge", "soar", "beat",
)
NEG_KEYWORDS = (
    "急落", "大幅安", "続落", "最安値", "下方修正", "減益", "赤字", "売り",
    "下落", "懸念", "警戒", "制裁", "関税", "plunge", "crash", "miss",
)

# マンネリしやすい語（Novelty減点の補助）
STALE_TOPIC_HINTS = (
    "半導体", "円安", "NVIDIA", "エヌビディア", "AI関連",
)


def _jst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)


def _parse_published_at(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone(timedelta(hours=9))).replace(tzinfo=None)
        return dt
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _text_blob(news: Dict) -> str:
    parts = [
        str(news.get("title") or ""),
        str(news.get("snippet") or ""),
        str(news.get("summary") or ""),
        str(news.get("related_company_name") or ""),
    ]
    return " ".join(parts)


def _keyword_hit_score(text: str, keywords: Sequence[str], *, cap: float = 1.0) -> float:
    if not text:
        return 0.0
    lower = text.lower()
    hits = 0
    for kw in keywords:
        if kw.lower() in lower:
            hits += 1
    if hits <= 0:
        return 0.0
    # 1ヒットで0.45、以降減衰的に加点
    return min(cap, 0.45 + 0.15 * (hits - 1))


def score_freshness(news: Dict, *, now: Optional[datetime] = None) -> float:
    """12h以内=1.0、24h=0.55、48h=0.25、それ以上=0.05。日付不明は0.4。"""
    now = now or _jst_now()
    dt = _parse_published_at(news.get("published_at"))
    if not dt:
        return 0.40
    hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    if hours <= 12:
        return 1.0
    if hours <= 24:
        return 0.55
    if hours <= 48:
        return 0.25
    return 0.05


def score_heat_from_text(news: Dict) -> float:
    return _keyword_hit_score(_text_blob(news), HEAT_KEYWORDS)


def score_heat_from_price_change(change_percent: Optional[float]) -> float:
    if change_percent is None:
        return 0.0
    abs_chg = abs(float(change_percent))
    if abs_chg >= 8:
        return 1.0
    if abs_chg >= 5:
        return 0.85
    if abs_chg >= 3:
        return 0.65
    if abs_chg >= 2:
        return 0.4
    return 0.1


def score_impact_from_text(news: Dict) -> float:
    return _keyword_hit_score(_text_blob(news), IMPACT_KEYWORDS)


def score_action_from_text(news: Dict) -> float:
    return _keyword_hit_score(_text_blob(news), ACTION_KEYWORDS)


def score_novelty(news: Dict, recent_topics: Sequence[str]) -> float:
    """直近トピックと重なるほど減点。完全一致寄りなら低く。"""
    if not recent_topics:
        return 1.0
    title = str(news.get("title") or "")
    blob = _text_blob(news)
    if not title:
        return 0.7

    overlap = 0
    for topic in recent_topics[:24]:
        t = str(topic).strip()
        if not t:
            continue
        # 短い共通部分（6文字以上）やキーワード一致
        if t in title or title in t:
            overlap += 3
            continue
        # トークン的な粗い一致
        for hint in STALE_TOPIC_HINTS:
            if hint in t and hint in blob:
                overlap += 1
        # 漢字・カタカナの連続6文字以上が共有
        for m in re.finditer(r"[\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9]{6,}", t):
            chunk = m.group(0)
            if chunk in blob:
                overlap += 2
                break

    if overlap >= 5:
        return 0.05
    if overlap >= 3:
        return 0.25
    if overlap >= 1:
        return 0.55
    return 1.0


def _fetch_ticker_change_percent(ticker: Optional[str]) -> Optional[float]:
    if not ticker:
        return None
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist is None or len(hist) < 2:
            return None
        prev = float(hist["Close"].iloc[-2])
        cur = float(hist["Close"].iloc[-1])
        if prev == 0:
            return None
        return (cur - prev) / prev * 100.0
    except Exception:
        return None


def is_rotation_signal(news: Dict) -> bool:
    return _keyword_hit_score(_text_blob(news), ROTATION_KEYWORDS) >= 0.45


def infer_lane(news: Dict) -> str:
    """
    大局(macro) / 局所(local)。
    Impactプールや指数・金利系は macro、個別急騰落・1社材料は local。
    """
    pool = str(news.get("pool") or "").lower()
    if pool == "impact":
        return "macro"
    if pool == "heat":
        return "local"

    impact = float((news.get("scores") or {}).get("impact") or score_impact_from_text(news))
    heat = float((news.get("scores") or {}).get("heat") or score_heat_from_text(news))
    blob = _text_blob(news)
    has_company = bool(news.get("related_ticker") or news.get("related_company_name"))
    issuerish = _keyword_hit_score(blob, ISSUER_HINTS) >= 0.45

    if impact >= 0.55 and heat < 0.7:
        return "macro"
    if heat >= 0.55 and (issuerish or has_company):
        return "local"
    if impact >= heat + 0.15:
        return "macro"
    if heat >= impact + 0.1:
        return "local"
    # デフォルト: 会社名があるなら局所、なければ大局寄り
    return "local" if has_company or issuerish else "macro"


def infer_scope(news: Dict) -> str:
    """当事者1社(issuer) / テーマ(theme) / 不明(unclear)。"""
    blob = _text_blob(news)
    title = str(news.get("title") or "")
    company = str(news.get("related_company_name") or "").strip()
    ticker = str(news.get("related_ticker") or "").strip()
    issuerish = _keyword_hit_score(blob, ISSUER_HINTS) >= 0.45

    company_in_title = False
    if company and len(company) >= 2 and company[:8] in title:
        company_in_title = True
    if ticker:
        bare = ticker.replace(".T", "").replace(".t", "")
        if bare and bare in title:
            company_in_title = True

    if company_in_title or (issuerish and (company or ticker)):
        return "issuer"

    impact = float((news.get("scores") or {}).get("impact") or score_impact_from_text(news))
    if impact >= 0.45 or _keyword_hit_score(blob, IMPACT_KEYWORDS) >= 0.45:
        # 大局語があるが特定社名がタイトルに無い → テーマ／地合い
        return "theme"
    if company or ticker:
        return "issuer"
    return "unclear"


def infer_polarity(news: Dict) -> str:
    blob = _text_blob(news)
    pos = _keyword_hit_score(blob, POS_KEYWORDS)
    neg = _keyword_hit_score(blob, NEG_KEYWORDS)
    if pos >= 0.45 and neg >= 0.45:
        return "mixed"
    if pos >= 0.45:
        return "pos"
    if neg >= 0.45:
        return "neg"
    return "mixed"


def annotate_news_roles(news: Dict) -> Dict:
    """lane / scope / polarity を付与（既存値があれば尊重）。"""
    item = dict(news)
    if not item.get("lane"):
        item["lane"] = infer_lane(item)
    if not item.get("scope"):
        item["scope"] = infer_scope(item)
    if not item.get("polarity"):
        item["polarity"] = infer_polarity(item)
    return item


def apply_related_ticker_guard(news: Dict) -> Dict:
    """
    軽いガード:
    - scope=issuer: related は当事者想定。タイトル／社名と無関係ならクリアしないが expand はしない（単一のまま）
    - lane=macro: 弱く推定された個別ティッカーは外し、地合いニュースに無理な銘柄カードを付けない
    """
    item = dict(news)
    lane = item.get("lane") or infer_lane(item)
    scope = item.get("scope") or infer_scope(item)
    item["lane"] = lane
    item["scope"] = scope

    ticker = str(item.get("related_ticker") or "").strip()
    company = str(item.get("related_company_name") or "").strip()
    title = str(item.get("title") or "")
    blob = _text_blob(item)

    def _ticker_in_text() -> bool:
        if not ticker:
            return False
        bare = ticker.replace(".T", "").replace(".t", "")
        return bool(bare) and bare in blob

    def _real_company_in_text() -> bool:
        """タイトル丸写しの company_name は社名扱いしない。"""
        if not company or len(company) < 2:
            return False
        if title and company[:16] == title[:16]:
            return False
        return company[:10] in blob

    if lane == "macro" and ticker:
        if not _ticker_in_text() and not _real_company_in_text():
            item["related_ticker"] = None
            item["_related_cleared"] = "macro_no_party"
            if company and title and company[:16] == title[:16]:
                item["related_company_name"] = None

    if scope == "issuer" and ticker and not _ticker_in_text() and not _real_company_in_text():
        item["related_ticker"] = None
        item["_related_cleared"] = "issuer_mismatch"

    return item


def score_news_item(
    news: Dict,
    *,
    recent_topics: Sequence[str] = (),
    now: Optional[datetime] = None,
    use_price_heat: bool = True,
) -> Dict[str, float]:
    """各軸0〜1と weighted total を返す。"""
    freshness = score_freshness(news, now=now)
    heat_text = score_heat_from_text(news)
    change_pct = None
    if use_price_heat:
        change_pct = _fetch_ticker_change_percent(news.get("related_ticker"))
    heat_price = score_heat_from_price_change(change_pct)
    heat = max(heat_text, heat_price)
    impact = score_impact_from_text(news)
    action = score_action_from_text(news)
    novelty = score_novelty(news, recent_topics)

    total = (
        WEIGHTS["freshness"] * freshness
        + WEIGHTS["heat"] * heat
        + WEIGHTS["impact"] * impact
        + WEIGHTS["action"] * action
        + WEIGHTS["novelty"] * novelty
    )
    return {
        "freshness": round(freshness, 3),
        "heat": round(heat, 3),
        "impact": round(impact, 3),
        "action": round(action, 3),
        "novelty": round(novelty, 3),
        "total": round(total, 3),
        "price_change_percent": round(change_pct, 3) if change_pct is not None else None,
    }


def _dedupe_news(items: Sequence[Dict]) -> List[Dict]:
    seen = set()
    out: List[Dict] = []
    for n in items:
        title = str(n.get("title") or "").strip()
        url = str(n.get("url") or "").strip()
        key = (title[:40], url)
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(dict(n))
    return out


def enrich_llm_axis_scores(
    scored_items: List[Dict],
    gemini_client: Any,
    *,
    max_items: int = 12,
) -> List[Dict]:
    """
    ルールスコアの上に、LLMによる impact/heat/action の補正を載せる（任意）。
    失敗してもルール結果を返す。
    """
    if not scored_items or gemini_client is None:
        return scored_items

    subset = scored_items[:max_items]
    lines = []
    for i, n in enumerate(subset):
        lines.append(
            f"{i}. title={n.get('title', '')}\n   summary={n.get('snippet') or n.get('summary') or ''}"
        )
    prompt = f"""以下の株ニュース候補を採点し、JSONのみ返してください。
各要素は index と 0〜100 の整数スコアです。

観点:
- impact: 指数・複数セクター・為替など市場全体への波及
- heat: いま話題性・急変・サプライズ感
- action: 視聴者が明日チェックすべき行動が言えるか

入力:
{chr(10).join(lines)}

出力例:
{{"scores":[{{"index":0,"impact":80,"heat":60,"action":70}}, ...]}}
"""
    try:
        data = gemini_client.generate_json(prompt, model_role="lite")
        rows = data.get("scores") or []
        by_idx = {int(r["index"]): r for r in rows if "index" in r}
        for i, n in enumerate(subset):
            row = by_idx.get(i)
            if not row:
                continue
            # 0-100 → 0-1。ルールと平均して暴れを抑える
            for axis in ("impact", "heat", "action"):
                raw = row.get(axis)
                if raw is None:
                    continue
                llm_v = max(0.0, min(100.0, float(raw))) / 100.0
                rule_v = float(n.get("scores", {}).get(axis, 0.0))
                n.setdefault("scores", {})
                n["scores"][axis] = round(0.45 * rule_v + 0.55 * llm_v, 3)
            sc = n["scores"]
            sc["total"] = round(
                WEIGHTS["freshness"] * float(sc.get("freshness", 0))
                + WEIGHTS["heat"] * float(sc.get("heat", 0))
                + WEIGHTS["impact"] * float(sc.get("impact", 0))
                + WEIGHTS["action"] * float(sc.get("action", 0))
                + WEIGHTS["novelty"] * float(sc.get("novelty", 0)),
                3,
            )
            n["llm_rescored"] = True
    except Exception as e:
        log_kv("news_selector:llm_score_skip", {"err": str(e)[:120]})
    return scored_items


def select_attention_news(
    candidates: Sequence[Dict],
    *,
    recent_topics: Sequence[str] = (),
    max_keep: int = 8,
    heat_slots: int = 2,
    use_price_heat: bool = True,
    gemini_client: Any = None,
    enrich_with_llm: bool = True,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    候補をスコアし、本命/旬/循環の枠に沿って並べ替えたリストを返す。

    Returns:
        (ordered_news, meta)
    """
    deduped = _dedupe_news(candidates)
    now = _jst_now()
    scored: List[Dict] = []
    for n in deduped:
        scores = score_news_item(
            n, recent_topics=recent_topics, now=now, use_price_heat=use_price_heat
        )
        item = dict(n)
        item["scores"] = scores
        item["is_rotation_signal"] = is_rotation_signal(n)
        scored.append(item)

    if enrich_with_llm and gemini_client is not None:
        scored = enrich_llm_axis_scores(scored, gemini_client)

    # レーン／スコープ付与 + related の軽いガード
    scored = [apply_related_ticker_guard(annotate_news_roles(x)) for x in scored]

    remaining = list(scored)
    picked: List[Dict] = []
    slots_used: List[str] = []

    def _take(pred, slot: str, key_fn) -> Optional[Dict]:
        nonlocal remaining
        pool = [x for x in remaining if pred(x)]
        if not pool:
            return None
        pool.sort(key=key_fn, reverse=True)
        chosen = pool[0]
        remaining = [x for x in remaining if x is not chosen]
        chosen = dict(chosen)
        chosen["slot"] = slot
        picked.append(chosen)
        slots_used.append(slot)
        return chosen

    # 1) 本命: lane=macro 優先。鮮度を確保しつつ impact×total
    _take(
        lambda x: (
            x.get("lane") == "macro"
            and float(x["scores"].get("freshness", 0)) >= 0.4
        ),
        "honmei",
        key_fn=lambda x: (
            float(x["scores"].get("impact", 0)) * 0.6
            + float(x["scores"].get("total", 0)) * 0.4
        ),
    )
    if not any(s == "honmei" for s in slots_used):
        _take(
            lambda x: float(x["scores"].get("freshness", 0)) >= 0.4,
            "honmei",
            key_fn=lambda x: (
                float(x["scores"].get("impact", 0)) * 0.6
                + float(x["scores"].get("total", 0)) * 0.4
            ),
        )
    # 鮮度フィルタで取れなければ total 最高
    if not any(s == "honmei" for s in slots_used):
        _take(lambda x: True, "honmei", key_fn=lambda x: float(x["scores"].get("total", 0)))

    # 2) 旬枠: lane=local を優先（カリン飛びつき）
    for _ in range(max(0, heat_slots)):
        taken = _take(
            lambda x: (
                x.get("lane") == "local"
                and float(x["scores"].get("heat", 0)) >= 0.35
            ),
            "heat",
            key_fn=lambda x: (
                float(x["scores"].get("heat", 0)) * 0.7
                + float(x["scores"].get("freshness", 0)) * 0.3
            ),
        )
        if taken is None:
            _take(
                lambda x: float(x["scores"].get("heat", 0)) >= 0.35,
                "heat",
                key_fn=lambda x: (
                    float(x["scores"].get("heat", 0)) * 0.7
                    + float(x["scores"].get("freshness", 0)) * 0.3
                ),
            )

    # 3) 循環サイン 0〜1
    _take(
        lambda x: bool(x.get("is_rotation_signal")),
        "rotation",
        key_fn=lambda x: float(x["scores"].get("total", 0)),
    )

    # 4) 残りを total で埋める
    remaining.sort(key=lambda x: float(x["scores"].get("total", 0)), reverse=True)
    for x in remaining:
        if len(picked) >= max_keep:
            break
        item = dict(x)
        item["slot"] = item.get("slot") or "support"
        picked.append(item)
        slots_used.append(item["slot"])

    meta = {
        "candidate_count": len(deduped),
        "kept": len(picked),
        "slots": slots_used,
        "weights": dict(WEIGHTS),
        "lanes": [p.get("lane") for p in picked],
        "scopes": [p.get("scope") for p in picked],
        "top_titles": [p.get("title", "")[:40] for p in picked[:5]],
    }
    log_kv("news_selector:done", meta)
    return picked[:max_keep], meta


__all__ = [
    "WEIGHTS",
    "select_attention_news",
    "score_news_item",
    "score_freshness",
    "score_novelty",
    "is_rotation_signal",
    "infer_lane",
    "infer_scope",
    "infer_polarity",
    "annotate_news_roles",
    "apply_related_ticker_guard",
]
