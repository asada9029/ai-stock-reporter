"""
台本生成エンジン
動画構成から実際の読み上げ台本を生成
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import re

from src.analysis.scene_schema import validate_scene_list, ALLOWED_EMOTIONS, ALLOWED_IMAGE_TYPES

from src.analysis.gemini_client import GeminiClient
from src.config.presentation import is_immersive_mode, normalize_presentation_mode


class ScriptGenerator:
    """台本生成クラス"""
    
    # 読み上げ速度の目安（文字/秒）
    CHARS_PER_SECOND = 3.5  # 少しゆっくりめに設定
    
    # 間の長さ（秒）
    PAUSE_SHORT = 0.5
    PAUSE_MEDIUM = 1.0
    PAUSE_LONG = 2.0
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """
        初期化
        
        Args:
            gemini_client: GeminiClientインスタンス
        """
        self.client = gemini_client or GeminiClient(
            # model_name=GeminiClient.MODEL_TEST,
            enable_search=False  # 台本生成では検索不要
        )
        
        print("[OK] ScriptGenerator 初期化完了")

    @staticmethod
    def _immersive_prompt_appendix(analysis_data: Dict) -> str:
        """classic プロンプトの on_screen / opening 指示を上書きする追記ブロック。"""
        thumb = analysis_data.get("selected_thumbnail_title", "本日の注目ニュース")
        return f"""

# 【immersive 演出モード：以下で on_screen_text / opening の指示をすべて上書き】
- 視聴者は「読む」より「聞く」ことを優先します。詳しい説明は speech_text（読み上げ）に書き、画面は補助ラベルに留めてください。
- on_screen_text は「■」「└」形式は禁止。1シーンあたり **必ず2行**（最大3行）。**1行のみは禁止**（opening の3行ラベルは除く）。
  - 1行目: 事実・数値・見出し（例: "S&P500 +0.3%", "日経 3万8500円台"）
  - 2行目: 見解・影響・注意点（例: "金利上昇がハイテクに重石", "円安で輸出株に追い風"）
- 各行は短めだが情報は2行で足す（目安：1行あたり全角18〜22文字以内。composer側で20文字で折り返し）。
- 良い例（2行セット）: ["S&P500 +0.3%", "小幅続伸も上値は重い"] / ["半導体 +4.2%", "AI需要で牽引"]
- 悪い例: 1行だけ、音声の長文をそのまま載せる、箇条書き8行。
- 【opening 上書き】:
    - 挨拶の直後、20〜40秒以内に「今日の米国市場の結論（一言）」と「最大の材料は何か」を speech_text で言い切ること。
    - その直後に「ではまず指数（または市場全体）から確認して、次にニュースを深掘りします」のように自然に次へ繋げてください。
    - opening の on_screen_text は最大3行。メニュー箇条書き8行は禁止。例:
        "米国: 小幅安"
        "注目: {thumb[:14]}..."
        "日本: 影響は○"
    - opening はシーン分割なしの1シーンでOK。
- 【シーン分割】1画面＝1メッセージ。情報が多いときはシーンを増やし、1シーンの on_screen_text を3行以内に保つ。
- speech_text / text / 数値の正確さ・読み上げカタカナ・初心者向けの深掘りは、classic と同じ基準を維持してください。

- 【注目ニュースの画面（重要）】OG画像は必須ではありません（内容とズレることがあるため）。ニュースの「何の話か」を画面で必ず明確にしてください。
  - 関連銘柄がある場合は、`related_ticker` / `related_company_name` を必ず設定してください（可能なら target_files に関連チャート）。
  - 関連銘柄チャートが無い場合でも、target_files を無理に埋めず、`related_ticker` / `related_company_name` を設定してティッカー/社名カードが出せるようにしてください。
  - 追加キー（任意）: `ticker`, `company_name`（関連銘柄と同じでOK）
"""

    def generate_structured_scenes(
        self,
        video_structure: Dict,
        analysis_data: Dict,
        enriched_data: Optional[Dict] = None,
        max_retries: int = 5,
        presentation_mode: str = "classic",
    ) -> List[Dict]:
        """
        LLMに台本＋演出指示（JSON配列）を生成させ、バリデーションして返す。
        """
        video_type = video_structure.get("video_type", "evening_video")
        is_morning = "morning" in video_type
        is_shorts = "shorts" in video_type

        # 動画タイプに応じてプロンプトを分岐
        if is_shorts:
            # ショート動画専用プロンプト
            shorts_type = "案A（やさしい株用語解説）" if "shorts_a" in video_type else "案B（注目銘柄）"
            
            # 案Bの場合、チャート画像がある銘柄を特定
            valid_companies = []
            if "shorts_b" in video_type:
                for sector in analysis_data.get("sector_analysis", {}).get("sectors", []):
                    for company in sector.get("companies", []):
                        if company.get("chart_image_path"):
                            valid_companies.append(company)
            
            # 過去解説用語履歴の取得（shorts_aのみ）
            history_file = Path("data/shorts_term_history.json")
            recent_terms = []
            if "shorts_a" in video_type:
                recent_terms = self._get_recent_shorts_terms(history_file, max_count=30)
            
            # ※案A의タイトルは表示側で固定生成するため、on_screen_text には含めない
            prompt = f"""
あなたは株ニュース解説キャラクター「株野（かぶの）みのり」の動画ディレクター兼台本作家です。
YouTubeショート（縦型動画）用の、60秒以内の超短縮台本を生成してください。

# ショート動画のコンセプト: {shorts_type}
{"案A: 本日のマーケットに関連する、初心者が躓きやすい・知っておくべき重要な株用語・経済用語を1つピックアップし、やさしく解説します（用語解説）。" if "shorts_a" in video_type else f"案B: チャートが動いている注目銘柄「{valid_companies[0]['company_name'] if valid_companies else '注目銘柄'}」を1つピックアップして深掘りします。"}

