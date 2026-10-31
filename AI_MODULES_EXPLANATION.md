# TÀI LIỆU KỸ THUẬT: CƠ CHẾ HOẠT ĐỘNG CỦA 6 ĐỘNG CƠ AI & BỘ ĐỊNH TUYẾN
## HỆ THỐNG QUẢN TRỊ CƠ SỞ DỮ LIỆU POSTGRESQL CỬA HÀNG LINH KIỆN MÁY TÍNH
*(Phiên bản 3.1 — 100% Python chạy cục bộ, không sử dụng API trí tuệ nhân tạo của bên thứ ba. Nội dung đối chiếu trực tiếp với mã nguồn trong `ai_service/app/`.)*

---

## MỤC LỤC TỔNG QUAN

1. [Kiến trúc Tổng thể & Sơ đồ Luồng Dữ liệu](#1-kiến-trúc-tổng-thể--sơ-đồ-luồng-dữ-liệu)
2. [Bộ Định Tuyến Truy Vấn (Query Router)](#2-bộ-định-tuyến-truy-vấn-query-router)
3. [AI 1: Chuyển Ngôn Ngữ Tự Nhiên Sang SQL (NL2SQL Engine)](#3-ai-1-chuyển-ngôn-ngữ-tự-nhiên-sang-sql-nl2sql-engine)
4. [AI 2: Tìm Kiếm Ngữ Nghĩa & Tư Vấn Cấu Hình (Semantic Search & Knowledge Graph)](#4-ai-2-tìm-kiếm-ngữ-nghĩa--tư-vấn-cấu-hình-semantic-search--knowledge-graph)
5. [AI 3: Giám Sát An Ninh Zero-Trust (Security Sentinel)](#5-ai-3-giám-sát-an-ninh-zero-trust-security-sentinel)
6. [AI 4: Cố Vấn Chỉ Mục (Smart Index Advisor)](#6-ai-4-cố-vấn-chỉ-mục-smart-index-advisor)
7. [AI 5: Dự Báo Tăng Trưởng & Quy Hoạch Phân Vùng (Predictive Partitioning Planner)](#7-ai-5-dự-báo-tăng-trưởng--quy-hoạch-phân-vùng-predictive-partitioning-planner)
8. [AI 6: Quản Trị Sao Lưu & Kiểm Soát Toàn Vẹn (Smart Backup Intelligence)](#8-ai-6-quản-trị-sao-lưu--kiểm-soát-toàn-vẹn-smart-backup-intelligence)
9. [Bảng Tổng Hợp Công Nghệ & Thuật Toán](#9-bảng-tổng-hợp-công-nghệ--thuật-toán)

---

## 1. KIẾN TRÚC TỔNG THỂ & SƠ ĐỒ LUỒNG DỮ LIỆU

Hệ thống theo nguyên tắc **Zero-Third-Party AI**: luật xử lý ngôn ngữ tiếng Việt (Rule-Based NLP), học máy cổ điển (scikit-learn: TF-IDF, Logistic Regression, Isolation Forest), phân tích cây cú pháp SQL (AST, thư viện `sqlglot`) và các mô hình dự báo toán học đều viết bằng **Python** và chạy trực tiếp trên máy chủ nội bộ. Không có dữ liệu nào được gửi ra dịch vụ AI bên ngoài.

Tên bảng/cột trong tài liệu là tên thật trong schema `"LinhKien"` (chữ thường, gạch dưới): `san_pham`, `don_hang`, `chi_tiet_don_hang`, `khach_hang`, `ton_kho`...

```
                    [ Người dùng nhập câu hỏi tiếng Việt ]
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ AI 3: CHỐT CHẶN ĐẦU VÀO    │ (ý định ghi/xóa, hỏi mật khẩu/giá vốn)
                        └─────────────┬─────────────┘
                                      │ Điểm < 70
                                      ▼
                        ┌───────────────────────────┐
                        │   BỘ ĐỊNH TUYẾN (ROUTER)  │
                        └──────┬─────────────┬──────┘
             Câu hỏi nghiệp vụ │             │ Tư vấn linh kiện,
             (báo cáo, thống kê)│             │ cấu hình máy tính
                               ▼             ▼
                 ┌───────────────────┐ ┌───────────────────┐
                 │  AI 1: NL2SQL     │ │  AI 2: SEMANTIC   │
                 │  (Luật + Học máy) │ │  (Hybrid Ranking) │
                 └─────────┬─────────┘ └─────────┬─────────┘
                           │ SQL có tham số %s   │ yêu cầu tìm kiếm
                           ▼                     ▼
                 ┌───────────────────┐ ┌───────────────────┐
                 │ AI 3: CHẤM ĐIỂM   │ │ AI 3: GIÁM SÁT    │
                 │ SQL (AST + ML)    │ │ AI 2 (độ phủ...)  │
                 └─────────┬─────────┘ └─────────┬─────────┘
                           ▼                     ▼
                 ┌─────────────────────────────────────────┐
                 │ PostgreSQL — role CHỈ ĐỌC               │
                 │ (text2sql_readonly / manager_readonly)  │
                 └────────────────────┬────────────────────┘
                                      │
      ┌───────────────────────────────┼───────────────────────────────┐
      ▼                               ▼                               ▼
┌─────────────┐                ┌─────────────┐                ┌─────────────┐
│    AI 4     │                │    AI 5     │                │    AI 6     │
│INDEX ADVISOR│                │ PARTITION   │                │SMART BACKUP │
│(EXPLAIN,    │                │(OLS / Holt, │                │(Rủi ro 0-100│
│ HypoPG)     │                │ phân vùng)  │                │ & SHA-256)  │
└─────────────┘                └─────────────┘                └─────────────┘
```

Mọi truy vấn của chatbot đều chạy bằng role **chỉ đọc**: ngay cả khi một câu SQL lọt qua các lớp kiểm tra, PostgreSQL vẫn từ chối mọi lệnh ghi. Kết nối được tái sử dụng qua pool (`app/db.py`), mỗi role một hàng chờ riêng.

---

## 2. BỘ ĐỊNH TUYẾN TRUY VẤN (QUERY ROUTER)

- **Vị trí mã nguồn:** `ai_service/app/router.py`
- **Mục tiêu:** Tự động chuyển câu hỏi tới **AI 1** (truy vấn nghiệp vụ CSDL) hoặc **AI 2** (tư vấn linh kiện theo nhu cầu).

### 2.1. Nguyên lý hoạt động
Câu hỏi được chuẩn hóa (có dấu và không dấu) rồi kiểm tra theo thứ tự:
1. **Tín hiệu tư vấn** (`CONSULTATION_SIGNALS_REGEX`): `tư vấn`, `gợi ý`, `nên mua`, `phù hợp`, `cấu hình`, `build pc`, `dàn máy`, `tốt nhất`, hoặc mẫu `để/cho (máy) chơi game / làm đồ họa / học / stream...`
2. **Tín hiệu thông số phần cứng JSONB** (`SPEC_SIGNALS_REGEX`): `vram`, `socket`, `lga1700`, `am4/am5`, `bus`, `tdp`, `gddr`, `ips`, `hz`, `tần số quét`, `công suất`, `wattage`, `modular`.
3. **Nhu cầu trong Đồ thị tri thức phần cứng** (`knowledge_graph.json`), ví dụ chơi game, đồ họa, văn phòng, học tập.
4. **Độ tin cậy của AI 1:** không có tín hiệu tư vấn và AI 1 nhận diện ý định với độ tin cậy **≥ 0,8** → giao cho AI 1. Còn lại, nếu phát hiện nhu cầu phần cứng → AI 2; không thì trả về "ngoài phạm vi".

### 2.2. Ví dụ thực tế
- `"Top 5 sản phẩm đắt nhất"` → không có tín hiệu tư vấn, AI 1 nhận diện `TOP_PRODUCTS_BY_PRICE_DESC` (độ tin cậy 1,0) → **AI 1**.
- `"Tư vấn cấu hình PC chơi game nặng khoảng 25 triệu"` → khớp tín hiệu tư vấn và nhu cầu chơi game → **AI 2**.

---

## 3. AI 1: CHUYỂN NGÔN NGỮ TỰ NHIÊN SANG SQL (NL2SQL ENGINE)

- **Vị trí mã nguồn:** `pipeline.py`, `text_normalizer.py`, `intent_classifier.py`, `ml_intent_classifier.py`, `entity_extractor.py`, `query_templates.py`, `sql_builder.py`, `explanation.py`
- **Mục tiêu:** Chuyển câu hỏi quản trị kinh doanh tiếng Việt sang SQL an toàn, không dùng mô hình ngôn ngữ lớn (LLM).

```
Câu hỏi tiếng Việt
   │
   ▼
[ Bước 1: Text Normalizer ] ──► chữ thường, viết tắt -> đầy đủ, bản có dấu + không dấu
   │
   ▼
[ Bước 2: Intent Classifier ] ─► (a) Luật regex  ──không khớp──► (b) Học máy TF-IDF + Logistic Regression
   │
   ▼
[ Bước 3: Entity Extractor ] ──► giá, Top N, hãng, danh mục, trạng thái, năm, kênh bán, phương thức thanh toán
   │
   ▼
[ Bước 4: SQL Builder ] ───────► mẫu SQL dựng sẵn + tham số %s truyền riêng
   │
   ▼
[ Bước 5: Explanation ] ───────► diễn giải bằng tiếng Việt vì sao hệ thống hiểu như vậy
```

### 3.1. Chi tiết từng bước

#### Bước 1: Chuẩn hóa văn bản (`text_normalizer.py`)
- Cắt câu quá dài (tối đa 300 ký tự, chống ReDoS), chuẩn hóa Unicode NFC, chuyển chữ thường, bỏ dấu câu nhưng giữ dấu `,` `.` giữa hai chữ số (`1,5 triệu`, `5.000.000`).
- Chuẩn hóa từ đồng nghĩa linh kiện: `card màn hình`/`card đồ họa` → `vga`, `bo mạch chủ` → `mainboard`, `bộ vi xử lý` → `cpu`, `thùng máy` → `vỏ case`...
- Sửa lỗi gõ tên kênh bán: `shoppee/shope/sopee` → `shopee`, `face book` → `facebook`, `web site` → `website`.
- Sinh song song bản có dấu và bản không dấu (`remove_diacritics`) để hiểu cả câu gõ thiếu dấu.

#### Bước 2: Phân loại ý định — luật trước, học máy sau
- **20 ý định** chia 3 cấp:
  - *Cơ bản:* `LIST_PRODUCTS`, `FILTER_PRODUCTS_BY_PRICE`, `FILTER_PRODUCTS_BY_PRICE_RANGE`, `TOP_PRODUCTS_BY_PRICE_DESC`, `TOP_PRODUCTS_BY_PRICE_ASC`, `COUNT_ORDERS`, `ORDERS_BY_STATUS`
  - *Trung bình:* `FILTER_BY_CATEGORY`, `FILTER_BY_BRAND`, `LOW_STOCK`, `ORDERS_COUNT_BY_STATUS`, `ORDERS_BY_CHANNEL`, `PAYMENT_METHODS_STATS`, `CUSTOMERS_BY_CITY`
  - *Nâng cao:* `BEST_SELLING_PRODUCTS`, `TOP_SPENDING_CUSTOMERS`, `SALES_BY_MONTH`, `EMPLOYEE_PERFORMANCE`, `TOTAL_REVENUE`, `SUPPLIER_PURCHASE_TOTAL`
- **(a) Luật regex** (`intent_classifier.py`): khớp mẫu câu đặc trưng → độ tin cậy 1,0. Có luật loại trừ ngữ cảnh (ví dụ "bạn sale nào bán nhiều nhất" là hỏi về nhân viên, không phải sản phẩm bán chạy).
- **(b) Học máy** (`ml_intent_classifier.py`, dữ liệu huấn luyện `app/data/intent_training.json`): khi không luật nào khớp, mô hình **TF-IDF + Logistic Regression** dự đoán ý định, độ tin cậy là xác suất thật của mô hình:
  - xác suất **≥ 0,55** → chấp nhận ý định;
  - **0,30 – 0,55** → hỏi lại người dùng kèm gợi ý (*"Ý bạn là: «Doanh thu theo tháng»?"*);
  - **< 0,30** → không hiểu, trả về ngoài phạm vi.
- **Kết quả đo** (`eval/report_text2sql.md`, bộ 50 câu): chỉ dùng luật đạt 50%; luật + học máy đạt **90%**. Trên 25 câu diễn đạt lại chưa có trong dữ liệu huấn luyện, độ chính xác tăng từ 0% lên 80%. Các câu còn lại hệ thống hỏi lại chứ không trả lời sai.

#### Bước 3: Bóc tách thực thể (`entity_extractor.py`)
- **Giá** (`extract_price_condition`): `trên 5 triệu`, `từ 1 triệu đến 3 triệu`, `dưới 500k`; quy đổi `triệu/tr` × 10⁶, `k/nghìn` × 10³.
- **Top N** (`extract_top_n`): `top 5`, `10 sản phẩm` → `LIMIT`.
- **Danh mục, hãng** (`extract_category`, `extract_brand`): đối chiếu danh mục/thương hiệu trong CSDL (VGA, CPU, RAM, ASUS, MSI, Intel, AMD...).
- **Trạng thái đơn** (`extract_order_status`): `đã hủy/bị hủy` → `'da_huy'`, `hoàn thành` → `'hoan_thanh'`.
- **Năm, kênh bán, phương thức thanh toán** (`extract_year`, `extract_channel`, `extract_payment_method`).

#### Bước 4: Dựng SQL an toàn (`query_templates.py`, `sql_builder.py`)
- Mỗi ý định có mẫu SQL viết sẵn; giá trị người dùng nhập **không bao giờ được nối chuỗi** vào SQL mà truyền riêng qua placeholder `%s` của `psycopg2`.

#### Bước 5: Diễn giải (`explanation.py`)
- Sinh câu tiếng Việt giải thích cách hiểu và điều kiện SQL đã áp dụng.

### 3.2. Ví dụ chạy thực tế
- **Đầu vào:** `"Các linh kiện có giá từ 1 triệu đến 3 triệu"`
- **Ý định:** `FILTER_PRODUCTS_BY_PRICE_RANGE` (độ tin cậy 1,0 — luật `rule_15_price_range`)
- **SQL sinh ra:**
  ```sql
  SELECT id, ten, gia_niem_yet
  FROM san_pham
  WHERE gia_niem_yet BETWEEN %s AND %s AND dang_kinh_doanh = TRUE
  ORDER BY gia_niem_yet ASC;
  ```
- **Tham số:** `[1000000, 3000000]`
- **Diễn giải:** *"Nhận diện yêu cầu lọc sản phẩm trong khoảng giá từ 1,000,000 VNĐ đến 3,000,000 VNĐ. Áp dụng điều kiện `gia_niem_yet BETWEEN %s AND %s`."*

Trước khi thực thi, hệ thống chạy `EXPLAIN` để ước lượng số dòng thật rồi chuyển câu SQL cho AI 3 chấm điểm (mục 5).

---

## 4. AI 2: TÌM KIẾM NGỮ NGHĨA & TƯ VẤN CẤU HÌNH (SEMANTIC SEARCH & KNOWLEDGE GRAPH)

- **Vị trí mã nguồn:** `ai_semantic_search.py`, `knowledge_graph.py`, `app/data/knowledge_graph.json`
- **Mục tiêu:** Gợi ý linh kiện theo nhu cầu thực tế (học tập, văn phòng, đồ họa, chơi game...) bằng cách kết hợp vector hóa văn bản và đồ thị tri thức phần cứng.

### 4.1. Thuật toán Xếp hạng Lai (Hybrid Ranking)

$$\text{FinalScore} = w_1 \cdot S_{\text{word}} + w_2 \cdot S_{\text{char}} + w_3 \cdot S_{\text{kg}}$$

- $S_{\text{word}}$ (**$w_1 = 0{,}5$**): độ tương đồng Cosine TF-IDF mức từ (n-gram 1–2) — bắt đúng từ khóa tên sản phẩm.
- $S_{\text{char}}$ (**$w_2 = 0{,}2$**): độ tương đồng Cosine TF-IDF n-gram ký tự (3–5 ký tự, `char_wb`) — chịu được lỗi gõ, viết dính, mã model (`rtx3060`, `i5-13400f`).
- $S_{\text{kg}}$ (**$w_3 = 0{,}3$**): điểm tăng cường từ đồ thị tri thức: trọng số của danh mục đối với nhu cầu đã phát hiện, cộng **+0,3** cho mỗi thông số JSONB (VRAM, socket, công suất...) khớp gợi ý của đồ thị.
- **Hết hàng:** điểm nhân **× 0,75**.
- **Lọc ngân sách** ("dưới 15 triệu") áp dụng **trước** khi xếp hạng; sản phẩm dưới điểm tối thiểu 0,05 bị loại.
- Toàn bộ phép tính được **vector hóa bằng NumPy** (khoảng 16 ms với 5.000 sản phẩm); chỉ mục tự làm mới sau 10 phút để cập nhật giá và tồn kho.
- Trọng số có thể dò tự động bằng grid search: `python ai_service/eval/eval_semantic.py --tune`.

### 4.2. Phẳng hóa thông số kỹ thuật JSONB (`flatten_specs`)
- Dữ liệu gốc cột `thong_so_ky_thuat`: `{"socket": "AM4", "cores": 6, "tdp": "65W"}`
- Sau phẳng hóa (không dấu, để vector hóa): `"socket am4 cores 6 tdp 65w"`

### 4.3. Gợi ý cấu hình (`suggest_build`)
Với yêu cầu dựng cả bộ máy, đồ thị tri thức xác định các danh mục cần có cho nhu cầu đó; hệ thống chọn sản phẩm phù hợp nhất trong từng danh mục, ưu tiên linh kiện khớp thông số gợi ý.

### 4.4. AI 2 cũng được AI 3 giám sát
Trước khi trả kết quả, AI 3 chấm điểm yêu cầu tìm kiếm (mục 5.3) để chặn hành vi "cào" toàn bộ danh mục sản phẩm và giá.

---

## 5. AI 3: GIÁM SÁT AN NINH ZERO-TRUST (SECURITY SENTINEL)

- **Vị trí mã nguồn:** `ai_security_guard.py`, `ai_anomaly_detector.py`, `session_context.py`, `audit_seeder.py`
- **Mục tiêu:** Ngăn phá hoại, rò rỉ dữ liệu nhạy cảm và trích xuất hàng loạt theo nguyên tắc *"Never Trust, Always Verify"*. Mọi quyết định được ghi vào nhật ký kiểm toán `logs/security_audit.jsonl`.

### 5.1. Lớp 1 — Chốt chặn câu hỏi đầu vào (`evaluate_question_text`)
Đọc câu hỏi tiếng Việt **trước khi định tuyến**, bắt cả những câu không sinh ra SQL:
- Ý định ghi/xóa/sửa/cấp quyền (ví dụ *"xóa bảng sản phẩm"*): **+80 → chặn**. Hệ thống chỉ cho phép đọc dữ liệu.
- Hỏi dữ liệu bí mật (`mật khẩu`, `password_hash`, `giá vốn`...): **+40 → cảnh báo**.

### 5.2. Lớp 2 — Chấm điểm câu SQL của AI 1 (`AISecurityGuard.evaluate_risk`)
Câu SQL được phân tích thành **cây cú pháp AST bằng `sqlglot`**. Khi phân tích được, hệ thống chỉ tin kết quả AST (không quét regex trên chuỗi thô), nên từ khóa nằm trong dữ liệu như `LIKE '%update%'` không bị coi là lệnh phá hoại.

| Nhân tố | Điểm | Ghi chú |
| :--- | :---: | :--- |
| Lệnh phá hoại / ghi (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `GRANT`...), nhiều câu lệnh nối `;` | **+80** | gần như chắc chắn bị chặn |
| Không phân tích được cú pháp | +15 | |
| Cột nhạy cảm | theo cột | `app_users.password_hash` +80, `san_pham.gia_von` +70, `khach_hang.email` / `so_dien_thoai` +20, `dia_chi.dia_chi_chi_tiet` +20, `khach_hang.ngay_sinh` +10 |
| Bảng nhạy cảm | tối đa 50 | `khach_hang` 25, `thanh_toan` 25, `dia_chi` 20, `don_hang` 15 |
| `SELECT *` trên bảng nhạy cảm | +20 | |
| Trích xuất hàng loạt (số dòng ước tính từ `EXPLAIN` > 500, hoặc bảng nhạy cảm không `LIMIT` và không phải hàm tổng hợp) | +35 | |
| Khung giờ 0h – 6h | +30 | |
| IP ngoài dải tin cậy (`127.0.0.1`, `192.168.1.*`, `10.0.0.*`) | +25 | |
| Số lần sai mật khẩu trước khi đăng nhập | +15/lần, tối đa 45 | lấy từ màn hình đăng nhập |
| Tần suất truy vấn > 5 truy vấn/giây | +20 | đo thật theo phiên |
| **Học máy — Isolation Forest** đánh dấu hành vi ngoại lai | **+20** | xem 5.4 |
| **Học máy — lệch thói quen của chính người dùng** (z-score ≥ 3) | **+15** | xem 5.4 |

**Quyết định (điểm tối đa 100):**
- **< 40 — An toàn:** cho chạy.
- **40 – 69 — Cảnh báo:** cho chạy nhưng **che dữ liệu nhạy cảm** (mục 5.5) và ghi cảnh báo.
- **≥ 70 — Nguy hiểm:** **chặn thực thi**, ghi nhật ký, **khóa phiên 60 giây ngay lần đầu**, đề xuất lệnh `REVOKE` cho DBA.

### 5.3. Lớp 3 — Giám sát yêu cầu tìm kiếm của AI 2 (`evaluate_semantic_request`)

| Nhân tố | Điểm |
| :--- | :---: |
| Câu hỏi chứa mã SQL / script | +45 |
| Phiên đã xem > 60% danh mục sản phẩm | +55 |
| Phiên đã xem > 30% danh mục sản phẩm | +30 |
| Yêu cầu lấy "tất cả / toàn bộ" | +15 |
| Khung giờ 0h – 6h | +30 |
| IP lạ | +25 |
| Isolation Forest đánh dấu bất thường | +20 |
| Câu hỏi dài bất thường | +10 |

< 40 cho phép; 40 – 69 giới hạn số kết quả trả về; ≥ 70 chặn. AI 2 không dùng yếu tố tần suất hỏi.

### 5.4. Thành phần học máy (`ai_anomaly_detector.py`)
- **Đặc trưng của mỗi truy vấn (10):** giờ (sin/cos), log số dòng, số bảng, số cột, có `SELECT *`, có `LIMIT`, có hàm tổng hợp, log tần suất, log độ dài SQL.
- **Isolation Forest** học "hành vi bình thường" từ 400 mẫu nền, cộng với lịch sử thật trong nhật ký kiểm toán (đọc tối đa 5.000 bản ghi gần nhất). Mô hình tự huấn luyện lại sau mỗi 50 bản ghi mới.
- **Hồ sơ từng người dùng:** người có từ 10 truy vấn trở lên được tính z-score số dòng truy vấn; lệch ≥ 3 độ lệch chuẩn so với thói quen thì bị cộng điểm. Ví dụ: một người thường xem khoảng 10 dòng bỗng lấy 400 dòng.
- Có chức năng **nạp lịch sử mẫu** (`audit_seeder.py`) để mô hình có dữ liệu học khi demo; lịch sử mẫu được đánh dấu riêng và không tính vào thống kê thật.

### 5.5. Che dữ liệu động (Dynamic Data Masking — `session_context.py`)
Khi truy vấn ở mức Cảnh báo, các cột `email`, `so_dien_thoai`, `dia_chi_chi_tiet` trong kết quả được che, ví dụ `nguyenvana@gmail.com` → `n***@gmail.com`.

### 5.6. Hỗ trợ từ tầng CSDL
AI 3 là lớp ứng dụng; tầng PostgreSQL bảo vệ thêm (`database/nang_cap_bao_mat_toi_uu.sql`):
- role chỉ đọc cho chatbot;
- RLS theo tài khoản nhân viên (`nv_<id>`);
- chặn cột `gia_von` (Column-Level Security);
- mật khẩu web lưu bằng bcrypt và chỉ kiểm tra qua hàm `fn_xac_thuc_nguoi_dung`.

---

## 6. AI 4: CỐ VẤN CHỈ MỤC (SMART INDEX ADVISOR)

- **Vị trí mã nguồn:** `ai_service/app/ai_index_advisor.py`
- **Mục tiêu:** Đọc kế hoạch thực thi (`EXPLAIN (FORMAT JSON)`) để tìm nút quét tuần tự (Seq Scan) tốn kém, đề xuất **đúng loại** chỉ mục kèm câu lệnh DDL.

### 6.1. Cây quyết định theo luật
Dữ liệu thống kê lấy từ `pg_class` (`reltuples`), `pg_index` và cây kế hoạch:

```
                   [ Câu truy vấn cần chẩn đoán ]
                                  │
                                  ▼
             [ EXPLAIN (FORMAT JSON) -> tìm các nút Seq Scan ]
                                  │
                                  ▼
                   Bảng có >= 1.000 dòng hay không?
                    ├── KHÔNG ──► BỎ QUA (quét tuần tự bảng nhỏ nhanh hơn dùng index)
                    └── CÓ
                         │
                         ▼
             Độ chọn lọc (số dòng trả về / tổng) <= 20%?
              ├── KHÔNG ──► BỎ QUA (lấy quá nhiều dòng, index không giúp)
              └── CÓ
                   │
                   ▼
       Cột cần lọc đã là cột dẫn đầu của một index chưa?
        ├── ĐÃ CÓ ──► BỎ QUA (tránh index trùng, làm chậm INSERT)
        └── CHƯA
             │
             ▼
      [ Chọn loại chỉ mục & sinh CREATE INDEX ]
```

Các bảng được giữ nguyên quét tuần tự đều có lý do hiển thị rõ trên giao diện.

### 6.2. Các loại chỉ mục được đề xuất
1. **B-Tree:** điều kiện `=`, `>`, `<`, `BETWEEN` (ví dụ `gia_niem_yet`, `ngay_dat`).
2. **B-Tree nhiều cột (Composite):** nhiều điều kiện; cột so sánh bằng đứng trước, cột so sánh khoảng đứng sau.
3. **Partial Index (B-Tree một phần):** khi có điều kiện cố định trên cột ít giá trị, ví dụ:
   ```sql
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_don_hang_ngay_dat_partial
   ON "LinhKien".don_hang (ngay_dat) WHERE trang_thai = 'hoan_thanh';
   ```
4. **GIN `pg_trgm`:** tìm chuỗi con `ILIKE '%rtx%'` (B-Tree không dùng được khi `%` ở đầu).
5. **JSONB:** GIN `jsonb_path_ops` cho toán tử `@>`, hoặc chỉ mục biểu thức `((thong_so_ky_thuat ->> 'socket'))` cho truy vấn theo một khóa.

### 6.3. Đo hiệu quả thật bằng HypoPG
Nếu máy chủ cài extension **HypoPG**, AI 4 tạo **chỉ mục giả định** (không tạo index thật). Sau đó chạy lại `EXPLAIN` để hiển thị chi phí trước/sau và % cải thiện. Nếu chưa cài, giao diện ghi rõ "chưa đo", không đưa ra con số ước đoán.

### 6.4. Phân tích khối lượng công việc thật (`analyze_workload`)
Lấy các truy vấn tốn tổng thời gian nhiều nhất từ **`pg_stat_statements`** (qua hàm an toàn `fn_top_truy_van`, chỉ trả về câu `SELECT` đã chuẩn hóa) rồi chạy cố vấn cho từng câu.

### 6.5. An toàn DDL
Bảng thường dùng `CREATE INDEX CONCURRENTLY IF NOT EXISTS` — **không khóa ghi** trong lúc tạo index. Lệnh này không chạy được trong khối `BEGIN/COMMIT`. Bảng đã phân vùng không dùng `CONCURRENTLY`; index tạo trên bảng cha sẽ tự áp dụng xuống các phân vùng con.

---

## 7. AI 5: DỰ BÁO TĂNG TRƯỞNG & QUY HOẠCH PHÂN VÙNG (PREDICTIVE PARTITIONING PLANNER)

- **Vị trí mã nguồn:** `ai_predictive_partitioning.py`, `partition_demo.py`
- **Mục tiêu:** Dự báo số đơn hàng mỗi tháng của bảng `don_hang`, ước tính khi nào chạm ngưỡng (mặc định **1.000.000 dòng**), đưa ra quyết định và sinh kế hoạch chuyển sang bảng phân vùng.

### 7.1. Chuẩn bị dữ liệu
Đếm số đơn theo tháng. `generate_series` lấp các tháng không có đơn bằng 0; tháng hiện tại chưa kết thúc bị loại để không kéo lệch dự báo.

### 7.2. Ba mô hình dự báo và cách chọn
1. **Hồi quy tuyến tính OLS:** $y = a \cdot x + b$, với
   $a = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sum (x_i - \bar{x})^2}$, $b = \bar{y} - a\bar{x}$
   ($x$: chỉ số tháng, $y$: số đơn trong tháng).
2. **Làm trơn hàm mũ Holt** (có thành phần xu hướng).
3. **Baseline:** trung bình 3 tháng gần nhất.

**Backtest:** giữ lại 3 tháng cuối làm tập kiểm tra, tính **MAE, RMSE, MAPE** cho cả 3 mô hình, chọn mô hình có **MAE nhỏ nhất**. Hệ thống **không** chọn theo R², vì R² thấp chỉ cho biết số đơn đi ngang, không cho biết mô hình dự báo kém.

**Khoảng tin cậy 95%:** $\hat{y} \pm 1{,}96 \cdot SE$ ($SE$: sai số chuẩn phần dư).

### 7.3. Quyết định
Từ dự báo và dung lượng trung bình mỗi đơn, ước tính số ngày đến ngưỡng:
- **< 90 ngày:** `PARTITION_SOON` — phân vùng ngay.
- **90 – 365 ngày:** `MONITOR` — chuẩn bị kế hoạch, theo dõi hằng tháng.
- **≥ 365 ngày:** `NOT_NEEDED` — chưa cần.

**Kịch bản giả sử (What-if):** chỉnh hệ số tăng trưởng (×1 đến ×500) và ngưỡng phân vùng ngay trên giao diện để thấy trường hợp "cần phân vùng".

### 7.4. Kế hoạch di chuyển 5 bước (sinh tự động)
1. Tạo bảng cha `PARTITION BY RANGE (ngay_dat)` bằng `LIKE "LinhKien".don_hang` (sao chép đúng cột, kiểu dữ liệu, CHECK). Khóa chính `(id, ngay_dat)` vì khóa chính của bảng phân vùng phải chứa cột phân vùng.
2. Tạo **mỗi tháng một phân vùng** (theo tháng thật của dữ liệu + 3 tháng dự báo) và **phân vùng DEFAULT**.
3. Chép dữ liệu `INSERT ... SELECT *`, chạy `ANALYZE`.
4. Xử lý khóa ngoại (`chi_tiet_don_hang`, `thanh_toan` tham chiếu `don_hang.id`), tạo lại trigger nghiệp vụ, chính sách RLS và quyền GRANT. Kế hoạch cảnh báo rõ: bỏ sót bước này sẽ mất bảo mật mức dòng.
5. Hoán đổi bảng trong 1 giao dịch (`LOCK` → chép đơn phát sinh giữa chừng → `RENAME`), giữ bảng cũ làm bản dự phòng.

### 7.5. Thực hiện phân vùng trên bản sao (`partition_demo.py`)
Nút **"Thực hiện phân vùng"** (chỉ Admin) chạy thật kế hoạch trên bảng **`don_hang_phan_vung`** — một bản sao, **không đụng tới `don_hang`**:
- 1 giao dịch: lỗi giữa chừng thì tự hoàn tác.
- Mỗi tháng một phân vùng + 3 tháng tới + DEFAULT, chép toàn bộ đơn, `ANALYZE`.
- Thu hồi quyền đọc bản sao của role chatbot, Manager và nhân viên (bản sao không có RLS).
- **So sánh `EXPLAIN ANALYZE`** cùng một truy vấn doanh thu 1 tháng. Ví dụ tháng 06/2026: bảng gốc chi phí 19,4; bảng phân vùng chi phí 10,6 và **chỉ quét 1/26 phân vùng** (*partition pruning*); kết quả hai bảng giống hệt.
- Có nút xóa và tạo lại bản sao.

---

## 8. AI 6: QUẢN TRỊ SAO LƯU & KIỂM SOÁT TOÀN VẸN (SMART BACKUP INTELLIGENCE)

- **Vị trí mã nguồn:** `ai_service/app/ai_smart_backup.py`
- **Mục tiêu:** Đặt tần suất backup theo tốc độ thay đổi dữ liệu, chấm điểm rủi ro mất dữ liệu bằng số liệu thật, dự báo dung lượng và kiểm tra toàn vẹn bản backup.

### 8.1. Phân loại bảng theo tốc độ thay đổi (HOT / WARM / COLD)
- **Phân hạng nghiệp vụ mặc định:**
  - **HOT** — backup mỗi **1 giờ**: `don_hang`, `chi_tiet_don_hang`, `thanh_toan`, `ton_kho`.
  - **WARM** — mỗi **6 giờ**: `san_pham`, `khach_hang`, `dia_chi`, `phieu_nhap`, `chi_tiet_phieu_nhap`, `san_pham_nha_cung_cap`, `lich_su_thay_doi_gia`.
  - **COLD** — mỗi **24 giờ**: `danh_muc`, `thuong_hieu`, `nha_cung_cap`...
- **Đo thật:** lưu ảnh chụp bộ đếm `n_tup_ins + n_tup_upd + n_tup_del` từ `pg_stat_user_tables`. Từ chênh lệch giữa hai lần chụp, tính **% số dòng thay đổi mỗi giờ**: **≥ 1%/giờ → HOT**, **≥ 0,1%/giờ → WARM**, thấp hơn → COLD. Bảng đo được nóng hơn mức mặc định sẽ được nâng hạng.

### 8.2. Điểm rủi ro mất dữ liệu (0 – 100)
Bật "Dùng số liệu đo thật" để lấy dữ liệu từ hệ thống thay cho tham số mô phỏng: lần backup gần nhất và checksum (bảng `backup_history`), `archive_mode`, `pg_stat_archiver`, dung lượng trống ổ đĩa, thư mục offsite.

| Yếu tố | Điểm |
| :--- | :---: |
| Lần backup cuối > 24 giờ (> 12 giờ: +15) | +30 |
| Không có bản sao offsite (`BACKUP_OFFSITE_DIR`) | +20 |
| WAL `archive_mode` tắt (không khôi phục được tới từng thời điểm) | +20 |
| Bản backup gần nhất chưa kiểm chứng checksum / không còn tệp | +15 |
| Bảng nhạy cảm (`khach_hang`, `thanh_toan`, `don_hang`) đang ở mức HOT | +15 |
| `pg_stat_archiver` ghi nhận lưu WAL thất bại | +10 |
| Ổ đĩa backup còn < 20% dung lượng trống | +10 |

**Mức:** < 30 An toàn · 30 – 59 Cảnh báo · ≥ 60 Nguy hiểm (khuyến nghị backup full ngay).

### 8.3. Dự báo dung lượng
Ghi lịch sử dung lượng CSDL vào `backup_size_log`, hồi quy OLS theo **MB/ngày**, dự báo sau 30 / 60 / 90 ngày.

### 8.4. Sao lưu, kiểm tra toàn vẹn SHA-256 và khôi phục
1. Sinh lệnh `pg_dump` theo loại: **Full** (`-Fc -Z9`), **Schema** (`-s`), **Table** (`-t`) và lệnh `pg_restore` tương ứng. Hệ thống không có backup vi sai.
2. Sau khi backup, đọc tệp theo từng khối và tính $\text{Checksum} = \text{SHA256}(\text{tệp backup})$, lưu vào bảng **`backup_history`** cùng dung lượng, loại và trạng thái. Từ phiên bản này chỉ lưu **tên tệp**, nên đổi tên hay chuyển thư mục dự án vẫn tìm được tệp; bản ghi cũ lưu đường dẫn tuyệt đối cũng được tìm lại theo tên tệp trong thư mục `backups`.
3. Khi khôi phục, băm lại tệp và đối chiếu. Sai khác dù 1 bit (hỏng đĩa hoặc bị sửa) thì **từ chối khôi phục** và báo cảnh báo toàn vẹn.

---

## 9. BẢNG TỔNG HỢP CÔNG NGHỆ & THUẬT TOÁN

| Động cơ | Chức năng | Thuật toán & phương pháp cốt lõi | Thư viện & công cụ | File mã nguồn |
| :---: | :--- | :--- | :--- | :--- |
| **Router** | Định tuyến câu hỏi | Regex tín hiệu tư vấn/thông số, tra cứu đồ thị tri thức, ngưỡng tin cậy AI 1 ≥ 0,8 | `re`, dataclasses | `app/router.py` |
| **AI 1** | NL2SQL | Luật regex + **TF-IDF + Logistic Regression** (≥ 0,55 chấp nhận, 0,30 – 0,55 hỏi lại), bóc tách thực thể, SQL tham số hóa | `re`, **`scikit-learn`**, `psycopg2` | `app/pipeline.py`<br>`app/intent_classifier.py`<br>`app/ml_intent_classifier.py`<br>`app/sql_builder.py` |
| **AI 2** | Tìm kiếm ngữ nghĩa & tư vấn | Hybrid Ranking: TF-IDF từ (0,5) + n-gram ký tự (0,2) + đồ thị tri thức (0,3), phạt hết hàng × 0,75 | **`scikit-learn`**, `numpy` | `app/ai_semantic_search.py`<br>`app/knowledge_graph.py` |
| **AI 3** | Giám sát an ninh Zero-Trust | Phân tích AST, chấm điểm rủi ro đa nhân tố, **Isolation Forest**, z-score theo người dùng, che dữ liệu động | **`sqlglot`**, **`scikit-learn`**, `numpy` | `app/ai_security_guard.py`<br>`app/ai_anomaly_detector.py`<br>`app/session_context.py` |
| **AI 4** | Cố vấn chỉ mục | Cây quyết định trên `EXPLAIN JSON` + thống kê catalog, chọn loại index, **HypoPG** đo trước/sau, phân tích `pg_stat_statements` | PostgreSQL catalogs, `hypopg`, `psycopg2` | `app/ai_index_advisor.py` |
| **AI 5** | Quy hoạch phân vùng | **OLS / Holt / baseline** chọn theo backtest MAE, khoảng tin cậy 95%, kế hoạch phân vùng theo tháng, thực hiện trên bản sao + so sánh `EXPLAIN ANALYZE` | `math`, PostgreSQL partitioning | `app/ai_predictive_partitioning.py`<br>`app/partition_demo.py` |
| **AI 6** | Sao lưu & phục hồi | Đo tốc độ thay đổi, chấm điểm rủi ro 0 – 100 từ số liệu thật, hồi quy dung lượng, **SHA-256** | `pg_dump`, `pg_restore`, `hashlib`, `shutil` | `app/ai_smart_backup.py` |

---
*Tài liệu phục vụ báo cáo đồ án môn Quản trị Cơ sở Dữ liệu. Các ngưỡng, trọng số và tên bảng/cột được đối chiếu với mã nguồn trong thư mục `ai_service/app/`.*
