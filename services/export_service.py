import csv
import os
from typing import Dict, List, Optional

import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from models.bom import BomRow
from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from models.pickplace import PickPlaceData


_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)

_DELETED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
_DELETED_FONT = Font(color="9C0006", size=11)

_BOM_TITLE_FONT = Font(name="Times New Roman", bold=True, color="FF0000", size=24)
_BOM_HEADER_FILL = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
_BOM_HEADER_FONT = Font(name="Times New Roman", bold=True, color="000000", size=13)
_BOM_BODY_FONT = Font(name="Times New Roman", size=13)
_BOM_RED = "FF0000"
_BOM_BLACK = "000000"


class ExportService:

    @staticmethod
    def export_report(records: List[ReviewRecord], file_path: str) -> str:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Review Report"

        headers = [
            "Designator", "MPN", "Layer", "Old X", "Old Y", "Old Rotation",
            "New X", "New Y", "New Rotation",
            "Aligned X", "Aligned Y", "Aligned Rotation",
            "Status", "Pre-screen Flags", "Remark", "Review Time",
        ]

        _write_header(sheet, headers)

        for row_idx, record in enumerate(records, start=2):
            sheet.cell(row=row_idx, column=1, value=record.designator)
            sheet.cell(row=row_idx, column=2, value=record.mpn)
            sheet.cell(row=row_idx, column=3, value=record.layer)
            sheet.cell(row=row_idx, column=4, value=record.old_x)
            sheet.cell(row=row_idx, column=5, value=record.old_y)
            sheet.cell(row=row_idx, column=6, value=record.old_rotation)
            is_edited = record.status in ("Edited", "OK")
            is_aligned = record.status in ("Aligned", "OK")
            sheet.cell(row=row_idx, column=7, value=record.new_x if is_edited else "")
            sheet.cell(row=row_idx, column=8, value=record.new_y if is_edited else "")
            sheet.cell(row=row_idx, column=9, value=record.new_rotation if is_edited else "")
            sheet.cell(row=row_idx, column=10, value=record.new_x if is_aligned else "")
            sheet.cell(row=row_idx, column=11, value=record.new_y if is_aligned else "")
            sheet.cell(row=row_idx, column=12, value=record.new_rotation if is_aligned else "")
            sheet.cell(row=row_idx, column=13, value=record.status)
            sheet.cell(row=row_idx, column=14, value="·".join(record.prescreen_flags))
            sheet.cell(row=row_idx, column=15, value=record.remark)
            sheet.cell(row=row_idx, column=16, value=record.review_time or "")

            _apply_row_style(sheet, row_idx, len(headers))
            if record.status == "Deleted":
                for col in range(1, len(headers) + 1):
                    cell = sheet.cell(row=row_idx, column=col)
                    cell.fill = _DELETED_FILL
                    cell.font = _DELETED_FONT

        _auto_width(sheet, headers)

        workbook.save(file_path)
        workbook.close()
        return file_path

    @staticmethod
    def export_pickplace_fixed(
        records: List[ReviewRecord],
        original_data: PickPlaceData,
        file_path: str,
        pcb_info: Optional[PcbInfo] = None,
    ) -> str:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        by_block: dict = {}
        for r in records:
            by_block.setdefault(getattr(r, "block", 0), []).append(r)

        # The block/instance column (Panel_Instance) is always dropped so the
        # exported file stays clean. Per-block rows are still written block by
        # block below; blocks are told apart by renamed designators (C1_2, ...)
        # when the panelize rename option is on.
        headers = [
            h for h in original_data.headers
            if h.strip().lower() not in ("layer", "panel_instance")
        ]

        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            if pcb_info is not None and pcb_info.has_data():
                writer.writerow(pcb_info.to_row())

            for block_idx in sorted(by_block):
                block_records = {
                    (r.base_designator or r.designator): r
                    for r in by_block[block_idx]
                    if r.designator
                }
                for raw_row in original_data.raw_data:
                    des = str(raw_row.get("Designator", "")).strip()
                    record = block_records.get(des)
                    if record is None:
                        continue

                    values = []
                    for header in headers:
                        value = raw_row.get(header, "")
                        hdr_lower = header.lower()
                        if hdr_lower == "designator":
                            value = record.designator
                        elif hdr_lower == "x":
                            if block_idx or record.new_x is not None:
                                value = record.new_x if record.new_x is not None else record.old_x
                        elif hdr_lower == "y":
                            if block_idx or record.new_y is not None:
                                value = record.new_y if record.new_y is not None else record.old_y
                        elif hdr_lower == "rotation":
                            if block_idx or record.new_rotation is not None:
                                value = record.new_rotation if record.new_rotation is not None else record.old_rotation
                        values.append(value)
                    writer.writerow(values)

        return file_path

    @staticmethod
    def export_pickplace_fixed_by_layer(
        records: List[ReviewRecord],
        original_data: PickPlaceData,
        file_path: str,
        layer: str,
        pcb_info: Optional[PcbInfo] = None,
    ) -> int:
        """Same format as export_pickplace_fixed, filtered to one layer.

        layer: "top" (everything not Bottom, empty included) or "bottom".
        Returns the number of matching records; writes nothing when 0.
        """
        from services.bom_compare import is_bottom_layer
        want_bottom = (layer or "").strip().lower() == "bottom"
        filtered = [r for r in records
                    if is_bottom_layer(r.layer) == want_bottom]
        if not filtered:
            return 0
        ExportService.export_pickplace_fixed(
            filtered, original_data, file_path, pcb_info)
        return len(filtered)

    @staticmethod
    def export_bom_fixed(
        bom_rows: List[BomRow],
        file_path: str,
        missing_of: Optional[Dict[int, List[str]]] = None,
        bottom_keys: Optional[set] = None,
        title: str = "",
    ) -> str:
        """Export the cleaned BOM table as a styled .xlsx workbook.

        Row 1: merged title (Times New Roman 24, red, centered).
        Row 2: gray header. Data rows: Times New Roman 13, thin borders;
        only Bottom designators render red inside the Designator cell.
        """
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont
        from openpyxl.styles import Color

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        missing_of = missing_of or {}
        bottom = {str(k or "").strip().upper() for k in (bottom_keys or set())}

        headers = ["STT", "Designator", "MPN", "Description",
                   "Quantity", "Note", "Missing Pickplace"]

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "BOM Fixed"

        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        title_cell = sheet.cell(row=1, column=1, value=title)
        title_cell.font = _BOM_TITLE_FONT
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        sheet.row_dimensions[1].height = 32

        for col_idx, header in enumerate(headers, start=1):
            cell = sheet.cell(row=2, column=col_idx, value=header)
            cell.font = _BOM_HEADER_FONT
            cell.fill = _BOM_HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center",
                                       wrap_text=True)
            cell.border = _THIN_BORDER

        top_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
        center_mid = Alignment(horizontal="center", vertical="center",
                               wrap_text=True)
        for row_idx, row in enumerate(bom_rows, start=3):
            values = [
                row.stt,
                None,  # Designator: rich text below
                row.mpn,
                row.description,
                row.quantity_raw or (row.quantity if row.quantity else ""),
                row.note,
                ", ".join(missing_of.get(row.stt, [])),
            ]
            for col_idx, value in enumerate(values, start=1):
                if col_idx == 2:
                    continue
                cell = sheet.cell(row=row_idx, column=col_idx, value=value)
                cell.font = _BOM_BODY_FONT
                cell.border = _THIN_BORDER
                cell.alignment = center_mid if col_idx in (1, 5) else top_left
            names = [d.strip() for d in row.designator_display.split(",")
                     if d.strip()] or [d.strip() for d in row.designators
                                       if d.strip()]
            des_cell = sheet.cell(row=row_idx, column=2)
            if len(names) == 1:
                # single name: plain value + cell font round-trips reliably
                lone_red = names[0].upper() in bottom
                des_cell.value = names[0]
                des_cell.font = Font(
                    name="Times New Roman", size=13,
                    color=_BOM_RED if lone_red else _BOM_BLACK)
            else:
                blocks = []
                for pos, name in enumerate(names):
                    if pos:
                        blocks.append(", ")
                    color = _BOM_RED if name.upper() in bottom else _BOM_BLACK
                    blocks.append(TextBlock(
                        InlineFont(sz=13, rFont="Times New Roman",
                                   color=Color(rgb=color)),
                        name))
                des_cell.value = CellRichText(blocks) if blocks else ""
            des_cell.border = _THIN_BORDER
            des_cell.alignment = top_left

        _auto_width(sheet, headers, min_row=2)
        sheet.freeze_panes = "A3"
        workbook.save(file_path)
        workbook.close()
        return file_path

    @staticmethod
    def export_eco_report(diff, file_path: str) -> str:
        """Export an ECO compare result (single sheet + Group column)."""
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "ECO Diff"

        headers = ["Group", "Designator", "Old", "New", "Change"]
        _write_header(sheet, headers)

        def _coord(x, y, rot) -> str:
            return f"{x}, {y} / {rot}"

        rows = []
        for a in diff.added:
            rows.append(("Added", a.designator, "-",
                         f"{_coord(a.x, a.y, a.rotation)}"
                         + (f" · {a.mpn}" if a.mpn else ""), "+new"))
        for x in diff.removed:
            rows.append(("Removed", x.designator,
                         f"{_coord(x.x, x.y, x.rotation)}", "-", "−gone"))
        for v in diff.moved:
            rows.append(("Moved", v.designator,
                         f"{_coord(v.old_x, v.old_y, v.old_rotation)}",
                         f"{_coord(v.new_x, v.new_y, v.new_rotation)}",
                         f"ΔX{v.dx:+g} ΔY{v.dy:+g} ΔR{v.drot:+g}°"))
        for c in diff.mpn_changed:
            rows.append(("MPN changed", c.designator, c.old_mpn, c.new_mpn,
                         "MPN"))
        for d in list(diff.old_duplicates) + list(diff.new_duplicates):
            rows.append(("Duplicates", d.designator,
                         "Old" if d.side == "old" else "New",
                         f"×{d.count}", "dup"))

        for row_idx, values in enumerate(rows, start=2):
            for col_idx, value in enumerate(values, start=1):
                sheet.cell(row=row_idx, column=col_idx, value=value)
            _apply_row_style(sheet, row_idx, len(headers))

        _auto_width(sheet, headers)
        sheet.freeze_panes = "A2"
        workbook.save(file_path)
        workbook.close()
        return file_path


def _write_header(sheet, headers: List[str], row: int = 1) -> None:
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _THIN_BORDER


def _apply_row_style(sheet, row_idx: int, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = sheet.cell(row=row_idx, column=col)
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _auto_width(sheet, headers: List[str], min_row: int = 2) -> None:
    for col_idx, header in enumerate(headers, start=1):
        max_len = len(header)
        for row in sheet.iter_rows(
            min_col=col_idx, max_col=col_idx, min_row=min_row, max_row=sheet.max_row
        ):
            for cell in row:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        sheet.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 30)
