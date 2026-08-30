# マイカブ 本編動画 内容仕様（朝／夜）

最終更新: 2026-08-25  
対象: 他エージェントへの引き継ぎ。横型本編（朝・夜）の**動画内容**を、構成・情報粒度・キャラ・LLM指示まで含めて記述する。  
ショート（`shorts_a` / `shorts_b`）は末尾に概要のみ。

## 正本ファイル

| 役割 | パス |
|---|---|
| セクション構成・枠尺 | `src/config/video_structure.json` |
| 尺ポリシー | `src/config/video_duration.py` |
| キャラ・声 | `src/config/characters.json` |
| 台本LLMプロンプト | `src/analysis/script_generator.py` |
| ニュース選定 | `src/analysis/news_selector.py` |
| データ集約 | `src/data_collection/data_aggregator.py` |
| ニュース収集クエリ | `src/data_collection/market_data_collector.py` |
| シーンスキーマ | `src/analysis/scene_schema.py` |
| 図解生成 | `src/video_generation/diagram_generator.py` |
| 演出モード | `src/config/presentation.py` |

---

## 1. 番組の骨格

- 番組名: **マイカブ**
- コンセプト: **やさしいのにちょっと尖ってる株ニュース**
- 視聴者: 投資初心者。中学生でも分かる噛み砕き。ただし数値・社名・因果は具体的に出す
- UI: Studio Soft。枠の押し込み禁止。ブリッジの単色ベタ禁止
- 説明: 文字の羅列より図解優先
- 形式: 横型本編 1920×1080。目標尺 **20分（1200秒）**
- 公開最低ライン（品質チェック）: 推定尺 300秒（5分）、シーン数 12以上、speech 文字数は 300秒×3.5字/秒×0.72 から逆算
- 実測は目標より短くなりがち（lite モデルで 7〜8 分前後でも通す設計）

### 配信タイミング

- 朝: 案内上 **7時**。対象は NYSE 前営業日（土曜朝・日曜朝は出さない。月曜朝は金曜の米国結果。月曜はニュース窓 72h）
- 夜: 案内上 **18時**。対象は当日の JPX 営業日
- 休場ギャップがあれば closing で次回日時を言う（台本側 `next_delivery_info.is_holiday_gap`。実データは `main.py` が `next_delivery_info` を付与）

### YouTube（簡易タイトル）

- 朝: `【朝刊】米国株市場まとめ YYYY/MM/DD` / 「昨晩の米国株市場の動きをAIがサクッと解説します。」
- 夜: `【夕刊】日本株市場まとめ YYYY/MM/DD` / 「本日の日本株市場の動きをAIがサクッと解説します。」

### 演出モード

`main.py` の `--presentation classic|immersive`。横型本編のみ immersive 可。ショートは常に classic。

- **classic（デフォルト）**: 画面は `■事実` + `└考察`。画像ありシーンは最大4行（2セット）
- **immersive**: 聞く優先。on_screen は原則2行（1行目=事実・数値、2行目=見解）。1行のみ禁止。opening は最大3行ラベル。メニュー8行禁止

---

## 2. キャラクター

正本: `src/config/characters.json`。声IDの差し替えはここだけ。人格は凍結。立ち絵の最終決定は保留（カリンは仮置き `karin_*.png`）。

| ID | 表示名 | 役割 | 口調 | VOICEVOX |
|---|---|---|---|---|
| `minori` | 株野みのり | ホスト / 解説 | 敬語。やさしいが芯が硬い。根拠のない強気はスルーし、短く断定して締める | 四国めたん ノーマル（speaker_id=2） |
| `karin` | 相場カリン | パートナー / 飛びつき | タメ口寄り。好奇心暴走の後輩。視聴者代弁で早とちりし、旬・急騰落に飛びつく。みのりに止められるのが定番 | 春日部つむぎ ノーマル（speaker_id=8） |

### LLMに渡しているキャラ指示（原文に近い）

