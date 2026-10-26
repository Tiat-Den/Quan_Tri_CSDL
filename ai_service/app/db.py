"""
Module quản lý kết nối PostgreSQL và thực thi truy vấn an toàn cho AI Service.
Hỗ trợ kiểm soát bảo mật Text-to-SQL (Read-only, Anti-SQLi, Timeout, Fallback kết nối).
"""
import logging
import os
import threading
import re
import time
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import psycopg2
from psycopg2 import OperationalError, extensions

try:
    import sqlglot
    from sqlglot import exp
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False

from app import config
from app.config import (
    DB_ADMIN_PASSWORD,
    DB_ADMIN_USER,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_SCHEMA,
    DB_USER,
)

class DatabaseConnectionError(Exception):
    """Lỗi kết nối cơ sở dữ liệu khi không thể xác thực hoặc mất kết nối."""
    pass

logger = logging.getLogger("ai_service.db")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [DB] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Danh sách từ khóa DDL, DML ghi hoặc câu lệnh quản trị bị cấm
FORBIDDEN_KEYWORDS = [
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "CREATE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "COPY",
    "REINDEX",
    "VACUUM",
    "SHUTDOWN",
    "DO",
    "LISTEN",
    "NOTIFY",
    "INTO",
    "PG_SLEEP",
    "PG_READ_FILE",
    "PG_READ_BINARY_FILE",
    "PG_LS_DIR",
    "LO_IMPORT",
    "LO_EXPORT",
    "DBLINK",
    "DBLINK_EXEC",
    "SET_CONFIG",
    "PG_TERMINATE_BACKEND",
    "PG_CANCEL_BACKEND",
]

# Regex tìm kiếm từ khóa cấm theo ranh giới từ nguyên bản (word boundary)
FORBIDDEN_REGEX = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Danh sách các hàm PostgreSQL nguy hiểm bị cấm tuyệt đối
FORBIDDEN_FUNCS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "dblink",
    "dblink_exec",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
}


def get_connection(use_admin: bool = False) -> psycopg2.extensions.connection:
    """
    Tạo và trả về đối tượng kết nối psycopg2 tới cơ sở dữ liệu PostgreSQL.
    
    Quy tắc phân quyền & An toàn:
    - Mặc định sử dụng role chỉ đọc `config.DB_USER` (text2sql_readonly).
    - Kết nối readonly luôn gắn options: default_transaction_read_only=on, statement_timeout=3000ms.
    - Nếu kết nối readonly thất bại:
      + Nếu config.ALLOW_ADMIN_FALLBACK=True: cảnh báo và fallback sang admin.
      + Mặc định: ném lỗi DatabaseConnectionError rõ ràng, không ngầm leo thang quyền.
    - Kết nối admin (use_admin=True): chỉ cho phép khi config.ALLOW_ADMIN_CONNECTION=True.
    """
    conn = None

    host = getattr(config, "DB_HOST", DB_HOST)
    port = getattr(config, "DB_PORT", DB_PORT)
    dbname = getattr(config, "DB_NAME", DB_NAME)
    user = getattr(config, "DB_USER", DB_USER)
    password = getattr(config, "DB_PASSWORD", DB_PASSWORD)
    admin_user = getattr(config, "DB_ADMIN_USER", DB_ADMIN_USER)
    admin_password = getattr(config, "DB_ADMIN_PASSWORD", DB_ADMIN_PASSWORD)
    schema = getattr(config, "DB_SCHEMA", DB_SCHEMA)

    if use_admin:
        if not getattr(config, "ALLOW_ADMIN_CONNECTION", False):
            raise PermissionError(
                "Kết nối bằng quyền Admin bị chặn bởi chính sách bảo mật (ALLOW_ADMIN_CONNECTION=0)."
            )
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=admin_user,
            password=admin_password,
            connect_timeout=3,
        )
        logger.info("Kết nối CSDL thành công với user admin: %s", admin_user)
    else:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=3,
                options="-c default_transaction_read_only=on -c statement_timeout=3000",
            )
            logger.debug("Kết nối CSDL thành công với user readonly: %s", user)
        except Exception as err:
            if getattr(config, "ALLOW_ADMIN_FALLBACK", False):
                logger.warning(
                    "Kết nối bằng role readonly '%s' thất bại (%s). "
                    "Kích hoạt Fallback sang admin '%s' theo cấu hình ALLOW_ADMIN_FALLBACK.",
                    user,
                    err,
                    admin_user,
                )
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    dbname=dbname,
                    user=admin_user,
                    password=admin_password,
                    connect_timeout=3,
                )
            else:
                logger.error("Kết nối bằng role readonly '%s' thất bại: %s", user, err)
                raise DatabaseConnectionError(
                    f"Không thể kết nối với role chỉ đọc '{user}': {err}"
                ) from err

    conn.autocommit = True

    # Thiết lập tham số môi trường phiên làm việc an toàn
    with conn.cursor() as cur:
        cur.execute(f'SET search_path TO "{schema}", public;')
        cur.execute("SET statement_timeout = '3s';")

    return conn


