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


class ScriptGenerator:
    """台本生成クラス"""
    
    # 読み上げ速度の目安（文字/秒）
    CHARS_PER_SECOND = 4.0  # 落ち着いた速度
    
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
        
        print("✅ ScriptGenerator 初期化完了")

    def generate_structured_scenes(
        self,
        video_structure: Dict,
        analysis_data: Dict,
        enriched_data: Optional[Dict] = None,
        max_retries: int = 5
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
            shorts_type = "案A（ニュースまとめ）" if "shorts_a" in video_type else "案B（注目銘柄）"
            
            # 案Bの場合、チャート画像がある銘柄を特定
            valid_companies = []
            if "shorts_b" in video_type:
                for sector in analysis_data.get("sector_analysis", {}).get("sectors", []):
                    for company in sector.get("companies", []):
                        if company.get("chart_image_path"):
                            valid_companies.append(company)
            
            # ※案Aの「◯/◯の3大ニュース」は表示側でコード生成するため、on_screen_text には含めない
            prompt = f"""
あなたは株ニュース解説キャラクター「株野（かぶの）みのり」の動画ディレクター兼台本作家です。
YouTubeショート（縦型動画）用の、60秒以内の超短縮台本を生成してください。

# ショート動画のコンセプト: {shorts_type}
{"案A: 今日の重要ニュース3つをテンポよく解説します。" if "shorts_a" in video_type else f"案B: チャートが動いている注目銘柄「{valid_companies[0]['company_name'] if valid_companies else '注目銘柄'}」を1つピックアップして深掘りします。"}

# 全般ルール
- 【60秒の壁】: 読み上げテキスト（text）の合計文字数を200〜240文字程度に抑え、絶対に60秒以内で終わるようにしてください。
- 【縦型レイアウト】: 
    - 【重要】ショートでは「タイトル表示」「字幕表示（segments）」は一切しません（テキストは on_screen_text のみを使用）。
    - 案A（テキストのみ）: target_files は空配列。on_screen_text は必ず「固定フォーマット」で出力してください（下記参照）。
    - 案B（画像＋テキスト）: 画面上部に target_files（チャート画像）を1枚、その下に on_screen_text（固定フォーマット）で要約テキストを表示します。
- 【構成】: 
    - 導入（5秒）: 「こんにちは、株野みのりです！」（※導入シーンからニュース内容を表示してください）
    - 本編（45秒）: ニュース解説または銘柄解説
    - 結び（10秒）: ニュースのまとめや「明日も見てね！」といった挨拶（※重要：チャンネル登録や高評価の訴求は、後のシーンで自動追加されるため、ここでは絶対に言わないでください）。
- 【データ遵守】: 分析データにある正確な数値を使用してください。
- 【読み上げ対策（最重要）】: ENEOS（エネオス）、LIXIL（リクシル）、NVIDIA（エヌビディア）など、アルファベットの企業名や英単語は、音声合成で一文字ずつ読まれないよう、必ず読み上げ台本（text）の中では「自然なカタカナ表記」に変換してください。

# on_screen_text 固定フォーマット（重要）
- 案A（ニュースまとめ / target_files=[]）:
    必ず以下の並びを3セット（=ニュース3本）で繰り返す:
        ■ニュースタイトル
        └コメント
        （改行）
        ■ニュースタイトル
        └コメント
        （改行）
        ■ニュースタイトル
        └コメント
    制約: 「■ニュースタイトル」「└コメント」は、それぞれなるべく1行に収めてください（長い場合は短く言い換える）。
- 案B（注目銘柄 / target_files=[チャート画像1枚]）:
    必ず以下の形式:
        ■企業名
        ・コメント1
        ・コメント2
        ・コメント3
    制約: 各コメントはなるべく1行に収めてください（長い場合は短く言い換える）。

# 分析データ
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene, section_title, duration, text, emotion, image_type, bg_name, target_files, on_screen_text
- shorts動画では section_title は空文字（""）でOKです（表示しないため）。
- shorts動画では image_type は "bg_only" (案A) または "chart" (案B) を基本としてください。
- target_files: 案Aは []。案Bは `["{valid_companies[0]['chart_image_path'] if valid_companies else ''}"]` のように指定。

出力は純粋なJSON配列のみを返してください。
"""
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
- 【尺の確保】: 全体で18分（1080秒）を大きく超える、極めて情報密度の高い動画にしてください。VOICEVOXでの読み上げは想定より短くなる傾向があるため、ニュースのピックアップ数を増やすなど、各トピックの解説を徹底的に深掘りし、圧倒的な分量の台本を書いてください。
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
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title` (見出し) と `snippet` (要約)があります。
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
    1. サムネイルのメインニュース（`attention_news` の {analysis_data.get('main_news_index', 0)} 番目のニュース）を最初に、最も詳しく解説してください。
    2. 次に、ハイライトに選ばれたニュース（`attention_news` の {analysis_data.get('highlight_indices', [])} 番目のニュース）を順に紹介してください。
    3. その後、`attention_news` から**上記（1, 2）以外の**重要なものを数件ピックアップ。
    それぞれ独立したシーン、または分割したシーンで紹介・分析してください。**重要：サムネイルやハイライトで選んだニュースを二重に紹介しないよう、インデックスを厳格にチェックしてください。**
4. 【us_sector_analysis】: `sector_analysis -> rankings_screenshot` を表示しながら、上昇・下落が顕著だったセクター(`sector_analysis -> sectors`)を紹介した後、シーンを切り替え、挙げたセクターの最新ニュース(`sector_analysis -> sectors -> news`)を`on_screen_text`で表示し、騰落原因を分析。理由が不明な場合は市場心理（利益確定、材料待ち等）を推測。
5. 【japan_impact_prediction】: `jp_tomorrow_outlook` 内のニュースを具体的に参照し、米国の動きが日本にどう影響するか。注目日本株の予測（例：NVIDIA高→東エレク）、為替の影響。
6. 【closing】: 今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「夜18時のイブニングレポートもお楽しみに！」といった言葉で締めてください。

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene: 整数（1から開始）
- section_title: 文字列（短いタイトル。例：「本日の日経平均」「注目ニュース：半導体」）
- duration: 秒数
- text: 読み上げるテキスト
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

# 台本作成の鉄則（コンセプト：初心者フレンドリー＆ロジカル）
    1. 【初心者でもわかる比喩】：専門用語（例：流動性、円安メリット、窓開け）が出た際は、身近な例で補足したり、必ずわかりやすく説明してあげてください。
    2. 【情報の相関分析】：単一のデータだけでなく、「米国の金利が上がったから、日本のハイテク株が売られた」のように、複数のデータ（為替×市場、米国×日本など）を組み合わせた因果関係を1つ以上述べてください。
    3. 【読み上げ対策（重要）】：ENEOS（エネオス）、LIXIL（リクシル）やNVIDIA（エヌビディア）など、アルファベットの企業名や英単語は、音声合成で一文字ずつ（エル・アイ...等）読まれないよう、必ず読み上げ台本（text）の中では自然なカタカナ表記（例：エネオス、リクシル、エヌビディア、ナスダック）に変換してください。ただし、画面表示用（on_screen_text）はアルファベットのままで構いません。
    4. 【正確な高値表現】：日経平均などの指標が上がっている際、安易に「最高値」と表現しないでください。過去最高を更新した時のみ「史上最高値」を使用し、それ以外は「年初来高値」「〇ヶ月ぶりの高値」「バブル後高値」など、分析データに基づいた正確な期間を添えてください。
    5. 【誠実なぼかし】：明確な理由がない場合は「謎」とせず、「今は材料待ちで市場が様子見をしているようです」や「過熱感から利益確定の売りが出た可能性があります」など、市場心理を推測して伝えてください。
    6. 【具体性】：ニュースは「ある企業が〜」ではなく「NVIDIAが〜」と実名を出してください。
    7. 【数値】：株価や騰落率などの数値は「大きく動いた」ではなく「300円安の〇〇円」などと具体的に述べてください。また、数値は「38,567.23円」だったら、「3万8500円付近」や「3万8560円」など、耳で聞いてわかりやすい表現に丸めてください。
    8. 【感情の同期】：市場が好調なら「happy/excited」、大幅下落なら「sad/disappointed」など、ニュースの内容に合わせた感情を選択してください。
    9. 【行動指針の提示】：最後に「今日はまず〇〇をチェックしましょう」など、視聴者が次に取るべきアクションを具体的に指示してください。
    10. 【データ不足時の対応】：対応するデータがない場合、データがない旨を伝える。

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
- 【尺の確保】: 全体で16分（960秒）を大きく超える、極めて情報密度の高い動画にしてください。VOICEVOXでの読み上げは想定より短くなる傾向があるため、ニュースのピックアップ数を増やすなど、各トピックの解説を徹底的に深掘りし、圧倒的な分量の台本を書いてください。
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
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title` (見出し) と `snippet` (要約) があります。
- `sector_analysis`: 注目セクターと個別銘柄の統合データ。
    - `rankings_screenshot`: 33業種ランキング表の画像パス。
    - `sectors`: セクターごとの詳細リスト。各要素に `sector_name` (セクター名), `type` (top/bottom), `change` (騰落率), `companies` (そのセクターの主要銘柄リスト) があります。
    - `companies` の各要素: `company_name` (社名), `news` (銘柄ニュース), `chart_image_path` (個別チャート画像パス)
- `kessan_schedule` / `soukai_schedule`: 決算と総会の予定。
    - `image_path`: スケジュール一覧表の画像パス
    - `data`: 予定の詳細リスト。空の場合は予定がないことを意味します。
- `prev_ir_analysis`: 前回紹介銘柄の追跡結果リスト。
    - 各要素: `company_name` (社名), `change_percent` (騰落率), `recent_news` (直近ニュースリスト), `reason_summary` (変動理由の要約), `chart_image_path` (チャート画像パス)
- `us_tonight_outlook`: 今夜の米国市場の見通しに関するニュースリスト。`title` (見出し) と `snippet` (要約) があります。
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
    1. サムネイルのメインニュース（`attention_news` の {analysis_data.get('main_news_index', 0)} 番目のニュース）を最初に、最も詳しく解説してください。
    2. 次に、ハイライトに選ばれたニュース（`attention_news` の {analysis_data.get('highlight_indices', [])} 番目のニュース）を順に紹介してください。
    3. その後、`attention_news` から**上記（1, 2）以外の**重要なものを数件ピックアップ。
    それぞれ独立したシーン、または分割したシーンでさらっと紹介・分析。**重要：サムネイルやハイライトで選んだニュースを二重に紹介しないよう、インデックスを厳格にチェックしてください。**
4. 【event_calendar】: 決算(`kessan_schedule`)と株主総会(`soukai_schedule`)をそれぞれ独立したシーンに分け、それぞれの `image_path` を必ず添付。データがなければ「予定なし」と伝える。
5. 【sector_overview】: `sector_analysis -> rankings_screenshot` を表示。上昇・下落が顕著だったセクターをそれぞれ3つ具体的に挙げる。
6. 【sector_attention】: `sector_analysis -> sectors` のデータを使用。セクターごとにシーンを分け、そのセクターの騰落率を紹介した後、各主要銘柄の `chart_image_path` を表示し、ニュースを `on_screen_text` で表示しながら変動原因を分析。各銘柄を丁寧に紹介してください。
7. 【prev_ir_tracking】: `prev_ir_analysis` の銘柄ごとにシーンを作成。`chart_image_path` を表示し、変動率や直近ニュースを `on_screen_text` で表示しながら、前回から今回への変動要因(reason_summary)を説明。データがなければスキップ。
8. 【tomorrow_strategy】: `us_tonight_outlook` 内のニュースを具体的に参照し、明日の展望を解説。
9. 【closing】: 今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「明日朝7時のモーニングレポートもお楽しみに！」といった言葉で締めてください。

# 出力形式
各シーンオブジェクトは必ず以下のキーを持ってください:
- scene: 整数（1から開始）
- section_title: 文字列（短いタイトル。例：「本日の日経平均」「注目ニュース：半導体」）
- duration: 秒数
- text: 読み上げるテキスト
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

# 台本作成の鉄則（コンセプト：初心者フレンドリー＆ロジカル）
    1. 【初心者でもわかる比喩】：専門用語（例：流動性、円安メリット、窓開け）が出た際は、身近な例で補足したり、必ずわかりやすく説明してあげてください。
    2. 【情報の相関分析】：単一のデータだけでなく、「米国の金利が上がったから、日本のハイテク株が売られた」のように、複数のデータ（為替×市場、米国×日本）を組み合わせた因果関係を1つ以上述べてください。
    3. 【読み上げ対策（重要）】：ENEOS（エネオス）、LIXIL（リクシル）やNVIDIA（エヌビディア）など、アルファベットの企業名や英単語は、音声合成で一文字ずつ（エル・アイ...等）読まれないよう、必ず読み上げ台本（text）の中では自然なカタカナ表記（例：エネオス、リクシル、エヌビディア、ナスダック）に変換してください。ただし、画面表示用（on_screen_text）はアルファベットのままで構いません。
    4. 【正確な高値表現】：日経平均などの指標が上がっている際、安易に「最高値」と表現しないでください。過去最高を更新した時のみ「史上最高値」を使用し、それ以外は「年初来高値」「〇ヶ月ぶりの高値」「バブル後高値」など、分析データに基づいた正確な期間を添えてください。
    5. 【誠実なぼかし】：明確な理由がない場合は「謎」とせず、「今は材料待ちで市場が様子見をしているようです」や「過熱感から利益確定の売りが出た可能性があります」など、市場心理を推測して伝えてください。
    6. 【具体性】：ニュースは「ある企業が〜」ではなく「トヨタ自動車が〜」と実名を出してください。
    7. 【数値】：株価や騰落率などの数値は「大きく動いた」ではなく「300円安の〇〇円」と具体的に述べてください。また、数値は「38,567.23円」だったら、「3万8500円付近」や「3万8560円」など、耳で聞いてわかりやすい表現に丸めてください。
    8. 【感情の同期】：市場が好調なら「happy/excited」、大幅下落なら「sad/disappointed」など、ニュースの内容に合わせた感情を選択してください。
    9. 【行動指針の提示】：最後に「明日の朝はまず〇〇をチェックしましょう」など、視聴者が次に取るべきアクションを具体的に指示してください。
    10. 【データ不足時の対応】：決算/総会データがない場合、「本日の予定はありません」と事実を伝える。前回紹介銘柄データがない場合、このセクション自体をスキップするか、手短に次へ進む。

出力は純粋なJSON配列のみを返してください。
"""

        attempt = 0
        last_errs = []
        while attempt < max_retries:
            attempt += 1
            try:
                raw = self.client.generate_content(prompt, max_retries=1, use_search=False)
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
                            print(f"🔧 シーン {i} の感情 '{scene['emotion']}' を 'normal' に自動修正しました")
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

                # save file
                out_dir = Path("data/scripts")
                out_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = out_dir / f"scenes_{ts}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(scenes, f, ensure_ascii=False, indent=2)
                print(f"💾 シーンJSONを保存: {filepath}")
                return scenes

            except Exception as e:
                last_errs.append(str(e))
                print(f"🔁 structured scenes generation attempt {attempt} failed: {e}")
                continue

        # 最後にエラーを投げる
        raise RuntimeError(f"structured scenes generation failed after {max_retries} attempts. errors: {last_errs}")
