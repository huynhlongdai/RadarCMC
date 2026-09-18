# Thiết kế UX/UI — EXIT RADAR

**Build with CMC: API Hackathon · Track: AI Agents and Automation**
Phiên bản 1 · 18/09/2026

---

## 0. Một quyết định phải nói trước

Đề bài anh đưa có các mục **đăng ký/đăng nhập, thanh toán, phân quyền người dùng**. Những mục đó **không áp dụng** cho sản phẩm này, và tôi không muốn vẽ ra một hệ thống tài khoản không tồn tại để lấp chỗ trống.

**Exit Radar không có tài khoản, không có đăng nhập, không có thanh toán.** Lý do:

- Người dùng là một cá nhân tra một token trước khi mua. Bắt họ đăng ký là thêm ma sát vào đúng khoảnh khắc họ đang vội.
- Không có dữ liệu người dùng nào cần lưu trên máy chủ. Watchlist lưu cục bộ trong trình duyệt.
- Không có gì để bán. Sản phẩm dự thi, miễn phí.
- Bớt được tài khoản + thanh toán nghĩa là bớt khoảng 15 giờ công, dồn cho phần chấm điểm thật.

Thay vào chỗ đó, tôi thiết kế **ba chế độ dữ liệu** — vì đó mới là thứ thực sự phân quyền cho người dùng ở sản phẩm này, và nó ảnh hưởng trực tiếp tới độ phủ dữ liệu hiển thị trên màn hình.

**Mặt sản phẩm gồm hai thứ dùng chung một lõi:**
1. **Web app một trang** — bề mặt chính, dùng để demo và cho người dùng phổ thông
2. **CLI** — cùng lõi đó, cho người dùng kỹ thuật và làm bằng chứng trong bài nộp

---

## 5.1. Information architecture

### Cấu trúc nội dung

Nội dung chia thành 5 tầng, từ nông tới sâu:

| Tầng | Nội dung | Ai đọc |
|---|---|---|
| 1 | Đầu vào: token, chain | Mọi người dùng |
| 2 | **Kết luận**: điểm 0-100, mức rủi ro, độ phủ dữ liệu | Mọi người dùng, đọc trong 3 giây |
| 3 | **Lý do**: 3 lý do đóng góp nhiều nhất, kèm số | Người muốn biết vì sao |
| 4 | **Chi tiết**: 5 chiều, dòng tiền cá mập, lịch sử so sánh | Người muốn kiểm chứng |
| 5 | **Minh bạch**: endpoint đã gọi, phương pháp, giới hạn, disclaimer | Ban giám khảo, người hoài nghi |

Nguyên tắc chi phối toàn bộ IA: **kết luận trước, bằng chứng sau, minh bạch cuối cùng.** Người dùng không bao giờ phải cuộn để thấy điểm. Ban giám khảo không bao giờ phải tìm cách kiểm chứng.

### Sitemap

Sản phẩm là web app một trang, nhưng vẫn dùng route thật — vì **mỗi kết quả quét phải có URL chia sẻ được**. Giám khảo mở link trong video là thấy đúng kết quả, không phải làm lại thao tác.

```
/                                  Quét token              (trang chính)
/scan/{chain}/{address}            Kết quả quét            (URL chia sẻ được, có thể đánh dấu)
/watchlist                         Danh sách theo dõi      (bảng + chênh lệch)
/watchlist/{chain}/{address}       Lịch sử một token       (biểu đồ điểm theo thời gian)
/settings                          Cài đặt                 (key CMC, chế độ dữ liệu, xoá dữ liệu cục bộ)
/method                            Phương pháp             (công bố ngưỡng 5 chiều)
/evidence                          Nhật ký lời gọi API     (minh bạch)
/about                             Giới hạn & disclaimer
```

Bảy route. Không có route nào bị chặn sau đăng nhập.

### Điều hướng

