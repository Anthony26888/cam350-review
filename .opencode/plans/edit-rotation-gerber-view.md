# Feature: Edit Rotation trong Gerber View (chuột phải component table)

## Yêu cầu user xác nhận
- Double-click component (đã có sẵn: highlight + magnifier zoom tới vị trí) → **chuột phải** dòng trong component table → menu → **"Edit Rotation"**.
- Dialog gồm: ô nhập rotation + **NÚM XOAY LỚN custom để xoay ước lượng bằng chuột** (xem thực tế qua preview); tinh chỉnh từng góc một qua ô số + nút −1°/+1°; bên dưới là **preview zoom** pad Gerber với crosshair + arrow, **cập nhật live** mọi thay đổi.
- Bấm OK → tự lưu DB, status "Edited". Không cần Undo.
- **Núm xoay 2 chế độ**:
  - **Thường**: góc = vị trí núm.
  - **IC**: chỉ KẾT QUẢ góc đổi, núm vẫn vậy → **góc = (núm − 45) mod 360** (núm 0→315, 45→0 … 315→270).
  - Chuyển chế độ giữa chừng: **giữ núm, góc/spinbox/preview nhảy theo**.
  - Mỗi lần mở dialog luôn mặc định chế độ **Thường**.

## File mới: `ui/rotation_edit_dialog.py`

### RotaryKnob(QWidget) — núm xoay lớn custom, KHÔNG dùng QDial
- Kích thước lớn: minimum 170×170px, stretch được (~180px thực tế).
- **Paint (khớp dark theme `ui/style.py`)**:
  - Vành tick: tick nhỏ mỗi 10°, tick lớn mỗi 45° màu #94A3B8; nhãn 0°/90°/180°/270° màu #E2E8F0 cỡ nhỏ ở vành ngoài.
  - Thân núm tròn: QRadialGradient #1E293B→#0F172A, viền #334155, hơi 3D.
  - Chỉ báo: thanh tròn màu ACCENT #0D9488 từ gần tâm ra mép theo góc núm hiện tại (luôn là vị trí NÚM, không phụ thuộc quy đổi IC).
  - Halo nhẹ quanh chỉ báo khi đang kéo (hover/drag state).
- **Tương tác chuột — xoay ước lượng tự do**:
  - `mousePressEvent`/`mouseMoveEvent` (trái): tính góc từ tâm bằng atan2 → gọi callback liên tục → spinbox/preview cập nhật REALTIME trong lúc kéo (đây là chức năng "ước lượng + xem thực tế").
  - Giữ **Ctrl khi kéo** = snap 15° (tiện đặt nhanh góc IC).
  - `wheelEvent`: mỗi notch lăn = ±1° (fine tune nhanh tay không cần rời chuột).
- Widget phát signal `angleChanged(float)` (góc núm 0..360); dialog tự map sang góc rotation theo chế độ.

### RotationPreviewWidget(QWidget)
- Ctor: `flashes` (paste RenderData.flashes layer hiện tại), `center=(x,y)` mm, rotation ban đầu.
- `set_rotation(v)`: lưu + `self.update()` (live repaint).
- `paintEvent`: auto-fit `half = max(2.5 * size_pad_chính, 0.8mm)`; vẽ pads (rect/ellipse/polygon đơn giản hóa), crosshair 2 nét qua tâm, mũi tên — **sao chép hình học MarkerOverlayItem.paint**: `tip = half + alen`, polygon `[(-tip,0), (-half,-wing), (-half,wing)]`, `rotate(-rot)`.

