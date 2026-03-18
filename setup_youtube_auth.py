import os
import json
import base64
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# .envを読み込む
load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.readonly'
]

def initialize_auth():
    # .envからGCP_CLIENT_SECRETSを取得
    client_secrets_json = os.getenv('GCP_CLIENT_SECRETS')
    if not client_secrets_json:
        print("❌ エラー: .envにGCP_CLIENT_SECRETSが設定されていません。")
        return

    # 一時的にJSONファイルとして保存（OAuthライブラリがファイルを要求するため）
    secrets_path = 'temp_secrets.json'
    try:
        # 文字列が引用符で囲まれている可能性があるため、適切にパース
        secrets_data = json.loads(client_secrets_json)
        with open(secrets_path, 'w') as f:
            json.dump(secrets_data, f)
        
        # 認証フローの実行
        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        # ローカルサーバーを起動して認証
        creds = flow.run_local_server(
            port=0,
            access_type='offline',  # 合鍵（リフレッシュトークン）を要求する
            prompt='consent'        # 同意画面を強制して、確実に合鍵をもらう
        )
        
        # token.jsonとして保存
        token_path = 'token.json'
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        
        print(f"✅ 認証成功！ '{token_path}' を作成しました。")
        
        # Base64エンコード
        with open(token_path, 'rb') as f:
            encoded_string = base64.b64encode(f.read()).decode('utf-8')
        
        print("\n" + "="*50)
        print("GitHub Secrets に登録する文字列 (TOKEN_JSON_BASE64):")
        print("="*50)
        print(encoded_string)
        print("="*50)
        print("\nこの文字列をコピーして、GitHubの 'TOKEN_JSON_BASE64' シークレットに登録してください。")
        print("\n⚠️ セキュリティのため、この後 'token.json' を削除します。")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
    finally:
        # 一時ファイルを削除
        if os.path.exists(secrets_path):
            os.remove(secrets_path)
            print(f"🗑️ '{secrets_path}' を削除しました。")
        # token.jsonを削除
        if os.path.exists(token_path):
            os.remove(token_path)
            print(f"🗑️ '{token_path}' を削除しました。")

if __name__ == "__main__":
    initialize_auth()