- **Thanh trên cùng cố định**, 4 mục: *Quét · Theo dõi · Phương pháp · Về sản phẩm*. Mục đang xem được làm nổi bằng cả màu và gạch chân, không chỉ màu.
- **Dưới 640px**: thanh trên chuyển thành **thanh dưới** (bottom bar) — người dùng tra token trên điện thoại, ngón cái với tới đáy màn hình dễ hơn đỉnh.
- Không có menu hamburger. Bốn mục thì không cần giấu.
- Không có breadcrumb. Sâu nhất chỉ hai cấp.

### Phân quyền người dùng

Không có vai trò người dùng. Thay bằng **ba chế độ dữ liệu**, hiển thị công khai bằng badge ở góc trên bên phải:

| Chế độ | Điều kiện | Chiều chấm điểm | Hiển thị |
|---|---|---|---|
| **Công khai** | Mặc định, không cần gì | A, B, C | Badge xám "Công khai · 3/5 chiều" |
| **Đầy đủ** | Người dùng đã dán key CMC trong Cài đặt | A, B, C, D, E | Badge nhấn "Đầy đủ · 5/5 chiều" |
| **Ngoại tuyến** | Người dùng bật, hoặc mất mạng | Theo fixtures đã chụp | Badge hổ phách "Dữ liệu mẫu" |

Lý do thiết kế này: độ phủ dữ liệu là thông tin sống còn của sản phẩm. Người dùng phải luôn biết mình đang đọc kết luận dựa trên 3 chiều hay 5 chiều. Giấu nó đi là biến sản phẩm trung thực thành sản phẩm nói dối.

### Quan hệ giữa các màn hình

```
                    ┌──────────┐
                    │  Quét /  │
                    └────┬─────┘
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        [Chọn token]  [Kết quả]  [Ngoại tuyến]
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        [Theo dõi]   [Phương pháp] [Nhật ký API]
              │
              ▼
        [Lịch sử token] ──► quay lại [Kết quả]
```

Luồng một chiều. Từ kết quả, người dùng có thể lưu vào theo dõi hoặc chạy lại. Không có luồng nào bắt buộc quay về trang chủ.

---

## 5.2. User flow

### Flow 1 — Quét một token (luồng chính)

**Mục tiêu thời gian: dưới 10 giây từ lúc mở trang đến lúc đọc được kết luận.**

1. **Vào `/`** — một ô nhập lớn ở giữa trang, một nút "Kiểm tra". Không có gì khác cạnh tranh sự chú ý.
2. **Nhập** — dán địa chỉ contract, hoặc gõ symbol. Chain tự nhận diện từ địa chỉ; nếu không nhận ra thì để người dùng chọn.
3. **Gợi ý khi gõ** — debounce 300ms, hiện tối đa 6 kết quả, mỗi dòng có tên, chain, thanh khoản, số holder. Người dùng phân biệt được token thật với token nhái ngay ở bước này.
4. **Nếu mơ hồ** — không tự chọn. Hiện danh sách đầy đủ, sắp theo thanh khoản giảm dần, kèm cảnh báo "có nhiều token trùng tên".
5. **Đang chạy** — hiện tiến trình theo nhóm dữ liệu: *Định danh ✓ · Thanh khoản ✓ · Holder ⋯ · Hợp đồng ⋯ · Dòng tiền*. Người dùng thấy hệ thống đang làm gì, và thấy được lời gọi nào đã xong.
6. **Kết quả** — thẻ kết luận trên cùng, 3 lý do ngay dưới, rồi tới các chiều chi tiết.
7. **Hành động trên trang kết quả** — hai nút: **"Theo dõi"** (chính) và **"Chạy lại"** (phụ). Thêm nút phụ "Sao chép liên kết".

### Flow 2 — Tìm kiếm

Không có trang tìm kiếm riêng. Ô nhập trên trang chủ *chính là* ô tìm kiếm. Kết quả gợi ý hiện ngay dưới, người dùng chọn hoặc bấm Enter để quét kết quả đầu.

