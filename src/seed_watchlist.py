# src/watchlist.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Any, Dict

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

COLUMNS = [
    "ticker",
    "name",
    "sheet_name",
    "csv",
    "pivot_date",
    "lookback",
    "horizon",
    "pivot_side",
    "spreadsheet",
    "market",
]

def load_env_defaults():
    load_dotenv()
    sa = os.getenv("SA_JSON")
    target = os.getenv("WATCHLIST_SPREADSHEET") or os.getenv("TARGET_SPREADSHEET")
    sheet = os.getenv("WATCHLIST_SHEET", "watchlist")
    data_dir = os.getenv("DATA_DIR", "data")
    return sa, target, sheet, data_dir

def get_gspread_client(sa_json_path: str):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(sa_json_path, scopes=scopes)
    return gspread.authorize(creds)

def open_sheet(gc, spreadsheet: str, sheet_name: str):
    if spreadsheet.strip().lower().startswith("http"):
        sh = gc.open_by_url(spreadsheet.strip())
    else:
        sh = gc.open_by_key(spreadsheet.strip())
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=2000, cols=26)
        ws.update(range_name="A1", values=[COLUMNS])  # 命名參數，避免警告
    return sh, ws

def to_sheets_matrix(df: pd.DataFrame) -> List[List[Any]]:
    out = df.astype(object).where(pd.notna(df), "")
    return [list(out.columns)] + out.values.tolist()

def read_df(ws) -> pd.DataFrame:
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=COLUMNS)
    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[COLUMNS]
    return df

def write_df(ws, df):
    ws.clear()
    ws.update(range_name="A1", values=to_sheets_matrix(df))  # 命名參數，避免警告

def cmd_list(sa: str, spreadsheet: str, sheet: str):
    gc = get_gspread_client(sa)
    _, ws = open_sheet(gc, spreadsheet, sheet)
    df = read_df(ws)
    if df.empty:
        print("(watchlist is empty)")
        return
    show = df.copy()
    show.index = range(1, len(show) + 1)
    print(show.to_string())

def normalize_row(args, data_dir: str) -> Dict[str, str]:
    ticker = (args.ticker or "").strip()
    if not ticker:
        raise ValueError("ticker 為必填")
    csv_path = (args.csv or "").strip()
    if not csv_path:
        csv_path = str(Path(data_dir) / f"{ticker}.csv")
    row = {
        "ticker": ticker,
        "name": (args.name or "").strip(),
        "sheet_name": (args.sheet_name or ticker).strip(),
        "csv": csv_path,
        "pivot_date": (args.pivot_date or "").strip(),
        "lookback": str(args.lookback if args.lookback is not None else 10),
        "horizon": str(args.horizon if args.horizon is not None else 30),
        "pivot_side": (args.pivot_side or "low").strip().lower(),
        "spreadsheet": (args.spreadsheet or "").strip(),
        "market": (args.market or "").strip(),
    }
    if row["pivot_side"] not in ("low", "high"):
        row["pivot_side"] = "low"
    return row

def cmd_add(sa: str, spreadsheet: str, sheet: str, data_dir: str, args):
    gc = get_gspread_client(sa)
    _, ws = open_sheet(gc, spreadsheet, sheet)
    df = read_df(ws)

    new_row = normalize_row(args, data_dir)
    exists = df["ticker"].astype(str).str.lower() == new_row["ticker"].lower()

    if exists.any():
        if args.update:
            df.loc[exists, :] = pd.DataFrame([new_row], columns=COLUMNS).values[0]
            print(f"已更新：ticker={new_row['ticker']}")
        else:
            raise ValueError(f"ticker 已存在：{new_row['ticker']}；若要覆蓋請加 --update")
    else:
        df = pd.concat([df, pd.DataFrame([new_row], columns=COLUMNS)], ignore_index=True)
        print(f"已新增：ticker={new_row['ticker']}")

    write_df(ws, df)

def cmd_remove(sa: str, spreadsheet: str, sheet: str, args):
    gc = get_gspread_client(sa)
    _, ws = open_sheet(gc, spreadsheet, sheet)
    df = read_df(ws)

    if df.empty:
        print("watchlist 目前是空的，沒有可刪除的資料。")
        return

    if args.row is None and not args.ticker:
        print("請提供 --ticker 或 --row")
        return

    if args.row is not None:
        idx = int(args.row)
        if not (1 <= idx <= len(df)):
            print(f"row 超出範圍 (1~{len(df)})，請先執行：python .\\src\\watchlist.py list")
            return
        removed = df.iloc[idx - 1].to_dict()
        df = df.drop(df.index[idx - 1]).reset_index(drop=True)
        print(f"已刪除 row={idx} (ticker={removed['ticker']})")
    else:
        ticker = args.ticker.strip().lower()
        exists = df["ticker"].astype(str).str.lower() == ticker
        if not exists.any():
            print(f"ticker 不存在：{args.ticker}")
            return
        df = df.loc[~exists].reset_index(drop=True)
        print(f"已刪除：ticker={args.ticker}")

    write_df(ws, df)

def main():
    sa_default, ss_default, sheet_default, data_dir_default = load_env_defaults()
    ap = argparse.ArgumentParser(description="維護 Google Sheet 的 watchlist（增改刪查）")
    ap.add_argument("--sa", default=sa_default, help="Service Account JSON 路徑（預設 .env 的 SA_JSON）")
    ap.add_argument("--spreadsheet", default=ss_default, help="watchlist 所在試算表（預設 .env）")
    ap.add_argument("--sheet", default=sheet_default, help="watchlist 工作表名稱（預設 .env 或 'watchlist'）")
    ap.add_argument("--data_dir", default=data_dir_default, help="自動生成 csv 路徑時使用（預設 .env 的 DATA_DIR 或 'data'）")

    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出 watchlist")
    p_list.set_defaults(func=lambda a: cmd_list(a.sa, a.spreadsheet, a.sheet))

    p_add = sub.add_parser("add", help="新增一列（若存在同 ticker，預設擋下；加 --update 則覆蓋）")
    p_add.add_argument("--ticker", required=True)
    p_add.add_argument("--name")
    p_add.add_argument("--sheet_name")
    p_add.add_argument("--csv")
    p_add.add_argument("--pivot_date")
    p_add.add_argument("--lookback", type=int)
    p_add.add_argument("--horizon", type=int)
    p_add.add_argument("--pivot_side", choices=["low", "high"])
    p_add.add_argument("--spreadsheet")
    p_add.add_argument("--market")
    p_add.add_argument("--update", action="store_true", help="若 ticker 已存在則覆蓋")
    p_add.set_defaults(func=lambda a: cmd_add(a.sa, a.spreadsheet, a.sheet, a.data_dir, a))

    p_rm = sub.add_parser("remove", help="刪除一列（--ticker 或 --row 二選一）")
    p_rm.add_argument("--ticker")
    p_rm.add_argument("--row", type=int)
    p_rm.set_defaults(func=lambda a: cmd_remove(a.sa, a.spreadsheet, a.sheet, a))

    args = ap.parse_args()

    if not args.sa or not Path(args.sa).exists():
        raise FileNotFoundError(f"Service account JSON not found: {args.sa}")
    if not args.spreadsheet:
        raise ValueError("缺少目標試算表（--spreadsheet 或 .env）")

    args.func(args)

if __name__ == "__main__":
    main()
