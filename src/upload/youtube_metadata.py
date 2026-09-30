"""
YouTubeタイトル・概要欄の生成。
クリック理由（フック）を先頭に置き、日付ブランドは末尾に回す。
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytz

from src.utils.market_calendar import get_next_market_open


def _jst_now() -> datetime.datetime:
    return datetime.datetime.now(pytz.timezone("Asia/Tokyo"))


def market_schedule_video_type(video_type: str) -> str:
    """
    市場カレンダー判定・次回配信計算に使う「本編相当」のタイプを返す。
    shorts は実行時刻(JST)から朝/夜を推定する。
    """
    if "shorts" not in video_type:
        return video_type
    h = _jst_now().hour
    return "morning_video" if 5 <= h < 12 else "evening_video"


def _clean_hook(text: str, fallback: str) -> str:
    hook = re.sub(r"\s+", " ", (text or "").strip())
    hook = re.sub(r"【\s*初心者向け\s*】\s*$", "", hook).strip()
    if not hook or hook in ("「」", "本日の株式市場まとめ"):
        return fallback
    if re.fullmatch(r"[「」『』【】…・\s]+", hook):
        return fallback
    return hook


def _slot_label(video_type: str) -> str:
    if "morning" in video_type:
        return "朝刊"
    if "evening" in video_type:
        return "夕刊"
    return ""


def extract_shorts_topic_from_scenes(
    scenes: Optional[Sequence[Dict[str, Any]]],
    video_type: str = "shorts_a",
) -> Tuple[str, List[str]]:
    """
    ショート台本から題材（用語名 / 企業名）と概要用ハイライトを抽出する。
    Returns: (topic, highlights)
    """
    scenes = list(scenes or [])
    topic = ""
    bullets: List[str] = []

    for sc in scenes:
        term = str(sc.get("explained_term") or "").strip()
        if term:
            topic = term
        ost = sc.get("on_screen_text") or []
        if not isinstance(ost, list):
            continue
        for line in ost:
            s = str(line).strip()
            if not s:
                continue
            if s.startswith("■") and not topic:
                topic = s.lstrip("■").strip()
            elif s.startswith("・") or s.startswith("└"):
                body = s.lstrip("・└ ").strip()
                if body and body not in bullets:
                    bullets.append(body)

        if topic and len(bullets) >= 2:
            break

    if not topic:
        topic = "株用語" if "shorts_a" in video_type else "注目銘柄"

    return topic, bullets[:3]


def build_youtube_title(
    video_type: str,
    thumbnail_title: str = "",
    *,
    date_str: Optional[str] = None,
) -> str:
    """フック先頭・日付末尾のタイトルを組み立てる。【初心者向け】は付けない。"""
    date_str = date_str or _jst_now().strftime("%m/%d")
    is_shorts = "shorts" in video_type

    if is_shorts:
        topic = _clean_hook(
            thumbnail_title,
            "株用語" if "shorts_a" in video_type else "注目銘柄",
        )
        if len(topic) > 28:
            topic = topic[:27] + "…"
        if "shorts_a" in video_type:
            return f"【株用語】{topic}とは？1分で解説【{date_str}】"
        return f"【注目銘柄】{topic}｜今日の動きをチェック【{date_str}】"

    slot = _slot_label(video_type)
    fallback = "米国株市場まとめ" if "morning" in video_type else "日本株市場まとめ"
    hook = _clean_hook(thumbnail_title, fallback)
    if len(hook) > 48:
        hook = hook[:47] + "…"
    return f"{hook}｜マイカブ {date_str}{slot}"


def build_youtube_description(
    video_type: str,
    thumbnail_title: str = "",
    thumbnail_highlights: Optional[Sequence[str]] = None,
    chapters_text: str = "",
    *,
    date_str: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> str:
    """概要欄。先頭行に検索されやすいフックを置く。"""
    now = now or _jst_now()
    date_str = date_str or now.strftime("%m/%d")
    highlights = [h for h in (thumbnail_highlights or []) if str(h).strip()]
    is_shorts = "shorts" in video_type

    if "shorts_a" in video_type:
        default_hook = "株用語"
    elif is_shorts:
        default_hook = "注目銘柄"
    elif "morning" in video_type:
        default_hook = "米国株市場まとめ"
    else:
        default_hook = "日本株市場まとめ"

    hook = _clean_hook(thumbnail_title, default_hook)

    if is_shorts:
        if "shorts_a" in video_type:
            lead = (
                f"「{hook}」を1分でやさしく解説します。"
                "今日のマーケットを読むときに押さえておきたい株用語です。"
            )
            impact = "忙しいときの復習用に、サクッとどうぞ。"
            hashtags = (
                "#日本株\n#日経平均\n#米国株\n#株用語\n#株ニュース\n"
                "#投資初心者\n#株価予想\n#Shorts\n#マイカブ"
            )
            comment_cta = (
                f"「{hook}」のほかに解説してほしい用語があれば、コメントで教えてください！"
            )
            seo_keywords = f"{hook}, 株用語, 投資初心者, 株ニュース, 新NISA, S&P500"
        else:
            lead = f"注目銘柄「{hook}」の動きをサクッと解説します。"
            impact = "チャートが動いている銘柄のポイント整理です。投資判断の参考材料としてどうぞ。"
            hashtags = (
                "#日本株\n#日経平均\n#米国株\n#S&P500\n#注目銘柄\n"
                "#株価予想\n#Shorts\n#マイカブ"
            )
            comment_cta = "明日いちばん気になる銘柄があれば、コメントで教えてください！"
            seo_keywords = f"{hook}, 注目銘柄, 株価予想, 日本株, 米国株, S&P500"
    elif "morning" in video_type:
        lead = (
            f"「{hook}」を中心に、昨晩の米国株の動きと日本株への影響を初心者向けに解説します。"
        )
        impact = "S&P500・セクター騰落・注目ニュースを、これ一本でざっくり把握できます。"
        hashtags = "#米国株\n#S&P500\n#株ニュース\n#投資初心者\n#株価予想\n#マイカブ"
        comment_cta = "今日いちばん気になるのは金利？半導体？為替？コメントで教えてください！"
        seo_keywords = "株価予想, 明日の注目銘柄, 株式投資, 新NISA, 資産運用, 日経平均, S&P500"
    else:
        lead = f"「{hook}」を中心に、本日の日本株市場の動きを初心者向けに解説します。"
        impact = "日経平均・注目銘柄・決算材料を、仕事終わりにサクッと確認できます。"
        hashtags = (
            "#日本株\n#日経平均\n#株ニュース\n#投資初心者\n"
            "#明日の注目銘柄\n#株価予想\n#マイカブ"
        )
        comment_cta = "今日の市場でいちばん気になったニュースを、コメントで教えてください！"
        seo_keywords = "株価予想, 明日の注目銘柄, 株式投資, 新NISA, 資産運用, 日経平均, S&P500"

    news_bits = [hook] + [
        str(h).strip()
        for h in highlights
        if str(h).strip() and str(h).strip() != hook
    ]
    news_bits = [b for b in news_bits if b and b not in ("「」",)]
    if len(news_bits) > 1:
        news_intro = "本日のポイント：" + " / ".join(news_bits[:4]) + "\n"
    else:
        news_intro = ""

    schedule_type = market_schedule_video_type(video_type)
    next_upload = get_next_market_open(schedule_type)
    next_date_str = next_upload.strftime("%m/%d")
    next_time_str = next_upload.strftime("%H:%M")
    if "morning" in schedule_type:
        is_gap = next_upload.date() != now.date()
    else:
        is_gap = (next_upload.date() - now.date()).days > 1

    next_info = f"【次回の配信予定】\n次回は {next_date_str} {next_time_str} 頃に投稿予定です。"
    if is_gap:
        next_info += "（※市場の休日のため、少し間が空きますが楽しみにお待ちください！）"

    chapters_section = ""
    if chapters_text and not is_shorts:
        chapters_section = f"【チャプター】\n{chapters_text}\n\n"

    description = f"""{lead}
{news_intro}{impact}

