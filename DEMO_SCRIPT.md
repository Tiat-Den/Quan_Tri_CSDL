# KỊCH BẢN THUYẾT TRÌNH & DEMO HỆ THỐNG (DEMO SCRIPT)
## ĐỀ TÀI: HỆ THỐNG TRUY VẤN CSDL BẰNG NGÔN NGỮ TỰ NHIÊN TIẾNG VIỆT & BỘ 6 ĐỘNG CƠ QUẢN TRỊ CSDL NỘI BỘ
**Môn học:** Quản trị Cơ sở Dữ liệu  
**Thời lượng chuẩn:** 8 – 10 phút (Khớp hoàn hảo với khung thời gian bảo vệ đồ án)

---

## 📋 MỤC LỤC KỊCH BẢN

1. [Checklist Chuẩn bị Trước Giờ G (T-5 Phút)](#1-checklist-chuẩn-bị-trước-giờ-g-t-5-phút)
2. [Timeline & Phân Bổ Thời Gian](#2-timeline--phân-bổ-thời-gian)
3. [Kịch Bản Thuyết Trình & Thao Tác Chi Tiết (Từng Bước)](#3-kịch-bản-thuyết-trình--thao-tác-chi-tiết)
   - [Chặng 1: Mở đầu & Tuyên ngôn Kiến trúc (1 phút)](#chặng-1-mở-đầu--tuyên-ngôn-kiến-trúc-1-phút)
   - [Chặng 2: Cổng Đăng nhập Bảo mật & Phiên làm việc (1.5 phút)](#chặng-2-cổng-đăng-nhập-bảo-mật--phiên-làm-việc-15-phút)
   - [Chặng 3: Demo Bộ đôi Router & Text-to-SQL AI 1 (2 phút)](#chặng-3-demo-bộ-đôi-router--text-to-sql-ai-1-2-phút)
   - [Chặng 4: Demo Tư vấn Cấu hình Phần cứng AI 2 (1.5 phút)](#chặng-4-demo-tư-vấn-cấu-hình-phần-cứng-ai-2-15-phút)
   - [Chặng 5: Thử thách Hacker — Giám sát An ninh Zero-Trust AI 3 (1.5 phút)](#chặng-5-thử-thách-hacker--giám-sát-an-ninh-zero-trust-ai-3-15-phút)
   - [Chặng 6: Bộ Ba Quản Trị CSDL Chuyên Sâu AI 4, AI 5, AI 6 (1.5 phút)](#chặng-6-bộ-ba-quản-trị-csdl-chuyên-sâu-ai-4-ai-5-ai-6-15-phút)
   - [Chặng 7: Kết luận & Chuyển sang phần Q&A (0.5 phút)](#chặng-7-kết-luận--chuyển-sang-phần-qa-05-phút)
4. [Bộ Câu Hỏi Phản Biện Của Hội Đồng & Cách Đối Đáp Chuẩn Xác (Q&A Cheat Sheet)](#4-bộ-câu-hỏi-phản-biện-của-hội-đồng--cách-đối-đáp-chuẩn-xác)

---

## 1. CHECKLIST CHUẨN BỊ TRƯỚC GIỜ G (T-5 PHÚT)

Trước khi mời Thầy/Cô và Hội đồng theo dõi màn hình, hãy đảm bảo:

- [ ] **PostgreSQL đang chạy:** Dịch vụ PostgreSQL 16/17 đã khởi động, kết nối tới CSDL `LinhKien_DB`.
- [ ] **Chạy ứng dụng:** Mở PowerShell tại thư mục gốc đồ án:
  ```powershell
  python ai_service/web_app.py
  ```
- [ ] **Trình duyệt Web:** Mở `http://localhost:8501`. Đảm bảo trang đang ở màn hình **Đăng nhập (Login Portal)**, nếu đang có phiên đăng nhập cũ hãy bấm **Đăng xuất**.
- [ ] **Phóng to màn hình:** Nhấn `Ctrl +` (khoảng $110\% - 125\%$) để Thầy/Cô ngồi xa cũng đọc rõ chữ, câu lệnh SQL và bảng số liệu.
- [ ] **Tài khoản ghi nhớ sẵn:**
  - Tài khoản Admin: `admin` / `admin123`
  - Tài khoản Manager: `manager` / `manager123`

---

## 2. TIMELINE & PHÂN BỔ THỜI GIAN

```
[00:00] ─── Chặng 1: Giới thiệu & Triết lý kiến trúc (1m)
[01:00] ─── Chặng 2: Login Gate & Token URL Cryptographic (1.5m)
[02:30] ─── Chặng 3: Router + Text-to-SQL AI 1 (2m)
[04:30] ─── Chặng 4: Tư vấn Cấu hình AI 2 & Knowledge Graph (1.5m)
[06:00] ─── Chặng 5: Test SQL Injection & Zero-Trust AI 3 (1.5m)
[07:30] ─── Chặng 6: Quản trị CSDL: Index (AI 4), Partition (AI 5), Backup (AI 6) (1.5m)
[09:00] ─── Chặng 7: Kết luận & Mời Hội đồng chấm phản biện
```

---

## 3. KỊCH BẢN THUYẾT TRÌNH & THAO TÁC CHI TIẾT

### Chặng 1: Mở đầu & Tuyên ngôn Kiến trúc (1 phút)

> **Lời thoại mẫu:**
> *"Kính thưa Thầy/Cô trong Hội đồng chấm đồ án Quản trị Cơ sở Dữ liệu!  
> Hôm nay nhóm chúng em xin được trình bày và demo hệ thống: **'Quản Trị Cơ Sở Dữ Liệu Cửa Hàng Linh Kiện Máy Tính Bằng Ngôn Ngữ Tự Nhiên & Bộ 6 Động Cơ Phân Tích Nội Bộ'**.*
>
> *Điểm đặc biệt và là triết lý bất khả xâm phạm của đồ án này: **100% Thuần Python chạy cục bộ — Hoàn toàn KHÔNG sử dụng bất kỳ API trí tuệ nhân tạo bên thứ ba nào (như OpenAI, Gemini hay Claude)**.  
> Toàn bộ logic dịch SQL, tìm kiếm ngữ nghĩa, kiểm toán bảo mật, gợi ý chỉ mục, dự báo phân vùng và tự động sao lưu đều được giải quyết bằng các thuật toán toán học, học máy cổ điển và phân tích cú pháp AST chạy trực tiếp trên máy chủ nội bộ. Điều này đảm bảo: **Chi phí vận hành bằng 0, độ trễ chỉ vài mili-giây và bảo mật dữ liệu doanh nghiệp tuyệt đối**."*

---

### Chặng 2: Cổng Đăng nhập Bảo mật & Phiên làm việc (1.5 phút)

#### 🎯 Thao tác trên màn hình:
1. Đang đứng ở trang Đăng nhập.
2. Thử gõ sai mật khẩu: `admin` / `sai_mat_khau` $\rightarrow$ Nhấn Enter.
3. Nhập mật khẩu đúng: `admin` / `admin123` $\rightarrow$ Nhấn Enter.
4. Chỉ chuột lên thanh địa chỉ trình duyệt: xuất hiện tham số `?t=eyJ...`
5. Nhấn **F5 (Reload trang)**.

> **Lời thoại mẫu:**
> *"Đầu tiên là cổng xác thực an ninh tầng ứng dụng. Mật khẩu của hệ thống không lưu dạng bản rõ mà được mã hóa băm muối an toàn bằng thuật toán **Bcrypt** thông qua hàm `SECURITY DEFINER` trong PostgreSQL.  
> Nếu em cố tình dò mật khẩu quá 5 lần, cơ chế Brute-force Lockout sẽ tạm khóa đăng nhập trong 60 giây.  
> 
> Bây giờ em đăng nhập bằng tài khoản Quản Trị Viên `admin`. Thầy/Cô có thể thấy, trên URL lập tức sinh ra một chuỗi **Token HMAC có chữ ký mật mã `?t=...`**.  
> Khi người dùng bấm F5 tải lại trang, hệ thống tự động giải mã và xác thực chữ ký token để duy trì phiên làm việc mà không làm mất trạng thái, đồng thời ngăn chặn hoàn toàn việc người dùng tự sửa URL để leo thang đặc quyền."*

---

### Chặng 3: Demo Bộ đôi Router & Text-to-SQL AI 1 (2 phút)

#### 🎯 Thao tác trên màn hình:
1. Đang ở **Tab 1: Truy vấn · AI 1–2**.
2. Nhập câu hỏi nghiệp vụ vào ô input:
   ```
   Các linh kiện có giá từ 1 triệu đến 3 triệu
   ```
3. Nhấn nút **Thực thi**.
4. Màn hình hiển thị:
   - Huy hiệu xanh: `Định tuyến: AI 1 (NL2SQL)` kèm thời gian xử lý siêu tốc ($\sim 15\text{ms}$).
   - Bảng kết quả dữ liệu trả về từ PostgreSQL.
   - Mở rộng khung xem câu lệnh SQL sinh ra và Giải thích logic.
5. Tiếp tục thử một câu hỏi nâng cao (Cấp độ 3):
   ```
   Top 5 sản phẩm bán chạy nhất của cửa hàng
   ```
6. Nhấn **Thực thi** $\rightarrow$ Quan sát kết quả JOIN 3 bảng phức tạp (`SanPham`, `ChiTietDonHang`, `DonHang`).

> **Lời thoại mẫu:**
> *"Tại Tab Truy vấn chính, hệ thống tích hợp **Bộ định tuyến thông minh (Query Router)**. Người dùng không cần quan tâm câu hỏi thuộc loại nào, chỉ cần gõ tiếng Việt tự nhiên.  
> 
> Với câu hỏi: 'Các linh kiện có giá từ 1 triệu đến 3 triệu':  
> - Router phân tích tín hiệu và nhận diện ngay đây là câu hỏi lọc dữ liệu nghiệp vụ, lập tức giao cho **AI 1 (NL2SQL Engine)**.  
> - Pipeline 5 bước của AI 1 đã: Chuẩn hóa từ đồng nghĩa, phân loại trúng Intent `FILTER_PRODUCTS_BY_PRICE_RANGE`, bóc tách thực thể giá tiền `min_price = 1,000,000` và `max_price = 3,000,000`.  
> - Điểm tối quan trọng trong môn CSDL: Câu lệnh SQL sinh ra là **Parameterized Query sử dụng tuple `%s`**, tuyệt đối không nối chuỗi f-string, được thực thi dưới quyền Role chỉ đọc `text2sql_readonly` có giới hạn `statement_timeout = 3s` và `search_path` khóa chặt ở schema `LinhKien`."*

---

### Chặng 4: Demo Tư vấn Cấu hình Phần cứng AI 2 (1.5 phút)

#### 🎯 Thao tác trên màn hình:
1. Vẫn ở Tab 1, xóa ô nhập liệu và gõ câu hỏi tư vấn:
   ```
   Tư vấn cho tôi cấu hình PC chơi game nặng khoảng 25 triệu
   ```
2. Nhấn nút **Thực thi**.
3. Quan sát màn hình:
   - Huy hiệu đổi sang: `Định tuyến: AI 2 (Semantic Search & Knowledge Graph)`.
   - Bảng đề xuất linh kiện đồng bộ hiển thị đầy đủ: CPU, VGA, Mainboard, RAM, Nguồn, Ổ cứng kèm tổng giá tiền bám sát 25 triệu.
   - Nhấn mở chi tiết một linh kiện: hiển thị thông số kỹ thuật JSONB (Socket, TDP, VRAM,...).

> **Lời thoại mẫu:**
> *"Bây giờ, em đổi sang một câu hỏi mang tính tư vấn tiêu dùng: 'Tư vấn cho tôi cấu hình PC chơi game nặng khoảng 25 triệu'.  
> Thầy/Cô có thể thấy, **Router đã lập tức bắt được tín hiệu tư vấn** và tự động chuyển luồng sang **AI 2**.  
> 
> AI 2 sử dụng thuật toán **Hybrid Ranking kết hợp Đồ thị Tri thức Phần cứng (Hardware Knowledge Graph)**:  
> - Nó không chỉ tìm kiếm văn bản đơn thuần bằng TF-IDF từ và ký tự, mà còn phẳng hóa trường dữ liệu JSONB `thong_so_ky_thuat`.  
> - Đặc biệt, hệ thống kiểm tra logic tương thích phần cứng: Đảm bảo Mainboard và CPU phải trùng chuẩn Socket (như LGA1700), và công suất bộ nguồn PSU phải lớn hơn tổng điện năng tiêu thụ TDP của CPU và Card đồ họa cộng thêm 150W an toàn."*

---

### Chặng 5: Thử thách Hacker — Giám sát An ninh Zero-Trust AI 3 (1.5 phút)

#### 🎯 Thao tác trên màn hình:
1. Nhập vào ô truy vấn một câu lệnh tấn công SQL Injection kinh điển:
   ```
   Top 5 sản phẩm'; DROP TABLE "LinhKien"."SanPham"; --
   ```
2. Nhấn nút **Thực thi**.
3. Màn hình lập tức hiện cảnh báo đỏ:
   > ⛔ **TRUY VẤN BỊ CHẶN BỞI AI 3 (ZERO-TRUST SECURITY SENTINEL)**  
   > *Lý do: Phát hiện node câu lệnh phá hoại DDL (DROP TABLE) qua phân tích cây cú pháp AST. Điểm rủi ro: 95/100 (HIGH).*
4. Chuyển sang **Tab 2: Giám sát an toàn · AI 3**.
5. Cho Thầy/Cô xem bảng **Security Audit Log (Nhật ký kiểm toán thời gian thực)**: Hành vi vừa rồi đã được ghi lại rõ ràng (Thời gian, User, Câu lệnh, Điểm rủi ro, Trạng thái BLOCKED).
6. Chỉ vào các chỉ số: Số truy vấn an toàn, Số vụ tấn công bị chặn, Điểm rủi ro trung bình.

> **Lời thoại mẫu:**
> *"Bây giờ là phần kiểm thử an ninh tối thượng: Em sẽ đóng vai một kẻ tấn công cố tình chèn mã độc phá hoại CSDL: `Top 5 sản phẩm'; DROP TABLE ...; --`.  
> 
> Thầy/Cô có thể thấy, hệ thống đã **chặn đứng ngay lập tức**!  
> Khác với các hệ thống lọc từ khóa thô sơ rất dễ bị qua mặt, **AI 3 sử dụng thư viện `sqlglot` để phân tích Cây cú pháp trừu tượng (AST Parsing)**. Nó bóc tách cấu trúc câu lệnh thành các node cú pháp và phát hiện node `exp.Drop` nguy hiểm.  
> Ma trận chấm điểm rủi ro đa nhân tố đã chấm hành vi này 95/100 điểm rủi ro (Mức CRITICAL), kích hoạt cơ chế tự vệ, ngăn chặn thực thi và ghi vết toàn bộ vào file nhật ký kiểm toán độc lập `security_audit.jsonl`."*

---

### Chặng 6: Bộ Ba Quản Trị CSDL Chuyên Sâu AI 4, AI 5, AI 6 (1.5 phút)

#### 🎯 Thao tác trên màn hình:
1. Chuyển sang **Tab 3: Cố vấn chỉ mục · AI 4**:
   - Chọn bảng `DonHang` $\rightarrow$ Bấm **Phân tích chỉ mục**.
   - Quan sát cây quyết định: Bảng có trên 1,000 dòng, kiểm tra độ chọn lọc, và hiển thị đề xuất:
     ```sql
     CREATE INDEX CONCURRENTLY idx_donhang_trangthai_partial 
     ON "LinhKien"."DonHang"(trang_thai) 
     WHERE trang_thai = 'hoan_thanh';
     ```
   - Nêu rõ: Đề xuất **Partial Index** giúp tiết kiệm $80\%$ dung lượng đĩa so với index thường, và từ khóa `CONCURRENTLY` giúp tạo index mà **không khóa bảng**.

2. Chuyển sang **Tab 4: Quy hoạch phân vùng · AI 5**:
   - Màn hình hiển thị đồ thị tăng trưởng số lượng đơn hàng theo tháng.
   - Chỉ vào đường dự báo tương lai kèm dải màu **Khoảng tin cậy 95% ($\pm 1.96 \cdot \text{SE}$)** sinh từ mô hình Hồi quy tuyến tính OLS.
   - Kéo xuống xem bảng so sánh sai số Backtest (chọn mô hình có $\text{MAE}$ thấp nhất) và kịch bản di chuyển bảng sang Partitioned Table 5 bước an toàn.

3. Chuyển sang **Tab 5: Sao lưu & phục hồi · AI 6**:
   - Chỉ vào đồng hồ đo **Điểm rủi ro mất dữ liệu (Data Loss Risk Score)**: Dựa trên RPO thực tế, trạng thái WAL Archiving và dung lượng ổ đĩa.
   - Bấm nút **Tạo bản sao lưu ngay**: Hệ thống gọi `pg_dump` tạo file nén, sau đó lập tức tính toán mã băm mật mã **SHA-256 Checksum** để niêm phong tính toàn vẹn của tệp sao lưu.

> **Lời thoại mẫu:**
> *"Ba tab tiếp theo chính là trái tim của môn học Quản trị CSDL:  
> - **AI 4 (Index Advisor):** Dựa trên cây quyết định khảo sát catalog thật (`pg_class`, `pg_index`), đề xuất đúng loại chỉ mục như Partial Index hay GIN Index, sinh DDL kèm lệnh `CONCURRENTLY` an toàn cho môi trường Production.  
> - **AI 5 (Partitioning Planner):** Ứng dụng hồi quy tuyến tính OLS và kiểm định đối chứng Backtesting, dự báo thời điểm bảng vượt ngưỡng 1 triệu bản ghi để lập kế hoạch phân vùng theo dải thời gian mà không gây gián đoạn hệ thống.  
> - **AI 6 (Smart Backup):** Đánh giá rủi ro RPO/RTO theo thời gian thực và bảo vệ bản sao lưu bằng mã băm SHA-256 Checksum, đảm bảo nếu file backup bị lỗi ổ cứng hoặc bị sửa đổi dù chỉ 1 byte thì hệ thống sẽ từ chối phục hồi để bảo vệ tính toàn vẹn CSDL."*

---

### Chặng 7: Kết luận & Chuyển sang phần Q&A (0.5 phút)

> **Lời thoại mẫu:**
> *"Kính thưa Hội đồng, toàn bộ hệ thống từ tầng Giao diện Streamlit, Bộ định tuyến Router đến 6 Động cơ AI phân tích đều đã hoạt động đồng bộ, chuẩn xác và vượt qua 24/24 unit test tự động với độ chính xác đạt 100%.  
> 
> Nhóm chúng em xin chân thành cảm ơn Thầy/Cô đã lắng nghe và rất mong nhận được những câu hỏi nhận xét, góp ý từ Hội đồng để hoàn thiện đồ án tốt hơn nữa ạ!"*

---

## 4. BỘ CÂU HỎI PHẢN BIỆN CỦA HỘI ĐỒNG & CÁCH ĐỐI ĐÁP CHUẨN XÁC

Dưới đây là 6 câu hỏi kinh điển mà các Giảng viên Quản trị CSDL rất hay hỏi, kèm câu trả lời "ăn điểm tuyệt đối":

---

### ❓ Câu 1: "Tại sao nhóm không dùng OpenAI API hay LLM có sẵn mà lại tự xây dựng Rule Engine bằng Python?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, nhóm chọn giải pháp 100% Python thuần cục bộ vì 3 lý do cốt lõi trong doanh nghiệp:  
> 1. **Bảo mật dữ liệu tối thượng (Data Privacy):** Dữ liệu kinh doanh, khách hàng và cấu trúc bảng nội bộ không bao giờ bị gửi ra máy chủ nước ngoài của bên thứ ba.  
> 2. **Độ trễ và Tính ổn định:** Mô hình Rule Engine cục bộ phản hồi trong 10 đến 20 mili-giây, không phụ thuộc kết nối Internet, không lo rớt mạng hay nghẽn API.  
> 3. **Tính tiền định và Kiểm soát tuyệt đối (Determinism):** LLM có hiện tượng 'ảo giác' (hallucination) có thể sinh ra câu SQL sai lệch hoặc nguy hiểm. Trong khi Rule Engine của nhóm ánh xạ chính xác $100\%$ vào các mẫu SQL đã được kiểm duyệt và kiểm thử nghiêm ngặt."*

---

### ❓ Câu 2: "Hệ thống bảo vệ CSDL chống SQL Injection bằng cách nào?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, hệ thống bảo vệ theo nguyên tắc phòng thủ theo chiều sâu (Defense-in-depth) qua 4 lớp:  
> 1. **Tầng phân quyền PostgreSQL:** Toàn bộ truy vấn từ web chạy qua Role `text2sql_readonly` chỉ có quyền `SELECT`, bị `REVOKE` toàn bộ quyền `INSERT/UPDATE/DELETE/DROP` và bị giới hạn `statement_timeout = 3s`.  
> 2. **Tầng sinh mã SQL:** Tuyệt đối không nối chuỗi (no f-string), luôn dùng Parameterized Query (`%s`) của thư viện `psycopg2`, tách rời mã lệnh và dữ liệu đầu vào.  
> 3. **Tầng phân tích cú pháp AST (AI 3):** Sử dụng `sqlglot` dịch câu lệnh thành cây cú pháp, phát hiện và chặn đứng mọi node phá hoại (`exp.Drop`, `exp.Delete`,...).  
> 4. **Tầng giám sát hành vi:** Chặn câu lệnh đa tầng (ngăn cách dấu `;`), phát hiện quét catalog và khóa phiên nếu vi phạm liên tục."*

---

### ❓ Câu 3: "Khi nào thì Index Advisor (AI 4) quyết định đề xuất Partial Index thay vì Index thông thường?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, AI 4 nhận diện các cột có **độ biến thiên giá trị thấp (Low-cardinality)** như cột `trang_thai` (chỉ có vài giá trị: `cho_xu_ly`, `hoan_thanh`, `da_huy`) hoặc `dang_kinh_doanh` (`true/false`).  
> Nếu tạo B-Tree index toàn bộ trên các cột này, cây chỉ mục sẽ rất lớn và lãng phí vì trùng lặp nhiều. AI 4 sẽ phân tích mệnh đề `WHERE` và đề xuất **Partial Index** chỉ đánh chỉ mục trên các dòng có giá trị thường xuyên được tìm kiếm (ví dụ: `WHERE trang_thai = 'hoan_thanh'`). Điều này giúp giảm tới $80\%$ kích thước tệp index trên đĩa và tăng tốc độ ghi dữ liệu đáng kể ạ."*

---

### ❓ Câu 4: "Tại sao trong câu lệnh CREATE INDEX của AI 4 lại luôn có từ khóa CONCURRENTLY?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, trong môi trường sản xuất thực tế (Production), lệnh `CREATE INDEX` thông thường sẽ áp đặt một khóa độc quyền (ShareLock) lên bảng, chặn toàn bộ các thao tác ghi dữ liệu (`INSERT`, `UPDATE`, `DELETE`) của khách hàng cho đến khi đánh chỉ mục xong.  
> Với từ khóa `CONCURRENTLY`, PostgreSQL sẽ quét bảng hai lần và xây dựng index ở chế độ nền **mà không hề khóa bảng**. Khách hàng vẫn mua hàng và tạo đơn bình thường, đảm bảo tính sẵn sàng cao (High Availability) cho hệ thống cửa hàng ạ."*

---

### ❓ Câu 5: "Mô hình dự báo phân vùng (AI 5) xử lý vấn đề tháng thiếu dữ liệu như thế nào?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, nếu chỉ truy vấn `GROUP BY DATE_TRUNC('month', ngay_tao)` thông thường, các tháng cửa hàng không phát sinh đơn hàng sẽ bị biến mất khỏi bảng kết quả, làm đứt gãy chuỗi thời gian và gây sai lệch hệ số góc của mô hình hồi quy.  
> Để xử lý triệt để, nhóm sử dụng hàm `generate_series` của PostgreSQL để tạo một trục thời gian liên tục đầy đủ các tháng từ điểm bắt đầu đến hiện tại, sau đó `LEFT JOIN` với bảng `DonHang` và dùng `COALESCE(count, 0)`. Nhờ vậy, chuỗi dữ liệu đầu vào của mô hình hồi quy luôn chuẩn xác $100\%$ về mặt toán học ạ."*

---

### ❓ Câu 6: "Mã băm SHA-256 trong module Backup (AI 6) có vai trò gì trong quản trị CSDL?"
> **💡 Cách trả lời:**  
> *"Dạ thưa Thầy/Cô, một trong những thảm họa lớn nhất của quản trị CSDL là khi xảy ra sự cố, người quản trị lấy bản backup ra để khôi phục nhưng phát hiện file backup đã bị hỏng ngầm do lỗi phần cứng (silent corruption) hoặc bị mã độc can thiệp sửa đổi.  
> Khi AI 6 tạo file backup, hệ thống ngay lập tức đọc từng khối $64\text{ KB}$ và tính mã băm mật mã **SHA-256 Checksum** để niêm phong lại. Trước khi thực hiện lệnh `RESTORE`, hệ thống băm lại tệp và đối chiếu: Nếu sai khác dù chỉ một bit duy nhất, hệ thống sẽ cảnh báo đỏ và từ chối khôi phục để bảo vệ tính toàn vẹn của CSDL ạ."*

---

*Chúc bạn có một buổi thuyết trình tự tin, mạch lạc và đạt điểm số xuất sắc nhất!*
