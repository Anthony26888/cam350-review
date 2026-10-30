<div align="center">
  <img src="assets/icon.ico" width="128" alt="CAM350 Review Assistant logo">
  <h1>CAM350 Review Assistant</h1>
  <p>Review and correct PickPlace data for <b>CAM350</b> — verify every component, align origins against Gerber, and export fixed files without leaving your review flow.</p>
  <p>
    <img src="https://img.shields.io/badge/version-2.2.3-blue" alt="version">
    <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" alt="python">
    <img src="https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white" alt="windows">
    <img src="https://img.shields.io/badge/PySide6-Qt-green" alt="pyside6">
    <img src="https://img.shields.io/badge/pytest-542_passing-brightgreen" alt="tests">
  </p>
</div>

---

## Overview

A Windows desktop tool for reviewing PickPlace Excel files (`.xlsx`) against CAM350. Walk through every component, jump the CAD view to each coordinate, mark **OK** / **Edited**, batch-fix offsets, auto-align origins from Gerber files, track per-component edit history, and export corrected data.

- Built with **Python 3 + PySide6 (Qt)** and **openpyxl**
- Targets **Windows** (uses `win32gui` / `pyautogui` to drive CAM350)
- Current version: **2.2.8** (`utils/version.py`)
- Session format: **v8** (`.cam350review`, backward-compatible load)

---

## Screenshots

| Main window | Component history | Gerber View |
| --- | --- | --- |
| Table + detail panel + toolbar | `Time \| Step \| Changes` timeline per component | GKO/GTP/GBP overlay with PickPlace markers |
| `docs/screenshots/main.png` *(placeholder)* | `docs/screenshots/history.png` *(placeholder)* | `docs/screenshots/gerber.png` *(placeholder)* |

> Screenshots are optional. To add them later, save PNG files under `docs/screenshots/` and update the paths above. The app logo is `assets/icon.ico` (also used as the window icon in `main.py`).

---

## User Guide (print-ready, A4)

Full end-user manual covering installation, calibration, review workflow,
history, Gerber align, sessions, and export:

- `docs/USER_GUIDE.md` — source (English)
- `exports/USER_GUIDE_A4.pdf` — print-ready A4 PDF
- `exports/USER_GUIDE_A4.docx` — editable A4 Word file

Regenerate both exports after editing the source:

```bash
pip install python-docx reportlab
python tools/build_user_guide.py
```

---

## What's new in 2.2.x

- **Component History table** (`ui/review_panel.py`): the old `Actions` group was replaced by a `History` table with 3 columns — `Time (HH:MM:SS) | Step (Import/Align/Edit/OK/Batch/Delete/BOM) | Changes (X/Y/Rot/MPN old-&gt;new + remark)`. Newest entry first; unchanged fields are hidden.
- **Persistent history** (`models/history.py`, `database/history_repo.py`): append-only `component_history` SQLite table keyed by `(designator, block)`, indexed for fast per-component lookup. Survives undo/redo and panelize (new panel blocks start with empty history).
- **Session v8** (`services/session_service.py`): `history[]` and `bom_rows[]` are saved/loaded with `.cam350review` alongside records, Gerber paths, embedded Gerber files, prescreen state, and panel config.
- **Compare Revisions (ECO)** (`services/eco_diff.py`): diff the open session against a new PickPlace file (Added/Removed/Moved/MPN), apply in one undo step, export an ECO report.
- **Actions removed from the side panel**: `Previous/Next` are now `Up/Down`, `OK` is `Space`, `Edit` is `Ctrl+E`; `Jump CAM350` remains available from the table and the always-on-top `JumpPopup`.

---

## Features

### Core review workflow
- Open a PickPlace Excel file (`.xlsx`) — reads `Designator`, `MPN`, `Layer`, `X`, `Y`, `Rotation` columns (custom mapping supported).
- Review each component in the detail panel; select a row to see old/new values, status, remark, datasheet, and progress.
- **Jump CAM350** — moves the mouse to the calibrated X/Y text boxes in CAM350 and types the coordinate automatically.
- Mark a record as **OK** (`Space`) or **Edited** (`Ctrl+E`).
- Search for a component datasheet online (background thread, no UI freeze).

