"""
MODULE AI 3: GIÁM SÁT AN NINH CSDL & CHỐNG RÒ RỈ DỮ LIỆU (ZERO-TRUST SECURITY GUARD)
Kế thừa từ kiến trúc Bài_8.3 và Bài_8.6; cải tiến toàn diện theo tài liệu kỹ thuật (A3-1 đến A3-4).
- Phân tích cú pháp cây AST bằng `sqlglot` (bảng, cột, bí danh, JOIN, subquery, SELECT *, aggregate).
- Hệ thống chấm điểm rủi ro phiên đa nhân tố theo config.SECURITY_WEIGHTS.
- Ngữ cảnh phiên thời gian thực (SessionContext, RateTracker) và Dynamic Data Masking.
- Ghi nhật ký kiểm toán độc lập ra logs/security_audit.jsonl.
- Đề xuất lệnh DBA REVOKE SELECT (chỉ đề xuất, không tự động chạy DDL phá hoại CSDL).
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp

from app.config import SECURITY_WEIGHTS
from app.schema_catalog import SENSITIVE_COLUMNS
from app.session_context import SessionContext, mask_sensitive_columns

logger = logging.getLogger("ai_service.security_guard")

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AUDIT_LOG_FILE = LOGS_DIR / "security_audit.jsonl"

# Các loại Node câu lệnh phá hoại trong SQL AST
DESTRUCTIVE_NODES = (
    exp.Drop,
    exp.Delete,
    exp.Update,
    exp.Insert,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Into,
)

DESTRUCTIVE_KEYWORDS_REGEX = re.compile(
    r'\b(drop|delete|update|insert|alter|truncate|grant|revoke|create|pg_sleep|copy)\b',
    re.IGNORECASE,
)


_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _strip_string_literals(sql: str) -> str:
    """Bỏ nội dung chuỗi '...' để từ khóa nằm trong dữ liệu (vd: LIKE '%update%') không bị báo nhầm."""
    return _STRING_LITERAL.sub("''", sql or "")


import threading

# Khóa dùng chung cho mọi thao tác ghi nhật ký (Streamlit chạy nhiều phiên bằng nhiều luồng)
AUDIT_LOG_LOCK = threading.RLock()


def write_audit_log(entry: Dict[str, Any]):
    """Ghi một bản ghi nhật ký an ninh vào logs/security_audit.jsonl."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_LOCK, open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Không thể ghi audit log: %s", e)


# Bộ đệm nội dung nhật ký: chỉ đọc + parse JSON lại khi tệp thay đổi (khác thời điểm sửa hoặc kích thước).
# Dashboard gọi read_audit_log nhiều lần mỗi lần tải trang; không cần parse lại cả tệp mỗi lần.
_AUDIT_CACHE: Dict[str, Any] = {"key": None, "records": []}


