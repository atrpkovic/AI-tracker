# playwright_aio_cdp.py
# Uses your real Chrome profile — no automation banner, no sandbox fingerprint.

import asyncio
import json
import os
import random
import time
from datetime import datetime
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

# Path to your installed Chrome executable
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# Path to your real Chrome profile (Profile 1 or Default)
USER_DATA_DIR = r"C:\Users\MDC21\AppData\Local\Google\Chrome\User Data"
SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

KEYWORD = "what ply is load range e"
WAIT_MIN, WAIT_MAX = 5, 10


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def main():
    print("🚀 Starting Chrome via CDP (no automation banner)...")

    # 1️⃣ Start your actual Chrome manually
    # (Playwright will attach to it via remote debugging)
    os.system(f'"{CHROME_PATH}" --remote-debugging-port=9222 --user-data-dir="{USER_DATA_DIR}"')

    print("🕓 Waiting a few seconds for Chrome to start...")
    await asyncio.sleep(5)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        q = quote_plus(KEYWORD)
        url = f"https://www.google.com/search?q={q}&hl=en"
        print(f"🔍 Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")

        # Simulate human delay + scroll
        await asyncio.sleep(random.uniform(WAIT_MIN, WAIT_MAX))
        for _ in range(random.randint(1, 3)):
            await page.mouse.wheel(0, random.randint(400, 900))
            await asyncio.sleep(random.uniform(0.8, 1.5))

        html = await page.content()
        if "Our systems have detected unusual traffic" in html:
            print("⚠️ CAPTCHA triggered even in CDP mode. Solve manually in the Chrome window, then press Enter.")
            input("✅ Press Enter here after solving manually...")

        # Try to locate AI Overview section
        aio_locator = page.locator("div:has-text('AI Overview')")
        if await aio_locator.count() > 0:
            text_blocks = await aio_locator.locator("p, li").all_inner_texts()
            links = [
                href
                for href in await aio_locator.locator("a").evaluate_all(
                    "els => els.map(a => a.href).filter(h => h && h.startsWith('http'))"
                )
            ]
            aio_data = {"keyword": KEYWORD, "text": " ".join(text_blocks), "links": links}
            out = os.path.join(SNAPSHOT_DIR, f"aio_cdp_result_{_stamp()}.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(aio_data, f, indent=2)
            print(f"✅ Found AI Overview, saved to {out}")
        else:
            out = os.path.join(SNAPSHOT_DIR, f"aio_cdp_snapshot_{_stamp()}.html")
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"⚠️ No AI Overview detected, saved HTML snapshot: {out}")

        await browser.close()
        print("✅ Done.")


if __name__ == "__main__":
    asyncio.run(main())
