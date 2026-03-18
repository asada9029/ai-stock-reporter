# 📈 AI Stock Reporter

AIによる自動株式ニュース解説動画生成・投稿システムです。
毎日2回（朝・夜）、最新の市場データを収集し、分析・台本生成・音声合成・動画作成・YouTube投稿までを完全自動で行います。

## 🌟 主な特徴

- **🤖 高度な市場分析**: LLM を使用し、複雑な市場動向を初心者にもわかりやすく解説。
- **🌅 1日2回のレポート**:
  - **モーニングレポート**: 米国市場の結果と、それが今日の日本市場に与える影響を分析。
  - **イブニングレポート**: 日本市場の終値まとめ、注目セクター、個別銘柄の動向を詳しく解説。
- **🎤 自然な音声合成**: VOICEVOX（株野みのり：四国めたん）による親しみやすいナレーション。
- **📊 視覚的な動画構成**: 指数チャート、業種別騰落ランキング、個別銘柄チャートを自動生成・挿入。
- **🚀 完全自動パイプライン**: データ収集からYouTube投稿まで、人の手を介さずに実行可能。

## 📂 リポジトリ構成

```text
ai-stock-reporter/
├── src/
│   ├── data_collection/    # 市場データ、ニュース、チャート画像の取得
│   ├── analysis/           # Geminiによる分析、台本（シーンJSON）の生成
│   ├── voice_generation/   # VOICEVOX APIを使用した音声合成
│   ├── video_generation/   # MoviePyによる動画合成、サムネイル生成
│   ├── upload/             # YouTube Data APIによる動画投稿
│   ├── config/             # 動画構成や定数定義
│   └── utils/              # 共通ユーティリティ
├── data/                   # 生成された音声、台本、一時データの保存
├── output/                 # 最終的な動画ファイル、サムネイルの出力
├── main.py # メイン実行スクリプト
├── requirements.txt        # 依存ライブラリ一覧
└── .env                    # APIキーなどの環境変数（要作成）
```

## 🛠 セットアップ

### 1. プリリクエスト
- Python 3.10以上
- [VOICEVOX](https://voicevox.hiroshiba.jp/) デスクトップ版またはDocker版（実行時に起動している必要があります）
- Google Cloud Project (Gemini API & YouTube Data API)

### 2. インストール
```bash
git clone https://github.com/yourusername/ai-stock-reporter.git
cd ai-stock-reporter
pip install -r requirements.txt
```

### 3. 環境設定
`.env` ファイルを作成し、以下の情報を設定してください。
```env
GEMINI_API_KEY=your_gemini_api_key
YOUTUBE_API_KEY=your_youtube_api_key
# その他必要な環境変数
```

## 🚀 実行手順

### 通常の実行（データ収集〜動画生成）

朝動画（モーニングレポート）を生成する場合：
```bash
python run_combined_pipeline.py --type morning_video
```

夜動画（イブニングレポート）を生成する場合：
```bash
python run_combined_pipeline.py --type evening_video
```

### テスト実行
動画レンダリングを行わずに、台本の長さ（尺）を確認する場合：
```bash
python test_morning_audio_duration.py
```
※ `test_morning_audio_duration.py` 内の `target_type` を書き換えることで朝夜両方のテストが可能です。

## 📝 ライセンス
このプロジェクトのライセンスについては、[LICENSE](LICENSE)ファイルを参照してください。

## 🤝 貢献
バグ報告や機能改善の提案は、IssueまたはPull Requestにて受け付けています。
