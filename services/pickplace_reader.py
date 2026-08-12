from typing import Dict, Any, List, Optional

import openpyxl

from models.pickplace import PickPlaceData, PickPlaceComponent, COLUMN_FIELDS


REQUIRED_COLUMNS = {"Designator", "MPN", "Layer", "X", "Y", "Rotation"}

STANDARD_MAPPING = {
    "designator": "Designator",
    "mpn": "MPN",
    "layer": "Layer",
    "x": "X",
    "y": "Y",
    "rotation": "Rotation",
}

STANDARD_REQUIRED = set(COLUMN_FIELDS)

MIN_REQUIRED = {"designator", "x", "y"}

FIELD_ALIASES: Dict[str, tuple] = {
    "designator": (
        "designator", "refdes", "ref des", "ref", "reference",
        "component", "part reference", "reference designator",
    ),
    "mpn": (
        "mpn", "part number", "partnumber", "part no", "part no.",
        "pn", "part", "manufacturer part number", "mpn no", "mfr part no",
    ),
    "layer": (
        "layer", "side", "layer name", "assembly layer", "layer side",
        "top/bottom", "assembly side",
    ),
    "x": (
        "x", "xpos", "x pos", "x position", "center x", "centroid x",
        "coord x", "position x", "x(mm)", "x mm", "x coordinate",
    ),
    "y": (
        "y", "ypos", "y pos", "y position", "center y", "centroid y",
        "coord y", "position y", "y(mm)", "y mm", "y coordinate",
    ),
    "rotation": (
        "rotation", "rot", "angle", "orientation", "theta", "rotate",
        "rotation angle", "angle (deg)", "angle(deg)",
    ),
}


def _normalize(value: str) -> str:
    return "".join(value.lower().split())


def guess_mapping(headers: List[str]) -> Dict[str, str]:
    normalized = {_normalize(h): h for h in headers if h}
    mapping: Dict[str, str] = {}
    for field in COLUMN_FIELDS:
        for alias in FIELD_ALIASES[field]:
            key = _normalize(alias)
            if key in normalized:
                mapping[field] = normalized[key]
                break
    return mapping


class PickPlaceReader:

    @staticmethod
    def read_headers(file_path: str) -> List[str]:
        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Cannot open Excel file: {e}")

        try:
            sheet = workbook.active
            headers: List[str] = []
            if sheet is not None:
                for row in sheet.iter_rows(max_row=1, values_only=True):
                    headers = [str(h).strip() if h is not None else "" for h in row]
                    break
        finally:
            workbook.close()
        return headers

    @staticmethod
    def read(file_path: str) -> PickPlaceData:
        return PickPlaceReader.read_with_mapping(
            file_path, STANDARD_MAPPING, required=STANDARD_REQUIRED
        )

    @staticmethod
    def read_with_mapping(
        file_path: str,
        mapping: Optional[Dict[str, str]] = None,
        required: Optional[List[str]] = None,
    ) -> PickPlaceData:
        mapping = mapping or {}
        if required is None:
            required = list(STANDARD_REQUIRED)
        required_set = set(required)

        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Cannot open Excel file: {e}")

        try:
            sheet = workbook.active
            if sheet is None:
                raise ValueError("Excel file has no active sheet")

            rows = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()

        if len(rows) < 2:
            raise ValueError("Excel file has no data rows")

        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        header_lookup = {h.lower(): i for i, h in enumerate(headers) if h}

        col_map: Dict[str, int] = {}
        missing: List[str] = []
        for field in COLUMN_FIELDS:
            target = mapping.get(field)
            if not target:
                if field in required_set:
                    missing.append(field)
                continue
            key = str(target).strip().lower()
            if key in header_lookup:
                col_map[field] = header_lookup[key]
            elif field in required_set:
                missing.append(str(target))

        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

        data = PickPlaceData(headers=headers, file_path=file_path)
        data.column_mapping = dict(mapping)

        for row_idx, row in enumerate(rows[1:], start=1):
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            try:
                component = PickPlaceComponent(
                    designator=_safe_str(_cell(row, col_map.get("designator"))),
                    mpn=_safe_str(_cell(row, col_map.get("mpn"))),
                    layer=_safe_str(_cell(row, col_map.get("layer"))),
                    x=_safe_float(_cell(row, col_map.get("x"))),
                    y=_safe_float(_cell(row, col_map.get("y"))),
                    rotation=_safe_float(_cell(row, col_map.get("rotation"))),
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

        return data


def _cell(row: tuple, col_idx: Optional[int]) -> Any:
    if col_idx is None or col_idx >= len(row):
        return None
    return row[col_idx]


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
