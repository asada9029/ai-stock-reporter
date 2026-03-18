"""
動画合成モジュール
音声・背景・キャラクターを合成して動画を生成
"""

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# moviepy 2.x のインポート
from moviepy import (
    ImageClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, ColorClip, VideoFileClip
)


class VideoComposer:
    """動画合成クラス"""
    
    # 動画設定
    DEFAULT_RESOLUTION = (1920, 1080)  # フルHD
    DEFAULT_FPS = 30
    DEFAULT_BACKGROUND_COLOR = (20, 30, 50)  # ダークブルー
    
    def __init__(
        self,
        resolution: Tuple[int, int] = None,
        fps: int = None
    ):
        """
        初期化
        
        Args:
            resolution: 解像度 (幅, 高さ)
            fps: フレームレート
        """
        self.resolution = resolution or self.DEFAULT_RESOLUTION
        self.fps = fps or self.DEFAULT_FPS
        
        print("✅ VideoComposer 初期化完了")
        print(f"   解像度: {self.resolution[0]}x{self.resolution[1]}")
        print(f"   FPS: {self.fps}")
    
    def create_background(
        self,
        duration: float,
        color: Tuple[int, int, int] = None,
        image_path: Optional[str] = None
    ) -> ImageClip:
        """
        背景を作成
        
        Args:
            duration: 長さ（秒）
            color: 背景色 (R, G, B)
            image_path: 背景画像のパス（指定時はこちらを優先）
        
        Returns:
            ImageClip: 背景クリップ
        """
        if image_path and Path(image_path).exists():
            # 画像から背景作成
            img = Image.open(image_path)
            img = img.resize(self.resolution, Image.Resampling.LANCZOS)
            
            clip = ImageClip(np.array(img), duration=duration)
            
        else:
            # 単色背景
            bg_color = color or self.DEFAULT_BACKGROUND_COLOR
            clip = ColorClip(
                size=self.resolution,
                color=bg_color,
                duration=duration
            )
        
        return clip
    
    def create_gradient_background(
        self,
        duration: float,
        color_top: Tuple[int, int, int] = (20, 30, 80),
        color_bottom: Tuple[int, int, int] = (10, 15, 40)
    ) -> ImageClip:
        """
        グラデーション背景を作成
        
        Args:
            duration: 長さ（秒）
            color_top: 上部の色
            color_bottom: 下部の色
        
        Returns:
            ImageClip: 背景クリップ
        """
        width, height = self.resolution
        
        # グラデーション画像作成
        gradient = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            ratio = y / height
            color = tuple(
                int(color_top[i] * (1 - ratio) + color_bottom[i] * ratio)
                for i in range(3)
            )
            gradient[y, :] = color
        
        clip = ImageClip(gradient, duration=duration)
        
        return clip
    
    def add_character(
        self,
        background_clip: ImageClip,
        character_image_path: str,
        position: Tuple[int, int] = None,
        scale: float = 1.0
    ) -> CompositeVideoClip:
        """
        キャラクター画像を追加
        
        Args:
            background_clip: 背景クリップ
            character_image_path: キャラクター画像のパス
            position: 配置位置 (x, y)（Noneの場合は右下）
            scale: スケール（1.0 = 元サイズ）
        
        Returns:
            CompositeVideoClip: 合成クリップ
        """
        if not Path(character_image_path).exists():
            print(f"⚠️ キャラクター画像が見つかりません: {character_image_path}")
            return background_clip
        
        # 画像読み込み
        char_img = Image.open(character_image_path)
        
        # スケール調整
        if scale != 1.0:
            new_size = (
                int(char_img.width * scale),
                int(char_img.height * scale)
            )
            char_img = char_img.resize(new_size, Image.Resampling.LANCZOS)
        
        # 位置決定（デフォルト: 右下）
        if position is None:
            x = self.resolution[0] - char_img.width - 50
            y = self.resolution[1] - char_img.height - 50
        else:
            x, y = position
        
        # クリップ作成
        char_clip = ImageClip(np.array(char_img), duration=background_clip.duration)
        char_clip = char_clip.with_position((x, y))
        
        # 透過対応
        if char_img.mode == 'RGBA':
            char_clip = char_clip.with_effects([])  # 2.xでは透過は自動対応
        
        # 合成
        composite = CompositeVideoClip([background_clip, char_clip])
        
        return composite
    
    def add_audio(
        self,
        video_clip,
        audio_path: str
    ):
        """
        音声を追加
        
        Args:
            video_clip: 動画クリップ
            audio_path: 音声ファイルのパス
        
        Returns:
            VideoClip: 音声付き動画クリップ
        """
        if not Path(audio_path).exists():
            print(f"⚠️ 音声ファイルが見つかりません: {audio_path}")
            return video_clip
        
        audio = AudioFileClip(audio_path)
        
        # 動画の長さを音声に合わせる
        video_clip = video_clip.with_duration(audio.duration)
        video_clip = video_clip.with_audio(audio)
        
        return video_clip
    
    def create_simple_video(
        self,
        audio_path: str,
        output_path: str,
        background_image: Optional[str] = None,
        character_image: Optional[str] = None,
        background_color: Optional[Tuple[int, int, int]] = None
    ) -> str:
        """
        シンプルな動画を作成（ワンステップ）
        
        Args:
            audio_path: 音声ファイルのパス
            output_path: 出力パス
            background_image: 背景画像のパス（オプション）
            character_image: キャラクター画像のパス（オプション）
            background_color: 背景色（オプション）
        
        Returns:
            str: 出力ファイルパス
        """
        print(f"\n🎬 動画作成中: {Path(output_path).name}")
        
        # 音声の長さを取得
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        print(f"   音声の長さ: {duration:.2f}秒")
        
        # 背景作成
        if background_image:
            background = self.create_background(duration, image_path=background_image)
        else:
            background = self.create_gradient_background(duration)
        
        # キャラクター追加
        if character_image and Path(character_image).exists():
            video = self.add_character(background, character_image, scale=0.5)
        else:
            video = background
        
        # 音声追加
        video = video.with_audio(audio)
        video = video.with_fps(self.fps)
        
        # 出力
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"   レンダリング中...")
        video.write_videofile(
            str(output_file),
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            threads=4,
            logger=None  # ログを簡潔に
        )
        
        # クリーンアップ
        video.close()
        audio.close()
        
        print(f"✅ 動画作成完了: {output_file}")
        return str(output_file)
    
    def create_title_card(
        self,
        title: str,
        duration: float = 3.0,
        background_color: Tuple[int, int, int] = (20, 30, 50),
        text_color: Tuple[int, int, int] = (255, 255, 255)
    ) -> ImageClip:
        """
        タイトルカードを作成
        
        Args:
            title: タイトルテキスト
            duration: 表示時間（秒）
            background_color: 背景色
            text_color: テキスト色
        
        Returns:
            ImageClip: タイトルカードクリップ
        """
        # 画像作成
        img = Image.new('RGB', self.resolution, background_color)
        draw = ImageDraw.Draw(img)
        
        # フォント設定（システムフォントを使用）
        try:
            # 日本語対応フォントを試す
            font_size = 80
            font_paths = [
                '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',  # macOS
                'C:\\Windows\\Fonts\\msgothic.ttc',  # Windows
                '/usr/share/fonts/truetype/takao-gothic/TakaoGothic.ttf',  # Linux
            ]
            
            font = None
            for font_path in font_paths:
                if Path(font_path).exists():
                    font = ImageFont.truetype(font_path, font_size)
                    break
            
            if font is None:
                # フォールバック
                font = ImageFont.load_default()
        except Exception as e:
            print(f"⚠️ フォント読み込みエラー: {e}")
            font = ImageFont.load_default()
        
        # テキストを中央に配置
        bbox = draw.textbbox((0, 0), title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (self.resolution[0] - text_width) // 2
        y = (self.resolution[1] - text_height) // 2
        
        draw.text((x, y), title, fill=text_color, font=font)
        
        # クリップ作成
        clip = ImageClip(np.array(img), duration=duration)
        
        return clip
    
    def concatenate_sections(
        self,
        section_videos: list,
        output_path: str
    ) -> str:
        """
        複数のセクション動画を連結
        
        Args:
            section_videos: 動画ファイルパスのリスト
            output_path: 出力パス
        
        Returns:
            str: 出力ファイルパス
        """
        print(f"\n🎬 動画連結中: {len(section_videos)}セクション")
        
        # クリップ読み込み
        clips = []
        
        for video_path in section_videos:
            if Path(video_path).exists():
                clip = VideoFileClip(video_path)
                clips.append(clip)
            else:
                print(f"⚠️ ファイルが見つかりません: {video_path}")
        
        if not clips:
            raise ValueError("連結する動画がありません")
        
        # 連結
        final_video = concatenate_videoclips(clips, method="compose")
        
        # 出力
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"   レンダリング中...")
        final_video.write_videofile(
            str(output_file),
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            threads=4,
            logger=None
        )
        
        # クリーンアップ
        for clip in clips:
            clip.close()
        final_video.close()
        
        print(f"✅ 連結完了: {output_file}")
        return str(output_file)


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 VideoComposer テスト")
    print("="*60 + "\n")
    
    try:
        composer = VideoComposer()
        
        # テスト1: シンプルな背景動画
        print("\n=== テスト1: シンプルな背景動画 ===")
        
        # テスト用音声を確認
        test_audio = "data/test_audio/test_basic.wav"
        if not Path(test_audio).exists():
            print("⚠️ テスト用音声が見つかりません。")
            print("   先に voice_generation のテストを実行してください。")
        else:
            output1 = composer.create_simple_video(
                audio_path=test_audio,
                output_path="data/test_video/test1_simple.mp4"
            )
            
            print(f"✅ 動画1作成完了")
        
        # テスト2: タイトルカード
        print("\n=== テスト2: タイトルカード ===")
        
        title_card = composer.create_title_card(
            title="株ニュースAI VTuber",
            duration=3.0
        )
        
        # 音声なしで保存
        title_card.write_videofile(
            "data/test_video/test2_title.mp4",
            fps=composer.fps,
            codec='libx264',
            preset='fast',
            logger=None
        )
        title_card.close()
        
        print(f"✅ タイトルカード作成完了")
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - data/test_video/test1_simple.mp4")
        print("  - data/test_video/test2_title.mp4")
        print("\n🎥 動画を再生して確認してください！")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
