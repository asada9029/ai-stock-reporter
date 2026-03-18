#!/usr/bin/env python3
"""
YouTube Upload Test Script.
Use this to test the uploader without running the full pipeline.
"""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

load_dotenv()

from src.upload.youtube_uploader import YouTubeUploader, get_publish_time

def test_upload():
    # --- テスト設定（ここを直接書き換えてください） ---
    TEST_TYPE = "morning_video"  # "morning_video" or "evening_video"
    TEST_VIDEO_PATH = f"output/final_video_{TEST_TYPE}.mp4"
    TEST_THUMBNAIL_PATH = f"output/thumbnail_final_video_{TEST_TYPE}.png"
    IS_PUBLIC = True  # Trueなら即時公開、Falseなら予約投稿
    # ----------------------------------------------

    print(f"🧪 YouTubeアップロードテスト開始: {TEST_TYPE}")
    
    # ファイルの存在確認
    if not os.path.exists(TEST_VIDEO_PATH):
        print(f"❌ エラー: テスト用の動画ファイルが見つかりません: {TEST_VIDEO_PATH}")
        return
    
    title = f"【テスト】自動投稿テスト ({TEST_TYPE})"
    description = "これはAI Stock Reporterのアップロードテストです。"
    
    # 予約時間の取得
    publish_at = None if IS_PUBLIC else get_publish_time(TEST_TYPE)
    
    print(f"📝 タイトル: {title}")
    if publish_at:
        print(f"⏰ 予約時間: {publish_at}")
    else:
        print("⏰ 公開設定: 即時公開 (public)")

    try:
        uploader = YouTubeUploader()
        video_id = uploader.upload_video(
            video_path=TEST_VIDEO_PATH,
            title=title,
            description=description,
            publish_at=publish_at,
            thumbnail_path=TEST_THUMBNAIL_PATH if os.path.exists(TEST_THUMBNAIL_PATH) else None,
            category_id="25"
        )
        print(f"✅ テストアップロード成功！ Video ID: {video_id}")
        print(f"確認URL: https://www.youtube.com/watch?v={video_id}")
        print("\n※確認後、YouTube Studioから手動で削除してください。")
    except Exception as e:
        print(f"❌ テストアップロード失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_upload()
