"""
immersive モード検証用の共通ユーティリティ。

ステップ1: レイアウト（無音・LLM不要）
ステップ2: 台本（LLM・集約JSON）
ステップ3: パイプライン短縮（VOICEVOX・SE・BGM、台本は固定 or JSON）
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "collected_data"
SCRIPTS_DIR = PROJECT_ROOT / "data" / "scripts"
OUTPUT_DIR = PROJECT_ROOT / "output" / "immersive_validation"
ASSETS_DIR = "src/assets"


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def resolve_test_image() -> str:
    """レイアウト/パイプライン検証用の画像パス（存在するものを優先）。"""
    candidates = [
        PROJECT_ROOT / "src/assets/images/mini.png",
        PROJECT_ROOT / "src/assets/images/studio_main.png",
        PROJECT_ROOT / "output/stock_charts",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    if candidates[2].is_dir():
        charts = sorted(candidates[2].glob("*.png"), reverse=True)
        if charts:
            return str(charts[0])
    raise FileNotFoundError(
        "検証用画像が見つかりません。src/assets/images/mini.png か "
        "output/stock_charts/*.png を用意してください。"
    )


def load_aggregated_data(video_category: str) -> Tuple[Dict[str, Any], Path]:
    """
    video_category: 'evening' | 'morning'
    """
    pattern = f"aggregated_data_{video_category}_*.json"
    files = sorted(DATA_DIR.glob(pattern), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"集約データがありません: {DATA_DIR / pattern}\n"
            "過去の main.py 実行結果か、test_script_data_mapping.py で生成してください。"
        )
    path = files[0]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), path


def load_video_structure(video_type: str) -> Dict[str, Any]:
    structure_path = PROJECT_ROOT / "src/config/video_structure.json"
    with open(structure_path, "r", encoding="utf-8") as f:
        structures = json.load(f)
    vs = structures.get(video_type)
    if not vs:
        raise KeyError(f"video_structure.json に {video_type} がありません")
    return vs


def load_scenes_json(path: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Path]:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
    else:
        files = sorted(SCRIPTS_DIR.glob("scenes_*.json"), reverse=True)
        if not files:
            raise FileNotFoundError(
                f"台本JSONがありません: {SCRIPTS_DIR / 'scenes_*.json'}\n"
                "ステップ2を実行するか、--scenes-json でパスを指定してください。"
            )
        p = files[0]
    with open(p, "r", encoding="utf-8") as f:
        scenes = json.load(f)
    if not isinstance(scenes, list):
        raise ValueError(f"台本JSONは配列である必要があります: {p}")
    return scenes, p


def _seg(text: str, duration: float = 5.0) -> List[Dict[str, Any]]:
    return [{"text": text, "start": 0.0, "duration": duration}]


def build_layout_scenes(style: str) -> List[Dict[str, Any]]:
    """
    style: 'classic' | 'immersive'
    横動画レイアウト比較用（各5秒・無音レンダリング向け）。
    """
    img = resolve_test_image()
    if style == "immersive":
        opening_text = ["米国: 小幅安", "注目: エヌビディア決算", "日本: 影響は限定的"]
        menu_classic = None
        chart_text = ["S&P500 -1.2%"]
        text_only = ["日経 -1.9%", "半導体 +4.2%"]
    else:
        opening_text = [
            "・市場の動向",
            "・注目ニュース紹介（テストニュース）",
            "・セクター分析",
            "・今夜の米国市場と明日の展望",
            "・まとめ",
        ]
        menu_classic = opening_text
        chart_text = ["■ 画像とテキストの併用", "  └ 画像の下に解説テキスト"]
        text_only = [
            "■ 見出し：長文テスト",
            "  └ 音声と同じ内容を画面に載せると読む負荷が上がる",
            "■ 2つ目の見出し",
            "  └ インデント確認用",
        ]

    scenes: List[Dict[str, Any]] = [
        {
            "scene": 1,
            "section_title": "opening：レイアウト検証",
            "duration": 5.0,
            "text": "オープニングのレイアウト確認です。",
            "on_screen_text": opening_text if style == "immersive" else menu_classic,
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
            "segments": _seg("オープニング"),
        },
        {
            "scene": 2,
            "section_title": "市場指数：日経平均",
            "duration": 5.0,
            "text": "チャートと短いラベルの併用です。",
            "on_screen_text": chart_text,
            "emotion": "normal",
            "image_type": "chart",
            "target_files": [img],
            "segments": _seg("指数シーン"),
        },
        {
            "scene": 3,
            "section_title": "注目ニュース：テスト",
            "duration": 5.0,
            "text": "テキストのみ、またはラベル2行の確認です。",
            "on_screen_text": text_only,
            "emotion": "confident",
            "image_type": "bg_only",
            "target_files": [],
            "segments": _seg("ニュースシーン"),
        },
    ]
    return scenes


def build_pipeline_scenes(style: str = "immersive") -> List[Dict[str, Any]]:
    """
    パイプライン短縮検証用（3シーン + 末尾 subscribe は pipeline が追加）。
    セクション名を変えて section_change SE を2回鳴らす。
    """
    img = resolve_test_image()
    if style == "immersive":
        s1_text = ["米国: 小幅安", "注目: テスト材料"]
        s2_text = ["日経 -0.8%"]
        s3_text = ["半導体 +3.1%", "注目: 決算"]
    else:
        s1_text = ["■ オープニング", "  └ classic 検証"]
        s2_text = ["■ 日経平均", "  └ 前日比の確認"]
        s3_text = ["■ ニュース", "  └ テスト"]

    return [
        {
            "scene": 1,
            "section_title": "opening：検証オープニング",
            "duration": 8.0,
            "text": (
                "immersive パイプライン検証です。"
                "今日の相場は小幅安、材料はテストニュースです。"
                "このあと指数とニュースを短く確認します。"
            ),
            "speech_text": (
                "immersive パイプライン検証です。"
                "今日の相場は小幅安、材料はテストニュースです。"
                "このあと指数とニュースを短く確認します。"
            ),
            "on_screen_text": s1_text,
            "emotion": "happy",
            "image_type": "bg_only",
            "target_files": [],
        },
        {
            "scene": 2,
            "section_title": "市場指数：日経平均",
            "duration": 10.0,
            "text": "日経平均は小幅安でした。値動きは限定的です。",
            "speech_text": "日経平均は小幅安でした。値動きは限定的です。",
            "on_screen_text": s2_text,
            "emotion": "normal",
            "image_type": "chart",
            "target_files": [img],
        },
        {
            "scene": 3,
            "section_title": "注目ニュース：テスト",
            "duration": 10.0,
            "text": "半導体関連が強い一方、全体は様子見です。",
            "speech_text": "半導体関連が強い一方、全体は様子見です。",
            "on_screen_text": s3_text,
            "emotion": "confident",
            "image_type": "chart",
            "target_files": [img],
        },
    ]


def minimal_analysis_data() -> Dict[str, Any]:
    return {
        "attention_news": [
            {"title": "パイプライン検証ニュース", "snippet": "テスト用"}
        ],
        "selected_thumbnail_title": "【検証】サムネタイトル",
        "selected_highlights": ["H1", "H2", "H3"],
        "main_news_index": 0,
        "highlight_indices": [],
        "market_indices": {},
        "sector_analysis": {"sectors": []},
    }


@contextmanager
def patch_pipeline_no_thumbnail():
    """サムネ LLM をスキップ（横型パイプライン短縮検証用）。"""
    import src.video_generation.structured_pipeline as pipeline

    original_cls = pipeline.ThumbnailGenerator

    class _MockThumbnailGenerator:
        def create_thumbnail_from_analysis(self, **kwargs):
            return "", "【検証】サムネ", ["H1", "H2", "H3"], 0, []

    pipeline.ThumbnailGenerator = _MockThumbnailGenerator
    try:
        yield
    finally:
        pipeline.ThumbnailGenerator = original_cls


def print_step1_checklist() -> None:
    print(
        """