### Flow 3 — Thực hiện hành động chính

Hành động chính của sản phẩm là **đọc kết luận**. Mọi thứ khác phục vụ nó:

| Bước | Thời gian mục tiêu |
|---|---|
| Vào trang → hiểu sản phẩm làm gì | 2 giây |
| Nhập token → có kết quả | 6 giây |
| Đọc điểm + mức rủi ro | 2 giây |
| Đọc 3 lý do | 10 giây |

Nếu tính năng nào không rút ngắn được một trong bốn dòng trên, nó không thuộc bản này.

### Flow 4 — Thanh toán

**Không có.** Sản phẩm miễn phí, không tài khoản.

**Flow thay thế: nâng lên chế độ đầy đủ.** Người dùng vào *Cài đặt*, dán key CMC Pro vào một ô, bấm "Kiểm tra key". Hệ thống gọi thử một endpoint chỉ có ở tier trả phí và báo kết quả:
- Thành công → badge đổi từ "Công khai · 3/5" sang "Đầy đủ · 5/5", chạy lại token hiện tại
- Thất bại → thông báo rõ lý do (key sai / tier chưa đủ), không lưu key

**Điểm quan trọng phải nói rõ trên giao diện:** key được lưu **trong trình duyệt của người dùng**, không gửi lên máy chủ nào. Ghi thẳng dòng này dưới ô nhập key.

### Flow 5 — Quản lý tài khoản → quản lý theo dõi

Thay cho "quản lý tài khoản":

- **Thêm** — từ trang kết quả, một nút
- **Xoá một** — nút xoá trên dòng, có xác nhận
- **Chạy lại tất cả** — nút ở đầu bảng, chạy tuần tự có thanh tiến trình
- **Xoá toàn bộ dữ liệu cục bộ** — trong Cài đặt, có hộp thoại xác nhận nói rõ không thể hoàn tác

### Flow 6 — Xử lý lỗi và trường hợp ngoại lệ

Đây là phần quyết định sản phẩm trông đáng tin hay không. Tám trường hợp, mỗi trường hợp có thông báo cụ thể và một hành động khắc phục:

| # | Tình huống | Hiển thị | Hành động cho người dùng |
|---|---|---|---|
| 1 | Không tìm thấy token | "Không tìm thấy token này trên {chain}" | Đổi chain, hoặc dán địa chỉ contract |
| 2 | Nhiều token trùng tên | Danh sách chọn kèm thanh khoản + số holder, có cảnh báo | Chọn đúng token |
| 3 | Chạm giới hạn API (429) | "Đang chờ giới hạn API · thử lại sau {n} giây" kèm đếm ngược | Tự thử lại, người dùng không phải làm gì |
| 4 | Thiếu dữ liệu một phần | Vẫn hiện kết quả, kèm badge độ phủ và dòng "chiều không áp dụng" | Bật chế độ đầy đủ |
| 5 | Độ phủ dưới 50% | **Thay hẳn thẻ kết luận** bằng "Không đủ dữ liệu để kết luận" — không hiện điểm | Bật đầy đủ, hoặc thử chain khác |
| 6 | Chưa có key | Badge "Công khai" | Nút "Bật chế độ đầy đủ" |
| 7 | Mất mạng, không có fixtures | Màn hình lỗi có nút "Dùng dữ liệu mẫu" | Chuyển sang chế độ ngoại tuyến |
| 8 | Token quá mới, chưa có pool | "Token chưa có thanh khoản — chưa thể chấm điểm cấu trúc" | Quay lại sau |

Trường hợp 5 là quan trọng nhất. Sản phẩm **thà nói không biết** còn hơn đưa ra một điểm số dựa trên một phần ba dữ liệu. Đây là quyết định thiết kế, không phải quyết định kỹ thuật.

---

## 5.3. Wireframe

