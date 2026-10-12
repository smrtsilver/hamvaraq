"""
اسکرین‌شات‌های manifest (فروشگاه/نصب PWA). سرور توسعه با داده‌ی نمونه باید بالا باشه:
  python manage.py seed_demo && python manage.py runserver 8765
  python scripts/build_screenshots.py [http://localhost:8765]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = Path(__file__).resolve().parent.parent / "static" / "brand" / "screenshots"
SHOTS = [("narrow-1", "/", 390, 844), ("narrow-2", "/books/", 390, 844), ("narrow-3", "/books/2/", 390, 844),
         ("wide-1", "/", 1280, 720), ("wide-2", "/books/", 1280, 720)]

OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    for name, path, w, h in SHOTS:
        page = browser.new_context(viewport={"width": w, "height": h}, locale="fa-IR", is_mobile=w < 600, device_scale_factor=1).new_page()
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"{name}.png"))
        print("ساخته شد:", OUT / f"{name}.png")
    browser.close()
