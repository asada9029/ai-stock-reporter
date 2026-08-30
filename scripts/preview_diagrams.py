"""図解プレビュー生成（検証用）。"""
from pathlib import Path

from src.video_generation.diagram_generator import (
    generate_capital_flow_diagram,
    generate_impact_flow_diagram,
    generate_market_board_diagram,
    generate_news_bundle_diagram,
)


def main() -> None:
    out = Path("output/diagram_preview")
    out.mkdir(parents=True, exist_ok=True)
    news = [
        {"title": "米金利低下でハイテク買い", "slot": "honmei", "related_company_name": "NVIDIA"},
        {"title": "急騰の半導体株", "slot": "heat"},
        {"title": "資金は内需へ", "slot": "rotation"},
    ]
    print("bundle", generate_news_bundle_diagram(news, output_path=out / "news_bundle.png"))
    print(
        "flow",
        generate_impact_flow_diagram(
            left_label="金利低下",
            mid_label="半導体",
            right_label="日本株",
            output_path=out / "impact_flow.png",
        ),
    )
    print(
        "board",
        generate_market_board_diagram(
            {
                "NIKKEI": {"name": "日経平均", "current_price": 38500, "change_percent": 0.85},
                "NASDAQ": {"name": "NASDAQ", "current_price": 17800, "change_percent": -0.32},
                "SP500": {"name": "S&P500", "current_price": 5200, "change_percent": 0.12},
                "USDJPY": {"name": "ドル円", "current_price": 149.2, "change_percent": -0.1},
            },
            output_path=out / "market_board.png",
        ),
    )
    print(
        "capital",
        generate_capital_flow_diagram(
            [
                {"name": "半導体", "change_percent": 2.1},
                {"name": "銀行", "change_percent": 1.4},
            ],
            [
                {"name": "不動産", "change_percent": -1.8},
                {"name": "小売", "change_percent": -0.9},
            ],
            output_path=out / "capital_flow.png",
        ),
    )
    print("files", sorted(p.name for p in out.glob("*.png")))


if __name__ == "__main__":
    main()