def _strip_sql_comments_and_strings(sql: str) -> str:
    """
    Loại bỏ chú thích (-- và /* */) cùng các chuỗi ký tự ('...') để kiểm tra từ khóa cấm.
    Tránh trường hợp chuỗi ký tự bình thường của sản phẩm vô tình chứa từ khóa cấm.
    """
    # Xóa chuỗi hằng số ('chuỗi')
    no_strings = re.sub(r"'(?:''|[^'])*'", "''", sql)
    # Xóa chú thích khối (/* ... */)
    no_block_comments = re.sub(r"/\*[\s\S]*?\*/", " ", no_strings)
    # Xóa chú thích dòng (-- ...)
    no_line_comments = re.sub(r"--.*$", " ", no_block_comments, flags=re.MULTILINE)
    return no_line_comments


def validate_sql_security(sql: str) -> Tuple[bool, str]:
    """
    Kiểm tra bảo mật nghiêm ngặt cho câu lệnh SQL sinh ra bởi AI:
    1. Không được rỗng.
    2. Chặn tấn công đa câu lệnh (multi-statement) thông qua ký tự chấm phẩy ';' nối lệnh.
    3. Chặn ký hiệu chú thích độc hại ';--'.
    4. Bắt buộc bắt đầu bằng SELECT, WITH hoặc EXPLAIN (không chứa ANALYZE).
    5. Kiểm tra cây cú pháp AST bằng sqlglot:
       - Chặn mệnh đề INTO (chặn SELECT ... INTO)
       - Chặn các lệnh ghi DDL/DML lồng ghép trong CTE hoặc Subquery
       - Chặn các hàm quản trị hệ thống bị cấm (pg_sleep, pg_read_file, lo_import...)
    6. Lớp bảo vệ bổ sung bằng regex đối với từ khóa cấm và hàm nguy hiểm.

    Trả về: (is_valid: bool, error_message: str)
    """
    if not sql or not sql.strip():
        return False, "Câu lệnh SQL rỗng hoặc không hợp lệ."

    raw_sql = sql.strip()

    # Kiểm tra ký tự nối lệnh độc hại ';--'
    if ";--" in raw_sql:
        return False, "Phát hiện ký hiệu nguy hiểm ';--'. Câu lệnh bị chặn bảo mật."

    # Làm sạch chuỗi và chú thích trước khi phân tích cấu trúc
    structural_sql = _strip_sql_comments_and_strings(raw_sql).strip()
    if not structural_sql:
        return False, "Câu lệnh chỉ chứa chú thích hoặc khoảng trắng rỗng."

    # Kiểm tra đa câu lệnh: Cho phép một dấu chấm phẩy duy nhất ở cuối câu, cấm dấu chấm phẩy ở giữa
    trimmed_trailing = structural_sql.rstrip(";").strip()
    if ";" in trimmed_trailing:
        return (
            False,
            "Chặn đa câu lệnh: Không cho phép ký tự ';' nối nhiều truy vấn trong cùng một câu.",
        )

    # Kiểm tra EXPLAIN chứa ANALYZE (kể cả dạng EXPLAIN (ANALYZE))
    if re.search(r"\bEXPLAIN\b", structural_sql, re.IGNORECASE) and re.search(r"\bANALYZE\b", structural_sql, re.IGNORECASE):
        return False, "Từ chối thực thi: EXPLAIN ANALYZE bị chặn để bảo vệ tài nguyên DB."

    # Phân tích cú pháp AST bằng sqlglot (nếu khả dụng)
    if SQLGLOT_AVAILABLE:
        try:
            statements = sqlglot.parse(raw_sql, read="postgres")
        except Exception as parse_err:
            return False, f"Lỗi cú pháp SQL hoặc cấu trúc không hợp lệ: {parse_err}"

        if len(statements) != 1:
            return False, "Chặn đa câu lệnh: Chỉ cho phép đúng 1 câu lệnh SQL duy nhất."

        stmt = statements[0]
        if stmt is None:
            return False, "Câu lệnh SQL rỗng."

        if isinstance(stmt, (exp.Select, exp.Union)):
            pass
        elif hasattr(exp, "Command") and isinstance(stmt, exp.Command):
            cmd_str = str(stmt).strip()
            if not re.match(r"^explain\b", cmd_str, re.IGNORECASE):
                return False, f"Từ chối thực thi: Lệnh '{cmd_str.split()[0]}' không được phép."
            if re.search(r"\banalyze\b", cmd_str, re.IGNORECASE):
                return False, "Từ chối thực thi: EXPLAIN ANALYZE bị chặn để bảo vệ tài nguyên DB."
            if FORBIDDEN_REGEX.search(cmd_str):
                return False, "Từ chối thực thi: EXPLAIN chứa từ khóa bị cấm."
        else:
            return (
                False,
                f"Từ chối thực thi: Câu lệnh kiểu {type(stmt).__name__}. "
                "Chỉ cho phép các câu lệnh truy vấn đọc dữ liệu bắt đầu bằng SELECT, WITH hoặc EXPLAIN.",
            )

        # Duyệt cây AST tìm mệnh đề INTO
        if list(stmt.find_all(exp.Into)):
            return False, "Phát hiện mệnh đề INTO bị cấm (chặn SELECT ... INTO)."

        # Duyệt cây AST tìm các lệnh DDL / DML lồng trong CTE/Subquery
        if list(stmt.find_all((exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.TruncateTable))):
            return False, "Phát hiện thao tác ghi/xóa/sửa đổi DDL/DML bị cấm trong câu lệnh."

        # Duyệt cây AST tìm các hàm cấm
        for func in stmt.find_all((exp.Anonymous, exp.Func)):
            fname = getattr(func, "name", "")
            if fname and fname.lower() in FORBIDDEN_FUNCS:
                return False, f"Phát hiện hàm quản trị/nguy hiểm bị cấm: '{fname}'."

    # Lớp phòng vệ bổ sung bằng Regex
    first_token_match = re.match(r"^\s*([a-zA-Z]+)", structural_sql)
    if not first_token_match:
        return False, "Không thể xác định từ khóa khởi đầu của câu lệnh SQL."

    first_keyword = first_token_match.group(1).upper()
    if first_keyword not in ("SELECT", "WITH", "EXPLAIN"):
        return (
            False,
            f"Từ chối thực thi: Câu lệnh bắt đầu bằng '{first_keyword}'. "
            "Chỉ cho phép các câu lệnh truy vấn đọc dữ liệu bắt đầu bằng SELECT, WITH hoặc EXPLAIN.",
        )

    # Chặn các từ khóa ghi, xóa, quản trị
    forbidden_match = FORBIDDEN_REGEX.search(structural_sql)
    if forbidden_match:
        keyword = forbidden_match.group(0).upper()
        return (
            False,
            f"Phát hiện từ khóa nguy hiểm bị cấm: '{keyword}'. "
            "Hệ thống Text-to-SQL chỉ hỗ trợ quyền truy vấn dữ liệu (DQL).",
        )

    return True, ""


