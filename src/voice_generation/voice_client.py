"""
VOICEVOXクライアント
四国めたんの音声生成
"""

import requests
import json
import wave
from pathlib import Path
from typing import Dict, Optional, List
import time


class VOICEVOXClient:
    """VOICEVOXクライアント"""
    
    # 四国めたんのスピーカーID
    SHIKOKU_METAN_NORMAL = 2      # ノーマル（通常解説用）
    SHIKOKU_METAN_AME = 0          # あまあま（重要ポイント強調用）
    SHIKOKU_METAN_TSUN = 6         # ツンツン（注意喚起用）
    SHIKOKU_METAN_SEXY = 4         # セクシー（特別な強調用）
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50021,
        default_speaker: int = None
    ):
        """
        初期化
        
        Args:
            host: VOICEVOXエンジンのホスト
            port: VOICEVOXエンジンのポート
            default_speaker: デフォルトスピーカーID
        """
        self.base_url = f"http://{host}:{port}"
        self.default_speaker = default_speaker or self.SHIKOKU_METAN_NORMAL
        
        # 接続確認
        if not self._check_connection():
            raise ConnectionError(
                f"VOICEVOXエンジンに接続できません: {self.base_url}\n"
                "VOICEVOXが起動していることを確認してください。"
            )
        
        print(f"✅ VOICEVOX クライアント初期化完了")
        print(f"   - エンドポイント: {self.base_url}")
        print(f"   - デフォルトスピーカー: {self._get_speaker_name(self.default_speaker)}")
    
    def _check_connection(self) -> bool:
        """
        VOICEVOXエンジンへの接続確認
        
        Returns:
            bool: 接続可能か
        """
        try:
            response = requests.get(f"{self.base_url}/version", timeout=5)
            if response.status_code == 200:
                version = response.json()
                print(f"🎤 VOICEVOX バージョン: {version}")
                return True
            return False
        except Exception as e:
            print(f"❌ 接続エラー: {e}")
            return False
    
    def _get_speaker_name(self, speaker_id: int) -> str:
        """スピーカー名を取得"""
        speaker_names = {
            self.SHIKOKU_METAN_NORMAL: "四国めたん（ノーマル）",
            self.SHIKOKU_METAN_AME: "四国めたん（あまあま）",
            self.SHIKOKU_METAN_TSUN: "四国めたん（ツンツン）",
            self.SHIKOKU_METAN_SEXY: "四国めたん（セクシー）"
        }
        return speaker_names.get(speaker_id, f"スピーカーID: {speaker_id}")
    
    def generate_audio(
        self,
        text: str,
        speaker: Optional[int] = None,
        speed: float = 1.0,
        pitch: float = 0.0,
        intonation: float = 1.0,
        volume: float = 1.0
    ) -> bytes:
        """
        音声を生成
        
        Args:
            text: 読み上げるテキスト
            speaker: スピーカーID（Noneの場合はデフォルト）
            speed: 話速（0.5～2.0、デフォルト1.0）
            pitch: 音高（-0.15～0.15、デフォルト0.0）
            intonation: 抑揚（0.0～2.0、デフォルト1.0）
            volume: 音量（0.0～2.0、デフォルト1.0）
        
        Returns:
            bytes: WAVファイルのバイナリデータ
        """
        speaker_id = speaker if speaker is not None else self.default_speaker
        
        # Step 1: 音声合成用のクエリを作成
        query = self._create_audio_query(text, speaker_id)
        
        # パラメータ調整
        query['speedScale'] = speed
        query['pitchScale'] = pitch
        query['intonationScale'] = intonation
        query['volumeScale'] = volume
        
        # Step 2: 音声合成
        audio_data = self._synthesis(query, speaker_id)
        
        return audio_data
    
    def _create_audio_query(self, text: str, speaker: int) -> Dict:
        """
        音声合成用のクエリを作成
        
        Args:
            text: テキスト
            speaker: スピーカーID
        
        Returns:
            Dict: クエリデータ
        """
        url = f"{self.base_url}/audio_query"
        params = {
            'text': text,
            'speaker': speaker
        }
        
        try:
            response = requests.post(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"クエリ作成エラー: {e}")
    
    def _synthesis(self, query: Dict, speaker: int) -> bytes:
        """
        音声合成を実行
        
        Args:
            query: クエリデータ
            speaker: スピーカーID
        
        Returns:
            bytes: WAVデータ
        """
        url = f"{self.base_url}/synthesis"
        params = {'speaker': speaker}
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                data=json.dumps(query),
                timeout=60
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise Exception(f"音声合成エラー: {e}")
    
    def save_audio(
        self,
        audio_data: bytes,
        output_path: str
    ) -> str:
        """
        音声データをファイルに保存
        
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
    
    def generate_and_save(
        self,
        text: str,
        output_path: str,
        speaker: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        音声を生成して保存（ワンステップ）
        
        Args:
            text: テキスト
            output_path: 出力パス
            speaker: スピーカーID
            **kwargs: その他のパラメータ（speed, pitch等）
        
        Returns:
            str: 保存したファイルパス
        """
        audio_data = self.generate_audio(text, speaker, **kwargs)
        return self.save_audio(audio_data, output_path)
    
    def get_audio_duration(self, audio_data: bytes) -> float:
        """
        音声の長さを取得（秒）
        
        Args:
            audio_data: 音声データ
        
        Returns:
            float: 長さ（秒）
        """
        import io
        
        # バイナリデータからWAVを読み込み
        with wave.open(io.BytesIO(audio_data), 'rb') as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = frames / float(rate)
        
        return duration
    
    def generate_with_style_switching(
        self,
        text_segments: List[Dict],
        output_path: str
    ) -> str:
        """
        スタイル切り替えありで音声生成
        
        Args:
            text_segments: テキストセグメントのリスト
                例: [
                    {"text": "おはようございます", "speaker": 2},
                    {"text": "重要なニュースです", "speaker": 4},
                ]
            output_path: 出力パス
        
        Returns:
            str: 保存したファイルパス
        """
        audio_segments = []
        
        for segment in text_segments:
            text = segment['text']
            speaker = segment.get('speaker', self.default_speaker)
            params = {k: v for k, v in segment.items() if k not in ['text', 'speaker']}
            
            audio_data = self.generate_audio(text, speaker, **params)
            audio_segments.append(audio_data)
        
        # 音声を連結
        combined_audio = self._combine_audio_segments(audio_segments)
        
        return self.save_audio(combined_audio, output_path)
    
    def _combine_audio_segments(self, audio_segments: List[bytes]) -> bytes:
        """
        複数の音声セグメントを連結
        
        Args:
            audio_segments: 音声データのリスト
        
        Returns:
            bytes: 連結された音声データ
        """
        import io
        
        if not audio_segments:
            raise ValueError("音声セグメントが空です")
        
        if len(audio_segments) == 1:
            return audio_segments[0]
        
        # 最初のセグメントから設定を取得
        with wave.open(io.BytesIO(audio_segments[0]), 'rb') as first_wav:
            params = first_wav.getparams()
        
        # 出力用のバッファ
        output_buffer = io.BytesIO()
        
        with wave.open(output_buffer, 'wb') as output_wav:
            output_wav.setparams(params)
            
            # 各セグメントのフレームを連結
            for audio_data in audio_segments:
                with wave.open(io.BytesIO(audio_data), 'rb') as segment_wav:
                    frames = segment_wav.readframes(segment_wav.getnframes())
                    output_wav.writeframes(frames)
        
        return output_buffer.getvalue()
    
    def test_speakers(self, test_text: str = "こんにちは、テストです。") -> None:
        """
        全スピーカーをテスト
        
        Args:
            test_text: テスト用テキスト
        """
        print("\n" + "="*60)
        print("🎤 スピーカーテスト")
        print("="*60)
        
        speakers = [
            self.SHIKOKU_METAN_NORMAL,
            self.SHIKOKU_METAN_AME,
            self.SHIKOKU_METAN_TSUN,
            self.SHIKOKU_METAN_SEXY
        ]
        
        for speaker in speakers:
            print(f"\n📢 {self._get_speaker_name(speaker)}")
            try:
                audio_data = self.generate_audio(test_text, speaker)
                duration = self.get_audio_duration(audio_data)
                print(f"   ✅ 生成成功 (長さ: {duration:.2f}秒)")
            except Exception as e:
                print(f"   ❌ エラー: {e}")


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎤 VOICEVOXクライアント テスト")
    print("="*60 + "\n")
    
    try:
        # クライアント初期化
        client = VOICEVOXClient()
        
        # テスト1: 基本的な音声生成
        print("\n=== テスト1: 基本的な音声生成 ===")
        test_text = "おはようございます。今日は株式市場のニュースをお伝えします。"
        
        audio_data = client.generate_audio(test_text)
        duration = client.get_audio_duration(audio_data)
        print(f"✅ 音声生成成功")
        print(f"   テキスト: {test_text}")
        print(f"   長さ: {duration:.2f}秒")
        
        # 保存
        output_path = "data/test_audio/test_basic.wav"
        client.save_audio(audio_data, output_path)
        
        # テスト2: パラメータ調整
        print("\n=== テスト2: パラメータ調整 ===")
        
        # 速度変更
        fast_audio = client.generate_audio(test_text, speed=1.2)
        fast_duration = client.get_audio_duration(fast_audio)
        print(f"✅ 速度1.2x: {fast_duration:.2f}秒")
        
        slow_audio = client.generate_audio(test_text, speed=0.9)
        slow_duration = client.get_audio_duration(slow_audio)
        print(f"✅ 速度0.9x: {slow_duration:.2f}秒")
        
        # テスト3: スタイル切り替え
        print("\n=== テスト3: スタイル切り替え ===")
        segments = [
            {
                "text": "おはようございます。",
                "speaker": client.SHIKOKU_METAN_NORMAL
            },
            {
                "text": "重要なニュースです。",
                "speaker": client.SHIKOKU_METAN_SEXY,
                "speed": 0.95
            },
            {
                "text": "日経平均が大きく上昇しました。",
                "speaker": client.SHIKOKU_METAN_NORMAL
            }
        ]
        
        output_path = "data/test_audio/test_style_switching.wav"
        client.generate_with_style_switching(segments, output_path)
        print(f"✅ スタイル切り替え音声生成完了")
        
        # テスト4: 全スピーカーテスト
        print("\n=== テスト4: 全スピーカーテスト ===")
        client.test_speakers("株式市場は本日、大きく上昇しました。")
        
        print("\n" + "="*60)
        print("✅ 全テスト完了")
        print("="*60)
        print("\n生成された音声ファイル:")
        print("  - data/test_audio/test_basic.wav")
        print("  - data/test_audio/test_style_switching.wav")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
