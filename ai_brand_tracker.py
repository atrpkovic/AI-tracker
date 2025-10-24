import json
import requests
import os
from datetime import datetime

SERPAPI_KEY = "5d3f50d427ec0c756bc4c02d12d8d6461e4b31dd1d0190d310bc447993ceb27b"
PROMPT = "best budget-friendly tire webshop"


def save_json(data, label):
    """Save the full SerpApi JSON response to disk."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"serpapi_{label}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved {label} JSON to {filename}")


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
            "include_ai_overview": "true",  # forces inclusion
            "ai_mode": "strict"             # filter only responses containing ai_overview
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    save_json(data, "google")

    token = None
    if "ai_overview" in data:
        token = data["ai_overview"].get("page_token")
        print(f"Page token: {token}")
    else:
        print("❌ No ai_overview object in step 1 response.")
    return token


def fetch_google_ai_overview(page_token):
    print(f"🔍 Step 2: engine=google_ai_overview → token {page_token}")
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
    save_json(data, "ai_overview")


def main():
    token = fetch_google_search(PROMPT)
    if token:
        fetch_google_ai_overview(token)
    else:
        print("No token found — cannot proceed to Step 2.")


if __name__ == "__main__":
    main()
