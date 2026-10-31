# HỆ THỐNG QUẢN TRỊ CSDL VÀ PHÂN TÍCH THÔNG MINH CHO CỬA HÀNG LINH KIỆN MÁY TÍNH
> **Đồ Án Môn Học:** Quản Trị Cơ Sở Dữ Liệu (Database Administration - DBA)  
> **Kiến Trúc Cốt Lõi:** PostgreSQL (`LinhKien_DB`) + 6 Phân Hệ Phân Tích Thông Minh (100% Python Thuần Cục Bộ, Không Gọi API Bên Thứ Ba) + Giao Diện Quản Trị Streamlit.

---

## 📑 MỤC LỤC
1. [Tổng Quan Dự Án & Tiêu Chí Thiết Kế](#1-tổng-quan-dự-án--tiêu-chí-thiết-kế)
2. [Cấu Trúc Thư Mục Dự Án](#2-cấu-trúc-thư-mục-dự-án)
3. [Hướng Dẫn Thiết Lập & Chạy Các File Trong `database/`](#3-hướng-dẫn-thiết-lập--chạy-các-file-trong-database)
   - [3.1. Bảng tra cứu các file database](#31-bảng-tra-cứu-các-file-trong-thư-mục-database)
   - [3.2. Quy trình thiết lập CSDL ban đầu (Khuyến nghị)](#32-quy-trình-thiết-lập-csdl-ban-đầu-khuyến-nghị)
   - [3.3. Quy trình thực thi thủ công từng file SQL (Tùy chọn)](#33-quy-trình-thực-thi-thủ-công-từng-file-sql-tùy-chọn)
   - [3.4. Vận hành ETL làm sạch dữ liệu](#34-vận-hành-etl-làm-sạch-dữ-liệu-khách-hàng-etl_lam_sach_du_lieupy)
   - [3.5. Vận hành bảo trì CSDL định kỳ](#35-vận-hành-bảo-trì-csdl-định-kỳ-bao_tripy)
4. [Hướng Dẫn Cài Đặt Môi Trường & Cấu Hình](#4-hướng-dẫn-cài-đặt-môi-trường--cấu-hình)
5. [Khởi Chạy Ứng Dụng Quản Trị (Streamlit UI)](#5-khởi-chạy-ứng-dụng-quản-trị-streamlit-ui)
6. [Tài Khoản Đăng Nhập & Phân Quyền](#6-tài-khoản-đăng-nhập--phân-quyền)
7. [Chạy Kiểm Thử Tự Động (Unit Tests)](#7-chạy-kiểm-thử-tự-động-unit-tests)

---

## 1. TỔNG QUAN DỰ ÁN & TIÊU CHÍ THIẾT KẾ

Hệ thống được xây dựng nhằm đáp ứng toàn diện các tiêu chuẩn quản trị cơ sở dữ liệu hiện đại cho một chuỗi cửa hàng bán lẻ linh kiện máy tính, kết hợp bộ công cụ phân tích tự động hóa giúp DBA và nhân viên vận hành hiệu quả:

* **100% Python & PostgreSQL thuần:** Không phụ thuộc bất kỳ dịch vụ hay API AI đám mây (OpenAI, Claude, Gemini...), đảm bảo bảo mật dữ liệu nội bộ và chi phí vận hành bằng 0.
* **Bảo Mật Zero-Trust & RLS:**
  * Nguyên tắc đặc quyền tối thiểu: Người dùng truy vấn qua role `text2sql_readonly` chỉ có quyền `SELECT`.
  * Row-Level Security (RLS) gắn chặt với từng nhân viên qua session variable `app.current_user_id`.
  * Column-Level Security (CLS) che giấu giá nhập, chiết khấu và mật khẩu.
  * Mật khẩu được băm bằng thuật toán `bcrypt` có Salt riêng biệt.
* **Hiệu Năng & Tối Ưu CSDL:**
  * Partitioning theo thời gian (Range Partitioning theo tháng) cho bảng dữ liệu biến động cao `lich_su_thay_doi_gia`.
  * Chỉ mục đa dạng: B-Tree trên 10 khóa ngoại, GIN Index trên trường JSONB `thong_so_ky_thuat`.
  * Materialized View tổng hợp doanh thu có cơ chế làm mới định kỳ `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
  * Business Triggers tự động hóa: Tự động tính tổng tiền chi tiết đơn hàng, tự động trừ số lượng tồn kho, ghi log lịch sử giá khi cập nhật.
* **6 Module Trợ Lý DBA Thông Minh:**
  1. `AI 1 - Text2SQL Engine`: Biên dịch câu hỏi tự nhiên tiếng Việt sang SQL chuẩn hóa, an toàn với tham số hóa `%s`.
  2. `AI 2 - Semantic Search`: Đề xuất linh kiện theo nhu cầu người dùng dựa trên TF-IDF, N-gram và Knowledge Graph thông số kỹ thuật.
  3. `AI 3 - Zero-Trust Sentinel`: Bộ lọc an ninh 4 lớp (Regex, AST Parser, Isolation Forest, Z-score) chặn SQL Injection, rò rỉ dữ liệu và phát hiện bất thường.
  4. `AI 4 - Smart Index Advisor`: Phân tích câu lệnh chậm từ `pg_stat_statements`, mô phỏng chi phí `EXPLAIN` và gợi ý chỉ mục tối ưu.
  5. `AI 5 - Partitioning Planner`: Giám sát dung lượng và tốc độ tăng trưởng bảng dữ liệu, tự động đề xuất phân vùng Range/List/Hash.
  6. `AI 6 - Smart Backup & DR`: Lên lịch sao lưu 3 tầng (Full, Schema-only, Data-only), nén gzip, tự động kiểm tra tính toàn vẹn (Self-test verify).

---

## 2. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
Quan_tri_csdl/Cuoi_Ky/
├── database/                                # Tầng Lưu Trữ & Quản Trị CSDL
│   ├── schema.sql                           # Khởi tạo CSDL, schema "LinhKien", 14 bảng, role, app_users
│   ├── sinh_du_lieu.py                      # Script sinh dữ liệu thực tế tiếng Việt (Seed 42)
│   ├── apply_advanced_objects.py            # Script tự động thực thi và kiểm định toàn bộ CSDL nâng cao
│   ├── advanced_objects.sql                 # JSONB, GIN, Regex check, Views, MV, Triggers, RLS/CLS
│   ├── security_hardening.sql               # Siết chặt phân quyền, thu hồi public permissions
│   ├── ai_notify_alerts.sql                 # Tích hợp PostgreSQL NOTIFY cho Sentinel và Z-score
│   ├── nang_cap_bao_mat_toi_uu.sql          # Nâng cấp RLS không thể lách, bcrypt salt, 10 FK index, Partition
│   ├── hoc_tu_cau_chua_hieu.sql             # Bảng lưu nhật ký câu chưa hiểu phục vụ tự học (Human-in-the-loop)
│   ├── turnt_on_statements.sql              # Bật pg_stat_statements phục vụ Index Advisor
│   ├── etl_lam_sach_du_lieu.py              # Pipeline ETL làm sạch dữ liệu khách hàng
│   └── bao_tri.py                           # Kịch bản bảo trì tự động (VACUUM, REFRESH MV, sync role)
│
├── ai_service/                              # Tầng Logic Xử Lý & Ứng Dụng Web
│   ├── app/
│   │   ├── ai_1_text2sql/                   # Module AI 1: Xử lý ngôn ngữ tự nhiên -> SQL
│   │   ├── ai_2_semantic/                   # Module AI 2: Tìm kiếm & tư vấn ngữ nghĩa linh kiện
│   │   ├── ai_3_security/                   # Module AI 3: Zero-Trust Sentinel & giám sát an toàn
│   │   ├── ai_4_index_advisor/              # Module AI 4: Khuyến nghị chỉ mục thông minh
│   │   ├── ai_5_partitioning/               # Module AI 5: Quy hoạch phân vùng bảng
│   │   ├── ai_6_smart_backup/               # Module AI 6: Sao lưu & phục hồi thảm họa
│   │   ├── auth.py                          # Xác thực người dùng, bcrypt, session
│   │   ├── config.py                        # Cấu hình hệ thống, biến môi trường
│   │   ├── db.py                            # Kết nối psycopg2, Connection Pool, an toàn truy vấn
│   │   ├── learning_loop.py                 # Vòng lặp học từ câu chưa hiểu
│   │   └── router.py                        # Bộ định tuyến câu hỏi thông minh
│   ├── tests/                               # 13 file Unit Tests kiểm thử toàn diện (172 test cases)
│   ├── web_app.py                           # Giao diện Web trực quan Streamlit
│   ├── run_app.py                           # Launcher khởi động giao diện nhanh
│   └── requirements.txt                     # Danh sách thư viện Python phụ thuộc
│
└─ .env.example                             # Mẫu cấu hình biến môi trường
```

---

## 3. HƯỚNG DẪN THIẾT LẬP & CHẠY CÁC FILE TRONG `database/`

### 3.1. Bảng tra cứu các file trong thư mục `database/`

| STT | Tên file | Ngôn ngữ | Vai trò / Chức năng |
| :---: | :--- | :---: | :--- |
| **1** | `schema.sql` | SQL | Tạo schema `"LinhKien"`, 14 bảng dữ liệu, domain/kiểu dữ liệu, role `text2sql_readonly`, bảng `app_users`. |
| **2** | `sinh_du_lieu.py` | Python | Sinh dữ liệu mô phỏng thực tế lớn: 1.500 khách hàng, 8.000 đơn hàng, hàng chục ngàn chi tiết đơn và tồn kho. |
| **3** | `apply_advanced_objects.py` | Python | **(Khuyên dùng)** Script chạy tuần tự và kiểm thử tự động toàn bộ 5 file SQL nâng cao (3, 4, 5, 6, 7). |
| **4** | `advanced_objects.sql` | SQL | Cài đặt trường JSONB, GIN Index, ràng buộc Regex, Views, Materialized View, Triggers tự động hóa và RLS. |
| **5** | `security_hardening.sql` | SQL | Siết chặt bảo mật CSDL, thu hồi quyền truy cập `public`, cấp quyền đúng nguyên tắc đặc quyền tối thiểu. |
| **6** | `ai_notify_alerts.sql` | SQL | Tạo channel `pg_notify` cho PostgreSQL gửi cảnh báo real-time tới AI 3 Sentinel khi phát hiện bất thường. |
| **7** | `nang_cap_bao_mat_toi_uu.sql` | SQL | Nâng cấp RLS không thể lách qua `tai_khoan_nhan_vien`, băm mật khẩu `bcrypt`, tạo 10 FK index, phân vùng bảng giá. |
| **8** | `hoc_tu_cau_chua_hieu.sql` | SQL | Tạo bảng `cau_hoi_chua_hieu` và `lich_su_huan_luyen` phục vụ quy trình Human-in-the-loop cho AI 1 & AI 2. |
| **9** | `turnt_on_statements.sql` | SQL | Bật extension `pg_stat_statements` để hệ điều hành PostgreSQL ghi nhận thời gian chạy của các câu lệnh. |
| **10**| `etl_lam_sach_du_lieu.py` | Python | Chứng minh tiêu chí "Dữ liệu sạch": Đưa dữ liệu thô vào staging, chuẩn hóa loại bỏ lỗi/trùng lặp, nạp vào CSDL. |
| **11**| `bao_tri.py` | Python | Tự động hóa bảo trì: `VACUUM ANALYZE`, làm mới Materialized View không khóa bảng, tạo phân vùng tháng mới. |

---

### 3.2. Quy trình thiết lập CSDL ban đầu (Khuyến nghị)

Đây là quy trình nhanh nhất, chuẩn xác nhất và ít lỗi nhất bằng cách kết hợp `psql` và script Python tự động hóa có sẵn.

#### Bước 1: Tạo Database và Schema cơ sở
Mở Terminal / PowerShell và chạy:
```powershell
# Chạy với user postgres (nhập mật khẩu khi được hỏi):
psql -U postgres -f database/schema.sql
```
> **Kết quả:** Database `LinhKien_DB` được tạo, thiết lập schema `"LinhKien"`, tạo 14 bảng quan hệ, bảng `app_users` và role `text2sql_readonly`.

#### Bước 2: Nạp dữ liệu mô phỏng lớn
Chạy script sinh dữ liệu chuẩn hóa (đã cố định hạt giống ngẫu nhiên `SEED = 42` để kết quả nhất quán):
```powershell
# Cách 1: Truyền trực tiếp mật khẩu postgres qua tham số --password
python database/sinh_du_lieu.py --password MAT_KHAU_POSTGRES

# Cách 2: Nếu đã tạo file .env hoặc đặt biến PGPASSWORD
python database/sinh_du_lieu.py
```
> **Kết quả:** Nạp xong 12 danh mục, 20 thương hiệu, 80 nhà cung cấp, 25 chi nhánh, 120 nhân viên, 1.500 khách hàng, 8.000 đơn hàng cùng toàn bộ chi tiết và phiếu nhập kho.

#### Bước 3: Áp dụng toàn bộ đối tượng nâng cao, triggers và bảo mật
Chạy script tổng hợp `apply_advanced_objects.py`:
```powershell
python database/apply_advanced_objects.py
```
Script này sẽ tự động:
1. Nạp `advanced_objects.sql` (JSONB, Triggers tính tiền, Trừ kho, Audit giá, RLS).
2. Nạp `security_hardening.sql` (Siết bảo mật schema).
3. Nạp `ai_notify_alerts.sql` (PostgreSQL NOTIFY channel).
4. Nạp `nang_cap_bao_mat_toi_uu.sql` (RLS nhân viên, mật khẩu bcrypt, 10 FK indexes, Range partitioning).
5. Nạp `hoc_tu_cau_chua_hieu.sql` (Bảng tự học Human-in-the-loop).
6. Tự động chạy bộ kiểm định (Self-Check Test) xác nhận mọi trigger và quyền hạn hoạt động chính xác 100%.

#### Bước 4: Bật Extension giám sát hiệu năng truy vấn
Chạy lệnh kích hoạt extension:
```powershell
psql -U postgres -d LinhKien_DB -f database/turnt_on_statements.sql
```
> **Lưu ý:** Extension `pg_stat_statements` cần được khai báo trong file cấu hình `postgresql.conf` (`shared_preload_libraries = 'pg_stat_statements'`). Nếu PostgreSQL chưa cấu hình dòng này, AI 4 vẫn hoạt động bình thường qua chế độ phân tích truy vấn độc lập.

---

### 3.3. Quy trình thực thi thủ công từng file SQL (Tùy chọn)

Nếu bạn muốn thực thi từng file bằng công cụ dòng lệnh `psql` hoặc chạy qua giao diện **pgAdmin / DBeaver**, hãy thực hiện đúng theo thứ tự sau:

```powershell
# 1. Tạo cấu trúc bảng
psql -U postgres -f database/schema.sql

# 2. Sinh dữ liệu
python database/sinh_du_lieu.py --password MAT_KHAU_POSTGRES

# 3. Nạp đối tượng nâng cao (JSONB, GIN, Views, Triggers, RLS ban đầu)
psql -U postgres -d LinhKien_DB -f database/advanced_objects.sql

# 4. Siết chặt quyền bảo mật
psql -U postgres -d LinhKien_DB -f database/security_hardening.sql

# 5. Cài đặt channel cảnh báo bất thường
psql -U postgres -d LinhKien_DB -f database/ai_notify_alerts.sql

# 6. Nâng cấp RLS gắn nhân viên, băm bcrypt, chỉ mục khóa ngoại & phân vùng
psql -U postgres -d LinhKien_DB -f database/nang_cap_bao_mat_toi_uu.sql

# 7. Tạo bảng lưu trữ câu hỏi chưa hiểu cho AI tự học
psql -U postgres -d LinhKien_DB -f database/hoc_tu_cau_chua_hieu.sql

# 8. Bật pg_stat_statements
psql -U postgres -d LinhKien_DB -f database/turnt_on_statements.sql
```

---

### 3.4. Vận hành ETL làm sạch dữ liệu khách hàng (`etl_lam_sach_du_lieu.py`)

File này chứng minh năng lực xử lý dữ liệu chuẩn DBA: Dữ liệu bẩn từ bên ngoài không được nạp thẳng vào bảng chính mà phải qua vùng đệm `staging` và được làm sạch bằng Python.

* **Bước 1: Sinh dữ liệu mẫu bẩn vào vùng đệm staging (khoảng trắng thừa, số điện thoại sai định dạng, email hoa/thường, trùng lặp...):**
  ```powershell
  python database/etl_lam_sach_du_lieu.py --tao-du-lieu-ban 40
  ```
* **Bước 2: Chạy thử nghiệm làm sạch (Dry-run, chỉ in kết quả phân tích, chưa ghi vào DB chính):**
  ```powershell
  python database/etl_lam_sach_du_lieu.py --chay-thu
  ```
* **Bước 3: Thực thi làm sạch và nạp dữ liệu sạch vào bảng `khach_hang`:**
  ```powershell
  python database/etl_lam_sach_du_lieu.py
  ```
* **Bước 4: Hoàn tác (nếu muốn xóa các dữ liệu khách hàng vừa được ETL nạp vào để thử nghiệm lại):**
  ```powershell
  python database/etl_lam_sach_du_lieu.py --hoan-tac
  ```

---

### 3.5. Vận hành bảo trì CSDL định kỳ (`bao_tri.py`)

Script thực hiện các tác vụ DBA tự động: dọn dẹp dòng rác (`VACUUM ANALYZE`), làm mới `Materialized View` đồng thời (`CONCURRENTLY`), đồng bộ tài khoản RLS cho nhân viên mới và tự động tạo trước bảng phân vùng cho tháng kế tiếp.

* **Chạy bảo trì ngay lập tức:**
  ```powershell
  python database/bao_tri.py
  ```
* **Chỉ kiểm tra và xuất báo cáo sức khỏe CSDL (Tỷ lệ dòng chết, bảng thiếu ANALYZE, Cache Hit Ratio):**
  ```powershell
  python database/bao_tri.py --chi-bao-cao
  ```
* **Lên lịch chạy tự động định kỳ 2h sáng hàng ngày (Windows Task Scheduler):**
  ```cmd
  schtasks /Create /TN "LinhKien_BaoTri" /SC DAILY /ST 02:00 /TR "python D:\PhạmTiếnĐạt\Quan_tri_csdl\Cuoi_Ky\database\bao_tri.py"
  ```
  *(Kết quả bảo trì được ghi nhật ký tự động vào file `ai_service/logs/bao_tri.log`)*.

---

## 4. HƯỚNG DẪN CÀI ĐẶT MÔI TRƯỜNG & CẤU HÌNH

### 4.1. Yêu cầu hệ thống
* Python >= 3.10
* PostgreSQL >= 14 (Khuyến nghị 16 hoặc 17)

### 4.2. Cài đặt các thư viện Python
Mở Terminal tại thư mục gốc của dự án:
```powershell
# Cài đặt toàn bộ thư viện cần thiết
pip install -r ai_service/requirements.txt
```

### 4.3. Thiết lập biến môi trường (`.env`)
Tạo một file `.env` tại thư mục gốc hoặc trong `ai_service/.env` (tham khảo file `.env.example`):
```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=LinhKien_DB
DB_SCHEMA=LinhKien

# Tài khoản chỉ đọc cho người dùng / AI 1 & AI 2
DB_USER=text2sql_readonly
DB_PASSWORD=your_readonly_password

# Tài khoản quản trị CSDL chạy phân hệ DBA (AI 4, AI 5, AI 6, Bảo trì, ETL)
DB_ADMIN_USER=postgres
DB_ADMIN_PASSWORD=your_postgres_password

ALLOW_ADMIN_CONNECTION=true
```

---

## 5. KHỞI CHẠY ỨNG DỤNG QUẢN TRỊ (STREAMLIT UI)

Hệ thống cung cấp giao diện quản trị Clean Enterprise, trực quan và không bị "mùi AI", tích hợp toàn bộ chức năng vào thanh điều hướng bên trái:

```powershell
# Cách 1: Khởi động qua script launcher
python ai_service/run_app.py

# Cách 2: Khởi động trực tiếp bằng lệnh Streamlit
streamlit run ai_service/web_app.py
```

Ứng dụng sẽ tự động mở trên trình duyệt tại địa chỉ:
👉 **`http://localhost:8501`**

---

## 6. TÀI KHOẢN ĐĂNG NHẬP & PHÂN QUYỀN

Hệ thống tích hợp bảng quản lý `app_users` với mật khẩu băm bảo mật `bcrypt`:

| Tên Đăng Nhập | Mật Khẩu | Vai Trò (Role) | Phạm Vi Quyền Hạn |
| :--- | :--- | :---: | :--- |
| **`admin`** | `admin123` | **ADMIN** | Toàn quyền: Xem toàn bộ dữ liệu, chạy AI 1–6, xem báo cáo DBA, cấu hình sao lưu và phân vùng. |
| **`manager`** | `manager123` | **MANAGER** | Quản lý: Xem doanh thu, đơn hàng, truy vấn Text2SQL, semantic search, giám sát cảnh báo an toàn. |
---

## 7. CHẠY KIỂM THỬ TỰ ĐỘNG (UNIT TESTS)

Dự án đi kèm bộ kiểm thử tự động toàn diện gồm **172 Test Cases** bao phủ toàn bộ 6 module AI, luồng an toàn, trích xuất thực thể và bảo mật SQL:

```powershell
# Chạy toàn bộ 172 unit test cases
python -m unittest discover -s ai_service/tests -p "test_*.py"
```

**Kết quả kiểm thử chuẩn:**
```text
Ran 172 tests in 3.42s
OK
```

---
*Dự án phục vụ bảo vệ môn học Quản Trị Cơ Sở Dữ Liệu.*
