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
        self.fetch_og = os.getenv("NEWS_ENRICH_OG", "true").lower() not in (
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

            if self.fetch_og:
                url = item.get("url") or ""
                og_url = fetch_og_image_url(url)
                item["og_image_url"] = og_url
                if og_url:
                    ext = guess_extension(og_url)
                    local_path = os.path.join(out_dir, f"{tag}_{i}_{ts}_og.{ext}")
                    if download_image(og_url, local_path):
                        item["og_image_path"] = local_path

        og_judgments = self._batch_judge_og_images(news_list)

        chart_budget = self.max_chart_captures
        attached = 0

        for i, item in enumerate(news_list):
            judgment = og_judgments.get(i, {})
            og_path = item.get("og_image_path")
            use_og = bool(judgment.get("relevant")) and og_path and os.path.exists(og_path)

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
