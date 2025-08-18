# src/upload_to_sheets.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from datetime import datetime
from typing import Literal, Optional

import numpy as np
import pandas as pd

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

PivotSide = Literal["low", "high"]


# ------------------------- Adam Theory ------------------------- #
def adam_projection(
    hist_df: pd.DataFrame,
    pivot_date: Optional[pd.Timestamp],
    lookback_days: int = 10,
    horizon_days: int = 30,
    side: PivotSide = "low",
) -> pd.DataFrame:
    """
    亞當理論：以 pivot 為對稱軸，將 pivot 前的一段路徑鏡射到未來。
    horizon_days：投影的未來「工作日」長度。
    """
    df = hist_df.copy()

    # 日期欄位正規化
    if "Date" not in df.columns:
        cand = [c for c in df.columns if str(c).lower().startswith("date")]
        if not cand:
            raise ValueError("CSV must contain a Date/Datetime column")
        df.rename(columns={cand[0]: "Date"}, inplace=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    # 必要欄位
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if "Adj Close" in df.columns and "Close" not in df.columns:
        df.rename(columns={"Adj Close": "Close"}, inplace=True)
    if "Close" not in df.columns:
        raise ValueError("CSV must contain Close column")
    for c in needed:
        if c not in df.columns:
            df[c] = 0 if c == "Volume" else df["Close"]

    # 數值轉型與補值（避免 NaN）
    for c in needed:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Close"] = df["Close"].interpolate().bfill().ffill()
    for c in ["Open", "High", "Low"]:
        df[c] = df[c].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0)

    prices = df["Close"].astype(float)
    dates = df["Date"]

    # 選 pivot
    if pivot_date is not None:
        pivot_dt = pd.to_datetime(pivot_date)
        if (dates == pivot_dt).any():
            pivot_idx = int(np.flatnonzero(dates == pivot_dt)[0])
        else:
            pivot_idx = (dates - pivot_dt).abs().idxmin()
            pivot_dt = dates.iloc[pivot_idx]
    else:
        window = df.iloc[-max(20, lookback_days * 2) :]
        pivot_idx = window["Close"].idxmin() if side == "low" else window["Close"].idxmax()
        pivot_dt = dates.loc[pivot_idx]

    pivot_price = float(prices.iloc[pivot_idx])

    # 取 pivot 前最後 horizon_days 的路徑（不足則盡量取）
    need = horizon_days
    start_idx = max(0, pivot_idx - need)
    past = prices.iloc[start_idx : pivot_idx + 1]  # 含 pivot
    past_wo_pivot = past.iloc[:-1] if len(past) > 1 else past
    if len(past_wo_pivot) < need:
        need = len(past_wo_pivot)
    last_segment = past_wo_pivot.iloc[-need:]

    # 鏡射
    mirrored = pivot_price + (pivot_price - last_segment.iloc[::-1].astype(float).values)

    # 產生未來工作日序列
    future_dates = pd.bdate_range(start=pivot_dt, periods=horizon_days + 1)[1:]
    if len(mirrored) < horizon_days:
        tail = np.full(horizon_days - len(mirrored), mirrored[-1])
        mirrored = np.concatenate([mirrored, tail])
    proj = pd.DataFrame({"Date": future_dates[:horizon_days], "Projected": mirrored[:horizon_days]})
    return proj


