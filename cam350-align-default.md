---
description: Tính offset Bottom-Left Origin từ Gerber và áp dụng vào toạ độ X,Y của PickPlace (đã kiểm chứng thực tế, độ chính xác < 0.01mm). Hỗ trợ cả board đơn và panel nhiều board (step-and-repeat hoặc nhiều block LN/SR rời rạc cùng kích thước). Hỗ trợ 2 chế độ gốc toạ độ xuất ra: Panel Origin (mặc định — toàn panel dùng chung 1 gốc = góc trái–dưới panel, Width/Height dùng để xoay/mirror cũng là của cả panel) hoặc Board Origin (mỗi board 1 gốc riêng, chỉ dùng khi người dùng chỉ rõ).
---

# PCB PickPlace Origin Offset — Hướng dẫn thực thi

Mục tiêu: xác định gốc toạ độ (0,0) từ file Gerber outline (góc
trái–dưới cùng), tính offset chính xác giữa hệ toạ độ PickPlace và hệ
toạ độ Gerber, rồi dịch toàn bộ X, Y trong PickPlace theo offset đó.

Với panel nhiều board, tài liệu hỗ trợ **2 chế độ gốc toạ độ** (chọn ở
STEP 0B, xem mục 2B):
- **Chế độ Panel Origin (mặc định):** toàn panel dùng chung 1 gốc
  (0,0) = góc trái–dưới của **toàn panel** (không phải của board), và
  mọi công thức cần Width/Height (xoay 90°, mirror, kiểm tra biên) đều
  dùng **Panel Width/Height** thay vì Board Width/Height. Dùng khi máy
  đặt linh kiện định vị theo panel tổng (1 fiducial/kẹp chung cho cả
  tờ) — và là lựa chọn mặc định nếu người dùng không chỉ rõ khác đi.
- **Chế độ Board Origin:** mỗi board instance trên panel có gốc (0,0)
  và Width/Height riêng của chính nó. Dùng khi máy đặt linh kiện định
  vị theo từng board riêng lẻ (mỗi board có fiducial/kẹp riêng) — chỉ
  áp dụng khi người dùng chỉ rõ muốn chế độ này.

Việc dò offset bằng GTP/GBP (STEP 3B) **luôn luôn** phải làm riêng theo
từng board instance bất kể chế độ nào — chế độ Panel Origin chỉ khác ở
bước cuối (dịch gốc, xoay, mirror), không thay đổi cách match pad.

Tài liệu này đã được kiểm chứng trên các bộ dữ liệu thật:
- Board đơn PSU_FEM, 241 linh kiện — sai số offset toàn cục **< 0.01mm**
  (trung vị đo được: 0.002mm).
- Panel LENS (1×2, step-repeat theo Y, dy=56.6mm), 192 linh kiện — xác
  nhận thuật toán STEP 3B (KDTree + ngưỡng 8mm + median) tự động loại
  trừ pad của board khác trên panel mà KHÔNG cần crop thủ công, miễn
  ngưỡng match ≤ khoảng cách thật giữa 2 board. STEP 0/STEP 3B dưới
  đây bổ sung cơ chế crop tường minh để không phụ thuộc may rủi vào
  ngưỡng đó khi panel có nhiều board xếp sát nhau.
