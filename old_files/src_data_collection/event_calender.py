"""
イベントカレンダーモジュール（初心者向けシンプル版）
AIの検索を支援するヒント情報を提供
"""

from datetime import datetime, timedelta
from typing import Dict, List


def get_event_search_hints() -> Dict:
    """
    AIが検索すべきイベント情報のヒントを返す
    
    Returns:
        Dict: 検索キーワードと日付情報
    """
    today = datetime.now()
    
    # 1ヶ月後まで
    one_month_later = today + timedelta(days=30)
    
    # 曜日を日本語で取得
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    today_weekday = weekdays_jp[today.weekday()]
    
    return {
        "dates": {
            "today": today.strftime("%Y年%m月%d日"),
            "today_en": today.strftime("%Y-%m-%d"),
            "weekday": today_weekday,
            "month_range": f"{today.strftime('%Y年%m月')}〜{one_month_later.strftime('%Y年%m月')}"
        },
        "search_keywords": {
            # 決算発表（最重要）
            "earnings": [
                f"決算発表予定 {today.strftime('%Y年%m月%d日')}",
                f"本日の決算発表 {today.strftime('%m月%d日')}",
                "今週の決算発表予定"
            ],
            # 超重要な経済指標のみ
            "critical_indicators": [
                # 日本
                f"日銀 金融政策決定会合 {today.year}年 予定",
                f"日本 GDP発表 {today.strftime('%Y年%m月')}",
                f"消費者物価指数 日本 {today.strftime('%Y年%m月')}",
                
                # 米国
                f"FOMC {today.year}年 日程",
                f"米雇用統計 {today.strftime('%Y年%m月')}",
                f"CPI アメリカ {today.strftime('%Y年%m月')} 発表"
            ]
        },
        # 初心者向け説明文
        "beginner_explanations": {
            "FOMC": "アメリカの中央銀行が金利を決める会議。株価に大きな影響があります",
            "日銀金融政策決定会合": "日本銀行が金利を決める会議。株価に大きな影響があります",
            "米雇用統計": "毎月第1金曜日発表。アメリカの雇用状況を示す指標で、株価が大きく動く日として有名です",
            "CPI": "物価の上がり具合を示す指標。インフレが進むと金利が上がる可能性があり、株価に影響します",
            "GDP": "国の経済成長率。経済が成長していれば株価にプラス、縮小していればマイナスです",
            "決算発表": "企業の業績発表。予想を上回れば株価上昇、下回れば下落することが多いです"
        },
        # 重要度（シンプル化：2段階のみ）
        "importance_keywords": {
            "critical": [
                "FOMC", "日銀", "金融政策", "利上げ", "利下げ",
                "雇用統計", "CPI", "GDP", "決算発表"
            ],
            "high": [
                "本決算", "四半期決算", "増配", "減配"
            ]
        },
        "context": {
            "is_morning": datetime.now().hour < 12,
            "is_after_close": datetime.now().hour >= 15
        }
    }


def get_search_priority() -> Dict[str, List[str]]:
    """
    時間帯に応じた検索優先度を返す（シンプル版）
    
    Returns:
        Dict: 優先度別の検索キーワードリスト
    """
    hints = get_event_search_hints()
    context = hints["context"]
    
    if context["is_morning"]:
        # 朝：米国の重要指標と本日の決算
        return {
            "priority_high": (
                hints["search_keywords"]["earnings"][:2] +
                [hints["search_keywords"]["critical_indicators"][3],  # FOMC
                 hints["search_keywords"]["critical_indicators"][4]]  # 米雇用統計
            )
        }
    
    elif context["is_after_close"]:
        # 引け後：本日の決算発表
        return {
            "priority_high": (
                hints["search_keywords"]["earnings"] +
                ["引け後 決算発表 今日", "本日の決算発表"]
            )
        }
    
    else:
        # 日中：決算メイン
        return {
            "priority_high": hints["search_keywords"]["earnings"]
        }


