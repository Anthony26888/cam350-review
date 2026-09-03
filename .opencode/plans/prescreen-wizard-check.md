# Plan: Pre-screen Check — Bước 6/7 của Origin Align Wizard

## Nguyên tắc (đã chốt với user)
- Điểm vào DUY NHẤT: Step 6/7 trong Origin Align Wizard. Không nút toolbar, không menu.
- Cột Flags mặc định TRỐNG; chỉ có dữ liệu sau khi bấm Run Check ở bước này.
- Trang kết quả trong wizard CHỈ hiện số tổng từng hạng mục + legend chú thích viết tắt.
- Chi tiết vị trí lỗi: cột Flags (bảng chính) + khung cam nét đứt (viewer).
- Dismiss: chuột phải dòng có flag trên bảng chính → "Bỏ qua cảnh báo", persisted.

## 1. services/prescreen.py (mới, thuần Python không Qt)
- PrescreenIssue(kind, index, designator, x, y, detail)
- dismiss_key = f"{kind}:{designator}:{x:.3f}:{y:.3f}"
- run_prescreen(records, paste_top=None, paste_bottom=None, outline_bbox=None,
               cfg=PrescreenConfig(), dismissed=frozenset()) -> List[PrescreenIssue]
  - DUP: trùng ≤ dup_tol (0.05mm), grid-bucket O(n), flag bản ghi sau
  - ROT: nhóm MPN ≥ rot_min_group(2), lệch vòng-tròn > rot_dev(45°) so đa số
  - OUT: ngoài outline_bbox giãn out_margin(1mm); bỏ qua nếu None
  - PAD: > pad_tol(0.3mm) tới paste gần nhất; top↔paste_top, bottom↔paste_bottom
  - Tọa độ hiệu dụng new_x ?? old_x; rotation %360; lọc dismissed trước khi trả

## 2. Model / Session / Config (additive)
- ReviewRecord.prescreen_flags: List[str] transient (không serialize)
- SessionData.prescreen_dismissed: List[str]; VERSION giữ 5
- models/config.py: PrescreenConfig(enabled, rot_dev, rot_min_group, dup_tol,
  pad_tol, out_margin) + wire ConfigManager defaults

## 3. ui/table_widget.py
- _COLUMNS chèn "Flags" sau "Rotation"; dồn _STATUS/CHECK/REMARK_COLUMN → 9/10/11
- Cell Flags: text "ROT·PAD", màu #F59E0B, tooltip mô tả loại, non-editable
- update_all_rows(); context menu chuột phải dòng có flag → signal flag_dismiss_requested(int)

## 4. ui/gerber_viewer.py
- MarkerOverlayItem: params flagged_indices=set(), flag_color="#F59E0B";
  set_flagged_indices(); paint() vẽ rect nét đứt cosmetic quanh marker bị flag
- GerberViewer.set_flagged_indices(indices) -> _rebuild_marker_overlay() truyền qua

## 5. ui/origin_align_wizard.py — Step 6/7
- Tiêu đề các bước đổi "/6" → "/7"; chèn _step_prescreen giữa macro và result
- UI: nút [▶ Run Check] + progress + khối tổng ROT/PAD/DUP/OUT/Tổng +
  LEGEND luôn hiển thị (ngưỡng động từ config) + gợi ý xem chi tiết ở cột Flags/viewer
- PrescreenWorker(QThread): parse GKO-bbox + parse_flashes(gtp/gbp) → run_prescreen
- Next luôn bật ở bước này (được phép bỏ qua); get_prescreen_result() -> Optional[list]

## 6. ui/main_window.py
- Sau wizard accepted: đọc kết quả; khác None → clear flags cũ toàn records,
  ghi kinds mới, update_all_rows(), status bar tổng, viewer.set_flagged_indices()
- Dismiss handler: thêm key vào _prescreen_dismissed, xóa flag dòng, lưu session
- Load session nạp dismissed; mọi SessionService.save truyền prescreen_dismissed

## 7. export_service.py + i18n
- Sheet tổng hợp thêm cột "Pre-screen Flags"
- i18n VN/EN: Run Check, Chú thích/Legend, các mô tả ROT/PAD/DUP/OUT,
  "Bỏ qua cảnh báo", summary "⚠ Pre-screen: ..."

## 8. Tests ~13 → mục tiêu ≈ 364 passed
- test_prescreen_service.py (~7): từng check pass/fail/biên/dismiss/skip-thiếu-dữ-liệu
- session round-trip prescreen_dismissed (+1)
- table_widget (+2): flags cell + hằng cột mới + signal dismiss
- main_window (+2): áp kết quả wizard + dismiss handler
- wizard (+1): bước 6 build + tổng cập nhật từ fake issues
