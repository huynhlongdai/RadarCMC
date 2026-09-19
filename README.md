# Exit Radar — chấm điểm rủi ro cấu trúc token DEX

**Một điểm 0–100 cho mỗi token DEX, kèm bằng chứng tra được và số chiều thực sự chấm được.**

Exit Radar gộp cấu trúc thanh khoản, phân bố holder và dòng tiền ví lớn thành một điểm duy nhất,
nhưng không bao giờ giấu phần thiếu: mỗi kết quả đi kèm `dimsScored/dimsTotal`, danh sách địa chỉ
pool, địa chỉ ví, số khối và biểu đồ dựng từ dữ liệu thô của CoinMarketCap.

> Đây là bằng chứng cấu trúc, không phải lời khuyên đầu tư.

---

## 1. Vấn đề và cách giải quyết

Người mua token DEX có ba câu hỏi, và cả ba đều không được trả lời bởi bảng giá:

1. Thanh khoản có thật, hay chỉ một pool mỏng do chính dev bơm vào?
2. Holder tập trung tới mức nào, và có dấu hiệu bundle/bot không?
3. Dòng tiền ví lớn đang vào hay đang rút?

Exit Radar trả lời bằng một điểm 0–100 **có thể kiểm chứng ngược**: mỗi lý do đều gắn với một con số
lấy từ một endpoint cụ thể, và giao diện cho phép mở thẳng explorer để tự đối chiếu.

## 2. Ba điểm khác biệt

| Điểm khác biệt | Cách làm |
|---|---|
| **Không bao giờ bịa điểm** | Chiều nào thiếu dữ liệu bị **loại khỏi công thức**, không tính là 0. Điểm chỉ được đưa ra khi chấm được ≥ 50% trọng số |
| **Bằng chứng là công dân hạng nhất** | Mỗi kết luận có hộp dẫn chứng: nguồn endpoint, thời điểm lấy, giá trị thô, và link explorer khi có mã giao dịch thật |
| **Dùng được bằng agent** | Kèm **MCP server riêng** (`exit_radar_mcp.py`) trả *kết luận đã chấm điểm*, bổ trợ cho CMC MCP trả *dữ liệu thô* |

## 3. Kiến trúc

```
trình duyệt (exit-radar-app.html)
        │  X-CMC-Key (chỉ đi tới máy của bạn)
        ▼
máy chủ Exit Radar (exit_radar_server.py · 127.0.0.1:8787)
        │  /v1, /v3  (Pro API khi có key)
        ▼
CoinMarketCap API

agent AI  ──stdio──►  exit_radar_mcp.py  ──HTTP──►  máy chủ Exit Radar
```

CMC **không** gửi header `Access-Control-Allow-Origin` (đã kiểm chứng bằng thực nghiệm), nên trình
duyệt không thể gọi thẳng `pro-api.coinmarketcap.com`. Vì vậy luôn có một máy chủ trung gian — chạy
trên máy người dùng hoặc trên Vercel.

## 4. Bắt đầu nhanh

### 4.1 Chạy trên máy (đầy đủ tính năng)

```bash
python3 exit_radar_server.py             # mở http://127.0.0.1:8787
python3 exit_radar_server.py --selftest  # quét thử một token, in JSON rồi thoát
python3 exit_radar_server.py --bot --every 10   # thêm bot cảnh báo Telegram
```

Chỉ cần thư viện chuẩn của Python 3 — không cài gì thêm.

### 4.2 Dùng từ agent AI (MCP)

```bash
python3 exit_radar_mcp.py     # MCP stdio, 7 tool
```

Cấu hình mẫu cho Claude Desktop / Cursor nằm ở `mcp.json`, hướng dẫn đầy đủ ở
[`docs/huong-dan-mcp.md`](docs/huong-dan-mcp.md).

### 4.3 Triển khai Vercel

Import repo → Framework Preset **Other** → để trống Build/Output → đặt biến `CMC_API_KEY`.
Mọi endpoint phải có rewrite trong `vercel.json` (đã có sẵn 11 rewrite); thiếu rewrite thì Vercel
trả `404` dù build thành công.

## 5. Key CMC

Thứ tự ưu tiên: header `X-CMC-Key` (người dùng dán trong web) → biến môi trường `CMC_API_KEY` →
tệp `.data/cmc_key` → không có key (chế độ công khai).

- Bản phát hành này có **key mặc định của hệ thống**: lần chạy đầu, máy chủ tự ghi key vào
  `.data/cmc_key` (quyền `600`, đã nằm trong `.gitignore`).
- **Cảnh báo:** key mặc định nằm trong mã nguồn, nên nếu repo là công khai thì bất kỳ ai đọc mã cũng
  lấy được key. Cách an toàn: đặt repo ở chế độ private, hoặc xoá hằng `CMC_DEFAULT_KEY` trong
  `exit_radar_server.py` và chỉ đặt `CMC_API_KEY` trong biến môi trường.
- Người dùng cuối luôn có thể dán key riêng; key đó chỉ nằm trong trình duyệt và đi tới máy chủ của chính họ.

## 6. Ba chế độ dữ liệu

| Chế độ | Cần gì | Chấm được |
|---|---|---|
| Công khai | không cần key | A · B · E |
| Đầy đủ | key CMC Pro | + C · D (khi gói mở endpoint) |
| Dữ liệu mẫu | không cần mạng | fixtures cục bộ |

## 7. Mô hình chấm điểm

Năm chiều, mỗi chiều 0–100, chuẩn hoá **chỉ trên các chiều chấm được**:

```
score = max(0, round(raw_sum / max_sum_của_các_chiều_áp_dụng * 100))
```

