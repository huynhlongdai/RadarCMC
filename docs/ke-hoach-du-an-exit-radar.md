# Kế hoạch dự án — EXIT RADAR

**Build with CMC: API Hackathon · Track: AI Agents and Automation**
**Hôm nay: 18/09/2026 (thứ Sáu) · Deadline nộp: 30/09/2026 23:59 UTC = 06:59 sáng 01/10 giờ Việt Nam**
**Quỹ thời gian: 13 ngày, trong đó 11 ngày làm việc + 1 ngày nộp + 1 ngày đệm**

Mục tiêu của kế hoạch này: **nộp xong trước deadline ít nhất 36 giờ**, và mọi rủi ro về dữ liệu được phát hiện trong 3 ngày đầu — không phải vào ngày 27.

---

## 1. Phân rã sản phẩm thành module

| # | Module | Trách nhiệm | Không được làm gì |
|---|---|---|---|
| **M1** | Nền tảng | Nạp cấu hình từ `.env`, logging có cấu trúc, phân loại lỗi (`CMCAuthError`, `CMCRateLimit`, `CMCPartialData`), khung CLI | Không chứa logic nghiệp vụ |
| **M2** | CMC Client | Tầng HTTP **duy nhất**: hai chế độ keyless/có key tự động, đúng động từ GET/POST từng endpoint, cache TTL 60s, backoff khi 429, log mọi lời gọi (endpoint, tham số, status, thời gian, cache hit) | Không biết gì về chấm điểm rủi ro |
| **M3** | Models & chuẩn hoá | dataclass nội bộ (`Token`, `LiquidityPoint`, `HolderEntry`, `SecurityFlags`, `WhaleFlow`, `Liquidation`), chuẩn hoá JSON thô → model, phân biệt rõ **thiếu trường** với **giá trị 0** | Không gọi mạng |
| **M4** | Resolver & Collector | `search` → định danh token; nếu mơ hồ thì in danh sách cho người dùng chọn; gom song song 9-14 lời gọi; xử lý lỗi từng phần và tính độ phủ | Không chấm điểm |
| **M5** | Động cơ tín hiệu (A/B/C) | 3 hàm thuần: xu hướng thanh khoản, cô đặc holder, rủi ro hợp đồng | Không gọi mạng, không đọc file |
| **M6** | Phân tích dòng tiền cá mập (E) | Phân tích `holders/list`, `holders/detail`, `holders/trend/list`, `holders/tag_count`, `tokens/transactions` → dòng ròng, phân bố theo nhãn, hướng đi | Không gọi mạng |
| **M7** | Tổng hợp & kết luận | Gộp 5 chiều theo trọng số, tính độ phủ, xếp mức kết luận, chọn và xếp hạng 3 lý do | Không định dạng trình bày |
| **M8** | Watchlist & delta | Lưu mỗi lần quét, phiên bản hoá file, tính và in phần chênh lệch so với lần gần nhất | Không gọi mạng |
| **M9** | Báo cáo | 3 định dạng: terminal, HTML tự chứa (CSS inline, không CDN), JSON | Không chứa logic tính điểm |
| **M10** | CLI | Tham số, luồng chạy, mã thoát, trợ giúp | Mỏng nhất có thể |
| **M11** | Offline & bằng chứng | Chụp response thật vào `fixtures/`, chế độ `--offline` chạy không mạng, dọn `docs/evidence/` | — |
| **M12** | Kiểm thử | Unit test cho M5/M6/M7 (thuần, không cần mạng), test tích hợp có mock cho M2 | Không cần mạng thật |
| **M13** | Tài liệu & hồ sơ nộp | README 7 mục bắt buộc, evidence, kịch bản video, bài post X, mục Originality và Scope | — |

---

## 2. Ước lượng từng tính năng

Đơn vị: **giờ công của agent**. Cột "Rủi ro" là xác suất phải làm lại, không phải độ khó code.

