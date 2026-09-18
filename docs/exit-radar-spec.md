# EXIT RADAR — Đặc tả sản phẩm dự thi (v2)

**Build with CMC: API Hackathon · Track: AI Agents and Automation · Deadline 30/09/2026 23:59 UTC**

> v2 bổ sung **Lớp cá mập** (dòng tiền ví lớn) theo yêu cầu, và ghi rõ những phần **cố tình không đưa vào** kèm lý do. Đọc hết trước khi viết dòng code đầu tiên.

---

## 1. Sản phẩm là gì, trong một câu

**Exit Radar trả lời hai câu hỏi của một người mới trước khi xuống tiền: "cấu trúc token này có dấu hiệu rút thanh khoản không?" và "có ví lớn nào đang vào hay đang ra không?"**

Tagline dùng trong README và video: *"Giá cho bạn biết chuyện đã xảy ra. Cấu trúc và dòng tiền cho bạn biết chuyện sắp xảy ra."*

### Vì sao chọn ý này

Tính đến 18/09, sự kiện có 19 bài nộp. Trong 5 bài đã đọc kỹ, **không bài nào đụng vào nhóm endpoint DEX**:

| Bài nộp | Nhóm dữ liệu dùng |
|---|---|
| TrendLab Market Structure Map | `listings/latest`, `global-metrics`, `categories`, `altcoin-season-index` |
| CMC-Alpha-Terminal | `listings/latest`, `quotes/latest`, `global-metrics` |
| MarketMind | giá, vốn hoá, volume, dominance, rankings |
| CMC Agent Tools | `quotes/latest`, `listings/latest`, `cryptocurrency/info`, `listings/new` |
| Will RWA Let Me In? | nhóm `real-world-assets` |

Tất cả đều là dữ liệu CEX. Mảng DEX — đặc biệt là **hành vi holder** — đang trống hoàn toàn.

---

## 2. Vấn đề

Người mới mua token trên DEX có hai nỗi sợ, và cả hai đều là câu hỏi về dữ liệu chứ không phải về cảm tính:

**Nỗi sợ 1 — "Cấu trúc có vấn đề gì không?"**
Thứ làm mất tiền hiếm khi là một đợt sập thị trường. Nó là một lối thoát cấu trúc: nhà cung cấp thanh khoản rút pool, top holder xả hàng, hợp đồng còn hàm mint/đổi thuế. Dữ liệu để nhìn thấy trước đều công khai, và nó xuất hiện **trước** khi giá sập.

**Nỗi sợ 2 — "Có ai lớn đang vào không, hay chỉ mình tôi?"**
Người mới không có cách nào biết ví lớn nào đang mua, mua khi nào, khối lượng bao nhiêu, và họ đang giữ hay đã rời đi. Họ chỉ thấy giá — mà giá thì không nói ai đang mua.

Cả hai nỗi sợ này đều trả lời được bằng CMC API. **Nhóm endpoint Holder của CMC là thứ không ai trong 19 bài nộp dùng tới.**

---

## 3. Người dùng

> Người mới, mua token vốn hoá nhỏ trên DEX (Solana, Ethereum, BNB Chain, Base), vị thế 200-5.000 USD, **đã từng bị rug một lần**, giờ muốn kiểm tra trước khi mua và kiểm tra lại những gì đang giữ mỗi ngày. Họ không đọc được chart phức tạp và không biết dùng công cụ chuyên nghiệp.

Ba thời điểm sử dụng:

| Thời điểm | Câu hỏi | Cách dùng |
|---|---|---|
| Trước khi mua | "Con này có dấu hiệu gì bất thường không? Có cá mập nào đang vào không?" | Chạy một lần, đọc verdict |
| Đang giữ | "Từ hôm qua tới giờ có gì thay đổi?" | Chạy lại watchlist, xem delta |
| Nghe ngóng | "Con này có phải chỉ mình tôi mua không?" | Xem khối holder có cô đặc không |

---

## 4. Hai ý tưởng cốt lõi

