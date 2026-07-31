import configparser
from datetime import datetime, date
import os
import time
import random
import json
import threading
import pandas as pd
import traceback
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Custom modules
from get_query import *
from get_text_via_ocr_ollama import get_text_from_slow_site
from ai_analysis import *
from check_and_add_to_gsheet import append_to_gsheet

# --- CONFIGURATION & CONSTANTS ---
SEARCH_DELAY_SECONDS = 2  # Default delay between standard search requests (can be overridden by ini)
MAX_RETRIES = 6  # Increased retry limit when encountering rate limits (429)
QUOTA_STATE_FILE = "quota_state.json"
QUOTA_LOCK = threading.Lock()


def get_google_search_engine_credentials(config_file="google_config.ini"):
    """Reads Google API credentials and optional rate-limit settings from the config file.

    NOTE: If DAILY_QUOTA is not provided in the config, we default to 100 (Google free tier).
    """
    config = configparser.ConfigParser()

    if not os.path.exists(config_file):
        print(f"ERROR: Configuration file '{config_file}' not found.")
        return None, None, None, None

    try:
        config.read(config_file)
        if 'google_api' in config:
            api_key = config['google_api'].get('API_KEY')
            cse_id = config['google_api'].get('CSE_ID')

            # Optional tuning parameters
            min_interval = config['google_api'].getfloat('RATE_LIMIT_MIN_INTERVAL_SECONDS', fallback=SEARCH_DELAY_SECONDS)

            # Default to the Google free-tier of 100 queries/day if not specified
            if config['google_api'].get('DAILY_QUOTA') is not None:
                try:
                    daily_quota = config['google_api'].getint('DAILY_QUOTA')
                except Exception:
                    daily_quota = 100
            else:
                daily_quota = 100

            print(f"Using RATE_LIMIT_MIN_INTERVAL_SECONDS={min_interval}, DAILY_QUOTA={daily_quota}")

            return api_key, cse_id, float(min_interval), daily_quota
        else:
            print(f"ERROR: Section '[google_api]' not found in '{config_file}'.")
            return None, None, None, None

    except KeyError as e:
        print(f"ERROR: Missing key in '{config_file}' under [google_api]: {e}")
        return None, None, None, None
    except Exception as e:
        print(f"An unexpected error occurred while reading '{config_file}': {e}")
        return None, None, None, None


def _load_quota_state(path=QUOTA_STATE_FILE):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_quota_state(state, path=QUOTA_STATE_FILE):
    try:
        with open(path, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"WARNING: Failed to persist quota state: {e}")


def increment_daily_count(path=QUOTA_STATE_FILE):
    """Persist a simple per-day counter to avoid exceeding a configured daily quota."""
    with QUOTA_LOCK:
        state = _load_quota_state(path)
        today = date.today().isoformat()
        state.setdefault(today, 0)
        state[today] += 1
        # Optionally prune old days
        for k in list(state.keys()):
            if k != today:
                try:
                    # keep only last 7 days
                    if (date.fromisoformat(today) - date.fromisoformat(k)).days > 7:
                        del state[k]
                except Exception:
                    pass
        _save_quota_state(state)
        return state[today]


def get_daily_count(path=QUOTA_STATE_FILE):
    state = _load_quota_state(path)
    today = date.today().isoformat()
    return int(state.get(today, 0))


# Simple per-process rate limiter (min interval between requests)
_last_request_time = 0.0
_last_request_lock = threading.Lock()


def rate_limited(min_interval_seconds=1.0):
    def decorator(func):
        def wrapper(*args, **kwargs):
            global _last_request_time
            with _last_request_lock:
                now = time.time()
                wait = min_interval_seconds - (now - _last_request_time)
                if wait > 0:
                    time.sleep(wait)
                result = func(*args, **kwargs)
                _last_request_time = time.time()
                return result
        return wrapper
    return decorator


def _extract_retry_after_from_http_error(e):
    """Try to extract Retry-After seconds from a googleapiclient.errors.HttpError if present."""
    try:
        # e.resp may be an httplib2.Response-like object; headers may be dict-like
        hdrs = getattr(e.resp, 'headers', None) or getattr(e.resp, 'get', None)
        if isinstance(hdrs, dict):
            ra = hdrs.get('retry-after') or hdrs.get('Retry-After')
            if ra:
                try:
                    return float(ra)
                except Exception:
                    # could be HTTP date; fallback to None
                    return None
        # Sometimes e.resp has a get method
        if hasattr(e.resp, 'get') and callable(e.resp.get):
            ra = e.resp.get('retry-after') or e.resp.get('Retry-After')
            if ra:
                try:
                    return float(ra)
                except Exception:
                    return None
    except Exception:
        pass
    return None