def _serialize_value(val: Any) -> Any:
    """Chuyển đổi các kiểu dữ liệu PostgreSQL (Decimal, date, datetime) sang dạng chuẩn."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        # Trả về int nếu là số nguyên, ngược lại float
        return int(val) if val % 1 == 0 else float(val)
    if isinstance(val, (datetime, date, dt_time)):
        return val.isoformat()
    return val



# ==============================================================================
# POOL KẾT NỐI: tái sử dụng kết nối thay vì mở/đóng mới cho mỗi truy vấn.
# Mỗi lần mở kết nối mới tốn bắt tay TCP + xác thực SCRAM (~20-80 ms trên Windows); một lần tải
# dashboard có hơn 20 truy vấn nên tái sử dụng kết nối làm trang nhanh hơn rõ rệt.
# Mỗi loại tài khoản (readonly / manager / admin) có hàng chờ riêng -> không lẫn quyền giữa các role.
# ==============================================================================
_POOL: Dict[str, List[Any]] = {}
_POOL_LOCK = threading.Lock()
_POOL_MAX_IDLE = int(os.getenv("DB_POOL_MAX_IDLE", "4"))


def _pool_key(use_admin: bool, role: Optional[str]) -> str:
    if role in ("admin", "manager"):
        return f"role:{role}"
    return "admin" if use_admin else "readonly"


def _acquire_connection(key: str, use_admin: bool, role: Optional[str]):
    """Lấy kết nối rảnh trong pool (reused=True) hoặc mở kết nối mới (reused=False)."""
    with _POOL_LOCK:
        idle = _POOL.get(key, [])
        while idle:
            conn = idle.pop()
            if not conn.closed:
                return conn, True
    if role in ("admin", "manager"):
        return get_connection_by_role(role=role), False
    return get_connection(use_admin=use_admin), False


def _release_connection(key: str, conn, healthy: bool) -> None:
    """Trả kết nối về pool nếu còn tốt (đã kết thúc transaction); ngược lại đóng hẳn."""
    if conn is None:
        return
    if healthy and not conn.closed:
        try:
            if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                conn.rollback()
        except Exception:
            healthy = False
    if healthy and not conn.closed:
        with _POOL_LOCK:
            idle = _POOL.setdefault(key, [])
            if len(idle) < _POOL_MAX_IDLE:
                idle.append(conn)
                return
    try:
        conn.close()
    except Exception:
        pass


def close_all_pooled_connections() -> None:
    with _POOL_LOCK:
        conns = [c for idle in _POOL.values() for c in idle]
        _POOL.clear()
    for c in conns:
        try:
            c.close()
        except Exception:
            pass



def get_connection_by_role(role: str = "admin") -> psycopg2.extensions.connection:
    """
    Trả về kết nối PostgreSQL theo vai trò người dùng:
    - role == 'admin': Dùng role CHỈ ĐỌC text2sql_readonly (thấy cả gia_von, nhưng không ghi/xóa được).
      Nguyên tắc đặc quyền tối thiểu: câu hỏi chatbot của admin KHÔNG chạy bằng superuser postgres,
      nên dù SQL sinh ra có lọt qua các lớp kiểm tra thì CSDL vẫn từ chối mọi lệnh ghi.
    - role == 'manager': Dùng tài khoản DB_MANAGER_USER (manager_readonly, bị CLS ẩn gia_von)
    - Các tác vụ quản trị thật (backup, ghi nhật ký...) gọi get_connection(use_admin=True) riêng.
    """
    if role == "manager":
        host = getattr(config, "DB_HOST", "127.0.0.1")
        port = getattr(config, "DB_PORT", 5432)
        dbname = getattr(config, "DB_NAME", "LinhKien_DB")
        mgr_user = getattr(config, "DB_MANAGER_USER", "manager_readonly")
        mgr_pwd = getattr(config, "DB_MANAGER_PASSWORD", "manager_readonly_pwd")
        schema = getattr(config, "DB_SCHEMA", "LinhKien")
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=mgr_user,
                password=mgr_pwd,
                connect_timeout=3,
            )
            cur = conn.cursor()
            cur.execute(f'SET search_path TO "{schema}", public;')
            cur.execute("SET statement_timeout = '3s';")
            cur.close()
            return conn
        except Exception as e:
            logger.warning("Không thể kết nối bằng role manager_readonly (%s), fallback sang text2sql_readonly", e)
            return get_connection(use_admin=False)
    else:
        return get_connection(use_admin=False)


def execute_admin_query(
    sql: str,
    params: Optional[Union[List[Any], Tuple[Any, ...]]] = None,
) -> Dict[str, Any]:
    """Thực thi truy vấn dưới quyền Admin superuser (dành cho auth và quản trị)."""
    return execute_query(sql, params, use_admin=True)


def execute_query(
    sql: str,
    params: Optional[Union[List[Any], Tuple[Any, ...]]] = None,
    use_admin: bool = False,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Thực thi câu lệnh SQL an toàn với tham số %s (parameterized query).

    Quy trình:
    1. Kiểm tra an toàn SQL bằng validate_sql_security().
    2. Kết nối tới DB và thiết lập search_path, statement_timeout (3s).
    3. Giới hạn số dòng tối đa (fetchmany(MAX_ROWS + 1)) và đặt cờ truncated.
    4. Đo đạc thời gian thực thi chính xác (ms).
    5. Trả về cấu trúc chuẩn:
       {
           "success": bool,
           "columns": List[str],
           "data": List[Dict[str, Any]],
           "row_count": int,
           "execution_time_ms": float,
           "error": str,
           "truncated": bool
       }
    """
    # 1. Kiểm tra bảo mật
    is_valid, sec_error = validate_sql_security(sql)
    if not is_valid:
        logger.warning("Truy vấn bị từ chối bởi cơ chế an toàn: %s | SQL: %s", sec_error, sql)
        return {
            "success": False,
            "columns": [],
            "data": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "error": sec_error,
            "truncated": False,
        }

    max_rows = getattr(config, "MAX_ROWS", 500)
    pool_key = _pool_key(use_admin, role)
    # Thử tối đa 2 lần: kết nối lấy lại từ pool có thể đã bị server đóng (khởi động lại PostgreSQL, mạng chập chờn)
    for attempt in range(2):
        conn = None
        reused = False
        healthy = False
        start_time = time.perf_counter()
        try:
            conn, reused = _acquire_connection(pool_key, use_admin, role)
            with conn.cursor() as cur:
                # Luôn đảm bảo search_path và statement_timeout
                cur.execute(f'SET search_path TO "{DB_SCHEMA}", public;')
                cur.execute("SET statement_timeout = '3s';")

                param_tuple = tuple(params) if params is not None else None
                cur.execute(sql, param_tuple)

                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    raw_rows = cur.fetchmany(max_rows + 1)
                    truncated = len(raw_rows) > max_rows
                    if truncated:
                        raw_rows = raw_rows[:max_rows]
                    data = [
                        {col: _serialize_value(val) for col, val in zip(columns, row)}
                        for row in raw_rows
                    ]
                    row_count = len(data)
                else:
                    columns = []
                    data = []
                    row_count = 0
                    truncated = False

            healthy = True
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": True,
                "columns": columns,
                "data": data,
                "row_count": row_count,
                "execution_time_ms": execution_time_ms,
                "error": "",
                "truncated": truncated,
            }

        except psycopg2.extensions.QueryCanceledError as ex:
            healthy = True
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Truy vấn vượt quá thời gian tối đa (statement_timeout 3s): %s", ex)
            return {
                "success": False,
                "columns": [],
                "data": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "error": "Truy vấn bị hủy do vượt quá giới hạn thời gian thực thi (3 giây).",
                "truncated": False,
            }

        except DatabaseConnectionError as ex:
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Lỗi kết nối CSDL (DatabaseConnectionError): %s", ex)
            return {
                "success": False,
                "columns": [],
                "data": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "error": str(ex),
                "truncated": False,
            }

        except (OperationalError, psycopg2.InterfaceError) as ex:
            if reused and attempt == 0:
                logger.info("Kết nối trong pool đã bị đóng, mở kết nối mới và thử lại: %s", ex)
                continue
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Lỗi kết nối cơ sở dữ liệu PostgreSQL: %s", ex)
            return {
                "success": False,
                "columns": [],
                "data": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "error": f"Lỗi kết nối CSDL: Không thể kết nối tới {DB_HOST}:{DB_PORT}/{DB_NAME} ({ex}).",
                "truncated": False,
            }

        except Exception as ex:
            healthy = True  # lỗi SQL thông thường (sai cú pháp, thiếu quyền...): kết nối vẫn dùng lại được
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = str(ex).strip()
            logger.error("Lỗi thực thi truy vấn SQL: %s", err_msg)
            return {
                "success": False,
                "columns": [],
                "data": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "error": f"Lỗi CSDL: {err_msg}",
                "truncated": False,
            }

        finally:
            _release_connection(pool_key, conn, healthy)
    return {
        "success": False, "columns": [], "data": [], "row_count": 0,
        "execution_time_ms": 0.0, "error": "Không thể kết nối CSDL.", "truncated": False,
    }




