# マイカブ クオリティアップ — 引き継ぎメモ

最終更新: 2026-08-25  
ブランチ: `feature/update`  
正本Plan: `docs/QUALITY_UPGRADE_PLAN.md`

## これは何か

Cloud Agent / 別セッションが **迷わず続きをやるための短い引き継ぎ**。  
詳細なフェーズ管理は PLAN を見る。

## 進捗（要約）

| ID | 項目 | 状態 |
|---|---|---|
| P1 | ニュース選定 | ✅ |
| P2 | 台本ストーリー | ✅ |
| P3a | ブリッジ・帯・テロップ素材 | ✅ |
| P3b | 本文図解UI | ✅ news地図・影響フロー・地合いボード・資金循環 |
| P4 | 決算見直し | ✅ |
| P5 | 二人掛け合い | ✅ speaker/dialogue + VOICEVOX切替 + 仮立ち絵切替 |
| P6 | 資金循環・地合いボード | ✅ `market_board` / `capital_flow` 生成・aggregator結線 |
| P7 | 情報量アップ | 後回し |
| — | Watchflow反映（lane/scope・夜attention薄め） | ✅ 2026-08-25 |

## いまやること

1. 本番パイプラインで朝 or 夜を1本回して、lane/scope と夜の attention 薄めを目視確認  
2. Cloud で続きなら **commit + push**  
3. 回帰スモーク: `PYTHONPATH=. python scripts/smoke_dialogue_diagram.py`  

## 変えないこと

- Studio Soft のトーン  
- キャラ人格（みのり／カリン）※絵柄最終決定は保留  
- ニュース重み: 鮮度→旬→波及  
- 空データは無言スキップ  
- `characters.json` の声ID差し替え設計  

## Cloud 引き継ぎ手順

1. `git status` で未コミットを確認 → **commit + push 必須**（Cloud は GitHub を見る）  
2. Agent に渡す一文:

> `docs/QUALITY_UPGRADE_PLAN.md` を正本に、未完了の先頭フェーズから実装。終わったら PLAN とこの HANDOFF の進捗を更新。

3. `.env` は push しない  

## 主なコード位置

- 選定: `src/analysis/news_selector.py`  
- 掛け合い: `src/analysis/dialogue_util.py` / `structured_pipeline.py`（VOICEVOX speaker）  
- 図解生成: `src/video_generation/diagram_generator.py`  
- UIトークン: `src/config/studio_soft.py`  
- キャラ声・仮絵: `src/config/characters.json`  
- 合成: `src/video_generation/structured_video_composer.py`  
- 台本: `src/analysis/script_generator.py`  
- 検証: `test_dialogue_util.py` / `scripts/preview_diagrams.py`  