Wireframe mức xám, chỉ quan tâm bố cục, thứ tự thông tin và hành động chính. Chưa có màu, chưa có hình ảnh. Xem file `exit-radar-ui.html` — phần "Wireframe" vẽ đủ 4 màn hình.

### Màn 1 — Quét (trạng thái trống)

```
┌──────────────────────────────────────────────┐
│  EXIT RADAR        Quét  Theo dõi  Phương pháp│  ← nav trên
├──────────────────────────────────────────────┤
│                                              │
│              Kiểm tra token DEX              │  ← tiêu đề, 1 dòng
│      trước khi bạn mua nó                    │
│                                              │
│   ┌────────────────────────────┐  ┌───────┐ │
│   │ dán địa chỉ hoặc symbol    │  │Kiểm tra│ │  ← ô nhập + nút, hàng giữa

│   └────────────────────────────┘  └───────┘ │
│                                              │
│   Ví dụ:  BONK   ·   WIF   ·   PEPE          │  ← bấm được
│                                              │
├──────────────────────────────────────────────┤
│  Không phải lời khuyên đầu tư · Nguồn: CMC    │  ← footer
└──────────────────────────────────────────────┘
```

### Màn 2 — Kết quả quét

```
┌──────────────────────────────────────────────┐
│  EXIT RADAR        Quét  Theo dõi  Phương pháp│
├──────────────────────────────────────────────┤
│  BONK · Solana           [Công khai · 3/5]   │  ← định danh + badge chế độ
│  $0,0000231  ·  Thanh khoản $4,2M            │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │   68        CAO      Độ phủ 80%        │ │  ← THẺ KẾT LUẬN (điểm to nhất)
│  │   ────────────────────────────────     │ │
│  │   1  Thanh khoản giảm 34%/24h   +22/30 │ │  ← 3 LÝ DO
│  │   2  Top 10 nắm 61% supply      +17/25 │ │
│  │   3  2 ví nhãn xấu nắm 9%        +6/15 │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  DÒNG TIỀN CÁ MẬP                            │  ← khối riêng, nổi bật nhì
│   Tăng vị thế: 3 ví  ·  Giảm: 7 ví           │
│   Ròng 24h: −$1.180.000  →  đang RÚT RA      │
│                                              │
│  5 CHIỀU                                     │
│   A Thanh khoản   ████████████░░░░  22/30   │  ← thanh đo từng chiều
│   B Holder        █████████░░░░░░░  17/25   │
│   C Hợp đồng      ████████░░░░░░░░  13/20   │
│   D Đòn bẩy       ░░░░░░░░░░░░░░░░  n/a     │
│   E Dòng tiền     ███░░░░░░░░░░░░░  +6/15   │
│                                              │
│  SO VỚI LẦN TRƯỚC (17/09 14:20)              │
│   Điểm 51 → 68  ·  Thanh khoản −18%          │
│                                              │
│  ▸ Endpoint đã gọi (9)                       │  ← thu gọn, mở khi cần
│                                              │
│  [ Theo dõi ]  [ Chạy lại ]  [ Sao chép link]│  ← hành động
├──────────────────────────────────────────────┤
│  Không phải lời khuyên đầu tư                 │
└──────────────────────────────────────────────┘
```

**Thứ tự thông tin, và vì sao:** điểm và mức → 3 lý do → dòng tiền cá mập → 5 chiều → lịch sử → endpoint log. Người dùng mới đọc điểm trước, cần biết *tại sao* ngay sau đó, rồi mới tuỳ nhu cầu đi sâu. Endpoint log để cuối vì nó phục vụ ban giám khảo, không phục vụ người dùng — nhưng phải luôn có mặt.

### Màn 3 — Chọn token khi mơ hồ