### 4.1. Chấm điểm cấu trúc, không chấm điểm giá

Và quan trọng hơn: **đo hướng đi, không chỉ trạng thái.** Một ảnh chụp tĩnh nói "top 10 holder nắm 40%" nghe bình thường. Nhưng nếu hôm qua nó là 25%, đó là tín hiệu. Dataset cho biết hướng đi của thanh khoản là `GET /v1/dex/liquidity-change/list` — gần như không ai dùng.

### 4.2. Lớp cá mập — đọc dòng tiền, theo cả hai chiều

Đây là phần bổ sung mới, và nó làm sản phẩm mạnh hơn hẳn: **không phải chỉ cảnh báo rủi ro, mà còn nhận diện tín hiệu tích cực.**

CMC có nguyên một nhóm endpoint Holder cho việc này:

| Endpoint | Cho biết gì |
|---|---|
| `POST /v1/dex/holders/list` | Danh sách holder kèm số dư |
| `POST /v1/dex/holders/detail` | Chi tiết một holder cụ thể |
| `GET /v1/dex/holders/trend/list` | **Xu hướng thay đổi vị thế của holder** |
| `GET /v1/dex/holders/tag_count` | **Đếm holder theo nhãn phân loại** |
| `GET /v1/dex/holders/count` | Tổng số holder |

Và ở nhóm Token có thêm:
| `GET /v1/dex/tokens/transactions` | Danh sách swap — thấy được các giao dịch lớn |

**Điểm mấu chốt:** `holders/tag_count` cho thấy CMC có **phân loại holder theo nhãn**. Nếu nhãn bao gồm các loại như cá mập, sniper, bundler, team, đó chính xác là thứ người dùng cần. **Nhưng danh mục nhãn cụ thể là gì thì phải đọc tài liệu endpoint trước — không được đoán.** Đây là việc đầu tiên agent phải làm ở ngày 20/09.

Cách dùng trong sản phẩm:

- Nhãn kiểu sniper/bundler nắm lớn từ đầu → **tăng** điểm rủi ro (họ mua để bán lại, không phải để nắm giữ)
- Nhãn team/insider còn giữ nhiều → tăng
- Holder lớn **đang giảm** vị thế theo trend → tăng mạnh
- Holder lớn **đang tăng** vị thế, đặc biệt là ví có nhãn đáng tin → **giảm** điểm rủi ro

Đây là điều làm Exit Radar khác mọi công cụ khác: nó **hai chiều**. Một công cụ lúc nào cũng hét rủi ro thì người dùng sẽ bỏ sau ba lần. Một công cụ biết nói "cấu trúc bình thường, và có 4 ví lớn vừa tăng vị thế trong 6 giờ qua" thì người dùng quay lại.

---

## 5. Luồng hoạt động

### Bước 1 — Định danh

Đầu vào: địa chỉ hợp đồng + chain, hoặc symbol.
Dùng `GET /v1/dex/search` để tra token chuẩn. Nếu ra nhiều kết quả, **in danh sách và để người dùng chọn** — không tự đoán. Đoán sai token là lỗi nghiêm trọng nhất trong loại sản phẩm này.

### Bước 2 — Thu thập song song

| Việc cần lấy | Endpoint |
|---|---|
| Chi tiết token | `GET /v1/dex/token` |
| Giá hiện tại | `GET /v1/dex/token/price` |
| Thanh khoản hiện tại | `GET /v1/dex/token-liquidity/query` |
| **Lịch sử thay đổi thanh khoản** | `GET /v1/dex/liquidity-change/list` |
| Danh sách pool | `GET /v1/dex/token/pools` |
| **Cảnh báo bảo mật hợp đồng** | `GET /v1/dex/security/detail` |
| **Danh sách holder** | `POST /v1/dex/holders/list` |
| Số lượng holder | `GET /v1/dex/holders/count` |
| **Chi tiết holder** | `POST /v1/dex/holders/detail` |
| **Xu hướng vị thế holder** | `GET /v1/dex/holders/trend/list` |
| **Nhãn phân loại holder** | `GET /v1/dex/holders/tag_count` |
| **Danh sách swap** | `GET /v1/dex/tokens/transactions` |
| Cặp giao dịch | `GET /v4/dex/spot-pairs/latest` |
| *(tùy chọn, cần key)* Thanh lý theo coin | `GET /v5/derivatives/liquidations/cryptocurrency/list/latest` |