def programmable_search(service, cse_id, query, retries=MAX_RETRIES, min_interval_seconds=SEARCH_DELAY_SECONDS, daily_quota=None):
    """
    Performs a search using Google's Custom Search Engine API with robust backoff for rate limits.
    - Wraps calls in a client-side rate limiter (min_interval_seconds).
    - Honors Retry-After when present.
    - Persists a daily counter (if daily_quota is set) to avoid overshooting configured quota.
    """
    # Check daily quota before making call
    if daily_quota is not None:
        current = get_daily_count()
        if current >= daily_quota:
            print(f"DAILY QUOTA reached ({current}/{daily_quota}). Skipping query '{query}'.")
            return None

    @rate_limited(min_interval_seconds=min_interval_seconds)
    def _do_request():
        return service.cse().list(
            q=query,
            cx=cse_id,
            num=10,
            sort='date',
            dateRestrict='d1'
        ).execute()

    backoff = 1.0
    for attempt in range(1, retries + 1):
        try:
            result = _do_request()
            # Upon success increment daily counter
            if daily_quota is not None:
                increment_daily_count()
            return result

        except HttpError as e:
            # Try to extract HTTP status safely
            status = None
            try:
                status = int(getattr(e.resp, 'status', None) or getattr(e.resp, 'status_code', None))
            except Exception:
                pass

            # If it's a rate limit, honor Retry-After if present
            if status == 429:
                retry_after = _extract_retry_after_from_http_error(e)
                if retry_after:
                    wait_time = float(retry_after) + random.uniform(0.2, 1.0)
                else:
                    wait_time = backoff + random.uniform(0.5, 1.5)

                print(f"⚠️ Rate limit (429) hit for query '{query}'. Retrying in {wait_time:.1f}s... (Attempt {attempt}/{retries})")
                time.sleep(wait_time)
                backoff = min(backoff * 2, 60)
                continue

            # Transient server errors: retry with backoff
            if status in (500, 502, 503, 504):
                wait_time = backoff + random.uniform(0.5, 1.5)
                print(f"Server error {status} for query '{query}'. Retrying in {wait_time:.1f}s... (Attempt {attempt}/{retries})")
                time.sleep(wait_time)
                backoff = min(backoff * 2, 60)
                continue

            # Non-retryable HTTP error: log and return None
            print(f"HTTP Error for query '{query}': {e}")
            return None

        except Exception as e:
            # Network-level or unexpected error: retry a few times
            if attempt == retries:
                print(f"Unexpected search error for query '{query}': {e}")
                return None
            wait_time = backoff + random.uniform(0.5, 1.5)
            print(f"Transient error for query '{query}': {e}. Retrying in {wait_time:.1f}s... (Attempt {attempt}/{retries})")
            time.sleep(wait_time)
            backoff = min(backoff * 2, 60)
            continue

    print(f"❌ Max retries reached for query '{query}'. Skipping.")
    return None


def main():
    # Get Credentials + optional rate limit settings
    API_KEY, CSE_ID, min_interval_seconds, daily_quota = get_google_search_engine_credentials()

    if not API_KEY or not CSE_ID:
        print("Cannot proceed without valid credentials.")
        return

    # Initialize the Google Service ONCE
    service = build("customsearch", "v1", developerKey=API_KEY)

    # Get queries
    query_list = get_query("query.txt")
    feeds_data = []

    for query in query_list:
        print(f"\nSearching for: {query}")

        search_results = programmable_search(service, CSE_ID, query, retries=MAX_RETRIES,
                                            min_interval_seconds=min_interval_seconds,
                                            daily_quota=daily_quota)

        # Extra safety delay after the search (small buffer)
        time.sleep(0.2)

        if not search_results or 'items' not in search_results:
            print(f"No valid results found or search failed for: {query}")
            continue

        print(f"Found {len(search_results['items'])} results.\n")

        for item in search_results['items']:
            link = item.get('link', '')
            snippet = str(item.get('snippet', ''))

            # Check link filter constraint
            if "status" not in link:
                continue

            print("~~~~~~~~~~~~~~~~~~~~Match~~~~~~~~~~~~~~~~~~~~")
            print(f"Title: {item.get('title')}")

            try:
                date, result = get_text_from_slow_site(link)
                time.sleep(1)  # Small pause to relieve site / local Ollama server

                if result == "Error":
                    continue

                if is_aviation_cyber_incident(result):
                    print(" -> MATCH: Added to feeds.")

                    attacker = get_attacker_data(result)
                    org_info = get_aviation_data(result)
                    geo_info = extract_geo_data(result)
                    attack_type_info = identify_attack_type(result)
                    direct_impact_info = identify_direct_impact(result)
                    motivation_info = identify_motivation(result)

                    attacker_name = attacker.attacker if attacker else ""
                    organizations = ", ".join([entity.name for entity in
                                               org_info.organizations]) if org_info and org_info.organizations else ""
                    aviation_entities = ", ".join([entity.entity_type for entity in
                                                   org_info.organizations]) if org_info and org_info.organizations else ""
                    country = geo_info.country if geo_info else ""
                    region = geo_info.region if geo_info else ""

                    feeds_data.append({
                        "query": query,
                        "title": item.get('title'),
                        "snippet": snippet,
                        "url": link,
                        "date": date,
                        "threat actor": attacker_name,
                        "organizations": organizations,
                        "aviation entity": aviation_entities,
                        "country": country,
                        "region": region,
                        "remarks": "",
                        "analyst review": ""
                    })

                else:
                    print(" -> NO MATCH: Skipped.")

            except Exception as e:
                print(f"Error processing item link ({link}): {e}")

    # Process collected data
    if feeds_data:
        print(f"\nProcessing {len(feeds_data)} matched items...")
        df = pd.DataFrame(feeds_data)

        # Output local copy
        df.to_excel("test.xlsx", index=False)

        deduped_df = df.drop_duplicates(subset=['url'])

        try:
            append_to_gsheet(deduped_df)
            print("Data successfully processed.")
        except Exception as e:
            print(f"ERROR calling check_and_add_to_gsheet: {e}")
            raise
    else:
        print("\nNo matching recent feeds data found today.")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    try:
        main()
    except Exception as main_e:
        error_details = traceback.format_exc()
        print(f"\nCRASH DETECTED:\n{error_details}")
