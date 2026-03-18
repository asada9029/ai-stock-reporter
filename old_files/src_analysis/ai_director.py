"""
AIディレクター（最重要モジュール）
動画の構成・内容を完全にAIが主導で決定する
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from src.analysis.gemini_client import GeminiClient


class AIDirector:
    """AI主導の動画ディレクター"""
    
    # 基本動画フォーマット（固定構成）
    BASE_VIDEO_STRUCTURE = {
        "morning": {
            "total_duration": 480,
            "sections": [
                {"name": "opening", "duration": 20, "required": True},
                {"name": "us_market_summary", "duration": 90, "required": True},
                {"name": "us_news_highlights", "duration": 120, "required": True},
                {"name": "us_sector_analysis", "duration": 110, "required": True},
                {"name": "japan_impact_prediction", "duration": 120, "required": True},
                {"name": "closing", "duration": 20, "required": True}
            ]
        },
        "evening": {
            "total_duration": 420,  # 7分
            "sections": [
                {"name": "opening", "duration": 30, "required": True},
                {"name": "japan_market", "duration": 90, "required": True},
                {"name": "sector_analysis", "duration": 120, "required": True},
                {"name": "after_hours_ir", "duration": 60, "required": False},
                {"name": "top_stocks", "duration": 60, "required": False},
                {"name": "tomorrow_outlook", "duration": 30, "required": True},
                {"name": "closing", "duration": 30, "required": True}
            ]
        }
    }
    
    # 全33業種のリスト
    ALL_SECTORS = [
        "水産・農林業", "鉱業", "建設業", "食料品", "繊維製品",
        "パルプ・紙", "化学", "医薬品", "石油・石炭製品", "ゴム製品",
        "ガラス・土石製品", "鉄鋼", "非鉄金属", "金属製品", "機械",
        "電気機器", "輸送用機器", "精密機器", "その他製品", "電気・ガス業",
        "陸運業", "海運業", "空運業", "倉庫・運輸関連業", "情報・通信業",
        "卸売業", "小売業", "銀行業", "証券、商品先物取引業", "保険業",
        "その他金融業", "不動産業", "サービス業"
    ]
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """
        初期化
        
        Args:
            gemini_client: GeminiClientインスタンス（Noneの場合は自動生成）
        """
        self.client = gemini_client or GeminiClient(
            # model_name=GeminiClient.MODEL_FLASH,
            enable_search=True
        )
        
        print("✅ AIディレクター初期化完了")
    
    def conduct_comprehensive_research(
        self,
        base_data: Dict,
        video_type: str = "morning"
    ) -> Dict:
        """
        Step 1: AI主導の包括的調査（ゼロベース）⭐最重要⭐
        
        Args:
            base_data: 基礎データ（市場データ、イベントヒント）
            video_type: 動画タイプ ("morning" or "evening")
        
        Returns:
            Dict: 調査結果
        """
        print("\n" + "="*60)
        print("🔍 Step 1: AI主導の包括的調査を開始")
        print("="*60)
        
        current_time = datetime.now()
        is_morning = video_type == "morning"
        
        # 調査プロンプトの構築
        research_prompt = self._build_research_prompt(
            base_data, 
            video_type,
            current_time
        )
        
        print("\n📡 Web Searchで情報収集中...")
        print("   - 過去24時間の日本株ニュース")
        print("   - 全33業種のセクター別動向")
        if not is_morning:
            print("   - 引け後（15時以降）のIR情報")
        print("   - 米国市場の重要イベント")
        print("   - 日銀・政府の発表")
        
        try:
            # Web Searchを使用して調査
            research_result = self.client.generate_json_with_search(
                research_prompt,
                max_retries=3
            )
            
            print("\n✅ 調査完了")
            print(f"   - 発見したニュース: {len(research_result.get('news', []))}件")
            print(f"   - 注目セクター候補: {len(research_result.get('notable_sectors', []))}件")
            
            return research_result
            
        except Exception as e:
            print(f"\n❌ 調査エラー: {e}")
            raise
    
    def _build_research_prompt(
        self,
        base_data: Dict,
        video_type: str,
        current_time: datetime
    ) -> str:
        """
        調査用プロンプトを構築
        
        Args:
            base_data: 基礎データ
            video_type: 動画タイプ
            current_time: 現在時刻
        
        Returns:
            str: プロンプト
        """
        is_morning = video_type == "morning"
        time_str = current_time.strftime("%Y年%m月%d日 %H:%M")
        
        if is_morning:
            prompt = f"""
