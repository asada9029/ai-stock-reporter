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
from src.config.video_duration import (
    SCRIPT_GENERATION_MAX_ATTEMPTS,
    apply_duration_policy_to_structure,
    format_duration_prompt_rule,
    format_section_duration_hint,
)
from src.analysis.script_quality import (
    evaluate_script_quality,
    optional_section_keys_to_skip,
)


def _load_characters_config() -> Dict:
    path = Path(__file__).resolve().parent.parent / "config" / "characters.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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
        self.characters = _load_characters_config()

    def _character_prompt_block(self) -> str:
        minori = self.characters.get("minori") or {}
        karin = self.characters.get("karin") or {}
        return f"""
# キャラクター設定（番組の顔）
- 株野みのり（ホスト / speaker=`minori`）: {minori.get('speaking_style') or '敬語。やさしいが芯が硬い。'}
- 相場カリン（パートナー / speaker=`karin`）: {karin.get('speaking_style') or 'タメ口寄りの後輩。旬に飛びつく。'}
※「やさしいのにちょっと尖ってる」トーン。まじめニュース番組にしない。ほのぼのたとえを適宜入れる。

# 二人掛け合い（重要）
- 通常の解説シーンは `speaker: "minori"` の一人語りでよい。
- **opening（フック）・旬ニュース（slot=heat）・closing（締め）** では掛け合いを入れる。
- 掛け合いシーンは `dialogue` 配列を必ず付ける:
  `[{{"speaker":"minori","text":"...","speech_text":"..."}},{{"speaker":"karin","text":"...","speech_text":"..."}}]`
- `text` / `speech_text` は dialogue を連結した全文でもよい（字幕用）。話者切替は dialogue が正。
- 全編二人にはしない。情報ブロックはみのり主導、感情ブロックだけカリンを出す。
"""

    def _news_story_prompt_block(self) -> str:
        return """
# ニュース物語の組み立て（重要）
- `attention_news` の各要素には `slot`（honmei/heat/rotation/support）と `scores`、あれば `lane` / `scope` / `polarity` がある。
- **lane**: `macro`=大局（地合いの主語）、`local`=局所（個別・旬）。honmei は macro 寄り、heat は local 寄り。
- **scope**: `issuer`=当事者1社 → 関連チャート／言及はその1社だけ（同業に広げない）。`theme`=テーマ全体。`unclear`=広げない。
- 1本ずつ並列で終わらせない。流れは「束ねて紹介 → まとめて影響の読み → 明日の立ち回り」。
- slot=honmei は本命としてやや厚め。slot=heat は旬・感情を厚めに。slot=rotation は資金の行き先・違和感として扱う。
- 同じ話題の重複解説は禁止。
- 【図解優先】次のパスがある場合は該当シーンの `target_files` に必ず指定し、文字の羅列より図を見せる。on_screen_text は図の補足を最大2行。
  - `diagrams.news_bundle_path`（ニュース束の導入）
  - `diagrams.impact_flow_path`（影響の読み）
  - `diagrams.market_board_path`（指数/地合いの導入）
  - `diagrams.capital_flow_path`（資金の行き先・セクター概要）
  - `diagrams.checklist_path`（チェック3点。展望セクションで使用）
"""
    @staticmethod
    def _immersive_prompt_appendix(analysis_data: Dict) -> str:
        """classic プロンプトの on_screen / opening 指示を上書きする追記ブロック。"""
        thumb = analysis_data.get("selected_thumbnail_title", "本日の注目ニュース")
        return f"""

# 【immersive 演出モード：以下で on_screen_text / opening の指示をすべて上書き】
- 視聴者は「読む」より「聞く」ことを優先します。詳しい説明は speech_text（読み上げ）に書き、画面は補助ラベルに留めてください。
- on_screen_text は「■」「└」形式は禁止。図解シーンは最大2行の補足。**ニュース／文字中心シーンは3〜5行**で密度を確保（1行のみは禁止）。
  - 1行目: 事実・数値・見出し（例: "S&P500 +0.3%", "日経 3万8500円台"）
  - 2行目以降: 見解・影響・注意点・関連チェック（例: "金利上昇がハイテクに重石", "円安で輸出株に追い風"）
- 各行は短め（目安：1行あたり全角18〜22文字以内）。
- 良い例（ニュース）: ["決算後に急落", "見通し下方修正", "小売セクター波及に注意", "寄り付き反応を確認"]
- 悪い例: 1行だけ、音声の長文をそのまま載せる、箇条書き8行。
- 【opening 上書き】:
    - 挨拶の直後、20〜40秒以内に「今日の米国市場の結論（一言）」と「最大の材料は何か」を speech_text で言い切ること。
    - その直後に「ではまず指数（または市場全体）から確認して、次にニュースを深掘りします」のように自然に次へ繋げてください。
    - opening の on_screen_text は **4〜5行**（寂しい3行だけは避ける）。メニュー8行は禁止。例:
        "米国株: AI決算でハイテク主導高"
        "注目: {thumb[:16]}"
        "関連: エヌビディア／セールスフォース急伸"
        "日本株: 半導体・ソフト関連に波及注目"
        "チェック: 寄り付きの選別反応"
    - opening はシーン分割なしの1シーンでOK。
- 【シーン分割】1画面＝1メッセージ。図解シーンの補足は2行以内。**文字中心／ニュースは3〜5行**を維持し、それ以上ならシーン分割。
- speech_text / text / 数値の正確さ・読み上げカタカナ・初心者向けの深掘りは、classic と同じ基準を維持してください。

- 【注目ニュースの画面（重要）】OG画像は必須ではありません（内容とズレることがあるため）。ニュースの「何の話か」を画面で必ず明確にしてください。
  - 関連銘柄がある場合は、`related_ticker` / `related_company_name` を必ず設定してください（可能なら target_files に関連チャート）。
  - 関連銘柄チャートが無い場合でも、target_files を無理に埋めず、`related_ticker` / `related_company_name` を設定してティッカー/社名カードが出せるようにしてください。
  - 追加キー（任意）: `ticker`, `company_name`（関連銘柄と同じでOK）
- 【チェックリスト図】`diagrams.checklist_path` がある場合、japan_impact_prediction / tomorrow_strategy で `target_files` に指定して画面を厚くする。
"""

    def generate_structured_scenes(
        self,
        video_structure: Dict,
        analysis_data: Dict,
        enriched_data: Optional[Dict] = None,
        max_retries: int = SCRIPT_GENERATION_MAX_ATTEMPTS,
        presentation_mode: str = "classic",
    ) -> List[Dict]:
        """
        LLMに台本＋演出指示（JSON配列）を生成させ、バリデーションして返す。
        """
        video_type = video_structure.get("video_type", "evening_video")
        is_morning = "morning" in video_type
        is_shorts = "shorts" in video_type
        duration_rule = format_duration_prompt_rule()
        section_weight_rule = ""

        if not is_shorts:
            video_structure = apply_duration_policy_to_structure(video_structure)
            skip_section_keys = optional_section_keys_to_skip(analysis_data, video_type)
            section_weight_rule = format_section_duration_hint(video_structure)
        else:
            skip_section_keys = set()

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
あなたは株ニュース解説番組「マイカブ」の動画ディレクター兼台本作家です。
ホストは「株野（かぶの）みのり」。パートナーは「相場カリン」。掛け合いは opening / 旬ニュース / closing で使う。
「初心者でも投資が楽しく、わかりやすくなる」をコンセプトに、情報密度の高い動画シーン配列をJSON形式の配列で出力してください。
昨晩の米国市場の動向を受け、今日の日本市場がどう動くかに焦点を当てます。
{self._character_prompt_block()}
{self._news_story_prompt_block()}

