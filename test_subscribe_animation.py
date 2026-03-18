import os
from pathlib import Path
from src.video_generation.structured_video_composer import render_scenes_to_video

def test_subscribe_only():
    """チャンネル登録シーンのみを生成するテスト"""
    print("\n🎬 チャンネル登録シーン（単体）のテストを開始します...")
    
    # チャンネル登録シーンのみの構成
    # pipeline.py で自動追加される内容を模倣
    scenes = [
        {
            "scene": 1,
            "section_title": "subscribe",
            "duration": 5.0, # テスト用に5秒
            "text": "チャンネル登録よろしくお願いします！",
            "on_screen_text": [],
            "emotion": "happy",
            "image_type": "bg_only",
            "bg_name": "bg_subscribe",
            "target_files": [],
            "segments": [
                {"text": "チャンネル登録よろしくお願いします！", "duration": 5.0, "start": 0.0}
            ]
        }
    ]

    output_path = "output/test_subscribe_only.mp4"
    
    # 直接レンダリング関数を呼ぶ
    result_path = render_scenes_to_video(
        scenes=scenes,
        output_path=output_path,
        assets_dir="src/assets",
        size=(1920, 1080),
        fps=24
    )
    
    if result_path and os.path.exists(result_path):
        print(f"✅ テスト動画が生成されました: {result_path}")
        print("クリーム背景とアニメーションのみが表示されているか確認してください。")
    else:
        print("❌ 動画生成に失敗しました。")

if __name__ == "__main__":
    test_subscribe_only()
