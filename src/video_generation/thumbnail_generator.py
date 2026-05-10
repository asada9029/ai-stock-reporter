"""
サムネイル自動生成モジュール
YouTubeサムネイルを自動生成
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from datetime import datetime


class ThumbnailGenerator:
    """サムネイル生成クラス"""
    
    # サムネイルサイズ（YouTube推奨）
    THUMBNAIL_SIZE = (1280, 720)
    
    # カラーパレット
    COLORS = {
        'morning': {
            'bg_image': 'thumbnail_bg_morning.png',
            'text_main': (255, 255, 255),       # 中：白
            'outline': (120, 63, 0),             # 外：濃いオレンジ色
            'accent': (255, 255, 0),            # アクセント：黄色
            'band': (200, 0, 0, 230)            # 帯：赤（半透明）
        },
        'evening': {
            'bg_image': 'thumbnail_bg_evening.png',
            'text_main': (255, 255, 255),       # 中：白
            'outline': (4, 34, 64),             # 外：濃い紺色
            'accent': (255, 255, 0),            # アクセント：黄色
            'band': (0, 30, 80, 230)            # 帯：濃い青（半透明）
        }
    }
    
    def __init__(self):
        """初期化"""
        self.font_path = self._find_font()
        self.assets_dir = Path(__file__).parent.parent / "assets"
        print("✅ ThumbnailGenerator 初期化完了")
    
    def _find_font(self) -> Optional[str]:
        """日本語フォントを検索"""
        font_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts', 'SourceHanSans-Heavy.otf'), # 一番雰囲気合っている
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts', 'MPLUS1-Bold.ttf'), # ちょっとポップ
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts', 'NotoSansJP-Regular.ttf'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'assets', 'fonts', 'NotoSansJP-Regular.ttf'),
            'C:\\Windows\\Fonts\\msgothic.ttc',
            '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
        ]
        
        for path in font_paths:
            if Path(path).exists():
                return path
        
        return None
    
    def _create_gradient_background(
        self,
        size: Tuple[int, int],
        color_top: Tuple[int, int, int],
        color_bottom: Tuple[int, int, int]
    ) -> Image.Image:
        """グラデーション背景を作成"""
        width, height = size
        gradient = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            ratio = y / height
            color = tuple(
                int(color_top[i] * (1 - ratio) + color_bottom[i] * ratio)
                for i in range(3)
            )
            gradient[y, :] = color
        
        return Image.fromarray(gradient)
    
    def _draw_text_with_shadow(
        self,
        draw: ImageDraw.Draw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill_color: Tuple[int, int, int],
        outline_color: Tuple[int, int, int] = (255, 255, 255),
        outline_width: int = 3,
        shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 180),
        shadow_offset: Tuple[int, int] = (5, 5),
        shadow_blur: int = 2
    ):
        """縁取り＋ドロップシャドウ付きテキストを描画"""
        x, y = position
        sx, sy = shadow_offset
        
        # 1. ドロップシャドウを描画
        # shadow_blur の範囲で影を広げて描画
        for dx in range(-shadow_blur, shadow_blur + 1):
            for dy in range(-shadow_blur, shadow_blur + 1):
                draw.text((x + sx + dx, y + sy + dy), text, font=font, fill=shadow_color)
        
        # 2. 縁取りを描画（元のロジック）
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
        
        # 3. メインテキストを描画
        draw.text((x, y), text, font=font, fill=fill_color)

    def _draw_text_with_double_outline(
        self,
        draw: ImageDraw.Draw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill_color: Tuple[int, int, int],
        inner_outline_color: Tuple[int, int, int],
        outer_outline_color: Tuple[int, int, int] = (0, 0, 0),
        inner_width: int = 3,
        outer_width: int = 6
    ):
        """二重縁取り付きテキストを描画（外側：黒、中間：白、内側：メイン色）"""
        x, y = position
        
        # 1. 大外の縁取り（黒）
        for dx in range(-outer_width, outer_width + 1):
            for dy in range(-outer_width, outer_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=outer_outline_color)
        
        # 2. 中間の縁取り（白）
        for dx in range(-inner_width, inner_width + 1):
            for dy in range(-inner_width, inner_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=inner_outline_color)
        
        # 3. メインテキスト（指定色）
        draw.text((x, y), text, font=font, fill=fill_color)

    def _draw_text_with_outline(
        self,
        draw: ImageDraw.Draw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill_color: Tuple[int, int, int],
        outline_color: Tuple[int, int, int] = (255, 255, 255),
        outline_width: int = 3
    ):
        """縁取り付きテキストを描画"""
        x, y = position
        
        # 縁取り
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
        
        # メインテキスト
        draw.text((x, y), text, font=font, fill=fill_color)

    def _parse_percent_value(self, value) -> Optional[float]:
        """'1.23%' や '+1.23' を float に変換。失敗時は None。"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None

        # 文字列中の数値を抽出（例: '+1.23%', ' 1.23 '）
        m = re.search(r'[-+]?\d+(?:\.\d+)?', value.replace(',', ''))
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    def _nikkei_abs_change_percent(self, analysis_result: Dict) -> Optional[float]:
        """日経の前日比％（絶対値用の元値）。取得・パースできなければ None。"""
        market_indices = analysis_result.get("market_indices", {}) or {}
        nikkei = market_indices.get("NIKKEI", {}) or {}
        return self._parse_percent_value(nikkei.get("change_percent"))

    def _nikkei_hero_allowed(self, analysis_result: Dict) -> bool:
        """
        日経をサムネ主役にしてよいのは、取得データで変動率の絶対値が3.0%以上のときのみ。
        数値が不明なときは出さない（誤表示より安全側）。
        """
        p = self._nikkei_abs_change_percent(analysis_result)
        return p is not None and abs(p) >= 3.0

    def _title_references_nikkei_market(self, title: str) -> bool:
        """
        日経・日本株指数の主役表現が含まれるか（表記ゆれ・指数の『5.2万』等も含む）。
        """
        if not title:
            return False
        if re.search(r"日経|日経平均|ニッケイ|平均株価", title):
            return True
        # 指数レベルの「4.0〜5.9万」表記（月収の「月30万」は除外）
        if re.search(r"(?<!月)(?<![年月])\d+\.\d+万", title):
            return True
        if re.search(r"(?<!月)(?<![年月])[45]\d*\.?\d*万円?台", title):
            return True
        return False

    def _title_mentions_nikkei_or_historical_peak(self, title: str) -> bool:
        """日経主役や『歴史的高値』系の誇張ワードが含まれるか判定。"""
        if not title:
            return False
        if self._title_references_nikkei_market(title):
            return True
        keywords = [
            "歴史的高値", "歴史的最高値", "最高値", "高値更新",
            "史上最高", "新高値", "年初来高値"
        ]
        return any(k in title for k in keywords)

    def _title_mentions_historical_peak(self, title: str) -> bool:
        """『歴史的高値』系ワードが含まれるか判定。"""
        if not title:
            return False
        keywords = [
            "歴史的高値", "歴史的最高値", "史上最高", "最高値", "高値更新", "新高値", "年初来高値"
        ]
        return any(k in title for k in keywords)

    def _has_historical_peak_evidence(self, analysis_result: Dict, main_news_index: int) -> bool:
        """
        タイトルの『高値更新』系表現を許可できる裏取りがあるか判定。
        根拠は attention_news の title/snippet に高値更新を示す語があること。
        """
        attention_news = analysis_result.get("attention_news", []) or []
        if not attention_news:
            return False

        evidence_keywords = [
            "年初来高値", "史上最高値", "過去最高値", "最高値更新", "高値更新",
            "record high", "all-time high", "new high", "hit a high"
        ]

        # メインニュースを最優先で確認し、なければ全体を確認
        check_indices = []
        if isinstance(main_news_index, int) and 0 <= main_news_index < len(attention_news):
            check_indices.append(main_news_index)
        check_indices.extend([i for i in range(len(attention_news)) if i != main_news_index])

        for idx in check_indices:
            news = attention_news[idx] or {}
            blob = f"{news.get('title', '')} {news.get('snippet', '')}".lower()
            if any(k.lower() in blob for k in evidence_keywords):
                return True
        return False

    _INCOME_TEMPLATE_RE = re.compile(
        r"月\s*\d+\s*万|年\s*\d+\s*万|資産\s*\d+\s*倍|稼げる|禁断の術"
    )

    def _has_income_template(self, text: str) -> bool:
        if not text:
            return False
        return bool(self._INCOME_TEMPLATE_RE.search(text))

    def _fallback_safe_title(
        self,
        attention_news: List[Dict],
        *,
        block_nikkei: bool = True,
        block_income_template: bool = True,
    ) -> str:
        """
        条件違反時の安全なフォールバックタイトルを生成。
        日経系・月○万定型を避けてニュース見出しを使う。
        """
        ng_words = ["日経", "日経平均", "NIKKEI", "nikkei", "ニッケイ", "平均株価"]
        for news in attention_news:
            t = news.get("title", "")
            if not t:
                continue
            if block_nikkei and any(w in t for w in ng_words):
                continue
            if block_income_template and self._has_income_template(t):
                continue
            return t
        # 全日経・全日定型などで候補が無いときは指数を出さない安全側へ
        return "本日の株式市場まとめ"

    def _format_market_facts_for_prompt(self, analysis_result: Dict) -> str:
        """LLMに渡す確定市場数値（日経の可否判断用）。"""
        market_indices = analysis_result.get("market_indices", {}) or {}
        lines = []
        nikkei = market_indices.get("NIKKEI")
        if nikkei:
            lines.append(
                f"- 日経平均: 値 {nikkei.get('current_price', '-')} "
                f"前日比 {nikkei.get('change', '-')} ({nikkei.get('change_percent', '-')})"
            )
        sp = market_indices.get("SP500")
        if sp:
            lines.append(
                f"- S&P500: 値 {sp.get('current_price', '-')} "
                f"前日比 {sp.get('change', '-')} ({sp.get('change_percent', '-')})"
            )
        if not lines:
            return "（市場指数データなし。日経・指数を主役にしないこと。）"
        p = self._nikkei_abs_change_percent(analysis_result)
        if p is None:
            lines.append(
                "- 【厳守】日経の変動率がここで確認できないため、タイトルに日経・"
                "日本株指数の水準（〇〇万など）を出さないこと。"
            )
        elif abs(p) < 3.0:
            lines.append(
                f"- 【厳守】日経の変動率は絶対値 {abs(p):.2f}% ＜ 3.0% のため、"
                "タイトルに日経・日本株指数を主役として出さないこと。"
            )
        else:
            lines.append(
                f"- 日経の変動率は絶対値 {abs(p):.2f}% なので、日経を主役にしてよい。"
            )
        return "\n".join(lines)

    def _get_max_index_move_percent(self, analysis_result: Dict) -> float:
        """主要指数の絶対変動率の最大値を返す。"""
        market_indices = analysis_result.get("market_indices", {}) or {}
        max_abs = 0.0
        for data in market_indices.values():
            pct = self._parse_percent_value((data or {}).get("change_percent"))
            if pct is None:
                continue
            max_abs = max(max_abs, abs(pct))
        return max_abs

    def _has_material_news_signal(self, analysis_result: Dict) -> bool:
        """
        中強度ワードの根拠となる材料ニュースがあるか。
        """
        attention_news = analysis_result.get("attention_news", []) or []
        if not attention_news:
            return False
        material_keywords = [
            "決算", "下方修正", "上方修正", "利上げ", "利下げ", "関税", "地政学", "中東", "停戦",
            "cpi", "fomc", "雇用統計", "日銀", "frb", "米雇用", "ガイダンス", "業績"
        ]
        for news in attention_news:
            blob = f"{news.get('title', '')} {news.get('snippet', '')}".lower()
            if any(k in blob for k in material_keywords):
                return True
        return False

    def _sanitize_title_by_evidence(self, title: str, analysis_result: Dict, main_news_index: int) -> str:
        """
        強い表現を根拠に応じて自動で調整する。
        CTRは保ちつつ、言い過ぎを1段弱める。
        """
        if not title:
            return title

        max_move = self._get_max_index_move_percent(analysis_result)
        has_material = self._has_material_news_signal(analysis_result)
        has_peak_evidence = self._has_historical_peak_evidence(analysis_result, main_news_index)

        # A級: 強い表現（根拠が弱ければB級へ）
        strong_to_mid = {
            "歴史的高値": "高値圏",
            "歴史的最高値": "高値圏",
            "史上最高": "高値圏",
            "最高値": "高値圏",
            "高値更新": "上昇基調",
            "新高値": "上昇基調",
            "年初来高値": "上昇基調",
            "暴落": "急落警戒",
            "急騰": "急伸",
            "爆騰": "急伸",
            "爆上げ": "上昇"
        }

        # B級: 中強度（根拠が弱ければC級へ）
        mid_to_safe = {
            "波乱": "警戒",
            "異変": "変化",
            "急変": "変化",
            "急落警戒": "下振れ警戒",
            "急伸": "上昇",
            "上昇基調": "注目"
        }

        adjusted = title

        # 歴史的高値系は裏取り必須
        if not has_peak_evidence:
            for k, v in strong_to_mid.items():
                if k in ["歴史的高値", "歴史的最高値", "史上最高", "最高値", "高値更新", "新高値", "年初来高値"]:
                    adjusted = adjusted.replace(k, v)

        # 変動率が小さいのに「暴落/急騰/爆上げ」は抑制
        if max_move < 2.0:
            for k in ["暴落", "急騰", "爆騰", "爆上げ"]:
                adjusted = adjusted.replace(k, strong_to_mid[k])

        # 材料ニュースが薄い日は中強度ワードも1段弱める
        if not has_material:
            for k, v in mid_to_safe.items():
                adjusted = adjusted.replace(k, v)

        return adjusted
    
    def create_thumbnail_from_analysis(
        self,
        analysis_result: Dict,
        video_type: str = 'evening',
        output_path: str = None
    ) -> Tuple[str, str, List[str]]:
        """
        AI分析結果からサムネイルを自動生成
        Returns: (output_path, title, highlights)
        """
        # --- 履歴の読み込み (previous.jsonと同様の仕組み) ---
        history_file = Path("logs/thumbnail_history.json")
        history_data = []
        if history_file.exists():
            try:
                import json
                with open(history_file, "r", encoding="utf-8") as f:
                    history_data = json.load(f)
            except:
                history_data = []
        
        # 直近10件のタイトルを抽出
        recent_titles = [item.get('title', '') for item in history_data[-10:]]
        history_text = "\n".join([f"- {t}" for t in recent_titles]) if recent_titles else "（履歴なし）"
        # ----------------------------------------------

        # 日付取得
        date = datetime.now().strftime("%Y/%m/%d")
        
        # 注目ニュースの取得
        attention_news = analysis_result.get('attention_news', [])
        
        # LLMを使用してインパクトのあるタイトルとハイライトを選定
        try:
            from src.analysis.gemini_client import GeminiClient
            client = GeminiClient()
            
            # ニュースリストを文字列化
            news_text = ""
            for i, n in enumerate(attention_news):
                news_text += f"{i+1}. {n.get('title', '')}\n"

            market_facts = self._format_market_facts_for_prompt(analysis_result)
            
            prompt = f"""
            以下のニュースリストから、YouTubeのサムネイルとして「今すぐクリックしなければ損をする」ほどのインパクトと、
            「この材料は見逃せない」と思わせる最高のタイトル（1つ）と、概要欄用のハイライト（3つ）を生成してください。

            【確定市場データ（タイトルの数値・主役判断はこれに従う。ニュース記事と矛盾したら必ずこちらを優先）】
            {market_facts}

            【ニュースリスト】
            {news_text}

            【過去のタイトル履歴（これらと似た表現・単語は厳禁）】
            {history_text}

            【ニュースの採用優先順位】
            タイトルに採用するメインニュースは、以下の「異常値」を基準に選定してください：
            1. **【特級：歴史的節目】**: 
               - **「史上最高値」は、過去の全ての記録を塗り替えた時のみ使用してください。**
               - それ以外は「年初来高値（今年一番）」「〇ヶ月ぶり高値」「昨年来高値」など、期間を正確に表現してください。
            2. **【A級：異常な変動】**: 
               - **株価指数（日経・ナスダック等）**: 3.0%以上の変動
               - **個別銘柄**: 5.0%以上の変動（決算、ストップ高/安、材料視）
               - **為替（ドル円）**: 1.5円以上の急騰/急落
            3. **【B級：サプライズ指標】**: 予想を大きく裏切るCPI、雇用統計、金利政策決定。
            ※重要：日経平均は増減が3.0%未満なら主役にしないこと。上記3%〜5%以上動いているトピックを最優先で選ぶこと。

            【リライトの指針：サムネイル用タイトル（title）】
            1. **主語の明示（必須）**:
               - 「何が」起きているのかを明確にしてください。
               - 悪い例：「1300円の悪夢」「2000円安で拾う」
               - 良い例：「日経平均1300円の悪夢」「米国株2000円安は絶好の買場」「テスラ6000億の衝撃」

            2. **数値の正確性と確定値の優先（最重要）**:
               - ニュース記事（スニペット）内の数値と、市場データ（指数の終値等）に乖離がある場合は、**必ず最新の市場データ数値を優先**してください。
               - 特に日経平均の騰落幅などは、古いニュース記事の数字を拾わず、現在の正確な数値を反映させてください。
               - **ただし、重要なニュースであれば具体的な数値がなくても構いません。** 数値を入れることよりも、ニュースの重大さやインパクトを伝えることを優先してください。

            3. **訴求の多様化（テンプレ禁止）**:
               - 「月○万」「年○万」「資産○倍」「稼げる」「禁断の術」など、**定型的な金額訴求は使わないこと**（クリック率のために似た構文を繰り返さない）。
               - 代わりに、ニュース固有の固有名詞・出来事・対立構造（誰が・何を・市場にどう効くか）を短く尖らせる。

            4. **事実（異常値）に基づく選定（最優先）**:
               - ニュースリストの中で、「実際に大きく動いた数値」や「今日初めて出た重大な事実」を主役にしてください。
               - 市場が動いていないのに「日経〇万突破！」や「資産爆増」といった、根拠のない将来予測や定型文を使い回すことは**厳禁**です。
               - 変化がない市場（日経平均が横ばい等）は、パワーワードであってもサムネイルに採用しないでください。

            5. **トピック重複の完全排除（脱・マンネリ）**:
               - 【過去のタイトル履歴】を1つずつ確認し、**同じキーワード（例：150兆円、富へのカギ、金脈、AI王者、日経〇万）や同じ構成のタイトルを生成することを絶対に避けてください。**
               - 直近3回以内のタイトルと「パッと見で同じ動画」だと思われたら失敗です。
               - リストの中に、まだサムネイルにしていない「新鮮な切り口のニュース」があれば、たとえ地味に見えてもそちらを鋭くリライトして採用してください。

            6. **知名度の低い専門用語のみを翻訳・補足**:
               - 「ISM」「CPI」「PCE」「FOMC」など、一般層に馴染みの薄い指標名のみを、直感的な言葉（物価、景気、金利、買い時）に翻訳してください。
               - ニュースを単なる「出来事」として扱わず、「投資家の財布にどう影響するか」を強調してください。

            7. **「攻め」と「守り」の使い分け**:
               - ニュースの性質（好材料か悪材料か）を見極め、ポジティブな「期待」かネガティブな「警告」かを明確に打ち出してください。

            8. **構成**:
               - 最も強いキーワードを【】で囲み、続く文章で「期待」や「危機感」を煽ってください。文字数：21文字以内。

            【リライトの指針：概要欄用ハイライト（highlights）】
               - タイトル以外の重要ニュースから3つ選定。各17文字以内。
               - 「自分の資産にどう影響するか」を投資家目線で鋭く記述。
               - 「月○万」「年○万」「資産○倍」などの定型はハイライトでも使わないこと。

            【キャラクターの感情（emotion）】
               - タイトルの内容（ポジティブなら happy/excited, 危機なら surprised/sad等）に合わせ、視聴者の共感を得やすい感情を選択。
               - 選択肢：normal, angry, happy, sad, surprised, excited, disappointed

            【出力形式】
            以下のJSON形式のみ。
            {{
                "title": "タイトル文字列",
                "highlights": ["ハイライト1", "ハイライト2", "ハイライト3"],
                "main_news_index": ニュースリストの何番目か(0開始の数値),
                "highlight_indices": [ハイライト1のインデックス, ハイライト2のインデックス, ハイライト3のインデックス],
                "emotion": "感情名"
            }}
            """
            
            res = client.generate_content(prompt, use_search=False, model_role="lite")
            # JSON抽出
            import json
            m = re.search(r'\{.*\}', res, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                title = data.get('title', '')
                highlights = data.get('highlights', [])
                emotion = data.get('emotion', 'happy')
                
                # インデックス情報の保持
                main_news_index = data.get('main_news_index', 0)
                highlight_indices = data.get('highlight_indices', [])

                # --- 履歴の保存 ---
                history_data.append({
                    "date": datetime.now().isoformat(),
                    "video_type": video_type,
                    "title": title
                })
                # 直近100件程度に制限して保存
                history_file.parent.mkdir(parents=True, exist_ok=True)
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(history_data[-100:], f, ensure_ascii=False, indent=2)
                # -----------------
            else:
                raise ValueError("JSON not found")
                
        except Exception as e:
            print(f"⚠️ LLMによるタイトル選定失敗: {e}。フォールバックロジックを使用します。")
            # フォールバック（既存のロジック）
            if attention_news:
                title = attention_news[0].get('title', '本日の株式市場まとめ')
                highlights = [n.get('title', '') for n in attention_news[1:4]]
                main_news_index = 0
                highlight_indices = [1, 2, 3]
            else:
                title = "本日の株式市場まとめ"
                highlights = []
                main_news_index = 0
                highlight_indices = []
            emotion = 'happy'

        # 生成結果の最終バリデーション:
        # 「日経を主役にしない条件」をコード側で強制し、LLM逸脱を防ぐ
        if not self._nikkei_hero_allowed(analysis_result) and self._title_references_nikkei_market(title):
            print("⚠️ 日経の変動が3.0%未満または未取得のため、日経・指数主役のタイトルを差し替えます。")
            title = self._fallback_safe_title(attention_news, block_nikkei=True, block_income_template=True)
            main_news_index = 0
            for idx, news in enumerate(attention_news):
                if news.get("title", "") == title:
                    main_news_index = idx
                    break
            emotion = 'normal'

        # 「歴史的高値」系ワードは、ニュース側で高値更新の裏取りがある場合のみ許可
        if self._title_mentions_historical_peak(title) and not self._has_historical_peak_evidence(analysis_result, main_news_index):
            print("⚠️ 高値更新の裏取りがないため、歴史的高値系タイトルを差し替えます。")
            title = self._fallback_safe_title(attention_news, block_nikkei=not self._nikkei_hero_allowed(analysis_result), block_income_template=True)
            main_news_index = 0
            for idx, news in enumerate(attention_news):
                if news.get("title", "") == title:
                    main_news_index = idx
                    break
            emotion = 'normal'

        # 「月○万」等の定型が残った場合は差し替え
        if self._has_income_template(title):
            print("⚠️ 月○万などの定型表現のため、タイトルを差し替えます。")
            title = self._fallback_safe_title(attention_news, block_nikkei=not self._nikkei_hero_allowed(analysis_result), block_income_template=True)
            main_news_index = 0
            for idx, news in enumerate(attention_news):
                if news.get("title", "") == title:
                    main_news_index = idx
                    break
            emotion = 'normal'

        # 強い表現を、根拠に合わせて1段階調整（CTRと正確性の両立）
        title = self._sanitize_title_by_evidence(title, analysis_result, main_news_index)

        # サニタイズ後に日経主役が復活しないよう再チェック
        if not self._nikkei_hero_allowed(analysis_result) and self._title_references_nikkei_market(title):
            print("⚠️ 調整後も日経主役が検出されたため、タイトルを差し替えます。")
            title = self._fallback_safe_title(attention_news, block_nikkei=True, block_income_template=True)
            main_news_index = 0
            for idx, news in enumerate(attention_news):
                if news.get("title", "") == title:
                    main_news_index = idx
                    break
            emotion = 'normal'

        # タイトル文字数制限（最終確認）
        if len(title) > 23:
            title = title[:22] + "…"

        # ハイライトの月○万定型をニュース見出しへ差し替え
        hi = highlight_indices if isinstance(highlight_indices, list) else []
        fixed_highlights: List[str] = []
        for i, h in enumerate(highlights):
            if self._has_income_template(h):
                idx = hi[i] if i < len(hi) and isinstance(hi[i], int) else None
                if idx is not None and 0 <= idx < len(attention_news):
                    fixed_highlights.append(
                        attention_news[idx].get("title", "最新の市場動向をチェック")
                    )
                else:
                    fixed_highlights.append("最新の市場動向をチェック")
            else:
                fixed_highlights.append(h)
        highlights = fixed_highlights
            
        # ハイライト文字数制限（最終確認）
        highlights = [h[:16] + "…" if len(h) > 17 else h for h in highlights]
        while len(highlights) < 3:
            highlights.append("最新の市場動向をチェック")
            
        # サムネイル作成
        path = self.create_thumbnail(
            title=title,
            date=date,
            highlights=[], # サムネイル画像にはハイライトを描画しない
            video_type='evening' if 'evening' in video_type else 'morning',
            output_path=output_path,
            emotion=emotion
        )
        return path, title, highlights, main_news_index, highlight_indices

    def create_thumbnail(
        self,
        title: str,
        date: str,
        highlights: List[str],
        video_type: str = 'morning',
        output_path: str = None,
        emotion: str = 'happy'
    ) -> str:
        """
        サムネイルを作成
        """
        # カラーパレット取得
        colors = self.COLORS.get(video_type, self.COLORS['morning'])
        
        # 背景作成
        bg_name = colors.get('bg_image')
        bg_path = self.assets_dir / "images" / bg_name if bg_name else None
        
        if bg_path and bg_path.exists():
            try:
                img = Image.open(bg_path).convert("RGBA")
                img = img.resize(self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"⚠️ 背景画像読み込みエラー: {e}")
                img = self._create_gradient_background(self.THUMBNAIL_SIZE, (30, 30, 30), (10, 10, 10))
        else:
            # フォールバック: グラデーション背景
            img = self._create_gradient_background(
                self.THUMBNAIL_SIZE,
                colors.get('background_top', (30, 30, 30)),
                colors.get('background_bottom', (10, 10, 10))
            )
        
        # キャラクター画像の追加（右側）
        char_filename = f"{emotion}.png"
        char_path = self.assets_dir / "images" / char_filename
        if not char_path.exists():
            char_path = self.assets_dir / "images" / "happy.png"
        if not char_path.exists():
            char_path = self.assets_dir / "images" / "normal.png"
            
        char_w = 0 # キャラクターの幅を保持
        if char_path.exists():
            try:
                char_img = Image.open(char_path).convert("RGBA")
                # アスペクト比を維持してリサイズ（高さの80%程度）
                h = int(self.THUMBNAIL_SIZE[1] * 0.8)
                char_w = int(char_img.width * (h / char_img.height))
                char_img = char_img.resize((char_w, h), Image.Resampling.LANCZOS)
                
                # 右下に配置
                img.paste(char_img, (self.THUMBNAIL_SIZE[0] - char_w + 40, self.THUMBNAIL_SIZE[1] - h), char_img)
            except Exception as e:
                print(f"⚠️ キャラクター画像合成エラー: {e}")

        draw = ImageDraw.Draw(img)
        
        # フォント設定
        try:
            if self.font_path:
                font_title = ImageFont.truetype(self.font_path, 95) # 80 -> 95
                font_date = ImageFont.truetype(self.font_path, 45)
                font_highlight = ImageFont.truetype(self.font_path, 48) # 45 -> 48
                font_tag = ImageFont.truetype(self.font_path, 35)
            else:
                font_title = font_date = font_highlight = font_tag = ImageFont.load_default()
        except Exception as e:
            print(f"⚠️ フォント読み込みエラー: {e}")
            font_title = font_date = font_highlight = font_tag = ImageFont.load_default()
        
        # 日付タグ（右上に移動）
        tag_text = f"{date}"
        tag_bbox = draw.textbbox((0, 0), tag_text, font=font_date)
        tag_width = tag_bbox[2] - tag_bbox[0]
        tag_height = tag_bbox[3] - tag_bbox[1]
        
        # 配置を右上に変更
        tag_x = self.THUMBNAIL_SIZE[0] - tag_width - 60
        tag_y = 30
        tag_padding = 20
        
        # 日付テキスト (縁取り文字)
        self._draw_text_with_shadow(
            draw, (tag_x, tag_y), tag_text,
            font_date, colors['text_main'], colors['outline'], 4
        )
        
        # メインタイトル（中央寄り、巨大化）
        title_y = 180
        title_x = 60
        
        # タイトルを改行処理（1行7文字まで、最大3行）
        max_chars_per_line = 7
        
        # 【】で囲まれた部分を抽出して色を変える準備
        accent_match = re.search(r'【(.*?)】', title)
        accent_text = accent_match.group(1) if accent_match else None
        
        # 表示用タイトル（【】を削除）
        display_title = title.replace('【', '').replace('】', '')
        
        # 改行処理
        lines = []
        for i in range(0, len(display_title), max_chars_per_line):
            lines.append(display_title[i:i+max_chars_per_line])
        
        # フォントサイズをさらに大きく (95 -> 130)
        try:
            if self.font_path:
                font_title = ImageFont.truetype(self.font_path, 130)
            else:
                font_title = ImageFont.load_default()
        except:
            font_title = ImageFont.load_default()

        # 帯（座布団）を描画
        title_outline = colors.get('outline', (120, 63, 0))
        band_color = colors.get('band', (0, 0, 0, 200))
        accent_color = colors.get('accent', (255, 255, 0))
        
        # 帯の右端をキャラの左側に合わせる（キャラがいない場合は画面右端付近まで）
        band_right_x = self.THUMBNAIL_SIZE[0] - char_w + 20 if char_w > 0 else self.THUMBNAIL_SIZE[0] - 100
        
        # --- 1. すべての行の「帯（座布団）」を先に描画 ---
        for i, line in enumerate(lines[:3]):
            y = title_y + i * 150
            
            # テキストの高さだけ取得
            bbox = draw.textbbox((title_x, y), line, font=font_title)
            text_h = bbox[3] - bbox[1]
            
            # 帯を「左端からキャラの左」まで描画（四角形）
            draw.rectangle(
                [30, y + 20, band_right_x + 100, y + text_h + 70],
                fill=band_color
            )
            
        # --- 2. その後にすべての行の「テキスト」を描画 ---
        # 元のタイトル（【】あり）をスキャンして、各文字の色を決定する
        # display_title（【】なし）の各文字に対応する色リストを作成
        color_list = []
        is_accent_zone = False
        for char in title:
            if char == '【':
                is_accent_zone = True
                continue
            elif char == '】':
                is_accent_zone = False
                continue
            
            # 【】以外の文字に対して色を割り当て
            color_list.append(accent_color if is_accent_zone else colors['text_main'])

        char_idx = 0
        for i, line in enumerate(lines[:3]):
            y = title_y + i * 150
            
            # 1文字ずつ描画して色を変える
            current_x = title_x
            for char in line:
                # color_list からこの文字に対応する色を取得
                char_color = color_list[char_idx] if char_idx < len(color_list) else colors['text_main']
                
                self._draw_text_with_shadow(
                    draw, (current_x, y), char,
                    font_title, char_color, title_outline, 6,
                    shadow_offset=(8, 8), shadow_blur=4
                )
                # 次の文字の開始位置
                char_bbox = draw.textbbox((0, 0), char, font=font_title)
                current_x += char_bbox[2] - char_bbox[0]
                char_idx += 1

        # 保存
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"output/thumbnail_{video_type}_{timestamp}.png"
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        img.save(output_file, quality=95)
        
        print(f"💾 サムネイル保存: {output_file}")
        return str(output_file)
    
    def create_simple_thumbnail(
        self,
        main_text: str,
        sub_text: str = None,
        video_type: str = 'morning',
        output_path: str = None
    ) -> str:
        """
        シンプルなサムネイルを作成
        """
        highlights = [sub_text] if sub_text else []
        date = datetime.now().strftime("%Y/%m/%d")
        
        return self.create_thumbnail(
            title=main_text,
            date=date,
            highlights=highlights,
            video_type=video_type,
            output_path=output_path
        )


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🖼️  ThumbnailGenerator テスト")
    print("="*60 + "\n")
    
    try:
        generator = ThumbnailGenerator()
        
        # テスト1: 朝の動画サムネイル
        print("\n=== テスト1: 朝の動画サムネイル ===")
        
        thumbnail1 = generator.create_thumbnail(
            title="【米国株急変】！？トランプ発言の衝撃",
            date="2025/12/1",
            highlights=[],
            video_type='morning',
            output_path="output/test_morning.png",
            emotion='surprised'
        )
        
        # テスト2: 夜の動画サムネイル
        print("\n=== テスト2: 夜の動画サムネイル ===")
        
        thumbnail2 = generator.create_thumbnail(
            title="【日本株暴落】の危機！？米大手解約停止",
            date="2025/12/1",
            highlights=[],
            video_type='evening',
            output_path="output/test_evening.png",
            emotion='sad'
        )
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        print("\n生成されたファイル:")
        print("  - output/test_morning.png")
        print("  - output/test_evening.png")
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