あなたは株式市場の専門家です。以下の調査を**Web検索を活用して**実施してください。
朝の動画（モーニングレポート）向けに、昨晩の米国市場の動向と日本市場への影響を重点的に調査します。
個別銘柄よりも、市場全体のニュース、セクター別の騰落原因、日本市場への波及効果を深掘りしてください。

# 現在時刻
{time_str}

# 基礎データ（参考情報）
{json.dumps(base_data, ensure_ascii=False, indent=2)}

# 調査タスク

## 1. 昨晩の米国市場サマリー検索
以下のキーワードで**必ず検索**してください：
- "米国株 昨晩 サマリー {current_time.strftime('%Y年%m月%d日')}"
- "S&P500 ナスダック ダウ 終値 理由"
- "FRB発言 経済指標 昨晩 影響"

## 2. 米国市場の重要ニュース検索（深掘り）
- "米国 経済ニュース 政治 国際情勢 技術動向 過去12時間"
- "米国株式市場に影響を与えたニュース 詳細"
- カテゴリ別（経済、政治、国際、技術）に、市場への影響分析を含めて調査してください。

## 3. 米国セクター別騰落原因の調査
- "米国市場 セクター別騰落率 理由"
- "ヒートマップ 米国株 昨晩 分析"
- 上昇・下落が顕著だったセクターについて、その背景（マクロ経済、業界ニュースなど）を特定してください。理由が不明確な場合は「材料待ち」「過熱感」などの市場心理を調査。

## 4. 日本市場への波及効果・影響予測
- "シカゴ日経先物 終値"
- "ADR 日本株 動向"
- "米国株の動きを受けた今日の日本株の見通し"
- "ドル円 為替 昨晩の動きと輸出株への影響"
- 具体的な日本銘柄への波及例（例：米半導体高→東エレク、アドバンテストなど）を調査。

# 出力形式（必ずJSON形式で）
{{
  "search_timestamp": "{time_str}",
  "us_market": {{
    "summary": "米国市場全体の動き（200文字程度）",
    "indices": [
      {{"name": "S&P500", "value": "数値", "change": "騰落"}},
      {{"name": "NASDAQ", "value": "数値", "change": "騰落"}},
      {{"name": "DOW", "value": "数値", "change": "騰落"}}
    ],
    "reasons": ["理由1", "理由2"]
  }},
  "news_highlights": [
    {{
      "title": "ニュースタイトル",
      "summary": "詳細な要約",
      "category": "経済/政治/国際/技術",
      "importance": "high/medium",
      "market_impact_analysis": "株式市場への具体的な影響分析"
    }}
  ],
  "sector_analysis": [
    {{
      "sector": "セクター名",
      "trend": "上昇/下落",
      "change_percent": "数値",
      "reason_analysis": "なぜその状況になったのかの詳細な原因分析（不明なら市場心理を推測）"
    }}
  ],
  "japan_impact": {{
    "prediction": "日本市場への詳細な波及予測",
    "notable_stocks": [
      {{"stock": "銘柄名", "reason": "米国市場やニュースとの具体的な関連性"}}
    ],
    "forex_analysis": "為替の動きと日本市場（輸出・輸入株など）への影響"
  }},
  "market_sentiment": "ポジティブ/ネガティブ/中立",
  "summary": "本日の市場全体の要約"
}}

