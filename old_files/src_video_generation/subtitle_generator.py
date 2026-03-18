"""
テロップ（字幕）生成モジュール
台本から字幕を生成して動画に合成
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional
import re
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy import TextClip, CompositeVideoClip


class SubtitleGenerator:
    """字幕生成クラス"""
    
    # 字幕設定
    DEFAULT_FONT_SIZE = 48
    DEFAULT_FONT_COLOR = (255, 255, 255)  # 白
    DEFAULT_BG_COLOR = (0, 0, 0, 180)      # 半透明黒
    DEFAULT_POSITION = ('center', 'bottom')
    DEFAULT_CHARS_PER_SECOND = 4.0         # 読み上げ速度（文字/秒）
    
    def __init__(
        self,
        font_size: int = None,
        font_color: Tuple[int, int, int] = None
    ):
        """
        初期化
        
        Args:
            font_size: フォントサイズ
            font_color: フォント色
        """
        self.font_size = font_size or self.DEFAULT_FONT_SIZE
        self.font_color = font_color or self.DEFAULT_FONT_COLOR
        
        # フォントパス検索
        self.font_path = self._find_japanese_font()
        
        print("✅ SubtitleGenerator 初期化完了")
        print(f"   フォントサイズ: {self.font_size}")
        print(f"   フォント: {self.font_path}")
    
    def _find_japanese_font(self) -> Optional[str]:
        """日本語フォントを検索"""
        font_paths = [
            # macOS
            '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc',
            '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
            # Windows
            'C:\\Windows\\Fonts\\msgothic.ttc',
            'C:\\Windows\\Fonts\\meiryo.ttc',
            # Linux
            '/usr/share/fonts/truetype/takao-gothic/TakaoGothic.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        ]
        
        for font_path in font_paths:
            if Path(font_path).exists():
                return font_path
        
        print("⚠️ 日本語フォントが見つかりません。デフォルトフォントを使用します。")
        return None
    
    def parse_script_to_subtitles(
        self,
        script: str,
        duration: float
    ) -> List[Dict]:
        """
        台本から字幕タイミングを生成
        
        Args:
            script: 台本テキスト
            duration: 音声の長さ（秒）
        
        Returns:
            List[Dict]: 字幕情報のリスト
                [
                    {
                        "text": "表示テキスト",
                        "start": 0.0,
                        "end": 2.5
                    },
                    ...
                ]
        """
        # 間を除去
        text_only = re.sub(r'（.*?）', '', script)
        
        # 句読点で分割
        sentences = re.split(r'[。．！？\n]+', text_only)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return []
        
        subtitles = []
        current_time = 0.0
        
        # 全体の文字数
        total_chars = sum(len(s) for s in sentences)
        
        for sentence in sentences:
            if not sentence:
                continue
            
            # 文の長さから表示時間を計算
            char_count = len(sentence)
            sentence_duration = char_count / self.DEFAULT_CHARS_PER_SECOND
            
            # 全体の時間に収まるように調整
            time_ratio = duration / (total_chars / self.DEFAULT_CHARS_PER_SECOND)
            sentence_duration *= time_ratio
            
            # 最小・最大表示時間
            sentence_duration = max(1.0, min(sentence_duration, 5.0))
            
            subtitle = {
                "text": sentence,
                "start": round(current_time, 2),
                "end": round(current_time + sentence_duration, 2)
            }
            
            subtitles.append(subtitle)
            current_time += sentence_duration
        
        # 最後の字幕の終了時刻を調整
        if subtitles:
            subtitles[-1]["end"] = round(duration, 2)
        
        return subtitles
    
    def create_subtitle_image(
        self,
        text: str,
        width: int = 1920,
        height: int = 150
    ) -> np.ndarray:
        """
        字幕画像を作成
        
        Args:
            text: 字幕テキスト
            width: 画像幅
            height: 画像高さ
        
        Returns:
            np.ndarray: 字幕画像
        """
        # 透明背景の画像作成
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # フォント設定
        try:
            if self.font_path:
                font = ImageFont.truetype(self.font_path, self.font_size)
            else:
                font = ImageFont.load_default()
        except Exception as e:
            print(f"⚠️ フォント読み込みエラー: {e}")
            font = ImageFont.load_default()
        
        # テキストのバウンディングボックス取得
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 背景ボックス（半透明黒）
        padding = 20
        box_x1 = (width - text_width) // 2 - padding
        box_y1 = (height - text_height) // 2 - padding
        box_x2 = box_x1 + text_width + padding * 2
        box_y2 = box_y1 + text_height + padding * 2
        
        draw.rectangle(
            [box_x1, box_y1, box_x2, box_y2],
            fill=self.DEFAULT_BG_COLOR
        )
        
        # テキストを中央に配置
        text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2
        
        # 縁取り（黒）
        outline_width = 2
        for dx in [-outline_width, 0, outline_width]:
            for dy in [-outline_width, 0, outline_width]:
                if dx != 0 or dy != 0:
                    draw.text(
                        (text_x + dx, text_y + dy),
                        text,
                        fill=(0, 0, 0),
                        font=font
                    )
        
        # メインテキスト（白）
        draw.text(
            (text_x, text_y),
            text,
            fill=self.font_color,
            font=font
        )
        
        return np.array(img)
    
    def generate_srt_file(
        self,
        subtitles: List[Dict],
        output_path: str
    ) -> str:
        """
        SRT形式の字幕ファイルを生成
        
        Args:
            subtitles: 字幕情報のリスト
            output_path: 出力パス
        
        Returns:
            str: 保存したファイルパス
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                # インデックス
                f.write(f"{i}\n")
                
                # タイムスタンプ
                start_time = self._format_srt_time(sub['start'])
                end_time = self._format_srt_time(sub['end'])
                f.write(f"{start_time} --> {end_time}\n")
                
                # テキスト
                f.write(f"{sub['text']}\n")
                f.write("\n")
        
        print(f"💾 字幕ファイル保存: {output_file}")
        return str(output_file)
    
    def _format_srt_time(self, seconds: float) -> str:
        """
        秒数をSRT形式の時刻に変換
        
        Args:
            seconds: 秒数
        
        Returns:
            str: SRT形式の時刻（例: 00:00:05,500）
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def add_subtitles_to_video(
        self,
        video_clip,
        subtitles: List[Dict],
        position: Tuple = ('center', 850)
    ):
        """
        動画に字幕を追加
        
        Args:
            video_clip: 動画クリップ
            subtitles: 字幕情報のリスト
            position: 字幕の位置
        
        Returns:
            CompositeVideoClip: 字幕付き動画
        """
        from moviepy import ImageClip
        
        subtitle_clips = []
        
        for sub in subtitles:
            # 字幕画像作成
            subtitle_img = self.create_subtitle_image(sub['text'])
            
            # クリップ化
            sub_clip = ImageClip(
                subtitle_img,
                duration=sub['end'] - sub['start']
            )
            sub_clip = sub_clip.with_start(sub['start'])
            sub_clip = sub_clip.with_position(position)
            
            subtitle_clips.append(sub_clip)
        
        # 動画と字幕を合成
        if subtitle_clips:
            final_video = CompositeVideoClip([video_clip] + subtitle_clips)
            return final_video
        else:
            return video_clip
    
    def create_video_with_subtitles(
        self,
        video_path: str,
        script: str,
        audio_duration: float,
        output_path: str
    ) -> str:
        """
        動画に字幕を追加（ワンステップ）
        
        Args:
            video_path: 元動画のパス
            script: 台本
            audio_duration: 音声の長さ
            output_path: 出力パス
        
        Returns:
            str: 出力ファイルパス
        """
        from moviepy import VideoFileClip
        
        print(f"\n📝 字幕付き動画作成中...")
        
        # 字幕生成
        subtitles = self.parse_script_to_subtitles(script, audio_duration)
        print(f"   字幕数: {len(subtitles)}個")
        
        # 動画読み込み
        video = VideoFileClip(video_path)
        
        # 字幕追加
        video_with_subs = self.add_subtitles_to_video(video, subtitles)
        
        # 出力
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"   レンダリング中...")
        video_with_subs.write_videofile(
            str(output_file),
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            threads=4,
            logger=None
        )
        
        # クリーンアップ
        video.close()
        video_with_subs.close()
        
        print(f"✅ 字幕付き動画作成完了: {output_file}")
        return str(output_file)


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("📝 SubtitleGenerator テスト")
    print("="*60 + "\n")
    
    try:
        generator = SubtitleGenerator()
        
        # テスト1: 台本から字幕生成
        print("\n=== テスト1: 台本から字幕生成 ===")
        
        test_script = """
