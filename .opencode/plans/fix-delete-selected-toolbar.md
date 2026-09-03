# Fix: Nút "Delete Selected" / "OK Checked" trên toolbar bấm không chạy

## Nguyên nhân
- `ui/main_window.py`: `_btn_delete` (dòng 414) và `_btn_ok_checked` (dòng 407) được tạo + enable sau khi load, nhưng **thiếu `.clicked.connect(...)`** — mất từ một lần refactor trước.
- Hàm xử lý vẫn tồn tại: `_delete_selected` (dòng 1329), `_mark_checked_ok` (dòng 1294).

## Sửa (ui/main_window.py)
1. Sau dòng `self._btn_ok_checked.setEnabled(False)` (~412):
   ```python
   self._btn_ok_checked.clicked.connect(self._mark_checked_ok)
   ```
2. Sau dòng `self._btn_delete.setEnabled(False)` (~419):
   ```python
   self._btn_delete.clicked.connect(self._delete_selected)
   ```

## Test chống hồi quy (tests/test_main_window_delete.py)
Thêm test kiểm tra 2 dòng connect tồn tại trong mã nguồn `ui/main_window.py`
(không có hạ tầng dựng MainWindow thật trong test suite):
```python
def test_toolbar_action_buttons_are_connected():
    src = (Path(__file__).resolve().parents[1] / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "self._btn_delete.clicked.connect(self._delete_selected)" in src
    assert "self._btn_ok_checked.clicked.connect(self._mark_checked_ok)" in src
```
(cần `from pathlib import Path` ở đầu file)

## Kiểm chứng
- `python -m pytest tests/test_main_window_delete.py -q` → 10 pass
- Full suite: `python -m pytest -q` → kỳ vọng 326 passed
- Thủ công: load CSV → tick dòng → bấm Delete Selected hiện dialog xác nhận; bấm OK Checked đánh dấu OK.

## Trạng thái
- [x] Chẩn đoán xong
- [ ] Áp dụng edit (đang bị chặn bởi Plan mode — cần chuyển sang Build)
- [ ] Thêm test + chạy suite
