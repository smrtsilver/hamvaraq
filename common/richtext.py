"""
رندر امن متن کاربر: فقط چند قالب ساده (پاراگراف، **پررنگ**، *مورب*، ## تیتر، > نقل، - فهرست، [متن](لینک)).
اول همه‌چیز escape می‌شه و بعد قالب‌ها اعمال می‌شن؛ پس هیچ HTML خامی از کاربر نمی‌گذره.
لینک فقط http/https و همیشه با nofollow/ugc.
"""

import re
from html import escape

from django.utils.safestring import mark_safe

MAX_LEN = 20000
_LINK = re.compile(r"\[([^\]\n]{1,120})\]\((https?://[^\s)<>\"']{3,400})\)")
_BOLD_ITALIC = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\*\w])")
_OL = re.compile(r"^\s*(?:\d+|[۰-۹]+)[.)]\s+(.*)$")
_UL = re.compile(r"^\s*[-•*]\s+(.*)$")

LINK_ATTRS = 'target="_blank" rel="nofollow ugc noopener noreferrer"'


def count_links(text):
    return len(_LINK.findall(text or ""))


def _inline(escaped):
    links = []

    def stash(m):
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    text = _LINK.sub(stash, escaped)
    text = _BOLD_ITALIC.sub(r"<strong><em>\1</em></strong>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f'<a href="{links[int(m.group(1))][1]}" {LINK_ATTRS}>{links[int(m.group(1))][0]}</a>', text)


def render(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")[:MAX_LEN]
    lines = escape(text, quote=True).split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("### "):
            flush(); out.append(f"<h4>{_inline(stripped[4:])}</h4>")
        elif stripped.startswith("## "):
            flush(); out.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("&gt;"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith("&gt;"):
                quote.append(lines[i].strip()[4:].strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(_inline(q) for q in quote) + "</blockquote>")
            continue
        elif _UL.match(line) or _OL.match(line):
            flush()
            ordered = bool(_OL.match(line))
            pattern = _OL if ordered else _UL
            items = []
            while i < len(lines) and pattern.match(lines[i]):
                items.append(pattern.match(lines[i]).group(1))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        else:
            para.append(stripped)
        i += 1
    flush()
    return mark_safe("\n".join(out))


def plain(text, limit=200):
    """نسخه‌ی بدون قالب برای خلاصه و meta."""
    t = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text or "")
    t = re.sub(r"[*#>]+|^\s*[-•]\s+", "", t, flags=re.M)
    t = " ".join(t.split())
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"
