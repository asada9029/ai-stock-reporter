"""
音声時間管理モジュール
音声の長さを測定し、目標時間に調整
"""

import wave
import io
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
from datetime import datetime


class DurationManager:
    """音声時間管理クラス"""
    
    # 速度調整の範囲
    MIN_SPEED = 0.75   # 最小速度（これ以上遅くしない）
    MAX_SPEED = 1.3    # 最大速度（これ以上速くしない）
    
    # 許容誤差（秒）
    TOLERANCE = 5.0    # 目標時間との誤差がこれ以内ならOK
    
    def __init__(self):
        """初期化"""
        self.section_durations = {}
        print("✅ DurationManager 初期化完了")
    
    def measure_audio_duration(self, audio_data: bytes) -> float:
        """
        音声の長さを測定
        
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
    
    def calculate_required_speed(
        self,
        current_duration: float,
        target_duration: float
    ) -> Tuple[float, bool]:
        """
        目標時間に合わせるための速度を計算
        
        Args:
            current_duration: 現在の長さ（秒）
            target_duration: 目標の長さ（秒）
        
        Returns:
            Tuple[float, bool]: (必要な速度, 調整可能か)
        """
        if target_duration <= 0:
            return 1.0, False
        
        # 必要な速度 = 現在の長さ / 目標の長さ
        required_speed = current_duration / target_duration
        
        # 速度が範囲内か確認
        if required_speed < self.MIN_SPEED:
            # 遅すぎる → 最小速度で妥協
            return self.MIN_SPEED, False
        elif required_speed > self.MAX_SPEED:
            # 速すぎる → 最大速度で妥協
            return self.MAX_SPEED, False
        else:
            return required_speed, True
    
    def check_duration_match(
        self,
        current_duration: float,
        target_duration: float
    ) -> Dict:
        """
        時間が目標に合っているかチェック
        
        Args:
            current_duration: 現在の長さ（秒）
            target_duration: 目標の長さ（秒）
        
        Returns:
            Dict: チェック結果
        """
        diff = current_duration - target_duration
        diff_percent = (diff / target_duration) * 100 if target_duration > 0 else 0
        
        is_ok = abs(diff) <= self.TOLERANCE
        
        result = {
            "current_duration": round(current_duration, 2),
            "target_duration": round(target_duration, 2),
            "difference": round(diff, 2),
            "difference_percent": round(diff_percent, 2),
            "is_acceptable": is_ok,
            "status": "OK" if is_ok else "調整が必要"
        }
        
        return result
    
    def adjust_speed_for_target(
        self,
        audio_data: bytes,
        target_duration: float,
        voicevox_client,
        text: str,
        **generation_params
    ) -> Tuple[bytes, Dict]:
        """
        目標時間に合わせて音声を再生成
        
        Args:
            audio_data: 元の音声データ
            target_duration: 目標時間（秒）
            voicevox_client: VOICEVOXクライアント
            text: テキスト
            **generation_params: 音声生成パラメータ
        
        Returns:
            Tuple[bytes, Dict]: (調整後の音声, 調整情報)
        """
        current_duration = self.measure_audio_duration(audio_data)
        
        # 速度計算
        required_speed, is_adjustable = self.calculate_required_speed(
            current_duration,
            target_duration
        )
        
        # 元の速度を取得（デフォルト1.0）
        original_speed = generation_params.get('speed', 1.0)
        
        # 新しい速度
        new_speed = original_speed * required_speed
        
        # 速度を範囲内にクリップ
        new_speed = max(self.MIN_SPEED, min(self.MAX_SPEED, new_speed))
        
        # 音声を再生成
        generation_params['speed'] = new_speed
        adjusted_audio = voicevox_client.generate_audio(text, **generation_params)
        
        adjusted_duration = self.measure_audio_duration(adjusted_audio)
        
        adjustment_info = {
            "original_duration": round(current_duration, 2),
            "target_duration": round(target_duration, 2),
            "adjusted_duration": round(adjusted_duration, 2),
            "original_speed": round(original_speed, 2),
            "required_speed": round(required_speed, 2),
            "adjusted_speed": round(new_speed, 2),
            "is_fully_adjustable": is_adjustable,
            "final_difference": round(adjusted_duration - target_duration, 2)
        }
        
        return adjusted_audio, adjustment_info
    
    def record_section_duration(
        self,
        section_name: str,
        duration: float,
        target_duration: float
    ):
        """
        セクションの時間を記録
        
        Args:
            section_name: セクション名
            duration: 実際の時間
            target_duration: 目標時間
        """
        self.section_durations[section_name] = {
            "actual": round(duration, 2),
            "target": round(target_duration, 2),
            "difference": round(duration - target_duration, 2)
        }
    
    def get_total_duration(self) -> Dict:
        """
        全セクションの合計時間を取得
        
        Returns:
            Dict: 合計時間情報
        """
        if not self.section_durations:
            return {
                "total_actual": 0,
                "total_target": 0,
                "total_difference": 0
            }
        
        total_actual = sum(s['actual'] for s in self.section_durations.values())
        total_target = sum(s['target'] for s in self.section_durations.values())
        
        return {
            "total_actual": round(total_actual, 2),
            "total_target": round(total_target, 2),
            "total_difference": round(total_actual - total_target, 2),
            "sections": self.section_durations
        }
    
    def generate_duration_report(self) -> str:
        """
        時間管理レポートを生成
        
        Returns:
            str: レポート文字列
        """
        if not self.section_durations:
            return "記録されたセクションがありません"
        
        total = self.get_total_duration()
        
        report = "\n" + "="*60 + "\n"
        report += "⏱️  音声時間管理レポート\n"
        report += "="*60 + "\n\n"
        
        report += "【セクション別】\n"
        for name, info in self.section_durations.items():
            status = "✅" if abs(info['difference']) <= self.TOLERANCE else "⚠️"
            report += f"{status} {name}:\n"
            report += f"   実際: {info['actual']}秒 / 目標: {info['target']}秒 "
            report += f"(差: {info['difference']:+.2f}秒)\n"
        
        report += f"\n【合計】\n"
        report += f"実際の総時間: {total['total_actual']}秒\n"
        report += f"目標の総時間: {total['total_target']}秒\n"
        report += f"差分: {total['total_difference']:+.2f}秒\n"
        
        # 判定
        if abs(total['total_difference']) <= self.TOLERANCE * 2:
            report += f"\n✅ 目標時間に収まっています\n"
        else:
            report += f"\n⚠️ 目標時間から大きくズレています\n"
        
        report += "="*60 + "\n"
        
        return report
    
    def save_duration_report(
        self,
        output_path: str = "data/reports/duration_report.txt"
    ) -> str:
        """
        レポートをファイルに保存
        
        Args:
            output_path: 出力パス
        
        Returns:
            str: 保存したファイルパス
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        report = self.generate_duration_report()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
            f.write(f"\n生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # JSON形式でも保存
        json_path = output_file.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.get_total_duration(), f, ensure_ascii=False, indent=2)
        
        print(f"💾 レポート保存: {output_file}")
        return str(output_file)
    
    def suggest_adjustments(self) -> List[str]:
        """
        調整が必要なセクションの提案
        
        Returns:
            List[str]: 提案リスト
        """
        suggestions = []
        
        for name, info in self.section_durations.items():
            diff = info['difference']
            
            if abs(diff) > self.TOLERANCE:
                if diff > 0:
                    # 長すぎる
                    speed_up = (info['actual'] / info['target'])
                    suggestions.append(
                        f"{name}: {diff:.1f}秒長い → 速度を{speed_up:.2f}xに上げる"
                    )
                else:
                    # 短すぎる
                    slow_down = (info['actual'] / info['target'])
                    suggestions.append(
                        f"{name}: {-diff:.1f}秒短い → 速度を{slow_down:.2f}xに下げる"
                    )
        
        return suggestions
    
    def reset(self):
        """記録をリセット"""
        self.section_durations = {}
        print("🔄 時間記録をリセットしました")


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("⏱️  DurationManager テスト")
    print("="*60 + "\n")
    
    try:
        from src.voice_generation.voice_client import VOICEVOXClient
        
        manager = DurationManager()
        voicevox = VOICEVOXClient()
        
        # テスト1: 音声の長さ測定
        print("=== テスト1: 音声の長さ測定 ===")
        test_text = "おはようございます。今日は株式市場のニュースをお伝えします。"
        
        audio = voicevox.generate_audio(test_text)
        duration = manager.measure_audio_duration(audio)
        
        print(f"テキスト: {test_text}")
        print(f"長さ: {duration:.2f}秒")
        
        # テスト2: 目標時間チェック
        print("\n=== テスト2: 目標時間チェック ===")
        target = 5.0
        check_result = manager.check_duration_match(duration, target)
        
        print(f"現在: {check_result['current_duration']}秒")
        print(f"目標: {check_result['target_duration']}秒")
        print(f"差分: {check_result['difference']}秒 ({check_result['difference_percent']}%)")
        print(f"判定: {check_result['status']}")
        
        # テスト3: 速度調整
        print("\n=== テスト3: 速度調整 ===")
        
        print(f"目標時間: {target}秒に調整中...")
        adjusted_audio, adjust_info = manager.adjust_speed_for_target(
            audio,
            target,
            voicevox,
            test_text
        )
        
        print(f"元の長さ: {adjust_info['original_duration']}秒")
        print(f"元の速度: {adjust_info['original_speed']}x")
        print(f"調整後の速度: {adjust_info['adjusted_speed']}x")
        print(f"調整後の長さ: {adjust_info['adjusted_duration']}秒")
        print(f"最終差分: {adjust_info['final_difference']}秒")
        
        # 保存
        from src.voice_generation.pause_handler import PauseHandler
        pause_handler = PauseHandler()
        pause_handler.save_audio(audio, "data/test_audio/test_original.wav")
        pause_handler.save_audio(adjusted_audio, "data/test_audio/test_adjusted.wav")
        
        # テスト4: 複数セクションの記録
        print("\n=== テスト4: 複数セクションの記録 ===")
        
        manager.record_section_duration("opening", 32.5, 30.0)
        manager.record_section_duration("us_market", 88.3, 90.0)
        manager.record_section_duration("closing", 28.7, 30.0)
        
        # テスト5: レポート生成
        print("\n=== テスト5: レポート生成 ===")
        print(manager.generate_duration_report())
        
        # テスト6: 調整提案
        print("\n=== テスト6: 調整提案 ===")
        suggestions = manager.suggest_adjustments()
        
        if suggestions:
            print("調整が必要なセクション:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")
        else:
            print("✅ 全セクションが目標時間内です")
        
        # テスト7: レポート保存
        print("\n=== テスト7: レポート保存 ===")
        report_path = manager.save_duration_report()
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - data/test_audio/test_original.wav（元の音声）")
        print("  - data/test_audio/test_adjusted.wav（調整後）")
        print(f"  - {report_path}")
        print("\n🎧 2つの音声を比較して、速度の違いを確認してください！")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