**Cảnh báo kỹ thuật quan trọng:** tài liệu endpoint liệt kê một số endpoint là **POST**, trong khi trang Keyless Public API liệt kê cùng endpoint đó là **GET**. Ví dụ `holders/list`. Vì vậy agent **phải kiểm tra động từ HTTP của từng endpoint trong tài liệu trước khi code**, và code phải xử lý được cả trường hợp keyless chỉ nhận GET. Không được đoán.

Tài liệu cần đọc trước khi viết phần parse:
- `https://coinmarketcap.com/api/documentation/pro-api-reference/token`
- `https://coinmarketcap.com/api/documentation/pro-api-reference/holder`
- `https://coinmarketcap.com/api/documentation/pro-api-reference/derivatives`
- Bản dump toàn bộ: `https://pro.coinmarketcap.com/llms-full.txt`

**Quy tắc bắt buộc:** mở tài liệu của từng endpoint để đọc **tên trường chính xác**. Không đoán tên trường.

### Bước 3 — Chấm điểm 5 chiều

Xem mục 6. Toàn bộ hàm chấm điểm phải là **hàm thuần**: nhận dict, trả dict, không gọi mạng bên trong.

### Bước 4 — Giải thích

Xuất ra **đúng 3 lý do**, xếp theo mức đóng góp, mỗi lý do **kèm số cụ thể**. Cấm trả về một con số trống không lý do.

### Bước 5 — Ghi nhận và so sánh

Lưu mỗi lần quét vào `watchlist.json`. Lần sau in ra delta so với lần gần nhất.

### Bước 6 — Xuất kết quả

Terminal (bản in gọn) · `--json` (cho agent khác) · `--html` (một file tự chứa, CSS inline, không CDN).

---

## 6. Mô hình chấm điểm — công bố công khai

Viết mục này rõ ràng trong README. Giám khảo cần thấy có quy tắc, không phải cảm tính.

**Tổng điểm rủi ro: 0-100, cộng từ 5 chiều. Chiều E có thể mang giá trị âm.**

### A. Xu hướng thanh khoản — tối đa 30 điểm

- Mức giảm thanh khoản 24h và 7d
- Không giảm → 0 điểm; giảm càng sâu điểm càng cao, tuyến tính
- Giảm ≥ 50% trong 24h → chạm trần 30
- **Tín hiệu phụ:** ≥ 90% thanh khoản nằm trong một pool duy nhất → cộng thêm. Rút một pool là token chết hoàn toàn.

### B. Cô đặc holder — tối đa 25 điểm

- Tỷ lệ supply do top 10 holder nắm giữ (loại trừ địa chỉ burn/locked nếu nhận diện được, và **ghi rõ đã loại gì**)
- Top 10 ≥ 70% → chạm trần 25; từ 70% xuống 30% → giảm tuyến tính về 0
- **Tín hiệu phụ:** số holder giảm theo thời gian. Cẩn thận — có thể do gộp địa chỉ, nên chỉ tính là tín hiệu phụ.

### C. Rủi ro hợp đồng — tối đa 20 điểm

Đếm cờ đỏ từ `security/detail`: honeypot, quyền mint còn mở, chưa từ bỏ quyền sở hữu, đổi được thuế chuyển nhượng, có hàm blacklist, hợp đồng nâng cấp được. Honeypot là cờ nặng nhất.

### D. Lớp đòn bẩy — tối đa 10 điểm

Từ dữ liệu thanh lý phái sinh: nếu token có thị trường phái sinh và đang có thanh lý lớn, một cú rút thanh khoản sẽ bị khuếch đại.

