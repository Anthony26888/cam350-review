# Fix: Edit Rotation — sửa lệch tâm preview + thu gọn cửa sổ (Compact)

## Gộp 2 yêu cầu user
1. **Lệch tâm preview** (đã chẩn đoán): `centerOn` chỉ gọi lúc build UI khi viewport chưa có size thật.
2. **Thu gọn cửa sổ** mức Compact: ~360×430px, núm 116px, preview 290×180 (user chọn Compact + gộp cả 2 sửa).

## Phần 1 — Sửa lệch tâm (`ui/rotation_edit_dialog.py`)
Thêm re-center sau khi layout có kích thước thật (cơ chế tương tự `_refresh_magnifier`):
```python
def _recenter_preview(self) -> None:
    if self._scene is not None and self._marker_item is not None:
        self._preview.centerOn(self._cx, self._cy)

def showEvent(self, ev):
    super().showEvent(ev)
    self._recenter_preview()

def resizeEvent(self, ev):
    super().resizeEvent(ev)
    self._recenter_preview()
```
Giữ nguyên `centerOn` ban đầu trong `_build_ui`.

## Phần 2 — Thu gọn Compact (`ui/rotation_edit_dialog.py`)
1. `RotaryKnob.__init__`: `setMinimumSize(170, 170)` → **`setMinimumSize(116, 116)`** (vẫn kéo to hơn được).
2. `_build_ui`: preview `setMinimumSize(380, 280)` → **`setMinimumSize(290, 180)`**.
3. `_build_ui` đầu hàm:
```python
layout.setContentsMargins(12, 12, 12, 12)
layout.setSpacing(8)
```
4. Cuối `__init__` (sau khi set giá trị khởi tạo): `self.resize(360, 430)` — kích thước mở đầu gọn; vẫn resize/maximize tự do (recenter chạy theo resizeEvent nên marker luôn giữa).

## Tests — cập nhật `tests/test_rotation_edit_dialog.py`
1. Test mới regression lệch tâm:
```python
def test_preview_centered_after_show(app):
    d = _dialog(rot=45.0)
    d.resize(360, 430)
    d.show()
    QApplication.processEvents()
    vp = d._preview.viewport()
    c = d._preview.mapToScene(vp.rect().center())
    assert abs(c.x() - 10.0) < 0.05
    assert abs(c.y() - (-20.0)) < 0.05
    d.done(QDialog.Rejected)
```
2. Test mới compact minimums:
```python
def test_compact_minimum_sizes(app):
    d = _dialog()
    assert d._knob.minimumSize().width() == 116
    assert d._preview.minimumSize().width() == 290
    assert d._preview.minimumSize().height() == 180
    d.done(QDialog.Rejected)
```
3. Các test cũ giữ nguyên (mapping/knob/cleanup không đổi logic).

## Kiểm chứng
- `python -m pytest tests/test_rotation_edit_dialog.py -q` (~21 test)
- Full suite kỳ vọng ~350 passed.
- Thủ công: mở Edit Rotation → cửa sổ nhỏ gọn ~360×430; marker nằm ĐÚNG GIỮA preview; kéo resize vẫn giữa; núm xoay vẫn đủ lớn để kéo ước lượng.

## Trạng thái
- [x] Chốt phương án với user (Compact + gộp 2 sửa)
- [ ] Chuyển Build: edit dialog (recenter + compact) → tests → full suite
