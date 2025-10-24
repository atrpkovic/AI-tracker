# aio_playwright_fallback.py
import os
import time
import random
import json
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from datetime import datetime

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

def fetch_ai_overview_browser(keyword, session_path="session.json", headless=True, save_snapshot=False):
    """
    Stealth Playwright fallback to fetch AI Overview text + links for `keyword`.
    Returns {"text": str, "links": [str], "snapshot": optional filename}
    """
    result = {"text": "", "links": [], "snapshot": None}
    safe_kw = keyword.replace(" ", "_")[:40]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-extensions",
                    "--disable-gpu",
                    "--window-size=1280,800",
                ],
            )

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": random.randint(1200, 1400), "height": random.randint(700, 900)},
                locale="en-US",
                storage_state=session_path if os.path.exists(session_path) else None,
            )

            page = context.new_page()
            stealth_sync(page)

            query = keyword.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}&hl=en"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Simulate human-like behavior
            time.sleep(random.uniform(3.5, 6.5))
            for _ in range(random.randint(1, 3)):
                page.mouse.wheel(0, random.randint(400, 800))
                time.sleep(random.uniform(0.5, 1.5))

            html = page.content()

            # Try to locate the AI Overview
            try:
                blocks = page.locator("div:has-text('AI Overview')").locator("p, li").all_inner_texts()
                if blocks:
                    result["text"] = " ".join(blocks)
                anchors = page.locator("div:has-text('AI Overview') a").all()
                for a in anchors:
                    href = a.get_attribute("href")
                    if href and href.startswith("http"):
                        result["links"].append(href)
            except Exception:
                if "AI Overview" in html or 'data-md="AIOverview"' in html:
                    anchors = page.locator("a").all()
                    for a in anchors:
                        href = a.get_attribute("href")
                        if href and href.startswith("http"):
                            result["links"].append(href)

            # Optionally save snapshot for debugging
            if save_snapshot:
                snap_name = f"playwright_snapshot_{safe_kw}_{timestamp}.html"
                with open(snap_name, "w", encoding="utf-8") as fh:
                    fh.write(page.content())
                result["snapshot"] = snap_name

            # Save session for continuity
            context.storage_state(path=session_path)
            context.close()
            browser.close()

    except Exception as e:
        result["error"] = str(e)

    return result