```
┌──────────────────────────────────────────────┐
│  ⚠ Có 4 token trùng tên "PEPE"               │  ← cảnh báo trên cùng

│                                              │
│  ○ PEPE      Ethereum   $4,1B   212.004 holder│  ← sắp theo thanh khoản
│  ○ PEPE      Solana     $1,2M     3.140 holder│
│  ○ PEPE 2.0  BNB Chain  $84K        412 holder│
│  ○ Pepe      Base       $12K         97 holder│
└──────────────────────────────────────────────┘
```

Mỗi dòng có đủ dữ liệu để phân biệt token thật với token nhái, ngay trên màn hình chọn.

### Màn 4 — Theo dõi

```
┌──────────────────────────────────────────────┐
│  Theo dõi (5)                  [Chạy lại tất cả]│
├──────────────────────────────────────────────┤
│  TOKEN       CHAIN     ĐIỂM   THAY ĐỔI        │
│  BONK        Solana     68    ▲ +17  ⚠         │  ← mũi tên + % thay đổi
│  WIF         Solana     31    ▼  −4            │
│  PEPE        Ethereum   22    ─   0            │
│  ...                                          │
└──────────────────────────────────────────────┘
```

---

## 5.4. UI Design

### Màu sắc

**Quyết định nền tảng: lấy nguyên ngôn ngữ thị giác của CoinMarketCap.**

Bảng màu không phải do tôi chọn, mà lấy từ hệ thống thiết kế công khai của CMC. Màu nhấn chính là đúng `--c-color-blue: #3861FB` — biến mà chính CMC gọi là `--c-color-official`. Nền tối `#17181B`, nền sáng `#F8FAFD` và `#EFF2F5`. Xám chữ `#616E85` ở bản sáng.

Thang mức rủi ro dùng đúng ngữ nghĩa mà CMC đã dạy người dùng của họ:

| Mức | Màu | Biến CMC |
|---|---|---|
| THẤP | `#16C784` | `--c-color-green-500` |
| ĐỂ MẮT | `#EE8B2A` | `--c-color-orange-500` |
| CAO | `#E4572E` | cam đậm, pha giữa cam và đỏ CMC |
| NGHIÊM TRỌNG | `#EA3943` | `--c-color-red-500` |

**Quy tắc kèm theo, để tránh xung đột nghĩa:** trong crypto, xanh là giá tăng và đỏ là giá giảm. Vì vậy trong Exit Radar, **xanh và đỏ chỉ dành cho mức rủi ro** — mọi biến động giá và thanh khoản hiển thị bằng chữ mono trung tính, không tô màu. Sản phẩm không bao giờ tô màu giá, nên hai màu này giữ được một nghĩa duy nhất.

Màu nhấn: **một màu duy nhất** cho nút chính, link và mục điều hướng đang chọn. Không có màu nhấn thứ hai.

Mặc định **nền tối**, có light mode. Lý do nền tối mặc định: người dùng crypto thường tra token buổi tối, và nền tối làm các con số nổi hơn.

### Typography

- **Font giao diện:** một font sans duy nhất cho toàn bộ chữ. Không dùng quá hai font.
- **Font cho số:** font mono/tabular cho **mọi con số** — số dư, phần trăm, điểm. Chi tiết nhỏ này làm các bảng và thanh đo thẳng cột, khiến sản phẩm trông đáng tin hơn hẳn. Đây là chi tiết tôi khuyên không được bỏ.
- **Thang cỡ chữ:** 12 · 13 · 15 · 17 · 20 · 26 · 34 · 44
- **Điểm số rủi ro là thứ duy nhất được dùng cỡ 44px.** Nếu mọi thứ đều to thì không gì nổi bật.

### Icon

Một bộ icon nét, cùng độ dày nét, cùng kích thước lưới. Icon **chỉ dùng ở**: thanh điều hướng, trạng thái (cảnh báo/thành công), và nút có hành động phá huỷ. Không dùng icon trang trí.

### Component

