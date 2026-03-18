import os
import datetime
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
import json
import base64
from pathlib import Path
import pytz

class YouTubeUploader:
    def __init__(self):
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        scopes = ['https://www.googleapis.com/auth/youtube.upload']
        
        # GitHub Secrets から復元されたファイルを優先的に探す
        token_path = Path('src/config/token.json')
        
        try:
            if not token_path.exists():
                # .env の TOKEN_JSON_BASE64 から復元を試みる (ローカル実行用)
                token_base64 = os.getenv('TOKEN_JSON_BASE64')
                if token_base64:
                    token_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(token_path, 'wb') as f:
                        f.write(base64.b64decode(token_base64))
                else:
                    raise FileNotFoundError("token.json not found and TOKEN_JSON_BASE64 not set.")

            with open(token_path, 'r') as f:
                creds_data = json.load(f)
                creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data, scopes)

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # 更新されたトークンを保存（一時的に上書き）
                with open(token_path, 'w') as f:
                    f.write(creds.to_json())

            return build('youtube', 'v3', credentials=creds)
        finally:
            # セキュリティのため、認証サービス構築後に token.json を削除
            if token_path.exists():
                try:
                    token_path.unlink()
                    print(f"🗑️ セキュリティのため '{token_path}' を削除しました。")
                except Exception as e:
                    print(f"⚠️ '{token_path}' の削除に失敗しました: {e}")

    def upload_video(self, video_path, title, description, category_id="25", publish_at=None, thumbnail_path=None):
        """
        動画をアップロードする。
        publish_at: ISO 8601形式の文字列 (例: 2026-02-15T18:00:00Z)
        """
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'private', # 予約投稿の場合は一旦 private
                'selfDeclaredMadeForKids': False,
            }
        }

        if publish_at:
            body['status']['publishAt'] = publish_at
            # 予約投稿の場合は privacyStatus を 'private' にする必要がある（API仕様）
            body['status']['privacyStatus'] = 'private'
        else:
            body['status']['privacyStatus'] = 'public'

        media = MediaFileUpload(
            video_path, 
            chunksize=1024 * 1024, 
            resumable=True, 
            mimetype='video/mp4'
        )

        print(f"🚀 動画をアップロード中: {video_path}")
        request = self.youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  - アップロード進捗: {int(status.progress() * 100)}%")

        video_id = response['id']
        print(f"✅ 動画アップロード完了! Video ID: {video_id}")

        # サムネイルのアップロード
        if thumbnail_path and os.path.exists(thumbnail_path):
            print(f"🖼️ サムネイルをアップロード中: {thumbnail_path}")
            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            print("✅ サムネイルアップロード完了")

        return video_id

def get_publish_time(video_type):
    """
    動画タイプに合わせて予約投稿時間を計算する。
    朝動画: 当日の 08:00 JST
    夜動画: 当日の 18:00 JST
    """
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.datetime.now(jst)
    
    if "morning" in video_type:
        publish_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        publish_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
    
    # もし既にその時間を過ぎていたら、5分後に設定（即時公開に近い状態）
    if publish_time < now:
        publish_time = now + datetime.timedelta(minutes=5)
        
    return publish_time.isoformat()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--type", required=True, choices=["morning_video", "evening_video"])
    parser.add_argument("--thumbnail", help="Path to thumbnail image")
    args = parser.parse_args()

    # タイトルと説明文の生成（簡易版）
    date_str = datetime.datetime.now().strftime("%Y/%m/%d")
    if args.type == "morning_video":
        title = f"【朝刊】米国株市場まとめ {date_str}"
        description = "昨晩の米国株市場の動きをAIがサクッと解説します。"
    else:
        title = f"【夕刊】日本株市場まとめ {date_str}"
        description = "本日の日本株市場の動きをAIがサクッと解説します。"

    publish_at = get_publish_time(args.type)
    
    uploader = YouTubeUploader()
    uploader.upload_video(
        video_path=args.video,
        title=title,
        description=description,
        publish_at=publish_at,
        thumbnail_path=args.thumbnail
    )
