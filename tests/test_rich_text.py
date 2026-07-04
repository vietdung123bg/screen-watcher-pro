"""Tests for the chatbot Markdown/HTML renderer (app/ui/rich_text.py)."""

from __future__ import annotations

import pytest

from app.ui.rich_text import html_to_markdown


# ---- HTML -> Markdown (pure, no Tk) ----

def test_html_inline_to_markdown():
    assert html_to_markdown("<b>Bold</b>") == "**Bold**"
    assert html_to_markdown("<strong>S</strong>") == "**S**"
    assert html_to_markdown("<code>x=1</code>") == "`x=1`"
    assert html_to_markdown('<a href="http://x">t</a>') == "[t](http://x)"


def test_html_plain_text_passthrough():
    # No tags -> returned unchanged (identifiers with underscores untouched).
    s = "latest result for owner_group and chat_agent.py — nothing to convert"
    assert html_to_markdown(s) == s


def test_html_list_becomes_markdown_bullets():
    out = html_to_markdown("<ul><li>a</li><li>b</li></ul>")
    assert "- a" in out and "- b" in out


# ---- Markdown -> Text tags (needs Tk; skip if no display) ----

def _text_widget_or_skip():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception as e:                     # headless CI without a display
        pytest.skip(f"no Tk display: {e}")
    root.withdraw()
    return tk, root


def test_insert_markdown_strips_syntax_and_applies_tags():
    tk, root = _text_widget_or_skip()
    from app.ui.rich_text import configure_markdown_tags, insert_markdown
    t = tk.Text(root)
    configure_markdown_tags(t)
    insert_markdown(t, "### Title\n**bold** and `code` and *it*\n- one\n[link](http://x)")
    content = t.get("1.0", "end")
    assert "**" not in content and "`" not in content   # raw markers removed
    assert t.tag_ranges("md_bold") and t.tag_ranges("md_code")
    assert t.tag_ranges("md_bullet") and t.tag_ranges("md_link")
    root.destroy()


def test_insert_markdown_keeps_underscored_identifiers_literal():
    tk, root = _text_widget_or_skip()
    from app.ui.rich_text import configure_markdown_tags, insert_markdown
    t = tk.Text(root)
    configure_markdown_tags(t)
    insert_markdown(t, "See owner_group and execution_id and chat_agent.py.")
    content = t.get("1.0", "end")
    assert "owner_group" in content and "chat_agent.py" in content
    assert not t.tag_ranges("md_italic")               # underscores are NOT italic
    root.destroy()