**Quy tắc trung thực bắt buộc:** phần lớn token vốn hoá nhỏ **không có** thị trường phái sinh. Khi đó chiều này phải đánh dấu **"không áp dụng"**, tuyệt đối không tính là 0 điểm rồi coi như an toàn. Khác biệt giữa "đã kiểm tra và sạch" với "không kiểm tra được" là toàn bộ giá trị của sản phẩm.

### E. Dòng tiền cá mập — từ −15 đến +15 điểm (MỚI)

Chiều duy nhất có thể **giảm** điểm rủi ro. Hai nguồn dữ liệu: nhãn phân loại holder (`holders/tag_count`) và xu hướng vị thế (`holders/trend/list`), bổ trợ bằng danh sách swap.

**Cộng điểm rủi ro (tối đa +15):**
- Ví có nhãn kiểu sniper/bundler nắm tỷ lệ lớn → họ mua để xả, không phải để giữ
- Ví team/insider còn nắm nhiều
- Holder lớn đang **giảm** vị thế theo trend
- Áp lực bán ròng từ các swap lớn gần đây

**Trừ điểm rủi ro (tối đa −15):**
- Ví lớn đang **tăng** vị thế theo trend
- Số holder tăng đều, không cô đặc thêm
- Không có nhãn đáng ngờ nào nắm tỷ lệ đáng kể

**Quy tắc bắt buộc:** nếu endpoint nhãn hoặc trend không trả được dữ liệu, chiều E phải ghi rõ **"không áp dụng"** và hạ độ phủ. Không được cộng 0 rồi coi như đã kiểm tra sạch.

**Về danh mục nhãn:** agent phải đọc tài liệu `holders/tag_count` để biết CMC thực sự có những nhãn nào trước khi viết logic. Không được giả định có nhãn "whale" hay "smart money". Nếu CMC không có nhãn đó, chuyển sang suy luận từ dữ liệu sẵn có: tương quan giữa số dư holder và biến động vị thế theo trend, và ghi rõ trong README là suy luận chứ không phải nhãn chính thức. **Trung thực về mức độ suy luận quan trọng hơn việc có một tính năng trông ngầu.**

### Xếp hạng kết luận

| Điểm | Mức | Câu kết luận |
|---|---|---|
| 0-24 | THẤP | Không phát hiện dấu hiệu cấu trúc bất thường |
| 25-49 | ĐỂ MẮT | Có điểm cần theo dõi |
| 50-74 | CAO | Cấu trúc có dấu hiệu bất thường rõ |
| 75-100 | NGHIÊM TRỌNG | Cấu trúc giống các vụ rút thanh khoản đã xảy ra |

### Chống "hét rủi ro" — bắt buộc

Mọi kết quả phải in kèm **độ phủ dữ liệu**:

```
Rủi ro: 82/100 · NGHIÊM TRỌNG · Độ phủ dữ liệu: 80% (4/5 chiều)
```

Độ phủ dưới 50% → kết luận bắt buộc là "KHÔNG ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN", không đưa ra mức rủi ro.

Và phải chứng minh hệ thống **biết phân biệt**: chạy trên ít nhất 3 token, **có ít nhất 1 token điểm thấp**, và **có ít nhất 1 token mà chiều E trừ điểm** (tức là có tín hiệu dòng tiền tích cực).

---

## 7. Định dạng kết quả — ví dụ cụ thể

Agent phải tạo ra đúng dạng này:

```
EXIT RADAR ────────────────────────────────────────────────
Token    BONK (So11111111111111111111111111111111111111112)
Chain    Solana
Giá      $0.0000231   ·   Thanh khoản: $4.2M   ·   Holder: 41.208

RỦI RO   68/100  ·  CAO  ·  Độ phủ dữ liệu 100% (5/5 chiều)

LÝ DO (xếp theo mức đóng góp)
 1. Thanh khoản giảm 34% trong 24h và 58% trong 7d              +22 / 30
 2. Top 10 holder nắm 61% supply                                 +17 / 25
 3. Còn 2 ví mang nhãn đáng ngờ nắm 9% supply, 1 ví đang rút      +6 / 15
    (Hợp đồng: chưa từ bỏ quyền sở hữu, quyền mint còn mở        +13 / 20)
    (Phái sinh: không áp dụng — token không có thị trường này)

DÒNG TIỀN CÁ MẬP
    Holder lớn tăng vị thế 24h qua:   3 ví   ·   +$412.000 ròng
    Holder lớn giảm vị thế 24h qua:   7 ví   ·   −$1.180.000 ròng
    Nhãn đáng ngờ đang nắm:           9% supply
    → Dòng tiền ròng đang RÚT RA. Đây là lý do chính của chiều E.

SO VỚI LẦN KIỂM TRA TRƯỚC (17/09 14:20)
    Thanh khoản −18%   ·   Điểm rủi ro 51 → 68   ·   Holder count −12

ENDPOINT ĐÃ GỌI
    /v1/dex/search                     200   (định danh token)
    /v1/dex/token-liquidity/query      200
    /v1/dex/liquidity-change/list      200
    /v1/dex/security/detail            200
    /v1/dex/holders/list               200
    /v1/dex/holders/trend/list         200
    /v1/dex/holders/tag_count          200
    /v1/dex/tokens/transactions        200
    /v4/dex/spot-pairs/latest          200
    ── 9 lời gọi · cache: 0/9 · 2.4s

BÁO CÁO: exit-radar/token-BONK.html
────────────────────────────────────────────────────────────
Đây là bằng chứng cấu trúc từ dữ liệu công khai, không phải
lời khuyên đầu tư. Sản phẩm không nói mua hay bán.
```

Khối `ENDPOINT ĐÃ GỌI` là mục BTC yêu cầu tường minh, và cũng là bằng chứng "real API call". **Không được bỏ.**

---

## 8. Kiến trúc

```
exit-radar/
├── cmc/
│   ├── client.py        # lớp gọi HTTP duy nhất, xử lý GET/POST, key/keyless
│   ├── cache.py         # cache theo TTL
│   └── endpoints.py     # khai báo endpoint + động từ HTTP, một chỗ duy nhất
├── core/
│   ├── resolve.py       # định danh token
│   ├── signals.py       # 5 hàm chấm điểm, HÀM THUẦN
│   ├── whales.py        # phân tích dòng tiền holder — HÀM THUẦN
│   ├── score.py         # gộp điểm, xếp mức, tính độ phủ
│   ├── store.py         # watchlist.json, append + tính delta
│   └── models.py        # dataclass dữ liệu chuẩn hoá
├── report/
│   ├── terminal.py
│   └── html.py
├── fixtures/            # response mẫu để chạy offline
├── docs/evidence/       # response thật đã chụp, kèm timestamp
├── tests/
├── cli.py
├── .env.example
├── .gitignore
└── README.md
```

**Nguyên tắc:**
- `cmc/client.py` là chỗ **duy nhất** biết cách gọi API
- `signals.py`, `whales.py`, `score.py` **không import thư viện mạng**. Nhận dict, trả dict → test được không cần internet → ăn điểm chất lượng code
- Mọi lời gọi API phải ghi log: endpoint, tham số, HTTP status, thời gian, cache hit/miss

---

## 9. Cấu hình API — hai chế độ

```python
# Chế độ 1: keyless
base = "https://pro-api.coinmarketcap.com/public-api"
headers = {}

# Chế độ 2: có key
base = "https://pro-api.coinmarketcap.com"
headers = {"X-CMC_PRO_API_KEY": os.environ["CMC_API_KEY"]}
```

Tự chọn theo việc `CMC_API_KEY` có tồn tại hay không. **Cả hai chế độ phải chạy được.**

**Lưu ý về độ phủ của keyless:** theo trang Keyless Public API, bộ keyless gồm 18 endpoint Standard + 17 endpoint DEX — trong đó có `holders/list`, `holders/detail`, `holders/count`. Nhưng `holders/trend/list` và `holders/tag_count` **không nằm trong danh sách keyless** → cần key Startup tier. Vì vậy hãy thiết kế để chiều E tự động chuyển thành "không áp dụng" khi chạy keyless, và đăng ký DoraHacks sớm để có key đầy đủ.