| Module | Tính năng chính | Giờ | Rủi ro | Vì sao rủi ro ở mức đó |
|---|---|---|---|---|
| M1 | Config, logging, phân loại lỗi | 3 | Thấp | Thuần kỹ thuật |
| M2 | HTTP hai chế độ, cache, backoff, log | 6 | Thấp | Đã biết rõ cơ chế |
| M3 | Models + chuẩn hoá | 5 | **Cao** | Phụ thuộc tên trường thật — phải đọc tài liệu và chạy thử |
| M4 | Resolver + collector song song | 5 | Trung bình | Xử lý lỗi từng phần dễ sai |
| M5 | Chiều A/B/C | 6 | Trung bình | Ngưỡng phải hiệu chỉnh trên dữ liệu thật |
| M6 | **Chiều E — dòng tiền cá mập** | 7 | **Cao nhất** | Chưa biết `trend/list` và `tag_count` trả gì; 2 endpoint này cần key |
| M7 | Gộp điểm, độ phủ, kết luận | 4 | Trung bình | Logic độ phủ phải đúng, nếu không sản phẩm mất uy tín |
| M8 | Watchlist + delta | 3 | Thấp | Đơn giản |
| M9 | Terminal + HTML + JSON | 6 | Thấp | HTML một file dễ |
| M10 | CLI | 3 | Thấp | Mỏng |
| M11 | Offline + fixtures + evidence | 3 | Thấp | — |
| M12 | Test suite | 6 | Thấp | Chỉ làm được vì M5/M6/M7 là hàm thuần |
| M13 | README + video + post X | 6 | Trung bình | Video cần người quay thật |
| | **Tổng** | **63** | | |
| | Đệm sửa lỗi tích hợp (~15%) | **10** | | |
| | **Tổng cần** | **73 giờ** | | |

**Phân bổ:** 73 giờ trên 11 ngày ≈ **6,6 giờ/ngày**. Đây là mức bình thường cho một agent chạy liên tục — nhưng phần rủi ro không nằm ở số giờ, nằm ở **hai chỗ chặn bên ngoài**: key API và chất lượng dữ liệu thật.

---

## 3. Phụ thuộc

### 3.1. Sơ đồ phụ thuộc giữa module

```
   [NGƯỜI] đăng ký DoraHacks + email CMC
              │
              ▼  (mở khoá endpoint cần key)
   M1 ──► M2 ──► M3 ──► M4 ──┬──► M5 ──┐
                              │         ├──► M7 ──┬──► M9 ──┐
                              └──► M6 ──┘          ├──► M8  │
                                                   └──► M10 ◄┘
                                                        │
                                          M11 ◄─────────┘
                                          M12 ◄── M5, M6, M7
                                          M13 ◄── tất cả + video
```

### 3.2. Đường găng (critical path)

**M1 → M2 → M3 → M4 → M5 → M7 → M9 → M10 → M11 → M13 → nộp bài**

M6 (chiều E) nằm **ngoài đường găng** — đây là chủ ý. Nếu chiều E thất bại, sản phẩm vẫn nộp được. Đừng bao giờ để module khác biệt chặn đường nộp bài.

### 3.3. Phụ thuộc bên ngoài — thứ có thể chặn cả dự án

| Phụ thuộc | Ai làm | Chặn cái gì | Nếu trễ thì sao |
|---|---|---|---|
| Đăng ký DoraHacks + nộp đúng email tài khoản CMC | **Người** | Key Startup tier → mở `holders/trend/list`, `holders/tag_count`, derivatives | Chiều D + E mất phần nâng cao; vẫn nộp được ở dạng keyless |
| Key API hoạt động | **Người + CMC** | Như trên | Như trên |
| Nhóm endpoint Holder có dữ liệu thật | CMC | Chiều E | Chuyển sang suy luận từ `holders/list` + `trend/list` |
| `liquidity-change/list` có dữ liệu theo chain | CMC | Chiều A | Chuyển sang proxy từ `token/pools` |
| Quay video demo | **Người** | Không nộp được bài | Không có phương án thay thế — mục bắt buộc |
| Đăng bài trên X | **Người** | Không nộp được bài | Không có phương án thay thế — mục bắt buộc |

**Ba việc chỉ con người làm được:** đăng ký tài khoản, quay video, đăng bài X. Ba việc này phải xếp lịch, không thể để agent tự xử lý.

---

## 4. Kế hoạch sprint

### Sprint 1 — "Chạm được dữ liệu thật" · 18-20/09 · 3 ngày

**Mục tiêu:** giải quyết toàn bộ rủi ro dữ liệu **trước khi viết một dòng logic sản phẩm nào**. Đây là sprint quan trọng nhất.

| Việc | Module | Giờ |
|---|---|---|
| **NGƯỜI:** tạo tài khoản CMC, đăng ký DoraHacks, nộp đúng email CMC | — | 0,5 |
| Dựng khung dự án, config, logging, phân loại lỗi | M1 | 3 |
| Viết tầng HTTP hai chế độ, cache, backoff, log | M2 | 6 |
| Đọc tài liệu 14 endpoint: **động từ HTTP và tên trường chính xác** | M3 (chuẩn bị) | 3 |
| Gọi thử toàn bộ endpoint keyless trên 5-10 token, 2 chain; chụp response thật | M11 | 4 |
| Viết báo cáo khảo sát dữ liệu: endpoint nào trả gì, chain nào có gì | M11 | 2 |