### Table
- Filterable, searchable table with per-row checkboxes.
- Filter by status, text, and X/Y coordinate ranges.
- Status column is color-coded:
  - **OK** — dark green
  - **Edited** — orange
  - **Aligned** — light blue
  - **Pending** — default
- Bulk actions: **OK Checked**, **Delete Checked**.

### Editing
- **Edit** individual records (X, Y, Rotation, remark).
- **Batch Edit** selected records:
  - Apply X / Y / Rotation offsets (`new = current + offset`).
  - Force **new X / new Y** to be negative.
  - Set a remark for all selected records.
  - Confirmation summary shown before applying, with a progress dialog.
- **Undo / Redo** (`Ctrl+Z` / `Ctrl+Shift+Z`) for edit, OK, batch edit, delete and align operations.

### Component history
- Every mutation logs one row: `Import`, `Align`, `Edit`, `Batch`, `OK`, `Delete` (+ Gerber rotation edits).
- Each row stores `old_x/y/rotation -&gt; new_x/y/rotation`, remark, and `created_at`.
- Select any component to see its timeline in `Time | Step | Changes` order (newest first).
- Empty components show `No history`. History is capped at 100 entries per component in the UI query.

### Alignment (Gerber origin align)
- Wizard that detects the board/panel outline from a **GKO** Gerber file.
- Optional **GTP** (top paste) / **GBP** (bottom paste) for more accurate offsets.
- Auto-aligns component coordinates to the panel/board origin, supports 90/180/270° rotation, and mil→mm conversion.
- Runs in a background thread with progress feedback.
- Pre-screen check flags `ROT / PAD / DUP / OUT` issues before aligning.
- Panelize support: multiply a single board into multi-block panels (with clear/restore).

### Gerber View
- Overlay PickPlace markers on GKO outline + GTP/GBP paste + GTO/GBO silkscreen.
- Search, filters, measure tool, rotation editor, display settings persisted per session.

### Export
- **Export Review Report** — full review report as `.xlsx` (old/new/aligned values, status, remark, review time).
- **Export PickPlace Fixed** — corrected PickPlace file, preserving original columns with MPN always present (inserted after Designator when missing) and skipping deleted records. MPN cells use Excel text formulas (`="..."`) so leading zeros are kept and Excel displays them left-aligned.
- Both exports run in background threads.

### BOM compare (BOM tab)

- Open a BOM Excel file with column mapping; dirty Designator cells are
  cleaned and ranges expanded (`C1-C4` → `C1,C2,C3,C4`).
- Dedicated **BOM** tab next to **PickPlace**: `STT | Designator | MPN |
  Description | Quantity | Note | Missing Pickplace`; Bottom-layer
  designators render red, quantity mismatches highlight yellow.
- Two-way compare: extra PickPlace rows tint orange (+ status filter
  `Extra`), MPN mismatches highlight red, empty MPN cells are auto-filled
  from BOM on load (logged as `BOM` history, single undo step). BOM rows
  persist in session v8.

### Sessions
- Save / load / restore the whole review session (`.cam350review` files, v8).
- The last session path is remembered for the next launch.
- **Gerber files are embedded** in the session (zlib+base64) so a `.cam350review` opened on another machine renders Gerber View even when the original Gerber files are not present. Existing local Gerber paths are preferred when they still exist.
- History, prescreen dismissals, panel config, PCB info, BOM rows, and Gerber view settings are all part of the session.

### Settings & calibration
- Calibration wizard to capture the on-screen positions of CAM350's X/Y text boxes and window title.
- Test CAM350 connection and jump.
- Config is stored in `%APPDATA%\CAM350_Review\config.json` (persists across installs).

---

## Installation

### From the installer (recommended)
Build or download the setup file (`CAM350_Review_Setup_2.2.3.exe`) and run it.
It installs to `%ProgramFiles%\CAM350 Review Assistant` and creates a desktop shortcut.

### From source
```bash
pip install -r requirements.txt
python main.py
```

---

## Usage

