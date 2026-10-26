# CAM350 Review Assistant — User Guide

![CAM350 Review Assistant logo](../assets/icon.ico)

**Version 2.2.3 · Windows · Python 3.12 + PySide6 · Session format v7**

This guide covers the complete application: installation, license activation,
calibration, PickPlace review, batch editing, per-component history, Gerber
alignment, Gerber View, panelize, PCB info, sessions, export, settings, and
troubleshooting. It is laid out for **A4 portrait printing** (see
`exports/USER_GUIDE_A4.pdf` / `exports/USER_GUIDE_A4.docx`).

---

## Table of Contents

1. Overview
2. System Requirements
3. Installation
4. License Activation
5. Application Layout
6. First-Time Setup (Calibration)
7. Opening a PickPlace File
8. BOM Compare (BOM Tab)
9. Reviewing Components
10. Table, Search, and Filters
11. Editing (Single, Batch, Undo/Redo)
12. Component History
13. Gerber Origin Align (7-Step Wizard)
14. Gerber View
15. Panelize
16. Compare Revisions (ECO)
17. PCB Info
18. Settings
19. Sessions
20. Export
21. Keyboard Shortcuts
22. Troubleshooting and FAQ
23. Appendix (File Formats and Data Locations)
24. Contact

---

## 1. Overview

CAM350 Review Assistant is a Windows desktop tool for reviewing and correcting
PickPlace data used with **CAM350**. Instead of checking coordinates manually
in CAD, you walk through every component in a table, jump the CAD view to each
coordinate, correct values, and export a fixed file.

Typical flow:

```text
Calibrate → Open PickPlace (.xlsx) → Review each row (OK / Edit)
→ Batch fix / Align origin → Check History → Export report + fixed file
```

## 2. System Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10/11 64-bit |
| CAD | CAM350 running, display units set to **mm** for accurate jumps |
| Python (source run) | 3.12 (PySide6, openpyxl, numpy, scipy, cryptography, gerbonara, pyautogui, pywin32) |
| Installer run | No Python needed, run `CAM350_Review_Setup_2.2.3.exe` as Administrator |
| Display | 1280×720 minimum, 1920×1080 recommended |

## 3. Installation

### 3.1 From the installer (recommended)

1. Close the app if it is running (the installer can also close it automatically
   via the `CAM350ReviewMutex` single-instance mutex).
2. Right-click `CAM350_Review_Setup_2.2.3.exe` → **Run as administrator**.
3. Follow the wizard. It installs to `%ProgramFiles%\CAM350 Review Assistant`
   and creates a desktop shortcut.