def check_db_connection() -> Dict[str, Any]:
    """
    Kiểm tra tình trạng kết nối CSDL phục vụ hiển thị trạng thái trên giao diện Streamlit/API.
    """
    start_time = time.perf_counter()
    try:
        conn = get_connection(use_admin=False)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, version();")
            row = cur.fetchone()
        conn.close()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "connected": True,
            "database": row[0],
            "user": row[1],
            "version": row[2].split(",")[0],
            "schema": DB_SCHEMA,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as ex:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "connected": False,
            "database": DB_NAME,
            "user": DB_USER,
            "version": None,
            "schema": DB_SCHEMA,
            "latency_ms": latency_ms,
            "error": str(ex),
        }


def get_schema_info() -> Dict[str, Any]:
    """
    Lấy danh sách thông tin 14 bảng, các cột, kiểu dữ liệu và chú thích từ schema LinhKien.
    """
    sql = """
    SELECT 
        t.table_name,
        obj_description(pgc.oid, 'pg_class') AS table_description,
        c.column_name,
        c.data_type,
        c.is_nullable,
        col_description(pgc.oid, c.ordinal_position) AS column_description
    FROM information_schema.tables t
    JOIN pg_class pgc ON pgc.relname = t.table_name
    JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace AND pgn.nspname = t.table_schema
    JOIN information_schema.columns c 
        ON c.table_schema = t.table_schema AND c.table_name = t.table_name
    WHERE t.table_schema = %s AND t.table_type = 'BASE TABLE'
    ORDER BY t.table_name, c.ordinal_position;
    """
    res = execute_query(sql, [DB_SCHEMA])
    if not res["success"]:
        return {"success": False, "tables": {}, "error": res["error"]}

    tables: Dict[str, Dict[str, Any]] = {}
    for r in res["data"]:
        tbl = r["table_name"]
        if tbl not in tables:
            tables[tbl] = {
                "table_name": tbl,
                "description": r["table_description"] or "",
                "columns": [],
            }
        tables[tbl]["columns"].append(
            {
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "description": r["column_description"] or "",
            }
        )

    return {
        "success": True,
        "schema": DB_SCHEMA,
        "table_count": len(tables),
        "tables": tables,
    }