def read_audit_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Đọc danh sách các bản ghi nhật ký an ninh gần nhất phục vụ Streamlit UI."""
    if not AUDIT_LOG_FILE.exists():
        return []
    try:
        st_ = AUDIT_LOG_FILE.stat()
        key = (st_.st_mtime_ns, st_.st_size)
        if _AUDIT_CACHE["key"] != key:
            records = []
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass
            _AUDIT_CACHE["key"], _AUDIT_CACHE["records"] = key, records
        # Trả bản sao từng bản ghi để nơi gọi có sửa cũng không làm hỏng bộ đệm
        return [dict(r) for r in _AUDIT_CACHE["records"][-limit:][::-1]]
    except Exception as e:
        logger.error("Không thể đọc audit log: %s", e)
        return []


class AISecurityGuard:
    """
    Module AI Giám sát An ninh Zero-Trust & Chống rò rỉ dữ liệu (Exfiltration Guard).
    """

    TRUSTED_IPS = ("127.0.0.1", "192.168.1.", "10.0.0.", "localhost", "::1")
    SENSITIVE_HOURS = range(0, 6)  # 00:00 - 05:59 sáng
    SENSITIVE_TABLES = {"khach_hang": 25.0, "dia_chi": 20.0, "thanh_toan": 25.0, "don_hang": 15.0}

    # Bảng trọng số cột nhạy cảm theo tài liệu kỹ thuật A3-2
    COLUMN_WEIGHTS = {
        ("san_pham", "gia_von"): 70.0,
        ("app_users", "password_hash"): 80.0,
        ("khach_hang", "email"): 20.0,
        ("khach_hang", "so_dien_thoai"): 20.0,
        ("dia_chi", "dia_chi_chi_tiet"): 20.0,
        ("khach_hang", "ngay_sinh"): 10.0,
    }

    @classmethod
    def _parse_sql_ast(cls, sql_query: str) -> Dict[str, Any]:
        """
        Phân tích cú pháp SQL bằng `sqlglot` để bóc tách chính xác các bảng và cột truy cập (A3-1).
        """
        clean_sql = sql_query.strip()
        try:
            parsed = sqlglot.parse_one(clean_sql, read="postgres")
            parse_error = False
        except Exception:
            parsed = None
            parse_error = True

        if parsed is None:
            # Fallback regex nếu sqlglot không phân tích được
            clean_lower = clean_sql.lower()
            tables = set()
            for tbl in ["san_pham", "khach_hang", "don_hang", "chi_tiet_don_hang", "dia_chi", "thanh_toan", "nhan_vien", "nha_cung_cap", "ton_kho"]:
                if re.search(r'\b' + tbl + r'\b', clean_lower):
                    tables.add(tbl)
            cols = set()
            for col in ["gia_von", "password_hash", "email", "so_dien_thoai", "dia_chi_chi_tiet", "ngay_sinh"]:
                if re.search(r'\b' + col + r'\b', clean_lower):
                    cols.add(col)
            has_star = bool(re.search(r'select\s+\*', clean_lower))
            has_agg = bool(re.search(r'\b(count|sum|avg|min|max)\s*\(', clean_lower))
            has_limit = bool(re.search(r'\blimit\b', clean_lower))
            is_destructive = bool(DESTRUCTIVE_KEYWORDS_REGEX.search(clean_lower))

            return {
                "parsed": None,
                "parse_error": True,
                "tables": tables,
                "columns": cols,
                "has_star": has_star,
                "has_agg": has_agg,
                "has_limit": has_limit,
                "is_destructive": is_destructive,
            }

        # Trích xuất bảng
        tables = set()
        for t in parsed.find_all(exp.Table):
            tables.add(t.name.lower())

        # Trích xuất cột
        cols = set()
        for c in parsed.find_all(exp.Column):
            cols.add(c.name.lower())

        # Kiểm tra SELECT * (loại trừ trường hợp * nằm bên trong hàm tổng hợp như COUNT(*))
        stars = list(parsed.find_all(exp.Star))
        direct_stars = [s for s in stars if not s.find_ancestor(exp.AggFunc)]
        has_star = bool(direct_stars)

        # Kiểm tra hàm tổng hợp (COUNT, SUM, AVG, MIN, MAX...)
        has_agg = bool(list(parsed.find_all(exp.AggFunc)))

        # Kiểm tra LIMIT
        has_limit = bool(parsed.find(exp.Limit))

        # Kiểm tra thao tác phá hoại DDL/DML trên cây AST
        is_destructive = isinstance(parsed, DESTRUCTIVE_NODES) or any(
            isinstance(node, DESTRUCTIVE_NODES) for node in parsed.walk()
        )

        # Bổ sung kiểm tra regex cho từ khóa phá hoại phòng ngừa CTE ngầm
        # (bỏ qua nội dung chuỗi ký tự để tránh báo nhầm, vd: WHERE ten LIKE '%update%')
        if not is_destructive and DESTRUCTIVE_KEYWORDS_REGEX.search(_strip_string_literals(clean_sql)):
            is_destructive = True

        return {
            "parsed": parsed,
            "parse_error": False,
            "tables": tables,
            "columns": cols,
            "has_star": has_star,
            "has_agg": has_agg,
            "has_limit": has_limit,
            "is_destructive": is_destructive,
        }

    @classmethod
    def evaluate_risk(
        cls,
        sql_query: str,
        user: str = "analyst",
        ip_address: str = "127.0.0.1",
        hour: Optional[int] = None,
        estimated_rows: int = 10,
        failed_logins: int = 0,
        qps: float = 1.0,
        ctx: Optional[SessionContext] = None,
        plan_rows: Optional[int] = None,
        use_anomaly: bool = True,
        engine: str = "AI 3 (kiểm tra thủ công)",
        write_log: bool = True,
        question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Thuật toán AI chấm điểm rủi ro phiên đa nhân tố (A3-2).
        Hỗ trợ cả ngữ cảnh phiên SessionContext và các tham số tương thích ngược.
        """
        if ctx is not None:
            user = ctx.user
            ip_address = ctx.ip
            hour = ctx.hour
            failed_logins = ctx.failed_logins
            qps = ctx.qps

        if hour is None:
            hour = datetime.now().hour

        eff_rows = plan_rows if plan_rows is not None else estimated_rows

        score = 0.0
        factors = []

        ast_info = cls._parse_sql_ast(sql_query)
        tables = ast_info["tables"]
        columns = ast_info["columns"]
        has_star = ast_info["has_star"]
        has_agg = ast_info["has_agg"]
        has_limit = ast_info["has_limit"]
        is_destructive = ast_info["is_destructive"]
        parse_error = ast_info["parse_error"]

        if parse_error:
            score += 15.0
            factors.append("Câu lệnh SQL chứa cú pháp không phân tích được qua AST (+15 điểm)")

        # 1. Từ khóa phá hoại / DDL / DML ghi (+80 điểm)
        if is_destructive:
            score += 80.0
            factors.append("Phát hiện thao tác phá hoại DDL / DML ghi hoặc từ khóa bị cấm (+80 điểm)")

        # 2. Cột dữ liệu nhạy cảm
        # Duyệt qua các cột nhạy cảm đã định nghĩa
        matched_sensitive_cols = set()
        # Khi AST phân tích thành công: chỉ tin kết quả AST (không quét regex trên chuỗi thô
        # để tránh khớp nhầm tên cột nằm trong chuỗi ký tự/comment và cộng điểm hai lần).
        sql_for_regex = _strip_string_literals(sql_query)
        for (stbl, scol), col_weight in cls.COLUMN_WEIGHTS.items():
            if parse_error:
                col_hit = bool(re.search(r'\b' + scol + r'\b', sql_for_regex, re.IGNORECASE))
            else:
                col_hit = scol in columns
            if col_hit:
                if not stbl or stbl in tables or len(tables) <= 1:
                    matched_sensitive_cols.add(f"{stbl}.{scol}" if stbl else scol)
                    score += col_weight
                    factors.append(f"Truy cập cột nhạy cảm `{stbl}.{scol}` (+{col_weight:.0f} điểm)")

        # 3. Bảng nhạy cảm (Cộng theo từng bảng khác nhau, tối đa 50 điểm - A3-2)
        table_penalty = 0.0
        accessed_sensitive_tables = []
        for tbl, weight in cls.SENSITIVE_TABLES.items():
            if parse_error:
                tbl_hit = bool(re.search(r'\b' + tbl + r'\b', sql_for_regex, re.IGNORECASE))
            else:
                tbl_hit = tbl in tables
            if tbl_hit:
                accessed_sensitive_tables.append(tbl)
                table_penalty += weight

        if table_penalty > 0:
            actual_table_penalty = min(table_penalty, 50.0)
            score += actual_table_penalty
            factors.append(
                f"Truy vấn các bảng nhạy cảm: {', '.join(accessed_sensitive_tables)} "
                f"(+{actual_table_penalty:.0f} điểm, trần 50)"
            )

        # 4. SELECT * trên bảng nhạy cảm (+20 điểm - A3-2)
        if has_star and accessed_sensitive_tables:
            score += 20.0
            factors.append(
                f"Sử dụng `SELECT *` trên bảng dữ liệu nhạy cảm ({', '.join(accessed_sensitive_tables)}) (+20 điểm)"
            )

        # 5. Trích xuất dữ liệu hàng loạt (Bulk Exfiltration - +35 điểm - A3-2)
        # Chỉ tính khi:
        # a) plan_rows / eff_rows > 500
        # HOẶC b) Truy vấn bảng nhạy cảm không có LIMIT và không phải là hàm tổng hợp thuần túy (COUNT/SUM...)
        is_bulk = False
        if eff_rows > 500:
            is_bulk = True
            factors.append(f"Khối lượng dữ liệu trích xuất dự kiến lớn ({eff_rows} dòng > 500) (+35 điểm)")
        elif accessed_sensitive_tables and not has_limit and not has_agg:
            is_bulk = True
            factors.append(
                f"Truy vấn bảng nhạy cảm không có mệnh đề LIMIT và không có hàm tổng hợp gom nhóm (+35 điểm)"
            )

        if is_bulk:
            score += 35.0

        # 6. Khung giờ nhạy cảm (Ban đêm 0h - 6h: +30 điểm)
        if hour in cls.SENSITIVE_HOURS:
            score += 30.0
            factors.append(f"Truy cập vào khung giờ ban đêm ({hour:02d}:00) ngoài giờ làm việc (+30 điểm)")

        # 7. IP lạ ngoài dải tin cậy (+25 điểm)
        if not any(ip_address.startswith(p) for p in cls.TRUSTED_IPS):
            score += 25.0
            factors.append(f"Địa chỉ IP không thuộc dải tin cậy ({ip_address}) (+25 điểm)")

        # 8. Lịch sử sai mật khẩu (+15/lần, tối đa 45 điểm)
        if failed_logins > 0:
            penalty = min(failed_logins * 15.0, 45.0)
            score += penalty
            factors.append(f"Lịch sử nhập sai mật khẩu {failed_logins} lần gần đây (+{penalty:.0f} điểm)")

        # 9. Tốc độ thao tác cao bất thường QPS > 5 (+20 điểm)
        if qps > 5.0:
            score += 20.0
            factors.append(f"Tần suất truy vấn cao bất thường ({qps:.1f} req/s > 5.0) (+20 điểm)")

        # 10. HỌC MÁY: Phát hiện hành vi bất thường (Isolation Forest + hồ sơ z-score theo người dùng)
        features = None
        anomaly_info: Optional[Dict[str, Any]] = None
        if use_anomaly:
            try:
                from app.ai_anomaly_detector import build_features, get_anomaly_detector
                features = build_features(
                    hour=hour,
                    rows=eff_rows,
                    n_tables=len(tables),
                    n_columns=len(columns),
                    has_star=has_star,
                    has_limit=has_limit,
                    has_agg=has_agg,
                    qps=qps,
                    sql_len=len(sql_query or ""),
                )
                anomaly_info = get_anomaly_detector().score(features, user=user, rows=eff_rows)
                w_anom = SECURITY_WEIGHTS.get("anomaly", 20.0)
                w_user = SECURITY_WEIGHTS.get("user_deviation", 15.0)
                if anomaly_info["is_anomaly"]:
                    score += w_anom
                    factors.append(
                        f"Mô hình Isolation Forest phát hiện hành vi truy vấn bất thường "
                        f"(điểm bất thường {anomaly_info['anomaly_score']:.2f}) (+{w_anom:.0f} điểm)"
                    )
                if anomaly_info["user_deviation"]:
                    score += w_user
                    factors.append(
                        f"Số dòng truy xuất lệch {anomaly_info['user_zscore']} độ lệch chuẩn so với thói quen "
                        f"của người dùng `{user}` (+{w_user:.0f} điểm)"
                    )
            except Exception as e:  # Lỗi ML không được làm sập luồng an ninh theo luật
                logger.warning("Anomaly detector lỗi, bỏ qua thành phần học máy: %s", e)

        # Giới hạn thang điểm 0 - 100
        final_score = min(max(score, 0.0), 100.0)

        # Phân loại trạng thái an ninh (A3-2)
        recommended_dba_actions = []
        if final_score >= 70.0:
            status = "HIGH"
            level_label = "NGUY CƠ CAO (HIGH)"
            action = "CHẶN TRUY VẤN (Đề xuất DBA thu hồi quyền)"
            allowed = False
            # Sinh câu lệnh DBA gợi ý
            all_accessed = list(tables) if tables else ["san_pham"]
            recommended_dba_actions = [
                f"REVOKE SELECT ON \"LinhKien\".{t} FROM {user};"
                for t in all_accessed
            ]
        elif final_score >= 40.0:
            status = "WARNING"
            level_label = "CẢNH BÁO (WARNING)"
            action = "KÍCH HOẠT DYNAMIC RLS (Giới hạn dòng và che dữ liệu nhạy cảm)"
            allowed = True
        else:
            status = "NORMAL"
            level_label = "AN TOÀN (NORMAL)"
            action = "CHO PHÉP THỰC THI BÌNH THƯỜNG"
            allowed = True

        eval_result = {
            "score": round(final_score, 1),
            "status": status,
            "level_label": level_label,
            "action": action,
            "allowed": allowed,
            "factors": factors if factors else ["Tất cả thông số phiên nằm trong ngưỡng an toàn tuyệt đối."],
            "evaluated_at": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
            "user": user,
            "ip": ip_address,
            "hour": hour,
            "estimated_rows": eff_rows,
            "qps": qps,
            "accessed_tables": list(tables),
            "accessed_columns": list(columns),
            "recommended_dba_actions": recommended_dba_actions,
            "anomaly": anomaly_info,
            "engine": engine,
        }

        # Ghi nhật ký kiểm toán (A3-4); write_log=False khi chỉ chấm thử (vd: nạp lịch sử mẫu)
        if not write_log:
            return eval_result
        write_audit_log({
            "timestamp": datetime.now().isoformat(),
            "engine": engine,
            "question": (question or "")[:300],
            "user": user,
            "ip": ip_address,
            "sql": sql_query[:300],
            "score": eval_result["score"],
            "status": eval_result["status"],
            "allowed": eval_result["allowed"],
            "factors": eval_result["factors"],
            "features": features,
            "anomaly_score": anomaly_info["anomaly_score"] if anomaly_info else None,
        })

        # Đẩy cảnh báo mức HIGH vào CSDL -> Trigger -> pg_notify (LISTEN/NOTIFY), best-effort
        if status == "HIGH":
            publish_security_alert(eval_result, sql_query)

        return eval_result