- Panel ISP (2 board giống hệt nhau, MỖI board 1 block `%LN%...%SR%`
  riêng với `SRX1Y1` — KHÔNG dùng step-repeat thật `nx>1`/`ny>1` — xác
  nhận cần mở rộng STEP 0 để nhận diện kiểu panel "nhiều block rời rạc
  cùng kích thước" thay vì chỉ dựa vào `nx>1`/`ny>1`.

--------------------------------------------------
## 1. WORKSPACE

```
input/
  gerber/
    *.GKO            (bắt buộc — board/panel outline)
    *.GTP             (khuyến nghị — Top Paste, dùng để dò offset chính xác)
    *.GBP             (khuyến nghị — Bottom Paste, nếu có linh kiện Bottom)
  PickPlace.xlsx      (bắt buộc)
output/
scripts/
```

- Nếu có nhiều file cùng loại trong input/ → dừng lại, báo xung đột.
- Không sửa/xoá gì trong input/. Không ghi đè file gốc.
- Mọi file sinh ra nằm trong output/.

--------------------------------------------------
## 2. STEP 0 — Phát hiện Panel (Step-and-Repeat)

**Bắt buộc chạy bước này trước khi tính Board Origin.** Bỏ qua bước
này là nguyên nhân phổ biến nhất khiến offset bị tính sai theo kiểu
"lệch vào giữa 2 board" khi Gerber thực chất là 1 panel nhiều board.

1. Đọc mọi block `%LN<tên>*%` ... `%SRXaYbIdxJdy*%` trong GKO. Mỗi
   block `%LN%` mở ra một "layer con" đặt tên riêng; lệnh `%SR%` theo
   sau nó khai báo cách layer con đó được step-repeat: `a`×`b` bản
   sao, bước lặp `(dx, dy)` (đơn vị theo `%MOIN%`/`%MOMM%`, quy đổi mm
   như STEP 1).

   ```python
   import re

   def parse_sr_blocks(path):
       blocks, cur_name = [], None
       for line in open(path):
           line = line.strip()
           if m := re.match(r'%LN(.+?)\*%', line):
               cur_name = m.group(1)
           if m := re.match(r'%SRX(\d+)Y(\d+)I([\d.]+)J([\d.]+)\*%', line):
               blocks.append({'name': cur_name, 'nx': int(m.group(1)), 'ny': int(m.group(2)),
                               'dx_in': float(m.group(3)), 'dy_in': float(m.group(4))})
       return blocks
   ```

2. Phân loại các block — có **2 kiểu panel** cần nhận diện, không chỉ 1:

   **Kiểu A — step-repeat thật (`nx>1` hoặc `ny>1`):**
   - **Sub-board block** — block có `nx > 1` hoặc `ny > 1`. Đây là
     outline của **1 board đơn**, dùng để tính Board Origin/Width/
     Height ở STEP 1. Các instance khác trên panel suy ra bằng cộng
     `(dx, dy)` theo `(nx, ny)`.
   - **Panel outline block** — block còn lại, thường `nx=ny=1, I=J=0`
     (ví dụ tên `LENS.gko` không có hậu tố `.subN`). Đây là outline
     **toàn panel** (bao gồm rail, tooling hole, fiducial panel).

   **Kiểu B — nhiều block rời rạc cùng kích thước, KHÔNG dùng SR thật
   (mỗi board vẽ trực tiếp bằng toạ độ tuyệt đối của chính nó, block
   của nó khai `SRX1Y1I0J0`):**
   - Tính Width/Height (Xmax−Xmin, Ymax−Ymin) của **từng** block có
     hậu tố `.subN` (mọi block, kể cả `SRX1Y1`).
   - Nếu có **≥2 block `.subN`** mà Width/Height của chúng giống nhau
     trong sai số nhỏ (ví dụ ≤ 0.01mm) → coi đây là **panel nhiều
     instance của cùng 1 board**, dù không có `nx>1`/`ny>1` nào. Mỗi
     block `.subN` là 1 board instance độc lập, dùng outline (Xmin,
     Ymin, W, H) của **chính block đó** làm Board Origin/W/H riêng cho
     instance đó ở STEP 1 (không suy ra bằng cộng dx,dy như kiểu A).
   - Nếu Width/Height của các block `.subN` khác nhau đáng kể (panel
     nhiều loại board khác nhau trên cùng 1 tờ) → dừng lại, báo cho
     người dùng, xử lý thủ công vì nằm ngoài phạm vi quy trình tự động
     này.
   - Block **không** có hậu tố `.subN` (tên trùng đúng tên file, ví dụ
     `ISP.gko`) là **panel outline block** — outline toàn panel.

   Trong cả 2 kiểu: **Panel outline block** chỉ dùng để (a) vẽ overlay
   tham khảo ở STEP 9, và (b) tính **Panel Origin/Width/Height** ở
   STEP 1B — bắt buộc phải tính vì đây là chế độ mặc định (STEP 0B) —
   không bao giờ dùng để tính Board Origin của từng instance.
3. Nếu KHÔNG tìm thấy panel theo cả kiểu A lẫn kiểu B ở trên → đây là
   **board đơn** (trường hợp gốc của tài liệu này), bỏ qua toàn bộ phần
   "panel" trong các bước dưới, dùng thẳng outline duy nhất trong GKO.
4. Nếu tìm thấy panel (kiểu A hoặc B) → ghi lại danh sách instance
   `[(sub_block_name_k, board_origin_k, board_w_k, board_h_k), ...]`
   để dùng xuyên suốt STEP 1 → STEP 3B. Với kiểu A, `board_origin_k`
   suy ra từ `(dx,dy)*k` cộng vào outline sub-board gốc; với kiểu B,
   `board_origin_k` đọc trực tiếp từ outline riêng của từng block
   `.subN`.
5. Kiểm chứng thực tế:
   - **Panel LENS (kiểu A):** `%SRX1Y2I0.00000J2.22839*%` gắn với
     layer `LENS.gko.sub1` → panel 1×2 theo Y, `dy = 2.22839in =
     56.6011mm`. Layer `LENS.gko` (không lặp) là outline panel tổng.
   - **Panel ISP (kiểu B):** 2 block `ISP.gko.sub1` và `ISP.gko.sub2`,
     mỗi block đều khai `%SRX1Y1I0.00000J0.00000*%` (không phải step-
     repeat thật). Outline riêng từng block: `sub1` → W=139.9997mm,
     H=119.9998mm; `sub2` → W=139.9997mm, H=119.9998mm — giống hệt
     nhau → xác nhận đây là panel 2 instance của cùng 1 board theo
     kiểu B. Block `ISP.gko` (không suffix) là panel outline, Xmin=
     -5.0000mm, Ymin=-74.3778mm, W=149.9997mm, H=191.3778mm.

--------------------------------------------------
## 2B. STEP 0B — Chọn chế độ gốc toạ độ xuất ra (chỉ áp dụng khi có panel)

Chỉ hỏi/áp dụng bước này nếu STEP 0 xác định là panel nhiều board (kiểu
A hoặc B). Board đơn thì bỏ qua, luôn dùng Board Origin/W/H của chính
nó.

**Nên hỏi người dùng để xác nhận, nhưng nếu người dùng không chỉ rõ thì
mặc định dùng chế độ Panel Origin — không cần dừng lại chờ xác nhận
mới được tiếp tục:**

> "Toạ độ xuất ra bạn muốn lấy gốc (0,0) ở đâu?
> (1) Cả panel dùng chung 1 gốc (góc trái–dưới của toàn panel) —
>     mặc định, hay
> (2) Mỗi board 1 gốc riêng (góc trái–dưới của chính board đó)?"

- **Chế độ (1) — Panel Origin** (mặc định nếu người dùng không chỉ rõ):
  dùng chung `panel_origin`, `panel_width`, `panel_height` (tính ở
  STEP 1B) cho bước dịch gốc cuối cùng (STEP 4B) và cho công thức
  xoay/mirror (STEP 6/7, áp dụng **1 lần cho toàn bộ panel**, không
  xoay/mirror riêng từng board). Board Origin/W/H của từng instance
  (STEP 0.4) **vẫn bắt buộc dùng** cho việc dò offset bằng GTP/GBP
  (STEP 3B) — chế độ Panel Origin không thay đổi cách match pad, chỉ
  thay đổi gốc/kích thước dùng ở bước dịch, xoay, mirror, kiểm tra
  biên.
- **Chế độ (2) — Board Origin:** mỗi instance dùng `board_origin_k`,
  `board_w_k`, `board_h_k` của chính nó (từ STEP 0.4) cho mọi bước sau
  — STEP 4 (dịch offset), STEP 6 (xoay), STEP 7 (mirror), STEP 9
  (kiểm tra biên) đều xử lý **riêng từng instance**, không có bước
  dịch nào dùng Panel Origin. Chỉ dùng khi người dùng chỉ rõ muốn chế
  độ này (ví dụ máy đặt linh kiện định vị theo từng board riêng lẻ,
  mỗi board có fiducial/kẹp riêng).
- Vì STEP 1B (tính Panel Origin/Width/Height) không tốn thêm chi phí
  đáng kể so với STEP 1, nên luôn chạy STEP 1B song song với STEP 1 —
  kể cả khi cuối cùng người dùng chọn chế độ Board Origin — để không
  phải parse lại GKO nếu người dùng đổi ý giữa chừng.
- Ghi lại chế độ đã chọn (kể cả khi dùng mặc định, không được người
  dùng xác nhận rõ) vào sheet "Summary" (STEP 9) để truy vết.

--------------------------------------------------
## 3. STEP 1 — Board Origin từ Gerber (GKO)

1. Đọc `%MOIN*%` hoặc `%MOMM*%` để biết đơn vị. Không đoán — nếu không
   xác định được, dừng lại và báo lỗi.
2. Đọc format toạ độ từ `%FSLAX_Y_*%` (ví dụ `FSLAX24Y24` = 2 số nguyên
   + 4 số thập phân, không có dấu chấm trong chuỗi số).
3. Parse các lệnh toạ độ (`X..Y..D01/D02`) theo kiểu **modal**: nếu một
   dòng chỉ có Y (không có X) thì X giữ nguyên giá trị lần trước, và
   ngược lại. Đồng thời gắn nhãn `layer_name` (giá trị `%LN%` hiện
   hành tại thời điểm đó) cho từng điểm — cần nhãn này để lọc theo
   STEP 0.
4. Quy đổi mọi toạ độ về mm: `1 inch = 25.4 mm`.
5. **Nếu là panel nhiều board (theo STEP 0):**
   - **Kiểu A (step-repeat thật):** Board Outline lấy các điểm có
     `layer_name == sub_block_name` (1 block duy nhất), rồi suy ra
     outline của từng instance k bằng cộng `(k_x*dx, k_y*dy)`.
   - **Kiểu B (nhiều block rời rạc cùng kích thước):** lặp lại việc
     lọc + tính outline **riêng cho từng** `sub_block_name_k` trong
     danh sách instance (STEP 0.4) — mỗi block `.subN` cho ra 1 outline
     độc lập, KHÔNG suy ra bằng cộng dx,dy.
   - Trong cả 2 kiểu: bỏ qua mọi điểm thuộc panel outline block (block
     không có hậu tố `.subN`) khi tính Board Origin.
   - **Nếu là board đơn:** lấy toàn bộ điểm D01/D02 trong file như quy
     trình gốc.
   Board Outline = tập hợp mọi điểm vẽ (D01) và điểm move (D02) tạo
   thành contour khép kín. Bỏ qua text, dimension, tooling mark.
6. **Board Origin[k] = (Xmin, Ymin)** của outline instance k đã lọc ở
   bước 5. Board Width[k] = Xmax − Xmin. Board Height[k] = Ymax − Ymin.
   Với board đơn hoặc panel kiểu A, Width/Height giống nhau cho mọi
   instance (cùng 1 board lặp lại) — với panel kiểu B, tính riêng từng
   instance rồi đối chiếu chúng phải xấp xỉ bằng nhau (đã kiểm tra ở
   STEP 0.2), nhưng vẫn lưu riêng `board_origin_k` cho từng instance vì
   toạ độ tuyệt đối trên panel khác nhau.
7. Không làm tròn giá trị trung gian — chỉ làm tròn ở bước export cuối
   (4 chữ số thập phân, 0.0001 mm).

```python
def parse_gerber_points(path, codes):
    """codes: ('1','2') cho outline vẽ, hoặc ('3',) cho flash pad.
       Tra ve list (x_mm, y_mm, layer_name)"""
    x = y = 0
    cur_name = None
    pts = []
    for line in open(path):
        line = line.strip()
        if m := re.match(r'%LN(.+?)\*%', line):
            cur_name = m.group(1)
        if not (line.startswith('X') or line.startswith('Y')):
            continue
        m = re.match(r'(X(-?\d+))?(Y(-?\d+))?D0?(\d)\*', line)
        if not m:
            continue
        if m.group(2):
            x = int(m.group(2)) / 10000.0   # format 2.4, inch — chinh theo FS thuc te
        if m.group(4):
            y = int(m.group(4)) / 10000.0
        if m.group(5) in codes:
            pts.append((x * 25.4, y * 25.4, cur_name))
    return pts

all_pts = parse_gerber_points('input/gerber/board.GKO', codes=('1', '2'))

def bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys)), (max(xs) - min(xs)), (max(ys) - min(ys))

# STEP 0 da xac dinh danh sach instance: [] neu board don,
# hoac list cac sub_block_name (kieu A: 1 ten + suy ra qua dx,dy;
# kieu B: nhieu ten, moi ten 1 outline doc lap)
instances = {}  # k -> {'origin':(x,y), 'w':.., 'h':.., 'sub_name':str}

if not sub_block_names:                       # board don
    outline = [(x, y) for x, y, name in all_pts]
    origin, w, h = bbox(outline)
    instances[0] = {'origin': origin, 'w': w, 'h': h, 'sub_name': None}
    k = 0   # board don chi co 1 "instance" duy nhat, dat k=0 de dong bo bien ben duoi
elif panel_kind == 'A':                        # step-repeat that
    outline = [(x, y) for x, y, name in all_pts if name == sub_block_names[0]]
    origin0, w, h = bbox(outline)
    for ky in range(ny):
        for kx in range(nx):
            k = ky * nx + kx
            instances[k] = {
                'origin': (origin0[0] + kx * dx_mm, origin0[1] + ky * dy_mm),
                'w': w, 'h': h, 'sub_name': sub_block_names[0],
            }
else:                                          # kieu B: nhieu block roi rac
    for k, name in enumerate(sub_block_names):
        outline = [(x, y) for x, y, nm in all_pts if nm == name]
        origin, w, h = bbox(outline)
        instances[k] = {'origin': origin, 'w': w, 'h': h, 'sub_name': name}

# board_origin/board_width/board_height "hien hanh" dung khi xu ly
# rieng 1 instance k trong cac buoc sau (STEP 2..STEP 8)
board_origin = instances[k]['origin']
board_width  = instances[k]['w']
board_height = instances[k]['h']
```

Kiểm chứng thực tế (panel LENS, kiểu A): sub-block `LENS.gko.sub1` →
`Board Origin = (-2.0015, 0.0000) mm`, `Board Width = 79.9998mm`,
`Board Height = 55.0012mm` — khớp với 1 board đơn, không bị phồng ra
theo kích thước cả panel.

Kiểm chứng thực tế (panel ISP, kiểu B):
- `instances[0]` (từ `ISP.gko.sub1`): `Board Origin = (0.0000, -2.9997)
  mm`, `Board Width = 139.9997mm`, `Board Height = 119.9998mm`.
- `instances[1]` (từ `ISP.gko.sub2`): `Board Origin = (0.0000,
  -74.3778) mm`, `Board Width = 139.9997mm`, `Board Height =
  119.9998mm` — Width/Height khớp với instance 0 (chênh < 0.001mm),
  xác nhận đúng 2 instance của cùng 1 board; `Board Origin` khác nhau
  vì toạ độ tuyệt đối 2 board trên panel khác nhau (không suy ra bằng
  cộng dx,dy vì đây không phải step-repeat thật).

--------------------------------------------------
## 3B. STEP 1B — Panel Origin/Width/Height (mặc định luôn tính khi có panel)

Vì chế độ Panel Origin là mặc định (STEP 0B), bước này **luôn chạy**
mỗi khi STEP 0 xác định có panel (kiểu A hoặc B) — không chỉ khi người
dùng chọn rõ. Chỉ bỏ qua khi người dùng đã xác nhận rõ ràng muốn dùng
chế độ Board Origin.

Dùng **panel outline block** (block không có hậu tố `.subN`, xác định
ở STEP 0) — KHÔNG dùng outline của bất kỳ sub-board nào.

```python
panel_outline = [(x, y) for x, y, name in all_pts if name == panel_block_name]
panel_origin, panel_width, panel_height = bbox(panel_outline)
```

- `panel_origin = (Xmin, Ymin)` của toàn panel — đây sẽ là điểm (0,0)
  của toạ độ xuất ra cuối cùng khi dùng chế độ Panel Origin (mặc định).
- `panel_width`, `panel_height` dùng thay `board_width`, `board_height`
  trong công thức STEP 6 (xoay) và STEP 7 (mirror) khi chế độ Panel
  Origin được dùng — xem lưu ý trong 2 bước đó.
- Board Origin/W/H của từng instance (STEP 1) **không bị thay thế** —
  vẫn dùng cho STEP 3B (dò offset bằng GTP/GBP theo từng board).

Kiểm chứng thực tế (panel ISP): block `ISP.gko` (không suffix) →
`Panel Origin = (-5.0000, -74.3778) mm`, `Panel Width = 149.9997mm`,
`Panel Height = 191.3778mm`.

--------------------------------------------------
## 4. STEP 2 — Đọc PickPlace.xlsx

1. Tự động nhận diện cột: Designator, Layer, X, Y, Rotation (thường có
   dạng "Center-X(mm)", "Center-Y(mm)" — giữ nguyên các cột khác).
2. Tự động nhận diện đơn vị (mm / inch / mil), đối chiếu với độ lớn số
   liệu thực tế (giá trị hàng nghìn → gần chắc chắn là mil, không phải
   mm). Nếu mâu thuẫn → dừng lại, báo xung đột.
3. Quy đổi toàn bộ về mm (1 inch = 25.4mm, 1 mil = 0.0254mm).
4. **Trường hợp panel nhiều board (STEP 0):** xác định PickPlace đang
   ở dạng nào:
   - **Dạng "1 board"** (phổ biến nhất — CPL gốc từ CAD, chưa nhân
     bản theo panel): tổng số dòng ≈ số linh kiện của 1 board, bounding
     box Y xấp xỉ `Board Height`. Đây là trường hợp panel LENS đã kiểm
     chứng (192 dòng, Y span ≈ 48mm so với Board Height 55mm) và panel
     ISP (202 dòng, cho 1 trong 2 board — xem STEP 3C).
     - **Luôn hỏi người dùng mục đích:** (a) chỉ cần offset/kiểm tra
       cho **1 instance cụ thể** (máy đặt linh kiện tự lặp panel), hay
       (b) cần **nhân bản dữ liệu này ra toàn bộ N instance** để xuất
       thành 1 chương trình pick-place cho cả tờ panel (mỗi instance
       có transform riêng — offset + rotation nếu có, xem STEP 3C).
       Trường hợp (b) là tình huống thực tế đã gặp ở panel ISP: PickPlace
       chỉ có 202 dòng (1 board), nhưng panel có 2 board (sub1, sub2)
       cần đặt linh kiện thật — phải chạy STEP 3B/3C riêng cho **từng**
       instance rồi áp transform của instance đó lên **toàn bộ** 202
       dòng gốc, nhân đôi thành 404 dòng kết quả (không phải chỉ chọn
       1 instance gần nhất rồi bỏ qua instance còn lại). Trường hợp (b)
       cũng chính là tình huống mà chế độ Panel Origin (mặc định) phát
       huy tác dụng nhiều nhất — vì kết quả cuối là 1 bảng toạ độ dùng
       chung 1 gốc cho cả tờ panel.
   - **Dạng "cả panel"** (CPL đã export theo toạ độ panel, chứa đủ
     `nx*ny` bản sao): tổng số dòng ≈ (số linh kiện 1 board) × nx × ny,
     và có khoảng trống rõ rệt theo trục lặp khi sort toạ độ (xem cách
     dò gap ở STEP 3B bên dưới) — mỗi cụm ứng với 1 board instance,
     cần tách riêng từng cụm rồi lặp lại STEP 3B→STEP 7 cho từng cụm
     độc lập trước khi gộp lại ở STEP 8.
   - Nếu không chắc chắn → in ra tổng số dòng và bounding box Y, hỏi
     người dùng xác nhận trước khi tiếp tục.

--------------------------------------------------
## 5. STEP 3 — Ước lượng Offset ban đầu (bounding-box heuristic)

Dùng khi CHƯA có GTP/GBP, hoặc để làm điểm khởi tạo cho STEP 3B. Áp
dụng cho **1 board instance** (đã xác định ở STEP 2.4 nếu PickPlace là
dạng "cả panel").

```python
pp_xs = [p.x for p in pickplace_points]
pp_ys = [p.y for p in pickplace_points]
mid_pp = ((min(pp_xs)+max(pp_xs))/2, (min(pp_ys)+max(pp_ys))/2)
mid_board = (board_origin[0] + board_width/2, board_origin[1] + board_height/2)
offset0 = (mid_board[0]-mid_pp[0], mid_board[1]-mid_pp[1])
```

- Nếu bounding box PickPlace (sau khi cộng offset0) đã nằm gọn trong
  board với biên hợp lý → có thể dùng luôn offset0, dừng ở đây.
- Nếu độ lệch lớn / cần độ chính xác cao (< 0.01mm) → bắt buộc làm
  tiếp STEP 3B.

--------------------------------------------------
## 6. STEP 3B — Tinh chỉnh Offset bằng GTP/GBP (khuyến nghị luôn dùng)

**Nguyên tắc quan trọng:** GTP/GBP KHÔNG dùng để tính Board Origin (vẫn
chỉ lấy từ GKO). GTP/GBP chỉ dùng để dò offset chính xác bằng cách đối
chiếu vị trí pad thật với PickPlace.

**Sai lầm cần tránh (board đơn):** so mỗi điểm PickPlace với PAD GẦN
NHẤT (1 pad đơn lẻ) sẽ cho sai số ảo ~0.3–0.5mm, vì tâm linh kiện
(PickPlace) không trùng với vị trí 1 chân pad cụ thể — nó phải so với
**centroid của cả cụm pad** thuộc linh kiện đó.

**Sai lầm cần tránh (panel nhiều board — MỚI):** khi GKO là panel
(STEP 0), file GTP/GBP thường là paste layer của **toàn panel**, có
thể chứa pad của nhiều board instance cùng lúc, trong khi PickPlace
(nếu ở dạng "1 board", xem STEP 2.4) chỉ đại diện cho 1 board. Nếu
KDTree được match với toàn bộ pad panel mà không lọc theo instance,
linh kiện gần mép board có nguy cơ bắt nhầm pad của board bên cạnh —
per-component offset khi đó bị trộn giữa 2 "cụm" cách nhau đúng bằng
bước lặp panel (dx, dy), và median cuối cùng có thể tính ra một giá
trị không khớp với board thực nào cả (biểu hiện: sau khi áp offset,
linh kiện coi như nằm "lửng" giữa 2 board trên panel). Ngưỡng lọc
`dist_pad < 8.0mm` trong thuật toán gốc làm giảm rủi ro này nhưng
không loại trừ hoàn toàn — panel có board xếp sát nhau (khoảng cách
giữa 2 board < ~16mm) vẫn có thể bị match chéo. **Bắt buộc crop tường
minh theo instance** thay vì chỉ dựa vào ngưỡng khoảng cách.

Lưu ý: bước này luôn làm việc trên toạ độ Gerber tuyệt đối gốc của
từng instance (Board Origin/W/H, STEP 1), bất kể chế độ xuất cuối cùng
đã chọn ở STEP 0B là gì — Panel Origin chỉ ảnh hưởng tới bước dịch gốc
sau này (STEP 4B), không ảnh hưởng tới STEP 3B.

**Riêng với layer Bottom:** vì STEP 7 giờ luôn bắt buộc mirror (không
được bỏ qua), tập điểm PickPlace Bottom (`pp` trong code dưới đây)
phải được mirror **trước** khi đưa vào vòng lặp KDTree — dùng công
thức `x_mirrored = RefWidth - x` với `RefWidth` lấy đúng như STEP 7
(`panel_width` ở chế độ Panel Origin, hoặc `board_width` của đúng
instance ở chế độ Board Origin). Offset (và góc xoay, nếu chạy STEP
3C) tìm được từ đây là offset áp dụng lên toạ độ **đã mirror**, khớp
với thứ tự xử lý cuối cùng ở STEP 4 → STEP 4B → STEP 6 → STEP 7.

### Thuật toán (đã kiểm chứng, hội tụ ổn định trong 3–10 vòng lặp):

```python
import numpy as np
from scipy.spatial import cKDTree

def parse_flashes(path, sub_block_name=None):
    pts = parse_gerber_points(path, codes=('3',))
    if sub_block_name:
        # Neu ban than file GTP/GBP cung khai bao layer con theo instance,
        # loc truoc theo ten. Thuong GTP KHONG khai bao lai %LN%, nen buoc
        # loc thuc te se lam o crop_to_instance() ben duoi, theo toa do.
        pass
    return np.array([(x, y) for x, y, name in pts])

def pick_matching_instance(pp_mid_y, ny, dy_mm, board_h_mm):
    """Tu dong chon instance k (0..ny-1) co Y-window gan tam bbox PickPlace nhat.
       Chi can cho truc co step-repeat; truc con lai (I hoac J = 0) khong doi."""
    best_k, best_dist = 0, 1e9
    for k in range(ny):
        window_mid = k*dy_mm + board_h_mm/2
        d = abs(pp_mid_y - window_mid)
        if d < best_dist:
            best_dist, best_k = d, k
    return best_k

def crop_to_instance(gtp_all, k, dy_mm, board_h_mm, margin_mm=5.0):
    """Chi giu pad trong window Y cua instance k (cong voi bien an toan margin)."""
    lo, hi = k*dy_mm - margin_mm, k*dy_mm + board_h_mm + margin_mm
    return gtp_all[(gtp_all[:,1] >= lo) & (gtp_all[:,1] <= hi)]

gtp_all = parse_flashes('input/gerber/top.GTP')   # dung gbp cho layer Bottom
pp  = np.array([(c.x, c.y) for c in pickplace_top_layer])   # mm

offset0 = np.array(offset0)  # tu STEP 3

if is_panel:  # tu STEP 0
    pp_mid_y = (pp[:,1].min() + pp[:,1].max()) / 2 + offset0[1]
    k = pick_matching_instance(pp_mid_y, ny, dy_mm, board_height)
    gtp = crop_to_instance(gtp_all, k, dy_mm, board_height)
else:
    gtp = gtp_all

offset = offset0.copy()

for _ in range(20):
    shifted = pp + offset
    tree = cKDTree(shifted)
    dist_pad, idx_pad = tree.query(gtp)          # moi pad -> PickPlace gan nhat
    keep = dist_pad < 8.0                         # loai pad match sai ro rang

    groups = {}
    for gi, pi in zip(np.where(keep)[0], idx_pad[keep]):
        groups.setdefault(pi, []).append(gtp[gi])

    per_component_offset = np.array([
        np.mean(pts, axis=0) - pp[pi] for pi, pts in groups.items()
    ])

    new_offset = np.median(per_component_offset, axis=0)  # median = chong outlier
    if np.linalg.norm(new_offset - offset) < 1e-8:
        offset = new_offset
        break
    offset = new_offset

# Danh gia do tin cay
resid = per_component_offset - offset
dist_resid = np.linalg.norm(resid, axis=1)
print("Instance:", k if is_panel else "N/A (board don)")
print("Offset:", offset)
print("Median residual (mm):", np.median(dist_resid))   # ky vong < 0.01mm
```

### Kiểm chứng thực tế (panel LENS)

Chạy trên bộ dữ liệu thật (192 linh kiện, 165 TopLayer, GTP panel 82
pad):

| | Không crop (dùng cả 82 pad panel) | Crop instance k=0 (80 pad, loại 2 pad instance k=1) |
|---|---|---|
| offset | (12.9988, 16.9992) mm | (12.9988, 16.9992) mm |
| matched | 43 / 165 | 43 / 165 |
| median residual | 0.00000 mm | 0.00000 mm |

**Kết quả giống hệt nhau** trong trường hợp cụ thể này, vì 2 pad thuộc
instance k=1 nằm cách cụm chính (instance k=0) tới ~38mm — vượt xa
ngưỡng lọc `dist_pad < 8.0mm` nên tự động bị loại dù không crop. Điều
này **không có nghĩa bước crop là thừa**: đây là may mắn của panel
LENS vì khoảng trống giữa 2 board (~38–56mm) đủ lớn. Với panel có
board xếp sát nhau hơn (khoảng cách giữa 2 board < 16mm, tức 2× ngưỡng
8mm), việc không crop sẽ gây match chéo thật sự. Vì vậy bước crop vẫn
**bắt buộc giữ trong quy trình** như một cơ chế an toàn tường minh,
không phụ thuộc may rủi vào khoảng cách panel cụ thể.

Ghi chú thêm từ dữ liệu thật: chỉ 43/165 linh kiện TopLayer match được
pad trong bán kính 8mm — số còn lại không có paste pad tương ứng trong
GTP (linh kiện dùng chân hàn kiểu khác, hoặc GTP không xuất paste cho
toàn bộ linh kiện). Đây là tình huống bình thường, không phải lỗi:
offset vẫn được suy ra ổn định từ 43 linh kiện match được, và các linh
kiện không match sẽ được liệt kê ở sheet "Khong_Khop" (STEP 9).

### Diễn giải kết quả:

- **Dùng MEDIAN (không dùng mean)** của `per_component_offset` để suy
  ra offset cuối — median chống nhiễu tốt hơn nhiều so với mean, vì
  luôn có một tỷ lệ linh kiện bị ghép cặp sai (footprint lớn, linh kiện
  đặt sát nhau, không có attribute Designator trong Gerber X1 format).
- **Median residual < 0.01mm** → offset toàn cục đã đủ chính xác,
  DỪNG LẠI, dùng offset này cho STEP 4.
- Nếu vẫn còn nhiều linh kiện lệch > 0.1–0.5mm sau khi áp offset cuối:
  đây **không phải lỗi offset toàn cục** (đã được median lọc ra) — mà
  là lỗi ghép cặp cục bộ cho từng linh kiện đó. Liệt kê các linh kiện
  này riêng để kiểm tra thủ công qua overlay (STEP 9), KHÔNG cố "sửa"
  offset toàn cục thêm để chiều theo các điểm lệch cục bộ này.
- **Nếu là panel nhiều board và PickPlace ở dạng "cả panel"** (STEP
  2.4): lặp lại toàn bộ STEP 3B riêng cho từng instance k=0..ny*nx-1,
  mỗi instance có `offset[k]` riêng — KHÔNG dùng chung 1 offset cho cả
  panel, vì sai số cơ khí đặt panel có thể khác nhau nhẹ giữa các vị
  trí trên tờ panel.
- Để loại bỏ hoàn toàn bước ghép cặp phỏng đoán này (đạt chính xác
  tuyệt đối từng linh kiện), Gerber cần ở định dạng **X2** có attribute
  `%TO.C,<designator>*%` gắn theo từng pad — khi đó có thể match trực
  tiếp theo tên linh kiện thay vì suy đoán theo khoảng cách hình học.

--------------------------------------------------
## 6B. STEP 3C — Phát hiện Rotation riêng từng Instance (BẮT BUỘC khi panel nhiều board)

**Sai lầm nghiêm trọng cần tránh:** STEP 3B mặc định chỉ tìm offset
bằng **tịnh tiến thuần tuý** (translation). Nếu 1 board instance trên
panel thực ra được đặt **xoay** (0°/90°/180°/270°) so với board dùng
để tạo PickPlace gốc — tình huống rất phổ biến khi panel hoá 2 board
đối xứng để tiết kiệm diện tích — thì việc chỉ tìm offset tịnh tiến
cho instance đó sẽ luôn cho kết quả **tồi** (match ít, residual lớn,
và nếu vẫn dùng vì "không còn cách nào khác" thì linh kiện sẽ lệch
**đều, có hệ thống**, dễ bị hiểu nhầm là "sai gốc toạ độ" trong khi bản
chất là thiếu phép xoay). Đây chính là nguyên nhân đã kiểm chứng thực
tế trên panel ISP (xem bên dưới).

### Thuật toán: thử cả 4 góc, chọn góc cho residual tốt nhất

```python
def try_rotation(gtp_pts, pp, angle_deg):
    """Xoay pp quanh goc (0,0) theo angle_deg (0/90/180/270), roi chay
       lai vong lap STEP 3B tim offset tinh tien tot nhat cho gia thiet
       xoay nay. Tra ve (offset, n_matched, median_residual)."""
    theta = np.radians(angle_deg)
    R = np.array([[np.cos(theta), -np.sin(theta)],
                  [np.sin(theta),  np.cos(theta)]])
    pp_rot = pp @ R.T
    mid_pp = pp_rot.mean(axis=0)
    mid_gtp = np.array(gtp_pts).mean(axis=0)
    offset0 = mid_gtp - mid_pp
    result = solve_offset_median(gtp_pts, pp_rot, offset0)   # vong lap STEP 3B
    return result  # (offset, n_matched, median_residual) hoac None

best = None
for angle in (0, 90, 180, 270):
    res = try_rotation(gtp_instance_k, pp, angle)
    if res is None:
        continue
    offset, n_matched, resid = res
    # uu tien residual nho VA n_matched cao — mot minh residual khong du,
    # vi goc sai van co the "match" vai diem ngau nhien voi residual nho
    if best is None or (resid < best[3] and n_matched >= best[2] * 0.5):
        best = (angle, offset, n_matched, resid)

chosen_angle, chosen_offset, n_matched, resid = best
```

- Chạy riêng cho **từng instance** trên panel (không giả định mọi
  instance cùng góc xoay — dù thực tế phổ biến nhất là 0° hoặc 180°).
- Tiêu chí chọn góc đúng: **residual median phải nhỏ tương đương mức
  đã kiểm chứng (< 0.01mm)** VÀ **số lượng match phải xấp xỉ số match
  của góc tốt nhất khác** (không chỉ dựa vào residual một mình — góc
  sai vẫn có thể tình cờ match rất ít điểm với residual nhỏ).
- Nếu KHÔNG góc nào cho residual < 0.01mm với số match hợp lý → dừng
  lại, báo cho người dùng (có thể instance đó dùng board khác hẳn, hoặc
  cần kiểm tra thủ công qua overlay).
- Áp dụng phép xoay đã chọn cho **cả toạ độ (X,Y) lẫn Rotation**:
  ```python
  # (x,y) da xoay theo chosen_angle roi cong offset (giu nguyen thu tu:
  # xoay truoc, tinh tien sau — dung cong thuc try_rotation() o tren)
  x_new, y_new = rotate(x, y, chosen_angle) + chosen_offset
  rotation_new = (rotation_original + chosen_angle) % 360
  ```
- Top và Bottom của **cùng 1 instance** có thể có góc xoay khác nhau
  về mặt lý thuyết (do 1 layer bị lỗi export) nhưng trên thực tế nên
  **giống nhau** — nếu STEP 3C ra góc khác nhau giữa Top/Bottom của
  cùng 1 instance, dừng lại và báo nghi ngờ thay vì áp dụng luôn.

### Kiểm chứng thực tế (panel ISP, 2 board):

| Instance | Layer | Góc thử | Matched | Residual (mm) | Kết luận |
|---|---|---|---|---|---|
| sub1 | Top | 0° | 36/172 | 0.0002 | **chọn 0°** |
| sub1 | Bottom | 0° | 26/30 | 0.0000 | **chọn 0°** |
| sub2 | Top | 0° | 23/172 | 1.9400 | loại (residual quá lớn) |
| sub2 | Top | 180° | 36/172 | 0.0002 | **chọn 180°** |
| sub2 | Bottom | 180° | 26/30 | 0.0000 | **chọn 180°** |

Kết quả: `sub1` không xoay, offset `(15.0012, 1.9990) mm`; `sub2` xoay
**180°**, offset `(124.9985, 40.6232) mm` — cùng 1 offset cho cả Top
và Bottom của mỗi instance. Đúng với quan sát trực quan trên ảnh
CAM350: board thứ 2 trên panel bị lật ngược nhãn linh kiện (MAIN, PWR
INPUT đọc ngược) so với board 1. Lưu ý: kết quả offset Bottom ở đây
được fit trên toạ độ Bottom gốc (chưa mirror) — theo quy tắc hiện tại
(STEP 7 luôn bắt buộc mirror), số liệu này cần fit lại trên toạ độ đã
mirror trước, xem lưu ý STEP 7.

### Diễn giải kết quả:

- Đây là lý do phổ biến nhất khiến kết quả "lệch đều 1 khoảng cố định"
  khi debug bằng mắt qua overlay CAM350 dù offset tịnh tiến đã tính
  đúng cho 1 instance — nếu bỏ qua STEP 3C, instance còn lại (bị xoay)
  sẽ luôn sai một cách hệ thống bất kể offset tính lại bao nhiêu lần.
- Không nên "cứng hoá" giả định chỉ có 0°/180° — panel có thể dùng
  90°/270° tuỳ cách sắp xếp tối ưu diện tích, luôn thử đủ cả 4 góc.
- Nếu người dùng đã biết trước góc xoay của từng instance (ví dụ nhìn
  bằng mắt qua ảnh CAM350 như panel ISP), có thể bỏ qua vòng lặp thử 4
  góc và chỉ định thẳng góc đó — nhưng vẫn nên chạy lại STEP 3B với góc
  đã cho để xác nhận residual < 0.01mm trước khi tin dùng.

--------------------------------------------------
## 7. STEP 4 — Áp dụng Offset (+ Rotation riêng instance nếu có — STEP 3C)

```python
# instance khong xoay (chosen_angle == 0): tinh tien thuan tuy nhu cu
Xnew = Xoriginal + OffsetX
Ynew = Yoriginal + OffsetY
RotationNew = RotationOriginal

# instance co xoay (chosen_angle tu STEP 3C, vi du 180):
Xr, Yr = rotate(Xoriginal, Yoriginal, chosen_angle)   # quanh goc (0,0)
Xnew = Xr + OffsetX
Ynew = Yr + OffsetY
RotationNew = (RotationOriginal + chosen_angle) % 360
```

- Nếu STEP 3C không phát hiện panel nào bị xoay (mọi instance đều
  `chosen_angle = 0`, trường hợp phổ biến với panel step-repeat thật
  kiểu A) → công thức thu gọn về đúng bản gốc: chỉ tịnh tiến, không
  xoay, không mirror, không scale.
- Giữ nguyên khoảng cách tương đối giữa các linh kiện **trong cùng 1
  instance**.
- Nếu PickPlace có cả layer Bottom: xử lý riêng bằng GBP theo đúng quy
  trình STEP 3B/3C — offset (và góc xoay, nếu có) của Top/Bottom **có
  thể** trùng nhau (đã kiểm chứng thực tế trên panel ISP: trùng nhau
  100%) nhưng **không được giả định luôn trùng** — vẫn phải tính riêng
  và đối chiếu.
- Nếu panel nhiều board và PickPlace ở dạng "cả panel": áp offset
  riêng của từng instance cho đúng nhóm linh kiện thuộc instance đó,
  rồi gộp lại thành 1 bảng kết quả duy nhất.

### STEP 4B — Dịch về gốc chung (mặc định khi có panel — chế độ Panel Origin)

Chạy ngay sau STEP 4, TRƯỚC STEP 5 (hỏi góc xoay). Vì Panel Origin là
chế độ mặc định (STEP 0B), bước này **luôn chạy** khi STEP 0 xác định
là panel — trừ khi người dùng đã chọn rõ chế độ Board Origin, khi đó
bỏ qua bước này hoàn toàn. Sau bước này, mọi instance dùng chung 1 gốc
toạ độ = góc trái–dưới của panel — khác với STEP 4 gốc, nơi mỗi
instance vẫn đang ở toạ độ tuyệt đối của hệ Gerber gốc (chưa dịch về
0,0).

```python
Xfinal = Xnew - panel_origin[0]   # panel_origin tu STEP 1B
Yfinal = Ynew - panel_origin[1]
```

- Áp dụng cho **mọi linh kiện của mọi instance** cùng lúc, dùng chung
  **1** `panel_origin` duy nhất (không phải `board_origin` riêng từng
  instance) — đây là điểm khác biệt cốt lõi so với chế độ Board Origin.
- Vì offset ở STEP 4 đã tính riêng theo pad thật của từng instance
  (STEP 3B), tương quan vị trí thật giữa các board trên panel được giữ
  nguyên chính xác; bước này chỉ dịch gốc, không làm lệch vị trí tương
  đối giữa các board.
- Chỉ khi người dùng đã chọn rõ chế độ Board Origin ở STEP 0B thì mới
  **bỏ qua bước STEP 4B này hoàn toàn** — coi `Xnew, Ynew` từ STEP 4 là
  toạ độ cuối luôn (mỗi instance vẫn giữ gốc/khoảng lệch tuyệt đối
  riêng của hệ Gerber, không dịch về panel).
- Kiểm chứng thực tế (panel ISP, chế độ Panel Origin): `panel_origin =
  (-5.0000, -74.3778) mm` → mọi component của cả `instance 0` lẫn
  `instance 1` cùng trừ đúng 1 cặp giá trị này; sau STEP 4B, board có
  Ymin nhỏ nhất trên panel (chính là board chứa instance 1, do
  `board_origin[1].y = -74.3778` gần khớp `panel_origin.y`) sẽ có toạ
  độ Y gần 0.

--------------------------------------------------
## 8. STEP 5 — Hỏi góc xoay Panel

Thực hiện SAU KHI đã áp offset (STEP 4/STEP 4B), TRƯỚC bước Mirror
(STEP 7).

Không tự suy đoán góc xoay — **luôn hỏi người dùng trước khi xử lý**:

> "Bạn muốn xoay panel/board một góc bao nhiêu? 0° hay 90°?"

- Mặc định (không xoay) là **0°** — nếu người dùng không cần xoay,
  bỏ qua STEP 6, đi thẳng tới STEP 7 (Mirror) với toạ độ nguyên trạng
  từ STEP 4/STEP 4B.
- Nếu người dùng chọn **90°** → thực hiện STEP 6.
- Góc xoay áp dụng cho **toàn bộ panel/board** (mọi linh kiện, cả
  TopLayer và BottomLayer) theo cùng 1 góc đã chọn — không xoay lệch
  giữa 2 layer.
- Ghi lại góc đã chọn vào sheet "Summary" (STEP 9) để truy vết.

--------------------------------------------------
## 9. STEP 6 — Áp dụng xoay Panel

Đầu vào: toạ độ `(x, y, r)` đã có offset từ STEP 4 (và STEP 4B, vì đây
là chế độ mặc định khi có panel — coi `Xfinal, Yfinal` là `x, y` trong
công thức dưới đây). `H`, `W` lấy tuỳ chế độ đã chọn ở STEP 0B:

- **Chế độ Panel Origin (mặc định):** `H = panel_height`, `W =
  panel_width` (STEP 1B) — xoay **toàn panel như 1 khối duy nhất**, áp
  dụng công thức dưới đây **1 lần** cho toàn bộ linh kiện của **mọi
  instance** cùng lúc (không xoay riêng từng board quanh gốc cục bộ
  nữa, vì gốc chung đã là panel).
- **Chế độ Board Origin (chỉ khi người dùng chọn rõ):** `H =
  board_height`, `W = board_width` **của từng instance** (STEP 1) —
  xoay riêng từng board quanh gốc cục bộ của chính nó, áp dụng lặp lại
  công thức dưới đây cho từng nhóm linh kiện thuộc từng instance.

Trong cả 2 chế độ: `H, W` lấy **trước khi xoay** (kích thước gốc chưa
xoay).

**0°:** không đổi gì — `x' = x`, `y' = y`, `r' = r`. Bỏ qua phần còn
lại của bước này.

**90°:**

| Layer | x' | y' | Rotation r' |
|---|---|---|---|
| TopLayer | `x' = H − y` | `y' = x` | `r' = r + 90` |
| BottomLayer | `x' = −y` | `y' = W + x` | `r' = r − 90` |

```python
def rotate_90(x, y, r, layer, board_w, board_h):
    layer_norm = layer.strip().lower()
    if layer_norm in ("top", "toplayer"):
        x2 = board_h - y
        y2 = x
        r2 = (r + 90) % 360
    elif layer_norm in ("bottom", "bottomlayer"):
        x2 = -y
        y2 = board_w + x
        r2 = (r - 90) % 360
    else:
        raise ValueError(f"Layer khong xac dinh: {layer}")
    return x2, y2, r2

for c in components:
    if rotation_angle == 90:
        # origin_mode == 'panel' (mac dinh) -> dung panel_width/panel_height
        # (STEP 1B), ap dung 1 lan cho MOI component thuoc MOI instance.
        # origin_mode == 'board' (chi khi nguoi dung chon ro) -> dung
        # board_width/board_height CUA DUNG instance ma component do
        # thuoc ve (moi instance mot cap W,H).
        w = panel_width if origin_mode == 'panel' else instances[c.instance_k]['w']
        h = panel_height if origin_mode == 'panel' else instances[c.instance_k]['h']
        c.x, c.y, c.rotation = rotate_90(c.x, c.y, c.rotation, c.layer, w, h)
    # rotation_angle == 0 -> khong doi
```

Lưu ý:
- Công thức TopLayer và BottomLayer **khác nhau** — không dùng chung 1
  công thức cho cả 2 layer, vì Bottom được nhìn từ mặt dưới nên phép
  xoay kèm theo phản chiếu trục khác với Top.
- Sau khi xoay 90°, **bounding box đổi chiều**: chiều rộng mới của
  panel/board = `H` cũ, chiều cao mới = `W` cũ. Nếu STEP 7 (Mirror)
  chạy sau bước này và cần `RefWidth` để mirror, phải dùng giá trị
  đã hoán đổi tương ứng — xem lưu ý trong STEP 7.
- Chỉ xoay **một lần** theo đúng góc người dùng chọn ở STEP 5 — không
  lặp lại bước này nhiều lần trên cùng dữ liệu, nếu không toạ độ sẽ
  xoay chồng thêm 90°/180° ngoài ý muốn.
- Áp dụng xoay cho **mọi linh kiện** (Top và Bottom) cùng lúc, dùng
  cùng 1 góc đã chọn ở STEP 5, KHÔNG xoay riêng lẻ từng layer theo góc
  khác nhau.
- Nếu panel nhiều board (STEP 0) và PickPlace ở dạng "cả panel":
  - **Chế độ Panel Origin (mặc định):** áp dụng xoay 1 lần cho toàn bộ
    linh kiện của mọi instance với `H, W` là kích thước **cả panel** —
    các board xoay cùng nhau như 1 tờ cứng, KHÔNG xoay riêng từng board
    quanh gốc cục bộ của nó (nếu làm vậy sẽ phá vỡ tương quan vị trí
    giữa các board trên panel, vì mỗi board sẽ "xoay tại chỗ" thay vì
    xoay cùng cả tờ quanh 1 tâm chung).
  - **Chế độ Board Origin (chỉ khi người dùng chọn rõ):** áp dụng xoay
    cho từng instance với `H, W` là kích thước của **1 board đơn**
    (không phải cả panel) — vì mỗi board trên panel xoay giống hệt
    nhau quanh gốc cục bộ của chính nó.

--------------------------------------------------
## 10. STEP 7 (Mirror) — Lật toạ độ X cho linh kiện lớp Bottom

Chỉ thực hiện SAU KHI di chuyển gốc toạ độ (STEP 4/STEP 4B) đã thành
công, và SAU KHI đã xử lý xong STEP 5/STEP 6 (xoay panel, nếu có).

**STEP 7 luôn bắt buộc chạy cho mọi linh kiện `Layer` là `Bottom` hoặc
`BottomLayer` — KHÔNG được bỏ qua trong bất kỳ trường hợp nào**, kể cả
khi STEP 3B/3C đã dò offset Bottom bằng GBP thật và residual median đã
đạt < 0.01mm chỉ với tịnh tiến/xoay thuần tuý (không cộng thêm mirror
nào trong mô hình dò offset). Residual thấp trên toạ độ Bottom **chưa
mirror** không phải căn cứ để bỏ qua bước này.

Vì mirror luôn được áp dụng, để offset/rotation tìm được ở STEP 3B/3C
khớp đúng với toạ độ Bottom **sau khi** mirror, việc dò offset bằng
GBP cho layer Bottom phải chạy trên tập điểm PickPlace **đã được
mirror trước** (dùng đúng công thức `RefWidth` ở STEP 7 bên dưới, áp
lên X trước khi đưa vào vòng lặp KDTree của STEP 3B), rồi mới tìm
offset tịnh tiến (và góc xoay ở STEP 3C) trên tập điểm đã mirror đó.
Không fit trên toạ độ Bottom gốc chưa mirror.

Ghi chú lịch sử: kiểm chứng trước đây trên panel ISP (xem STEP 3C)
từng fit trực tiếp trên toạ độ Bottom gốc (chưa mirror) và cho residual
~0.0000mm — theo quy tắc hiện tại, dữ liệu đó cần fit lại trên toạ độ
đã mirror trước khi tin dùng cho pipeline mới; không suy ra "không cần
mirror" chỉ từ một lần fit trên toạ độ chưa mirror.

Chỉ áp dụng cho các dòng có `Layer` là `Bottom` hoặc `BottomLayer`.
Linh kiện `TopLayer` **giữ nguyên**, không đụng vào.

Công thức:

```python
Xmirrored = RefWidth - Xnew   # Xnew là toạ độ đã dịch offset (STEP 4 / STEP 4B)
Ymirrored = Ynew               # Y giữ nguyên, không mirror
```

`RefWidth` tuỳ chế độ đã chọn ở STEP 0B:
- **Chế độ Panel Origin (mặc định):** `RefWidth = panel_width` (STEP
  1B), áp dụng **chung 1 giá trị** cho linh kiện Bottom của **mọi
  instance** — mirror quanh trục dọc của cả panel, không phải của
  từng board.
- **Chế độ Board Origin (chỉ khi người dùng chọn rõ):** `RefWidth =
  board_width` **của đúng instance** mà linh kiện đó thuộc về (mỗi
  instance mirror quanh trục dọc của chính nó).

```python
for c in components:
    if c.layer.strip().lower() in ("bottom", "bottomlayer"):
        ref_w = panel_width if origin_mode == 'panel' else instances[c.instance_k]['w']
        c.x = ref_w - c.x    # c.x lúc này đã là toạ độ sau STEP 4 (/ STEP 4B)
        # c.y không đổi
    # nếu layer là Top/TopLayer -> không làm gì cả
```

Lưu ý:
- `RefWidth` **không bao giờ** lấy từ PickPlace hay GTP/GBP — luôn lấy
  từ GKO (`board_width` theo STEP 1, hoặc `panel_width` theo STEP 1B).
- Chế độ Board Origin: với panel nhiều board dùng cùng 1 loại board,
  mọi instance có `board_width` xấp xỉ nhau nhưng vẫn nên lấy đúng giá
  trị của **đúng instance** đang xử lý (không giả định luôn giống nhau
  tuyệt đối, nhất là panel kiểu B).
- **Nếu đã xoay 90° ở STEP 6:** `RefWidth` dùng trong công thức Mirror
  phải là chiều rộng SAU xoay:
  - Chế độ Panel Origin: dùng `panel_height` gốc (đã hoán đổi) —
    `ref_w = panel_height if rotation_angle == 90 else panel_width`.
  - Chế độ Board Origin: dùng `board_height` gốc (đã hoán đổi vai trò
    với `board_width`) của đúng instance —
    `ref_w = board_height if rotation_angle == 90 else board_width`.
  Dùng nhầm giá trị gốc (chưa hoán đổi) sẽ làm linh kiện Bottom bị
  mirror sai vị trí sau khi đã xoay panel.
- Chỉ mirror **một lần** — không lặp lại bước này nhiều lần trên cùng
  một linh kiện, nếu không toạ độ sẽ quay lại vị trí cũ.
- Không mirror Rotation trong bước này (nếu cần hiệu chỉnh góc xoay khi
  nhìn từ mặt Bottom thì xử lý ở bước khác, không gộp vào công thức
  toạ độ X/Y này).
- Nếu muốn kiểm tra bằng GBP (STEP 3B áp dụng riêng cho Bottom), luôn
  đối chiếu **sau khi đã mirror** ở bước này, không đối chiếu trước.

--------------------------------------------------
## 11. STEP 8 — Xuất kết quả

`output/PickPlace_Fixed.xlsx`
- Giữ nguyên mọi cột gốc (Designator, MPN, Comment, Layer, Rotation...).
- Chỉ cập nhật X, Y.
- Xuất làm tròn 4 chữ số thập phân (0.0001 mm) — không làm tròn 2 chữ
  số, việc đó tự nó có thể gây lệch ~0.005–0.01mm.
- Nếu panel nhiều board và PickPlace gốc ở dạng "cả panel": thêm 1 cột
  phụ `Panel_Instance` (k=0,1,2...) ghi rõ linh kiện thuộc board nào
  trên panel, để dễ đối chiếu khi debug.

--------------------------------------------------
## 11B. STEP 8B — Kiểm tra Rotation (đối chiếu với pad thật)

Chạy SAU STEP 8 (đã có toạ độ cuối cùng), dùng lại các cụm pad đã
match ở STEP 3B để tự kiểm tra xem `Rotation` khai báo trong PickPlace
có khớp với hình dạng pad thật trên Gerber hay không.

**Giới hạn quan trọng — đọc trước khi dùng:** Gerber X1 thông thường
(kể cả GTP/GBP đã kiểm chứng ở đây) **không có marker pin-1** gắn theo
từng pad (cần định dạng X2 với `%TO.C,<designator>*%` hoặc aperture
đánh dấu riêng pad pin-1 mới làm được). Vì vậy **không thể xác định
hướng tuyệt đối "trái/phải/lên/xuống" cho một linh kiện đơn lẻ** một
cách đáng tin cậy chỉ từ hình dạng cụm pad. Phương pháp dưới đây kiểm
tra được thứ khả thi và đã kiểm chứng bằng dữ liệu thật: **tính nhất
quán Rotation giữa các linh kiện cùng Footprint** — nếu đa số linh
kiện cùng loại footprint "khớp" theo 1 hướng mà một vài linh kiện lệch
90°/270° so với số đông, gần như chắc chắn đó là lỗi Rotation thật.

Hai giới hạn cần biết:
- **Không phát hiện được lệch đúng 180°** (linh kiện quay ngược 2 đầu)
  vì trục chính PCA đối xứng qua 180° — chỉ bắt được lệch 90°/270°
  (đổi trục ngang↔dọc).
- **Không phát hiện được lỗi hệ thống** (toàn bộ thư viện Footprint bị
  sai Rotation gốc giống nhau ở mọi instance) — vì phương pháp so sánh
  "nhất quán trong nhóm", cả nhóm sai giống nhau thì vẫn nhất quán.
- Chỉ áp dụng được cho linh kiện có **≥2 pad** match được trong bán
  kính dò của STEP 3B (cần ít nhất 2 điểm mới tính được 1 trục), và
  chỉ đánh giá được cho Footprint có **≥3 linh kiện** khớp pad để có
  đủ mẫu xác định "đa số".

### Thuật toán (đã kiểm chứng thực tế trên panel LENS)

```python
import numpy as np
from collections import defaultdict

def pca_axis_angle_mod180(pts):
    """Goc (do) cua truc chinh cua cum pad, mod 180 (truc doi xung 2 chieu)."""
    pts = np.array(pts)
    if len(pts) < 2:
        return None
    c = pts.mean(axis=0)
    d = pts - c
    cov = np.cov(d.T)
    if cov.shape != (2, 2):
        return None
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, np.argmax(evals)]
    return np.degrees(np.arctan2(major[1], major[0])) % 180

records = []
for pi, matched_pad_pts in groups.items():         # groups: ket qua STEP 3B (component idx -> list pad)
    comp = components[pi]
    if len(matched_pad_pts) < 2:
        continue
    raw_angle = pca_axis_angle_mod180(matched_pad_pts)
    if raw_angle is None:
        continue
    # "go-xoay" cum pad theo Rotation da khai bao -> neu Rotation dung,
    # moi linh kien cung Footprint se cho ra cung 1 "hinh dang chuan hoa"
    derot_angle = (raw_angle - (comp.rotation % 180)) % 180
    records.append({'designator': comp.designator, 'footprint': comp.footprint,
                     'rotation': comp.rotation, 'n_pads_matched': len(matched_pad_pts),
                     'derot_angle': derot_angle})

by_footprint = defaultdict(list)
for r in records:
    by_footprint[r['footprint']].append(r)

suspects = []
for fp, recs in by_footprint.items():
    if len(recs) < 3:
        continue   # khong du mau -> khong danh gia, khong dua vao suspects
    angles = np.array([r['derot_angle'] for r in recs])
    # gom nhom theo boi so 90 do (0/90 cluster) bang cach lay median lam chuan
    median_angle = np.median(angles)
    for r, a in zip(recs, angles):
        diff = min(abs(a - median_angle), 180 - abs(a - median_angle))
        if diff > 30:   # lech > 30 do so voi da so cung Footprint -> nghi ngo
            suspects.append({**r, 'expected_derot_angle_median': round(median_angle, 1),
                              'diff_deg': round(diff, 1)})
```

### Kiểm chứng thực tế (panel)

Chạy trên 43 linh kiện TopLayer đã match pad ở STEP 3B: 36 linh kiện
có ≥2 pad để tính trục; trong đó Footprint `C0402` có 34 mẫu (đủ để
đánh giá "đa số") — **cả 34 mẫu cho `derot_angle = 0.0°` giống hệt
nhau**, không có mẫu nào lệch → 0 linh kiện bị đánh dấu nghi ngờ. Các
Footprint khác trong tập match được đều có < 3 mẫu nên bị bỏ qua (ghi
"không đủ mẫu"), đúng như thiết kế thuật toán — không cố đưa ra kết
luận khi không đủ dữ liệu thống kê.

### Diễn giải kết quả

- `diff_deg` càng gần 90 (không phải gần 30) → càng chắc chắn là lỗi
  Rotation thật (lệch tròn 90°), không phải nhiễu đo đạc.
- `diff_deg` trong khoảng 30–60° mà không rõ rệt quanh 90° → có thể do
  cụm pad match sai (lỗi ghép cặp cục bộ ở STEP 3B) chứ không hẳn lỗi
  Rotation — đối chiếu chéo với sheet "Residual_Chi_Tiet" (STEP 9)
  trước khi kết luận.
- Không đưa các linh kiện "không đủ mẫu" hoặc "< 2 pad match" vào danh
  sách nghi ngờ — liệt kê riêng dưới dạng "không kiểm tra được" để
  người dùng biết phạm vi thực tế của bước kiểm tra này, tránh hiểu
  nhầm "không bị flag = chắc chắn đúng".
- Nếu cần xác định **hướng tuyệt đối** (đúng yêu cầu gốc: 0°=trái,
  90°=lên, 180°=phải, 270°=xuống so với pad) cho từng linh kiện độc
  lập — bắt buộc phải có thêm 1 trong 2 nguồn dữ liệu sau, ngoài phạm
  vi Gerber X1 hiện có:
  1. Gerber **X2** với attribute `%TO.C,<designator>*%` gắn theo từng
     pad, kèm attribute pin/pad-number để xác định đâu là pin-1.
  2. Silkscreen layer (GTO/GBO) có ký hiệu pin-1 (chấm tròn, vát góc)
     đọc được vị trí tương đối so với cụm pad.

--------------------------------------------------
## 12. STEP 9 — Report + Overlay (bắt buộc để kiểm chứng bằng mắt)

`output/Alignment_Report.xlsx` gồm:

**Sheet "Summary":**
- Board Origin, Board Width/Height (từng instance nếu là panel), Offset
  X/Y đã áp dụng.
- **Chế độ gốc toạ độ đã dùng** (STEP 0B): "Panel Origin" (mặc định)
  hay "Board Origin" (chỉ khi người dùng chọn rõ) — ghi rõ liệu chế độ
  này là do người dùng xác nhận hay do dùng mặc định vì không được hỏi
  rõ. Nếu là "Panel Origin": ghi thêm `Panel Origin`, `Panel Width`,
  `Panel Height` (STEP 1B) — đây là gốc/kích thước thực sự dùng để
  xuất toạ độ cuối, xoay, mirror, kiểm tra biên.
- Nếu là panel: thêm kiểu panel (A = step-repeat thật với `nx, ny, dx,
  dy`, hay B = nhiều block rời rạc cùng kích thước) và offset riêng của
  từng instance nếu PickPlace ở dạng "cả panel".
- Phương pháp dò offset (bounding-box hay GTP/GBP cross-correlation).
- Median / mean / max residual.
- **Tổng số linh kiện đã khớp** (tìm được cụm pad tương ứng trong
  GTP/GBP, residual tính được).
- **Tổng số linh kiện không khớp** (không tìm được pad nào trong bán
  kính hợp lệ).
- **Tổng số linh kiện ngoài board** sau hiệu chỉnh.
- Tổng số linh kiện = Số khớp + Số không khớp (đối chiếu lại phải khớp
  tổng số dòng trong PickPlace.xlsx).

**Sheet "Rotation_Nghi_Ngo" (linh kiện có Rotation lệch so với đa số cùng Footprint — kết quả STEP 8B):**

| Designator | Layer | Footprint | Rotation hiện tại | Số pad match | Lệch so với đa số (độ) | Ghi chú |
|---|---|---|---|---|---|---|

- Chỉ liệt kê linh kiện được STEP 8B đánh dấu `diff_deg > 30`. Cột
  "Ghi chú" ghi rõ mức tin cậy: `~90° — nghi ngờ cao` (lệch tròn 90°)
  hay `~30-60° — có thể do match sai, cần soát overlay` (lệch không
  tròn 90°, khả năng lỗi ghép cặp STEP 3B hơn là lỗi Rotation thật).
- Thêm 1 dòng tổng kết cuối bảng: tổng số linh kiện **không kiểm tra
  được** (do <2 pad match, hoặc Footprint có <3 mẫu) — để người dùng
  biết rõ phạm vi bao phủ thực tế của bước kiểm tra này, không nhầm "không
  bị liệt kê" thành "đã xác nhận đúng".
- Nếu không có linh kiện nào nghi ngờ → ghi dòng "(không phát hiện
  linh kiện nào lệch Rotation so với đa số cùng Footprint)".

