import json
import requests
import csv
from datetime import datetime, timezone
import time
import os
import random
from urllib.parse import urlparse
from typing import Optional, List
import logging
import os
from dotenv import load_dotenv
import google.generativeai as genai # <-- NEW IMPORT

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====== CONFIG ======
load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # <-- NEW: Add this to your .env file
KEYWORDS_FILE = "keywords.csv"
BRANDS_FILE = "brands.json"
OUTPUT_FILE = "ai_overview_brand_hits_master.csv"
SAVE_JSON = True

# Rate limiting (SerpApi allows ~100 searches/hour on free tier)
MIN_DELAY = 2
MAX_DELAY = 5

# Set to False for production
DEBUG_MODE = False
# ====================

# --- NEW: Configure Gemini ---
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("Gemini API configured successfully.")
    except Exception as e:
        logger.error(f"Error configuring Gemini API: {e}")
        GEMINI_API_KEY = None # Disable if config fails
else:
    logger.warning("GEMINI_API_KEY not found in .env. Sentiment analysis will be skipped.")
# -----------------------------


def _now_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def _safe_name(s: str, limit=40):
    return "".join(c for c in s.replace(" ", "_")[:limit] if c.isalnum() or c in ("_", "-"))


# --- NEW: Sentiment Analysis Function ---
def get_llm_sentiment(overview_text: str, brand: str, retries: int = 3) -> str:
    """Analyzes the sentiment of an AI overview for a specific brand using Gemini."""
    global GEMINI_API_KEY

    if not GEMINI_API_KEY:
        return "not_configured"

    # Check if text is too short to be meaningful
    if not overview_text or len(overview_text) < 20:
        logger.warning(f"Overview text for '{brand}' is too short, skipping sentiment.")
        return "no_text"
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash') # Use a fast and modern model
    except Exception as e:
        logger.error(f"Could not initialize Gemini model: {e}")
        return "model_error"

    prompt = f"""
    You are a brand sentiment analyzer. Analyze the following AI-generated Overview 
    to determine the sentiment *specifically* towards the brand: "{brand}".

    Respond with only one word: good, neutral, or bad.

    Rules:
    - good: The text speaks positively about the brand, recommends it, or it's the primary positive subject.
    - neutral: The text is purely informational, lists the brand as an option, or the mention is not detrimental (e.g., just a citation).
    - bad: The text is negative, mentions complaints, warns against the brand, or highlights a competitor over it.

    AI Overview Text:
    "{overview_text}"

    Your one-word-answer:
    """

    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            sentiment = response.text.strip().lower()
            
            # Basic validation
            if sentiment in ["good", "neutral", "bad"]:
                return sentiment
            else:
                logger.warning(f"Unexpected sentiment response: '{sentiment}'. Defaulting to neutral.")
                return "neutral"
                
        except Exception as e:
            logger.error(f"Gemini API error (attempt {attempt+1}/{retries}): {e}")
            if "API key not valid" in str(e):
                logger.error("❌ Invalid Gemini API key. Disabling sentiment analysis.")
                GEMINI_API_KEY = None # <-- This line now works
                return "api_key_invalid"
            time.sleep(2 * (attempt + 1)) # Exponential backoff
    
    logger.error(f"Sentiment analysis failed for '{brand}' after {retries} attempts.")
    return "error"
# ------------------------------------


def save_json(data, label, keyword):
    if not SAVE_JSON:
        return None
    fname = f"serpapi_{label}_{_safe_name(keyword)}_{_stamp()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved JSON: {fname}")
    return fname

def normalize_host(u: str) -> str:
    try:
        host = urlparse(u).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""

