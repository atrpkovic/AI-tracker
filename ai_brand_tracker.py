import json
import requests
import os
from datetime import datetime
import csv

SERPAPI_KEY = "5d3f50d427ec0c756bc4c02d12d8d6461e4b31dd1d0190d310bc447993ceb27b"
PROMPT = "best budget-friendly tire webshop"

BRANDS_FILE = r"C:\Users\MDC21\vsfiles\.vscode\AIO tracker\brands.json"

def save_json(data, label):
    """Save full SerpApi JSON to disk."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"serpapi_{label}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved {label} JSON to {filename}")
    return filename


def fetch_google_search(prompt):
    print(f"🔍 Step 1: engine=google → {prompt}")
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
    #save_json(data, "google")

    token = None
    if "ai_overview" in data:
        token = data["ai_overview"].get("page_token")
    else:
        print("❌ No ai_overview object in step 1 response.")
    return token


def fetch_google_ai_overview(page_token):
    print(f"🔍 Step 2: engine=google_ai_overview")
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
    filename = save_json(data, "ai_overview")
    return filename


def flatten_json(obj):
    """Recursively collect all text and URLs."""
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                items.extend(flatten_json(v))
            elif isinstance(v, str):
                items.append(v)
    elif isinstance(obj, list):
        for i in obj:
            items.extend(flatten_json(i))
    return items


def find_brands_in_json(json_file, brands_file):
    """Scan JSON for brand mentions."""
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(brands_file, "r", encoding="utf-8") as f:
        brands = json.load(f)

    brand_map = {}
    for domain, aliases in brands.items():
        all_terms = [domain.lower()] + [a.lower() for a in aliases]
        brand_map[domain] = all_terms

    all_text = flatten_json(data)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    for domain, terms in brand_map.items():
        for term in terms:
            for entry in all_text:
                entry_lower = entry.lower()
                if term in entry_lower:
                    url = entry if entry_lower.startswith("http") else ""
                    context = entry[:200].replace("\n", " ")
                    results.append([timestamp, domain, term, context, url])

    if results:
        output = f"ai_overview_brand_hits_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Brand", "Matched Term", "Context", "URL"])
            writer.writerows(results)
        print(f"✅ Found {len(results)} brand mentions. Results saved to {output}")
    else:
        print("⚠️ No brand mentions found.")


def main():
    token = fetch_google_search(PROMPT)
    if token:
        json_file = fetch_google_ai_overview(token)
        find_brands_in_json(json_file, BRANDS_FILE)
    else:
        print("No token found — cannot proceed to Step 2.")


if __name__ == "__main__":
    main()