**Xử lý giới hạn:** backoff cấp số nhân khi gặp 429, cache TTL 60 giây. Không hardcode key, `.env` trong `.gitignore`.

---

## 10. Chế độ offline — bắt buộc

`--offline` đọc từ `fixtures/`, cho phép **giám khảo chạy thử trong 30 giây mà không cần key**. Giám khảo chấm 19 bài; thứ chạy được ngay không cần cấu hình sẽ được đánh giá cao hơn.

Mỗi lần gọi API thật trong quá trình phát triển phải lưu response thô vào `docs/evidence/` kèm timestamp. Đây là bằng chứng bài nộp.

---

## 11. Những gì CỐ TÌNH không đưa vào, và vì sao

Phần này phải viết trong README dưới mục "Scope and roadmap". Giám khảo đánh giá cao việc bạn biết giới hạn của mình.

### 11.1. Mặt NFT — không làm trong bản này

Yêu cầu ban đầu có một nửa về NFT (kiểm tra contract NFT được whitelist mint, thuộc tính, thay đổi contract, ví cá mập nào đã mint, chất lượng ví qua NFT đang giữ). **Không đưa vào vì dữ liệu không tồn tại trong CMC API.**

Toàn bộ danh mục tài liệu CMC gồm các nhóm: Cryptocurrency, Exchange, Global Metrics, Content, Community, CMC Index, Token (DEX), Platform, Holder, OHLCV, RWA, Derivatives, CMC AI, Tools và một số nhóm nhỏ. **Không có nhóm NFT nào.** Nghĩa là toàn bộ phần NFT sẽ phải dựng trên nguồn khác (OpenSea, Magic Eden, Alchemy) — mà luật cuộc thi yêu cầu sản phẩm chạy trên dữ liệu CMC, và 20 điểm nằm ở mục "dùng API thú vị". Một bài nộp mà CMC chỉ là phần phụ sẽ mất điểm nặng ở đúng mục đó.

Ngoài ra, phần "ví cá mập có NFT giá cao để đánh giá chất lượng ví" đòi hỏi dữ liệu danh mục theo địa chỉ — CMC chỉ cho biết số dư của một địa chỉ **trong chính token đang xét**, không cho toàn bộ danh mục xuyên chain.

**Hướng đi đúng cho phần này:** ghi vào README là hướng phát triển tiếp theo, kèm một câu nêu rõ cần nguồn dữ liệu gì. Điều đó cho thấy bạn hiểu sản phẩm, mà không làm loãng bài nộp.

### 11.2. Kiểm tra mã nguồn hợp đồng / lịch sử thay đổi contract

CMC cho **cảnh báo bảo mật** (`security/detail`: honeypot, quyền mint, quyền sở hữu, thuế chuyển nhượng, blacklist). Đó là mức CMC làm được, và ta dùng hết.

Nhưng **xác minh mã nguồn đã công bố, xem lịch sử proxy upgrade, đọc hàm trong contract** thì phải dùng API của block explorer (Etherscan, Basescan, Solscan) — không phải CMC. Không đưa vào bản này, chỉ ghi vào roadmap.

### 11.3. Metadata tài khoản X (tuổi tài khoản, lịch sử đổi tên, khu vực tạo)

**Không làm, và không chỉ vì thiếu dữ liệu.** X API không cung cấp "khu vực tạo hồ sơ", còn thu thập lịch sử đổi tên hay ngày tạo tài khoản bằng cách cào dữ liệu là vi phạm điều khoản sử dụng của X — và một bài dự thi công khai không nên xây trên nền đó.

**Thay thế trong phạm vi cho phép:** nhóm endpoint Content của CMC (`/v1/content/latest`, `/v1/content/posts/top`) trả về **bài đăng và thảo luận cộng đồng** quanh token. Đó là tín hiệu mức độ chú ý hợp pháp, lấy từ CMC. Nếu muốn thêm, dùng đúng nhóm này và ghi rõ nguồn.

