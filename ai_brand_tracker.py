import json
import requests
import csv
from datetime import datetime
import time
import os

SERPAPI_KEY = "5d3f50d427ec0c756bc4c02d12d8d6461e4b31dd1d0190d310bc447993ceb27b"
KEYWORDS_FILE = r"C:\Users\MDC21\vsfiles\.vscode\AIO tracker\keywords.csv"
BRANDS_FILE = r"C:\Users\MDC21\vsfiles\.vscode\AIO tracker\brands.json"

OUTPUT_FILE = "ai_overview_brand_hits_master.csv"


def save_json(data, label, keyword):
    """Save the SerpApi JSON response for debugging and auditing."""
    safe_keyword = keyword.replace(" ", "_")[:40]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"serpapi_{label}_{safe_keyword}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved {label} JSON to {filename}")
    return filename


def flatten_json(obj):
    """Recursively collect all text and URLs from JSON."""
    items = []
    if isinstance(obj, dict):
        for v in obj.values():
            items.extend(flatten_json(v))
    elif isinstance(obj, list):
        for i in obj:
            items.extend(flatten_json(i))
    elif isinstance(obj, str):
        items.append(obj)
    return items


def find_brands_in_json(json_file, brands_file, keyword):
    """Scan JSON for brand mentions and deduplicate results."""
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(brands_file, "r", encoding="utf-8") as f:
        brands = json.load(f)

    brand_map = {
        domain: [domain.lower()] + [a.lower() for a in aliases]
        for domain, aliases in brands.items()
    }

    all_text = flatten_json(data)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    results = []
    seen = set()  # 🧩 store (keyword, brand) pairs we've already logged

    for domain, terms in brand_map.items():
        found_match = False  # flag to track if this brand was already found
        for term in terms:
            if found_match:
                break  # stop checking further aliases for this brand
            for entry in all_text:
                entry_lower = entry.lower()
                if term in entry_lower:
                    if (keyword, domain) not in seen:
                        seen.add((keyword, domain))
                        url = entry if entry_lower.startswith("http") else ""
                        context = entry[:200].replace("\n", " ")
                        results.append([
                            timestamp,
                            keyword,
                            domain,
                            term,
                            context,
                            url
                        ])
                        found_match = True
                        break  # stop once we find the brand once

    return results

def fetch_google_search(prompt):
    """Fetch Google SERP data and extract AI Overview page_token."""
    print(f"\n🔍 Step 1: engine=google → {prompt}")
    r = requests.get(
        "https://serpapi.com/search",
        params={
            "engine": "google",
            "q": prompt,
            "hl": "en",
            "api_key": SERPAPI_KEY,
            "no_cache": "true",
            "google_domain": "google.com",
            "location": "United States",
            "safe": "active",
            "device": "desktop",
            "num": 10,
            "include_ai_overview": "true",
            "ai_mode": "strict"
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "ai_overview" in data:
        token = data["ai_overview"].get("page_token")
        return token
    else:
        print("❌ No ai_overview object found.")
        return None


def fetch_google_ai_overview(page_token, keyword):
    """Fetch the AI Overview JSON using page_token."""
    print(f"🔍 Step 2: engine=google_ai_overview → {keyword}")
    r = requests.get(
        "https://serpapi.com/search",
        params={
            "engine": "google_ai_overview",
            "page_token": page_token,
            "api_key": SERPAPI_KEY,
            "output": "json",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return save_json(data, "ai_overview", keyword)

def main():
    print("🚀 Starting AI Overview Brand Tracker\n")

    # Read keywords
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    # Prepare output CSV
    header = ["Timestamp", "Keyword", "Brand", "Matched Term", "Context", "URL"]
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)

    for keyword in keywords:
        try:
            token = fetch_google_search(keyword)
            if not token:
                print(f"⚠️ Skipping '{keyword}' (no AI Overview found)\n")
                continue

            json_file = fetch_google_ai_overview(token, keyword)
            results = find_brands_in_json(json_file, BRANDS_FILE, keyword)

            if results:
                with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(results)
                print(f"✅ Recorded {len(results)} brand mentions for '{keyword}'\n")
            else:
                print(f"⚠️ No brand mentions found for '{keyword}'\n")

            # Rate limit to avoid API throttling
            time.sleep(5)

        except requests.HTTPError as e:
            print(f"❌ HTTP error for '{keyword}': {e}")
        except Exception as e:
            print(f"❌ Unexpected error for '{keyword}': {e}")

    print("\n✅ All keywords processed.")
    print(f"📊 Results saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
