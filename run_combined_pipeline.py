#!/usr/bin/env python3
"""
Combined pipeline to generate a full video based on the user's outline.
1. Collect data (DataAggregator)
2. Generate structured scenes (ScriptGenerator)
3. Compose video (StructuredPipeline)
"""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import shutil

# Add project root to path
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.data_collection.data_aggregator import DataAggregator
from src.analysis.script_generator import ScriptGenerator
from src.video_generation.structured_pipeline import compose_video_from_analysis
from src.utils.market_calendar import is_market_open

def cleanup_old_files():
    """
    過去の実行で生成された一時ファイルや中間データを削除する。
    """
    print("\n🧹 古い一時ファイルのクリーンアップを開始します...")
    
    # 削除対象のディレクトリ
    cleanup_dirs = [
        "data/collected_data",
        "data/scripts",
        "data/images",
        "output/market_charts",
        "output/sector_charts",
        "output/stock_charts",
        "data/cache"
    ]
    
    for dir_path in cleanup_dirs:
        p = Path(dir_path)
        if p.exists():
            print(f"  - {dir_path} 内のファイルを削除中...")
            for file in p.glob("*"):
                if file.is_file():
                    try:
                        file.unlink()
                    except Exception as e:
                        print(f"    ⚠️ 削除失敗: {file} ({e})")
    
    print("✅ クリーンアップ完了\n")

def main():
    parser = argparse.ArgumentParser(description="Run the full combined video generation pipeline.")
    parser.add_argument("--type", default="morning_video", choices=["morning_video", "evening_video"], help="Video type from video_structure.json")
    parser.add_argument("--out", help="Output video path (defaults to output/final_video_[type].mp4)")
    parser.add_argument("--skip-data", action="store_true", help="Skip data collection and use latest aggregated data")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup of old files")
    args = parser.parse_args()

    # デフォルトの出力パス設定
    if not args.out:
        args.out = f"output/final_video_{args.type}.mp4"

    # 市場の休日判定
    if not is_market_open(args.type):
        print(f"\n☕ 今日は市場の休日のため、{args.type} の生成をスキップします。")
        return

    # クリーンアップの実行
    if not args.no_cleanup and not args.skip_data:
        cleanup_old_files()

    # 1. Load video structure
    structure_path = project_root / "src/config/video_structure.json"
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    
    video_structure = structures.get(args.type)
    if not video_structure:
        print(f"Error: Video type '{args.type}' not found in {structure_path}")
        return

    # 2. Collect Data
    # 朝動画の場合は米国市場データを重視するようにDataAggregatorにヒントを出す
    video_category = "morning" if "morning" in args.type else "evening"
    
    if args.skip_data:
        print("Skipping data collection, looking for latest data...")
        data_dir = Path("data/collected_data")
        data_files = sorted(data_dir.glob(f"aggregated_data_{video_category}_*.json"), reverse=True)
        if not data_files:
            print(f"No collected data found for {video_category}. Running collection...")
            aggregator = DataAggregator()
            analysis_data = aggregator.aggregate_all_data(video_type=video_category)
        else:
            print(f"Using latest data: {data_files[0]}")
            with open(data_files[0], "r", encoding="utf-8") as f:
                analysis_data = json.load(f)
    else:
        print(f"Starting data collection for {video_category}...")
        aggregator = DataAggregator()
        analysis_data = aggregator.aggregate_all_data(video_type=video_category)

    # 3. Generate Video
    print("\nStarting video generation pipeline...")
    # enriched_data can include additional context if needed
    enriched_data = {
        "prev_ir_analysis": analysis_data.get("prev_ir_analysis", [])
    }
    
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_path = compose_video_from_analysis(
        video_structure=video_structure,
        analysis_data=analysis_data,
        enriched_data=enriched_data,
        output_video=str(output_path),
        assets_dir="src/assets",
        video_type=args.type # video_type を渡すように追加
    )

    if result_path:
        print(f"\n✅ Video generation successful! Output: {result_path}")
    else:
        print("\n❌ Video generation failed.")

if __name__ == "__main__":
    main()
