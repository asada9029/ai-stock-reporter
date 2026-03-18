# test_voicevox.py を作成
import requests

def test_voicevox_connection():
    """VOICEVOX接続テスト"""
    try:
        response = requests.get("http://localhost:50021/version")
        if response.status_code == 200:
            print(f"✅ VOICEVOX接続成功: {response.json()}")
            return True
        else:
            print("❌ VOICEVOX接続失敗")
            return False
    except Exception as e:
        print(f"❌ エラー: {e}")
        print("VOICEVOXが起動していることを確認してください")
        return False

def test_voice_generation():
    """音声生成テスト"""
    base_url = "http://localhost:50021"
    
    # 四国めたん ノーマル
    text = "テストです。接続できています。"
    speaker_id = 2
    
    # クエリ作成
    response = requests.post(
        f"{base_url}/audio_query",
        params={'text': text, 'speaker': speaker_id}
    )
    
    if response.status_code != 200:
        print(f"❌ クエリ作成失敗: {response.text}")
        return False
    
    query_data = response.json()
    
    # 音声合成
    response = requests.post(
        f"{base_url}/synthesis",
        params={'speaker': speaker_id},
        json=query_data
    )
    
    if response.status_code == 200:
        with open("test_voice.wav", "wb") as f:
            f.write(response.content)
        print("✅ 音声生成成功: test_voice.wav")
        return True
    else:
        print(f"❌ 音声合成失敗: {response.text}")
        return False

if __name__ == "__main__":
    print("=== VOICEVOX接続テスト ===")
    if test_voicevox_connection():
        print("\n=== 音声生成テスト ===")
        test_voice_generation()