# 動画構成案
{json.dumps(video_structure, ensure_ascii=False, indent=2)}

# 分析データ
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 全般ルール
{duration_rule}
{section_weight_rule}
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
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title`, `snippet`, `slot` (honmei/heat/rotation/support), `scores`, 任意で `lane` / `scope` / `polarity`, `visual_image_path`（OG画像 or 関連銘柄チャート）, `visual_source` ("og"|"chart"), `related_ticker`, `related_company_name` があります。
- `sector_analysis`: 注目セクターデータ。
    - `rankings_screenshot`: 米国業種ランキング表の画像パス。
    - `sectors`: セクターごとの詳細リスト。各要素に `sector_name` (セクター名), `type` (top/bottom), `change` (騰落率), `news` (そのセクターの最新ニュースリスト) があります。
    - `news` の各要素: `title` (見出し), `summary` (要約)
- `jp_tomorrow_outlook`: 明日の日本市場への影響予測に関するニュースリスト。`title` (見出し) と `summary` (要約) があります。
- `next_delivery_info`: 次回の配信予定情報（`date`, `time`, `is_holiday_gap`）。

# セクション別詳細指示
1. 【opening】: 
    - 挨拶の直後、今日の一言結論か違和感（例: 資金の行き先）を短く示し、続けて「まずは市場指数、その次に（サムネイル：{analysis_data.get('selected_thumbnail_title', '本日の注目ニュース')}）」と案内する。
    - 後半メニュー（米国セクター分析、日本市場への影響予測）も触れる。
    - 【重要：on_screen_textの指示】: 以下を1行ずつ箇条書きで表示してください。
        "・米国市場の動向"
        "・米国注目ニュース：{analysis_data.get('selected_thumbnail_title', '本日のトピック')[:12]}..."
        "・米国セクター分析"
        "・日本市場への影響予測"
        "・まとめ"
    - また、このセクションだけシーン分割はなしでお願いします。
2. 【us_market_summary】: 可能なら先に `diagrams.market_board_path` を見せて地合いを一目で示し、その後 S&P500、ナスダック(NASDAQ)、ダウ(DOW)をそれぞれ独立したシーンに分ける。各指数の `chart_image_path` を見せながら、終値(current_price)、前日比(change_percent)、変動原因を分析。
3. 【us_news_highlights】: **束ねて紹介 → 影響の読み** の流れで。
    ※ `attention_news` は選定済み。slot / lane / scope を尊重。
    1. まず `diagrams.news_bundle_path` があればそれを全画面で見せ、slot=honmei と主な heat を短く束ねて紹介。
    2. 続けて `diagrams.impact_flow_path` を見せ、「これらの材料が市場・セクターにどう効くか」を1〜2シーンでまとめて予測。
    3. rotation / `diagrams.capital_flow_path` があれば資金の行き先・違和感として触れる。
    - heat 枠のシーンはカリンとの掛け合い（dialogue）を推奨。
    - `scope=issuer` は関連チャート・言及をその1社だけ（同業に広げない）。`lane=macro` に無理な個別ティッカーカードを付けない。
    - **【ニュース画像】**: 図解を優先。個別 `visual_image_path` は補助。OGは無理に使わない。
4. 【us_sector_analysis】: `diagrams.capital_flow_path` があれば先に見せ、続けて `sector_analysis -> rankings_screenshot` を表示しながら、上昇・下落が顕著だったセクター(`sector_analysis -> sectors`)を紹介した後、シーンを切り替え、挙げたセクターの最新ニュース(`sector_analysis -> sectors -> news`)を`on_screen_text`で表示し、騰落原因を分析。理由が不明な場合は市場心理（利益確定、材料待ち等）を推測。
5. 【japan_impact_prediction】: `jp_tomorrow_outlook` と直前のニュース束を踏まえ、米国→日本の影響を予測。最後に「今日見るべきチェック3点」で締める。`diagrams.checklist_path` があれば `target_files` に指定。注目日本株の予測（例：NVIDIA高→東エレク）、為替の影響。
6. 【closing】: 掛け合いで締め。今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「夜18時のイブニングレポートもお楽しみに！」といった言葉で締めてください。

# 分析データの追加キー
- `diagrams.news_bundle_path` / `impact_flow_path` / `market_board_path` / `capital_flow_path` / `checklist_path`: 図解PNG。あるときは該当セクションで必ず使う。

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
- speaker: 文字列（`"minori"` または `"karin"`。一人語り時）
- dialogue: 任意。掛け合い時は配列。各要素に speaker / text / speech_text

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
    10. 【データ不足時の対応】：対応データが空なら、その旨を長々と説明せず、該当シーンを作らず次セクションへ進む（無言スキップ）。`attention_news` が空の場合のみ「ニュースが取得できませんでした」と述べる。
    11. 【自然な文章構成】：読み上げが不自然に細切れにならないよう、一文一文を適切な長さ（40〜80文字程度）に保ち、意味の区切りで自然に読めるように構成してください。

出力は純粋なJSON配列のみを返してください。
"""
        else:
            # 既存の夜動画用プロンプトを完全に復元
            prompt = f"""
あなたは株ニュース解説番組「マイカブ」の動画ディレクター兼台本作家です。
ホストは「株野（かぶの）みのり」。パートナーは「相場カリン」。掛け合いは opening / 旬ニュース / closing で使う。
「初心者でも投資が楽しく、わかりやすくなる」をコンセプトに、情報密度の高い動画シーン配列をJSON形式の配列で出力してください。
{self._character_prompt_block()}
{self._news_story_prompt_block()}

# 動画構成案
{json.dumps(video_structure, ensure_ascii=False, indent=2)}

# 分析データ（ここにある具体的な数値・名称・内容を必ず使用してください）
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}

# 全般ルール
{duration_rule}
{section_weight_rule}
- 【シーン分割の徹底】: 1シーンに情報を詰め込みすぎないでください。画像（target_files）やテキスト（on_screen_text）が画面内に収まりきらない、あるいは視聴者が理解しにくいと判断した場合は、必ずシーンを分割してください。特に、画像（target_files）があるシーンでは、on_screen_text（画面表示用テキスト）は最大4行（2セット）までとし、それ以上の情報を伝えたい場合は必ずシーンを分割してください（画像がないシーンでは4行を超えても構いません）。
- 【タイトルの形式】：opening以外の各シーンのタイトルは必ず、「セクション名：具体的な内容」という形式にする。openingは「本日のトピック」というタイトルでお願いします。他のシーンのセクション名ですが、market_indiciesなら市場指数, news_highlightsなら注目ニュース, event_calenderなら注目決算スケジュール, sector_overviewならセクター概要, sector_attentionなら[セクター名]注目銘柄, prev_ir_attentionなら前回紹介銘柄の動向, tomorrow_strategyなら今夜の米国市場と明日の展望, closingならまとめでお願いします。ただし、シーン分割をした場合、セクション名を分割してもOKです。例えば「今夜の米国市場」と「明日の展望」で分けるみたいな感じです。
- 【セクションの順番】：なるべく動画構成案通り（opening→market_indices→news_highlights→event_calender→sector_overview→sector_attention→prev_ir_tracking→tomorrow_strategy→closing）にしてください。
- 【画像レイアウト】: 画像が2枚以上の場合は、必ず左右並列（horizontal）にしてください。上下並列（vertical）は使用禁止です。
- 【画像とテキストの併用】: 画像とテキストを同時に表示する場合、画像がメイン、テキストが補足となります。
- 【データ遵守】: 捏造厳禁。分析データにある数値、企業名、ニュース内容のみを根拠にしてください。
- 【専門用語の解説】: 専門用語は初心者にもわかるように簡潔に解説してください。

# 分析データの構造定義（辞書形式）
- `market_indices`: 主要指数の辞書。キーは "NIKKEI", "SP500", "USDJPY"。
    - 各要素: `name` (名称), `current_price` (終値), `change_percent` (前日比%), `chart_image_path` (チャート画像パス)
- `attention_news`: 市場全体の重要ニュースのリスト。各要素に `title`, `snippet`, `slot` (honmei/heat/rotation/support), `scores`, 任意で `lane` (macro/local), `scope` (issuer/theme/unclear), `polarity`, `visual_image_path`, `visual_source` ("og"|"chart"), `related_ticker`, `related_company_name` があります。
- `sector_analysis`: 注目セクターと個別銘柄の統合データ。
    - `rankings_screenshot`: 33業種ランキング表の画像パス。
    - `sectors`: セクターごとの詳細リスト。各要素に `sector_name` (セクター名), `type` (top/bottom), `change` (騰落率), `companies` (主要銘柄・少なめ) があります。
    - `companies` の各要素: `company_name` (社名), `news` (銘柄ニュース), `chart_image_path` (個別チャート画像パス)
- `kessan_schedule`: 注目決算のみ。`image_path` / `image_paths`（最大2ページ）と `data`。空ならセクション自体を作らない。
- `soukai_schedule`: 使わない（株主総会は扱わない）。
- `prev_ir_analysis`: 前回紹介銘柄の追跡結果リスト。
    - 各要素: `company_name` (社名), `change_percent` (騰落率), `recent_news` (直近ニュースリスト), `reason_summary` (変動理由の要約), `chart_image_path` (チャート画像パス)
- `us_tonight_outlook`: 今夜の米国市場の見通しニュースリスト。`attention_news` と同様に `visual_image_path` 等を含む場合があります。
- `next_delivery_info`: 次回の配信予定情報（`date`, `time`, `is_holiday_gap`）。

# セクション別詳細指示
1. 【opening】: 
    - 挨拶の直後、今日の一言結論か違和感を短く示し、「まずは市場指数、その次に（サムネイル：{analysis_data.get('selected_thumbnail_title', '本日の注目ニュース')}）」と案内。
    - 続けて後半メニューも触れる。
    - 【重要：on_screen_textの指示】: 以下を1行ずつ箇条書きで表示してください。
        "・市場の動向"
        "・注目ニュース：{analysis_data.get('selected_thumbnail_title', '本日のトピック')[:12]}..."
        "・注目決算スケジュール"
        "・セクター分析"
        "・注目銘柄のIR"
        "・前回紹介銘柄の動向"
        "・今夜の米国市場と明日の展望"
        "・まとめ"
    - また、このセクションだけシーン分割はなしでお願いします。
2. 【market_indices】: 可能なら先に `diagrams.market_board_path`（日経・S&P・ドル円）を見せる。その後、日経平均(NIKKEI)、S&P500(SP500)、ドル円(USDJPY)をそれぞれ独立したシーンに分ける（数値は `market_indices`）。必ず日経平均から先。チャートがある指数は `chart_image_path` を見せ、ドル円は数値中心でも可。
3. 【news_highlights】: **束ねて紹介 → 影響の読み**。役割は今日の材料（誰が・何が・効き方）。大局の長い地合い説明は指数・セクター側へ寄せ、ここは局所（lane=local / heat）を厚めに。honmei（macro）は短く主語として残す。
    ※ `attention_news` は選定済み。slot / lane / scope を尊重。
    1. `diagrams.news_bundle_path` があれば全画面で見せ、honmei と主な heat を束ねて紹介。
    2. `diagrams.impact_flow_path` を見せ「まとめると市場にどう効くか」を1〜2シーンで予測。
    3. rotation / `diagrams.capital_flow_path` があれば資金の行き先として触れる。
    - heat 枠はカリンとの掛け合い（dialogue）を推奨。
    - `scope=issuer` のニュースは関連チャート・言及をその1社だけに限定（同業に広げない）。
    - **【ニュース画像】**: 図解を優先。個別 visual は補助。
4. 【event_calendar】: 決算のみ。`kessan_schedule.image_paths`（なければ `image_path`）を最大2ページ分、ページごとにシーン化。株主総会は扱わない。`data` が空、または画像が無い場合は **このセクションのシーンを一切作らず、次へ無言で進む**（「予定はありません」「スキップします」等は言わない）。
5. 【sector_overview】: **夜の核。厚めに。** `diagrams.capital_flow_path` があれば先に見せ、続けて `sector_analysis -> rankings_screenshot`。上昇・下落が顕著だったセクターをそれぞれ具体名で挙げ、「なぜ」を短く。news_highlights と同じ話の繰り返し禁止。
6. 【sector_attention】: **任意・薄め。** overview やニュースと重複するなら **シーンを作らず省略してよい**。残すなら「材料で実際に動いた銘柄」を最大1〜2本だけチャート付きで。代表企業の百科事典・丁寧な全銘柄紹介は禁止。
7. 【prev_ir_tracking】: `prev_ir_analysis` の銘柄ごとにシーンを作成。`chart_image_path` を表示し、変動率や直近ニュースを `on_screen_text` で表示しながら、前回から今回への変動要因(reason_summary)を説明。データがなければ **無言スキップ**（言い訳しない）。
8. 【tomorrow_strategy】: `us_tonight_outlook` と本日のニュース束を踏まえ、明日の注目／注意（チェック3点）で締める。**`diagrams.checklist_path` があれば必ず `target_files` に指定**。各ニュースに `visual_image_path` があれば補助で含めてよい。
9. 【closing】: 掛け合いで締め。今回のまとめと次回の配信予告。`next_delivery_info` -> `is_holiday_gap` が True なら「市場がお休みのため少し間が空きます。次回は `date` の `time` 頃に投稿予定です。楽しみにお待ちくださいね」と付け加えてください。もし `next_delivery_info` -> `is_holiday_gap` が False なら最後に「明日朝7時のモーニングレポートもお楽しみに！」といった言葉で締めてください。

# 分析データの追加キー
- `diagrams.news_bundle_path` / `impact_flow_path` / `market_board_path` / `capital_flow_path` / `checklist_path`: 図解PNG。あるときは該当セクションで優先使用。

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
- speaker: 文字列（`"minori"` または `"karin"`。一人語り時）
- dialogue: 任意。掛け合い時は配列。各要素に speaker / text / speech_text

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
    10. 【データ不足時の対応】：決算データが空なら event_calendar シーンを作らない（「予定なし」「スキップ」と言わない）。前回紹介銘柄が空なら無言スキップ。`attention_news` が空の場合のみ「ニュースが取得できませんでした」と述べる。
    11. 【自然な文章構成】：読み上げが不自然に細切れにならないよう、一文一文を適切な長さ（40〜80文字程度）に保ち、意味の区切りで自然に読めるように構成してください。

出力は純粋なJSON配列のみを返してください。
"""

        presentation_mode = normalize_presentation_mode(presentation_mode)
        if is_immersive_mode(presentation_mode, video_type=video_type):
            print("[Mode] 台本生成: immersive（聞き中心・番組感）モード")
            prompt += self._immersive_prompt_appendix(analysis_data)

        attempt = 0
        last_errs = []
        quality_retry_appendix = ""
        while attempt < max_retries:
            attempt += 1
            try:
                current_prompt = prompt + quality_retry_appendix
                raw = self.client.generate_content(
                    current_prompt,
                    max_retries=5,
                    use_search=False,
                    model_role="script",
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
                        quality_retry_appendix += (
                            "\n出力がスキーマに合致していません。"
                            "必ず前述のスキーマ通りのJSON配列のみを返してください。"
                        )
                        continue

                # --- 横型本編: 推定尺・セクション網羅チェック ---
                if not is_shorts:
                    from src.config.video_duration import get_duration_policy

                    quality = evaluate_script_quality(
                        scenes,
                        video_type,
                        skip_optional_section_keys=skip_section_keys,
                    )
                    policy = get_duration_policy(video_type)
                    if quality and policy and not quality.passed:
                        print(
                            f"[WARN] 台本品質不足 (試行 {attempt}/{max_retries}): {quality.summary}"
                        )
                        last_errs.extend(quality.issues)
                        if attempt >= max_retries:
                            raise RuntimeError(
                                f"台本が最低品質ラインを満たしませんでした（{max_retries}回試行）: "
                                f"{quality.summary}"
                            )
                        quality_retry_appendix = quality.build_retry_appendix(policy)
                        continue
                    if quality and policy:
                        print(
                            f"[OK] 台本品質チェック通過: 推定尺={quality.estimated_seconds:.0f}s "
                            f"(最低{policy.min_publish_seconds}s) / シーン数={quality.scene_count}"
                        )

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