おはようございます。（間）
今日は2025年12月1日です。（長めの間）
昨夜の米国市場から見ていきましょう。（間）
ダウ平均は300ドル高でした。
"""
        
        duration = 15.0
        subtitles = generator.parse_script_to_subtitles(test_script, duration)
        
        print(f"生成された字幕: {len(subtitles)}個")
        for i, sub in enumerate(subtitles, 1):
            print(f"  {i}. [{sub['start']:.2f}s - {sub['end']:.2f}s] {sub['text']}")
        
        # テスト2: SRTファイル生成
        print("\n=== テスト2: SRTファイル生成 ===")
        srt_path = generator.generate_srt_file(
            subtitles,
            "data/test_subtitles/test.srt"
        )
        
        # テスト3: 字幕画像生成
        print("\n=== テスト3: 字幕画像生成 ===")
        subtitle_img = generator.create_subtitle_image("おはようございます")
        
        # 画像保存（確認用）
        from PIL import Image
        img = Image.fromarray(subtitle_img)
        img_path = Path("data/test_subtitles/subtitle_sample.png")
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(img_path)
        print(f"✅ 字幕画像保存: {img_path}")
        
        # テスト4: 動画に字幕追加（既存動画がある場合）
        print("\n=== テスト4: 動画に字幕追加 ===")
        test_video = "data/test_video/test1_simple.mp4"
        
        if Path(test_video).exists():
            output = generator.create_video_with_subtitles(
                video_path=test_video,
                script=test_script,
                audio_duration=duration,
                output_path="data/test_video/test_with_subtitles.mp4"
            )
            print(f"✅ 字幕付き動画作成完了")
        else:
            print("⚠️ テスト用動画が見つかりません")
            print("   先に video_composer のテストを実行してください")
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - data/test_subtitles/test.srt")
        print("  - data/test_subtitles/subtitle_sample.png")
        if Path("data/test_video/test_with_subtitles.mp4").exists():
            print("  - data/test_video/test_with_subtitles.mp4")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
