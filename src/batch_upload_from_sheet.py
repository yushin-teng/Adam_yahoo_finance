# -*- coding: utf-8 -*-
import argparse, os, sys, time, csv
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# ---- 新增：用 yfinance 抓價 ----
import yfinance as yf

REQ_COLS = ["ticker","name","sheet_name","csv","pivot_date","lookback","horizon","pivot_side","spreadsheet","market"]

def load_env():
    load_dotenv()
    return {
        "SA_JSON": os.getenv("SA_JSON"),
        "TARGET_SPREADSHEET": os.getenv("WATCHLIST_SPREADSHEET") or os.getenv("TARGET_SPREADSHEET"),
        "WATCH_SHEET": os.getenv("WATCHLIST_SHEET","watchlist"),
        "DATA_DIR": os.getenv("DATA_DIR","data"),
        "AUTO_FETCH": os.getenv("AUTO_FETCH","1") == "1",
        "FETCH_PERIOD": os.getenv("FETCH_PERIOD","1y"),
        "REFRESH_DAYS": int(os.getenv("REFRESH_DAYS","3")),
        "FETCH_INTERVAL": os.getenv("FETCH_INTERVAL","1d"),
    }

def gspread_client(sa_json):
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(sa_json, scopes=scopes)
    return gspread.authorize(creds)

def open_ws(gc, spreadsheet, sheet_name):
    sh = gc.open_by_key(spreadsheet) if "https://" not in spreadsheet else gc.open_by_url(spreadsheet)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=2000, cols=26)
        ws.update("A1", [REQ_COLS])
    return sh, ws

def df_from_ws(ws):
    vals = ws.get_all_values()
    if not vals: return pd.DataFrame(columns=REQ_COLS)
    df = pd.DataFrame(vals[1:], columns=vals[0])
    for c in REQ_COLS:
        if c not in df.columns: df[c] = ""
    return df[REQ_COLS]

def ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def need_refresh(csv_path: Path, refresh_days: int) -> bool:
    if not csv_path.exists(): return True
    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
    return (datetime.now() - mtime).days >= refresh_days

def fetch_to_csv(ticker: str, market: str, out_csv: Path, period: str, interval: str):
    symbol = f"{ticker}{market or ''}"
    print(f"  csv 未提供或需更新 -> 下載 '{symbol}' 到 {out_csv}")
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance 無資料: {symbol}")
    out = df.reset_index()[["Date","Open","High","Low","Close","Volume"]]
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    ensure_parent(out_csv)
    out.to_csv(out_csv, index=False)
    print("  OK.")

def run_row(row: dict, args, env):
    """回傳 (sheet_name, csv_path, msg)"""
    ticker = row["ticker"].strip()
    name = row.get("name","").strip()
    sheet_name = (row.get("sheet_name") or ticker).strip()
    pivot_date = row.get("pivot_date","").strip()
    lookback = (row.get("lookback") or "10").strip()
    horizon = (row.get("horizon") or "30").strip()
    pivot_side = (row.get("pivot_side") or "low").strip().lower()
    market = row.get("market","").strip()

    # csv path
    csv_cell = (row.get("csv") or "").strip()
    csv_path = Path(csv_cell) if csv_cell else Path(env["DATA_DIR"]) / f"{ticker}.csv"

    # 自動抓價
    if env["AUTO_FETCH"]:
        if need_refresh(csv_path, env["REFRESH_DAYS"]):
            fetch_to_csv(ticker, market, csv_path, env["FETCH_PERIOD"], env["FETCH_INTERVAL"])

    # 呼叫 upload_to_sheets.py 寫入 + 畫圖
    up = Path(__file__).resolve().parent / "upload_to_sheets.py"
    cmd = [
        sys.executable, str(up),
        "--sa", args.sa,
        "--spreadsheet", args.spreadsheet,
        "--csv", str(csv_path),
        "--sheet_name", sheet_name,
        "--pivot_date", pivot_date,
        "--lookback", lookback,
        "--horizon", horizon,
        "--pivot_side", pivot_side,
    ]
    os.system(" ".join(cmd))
    return sheet_name, str(csv_path)

def main():
    p = argparse.ArgumentParser()
    env = load_env()
    p.add_argument("--sa", default=env["SA_JSON"])
    p.add_argument("--spreadsheet", default=env["TARGET_SPREADSHEET"])
    p.add_argument("--watch_sheet", default=env["WATCH_SHEET"])
    p.add_argument("--data_dir", default=env["DATA_DIR"])
    p.add_argument("--auto_fetch", type=int, default=1 if env["AUTO_FETCH"] else 0)
    p.add_argument("--fetch_period", default=env["FETCH_PERIOD"])
    p.add_argument("--refresh_days", type=int, default=env["REFRESH_DAYS"])
    p.add_argument("--fetch_interval", default=env["FETCH_INTERVAL"])
    args = p.parse_args()

    if not args.sa or not Path(args.sa).exists():
        raise FileNotFoundError(f"Service account JSON 不存在: {args.sa}")
    if not args.spreadsheet:
        raise ValueError("缺少目標試算表 --spreadsheet 或 .env 設定")

    # 覆蓋 env 參數（讓 run_batch 可動態指定）
    env["AUTO_FETCH"] = args.auto_fetch == 1
    env["FETCH_PERIOD"] = args.fetch_period
    env["REFRESH_DAYS"] = args.refresh_days
    env["FETCH_INTERVAL"] = args.fetch_interval
    env["DATA_DIR"] = args.data_dir

    gc = gspread_client(args.sa)
    _, ws = open_ws(gc, args.spreadsheet, args.watch_sheet)
    df = df_from_ws(ws)

    rows = len(df)
    print(f"[Batch] start: {datetime.now():%Y-%m-%d %H:%M:%S.%f} | rows = {rows}")

    for i, row in df.iterrows():
        if not str(row["ticker"]).strip():
            continue
        ticker = row["ticker"].strip()
        sheet_name, csv_path = run_row(row.to_dict(), args, env)
        print(f" -> [{i+1}/{rows}] {ticker:>6}  (sheet={sheet_name}, csv={csv_path})")
        print(" OK.")

    log_dir = Path("outputs"); log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"run_log_sheet_{datetime.now():%Y%m%d_%H%M%S}.csv"
    df.to_csv(log_file, index=False, encoding="utf-8-sig")
    print(f"\n[Batch] done. Summary: {log_file}")

if __name__ == "__main__":
    main()
