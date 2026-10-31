# AI SERVICE: HỆ THỐNG 6 PHÂN HỆ PHÂN TÍCH THÔNG MINH CHO POSTGRESQL

Phân hệ dịch vụ thông minh hỗ trợ người dùng và Quản trị viên CSDL (DBA) cho cơ sở dữ liệu **LinhKien_DB**, hoạt động **100% bằng Python thuần cục bộ**, không phụ thuộc bất kỳ API AI đám mây bên thứ ba.

---

## 1. Cấu Trúc Thư Mục Module

```text
ai_service/
├── app/
│   ├── ai_1_text2sql/          # Module 1: Xử lý ngôn ngữ tự nhiên tiếng Việt -> SQL
│   │   ├── text_normalizer.py  # Chuẩn hóa tiếng Việt, đồng nghĩa, bóc tách dấu
│   │   ├── schema_catalog.py   # Allowlist bảng/cột, danh mục, thương hiệu
│   │   ├── intent_classifier.py# Phân loại ý định bằng Regex & quy tắc ưu tiên
│   │   ├── entity_extractor.py # Trích xuất giá (triệu, k, đ), top N, hãng, danh mục
│   │   ├── query_templates.py  # SQL templates an toàn có placeholder %s
│   │   ├── sql_builder.py      # Ghép tham số SQL chống SQLi
│   │   ├── explanation.py      # Tạo lời giải thích quy tắc rõ ràng
│   │   └── ml_classifier.py    # Fallback phân loại ý định bằng Scikit-Learn
│   │
│   ├── ai_2_semantic/          # Module 2: Tìm kiếm & tư vấn linh kiện theo nhu cầu
│   │   ├── search_engine.py    # TF-IDF, N-gram, Character-level n-gram
│   │   └── knowledge_graph.py  # Đồ thị tri thức thông số tương thích linh kiện
│   │
│   ├── ai_3_security/          # Module 3: Zero-Trust Sentinel & An toàn truy vấn
│   │   ├── sentinel.py         # Bộ lọc 4 lớp an ninh: Regex, AST Parser, Anomaly
│   │   └── outliner_detector.py# Phát hiện đơn hàng bất thường bằng Z-score & IQR
│   │
│   ├── ai_4_index_advisor/     # Module 4: Khuyến nghị chỉ mục thông minh
│   │   └── advisor.py          # Phân tích EXPLAIN, chi phí câu lệnh & đề xuất Index
│   │
│   ├── ai_5_partitioning/      # Module 5: Quy hoạch phân vùng bảng
│   │   └── planner.py          # Giám sát dung lượng & đề xuất Range/List/Hash
│   │
│   ├── ai_6_smart_backup/      # Module 6: Sao lưu thông minh & Phục hồi thảm họa
│   │   └── backup_manager.py   # Quản lý sao lưu 3 tầng, nén gzip, tự kiểm tra file
│   │
│   ├── auth.py                 # Xác thực tài khoản, băm bcrypt, phân quyền
│   ├── config.py               # Đọc và quản lý biến môi trường .env
│   ├── db.py                   # Kết nối psycopg2, Connection Pool, kiểm soát timeout
│   ├── learning_loop.py        # Vòng lặp tự học từ câu chưa hiểu (Human-in-the-loop)
│   ├── router.py               # Bộ định tuyến câu hỏi thông minh
│   ├── schemas.py              # Pydantic models
│   └── main.py                 # FastAPI server (tùy chọn)
│
├── tests/                      # 13 file Unit Tests kiểm thử tự động (172 test cases)
├── web_app.py                  # Giao diện Web quản trị Streamlit
├── run_app.py                  # Launcher chạy ứng dụng nhanh
└── requirements.txt            # Danh sách thư viện cần thiết
```

---

## 2. Hướng Dẫn Cài Đặt & Khởi Chạy

### Bước 1: Cài đặt thư viện
```powershell
pip install -r requirements.txt
```

### Bước 2: Chạy kiểm thử tự động (172 Unit Tests)
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

### Bước 3: Khởi động Giao diện Quản trị Web (Streamlit)
```powershell
# Chạy qua launcher nhanh:
python run_app.py

# Hoặc chạy trực tiếp bằng lệnh Streamlit:
streamlit run web_app.py
```
Giao diện sẽ tự động mở tại: `http://localhost:8501`

---

## 3. Tài Khoản Thử Nghiệm

| Tài khoản | Mật khẩu | Quyền hạn |
| :--- | :--- | :--- |
| `admin` | `admin123` | Quản trị viên (Toàn quyền 6 module) |
| `manager` | `manager123` | Quản lý kinh doanh (AI 1, AI 2, Báo cáo) |
| `nv01` | `password123` | Nhân viên bán hàng (Bị giới hạn bởi RLS) |
| `guest` | `guest123` | Khách vãng lai (Chỉ tra cứu sản phẩm) |
