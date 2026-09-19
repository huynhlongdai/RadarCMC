# Kit nộp bài — Build with CMC: API Hackathon

## 1. Thông tin định danh

- **Tên dự án:** Exit Radar — chấm điểm rủi ro cấu trúc token DEX
- **Track chính:** AI Agents and Automation
- **Track bổ trợ:** Best Use of CoinMarketCap Agent Hub
- **Một câu giới thiệu:** Một điểm 0–100 cho mỗi token DEX, kèm bằng chứng tra được và số chiều thực
  sự chấm được — và một MCP server để agent AI dùng lại kết luận đó.
- **Repo:** https://github.com/huynhlongdai/RadarCMC
- **Bản chạy thử:** (điền link Vercel sau khi Import lại repo)

## 2. Mô tả ngắn (dùng cho ô mô tả DoraHacks)

> Exit Radar chấm rủi ro cấu trúc cho token DEX trên dữ liệu CoinMarketCap và trả về **một điểm 0–100
> kèm bằng chứng**. Điểm được chuẩn hoá **chỉ trên những chiều thực sự chấm được** — thiếu dữ liệu thì
> chiều đó bị loại, hệ thống nói rõ "chưa đủ dữ liệu" chứ không bịa. Mỗi kết luận gắn với một con số
> thô, một endpoint và link explorer. Kèm theo là **MCP server** (`er_scan`, `er_evidence`,
> `er_marketctx`…) để agent AI gọi thẳng phần kết luận, bổ trợ cho CMC MCP vốn trả dữ liệu thô.

## 3. Vì sao dùng API CMC (không chỉ trang web)

- `dex/search`, `dex/token`, `dex/pairs`, `dex/tokens/transactions`, `dex/token-liquidity`,
  `cryptocurrency/quotes/latest` + `quotes/historical`, `fear-and-greed`, `altcoin-season-index`,
  `global-metrics`, `key/info`.
- Có **xác thực bằng key** và **che giấu lỗi** khi thiếu chiều dữ liệu.
- Keyless Public API **không có CORS** → buộc phải có máy chủ trung gian, và đó cũng là chỗ đặt logic chấm điểm.

## 4. Số liệu cần nêu khi thuyết trình

| Số | Giá trị thật đo được |
|---|---|
| Token thử | BONK (Solana) |
| Điểm | 22/100 · THẤP |
| Chiều chấm được | 3/5 (60%) — A 6/30, B 0/15, E 15/15 |
| Bằng chứng mở được | 7 mục |
| Cửa sổ mẫu dòng tiền | 60 lệnh trong 2,2 phút, 41 lệnh gắn cờ bundle/bot |
| Chi phí | 8–14 credit mỗi lần quét một token |
| Tool MCP | 7 |

## 5. Kịch bản video demo (90 giây)

1. (0–10s) Mở app, gõ `BONK`, bấm **Kiểm tra**.
2. (10–35s) Chỉ vào điểm 22/100 và **3/5 chiều** — nói rõ vì sao hai chiều bị loại, chỉ vào hộp dẫn chứng.
3. (35–55s) Mở một bằng chứng ra explorer để chứng minh số liệu kiểm chứng được.
4. (55–75s) Mở agent (Claude/Cursor), gọi `er_scan` và `er_evidence` — agent trả lời y hệt con số trên.
5. (75–90s) Chốt: "dữ liệu CMC cần một tầng kết luận, và tầng đó phải nói được nó thiếu gì".

## 6. Checklist trước khi bấm nộp

- [ ] Repo công khai, có `README.md` (đã xong)
- [ ] `docs/nop-bai.md`, `docs/huong-dan-mcp.md` (đã xong)
- [ ] Ảnh chụp: màn kết quả, hộp dẫn chứng, biểu đồ, bot Telegram, agent gọi MCP
- [ ] Video demo ≤ 90 giây, có tiếng
- [ ] Link bản chạy thử (Vercel) — nhớ Import lại repo và đặt `CMC_API_KEY`
- [ ] Ghi rõ giới hạn: chiều C/D chưa chấm được, chiều E là mẫu
- [ ] Nêu credit đã dùng và cách tiết kiệm
- [ ] Gắn thẻ track **AI Agents and Automation** và **Agent Hub**

## 7. Câu hỏi giám khảo có thể hỏi

**"Điểm 22 này có phải là thấp?"** — Không so sánh được với token chấm 5/5 chiều. Con số chỉ có nghĩa
kèm `dimsScored`; đó là lý do hệ thống in cả hai.

**"Sao không dùng Public API cho khỏi cần key?"** — Đã thử: keyless bị cạn hạn mức và `/public-api`
từ chối mọi key hợp lệ (`401 error_code 1001`). Khi có key, hệ thống tự chuyển sang `pro-api`.

**"Agent Hub khác gì MCP của bạn?"** — Agent Hub cho dữ liệu thô và thanh toán x402; MCP của Exit Radar
cho **kết luận đã chấm kèm bằng chứng**. Hai tầng bổ sung, không trùng.

**"Vì sao không dựng lại MCP của CMC?"** — Vì CMC đã có MCP, CLI, skills và x402 chính thức; dựng lại
là lãng phí. Việc còn thiếu là tầng kết luận, nên đó là thứ được làm.

**"Nếu dữ liệu sai thì sao?"** — Mọi số đều có nguồn endpoint + thời điểm; người dùng mở explorer đối
chiếu được. Chỗ nào lấy mẫu thì giao diện ghi rõ là mẫu.
