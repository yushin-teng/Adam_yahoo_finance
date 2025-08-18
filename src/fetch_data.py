# src/fetch_data.py
import yfinance as yf
import pandas as pd
from pathlib import Path
from typing import List, Optional

# 台股常見尾碼：上市 .TW、上櫃 .TWO
CANDIDATE_SUFFIXES: List[str] = [".TWO", ".TW", ""]  # 依序嘗試

def try_download(base_code: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    for suf in CANDIDATE_SUFFIXES:
        ticker = f"{base_code}{suf}"
        print(f"Trying: {ticker} ...")
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if not df.empty:
            df = df.rename_axis("Date").reset_index()
            df["Ticker"] = ticker
            print(f"✅ Success with {ticker}, rows={len(df)}")
            return df
        else:
            print(f"⚠️  No data for {ticker}")
    raise RuntimeError(f"No data found for {base_code} with suffixes {CANDIDATE_SUFFIXES}")

def main():
    base_code = "5443"               # 你要抓的股票本體代碼
    period = "1y"                    # 抓一年
    interval = "1d"                  # 日線

    df = try_download(base_code, period=period, interval=interval)

    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{base_code}.csv"   # 檔名用不帶尾碼的 5443.csv
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Done. Saved to {out_path.resolve()}")

if __name__ == "__main__":
    main()
