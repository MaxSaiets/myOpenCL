# Google Sheets to Telegram Summary Bot

This bot fetches data from a Google Sheet, summarizes it, and sends the summary to a Telegram chat.

## Features

- Fetches data from a public Google Sheet using an API key.
- Summarizes the sheet data (row count, column count, header, and sample rows).
- Sends the summary to a Telegram chat via a bot.
- Configurable via environment variables.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/MaxSaiets/sheets-to-telegram.git
   cd sheets-to-telegram
   ```

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file based on `.env.example` and fill in the required values:
   - `GOOGLE_API_KEY`: Your Google API key (for accessing public sheets).
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
   - `TELEGRAM_CHAT_ID`: The chat ID where the bot will send messages.
   - `SHEET_ID`: The ID of the Google Sheet to fetch data from.

## Usage

Run the bot with:

```bash
python3 main.py
```

You can override the sheet ID from the config with `--sheet-id`:

```bash
python3 main.py --sheet-id YOUR_SHEET_ID
```

To test without sending to Telegram, use the `--dry-run` flag:

```bash
python3 main.py --dry-run
```

## Example

Assuming you have a public Google Sheet with ID `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms` (the default test sheet), you can run:

```bash
python3 main.py
```

## Notes

- The bot currently only reads public sheets using an API key. For private sheets, you would need to use service account credentials and adjust the reader accordingly.
- The summary is basic and can be extended in `summarizer.py`.

## License

MIT