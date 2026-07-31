import configparser
from datetime import datetime
import os
import time
import random
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
SEARCH_DELAY_SECONDS = 2  # Delay between standard search requests
MAX_RETRIES = 3  # Retry limit when encountering rate limits (429)


def get_google_search_engine_credentials(config_file="google_config.ini"):
    """Reads Google API credentials from the config file."""
    config = configparser.ConfigParser()

    if not os.path.exists(config_file):
        print(f"ERROR: Configuration file '{config_file}' not found.")
        return None, None

    try:
        config.read(config_file)
        if 'google_api' in config:
            api_key = config['google_api']['API_KEY']
            cse_id = config['google_api']['CSE_ID']
            return api_key, cse_id
        else:
            print(f"ERROR: Section '[google_api]' not found in '{config_file}'.")
            return None, None

    except KeyError as e:
        print(f"ERROR: Missing key in '{config_file}' under [google_api]: {e}")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred while reading '{config_file}': {e}")
        return None, None


def programmable_search(service, cse_id, query, retries=MAX_RETRIES):
    """
    Performs a search using Google's Custom Search Engine API with backoff for rate limits.
    """
    for attempt in range(retries):
        try:
            # Added `dateRestrict='d1'` to filter results from the past 24 hours directly at API level
            result = service.cse().list(
                q=query,
                cx=cse_id,
                num=10,
                sort='date',
                dateRestrict='d1'
            ).execute()
            return result

        except HttpError as e:
            if e.resp.status == 429:
                # Calculate backoff with jitter (e.g., 4s, 8s, 16s + small random variance)
                wait_time = (2 ** (attempt + 2)) + random.uniform(0.5, 1.5)
                print(
                    f"⚠️ Rate limit (429) hit for query '{query}'. Retrying in {wait_time:.1f}s... (Attempt {attempt + 1}/{retries})")
                time.sleep(wait_time)
            else:
                print(f"HTTP Error for query '{query}': {e}")
                return None
        except Exception as e:
            print(f"Unexpected search error for query '{query}': {e}")
            return None

    print(f"❌ Max retries reached for query '{query}'. Skipping.")
    return None


def main():
    # Get Credentials
    API_KEY, CSE_ID = get_google_search_engine_credentials()

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

        search_results = programmable_search(service, CSE_ID, query)

        # Respect Google's rate limits
        time.sleep(SEARCH_DELAY_SECONDS)

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