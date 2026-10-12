"""
ساخت دارایی‌های برند هم‌ورق: نشان، لوگو (روشن/تیره/تک‌رنگ)، فاوآیکون، آیکون‌های PWA، تصویر OG.
اجرا:  python scripts/build_brand.py
نیاز: uharfbuzz, fonttools, playwright (برای PNG)  ← pip install -r requirements-dev.txt و کرومیوم
همه‌ی خروجی‌ها تو static/brand/ و قطعه‌ی لوگوی قالب‌ها تو templates/components/_logo.html
"""

import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "static" / "fonts" / "vazirmatn" / "Vazirmatn-ExtraBold.ttf"
OUT = ROOT / "static" / "brand"

GREEN, AMBER, LEAF, DEEP, CREAM, INK = "#1F6F54", "#E0A43A", "#2F9E73", "#124A39", "#FBF7EF", "#14201B"

# نشان: کتاب باز با دو صفحه (هم = دو طرف) و یک برگ که از عطف می‌رویه (ورق)
MARK_BODY = f"""<path d="M32 50C21 43 11 43 4 46V20C11 17 22 17 32 24Z" fill="{GREEN}"/>
<path d="M32 50C43 43 53 43 60 46V20C53 17 42 17 32 24Z" fill="{AMBER}"/>
<path d="M32 24C32 14 37 8 48 6C48 16 43 23 32 24Z" fill="{LEAF}"/>
<path d="M32 23C35 18 39 13 44 10" fill="none" stroke="{CREAM}" stroke-width="1.8" stroke-linecap="round"/>"""


def shaped(text, size):
    """حروف‌چینی فارسی با HarfBuzz ← (مسیر SVG، عرض، کادر)."""
    face = hb.Face(hb.Blob.from_file_path(str(FONT)))
    font = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    tt = TTFont(str(FONT))
    glyphs, order = tt.getGlyphSet(), tt.getGlyphOrder()
    scale = size / tt["head"].unitsPerEm
    path, bounds, x = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip(".")), BoundsPen(glyphs), 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        t = (scale, 0, 0, -scale, (x + pos.x_offset) * scale, -pos.y_offset * scale)
        for pen in (path, bounds):
            glyphs[order[info.codepoint]].draw(TransformPen(pen, t))
        x += pos.x_advance
    return path.getCommands(), x * scale, bounds.bounds


def logo_svg(text_color, with_text=True):
    """لوگوی افقی: نشان سمت راست، کلمه‌نشان سمت چپ (راست‌چین)."""
    d, width, (x0, y0, x1, y1) = shaped("هم‌ورق", 46)
    h = y1 - y0
    if not with_text:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{MARK_BODY}</svg>'
    gap = 10
    total = (x1 - x0) + gap + 64
    ty = 32 - (y0 + h / 2)  # وسط‌چین عمودی کلمه‌نشان کنار نشان
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total:.1f} 64" role="img" aria-label="هم‌ورق">'
            f'<g transform="translate(0 0)"><path transform="translate({-x0:.2f} {ty:.2f})" d="{d}" fill="{text_color}"/></g>'
            f'<g transform="translate({(x1 - x0) + gap:.1f} 0)">{MARK_BODY}</g></svg>')


def write_assets():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mark.svg").write_text(logo_svg(INK, with_text=False), encoding="utf-8")
    (OUT / "logo.svg").write_text(logo_svg(DEEP), encoding="utf-8")
    (OUT / "logo-dark.svg").write_text(logo_svg(CREAM), encoding="utf-8")
    mono = logo_svg("#000").replace(GREEN, "#000").replace(AMBER, "#000").replace(LEAF, "#000").replace(CREAM, "#fff")
    (OUT / "logo-mono.svg").write_text(mono, encoding="utf-8")
    (ROOT / "static" / "favicon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="{CREAM}"/>'
        f'<g transform="translate(4 6) scale(.875)">{MARK_BODY}</g></svg>', encoding="utf-8")
    # قطعه‌ی داخل قالب‌ها: کلمه‌نشان با currentColor تا با حالت تیره/روشن هماهنگ بشه
    inline = logo_svg("currentColor").replace('<svg ', '<svg class="logo-svg" focusable="false" ', 1)
    (ROOT / "templates" / "components").mkdir(parents=True, exist_ok=True)
    (ROOT / "templates" / "components" / "_logo.html").write_text(inline + "\n", encoding="utf-8")
    (ROOT / "templates" / "components" / "_mark.html").write_text(
        f'<svg class="logo-mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">{MARK_BODY}</svg>\n', encoding="utf-8")


def rasterize():
    from playwright.sync_api import sync_playwright

    mark = (OUT / "mark.svg").read_text(encoding="utf-8")
    tagline_font = FONT.as_uri()

    def page(html, w, h, path, transparent=False):
        pg.set_viewport_size({"width": w, "height": h})
        pg.set_content(f"<html><body style='margin:0;width:{w}px;height:{h}px;overflow:hidden'>{html}</body></html>")
        pg.wait_for_timeout(150)
        pg.screenshot(path=str(path), omit_background=transparent)

    def icon(size, bg, scale, round_px=0):
        s = size * scale
        r = f"border-radius:{round_px}px;" if round_px else ""
        return (f"<div style='width:{size}px;height:{size}px;background:{bg};{r}display:flex;align-items:center;justify-content:center'>"
                f"<div style='width:{s}px;height:{s}px'>{mark.replace('<svg ', '<svg width=100% height=100% ', 1)}</div></div>")

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
        pg = br.new_page()
        page(icon(512, CREAM, .78, 112), 512, 512, OUT / "icon-512.png", True)
        page(icon(192, CREAM, .78, 42), 192, 192, OUT / "icon-192.png", True)
        page(icon(512, CREAM, .56), 512, 512, OUT / "maskable-512.png")        # ناحیه‌ی امن ۸۰٪ مرکز
        page(icon(180, CREAM, .78), 180, 180, OUT / "apple-touch-icon.png")
        page(icon(48, CREAM, .8, 10), 48, 48, OUT / "favicon-48.png", True)
        page(icon(32, CREAM, .8, 7), 32, 32, OUT / "favicon-32.png", True)
        og = f"""
<style>@font-face{{font-family:V;src:url({tagline_font});font-weight:800}}
.og{{width:1200px;height:630px;background:linear-gradient(135deg,{CREAM} 0%,#F3EBDA 100%);font-family:V,sans-serif;direction:rtl;
display:flex;flex-direction:column;justify-content:center;padding:0 90px;box-sizing:border-box;position:relative}}
.og .b{{position:absolute;inset-inline-start:0;bottom:0;width:100%;height:14px;background:linear-gradient(90deg,{GREEN},{AMBER})}}</style>
<div class='og'><div style="width:470px">{(OUT / 'logo.svg').read_text(encoding='utf-8')}</div>
<div style='font-size:62px;font-weight:800;color:{DEEP};margin-top:34px;line-height:1.5'>بخوان، بسپار، دوباره بخوان</div>
<div style='font-size:32px;color:#4B5B54;margin-top:8px'>مبادله‌ی رایگان کتاب بین کتاب‌خوان‌ها</div><div class='b'></div></div>"""
        page(og, 1200, 630, OUT / "og-image.png")
        br.close()
    for name in ("icon-192.png", "icon-512.png", "maskable-512.png", "apple-touch-icon.png", "og-image.png"):
        print("ساخته شد:", OUT / name)


if __name__ == "__main__":
    write_assets()
    if "--no-png" not in sys.argv:
        rasterize()
