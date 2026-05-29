"""
ニュースにビジュアルを付与: OG画像（優先）→ 関連銘柄チャート（フォールバック）。
銘柄推定は search_news（Web Search）側で同時に行う。OG 関連性は画像取得後にバッチ Vision で1回判定。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.analysis.gemini_client import GeminiClient
from src.data_collection.og_image_fetcher import (
    download_image,
    fetch_og_image_url,
    guess_extension,
)
from src.data_collection.stock_chart_capturer import StockChartCapturer
from src.utils.logger import log_kv, timed, log


class NewsVisualEnricher:
    """attention_news 等に visual_image_path / ticker 情報を付与する。"""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        chart_capturer: Optional[StockChartCapturer] = None,
        output_base_dir: str = "output/collected",
    ):
        self.gemini = gemini_client or GeminiClient(enable_search=False)
        self.chart_capturer = chart_capturer or StockChartCapturer()
        self.output_base_dir = output_base_dir
        self.max_chart_captures = int(os.getenv("NEWS_MAX_CHART_CAPTURES", "6"))
        self.reuse_existing_charts = os.getenv("NEWS_REUSE_EXISTING_CHARTS", "true").lower() not in (
            "0",
            "false",
            "no",
        )
        # OG機能は残すが、基本は使わない（コスト/安定性のため）
        # NEWS_ENRICH_OG: OG画像を取得してローカル保存するか
        # NEWS_USE_OG: OG画像を最終的に採用するか（false なら判定も採用もしない）
        self.fetch_og = os.getenv("NEWS_ENRICH_OG", "false").lower() not in (
            "0",
            "false",
            "no",
        )
        self.use_og = os.getenv("NEWS_USE_OG", "false").lower() not in (
            "0",
            "false",
            "no",
        )

    def enrich_list(
        self,
        news_list: List[Dict[str, Any]],
        video_type: str,
        *,
        subdir: str = "news_visuals",
        tag: str = "news",
    ) -> int:
        if not news_list:
            return 0

        out_dir = os.path.join(self.output_base_dir, subdir, video_type)
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        log_kv(
            "🖼️ news_visual_enricher:start",
            {
                "count": len(news_list),
                "fetch_og": self.fetch_og,
                "use_og": self.use_og,
                "max_chart": self.max_chart_captures,
            },
        )

        for i, item in enumerate(news_list):
            item.setdefault("visual_image_path", None)
            item.setdefault("visual_source", None)
            item.setdefault("og_image_path", None)
            item.setdefault("og_image_url", None)
            item.setdefault("chart_image_path", None)
            item.setdefault("related_ticker", None)
            item.setdefault("related_company_name", None)
            item.setdefault("og_relevance_reason", None)

            raw_ticker = item.get("related_ticker")
            if raw_ticker:
                item["related_ticker"] = self._normalize_ticker(raw_ticker)
            else:
                # search_news 側で付かなかった場合のフォールバック（軽量なルール推定）
                inferred = self._infer_related_ticker(item)
                if inferred:
                    item["related_ticker"] = inferred

            # company_name も最低限埋める（表示カード用）
            if not item.get("related_company_name"):
                item["related_company_name"] = self._infer_related_company_name(item)

            if self.fetch_og:
                url = item.get("url") or ""
                og_url = fetch_og_image_url(url)
                item["og_image_url"] = og_url
                if og_url:
                    ext = guess_extension(og_url)
                    local_path = os.path.join(out_dir, f"{tag}_{i}_{ts}_og.{ext}")
                    if download_image(og_url, local_path):
                        item["og_image_path"] = local_path

        og_judgments = {}
        if self.fetch_og and self.use_og:
            with timed("🖼️ og:judge_batch"):
                og_judgments = self._batch_judge_og_images(news_list)

        chart_budget = self.max_chart_captures
        attached = 0

        for i, item in enumerate(news_list):
            judgment = og_judgments.get(i, {})
            og_path = item.get("og_image_path")
            use_og = (
                self.use_og
                and bool(judgment.get("relevant"))
                and og_path
                and os.path.exists(og_path)
            )

            if use_og:
                item["visual_image_path"] = og_path
                item["visual_source"] = "og"
                item["og_relevance_reason"] = judgment.get("reason", "")
                attached += 1
                print(f"  🖼️ [{i}] OG画像を採用: {item.get('title', '')[:40]}...")
                continue

            norm_ticker = item.get("related_ticker")
            company = item.get("related_company_name") or item.get("title", "")[:20]
            if not norm_ticker or chart_budget <= 0:
                continue

            # 既存チャートを再利用（Selenium節約）
            if self.reuse_existing_charts:
                existing = self._find_existing_chart_image(norm_ticker)
                if existing:
                    item["chart_image_path"] = existing
                    item["visual_image_path"] = existing
                    item["visual_source"] = "chart"
                    attached += 1
                    continue

            with timed("📈 news_chart:capture", level="debug") as t:
                t["ticker"] = norm_ticker
                chart_path = self.chart_capturer.capture_chart_screenshot(
                    norm_ticker, company or norm_ticker
                )
            if chart_path:
                item["chart_image_path"] = chart_path
                item["visual_image_path"] = chart_path
                item["visual_source"] = "chart"
                chart_budget -= 1
                attached += 1
                print(
                    f"  📈 [{i}] チャートを採用 ({norm_ticker}): "
                    f"{item.get('title', '')[:40]}..."
                )

        try:
            self.chart_capturer._close_driver()
        except Exception:
            pass

        return attached

    def _infer_related_ticker(self, item: Dict[str, Any]) -> Optional[str]:
        """title/snippet/url からティッカーっぽいものを推定（誤検出は許容しつつ保守的に）。"""
        title = str(item.get("title", "") or "")
        snippet = str(item.get("snippet", "") or "")
        url = str(item.get("url", "") or "")
        text = f"{title}\n{snippet}\n{url}"

        # まずは日本株（4桁）と .T
        m = re.search(r"\b(\d{4})\b", text)
        if m:
            return self._normalize_ticker(m.group(1))
        m = re.search(r"\b(\d{4}\.T)\b", text, flags=re.IGNORECASE)
        if m:
            return self._normalize_ticker(m.group(1))

        # $TSLA, (AAPL) など
        m = re.search(r"\$([A-Z]{1,5})\b", text)
        if m:
            return self._normalize_ticker(m.group(1))
        m = re.search(r"\(([A-Z]{1,5})\)", text)
        if m:
            cand = m.group(1)
            if cand not in {"AI", "USA", "US", "EU", "GDP", "CPI", "FOMC"}:
                return self._normalize_ticker(cand)

        # 英字ティッカー単体（保守的にタイトル優先で1個だけ）
        m = re.search(r"\b([A-Z]{1,5})\b", title)
        if m:
            cand = m.group(1)
            if cand not in {"AI", "USA", "US", "EU", "GDP", "CPI", "FOMC"}:
                return self._normalize_ticker(cand)

        return None

    def _infer_related_company_name(self, item: Dict[str, Any]) -> str:
        """会社名が無いときの最低限の埋め（表示カード用）。"""
        # それっぽい会社名が無ければタイトル先頭を短く
        title = str(item.get("title", "") or "").strip()
        if title:
            return title[:28]
        return ""

    def _find_existing_chart_image(self, ticker: str) -> Optional[str]:
        """output/stock_charts から同tickerの最新pngを探す。"""
        try:
            out_dir = getattr(self.chart_capturer, "output_dir", "output/stock_charts")
            if not out_dir:
                out_dir = "output/stock_charts"
            if not os.path.isdir(out_dir):
                return None
            prefix = f"{ticker}_"
            candidates: list[str] = []
            for name in os.listdir(out_dir):
                if not name.lower().endswith(".png"):
                    continue
                if name.startswith(prefix):
                    candidates.append(os.path.join(out_dir, name))
            if not candidates:
                return None
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return candidates[0]
        except Exception:
            return None

    def _normalize_ticker(self, raw: str) -> Optional[str]:
        if not raw:
            return None
        s = str(raw).strip().upper()
        if s in ("NULL", "NONE", "N/A", ""):
            return None
        if re.match(r"^\d{4}\.T$", s):
            return s
        if re.match(r"^\d{4}$", s):
            return f"{s}.T"
        if re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", s):
            return s
        return None

    def _batch_judge_og_images(
        self, news_list: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """OG 画像の関連性をまとめて1回の Vision で判定。"""
        from google.genai import types

        entries: List[tuple[int, str, str, str]] = []
        for i, item in enumerate(news_list):
            og_path = item.get("og_image_path")
            if not og_path or not os.path.exists(og_path):
                continue
            entries.append(
                (
                    i,
                    og_path,
                    item.get("title", ""),
                    item.get("snippet", ""),
                )
            )

        if not entries:
            return {}

        parts: list = []
        manifest = []
        for seq, (idx, path, title, snippet) in enumerate(entries, start=1):
            ext = os.path.splitext(path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(ext, "image/jpeg")
            try:
                with open(path, "rb") as f:
                    image_bytes = f.read()
                parts.append(
                    types.Part.from_bytes(data=image_bytes, mime_type=mime)
                )
                manifest.append(
                    {
                        "image_no": seq,
                        "index": idx,
                        "title": title,
                        "snippet": snippet[:300],
                    }
                )
            except Exception as e:
                print(f"    ⚠️ OG画像読込スキップ index={idx}: {e}")

        if not manifest:
            return {}

        prompt = f"""各画像はニュース記事の代表画像（OG）です。manifest の title/snippet と照合し、
記事の主題を視覚的に示すか判定してください。

manifest:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

- relevant: true … 記事内容と直接関係する写真・図・グラフ
- relevant: false … ロゴのみ、汎用ストック写真、広告、無関係

JSONのみ:
{{"judgments": [{{"index": 0, "relevant": true, "reason": "20字以内"}}]}}
"""

        parts.append(types.Part.from_text(text=prompt))

        try:
            client = GeminiClient._get_text_client()
            response = client.models.generate_content(
                model=GeminiClient.MODEL_FLASH,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(tools=[]),
            )
            text = re.sub(r"```json\s*|```\s*", "", (response.text or "")).strip()
            data = json.loads(text)
            out: Dict[int, Dict[str, Any]] = {}
            for row in data.get("judgments", []):
                if isinstance(row, dict) and "index" in row:
                    out[int(row["index"])] = {
                        "relevant": bool(row.get("relevant")),
                        "reason": str(row.get("reason", "")),
                    }
            print(f"  🔍 OG関連性バッチ判定: {len(out)} 件")
            return out
        except Exception as e:
            print(f"  ⚠️ OGバッチVision判定失敗: {e}")
            return {}
