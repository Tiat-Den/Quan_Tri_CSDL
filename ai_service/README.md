# AI SERVICE: TEXT-TO-SQL RULE ENGINE (PYTHON)

Dịch vụ phân tích ngôn ngữ tự nhiên tiếng Việt và sinh câu truy vấn SQL an toàn cho CSDL **LinhKien_DB** hoàn toàn bằng **tập luật (Rule-based)**, không gọi API LLM bên ngoài.

---

## 1. Cấu trúc thư mục

```text
ai_service/
├── app/
│   ├── __init__.py
│   ├── config.py             # Cấu hình host, port, limit
│   ├── schemas.py            # Pydantic request/response model
│   ├── text_normalizer.py    # Chuẩn hóa tiếng Việt, đồng nghĩa, bỏ dấu
│   ├── schema_catalog.py     # Allowlist bảng/cột, danh mục, thương hiệu
│   ├── intent_classifier.py  # Phân loại ý định bằng Regex & quy tắc ưu tiên
│   ├── entity_extractor.py   # Trích xuất giá (triệu, k, vnđ), top N, hãng, danh mục
│   ├── query_templates.py    # Template SQL an toàn có placeholder %s
│   ├── sql_builder.py        # Ghép SQL và tham số an toàn
│   ├── explanation.py        # Tạo lời giải thích quy tắc rõ ràng
│   └── main.py               # FastAPI server cung cấp endpoint RESTful
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py      # Unit tests kiểm tra độ chính xác của tập luật
├── requirements.txt
└── README.md
```

---

## 2. Cách chạy ứng dụng

### Bước 1: Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### Bước 2: Chạy kiểm thử tự động (Unit Test)
```bash
python -m unittest discover -s tests
```

### Bước 3: Khởi động Server API (FastAPI)
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
Hoặc:
```bash
python -m app.main
```

Tài liệu Swagger UI tương tác sẽ có tại: `http://127.0.0.1:8001/docs`

### Bước 4: Khởi động Giao diện Web Trực quan (Streamlit)
```bash
# Cách 1: Chạy trực tiếp qua Streamlit
streamlit run web_app.py

# Hoặc đứng từ thư mục gốc dự án:
streamlit run ai_service/web_app.py

# Cách 2: Chạy qua launcher nhanh
python run_app.py
```
Ứng dụng sẽ tự động mở giao diện tại: `http://localhost:8501`

---

## 3. Danh sách Endpoints

| Method | Endpoint | Mô tả |
| :---: | :--- | :--- |
| `GET` | `/health` | Kiểm tra tình trạng hoạt động của service |
| `GET` | `/intents` | Lấy danh sách các Intent đang hỗ trợ và câu hỏi mẫu |
| `POST` | `/interpret` | Nhận câu hỏi tiếng Việt, trả về Intent, SQL và giải thích |

### Ví dụ Request:
```json
{
  "question": "Top 5 sản phẩm đắt nhất"
}
```

### Ví dụ Response:
```json
{
  "success": true,
  "question": "Top 5 sản phẩm đắt nhất",
  "normalized_question": "top 5 sản phẩm đắt nhất",
  "intent": "TOP_PRODUCTS_BY_PRICE_DESC",
  "entities": {
    "limit": 5
  },
  "sql": "SELECT ten, gia_niem_yet \nFROM san_pham \nWHERE dang_kinh_doanh = TRUE \nORDER BY gia_niem_yet DESC \nLIMIT %s;",
  "params": [5],
  "explanation": "Nhận diện yêu cầu xem Top 5 sản phẩm đắt nhất. Áp dụng sắp xếp `ORDER BY gia_niem_yet DESC` với `LIMIT 5`.",
  "message": "Phân tích thành công bằng bộ xử lý quy tắc cục bộ."
}
```