1. **Calibrate** first (Tools → Calibration Wizard) — capture the X and Y textbox positions in CAM350, set the window title and jump delay. This is required for the Jump feature.
2. Open a PickPlace file (**File → Open PickPlace Excel** or the toolbar button).
3. Review records:
   - Select a row to view details and its **History** timeline.
   - Use **Jump CAM350** (table / popup) to move the CAD view to that component.
   - Mark **OK** or press **Edit** to correct coordinates.
4. For large corrections, use **Batch Edit** on checked rows.
5. Optionally run **Align Origin** to auto-align against Gerber files.
6. Export the final report or the fixed PickPlace file.

### Keyboard shortcuts
| Action | Shortcut |
| --- | --- |
| Mark OK | `Space` |
| Edit | `Ctrl+E` |
| Previous / Next | `↑` / `↓` |
| Focus search | `Ctrl+F` |
| New / Open / Save session | `Ctrl+N` / `Ctrl+O` / `Ctrl+S` |
| Save session as | `Ctrl+Shift+S` |
| Open PickPlace file | `Ctrl+W` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |

---

## Configuration

- **Runtime data** (config + SQLite database) live in:
  `%APPDATA%\CAM350_Review\`
- **Seeded default config** is bundled with the app; on first run it is copied to the folder above.
- `cam350_review.db` holds `review` records and the `component_history` log; it is automatically migrated to the user data folder if an old copy exists next to the source. New installs create both tables plus the `(designator, block)` history index.

---

## Development

### Project layout
```
cam350-review/
├── main.py                     # Entry point (applies theme + starts MainWindow)
├── ui/                         # Qt widgets & dialogs
│   ├── main_window.py          # Main window, toolbar, history logging
│   ├── table_widget.py         # Filterable/selectable record table
│   ├── review_panel.py         # Detail panel + History table (Time|Step|Changes)
│   ├── edit_dialog.py          # Single-record editor
│   ├── batch_edit_dialog.py    # Batch offset editor
│   ├── calibration_wizard.py   # CAM350 calibration
│   ├── origin_align_wizard.py  # Gerber origin alignment
│   ├── settings_dialog.py      # Settings & connection tests
│   ├── jump_popup.py           # Always-on-top quick-review popup
│   ├── gerber_viewer.py        # Gerber overlay viewer
│   ├── bom_table_widget.py     # BOM tab table (missing/red/qty highlights)
│   ├── bom_dialogs.py          # BOM mapping + Fill MPN dialogs
│   ├── eco_diff_dialog.py      # ECO pick + result dialogs
│   └── style.py                # Global light theme (QSS, teal accent)
├── models/                     # Dataclasses (review, history, pickplace, bom, config)
│   ├── review.py
│   ├── history.py              # HistoryEntry (incl. MPN changes)
│   └── bom.py                  # BomRow
├── services/                   # Business logic
│   ├── pickplace_reader.py     # Excel PickPlace reader
│   ├── bom_reader.py           # Excel BOM reader + designator cleaning
│   ├── bom_compare.py          # Two-way BOM ↔ PickPlace compare
│   ├── eco_diff.py             # Old-vs-new PickPlace revision diff
│   ├── export_service.py       # Report / fixed-file export
│   ├── session_service.py      # Session save/load (v8 with history + BOM)
│   ├── cam350_controller.py    # CAM350 window automation
│   ├── datasheet_service.py    # Datasheet search
│   └── gerber/                 # Gerber parsing, panel detection, alignment
├── database/                   # SQLite connection + repositories
│   ├── database.py             # review + component_history + pcb_info schema
│   ├── review_repo.py
│   └── history_repo.py
├── config/                     # ConfigManager + default config.json
├── utils/                      # path helpers, version, theme, perf log
├── assets/                     # App logo (icon.ico) & rotation guide images
│   └── icon.ico
├── scripts/                    # PyInstaller spec + Inno Setup script
├── tools/                      # Seller-side license tool + user-guide builder
└── tests/                      # Pytest unit tests (incl. test_history.py, test_bom_*.py)
```

### Running tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

### Building the installer
```bash
# 1. Build the one-file executable
python -m PyInstaller scripts/build.spec --noconfirm

