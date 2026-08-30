"""
本文向けの簡易図解（Studio Soft）。
文字だらけを減らし、視線でわかるカード／フローを出す。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.config.studio_soft import STUDIO_SOFT, ink_color


DIAGRAM_W = 1560


def _font(path: Optional[str], size: int) -> ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _find_font() -> Optional[str]:
    here = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    for name in ("SourceHanSans-Heavy.otf", "MPLUS1-Bold.ttf", "NotoSansJP-Regular.ttf"):
        p = here / name
        if p.exists():
            return str(p)
    return None


def _rounded_shadow(
    draw_base: Image.Image,
    box: Tuple[int, int, int, int],
    *,
    radius: int,
    fill: Tuple[int, int, int, int],
    shadow: bool = True,
) -> Image.Image:
    layer = Image.new("RGBA", draw_base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    if shadow:
        sh_a = int(STUDIO_SOFT.get("panel_shadow_alpha", 72))
        d.rounded_rectangle((x0 + 7, y0 + 10, x1 + 7, y1 + 10), radius=radius, fill=(44, 36, 32, sh_a))
        layer = layer.filter(ImageFilter.GaussianBlur(12))
        draw_base = Image.alpha_composite(draw_base, layer)
        layer = Image.new("RGBA", draw_base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
    outline = STUDIO_SOFT.get("panel_outline", (255, 255, 255, 140))
    d.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=radius,
        fill=fill,
        outline=outline if isinstance(outline, tuple) else (255, 255, 255, 140),
        width=3,
    )
    return Image.alpha_composite(draw_base, layer)


def _truncate(text: str, n: int) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _cjk_ratio(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    cjk = sum(1 for ch in t if ("\u3040" <= ch <= "\u30ff") or ("\u4e00" <= ch <= "\u9fff"))
    return cjk / max(1, len(t))


def _prefer_ja_text(*candidates: str, min_len: int = 4) -> str:
    """日本語っぽい候補を優先。なければ最初の非空を返す。"""
    cleaned = [str(c or "").strip() for c in candidates]
    cleaned = [c for c in cleaned if len(c) >= min_len]
    if not cleaned:
        return ""
    ja = [c for c in cleaned if _cjk_ratio(c) >= 0.25]
    return ja[0] if ja else cleaned[0]


def _news_headline(it: Dict) -> str:
    # 英語タイトルより日本語（title_ja / snippet）を優先
    return _prefer_ja_text(
        str(it.get("title_ja") or ""),
        str(it.get("snippet") or ""),
        str(it.get("summary") or ""),
        str(it.get("headline") or ""),
        str(it.get("title") or ""),
        min_len=2,
    ) or "ニュース"


def _news_subline(it: Dict) -> str:
    return _prefer_ja_text(
        str(it.get("summary") or ""),
        str(it.get("why_now") or ""),
        str(it.get("snippet") or ""),
        str(it.get("title_ja") or ""),
        min_len=4,
    )


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _wrap_text_lines(
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int = 2,
) -> List[str]:
    """指定幅内に収まるよう折り返し（日本語は1文字ずつ）。"""
    t = (text or "").strip()
    if not t or max_width <= 0:
        return []
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    if _text_width(draw, t, font) <= max_width:
        return [t]

    lines: List[str] = []
    cur = ""
    for ch in t:
        trial = cur + ch
        if cur and _text_width(draw, trial, font) > max_width:
            lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
        else:
            cur = trial
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) >= max_lines and len("".join(lines)) < len(t):
        last = lines[-1]
        while last and _text_width(draw, last + "…", font) > max_width:
            last = last[:-1]
        lines[-1] = (last + "…") if last else "…"
    return lines


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill,
    optical_dy: float = -2,
) -> None:
    """枠内の見切れを防ぐため anchor=mm を優先。日本語は光学補正で少し上げる。"""
    x, y = xy[0], xy[1] + optical_dy
    try:
        draw.text((x, y), text, font=font, fill=fill, anchor="mm")
    except TypeError:
        bb = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text((x - tw / 2, y - th / 2 - bb[1]), text, font=font, fill=fill)


def _slot_style(slot: str) -> Tuple[str, Tuple[int, int, int]]:
    s = (slot or "support").lower()
    if s == "honmei":
        return ("本命", STUDIO_SOFT["soft_coral"])  # type: ignore[return-value]
    if s == "heat":
        return ("話題", STUDIO_SOFT["soft_green"])  # type: ignore[return-value]
    if s == "rotation":
        return ("資金", STUDIO_SOFT["soft_blue"])  # type: ignore[return-value]
    return ("補足", STUDIO_SOFT["mute"])  # type: ignore[return-value]


def _save_diagram(img: Image.Image, output_path: Path) -> str:
    """角丸カード＋透明余白のまま保存（四角い白の裏板はみ出し防止）。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return str(output_path)


