import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_API_KEY, SHEET_ID

def get_sheet_data(sheet_id=None, range_name='A:Z'):
    """
    Fetch data from a Google Sheet.
    If sheet_id is not provided, uses the one from config.
    Returns a list of lists (rows).
    """
    if sheet_id is None:
        sheet_id = SHEET_ID

    # Use API key for public sheets (if the sheet is public and you have the key)
    # For private sheets, you would need service account credentials.
    # Since we are using an API key, we assume the sheet is public or we are using a key that can access it.
    # However, note: gspread typically uses service account. For API key, we might need to use a different approach.
    # Let's use the Google Sheets API directly with the API key for reading public sheets.
    # But for simplicity and to follow the plan, we'll use gspread with service account if available, else fallback.

    # Since we only have an API key, we cannot use gspread's standard method which requires service account.
    # We'll use the Google Sheets API via REST with the API key.

    import requests

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_name}"
    params = {
        "key": GOOGLE_API_KEY
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get('values', [])