# src/lib/fetch.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

def fetch_history(ticker: str,
                  save_path: str,
                  start: str | None = None,
                  end: str | None = None,
                  interval: str = "1d",
                  auto_adjust: bool = True) -> str:
    """
    用 yfinance 抓歷史K線並存成 CSV。回傳實際寫入的檔案路徑。
    - ticker: yfinance 代碼（例如 5443.TWO、NVDA）
    - save_path: 要存的 CSV 路徑
    - start/end: 'YYYY-MM-DD'，未提供則抓近兩年
    """
    if not start:
        start = (datetime.today() - timedelta(days=365*2)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.today().strftime("%Y-%m-%d")

    df = yf.download(ticker, start=start, end=end, interval=interval,
                     auto_adjust=auto_adjust, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data returned by yfinance for ticker: {ticker}")

    df = df.reset_index()  # Date 在 index，要攤平成欄位
    out = Path(save_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return str(out)