def _base_card(width: int, height: int, *, radius: int = 36) -> Image.Image:
    """透明キャンバス上にクリームの角丸カードを1枚だけ置く。"""
    cream = STUDIO_SOFT["surface_cream_solid"]
    alpha = int(STUDIO_SOFT.get("panel_cream_alpha", 250))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pad = 8
    return _rounded_shadow(
        img,
        (pad, pad, width - pad - 1, height - pad - 1),
        radius=radius,
        fill=(*cream, alpha),
        shadow=True,
    )


def generate_news_bundle_diagram(
    news_list: Sequence[Dict],
    *,
    output_path: Path,
    title: str = "本日の主要ニュース",
    min_items: int = 3,
) -> Optional[str]:
    """本命/旬/循環をカードで並べた図解。最低件数未満は要約行で補完。"""
    raw = [n for n in list(news_list or []) if isinstance(n, dict)]
    items: List[Dict] = list(raw[:5])
    if not items:
        return None
    # 件数不足時は既存ニュースの要約を別カードとして足して密度を確保
    for src in raw:
        if len(items) >= min_items:
            break
        extra = str(src.get("summary") or src.get("why_now") or "").strip()
        if len(extra) < 10:
            continue
        title_txt = str(src.get("title") or "")
        if any(str(it.get("title") or "") == _truncate(extra, 40) for it in items):
            continue
        items.append(
            {
                "slot": "support",
                "title": _truncate(extra, 40),
                "summary": _truncate(title_txt, 48),
            }
        )
    items = items[:5]

    w = DIAGRAM_W
    card_x0, card_x1 = 28, w - 32
    text_x = 196
    text_max_w = card_x1 - text_x - 28
    font_path = _find_font()
    ink = ink_color()
    title_font = _font(font_path, 44)
    body_font = _font(font_path, 34)
    small_font = _font(font_path, 24)
    badge_font = _font(font_path, 22)

    # カード内は詰めて、カード間ギャップで区切る
    head_line_h, sub_line_h = 36, 26
    gap_head_sub = 6
    pad_top, pad_bot = 10, 12
    card_gap = 32
    row_layouts = []
    for it in items:
        label, color = _slot_style(str(it.get("slot") or it.get("lane") or ""))
        headline = _news_headline(it)
        sub = _news_subline(it)
        if sub == headline or (headline and sub.startswith(headline[:10])):
            if len(sub) <= len(headline) + 2:
                sub = ""
        head_lines = _wrap_text_lines(headline, body_font, text_max_w, max_lines=1)
        sub_short = _truncate(sub, 48) if sub else ""
        sub_lines = _wrap_text_lines(sub_short, small_font, text_max_w, max_lines=1) if sub_short else []
        row_inner = (
            pad_top
            + len(head_lines) * head_line_h
            + (gap_head_sub if sub_lines else 0)
            + len(sub_lines) * sub_line_h
            + pad_bot
        )
        row_h = max(78, row_inner)
        row_layouts.append((it, label, color, head_lines, sub_lines, row_h))

    total_rows_h = sum(r[5] for r in row_layouts) + card_gap * max(0, len(row_layouts) - 1)
    cards_y = 108
    h = cards_y + total_rows_h + 40

    img = _base_card(w, h, radius=36)
    draw = ImageDraw.Draw(img)
    draw.text((40, 28), title, font=title_font, fill=ink)

    y = cards_y
    for idx, (it, label, color, head_lines, sub_lines, row_h) in enumerate(row_layouts):
        img = _rounded_shadow(
            img,
            (card_x0, y, card_x1, y + row_h),
            radius=18,
            fill=(255, 255, 255, 240),
        )
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((card_x0 + 10, y + 10, card_x0 + 22, y + row_h - 12), radius=6, fill=(*color, 230))
        bw = 88
        draw.rounded_rectangle((card_x0 + 32, y + 10, card_x0 + 32 + bw, y + 42), radius=14, fill=(*color, 220))
        _draw_centered_text(draw, (card_x0 + 32 + bw / 2, y + 26), label, font=badge_font, fill=(255, 255, 255))
        ty = y + pad_top
        for ln in head_lines:
            draw.text((text_x, ty), ln, font=body_font, fill=ink)
            ty += head_line_h
        if sub_lines:
            ty += gap_head_sub
            for ln in sub_lines:
                draw.text((text_x, ty), ln, font=small_font, fill=STUDIO_SOFT["mute"])
                ty += sub_line_h
        y += row_h + (card_gap if idx < len(row_layouts) - 1 else 0)

    return _save_diagram(img, Path(output_path))