4. Launch the app. Config, calibration, history, and license are stored under
   `%APPDATA%\CAM350_Review\` and survive upgrades. Never uninstall before
   upgrading; install over the existing version.

### 3.2 From source

```bash
pip install -r requirements.txt
python main.py
```

For development and tests:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## 4. License Activation

1. On first launch the license dialog shows your **Machine ID**.
2. Click **Copy** and send it to your provider.
3. Paste the received **License Key** and click **Activate**.
4. If the key expires or does not match the machine, the app shows the reason
   (expired / wrong machine / invalid / clock issue). Fix the system clock first
   if a clock error is reported, then contact your provider for renewal.
5. Seller-side management uses `tools/license_tool.py` (create, verify, list,
   check, due, renew, history, stats). It needs `cryptography` and the
   `private_key.pem` only for `create`/`renew`.

## 5. Application Layout

| Area | Contents |
|---|---|
| Toolbar | New/Open/Save session, Open PickPlace (Excel), Open BOM, Gerber, Report, Export, Batch, PCB, OK Checked, Delete, Settings |
| Left: tabs | PickPlace tab (default: records, filters, Missing MPN hint column) + BOM tab (BOM rows, Missing Pickplace, red Bottom designators) |
| Right top: stats | Total, Pending, OK, Edited, Aligned counters |
| Right middle: Component Information | Designator, MPN, Layer, Original X/Y/Rotation, New X/Y/Rotation, Status, Datasheet, Remark, Progress |
| Right bottom: History | `Time \| Step \| Changes` timeline for the selected component (see §12) |
| Status bar | Current action feedback + `Showing N / M` filter count |
| Popup | `JumpPopup` — always-on-top quick review (Prev/Next, Jump, OK, Save, Delete) |

*Fig 1 — Main window (`docs/screenshots/main.png`, placeholder).*

## 6. First-Time Setup (Calibration)

Calibration is **required** before Jump works. Go to **Tools → Calibration
Wizard**.

1. Set the CAM350 window title (use **Detect** while CAM350 is in the
   foreground, or type it manually, e.g. `CAM350 V15`).
2. Capture the **X Textbox**: hover the mouse over the CAM350 X field, click
   **Start Capture**, wait for the countdown. Repeat for Y, Go button, and the
   90° rotate button.
3. Set **Jump delay** (ms) — increase it on slow machines.
4. Click **Save & Close**, then use **Test Jump (X=0, Y=0)** in Settings to
   verify. If the cursor lands in the wrong field, re-run the wizard.

## 7. Opening a PickPlace File

- **File → Open PickPlace Excel...** (`Ctrl+W`) for standard files with
  `Designator, MPN, Layer, X, Y, Rotation` columns.
- **File → Open PickPlace with Mapping...** for files with different headers.
  Map each source column to Designator/MPN/Layer/X/Y/Rotation, optionally save
  the mapping as a named profile, and use **Auto-guess** for the first attempt.
- After loading, every row becomes a `Pending` record with an `Import` history
  entry (`X: …, Y: …, Rot: …`). The table, stats, and Gerber button are enabled.

## 8. BOM Compare (BOM Tab)

The left panel has two tabs: **PickPlace** (default) and **BOM**.
Open a BOM file with **File → Open BOM Excel...** (toolbar **BOM** button):
pick each Excel header for Designator/MPN/Description/Quantity/Note in the
mapping dialog (aliases like RefDes, Part Number, Q'ty are auto-guessed).

- Dirty Designator cells are cleaned automatically: `C1-C4` expands to
  `C1,C2,C3,C4`, separators unify to commas, junk marks are stripped.
  Grouped rows (`C1,C2` or `C1-C8`) are expanded for matching.
- The BOM table shows `STT | Designator | MPN | Description | Quantity |
  Note | Missing Pickplace`. The last column lists BOM designators absent
  from the PickPlace file. Designators whose PickPlace Layer is Bottom
  (`Bot/Bottom/BottomLayer`) render in red. A Quantity differing from the
  designator count highlights yellow.
- **Two-way compare** runs automatically:
  - Rows in PickPlace but not in BOM tint orange and count up in the
    `PickPlace (Extra: N)` tab label; choose `Extra` in the status filter
    to list only them.
  - A PickPlace MPN differing from the BOM row shows red with a tooltip
    naming the BOM row; nothing is auto-corrected.
- **Fill MPN from BOM is automatic**: when a BOM is loaded (or a PickPlace
  file is loaded while a BOM exists), every empty PickPlace MPN cell matching
  a BOM designator is filled immediately — no prompt. First BOM row wins on
  conflicts (count reported in the status bar). Each filled row logs one `BOM`
  history entry (`MPN: →{new}`) and the whole batch is a single undo step
  (`Ctrl+Z` reverts it).
- The rightmost PickPlace column, **Missing MPN**, shows the BOM-suggested
  MPN (green) for empty cells as a read-only hint.
- Clicking a BOM row swaps the Component Information card for a **BOM
  Summary** card (same slot and height): bold `MPN`, `Qty` in pcs,
  `Top/Bottom/Missing` counts in pcs with wrapped designator lists (only
  Bottom names render red), plus a `Share` line with percentages
  (`Top 60% · Bottom 20% · Missing 20%`). Clicking any PickPlace row swaps
  back to Component Information. The History panel merges the matched records' timelines
  (newest 20).
- BOM rows and the source filename persist inside `.cam350review` sessions
  (v8); older sessions open with an empty BOM tab.

*Fig 2 — BOM tab (`docs/screenshots/bom.png`, placeholder).*

## 9. Reviewing Components

1. Click a row (or press `Up`/`Down`). The detail panel, stats, and History
   table update together.
2. Press **Jump** (table double-click or `JumpPopup` → Jump to CAM350) to move
   the CAD view to `new` coordinates if present, otherwise `old` coordinates.
3. Compare the board against the panel values:
   - `Space` → mark **OK** (copies old values to new when empty).
   - `Ctrl+E` → open **Edit**, change X/Y/Rotation/remark, confirm. Status
     becomes **Edited**.
4. Use `JumpPopup` during long sessions: `Prev/Next` walk, `OK` confirms,
   `Save` writes typed values, `Delete` removes the row after confirmation.
5. `Search Datasheet` looks up the MPN online in a background thread; the link
   appears in the detail panel without freezing the UI.

## 10. Table, Search, and Filters

- **Search box** (`Ctrl+F`): matches Designator or MPN; the status bar shows
  `Showing N / M`.
- **Status filter**: All / Pending / OK / Edited / Aligned.
- **Coordinate range filter**: minimum/maximum X and Y.
- **Clear filters** restores the full list; selection follows the visible rows.
- **Checkboxes**: tick rows for bulk OK/Batch/Delete. `Clear` unticks all.
- **Flags column**: pre-screen warnings (`ROT/PAD/DUP/OUT`) with dashed frames
  mirrored in Gerber View. Right-click → **Dismiss flag** if reviewed.

## 11. Editing (Single, Batch, Undo/Redo)

### 11.1 Single edit

`Ctrl+E` opens **Edit – {designator}**: original values on top, editable
`New X/Y/Rotation + Remark` below. Confirming sets status **Edited**,
`review_time`, and one `Edit` history row (`old → new` per changed field).

### 11.2 Batch edit

Toolbar → **Batch**: applies to all checked rows after a confirmation summary.

- X/Y/Rotation offsets: `new = current + offset` (current = `new` if present,
  else `old`), rounded to 4 decimals.
- **Make new X/Y negative**: flips the sign of the result.
- **Remark**: overwrites the remark on every selected row.
- Each touched row becomes **Edited** with its own `Batch` history row.

### 11.3 Bulk OK / Delete

- **OK Checked**: marks every checked row **OK** (fills empty new values from
  old), one `OK` history row each.
- **Delete Selected**: asks for confirmation, marks rows `Deleted`, removes them
  from the working list (kept in the session file for audit/export filtering).

### 11.4 Undo / Redo

`Ctrl+Z` / `Ctrl+Shift+Z` (menu **Edit** mirrors the state). Up to 50 snapshots
of the whole record list. Undo/redo restores values and statuses; the history
log itself is append-only and is not rolled back.

## 12. Component History

The right-bottom panel is a 3-column table:

| Time | Step | Changes |
|---|---|---|
| `10:15:30` | `Edit` | `X: 10->11.5, Rot: 0°->90°, Remark: …` |
| `09:50:12` | `Align` | `X: 9.8->10.0, Y: 20.1->20.0` |
| `09:30:05` | `Import` | `X: 10, Y: 20, Rot: 0°` |

- **Time** shows `HH:MM:SS` cut from `YYYY-MM-DD HH:MM:SS`.
- **Step** is one of `Import, Align, Edit, Batch, OK, Delete, BOM` (Gerber rotation
  edits log as `Edit`; MPN fills from BOM log as `BOM` with `MPN: old->new`).
- **Changes** lists only fields that changed (`old → new`); `OK` with no value
  change shows `No value change`. Remarks are appended when present.
- Newest entry is on top. Components with no edits show one spanned row:
  `No history`.
- Storage: SQLite `component_history` table keyed by `(designator, block)` with
  an index for fast lookup; the UI queries the latest 100 rows. History is
  saved inside `.cam350review` (session v8) and restored on load.

*Fig 2 — History table (`docs/screenshots/history.png`, placeholder).*

## 13. Gerber Origin Align (Internal / Legacy Wizard)

> **Note:** Origin Align and standalone Run Check have been removed from the
> main toolbar and Tools menu. The wizard backend is retained for compatibility
> with existing session files and programmatic workflows.

Requires a **GKO** outline file; **GTP** (top paste) / **GBP** (bottom paste)
improve accuracy; **GTO/GBO** silkscreen is display-only.

1. **Select Gerber files** — GKO required, others optional. Invalid GKO stops
   the wizard with the parse error.
2. **Panel detection** — Single board, Panel Type A (step-repeat), or Panel
   Type B (multiple blocks); shows origin, size, and instance list.
3. **Rotation and units** — 0/90/180/270°, top vs bottom 90° formula
   (`(H-y, x)` vs `(y, x)`), mm vs mil (`×0.0254`).
4. **Compute + update** — per-instance offsets with progress; writes are
   flushed in one DB transaction. Touched rows become **Aligned** with one
   `Align` history row each.
5. **Panel origin from CAM350 (macro)** — top layer: `Ctrl+Alt+X` then jump to
   the panel origin; bottom layer adds `Ctrl+Alt+B` first; optional 90° board
   rotate via `Ctrl+Alt+R`. Switch to the CAM350 window inside the 5-second
   countdown and confirm with Enter. CAM350 must show **mm** units.
6. **Pre-screen check** — `Run Check` scans all rows (`ROT` unusual rotation vs
   MPN majority, `PAD` paste offset over tolerance, `DUP` shared coordinates,
   `OUT` outside outline). Re-run anytime from the toolbar; dismiss reviewed
   flags per row.
7. **Result** — origin mode, rotation, mil→mm flag, per-instance offsets and
   match counts, totals aligned vs skipped.

## 14. Gerber View

**Tools → Gerber View...** (enabled once records exist; also pick files in the
Gerber file dialog first).

- **Card on the left of the board** — *Layers + Overlay*. The chevron in its
  header folds the card away, so the board takes the whole width; the card
  always opens wide.
- The page reaches beyond the Gerber: the view can be scrolled and zoomed
  outside the outline of the board without being held back, so that a part
  that lies off the board can still be looked at. How far the page can be
  shrunk is still the zoom factor of the reference tool.
- **Toolbar under the title**: *Set origin* (a target icon) chooses the point
  the coordinates count from — turn it on and click the board.
- **Layers**: every file of the folder is a layer. The table has three
  columns — a tick (tick = shown, no tick = hidden), the name of the layer
  and the name of the file. Hovering a row shows the whole name, the place
  of the file and the colour of the layer. *Show all*, *Hide all* and *Only
  active* work on the whole list; clicking the name brings the layer on top
  of the others and hands it to the palette of the colours.
- **Colors**: a palette of 24 colours and a *Custom...* button. Click the
  swatch of the crosshair to choose what the palette works on — the label
  under the group tells which one; otherwise it works on the layer that was
  brought on top. The colour is taken at once, and the session remembers it.
- **Overlay (Pick&Place)**: show the crosshair, the colour of the crosshair
  and of the highlight, the scale of the crosshair, and the mark of the
  origin of the coordinates.
- **Mark of the origin**: a grey X of 3 mm stands at the point the
  coordinates count from. It follows the rotation, the flips and the
  offset, so it always shows where the origin lies on the page. *Show
  origin (0,0)* in the overlay group takes it away and brings it back.
- **Choosing the origin**: the *Set origin* button of the toolbar turns
  into a mode — click the board and the X jumps there, exactly onto the
  point that was clicked, and that point reads `0.00 / 0.00` from then on.
  The Pick&Place marks move with the origin: the origin is the point of
  the Gerber that stands for the (0,0) of the board, so picking the
  corner of the board puts the parts of the Pick&Place back on their
  pads. The component table keeps the coordinates of the file.
- **Reading coordinates**: the coordinate bar under the board shows the
  coordinates counted from the origin that was set — at the mark of the
  origin they read `0.00 / 0.00`, and at a part of the Pick&Place they
  read the same numbers as the component table. The coordinates of the
  file are shown in brackets, to look them up in the CAD. The X/Y fields
  of the footer and the *Go* button count from the origin as well.
- **The Pick&Place data does not move**: the component table, the menu of
  a component and the records keep the coordinates of the file, and they
  do not change when the origin is moved. Only the marks on the board
  and the numbers that count from the origin follow it.
- The Pick&Place parts stand in the coordinates of the board: they do not
  follow the turn of the page — it is the layers of the Gerber that are
  turned, so that they come to the parts.
- The layers, the colours and the crosshair are drawn right away; the
  *Display...* dialog keeps the transform and offset, the PickPlace
  markers, the snapping, the grid and the OpenGL switch, and its
  *Save display settings* button writes them into the session.
- Left table mirrors the main records with search and `Rot` column; selecting
  a row centers both the main and magnifier views.
- Details pane shows zoom factor and hover info; the magnifier looks at
  the mark of the part, wherever the origin put it; **Measure** clicks two
  points (`Esc`/right-click cancels, `Ctrl+click` bypasses snap).
- **Filters…** and **Display…** control attributes, coordinate ranges, rotation,
  mirror, offsets, and visibility. **Save display settings** persists them into
  the session.
- Rotation editor per component (including IC mode) writes `new_rotation`,
  status **Edited**, and an `Edit` history row.
- **Export PDF** renders the current overlay; **Fit View** and **Reset** restore
  the camera.

## 15. Panelize

**Tools → Panelize...** multiplies one board into `N` blocks.

1. Set the board count; Block 1 stays at `(0, 0)`.
2. Enter each extra block origin (normal block: bottom-left corner; 180°
   flipped block: top-right corner — click a board preview to flip it).
3. Optionally rename designators (`C1 → C1_2, C1_3, …`); GKO outline can
   auto-fill origins via **Detect from GKO**.
4. Confirm the `boards × parts = total` preview. New blocks start with empty
   history. **Tools → Clear Panelize** restores the pre-panel snapshot (kept
   for undo).

## 16. Compare Revisions (ECO)

**Tools → Compare Revisions (ECO)...** diffs the open session against a new
PickPlace file (the old side is always the current records, using reviewed
values where present).

1. Pick the **new `.xlsx`** (column mapping when headers differ) and set
   tolerances (`Move tol` default 0.01 mm, `Rotation tol` default 1.0°,
   remembered in config).
2. Browse the result groups **Added / Removed / Moved / MPN changed /
   Duplicates** with `Designator | Old | New | Δ` rows and
   `+A −R ~M ⇄P ⧉D` counts. The header shows unique-code counts on both
   sides, so a raw total mismatch with empty Added/Removed means duplicated
   rows — listed explicitly under Duplicates (`Designator | Old/New |
   ×count`). Clicking a row selects it in the main table (and Gerber View
   when open).
3. **Apply to current session** (confirm dialog with summary + optional
   one-click ECO report export): added rows arrive as `Pending` with
   `Import` history; removed rows are kept with remark `ECO removed`;
   moved rows take the new coordinates, reset to `Pending` with `Edit`
   history; MPN changes log `ECO` history. The whole batch is one undo step.
4. **Export ECO Report** (`.xlsx`, single `ECO Diff` sheet with a Group
   column) any time from the result dialog.

## 17. PCB Info

**Tools → PCB Info...** stores board width/height, working area, position,
thickness, and three Boc fiducial coordinates.

- Place the mouse in CAM350 and press the shown hotkey to auto-fill
  Boc 1 → Boc 2 → Boc 3. **Save** appears once enough data exists.
- Data persists in its own table and is included in sessions and the fixed
  PickPlace export. **Reset** restores defaults after confirmation.

## 18. Settings

**Tools → Settings**: CAM350 window title, jump delay, captured X/Y/Go/Rotate
positions, theme (Light/Dark — toolbar icons and title bar repaint), language
(English/Vietnamese — rebuilds menus/toolbar), **Run Calibration Wizard**,
**Test CAM350 Connection**, **Test Jump**, **Reset Configuration**, Save/Cancel.
Language and theme apply immediately without losing records.

## 19. Sessions

- **File → New / Open / Save / Save As** (`Ctrl+N / Ctrl+O / Ctrl+S /
  Ctrl+Shift+S`). Files use the `.cam350review` JSON format (v8).
- A session stores records (+ deleted audit rows), current index, PCB info,
  Gerber paths + embedded Gerber contents, Gerber view settings, column
  mapping, prescreen dismissals, panel config, the full history log, and the
  BOM rows + BOM source filename.
- Old sessions load transparently (missing BOM/history keys yield empty views);
  missing source files fall back to embedded record data. The last session path
  is remembered in config.

## 20. Export

Both run in background threads with progress; success/failure is reported in
the status bar and a message box.

- **Export Review Report** (`.xlsx`): every record including old/new/aligned
  values, status, remark, and review time.
- **Export PickPlace Fixed** (`.csv` by default): corrected coordinates,
  original columns preserved, `Deleted` rows skipped, PCB info applied.
  On the toolbar, the **Export** button always drops a menu with
  `PickPlace Fixed` and `BOM Fixed` (same items live under File → Export).
- **Export PickPlace Fixed Top / Bottom** (`.csv`): byte-identical format to
  PickPlace Fixed, filtered to one layer (`Bot/Bottom/BottomLayer/...` →
  Bottom, everything else including empty → Top). Choosing an empty layer
  warns instead of writing an empty file.
- **Export BOM Fixed** (`.xlsx`): the cleaned BOM table as shown in the BOM
  tab (`STT, Designator, MPN, Description, Quantity, Note, Missing
  Pickplace`). Clicking it first asks for a report title (blank by
  default): the title merges across all columns in red Times New Roman 24,
  headers are light gray, everything is Times New Roman 13 with table
  borders, and only Bottom designators render red inside the Designator
  cell. Enabled once a BOM is loaded.

## 21. Keyboard Shortcuts

| Action | Shortcut |
|---|---|
| Mark OK | `Space` |
| Edit | `Ctrl+E` |
| Previous / Next | `↑` / `↓` |
| Focus search | `Ctrl+F` |
| New / Open / Save session | `Ctrl+N` / `Ctrl+O` / `Ctrl+S` |
| Save session as | `Ctrl+Shift+S` |
| Open PickPlace file | `Ctrl+W` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |

## 22. Troubleshooting and FAQ

| Symptom | Cause → Fix |
|---|---|
| Jump lands in the wrong field | Bad calibration → re-run Calibration Wizard, then Test Jump |
| `CAM350 window not found` | Wrong title or minimized → Detect title again, restore the window |
| Macro fails / no origin | CAM350 not in mm, or wrong layer → set mm units, pick Top/Bottom correctly |
| `No numeric value in CAM350 X/Y field` | Clipboard/field unreadable → click the field once, retry |
| Old session has empty history | Saved before v2.2 → history starts fresh after upgrade, then persists as v8 |
| BOM tab empty after opening an old session | Sessions saved before BOM support carry no `bom_rows` → re-open the BOM file |
| Fill MPN finds nothing | PickPlace MPN cells already filled, or no BOM designator matches (check cleaning/prefix) |
| History shows only one edit | You are on an old build → upgrade; current log is append-only per `(designator, block)` |
| `Session file is empty` | Corrupt/empty `.cam350review` → re-open the source `.xlsx` |
| App already running blocks installer | Single-instance mutex → close the app or let the installer close it |

## 23. Appendix (File Formats and Data Locations)

- Runtime dir: `%APPDATA%\CAM350_Review\` (`config.json`, `cam350_review.db`,
  `error.log`, `perf.log`, `tmp_gerber/`).
- SQLite tables: `review` (one row per component), `component_history`
  (`designator, block, action, old/new x/y/rotation, mpn_old/new, remark,
  created_at` + `(designator, block, id DESC)` index), `pcb_info` (single row `id=1`).
- Session JSON keys: `version, source_file, current_index, records, pcb_info,
  gerberGko/Gtp/Gbp/Gto/Gbo, gerber_view, column_mapping, gerber_files,
  prescreen_dismissed, prescreen_ctx, panel_config, history, bom_rows,
  bom_source_file`.
- Installer: `%ProgramFiles%\CAM350 Review Assistant`, AppId-shared upgrades,
  `CAM350ReviewMutex` for close-during-install.
- Print: this guide targets **A4 portrait, 20 mm margins, 11 pt** (see
  `exports/USER_GUIDE_A4.pdf` / `.docx`).

## 24. Contact

Created by Nguyễn Hải Đăng — Email: haidang34821@gmail.com — Phone:
+84908799042. Include your `error.log` tail and the failing
`.cam350review`/`.xlsx` sample (redacted) when reporting issues.