### 11.4. Danh mục tài sản xuyên chain của một ví

CMC không có endpoint tra danh mục theo địa chỉ ví. Không đưa vào.

---

## 12. Kịch bản demo video 2 phút

| Thời lượng | Nội dung |
|---|---|
| 0:00-0:15 | Vấn đề: "Con token này mất 90% giá trị trong 4 phút. Thanh khoản đã biến mất 6 tiếng trước đó — không ai nhìn." |
| 0:15-0:35 | Chạy Exit Radar trên token thật. Cho thấy request bay đi. |
| 0:35-1:05 | Đọc verdict: 3 lý do kèm số, khối endpoint đã gọi. |
| 1:05-1:25 | **Khối DÒNG TIỀN CÁ MẬP** — "3 ví lớn đang tăng vị thế, 7 ví đang rút, ròng −$1.18M. Đây là thứ người mới không bao giờ tự thấy được." |
| 1:25-1:45 | **Chạy token lành mạnh → điểm thấp, chiều E trừ điểm.** Nói rõ: "hệ thống biết phân biệt, không phải lúc nào cũng hét rủi ro." |
| 1:45-1:55 | Chạy lại watchlist → phần delta so với lần trước. |
| 1:55-2:00 | Mở `docs/evidence/`, nhắc disclaimer. |

Đoạn 1:25-1:45 quan trọng hơn vẻ ngoài của nó. **Bỏ đoạn đó là mất niềm tin.**

---

## 13. Điểm gì ăn được tiêu chí nào

| Tiêu chí | Điểm | Cách ăn |
|---|---|---|
| Chạy được | 30 | Kiểm chứng trên nhiều token thật; có chế độ offline cho giám khảo chạy ngay; có test |
| Hữu ích với người thật | 25 | Giải quyết nỗi đau cụ thể của người mới; có phần kiểm tra lại hằng ngày; trả lời được câu "có ai lớn đang vào không" |
| Dùng API thú vị | 20 | Dùng nhóm DEX và **Holder** mà 19 bài nộp không ai đụng; dùng dữ liệu *thay đổi theo thời gian*, không chỉ ảnh chụp tĩnh |
| Chất lượng code & tài liệu | 15 | Hàm thuần tách khỏi I/O; có test; README công bố ngưỡng; log endpoint |
| Trình bày | 10 | Video 2 phút có kịch bản; báo cáo HTML gọn; khối endpoint rõ ràng |

---

## 14. Những gì KHÔNG được làm

1. **Không dựng MCP server.** CMC đã có MCP server chính thức, x402, CLI và bộ AI Agent Skills. Dựng lại là mất điểm originality.
2. **Không dùng `quotes/latest` làm xương sống.** Endpoint ai cũng dùng, chỉ được xuất hiện như thông tin phụ.
3. **Không coi dữ liệu thiếu là an toàn.** Không lấy được dữ liệu → ghi "không áp dụng", hạ độ phủ, không cộng 0 rồi kết luận thấp.
4. **Không bịa nhãn holder.** Đọc tài liệu để biết CMC có nhãn gì. Nếu không có nhãn cá mập, ghi rõ là suy luận từ dữ liệu.
5. **Không tự chọn token khi search ra nhiều kết quả.**
6. **Không viết câu mệnh lệnh kiểu "nên bán ngay".** Chỉ trình bày bằng chứng cấu trúc. Ghi rõ không phải lời khuyên đầu tư.
7. **Không commit API key.** Kiểm tra bằng `git log -p | grep -i cmc` trước khi push.
8. **Không đưa NFT vào bản này.** Xem mục 11.1.
9. **Không ôm thêm tính năng.** Danh sách đóng: quét một token, chấm điểm 5 chiều, đọc dòng tiền holder, so sánh delta, xuất báo cáo. Hết.

---

## 15. Thứ tự build 12 ngày