```
# キャラクター設定（番組の顔）
- 株野みのり（ホスト / speaker=`minori`）: 敬語。やさしいが芯が硬い。根拠のない強気はスルーし、短く断定して締める。
- 相場カリン（パートナー / speaker=`karin`）: タメ口寄り。好奇心暴走の後輩。視聴者代弁で早とちりし、旬・急騰落に飛びつく。みのりに止められるのが定番。
※「やさしいのにちょっと尖ってる」トーン。まじめニュース番組にしない。ほのぼのたとえを適宜入れる。

# 二人掛け合い（重要）
- 通常の解説シーンは `speaker: "minori"` の一人語りでよい。
- **opening（フック）・旬ニュース（slot=heat）・closing（締め）** では掛け合いを入れる。
- 掛け合いシーンは `dialogue` 配列を必ず付ける:
  [{"speaker":"minori","text":"...","speech_text":"..."},{"speaker":"karin","text":"...","speech_text":"..."}]
- `text` / `speech_text` は dialogue を連結した全文でもよい（字幕用）。話者切替は dialogue が正。
- 全編二人にはしない。情報ブロックはみのり主導、感情ブロックだけカリンを出す。
```

パイプラインは `dialogue` を読み上げ単位に展開し、speaker ごとに VOICEVOX ID を切り替える。カリンの仮立ち絵は emotion（normal / happy / excited）で切替。

### 感情

許可値（シーンJSON）: `normal`, `happy`, `surprised`, `sad`, `confident`, `angry`, `disappointed`, `excited`

- 中立の説明・数値読み・つなぎは `normal` でよい
- 好調・上昇・好材料 → `happy` / `excited`
- 下落・懸念・失望 → `sad` / `disappointed`
- 想定外 → `surprised`
- 強い批判 → `angry`
- 見通しの断定 → `confident`
- 全体を `normal` だけにしない
- speech が2句以上、または1シーン内でトーンが変わるときは `emotion_timeline`（`segment_index` + `emotion`）。秒数は音声長からシステムが計算。LLMが省略した場合はキーワードから補完

---

## 3. ニュース選定（情報粒度の上流）

優先順: **鮮度 → 旬(Heat) → 波及(Impact) → 行動(Action) → 新規性(Novelty)**

加重（合計 1.0）:

| 軸 | 重み |
|---|---|
| freshness | 0.35 |
| heat | 0.25 |
| impact | 0.20 |
| action | 0.12 |
| novelty | 0.08 |

### レーンとスコープ（Watchflow反映・動画向け）

収集は Impact / Heat の2クエリのまま。役割を固定する。

| クエリ | 取るもの | 載せないもの |
|---|---|---|
| Impact（大局） | 指数・金利・為替・複数セクター・地政学 | 個別決算・1社IRを本命にしない |
| Heat（局所／旬） | 急騰落・サプライズ・個別材料 | 地合い説明の代替にしない |

選定後に各ニュースへ付与:

| キー | 値 | 扱い |
|---|---|---|
| `lane` | `macro` / `local` | honmei は macro 優先、heat は local 優先 |
| `scope` | `issuer` / `theme` / `unclear` | issuer は関連チャート・言及をその1社だけ（同業に広げない） |
| `polarity` | `pos` / `neg` / `mixed` | 表示・口調の補助 |

軽いガード: `lane=macro` でタイトルに当事者が無い個別ティッカーは外す。`scope=issuer` で本文に出てこないティッカーは信頼しない。

注目銘柄の紹介自体は歓迎。買い／売れの推奨口調にする必要はない（現行どおりチェック／注目でよい）。

### 候補収集（各8件、Impact + Heat）

朝は米国、夜は日本。通常窓 **12h**（取れなければ 24h）。月曜朝は **72h**。

**朝 Impact クエリ（要旨）**  
過去12h（月曜72h）で、米国株全体に波及しそうな経済・政治・国際・技術ニュースを8個。指数・金利・為替・複数セクターに効く本命。日本の投資家に馴染みのある大手・景気。財布に直結する話。

