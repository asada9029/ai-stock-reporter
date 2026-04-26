import os
import sys
import json
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.data_collection.data_aggregator import DataAggregator
from src.video_generation.structured_pipeline import compose_video_from_analysis

def test_shorts_generation(shorts_type="shorts_a"):
    print(f"🚀 ショート動画テスト生成開始: {shorts_type}")
    
    # 1. データの準備
    video_category = "evening"
    data_dir = Path("data/collected_data")
    # 最新の集約データを探す
    data_files = sorted(data_dir.glob(f"aggregated_data_{video_category}_*.json"), reverse=True)
    
    if data_files:
        latest_data_path = data_files[0]
        print(f"📦 既存のデータを使用します: {latest_data_path}")
        with open(latest_data_path, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
    else:
        print("🔍 既存データが見つからないため、新規に収集します...")
        aggregator = DataAggregator()
        analysis_data = aggregator.aggregate_all_data(video_type=video_category)
    
    # 2. 構成の読み込み
    structure_path = project_root / "src/config/video_structure.json"
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    video_structure = structures.get(shorts_type)
    
    # 3. 動画生成
    video_path = f"output/test_{shorts_type}.mp4"
    video_size = (1080, 1920)
    
    result_path, thumb_path, thumb_title, thumb_highlights = compose_video_from_analysis(
        video_structure=video_structure,
        analysis_data=analysis_data,
        enriched_data={},
        output_video=video_path,
        assets_dir="src/assets",
        video_type=shorts_type,
        size=video_size
    )
    
    if result_path and os.path.exists(result_path):
        print(f"✅ ショート動画生成成功: {result_path}")
    else:
        print("❌ ショート動画生成失敗")

if __name__ == "__main__":
    # 案Aのテスト
    # test_shorts_generation("shorts_a")
    # 案Bのテスト（チャートがある場合）
    test_shorts_generation("shorts_b")