def publish_security_alert(eval_result: Dict[str, Any], sql_query: str) -> bool:
    """
    Ghi cảnh báo an ninh mức HIGH vào bảng "LinhKien".security_alert_log.
    Trigger trg_security_alert_notify (database/ai_notify_alerts.sql) sẽ phát pg_notify
    lên kênh 'ai_security_alert' để tiến trình security_listener.py nhận theo thời gian thực.
    Chỉ chạy khi ALLOW_ADMIN_CONNECTION=1; mọi lỗi đều được bỏ qua (không ảnh hưởng luồng chính).
    """
    try:
        from app import config
        if not getattr(config, "ALLOW_ADMIN_CONNECTION", False):
            return False
        from app.db import get_connection
        conn = get_connection(use_admin=True)
        try:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO "LinhKien".security_alert_log (nguoi_dung, dia_chi_ip, diem_rui_ro, muc_do, cau_sql, cac_yeu_to) '
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb);",
                (
                    str(eval_result.get("user", ""))[:100],
                    str(eval_result.get("ip", ""))[:64],
                    float(eval_result.get("score", 0)),
                    eval_result.get("status", "HIGH"),
                    (sql_query or "")[:1000],
                    json.dumps(eval_result.get("factors", []), ensure_ascii=False),
                ),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.info("Không ghi được cảnh báo vào CSDL (bỏ qua): %s", e)
        return False