def get_schema_tables() -> List[Dict[str, Any]]:
    """
    Hàm bổ trợ lấy danh sách bảng kèm chi tiết cột dưới dạng danh sách (phục vụ catalog/schema linking).
    """
    info = get_schema_info()
    if not info.get("success"):
        return []
    return list(info.get("tables", {}).values())


def get_dashboard_summary() -> Dict[str, Any]:
    """
    Lấy thông tin tổng hợp cho Dashboard:
    - Tổng số sản phẩm
    - Tổng số đơn hàng
    - Tổng số khách hàng
    - Tổng doanh thu các đơn hàng thành công (hoan_thanh)
    - Tổng số sản phẩm cảnh báo tồn kho thấp
    """
    summary = {
        "total_products": 0,
        "total_orders": 0,
        "total_completed_orders": 0,
        "total_customers": 0,
        "total_revenue": 0,
        "low_stock_count": 0,
    }

    q1 = execute_query("SELECT COUNT(*) AS cnt FROM san_pham;")
    if q1["success"] and q1["data"]:
        summary["total_products"] = q1["data"][0]["cnt"]

    q2 = execute_query("SELECT COUNT(*) AS cnt FROM don_hang;")
    if q2["success"] and q2["data"]:
        summary["total_orders"] = q2["data"][0]["cnt"]

    q3 = execute_query("SELECT COUNT(*) AS cnt FROM khach_hang;")
    if q3["success"] and q3["data"]:
        summary["total_customers"] = q3["data"][0]["cnt"]

    q4 = execute_query(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(tong_tien), 0) AS rev "
        "FROM don_hang WHERE trang_thai = 'hoan_thanh';"
    )
    if q4["success"] and q4["data"]:
        summary["total_completed_orders"] = q4["data"][0]["cnt"]
        summary["total_revenue"] = q4["data"][0]["rev"]

    q5 = execute_query("SELECT COUNT(*) AS cnt FROM ton_kho WHERE so_luong_ton <= muc_ton_toi_thieu;")
    if q5["success"] and q5["data"]:
        summary["low_stock_count"] = q5["data"][0]["cnt"]

    return summary