def generate_impact_flow_diagram(
    *,
    left_label: str,
    mid_label: str,
    right_label: str,
    output_path: Path,
    title: str = "どう効く？ 影響の流れ",
    note: str = "",
    left_sub: str = "",
    mid_sub: str = "",
    right_sub: str = "",
    bullets: Optional[Sequence[str]] = None,
) -> str:
    """ニュース → セクター/市場 → 日本株 の3ノード矢印図（下に要点行で密度確保）。"""
    w = DIAGRAM_W
    font_path = _find_font()
    ink = ink_color()
    title_font = _font(font_path, 52)
    node_font = _font(font_path, 34)
    small_font = _font(font_path, 26)
    tip_font = _font(font_path, 28)

    margin_x, gap = 32, 118
    node_w = (w - margin_x * 2 - gap * 2) // 3
    inner_w = node_w - 78
    xs = [margin_x, margin_x + node_w + gap, margin_x + (node_w + gap) * 2]

    def _node_lines(label: str, sub: str) -> Tuple[List[str], List[str], int]:
        main = _wrap_text_lines(label, node_font, inner_w, max_lines=3)
        sub_l = _wrap_text_lines(sub, small_font, inner_w, max_lines=2) if sub else []
        line_h = 36
        sub_line_h = 28
        h_need = max(88, len(main) * line_h + (10 if sub_l else 0) + len(sub_l) * sub_line_h + 28)
        return main, sub_l, h_need

    left_main, left_sub_l, lh = _node_lines(left_label, left_sub)
    mid_main, mid_sub_l, mh = _node_lines(mid_label, mid_sub)
    right_main, right_sub_l, rh = _node_lines(right_label, right_sub)
    node_h = max(lh, mh, rh, 176)

    node_specs = [
        (left_main, left_sub_l, STUDIO_SOFT["soft_coral"], xs[0]),
        (mid_main, mid_sub_l, STUDIO_SOFT["soft_blue"], xs[1]),
        (right_main, right_sub_l, STUDIO_SOFT["soft_green"], xs[2]),
    ]
    ny = 148
    tip_lines = [str(x).strip() for x in (bullets or []) if str(x).strip()][:3]
    tip_groups: List[List[str]] = []
    tip_max_w = w - 80
    for tip in tip_lines:
        wrapped = _wrap_text_lines(tip, tip_font, tip_max_w, max_lines=2)
        if not wrapped:
            continue
        wrapped[0] = "・" + wrapped[0]
        for i in range(1, len(wrapped)):
            wrapped[i] = "　　" + wrapped[i]
        tip_groups.append(wrapped)
    inner_line_h = 30
    bullet_item_gap = 14
    footer_h = 0
    if tip_groups:
        n_lines = sum(len(g) for g in tip_groups)
        n_gaps = max(0, len(tip_groups) - 1)
        footer_h = 40 + n_lines * inner_line_h + n_gaps * bullet_item_gap
    elif note:
        footer_h = 56
    h = ny + node_h + max(56, footer_h + 28)

    img = _base_card(w, h, radius=36)
    draw = ImageDraw.Draw(img)
    draw.text((48, 24), title, font=title_font, fill=ink)

    centers = []
    for main_lines, sub_lines, color, x in node_specs:
        img = _rounded_shadow(
            img,
            (x, ny, x + node_w, ny + node_h),
            radius=28,
            fill=(255, 255, 255, 245),
        )
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((x + 16, ny + 16, x + 42, ny + node_h - 16), radius=10, fill=(*color, 230))
        # 色バーの右から中央寄せ（バーに文字が被らない）
        inner_cx = x + 42 + (node_w - 58) / 2
        block_h = len(main_lines) * 36 + (10 if sub_lines else 0) + len(sub_lines) * 28
        y0 = ny + max(16, (node_h - block_h) // 2)
        cy = y0 + 16
        for ln in main_lines:
            _draw_centered_text(draw, (inner_cx, cy), ln, font=node_font, fill=ink)
            cy += 36
        if sub_lines:
            cy += 6
            for ln in sub_lines:
                _draw_centered_text(
                    draw,
                    (inner_cx, cy),
                    ln,
                    font=small_font,
                    fill=STUDIO_SOFT["mute"],
                )
                cy += 28
        centers.append(x + node_w)

    draw = ImageDraw.Draw(img)
    arrow_y = ny + node_h // 2
    for i in range(2):
        x0 = centers[i] + 8
        x1 = node_specs[i + 1][3] - 12
        mid = (x0 + x1) // 2
        draw.line((x0, arrow_y, x1 - 18, arrow_y), fill=STUDIO_SOFT["ink"], width=8)
        draw.polygon(
            [(x1, arrow_y), (x1 - 28, arrow_y - 16), (x1 - 28, arrow_y + 16)],
            fill=STUDIO_SOFT["ink"],
        )
        draw.text((mid - 30, arrow_y - 48), "影響", font=small_font, fill=STUDIO_SOFT["mute"])

    y_foot = ny + node_h + 36
    if tip_groups:
        yb = y_foot
        for gi, group in enumerate(tip_groups):
            for ln in group:
                draw.text((48, yb), ln, font=tip_font, fill=ink)
                yb += inner_line_h
            if gi < len(tip_groups) - 1:
                yb += bullet_item_gap
    elif note:
        note_lines = _wrap_text_lines(note, small_font, w - 96, max_lines=2)
        for i, ln in enumerate(note_lines):
            draw.text((48, h - 48 + i * 28), ln, font=small_font, fill=STUDIO_SOFT["mute"])

    return _save_diagram(img, Path(output_path))


def generate_checklist_diagram(
    items: Sequence[str],
    *,
    output_path: Path,
    title: str = "明日のチェック",
) -> Optional[str]:
    """行動チェックを大きなリスト図に。"""
    cleaned = [str(x).strip() for x in items if str(x).strip()][:5]
    if not cleaned:
        return None
    w = DIAGRAM_W
    h = 120 + len(cleaned) * 120 + 40
    font_path = _find_font()
    ink = ink_color()
    title_font = _font(font_path, 48)
    body_font = _font(font_path, 40)
    img = _base_card(w, h, radius=36)
    draw = ImageDraw.Draw(img)
    draw.text((48, 32), title, font=title_font, fill=ink)

    top = 110
    for i, text in enumerate(cleaned):
        y = top + i * 120
        img = _rounded_shadow(
            img,
            (60, y, w - 60, y + 100),
            radius=24,
            fill=(255, 255, 255, 240),
        )
        draw = ImageDraw.Draw(img)
        draw.ellipse((90, y + 22, 160, y + 92), fill=(*STUDIO_SOFT["soft_blue"], 230))
        num = str(i + 1)
        _draw_centered_text(draw, (125, y + 57), num, font=body_font, fill=(255, 255, 255))
        draw.text((190, y + 32), _truncate(text, 26), font=body_font, fill=ink)

    return _save_diagram(img, Path(output_path))


def generate_market_board_diagram(
    indices: Dict,
    *,
    output_path: Path,
    title: str = "今日の地合いボード",
) -> Optional[str]:
    """主要指数をカード並べで一目で見せる。"""
    if not indices:
        return None

    preferred = ["NIKKEI", "NASDAQ", "SP500", "S&P500", "DOW", "USDJPY", "USD/JPY"]
    cards: List[Tuple[str, Dict]] = []
    seen = set()
    for key in preferred:
        if key in indices and key not in seen:
            cards.append((key, indices[key] or {}))
            seen.add(key)
    for key, val in indices.items():
        if key not in seen and isinstance(val, dict):
            cards.append((key, val))
            seen.add(key)
        if len(cards) >= 6:
            break
    if not cards:
        return None

    w = DIAGRAM_W
    cols = min(3, len(cards))
    rows = (len(cards) + cols - 1) // cols
    margin_x, top = 48, 120
    gap_x, gap_y = 28, 28
    card_w = (w - margin_x * 2 - gap_x * (cols - 1)) // cols
    card_h = 220
    h = top + rows * card_h + (rows - 1) * gap_y + 48

    font_path = _find_font()
    ink = ink_color()
    title_font = _font(font_path, 52)
    name_font = _font(font_path, 34)
    big_font = _font(font_path, 58)
    small_font = _font(font_path, 28)

    img = _base_card(w, h, radius=36)
    draw = ImageDraw.Draw(img)
    draw.text((48, 32), title, font=title_font, fill=ink)

    for i, (key, data) in enumerate(cards):
        r, c = divmod(i, cols)
        x = margin_x + c * (card_w + gap_x)
        y = top + r * (card_h + gap_y)
        img = _rounded_shadow(
            img, (x, y, x + card_w, y + card_h), radius=24, fill=(255, 255, 255, 245)
        )
        draw = ImageDraw.Draw(img)
        name = str(data.get("name") or key)
        chg = data.get("change_percent")
        try:
            chg_f = float(chg) if chg is not None else None
        except (TypeError, ValueError):
            chg_f = None
        if chg_f is None:
            accent = STUDIO_SOFT["soft_blue"]
            chg_txt = "—"
        elif chg_f >= 0:
            accent = STUDIO_SOFT["soft_green"]
            chg_txt = f"+{chg_f:.2f}%"
        else:
            accent = STUDIO_SOFT["soft_coral"]
            chg_txt = f"{chg_f:.2f}%"
        draw.rounded_rectangle((x + 18, y + 18, x + 42, y + card_h - 18), radius=8, fill=(*accent, 230))
        draw.text((x + 58, y + 24), _truncate(name, 12), font=name_font, fill=STUDIO_SOFT["mute"])
        _draw_centered_text(
            draw,
            (x + card_w / 2, y + card_h / 2 + 4),
            chg_txt,
            font=big_font,
            fill=(*accent, 255),
        )
        price = data.get("current_price")
        if price is not None:
            price_txt = _truncate(str(price), 16)
            _draw_centered_text(
                draw,
                (x + card_w / 2, y + card_h - 36),
                price_txt,
                font=small_font,
                fill=ink,
            )

    return _save_diagram(img, Path(output_path))


def generate_capital_flow_diagram(
    inflows: Sequence[Dict],
    outflows: Sequence[Dict],
    *,
    output_path: Path,
    title: str = "資金の行き先（ざっくり）",
) -> Optional[str]:
    """流入セクター → 流出セクターの簡易図。"""
    ins = list(inflows or [])[:4]
    outs = list(outflows or [])[:4]
    if not ins and not outs:
        return None

    n_rows = max(len(ins), len(outs), 1)
    w = DIAGRAM_W
    top = 96
    row_h = 92
    col_inner_h = 100 + n_rows * row_h + 24
    # 中身に合わせた高さ（空のクリーム余白でスカスカにしない）
    h = top + col_inner_h + 56
    cream = STUDIO_SOFT["surface_cream_solid"]
    font_path = _find_font()
    ink = ink_color()
    title_font = _font(font_path, 52)
    head_font = _font(font_path, 34)
    body_font = _font(font_path, 34)

    img = _base_card(w, h, radius=36)
    draw = ImageDraw.Draw(img)
    draw.text((48, 32), title, font=title_font, fill=ink)

    col_w = 580
    left_x, right_x = 70, w - 70 - col_w
    col_top = top

    def _draw_column(x: int, header: str, color: Tuple[int, int, int], items: List[Dict], sign: str):
        nonlocal img
        img = _rounded_shadow(
            img, (x, col_top, x + col_w, col_top + col_inner_h), radius=28, fill=(255, 255, 255, 240)
        )
        d = ImageDraw.Draw(img)
        badge = (x + 24, col_top + 22, x + 250, col_top + 86)
        d.rounded_rectangle(badge, radius=18, fill=(*color, 220))
        _draw_centered_text(
            d,
            ((badge[0] + badge[2]) / 2, (badge[1] + badge[3]) / 2),
            header,
            font=head_font,
            fill=(255, 255, 255),
            optical_dy=-3,
        )
        y = col_top + 108
        for it in items:
            name = str(it.get("name") or it.get("sector_name") or it.get("sector") or "—")
            chg = it.get("change_percent", it.get("change"))
            try:
                chg_f = float(chg) if chg is not None else None
            except (TypeError, ValueError):
                chg_f = None
            if chg_f is None:
                chg_txt = ""
            elif sign == "+":
                chg_txt = f"+{abs(chg_f):.2f}%"
            else:
                chg_txt = f"-{abs(chg_f):.2f}%" if chg_f < 0 else f"{chg_f:.2f}%"
            d.rounded_rectangle((x + 28, y, x + col_w - 28, y + 84), radius=18, fill=(*cream, 255))
            d.text((x + 48, y + 26), _truncate(name, 14), font=body_font, fill=ink)
            if chg_txt:
                cb = d.textbbox((0, 0), chg_txt, font=body_font)
                d.text(
                    (x + col_w - 48 - (cb[2] - cb[0]), y + 26),
                    chg_txt,
                    font=body_font,
                    fill=(*color, 255),
                )
            y += row_h

    _draw_column(left_x, "流入寄り", STUDIO_SOFT["soft_green"], ins, "+")  # type: ignore[arg-type]
    _draw_column(right_x, "流出寄り", STUDIO_SOFT["soft_coral"], outs, "-")  # type: ignore[arg-type]

    mid_y = col_top + col_inner_h // 2
    ax0, ax1 = left_x + col_w + 12, right_x - 12
    draw = ImageDraw.Draw(img)
    draw.line((ax0, mid_y, ax1 - 18, mid_y), fill=STUDIO_SOFT["mute"], width=6)
    draw.polygon(
        [(ax1, mid_y), (ax1 - 28, mid_y - 16), (ax1 - 28, mid_y + 16)],
        fill=STUDIO_SOFT["mute"],
    )
    draw.text(((ax0 + ax1) // 2 - 50, mid_y - 52), "お金の移動", font=body_font, fill=STUDIO_SOFT["mute"])
    foot = "金利・業績・地合いで資金の流れが入れ替わる"
    fb = draw.textbbox((0, 0), foot, font=_font(font_path, 28))
    draw.text(
        ((w - (fb[2] - fb[0])) // 2, h - 48),
        foot,
        font=_font(font_path, 28),
        fill=STUDIO_SOFT["mute"],
    )

    return _save_diagram(img, Path(output_path))


__all__ = [
    "generate_news_bundle_diagram",
    "generate_impact_flow_diagram",
    "generate_checklist_diagram",
    "generate_market_board_diagram",
    "generate_capital_flow_diagram",
]
