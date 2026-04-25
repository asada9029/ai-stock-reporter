import datetime
import pandas as pd
import pandas_market_calendars as mcal
import pytz

def is_market_open(video_type: str, check_time: datetime.datetime = None) -> bool:
    """
    指定された動画タイプに合わせて、対象市場が開場していた（している）か判定する。
    
    Args:
        video_type: "morning_video" (米国市場) または "evening_video" (日本市場)
        check_time: 判定対象の時間（Noneの場合は現在時刻）
        
    Returns:
        bool: 市場が開場していた（している）場合は True
    """
    # タイムゾーン設定
    jst = pytz.timezone('Asia/Tokyo')
    if check_time is None:
        now_jst = datetime.datetime.now(jst)
    else:
        now_jst = check_time.astimezone(jst)
    
    if "morning" in video_type:
        # 米国市場 (NYSE) の判定
        # 朝動画は「前日の米国市場」の結果を報じる。
        # 実行タイミングがJST朝5:00前後なので、前日の日付で判定する。
        nyse = mcal.get_calendar('NYSE')
        
        # 判定対象日: 実行時のJST日付の前日（米国時間での前営業日を確認するため）
        # 例: JST 2/16(月) 5:00 実行の場合 -> 2/15(日) をチェック -> 休みならスキップ
        # 実際には NYSE のカレンダーが祝日・土日を考慮してくれる。
        check_date = now_jst - datetime.timedelta(days=1)

        # 【特別対応】
        # 1. 土曜日の朝（米国金曜日の結果）はスキップし、月曜日の朝にまとめて報じるようにする
        if now_jst.weekday() == 5: # 土曜日
            print(f"DEBUG: Skipping Saturday morning video (Friday market results). These will be covered on Monday.")
            return False
        
        # 2. 日曜日の朝もスキップ
        if now_jst.weekday() == 6: # 日曜日
            print(f"DEBUG: Skipping Sunday morning video.")
            return False

        # 3. 月曜日の朝は、米国金曜日の結果を報じるため、金曜日が開場していたかチェックする
        if now_jst.weekday() == 0: # 月曜日
            # 金曜日（3日前）をチェック
            check_date = now_jst - datetime.timedelta(days=3)
            print(f"DEBUG: Monday morning video. Checking Friday market ({check_date.date()}).")

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
        # 土曜日の朝（米国金曜の結果）はスキップする特別ルールを考慮して判定
        if is_market_open(next_type, check_time=next_check_date):
            # その日の投稿時間を設定
            if "morning" in next_type:
                return next_check_date.replace(hour=7, minute=0, second=0, microsecond=0)
            else:
                return next_check_date.replace(hour=18, minute=0, second=0, microsecond=0)
        
        # 次の投稿タイミングへ
        if "morning" in next_type:
            # 朝が休みなら、同じ日の夜をチェック
            next_type = "evening_video"
        else:
            # 夜の次は、翌日の朝をチェック
            next_type = "morning_video"
            next_check_date += datetime.timedelta(days=1)
            
    return now_jst # フォールバック