**Cổng kiểm soát (sáng thứ Hai 21/09, người duyệt):** phải biết chắc 4 điều:
1. Động từ HTTP đúng của từng endpoint là gì
2. Tên trường thật trong response là gì
3. `holders/trend/list` và `holders/tag_count` trả về những gì → **chiều E có khả thi không**
4. Chain nào có dữ liệu `liquidity-change` tốt

**Nếu cổng này không đạt:** chuyển ngay sang phương án B ở mục 5. Không được bước vào Sprint 2 khi còn mơ hồ về tên trường.

---

### Sprint 2 — "Walking skeleton" · 21-23/09 · 3 ngày

**Mục tiêu:** một lệnh chạy end-to-end ra bản kết luận đọc được, dù mới có 3 chiều.

| Việc | Module | Giờ |
|---|---|---|
| Models + chuẩn hoá dữ liệu | M3 | 5 |
| Resolver + collector song song, xử lý lỗi từng phần | M4 | 5 |
| Ba hàm chấm điểm A/B/C | M5 | 6 |
| Gộp điểm, độ phủ, xếp mức kết luận | M7 | 4 |
| Bản in terminal | M9 | 3 |
| CLI | M10 | 3 |
| Test cho A/B/C | M12 | 3 |

**Cổng kiểm soát (tối thứ Tư 23/09, người duyệt):** chạy `cli.py` trên token thật, ra bản kết luận có 3 lý do kèm số; **có ít nhất 1 token cho điểm thấp**.

**Nếu không đạt:** cắt chiều B xuống mức tối giản, dồn thời gian cho đường găng. Không cắt chiều A.

---

### Sprint 3 — "Khác biệt" · 24-26/09 · 3 ngày

**Mục tiêu:** thêm phần làm nên khác biệt — dòng tiền cá mập và theo dõi chênh lệch.

| Việc | Module | Giờ |
|---|---|---|
| Phân tích dòng tiền cá mập, chiều E | M6 | 7 |
| Chiều D (đòn bẩy) nếu key đã về | M6 | 2 |
| Watchlist + delta | M8 | 3 |
| Chế độ offline + chụp fixtures + dọn evidence | M11 | 3 |
| Hoàn thiện test suite | M12 | 3 |
| Đầu ra JSON | M9 | 1 |

**Cổng kiểm soát (sáng thứ Hai 28/09, người duyệt):** chiều E cho **điểm âm trên ít nhất 1 token** (chứng minh nhận diện được tín hiệu tích cực); `--offline` chạy khi ngắt mạng; delta in đúng.

**Nếu key chưa về:** chiều E chạy trên phần keyless (`holders/list`, `holders/detail`), ghi rõ giới hạn trong README. **Nếu vẫn không đủ dữ liệu:** bỏ chiều E, dồn trọng số về A/B/C/D, chuyển phần này vào mục roadmap. Sản phẩm vẫn nộp được.

---

### Sprint 4 — "Đóng gói" · 27-28/09 · 2 ngày

**Mục tiêu:** biến sản phẩm chạy được thành bài nộp.

| Việc | Module | Giờ |
|---|---|---|
| Báo cáo HTML tự chứa | M9 | 2 |
| Viết README đủ 7 mục bắt buộc | M13 | 3 |
| Dọn `docs/evidence/`, kiểm tra không có key trong repo | M13 | 1 |
| **NGƯỜI:** quay video demo 2 phút theo kịch bản | M13 | 1,5 |
| Soạn bài post X kèm `#BuildwithCMC` | M13 | 0,5 |

**Cổng kiểm soát (tối thứ Hai 28/09, người duyệt):** video đã quay xong và upload; README đủ checklist mục 17 của đặc tả; repo sạch key.

**Nếu HTML lỗi:** quay video trên bản in terminal + ảnh chụp. Không được để HTML chặn việc nộp.

---

### Sprint 5 — "Nộp" · 29/09 · 1 ngày · đệm 30/09

| Việc | Ai |
|---|---|
| Push repo, kiểm tra key bằng `git log -p \| grep -i cmc` | Agent |
| Nộp bài trên DoraHacks, chọn track AI Agents and Automation | **Người** |
| Đăng bài X kèm link bài nộp + link video + `#BuildwithCMC` | **Người** |
| Xác nhận bài nộp hiển thị công khai, bấm thử link | Cả hai |
| 30/09: chỉ sửa lỗi nhỏ | Agent |

**Cổng cuối:** có link bài nộp + link post X. Nộp xong trước deadline ít nhất **36 giờ**.

---

## 5. Thang phương án dự phòng

Kích hoạt theo thứ tự khi cổng kiểm soát không đạt. **Không được vượt qua cổng mà không quyết định.**

