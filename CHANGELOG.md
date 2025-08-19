# Changelog
All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-08-19
### Added
- **Adam Theory projection**: mirror-based future path with configurable horizon (`--horizon`, default 30 business days).
- **CSV → Google Sheets pipeline** using Service Account:
  - Supports **Spreadsheet ID or full URL**.
  - Creates/cleans worksheet safely:
    - If multiple sheets exist: delete & recreate the target sheet.
    - If it’s the only sheet: clear contents + try to delete existing charts.
- **Robust data sanitization**:
  - Drop fully-empty rows.
  - Coerce numeric columns, fill NaN/Inf/NaT before upload (JSON-safe).
- **Unified timeline for chart**:
  - Writes combined axis in **K:M** (`All_Date`, `Hist_Close`, `Projected`) so X-axis includes **future dates**.
- **Chart rendering via Sheets API**:
  - Two series (historical close, projected) using the combined timeline.
  - Chart title includes run timestamp for traceability.
- **CLI options**:
  - `--sa`, `--spreadsheet`, `--csv`, `--sheet_name`, `--pivot_date`, `--lookback`, `--horizon`, `--pivot_side`.

### Changed
- Use named parameters in `worksheet.update()` to avoid deprecation warnings.

### Notes
- First usable MVP release. No breaking changes expected.

## [0.2.0] - 2025-08-19
### Added
- fetch module (lib/fetch.py) + auto-fetch in batch when CSV missing (ticker+market).
- .env-driven runner (src/run_batch.py) for one-command batch runs.
- watchlist supports `market` column (.TWO/.TW/.US).


# Changelog

## [0.3.0] - 2025-08-19
### Added
- 新增 `watchlist` 支援，允許使用者直接在 Google Sheet 維護追蹤清單。
- `run_batch.py` 新增 `--auto_fetch` 功能，可自動補齊缺少的 CSV 檔案。
- 自動下載台股歷史資料（例：2609.TW, 2327.TW），並輸出至 `/data` 資料夾。
- 完成 watchlist → CSV → 圖表 的自動化串接流程。

### Changed
- 優化日誌輸出格式，讓每個 ticker 的執行結果更清楚。
- 預設 `fetch_data.py` 支援 `--period 1y` 參數，減少重複輸入。

### Fixed
- 修正原本缺少 CSV 時會出錯的問題，現在會自動抓取缺漏資料。

---

## [0.1.0] - 2025-08-10
### Added
- 初始版本，可手動執行 `fetch_data.py` 抓取個股歷史資料。
- 支援手動輸入 ticker、market，生成 CSV。
- 基本 Adam Theory 反射圖功能（需手動輸入 pivot date）。
