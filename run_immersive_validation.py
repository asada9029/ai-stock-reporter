"""
immersive 検証をステップ順に実行するエントリポイント。

使い方:
  python run_immersive_validation.py --step 1
  python run_immersive_validation.py --step 2 --type evening
  python run_immersive_validation.py --step 3 --presentation immersive
  python run_immersive_validation.py --step all --type evening

前提:
  ステップ1: 追加のサービス不要（MoviePy / フォント）
  ステップ2: GEMINI_API_KEY、data/collected_data/aggregated_data_*.json
  ステップ3: 上記 + VOICEVOX (http://localhost:50021)
"""

from __future__ import annotations

import argparse
import sys

from immersive_test_utils import DATA_DIR, ensure_output_dir


def _check_prerequisites(step: str, video_category: str) -> bool:
    ok = True
    if step in ("2", "3", "all"):
        files = list(DATA_DIR.glob(f"aggregated_data_{video_category}_*.json"))
        if not files:
            print(
                f"[WARN] 集約データなし: {DATA_DIR}/aggregated_data_{video_category}_*.json\n"
                "    ステップ2のみデータ収集するか、過去の main.py 出力を置いてください。"
            )
            if step == "2":
                print("    （test_immersive_script.py は無い場合 DataAggregator を起動します）")
        else:
            print(f"[OK] 集約データ: {files[0].name}")

    if step in ("3", "all"):
        try:
            import urllib.request

            urllib.request.urlopen("http://localhost:50021/docs", timeout=2)
            print("[OK] VOICEVOX: 応答あり")
        except Exception:
            print("[WARN] VOICEVOX が localhost:50021 で応答しません（ステップ3で必要）")
            ok = False

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="immersive 検証ランナー")
    parser.add_argument(
        "--step",
        choices=["1", "2", "3", "all"],
        required=True,
        help="実行するステップ",
    )
    parser.add_argument("--type", choices=["evening", "morning"], default="evening")
    parser.add_argument(
        "--presentation",
        choices=["classic", "immersive", "both"],
        default="immersive",
        help="ステップ2/3 の presentation",
    )
    parser.add_argument(
        "--scenes-json",
        default=None,
        help="ステップ3 で使う台本JSON（ステップ2の保存物）",
    )
    parser.add_argument(
        "--skip-prereq-check",
        action="store_true",
        help="前提チェックをスキップ",
    )
    args = parser.parse_args()

    ensure_output_dir()
    print(f"出力先: {ensure_output_dir()}\n")

    if not args.skip_prereq_check:
        if not _check_prerequisites(args.step, args.type):
            if args.step in ("3", "all"):
                print("\n[NG] 前提を満たしていません。VOICEVOX を起動するか --step 1 から実行してください。")
                return 1
        print()

    code = 0

    if args.step in ("1", "all"):
        from test_immersive_layout import run_layout_test

        print("=" * 60)
        print("ステップ1: レイアウト（無音）")
        print("=" * 60)
        code = max(code, run_layout_test("both"))

    if args.step in ("2", "all"):
        from test_immersive_script import run_script_test

        print("\n" + "=" * 60)
        print("ステップ2: 台本（LLM）")
        print("=" * 60)
        code = max(
            code,
            run_script_test(args.type, args.presentation, save=True),
        )

    if args.step in ("3", "all"):
        from test_immersive_pipeline import run_pipeline_test

        print("\n" + "=" * 60)
        print("ステップ3: 短縮パイプライン（音声・SE）")
        print("=" * 60)
        scenes_json = args.scenes_json
        if args.step == "all" and not scenes_json:
            print("  (info) --scenes-json 未指定のため内蔵3シーンで実行します")
        code = max(
            code,
            run_pipeline_test(
                presentation=args.presentation,
                video_category=args.type,
                scenes_json=scenes_json,
                use_builtin_scenes=scenes_json is None,
            ),
        )

    print("\n" + "=" * 60)
    if code == 0:
        print("[OK] 検証ランナー完了")
    else:
        print("[NG] 一部失敗 -- 上のログを確認してください")
    print("=" * 60)
    return code


if __name__ == "__main__":
    sys.exit(main())