**Sheet "Khong_Khop" (bảng riêng — linh kiện KHÔNG tìm được pad tương ứng):**

| Designator | Layer | Comment | Original X | Original Y | Corrected X | Corrected Y | Lý do |
|---|---|---|---|---|---|---|---|

- Liệt kê mọi linh kiện mà thuật toán STEP 3B không ghép được với cụm
  pad nào trong bán kính dò (kể cả khi toạ độ sau hiệu chỉnh vẫn nằm
  trong board — vì đây là vấn đề "không xác nhận được", không phải
  "sai vị trí"). Nếu không có → ghi dòng "(không có linh kiện nào
  không khớp)".

**Sheet "Ngoai_Board" / "Ngoai_Panel" (bảng riêng — linh kiện có toạ độ VƯỢT biên):**

| Designator | Layer | Original X | Original Y | Corrected X | Corrected Y | Vượt biên nào? |
|---|---|---|---|---|---|---|

Biên kiểm tra tuỳ chế độ đã dùng ở STEP 0B:
- **Chế độ Panel Origin (mặc định):** sau STEP 4B, mọi toạ độ đã ở hệ
  panel, biên là `[0, PanelWidth] × [0, PanelHeight]` (vì
  `panel_origin` đã bị trừ đi thành gốc 0). Đặt tên sheet là
  "Ngoai_Panel" trong trường hợp này để tránh nhầm lẫn.