# 2. Build the setup program (Inno Setup 7)
"C:\Program Files\Inno Setup 7\ISCC.exe" scripts/installer.iss
```
Output: `dist\installer\CAM350_Review_Setup_2.2.5.exe`

---

## Updating

Updates are distributed as a new installer built from the same Inno Setup script
(same `AppId`), so running it over an existing install upgrades in place without
losing config, calibration, history, or license (all stored in `%APPDATA%\CAM350_Review\`).

### For users (on an installed machine)
1. Close the CAM350 Review app (or let the installer close it automatically).
2. Run the new `CAM350_Review_Setup_<version>.exe` **as Administrator**
   (right-click → *Run as administrator*).
3. Follow the wizard; it installs over the previous version in the same folder.
4. Relaunch the app — config/license/history are preserved.

### For the developer (publishing a new version)
1. Bump the version in `utils/version.py` (`APP_VERSION`).
2. Build the update file:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build_update.ps1
   ```
   Output: `dist\installer\CAM350_Review_Setup_<version>.exe`
3. Distribute that file over your LAN / Google Drive / email.

> Notes:
> - The installer requests admin rights because the app installs into `%ProgramFiles%`.
> - A named mutex (`CAM350ReviewMutex`) is created at startup so the installer
>   can detect a running instance and close it (`CloseApplications=yes`).
> - Never uninstall before upgrading — the installer handles it automatically.

---

## Requirements

See `requirements.txt`:

- PySide6
- openpyxl
- pyautogui
- pywin32
- numpy
- scipy
- cryptography
- gerbonara

Dev-only: `pytest` (see `requirements-dev.txt`).

---

## FAQ

- **Jump does nothing?** Run Tools → Calibration Wizard first and keep CAM350 running with mm units. Use Test Jump to verify.
- **Old session files?** v6 and earlier sessions still load; history will start from empty and grow with new edits, then save as v7.
- **History shows only the last edit?** Upgrade to 2.2.x: history is now append-only per `(designator, block)`. Edits made before the upgrade only have `review_time`.
- **Logo not showing on GitHub?** The README references `assets/icon.ico`. If your viewer does not render `.ico`, keep `icon.ico` for the app and add a `assets/logo.png` copy for docs only.

---

## License tool (seller-side)

A cross-platform terminal tool to create, verify, monitor, and renew customer licenses.
Runs on Windows, macOS, and Ubuntu — just needs Python 3 and `cryptography`:

```bash
pip install cryptography
python tools/license_tool.py            # interactive menu (Vietnamese)
```

### Commands (non-interactive)

```bash
# Create a new license (auto-saves to licenses.json)
python tools/license_tool.py create --hwid <HWID> --customer "Cty X" --days 365 [--device "Máy A" --note ...]

# Verify a key against a machine
python tools/license_tool.py verify --key <KEY> --hwid <HWID>

# List issued licenses / check a customer or machine
python tools/license_tool.py list
python tools/license_tool.py check --customer "Cty X"
python tools/license_tool.py check --hwid <HWID>

# Monitor: licenses expiring soon (default 30 days) or already expired
python tools/license_tool.py due [--days 30]

# Renew a license (extends expiry, generates new key, records history)
python tools/license_tool.py renew --hwid <HWID> --days 180

# Renewal history / overview stats
python tools/license_tool.py history [--customer "Cty X"]
python tools/license_tool.py stats
```

### Notes
- `create` / `renew` need `private_key.pem` (kept next to the tool on your USB stick).
  `verify`, `check`, `list`, `due`, `history`, `stats` use only the embedded public key —
  safe to run anywhere.
- Licenses are recorded in `licenses.json` next to the tool (override with env
  `CAM350_LICENSE_REGISTRY`), portable across OSes — plug the USB into any machine.
- The customer's HWID is generated by the app on their Windows machine; the tool only
  receives it as a string, so it works on macOS/Linux too.
- Renewing keeps the same HWID — the customer just pastes the new key, no new Machine ID needed.

---

## License / Contact

Created by Nguyễn Hải Đăng
Email: haidang34821@gmail.com
Phone: +84908799042
