#!/usr/bin/env python3
"""
Google Sheets to Telegram summary bot.
"""
import argparse
import sys
from config import GOOGLE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SHEET_ID
from reader import get_sheet_data
from summarizer import summarize_sheet_data
from sender import send_telegram_message

def main():
    parser = argparse.ArgumentParser(description='Fetch data from Google Sheets and send a summary to Telegram.')
    parser.add_argument('--sheet-id', type=str, help='Google Sheet ID (overrides config)')
    parser.add_argument('--dry-run', action='store_true', help='Only print the summary, do not send to Telegram')
    args = parser.parse_args()

    sheet_id = args.sheet_id if args.sheet_id else SHEET_ID

    try:
        # Fetch data from the sheet
        values = get_sheet_data(sheet_id=sheet_id)
        # Summarize the data
        summary = summarize_sheet_data(values)
        print(summary)

        if not args.dry_run:
            # Send to Telegram
            result = send_telegram_message(summary)
            print("Message sent to Telegram:", result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()