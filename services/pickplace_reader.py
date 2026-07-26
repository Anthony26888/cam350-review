from typing import Dict, Any, List, Optional

import openpyxl

from models.pickplace import PickPlaceData, PickPlaceComponent


REQUIRED_COLUMNS = {"Designator", "MPN", "Layer", "X", "Y", "Rotation"}


class PickPlaceReader:

    @staticmethod
    def read(file_path: str) -> PickPlaceData:
        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Cannot open Excel file: {e}")

        sheet = workbook.active
        if sheet is None:
            raise ValueError("Excel file has no active sheet")

        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) < 2:
            raise ValueError("Excel file has no data rows")

        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        header_lower = {h.lower(): i for i, h in enumerate(headers)}

        missing = REQUIRED_COLUMNS - set(h for h in headers if h)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

        col_map = {
            "designator": header_lower.get("designator"),
            "mpn": header_lower.get("mpn"),
            "layer": header_lower.get("layer"),
            "x": header_lower.get("x"),
            "y": header_lower.get("y"),
            "rotation": header_lower.get("rotation"),
        }

        data = PickPlaceData(headers=headers, file_path=file_path)

        for row_idx, row in enumerate(rows[1:], start=1):
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            try:
                component = PickPlaceComponent(
                    designator=_safe_str(row[col_map["designator"]]),
                    mpn=_safe_str(row[col_map["mpn"]]),
                    layer=_safe_str(row[col_map["layer"]]),
                    x=_safe_float(row[col_map["x"]]),
                    y=_safe_float(row[col_map["y"]]),
                    rotation=_safe_float(row[col_map["rotation"]]),
                    row=row_idx,
                )
            except (IndexError, TypeError):
                continue

            raw_row: Dict[str, Any] = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    raw_row[header] = row[i]
            data.raw_data.append(raw_row)
            data.components.append(component)

        workbook.close()
        return data


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
