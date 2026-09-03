# Polish: Núm xoay hiện đại (arc ring + số tại tâm) + cửa sổ lớn hơn + bỏ nút ±1°

## Yêu cầu user chốt
1. Phong cách núm: **Arc ring + số độ tại tâm** (kiểu Nest/volume hiện đại), tick mảnh tinh gọn, dễ nhìn, TO hơn (min 150px).
2. Cửa sổ Edit Rotation: **~500×580px** (trước 360×430).
3. **Loại bỏ nút −1°/+1°** (tinh chỉnh từng độ vẫn qua spinbox bước 1 + lăn chuột trên núm).

## A. RotaryKnob redesign (`ui/rotation_edit_dialog.py`)
Giữ NGUYÊN ngữ nghĩa góc bearing + signal `angleChanged` (không đụng mapping/tests logic).

1. Kích thước: `setMinimumSize(116,116)` → **`setMinimumSize(150,150)`**.
2. Thêm state: `self._center_text = ""`, `self._hovered = False`; methods:
```python
def set_center_text(self, text: str) -> None:
    if text != self._center_text:
        self._center_text = text
        self.update()

def center_text(self) -> str:
    return self._center_text

def enterEvent(self, ev): self._hovered = True; self.update()
def leaveEvent(self, ev): self._hovered = False; self.update()
```
3. Thứ tự vẽ mới trong `paintEvent`:
   - Bóng mềm: ellipse rgba(0,0,0,110) lệch (0,+3).
   - **Track ring**: vòng tròn mờ rgba(148,163,184,45), pen rộng ~10px, round cap, bán kính `ring_r = outer - 12`.
   - **Progress arc**: quét TỪ bearing 0 THEO CHIỀU KIM ĐỒNG HỒ đến bearing hiện tại (drawArc rect(±ring_r), startAngle = 90*16, spanAngle = `-int(round(self._angle)) * 16`); màu ACCENT #0D9488, pen 10px round cap; khi `_dragging` vẽ thêm lớp glow cùng arc alpha 60 rộng 16px.
   - Tick: minor mỗi 10° alpha thấp 1px; major mỗi 45° dài+sáng 2px (vị trí bearing `(270-deg)%360` như hiện tại); nhãn 0/90/180/270 giữ nguyên vị trí, font 8pt màu #94A3B8.
   - Thân: radial gradient #2B3A52→#10192A, viền #475569 (hover: #64748B).
   - **Số tại tâm**: `_center_text` font "Segoe UI" 13pt bold màu #E2E8F0, căn giữa tâm.
   - Chỉ báo: thanh tròn 6px ACCENT nhạt #14B8A6 từ r*0.35 tới mép thân theo bearing `_angle` + chấm đầu 5px #CCFBF1; halo khi kéo giữ nguyên.

## B. Dialog (`ui/rotation_edit_dialog.py`)
1. **Xóa block `_btn_minus/_btn_plus`** (tạo nút + btn_row + addLayout) khỏi `_build_ui`; side column còn: label Rotation + spinbox + stretch.
2. Đồng bộ số tâm qua điểm tập trung duy nhất — mở rộng `_update_preview_marker`:
```python
def _update_preview_marker(self, rotation: float) -> None:
    if self._marker_item is not None:
        self._marker_item.set_markers([(self._cx, self._cy, float(rotation), self._half)])
    self._knob.set_center_text(f"{int(round(float(rotation))) % 360}°")
```
   (init/knob/spin/radio đều đi qua đây sẵn)
3. Kích thước: `self.resize(360, 430)` → **`self.resize(500, 580)`**. Preview min giữ 290×180.

## C. Tests (`tests/test_rotation_edit_dialog.py`)
1. XÓA `test_step_buttons_change_exactly_one_degree`.
2. SỬA `test_compact_minimum_sizes` → đổi tên `test_minimum_sizes`: knob min width == 150; preview 290×180.
3. THÊM:
```python
def test_center_text_follows_rotation(app):
    d = _dialog(rot=90.0)          # knob bearing 180
    assert d._knob.center_text() == "90°"
    d._radio_ic.setChecked(True)   # IC: 45°
    assert d._knob.center_text() == "45°"
    d.done(QDialog.Rejected)
```
4. Các test khác giữ nguyên (mapping bearing, marker scene, cleanup, pointer, centered_after_show, minimum preview).

## Kiểm chứng
- `python -m pytest tests/test_rotation_edit_dialog.py -q` (~19 test) → full suite kỳ vọng **351 passed**.
- Thủ công: dialog mở ~500×580 thoáng; núm 150px có vòng cung teal quét theo góc + số độ giữa núm; không còn nút ±1°; kéo/lăn/Ctrl-snap hoạt động như cũ; preview vẫn centered đúng component.

## Trạng thái
- [x] User chốt phong cách Arc-ring + tâm số, cỡ 500×580, bỏ ±1°
- [ ] Chuyển Build: sửa RotaryKnob paint + xóa nút + resize + tests → full suite
