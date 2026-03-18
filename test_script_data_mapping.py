import json
import os
import argparse
from pathlib import Path
from src.analysis.script_generator import ScriptGenerator
from src.data_collection.data_aggregator import DataAggregator

def test_script_generation():
    parser = argparse.ArgumentParser(description="台本生成確認スクリプト")
    parser.add_argument("--type", default="morning", choices=["morning", "evening"], help="動画タイプ (morning or evening)")
    args = parser.parse_args()

    video_type = f"{args.type}_video"
    print(f"🔍 台本生成確認テスト開始 ({video_type})")
    
    # 1. 最新の集約データを取得
    data_dir = Path("data/collected_data")
    # 指定したタイプの最新ファイルを探す
    data_files = sorted(data_dir.glob(f"aggregated_data_{args.type}_*.json"), reverse=True)
    
    if not data_files:
        print(f"⚠️ {args.type} 用の集約データが見つかりません。データ収集を開始します...")
        aggregator = DataAggregator()
        analysis_data = aggregator.aggregate_all_data(video_type=args.type)
        print(f"✅ データ収集完了")
    else:
        with open(data_files[0], "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        print(f"✅ 使用データ: {data_files[0].name}")

    # 2. 動画構成の読み込み
    structure_path = Path("src/config/video_structure.json")
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    video_structure = structures.get(video_type)

    if not video_structure:
        print(f"❌ {video_type} の構成が見つかりません。")
        return

    # 3. 台本生成（LLM呼び出し）
    print("📡 LLMに台本とシーン構成を依頼中（これには数十秒かかります）...")
    sg = ScriptGenerator()
    try:
        scenes = sg.generate_structured_scenes(
            video_structure=video_structure,
            analysis_data=analysis_data,
            enriched_data={"prev_ir_analysis": analysis_data.get("prev_ir_analysis", [])}
        )
    except Exception as e:
        print(f"❌ LLM呼び出しエラー: {e}")
        return

    # 4. 台本内容の表示
    print("\n" + "="*80)
    print(f"🎬 生成された台本プレビュー ({video_type})")
    print("="*80)
    
    total_duration = 0
    for i, sc in enumerate(scenes):
        scene_num = sc.get("scene", i+1)
        section = sc.get("section_title", "---")
        duration = sc.get("duration", 0)
        text = sc.get("text", "")
        on_screen = sc.get("on_screen_text", [])
        images = sc.get("target_files", [])
        emotion = sc.get("emotion", "normal")
        
        total_duration += duration
        
        print(f"\n【Scene {scene_num}】 {section} ({duration}秒 / 感情: {emotion})")
        print(f"🎙️ 台本: {text}")
        if on_screen:
            print(f"📺 画面テキスト: {on_screen}")
        if images:
            print(f"🖼️ 使用画像: {images}")
        print("-" * 40)

    print("\n" + "="*80)
    minutes = int(total_duration // 60)
    seconds = int(total_duration % 60)
    print(f"✅ テスト完了: 全 {len(scenes)} シーン / 推定合計時間: {minutes}分{seconds}秒")
    print("="*80)

if __name__ == "__main__":
    test_script_generation()
