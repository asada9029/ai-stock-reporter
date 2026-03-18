"""
間（ポーズ）処理モジュール
台本の「（間）」を検出して無音を挿入
"""

import re
import wave
import io
import numpy as np
from typing import List, Dict, Tuple
from pathlib import Path


class PauseHandler:
    """間（ポーズ）処理クラス"""
    
    # 間の長さ（秒）
    DEFAULT_PAUSE = 0.8      # 通常の間
    LONG_PAUSE = 1.5         # 長めの間
    SHORT_PAUSE = 0.3        # 短い間
    
    # WAVファイルの標準設定
    SAMPLE_RATE = 24000      # サンプリングレート（VOICEVOX標準）
    CHANNELS = 1             # モノラル
    SAMPLE_WIDTH = 2         # 16bit
    
    def __init__(self):
        """初期化"""
        print("✅ PauseHandler 初期化完了")
    
    def parse_script_with_pauses(self, script: str) -> List[Dict]:
        """
        台本から「（間）」を検出してセグメントに分割
        
        Args:
            script: 台本テキスト
        
        Returns:
            List[Dict]: セグメントのリスト
                [
                    {"type": "text", "content": "テキスト"},
                    {"type": "pause", "duration": 0.8},
                    ...
                ]
        """
        segments = []
        
        # パターン定義
        patterns = {
            r'（(\d+(?:\.\d+)?)秒間?）': 'custom',    # （2秒間）など
            r'（長めの間）': 'long',
            r'（短い間）': 'short',
            r'（間）': 'default'
        }
        
        # 全パターンを結合した正規表現
        combined_pattern = '|'.join(f'({p})' for p in patterns.keys())
        
        # テキストを分割
        current_pos = 0
        
        for match in re.finditer(combined_pattern, script):
            # マッチ前のテキスト
            if match.start() > current_pos:
                text = script[current_pos:match.start()].strip()
                if text:
                    segments.append({
                        "type": "text",
                        "content": text
                    })
            
            # 間の種類を判定
            matched_text = match.group(0)
            
            if '秒間' in matched_text or '秒）' in matched_text:
                # カスタム秒数
                duration_match = re.search(r'(\d+(?:\.\d+)?)', matched_text)
                if duration_match:
                    duration = float(duration_match.group(1))
                else:
                    duration = self.DEFAULT_PAUSE
            elif '長めの間' in matched_text:
                duration = self.LONG_PAUSE
            elif '短い間' in matched_text:
                duration = self.SHORT_PAUSE
            else:  # （間）
                duration = self.DEFAULT_PAUSE
            
            segments.append({
                "type": "pause",
                "duration": duration
            })
            
            current_pos = match.end()
        
        # 残りのテキスト
        if current_pos < len(script):
            text = script[current_pos:].strip()
            if text:
                segments.append({
                    "type": "text",
                    "content": text
                })
        
        return segments
    
    def generate_silence(
        self,
        duration: float,
        sample_rate: int = None,
        channels: int = None,
        sample_width: int = None
    ) -> bytes:
        """
        無音データを生成
        
        Args:
            duration: 長さ（秒）
            sample_rate: サンプリングレート
            channels: チャンネル数
            sample_width: サンプル幅（バイト）
        
        Returns:
            bytes: 無音のWAVデータ
        """
        sample_rate = sample_rate or self.SAMPLE_RATE
        channels = channels or self.CHANNELS
        sample_width = sample_width or self.SAMPLE_WIDTH
        
        # 必要なサンプル数
        num_samples = int(sample_rate * duration)
        
        # 無音データ（ゼロ配列）
        silence = np.zeros(num_samples, dtype=np.int16)
        
        # WAVファイルとして出力
        output_buffer = io.BytesIO()
        
        with wave.open(output_buffer, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(sample_rate)
            wav.writeframes(silence.tobytes())
        
        return output_buffer.getvalue()
    
    def combine_audio_with_pauses(
        self,
        audio_segments: List[bytes],
        pause_segments: List[Dict]
    ) -> bytes:
        """
        音声セグメントと間を結合
        
        Args:
            audio_segments: 音声データのリスト
            pause_segments: セグメント情報（parse_script_with_pausesの出力）
        
        Returns:
            bytes: 結合された音声データ
        """
        if not audio_segments:
            raise ValueError("音声セグメントが空です")
        
        # 最初の音声からパラメータを取得
        with wave.open(io.BytesIO(audio_segments[0]), 'rb') as first_wav:
            sample_rate = first_wav.getframerate()
            channels = first_wav.getnchannels()
            sample_width = first_wav.getsampwidth()
        
        # 出力バッファ
        output_buffer = io.BytesIO()
        
        with wave.open(output_buffer, 'wb') as output_wav:
            output_wav.setnchannels(channels)
            output_wav.setsampwidth(sample_width)
            output_wav.setframerate(sample_rate)
            
            audio_index = 0
            
            for segment in pause_segments:
                if segment['type'] == 'text':
                    # 音声セグメントを追加
                    if audio_index < len(audio_segments):
                        with wave.open(io.BytesIO(audio_segments[audio_index]), 'rb') as audio_wav:
                            frames = audio_wav.readframes(audio_wav.getnframes())
                            output_wav.writeframes(frames)
                        audio_index += 1
                
                elif segment['type'] == 'pause':
                    # 無音を追加
                    silence = self.generate_silence(
                        segment['duration'],
                        sample_rate,
                        channels,
                        sample_width
                    )
                    with wave.open(io.BytesIO(silence), 'rb') as silence_wav:
                        frames = silence_wav.readframes(silence_wav.getnframes())
                        output_wav.writeframes(frames)
        
        return output_buffer.getvalue()
    
    def get_audio_duration(self, audio_data: bytes) -> float:
        """
        音声の長さを取得
        
        Args:
            audio_data: 音声データ
        
        Returns:
            float: 長さ（秒）
        """
        with wave.open(io.BytesIO(audio_data), 'rb') as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = frames / float(rate)
        
        return duration
    
    def process_script_to_segments(
        self,
        script: str
    ) -> Tuple[List[str], List[Dict]]:
        """
        台本を処理してテキストセグメントとポーズ情報を返す
        
        Args:
            script: 台本テキスト
        
        Returns:
            Tuple[List[str], List[Dict]]: 
                - テキストセグメントのリスト（音声生成用）
                - 全セグメント情報（結合用）
        """
        segments = self.parse_script_with_pauses(script)
        
        # テキストのみを抽出
        text_segments = [
            seg['content'] 
            for seg in segments 
            if seg['type'] == 'text'
        ]
        
        return text_segments, segments
    
    def add_pauses_to_audio_list(
        self,
        audio_list: List[bytes],
        script: str
    ) -> bytes:
        """
        音声リストに台本の間を挿入して結合（簡易版）
        
        Args:
            audio_list: 音声データのリスト
            script: 元の台本
        
        Returns:
            bytes: 間を含む完成した音声データ
        """
        # 台本を解析
        text_segments, all_segments = self.process_script_to_segments(script)
        
        if len(text_segments) != len(audio_list):
            print(f"⚠️ 警告: テキストセグメント数({len(text_segments)})と音声数({len(audio_list)})が一致しません")
        
        # 音声と間を結合
        return self.combine_audio_with_pauses(audio_list, all_segments)
    
    def save_audio(self, audio_data: bytes, output_path: str) -> str:
        """
        音声データを保存
        
        Args:
            audio_data: 音声データ
            output_path: 出力パス
        
        Returns:
            str: 保存したファイルパス
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'wb') as f:
            f.write(audio_data)
        
        print(f"💾 音声保存: {output_file}")
        return str(output_file)


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("⏸️  PauseHandler テスト")
    print("="*60 + "\n")
    
    handler = PauseHandler()
    
    # テスト1: 台本の解析
    print("=== テスト1: 台本の解析 ===")
    test_script = """
おはようございます。（間）
今日は2025年12月1日です。（長めの間）
それでは見ていきましょう。（2秒間）
まず米国市場から。（短い間）
ダウ平均は300ドル高でした。
"""
    
    segments = handler.parse_script_with_pauses(test_script)
    
    print(f"総セグメント数: {len(segments)}")
    for i, seg in enumerate(segments, 1):
        if seg['type'] == 'text':
            print(f"  {i}. テキスト: {seg['content'][:30]}...")
        else:
            print(f"  {i}. ポーズ: {seg['duration']}秒")
    
    # テスト2: 無音生成
    print("\n=== テスト2: 無音生成 ===")
    
    silence_0_5 = handler.generate_silence(0.5)
    duration = handler.get_audio_duration(silence_0_5)
    print(f"✅ 0.5秒の無音生成: 実際の長さ {duration:.3f}秒")
    
    silence_2_0 = handler.generate_silence(2.0)
    duration = handler.get_audio_duration(silence_2_0)
    print(f"✅ 2.0秒の無音生成: 実際の長さ {duration:.3f}秒")
    
    # 保存してテスト
    handler.save_audio(silence_0_5, "data/test_audio/silence_0.5s.wav")
    handler.save_audio(silence_2_0, "data/test_audio/silence_2.0s.wav")
    
    # テスト3: VOICEVOXと組み合わせ
    print("\n=== テスト3: VOICEVOXと組み合わせ ===")
    
    try:
        from src.voice_generation.voice_client import VOICEVOXClient
        
        voicevox = VOICEVOXClient()
        
        # テキストセグメントを抽出
        text_segments, all_segments = handler.process_script_to_segments(test_script)
        
        print(f"テキストセグメント数: {len(text_segments)}")
        
        # 各テキストで音声生成
        audio_list = []
        for text in text_segments:
            print(f"  音声生成: {text[:30]}...")
            audio = voicevox.generate_audio(text)
            audio_list.append(audio)
        
        # 音声と間を結合
        print("\n音声と間を結合中...")
        final_audio = handler.combine_audio_with_pauses(audio_list, all_segments)
        
        final_duration = handler.get_audio_duration(final_audio)
        print(f"✅ 結合完了: 総時間 {final_duration:.2f}秒")
        
        # 保存
        output_path = "data/test_audio/test_with_pauses.wav"
        handler.save_audio(final_audio, output_path)
        
        print(f"\n🎧 音声ファイル生成完了:")
        print(f"   {output_path}")
        print(f"   再生して確認してください！")
        
    except ImportError:
        print("⚠️ VOICEVOXClientが見つかりません（スキップ）")
    except Exception as e:
        print(f"⚠️ エラー: {e}")
    
    print("\n" + "="*60)
    print("✅ テスト完了")
    print("="*60)
    print("\n生成されたファイル:")
    print("  - data/test_audio/silence_0.5s.wav")
    print("  - data/test_audio/silence_2.0s.wav")
    print("  - data/test_audio/test_with_pauses.wav（VOICEVOXがあれば）")