# --------------------- Google Sheets helpers ------------------- #
def get_gspread_client(sa_json_path: str):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(sa_json_path, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc, creds


def delete_all_charts_in_sheet(creds, spreadsheet_id: str, sheet_title: str):
    """
    嘗試刪除此分頁上的所有圖表。
    不同帳戶/版本回傳格式可能不同；若抓不到 chartId 會靜默略過。
    """
    service = build("sheets", "v4", credentials=creds)
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_id = None
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == sheet_title:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        return

    chart_ids = []
    for s in meta.get("sheets", []):
        if s["properties"]["sheetId"] != sheet_id:
            continue
        for ch in s.get("charts", []):
            if "chartId" in ch:
                chart_ids.append(ch["chartId"])
        for obj in s.get("objects", []):
            if "objectId" in obj:
                chart_ids.append(obj["objectId"])
        for obj in s.get("embeddedObjects", []):
            if "objectId" in obj:
                chart_ids.append(obj["objectId"])

    if not chart_ids:
        return

    requests = [{"deleteEmbeddedObject": {"objectId": cid}} for cid in chart_ids]
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()


def recreate_worksheet(sh, creds, spreadsheet_id: str, title: str):
    """
    - 若存在且文件中**不只一個分頁**：刪除後重建（乾淨不留舊圖）
    - 若存在且**是唯一分頁**：不刪；清空內容並嘗試刪除舊圖
    - 若不存在：新建
    """
    try:
        ws = sh.worksheet(title)
        sheets = sh.worksheets()
        if len(sheets) > 1:
            sh.del_worksheet(ws)
            return sh.add_worksheet(title=title, rows=2000, cols=26)
        else:
            ws.clear()
            try:
                delete_all_charts_in_sheet(creds, spreadsheet_id, title)
            except Exception:
                pass
            return ws
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=26)


# ---------------------- Safe matrix for Sheets ----------------- #
def to_sheets_matrix(df: pd.DataFrame):
    """
    將 DataFrame 轉成可安全上傳 Google Sheets 的 matrix：
    - datetime 轉 'YYYY-MM-DD'，無效日期 -> None
    - 非有限數值 (NaN/Inf/-Inf) -> None
    - 其它缺值 -> None
    """
    out = df.copy()

    # 日期欄位 -> 字串；無效日期 -> None
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            d = pd.to_datetime(out[col], errors="coerce")
            out[col] = d.dt.strftime("%Y-%m-%d")
            out.loc[d.isna(), col] = None

    # 數值欄位：非有限數值 -> None
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            vals = pd.to_numeric(out[col], errors="coerce").astype(float)
            vals[~np.isfinite(vals)] = np.nan
            out[col] = vals

    # 其餘缺值 -> None
    out = out.astype(object).where(pd.notna(out), None)

    return [out.columns.tolist()] + out.values.tolist()


# --------------------- Write tables + combined ----------------- #
def write_tables(ws, hist_df: pd.DataFrame, proj_df: pd.DataFrame) -> int:
    """
    A:E = Historical, H:I = Projection, K:M = Combined timeline for chart
    回傳合併時間軸的列數（含表頭），供畫圖使用。
    """
    # Historical (A:E)
    hist = hist_df.copy()
    hist = hist[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    hist.insert(0, "No.", range(1, len(hist) + 1))
    hist["Date"] = pd.to_datetime(hist["Date"], errors="coerce")
    ws.update(range_name="A1", values=to_sheets_matrix(hist))

    # Projection (H:I)
    proj = proj_df.copy()
    proj.insert(0, "No.", range(1, len(proj) + 1))
    proj["Date"] = pd.to_datetime(proj["Date"], errors="coerce")
    ws.update(range_name="H1", values=to_sheets_matrix(proj))

    # Combined timeline (K:M)
    hist_d = pd.DataFrame({
        "Date": pd.to_datetime(hist_df["Date"], errors="coerce"),
        "Hist_Close": pd.to_numeric(hist_df["Close"], errors="coerce")
    }).dropna(subset=["Date"]).sort_values("Date")

    proj_d = pd.DataFrame({
        "Date": pd.to_datetime(proj_df["Date"], errors="coerce"),
        "Projected": pd.to_numeric(proj_df["Projected"], errors="coerce")
    }).dropna(subset=["Date"]).sort_values("Date")

    combined = pd.merge(hist_d, proj_d, on="Date", how="outer").sort_values("Date").reset_index(drop=True)
    combined = combined.rename(columns={"Date": "All_Date"})  # 統一欄名
    ws.update(range_name="K1", values=to_sheets_matrix(combined[["All_Date", "Hist_Close", "Projected"]]))

    # 回傳資料列數 + 表頭
    return len(combined) + 1


# ---------------------- Add chart with combined ---------------- #
def add_chart_with_api(creds, spreadsheet_id: str, sheet_title: str,
                       combined_rows: int, run_ts: str):
    service = build("sheets", "v4", credentials=creds)
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_id = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == sheet_title:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        raise RuntimeError(f"Sheet '{sheet_title}' not found")

    # K=10, L=11, M=12（0-based）
    requests = [{
        "addChart": {
            "chart": {
                "spec": {
                    "title": f"{sheet_title} — Adam Theory — {run_ts}",
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Date"},
                            {"position": "LEFT_AXIS", "title": "Price"},
                        ],
                        "domains": [{
                            "domain": {
                                "sourceRange": {"sources": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1, "endRowIndex": combined_rows,  # K2:K...
                                    "startColumnIndex": 10, "endColumnIndex": 11        # K
                                }]}
                            }
                        }],
                        "series": [
                            {   # L = Hist_Close
                                "series": {"sourceRange": {"sources": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1, "endRowIndex": combined_rows,
                                    "startColumnIndex": 11, "endColumnIndex": 12       # L
                                }]}},
                                "targetAxis": "LEFT_AXIS", "type": "LINE",
                            },
                            {   # M = Projected
                                "series": {"sourceRange": {"sources": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1, "endRowIndex": combined_rows,
                                    "startColumnIndex": 12, "endColumnIndex": 13       # M
                                }]}},
                                "targetAxis": "LEFT_AXIS", "type": "LINE",
                            },
                        ],
                        "headerCount": 0,
                    }
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 13}  # N1
                    }
                },
            }
        }
    }]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


