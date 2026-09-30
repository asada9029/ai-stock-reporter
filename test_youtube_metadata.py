#!/usr/bin/env python3
"""YouTubeメタデータ生成の単体テスト。"""
from src.upload.youtube_metadata import (
    build_youtube_title,
    build_youtube_description,
    extract_shorts_topic_from_scenes,
)
from src.video_generation.thumbnail_generator import ThumbnailGenerator


def test_longform_title_hook_first():
    title = build_youtube_title(
        "morning_video",
        "【AMD時価総額1兆ドル超え】半導体覇権争い…",
        date_str="09/30",
    )
    assert title.startswith("【AMD時価総額1兆ドル超え】")
    assert "マイカブ 09/30朝刊" in title
    assert "初心者向け" not in title
    assert not title.startswith("【今日の株ニュース")


def test_shorts_title_includes_topic():
    a = build_youtube_title("shorts_a", "不可抗力通知", date_str="09/30")
    b = build_youtube_title("shorts_b", "AMD", date_str="09/30")
    assert a == "【株用語】不可抗力通知とは？1分で解説【09/30】"
    assert b == "【注目銘柄】AMD｜今日の動きをチェック【09/30】"


def test_empty_shorts_hook_has_fallback_not_blank():
    title = build_youtube_title("shorts_a", "", date_str="09/30")
    desc = build_youtube_description("shorts_a", "", [], date_str="09/30")
    assert "株用語" in title
    assert "本日は「」について" not in desc
    assert desc.startswith("「株用語」を1分でやさしく解説")


def test_extract_shorts_topic_from_scenes():
    scenes = [
        {
            "explained_term": "不可抗力通知",
            "on_screen_text": [
                "■不可抗力通知",
                "・契約を守れない宣言",
                "・AI需要の供給不安に",
            ],
        }
    ]
    topic, highlights = extract_shorts_topic_from_scenes(scenes, "shorts_a")
    assert topic == "不可抗力通知"
    assert "契約を守れない宣言" in highlights


def test_thumbnail_duplicate_topic_detection():
    tg = ThumbnailGenerator()
    recent = [
        "【AMD時価総額1兆ドル突破】半導体覇権争い…",
        "【米国債利回り20年ぶり高値】株安連鎖の波紋",
    ]
    assert tg._is_duplicate_topic("【AMD時価総額1兆ドル超え】半導体覇権争い…", recent)
    assert not tg._is_duplicate_topic("【旭有機材サプライズ増配】大幅続伸の裏側", recent)


if __name__ == "__main__":
    test_longform_title_hook_first()
    test_shorts_title_includes_topic()
    test_empty_shorts_hook_has_fallback_not_blank()
    test_extract_shorts_topic_from_scenes()
    test_thumbnail_duplicate_topic_detection()
    print("OK")
