import configparser
import telebot
import os

from docutils.nodes import organization


def prepare_and_send_alert(df, chat_id, bot):
    """
    Iterates through the DataFrame and sends a formatted Telegram message for each row.
    """
    for index, row in df.iterrows():
        # Use .get() to prevent KeyErrors if a column is somehow missing
        query = row.get("query", "N/A")
        date = row.get("date", "N/A")
        title = row.get("title", "N/A")
        threat_actor = row.get("threat_actor", "N/A")
        country = row.get("country", "N/A")
        region = row.get("region", "N/A")
        organizations = row.get("organizations", "N/A")
        #snippet = row.get("snippet", "N/A")
        url = row.get("url", "N/A")

        # Using f-strings and basic HTML formatting for Telegram
        notification_message = (
            #f"🔍 <b>Google Search Alert</b>\n"
            #f"<b>Query:</b> {query}\n"
            f"<b>Date:</b> {date}\n\n"
            f"<b>{title}</b>\n"
            f"<b>{threat_actor}</b>\n"
            f"<b>{country}</b>\n"
            f"<b>{region}</b>\n"
            f"<b>{organizations}</b>\n"
            #f"{snippet}\n\n"
            f"<a href='{url}'>Read More</a>\n"
            f"{'-' * 20}"
        )

        try:
            # parse_mode="HTML" allows us to use bold tags and clickable links
            bot.send_message(chat_id, notification_message, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            print(f"Failed to send Telegram message for '{title}': {e}")

def send_telegram_alert(df, config_file="tel_config.ini"):
    """
    Reads credentials and triggers the Telegram alert sending process.
    """
    config = configparser.ConfigParser()

    if not os.path.exists(config_file):
        print(f"ERROR: Configuration file '{config_file}' not found.")
        print("Please create a 'tel_config.ini' file as described in the comments.")
        return

    try:
        config.read(config_file)
        if 'tel_api' in config:
            TOKEN = config['tel_api']['telbot_token']
            chat_id = config['tel_api']['telegram_chat_id']
        else:
            print(f"ERROR: Section '[tel_api]' not found in '{config_file}'.")
            return

    except KeyError as e:
        print(f"ERROR: Missing key in '{config_file}' under [tel_api]: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading '{config_file}': {e}")
        return

    try:
        bot = telebot.TeleBot(TOKEN)
        prepare_and_send_alert(df, chat_id, bot)
    except Exception as e:
        print(f"Failed to initialize Telegram bot: {e}")

def send_telegram_error(error_message, config_file="tel_config.ini"):
    """
    Sends an error message to Telegram if the script crashes.
    """
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        return

    try:
        config.read(config_file)
        TOKEN = config['tel_api']['telbot_token']
        chat_id = config['tel_api']['telegram_chat_id']
    except Exception:
        return

    try:
        bot = telebot.TeleBot(TOKEN)
        msg = f"🚨 <b>Google Search Script Error</b> 🚨\n\n<pre>{error_message}</pre>"
        bot.send_message(chat_id, msg, parse_mode="HTML")
    except Exception as e:
        print(f"Failed to send error alert to Telegram: {e}")