| Ngày | Việc | Điều kiện hoàn thành |
|---|---|---|
| 18-19/09 | Đăng ký DoraHacks bằng email tài khoản CMC. Gọi thử 1 request keyless. Viết `cmc/client.py`. | Có response thật lưu vào `docs/evidence/` |
| 20/09 | **Kiểm tra độ phủ dữ liệu** trên 5-10 token, 2 chain. **Đọc tài liệu để biết `holders/tag_count` có nhãn gì, `holders/trend/list` trả về gì, và động từ HTTP của từng endpoint.** | Biết chắc chiều E có khả thi không |
| 21-23/09 | Viết `report/terminal.py`, `store.py`, `cli.py`. Bản chạy được đầu tiên | Chạy được trên token thật |
| 24-25/09 | 5 hàm chấm điểm + gộp điểm + độ phủ + `whales.py`. Viết test | Test pass, có 1 token điểm thấp và 1 token chiều E trừ điểm |
| 26/09 | Thêm lớp đòn bẩy phái sinh, `--offline`, chụp fixtures | Chạy offline được không cần key |
| 27/09 | `report/html.py` + README đầy đủ (gồm mục Scope and roadmap) | README có Phương pháp, endpoint, API gây khó, giới hạn |
| 28/09 | **Quay video demo 2 phút** theo kịch bản mục 12 | Video xong, đã upload |
| 29/09 | Push repo, post X kèm `#BuildwithCMC`, nộp DoraHacks | Đã nộp, có link |
| 30/09 | Dự phòng — chỉ sửa lỗi nhỏ | Không thêm tính năng |

**Ngày 20/09 là mốc rủi ro cao nhất.** Nếu nhóm endpoint Holder không cho thứ ta cần, phải biết ngay hôm đó. Nếu `holders/tag_count` không có nhãn hữu ích, chiều E chuyển sang suy luận thuần từ `trend/list` và `holders/list` — vẫn làm được, nhưng phải biết sớm.

---

## 16. Rủi ro và cách xử lý

| Rủi ro | Cách xử lý |
|---|---|
| Nhóm Holder không trả dữ liệu như kỳ vọng | Kiểm tra ngày 20/09. Nếu thiếu, chiều E rút xuống dùng `holders/list` + `trend/list`, ghi rõ trong README |
| `holders/trend/list` và `tag_count` cần key Startup tier | Thiết kế để chiều E tự động "không áp dụng" khi keyless; đăng ký sớm để có key |
| Sai động từ HTTP (GET vs POST) | Đọc tài liệu từng endpoint trước khi code; `endpoints.py` khai báo động từ ở một chỗ |
| Tên trường JSON khác dự đoán | Bắt buộc đọc tài liệu endpoint. Không đoán |
| Báo động nhầm quá nhiều | Phải có token điểm thấp trong bộ demo. Đây là rủi ro uy tín lớn nhất |
| Giám khảo không chạy được vì thiếu key | Chế độ `--offline` |

---

## 17. Hồ sơ nộp bài — checklist cuối

- [ ] Repo public trên GitHub
- [ ] `README.md`: vấn đề, kiến trúc, cách cài, cách chạy, output mẫu
- [ ] Mục **"CMC API endpoints used"** — tên từng endpoint tường minh
- [ ] Mục **"What the API made possible / Where it got in the way"** — ghi chỗ API gây khó thật
- [ ] Mục **"Methodology"** — công bố ngưỡng chấm điểm 5 chiều
- [ ] Mục **"Scope and roadmap"** — nêu rõ đã cố tình bỏ NFT và kiểm tra mã nguồn contract, và vì sao
- [ ] Mục **"Originality"** — repo mới, tích hợp CMC viết mới cho hackathon
- [ ] `docs/evidence/` có response thật kèm timestamp
- [ ] Video demo 2 phút
- [ ] Post X kèm link bài nộp + link video + `#BuildwithCMC`
- [ ] Track **AI Agents and Automation**
- [ ] `--offline` chạy được không cần key
- [ ] Không có API key trong repo
- [ ] Có ít nhất 1 token điểm thấp, và 1 token mà chiều E trừ điểm