# 全般ルール
- 【60秒の壁】: 読み上げテキスト（speech_text）の合計文字数を200〜240文字程度に抑え、絶対に60秒以内で終わるようにしてください。
- 【縦型レイアウト】: 
    - 【重要】ショートでは「タイトル表示」「字幕表示（segments）」は一切しません（テキストは on_screen_text のみを使用）。
    - 画面上部には target_files（用語解説用の美しいアイキャッチ画像やチャート）を表示し、その下に on_screen_text で3行の要約を配置するレイアウトです。
- 【構成】: 
    - 導入（5秒）: 「こんにちは、株野みのりです！」（※導入シーンから用語解説またはニュース内容を表示してください）
    - 本編（45秒）: 用語解説または銘柄解説
    - 結び（10秒）: ニュースや用語のまとめや「明日も見てね！」といった挨拶（※重要：チャンネル登録や高評価の訴求は、後のシーンで自動追加されるため、ここでは絶対に言わないでください）。
- 【データ遵守】: 分析データにある正確な数値を使用してください。
- 【読み上げと表示の分離（最重要）】:
  - `text`: ナレーション本文。NVIDIA / S&P500 / NASDAQ 等は英語表記のまま書く（字幕にもこの表記が使われる）
  - `speech_text`: 読み上げ専用。`text` と同じ内容だが、英字は自然なカタカナに置換（例: NVIDIA→エヌビディア、S&P500→エスアンドピー500）
  - `on_screen_text`: 英語表記のままで可

# on_screen_text 固定フォーマット（重要）
- 案A（やさしい株用語解説）:
    必ず以下の形式で出力してください（ショートBの企業解説と同じフォーマットです）。
        ■[用語名]
        ・[かみ砕いた解説1]
        ・[かみ砕いた解説2]
        ・[投資初心者への影響やアドバイス]
    制約: 1行は全角16文字以内を目安に。長い場合は極限まで短く言い換える。
    例：
        ■地政学リスク
        ・地域的な対立による緊張
        ・原油高や物流の混乱を招く
        ・防衛株の上昇や様子見に
- 案B（注目銘柄 / target_files=[チャート画像1枚]）:
    必ず以下の形式:
        ■企業名
        ・コメント1
        ・コメント2
        ・コメント3
    制約: 各コメントはなるべく1行に収めてください（長い場合は短く言い換える）。

# 分析データ（ここから本日のマーケットの重要な話題、または初心者が躓きがちな用語をピックアップしてください。例：地政学リスク、CPI、決算短信、空売り、日経平均、PBR、半導体セクター、為替介入など）
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene, section_title, duration, text, speech_text, emotion, image_type, bg_name, target_files, on_screen_text
- （任意だが推奨）案A（用語解説）では、解説対象となる用語名（例：「地政学リスク」や「PBR」）を **"explained_term"** というキーに格納して出力してください（全シーンで共通の用語名）。
- shorts動画では section_title は空文字（""）でOKです（表示しないため）。
- shorts動画では image_type は "chart" を基本としてください。
- target_files: 案A・案Bともに `["data/images/placeholder.png"]` のようなダミーを適当に指定してください。後から自動で正しい解説画像に置換されます。

出力は純粋なJSON配列のみを返してください。
"""
            if "shorts_a" in video_type and recent_terms:
                exclude_str = "、".join(recent_terms)
                prompt += f"\n\n# 【重複禁止ルール（最重要）】\n以下の用語は最近解説済みのため、今回は絶対に選ばないでください。同じ用語や、同じ意味・類似する表現は完全に除外してください（最重要）：\n👉 {exclude_str}\n"
        elif is_morning:
            # 朝動画専用プロンプト（ニュース、セクター、日本波及を重視）
            prompt = f"""
あなたは株ニュース解説キャラクター「株野（かぶの）みのり」の動画ディレクター兼台本作家です。
「株野みのり」は、優しいお姉さんキャラであり、敬語を使って話します。
「初心者でも投資が楽しく、わかりやすくなる」をコンセプトに、情報密度の高い動画シーン配列をJSON形式の配列で出力してください。
昨晩の米国市場の動向を受け、今日の日本市場がどう動くかに焦点を当てます。

# 動画構成案
{json.dumps(video_structure, ensure_ascii=False, indent=2)}

# 分析データ
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 全般ルール
- 【尺の確保】: 全体で12分（720秒）を少し超える（目安：12〜13分）動画にしてください。長すぎる冗長な繰り返しは避け、重要論点を優先して密度高くまとめてください。
- 【シーン分割の徹底】: 1シーンに情報を詰め込みすぎないでください。画像（target_files）やテキスト（on_screen_text）が画面内に収まりきらない、あるいは視聴者が理解しにくいと判断した場合は、必ずシーンを分割してください。特に、画像（target_files）があるシーンでは、on_screen_text（画面表示用テキスト）は最大4行（2セット）までとし、それ以上の情報を伝えたい場合は必ずシーンを分割してください（画像がないシーンでは4行を超えても構いません）。
- 【タイトルの形式】：opening以外の各シーンのタイトルは必ず、「セクション名：具体的な内容」という形式にする。openingは「本日のトピック」というタイトルでお願いします。他のシーンのセクション名ですが、us_market_summaryなら米国市場指数, us_news_highlightsなら米国注目ニュース, us_sector_analysisなら米国セクター分析, japan_impact_predictionなら日本市場への影響予測, closingならまとめでお願いします。ただし、シーン分割をした場合、セクション名を分割してもOKです。
- 【セクションの順番】：なるべく動画構成案通り（opening→us_market_summary→us_news_highlights→us_sector_analysis→japan_impact_prediction→closing）にしてください。
- 【画像レイアウト】: 画像が2枚以上の場合は、必ず左右並列（horizontal）にしてください。上下並列（vertical）は使用禁止です。
- 【画像とテキストの併用】: 画像とテキストを同時に表示する場合、画像がメイン、テキストが補足となります。
- 【データ遵守】: 捏造厳禁。分析データにある数値、企業名、ニュース内容のみを根拠にしてください。
- 【専門用語の解説】: 専門用語は初心者にもわかるように簡潔に解説してください。

