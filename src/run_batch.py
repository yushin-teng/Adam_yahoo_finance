# -*- coding: utf-8 -*-
import os, sys
from pathlib import Path
from dotenv import load_dotenv

def main():
    load_dotenv()
    script = Path(__file__).resolve().parent / "batch_upload_from_sheet.py"

    # 這些值會從 .env 讀，或可在這裡覆蓋
    cmd = [
        sys.executable, str(script),
        "--auto_fetch", "1",           # 啟用自動抓價
        "--fetch_period", "1y",        # 抓多久
        "--refresh_days", "3",         # CSV 超過幾天就重抓
        "--fetch_interval", "1d",      # 抓日線
    ]
    print("Running:", " ".join(cmd))
    os.system(" ".join(cmd))

if __name__ == "__main__":
    main()