def format_for_ai_prompt() -> str:
    """
    AIプロンプト用にフォーマットされたイベントヒントを返す（初心者向け）
    
    Returns:
        str: AIが読みやすい形式のヒント情報
    """
    hints = get_event_search_hints()
    priority = get_search_priority()
    
    prompt = f"""
# イベント情報検索ガイド（初心者向けシンプル版）

## 基本情報
- 今日の日付: {hints['dates']['today']} ({hints['dates']['weekday']}曜日)
- 検索対象期間: 今日から1ヶ月先まで

## 必ず検索すべき重要イベント

### 最優先：今日・今週の予定
{chr(10).join(f"- {keyword}" for keyword in priority['priority_high'])}

### 追加確認：1ヶ月以内の重要イベント
{chr(10).join(f"- {keyword}" for keyword in hints['search_keywords']['critical_indicators'])}

## 用語の初心者向け説明（動画内で使う場合）
{chr(10).join(f"- **{term}**: {explanation}" for term, explanation in hints['beginner_explanations'].items())}

## 重要度の判定基準
### 🔴 超重要（必ず取り上げる）
{', '.join(hints['importance_keywords']['critical'])}

### 🟡 重要（時間があれば取り上げる）
{', '.join(hints['importance_keywords']['high'])}

## 注意事項
- 1ヶ月以上先のイベントは含めない
- 初心者向けなので、専門用語は必ず説明を付ける
- 「なぜ株価に影響するのか」を明確に説明する
"""
    return prompt


def get_beginner_friendly_summary() -> Dict:
    """
    初心者向けの分かりやすいサマリーを返す
    
    Returns:
        Dict: 今注目すべきイベントの要約
    """
    hints = get_event_search_hints()
    today = datetime.now()
    
    # 曜日チェック
    is_first_friday = (today.weekday() == 4 and 1 <= today.day <= 7)
    
    summary = {
        "today_focus": [],
        "this_week_focus": [],
        "beginner_tips": []
    }
    
    # 米雇用統計の日かチェック
    if is_first_friday:
        summary["today_focus"].append({
            "event": "米雇用統計",
            "importance": "超重要",
            "explanation": "毎月第1金曜日の今日は「米雇用統計」の発表日です。この日は株価が大きく動くことで有名なので、注目です！"
        })
    
    # 基本的なフォーカスポイント
    summary["this_week_focus"] = [
        "今週の主要企業の決算発表",
        "日米の重要な経済指標",
        "日銀・FOMCの予定（ある場合）"
    ]
    
    # 初心者向けTips
    summary["beginner_tips"] = [
        "経済指標の発表日は株価が動きやすいので、落ち着いて見守りましょう",
        "決算発表は「予想と比べてどうだったか」が重要です",
        # "分からない用語が出てきたら、その場で調べる習慣をつけましょう"
    ]
    
    return summary


# テスト用
if __name__ == "__main__":
    print("=== イベント検索ヒント（初心者向けシンプル版） ===")
    hints = get_event_search_hints()
    
    print(f"\n📅 日付情報:")
    for key, value in hints['dates'].items():
        print(f"  {key}: {value}")
    
    print(f"\n🔍 検索キーワード（決算）:")
    for keyword in hints['search_keywords']['earnings']:
        print(f"  - {keyword}")
    
    print(f"\n🔍 検索キーワード（超重要指標のみ）:")
    for keyword in hints['search_keywords']['critical_indicators']:
        print(f"  - {keyword}")
    
    print(f"\n📚 初心者向け用語説明:")
    for term, explanation in hints['beginner_explanations'].items():
        print(f"  - {term}: {explanation}")
    
    print(f"\n=== 初心者向けサマリー(動画のOPとかに使う？？) ===")
    summary = get_beginner_friendly_summary()
    print(f"\n今日の注目:")
    for item in summary['today_focus']:
        print(f"  🔴 {item['event']}: {item['explanation']}")
    if not summary['today_focus']:
        print("  特になし")
    
    print(f"\n今週の注目:")
    for item in summary['this_week_focus']:
        print(f"  - {item}")
    
    print(f"\n初心者向けTips:")
    for tip in summary['beginner_tips']:
        print(f"  💡 {tip}")
    
    print(f"\n=== AIプロンプト用フォーマット ===")
    print(format_for_ai_prompt())