# 分析データの構造定義（辞書形式）
- `market_indices`: 主要指数の辞書。キーは "DOW", "NASDAQ", "S&P500"。
    - 各要素: `name` (名称), `current_price` (終値), `change_percent` (前日比%), `chart_image_path` (チャート画像パス)
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title`, `snippet`, `visual_image_path`（OG画像 or 関連銘柄チャート）, `visual_source` ("og"|"chart"), `related_ticker`, `related_company_name` があります。
- `sector_analysis`: 注目セクターデータ。
    - `rankings_screenshot`: 米国業種ランキング表の画像パス。
    - `sectors`: セクターごとの詳細リスト。各要素に `sector_name` (セクター名), `type` (top/bottom), `change` (騰落率), `news` (そのセクターの最新ニュースリスト) があります。
    - `news` の各要素: `title` (見出し), `summary` (要約)
- `jp_tomorrow_outlook`: 明日の日本市場への影響予測に関するニュースリスト。`title` (見出し) と `summary` (要約) があります。
- `next_delivery_info`: 次回の配信予定情報（`date`, `time`, `is_holiday_gap`）。

# セクション別詳細指示
1. 【opening】: 
    - 挨拶の直後、必ず「まずは市場指数の解説を行い、その次に（サムネイルにある具体的なニュースタイトル：{analysis_data.get('selected_thumbnail_title', '本日の注目ニュース')}）を詳しく解説します」という旨を伝えてください。
    - 続けて、後半のメニュー（米国セクター分析、日本市場への影響予測）を網羅していることを伝え、最後まで見るメリットを強調してください。
    - 【重要：on_screen_textの指示】: 以下を1行ずつ箇条書きで表示してください。
        "・米国市場の動向"
        "・米国注目ニュース：{analysis_data.get('selected_thumbnail_title', '本日のトピック')[:12]}..."
        "・米国セクター分析"
        "・日本市場への影響予測"
        "・まとめ"
    - また、このセクションだけシーン分割はなしでお願いします。
2. 【us_market_summary】: S&P500、ナスダック(NASDAQ)、ダウ(DOW)をそれぞれ独立したシーンに分ける。、各指数の `chart_image_path` を見せながら、終値(current_price)、前日比(change_percent)、変動原因を分析。
3. 【us_news_highlights】: **重要：以下の順番でニュースを紹介してください。**
    ※ `attention_news` はサムネイル優先で **既に並べ替え済み**。**index 0 = メインニュース** を必ず最初に最も詳しく解説。
    1. `attention_news[0]` を最初に詳しく解説。
    2. 次にハイライトニュース（並べ替え後 index 1,2,3... 付近）を順に紹介。
    3. その後、`attention_news` から**上記（1, 2）以外の**重要なものを数件ピックアップ。
    それぞれ独立したシーン、または分割したシーンで紹介・分析してください。**重要：サムネイルやハイライトで選んだニュースを二重に紹介しないよう、インデックスを厳格にチェックしてください。**
    - **【ニュース画像】**: `attention_news[i].visual_image_path` が「関連銘柄チャート」などで信頼できる場合のみ `target_files` に指定してください。OG画像は内容とズレることがあるため、無理に使う必要はありません。画像が無い場合は、`related_ticker` / `related_company_name` を設定し、画面のティッカー/社名カードで補ってください。
4. 【us_sector_analysis】: `sector_analysis -> rankings_screenshot` を表示しながら、上昇・下落が顕著だったセクター(`sector_analysis -> sectors`)を紹介した後、シーンを切り替え、挙げたセクターの最新ニュース(`sector_analysis -> sectors -> news`)を`on_screen_text`で表示し、騰落原因を分析。理由が不明な場合は市場心理（利益確定、材料待ち等）を推測。
5. 【japan_impact_prediction】: `jp_tomorrow_outlook` 内のニュースを具体的に参照し、米国の動きが日本にどう影響するか。注目日本株の予測（例：NVIDIA高→東エレク）、為替の影響。
6. 【closing】: 今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「夜18時のイブニングレポートもお楽しみに！」といった言葉で締めてください。

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene: 整数（1から開始）
- section_title: 文字列（短いタイトル。例：「本日の日経平均」「注目ニュース：半導体」）
- duration: 秒数
- text: ナレーション本文（英語表記OK。字幕にも使用）
- speech_text: 読み上げ専用（textと同内容だが英字はカタカナ読み）
- on_screen_text: 文字列の配列（画面表示用。画像がある場合は最大4行まで。以下の2項目1セットで構成）
    1. "■ [事実・見出し]"
    2. "  └ [考察・注意点]"
    事実・見出しというのは、ニュースやデータの客観的な要約（例：「SP500 終値3,856.72」「NVIDIA 営業益20%増」）
    考察・注意点というのは、事実・概要に対する分析や投資家が注意すべき点（例：「米金利上昇が重石」「円やによる上振れに注目」）
    ※画像があるシーンで3セット（6行）以上の情報を入れたい場合は、必ずシーンを分割してください。画像がないシーン（image_typeがcharacter_onlyやbg_onlyなど）では、4行を超えても問題ありません。
- emotion: 感情（必ず以下のいずれか1つを厳守して選択: normal, happy, surprised, sad, confident, angry, disappointed, excited）
- image_type: 画像種別（chart, character_only, bg_only, news_panel, chart_with_annotation）
- two_image_layout: 文字列（画像が2枚の場合のみ有効。"horizontal"（左右並列）または "vertical"（上下並列）。デフォルトは "horizontal"）
- bg_name: 背景画像名（基本は "bg_illust.png"）
- target_files: 画像パスの配列（分析データ内にある有効なファイルパスを正確に指定。1枚でも配列形式 ["path"] で出力）

# 台本作成の鉄則（コンセプト：徹底的な初心者目線＆ロジカル）
    1. 【徹底的な初心者目線】：専門用語（例：流動性、円安メリット、窓開け）の解説にとどまらず、「それが私たちの生活や投資にどう影響するのか」を中学生でもわかるレベルで噛み砕いてください。単なる用語補完ではなく、背景にあるストーリーを重視してください。
    2. 【情報の相関分析】：単一のデータだけでなく、「米国の金利が上がったから、日本のハイテク株が売られた」のように、複数のデータ（為替×市場、米国×日本など）を組み合わせた因果関係を1つ以上述べてください。
    3. 【読み上げと表示の分離（重要）】：`text` は英語表記のまま（NVIDIA, S&P500 等）。`speech_text` にだけカタカナ読み（エヌビディア、エスアンドピー500 等）を書く。`on_screen_text` は英語表記のままでよい。
    4. 【正確な高値表現】：日経平均などの指標が上がっている際、安易に「最高値」と表現しないでください。過去最高を更新した時のみ「史上最高値」を使用し、それ以外は「年初来高値」「〇ヶ月ぶりの高値」「バブル後高値」など、分析データに基づいた正確な期間を添えてください。
    5. 【誠実なぼかし】：明確な理由がない場合は「謎」とせず、「今は材料待ちで市場が様子見をしているようです」や「過熱感から利益確定の売りが出た可能性があります」など、市場心理を推測して伝えてください。
    6. 【具体性】：ニュースは「ある企業が〜」ではなく「NVIDIAが〜」と実名を出してください。
    7. 【数値】：株価や騰落率などの数値は「大きく動いた」ではなく「300円安の〇〇円」などと具体的に述べてください。また、数値は「38,567.23円」だったら、「3万8500円付近」や「3万8560円」など、耳で聞いてわかりやすい表現に丸めてください。
    8. 【感情（キャラ表情）】
        - `emotion`: シーンの基調。中立的な説明・数値の読み上げ・つなぎは **normal** でよい。
        - 好調・上昇・好材料は happy / excited、下落・懸念・失望は sad / disappointed、想定外は surprised、強い批判は angry、見通しの断定は confident。
        - 全体を normal だけにしない。内容に応じて積極的に使う。
    8b. 【emotion_timeline（重要）】
        - `speech_text` が **2句以上**（`。` `、` で区切れる）か、**1シーン内でトーンが変わる**ときは **必ず** `emotion_timeline` を付ける。
        - 形式: `[{{"segment_index": 0, "emotion": "happy"}}, {{"segment_index": 2, "emotion": "sad"}}]`
        - `segment_index` は読み上げの句順（0始まり）。**切り替え秒数はシステムが音声の長さから自動計算**する（あなたが秒数を書く必要はない）。
        - 単調な短い説明だけのシーンは `emotion: "normal"` のみで timeline 省略可。
        - 例: 前半好調・後半注意 → `[{{"segment_index":0,"emotion":"happy"}},{{"segment_index":2,"emotion":"confident"}}]`
        - 代替: `segment_emotions` 配列でも可。
    9. 【行動指針の提示】：最後に「今日はまず〇〇をチェックしましょう」など、視聴者が次に取るべきアクションを具体的に指示してください。
    10. 【データ不足時の対応】：対応するデータがない場合、データがない旨を伝える。
    11. 【自然な文章構成】：読み上げが不自然に細切れにならないよう、一文一文を適切な長さ（40〜80文字程度）に保ち、意味の区切りで自然に読めるように構成してください。

出力は純粋なJSON配列のみを返してください。
"""
        else:
            # 既存の夜動画用プロンプトを完全に復元
            prompt = f"""
あなたは株ニュース解説キャラクター「株野（かぶの）みのり」の動画ディレクター兼台本作家です。
「株野みのり」は、優しいお姉さんキャラであり、敬語を使って話します。
「初心者でも投資が楽しく、わかりやすくなる」をコンセプトに、情報密度の高い動画シーン配列をJSON形式の配列で出力してください。

# 動画構成案
{json.dumps(video_structure, ensure_ascii=False, indent=2)}

# 分析データ（ここにある具体的な数値・名称・内容を必ず使用してください）
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 全般ルール
- 【尺の確保】: 全体で15分（900秒）を少し超える（目安：15〜16分）動画にしてください。長すぎる冗長な繰り返しは避け、重要論点を優先して密度高くまとめてください。
- 【シーン分割の徹底】: 1シーンに情報を詰め込みすぎないでください。画像（target_files）やテキスト（on_screen_text）が画面内に収まりきらない、あるいは視聴者が理解しにくいと判断した場合は、必ずシーンを分割してください。特に、画像（target_files）があるシーンでは、on_screen_text（画面表示用テキスト）は最大4行（2セット）までとし、それ以上の情報を伝えたい場合は必ずシーンを分割してください（画像がないシーンでは4行を超えても構いません）。
- 【タイトルの形式】：opening以外の各シーンのタイトルは必ず、「セクション名：具体的な内容」という形式にする。openingは「本日のトピック」というタイトルでお願いします。他のシーンのセクション名ですが、market_indiciesなら市場指数, news_highlightsなら注目ニュース, event_calenderなら決算・株主総会スケジュール, sector_overviewならセクター概要, sector_attentionなら[セクター名]注目銘柄, prev_ir_attentionなら前回紹介銘柄の動向, tomorrow_strategyなら今夜の米国市場と明日の展望, closingならまとめでお願いします。ただし、シーン分割をした場合、セクション名を分割してもOKです。例えば「今夜の米国市場」と「明日の展望」で分けるみたいな感じです。
- 【セクションの順番】：なるべく動画構成案通り（opening→market_indices→news_highlights→event_calender→sector_overview→sector_attention→prev_ir_tracking→tomorrow_strategy→closing）にしてください。
- 【画像レイアウト】: 画像が2枚以上の場合は、必ず左右並列（horizontal）にしてください。上下並列（vertical）は使用禁止です。
- 【画像とテキストの併用】: 画像とテキストを同時に表示する場合、画像がメイン、テキストが補足となります。
- 【データ遵守】: 捏造厳禁。分析データにある数値、企業名、ニュース内容のみを根拠にしてください。
- 【専門用語の解説】: 専門用語は初心者にもわかるように簡潔に解説してください。

# 分析データの構造定義（辞書形式）
- `market_indices`: 主要指数の辞書。キーは "NIKKEI", "SP500"。
    - 各要素: `name` (名称), `current_price` (終値), `change_percent` (前日比%), `chart_image_path` (チャート画像パス)
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title`, `snippet`, `visual_image_path`, `visual_source` ("og"|"chart"), `related_ticker`, `related_company_name` があります。
- `sector_analysis`: 注目セクターと個別銘柄の統合データ。
    - `rankings_screenshot`: 33業種ランキング表の画像パス。
    - `sectors`: セクターごとの詳細リスト。各要素に `sector_name` (セクター名), `type` (top/bottom), `change` (騰落率), `companies` (そのセクターの主要銘柄リスト) があります。
    - `companies` の各要素: `company_name` (社名), `news` (銘柄ニュース), `chart_image_path` (個別チャート画像パス)
