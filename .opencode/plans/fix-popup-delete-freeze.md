# Fix: Bấm Delete trong Component Info làm đơ app

## Triệu chứng (user xác nhận)
- Đơ NGAY khi bấm Delete, KHÔNG thấy dialog xác nhận nào.

## Nguyên nhân
1. **Dialog xác nhận bị che**: `QMessageBox.question(self, ...)` (parent = MainWindow) KHÔNG có cờ StaysOnTop, trong khi Component Info popup có `Qt.WindowStaysOnTopHint` + `show_at()` căn giữa màn hình → hộp thoại modal mở ra NẰM DƯỚI popup → không nhìn thấy, mọi input bị chặn → "đơ".
2. **(Nguy cơ treo sau khi Yes)**: `refresh_records()` đặt `_scene_key = None` → mỗi lần xóa phải `scene.clear()` + render lại toàn bộ Gerber → treo nhiều giây trên board thật. Cần sửa luôn để mượt.

## Sửa 1 — ui/main_window.py (`_popup_delete`, ~dòng 1056)
Thay `QMessageBox.question(...)` bằng box instance luôn nổi trên popup:
```python
box = QMessageBox(self)
box.setWindowTitle(tr("Delete Record"))
box.setText(tr("Delete {des}?", des=record.designator))
box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
reply = box.exec()
```
(`Qt` đã được import sẵn trong main_window.py)

## Sửa 2 — ui/gerber_viewer.py
1. Tách block tạo marker overlay (hiện tại dòng 1977-2005 trong `_apply_style`) thành method mới:
```python
def _rebuild_marker_overlay(self) -> None:
    if not self._chk_pickplace.isChecked():
        if self._overlay is not None:
            self._scene.removeItem(self._overlay)
            self._overlay = None
        return
    grid = self._pad_grid(self._combo_layer.currentIndex() == 0)
    markers = []
    for record in self._current_layer_records():
        x, y, rotation = _record_coord(record)
        size = grid.nearest(x, y)
        half = _crosshair_half(size, self._cross_half) * self._crosshair_scale
        markers.append((x, -y, rotation, half))
    try:
        view_scale = abs(self._view.transform().m11())
    except Exception:
        view_scale = 1.0
    arrow_floor = (self._arrow_min_px / view_scale) if view_scale > 0 else 0.0
    if self._overlay is not None:
        self._scene.removeItem(self._overlay)
    self._overlay = MarkerOverlayItem(
        markers, show_unselected=self._chk_crosshair.isChecked(),
        arrow_floor=arrow_floor, arrow_min_px=self._arrow_min_px,
        cross_color=self._colors["cross"],
        highlight_color=self._colors["highlight"],
        checked_color=CHECKED_COLOR,
        checked_indices=self._checked_layer_indices(),
        show_frame=self._show_frame,
    )
    self._scene.addItem(self._overlay)
    self._restore_highlight()
```
   - Gọi `self._rebuild_marker_overlay()` thay cho block cũ trong `_apply_style` (giữ nhánh elif remove).
2. Sửa `refresh_records`: bỏ `_scene_key = None` và `_redraw()`; chỉ gọi `self._rebuild_marker_overlay()` sau `_apply_layer()`:
```python
self._apply_layer()
if getattr(self, "_loaded", False):
    self._rebuild_marker_overlay()
```
→ Giữ nguyên hình Gerber đã render, chỉ thay lớp marker → tức thì.

## Test cập nhật
- `tests/test_main_window_delete.py`: nâng fixture `mb` hỗ trợ instance-style (`__init__/setText/setWindowFlag/exec`), thêm test assert dialog có cờ StaysOnTop; cần import `Qt`.
- `tests/test_gerber_component_check.py`: thêm test identity — `_redraw()` trước, chụp item `_line_items["outline"]`, gọi `refresh_records`, khẳng định item GIỐNG NGUYÊN (chứng minh không rebuild scene).

## Kiểm chứng
- `python -m pytest tests/test_main_window_delete.py tests/test_gerber_component_check.py -q`
- Full suite kỳ vọng ~328 passed.
- Thủ công: mở Component Info → Delete → dialog hiện TRÊN popup → Yes → xóa nhanh, không đơ.

## Trạng thái
- [x] Chẩn đoán + user xác nhận triệu chứng & phương án
- [ ] Áp dụng edit (BỊ CHẶN bởi Plan mode — cần chuyển sang Build)