# 重要事項
- **必ずWeb検索を使用**して最新情報を取得してください
- 見つからない場合は"情報なし"ではなく、別のキーワードで再検索してください
- 信頼できる情報源（日経新聞、ロイター、Bloomberg等）を優先してください
- 初心者向けに分かりやすい説明を心がけてください
"""
        else:
            prompt = f"""
あなたは株式市場の専門家です。以下の調査を**Web検索を活用して**実施してください。
夕方の動画（イブニングレポート）向けに、本日の日本市場の動向を重点的に調査します。

# 現在時刻
{time_str}

# 基礎データ（参考情報）
{json.dumps(base_data, ensure_ascii=False, indent=2)}

# 調査タスク

## 1. 過去24時間の日本株市場ニュース検索
以下のキーワードで**必ず検索**してください：
- "日経平均 {current_time.strftime('%Y年%m月%d日')}"
- "東京株式市場 今日"
- "株式市場 ニュース 過去24時間"

## 2. 全33業種のセクター別ニュース検索
以下の業種について、**直近の重要なニュース**を検索してください：
{', '.join(self.ALL_SECTORS[:10])}... など全33業種

特に以下の業種は詳細に調査：
- 半導体関連（電気機器）
- 自動車（輸送用機器）
- 銀行、証券
- 情報・通信

## 3. 引け後IR情報の検索
以下を検索してください：
- "決算発表 15時以降 今日"
- "IR 適時開示 本日"
- "引け後 決算 日本企業"

## 4. 日銀・政府の発表検索
- "日銀 発表 {current_time.strftime('%Y年%m月')}"
- "金融政策 日本"
- "経済対策 政府"

# 出力形式（必ずJSON形式で）

{{
  "search_timestamp": "{time_str}",
  "news": [
    {{
      "title": "ニュースタイトル",
      "summary": "要約（100文字程度）",
      "source": "情報源",
      "category": "市場全体/セクター/個別銘柄/IR/経済指標",
      "importance": "high/medium/low",
      "affected_sectors": ["セクター名"],
      "affected_stocks": ["銘柄名（コード）"],
      "timestamp": "発表日時"
    }}
  ],
  "notable_sectors": [
    {{
      "sector": "セクター名",
      "reason": "注目理由",
      "news_count": 件数,
      "trend": "上昇/下落/横ばい",
      "key_points": ["ポイント1", "ポイント2"]
    }}
  ],
  "key_events": [
    {{
      "event": "イベント名",
      "impact": "影響の説明",
      "importance": "critical/high/medium"
    }}
  ],
  "market_sentiment": "ポジティブ/ネガティブ/中立",
  "summary": "本日の市場全体の要約（200文字程度）"
}}

# 重要事項
- **必ずWeb検索を使用**して最新情報を取得してください
- 見つからない場合は"情報なし"ではなく、別のキーワードで再検索してください
- 信頼できる情報源（日経新聞、ロイター、Bloomberg等）を優先してください
- 初心者向けに分かりやすい説明を心がけてください
"""

    
    def analyze_and_select(
        self,
        research_result: Dict,
        base_data: Dict,
        video_type: str = "morning"
    ) -> Dict:
        """
        Step 2: 総合分析と注目セクター・銘柄の選定
        
        Args:
            research_result: 調査結果
            base_data: 基礎データ
            video_type: 動画タイプ
        
        Returns:
            Dict: 分析結果
        """
        print("\n" + "="*60)
        print("📊 Step 2: 総合分析と選定")
        print("="*60)
        
        analysis_prompt = f"""
以下の調査結果と基礎データを統合して、動画で取り上げるべき内容を決定してください。

# 調査結果
{json.dumps(research_result, ensure_ascii=False, indent=2)}

# 基礎データ
{json.dumps(base_data, ensure_ascii=False, indent=2)}

