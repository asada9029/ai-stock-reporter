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

def generate_youtube_metadata(video_type, thumbnail_title, thumbnail_highlights):
    """サムネイルの文言などからタイトルと概要欄を生成する"""
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.datetime.now(jst)
    date_str = now.strftime("%m/%d") # YYYY/MM/DD -> MM/DD
    
    is_shorts = "shorts" in video_type
    
    if is_shorts:
        if "shorts_a" in video_type:
            base_title = f"【爆速！今日の株ニュース｜{date_str}】"
            impact_desc = "今日の重要ニュース3つを1分で解説！本編動画ではさらに詳しく深掘りしています。"
            hashtags = "#日本株\n#日経平均\n#米国株\n#S&P500\n#株ニュース\n#投資初心者\n#株価予想\n#Shorts\n#マイカブ"
        else:
            base_title = f"【明日の注目銘柄｜{date_str}】"
            impact_desc = "チャートが動いている注目銘柄をピックアップ！明日の投資戦略の参考にしてください。"
            hashtags = "#日本株\n#日経平均\n#米国株\n#S&P500\n#注目銘柄\n#株価予想\n#Shorts\n#マイカブ"
    elif "morning" in video_type:
        base_title = f"【今日の株ニュース｜{date_str} 朝刊】"
        impact_desc = "また、米国株（S&P500）の今後の株価予想や、セクター騰落率、日本株への影響について初心者の方にもわかりやすく解説します！"
        hashtags = "#米国株\n#S&P500\n#株ニュース\n#投資初心者\n#株価予想\n#マイカブ"
    else:
        base_title = f"【今日の株ニュース｜{date_str} 夕刊】"
        impact_desc = "また、日本株（日経平均）の今後の株価予想や、明日の注目銘柄、注目の決算速報、セクター騰落率について初心者の方にもわかりやすく解説します！"
        hashtags = "#日本株\n#日経平均\n#株ニュース\n#投資初心者\n#明日の注目銘柄\n#株価予想\n#マイカブ"

    # タイトルはサムネイルのメインタイトルを使用し、最後に【初心者向け】を追加
    title = f"{base_title}{thumbnail_title}【初心者向け】"
    
    # 次の配信予定を計算（ショートは本編スロットに合わせて判定）
    schedule_type = _market_schedule_video_type(video_type)
    next_upload = get_next_market_open(schedule_type)
    next_date_str = next_upload.strftime("%m/%d")
    next_time_str = next_upload.strftime("%H:%M")
    
    # 休日を挟む場合のメッセージ
    if "morning" in schedule_type:
        is_gap = next_upload.date() != now.date()
    else:
        is_gap = (next_upload.date() - now.date()).days > 1

    next_info = f"【次回の配信予定】\n次回は {next_date_str} {next_time_str} 頃に投稿予定です。"
    if is_gap:
        next_info += "（※市場の休日のため、少し間が空きますが楽しみにお待ちください！）"

    # ニュースの紹介文を作成
    news_intro = ""
    if thumbnail_highlights:
        news_list_str = "」、「".join(thumbnail_highlights)
        news_intro = f"本日は「{thumbnail_title}」、「{news_list_str}」について解説します。\n"
    else:
        news_intro = f"本日は「{thumbnail_title}」について解説します。\n"

    description = f"""{news_intro}{impact_desc}

【本日のキーワード】
株価予想、明日の注目銘柄、株式投資、新NISA、資産運用、日経平均、S&P500

【本チャンネルについて】
マイカブ（MaiKabu）は、毎日の株ニュースを投資初心者の方に向けて、専門用語を抑えてやさしくお届けするチャンネルです。
日本株（日経平均・高配当株）や米国株（S&P500・ナスダック）を中心に、新NISAでの資産運用に役立つ最新のマーケット動向や注目ニュースを毎日2本（朝・夜）更新で徹底解説しています。

忙しい朝や仕事終わりの時間に、これ一本で「今の相場」が丸わかり！
ぜひチャンネル登録をして、一緒に投資の知識を深めていきましょう。

※本動画は情報提供を目的としたものであり、特定の銘柄や投資判断を推奨するものではありません。

【リクエスト募集中！】
このチャンネルでは、皆さんの「見たい！」「知りたい！」を形にしていきたいです。
もし取り入れてほしい要素や企画があれば、ぜひコメント欄で教えてください！

{next_info}

{hashtags}
"""
    return title, description


def _market_schedule_video_type(video_type: str) -> str:
    """
    市場カレンダー判定・次回配信計算に使う「本編相当」のタイプを返す。
    - shorts は GitHub Actions 上では本編直後に走る想定のため、実行時刻(JST)から朝/夜を推定する。
    """
    if "shorts" not in video_type:
        return video_type
    jst = pytz.timezone("Asia/Tokyo")
    h = datetime.datetime.now(jst).hour
    # 朝本編ジョブは JST 5:00 前後、夜本編ジョブは JST 15:47 前後
    return "morning_video" if 5 <= h < 12 else "evening_video"


def main():
    parser = argparse.ArgumentParser(description="AI Stock Reporter Production Entry Point")
    parser.add_argument(
        "--type",
        default="evening_video",
        choices=["morning_video", "evening_video", "shorts_a", "shorts_b"],
    )
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup")
    args = parser.parse_args()

    print(f"\n🚀 AI Stock Reporter (Production) 起動: {args.type}")

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
        # shorts_a/b の場合は、直近の朝または夜のデータを流用する
        if "shorts" in args.type:
            # 実行時間帯によって朝か夜か決める（5-12時は朝、それ以外は夜のデータを参照）
            now_hour = datetime.datetime.now(pytz.timezone('Asia/Tokyo')).hour
            video_category = "morning" if 5 <= now_hour < 12 else "evening"
        else:
            video_category = "morning" if "morning" in args.type else "evening"
            
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
        data_dir = Path("data/collected_data")
        data_files = sorted(data_dir.glob(f"aggregated_data_{video_category}_*.json"), reverse=True)
        latest_data_path = str(data_files[0]) if data_files else None

        # 動画の合成
        video_path = f"output/final_video_{args.type}.mp4"
        enriched_data = {"prev_ir_analysis": analysis_data.get("prev_ir_analysis", [])}
        
        # ショート動画の場合はサイズを変更
        video_size = (1080, 1920) if "shorts" in args.type else (1920, 1080)
        
        print("\n🎬 動画合成を開始します...")
        result_path, thumb_path, thumb_title, thumb_highlights = compose_video_from_analysis(
            video_structure=video_structure,
            analysis_data=analysis_data,
            enriched_data=enriched_data,
            output_video=video_path,
            assets_dir="src/assets",
            video_type=args.type,
            size=video_size
        )
        
        if not result_path or not os.path.exists(video_path):
            raise RuntimeError("動画生成に失敗しました。")
        print(f"✅ 動画生成完了: {video_path}")

        # 4. YouTubeアップロード
        if not args.skip_upload:
            print("\n📺 YouTubeへのアップロード・予約投稿を開始します...")
            title, description = generate_youtube_metadata(args.type, thumb_title, thumb_highlights)
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

if __name__ == "__main__":
    main()
