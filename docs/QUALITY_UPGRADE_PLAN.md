# マイカブ クオリティアップ Plan（正本）

最終更新: 2026-08-24  
ブランチ: `feature/update`  
関連: `docs/QUALITY_UPGRADE_HANDOFF.md`（引き継ぎ用・短い版）

## ゴール

初心者向け株ニュース動画を、**情報として有用**かつ**見たくなるエンタメ**にする。  
見た目は Studio Soft。説明はできるだけ**文字より図解**。

## 方針（凍結）

| 項目 | 決定 |
|---|---|
| コンセプト | やさしいのにちょっと尖ってる株ニュース |
| キャラ設定 | みのり（解説）× カリン（飛びつき）※立ち絵は仮置き／最終は VOICEVOX公式寄りも検討中→**保留** |
| 声 | `characters.json` の speaker_id で差し替え可能（カリン当面ずんだもん） |
| UI | Studio Soft。枠押し込み禁止。ブリッジ単色ベタ禁止 |
| ニュース | 鮮度→旬→波及。束→影響→明日 |
| 空セクション | 無言スキップ |
| キャラ以外 | **どんどん進める** |

## フェーズと進捗

| ID | 内容 | 状態 | 次にやること |
|---|---|---|---|
| P1 | ニュース選定スコア | ✅ 完了 | メンテのみ |
| P2 | 台本ストーリー＋口調 | ✅ 完了 | dialogue 指示はスクリプトプロンプトに反映済 |
| P3a | ブリッジ／帯／テロップ素材 | ✅ 完了 | 気に入らなければ微調整 |
| P3b | **本文UIを図解寄りに** | ✅ 完了 | news_bundle / impact_flow / market_board / capital_flow。台本は diagrams.*_path を target_files 指定 |
| P4 | 決算見直し | ✅ 完了 | — |
| P5 | 二人掛け合い（声切替） | ✅ 完了 | opening/heat/closing で dialogue。pipeline が speaker 別 VOICEVOX。composer が仮立ち絵切替 |
| P6 | 資金循環／地合いボード | ✅ 完了 | aggregator が diagrams に結線。プレビューは `scripts/preview_diagrams.py` |
| P7 | 情報量アップ | 後回し | — |
| — | Watchflow反映 | ✅ | lane/scope/polarity、issuer軽いガード、夜 attention 薄め |

## 今すぐの優先順

1. （任意）本番パイプラインでの本編フル生成確認（lane/scope・夜の重複減）  
2. 必要なら Studio Soft 微調整  
3. P7 は後回し  

## 実装メモ（完了条件との対応）

- **図解UIが immersive で機能する**: `data_aggregator` → `diagrams` → 台本 `target_files` → composer が画像表示。キーは `news_bundle_path` / `impact_flow_path` / `market_board_path` / `capital_flow_path`。  
- **掛け合いが動く**: `dialogue` → `expand_scene_speech_units` → `generate_and_save(..., speaker=id)`。声IDは `characters.json` のみで差し替え。立ち絵は仮（`karin_*.png`）。  
- 単体: `python test_dialogue_util.py` / `python test_news_selector.py`  
- **検証済みスモーク**: `PYTHONPATH=. python scripts/smoke_dialogue_diagram.py`  
  - 出力: `output/quality_smoke/smoke_dialogue_diagram.mp4`  
  - 確認内容: 地合いボード／ニュース地図／影響フロー表示、みのり(2)↔カリン(3)の声切替  

## クラウドエージェントで続きをやるとき

1. ローカル変更を **commit → push**（GitHub の `feature/update`）  
2. Cloud Agent 起動  
3. プロンプト例:

```
docs/QUALITY_UPGRADE_PLAN.md と docs/QUALITY_UPGRADE_HANDOFF.md を読んで、
「今すぐの優先順」の先頭から実装を続けて。
キャラ立ち絵の作り込みはしない（仮置きのまま）。
characters.json の声差し替え設計は壊さない。
作業後は両方の docs の進捗表を更新すること。
```

4. Canvas（IDE横）は Cloud から見えない → **この PLAN / HANDOFF が正本**

## 完了の定義

- immersive 本編で図解UIが実際に出る  
- 二人掛け合いがフック／主役／締めで動く（声ID差し替え可）  
- HANDOFF の進捗表が最新