| Component | Biến thể |
|---|---|
| Nút | Chính · Phụ · Trong suốt · Nguy hiểm · đang tải · vô hiệu |
| Ô nhập | Văn bản · Tìm kiếm · Chọn · có lỗi · vô hiệu |
| Thẻ | Mặc định · Kết luận (4 mức) · Bằng chứng |
| Badge | Chế độ dữ liệu (3) · Độ phủ |
| Thanh đo chiều | Có giá trị · Không áp dụng · Đang tải |
| Điều hướng | Trên (desktop) · Dưới (di động) |
| Hộp thoại | Xác nhận xoá |
| Thông báo nổi | Thông tin · Thành công · Lỗi |
| Bảng | Danh sách theo dõi |
| Trạng thái rỗng | Chưa có gì · Không tìm thấy |
| Khung xương | Đang tải |

### Responsive

Thiết kế **mobile-first**, vì người dùng tra token trên điện thoại trước khi mua.

| Breakpoint | Bố cục |
|---|---|
| < 640px | Một cột · nav thành thanh dưới · nút hành động dính đáy |
| 640-1024px | Một cột rộng · nav trên |
| > 1024px | Hai cột: kết luận bên trái, chi tiết bên phải |

### Trạng thái tương tác

Mỗi component phải định nghĩa đủ: mặc định · rê chuột · nhấn · **tiêu điểm bàn phím** · vô hiệu · đang tải · lỗi · thành công.

Viền tiêu điểm bàn phím **không được xoá** — đây là lỗi phổ biến nhất khi làm dark mode.

### Accessibility

- Tương phản tối thiểu **4.5:1** cho chữ thường, 3:1 cho chữ lớn
- **Không truyền đạt mức rủi ro chỉ bằng màu.** Mọi mức luôn có nhãn chữ ("NGHIÊM TRỌNG") và con số đi kèm. Người mù màu đọc được đầy đủ thông tin.
- Vùng kết quả dùng `aria-live="polite"` để trình đọc màn hình đọc kết quả mới
- Mọi chức năng dùng được chỉ bằng bàn phím
- Vùng chạm tối thiểu 44×44px
- Thanh đo chiều có nhãn chữ, không chỉ độ dài thanh

### Light / dark mode

Có cả hai. Mặc định theo cài đặt hệ thống, có nút chuyển ở góc trên bên phải, lựa chọn được nhớ trong trình duyệt. **Mọi biến màu phải định nghĩa theo cặp** — không được hardcode màu ở bất kỳ component nào.

---

## 5.5. Design system

Toàn bộ định nghĩa dưới dạng CSS custom properties, để đổi theme chỉ cần đổi một khối biến.

### Biến màu

```css
:root {
  /* Bề mặt */
  --bg:            #17181B;
  --surface:       #1D1F24;
  --surface-2:     #24262C;
  --border:        #2E3138;
  --border-strong: #41454E;

  /* Chữ */
  --text:          #FFFFFF;
  --text-muted:    #A6B0C3;
  --text-faint:    #858CA2;

  /* Mức rủi ro */
  --risk-low:      #16C784;   /* lục lam — KHÔNG dùng xanh lá */
  --risk-watch:    #EE8B2A;   /* hổ phách */
  --risk-high:     #E4572E;   /* cam cháy */
  --risk-critical: #EA3943;   /* đỏ gạch, không phải đỏ neon */

  /* Nhấn — chỉ một màu */
  --accent:        #3861FB;
  --accent-text:   #ffffff;

  /* Trạng thái */
  --ok:            #16C784;
  --warn:          #EE8B2A;
  --err:           #EA3943;
}

[data-theme="light"] {
  --bg:            #ffffff;
  --surface:       #F8FAFD;
  --surface-2:     #EFF2F5;
  --border:        #DCE1EA;
  --border-strong: #C7CDD8;
  --text:          #17181B;
  --text-muted:    #616E85;
  --text-faint:    #858CA2;
  --risk-low:      #0B8A5D;
  --risk-watch:    #B4660F;
  --risk-high:     #BE4A18;
  --risk-critical: #C4292F;
  --accent:        #2A4FD0;
}
```

