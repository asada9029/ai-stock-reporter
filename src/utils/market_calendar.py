import datetime
import pandas as pd
import pandas_market_calendars as mcal
import pytz

def is_market_open(video_type: str) -> bool:
    """
    指定された動画タイプに合わせて、対象市場が開場していた（している）か判定する。
    
    Args:
        video_type: "morning_video" (米国市場) または "evening_video" (日本市場)
        
    Returns:
        bool: 市場が開場していた（している）場合は True
    """
    # タイムゾーン設定
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.datetime.now(jst)
    
    if "morning" in video_type:
        # 米国市場 (NYSE) の判定
        # 朝動画は「前日の米国市場」の結果を報じる。
        # 実行タイミングがJST朝6:15なので、前日の日付で判定する。
        nyse = mcal.get_calendar('NYSE')
        
        # 判定対象日: 実行時のJST日付の前日（米国時間での前営業日を確認するため）
        # 例: JST 2/16(月) 6:15 実行の場合 -> 2/15(日) をチェック -> 休みならスキップ
        # 実際には NYSE のカレンダーが祝日・土日を考慮してくれる。
        check_date = now_jst - datetime.timedelta(days=1)
        schedule = nyse.schedule(start_date=check_date.date(), end_date=check_date.date())
        
        if schedule.empty:
            print(f"DEBUG: NYSE is closed on {check_date.date()}")
            return False
        return True
        
    else:
        # 日本市場 (JPX) の判定
        # 夜動画は「当日の日本市場」の結果を報じる。
        jpx = mcal.get_calendar('JPX')
        
        # 判定対象日: 実行時のJST日付
        check_date = now_jst
        schedule = jpx.schedule(start_date=check_date.date(), end_date=check_date.date())
        
        if schedule.empty:
            print(f"DEBUG: JPX is closed on {check_date.date()}")
            return False
        return True

def get_next_market_open(video_type: str) -> datetime.datetime:
    """
    次に市場が開場し、動画が投稿される予定日時を計算する。
    
    Returns:
        datetime: 次の投稿予定日時（JST）
    """
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.datetime.now(jst)
    
    # 次の候補を判定
    if "morning" in video_type:
        # 現在が朝動画のタイミングなら、次は今日の夜動画
        next_type = "evening_video"
        next_check_date = now_jst
    else:
        # 現在が夜動画のタイミングなら、次は明日の朝動画
        next_type = "morning_video"
        next_check_date = now_jst + datetime.timedelta(days=1)

    # 市場が開いている日までループ
    for _ in range(10): # 最大10日先まで探す
        if is_market_open(next_type):
            # その日の投稿時間を設定
            if "morning" in next_type:
                return next_check_date.replace(hour=8, minute=0, second=0, microsecond=0)
            else:
                return next_check_date.replace(hour=18, minute=0, second=0, microsecond=0)
        
        # 次の投稿タイミングへ
        if "morning" in next_type:
            next_type = "evening_video"
            # 日付はそのまま（朝の次は同じ日の夜）
        else:
            next_type = "morning_video"
            next_check_date += datetime.timedelta(days=1)
            
    return now_jst # フォールバック
