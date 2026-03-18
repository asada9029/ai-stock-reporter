import json
from pathlib import Path
from src.video_generation.thumbnail_generator import ThumbnailGenerator

def test_thumbnail_generation():
    # 最新の収集データを探す
    data_dir = Path("data/collected_data")
    json_files = sorted(data_dir.glob("aggregated_data_*.json"), reverse=True)
    
    if not json_files:
        print("❌ 収集データが見つかりません。")
        return

    latest_data_path = json_files[0]
    print(f"📄 使用するデータ: {latest_data_path.name}")
    
    with open(latest_data_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    tg = ThumbnailGenerator()
    
    # 1. 分析データから生成
    print("\n--- テスト1: 分析データから生成 ---")
    thumb_path = tg.create_thumbnail_from_analysis(
        analysis_result=analysis_data,
        video_type="evening",
        output_path="output/test_thumbnail_auto.png"
    )
    print(f"✅ 生成完了: {thumb_path}")

    # 2. カスタムタイトルで生成
    print("\n--- テスト2: カスタムタイトルで生成 ---")
    thumb_path2 = tg.create_thumbnail(
        title="日経平均5万円突破！歴史的な爆騰の理由とは？",
        date="2026年02月10日",
        highlights=[
            "自民党圧勝で政治的安定感",
            "半導体関連株に強い買い",
            "今夜の米国株の見通し"
        ],
        video_type="evening",
        output_path="output/test_thumbnail_custom.png"
    )
    print(f"✅ 生成完了: {thumb_path2}")

if __name__ == "__main__":
    test_thumbnail_generation()