### Biến khoảng cách

Thang 4px, có tên theo bậc chứ không theo pixel — để sau này đổi thang không phải sửa toàn bộ:

```css
--space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
--space-5: 24px;  --space-6: 32px;  --space-7: 48px;  --space-8: 64px;

--radius-sm: 6px;  --radius-md: 10px;  --radius-lg: 16px;
--radius-full: 999px;
```

### Typography

```css
--font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
--font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;

--text-xs:  12px;   --text-sm:  13px;   --text-base: 15px;
--text-md:  17px;   --text-lg:  20px;   --text-xl:   26px;
--text-2xl: 34px;   --text-3xl: 44px;

--leading-tight: 1.2;  --leading-normal: 1.55;

--weight-normal: 400;  --weight-medium: 500;  --weight-bold: 650;
```

Quy tắc dùng: **mọi con số dùng `--font-mono`.** Điểm rủi ro dùng `--text-3xl`. Tiêu đề mục dùng `--text-md`. Nhãn nhỏ dùng `--text-xs` viết hoa, giãn chữ.

### Thư viện component

Mỗi component dưới đây có: mô tả, các biến thể, các trạng thái, và quy tắc dùng. Xem file `exit-radar-ui.html` để thấy chúng được vẽ ra thật.

| Component | Biến thể | Trạng thái |
|---|---|---|
| **Button** | primary · secondary · ghost · danger | default · hover · active · focus-visible · disabled · loading |
| **Input** | text · search · select · có lỗi | default · focus · filled · error · disabled |
| **Card** | default · verdict-low/watch/high/critical · evidence | tĩnh |
| **Badge** | mode-public · mode-full · mode-offline · coverage | tĩnh |
| **Meter** (thanh đo chiều) | có giá trị · không áp dụng | default · animating |
| **Nav** | top (desktop) · bottom (mobile) | default · active |
| **Modal** | confirm | open · closing |
| **Toast** | info · success · error | entering · visible · leaving |
| **Table** | watchlist | default · hover row · empty |
| **Skeleton** | line · card · row | shimmering |

---


---

## 5.6. Nhận diện CMC — quan hệ cộng sinh

Mục tiêu: người chấm của CMC phải cảm thấy sản phẩm này **thuộc về hệ sinh thái của họ**. Không bằng cách bắt chước hình thức, mà bằng cách lấy đúng ngôn ngữ thị giác của họ rồi dùng nó làm nổi bật dữ liệu của họ.

### Bảng đối chiếu biến CMC

| Biến CMC | Giá trị | Dùng ở đâu |
|---|---|---|
| `--c-color-blue` (CMC gọi là `--c-color-official`) | `#3861FB` | Màu nhấn chính: nút, link, nav đang chọn, thanh độ phủ |
| `--c-color-azure` | `#486DF7` | Viền tiêu điểm bàn phím, trạng thái rê chuột |
| `--c-color-green-500` | `#16C784` | Mức THẤP |
| `--c-color-orange-500` | `#EE8B2A` | Mức ĐỂ MẮT, badge dữ liệu mẫu |
| pha giữa cam và đỏ CMC | `#E4572E` | Mức CAO |
| `--c-color-red-500` | `#EA3943` | Mức NGHIÊM TRỌNG, hành động phá huỷ |
| `--c-color-gray-600` | `#616E85` | Chữ phụ bản sáng |
| nền tối · nền sáng | `#17181B` · `#F8FAFD` `#EFF2F5` | Nền hai theme |

Bản sáng dùng biến thể đậm hơn cho bốn mức rủi ro (`#0B8A5D`, `#B4660F`, `#BE4A18`, `#C4292F`) để đạt tương phản tối thiểu 4,5:1 trên nền trắng.

### Năm điểm cộng sinh ngoài màu sắc

