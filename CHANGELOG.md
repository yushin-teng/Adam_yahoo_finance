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

