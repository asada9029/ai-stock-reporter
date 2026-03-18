import argparse
import os
import sys
import traceback
from datetime import datetime

from src.data_collection.market_index_capturer import MarketIndexCapturer


def _configure_headless(capturer: MarketIndexCapturer, headless: bool) -> None:
    """
    MarketIndexCapturer は __init__ 内で headless を固定しているため、
    テスト用途では Options を差し替える。
    """
    try:
        # Selenium Options を作り直し
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        if headless:
            opts.add_argument("--headless")
        opts.add_argument("--window-size=1600,900")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        capturer.chrome_options = opts
    except Exception:
        # ここで失敗しても本筋ではないので、そのまま続行
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test-only runner for MarketIndexCapturer.capture_all_market_charts_and_data / capture_chart_and_data"
    )
    parser.add_argument(
        "--video-type",
        choices=["morning", "evening"],
        default="evening",
        help="Which set of markets to capture",
    )
    parser.add_argument(
        "--market",
        default=None,
        help="Optional single market key (e.g. NIKKEI, SP500, DOW, NASDAQ, USDJPY)",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Chrome headless (default: true). Use --no-headless to debug locally.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join("output", "market_charts_test"),
        help="Directory to save screenshots",
    )
    parser.add_argument(
        "--dump-html-on-failure",
        action="store_true",
        help="When a capture fails, dump page_source HTML to output dir (best effort).",
    )
    args = parser.parse_args()

    capturer = MarketIndexCapturer(output_dir=args.output_dir)
    _configure_headless(capturer, headless=args.headless)

    os.makedirs(args.output_dir, exist_ok=True)
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🧪 MarketIndexCapturer test started: {started_at}")
    print(f"  video_type={args.video_type} headless={args.headless} output_dir={args.output_dir}")
    if args.market:
        print(f"  market={args.market}")

    # 単一市場テスト
    if args.market:
        data = capturer.capture_chart_and_data(args.market)
        if not data:
            print("❌ capture_chart_and_data returned None.")
            return 2
        print("✅ capture_chart_and_data OK")
        print(f"  name={data.get('name')}")
        print(f"  current_price={data.get('current_price')}")
        print(f"  change={data.get('change')} ({data.get('change_percent')})")
        print(f"  chart_image_path={data.get('chart_image_path')}")
        return 0

    # 全体テスト（失敗時にどこで落ちたか見えるよう、キー単位で実行）
    all_data = {}
    keys = ["SP500", "DOW", "NASDAQ"] if args.video_type == "morning" else ["NIKKEI", "SP500"]
    for key in keys:
        print("\n" + "-" * 60)
        print(f"▶ capturing: {key}")
        try:
            data = capturer.capture_chart_and_data(key)
            if data:
                all_data[key] = data
                print(f"✅ OK: {key} current={data.get('current_price')} change={data.get('change')} ({data.get('change_percent')})")
            else:
                print(f"❌ FAILED (returned None): {key}")
        except Exception as e:
            print(f"❌ EXCEPTION: {key}: {e}")
            traceback.print_exc()

            if args.dump_html_on_failure:
                # MarketIndexCapturer 内部で driver を close してしまうので、
                # ここでは詳細HTMLは取得できないケースが多い。将来の拡張用に枠だけ用意。
                dump_path = os.path.join(
                    args.output_dir, f"failure_{key.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write("Failed with exception. See stacktrace in stdout.\n\n")
                    f.write("Exception:\n")
                    f.write(repr(e) + "\n\n")
                    f.write("Traceback:\n")
                    f.write(traceback.format_exc())
                print(f"📝 failure report saved: {dump_path}")

    print("\n" + "=" * 60)
    print("📦 summary")
    for key in keys:
        if key in all_data:
            d = all_data[key]
            print(f"  ✅ {key}: {d.get('current_price')} / {d.get('change')} ({d.get('change_percent')})")
        else:
            print(f"  ❌ {key}: no data")
    print("=" * 60)

    return 0 if len(all_data) == len(keys) else 3


if __name__ == "__main__":
    raise SystemExit(main())

