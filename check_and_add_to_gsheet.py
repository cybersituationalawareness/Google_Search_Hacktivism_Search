import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from send_telegram_alert import send_telegram_alert


def append_to_gsheet(df_new):
    print("append to gsheet")
    """
    Appends new rows from a DataFrame to a Google Sheet.
    Checks if the row already exists based on 'title' and 'date' to prevent duplicates.
    """
    # --- CONFIGURATION ---
    # Replace with your actual Google Sheet ID
    SPREADSHEET_ID = "1-WR_4-bWDShxHiA_bM22ApeQZmhe13AOICeIG39C4kU"

    if df_new.empty:
        print("Provided DataFrame is empty. Nothing to add to Google Sheets.")
        return

    # gspread cannot handle NaN/NaT values. Replace them with empty strings.
    df_new = df_new.fillna("")

    # 1. Authenticate with Google
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
    except Exception as e:
        print(f"Authentication Error: {e}")
        print("Please ensure 'credentials.json' is in the 'GTI Hacktivism' folder.")
        return

    # 2. Open the Sheet
    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1  # Targets the first tab
    except Exception as e:
        print(f"Error accessing the Google Sheet: {e}")
        print("Verify SPREADSHEET_ID and ensure the Service Account email has 'Editor' access.")
        return

    # 3. Fetch existing data for deduplication
    try:
        existing_records = worksheet.get_all_records()
        df_existing = pd.DataFrame(existing_records)
        is_sheet_empty = df_existing.empty
    except Exception:
        # Sheet is likely completely blank with no headers
        df_existing = pd.DataFrame()
        is_sheet_empty = True

    # 4. If sheet is empty, write headers and data
    if is_sheet_empty:
        print("Sheet appears to be empty. Initializing with new data...")
        header = df_new.columns.values.tolist()
        data = df_new.values.tolist()
        
        try:
            worksheet.clear()
            worksheet.append_rows([header] + data)
            print(f"Successfully initialized sheet with {len(df_new)} rows.")
            return
        except Exception as e:
            print(f"Failed to initialize Google Sheet: {e}")
            return

    # 5. Deduplication Logic
    # We will use 'title' + 'date' as a unique composite key to prevent appending the same report rows twice.
    # If your Google sheet doesn't have these columns, we skip deduplication and just append.
    if 'date prefix' in df_existing.columns and 'snippet' in df_existing.columns:
        # Create composite keys for comparison
        df_existing['composite_key'] = df_existing['title'].astype(str)
        df_new['composite_key'] = df_new['title'].astype(str)

        existing_keys = set(df_existing['composite_key'].tolist())
        df_to_append = df_new[~df_new['composite_key'].isin(existing_keys)].copy()
        
        # Clean up temporary column
        df_to_append = df_to_append.drop(columns=['composite_key'])
    else:
        # If columns don't match, just append everything (unsafe but necessary if headers are wrong)
        print("Warning: 'title' or 'date' columns not found in existing sheet. Appending all without deduplication.")
        df_to_append = df_new.copy()

    # 6. Append to Cloud
    if df_to_append.empty:
        print("No new unique results to append to Google Sheets. Everything is up to date.")
    else:
        try:
            new_rows = df_to_append.values.tolist()
            worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
            print(f"Successfully appended {len(df_to_append)} new rows to the Google Sheet.")

            send_telegram_alert(df_to_append)

        except Exception as e:
            print(f"Error during cloud append: {e}")