- `kessan_schedule` / `soukai_schedule`: 決算と総会の予定。
    - `image_path`: スケジュール一覧表の画像パス
    - `data`: 予定の詳細リスト。空の場合は予定がないことを意味します。
- `prev_ir_analysis`: 前回紹介銘柄の追跡結果リスト。
    - 各要素: `company_name` (社名), `change_percent` (騰落率), `recent_news` (直近ニュースリスト), `reason_summary` (変動理由の要約), `chart_image_path` (チャート画像パス)
- `us_tonight_outlook`: 今夜の米国市場の見通しニュースリスト。`attention_news` と同様に `visual_image_path` 等を含む場合があります。
- `next_delivery_info`: 次回の配信予定情報（`date`, `time`, `is_holiday_gap`）。

# セクション別詳細指示
1. 【opening】: 
    - 挨拶の直後、必ず「まずは市場指数の解説を行い、その次に（サムネイルにある具体的なニュースタイトル：{analysis_data.get('selected_thumbnail_title', '本日の注目ニュース')}）を詳しく解説します」という旨を伝えてください。
    - 続けて、後半のメニュー（決算、セクター分析、注目銘柄、展望）を網羅していることを伝え、最後まで見るメリットを強調してください。
    - 【重要：on_screen_textの指示】: 以下を1行ずつ箇条書きで表示してください。
        "・市場の動向"
        "・注目ニュース：{analysis_data.get('selected_thumbnail_title', '本日のトピック')[:12]}..."
        "・決算・株主総会スケジュール"
        "・セクター分析"
        "・注目銘柄のIR"
        "・前回紹介銘柄の動向"
        "・今夜の米国市場と明日の展望"
        "・まとめ"
    - また、このセクションだけシーン分割はなしでお願いします。
