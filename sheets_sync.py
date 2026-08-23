import os
import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = os.path.dirname(__file__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_spreadsheet():
    creds_path = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(BASE_DIR, "google_service_account.json")
    )
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["GOOGLE_SHEET_ID"])