- **Chế độ Board Origin (chỉ khi người dùng chọn rõ):** biên là
  `[BoardOriginX, BoardOriginX+BoardWidth] × [BoardOriginY,
  BoardOriginY+BoardHeight]` **của đúng instance** mà linh kiện thuộc
  về, bất kể đã khớp pad hay chưa. Đặt tên sheet là "Ngoai_Board".

Cột cuối ghi rõ vượt biên nào (X < min, X > max, Y < min, Y > max).
Nếu không có → ghi dòng tương ứng.

**Sheet "Residual_Chi_Tiet" (linh kiện đã khớp nhưng lệch nhiều, > 0.1mm):**
- Danh sách Designator, Layer, toạ độ đã hiệu chỉnh, residual — để
  soát thủ công, tách riêng với 2 sheet trên (2 sheet đó chỉ dành cho
  case "không khớp được" hoặc "ra ngoài board/panel", không phải
  residual lớn nhưng vẫn khớp bình thường).

- Chế độ Panel Origin (mặc định): vẽ **1 overlay duy nhất cho cả
  panel** — Panel Outline (đen, từ STEP 1B) làm khung ngoài, Board
  Outline của từng instance (xám, viền trong) để phân biệt ranh giới
  các board, Pad Gerber thật của toàn panel (xanh lá), PickPlace đã
  hiệu chỉnh và dịch về gốc panel (xanh dương) của mọi instance vẽ
  chung trên cùng 1 hệ toạ độ.