def get_dashboard_stats() -> Dict[str, Any]:
    """Alias cho get_dashboard_summary()."""
    return get_dashboard_summary()


def get_monthly_revenue_data() -> List[Dict[str, Any]]:
    """
    Lấy doanh thu theo từng tháng (dựa trên đơn hàng trạng thái 'hoan_thanh') phục vụ biểu đồ Streamlit.
    """
    sql = """
    SELECT 
        TO_CHAR(DATE_TRUNC('month', ngay_dat), 'YYYY-MM') AS thang,
        COUNT(id) AS so_don_hang,
        COALESCE(SUM(tong_tien), 0) AS doanh_thu
    FROM don_hang
    WHERE trang_thai = 'hoan_thanh'
    GROUP BY DATE_TRUNC('month', ngay_dat)
    ORDER BY DATE_TRUNC('month', ngay_dat) ASC;
    """
    res = execute_query(sql)
    if res["success"]:
        return res["data"]
    return []


def get_monthly_sales() -> List[Dict[str, Any]]:
    """Alias cho get_monthly_revenue_data()."""
    return get_monthly_revenue_data()


def get_low_stock_data(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Lấy danh sách các linh kiện có số lượng tồn kho thấp hơn hoặc bằng mức tồn tối thiểu.
    """
    sql = """
    SELECT 
        sp.id AS san_pham_id,
        sp.ma_sku,
        sp.ten AS ten_san_pham,
        dm.ten AS danh_muc,
        tk.so_luong_ton,
        tk.muc_ton_toi_thieu,
        sp.gia_niem_yet
    FROM ton_kho tk
    JOIN san_pham sp ON tk.san_pham_id = sp.id
    LEFT JOIN danh_muc dm ON sp.danh_muc_id = dm.id
    WHERE tk.so_luong_ton <= tk.muc_ton_toi_thieu
    ORDER BY tk.so_luong_ton ASC, (tk.muc_ton_toi_thieu - tk.so_luong_ton) DESC
    LIMIT %s;
    """
    res = execute_query(sql, [limit])
    if res["success"]:
        return res["data"]
    return []


def get_low_stock(limit: int = 10) -> List[Dict[str, Any]]:
    """Alias cho get_low_stock_data()."""
    return get_low_stock_data(limit=limit)
