"""
スタイル自動切り替えモジュール
セクションや内容に応じて音声スタイルを自動選択
"""

import re
from typing import Dict, List, Optional, Tuple
from src.voice_generation.voice_client import VOICEVOXClient


class StyleController:
    """音声スタイル制御クラス"""
    
    def __init__(self, voicevox_client: Optional[VOICEVOXClient] = None):
        """
        初期化
        
        Args:
            voicevox_client: VOICEVOXClientインスタンス
        """
        self.voicevox = voicevox_client or VOICEVOXClient()
        
        # スタイル定義
        self.styles = {
            'normal': {
                'speaker': self.voicevox.SHIKOKU_METAN_NORMAL,
                'speed': 1.0,
                'pitch': 0.0,
                'intonation': 1.0,
                'description': '通常の解説'
            },
            'emphasis': {
                'speaker': self.voicevox.SHIKOKU_METAN_AME,
                'speed': 0.95,
                'pitch': 0.02,
                'intonation': 1.2,
                'description': '重要ポイント強調'
            },
            'alert': {
                'speaker': self.voicevox.SHIKOKU_METAN_TSUN,
                'speed': 0.9,
                'pitch': 0.03,
                'intonation': 1.3,
                'description': '注意喚起'
            },
            'highlight': {
                'speaker': self.voicevox.SHIKOKU_METAN_SEXY,
                'speed': 0.92,
                'pitch': 0.01,
                'intonation': 1.25,
                'description': '特別な強調'
            },
            'fast': {
                'speaker': self.voicevox.SHIKOKU_METAN_NORMAL,
                'speed': 1.15,
                'pitch': 0.0,
                'intonation': 1.0,
                'description': '速めの進行'
            },
            'slow': {
                'speaker': self.voicevox.SHIKOKU_METAN_NORMAL,
                'speed': 0.85,
                'pitch': 0.0,
                'intonation': 1.1,
                'description': 'ゆっくり丁寧'
            }
        }
        
        print("✅ StyleController 初期化完了")
    
    def get_section_style(self, section_name: str) -> str:
        """
        セクション名からスタイルを決定
        
        Args:
            section_name: セクション名
        
        Returns:
            str: スタイル名
        """
        section_style_map = {
            'opening': 'emphasis',          # オープニング：明るく
            'us_market': 'normal',          # 米国市場：通常
            'japan_market': 'normal',       # 日本市場：通常
            'forex': 'normal',              # 為替：通常
            'sector_analysis': 'normal',    # セクター分析：通常
            'sector_focus': 'emphasis',     # セクター注目：強調
            'after_hours_ir': 'highlight',  # 引け後IR：特別強調
            'important_news': 'alert',      # 重要ニュース：注意喚起
            'top_stocks': 'normal',         # 注目銘柄：通常
            'tomorrow_outlook': 'emphasis', # 明日の見通し：強調
            'closing': 'normal',            # エンディング：通常
            'japan_preview': 'emphasis'     # 日本市場プレビュー：強調
        }
        
        return section_style_map.get(section_name, 'normal')
    
    def detect_text_emphasis(self, text: str) -> List[Dict]:
        """
        テキスト内の強調すべき部分を検出
        
        Args:
            text: テキスト
        
        Returns:
            List[Dict]: 強調パターンのリスト
        """
        emphasis_patterns = [
            # 重要キーワード
            {
                'pattern': r'(重要|注目|大きく|急|暴落|暴騰)',
                'style': 'alert'
            },
            # 数値の強調（大きな変動）
            {
                'pattern': r'(プラス|マイナス)?(\d+)%(以上|超)',
                'style': 'emphasis'
            },
            # 決算・IR
            {
                'pattern': r'(決算|業績|増配|減配|上方修正|下方修正)',
                'style': 'highlight'
            },
            # 金融政策
            {
                'pattern': r'(FOMC|日銀|金融政策|利上げ|利下げ)',
                'style': 'emphasis'
            }
        ]
        
        detected = []
        for pattern_info in emphasis_patterns:
            matches = re.finditer(pattern_info['pattern'], text)
            for match in matches:
                detected.append({
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group(0),
                    'style': pattern_info['style']
                })
        
        return detected
    
    def split_text_by_emphasis(
        self,
        text: str,
        emphasis_list: List[Dict]
    ) -> List[Dict]:
        """
        テキストを強調部分で分割
        
        Args:
            text: テキスト
            emphasis_list: 強調パターンのリスト
        
        Returns:
            List[Dict]: 分割されたセグメント
        """
        if not emphasis_list:
            return [{'text': text, 'style': 'normal'}]
        
        # 位置でソート
        emphasis_list = sorted(emphasis_list, key=lambda x: x['start'])
        
        segments = []
        current_pos = 0
        
        for emphasis in emphasis_list:
            # 強調前のテキスト
            if emphasis['start'] > current_pos:
                before_text = text[current_pos:emphasis['start']]
                if before_text.strip():
                    segments.append({
                        'text': before_text,
                        'style': 'normal'
                    })
            
            # 強調部分
            segments.append({
                'text': emphasis['text'],
                'style': emphasis['style']
            })
            
            current_pos = emphasis['end']
        
        # 残りのテキスト
        if current_pos < len(text):
            remaining = text[current_pos:]
            if remaining.strip():
                segments.append({
                    'text': remaining,
                    'style': 'normal'
                })
        
        return segments
    
    def generate_section_audio(
        self,
        section_name: str,
        text: str,
        auto_emphasis: bool = True
    ) -> bytes:
        """
        セクションの音声を生成（スタイル自動適用）
        
        Args:
            section_name: セクション名
            text: テキスト
            auto_emphasis: 自動強調を有効にするか
        
        Returns:
            bytes: 音声データ
        """
        # セクションの基本スタイル
        base_style_name = self.get_section_style(section_name)
        
        # 自動強調が無効の場合は基本スタイルのみ
        if not auto_emphasis:
            style = self.styles[base_style_name]
            return self.voicevox.generate_audio(
                text,
                speaker=style['speaker'],
                speed=style['speed'],
                pitch=style['pitch'],
                intonation=style['intonation']
            )
        
        # 強調部分を検出
        emphasis_list = self.detect_text_emphasis(text)
        
        # 強調がない場合は基本スタイル
        if not emphasis_list:
            style = self.styles[base_style_name]
            return self.voicevox.generate_audio(
                text,
                speaker=style['speaker'],
                speed=style['speed'],
                pitch=style['pitch'],
                intonation=style['intonation']
            )
        
        # テキストを分割
        segments = self.split_text_by_emphasis(text, emphasis_list)
        
        # 各セグメントで音声生成
        audio_segments = []
        for segment in segments:
            style_name = segment['style']
            style = self.styles[style_name]
            
            audio = self.voicevox.generate_audio(
                segment['text'],
                speaker=style['speaker'],
                speed=style['speed'],
                pitch=style['pitch'],
                intonation=style['intonation']
            )
            audio_segments.append(audio)
        
        # 音声を連結
        if len(audio_segments) == 1:
            return audio_segments[0]
        else:
            return self.voicevox._combine_audio_segments(audio_segments)
    
    def generate_styled_script(
        self,
        script_sections: List[Dict]
    ) -> List[Dict]:
        """
        台本全体にスタイルを適用
        
        Args:
            script_sections: 台本のセクションリスト
                [
                    {"name": "opening", "script": "..."},
                    {"name": "us_market", "script": "..."},
                    ...
                ]
        
        Returns:
            List[Dict]: スタイル情報付きセクション
        """
        styled_sections = []
        
        for section in script_sections:
            section_name = section['name']
            script = section['script']
            
            # セクションのスタイル決定
            style_name = self.get_section_style(section_name)
            
            styled_section = {
                **section,
                'style': style_name,
                'style_info': self.styles[style_name]
            }
            
            styled_sections.append(styled_section)
        
        return styled_sections
    
    def get_style_info(self, style_name: str) -> Dict:
        """
        スタイル情報を取得
        
        Args:
            style_name: スタイル名
        
        Returns:
            Dict: スタイル情報
        """
        return self.styles.get(style_name, self.styles['normal'])
    
    def list_styles(self) -> None:
        """利用可能なスタイルを表示"""
        print("\n" + "="*60)
        print("🎭 利用可能なスタイル")
        print("="*60)
        
        for name, info in self.styles.items():
            print(f"\n【{name}】")
            print(f"  説明: {info['description']}")
            print(f"  スピーカー: {info['speaker']}")
            print(f"  速度: {info['speed']}")
            print(f"  音高: {info['pitch']}")
            print(f"  抑揚: {info['intonation']}")


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎭 StyleController テスト")
    print("="*60 + "\n")
    
    try:
        controller = StyleController()
        
        # テスト1: スタイル一覧
        print("\n=== テスト1: スタイル一覧 ===")
        controller.list_styles()
        
        # テスト2: セクション別スタイル
        print("\n=== テスト2: セクション別スタイル ===")
        test_sections = ['opening', 'us_market', 'after_hours_ir', 'closing']
        
        for section in test_sections:
            style = controller.get_section_style(section)
            print(f"  {section}: {style}")
        
        # テスト3: テキスト内の強調検出
        print("\n=== テスト3: テキスト内の強調検出 ===")
        test_text = """
日経平均は大きく上昇し、プラス3%超となりました。
これはFOMCの結果を好感したもので、注目の決算発表も控えています。
"""
        
        emphasis_list = controller.detect_text_emphasis(test_text)
        print(f"検出された強調: {len(emphasis_list)}箇所")
        for emp in emphasis_list:
            print(f"  - '{emp['text']}' → {emp['style']}")
        
        # テスト4: テキスト分割
        print("\n=== テスト4: テキスト分割 ===")
        segments = controller.split_text_by_emphasis(test_text, emphasis_list)
        print(f"分割セグメント: {len(segments)}個")
        for i, seg in enumerate(segments, 1):
            print(f"  {i}. [{seg['style']}] {seg['text'][:30]}...")
        
        # テスト5: 音声生成（スタイル自動適用）
        print("\n=== テスト5: 音声生成（スタイル自動適用） ===")
        
        test_script = "おはようございます。今日は重要なニュースがあります。日経平均が大きく上昇しました。"
        
        print("音声生成中...")
        audio = controller.generate_section_audio(
            section_name='important_news',
            text=test_script,
            auto_emphasis=True
        )
        
        # 保存
        from src.voice_generation.pause_handler import PauseHandler
        pause_handler = PauseHandler()
        duration = pause_handler.get_audio_duration(audio)
        
        output_path = "data/test_audio/test_style_auto.wav"
        pause_handler.save_audio(audio, output_path)
        
        print(f"✅ 音声生成完了")
        print(f"   長さ: {duration:.2f}秒")
        print(f"   ファイル: {output_path}")
        
        # テスト6: 複数セクションのスタイル適用
        print("\n=== テスト6: 複数セクションのスタイル適用 ===")
        
        script_sections = [
            {"name": "opening", "script": "おはようございます"},
            {"name": "us_market", "script": "米国市場は上昇しました"},
            {"name": "after_hours_ir", "script": "重要な決算発表です"}
        ]
        
        styled = controller.generate_styled_script(script_sections)
        
        for section in styled:
            print(f"  {section['name']}: {section['style']} ({section['style_info']['description']})")
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - data/test_audio/test_style_auto.wav")
        print("\n🎧 再生して、強調部分で声が変わるか確認してください！")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
