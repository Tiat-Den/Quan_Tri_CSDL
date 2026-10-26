"""
Cấu hình cho AI Service (Text-to-SQL Rule Engine & Bộ 5 Module AI Quản Trị CSDL)
Mọi bí mật và ngưỡng quản trị được đọc từ file .env / biến môi trường, có giá trị dự phòng an toàn.
"""
import os
from pathlib import Path

# Nạp tự động tệp .env nếu tồn tại
def _load_env_file():
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in candidates:
        if env_path.exists() and env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass

_load_env_file()

# Server config
HOST = os.getenv("AI_SERVICE_HOST", "0.0.0.0")
PORT = int(os.getenv("AI_SERVICE_PORT", "8001"))
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "50"))
MAX_LIMIT = int(os.getenv("MAX_LIMIT", "100"))
MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
MAX_QUESTION_LEN = int(os.getenv("MAX_QUESTION_LEN", "300"))
CORS_ALLOW_ORIGINS = [orig.strip() for orig in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if orig.strip()]

# Database config
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "LinhKien_DB")
DB_SCHEMA = os.getenv("DB_SCHEMA", "LinhKien")

# Role chỉ đọc dành riêng cho AI Text-to-SQL (Tuân thủ Least Privilege)
DB_USER = os.getenv("DB_USER", "text2sql_readonly")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
if not DB_PASSWORD:
    import logging
    logging.getLogger("ai_service.config").warning("Biến DB_PASSWORD rỗng! Kết nối bằng role text2sql_readonly có thể thất bại.")

# Role chỉ đọc dành cho Manager (Ẩn cột gia_von qua CLS)
DB_MANAGER_USER = os.getenv("DB_MANAGER_USER", "manager_readonly")
DB_MANAGER_PASSWORD = os.getenv("DB_MANAGER_PASSWORD", "manager_readonly_pwd")

# Role Admin (Chỉ dùng cho nhiệm vụ DDL/Auth/Backup khi được cấp tường minh qua biến môi trường)
DB_ADMIN_USER = os.getenv("DB_ADMIN_USER", "postgres")
DB_ADMIN_PASSWORD = os.getenv("DB_ADMIN_PASSWORD", "")

# Chỉ cho phép kết nối admin khi được bật tường minh (Mặc định: False)
ALLOW_ADMIN_CONNECTION = os.getenv("ALLOW_ADMIN_CONNECTION", "0").lower() in ("1", "true", "yes")
ALLOW_ADMIN_FALLBACK = os.getenv("ALLOW_ADMIN_FALLBACK", "0").lower() in ("1", "true", "yes")

# Sandbox database DSN phục vụ kiểm thử an toàn
SANDBOX_DSN = os.getenv("SANDBOX_DSN", "")

# Ngưỡng và Trọng số bảo mật AI 3 (Zero-Trust Security)
SECURITY_WEIGHTS = {
    "union_injection": float(os.getenv("WEIGHT_UNION", "35.0")),
    "sensitive_column": float(os.getenv("WEIGHT_SENSITIVE", "30.0")),
    "high_cost": float(os.getenv("WEIGHT_HIGH_COST", "20.0")),
    "comment_syntax": float(os.getenv("WEIGHT_COMMENT", "15.0")),
    "subquery_abuse": float(os.getenv("WEIGHT_SUBQUERY", "15.0")),
    "stacked_queries": float(os.getenv("WEIGHT_STACKED", "40.0")),
    # Thành phần học máy của AI 3 (Isolation Forest + z-score theo người dùng)
    "anomaly": float(os.getenv("WEIGHT_ANOMALY", "20.0")),
    "user_deviation": float(os.getenv("WEIGHT_USER_DEVIATION", "15.0")),
}

# Ngưỡng đề xuất Index của AI 4 (Smart Index Advisor - A4-2)
MIN_TABLE_ROWS = int(os.getenv("MIN_TABLE_ROWS", "1000"))
MAX_SELECTIVITY = float(os.getenv("MAX_SELECTIVITY", "0.2"))
INDEX_ADVISOR_CONFIG = {
    "min_table_rows": MIN_TABLE_ROWS,
    "max_selectivity": MAX_SELECTIVITY,
    "min_seq_scan_cost": float(os.getenv("INDEX_MIN_COST", "25.0")),
}

# Ngưỡng phân vùng AI 5 (Predictive Partitioning - A5-4)
PARTITION_THRESHOLD_ROWS = int(os.getenv("PARTITION_THRESHOLD_ROWS", "1000000"))
PARTITION_THRESHOLD_BYTES = int(os.getenv("PARTITION_THRESHOLD_BYTES", "1073741824"))  # 1 GB
BACKTEST_MONTHS = int(os.getenv("BACKTEST_MONTHS", "3"))
MIN_MONTHS = int(os.getenv("MIN_MONTHS", "4"))