def extract_urls_from_aio(aio_json: dict) -> set:
    """Extract all URLs from AI Overview JSON structure"""
    urls = set()
    if not isinstance(aio_json, dict):
        return urls

    # Extract from references array
    for ref in aio_json.get("references", []) or []:
        if isinstance(ref, dict):
            link = ref.get("link")
            if isinstance(link, str) and link.startswith("http"):
                urls.add(link)

    # Extract from text_blocks
    for block in aio_json.get("text_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        
        # snippet_links within blocks
        for sl in block.get("snippet_links", []) or []:
            if isinstance(sl, dict):
                link = sl.get("link")
                if isinstance(link, str) and link.startswith("http"):
                    urls.add(link)
        
        # list items within blocks
        if isinstance(block.get("list"), list):
            for item in block["list"]:
                if isinstance(item, dict):
                    link = item.get("link")
                    if isinstance(link, str) and link.startswith("http"):
                        urls.add(link)
    
    return urls

def flatten_json(obj):
    """Recursively extract all string values from nested JSON"""
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(flatten_json(v))
    elif isinstance(obj, list):
        for i in obj:
            out.extend(flatten_json(i))
    elif isinstance(obj, str):
        out.append(obj)
    return out

def find_brands_in_aio(aio_json: dict, brands_file: str, keyword: str, source: str = "SerpApi") -> List[list]:
    """Match brands in AI Overview data"""
    with open(brands_file, "r", encoding="utf-8") as f:
        brands = json.load(f)

    brand_map = {
        domain.lower(): [domain.lower()] + [a.lower() for a in aliases]
        for domain, aliases in brands.items()
    }

    ts = _now_ts()
    results, seen = [], set()

    # --- MODIFIED: Extract the main overview text for sentiment analysis ---
    overview_text = aio_json.get("answer", "")
    if not overview_text:
        overview_text = aio_json.get("snippet", "") # Fallback
        if not overview_text:
             logger.warning("Could not find 'answer' or 'snippet' for overview text.")
             overview_text = "" # Ensure it's a string
    # -----------------------------------------------------------------

    urls = extract_urls_from_aio(aio_json)
    hosts = {u: normalize_host(u) for u in urls}
    flat_text = " ".join(flatten_json(aio_json)).lower()

    if DEBUG_MODE:
        logger.debug(f"Found {len(urls)} URLs in AI Overview")
        logger.debug(f"Text length: {len(flat_text)} chars")

    for domain, terms in brand_map.items():
        domain_core = domain[4:] if domain.startswith("www.") else domain

        # Priority 1: URL match (most reliable)
        matched_url = None
        for u, h in hosts.items():
            if h.endswith(domain_core):
                matched_url = u
                break
        
        if matched_url and (keyword, domain) not in seen:
            seen.add((keyword, domain))
            
            # --- NEW: Get sentiment ---
            sentiment = get_llm_sentiment(overview_text, domain)
            logger.info(f"Sentiment for '{domain}' (URL Match): {sentiment}")
            # --------------------------

            # --- MODIFIED: Add new columns to row ---
            results.append([
                ts, 
                keyword, 
                domain, 
                domain, # Matched Term
                overview_text, 
                sentiment, 
                matched_url[:200], # Context
                matched_url, # URL
                source
            ])
            # ----------------------------------------

            if DEBUG_MODE:
                logger.debug(f"Matched brand by URL: {domain} -> {matched_url}")
            continue

        # Priority 2: Text alias match
        alias = next((t for t in terms[1:] if t in flat_text), None)
        if alias and (keyword, domain) not in seen:
            seen.add((keyword, domain))
            any_url = next(iter(urls), "") # Get any related URL as context
            
            # --- NEW: Get sentiment ---
            sentiment = get_llm_sentiment(overview_text, domain)
            logger.info(f"Sentiment for '{domain}' (Alias Match): {sentiment}")
            # --------------------------

            # --- MODIFIED: Add new columns to row ---
            results.append([
                ts, 
                keyword, 
                domain, 
                alias, # Matched Term
                overview_text, 
                sentiment,
                alias, # Context
                any_url, # URL
                source
            ])
            # ----------------------------------------

            if DEBUG_MODE:
                logger.debug(f"Matched brand by alias: {domain} -> {alias}")

    return results

def fetch_google_search_serpapi(keyword: str, max_retries: int = 3) -> Optional[dict]:
    """
    Fetch Google search with AI Overview via SerpApi
    FIXED: Proper error handling and response validation
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"SerpApi request {attempt}/{max_retries}: {keyword}")
            
            response = requests.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google",
                    "q": keyword,
                    "api_key": SERPAPI_KEY,
                    "hl": "en",
                    "gl": "us",
                    "device": "desktop",
                    "num": 10,
                },
                timeout=30,
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Check for API errors
            if "error" in data:
                logger.error(f"SerpApi error: {data['error']}")
                if "Invalid API key" in str(data['error']):
                    logger.error("❌ Invalid API key - check your SERPAPI_KEY")
                    return None
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return None
            
            # Validate response structure
            if "search_metadata" not in data:
                logger.warning(f"Unexpected response structure")
                if attempt < max_retries:
                    time.sleep(3)
                    continue
                return None
            
            return data
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}")
            if attempt < max_retries:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            if attempt < max_retries:
                time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            break
    
    return None

def process_keyword(keyword: str, brands_file: str) -> tuple:
    """Process a single keyword with SerpApi"""
    
    # Fetch search results
    data = fetch_google_search_serpapi(keyword)
    
    if not data:
        return [], "API_ERROR"
    
    # Save full response if debugging
    if SAVE_JSON:
        save_json(data, "search_results", keyword)
    
    # Check if AI Overview exists
    if "ai_overview" not in data:
        logger.info(f"No AI Overview found for: {keyword}")
        return [], "NO_AIO"
    
    aio_json = data["ai_overview"]
    
    # Validate AI Overview structure
    if not isinstance(aio_json, dict):
        logger.warning(f"Invalid AI Overview structure for: {keyword}")
        return [], "INVALID_AIO"
    
    logger.info(f"✓ AI Overview found for: {keyword}")
    
    # Save AI Overview separately if needed
    if SAVE_JSON:
        save_json({"ai_overview": aio_json}, "ai_overview", keyword)
    
    # Find brand mentions
    rows = find_brands_in_aio(aio_json, brands_file, keyword)
    
    return rows, "SUCCESS"

def check_serpapi_account():
    """Check SerpApi account info"""
    try:
        response = requests.get(
            "https://serpapi.com/account",
            params={"api_key": SERPAPI_KEY},
            timeout=10
        )
        data = response.json()
        
        if "error" in data:
            logger.error(f"Account check failed: {data['error']}")
            return None
        
        searches_left = data.get("total_searches_left", "unknown")
        plan = data.get("plan_name", "unknown")
        
        logger.info(f"📊 SerpApi Account: {plan}")
        logger.info(f"📊 Searches remaining: {searches_left}")
        
        return data
    except Exception as e:
        logger.warning(f"Could not check account: {e}")
        return None

def main():
    logger.info("🚀 Starting AI Overview Brand Tracker\n")
    
    # Check account
    logger.info("Checking SerpApi account...")
    account = check_serpapi_account()
    if not account:
        logger.warning("⚠️ Could not verify account, but continuing anyway...")
    
    # Validate files
    if not os.path.exists(KEYWORDS_FILE):
        logger.error(f"Keywords file not found: {KEYWORDS_FILE}")
        return
    if not os.path.exists(BRANDS_FILE):
        logger.error(f"Brands file not found: {BRANDS_FILE}")
        return

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    logger.info(f"Loaded {len(keywords)} keywords\n")

    # --- MODIFIED: Initialize output CSV with new header ---
    header = ["Timestamp", "Keyword", "Brand", "Matched Term", "AI_Overview_Text", "Sentiment", "Context", "URL", "Source"]
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
    # -------------------------------------------------------
    
    # Process keywords
    stats = {
        "total": len(keywords),
        "success": 0,
        "no_aio": 0,
        "api_error": 0,
        "brands_found": 0
    }
    
    for i, keyword in enumerate(keywords, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i}/{len(keywords)}] Processing: {keyword}")
        logger.info(f"{'='*60}")
        
        try:
            rows, status = process_keyword(keyword, BRANDS_FILE)
            
            # Update stats
            if status == "SUCCESS":
                stats["success"] += 1
            elif status == "NO_AIO":
                stats["no_aio"] += 1
            elif status == "API_ERROR":
                stats["api_error"] += 1
            
            # Save results
            if rows:
                with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
                stats["brands_found"] += len(rows)
                logger.info(f"✅ Found {len(rows)} brand mention(s)")
            else:
                logger.info(f"ℹ️ No brand mentions (Status: {status})")
            
            # Rate limiting
            if i < len(keywords):  # Don't delay after last keyword
                delay = random.uniform(MIN_DELAY, MAX_DELAY)
                logger.info(f"⏳ Waiting {delay:.1f}s before next request...")
                time.sleep(delay)

        except KeyboardInterrupt:
            logger.info("\n⚠️ Interrupted by user")
            break
        except Exception as e:
            logger.error(f"❌ Error processing '{keyword}': {e}")
            stats["api_error"] += 1
            continue

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ PROCESSING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"📊 Total keywords: {stats['total']}")
    logger.info(f"📊 Successful: {stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)" if stats['total'] > 0 else "N/A")
    logger.info(f"📊 No AI Overview: {stats['no_aio']} ({stats['no_aio']/stats['total']*100:.1f}%)" if stats['total'] > 0 else "N/A")
    logger.info(f"📊 API Errors: {stats['api_error']}")
    logger.info(f"📊 Total brand mentions: {stats['brands_found']}")
    logger.info(f"📁 Results saved to: {OUTPUT_FILE}")
    
    # Check account again to see usage
    check_serpapi_account()

if __name__ == "__main__":
    main()