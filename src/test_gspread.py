import gspread
from google.oauth2.service_account import Credentials
import sys

SA = r"C:\Users\pc0329a\Desktop\TW_FINANCE_TRACKER\myfinancetracker-468304-97c706163fd4.json"
SID_OR_URL = "1aacDrxURirAqtVhOWyI6p234Q2tK2YEz5hhpqBD95lE"

scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(SA, scopes=scopes)
gc = gspread.authorize(creds)

try:
    if SID_OR_URL.startswith("http"):
        sh = gc.open_by_url(SID_OR_URL)
    else:
        sh = gc.open_by_key(SID_OR_URL)
    print("OK. Spreadsheet title =", sh.title)
    print("Worksheets =", [ws.title for ws in sh.worksheets()])
except Exception as e:
    print("FAILED:", repr(e))
    sys.exit(1)