# タスク
1. **今日の最重要トピック**を3つ選定
2. **注目セクター**を3つ選定（なぜ動いたかの理由も）
3. **注目銘柄**を5-10銘柄選定
4. 各セクションで取り上げるべき内容の優先順位付け

# 選定基準
- 初心者にとって分かりやすく重要な情報
- 市場全体に影響を与える情報
- 具体的な数値や事実がある情報
- 複数のソースで確認できる信頼性の高い情報

# 出力形式（JSON）
{{
  "top_topics": [
    {{
      "topic": "トピック名",
      "summary": "説明（150文字程度）",
      "importance_reason": "なぜ重要か",
      "beginner_explanation": "初心者向け補足説明"
    }}
  ],
  "selected_sectors": [
    {{
      "sector": "セクター名",
      "selection_reason": "選定理由",
      "price_movement": {{
        "current": 数値,
        "change": 数値,
        "change_percent": 数値
      }},
      "why_moved": "なぜ動いたか（具体的に）",
      "key_stocks": ["銘柄1", "銘柄2", "銘柄3"]
    }}
  ],
  "featured_stocks": [
    {{
      "stock": "銘柄名（コード）",
      "reason": "注目理由",
      "category": "値上がり/値下がり/出来高/決算/IR"
    }}
  ],
  "overall_analysis": "本日の総合分析（300文字程度）"
}}
"""
        
        try:
            analysis_result = self.client.generate_json(
                analysis_prompt,
                max_retries=3,
                use_search=False  # 分析フェーズでは検索不要
            )
            
            print("\n✅ 分析完了")
            print(f"   - 最重要トピック: {len(analysis_result.get('top_topics', []))}件")
            print(f"   - 注目セクター: {len(analysis_result.get('selected_sectors', []))}件")
            print(f"   - 注目銘柄: {len(analysis_result.get('featured_stocks', []))}件")
            
            return analysis_result
            
        except Exception as e:
            print(f"\n❌ 分析エラー: {e}")
            raise
    
    def decide_video_structure(
        self,
        analysis_result: Dict,
        video_type: str = "morning"
    ) -> Dict:
        """
        Step 3: 動画構成の決定
        
        Args:
            analysis_result: 分析結果
            video_type: 動画タイプ
        
        Returns:
            Dict: 動画構成
        """
        print("\n" + "="*60)
        print("🎬 Step 3: 動画構成の決定")
        print("="*60)
        
        base_structure = self.BASE_VIDEO_STRUCTURE[video_type]
        
        structure_prompt = f"""
以下の分析結果を基に、動画の構成を決定してください。

# 分析結果
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}

# 基本フォーマット
{json.dumps(base_structure, ensure_ascii=False, indent=2)}

# タスク
1. 基本フォーマットを基に、各セクションの内容を決定
2. 必要に応じてセクションの時間配分を調整（±20秒程度）
3. 取り上げる情報が少ない場合は、オプションセクションを削除
4. 総時間が7分（420秒）前後になるように調整

# 出力形式（JSON）
{{
  "total_duration": 420,
  "sections": [
    {{
      "name": "opening",
      "duration": 30,
      "content": {{
        "main_message": "今日のメインメッセージ",
        "topics_to_mention": ["トピック1", "トピック2"]
      }}
    }},
    {{
      "name": "us_market",
      "duration": 90,
      "content": {{
        "indices": ["ダウ", "ナスダック", "S&P500"],
        "key_points": ["ポイント1", "ポイント2"],
        "why_moved": "動いた理由"
      }}
    }}
    // 他のセクションも同様
  ],
  "adjustment_notes": "調整した点の説明"
}}

