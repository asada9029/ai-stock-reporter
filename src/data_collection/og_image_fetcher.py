"""
記事URLから OG / Twitter カード画像を取得する。
og:image は記事の「代表画像」（多くの場合ヒーロー画像・サムネ）として配信される。
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

META_IMAGE_KEYS = (
    ("property", "og:image"),
    ("property", "og:image:url"),
    ("property", "og:image:secure_url"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
)


def fetch_og_image_url(
    article_url: str,
    *,
    timeout: int | None = None,
) -> Optional[str]:
    """HTML の meta タグから代表画像 URL を抽出。"""
    if not article_url or article_url == "#":
        return None

    timeout = timeout or int(os.getenv("NEWS_OG_FETCH_TIMEOUT_SEC", "15"))
    headers = {"User-Agent": os.getenv("NEWS_FETCH_USER_AGENT", DEFAULT_USER_AGENT)}

    try:
        resp = requests.get(article_url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ⚠️ OG取得HTTP失敗: {article_url[:80]}... ({e})")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    base = resp.url or article_url

    for attr, key in META_IMAGE_KEYS:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            return _normalize_image_url(tag["content"].strip(), base)

    # link rel=image_src 等のフォールバック
    link = soup.find("link", rel=re.compile(r"image_src", re.I))
    if link and link.get("href"):
        return _normalize_image_url(link["href"].strip(), base)

    return None


def _normalize_image_url(raw: str, base_url: str) -> Optional[str]:
    if not raw or raw.startswith("data:"):
        return None
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return urljoin(base_url, raw)


def download_image(
    image_url: str,
    dest_path: str,
    *,
    timeout: int | None = None,
    min_bytes: int | None = None,
) -> bool:
    """画像をローカルに保存。成功時 True。"""
    min_bytes = min_bytes or int(os.getenv("NEWS_OG_MIN_FILE_BYTES", "8000"))
    timeout = timeout or int(os.getenv("NEWS_OG_FETCH_TIMEOUT_SEC", "15"))
    headers = {"User-Agent": os.getenv("NEWS_FETCH_USER_AGENT", DEFAULT_USER_AGENT)}

    try:
        resp = requests.get(image_url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            print(f"    ⚠️ OG URLが画像ではない: {content_type}")
            return False

        data = resp.content
        if len(data) < min_bytes:
            print(f"    ⚠️ OG画像が小さすぎます ({len(data)} bytes)")
            return False

        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    ⚠️ OG画像ダウンロード失敗: {e}")
        return False


def guess_extension(image_url: str, content_path: Optional[str] = None) -> str:
    path = urlparse(image_url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ext.lstrip(".")
    if content_path and os.path.exists(content_path):
        with open(content_path, "rb") as f:
            head = f.read(12)
        if head.startswith(b"\x89PNG"):
            return "png"
        if head[6:10] in (b"JFIF", b"Exif"):
            return "jpg"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "webp"
    return "jpg"