# ------------------------------ main --------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Upload CSV to Google Sheet & draw Adam Theory chart.")
    ap.add_argument("--sa", required=True, help="Path to service account JSON")
    ap.add_argument("--spreadsheet", required=True, help="Spreadsheet ID or full URL")
    ap.add_argument("--csv", required=True, help="Path to CSV (must include Date/Close; other cols optional)")
    ap.add_argument("--sheet_name", required=True, help="Worksheet name (e.g., 5443)")
    ap.add_argument("--pivot_date", default=None, help="YYYY-MM-DD, optional")
    ap.add_argument("--lookback", type=int, default=10, help="how many days to look back when choosing pivot")
    ap.add_argument("--horizon", type=int, default=30, help="future business days to project")
    ap.add_argument("--pivot_side", choices=["low", "high"], default="low")
    args = ap.parse_args()

    # 讀 CSV（先以字串讀，之後自己轉數值），砍掉整列空白
    df = pd.read_csv(args.csv, dtype=str)
    df = df.dropna(how="all")

    # 欄位名正規化
    date_col = next((c for c in df.columns if str(c).lower().startswith("date")), None)
    if not date_col:
        raise ValueError("CSV must contain a Date column")
    df.rename(columns={date_col: "Date"}, inplace=True)
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df.rename(columns={"Adj Close": "Close"}, inplace=True)

    # 補齊必要欄位
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = 0 if c == "Volume" else df.get("Close", 0)

    # 數值化與補值
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Close"] = df["Close"].interpolate().bfill().ffill()
    for c in ["Open", "High", "Low"]:
        df[c] = df[c].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0)

    # 計算投影
    proj = adam_projection(
        hist_df=df[["Date", "Open", "High", "Low", "Close", "Volume"]],
        pivot_date=pd.to_datetime(args.pivot_date) if args.pivot_date else None,
        lookback_days=args.lookback,
        horizon_days=args.horizon,
        side=args.pivot_side,
    )

    # 連線試算表
    gc, creds = get_gspread_client(args.sa)
    if args.spreadsheet.strip().lower().startswith("http"):
        sh = gc.open_by_url(args.spreadsheet.strip())
        spreadsheet_id = args.spreadsheet.split("/d/")[1].split("/")[0]
    else:
        sh = gc.open_by_key(args.spreadsheet.strip())
        spreadsheet_id = args.spreadsheet.strip()

    # 分頁：多分頁時刪舊再建；只剩一張時清空＋刪舊圖
    ws = recreate_worksheet(sh, creds, spreadsheet_id, args.sheet_name)

    # 寫入資料（含合併時間軸）
    combined_rows = write_tables(ws, df, proj)

    # 新增圖表（標題含執行時間）
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    add_chart_with_api(creds, spreadsheet_id, args.sheet_name, combined_rows, run_ts)

    print(f"Done. Worksheet '{args.sheet_name}' updated and chart added.")


if __name__ == "__main__":
    main()