**朝 Heat クエリ（要旨）**  
同時間窓で、いま話題の米国株・急騰急落・サプライズ決算・半導体/AIを8個。鮮度最優先。時価総額が小さくても成長・テーマなら可。

**夜 Impact / Heat**  
対象を日本市場に置き換え。円安円高、大手決算、経済対策、半導体、ストップ高安、材料株など。

各ニュースの粒度: `title`, `url`, `snippet`, `source`, `published_at`, `related_ticker`, `related_company_name`。後段で `slot` / `scores` / 任意の visual を付与。

### 枠（最大8件）

| slot | 枠 | 扱い |
|---|---|---|
| `honmei` | 本命 1 | **lane=macro 優先**。鮮度を確保しつつ impact×total |
| `heat` | 旬 1〜2 | **lane=local 優先**。急騰落・サプライズ。カリンが飛びつく枠 |
| `rotation` | 資金循環 0〜1 | 資金の行き先・違和感（キーワード＋可能ならフロー図） |
| `support` | 残り | 補助 |

Novelty は直近動画トピック（最大40件）との重複で減点。半導体／円安／NVIDIA などはマンネリしやすい語として減点補助。任意で LLM が impact/heat/action を 0–100 で再採点し、ルールと 45:55 で混ぜる。

### 台本での物語の流れ（並列紹介禁止）

**束ねて紹介 → まとめて影響の読み → 明日（または今日）の立ち回り**

同じ話題の重複解説は禁止。空セクションは**無言スキップ**（「予定はありません」等は言わない）。例外: `attention_news` が空のときだけ「ニュースが取得できませんでした」。実装上、収集0件なら動画生成自体を中止する。

---

## 4. 図解（本文UI）

パスがあるときは該当シーンの `target_files` に必ず指定。on_screen は図の補足を最大2行。

| キー（台本プロンプト側） | 図 | 使う場所 |
|---|---|---|
| `diagrams.news_bundle_path` | 今日のニュース地図（本命／話題／資金／補足、最大5本） | ニュース導入 |
| `diagrams.impact_flow_path` | どう効く？ 影響の流れ（ニュース→市場/セクター→日本株 or 明日） | 影響の読み |
| `diagrams.market_board_path` | 今日の地合いボード | 指数セクション冒頭 |
| `diagrams.capital_flow_path` | 資金の行き先（上昇上位4／下落下位4のざっくり） | セクター概要・rotation |

個別ニュースの OG 画像は必須ではない（ズレることがある）。図解優先。関連銘柄があれば `related_ticker` / `related_company_name`。チャートがあれば補助。

---

## 5. 朝動画（`morning_video`）

**主題:** 昨晩の米国市場 → 今日の日本市場がどう動くか。

目標尺 1200 秒。セクション順は固定。

| name | 画面タイトル | 枠秒 | 全体比 | 厚み |
|---|---|---|---|---|
| opening | 本日のトピック | 50 | 4% | 簡潔 |
| us_market_summary | 米国市場指数 | 225 | 19% | 厚め |
| us_news_highlights | 米国注目ニュース | 300 | 25% | 最厚 |
| us_sector_analysis | 米国セクター分析 | 275 | 23% | 厚め |
| japan_impact_prediction | 日本市場への影響予測 | 300 | 25% | 最厚 |
| closing | まとめ | 50 | 4% | 簡潔 |

opening はシーン分割なしの1シーン。指数は指数ごとに独立シーン。画像2枚以上は左右並列のみ（上下禁止）。

### 5.1 渡しているデータ（朝）

台本プロンプトが参照するキー（aggregator 側の実キー名は §9 を参照）:

