"""Lightweight Markdown + basic HTML renderer for a Tkinter ``tk.Text`` widget.

The chatbot's LLM replies are Markdown (and sometimes HTML). Tk's Text widget has
no markdown engine, so we parse a practical subset and apply Text *tags* for
styling — no external dependency.

Supported:
  * Markdown: headings (#..###), **bold**, *italic*, ***bold-italic***, `inline
    code`, ``` fenced code blocks ```, - / * / + and 1. lists, > blockquotes,
    --- horizontal rules, [text](url) links.
  * HTML: common inline/block tags are converted to their Markdown equivalent
    first (<b>/<strong>, <i>/<em>, <code>, <br>, <p>, <ul>/<li>, <h1..6>, <a>,
    table rows) and entities are decoded.

Single underscores are intentionally NOT treated as italic so identifiers like
``owner_group`` / ``chat_agent.py`` render literally.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ---- tag setup -------------------------------------------------------------

def configure_markdown_tags(text, family: str = "Segoe UI", size: int = 11) -> None:
    """Register the styling tags used by insert_markdown() on a Text widget."""
    text.tag_configure("md_bold", font=(family, size, "bold"))
    text.tag_configure("md_italic", font=(family, size, "italic"))
    text.tag_configure("md_bolditalic", font=(family, size, "bold italic"))
    text.tag_configure("md_h1", font=(family, size + 4, "bold"), spacing1=6, spacing3=3)
    text.tag_configure("md_h2", font=(family, size + 2, "bold"), spacing1=5, spacing3=2)
    text.tag_configure("md_h3", font=(family, size + 1, "bold"), spacing1=4, spacing3=2)
    text.tag_configure("md_code", font=("Consolas", size - 1), background="#eef0f2")
    text.tag_configure("md_codeblock", font=("Consolas", size - 1), background="#f0f2f4",
                       lmargin1=18, lmargin2=18)
    text.tag_configure("md_bullet", lmargin1=18, lmargin2=32)
    text.tag_configure("md_quote", foreground="#666666", lmargin1=14, lmargin2=14)
    text.tag_configure("md_link", foreground="#0066cc", underline=1)


# ---- HTML -> Markdown ------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<\/?[a-zA-Z][^>]*>")


class _HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)   # entities decoded into data
        self.out: list[str] = []
        self._href = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("b", "strong"):
            self.out.append("**")
        elif tag in ("i", "em"):
            self.out.append("*")
        elif tag == "code":
            self.out.append("`")
        elif tag == "br":
            self.out.append("\n")
        elif tag in ("p", "div", "ul", "ol", "tr"):
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "a":
            self._href = dict(attrs).get("href", "") or ""
            self.out.append("[")

    def handle_endtag(self, tag):
        if tag in ("b", "strong"):
            self.out.append("**")
        elif tag in ("i", "em"):
            self.out.append("*")
        elif tag == "code":
            self.out.append("`")
        elif tag in ("p", "div", "ul", "ol") or re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n")
        elif tag == "a":
            self.out.append(f"]({self._href})")

    def handle_data(self, data):
        self.out.append(data)


def html_to_markdown(s: str) -> str:
    """Convert a string that CONTAINS HTML into Markdown; pass plain text through."""
    if not _HTML_TAG_RE.search(s):
        return s
    parser = _HTMLToMarkdown()
    try:
        parser.feed(s)
        parser.close()
        return "".join(parser.out)
    except Exception:
        return s


# ---- Markdown -> Text tags -------------------------------------------------

# Inline spans, tried in this order. Underscores are NOT italic (see module doc).
_INLINE = re.compile(
    r"\*\*\*(?P<bi>.+?)\*\*\*"
    r"|\*\*(?P<b>.+?)\*\*"
    r"|`(?P<code>[^`]+?)`"
    r"|\[(?P<ltext>[^\]]+?)\]\((?P<lurl>[^)]+?)\)"
    r"|\*(?P<i>[^*]+?)\*",
    re.DOTALL,
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")


def _ins(text, s: str, tags=()):
    text.insert("end", s, tags)


def _insert_inline(text, s: str, base_tags=()):
    pos = 0
    for m in _INLINE.finditer(s):
        if m.start() > pos:
            _ins(text, s[pos:m.start()], base_tags)
        if m.group("bi") is not None:
            _ins(text, m.group("bi"), base_tags + ("md_bolditalic",))
        elif m.group("b") is not None:
            _ins(text, m.group("b"), base_tags + ("md_bold",))
        elif m.group("code") is not None:
            _ins(text, m.group("code"), base_tags + ("md_code",))
        elif m.group("ltext") is not None:
            _ins(text, m.group("ltext"), base_tags + ("md_link",))
        elif m.group("i") is not None:
            _ins(text, m.group("i"), base_tags + ("md_italic",))
        pos = m.end()
    if pos < len(s):
        _ins(text, s[pos:], base_tags)


def insert_markdown(text, md: str, base_tags: tuple = ()) -> None:
    """Render `md` (Markdown, possibly with HTML) into `text` at its end using tags.

    The widget should already be in a writable state (state='normal')."""
    md = html_to_markdown(md)
    in_code = False
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            _ins(text, line + "\n", base_tags + ("md_codeblock",))
            continue
        if _HR.match(line):
            _ins(text, "─" * 40 + "\n", base_tags + ("md_quote",))
            continue
        m = _HEADING.match(line)
        if m:
            lvl = len(m.group(1))
            tag = "md_h1" if lvl == 1 else "md_h2" if lvl == 2 else "md_h3"
            _insert_inline(text, m.group(2), base_tags + (tag,))
            _ins(text, "\n", base_tags)
            continue
        m = _QUOTE.match(line)
        if m:
            _insert_inline(text, m.group(1), base_tags + ("md_quote",))
            _ins(text, "\n", base_tags)
            continue
        m = _BULLET.match(line)
        if m:
            _ins(text, m.group(1) + "• ", base_tags + ("md_bullet",))
            _insert_inline(text, m.group(2), base_tags + ("md_bullet",))
            _ins(text, "\n", base_tags)
            continue
        m = _NUMBERED.match(line)
        if m:
            _ins(text, f"{m.group(1)}{m.group(2)}. ", base_tags + ("md_bullet",))
            _insert_inline(text, m.group(3), base_tags + ("md_bullet",))
            _ins(text, "\n", base_tags)
            continue
        _insert_inline(text, line, base_tags)
        _ins(text, "\n", base_tags)
