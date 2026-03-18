import os
import json
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.video_generation.structured_pipeline import compose_video_from_analysis

def test_bgm_and_voice():
    print("🎵 BGMと音声の合成テストを開始します...")
    
    # テスト用の出力パス
    output_path = "output/bgm_test.mp4"
    assets_dir = "src/assets"
    
    # 1. 最小限の動画構成
    video_structure = {
        "video_type": "test",
        "total_duration": 30,
        "sections": [
            {"name": "opening", "duration": 10},
            {"name": "market_indices", "duration": 20}
        ]
    }
    
    # 2. 最小限の分析データ
    analysis_data = {
        "timestamp": "2026-02-09 10:00:00",
        "attention_news": [
            {"title": "BGM合成のテスト中です", "snippet": "音楽と声が綺麗に混ざっているか確認してください。"}
        ],
        "market_indices": {
            "NIKKEI": {
                "name": "日経平均",
                "current_price": "38,000円",
                "change_percent": "+1.5%",
                "chart_image_path": "src/assets/images/studio_main.png"
            }
        }
    }

    # 3. 実行
    print("➡️ パイプラインを実行中（音声生成とBGM合成）...")
    try:
        # ScriptGeneratorのモック化（LLMを使わず固定シーンを返す）
        from unittest.mock import MagicMock
        from src.analysis.script_generator import ScriptGenerator
        
        # 固定のシーンデータ
        mock_scenes = [
            {
                "scene": 1,
                "section_title": "■ BGM合成テスト：オープニング",
                "duration": 10,
                "text": "こんにちは。四国めたんです。ただいま、BGMと音声の合成テストを行っています。Garden Partyの音楽が綺麗に流れているか確認してくださいね。",
                "on_screen_text": ["■ BGMテスト中", "  └ Garden Partyをループ再生"],
                "emotion": "happy",
                "image_type": "bg_only",
                "target_files": []
            },
            {
                "scene": 2,
                "section_title": "■ BGM合成テスト：マーケット",
                "duration": 15,
                "text": "続いて、マーケット指標の確認シーンです。BGMの音量は、私の声を邪魔しないように15パーセントに設定されています。最後はフェードアウトして終わりますよ。",
                "on_screen_text": ["■ 音量バランスの確認", "  └ BGM音量は15%に設定"],
                "emotion": "normal",
                "image_type": "chart",
                "target_files": ["src/assets/images/studio_main.png"]
            }
        ]

        # ScriptGeneratorをパッチしてLLMを呼ばせない
        import src.video_generation.structured_pipeline as pipeline
        original_sg = pipeline.ScriptGenerator
        
        mock_sg_instance = MagicMock()
        mock_sg_instance.generate_structured_scenes.return_value = mock_scenes
        pipeline.ScriptGenerator = lambda: mock_sg_instance

        try:
            result_path = compose_video_from_analysis(
                video_structure=video_structure,
                analysis_data=analysis_data,
                output_video=output_path,
                assets_dir=assets_dir
            )
        finally:
            # 元に戻す
            pipeline.ScriptGenerator = original_sg
        
        if result_path and os.path.exists(result_path):
            print(f"\n✅ テスト動画が生成されました: {result_path}")
            print("以下の点を確認してください：")
            print("1. BGM（Garden Party）が流れているか")
            print("2. 四国めたんの声がBGMに埋もれず聞こえるか（BGM音量15%設定）")
            print("3. 動画の最初と最後にBGMがフェードイン・アウトするか")
        else:
            print("\n❌ 動画の生成に失敗しました。")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # フォルダ作成
    os.makedirs("output", exist_ok=True)
    test_bgm_and_voice()