- `market_indices`: `"DOW"`, `"NASDAQ"`, `"S&P500"`。各 `name`, `current_price`, `change_percent`, `chart_image_path`
- `attention_news`: 選定済み最大8本。`title`, `snippet`, `slot`, `scores`, `visual_image_path`, `visual_source` (`og`/`chart`), `related_ticker`, `related_company_name`
- `sector_analysis.rankings_screenshot`: 米国業種ランキング表
- `sector_analysis.sectors`: 上位2＋下位2。各 `sector_name`, `type` (`top`/`bottom`), `change`, `news[]`（各セクター最大3件、`title`+`summary`）。月曜は72h、平日は24h
- `jp_tomorrow_outlook`: 最大5本。`title` + `summary`（米国→日本の波及、為替、取引戦略）
- `next_delivery_info`: `date`, `time`, `is_holiday_gap`
- `diagrams.*`: 上記図解パス
- `selected_thumbnail_title`: サムネ用の本命見出し（opening 案内に埋め込む）

実キャプチャ: 朝の指数は SP500 / DOW / NASDAQ。ドル円は朝では出さない。

### 5.2 セクション別LLM指示（朝）

1. **opening**  
   挨拶「おはようございます！」の直後、今日の一言結論か違和感（例: 資金の行き先）を短く示し、「まずは市場指数、その次に（サムネイル：{selected_thumbnail_title}）」と案内。後半メニュー（米国セクター分析、日本市場への影響予測）も触れる。  
   classic の on_screen（1行ずつ）:
   - ・米国市場の動向
   - ・米国注目ニュース：{サムネ12字}...
   - ・米国セクター分析
   - ・日本市場への影響予測
   - ・まとめ  
   immersive ではメニュー8行禁止。3行ラベル例: `米国: 小幅安` / `注目: …` / `日本: 影響は○`。挨拶直後20〜40秒で結論と最大材料を言い切る。

2. **us_market_summary**  
   可能なら先に `diagrams.market_board_path`。その後 S&P500、ナスダック、ダウをそれぞれ独立シーン。各 `chart_image_path` を見せ、終値・前日比・変動原因を分析。

3. **us_news_highlights**  
   `attention_news` は選定済み。slot を尊重。  
   1. `diagrams.news_bundle_path` を全画面で見せ、honmei と主な heat を短く束ねて紹介  
   2. `diagrams.impact_flow_path` で「これらの材料が市場・セクターにどう効くか」を1〜2シーン  
   3. rotation / `diagrams.capital_flow_path` があれば資金の行き先・違和感  
   heat 枠はカリンとの掛け合い推奨。図解優先。個別 visual は補助。OGは無理に使わない。

4. **us_sector_analysis**  
   `diagrams.capital_flow_path` があれば先に見せ、続けてランキングスクショ。上昇・下落が顕著なセクターを紹介したあと、そのセクターの `news` を on_screen で表示し騰落原因を分析。理由不明なら市場心理（利益確定、材料待ち等）を推測。

5. **japan_impact_prediction**  
   `jp_tomorrow_outlook` と直前のニュース束を踏まえ、米国→日本の影響を予測。最後に「今日見るべきチェック3点」。注目日本株の対応関係（例: NVIDIA高→東エレク）、為替。