- Chế độ Board Origin (chỉ khi người dùng chọn rõ): Board Outline
  (đen, **của 1 board đơn**), Pad Gerber thật từ GTP/GBP (xanh lá, đã
  crop theo instance nếu là panel), PickPlace đã hiệu chỉnh (xanh
  dương) — vẽ riêng theo hệ toạ độ cục bộ từng instance.
- Linh kiện thuộc sheet "Khong_Khop" hoặc "Ngoai_Board"/"Ngoai_Panel"
  → tô đỏ.
- Linh kiện lệch > 0.05mm (nhưng vẫn khớp, vẫn trong biên) → tô vàng.

Thang màu:
- **Xanh dương** — linh kiện khớp, trong biên, residual ≤ 0.05mm.
- **Vàng** — linh kiện khớp, trong biên, residual > 0.05mm.
- **Đỏ** — linh kiện không khớp (Khong_Khop) hoặc vượt biên
  (Ngoai_Board / Ngoai_Panel).



--------------------------------------------------
## QUY TẮC AN TOÀN

- Không sửa/xoá gì trong input/.
- Không ghi đè Gerber gốc hoặc PickPlace.xlsx gốc.
- Không sửa Designator / MPN / Comment.
- Mọi file sinh ra nằm trong output/.
- Board Origin và Panel Origin luôn chỉ lấy từ GKO — không bao giờ suy
  ra từ GTP/GBP hay từ chính PickPlace.