2. 【market_indices】: 日経平均(NIKKEI)、S&P500(SP500)をそれぞれ独立したシーンに分ける。必ず日経平均から先に紹介すること。各指数の `chart_image_path` を見せながら、終値(current_price)、前日比(change_percent)、変動原因を分析。最後にドル円(USDJPY)の動きとその影響を説明するシーンを追加。
3. 【news_highlights】: **重要：以下の順番でニュースを紹介してください。**
    ※ `attention_news` はサムネイル優先で **既に並べ替え済み** です。**index 0 = サムネイルのメインニュース** として必ず最初のシーンで最も詳しく解説してください。
    1. `attention_news[0]`（メイン）を最初に、最も詳しく解説してください。
    2. 次に、ハイライトニュース（元の index {analysis_data.get('highlight_indices', [])} に相当する記事。並べ替え後は index 1,2,3... 付近）を順に紹介してください。
    3. その後、`attention_news` から**上記（1, 2）以外の**重要なものを数件ピックアップ。
    それぞれ独立したシーン、または分割したシーンでさらっと紹介・分析。**重要：サムネイルやハイライトで選んだニュースを二重に紹介しないよう、インデックスを厳格にチェックしてください。**
    - **【ニュース画像】**: `attention_news[i].visual_image_path` が「関連銘柄チャート」などで信頼できる場合のみ `target_files` に指定してください。OG画像は内容とズレることがあるため、無理に使う必要はありません。画像が無い場合でも、`related_ticker` / `related_company_name` を設定し、画面のティッカー/社名カードで補ってください。
