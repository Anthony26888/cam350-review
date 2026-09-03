# Fix: Đồng bộ núm xoay với quy ước góc 0°=trái / 90°=dưới / 180°=phải / 270°=trên

## Yêu cầu user chốt
- GIỮ nguyên quy ước mũi tên hiện có: 0°=TRÁI, 90°=DƯỚI, 180°=PHẢI, 270°=TRÊN (board thật hiển thị đúng — không đụng vào).
- Chỉ sửa TRONG dialog Edit Rotation: núm xoay (chỉ báo khi kéo + nhãn số quanh vành) phải khớp quy ước này.

## Sai lệch hiện tại (đã đối chiếu code `ui/rotation_edit_dialog.py`)
- Chỉ báo núm đặt tại góc thô k (cw-từ-Đông): góc 0 → chỉ báo bên PHẢI (mũi tên lại bên TRÁI); góc 180 → trái (mũi tên phải). Lệch 180° tại 0/180.
- Nhãn số vẽ bằng công thức sin/cos khiến "0" ở TRÊN, "90" phải, "180" dưới, "270" trái — lệch cả hệ quy chiếu.

## Công thức mới
θ_núm = (180 − góc) mod 360 ; góc = (180 − θ_núm) mod 360 (θ cw từ Đông).
IC: góc_IC = góc_thường − 45 → góc_IC = (135 − θ) mod 360 ; θ = (135 − góc_IC) mod 360.

## Sửa `ui/rotation_edit_dialog.py`
1. `_rotation_from_knob(k)`:
```python
if self._ic_mode:
    return float((135 - int(round(k))) % 360)
return float((180 - int(round(k))) % 360)
```
2. `_knob_from_rotation(r)`:
```python
base = int(round(rotation)) % 360
if self._ic_mode:
    return float((135 - base) % 360)
return float((180 - base) % 360)
```
3. `RotaryKnob.paintEvent`: vòng tick + nhãn vẽ tại vị trí `ang = math.radians(180 - deg)` thay vì `math.radians(deg)` (logic major/nhãn 0/90/180/270 giữ theo deg) → "0" trái, "90" dưới, "180" phải, "270" trên.
4. Không đổi: preview scene, marker, board chính, quan hệ IC −45°.

## Tests cập nhật `tests/test_rotation_edit_dialog.py`
- `test_normal_mapping_identity` → bảng: k→góc = 0→180, 45→135, 90→90, 135→45, 180→0, 225→315, 270→270, 315→225 (marker rot theo spin).
- `test_ic_mapping_table` → bảng: 0→135, 45→90, 90→45, 135→0, 180→315, 225→270, 270→225, 315→180.
- `test_spin_input_repositions_knob`: IC spin 135 → knob 0; thường spin 100 → knob 80.
- Giữ nguyên: default-normal, temp-marker, share-scene, done-cleanup, scene-none, ±1°, không mutate record, luôn mở Normal, pointer mapping, knob paint smoke, centered_after_show, compact_minimums.
- Suite kỳ vọng ~350 passed.

## Kiểm chứng thủ công
Mở dialog ở component 0° → chỉ báo núm + nhãn "0" nằm BÊN TRÁI đúng như mũi tên preview; kéo núm lên TRÊN đọc 270°… mọi vị trí khớp 1:1 chiều mũi tên.

## Trạng thái
- [x] User chốt quy ước + phạm vi (chỉ dialog)
- [ ] Chuyển Build: edit dialog mapping + paint ring → cập nhật tests → full suite
