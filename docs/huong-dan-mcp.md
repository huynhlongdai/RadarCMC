# Dùng Exit Radar từ agent AI (MCP)

Exit Radar có sẵn một **MCP server stdio** để agent gọi thẳng phần *kết luận* của sản phẩm.
Nó bổ trợ cho CMC MCP: CMC MCP trả dữ liệu thô, Exit Radar trả điểm đã chấm kèm bằng chứng.

## 1. Chạy

```bash
python3 exit_radar_server.py     # cửa sổ 1 — máy chủ dữ liệu, 127.0.0.1:8787
python3 exit_radar_mcp.py        # cửa sổ 2 — MCP server, nói chuyện qua stdin/stdout
```

MCP server không tự lấy dữ liệu; nó gọi máy chủ ở trên. Muốn trỏ đi nơi khác thì đặt
`EXIT_RADAR_URL` (ví dụ bản trên Vercel).

## 2. Cấu hình client

`mcp.json` trong repo là bản mẫu:

```json
{
  "mcpServers": {
    "exit-radar": {
      "command": "python3",
      "args": ["/duong/dan/tuyet-doi/exit_radar_mcp.py"],
      "env": {
        "EXIT_RADAR_URL": "http://127.0.0.1:8787",
        "EXIT_RADAR_TIMEOUT": "90"
      }
    }
  }
}
```

- Claude Desktop: gộp vào `claude_desktop_config.json`.
- Cursor / VS Code: gộp vào cấu hình MCP của workspace.
- Dùng `python3` trong `command`; nếu máy dùng `python` thì đổi lại.

## 3. Bảy tool

| Tool | Tham số | Trả về |
|---|---|---|
| `er_health` | — | trạng thái máy chủ, chế độ, **nguồn key**, credit còn lại |
| `er_search` | `q` | token khớp (symbol, tên, contract), chuỗi DEX |
| `er_scan` | `q`, `chain` (tùy chọn) | **điểm 0–100**, mức rủi ro, `dimsScored/dimsTotal`, điểm từng chiều, bằng chứng |
| `er_evidence` | `q` | từng con số thô, nguồn endpoint, thời điểm lấy |
| `er_marketctx` | — | vốn hoá, BTC/ETH chi phối, stablecoin, phái sinh, sợ hãi & tham lam |
| `er_calls` | — | số lời gọi CMC và credit đã dùng cho lần quét gần nhất |
| `er_mcp_vs_cmc` | — | khi nào dùng MCP này, khi nào dùng CMC MCP/x402/REST, và các bẫy endpoint |

## 4. Ví dụ một phiên

```
agent → er_health
      ← {"ok":true,"cmcReachable":true,"keyProvided":true,"keySource":"tệp …/.data/cmc_key","keyValid":true}

agent → er_search {"q":"bonk"}
      ← 20 ứng viên, đúng nhất: BONK · solana · 0x… (kiểm bằng contract, không tin chuỗi con)

agent → er_scan {"q":"0x…"}
      ← score 22/100 (THẤP) · dimsScored 3/5 · A 6/30, B 0/15, E 15/15 · 7 bằng chứng

agent → er_marketctx
      ← bối cảnh thị trường để đặt kết quả vào chỗ đúng
```

## 5. Mẹo dùng đúng

- Luôn đọc `dimsScored/dimsTotal` trước khi so sánh hai token: 3/5 không so được với 5/5.
- Trước khi quét hàng loạt, gọi `er_calls` để biết ngân sách (mỗi token 8–14 credit).
- Nếu `er_scan` trả "không đủ dữ liệu", đừng tự suy diễn — chuyển sang `er_evidence` để xem cái gì thiếu.
- Muốn dữ liệu thô (giá, nến, listings) thì dùng CMC MCP/CLI/REST/x402, không phải MCP này.

## 6. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `khong goi duoc http://…` | máy chủ chưa chạy hoặc sai cổng | chạy `python3 exit_radar_server.py`, kiểm `EXIT_RADAR_URL` |
| `keyProvided: false` | chưa có key ở cả ba nguồn | đặt `CMC_API_KEY` hoặc để máy chủ tự ghi `.data/cmc_key` |
| Kết quả cũ | máy chủ có bộ nhớ tạm theo phiên | quét lại, hoặc khởi động lại máy chủ |
| Tool không hiện trong client | sai đường dẫn tuyệt đối trong `mcp.json` | dùng đường dẫn tuyệt đối tới `exit_radar_mcp.py` |