4. 【event_calendar】: 決算(`kessan_schedule`)と株主総会(`soukai_schedule`)をそれぞれ独立したシーンに分け、それぞれの `image_path` を必ず添付。データがなければ「予定なし」と伝える。
5. 【sector_overview】: `sector_analysis -> rankings_screenshot` を表示。上昇・下落が顕著だったセクターをそれぞれ3つ具体的に挙げる。
6. 【sector_attention】: `sector_analysis -> sectors` のデータを使用。セクターごとにシーンを分け、そのセクターの騰落率を紹介した後、各主要銘柄の `chart_image_path` を表示し、ニュースを `on_screen_text` で表示しながら変動原因を分析。各銘柄を丁寧に紹介してください。
7. 【prev_ir_tracking】: `prev_ir_analysis` の銘柄ごとにシーンを作成。`chart_image_path` を表示し、変動率や直近ニュースを `on_screen_text` で表示しながら、前回から今回への変動要因(reason_summary)を説明。データがなければスキップ。
8. 【tomorrow_strategy】: `us_tonight_outlook` 内のニュースを具体的に参照し、明日の展望を解説。各ニュースに `visual_image_path` があれば `target_files` に含めてください。
9. 【closing】: 今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「明日朝7時のモーニングレポートもお楽しみに！」といった言葉で締めてください。

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene: 整数（1から開始）
- section_title: 文字列（短いタイトル。例：「本日の日経平均」「注目ニュース：半導体」）
- duration: 秒数
- text: ナレーション本文（英語表記OK。字幕にも使用）
- speech_text: 読み上げ専用（textと同内容だが英字はカタカナ読み）
- on_screen_text: 文字列の配列（画面表示用。最大4行まで。以下の2項目1セットで構成）
    1. "■ [事実・見出し]"
    2. "  └ [考察・注意点]"
    事実・見出しというのは、ニュースやデータの客観的な要約（例：「日経平均 300円安」「トヨタ 営業益20%増」）
    考察・注意点というのは、事実・概要に対する分析や投資家が注意すべき点（例：「米金利上昇が重石」「円やによる上振れに注目」）
    ※1シーンに3セット（6行）以上の情報を入れたい場合は、必ずシーンを分割してください。
- emotion: 感情（必ず以下のいずれか1つを厳守して選択: normal, happy, surprised, sad, confident, angry, disappointed, excited）
- image_type: 画像種別（chart, character_only, bg_only, news_panel, chart_with_annotation）
- two_image_layout: 文字列（画像が2枚の場合のみ有効。"horizontal"（左右並列）または "vertical"（上下並列）。デフォルトは "horizontal"）
- bg_name: 背景画像名（基本は "bg_illust.png"）
- target_files: 画像パスの配列（分析データ内にある有効なファイルパスを正確に指定。1枚でも配列形式 ["path"] で出力）

# 台本作成の鉄則（コンセプト：徹底的な初心者目線＆ロジカル）
    1. 【徹底的な初心者目線】：専門用語（例：流動性、円安メリット、窓開け）の解説にとどまらず、「それが私たちの生活や投資にどう影響するのか」を中学生でもわかるレベルで噛み砕いてください。単なる用語補完ではなく、背景にあるストーリーを重視してください。
    2. 【情報の相関分析】：単一のデータだけでなく、「米国の金利が上がったから、日本のハイテク株が売られた」のように、複数のデータ（為替×市場、米国×日本）を組み合わせた因果関係を1つ以上述べてください。
    3. 【読み上げと表示の分離（重要）】：`text` は英語表記のまま（NVIDIA, S&P500 等）。`speech_text` にだけカタカナ読み（エヌビディア、エスアンドピー500 等）を書く。`on_screen_text` は英語表記のままでよい。
    4. 【正確な高値表現】：日経平均などの指標が上がっている際、安易に「最高値」と表現しないでください。過去最高を更新した時のみ「史上最高値」を使用し、それ以外は「年初来高値」「〇ヶ月ぶりの高値」「バブル後高値」など、分析データに基づいた正確な期間を添えてください。
    5. 【誠実なぼかし】：明確な理由がない場合は「謎」とせず、「今は材料待ちで市場が様子見をしているようです」や「過熱感から利益確定の売りが出た可能性があります」など、市場心理を推測して伝えてください。
    6. 【具体性】：ニュースは「ある企業が〜」ではなく「トヨタ自動車が〜」と実名を出してください。
    7. 【数値】：株価や騰落率などの数値は「大きく動いた」ではなく「300円安の〇〇円」と具体的に述べてください。また、数値は「38,567.23円」だったら、「3万8500円付近」や「3万8560円」など、耳で聞いてわかりやすい表現に丸めてください。
    8. 【感情（キャラ表情）】
        - `emotion`: シーンの基調。中立的な説明・数値の読み上げ・つなぎは **normal** でよい。
        - 好調・上昇・好材料は happy / excited、下落・懸念・失望は sad / disappointed、想定外は surprised、強い批判は angry、見通しの断定は confident。
        - 全体を normal だけにしない。内容に応じて積極的に使う。
    8b. 【emotion_timeline（重要）】
        - `speech_text` が **2句以上**（`。` `、` で区切れる）か、**1シーン内でトーンが変わる**ときは **必ず** `emotion_timeline` を付ける。
        - 形式: `[{{"segment_index": 0, "emotion": "happy"}}, {{"segment_index": 2, "emotion": "sad"}}]`
        - `segment_index` は読み上げの句順（0始まり）。**切り替え秒数はシステムが音声の長さから自動計算**する（あなたが秒数を書く必要はない）。
        - 単調な短い説明だけのシーンは `emotion: "normal"` のみで timeline 省略可。
        - 例: 前半好調・後半注意 → `[{{"segment_index":0,"emotion":"happy"}},{{"segment_index":2,"emotion":"confident"}}]`
        - 代替: `segment_emotions` 配列でも可。
    9. 【行動指針の提示】：最後に「明日の朝はまず〇〇をチェックしましょう」など、視聴者が次に取るべきアクションを具体的に指示してください。
    10. 【データ不足時の対応】：決算/総会データがない場合、「本日の予定はありません」と事実を伝える。前回紹介銘柄データがない場合、このセクション自体をスキップするか、手短に次へ進む。`attention_news` が空の場合、news_highlights（および関連するニュース紹介）で具体的なニュース見出し/銘柄を捏造せず、「ニュースが取得できませんでした」とだけ述べる。
    11. 【自然な文章構成】：読み上げが不自然に細切れにならないよう、一文一文を適切な長さ（40〜80文字程度）に保ち、意味の区切りで自然に読めるように構成してください。

