# Fix: Live preview của Edit Rotation dùng scene Gerber View (zoom detail)

## Vấn đề
Preview custom (QPainter vẽ lại flashes) SAI vì:
1. Bỏ qua display transform của board (combo_rot / mirror / flip / off_x/off_y).
2. Shape vẽ đơn giản hóa (rect theo bbox) ≠ aperture thật.
3. Tâm căn theo cách riêng → lệch vị trí thực.

Panel Details (magnifier) CHÍNH XÁC vì share trực tiếp `self._scene` đã render đầy đủ (`ui/gerber_viewer.py:1078`), transform qua `setTransform` + `centerOn(x,-y)` (`_refresh_magnifier` :1786-1791).

## Giải pháp: preview share scene + marker tạm

### Sửa `ui/rotation_edit_dialog.py`
1. **Bỏ hẳn** `RotationPreviewWidget`, `_flash_bbox_size`, các hằng PAD_FILL/PAD_EDGE/PREVIEW_BG.
2. Preview mới = `QGraphicsView` cấu hình giống magnifier: NoFrame, Antialiasing, background `BACKGROUND`(#0B1220 truyền qua param màu), non-interactive, NoDrag, NoAnchor, scrollbar AlwaysOff, min size ~(380×280).
3. Ctor mới:
```python
RotationEditDialog(record, scene, center, half, view_scale,
                   colors, arrow_min_px, marker_cls, parent=None)
# center = (x, -y) tọa độ SCENE (y đã flip như magnifier)
# colors = {"cross": QColor, "highlight": QColor, "checked": QColor}
# marker_cls = MarkerOverlayItem (inject để tránh circular import)
```
4. Marker tạm của riêng dialog:
```python
self._marker_item = marker_cls(
    [(center.x(), center.y(), rot_ban_dau, half)],
    show_unselected=True,
    arrow_min_px=arrow_min_px,
    cross_color=colors["cross"],
    highlight_color=colors["highlight"],
    checked_color=colors["checked"],
    checked_indices=set(),
    show_frame=True,
)
scene.addItem(self._marker_item)
view.setTransform(QTransform().fromScale(view_scale, view_scale))
view.centerOn(center.x(), center.y())
```
→ Hiển thị pads/silk/outline GIỐNG HỆT board (kể cả display transform), crosshair+arrow cùng hình học MarkerOverlayItem.
5. **Live update**: mọi thay đổi rotation (knob/spin/radio) gọi:
```python
self._marker_item.set_markers([(x, -y, new_rot, half)])
```
(`MarkerOverlayItem.set_markers` có sẵn :489 — chỉ repaint item này, mượt).
6. **Dọn dẹp**: override `done(self, r)`: `try: scene.removeItem(self._marker_item) except RuntimeError: pass` rồi `super().done(r)` — phủ cả OK lẫn Cancel/close. Guard scene None.
7. Bỏ param `flashes` khỏi ctor.

### Sửa `ui/gerber_viewer.py` — `_edit_rotation_for_row`
```python
x, y, cur = _record_coord(record)
size = self._pad_grid(is_top).nearest(x, y)
half = _crosshair_half(size, self._cross_half) * self._crosshair_scale
scale = _magnifier_scale(self._board_size(), 380, 300, self._mag_factor)
dlg = RotationEditDialog(
    record,
    scene=self._scene,
    center=(x, -y),
    half=half,
    view_scale=scale,
    colors={"cross": self._colors["cross"],
            "highlight": self._colors["highlight"],
            "checked": CHECKED_COLOR},
    arrow_min_px=self._arrow_min_px,
    marker_cls=MarkerOverlayItem,
    parent=self,
)
```
- Zoom = đúng công thức magifier với mag_factor ĐANG chọn ở Details → preview trông y hệt panel Details.
- Phần sau giữ nguyên (status Edited, cell Rot, `_rebuild_marker_overlay`, emit `rotation_edited`).

## Tests — cập nhật `tests/test_rotation_edit_dialog.py`
- Giữ nguyên nhóm mapping/knob/radio/±1° (logic không đổi).
- Bỏ 2 test paint-smoke cũ của RotationPreviewWidget.
- Thêm (dùng QGraphicsScene thật + MarkerOverlayItem thật):
  - Sau init: scene có thêm đúng 1 item marker tạm; `view.scene() is scene`.
  - `_on_knob_angle(135)` → `marker_item._markers[0][2] == 135`.
  - IC mode đổi radio → marker cập nhật theo giá trị quy đổi.
  - `d.done(QDialog.Rejected)` → item bị remove khỏi scene (đếm items về như cũ); gọi lần nữa không lỗi.
  - scene=None không crash (guard).

## Trạng thái
- [x] Chẩn đoán nguyên nhân sai (thiếu transform + shape giả) — khớp feedback user
- [ ] Chuyển Build: sửa dialog (share scene + marker tạm + cleanup) → sửa call site viewer → cập nhật tests → full suite (~346)