6. **closing**  
   掛け合いで締め。まとめと次回予告。`is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です」。False なら「夜18時のイブニングレポートもお楽しみに！」

タイトル形式: opening 以外は「セクション名：具体的な内容」。セクション日本語名は上表どおり。分割時はセクション名を分けてよい。

---

## 6. 夜動画（`evening_video`）

**主題:** 本日の日本市場の振り返り → 今夜の米国と明日の立ち回り。

| name | 画面タイトル | 枠秒 | 全体比 | 厚み |
|---|---|---|---|---|
| opening | 本日のトピック | 44 | 4% | 簡潔 |
| market_indices | 主要市場指数 | 156 | 13% | 中 |
| news_highlights | 注目ニュース | 178 | 15% | 中〜厚（局所中心） |
| event_calendar | 注目決算スケジュール | 89 | 7% | 簡潔／任意 |
| sector_overview | セクター概要 | 280 | 23% | **厚め（夜の核）** |
| sector_attention | 注目セクター | 100 | 8% | **任意・薄め**（材料銘柄1〜2のみ） |
| prev_ir_tracking | 前回紹介銘柄の追跡 | 176 | 15% | 任意 |
| tomorrow_strategy | 今夜の米国市場と明日の展望 | 133 | 11% | 中 |
| closing | まとめ | 44 | 4% | 簡潔 |

品質チェック上、`event_calendar` は決算データが空なら対象外。`prev_ir_tracking` と `sector_attention` は常に任意（省略しても品質NGにしない）。

### 夜の役割分担（重複防止）

- **news_highlights:** 今日の材料（誰が・何が・効き方）。局所を厚く、大局は短く主語として残す
- **sector_overview:** お金がどこへ（ランキング＋資金図）。ここを厚く
- **sector_attention:** 材料で動いた銘柄だけ。代表銘柄の百科事典にしない。重複なら省略可

### 6.1 渡しているデータ（夜）

台本プロンプトが参照するキー（aggregator 側の実キー名は §9 を参照）:

- `market_indices`: `"NIKKEI"`, `"SP500"`。各 `name`, `current_price`, `change_percent`, `chart_image_path`
- `attention_news`: 朝と同じ構造（日本市場ニュース、slot付き最大8本）
- `sector_analysis.rankings_screenshot`: 東証33業種ランキング表
- `sector_analysis.sectors`: 上位2＋下位2。各セクター代表企業 **2社**。社ごと `company_name`, `ticker`, `news`（過去12h・最大3件 title+summary）, `chart_image_path`
- `kessan_schedule`: 注目決算のみ。3日先まで収集 → LLMが最大16件厳選（話題・テーマ優先、時価総額は補助）→ 8件×最大2ページの表画像。`data` / `image_path` / `image_paths` / `page_count`。空ならセクション自体を作らない
- `soukai_schedule`: 使わない（株主総会は扱わない）。空で渡す
- `prev_ir_analysis`: 前回紹介銘柄。`company_name`, `change_percent`, `recent_news`, `reason_summary`, `chart_image_path`。空なら無言スキップ
- `us_tonight_outlook`: 今夜の米国市場の見通し 最大5本。visual がある場合あり
- `next_delivery_info`, `diagrams.*`, `selected_thumbnail_title`

実キャプチャ: 夜の指数は NIKKEI → SP500 の順。ドル円は台本指示ではシーン化するが、一括キャプチャの夜ループには入っていない（定義はある）。

### 6.2 セクション別LLM指示（夜）

1. **opening**  
   「お疲れ様です」の直後、今日の一言結論か違和感。「まずは市場指数、その次に（サムネイル：…）」。後半メニューも触れる。  
   classic の on_screen:
   - ・市場の動向
   - ・注目ニュース：{サムネ12字}...
   - ・注目決算スケジュール
   - ・セクター分析
   - ・注目銘柄のIR
   - ・前回紹介銘柄の動向
   - ・今夜の米国市場と明日の展望
   - ・まとめ  
   シーン分割なし。

2. **market_indices**  
   可能なら先に `diagrams.market_board_path`。日経平均を先に、次に S&P500。各チャートで終値・前日比・変動原因。最後にドル円の動きとその影響。

3. **news_highlights**  
   「束ねて紹介 → 影響の読み」。局所を厚く、honmei（macro）は短く主語。slot / lane / scope を尊重。`scope=issuer` は1社だけ。heat は掛け合い推奨。

4. **event_calendar**  
   決算のみ。`kessan_schedule.image_paths`（なければ `image_path`）を最大2ページ、ページごとにシーン化。株主総会は扱わない。`data` が空または画像が無い場合は**シーンを一切作らず次へ無言**（「予定はありません」等は言わない）。

5. **sector_overview**  
   **夜の核。** `diagrams.capital_flow_path` があれば先に見せ、続けてランキングスクショ。上昇・下落が顕著だったセクターを具体名で挙げ、「なぜ」を短く。ニュースとの重複禁止。

6. **sector_attention**  
   **任意・薄め。** overview／ニュースと重複するなら省略可。残すなら材料で動いた銘柄を最大1〜2本だけ。代表企業の百科事典は禁止。

7. **prev_ir_tracking**  
   銘柄ごとにシーン。チャート・騰落・直近ニュースを on_screen で見せ、`reason_summary` を説明。データがなければ無言スキップ。

8. **tomorrow_strategy**  
   `us_tonight_outlook` と本日のニュース束を踏まえ、明日の注目／注意（チェック3点）で締める。visual があれば `target_files` に含める。

9. **closing**  
   掛け合い。`is_holiday_gap` が True なら次回日時。False なら「明日朝7時のモーニングレポートもお楽しみに！」

タイトル形式: opening 以外は「セクション名：具体的な内容」。分割例: 「今夜の米国市場」と「明日の展望」。

---

## 7. 台本LLMへの共通指示（朝夜とも）

役割: 「マイカブの動画ディレクター兼台本作家」。出力は**純粋なJSON配列のみ**。

### 尺

- 目標 **20分（1200秒）** の読み上げ量
- セクション duration が大きいほどシーン数・speech を厚く。opening / closing は簡潔、ニュース・セクター・展望を厚め
- 品質不足なら最大3回やり直し。最低 300秒・12シーン・speech 文字数下限。欠落セクションがあればプロンプト末尾に追記して作り直し

### 全般ルール

- 1シーンに詰め込みすぎない。画像ありシーンの on_screen は最大4行（2セット）。それ以上はシーン分割（画像なしは4行超可）
- 画像とテキスト同時表示は、画像がメイン・テキストが補足
- 捏造厳禁。分析データにある数値・社名・ニュースのみ
- 専門用語は初心者にも簡潔に解説

### 鉄則11項（原文に近い）

1. **徹底的な初心者目線**: 用語解説にとどまらず、「生活や投資にどう影響するか」を中学生でも分かるレベルで。背景のストーリーを重視
2. **情報の相関分析**: 「米国の金利が上がったから、日本のハイテク株が売られた」のように、為替×市場・米国×日本などの因果を1つ以上
3. **読み上げと表示の分離**: `text` は英語表記のまま（NVIDIA, S&P500）。`speech_text` だけカタカナ（エヌビディア、エスアンドピー500）。`on_screen_text` は英語可
4. **正確な高値表現**: 安易に「最高値」と言わない。史上最高のときのみ「史上最高値」。それ以外は年初来／〇ヶ月ぶり／バブル後など、データ根拠のある期間
5. **誠実なぼかし**: 「謎」にせず、「材料待ちで様子見」「過熱感から利益確定の売り」など市場心理を推測
6. **具体性**: 「ある企業が」ではなく「トヨタ自動車が」「NVIDIAが」と実名
7. **数値**: 「大きく動いた」ではなく「300円安の〇〇円」。`38,567.23円` は「3万8500円付近」や「3万8560円」のように耳で分かる丸め
8. **感情**: 上記 emotion ルール。timeline は句インデックス指定
9. **行動指針**: 朝は「今日はまず〇〇をチェック」、夜は「明日の朝はまず〇〇をチェック」
10. **データ不足**: 空なら該当シーンを作らず次へ（無言スキップ）。`attention_news` が空の場合のみ「ニュースが取得できませんでした」
11. **自然な文章**: 一文 40〜80字程度。意味の区切りで自然に読める

### immersive 追記（有効時）

- on_screen の `■` `└` は禁止。必ず2行（最大3行）。1行のみ禁止
- 1行目=事実・数値、2行目=見解。目安 全角18〜22文字。composer 側で20文字折り返し
- OG必須ではない。関連銘柄があれば `related_ticker` / `related_company_name` を必ず設定

---

## 8. シーンJSONスキーマ

バリデーション必須: `scene`（1始まりの整数）, `duration`, `text`, `emotion`, `image_type`  
LLMにはさらに次の出力を促す:

| キー | 内容 |
|---|---|
| `section_title` | 短いタイトル |
| `speech_text` | 読み上げ専用（英字はカタカナ） |
| `on_screen_text` | 文字列配列。classic は `■事実` + `└考察` |
| `speaker` | `"minori"` または `"karin"`（一人語り時） |
| `dialogue` | 掛け合い配列。各要素に `speaker` / `text` / `speech_text` |
| `emotion_timeline` | `[{"segment_index":0,"emotion":"happy"}, ...]`。代替 `segment_emotions` |
| `two_image_layout` | 2枚時のみ。`"horizontal"`（左右）。`"vertical"` は禁止 |
| `bg_name` | 基本 `"bg_illust.png"` |
| `target_files` | 画像パス配列。1枚でも `["path"]` |
| `related_ticker` / `related_company_name` | ニュース画面用（任意だが推奨） |

`image_type`: `chart`, `character_only`, `bg_only`, `news_panel`, `chart_with_annotation`

パイプライン末尾でチャンネル登録シーンを強制追加する（台本 closing では登録訴求を重複させない想定）。朝の登録後テキストは「今日も一日頑張りましょう」、夜は「また明日」。

---

## 9. データキーの実装差分（コードを触るとき）

台本プロンプトが読む名前と、aggregator が書く名前がずれている。

| 意味 | 台本プロンプトが読む名前 | aggregator / main が書くキー |
|---|---|---|
| 指数 | `market_indices` | `market_indices` |
| 注目ニュース | `attention_news` | `attention_news` |
| セクター | `sector_analysis` | `sector_analysis` |
| 日本への波及（朝） | `jp_tomorrow_outlook` | `jp_tomorrow_outlook` |
| 決算（夜） | `kessan_schedule` | `kessan_schedule` |
| 前回IR（夜） | `prev_ir_analysis` | `prev_ir_analysis` |
| 今夜の米国（夜） | `us_tonight_outlook` | `us_tonight_outlook` |
| 図解 | `diagrams` | `diagrams` |
| 次回配信 | `next_delivery_info` | `main.py` が `next_delivery_info` を付与 |

### 9.1 入力データ（analysis_data）のイメージ

エージェントが受け取るニュースデータの例：

```json
{
  "attention_news": [
    {
      "title": "米長期金利が急低下、ハイテク株に買い",
      "snippet": "経済指標の軟化を受けて金利が低下し、ナスダックが反発しました。",
      "slot": "honmei",
      "scores": {"total": 0.85, "impact": 0.9, "heat": 0.4},
      "visual_image_path": "output/collected/news_visuals/morning/news_0.png"
    }
  ],
  "diagrams": {
    "news_bundle_path": "output/collected/diagrams/morning/news_bundle.png",
    "impact_flow_path": "output/collected/diagrams/morning/impact_flow.png"
  }
}
```

品質チェック（`script_quality.py`）は台本側のキー名を見る。コード変更時は両方を確認すること。

夜のドル円シーンは台本指示にあるが、指数キャプチャの夜ループは日経＋S&P中心。

---

## 10. 変えないこと（凍結）

- Studio Soft のトーン
- キャラ人格（みのり／カリン）。立ち絵の作り込みはしない
- ニュース重み: 鮮度 → 旬 → 波及
- 空セクションは無言スキップ
- `characters.json` の声ID差し替え設計
- 株主総会は扱わない

情報量アップ（P7）は後回し。見た目の微調整以外の本編仕様は本ドキュメントが現行。

---

## 11. ショート（参考）

本編とは別。各60秒。縦型。タイトル表示・字幕セグメントなし。on_screen のみ。結びでチャンネル登録は言わない（後段で自動追加）。

- **shorts_a**: 本日のマーケットに関連する株用語を1つ、初心者向けにやさしく解説。過去30件の用語は重複禁止
- **shorts_b**: チャートが動いている注目銘柄を1つ深掘り

speech 合計 200〜240字程度。絶対に60秒以内。