出力は純粋なJSON配列のみを返してください。
"""

        presentation_mode = normalize_presentation_mode(presentation_mode)
        if is_immersive_mode(presentation_mode, video_type=video_type):
            print("[Mode] 台本生成: immersive（聞き中心・番組感）モード")
            prompt += self._immersive_prompt_appendix(analysis_data)

        attempt = 0
        last_errs = []
        while attempt < max_retries:
            attempt += 1
            try:
                raw = self.client.generate_content(
                    prompt, max_retries=1, use_search=False, model_role="heavy"
                )
                # try direct parse
                try:
                    scenes = json.loads(raw)
                except Exception:
                    # extract JSON array substring
                    m = re.search(r"(\[.*\])", raw, re.DOTALL)
                    if m:
                        try:
                            scenes = json.loads(m.group(1))
                        except Exception as e:
                            raise ValueError(f"JSON parse failed: {e}")
                    else:
                        raise ValueError("No JSON array found in LLM output")

                ok, errs = validate_scene_list(scenes)
                if not ok:
                    # 感情(emotion)のエラーのみを自動修正する試み
                    from src.analysis.scene_schema import ALLOWED_EMOTIONS
                    fixed = False
                    for i, scene in enumerate(scenes):
                        if "emotion" in scene and scene["emotion"] not in ALLOWED_EMOTIONS:
                            print(f"[Fix] シーン {i} の感情 '{scene['emotion']}' を 'normal' に自動修正しました")
                            scene["emotion"] = "normal"
                            fixed = True
                    
                    if fixed:
                        # 修正後にもう一度バリデーション
                        ok, errs = validate_scene_list(scenes)
                    
                    if not ok:
                        last_errs = errs
                        # retry with stricter instruction
                        prompt = prompt + "\n出力がスキーマに合致していません。必ず前述のスキーマ通りのJSON配列のみを返してください。"
                        continue

                # --- 横型本編: 感情 timeline の補完（LLM が省略した場合） ---
                if not is_shorts:
                    from src.video_generation.character_emotion import enrich_emotion_timelines

                    n_enriched = enrich_emotion_timelines(scenes)
                    if n_enriched:
                        print(f"[Emotion] speech_text から emotion_timeline を補完: {n_enriched} シーン")

                # --- Shorts B: ダミー画像(placeholder)を必ず用意しておく ---
                # もともと shorts_b は target_files に placeholder を入れる前提があるため、
                # ファイルが無いと composer 側で「画像なし」とみなされてレイアウトが崩れる。
                if is_shorts and ("shorts_b" in video_type):
                    self._ensure_placeholder_image(Path("data/images/placeholder.png"))

                # --- Shorts A: Pillowでやさしい株用語解説のアイキャッチカード画像を動的生成して差し込む ---
                if is_shorts and ("shorts_a" in video_type):
                    # 用語名の抽出
                    term_name = "株用語"
                    for sc in scenes:
                        if sc.get("explained_term"):
                            term_name = str(sc["explained_term"]).strip()
                            break
                        elif sc.get("on_screen_text"):
                            for line in sc["on_screen_text"]:
                                if line.startswith("■"):
                                    term_name = line.replace("■", "").strip()
                                    break
                            if term_name != "株用語":
                                break
                    
                    # 履歴に保存
                    if term_name != "株用語":
                        self._save_shorts_term_history(history_file, term_name)
                    
                    # Pillow で用語カード画像を生成
                    visual = self._generate_term_card_image(term_name)
                    if visual:
                        for sc in scenes:
                            # 完全に「上部に画像＋下部にテキスト」型へ上書き
                            sc["image_type"] = "chart"
                            sc["target_files"] = [visual]

                # save file
                out_dir = Path("data/scripts")
                out_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = out_dir / f"scenes_{ts}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(scenes, f, ensure_ascii=False, indent=2)
                print(f"[Save] シーンJSONを保存: {filepath}")
                return scenes

            except Exception as e:
                last_errs.append(str(e))
                print(f"[Retry] structured scenes generation attempt {attempt} failed: {e}")
                continue

        # 最後にエラーを投げる
        raise RuntimeError(f"structured scenes generation failed after {max_retries} attempts. errors: {last_errs}")

    @staticmethod
    def _get_recent_shorts_terms(history_path: Path, max_count: int = 30) -> List[str]:
        """過去に解説した用語のリストを取得する"""
        if not history_path.exists():
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            # history はリスト: [{"term": "地政学リスク", "date": "2026-05-28..."}, ...]
            terms = [item["term"] for item in history if isinstance(item, dict) and "term" in item]
            return terms[:max_count]
        except Exception as e:
            print(f"[WARN] 履歴ファイルの読み込みに失敗しました: {e}")
            return []

    @staticmethod
    def _save_shorts_term_history(history_path: Path, term: str) -> None:
        """解説した用語を履歴に追記保存する"""
        history = []
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception as e:
                print(f"[WARN] 履歴ファイルの読み込みに失敗しました（初期化します）: {e}")
        
        # 重複用語があれば古い方を削除して最新を先頭にする
        history = [item for item in history if isinstance(item, dict) and item.get("term") != term]
        
        entry = {
            "term": term,
            "date": datetime.now().isoformat()
        }
        history.insert(0, entry)
        
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f"[History] 解説用語を履歴に記録しました: '{term}'")
        except Exception as e:
            print(f"[WARN] 履歴ファイルの保存に失敗しました: {e}")

    @staticmethod
    def _ensure_placeholder_image(path: Path) -> None:
        """Shorts B のダミー画像が無い場合にローカル生成する（無料・通信なし）。"""
        if path.exists():
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image, ImageDraw, ImageFont

            w, h = 1280, 720
            img = Image.new("RGB", (w, h), (235, 245, 255))
            draw = ImageDraw.Draw(img)

            # 枠
            draw.rectangle((40, 40, w - 40, h - 40), outline=(120, 150, 190), width=6)

            # テキスト（フォントはあれば使用）
            font = None
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 56)
            except Exception:
                font = ImageFont.load_default()

            text = "CHART"
            tw = draw.textlength(text, font=font)
            draw.text(((w - tw) // 2, (h // 2) - 40), text, fill=(60, 90, 140), font=font)

            img.save(path, "PNG")
            print(f"[Pillow] placeholder 画像を生成しました: {path}")
        except Exception as e:
            print(f"[WARN] placeholder 画像の生成に失敗しました: {e}")

    @staticmethod
    def _generate_term_card_image(term_name: str, assets_dir: str = "src/assets") -> str:
        """
        指定された用語名が入った、やさしい株用語解説のアイキャッチ画像を Pillow で生成して保存。
        """
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import hashlib
        
        w, h = 1280, 720
        # 1. 綺麗な斜めグラデーション（みのりのイメージカラー：ネイビーブルー系）
        base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(h):
            for x in range(w):
                r = int(12 + (x / w) * 15 + (y / h) * 10)
                g = int(24 + (x / w) * 20 + (y / h) * 15)
                b = int(58 + (x / w) * 35 + (y / h) * 25)
                base.putpixel((x, y), (r, g, b, 255))
                
        # 2. 半透明の二重角丸プレートを描画して奥行き感を出す
        plate_w, plate_h = 1120, 560
        plate_x = (w - plate_w) // 2
        plate_y = (h - plate_h) // 2
        
        plate_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        plate_draw = ImageDraw.Draw(plate_layer)
        
        # 外枠プレート
        plate_draw.rounded_rectangle(
            (plate_x, plate_y, plate_x + plate_w, plate_y + plate_h),
            radius=32,
            fill=(255, 255, 255, 12),
            outline=(255, 255, 255, 40),
            width=3
        )
        # 内枠プレート
        plate_draw.rounded_rectangle(
            (plate_x + 30, plate_y + 30, plate_x + plate_w - 30, plate_y + plate_h - 30),
            radius=24,
            fill=(255, 255, 255, 8),
            outline=(255, 255, 255, 25),
            width=2
        )
        
        base = Image.alpha_composite(base, plate_layer)
        draw = ImageDraw.Draw(base)
        
        # 3. フォントロード
        fonts_dir = Path(assets_dir) / "fonts"
        font_path = None
        for p in [
            fonts_dir / "NotoSansJP-Bold.ttf",
            fonts_dir / "NotoSansJP-Regular.ttf",
            fonts_dir / "NotoSansJP-Bold.otf",
            fonts_dir / "NotoSansJP-Regular.otf",
            Path("C:/Windows/Fonts/meiryob.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttc"),
            Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        ]:
            if p.exists():
                font_path = str(p)
                break
                
        def _get_font(size: int):
            if font_path:
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    pass
            return ImageFont.load_default()
            
        font_main = _get_font(130) # 標準：130pt (超巨大)
        font_desc = _get_font(64)  # 説明：64pt
        
        # 4. テキスト描画 (中央揃え)
        
        # a. 用語メイン名
        main_text = f"「 {term_name} 」"
        # 用語名が長すぎる場合はフォントサイズを縮小してはみ出しを防ぐ
        if len(term_name) <= 5:
            font_main = _get_font(130)
        elif len(term_name) <= 8:
            font_main = _get_font(110)
        elif len(term_name) <= 12:
            font_main = _get_font(85)
        else:
            font_main = _get_font(65)
            
        sw_main = draw.textlength(main_text, font=font_main)
        draw.text(((w - sw_main) // 2, plate_y + 130), main_text, fill=(255, 255, 255, 255), font=font_main)
        
        # b. 「を1分でやさしく解説！」
        desc_text = "を1分でやさしく解説！"
        sw_desc = draw.textlength(desc_text, font=font_desc)
        draw.text(((w - sw_desc) // 2, plate_y + 350), desc_text, fill=(255, 215, 0, 255), font=font_desc) # 綺麗なゴールド/イエロー
        
        # 5. 保存
        out_dir = Path("data/images")
        out_dir.mkdir(parents=True, exist_ok=True)
        # Windowsの日本語エンコーディング問題を回避するため、ファイル名はハッシュ化して安全にする
        term_hash = hashlib.md5(term_name.encode("utf-8")).hexdigest()[:8]
        filename = f"shorts_term_{term_hash}.png"
        out_path = out_dir / filename
        
        base.convert("RGB").save(out_path, "PNG")
        print(f"[Pillow] 用語解説カード画像を生成しました: {out_path}")
        return str(out_path)
