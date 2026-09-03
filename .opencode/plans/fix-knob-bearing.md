# Fix 2: Thanh gạt núm xoay vẫn lệch 90° — thống nhất hệ la bàn (bearing)

## Lỗi user báo
Góc 180° thanh gạt đang chỉ LÊN (mong muốn: PHẢI). Nguyên nhân: lần sửa trước trộn 2 hệ góc —
paint của RotaryKnob dùng bearing la bàn (0=lên: x=cx+r·sinθ, y=cy−r·cosθ) nhưng mapping/pointer
dùng cw-từ-Đông (atan2(dy,dx)) → mọi vị trí lệch 90°.

## Quy ước chuẩn duy nhất: BEARING (0°=lên, tăng theo kim đồng hồ)
Arrow/mũi tên (giữ nguyên từ board): góc 0=TRÁI(bearing 270), 90=DƯỚI(180), 180=PHẢI(90), 270=TRÊN(0)
⇒ bearing = (270 − góc) mod 360 ; góc = (270 − bearing) mod 360
IC: góc_IC = góc_thường − 45 ⇒ góc_IC = (225 − bearing) mod 360 ; bearing = (225 − góc_IC) mod 360

## Sửa `ui/rotation_edit_dialog.py`
1. `RotaryKnob._apply_pointer`: 
   `ang = math.degrees(math.atan2(dx, -dy)) % 360.0` (thay atan2(dy,dx)); Ctrl-snap giữ nguyên trên bearing.
2. `_rotation_from_knob(k)`: thường `(270 - int(round(k))) % 360`; ic `(225 - int(round(k))) % 360`
3. `_knob_from_rotation(r)`: thường `(270 - base) % 360`; ic `(225 - base) % 360`
4. `paintEvent` vòng tick/nhãn: `rad = math.radians((270 - deg) % 360)`
   → nhãn 0 TRÁI / 90 DƯỚI / 180 PHẢI / 270 TRÊN.

## Ma trận kiểm chứng
| Góc | Thanh gạt | Nhãn |
|-----|-----------|-------|
| 0   | Trái      | 0 trái |
| 90  | Dưới      | 90 dưới |
| 180 | Phải      | 180 phải |
| 270 | Trên      | 270 trên |
Kéo chuột: trái→0, xuống→90, phải→180, lên→270.

## Tests cập nhật `tests/test_rotation_edit_dialog.py`
- NORMAL_TABLE: (k→góc) 0→270, 45→225, 90→180, 135→135, 180→90, 225→45, 270→0, 315→315
- IC_TABLE: 0→225, 45→180, 90→135, 135→90, 180→45, 225→0, 270→315, 315→270
- test_indicator_sides_match_arrow_convention: [(270,0),(180,90),(90,180),(0,270)]
- test_initial_values_from_record: knob == 180.0 (rot 90)
- test_switch_mode_keeps_knob_changes_value: giữ nguyên (vẫn 45/90)
- test_spin_input_repositions_knob: IC spin135→knob 90; thường spin100→knob 170
- test_scene_none_still_works: knob 120 → spin 150
- test_knob_pointer_angle_mapping: Đông→90; Nam→180; Ctrl điểm 20°-từ-Đông (bearing 110) → snap 105
- Còn lại giữ nguyên. Suite kỳ vọng ~352 passed.

## Trạng thái
- [x] Chẩn đoán gốc rễ (2 hệ góc trộn nhau)
- [ ] Chuyển Build: sửa pointer + 2 mapping + ring offset → cập nhật tests → full suite
