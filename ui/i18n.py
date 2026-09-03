"""Lightweight EN/VN internationalization for the core review workflow.

English strings are used as keys so that the default (untouched) behavior
stays identical. Vietnamese is provided as a translation. Unknown keys fall
back to the English text.
"""

from typing import Any, Dict

_LANGUAGE = "en"

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {},
    "vi": {
        # Menus
        "&File": "&Tập tin",
        "New Session": "Phiên mới",
        "Open Session...": "Mở phiên...",
        "Save Session": "Lưu phiên",
        "Save Session As...": "Lưu phiên thành...",
        "Open PickPlace Excel...": "Mở file PickPlace Excel...",
        "Open PickPlace with Mapping...": "Mở PickPlace với ánh xạ cột...",
        "&Export": "&Xuất",
        "Export Review Report": "Xuất báo cáo review",
        "Export PickPlace Fixed": "Xuất PickPlace đã sửa",
        "Exit": "Thoát",
        "&Edit": "&Sửa",
        "Undo": "Hoàn tác",
        "Redo": "Làm lại",
        "&Tools": "&Công cụ",
        "Align PickPlace Origin...": "Canh gốc PickPlace...",
        "Gerber View...": "Xem Gerber...",
        "PCB Info...": "Thông tin PCB...",
        "Calibration Wizard": "Hướng dẫn hiệu chuẩn",
        "Settings": "Cài đặt",
        "&Help": "&Trợ giúp",
        "About": "Giới thiệu",
        # Toolbar tooltips
        "New Session (Ctrl+N)": "Phiên mới (Ctrl+N)",
        "Open Session (Ctrl+O)": "Mở phiên (Ctrl+O)",
        "Save Session (Ctrl+S)": "Lưu phiên (Ctrl+S)",
        "Open PickPlace Excel": "Mở file PickPlace Excel",
        "Align PickPlace Origin": "Canh gốc PickPlace",
        "Gerber View": "Xem Gerber",
        "Export Review Report": "Xuất báo cáo review",
        "Export PickPlace Fixed": "Xuất PickPlace đã sửa",
        "Batch Edit": "Sửa hàng loạt",
        "PCB Info": "Thông tin PCB",
        "OK Checked": "Đánh OK các dòng đã chọn",
        "Delete Selected": "Xóa các dòng đã chọn",
        "Settings": "Cài đặt",
        # Stats
        "Total: {0}": "Tổng: {0}",
        "OK: {0}": "OK: {0}",
        "Edit: {0}": "Sửa: {0}",
        "Pending: {0}": "Chờ: {0}",
        "Aligned: {0}": "Đã canh: {0}",
        # Status bar
        "Ready": "Sẵn sàng",
        "No session to restore. Open a PickPlace file or load a session.":
            "Không có phiên để khôi phục. Mở file PickPlace hoặc nạp một phiên.",
        "New session created": "Đã tạo phiên mới",
        "Loaded session: {name}": "Đã nạp phiên: {name}",
        "Session saved: {name}": "Đã lưu phiên: {name}",
        "Loaded {count} components from {name}": "Đã nạp {count} linh kiện từ {name}",
        "Jumped to {des}: ({x}, {y})": "Đã nhảy tới {des}: ({x}, {y})",
        "Jump cancelled (mouse moved to corner)": "Hủy nhảy (chuột đã ra góc màn hình)",
        "{des}: OK": "{des}: OK",
        "{des}: Edited": "{des}: Đã sửa",
        "Deleted {des}": "Đã xóa {des}",
        "Exporting...": "Đang xuất...",
        "Export complete": "Xuất hoàn tất",
        "Export failed": "Xuất thất bại",
        "Searching datasheet for {mpn}...": "Đang tìm datasheet cho {mpn}...",
        "Datasheet found for {mpn}": "Đã tìm thấy datasheet cho {mpn}",
        "No datasheet found for {mpn}": "Không tìm thấy datasheet cho {mpn}",
        "Datasheet search error: {message}": "Lỗi tìm datasheet: {message}",
        "Batch edited {n} records": "Đã sửa hàng loạt {n} dòng",
        "Marked OK: {n} records": "Đã đánh OK: {n} dòng",
        "All records deleted": "Đã xóa toàn bộ dòng",
        "Deleted {n} records": "Đã xóa {n} dòng",
        "Undo: restored previous state": "Hoàn tác: đã khôi phục trạng thái trước",
        "Redo: restored next state": "Làm lại: đã khôi phục trạng thái kế tiếp",
        # Common dialog titles
        "Warning": "Cảnh báo",
        "Error": "Lỗi",
        "Success": "Thành công",
        "Export Error": "Lỗi xuất",
        "CAM350 Error": "Lỗi CAM350",
        "No data to export.": "Không có dữ liệu để xuất.",
        "No data to export. Load a file first.": "Không có dữ liệu để xuất. Hãy nạp file trước.",
        "Session file is empty.": "File phiên trống.",
        "No data to save.": "Không có dữ liệu để lưu.",
        "Failed to load session: {e}": "Không nạp được phiên: {e}",
        "File exported:\n{path}": "Đã xuất file:\n{path}",
        "No records selected.": "Chưa chọn dòng nào.",
        "No records selected. Check records in the table first.":
            "Chưa chọn dòng nào. Hãy chọn dòng trong bảng trước.",
        "New Session": "Phiên mới",
        "Current session not saved. Discard?": "Phiên hiện tại chưa lưu. Bỏ qua?",
        "Open Session": "Mở phiên",
        "Open PickPlace File": "Mở file PickPlace",
        "Save Session As": "Lưu phiên thành",
        "Delete Record": "Xóa dòng",
        "Delete {des}?": "Xóa {des}?",
        "Delete Records": "Xóa các dòng",
        "Delete {n} selected records?": "Xóa {n} dòng đã chọn?",
        "Confirm Batch Edit": "Xác nhận sửa hàng loạt",
        "Apply the following to {n} selected records?\n\n- {list}":
            "Áp dụng các thay đổi sau cho {n} dòng đã chọn?\n\n- {list}",
        "Applying batch edit...": "Đang áp dụng sửa hàng loạt...",
        "Marking records as OK...": "Đang đánh OK các dòng...",
        "Mark OK": "Đánh OK",
        "Save Session": "Lưu phiên",
        "Save current session before closing?\nYes: save session file\nNo: discard all changes":
            "Lưu phiên trước khi đóng?\nCó: lưu file phiên\nKhông: bỏ hết thay đổi",
        # Gerber file pickers (previously mixed Vietnamese)
        "Please open a PickPlace file first.": "Vui lòng mở file PickPlace trước.",
        "No data. Open a PickPlace file or load a session first.":
            "Không có dữ liệu. Mở PickPlace hoặc session trước.",
        "Select GKO file (Outline)": "Chọn file GKO (Outline)",
        "Select GTP file (Top Paste - optional)": "Chọn file GTP (Top Paste - tùy chọn)",
        "Select GBP file (Bottom Paste - optional)": "Chọn file GBP (Bottom Paste - tùy chọn)",
        "Select GTO file (Silkscreen - optional)": "Chọn file GTO (Silkscreen - tùy chọn)",
        "Select GBO file (Bottom Silkscreen - optional)": "Chọn file GBO (Bottom Silkscreen - tùy chọn)",
        "All Files (*.*)": "Tất cả tệp (*.*)",
        # About dialog
        "About CAM350 Review Assistant": "Giới thiệu CAM350 Review Assistant",
        "Close": "Đóng",
        # Table widget
        "Search...": "Tìm kiếm...",
        "All": "Tất cả",
        "Pending": "Chờ",
        "OK": "OK",
        "Edited": "Đã sửa",
        "Aligned": "Đã canh",
        "Clear all filters": "Xóa bộ lọc",
        "No": "STT",
        "#": "#",
        "Designator": "Designator",
        "MPN": "MPN",
        "Layer": "Lớp",
        "X": "X",
        "Y": "Y",
        "Rotation": "Rotation",
        "Status": "Trạng thái",
        "Remark": "Ghi chú",
        # Review panel
        "Component Information": "Thông tin linh kiện",
        "Actions": "Thao tác",
        "Previous": "Trước",
        "Next": "Sau",
        "Jump CAM350": "Nhảy CAM350",
        "Search Datasheet": "Tìm datasheet",
        "OK (Space)": "OK (Space)",
        "Edit (Ctrl+E)": "Sửa (Ctrl+E)",
        "Designator:": "Designator:",
        "MPN:": "MPN:",
        "Layer:": "Lớp:",
        "Original X:": "X gốc:",
        "Original Y:": "Y gốc:",
        "Original Rotation:": "Rotation gốc:",
        "New X:": "X mới:",
        "New Y:": "Y mới:",
        "New Rotation:": "Rotation mới:",
        "Status:": "Trạng thái:",
        "Datasheet:": "Datasheet:",
        "Remark:": "Ghi chú:",
        "Progress:": "Tiến độ:",
        "View Datasheet": "Xem datasheet",
        "Not found": "Không tìm thấy",
        '<a href="{url}">View Datasheet</a>': '<a href="{url}">Xem datasheet</a>',
        "{reviewed}/{total} ({pct}%) - OK: {ok} | Edited: {edited}":
            "{reviewed}/{total} ({pct}%) - OK: {ok} | Đã sửa: {edited}",
        # Edit dialog
        "Edit - {des}": "Sửa - {des}",
        "Original Values": "Giá trị gốc",
        "Edit Values": "Giá trị mới",
        "Enter remark...": "Nhập ghi chú...",
        "X:": "X:",
        "Y:": "Y:",
        "Rotation:": "Rotation:",
        "Remark:": "Ghi chú:",
        # Batch edit dialog
        "Batch Edit - Offset Values": "Sửa hàng loạt - Giá trị offset",
        "Offset Values (applied to selected records)": "Giá trị offset (áp dụng cho các dòng đã chọn)",
        "Apply X offset": "Áp offset X",
        "Make new X negative": "Buộc X mới âm",
        "Apply Y offset": "Áp offset Y",
        "Make new Y negative": "Buộc Y mới âm",
        "Apply Rotation offset": "Áp offset Rotation",
        "Enter remark (applied to all selected)...": "Nhập ghi chú (áp dụng cho tất cả dòng đã chọn)...",
        "New value = current value + offset\nMake new X/Y negative flips the sign of the resulting coordinate":
            "Giá trị mới = giá trị hiện tại + offset\nBuộc X/Y mới âm sẽ đảo dấu của toạ độ kết quả",
        # Settings dialog
        "Configuration": "Cấu hình",
        "Window Title:": "Tiêu đề cửa sổ:",
        "Jump Delay:": "Độ trễ nhảy:",
        "X Textbox:": "Ô X:",
        "Y Textbox:": "Ô Y:",
        "Go Button:": "Nút Go:",
        "Rotate Button:": "Nút xoay 90°:",
        "Theme:": "Giao diện:",
        "Light": "Sáng",
        "Dark": "Tối",
        "Language:": "Ngôn ngữ:",
        "English": "Tiếng Anh",
        "Vietnamese": "Tiếng Việt",
        "Actions": "Thao tác",
        "Run Calibration Wizard": "Chạy hướng dẫn hiệu chuẩn",
        "Test CAM350 Connection": "Kiểm tra kết nối CAM350",
        "Test Jump (X=0, Y=0)": "Thử nhảy (X=0, Y=0)",
        "Reset Configuration": "Khôi phục cấu hình",
        "Save": "Lưu",
        "Cancel": "Hủy",
        "CAM350 is running and connected.": "CAM350 đang chạy và kết nối thành công.",
        "CAM350 not found. Ensure it is running.": "Không tìm thấy CAM350. Hãy đảm bảo nó đang chạy.",
        "Jump test successful.": "Thử nhảy thành công.",
        "Jump test failed. Check calibration.": "Thử nhảy thất bại. Kiểm tra hiệu chuẩn.",
        "Confirm Reset": "Xác nhận khôi phục",
        "Reset all configuration to defaults?": "Khôi phục toàn bộ cấu hình về mặc định?",
        "Configuration reset.": "Đã khôi phục cấu hình.",
        "Settings saved.": "Đã lưu cài đặt.",
        # Calibration wizard
        "Delay Settings": "Cài đặt độ trễ",
        "Jump delay:": "Độ trễ nhảy:",
        " ms": " ms",
        "Start Capture ({n}s countdown)": "Bắt đầu thu (đếm ngược {n}s)",
        "Skip": "Bỏ qua",
        "Save && Close": "Lưu && Đóng",
        "Window title:": "Tiêu đề cửa sổ:",
        "e.g. CAM350 V15": "VD: CAM350 V15",
        "Detect": "Phát hiện",
        "No positions captured yet.": "Chưa có vị trí nào được thu.",
        "Step {step} of 4: {name}": "Bước {step} trong 4: {name}",
        "Step 4 of 4: CAM350 Window": "Bước 4/4: Cửa sổ CAM350",
        "Activate CAM350 window, then click 'Detect', or type window title manually:":
            "Kích hoạt cửa sổ CAM350, rồi bấm 'Detect', hoặc gõ tiêu đề cửa sổ bằng tay:",
        "X Textbox": "Ô X",
        "Y Textbox": "Ô Y",
        "Rotate Button": "Nút xoay 90°",
        "✓ {label}: ({x}, {y})": "✓ {label}: ({x}, {y})",
        "✓ Window: {title}": "✓ Cửa sổ: {title}",
        "? {label}: not set": "? {label}: chưa đặt",
        "? Window title: not set": "? Chưa đặt tiêu đề cửa sổ",
        "1. Move mouse over CAM350 X textbox\n2. Click 'Start Capture'\n3. Wait 3 seconds - position auto-saved":
            "1. Di chuyển chuột lên ô X của CAM350\n2. Bấm 'Start Capture'\n3. Chờ 3 giây - vị trí sẽ tự động lưu",
        "1. Move mouse over CAM350 Y textbox\n2. Click 'Start Capture'\n3. Wait 3 seconds - position auto-saved":
            "1. Di chuyển chuột lên ô Y của CAM350\n2. Bấm 'Start Capture'\n3. Chờ 3 giây - vị trí sẽ tự động lưu",
        "1. Rotate the board 90° in CAM350 and move mouse over the rotation-confirm button\n2. Click 'Start Capture'\n3. Wait 10 seconds - position auto-saved":
            "1. Xoay board 90° trong CAM350 và di chuột lên nút xác nhận xoay\n2. Bấm 'Start Capture'\n3. Chờ 10 giây - vị trí sẽ tự động lưu",
        "Capturing in {n}s...": "Đang thu trong {n}s...",
        "No active window detected.": "Không phát hiện cửa sổ hoạt động.",
        "Calibration Complete": "Hoàn tất hiệu chuẩn",
        "All positions captured. Review and click Save & Close.":
            "Đã thu toàn bộ vị trí. Rà soát lại và bấm Lưu & Đóng.",
        "Calibration saved successfully.": "Đã lưu hiệu chuẩn thành công.",
        # CAM350 controller errors
        "CAM350 window not found": "Không tìm thấy cửa sổ CAM350",
        " (searched for '{title}' and 'CAM350')": " (đã tìm '{title}' và 'CAM350')",
        "{msg}. Is CAM350 running?": "{msg}. CAM350 có đang chạy không?",
        "Cannot activate CAM350 window. Please bring CAM350 to the foreground and try again.":
            "Không thể kích hoạt cửa sổ CAM350. Vui lòng đưa CAM350 lên foreground rồi thử lại.",
        "CAM350 not calibrated. Please run calibration first.":
            "CAM350 chưa được hiệu chuẩn. Hãy chạy hướng dẫn hiệu chuẩn trước.",
        "No numeric value found in CAM350 {axis} field. Position ({x}, {y}), clipboard content was: {content}":
            "Không tìm thấy giá trị số trong ô {axis} của CAM350. Vị trí ({x}, {y}), nội dung clipboard: {content}",
        # Align origin wizard
        "Step 1/7: Select Gerber Files": "Bước 1/7: Chọn file Gerber",
        "Gerber Files": "File Gerber",
        "GKO (Outline) *:": "GKO (Outline) *:",
        "GTP (Top Paste):": "GTP (Paste lớp trên):",
        "GBP (Bottom Paste):": "GBP (Paste lớp dưới):",
        "GTO (Top Overlay / Silkscreen):": "GTO (Silkscreen lớp trên):",
        "GBO (Bottom Overlay / Silkscreen):": "GBO (Silkscreen lớp dưới):",
        "(not selected)": "(chưa chọn)",
        "(optional)": "(tùy chọn)",
        "* GKO is required (Gerber Outline).\nGTP/GBP help detect offsets more accurately (recommended).\nGTO/GBO (names/designators on the board) are only used for display in Gerber View.":
            "* GKO là bắt buộc (Gerber Outline).\nGTP/GBP giúp phát hiện offset chính xác hơn (khuyến nghị).\nGTO/GBO (tên/designator trên board) chỉ dùng để hiển thị trong Gerber View.",
        "Browse...": "Duyệt...",
        "Select GKO file": "Chọn file GKO",
        "Select GTP file": "Chọn file GTP",
        "Select GBP file": "Chọn file GBP",
        "Select GTO file": "Chọn file GTO",
        "Select GBO file": "Chọn file GBO",
        "Please select the GKO (Outline) file.": "Vui lòng chọn file GKO (Outline).",
        "Analyzing Gerber...": "Đang phân tích Gerber...",
        "Cannot read GKO: {e}": "Không đọc được GKO: {e}",
        "Step 2/7: Panel Detection Result": "Bước 2/7: Kết quả phát hiện Panel",
        "Panel Type A (step-repeat)": "Panel loại A (step-repeat)",
        "Panel Type B (multiple blocks)": "Panel loại B (nhiều khối)",
        "Single board": "Board đơn",
        "Type: {kind}": "Loại: {kind}",
        "Instances: {count}": "Số bản: {count}",
        "Panel Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil":
            "Gốc Panel: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
        "Panel Width:  {w:.4f} mm  ({wm:.2f} mil)": "Chiều rộng Panel: {w:.4f} mm  ({wm:.2f} mil)",
        "Panel Height: {h:.4f} mm  ({hm:.2f} mil)": "Chiều cao Panel: {h:.4f} mm  ({hm:.2f} mil)",
        " [layer: {name}]": " [lớp: {name}]",
        "  Instance {k}{tag}:": "  Bản {k}{tag}:",
        "    origin=({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil":
            "    origin=({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
        "    w={w:.4f} mm ({wm:.2f} mil)  h={h:.4f} mm ({hm:.2f} mil)":
            "    w={w:.4f} mm ({wm:.2f} mil)  h={h:.4f} mm ({hm:.2f} mil)",
        "Panel detected. The next step lets you choose the origin mode.":
            "Đã phát hiện panel. Bước tiếp theo cho phép bạn chọn chế độ gốc.",
        "Step 3/7: Rotation and Unit Options": "Bước 3/7: Xoay và đơn vị",
        "Rotate Panel/Board": "Xoay Panel/Board",
        "0° (no rotation) - default": "0° (không xoay) - mặc định",
        "Select layer to apply 90° rotation formula": "Chọn lớp để áp công thức xoay 90°",
        "Top layer - 90° formula: (H-y, x)": "Lớp trên - công thức 90°: (H-y, x)",
        "Bottom layer - 90° formula: (y, x)": "Lớp dưới - công thức 90°: (y, x)",
        "PickPlace coordinate units": "Đơn vị toạ độ PickPlace",
        "mm (millimeters) - default": "mm (milimét) - mặc định",
        "mil (convert to mm: * 0.0254)": "mil (đổi sang mm: * 0.0254)",
        "Step 4/7: Computing offsets...": "Bước 4/7: Đang tính offset...",
        "Starting computation...": "Đang bắt đầu tính toán...",
        "Detecting panel from GKO...": "Đang phát hiện panel từ GKO...",
        "Detected: {kind}, {count} instance(s)": "Đã phát hiện: {kind}, {count} bản",
        "Reading GTP (Top Paste)...": "Đang đọc GTP (Paste trên)...",
        "Reading GBP (Bottom Paste)...": "Đang đọc GBP (Paste dưới)...",
        "Computing offset for each instance...": "Đang tính offset cho từng bản...",
        "Instance {current}/{total}: {name}...": "Bản {current}/{total}: {name}...",
        "board": "board",
        "Creating transforms...": "Đang tạo phép biến đổi...",
        "Calculation complete.": "Tính toán hoàn tất.",
        "Error: {e}": "Lỗi: {e}",
        "Step 4/7: Updating data...": "Bước 4/7: Đang cập nhật dữ liệu...",
        "Updated {count}/{total}": "Đã cập nhật {count}/{total}",
        "Done! {count} components aligned.": "Hoàn tất! Đã canh {count} linh kiện.",
        "Step 5/7: Get Panel Origin from CAM350 (Macro)": "Bước 5/7: Lấy Gốc Panel từ CAM350 (Macro)",
        "Layer": "Lớp",
        "Top layer (default)": "Lớp trên (mặc định)",
        "Bottom layer": "Lớp dưới (Bottom)",
        "Macro": "Macro",
        "Press the button below to run the macro on CAM350:\n1. After pressing Run Macro, the app waits 5 seconds - switch to the CAM350 window in the meantime\n2. If Step 2 selected 90° rotation: the program presses Ctrl+Alt+R to rotate the board 90° first\n3. Top layer: Ctrl+Alt+X (show Space Origin marker) -> jump to Panel Origin (from Step 2)\n4. Bottom layer: Ctrl+Alt+B (view Bottom) -> Ctrl+Alt+X -> jump to the transformed coordinates\n5. Confirm the dialog that appears by pressing Enter\n\nNote: CAM350 must be displaying mm units for accurate jumps.":
            "Nhấn nút bên dưới để chạy macro trên CAM350:\n1. Sau khi bấm Run Macro, ứng dụng chờ 5 giây - hãy chuyển sang cửa sổ CAM350 trong lúc đó\n2. Nếu Bước 2 chọn xoay 90°: chương trình nhấn Ctrl+Alt+R để xoay board 90° trước\n3. Lớp trên: Ctrl+Alt+X (hiện marker Space Origin) -> nhảy đến Gốc Panel (từ Bước 2)\n4. Lớp dưới: Ctrl+Alt+B (xem Bottom) -> Ctrl+Alt+X -> nhảy đến toạ độ đã biến đổi\n5. Xác nhận hộp thoại hiện ra bằng phím Enter\n\nLưu ý: CAM350 phải đang hiển thị đơn vị mm để nhảy chính xác.",
        "Run Macro ▶": "Chạy Macro ▶",
        "Not run yet.": "Chưa chạy.",
        "CAM350 is not calibrated. Please run the Calibration Wizard first.":
            "CAM350 chưa được hiệu chuẩn. Hãy chạy Hướng dẫn hiệu chuẩn trước.",
        "Got Panel Origin ({layer}): X = {x:.4f}, Y = {y:.4f}":
            "Đã lấy Gốc Panel ({layer}): X = {x:.4f}, Y = {y:.4f}",
        "Top": "Trên (Top)",
        "Bottom": "Dưới (Bottom)",
        "Please switch to the CAM350 window in {n} seconds...":
            "Vui lòng chuyển sang cửa sổ CAM350 trong {n} giây...",
        "Running macro on CAM350...": "Đang chạy macro trên CAM350...",
        "Running macro on CAM350... (layer={layer}, angle={angle}°, jump=({ox}, {oy}))":
            "Đang chạy macro trên CAM350... (lớp={layer}, góc={angle}°, nhảy=({ox}, {oy}))",
        "No Panel Origin data from Step 2.": "Không có dữ liệu Gốc Panel từ Bước 2.",
        "Macro failed: {error}": "Macro thất bại: {error}",
        "Step 7/7: Alignment Result": "Bước 7/7: Kết quả canh",
        "Panel Origin": "Gốc Panel",
        "Board Origin": "Gốc Board",
        "Yes (×0.0254)": "Có (×0.0254)",
        "No": "Không",
        "Origin mode: {mode}": "Chế độ gốc: {mode}",
        "Rotation: {angle}°": "Xoay: {angle}°",
        "mil→mm conversion: {value}": "Quy đổi mil→mm: {value}",
        "Panel": "Panel",
        "Board": "Board",
        "{label} Width:  {w:.4f} mm  ({wm:.2f} mil)": "Chiều rộng {label}: {w:.4f} mm  ({wm:.2f} mil)",
        "{label} Height: {h:.4f} mm  ({hm:.2f} mil)": "Chiều cao {label}: {h:.4f} mm  ({hm:.2f} mil)",
        "{label} Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil":
            "Gốc {label}: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
        "Per-instance offset results:": "Kết quả offset từng bản:",
        "Instance {k}:": "Bản {k}:",
        "  Board Width:  {w:.4f} mm ({wm:.2f} mil)": "  Chiều rộng board: {w:.4f} mm ({wm:.2f} mil)",
        "  Board Height: {h:.4f} mm ({hm:.2f} mil)": "  Chiều cao board: {h:.4f} mm ({hm:.2f} mil)",
        "  Board Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil":
            "  Gốc board: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
        "  [{layer}] Offset X: {v:.4f} mm": "  [{layer}] Offset X: {v:.4f} mm",
        "  [{layer}] Offset Y: {v:.4f} mm": "  [{layer}] Offset Y: {v:.4f} mm",
        "  [{layer}] Offset Rotation: {v:.0f}°": "  [{layer}] Offset rotation: {v:.0f}°",
        "  [{layer}] Matched: {m}/{total}, Residual: {r:.6f} mm":
            "  [{layer}] Khớp: {m}/{total}, Sai số còn lại: {r:.6f} mm",
        "  [{layer}] WARNING: pad offset (GTP) lệch gốc GKO > {tol} mm; "
        "đã ưu tiên GKO — tọa độ giữ nguyên theo file nguồn.":
            "  [{layer}] CẢNH BÁO: offset pad (GTP) lệch gốc GKO > {tol} mm; "
            "đã ưu tiên GKO — tọa độ giữ nguyên theo file nguồn.",
        "Combined": "Kết hợp",
        "Total components: {count}": "Tổng linh kiện: {count}",
        "Aligned: {count}": "Đã canh: {count}",
        "Skipped (unchanged): {count}": "Bỏ qua (không đổi): {count}",
        "◀ Back": "◀ Quay lại",
        "Finish": "Hoàn tất",
        # Gerber viewer
        "Gerber View - Overlay PickPlace": "Gerber View - Overlay PickPlace",
        "Display settings saved to session.": "Đã lưu cài đặt hiển thị vào phiên.",
        "Reading GKO (outline)...": "Đang đọc GKO (outline)...",
        "Reading GTP (Top Paste)...": "Đang đọc GTP (Paste trên)...",
        "Reading GBP (Bottom Paste)...": "Đang đọc GBP (Paste dưới)...",
        "Reading GTO (Silkscreen)...": "Đang đọc GTO (Silkscreen)...",
        "Reading GBO (Silkscreen)...": "Đang đọc GBO (Silkscreen)...",
        "Reading Gerber file...": "Đang đọc file Gerber...",
        "Done.": "Xong.",
        "Display...": "Hiển thị...",
        "Fit View": "Vừa khung",
        "Reset": "Đặt lại",
        "Export PDF...": "Xuất PDF...",
        "Export Gerber PDF": "Xuất PDF Gerber",
        "PDF exported to {path}": "Đã xuất PDF tới {path}",
        "Export Failed": "Xuất thất bại",
        "Layer": "Lớp",
        "Top layer (GKO + GTP)": "Lớp trên (GKO + GTP)",
        "Bottom layer (GKO + GBP)": "Lớp dưới (GKO + GBP)",
        "Components:": "Linh kiện:",
        "Search component...": "Tìm linh kiện...",
        "Search designator or MPN...": "Tìm theo designator hoặc MPN...",
        "Rot": "Rot",
        "No data yet.": "Chưa có dữ liệu.",
        "Details (Zoom {f:g}x)": "Chi tiết (Phóng to {f:g}x)",
        "Zoom:": "Phóng to:",
        "Hover the drawing / select a component to see details.":
            "Di chuột lên hình / chọn một linh kiện để xem chi tiết.",
        "Display settings": "Cài đặt hiển thị",
        "Save display settings": "Lưu cài đặt hiển thị",
        "Display": "Hiển thị",
        "Rotate Gerber:": "Xoay Gerber:",
        "Invert Gerber rotation": "Đảo chiều xoay Gerber",
        "Flip Gerber (Mirror Y)": "Lật Gerber (Mirror Y)",
        "Flip Gerber (Mirror X)": "Lật mặt Gerber (Mirror X)",
        "Offset X:": "Offset X:",
        "To Origin (0,0)": "Về gốc (0,0)",
        "Show GKO outline": "Hiện outline GKO",
        "Show Paste (GTP / GBP)": "Hiện Paste (GTP / GBP)",
        "Show Silkscreen (GTO / GBO)": "Hiện Silkscreen (GTO / GBO)",
        "Show PickPlace (aligned)": "Hiện PickPlace (đã canh)",
        "Show crosshair": "Hiện crosshair",
        "Arrow size:": "Kích thước mũi tên:",
        "Crosshair scale:": "Tỷ lệ crosshair:",
        "No valid GKO file.": "Không có file GKO hợp lệ.",
        "Outline: {ol} lines, {of} pads | Top: {tf} pads | Bottom: {bf} pads | Silk Top: {st} lines | Silk Bottom: {sb} lines":
            "Outline: {ol} đường, {of} pad | Trên: {tf} pad | Dưới: {bf} pad | Silk Trên: {st} đường | Silk Dưới: {sb} đường",
        "Error reading Gerber file": "Lỗi đọc file Gerber",
        "Cannot read Gerber:\n{message}": "Không đọc được Gerber:\n{message}",
        "Measure": "Đo kích thước",
        "Clear": "Xóa",
        "Click two points to measure the distance. Right-click or Esc cancels the current measurement.":
            "Click 2 điểm để đo khoảng cách. Click chuột phải hoặc Esc để hủy phép đo đang vẽ.",
        "Measure mode: click the start point.":
            "Chế độ đo: click điểm bắt đầu.",
        "Measure mode: click the end point.":
            "Chế độ đo: click điểm kết thúc.",
        "Distance: {d:.3f} mm": "Khoảng cách: {d:.3f} mm",
        "Snap to pad center when measuring":
            "Bám vào tâm pad khi đo",
        "Tolerance:": "Dung sai:",
        "Snap tolerance is in mm and applies to the nearest pad center within the radius.":
            "Dung sai tính theo mm, áp dụng cho tâm pad gần nhất nằm trong bán kính này.",
        "Snap": "Bám tâm pad",
        "Toggle snap to pad center when measuring. Hold Ctrl while clicking to bypass snap for that click.":
            "Bật/tắt bám tâm pad khi đo. Giữ Ctrl khi click để tạm thời không bám cho lần click đó.",
        "Distance: {d:.3f} mm (snap off)": "Khoảng cách: {d:.3f} mm (không bám)",
        "Compact": "Thu gọn",
        "Show/hide the options bar (buttons, layer, component settings). Search stays visible.":
            "Ẩn/hiện nhóm tùy chọn (nút chức năng, layer, cài đặt component). Ô tìm kiếm vẫn hiển thị.",
        "Show/hide the options bar and file stats (Outline/Top/Bottom/Silk) to give the component table more space.":
            "Ẩn/hiện nhóm tùy chọn và dòng thống kê file (Outline/Top/Bottom/Silk) để bảng component cao hơn.",
        # PCB Info dialog
        "Hotkey {hk}: point the mouse at the desired position in CAM350 then press the hotkey to read coordinates.\nThe macro auto-fills X Boc 1 & Y Boc 1, the 2nd time fills Boc 2, the 3rd time fills Boc 3. The Save button appears after enough data.":
            "Hotkey {hk}: di chuyển chuột đến vị trí mong muốn trong CAM350 rồi nhấn hotkey để đọc toạ độ.\nMacro tự điền X Boc 1 & Y Boc 1, lần thứ 2 điền Boc 2, lần thứ 3 điền Boc 3. Nút Save hiện ra khi đủ dữ liệu.",
        "Board": "Board",
        "Board Width:": "Chiều rộng Board:",
        "Board Height:": "Chiều cao Board:",
        "Working Area Width:": "Chiều rộng vùng làm việc:",
        "Position Working:": "Vị trí làm việc:",
        "Thickness:": "Độ dày:",
        "Boc Coordinates (auto-filled by hotkey)": "Toạ độ Boc (tự điền bằng hotkey)",
        "Reset": "Đặt lại",
        "Cannot register hotkey {hk}: {e}": "Không đăng ký được hotkey {hk}: {e}",
        "All 3 Boc positions filled. Press Save to save.": "Đã đủ 3 vị trí Boc. Nhấn Save để lưu.",
        "Macro Failed": "Macro thất bại",
        "Filled Boc {index} (X={x}, Y={y}).": "Đã điền Boc {index} (X={x}, Y={y}).",
        "Reset PCB Info": "Đặt lại PCB Info",
        "Clear all PCB Info data and restore defaults?": "Xóa toàn bộ dữ liệu PCB Info và trả về dữ liệu mặc định?",
        "Reset Failed": "Đặt lại thất bại",
        "Reset to default data.": "Đã đặt lại về dữ liệu mặc định.",
        "Save Failed": "Lưu thất bại",
        "PCB info saved.": "Đã lưu thông tin PCB.",
        # Jump popup
        "Component Info": "Thông tin linh kiện",
        "◀ Prev": "◀ Trước",
        "Next ▶": "Kế tiếp ▶",
        "Old X/Y:": "X/Y cũ:",
        "Old Rot:": "Rot cũ:",
        "New X/Y:": "X/Y mới:",
        "New Rot:": "Rot mới:",
        "Rotation Guide": "Hướng dẫn xoay",
        "Rotation guide": "Hướng dẫn xoay",
        "Remark...": "Ghi chú...",
        "Jump to CAM350": "Nhảy đến CAM350",
        "Delete": "Xóa",
        "Component {current}/{total} — {des}": "Linh kiện {current}/{total} — {des}",
        # Column mapping
        "Column Mapping": "Ánh xạ cột",
        "Profile:": "Hồ sơ:",
        "Load": "Nạp",
        "Save Profile": "Lưu hồ sơ",
        "Map source columns to fields": "Ánh xạ cột nguồn tới các trường",
        "Required": "Bắt buộc",
        "Auto-guess": "Tự đoán",
        "Preview:": "Xem trước:",
        "Profile name:": "Tên hồ sơ:",
        "The following fields are required: {names}": "Các trường sau là bắt buộc: {names}",
        # License
        "License Activation": "Kích hoạt giấy phép",
        "Machine ID:": "Mã máy:",
        "Copy": "Sao chép",
        "Copied!": "Đã sao chép!",
        "Send this Machine ID to your provider to receive a License Key.":
            "Gửi Mã máy này cho nhà cung cấp để nhận Mã giấy phép.",
        "License Key:": "Mã giấy phép:",
        "Paste your license key here": "Dán mã giấy phép vào đây",
        "Activate": "Kích hoạt",
        "Exit": "Thoát",
        "License": "Giấy phép",
        "Please enter a license key.": "Vui lòng nhập mã giấy phép.",
        "No active license found on this computer.": "Không tìm thấy giấy phép hoạt động trên máy này.",
        "The license key has expired. Please contact your provider for a renewal.":
            "Mã giấy phép đã hết hạn. Vui lòng liên hệ nhà cung cấp để gia hạn.",
        "The license key does not match this computer.": "Mã giấy phép không khớp với máy này.",
        "The license key is not valid.": "Mã giấy phép không hợp lệ.",
        "System clock issue detected. Set the correct date and time, then restart the app.":
            "Phát hiện sự cố đồng hồ hệ thống. Hãy đặt đúng ngày giờ rồi khởi động lại ứng dụng.",
        "No active license": "Không có giấy phép hoạt động",
        "Evaluation mode (license check disabled)": "Chế độ đánh giá (đã tắt kiểm tra giấy phép)",
        "Licensed to {customer} | Expires {expiry} | {days} days remaining":
            "Cấp cho {customer} | Hết hạn {expiry} | còn {days} ngày",
        # Pre-screen check (Align wizard step 6/7)
        "Step 6/7: Pre-screen Check": "Bước 6/7: Kiểm tra Pre-screen",
        "▶ Run Check": "▶ Chạy kiểm tra",
        "Not run yet. Press Run Check to scan the board.":
            "Chưa chạy. Nhấn Chạy kiểm tra để quét toàn bộ board.",
        "Starting pre-screen...": "Đang bắt đầu kiểm tra...",
        "Reading GKO (outline)...": "Đang đọc GKO (outline)...",
        "Reading GTP (Top Paste)...": "Đang đọc GTP (Paste lớp trên)...",
        "Reading GBP (Bottom Paste)...": "Đang đọc GBP (Paste lớp dưới)...",
        "Running pre-screen checks...": "Đang chạy các kiểm tra...",
        "Pre-screen failed: {message}": "Kiểm tra Pre-screen lỗi: {message}",
        "✅ No issues found.": "✅ Không phát hiện bất thường.",
        "🔁 ROT : {n}": "🔁 ROT : {n}",
        "📍 PAD : {n}": "📍 PAD : {n}",
        "📌 DUP : {n}": "📌 DUP : {n}",
        "⬛ OUT : {n}": "⬛ OUT : {n}",
        "Total: {total} / {rec_count} components":
            "Tổng: {total} / {rec_count} linh kiện",
        "Legend": "Chú thích",
        "🔁 ROT = Rotation — unusual rotation":
            "🔁 ROT = Rotation — góc xoay bất thường",
        "(differs more than {dev:g}\u00b0 from the majority of the same MPN)":
            "(lệch quá {dev:g}\u00b0 so với đa số cùng MPN)",
        "📍 PAD = Pad — PickPlace block offset vs paste":
            "📍 PAD = Pad — PickPlace lệch khối so với paste",
        "(median nearest-pad distance above {tol:g} mm)":
            "(trung vị khoảng cách tới pad gần nhất vượt {tol:g} mm)",
        "median nearest-pad distance {v:.2f} mm exceeds tolerance {tol:g} mm":
            "trung vị khoảng cách tới pad gần nhất {v:.2f} mm vượt ngưỡng {tol:g} mm",
        "📎 Paste match (median): {v} mm over {n} components":
            "📎 Độ khớp paste (trung vị): {v} mm trên {n} con",
        "📎 Paste match: no paste data":
            "📎 Độ khớp paste: không có dữ liệu paste",
        "Updating component table...":
            "Đang cập nhật bảng thành phần...",
        "Please wait":
            "Vui lòng đợi",
        "📌 DUP = Duplicate — two components share coordinates":
            "📌 DUP = Duplicate — hai linh kiện trùng tọa độ",
        "(within {tol:g} mm)": "(trong phạm vi {tol:g} mm)",
        "⬛ OUT = Out of outline — component outside board outline":
            "⬛ OUT = Out of outline — linh kiện nằm ngoài outline board",
        "(more than {margin:g} mm beyond the board edge)":
            "(vượt quá {margin:g} mm so với biên board)",
        "💡 Details: check the Flags column in the main table and dashed orange frames in Gerber View.":
            "💡 Xem chi tiết: cột Flags ở bảng chính và khung cam nét đứt trong Gerber View.",
        "Dismiss flag": "Bỏ qua cảnh báo",
        "duplicate coordinates with {des}": "trùng tọa độ với {des}",
        "rotation {rot:.0f}\u00b0 differs from MPN majority {maj:.0f}\u00b0 ({mpn})":
            "góc xoay {rot:.0f}\u00b0 khác đa số cùng MPN ({maj:.0f}\u00b0, {mpn})",
        "nearest paste pad is {dist:.3f} mm away (> {tol:g} mm)":
            "paste gần nhất cách {dist:.3f} mm (> {tol:g} mm)",
        "outside board outline (+{margin:g} mm)":
            "nằm ngoài outline board (+{margin:g} mm)",
        "⚠ Pre-screen: {total} issue(s) ({rot} ROT · {pad} PAD · {dup} DUP · {out} OUT)":
            "⚠ Pre-screen: {total} cảnh báo ({rot} ROT · {pad} PAD · {dup} DUP · {out} OUT)",
        "⚠ Layer {layer}: alignment unreliable — PAD/OUT results may be inaccurate.":
            "⚠ Lớp {layer}: align không tin cậy — kết quả PAD/OUT có thể không chính xác.",
        "Run Check": "Kiểm tra lại",
        "Reload": "Nạp lại",
        "Reload latest component data from the main window":
            "Nạp lại dữ liệu component mới nhất từ cửa sổ chính",
        "Pre-screen Check": "Kiểm tra Pre-screen",
        "Gerber outline file (GKO) is missing — run Align PickPlace Origin again.":
            "Thiếu file outline (GKO) — hãy chạy Align PickPlace Origin lại.",
        "Re-run the pre-screen check on the current data":
            "Chạy lại pre-screen trên dữ liệu hiện tại",
        "\U0001F504 Re-running pre-screen check...":
            "\U0001F504 Đang kiểm tra lại pre-screen...",
        "Run Align PickPlace Origin once to enable Run Check.":
            "Hãy chạy Align PickPlace Origin một lần để bật nút Run Check.",
    },
}


def set_language(lang: str) -> None:
    global _LANGUAGE
    _LANGUAGE = lang if lang in _TRANSLATIONS else "en"


def current_language() -> str:
    return _LANGUAGE


def tr(key: str, **kwargs: Any) -> str:
    text = _TRANSLATIONS.get(_LANGUAGE, {}).get(key)
    if text is None:
        text = _TRANSLATIONS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
