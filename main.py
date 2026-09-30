#!/usr/bin/env python3
"""
Main entry point for the AI Stock Reporter (Production).
Handles the full flow:
1. Check market holiday
2. Collect data (DataAggregator)
3. Generate video (StructuredPipeline)
4. Upload to YouTube (YouTubeUploader)
"""
import os
import sys
import argparse
import datetime
import pytz
import json
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from src.utils.market_calendar import is_market_open, get_next_market_open
from src.upload.youtube_uploader import YouTubeUploader, get_publish_time
from src.upload.youtube_metadata import (
    generate_youtube_metadata,
    market_schedule_video_type as _market_schedule_video_type,
)
from src.data_collection.data_aggregator import DataAggregator
from src.video_generation.structured_pipeline import compose_video_from_analysis

def cleanup_old_files():
    """過去の実行で生成された一時ファイルを削除する"""
    print("\n🧹 古い一時ファイルのクリーンアップを開始します...")
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
            for file in p.glob("*"):
                if file.is_file():
                    try:
                        file.unlink()
                    except Exception:
                        pass
    print("✅ クリーンアップ完了\n")


def main():
    parser = argparse.ArgumentParser(description="AI Stock Reporter Production Entry Point")
    parser.add_argument(
        "--type",
        default="evening_video",
        choices=["morning_video", "evening_video", "shorts_a", "shorts_b"],
    )
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup")
    parser.add_argument(
        "--presentation",
        default="classic",
        choices=["classic", "immersive"],
        help="動画演出モード（classic=現行, immersive=聞き中心・短い画面ラベル・セクションSE）",
    )
    args = parser.parse_args()

    print(f"\n🚀 AI Stock Reporter (Production) 起動: {args.type} [{args.presentation}]")

    market_schedule_type = _market_schedule_video_type(args.type)

    # 1. 市場の休日判定
    if not is_market_open(market_schedule_type):
        next_upload = get_next_market_open(market_schedule_type)
        next_date_str = next_upload.strftime("%m/%d")
        next_time_str = next_upload.strftime("%H:%M")
        print(f"\n☕ 今日は市場の休日のため、{args.type} の実行をスキップします。")
        print(f"📢 次回の配信は {next_date_str} {next_time_str} 頃を予定しています。楽しみにお待ちください！\n")
        return

    # 2. クリーンアップ
    if not args.no_cleanup:
        cleanup_old_files()

    # 3. 動画生成プロセス
    try:
        # 構成の読み込み
        structure_path = project_root / "src/config/video_structure.json"
        with open(structure_path, "r", encoding="utf-8") as f:
            structures = json.load(f)
        video_structure = structures.get(args.type)
        
        # データの集約
        # shorts_a/b は本編で保存済みの集約JSONを読む（Geminiの二重呼び出しを避ける）
        if "shorts" in args.type:
            now_hour = datetime.datetime.now(pytz.timezone('Asia/Tokyo')).hour
            video_category = "morning" if 5 <= now_hour < 12 else "evening"
        else:
            video_category = "morning" if "morning" in args.type else "evening"

        data_dir = Path("data/collected_data")
        if "shorts" in args.type:
            agg_files = sorted(
                data_dir.glob(f"aggregated_data_{video_category}_*.json"),
                reverse=True,
            )
            if not agg_files:
                raise RuntimeError(
                    f"ショート用の集約データがありません: {data_dir}/aggregated_data_{video_category}_*.json "
                    "（本編を先に同じジョブ内で実行するか、--no-cleanup で集約ファイルを残してください）"
                )
            with open(agg_files[0], "r", encoding="utf-8") as f:
                analysis_data = json.load(f)
            print(f"📂 ショート: 集約データを再利用しました → {agg_files[0]}")
        else:
            aggregator = DataAggregator()
            analysis_data = aggregator.aggregate_all_data(video_type=video_category)
        
        # 次の配信予定を計算して分析データに含める（台本用）
        next_upload = get_next_market_open(market_schedule_type)
        jst = pytz.timezone("Asia/Tokyo")
        now_jst = datetime.datetime.now(jst)
        if "morning" in market_schedule_type:
            is_holiday_gap = next_upload.date() != now_jst.date()
        else:
            is_holiday_gap = (next_upload.date() - now_jst.date()).days > 1
        analysis_data["next_delivery_info"] = {
            "date": next_upload.strftime("%m/%d"),
            "time": next_upload.strftime("%H:%M"),
            "is_holiday_gap": is_holiday_gap,
        }

        # 最新の集約データパスを取得
        data_files = sorted(
            data_dir.glob(f"aggregated_data_{video_category}_*.json"), reverse=True
        )
        latest_data_path = str(data_files[0]) if data_files else None

        # 動画の合成
        video_path = f"output/final_video_{args.type}.mp4"
        enriched_data = {"prev_ir_analysis": analysis_data.get("prev_ir_analysis", [])}
        
        # ショート動画の場合はサイズを変更
        video_size = (1080, 1920) if "shorts" in args.type else (1920, 1080)
        
        print("\n🎬 動画合成を開始します...")
        result_path, thumb_path, thumb_title, thumb_highlights, chapters_text = compose_video_from_analysis(
            video_structure=video_structure,
            analysis_data=analysis_data,
            enriched_data=enriched_data,
            output_video=video_path,
            assets_dir="src/assets",
            video_type=args.type,
            size=video_size,
            presentation_mode=args.presentation,
        )
        
        if not result_path or not os.path.exists(video_path):
            raise RuntimeError("動画生成に失敗しました。")
        print(f"✅ 動画生成完了: {video_path}")

        # 4. YouTubeアップロード
        if not args.skip_upload:
            print("\n📺 YouTubeへのアップロード・予約投稿を開始します...")
            title, description = generate_youtube_metadata(args.type, thumb_title, thumb_highlights, chapters_text)
            publish_at = get_publish_time(market_schedule_type)
            thumbnail_path = thumb_path if thumb_path else f"output/thumbnail_final_video_{args.type}.png"
            
            uploader = YouTubeUploader()
            uploader.upload_video(
                video_path=video_path,
                title=title,
                description=description,
                publish_at=publish_at,
                thumbnail_path=thumbnail_path,
                category_id="25"
            )
            print("✅ YouTubeへのアップロード・予約投稿が完了しました！")
        else:
            print("\n⏭️ アップロードをスキップしました。")

    except Exception as e:
        print(f"❌ プロセス実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) # GitHub Actions 等で失敗として検知させるため非ゼロで終了

if __name__ == "__main__":
    main()