# 重要事項
- 初心者が混乱しない構成を維持
- 各セクションの役割を明確に
- 情報の重複を避ける
- 視聴者が飽きないようテンポを考慮
"""
        
        try:
            structure_result = self.client.generate_json(
                structure_prompt,
                max_retries=3,
                use_search=False
            )
            
            print("\n✅ 構成決定完了")
            print(f"   - 総セクション数: {len(structure_result.get('sections', []))}")
            print(f"   - 総時間: {structure_result.get('total_duration', 0)}秒")
            
            return structure_result
            
        except Exception as e:
            print(f"\n❌ 構成決定エラー: {e}")
            raise
    
    def execute_full_direction(
        self,
        base_data: Dict,
        video_type: str = "morning"
    ) -> Dict:
        """
        全ステップを実行して動画構成を完成させる
        
        Args:
            base_data: 基礎データ
            video_type: 動画タイプ ("morning" or "evening")
        
        Returns:
            Dict: 完成した動画構成
        """
        print("\n" + "="*80)
        print(f"🎥 AIディレクション開始: {video_type.upper()} VIDEO")
        print("="*80)
        
        try:
            # Step 1: 包括的調査
            research_result = self.conduct_comprehensive_research(
                base_data,
                video_type
            )
            
            # Step 2: 分析と選定
            analysis_result = self.analyze_and_select(
                research_result,
                base_data,
                video_type
            )
            
            # Step 3: 構成決定
            structure_result = self.decide_video_structure(
                analysis_result,
                video_type
            )
            
            # 全結果を統合
            final_result = {
                "video_type": video_type,
                "timestamp": datetime.now().isoformat(),
                "research": research_result,
                "analysis": analysis_result,
                "structure": structure_result
            }
            
            print("\n" + "="*80)
            print("✅ AIディレクション完了")
            print("="*80)
            
            return final_result
            
        except Exception as e:
            print(f"\n❌ ディレクションエラー: {e}")
            raise
    
    def save_direction_result(
        self,
        result: Dict,
        output_dir: str = "data/direction"
    ) -> str:
        """
        ディレクション結果を保存
        
        Args:
            result: ディレクション結果
            output_dir: 出力ディレクトリ
        
        Returns:
            str: 保存したファイルパス
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_type = result.get("video_type", "unknown")
        filename = f"direction_{video_type}_{timestamp}.json"
        filepath = output_path / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"💾 ディレクション結果保存: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"❌ 保存エラー: {e}")
            raise


# テスト用
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎬 AIディレクター テスト")
    print("="*60 + "\n")
    
    # サンプルデータ
    sample_base_data = {
        "market_data": {
            "market": {
                "japan": {
                    "nikkei": {
                        "current": 39000.0,
                        "change": 300.0,
                        "change_percent": 0.77
                    }
                },
                "us": {
                    "dow": {
                        "current": 44000.0,
                        "change": 150.0,
                        "change_percent": 0.34
                    }
                }
            },
            "sectors": [
                {
                    "name": "半導体",
                    "change_percent": 2.5
                },
                {
                    "name": "自動車",
                    "change_percent": -1.2
                }
            ]
        },
        "event_search_hints": {
            "dates": {
                "today": "2025年12月01日"
            }
        }
    }
    
    try:
        # AIディレクター初期化
        director = AIDirector()
        
        # 朝の動画のディレクション実行
        print("\n【朝の動画をディレクション】")
        result = director.execute_full_direction(
            sample_base_data,
            video_type="morning"
        )
        
        # 結果保存
        saved_path = director.save_direction_result(result)
        
        print("\n【ディレクション結果サマリー】")
        print(f"動画タイプ: {result['video_type']}")
        print(f"最重要トピック数: {len(result['analysis'].get('top_topics', []))}")
        print(f"注目セクター数: {len(result['analysis'].get('selected_sectors', []))}")
        print(f"動画セクション数: {len(result['structure'].get('sections', []))}")
        print(f"総時間: {result['structure'].get('total_duration')}秒")
        
        print("\n" + "="*60)
        print("✅ テスト完了")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {e}")
        import traceback
        traceback.print_exc()
