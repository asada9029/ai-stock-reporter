import sys

def run_all_tests():
    """全テストを実行"""
    
    tests = [
        ("VOICEVOX接続", "test_voicevox.py"),
        ("Gemini API", "test_gemini.py"),
        ("データ収集", "test_data_collection.py")
    ]
    
    results = []
    
    for test_name, test_file in tests:
        print(f"\n{'='*50}")
        print(f"テスト: {test_name}")
        print(f"{'='*50}")
        
        try:
            exec(open(test_file).read())
            results.append((test_name, "✅ 成功"))
        except Exception as e:
            results.append((test_name, f"❌ 失敗: {e}"))
    
    # 結果サマリー
    print(f"\n{'='*50}")
    print("テスト結果サマリー")
    print(f"{'='*50}")
    
    for test_name, result in results:
        print(f"{test_name}: {result}")

if __name__ == "__main__":
    run_all_tests()
