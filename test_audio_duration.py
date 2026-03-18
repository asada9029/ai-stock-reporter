import json
from pathlib import Path
import re
from src.data_collection.data_aggregator import DataAggregator
from src.analysis.script_generator import ScriptGenerator
from src.voice_generation.voice_client import VOICEVOXClient
from moviepy import AudioFileClip

def _split_text_segments(s: str, max_c: int):
    if not s: return []
    s = s.strip()
    parts = re.split(r'([。、！？!?])', s)
    combined_parts = []
    for i in range(0, len(parts)-1, 2):
        combined_parts.append(parts[i] + parts[i+1])
    if len(parts) % 2 == 1:
        combined_parts.append(parts[-1])
    combined_parts = [p.strip() for p in combined_parts if p.strip()]
    segs, cur = [], ""
    for p in combined_parts:
        if len(cur) + len(p) <= max_c:
            cur += p
        else:
            if cur: segs.append(cur)
            if len(p) > max_c:
                while len(p) > max_c:
                    segs.append(p[:max_c])
                    p = p[max_c:]
                cur = p
            else:
                cur = p
    if cur: segs.append(cur)
    return segs

def test_audio_duration(video_type="morning_video"):
    print(f"🚀 VOICEVOX音声合成を含めた【{video_type}】の尺テストを開始します...")
    
    # 1. データ収集
    print("\n--- Step 1: データ収集 ---")
    aggregator = DataAggregator()
    analysis_data = aggregator.aggregate_all_data(video_type=video_type)
    
    # 2. 動画構成の読み込み
    print("\n--- Step 2: 動画構成の読み込み ---")
    config_path = Path("src/config/video_structure.json")
    with open(config_path, "r", encoding="utf-8") as f:
        video_structures = json.load(f)
    video_structure = video_structures.get(video_type)
    
    if not video_structure:
        print(f"❌ {video_type} の構成が見つかりません。")
        return

    # 3. 台本生成
    print("\n--- Step 3: 台本生成 (LLM) ---")
    generator = ScriptGenerator()
    scenes = generator.generate_structured_scenes(
        video_structure=video_structure,
        analysis_data=analysis_data
    )
    
    # 4. 音声合成と実測
    print("\n--- Step 4: 音声合成による実測 (VOICEVOX) ---")
    vv = VOICEVOXClient()
    audio_dir = Path("data/audio_test")
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    total_real_duration = 0.0
    
    for i, sc in enumerate(scenes):
        text = sc.get("text", "")
        padding_before = 0.3
        padding_after = 0.3
        max_chars = 50
        
        segments_texts = _split_text_segments(text, max_chars)
        scene_audio_duration = 0.0
        
        print(f"Processing Scene {i+1}/{len(scenes)}: {sc.get('section_title')}...")
        
        for j, seg_text in enumerate(segments_texts):
            audio_path = audio_dir / f"test_scene_{i+1}_seg_{j+1}.wav"
            try:
                vv.generate_and_save(seg_text, str(audio_path))
                with AudioFileClip(str(audio_path)) as ac:
                    scene_audio_duration += ac.duration
            except Exception as e:
                print(f"  ⚠️ 音声生成失敗: {e}")
                scene_audio_duration += len(seg_text) / 4.0 # 失敗時は推定値
        
        scene_total = padding_before + scene_audio_duration + padding_after
        total_real_duration += scene_total
        print(f"  => シーン実測尺: {scene_total:.2f}s")

    # 5. 結果表示
    print("\n--- Step 5: 最終結果 ---")
    minutes = int(total_real_duration // 60)
    seconds = int(total_real_duration % 60)
    
    print(f"🎬 総シーン数: {len(scenes)}")
    print(f"⏱️ VOICEVOX実測合計時間: {minutes}分 {seconds}秒 ({total_real_duration:.1f}秒)")
    
    if total_real_duration >= 480:
        print("✅ 目標の8分（480秒）を実測で超えています！")
    else:
        print(f"⚠️ 目標の8分に届いていません。不足分: {480 - total_real_duration:.1f}秒")

if __name__ == "__main__":
    # テストしたい動画タイプを指定 ("morning_video" または "evening_video")
    target_type = "morning_video"
    # target_type = "evening_video"
    test_audio_duration(video_type=target_type)