| Kịch bản | Phương án | Ảnh hưởng tới bài nộp |
|---|---|---|
| `liquidity-change/list` không có dữ liệu tốt | Dùng `token/pools` làm proxy: số pool giảm + thanh khoản tập trung vào 1 pool | Mất tín hiệu mạnh nhất, vẫn dùng được dữ liệu DEX |
| Nhóm Holder không đủ dữ liệu | Chiều E rút xuống dùng `holders/list` + `holders/detail`; ghi rõ là suy luận | Mất nhãn chính thức, giữ được tính năng |
| Key Startup chưa về trước 26/09 | Chạy toàn bộ trên keyless; chiều D và E thành "không áp dụng" | Độ phủ giảm, nhưng sản phẩm vẫn hai chiều và vẫn trung thực |
| Tụt tiến độ nghiêm trọng | Cắt theo thứ tự ở mục 6 | Xem mục 6 |

---

## 6. Thứ tự cắt khi tụt tiến độ

Cắt từ trên xuống. **Bốn thứ cuối cùng không bao giờ được cắt.**

| Thứ tự | Cắt gì | Vì sao cắt được |
|---|---|---|
| 1 | Chiều D (đòn bẩy phái sinh) | Chỉ 10 điểm, lại cần key |
| 2 | Báo cáo HTML | Video quay trên terminal vẫn đủ |
| 3 | Đầu ra JSON | Không ai chấm phần này |
| 4 | Tín hiệu phụ của chiều B | Giữ tín hiệu chính là đủ |
| 5 | Chiều E | Đau, nhưng sản phẩm vẫn còn giá trị |
| — | **KHÔNG CẮT:** chiều A, phần delta watchlist, chế độ offline, README + video | Đây là bốn thứ giám khảo chấm trực tiếp |

---

## 7. Việc chỉ con người làm được — xếp lịch trước

Bốn việc dưới đây không thể giao cho agent. Xếp lịch ngay hôm nay.

| # | Việc | Hạn chậm nhất | Chặn gì nếu trễ |
|---|---|---|---|
| 1 | Tạo tài khoản CMC + đăng ký DoraHacks với **đúng email tài khoản CMC** | 19/09 | Toàn bộ phần cần key |
| 2 | Duyệt ở 3 cổng kiểm soát (21, 23, 28/09) | Theo lịch | Quyết định sai hướng kéo dài |
| 3 | Quay video demo 2 phút | 28/09 | Không nộp được |
| 4 | Nộp bài + đăng X kèm `#BuildwithCMC` | 29/09 | Không nộp được |

**Ghi chú về cuối tuần:** 19-20/09 và 26-27/09 là cuối tuần. Agent vẫn chạy bình thường, nhưng các mốc cần con người duyệt đều được xếp vào **thứ Hai** để anh không bị chặn.

---

## 8. Định nghĩa "xong" của toàn dự án

Dự án xong khi **tất cả** những điều sau đúng:

- [ ] `python cli.py --token <địa chỉ thật> --chain <chain>` chạy và ra bản kết luận
- [ ] Bản kết luận có 3 lý do kèm số, độ phủ dữ liệu, và khối endpoint đã gọi
- [ ] Có ít nhất **1 token điểm thấp** và **1 token chiều E âm** trong bộ demo
- [ ] `--offline` chạy được khi ngắt mạng
- [ ] `pytest` xanh, không cần internet
- [ ] Không có API key trong repo
- [ ] README đủ 7 mục: vấn đề, kiến trúc, cài đặt, endpoints, API gây khó, phương pháp, originality + scope
- [ ] `docs/evidence/` có response thật kèm timestamp
- [ ] Video demo 2 phút đã upload
- [ ] Bài đã nộp trên DoraHacks, track AI Agents and Automation
- [ ] Bài post X kèm `#BuildwithCMC` đã đăng

---

## 9. Tóm tắt một màn hình

| Sprint | Ngày | Mục tiêu | Cổng kiểm soát |
|---|---|---|---|
| 1 | 18-20/09 | Chạm được dữ liệu thật | Sáng T2 21/09 — biết chắc chiều E có khả thi |
| 2 | 21-23/09 | Chạy end-to-end ra kết luận | Tối T4 23/09 — có token điểm thấp |
| 3 | 24-26/09 | Dòng tiền cá mập + delta + offline | Sáng T2 28/09 — chiều E âm trên 1 token |
| 4 | 27-28/09 | Đóng gói: README + video | Tối T2 28/09 — video xong |
| 5 | 29/09 | Nộp | Có link bài nộp + post X |
| Đệm | 30/09 | Chỉ sửa lỗi nhỏ | — |

**Tổng công: 73 giờ · 63 giờ tính năng + 10 giờ đệm.**
**Đường găng không đi qua chiều E** — đây là thiết kế có chủ ý để phần khác biệt không bao giờ chặn được việc nộp bài.