# ==============================================================================
# GIÁM SÁT AI 2 (SEMANTIC SEARCH) — chấm điểm ở mức CÂU HỎI
# AI 2 không chạy SQL do người dùng tạo nên không có nguy cơ tiêm mã SQL vào CSDL;
# rủi ro chính là bị lợi dụng để VÉT DỮ LIỆU danh mục/giá sản phẩm và gửi nội dung độc hại.
# (Theo yêu cầu: KHÔNG chấm điểm tần suất hỏi nhanh cho AI 2.)
# ==============================================================================
_RE_CODE_PAYLOAD = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|union|grant|revoke|pg_sleep|copy)\b|--|;|/\*|<script|\$\{|`",
    re.IGNORECASE,
)
_RE_BULK_REQUEST = re.compile(
    r"\b(tat ca|toan bo|liet ke het|xuat het|het san pham|moi san pham|dump|export|xuat file|bang gia day du|full)\b",
    re.IGNORECASE,
)

SEMANTIC_WEIGHTS = {
    "code_payload": 45.0,      # Câu hỏi chứa mã SQL / script
    "bulk_request": 15.0,      # Yêu cầu lấy "tất cả / toàn bộ"
    "coverage_warn": 30.0,     # Phiên đã xem > 30% danh mục sản phẩm
    "coverage_high": 55.0,     # Phiên đã xem > 60% danh mục sản phẩm
    "night": 30.0,             # 0h - 6h
    "untrusted_ip": 25.0,
    "anomaly": 20.0,           # Isolation Forest
    "too_long": 10.0,          # Câu hỏi dài bất thường
}
COVERAGE_WARN = 0.30
COVERAGE_HIGH = 0.60


def evaluate_semantic_request(
    question: str,
    user: str = "guest",
    ip_address: str = "127.0.0.1",
    hour: Optional[int] = None,
    coverage_ratio: float = 0.0,
    catalog_size: int = 0,
    seen_count: int = 0,
    use_anomaly: bool = True,
    write_log: bool = True,
) -> Dict[str, Any]:
    """
    AI 3 giám sát một yêu cầu gửi tới AI 2 (tìm kiếm ngữ nghĩa linh kiện).
    Các yếu tố: nội dung chứa mã, yêu cầu lấy toàn bộ, ĐỘ PHỦ DANH MỤC đã bị lấy trong phiên
    (dấu hiệu vét dữ liệu), giờ truy cập, IP, độ dài câu hỏi và mô hình Isolation Forest.
    Không dùng tần suất hỏi (QPS) cho AI 2.
    Hành động: < 40 cho phép; 40-69 giới hạn số kết quả; >= 70 chặn.
    """
    from app.text_normalizer import remove_diacritics

    if hour is None:
        hour = datetime.now().hour
    q = question or ""
    q_no = remove_diacritics(q.lower())
    score, factors = 0.0, []
    W = SEMANTIC_WEIGHTS

    if _RE_CODE_PAYLOAD.search(q):
        score += W["code_payload"]
        factors.append(f"Câu hỏi chứa mã SQL/script hoặc ký tự đặc biệt dùng để tấn công (+{W['code_payload']:.0f} điểm)")
    if _RE_BULK_REQUEST.search(q_no):
        score += W["bulk_request"]
        factors.append(f"Yêu cầu lấy toàn bộ / xuất hết dữ liệu sản phẩm (+{W['bulk_request']:.0f} điểm)")
    if coverage_ratio >= COVERAGE_HIGH:
        score += W["coverage_high"]
        factors.append(
            f"Phiên đã lấy {seen_count}/{catalog_size} sản phẩm ({coverage_ratio:.0%} danh mục) — dấu hiệu vét dữ liệu (+{W['coverage_high']:.0f} điểm)"
        )
    elif coverage_ratio >= COVERAGE_WARN:
        score += W["coverage_warn"]
        factors.append(
            f"Phiên đã lấy {seen_count}/{catalog_size} sản phẩm ({coverage_ratio:.0%} danh mục) (+{W['coverage_warn']:.0f} điểm)"
        )
    if hour in AISecurityGuard.SENSITIVE_HOURS:
        score += W["night"]
        factors.append(f"Truy cập vào khung giờ ban đêm ({hour:02d}:00) (+{W['night']:.0f} điểm)")
    if not any(ip_address.startswith(p) for p in AISecurityGuard.TRUSTED_IPS):
        score += W["untrusted_ip"]
        factors.append(f"Địa chỉ IP không thuộc dải tin cậy ({ip_address}) (+{W['untrusted_ip']:.0f} điểm)")
    if len(q) > 200:
        score += W["too_long"]
        factors.append(f"Câu hỏi dài bất thường ({len(q)} ký tự) (+{W['too_long']:.0f} điểm)")

    anomaly_info = None
    features = None
    if use_anomaly:
        try:
            from app.ai_anomaly_detector import build_features, get_anomaly_detector
            # Ánh xạ yêu cầu AI 2 sang không gian đặc trưng chung; QPS cố định 0 (không xét tần suất)
            features = build_features(
                hour=hour, rows=max(seen_count, 1), n_tables=1, n_columns=0,
                has_star=False, has_limit=True, has_agg=False, qps=0.0, sql_len=len(q),
            )
            anomaly_info = get_anomaly_detector().score(features, user=None, rows=0)
            if anomaly_info["is_anomaly"]:
                score += W["anomaly"]
                factors.append(
                    f"Mô hình Isolation Forest đánh giá yêu cầu bất thường (điểm {anomaly_info['anomaly_score']:.2f}) (+{W['anomaly']:.0f} điểm)"
                )
        except Exception as e:
            logger.warning("Anomaly detector lỗi khi giám sát AI 2: %s", e)

    final_score = min(max(score, 0.0), 100.0)
    if final_score >= 70:
        status, level_label, allowed, max_results = "HIGH", "NGUY CƠ CAO (HIGH)", False, 0
        action = "CHẶN YÊU CẦU AI 2"
    elif final_score >= 40:
        status, level_label, allowed, max_results = "WARNING", "CẢNH BÁO (WARNING)", True, 3
        action = "GIỚI HẠN CÒN 3 KẾT QUẢ"
    else:
        status, level_label, allowed, max_results = "NORMAL", "AN TOÀN (NORMAL)", True, None
        action = "CHO PHÉP"

    result = {
        "engine": "AI 2",
        "score": round(final_score, 1),
        "status": status,
        "level_label": level_label,
        "action": action,
        "allowed": allowed,
        "max_results": max_results,
        "factors": factors if factors else ["Yêu cầu tư vấn linh kiện bình thường."],
        "coverage_ratio": round(coverage_ratio, 3),
        "anomaly": anomaly_info,
        "user": user,
        "ip": ip_address,
        "hour": hour,
    }
    if not write_log:
        return result
    write_audit_log({
        "timestamp": datetime.now().isoformat(),
        "engine": "AI 2",
        "question": q[:300],
        "user": user,
        "ip": ip_address,
        "sql": "",
        "score": result["score"],
        "status": status,
        "allowed": allowed,
        "factors": result["factors"],
        "features": features,
        "anomaly_score": anomaly_info["anomaly_score"] if anomaly_info else None,
    })
    if status == "HIGH":
        publish_security_alert(result, f"[AI 2] {q}")
    return result


def summarize_by_engine(limit: int = 1000) -> Dict[str, Dict[str, int]]:
    """Thống kê nhật ký kiểm toán theo từng AI: tổng, cảnh báo, chặn."""
    stats: Dict[str, Dict[str, int]] = {}
    for r in read_audit_log(limit=limit):
        if r.get("source") == "seed_lich_su":
            continue  # lịch sử mẫu chỉ dùng để huấn luyện, không tính vào số liệu giám sát
        eng = r.get("engine") or "Khác"
        st_ = stats.setdefault(eng, {"tong": 0, "canh_bao": 0, "chan": 0})
        st_["tong"] += 1
        if r.get("status") == "WARNING":
            st_["canh_bao"] += 1
        if r.get("allowed") is False:
            st_["chan"] += 1
        if r.get("stage") == "Đầu vào":
            inp = stats.setdefault("Đầu vào", {"tong": 0, "canh_bao": 0, "chan": 0})
            inp["tong"] += 1
            inp["canh_bao"] += int(r.get("status") == "WARNING")
            inp["chan"] += int(r.get("allowed") is False)
    return stats


# ==============================================================================
# CHỐT CHẶN ĐẦU VÀO: AI 3 ĐỌC MỌI CÂU HỎI TIẾNG VIỆT TRƯỚC KHI ĐỊNH TUYẾN
# Bắt các yêu cầu THAY ĐỔI / PHÁ HOẠI dữ liệu viết bằng tiếng Việt tự nhiên
# (vd: "xóa bảng sản phẩm", "cập nhật giá", "cấp quyền admin") — những câu này không sinh
# ra SQL nên trước đây đi thẳng vào nhánh "không nhận diện được" mà AI 3 không hề thấy.
# Quy tắc: ĐỘNG TỪ thay đổi đứng TRƯỚC ĐỐI TƯỢNG dữ liệu (tránh báo nhầm "đơn hàng đã hủy",
# "sản phẩm mới thêm").
# ==============================================================================
# Động từ "mạnh": gần như luôn mang nghĩa ghi/xóa -> cho phép đối tượng đứng cách tối đa 40 ký tự
_VN_WRITE_VERBS = (
    r"xoa|xoa bo|xoa het|xoa sach|go bo|drop|truncate|delete|huy bang|huy toan bo|don sach|lam trong|"
    r"chinh sua|cap nhat|update|thay doi|dat lai|reset|ghi de|"
    r"chen|insert|create|alter|"
    r"cap quyen|grant|trao quyen|nang quyen|thu hoi quyen|revoke|vo hieu hoa|disable"
)
# Động từ "ngắn" dễ trùng nghĩa khi bỏ dấu (đổi/đôi/đợi, khóa/khoa, tạo, thêm, sửa) -> đối tượng phải đứng ngay sau
_VN_WEAK_VERBS = r"doi|khoa|tao|them|sua"
_VN_DATA_OBJECTS = (
    r"bang|du lieu|database|csdl|co so du lieu|schema|table|"
    r"san pham|don hang|khach hang|nhan vien|nha cung cap|thanh toan|ton kho|danh muc|thuong hieu|phieu nhap|"
    r"gia|so luong|trang thai|"
    r"tai khoan|nguoi dung|user|mat khau|password|quyen|role|admin|superuser|"
    r"trigger|index|chi muc|rls|policy|backup|ban sao luu"
)
_RE_VN_WRITE_INTENT = re.compile(
    r"\b(" + _VN_WRITE_VERBS + r")\b.{0,40}?\b(" + _VN_DATA_OBJECTS + r")\b",
    re.IGNORECASE,
)
_RE_VN_WEAK_INTENT = re.compile(
    r"\b(" + _VN_WEAK_VERBS + r")\s+(?:\w+\s+){0,1}?(" + _VN_DATA_OBJECTS + r")\b",
    re.IGNORECASE,
)
# Dạng CÓ DẤU bắt buộc của động từ ngắn (để "đợi đơn hàng", "card đôi giá" không bị báo nhầm)
_WEAK_VERB_ACCENTED = ("đổi", "khóa", "khoá", "tạo", "thêm", "sửa")


def _find_write_intent(q_lower: str, q_no: str) -> Optional[str]:
    m = _RE_VN_WRITE_INTENT.search(q_no)
    if m:
        return m.group(0)
    for m in _RE_VN_WEAK_INTENT.finditer(q_no):
        # remove_diacritics đổi từng ký tự nên vị trí trong chuỗi gốc trùng khớp
        original = q_lower[m.start():m.end()] if len(q_lower) == len(q_no) else ""
        if not original or original.startswith(_WEAK_VERB_ACCENTED):
            return m.group(0)
    return None
_RE_VN_SECRET = re.compile(
    r"\b(mat khau|password|password_hash|hash mat khau|gia von|gia nhap goc)\b", re.IGNORECASE
)
QUESTION_WEIGHTS = {"write_intent": 80.0, "secret_request": 40.0}


def evaluate_question_text(
    question: str,
    user: str = "guest",
    ip_address: str = "127.0.0.1",
    target_engine: str = "AI 1",
) -> Dict[str, Any]:
    """
    AI 3 kiểm tra NỘI DUNG câu hỏi tiếng Việt trước khi chuyển cho AI 1 / AI 2.
    - Ý định ghi/xóa/sửa/cấp quyền trên dữ liệu (+80, HIGH -> chặn): hệ thống chỉ cho phép ĐỌC.
    - Hỏi dữ liệu bí mật như mật khẩu, giá vốn (+40, WARNING -> ghi nhận và để AI 1 che cột).
    Chỉ ghi nhật ký khi có rủi ro (câu hỏi bình thường đã được AI 1 / AI 2 ghi nhật ký riêng).
    """
    from app.text_normalizer import remove_diacritics

    import unicodedata
    q_lower = unicodedata.normalize("NFC", question or "").lower()
    q_no = remove_diacritics(q_lower)
    score, factors = 0.0, []
    hit = _find_write_intent(q_lower, q_no)
    if hit:
        score += QUESTION_WEIGHTS["write_intent"]
        factors.append(
            f"Câu hỏi yêu cầu THAY ĐỔI/XÓA dữ liệu («{hit}») trong khi hệ thống chỉ cho phép đọc "
            f"(+{QUESTION_WEIGHTS['write_intent']:.0f} điểm)"
        )
    if _RE_VN_SECRET.search(q_no):
        score += QUESTION_WEIGHTS["secret_request"]
        factors.append(f"Câu hỏi nhắm tới dữ liệu bí mật (mật khẩu / giá vốn) (+{QUESTION_WEIGHTS['secret_request']:.0f} điểm)")
    if not any(ip_address.startswith(p) for p in AISecurityGuard.TRUSTED_IPS) and score > 0:
        score += 25.0
        factors.append(f"Địa chỉ IP không thuộc dải tin cậy ({ip_address}) (+25 điểm)")

    final_score = min(score, 100.0)
    if final_score >= 70:
        status, label, allowed, action = "HIGH", "NGUY CƠ CAO (HIGH)", False, "CHẶN CÂU HỎI (chỉ cho phép truy vấn đọc)"
    elif final_score >= 40:
        status, label, allowed, action = "WARNING", "CẢNH BÁO (WARNING)", True, "GHI NHẬN, CHO PHÉP ĐỌC CÓ CHE DỮ LIỆU"
    else:
        status, label, allowed, action = "NORMAL", "AN TOÀN (NORMAL)", True, "CHO PHÉP"

    result = {
        "engine": target_engine,
        "stage": "Đầu vào",
        "score": round(final_score, 1),
        "status": status,
        "level_label": label,
        "action": action,
        "allowed": allowed,
        "factors": factors,
        "user": user,
        "ip": ip_address,
    }
    if status != "NORMAL":
        write_audit_log({
            "timestamp": datetime.now().isoformat(),
            # Ghi nhận theo AI mà câu hỏi nhắm tới, đánh dấu bị chặn ở bước đầu vào
            "engine": target_engine,
            "stage": "Đầu vào",
            "question": (question or "")[:300],
            "user": user,
            "ip": ip_address,
            "sql": "",
            "score": result["score"],
            "status": status,
            "allowed": allowed,
            "factors": factors,
        })
        if status == "HIGH":
            publish_security_alert(result, f"[Câu hỏi] {question}")
    return result
