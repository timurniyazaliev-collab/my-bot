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


def get_or_create_worksheet(spreadsheet, title: str, headers: list[str]) -> tuple:
    try:
        ws = spreadsheet.worksheet(title)
        existing_headers = ws.row_values(1)
        if not existing_headers:
            ws.append_row(headers)
            existing_headers = headers
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=100, cols=max(len(headers), 1))
        ws.append_row(headers)
        existing_headers = headers
    return ws, existing_headers


def existing_ids(ws) -> set:
    values = ws.col_values(1)
    return set(values[1:]) if values else set()


def append_rows(ws, rows: list[list[str]]):
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")


def overwrite_all(ws, headers: list[str], rows: list[list[str]]):
    ws.clear()
    ws.append_row(headers)
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
