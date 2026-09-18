# Exit Radar — chấm điểm rủi ro cấu trúc token DEX

Exit Radar gộp cấu trúc thanh khoản, phân bố holder và dòng tiền ví lớn của một token
DEX thành một điểm 0–100 kèm **bằng chứng tra được** cho từng kết luận: địa chỉ pool, địa
chỉ ví, mã giao dịch và biểu đồ dựng từ dữ liệu thô của CoinMarketCap.

> Đây là bằng chứng cấu trúc, không phải lời khuyên đầu tư.

## Kiến trúc bắt buộc: phải có máy chủ nội bộ

CMC **không** gửi header `Access-Control-Allow-Origin` (đã kiểm chứng bằng thực nghiệm),
nên trình duyệt không thể gọi thẳng `pro-api.coinmarketcap.com`. Vì vậy app chạy theo mô hình:

```
trình duyệt  →  máy chủ nội bộ (127.0.0.1:8787)  →  CoinMarketCap API
```

Key CMC do trình duyệt gửi kèm qua header `X-CMC-Key`, chỉ đi tới `127.0.0.1` — không rời
khỏi máy người dùng.

```bash
python3 exit_radar_server.py            # mở http://127.0.0.1:8787
python3 exit_radar_server.py --selftest # quét thử, in JSON, thoát
CMC_API_KEY=<key> python3 exit_radar_server.py
```

## Ba chế độ dữ liệu

| Chế độ | Cần gì | Chấm được |
|---|---|---|
| Công khai | không cần key | A · B · E |
| Đầy đủ | key CMC Pro | + C · D |
| Dữ liệu mẫu | không cần mạng | fixtures cục bộ |

## Kết quả đo được với dữ liệu thật (BONK, Solana)

Lấy trực tiếp từ `/api/scan` — không phải số minh hoạ:

| Chiều | Điểm | Ghi chú |
|---|---|---|
| A Thanh khoản | 6/30 | 20 pool, pool lớn nhất 36,0% tổng |
| B Phân bố holder | 0/15 | 1.013.436 holder · ~4.100 holder mỗi triệu USD vốn hoá |
| C An toàn hợp đồng | không áp dụng | `dex/security/detail` không nhận tham số công khai |
| D Đòn bẩy & thanh lý | không áp dụng | endpoint phái sinh đòi API key |
| E Dòng tiền ví lớn | 15/15 | mẫu 60 lệnh · cửa sổ 2,2 phút · 41 lệnh gắn cờ bundle/bot |

Độ phủ **60%** (3/5 chiều). Dưới 50% hệ thống **không** đưa ra điểm — thà nói "không đủ
dữ liệu" còn hơn dựng một điểm trông chắc chắn hơn thực tế.

## Giới hạn đã biết — ghi rõ, không giấu

- **Chiều E là mẫu, không phải tổng 24h.** `/v1/dex/tokens/transactions` chỉ trả ~20 lệnh
  mỗi trang. Hệ thống phân trang 3 trang, nhưng với token sôi động cửa sổ thực chỉ vài phút.
  Giao diện hiện thẳng cửa sổ thời gian thật của mẫu.
- **`txId` của CMC là số nội bộ, không phải mã giao dịch.** Chỉ hiện link explorer khi có
  mã giao dịch thật; còn lại hiện số khối.
- **Bảng holder top cần key.** `/v1/dex/holders/list` là POST và bộ ẩn danh trả
  `400 Parameter error`; GET trả `405`. Với key, endpoint này trả địa chỉ ví, % tổng cung,
  số dư, USD đã mua/bán, lãi/lỗ đã thực hiện, nguồn cấp vốn và 4 cờ rủi ro.
- **Hai định nghĩa thanh khoản.** Endpoint sự kiện thay đổi và endpoint pool trả hai con số
  khác nhau; giao diện hiện cả hai và nói rõ chỗ chênh.
- **Hạn mức ẩn danh rất chặt.** 11 request song song là bị `429` ngay, nên tầng thu thập gọi
  tuần tự, giãn nhịp 0,4s và thử lại 3 lần với backoff.

## Tệp

```
exit_radar_server.py      máy chủ nội bộ + cầu nối CMC (chỉ thư viện chuẩn)
exit-radar-app.html       giao diện một tệp tự chứa, 8 màn
docs/exit-radar-spec.md   đặc tả sản phẩm
docs/ke-hoach-du-an-exit-radar.md   kế hoạch 13 module
docs/ux-ui-exit-radar.md  thiết kế UX/UI
docs/bang-theo-doi-sprint-exit-radar.xlsx   bảng theo dõi sprint
```