1. **Màu nhấn đúng là màu CMC.** Dùng chính `--c-color-official` của họ làm màu hành động. Sản phẩm trông như một phần của hệ sinh thái, không phải một app ngoài cắm vào API.
2. **Ghi công xuyên suốt.** Dòng "Dữ liệu: CoinMarketCap API · n endpoint · cập nhật x giây trước" ở đầu mọi màn hình kết quả, cộng footer ở mọi trang. Không giấu nguồn sau một dòng "powered by" duy nhất.
3. **Mỗi chiều chấm điểm ghi rõ endpoint sinh ra nó.** Chiều A ghi `liquidity-change/list`, chiều E ghi `holders/trend/list`. Đóng góp của CMC hiện ra ở từng bước.
4. **Panel "Phản hồi API" ngay trong sản phẩm.** Đề bài của CMC viết rõ: góp ý về API "đi thẳng tới đội sản phẩm và đáng giá hơn bất kỳ bài nộp nào". Vì vậy sản phẩm tự động tổng hợp ma sát thật từ nhật ký lời gọi — endpoint chậm nhất, trường bị thiếu, endpoint không áp dụng cho token nhỏ — kèm bằng chứng. Đây là món quà hiện diện ngay trong video demo, và nó không thể là ý kiến chủ quan vì số liệu lấy từ nhật ký thật.
5. **Trang Phương pháp dẫn nguồn tài liệu CMC.** Công bố ngưỡng chấm điểm kèm link tới trang tài liệu endpoint tương ứng. Người chấm thấy sản phẩm đọc đúng tài liệu và hiểu đúng API.

### Ranh giới — những gì không được làm

- **Không dùng logo CMC** trong giao diện, README hay video. Dùng màu thương hiệu làm nền tảng thị giác là chuyện khác với dùng logo.
- **Không viết** `đối tác chính thức`, `được CMC bảo trợ`, hay bất cứ câu nào ngụ ý quan hệ chính thức. Sản phẩm là bài dự thi.
- **Không dùng màu CMC để ngụ ý xác nhận.** Màu là ngôn ngữ thị giác, không phải con dấu chứng thực.
- **Ngôn ngữ trung tính khi nêu giới hạn API.** Viết "CMC chưa có endpoint cho NFT" thay vì "API thiếu". Người chấm CMC là đồng nghiệp, không phải bị cáo.

## Tác động lên kế hoạch dự án

Thiết kế này **thay đổi kế hoạch** đã lập, cần nói rõ:

**Thêm:** một module **M14 — Web UI** (giao diện một trang + máy chủ nội bộ phục vụ nó). Ước lượng:
- Dựng khung trang + design tokens: 2 giờ
- Màn Quét + ô tìm kiếm + gợi ý: 3 giờ
- Màn Kết quả + 5 thanh chiều + khối dòng tiền: 4 giờ
- Màn Theo dõi + chênh lệch: 2 giờ
- Cài đặt + 8 trạng thái lỗi: 2 giờ
- Responsive + dark/light + accessibility: 2 giờ
- **Tổng: 15 giờ**

**Bớt:** không có đăng nhập, không tài khoản, không thanh toán, không phân quyền → tiết kiệm khoảng **7 giờ** so với một thiết kế có tài khoản.

**Chênh lệch ròng: +8 giờ.** Lấy từ đâu: cắt đầu ra JSON (−1 giờ), cắt báo cáo HTML tĩnh vì web UI đã thay thế (−2 giờ), và dùng trọn 10 giờ đệm đã tính sẵn (−5 giờ). Vẫn nằm trong ngân sách.

**Điều chỉnh sprint:** M14 chèn vào **Sprint 3** (màn Quét + Kết quả, để có thứ quay video) và **Sprint 4** (Theo dõi + Cài đặt + responsive). Sprint 4 từ 2 ngày thành 3 ngày, lấy từ ngày đệm 30/09 — vẫn nộp trước deadline 24 giờ.