### RotationEditDialog(QDialog, modal)
- Spinbox rotation: range ±999999, decimals 1, singleStep 1 — LUÔN hiển thị góc thật (kết quả).
- Nút `−1°` / `+1°`: `spin.stepDown()/stepUp()` — nơi tinh chỉnh từng góc một.
- **Chế độ**: 2 QRadioButton — `tr("Normal")` / `tr("IC")`, mặc định Normal mỗi lần mở.
- Quy đổi trung tâm:
```python
def _rotation_from_knob(self, k: float) -> float:
    return float((int(round(k)) - 45) % 360) if self._ic_mode else round(k, 1) % 360

def _knob_from_rotation(self, rotation: float) -> float:
    base = int(round(rotation)) % 360
    return float((base + 45) % 360) if self._ic_mode else float(base)
```
- Đồng bộ có cờ `_syncing` chống đệ quy:
  - `knob.angleChanged` → `spin.setValue(_rotation_from_knob(k))` + preview update (kéo núm = realtime ước lượng).
  - `spin.valueChanged` → `knob.set_angle(_knob_from_rotation(v))` + preview update.
  - Radio toggled → KHÔNG đụng núm: `spin.setValue(_rotation_from_knob(knob.angle()))` + preview (giữ núm, đổi góc).
- Preview bên dưới (min height ~260).
- OK/Cancel; dialog KHÔNG mutate record; property `new_rotation`.
- Title: `tr("Edit Rotation - {des}")`.

## Sửa `ui/gerber_viewer.py`
1. Signal cạnh `checked_changed` (:761): `rotation_edited = Signal(int)`.
2. Setup bảng (~:1019): `setContextMenuPolicy(Qt.CustomContextMenu)` + connect `_on_component_menu`.
3. Method mới gần `_on_component_double_clicked` (:1809):
   - `_on_component_menu(pos)`: bỏ qua group-by-MPN; selectRow trước (highlight+magnifier chạy); QMenu action `tr("Edit Rotation")` → `_edit_rotation_for_row(row)`.
   - `_edit_rotation_for_row(row)`: mở `RotationEditDialog(record, paste.flashes, self)`; OK & khác cũ → `record.new_rotation=val`, `status="Edited"`, `review_time`, cập nhật cell Rot (`{val:.0f}°`), `self._rebuild_marker_overlay()`, emit `rotation_edited(idx toàn cục)`. Magnifier chung scene → arrow Details quay live.

## Sửa `ui/main_window.py`
- `_open_gerber_check` (:1532): `viewer.rotation_edited.connect(self._on_gerber_rotation_edited)`.
- Handler cạnh `_on_gerber_component_checked` (:1545): repo.update + update_record_row + _update_progress + status "{des}: Edited".

## i18n (`ui/i18n.py`) — key thiếu kèm VN
- "Edit Rotation"/"Sửa góc xoay"; "Edit Rotation - {des}"/"Sửa góc xoay - {des}"; "Rotation"/"Góc xoay"; "Knob Mode"/"Chế độ núm xoay"? (có thể bỏ group label); "Normal"/"Thường"; "IC"/"IC".

## Tests (offscreen, kỳ vọng suite ~343 passed)
1. `tests/test_rotation_edit_dialog.py` (mới):
   - Fake flashes SimpleNamespace(cx,cy,w,h,kind="rect",pts=None,macro=None).
   - Mapping Thường: knob 90→spin 90. IC: knob 45→spin 0; 0→315; 270→225; 315→270.
   - Đổi radio: knob giữ nguyên, spin/preview đổi theo.
   - Gõ spin 135 (IC) → knob=180; (Thường) → knob=135.
   - Knob: gọi handler pointer angle trực tiếp → spin/preview cập nhật; Ctrl-snap về bội 15°; wheel ±1°.
   - Nút ±1° đúng 1°; property new_rotation; dialog không mutate record; mở lại luôn Normal; preview + knob paint không crash.
2. `tests/test_gerber_component_check.py`: fake dialog Accepted 90 → `_edit_rotation_for_row(0)`: record mới, status Edited, signal index đúng, marker quay 90, cell Rot mới; guard group-mode.
3. Holder-style `_on_gerber_rotation_edited` trong `tests/test_main_window_delete.py`.

## Trạng thái
- [x] Khảo sát code + chốt: lưu DB ngay / không Undo / quy ước IC / núm to custom xoay ước lượng
- [ ] Chuyển Build: dialog mới (RotaryKnob + preview + 2 chế độ) → viewer → main_window → i18n → tests → full suite