| Mức | Điểm | Màu |
|---|---|---|
| THẤP | 0–24 | `#16C784` |
| ĐỂ MẮT | 25–49 | `#EE8B2A` |
| CAO | 50–74 | `#E4572E` |
| NGHIÊM TRỌNG | 75–100 | `#EA3943` |
| không áp dụng | — | mờ |

Dưới 50% trọng số hệ thống **không** đưa ra điểm — thà nói "không đủ dữ liệu" còn hơn dựng một điểm
trông chắc chắn hơn thực tế.

## 8. Kết quả đo được với dữ liệu thật (BONK, Solana)

Lấy trực tiếp từ `/api/scan`, không phải số minh hoạ:

| Chiều | Điểm | Ghi chú |
|---|---|---|
| A Thanh khoản | 6/30 | 20 pool, pool lớn nhất 36,0% tổng |
| B Phân bố holder | 0/15 | 1.013.436 holder · ~4.100 holder mỗi triệu USD vốn hoá |
| C An toàn hợp đồng | không áp dụng | `dex/security/detail` không nhận tham số công khai |
| D Đòn bẩy & thanh lý | không áp dụng | endpoint phái sinh đòi API key |
| E Dòng tiền ví lớn | 15/15 | mẫu 60 lệnh · cửa sổ 2,2 phút · 41 lệnh gắn cờ bundle/bot |

Độ phủ **60%** (3/5 chiều), điểm **22/100 — THẤP**, kèm 7 bằng chứng mở được trên explorer.

## 9. API của máy chủ

| Endpoint | Việc |
|---|---|
| `GET /api/health` | trạng thái, chế độ dữ liệu, nguồn key, credit còn lại |
| `GET /api/search?q=` | tìm token DEX theo tên/symbol/contract |
| `GET /api/scan?q=` | chấm điểm một token (điểm, chiều, bằng chứng) |
| `GET /api/evidence?q=` | bảng dẫn chứng thô của một token |
| `GET /api/markets` | danh sách thị trường |
| `GET /api/marketctx` | bối cảnh thị trường tổng |
| `GET /api/calls` | số lời gọi CMC và credit đã dùng |
| `GET/POST /api/tg?action=` | trạng thái bot Telegram, mã liên kết, gửi thử |
| `GET /api/cron/tick?secret=` | một vòng quét cho bộ lập lịch |
| `POST /api/telegram` | webhook Telegram (có `X-Telegram-Bot-Api-Secret-Token`) |

## 10. Dùng cùng CMC Agent Hub

Exit Radar **không** thay thế Agent Hub, mà đứng cạnh nó:

| Cần gì | Dùng gì |
|---|---|
| Dữ liệu thô: giá, nến, listings, cặp DEX, phái sinh | CMC MCP · CMC CLI · REST Pro · x402 |
| **Kết luận đã chấm điểm + bằng chứng** | **MCP của Exit Radar** (`er_scan`, `er_evidence`, `er_marketctx`) |
| Không có key, trả theo request | x402: `https://mcp.coinmarketcap.com/x402/mcp` (0,01 USD USDC trên Base) |
| Skill cho agent | `skills/exit-radar-cmc/SKILL.md` trong repo này |

Skill kèm theo còn ghi lại **các bẫy endpoint đã kiểm chứng** (public-api từ chối key, OHLCV bị 403,
`holders/list` lỗi 500, `dex/search` khớp chuỗi con, `pcid` vs `cid`, `txId` là số nội bộ) để agent
không mất lượt gọi vào đó.

## 11. Giới hạn đã biết — ghi rõ, không giấu

- **Chiều E là mẫu, không phải tổng 24h.** `/v1/dex/tokens/transactions` trả ~20 lệnh mỗi trang;
  hệ thống phân trang 3 trang, nhưng với token sôi động cửa sổ thực chỉ vài phút. Giao diện hiện
  thẳng cửa sổ thời gian thật của mẫu.
- **`txId` của CMC là số nội bộ**, không phải mã giao dịch. Chỉ hiện link explorer khi có mã thật.
- **Bảng holder top cần key**; `/v1/dex/holders/list` hiện trả `500 The system is busy` ngay cả khi
  có key — khi đó hệ thống bỏ chiều liên quan và nói rõ lý do.
- **Hai định nghĩa thanh khoản** (endpoint sự kiện thay đổi và endpoint pool) — giao diện hiện cả hai.
- **Chiều C và D chưa chấm được** với gói hiện tại: `security/detail` trả 400, `holders/trend/list`
  trả 403, `token-liquidity/query` trả 400.
- Mỗi lần quét một token tốn khoảng **8–14 credit**; nhịp quét dày sẽ vượt hạn mức tháng.

## 12. Cấu trúc

```
exit-radar-app.html       giao diện một trang (EN/VI/ZH), không build step
exit_radar_server.py      máy chủ dữ liệu + chấm điểm + bot Telegram
exit_radar_mcp.py         MCP server cho agent (stdio, 7 tool)
mcp.json                  cấu hình MCP mẫu
skills/exit-radar-cmc/    skill cho agent (cách dùng app + API CMC)
docs/                     spec, hướng dẫn MCP, kit nộp bài
api/index.py              bundle cho Vercel (sinh tự động)
vercel.json               11 rewrite
```

## 13. Nộp bài

- Track: **AI Agents and Automation** · bổ trợ: **Best Use of CoinMarketCap Agent Hub**
- Kit nộp bài, kịch bản video, checklist: [`docs/nop-bai.md`](docs/nop-bai.md)
- Đặc tả sản phẩm: [`docs/exit-radar-spec.md`](docs/exit-radar-spec.md)

## 14. Giấy phép

MIT. Dữ liệu thuộc CoinMarketCap; sản phẩm không đưa ra lời khuyên đầu tư.
