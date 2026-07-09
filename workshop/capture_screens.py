"""Capture real /admin UI screenshots as evidence PNGs, cropped to real content."""
from __future__ import annotations

import pathlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = pathlib.Path(__file__).resolve().parent / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    page.wait_for_timeout(400)
    # real content bottom = bottom of <main> (content pages), capped
    h = page.evaluate(
        "(() => { const m = document.querySelector('main');"
        " return Math.min(Math.ceil(m ? m.getBoundingClientRect().bottom + 20 : 760), 1900); })()")
    page.screenshot(path=str(OUT / name), clip={"x": 0, "y": 0, "width": 1280, "height": h})
    print("saved", name, "h=", h)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    # content pages: tall viewport so everything renders, then clip to <main> bottom
    page = browser.new_page(viewport={"width": 1280, "height": 1900})
    page.goto(f"{BASE}/admin/login"); page.wait_for_load_state("networkidle")
    page.fill("input[name=username]", "admin"); page.fill("input[name=password]", "admin123")
    page.click("button[type=submit]"); page.wait_for_load_state("networkidle")
    for url, name in [
        ("/admin/review-queue", "s02_review_queue.png"),
        ("/admin/sos", "s03_sos_pending.png"),
        ("/admin/rules", "s08_rules_after.png"),
        ("/admin/events", "s05_events.png"),
        ("/admin/rules/new", "s06_rule_new.png"),
        ("/admin/audit", "s09_audit_after.png"),
    ]:
        page.goto(BASE + url); page.wait_for_load_state("networkidle"); shot(page, name)

    # login: its own compact viewport (card is centered in the viewport)
    lp = browser.new_page(viewport={"width": 1100, "height": 620})
    lp.goto(f"{BASE}/admin/login"); lp.wait_for_load_state("networkidle")
    lp.wait_for_timeout(300)
    lp.screenshot(path=str(OUT / "s01_login.png"))
    print("saved s01_login.png")
    browser.close()
print("DONE")