【ステップ1 確認チェックリスト】
  □ immersive: 画面テキストがおおむね2行以内・短いラベルか
  □ immersive: 騰落ラベルが赤/緑/青系で色分けされているか
  □ classic: 従来どおり ■ / └ や長めのメニュー表示か
  □ 画像+テキスト: 画像と枠が重なっていないか
  □ 字幕（show_subtitles=False）で下部がテキスト用に広がっているか
"""
    )


def print_step2_checklist(presentation: str) -> None:
    print(
        f"""
【ステップ2 確認チェックリスト】（{presentation}）
  □ on_screen_text に ■ / └ が無い（immersive の場合）
  □ 1シーンあたり画面文字が短い（目安: 各行12文字前後）
  □ opening で結論・最大材料に触れているか（speech_text）
  □ opening の画面が8行メニューになっていないか（immersive）
  □ 保存された JSON: data/scripts/scenes_*.json
"""
    )


def print_step3_checklist(presentation: str) -> None:
    print(
        f"""
【ステップ3 確認チェックリスト】（{presentation}）
  □ VOICEVOX の読み上げが聞こえるか
  □ セクション切替（市場指数→注目ニュース）で SE が鳴るか（immersive のみ）
  □ BGM が流れ、声が潰れていないか
  □ チャプター用タイムコードがコンソール or 戻り値に出ているか
  □ subscribe シーンが末尾に付いているか
"""
    )