{chapters_section}【本日のキーワード】
{seo_keywords}

【本チャンネルについて】
マイカブ（MaiKabu）は、毎日の株ニュースを投資初心者の方に向けて、専門用語を抑えてやさしくお届けするチャンネルです。
日本株（日経平均・高配当株）や米国株（S&P500・ナスダック）を中心に、新NISAでの資産運用に役立つ最新のマーケット動向や注目ニュースを更新しています。

忙しい朝や仕事終わりの時間に、これ一本で「今の相場」が丸わかり！
ぜひチャンネル登録をして、一緒に投資の知識を深めていきましょう。

※本動画は情報提供を目的としたものであり、特定の銘柄や投資判断を推奨するものではありません。

【リクエスト募集中！】
{comment_cta}

{next_info}

{hashtags}
"""
    return description


def generate_youtube_metadata(
    video_type: str,
    thumbnail_title: str,
    thumbnail_highlights: Optional[Sequence[str]] = None,
    chapters_text: str = "",
) -> Tuple[str, str]:
    """サムネイル文言などからタイトルと概要欄を生成する。"""
    title = build_youtube_title(video_type, thumbnail_title)
    description = build_youtube_description(
        video_type,
        thumbnail_title,
        thumbnail_highlights,
        chapters_text,
    )
    return title, description