- **Nếu Gerber là panel nhiều board (STEP 0): Board Origin của từng
  instance luôn lấy từ outline của chính sub-board đó (kiểu A: 1 block
  + dx,dy; kiểu B: mỗi block `.subN` riêng), không bao giờ lấy từ
  outline toàn panel. Panel Origin/Width/Height (STEP 1B) chỉ lấy từ
  outline toàn panel, không bao giờ lấy từ outline 1 sub-board.**
- **Panel Origin là chế độ mặc định cho mọi panel nhiều board.** Chỉ
  chuyển sang chế độ Board Origin khi người dùng xác nhận rõ ràng muốn
  vậy — không tự ý chuyển đổi ngược lại giữa chừng.
- **Không được dùng lẫn 2 chế độ trong cùng 1 lần chạy** — đã dùng chế
  độ nào (mặc định Panel Origin hoặc Board Origin do người dùng chọn)
  thì toàn bộ STEP 4B/6/7/9 phải nhất quán theo chế độ đó (không xoay
  theo Panel W/H nhưng lại mirror theo Board W/H, hoặc ngược lại).
- Việc dò offset bằng GTP/GBP (STEP 3B) **luôn luôn** làm riêng theo
  từng board instance và dùng Board Origin/W/H của instance đó để crop
  pad, **bất kể** chế độ xuất cuối cùng là Panel Origin hay Board
  Origin — chế độ Panel Origin không thay đổi cách match pad.
- Khi dò offset bằng GTP/GBP trên panel nhiều board: luôn crop pad
  theo đúng instance đang xử lý (STEP 3B) trước khi match, không dựa
  hoàn toàn vào ngưỡng khoảng cách 8mm để tự lọc nhiễu chéo giữa các
  board.
