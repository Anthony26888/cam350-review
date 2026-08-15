# CAM350 Review Assistant

A desktop tool for reviewing and correcting PickPlace data used with **CAM350**. It lets you walk through every component, verify/adjust its coordinates against the CAM350 view, batch-edit offsets, align component origins against Gerber files, and export corrected data — all without leaving your review flow.

- Built with **Python 3 + PySide6 (Qt)** and **openpyxl**
- Targets **Windows** (uses `win32gui`/`pyautogui` to drive CAM350)
- Current version: **2.1.2**

---

## Features

### Core review workflow
- Open a PickPlace Excel file (`.xlsx`) — reads `Designator`, `MPN`, `Layer`, `X`, `Y`, `Rotation` columns.
- Review each component in a detail panel with previous/next navigation.
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

### Alignment (Gerber origin align)
- Wizard that detects the board/panel outline from a **GKO** Gerber file.
- Optional **GTP** (top paste) / **GBP** (bottom paste) for more accurate offsets.
- Auto-aligns component coordinates to the panel/board origin, supports 90/180/270° rotation, and mil→mm conversion.
- Runs in a background thread with progress feedback.

### Export
- **Export Review Report** — full review report as `.xlsx` (old/new/aligned values, status, remark, review time).
- **Export PickPlace Fixed** — corrected PickPlace file, preserving original columns and skipping deleted records.
- Both exports run in background threads.

### Sessions
- Save / load / restore the whole review session (`.cam350review` files).
- The last session is remembered and restored on the next launch.
- **Gerber files are embedded** in the session (zlib+base64) so a `.cam350review`
  opened on another machine renders Gerber View even when the original Gerber
  files are not present. The saved file is slightly larger; existing local
  Gerber paths are preferred when they still exist.

### Settings & calibration
- Calibration wizard to capture the on-screen positions of CAM350's X/Y text boxes and window title.
- Test CAM350 connection and jump.
- Config is stored in `%APPDATA%\CAM350_Review\config.json` (persists across installs).

---

## Installation

### From the installer (recommended)
Build or download the setup file (`CAM350_Review_Setup_2.1.2.exe`) and run it.
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
   - Select a row to view details.
   - Use **Jump CAM350** to move the CAD view to that component.
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
- `database\cam350_review.db` holds the review records; it is automatically migrated to the user data folder if an old copy exists next to the source.

---

## Development

### Project layout
```
cam350-review/
├── main.py                     # Entry point (applies theme + starts MainWindow)
├── ui/                         # Qt widgets & dialogs
│   ├── main_window.py          # Main window, toolbar, actions
│   ├── table_widget.py         # Filterable/selectable record table
│   ├── review_panel.py         # Detail panel
│   ├── edit_dialog.py          # Single-record editor
│   ├── batch_edit_dialog.py    # Batch offset editor
│   ├── calibration_wizard.py   # CAM350 calibration
│   ├── origin_align_wizard.py  # Gerber origin alignment
│   ├── settings_dialog.py      # Settings & connection tests
│   ├── jump_popup.py           # Always-on-top quick-review popup
│   └── style.py                # Global light theme (QSS, teal accent)
├── models/                     # Dataclasses (review, pickplace, config)
├── services/                   # Business logic
│   ├── pickplace_reader.py     # Excel PickPlace reader
│   ├── export_service.py       # Report / fixed-file export
│   ├── session_service.py      # Session save/load
│   ├── cam350_controller.py    # CAM350 window automation
│   ├── datasheet_service.py    # Datasheet search
│   └── gerber/                 # Gerber parsing, panel detection, alignment
├── database/                   # SQLite connection + repository
├── config/                     # ConfigManager + default config.json
├── utils/                      # path helpers (resource/user-data paths)
├── assets/                     # Icons & rotation guide images
├── scripts/                    # PyInstaller spec + Inno Setup script
└── tests/                      # Pytest unit tests
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
Output: `dist\installer\CAM350_Review_Setup_2.1.2.exe`

---

## Updating

Updates are distributed as a new installer built from the same Inno Setup script
(same `AppId`), so running it over an existing install upgrades in place without
losing config, calibration, or license (all stored in `%APPDATA%\CAM350_Review\`).

### For users (on an installed machine)
1. Close the CAM350 Review app (or let the installer close it automatically).
2. Run the new `CAM350_Review_Setup_<version>.exe` **as Administrator**
   (right-click → *Run as administrator*).
3. Follow the wizard; it installs over the previous version in the same folder.
4. Relaunch the app — config/license are preserved.

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

Dev-only: `pytest` (see `requirements-dev.txt`).

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
