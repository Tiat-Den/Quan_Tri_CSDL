"""
TRANG 2: BẢNG ĐIỀU KHIỂN QUẢN TRỊ CSDL & 6 ĐỘNG CƠ AI (DASHBOARD & APPS)
Được bảo vệ bởi tầng xác thực: Nếu chưa đăng nhập, tự động quay về trang đăng nhập.
"""

import streamlit as st

# Kiểm tra nếu chưa đăng nhập thì tự động đẩy về trang Login
if st.session_state.get("current_user") is None:
    st.warning("Bạn chưa đăng nhập! Đang chuyển hướng về trang đăng nhập...")
    st.switch_page("views/login_page.py")

import os
import sys
import time
from datetime import datetime, date
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

# Tự động chuyển sang chế độ Streamlit Server nếu người dùng chạy trực tiếp bằng lệnh `python web_app.py`
if not st.runtime.exists():
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", __file__, "--server.port=8501", "--server.headless=false"]
    sys.exit(stcli.main())

# Thiết lập đường dẫn thư mục làm việc để import nhất quán
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from app import config
from app.db import (
    check_db_connection,
    execute_query,
    get_dashboard_summary,
    get_low_stock_data,
    get_monthly_revenue_data,
    get_schema_info,
)
from app.pipeline import interpret, InterpretResult

# Import các Module AI Mở Rộng
from app.router import route, RouteDecision
from app.ai_semantic_search import semantic_search_engine, get_engine
from app.ai_security_guard import (
    AISecurityGuard,
    evaluate_question_text,
    evaluate_semantic_request,
    read_audit_log,
    summarize_by_engine,
)
from app.session_context import SessionContext, rate_tracker, mask_sensitive_columns, coverage_tracker
import uuid

# Mỗi phiên trình duyệt có mã riêng để AI 3 theo dõi hành vi độc lập (tần suất, độ phủ danh mục...)
if "session_id" not in st.session_state:
    st.session_state["session_id"] = f"web_{uuid.uuid4().hex[:12]}"


def _current_username() -> str:
    user = st.session_state.get("current_user") or {}
    return user.get("username") or get_current_role(st.session_state)
from app.ai_index_advisor import AIIndexAdvisor
from app.ai_predictive_partitioning import AIPredictivePartitioningEngine
from app.auth import authenticate, is_admin, is_manager, get_current_role
from app.ai_smart_backup import smart_backup_engine, AISmartBackupEngine
from app.ui_theme import BASE_CSS, CHART_BLUE, badge, kpi_card, meter, section_header, sub_header

# ==============================================================================
# BỘ ĐỆM DỮ LIỆU HIỂN THỊ (st.cache_data)
# Streamlit chạy lại TOÀN BỘ trang (cả 8 tab) sau mỗi cú bấm. Các số liệu chỉ để xem (trạng thái CSDL,
# tổng quan, lược đồ, AI 6...) được lưu đệm vài chục giây thay vì truy vấn lại mỗi lần -> trang phản hồi nhanh.
# Nút "Làm mới dữ liệu" ở thanh bên xóa bộ đệm khi cần số liệu tức thời.
# ==============================================================================
@st.cache_data(ttl=30, show_spinner=False)
def _c_db_status():
    return check_db_connection()


@st.cache_data(ttl=300, show_spinner=False)
def _c_schema_info():
    return get_schema_info()


@st.cache_data(ttl=60, show_spinner=False)
def _c_dashboard_summary():
    return get_dashboard_summary()


@st.cache_data(ttl=60, show_spinner=False)
def _c_monthly_revenue():
    return get_monthly_revenue_data()


@st.cache_data(ttl=60, show_spinner=False)
def _c_low_stock(limit: int):
    return get_low_stock_data(limit=limit)


@st.cache_data(ttl=60, show_spinner=False)
def _c_query(sql: str):
    return execute_query(sql)


@st.cache_data(ttl=60, show_spinner=False)
def _c_change_rate():
    return smart_backup_engine.analyze_change_rate()


@st.cache_data(ttl=120, show_spinner=False)
def _c_forecast_size():
    return smart_backup_engine.forecast_backup_size()


@st.cache_data(ttl=60, show_spinner=False)
def _c_risk(**kwargs):
    # use_real=True đọc lịch sử backup + archive_mode + dung lượng đĩa (mở kết nối quản trị) -> lưu đệm 60 giây
    return smart_backup_engine.evaluate_risk(**kwargs)


@st.cache_data(ttl=300, show_spinner=False)
def _c_table_catalog():
    """Số dòng ước tính (pg_class.reltuples), số khóa ngoại, số chỉ mục của từng bảng (bỏ bảng con phân vùng)."""
    res = execute_query(
        """
        SELECT c.relname AS bang,
               GREATEST(c.reltuples, 0)::bigint AS so_dong,
               (SELECT count(*) FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'f') AS so_fk,
               (SELECT count(*) FROM pg_index i WHERE i.indrelid = c.oid) AS so_index,
               c.relkind = 'p' AS phan_vung
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'LinhKien' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
        ORDER BY c.relname;
        """
    )
    return {r["bang"]: r for r in res.get("data", [])} if res.get("success") else {}


@st.cache_data(ttl=30, show_spinner=False)
def _c_backup_history(limit: int):
    return smart_backup_engine.get_backup_history(limit=limit)


# ==============================================================================
# CẤU HÌNH TRANG STREAMLIT
# ==============================================================================
st.set_page_config(
    page_title="Hệ Thống Quản Trị CSDL Linh Kiện",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Giao diện chuẩn Enterprise: CSS dùng chung ở app/ui_theme.py
st.markdown(BASE_CSS, unsafe_allow_html=True)

# ==============================================================================
# KHỞI TẠO SESSION STATE
# ==============================================================================
if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "login_failed" not in st.session_state:
    st.session_state.login_failed = False

if "history" not in st.session_state:
    st.session_state.history = []

if "query_input" not in st.session_state:
    st.session_state.query_input = ""

if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

if "input_box" not in st.session_state:
    st.session_state.input_box = ""

# ==============================================================================
# DANH SÁCH 20 CÂU HỎI MẪU VÀNG PHÂN THEO 3 CẤP ĐỘ (AI 1)
# ==============================================================================
def select_sample_question(question_text: str):
    st.session_state.query_input = question_text
    st.session_state.input_box = question_text
    st.session_state.auto_run = True

def clear_query_input():
    st.session_state.query_input = ""
    st.session_state.input_box = ""
    st.session_state.auto_run = False

SAMPLE_QUESTIONS_BY_LEVEL = {
    "Cấp độ 1: Cơ bản (Đơn bảng, Lọc, Đếm, Tồn kho)": [
        "Danh sách sản phẩm đang bán",
        "Tìm sản phẩm có giá trên 5 triệu",
        "Các linh kiện có giá từ 1 triệu đến 3 triệu",
        "Top 5 sản phẩm đắt nhất",
        "Top 10 linh kiện rẻ nhất",
        "Đếm tổng số đơn hàng của cửa hàng",
        "Danh sách các đơn hàng đã hủy",
    ],
    "Cấp độ 2: Trung bình (Khoảng giá, Sắp xếp, Trạng thái, Kênh bán)": [
        "Liệt kê tất cả card màn hình VGA",
        "Tìm các sản phẩm của hãng ASUS",
        "Những sản phẩm nào sắp hết hàng trong kho?",
        "Thống kê số lượng đơn hàng theo từng trạng thái",
        "Thống kê số đơn và doanh thu theo từng kênh bán",
        "Khách hàng hay thanh toán qua những phương thức nào nhất?",
        "Thống kê số lượng khách hàng theo từng tỉnh thành",
    ],
    "Cấp độ 3: Nâng cao (Gom nhóm, Xếp hạng VIP, Doanh thu)": [
        "Top 5 sản phẩm bán chạy nhất của cửa hàng",
        "Top 5 khách hàng mua nhiều tiền nhất",
        "Thống kê doanh thu theo từng tháng trong năm 2025",
        "Doanh số bán hàng của từng nhân viên",
        "Tổng doanh thu của tất cả đơn hàng đã hoàn thành",
        "Tổng tiền nhập hàng từ các nhà cung cấp",
    ],
}

# ==============================================================================
# HÀM XỬ LÝ TEXT-TO-SQL NỘI BỘ (AI 1)
# ==============================================================================
def process_question(question_text: str, role: str = 'admin') -> Dict[str, Any]:
    """Phân tích câu hỏi tự nhiên tiếng Việt sang SQL và chạy trên PostgreSQL thông qua pipeline dùng chung."""
    raw_question = question_text.strip() if question_text else ""
    if not raw_question:
        return {"success": False, "error": "Câu hỏi không được để trống"}

    # Kiểm tra khóa phiên tạm thời (Session Lockout) do vi phạm HIGH trước đó (A3-4)
    lockout_until = st.session_state.get("security_lockout_until", 0)
    now_ts = time.time()
    if lockout_until > now_ts:
        remaining = int(lockout_until - now_ts)
        return {
            "success": False,
            "error": f"Phiên làm việc tạm thời bị khóa do phát hiện nguy cơ an ninh cao (AI 3 Zero-Trust). Vui lòng thử lại sau {remaining} giây.",
            "error_type": "SECURITY_LOCKOUT",
            "sql": None,
        }

    res = interpret(raw_question)
    if not res.success or res.intent == "UNKNOWN":
        return {
            "success": False,
            "intent": "UNKNOWN",
            "confidence": 0.0,
            "entities": res.entities,
            "sql": None,
            "params": [],
            "explanation": res.explanation,
            "error_type": "UNKNOWN_INTENT",
            "matched_rule": res.matched_rule,
            "needs_clarification": res.needs_clarification,
            "clarification": res.clarification,
            "warnings": res.warnings,
        }

    # Đánh giá an ninh trước khi thực thi (AI 3 Zero-Trust Guard - A3-4)
    session_id = st.session_state.get("session_id", "web_session")
    real_qps = rate_tracker.record_hit(session_id)
    ctx = SessionContext(
        session_id=session_id,
        user=_current_username(),
        ip=st.session_state.get("sec_ip", "127.0.0.1"),
        ip_source="simulated",
        failed_logins=st.session_state.get("sec_failed", 0),
        qps=real_qps,
    )

    # Ước lượng số dòng THẬT bằng EXPLAIN để AI 3 nhận diện truy vấn trích xuất lớn
    plan_rows = None
    try:
        exp_res = execute_query(f"EXPLAIN (FORMAT JSON) {res.sql.strip().rstrip(';')}", res.params)
        if exp_res.get("success") and exp_res.get("data"):
            plan_rows = int(exp_res["data"][0]["QUERY PLAN"][0]["Plan"].get("Plan Rows", 0))
    except Exception:
        plan_rows = None

    sec_eval = AISecurityGuard.evaluate_risk(
        res.sql, ctx=ctx, plan_rows=plan_rows, engine="AI 1", question=raw_question,
    )

    if not sec_eval["allowed"]:
        # Khóa phiên trong 60 giây nếu đạt mức HIGH (A3-4)
        st.session_state["security_lockout_until"] = time.time() + 60
        return {
            "success": False,
            "error": f"Truy vấn bị chặn bởi AI 3 Zero-Trust Security Guard! Điểm rủi ro: {sec_eval['score']}/100 ({sec_eval['level_label']}). Hành động: {sec_eval['action']}",
            "error_type": "SECURITY_BLOCKED",
            "sql": res.sql,
            "security_eval": sec_eval,
            "explanation": res.explanation,
            "recommended_dba_actions": sec_eval.get("recommended_dba_actions", []),
        }

    # Thực thi an toàn trên CSDL PostgreSQL
    db_res = execute_query(res.sql, res.params, role=role)

    # Nếu trạng thái WARNING -> Áp dụng Dynamic Masking che cột nhạy cảm (A3-4)
    data = db_res.get("data", [])
    warnings = list(res.warnings)
    if sec_eval["status"] == "WARNING" and data:
        data = mask_sensitive_columns(data)
        warnings.append("AI 3 Security Guard: Đã kích hoạt Dynamic Data Masking để che các trường dữ liệu nhạy cảm (Email, SĐT, Địa chỉ).")

    return {
        "success": db_res["success"],
        "intent": res.intent,
        "confidence": res.confidence,
        "matched_rule": res.matched_rule,
        "entities": res.entities,
        "sql": res.sql,
        "params": res.params,
        "explanation": res.explanation,
        "columns": db_res.get("columns", []),
        "data": data,
        "row_count": len(data) if data else db_res.get("row_count", 0),
        "execution_time_ms": db_res.get("execution_time_ms", 0.0),
        "db_error": db_res.get("error", ""),
        "truncated": db_res.get("truncated", False),
        "needs_clarification": res.needs_clarification,
        "clarification": res.clarification,
        "warnings": warnings,
        "security_eval": sec_eval,
    }


def route_and_execute_question(question_text: str) -> Dict[str, Any]:
    """
    Tự động phân loại câu hỏi và định tuyến thông minh qua Router:
    - Nếu khớp Intent truy vấn CSDL -> Kích hoạt AI 1 (Text-to-SQL Engine).
    - Nếu là nhu cầu phần cứng, tư vấn cấu hình -> Kích hoạt AI 2 (Semantic Search & Knowledge Graph).
    """
    raw = question_text.strip()
    if not raw:
        return {"success": False, "error": "Câu hỏi không được để trống"}

    # CHỐT CHẶN ĐẦU VÀO: AI 3 đọc câu hỏi trước khi định tuyến (bắt cả câu không sinh ra SQL)
    lockout_until = st.session_state.get("security_lockout_until", 0)
    if lockout_until > time.time():
        return {
            "success": False,
            "engine": "AI 3",
            "error_type": "SECURITY_LOCKOUT",
            "error": f"Phiên làm việc tạm khóa do AI 3 phát hiện nguy cơ cao. Thử lại sau {int(lockout_until - time.time())} giây.",
        }
    # Phân loại trước (chỉ đọc, không thực thi) để biết câu hỏi nhắm tới AI nào
    pre_decision = route(raw)
    target_engine = "AI 2" if pre_decision.engine.lower() == "ai2" else "AI 1"
    q_sec = evaluate_question_text(
        raw, user=_current_username(), ip_address=st.session_state.get("sec_ip", "127.0.0.1"),
        target_engine=target_engine,
    )
    if not q_sec["allowed"]:
        st.session_state["security_lockout_until"] = time.time() + 60
        return {
            "success": False,
            "engine": "AI 3",
            "error_type": "SECURITY_BLOCKED",
            "error": f"AI 3 đã chặn câu hỏi! Điểm rủi ro {q_sec['score']}/100 ({q_sec['level_label']}). Hệ thống chỉ cho phép truy vấn ĐỌC dữ liệu.",
            "security_eval": q_sec,
        }

    decision = pre_decision
    engine_choice = decision.engine.lower()

    if engine_choice == "ai1":
        # => ĐỊNH TUYẾN SANG AI 1: TEXT-TO-SQL
        res = process_question(raw, role=get_current_role(st.session_state))
        res["engine"] = "AI 1"
        res["engine_name"] = "AI 1: Text-to-SQL Engine (Chuyển đổi truy vấn CSDL PostgreSQL)"
        res["route_decision"] = decision
        return res
    elif engine_choice == "ai2":
        # => ĐỊNH TUYẾN SANG AI 2: SEMANTIC SEARCH & KNOWLEDGE GRAPH
        engine = get_engine()
        engine.ensure_initialized()

        # AI 3 giám sát AI 2 trước khi trả kết quả (khóa phiên dùng chung với AI 1)
        lockout_until = st.session_state.get("security_lockout_until", 0)
        if lockout_until > time.time():
            return {
                "success": False,
                "engine": "AI 2",
                "error_type": "SECURITY_LOCKOUT",
                "error": f"Phiên làm việc tạm khóa do AI 3 phát hiện nguy cơ cao. Thử lại sau {int(lockout_until - time.time())} giây.",
                "route_decision": decision,
            }
        session_id = st.session_state.get("session_id", "web_session")
        catalog_size = len(getattr(engine, "products", []) or [])
        sem_sec = evaluate_semantic_request(
            raw,
            user=_current_username(),
            ip_address=st.session_state.get("sec_ip", "127.0.0.1"),
            coverage_ratio=coverage_tracker.coverage(session_id, catalog_size),
            catalog_size=catalog_size,
            seen_count=coverage_tracker.seen_count(session_id),
        )
        if not sem_sec["allowed"]:
            st.session_state["security_lockout_until"] = time.time() + 60
            return {
                "success": False,
                "engine": "AI 2",
                "error_type": "SECURITY_BLOCKED",
                "error": f"Yêu cầu bị AI 3 chặn! Điểm rủi ro {sem_sec['score']}/100 ({sem_sec['level_label']}).",
                "security_eval": sem_sec,
                "route_decision": decision,
            }

        sem_results = engine.search(raw, top_k=sem_sec["max_results"] or 5)
        coverage_tracker.add(session_id, [r.get("id") for r in sem_results])
        matched_needs = [n.get("tag", "") for n in decision.scores.get("needs", [])]
        if sem_results:
            return {
                "success": True,
                "engine": "AI 2",
                "engine_name": "AI 2: Semantic Search Engine (Không gian Vector TF-IDF & Bản đồ tri thức)",
                "query": raw,
                "matched_keywords": matched_needs,
                "results": sem_results,
                "security_eval": sem_sec,
                "row_count": len(sem_results),
                "execution_time_ms": 1.2,
                "route_decision": decision,
            }
        else:
            return {
                "success": False,
                "engine": "UNKNOWN",
                "error_type": "UNKNOWN_ALL",
                "error": "Câu hỏi nằm ngoài phạm vi 20 tập luật SQL của AI 1 và Bản đồ tri thức phần cứng của AI 2.",
                "route_decision": decision,
            }
    else:
        return {
            "success": False,
            "engine": "UNKNOWN",
            "error_type": "UNKNOWN_ALL",
            "error": "Câu hỏi nằm ngoài phạm vi 20 tập luật SQL của AI 1 và Bản đồ tri thức phần cứng của AI 2.",
            "route_decision": decision,
        }


# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.markdown(
        '<div class="side-brand">Quản trị CSDL cửa hàng linh kiện máy tính</div>',
        unsafe_allow_html=True,
    )

    # THÔNG TIN NGƯỜI DÙNG ĐĂNG NHẬP & PHÂN QUYỀN
    c_user = st.session_state.current_user
    _role_txt = "ADMIN" if is_admin(st.session_state) else "MANAGER"
    _initial = (c_user.get("ho_ten") or c_user.get("username") or "?").strip()[:1].upper()
    st.markdown(
        f"""
        <div class="user-card">
            <div class="user-avatar">{_initial}</div>
            <div>
                <div class="user-name">{c_user['ho_ten']}</div>
                {badge(_role_txt, "neutral")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Đăng xuất", use_container_width=True):
        st.session_state.current_user = None
        st.session_state.login_failed = False
        # Thu hồi token phiên trên server (link cũ trong lịch sử trình duyệt không vào lại được) rồi xóa khỏi URL
        from app.session_token import revoke_token

        revoke_token(st.query_params.get("t"))
        st.query_params.clear()
        st.rerun()

    # Kiểm tra trạng thái CSDL
    st.markdown('<div class="side-label">Kết nối cơ sở dữ liệu</div>', unsafe_allow_html=True)
    db_status = _c_db_status()
    if db_status["connected"]:
        st.markdown(
            f"""
            <div class="db-card">
                {badge("Đã kết nối", "healthy", dot=True)}<br>
                CSDL: <b>{db_status.get('database', 'LinhKien_DB')}</b> <br>
                Schema: <b>{db_status['schema']}</b><br>
                Độ trễ: <b>{db_status['latency_ms']} ms</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Làm mới dữ liệu", use_container_width=True, help="Xóa bộ đệm và tải lại số liệu mới nhất từ CSDL"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.markdown(f'<div class="db-card">{badge("Mất kết nối", "danger", dot=True)}</div>', unsafe_allow_html=True)
        st.error(f"Lỗi: {db_status.get('error', 'Không rõ')}")
        if st.button("Thử kết nối lại"):
            st.cache_data.clear()  # bỏ kết quả "mất kết nối" đang lưu đệm
            st.rerun()

    st.markdown('<div class="side-label">Bộ công cụ quản trị CSDL &amp; phân tích</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <ul class="module-list">
            <li><span class="code">AI 1</span><span><span class="name">TEX2SQL</span> · truy vấn bằng tiếng Việt</span></li>
            <li><span class="code">AI 2</span><span><span class="name">Semantic Search</span> · tư vấn linh kiện theo nhu cầu</span></li>
            <li><span class="code">AI 3</span><span><span class="name">Zero-Trust Sentinel</span> · giám sát an toàn truy vấn</span></li>
            <li><span class="code">AI 4</span><span><span class="name">Index Advisor</span> · khuyến nghị chỉ mục</span></li>
            <li><span class="code">AI 5</span><span><span class="name">Partitioning Planner</span> · quy hoạch phân vùng</span></li>
            <li><span class="code">AI 6</span><span><span class="name">Backup Intelligence</span> · sao lưu &amp; phục hồi</span></li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="side-label">Câu hỏi mẫu</div>', unsafe_allow_html=True)
    st.caption("Bấm để điền và thực thi ngay ở tab Truy vấn.")

    selected_level = st.selectbox("Cấp độ câu hỏi:", list(SAMPLE_QUESTIONS_BY_LEVEL.keys()))

    for q in SAMPLE_QUESTIONS_BY_LEVEL[selected_level]:
        st.button(
            q,
            key=f"sample_{q}",
            use_container_width=True,
            on_click=select_sample_question,
            args=(q,),
        )



# ==============================================================================
# TIÊU ĐỀ CHÍNH
# ==============================================================================
_hdr_role = "Admin" if is_admin(st.session_state) else "Manager"
st.markdown(
    f"""
    <div class="enterprise-header">
        <div>
            <h1>Hệ Thống Quản Trị CSDL Cửa Hàng Linh Kiện</h1>
        </div>
        <div class="meta">{_hdr_role} · {datetime.now().strftime("%d/%m/%Y")}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# ==============================================================================
# HỆ THỐNG 8 TAB CHÍNH
# ==============================================================================
(
    tab_ai12,
    tab_ai3,
    tab_ai4,
    tab_ai5,
    tab_ai6,
    tab_schema,
    tab_dashboard,
    tab_history,
) = st.tabs(
    [
        "Truy vấn",
        "Giám sát an toàn",
        "Cố vấn chỉ mục",
        "Quy hoạch phân vùng",
        "Sao lưu & phục hồi",
        "Lược đồ dữ liệu",
        "Tổng quan",
        "Lịch sử truy vấn",
    ]
)

# ------------------------------------------------------------------------------
# TAB 1: KẾT HỢP AI 1 & AI 2 (TỰ ĐỘNG ĐỊNH TUYẾN DỰA THEO CÂU HỎI)
# ------------------------------------------------------------------------------
with tab_ai12:
    st.markdown(section_header(
        "Truy vấn cơ sở dữ liệu bằng ngôn ngữ tự nhiên",
        "Câu hỏi được định tuyến tự động: câu hỏi nghiệp vụ tới AI 1 (sinh SQL và chạy trên PostgreSQL), "
        "nhu cầu tư vấn linh kiện tới AI 2 (tìm kiếm ngữ nghĩa). AI 3 kiểm tra mọi câu hỏi trước khi chạy.",
        "TEX2SQL / Semantic Search"), unsafe_allow_html=True)

    col_input, col_btn_run, col_btn_clear = st.columns([7.2, 1.6, 1.2])

    with col_input:
        user_question = st.text_input(
            "Nhập câu hỏi tiếng Việt bất kỳ:",
            placeholder="Ví dụ: Top 5 sản phẩm đắt nhất, Tìm linh kiện có giá trên 5 triệu, PC chơi game nặng, Cấu hình đồ họa render...",
            key="input_box",
            label_visibility="collapsed",
        )

    with col_btn_run:
        btn_run = st.button("Thực thi", type="primary", use_container_width=True)

    with col_btn_clear:
        btn_clear = st.button("Xóa", use_container_width=True, on_click=clear_query_input)

    # Bảng gợi ý câu hỏi mẫu cho cả 2 loại AI
    with st.expander("Câu hỏi mẫu (bấm để điền và thực thi)", expanded=False):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown("**Nghiệp vụ CSDL (AI 1)**")
            samples_ai1 = [
                "Top 5 sản phẩm đắt nhất",
                "Tìm sản phẩm có giá trên 5 triệu",
                "Các linh kiện có giá từ 1 triệu đến 3 triệu",
                "Đếm tổng số đơn hàng của cửa hàng",
                "Thống kê doanh thu theo từng tháng trong năm 2025",
                "Các sản phẩm sắp hết hàng",
            ]
            for s in samples_ai1:
                st.button(
                    s,
                    key=f"s_ai1_{s}",
                    use_container_width=True,
                    on_click=select_sample_question,
                    args=(s,),
                )

        with col_s2:
            st.markdown("**Tư vấn linh kiện (AI 2)**")
            samples_ai2 = [
                "PC chơi game nặng và stream",
                "Cấu hình làm đồ họa render video",
                "Máy tính văn phòng học tập giá rẻ",
                "Linh kiện mở nhiều tab đa nhiệm mượt",
                "Nâng cấp lưu trữ dữ liệu dung lượng lớn",
                "Bàn phím cơ gõ sướng và êm ái",
            ]
            for s in samples_ai2:
                st.button(
                    s,
                    key=f"s_ai2_{s}",
                    use_container_width=True,
                    on_click=select_sample_question,
                    args=(s,),
                )

    # Kích hoạt thực thi nếu người dùng bấm nút hoặc chọn từ câu hỏi mẫu
    should_execute = btn_run or st.session_state.auto_run
    if should_execute:
        # Nếu là auto_run (do bấm nút mẫu), ưu tiên dùng query_input được gán từ nút bấm
        if st.session_state.auto_run and st.session_state.query_input:
            query_to_run = st.session_state.query_input.strip()
        else:
            query_to_run = user_question.strip() or st.session_state.query_input.strip()
        st.session_state.auto_run = False

        if not query_to_run:
            st.warning("Vui lòng nhập câu hỏi trước khi thực thi.")
        else:
            with st.spinner("Đang phân tích câu hỏi và định tuyến..."):
                res = route_and_execute_question(query_to_run)

            # ======================= TRƯỜNG HỢP 1: KÍCH HOẠT AI 1 =======================
            if res.get("engine") == "AI 1":

                if not res.get("success") and res.get("needs_clarification") and res.get("clarification"):
                    # Hệ thống chưa chắc chắn -> hỏi lại kèm gợi ý thay vì báo lỗi
                    st.warning(res["clarification"])
                elif not res.get("success"):
                    st.error(f"Lỗi thực thi CSDL: {res.get('db_error') or res.get('error')}")
                    if res.get("sql"):
                        st.code(res["sql"], language="sql")
                else:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Ý định nhận diện", res["intent"])
                    _mech = "Học máy" if str(res.get("matched_rule", "")).startswith("ml_") else "Luật regex"
                    m2.metric("Độ tin cậy", f"{int(res['confidence'] * 100)}% ({_mech})")
                    m3.metric("Thời gian DB", f"{res['execution_time_ms']} ms")
                    m4.metric("Số dòng kết quả", f"{res['row_count']} dòng")

                    st.markdown("---")

                    col_sql, col_exp = st.columns([3, 2])
                    with col_sql:
                        st.markdown(sub_header("Câu lệnh SQL sinh ra"), unsafe_allow_html=True)
                        st.code(res["sql"], language="sql")
                        _how = "mô hình học máy cục bộ" if _mech == "Học máy" else "luật mẫu cục bộ"
                        st.caption(f"{res['execution_time_ms']} ms trên PostgreSQL · phân tích bằng {_how}"
                                   + (f" · tham số an toàn `{res['params']}`" if res.get("params") else ""))

                    with col_exp:
                        st.markdown(sub_header("Cách hệ thống hiểu câu hỏi"), unsafe_allow_html=True)
                        st.info(res["explanation"])
                        if res.get("entities"):
                            st.markdown(f"**Thực thể nhận diện được:** `{res['entities']}`")

                    _sec = res.get("security_eval") or {}
                    if _sec:
                        _txt = f"AI 3 giám sát: **{_sec.get('level_label')}** — {_sec.get('score')}/100 · {_sec.get('action')}"
                        if _sec.get("status") == "WARNING":
                            st.warning(_txt)
                        else:
                            st.caption(_txt)

                    # Bảng kết quả dữ liệu
                    st.markdown(sub_header("Kết quả từ PostgreSQL"), unsafe_allow_html=True)
                    if res["row_count"] > 0:
                        df = pd.DataFrame(res["data"])
                        st.dataframe(df, use_container_width=True)

                        csv_data = df.to_csv(index=False).encode("utf-8-sig")
                        st.download_button(
                            label="Tải kết quả về file CSV",
                            data=csv_data,
                            file_name=f"ket_qua_truy_van_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                        )
                    else:
                        st.info("Truy vấn thành công nhưng không tìm thấy bản ghi dữ liệu nào thỏa mãn điều kiện.")

                    st.session_state.history.insert(
                        0,
                        {
                            "Thời gian": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                            "Động cơ AI": "AI 1 (Text-to-SQL)",
                            "Câu hỏi": query_to_run,
                            "Chi tiết / Intent": res["intent"],
                            "Số dòng": res["row_count"],
                            "Thời gian (ms)": res["execution_time_ms"],
                            "Trạng thái": "Thành công",
                        },
                    )

            # ======================= TRƯỜNG HỢP 2: KÍCH HOẠT AI 2 =======================
            elif res.get("engine") == "AI 3":
                st.error(res.get("error"))
                for f in (res.get("security_eval") or {}).get("factors", []):
                    st.markdown(f"- {f}")
                st.caption("Phiên bị khóa 60 giây. Chi tiết xem ở tab Giám sát an toàn (lọc «Đầu vào»).")
                st.session_state.history.insert(
                    0,
                    {
                        "Thời gian": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                        "Động cơ AI": "AI 3 (chặn đầu vào)",
                        "Câu hỏi": query_to_run,
                        "Chi tiết / Intent": "BLOCKED",
                        "Số dòng": 0,
                        "Thời gian (ms)": 0.0,
                        "Trạng thái": "Bị chặn",
                    },
                )

            elif res.get("engine") == "AI 2" and not res.get("success"):
                st.error(res.get("error"))
                for f in (res.get("security_eval") or {}).get("factors", []):
                    st.markdown(f"- {f}")

            elif res.get("engine") == "AI 2":

                _sec2 = res.get("security_eval") or {}
                if _sec2:
                    _txt2 = f"AI 3 giám sát: **{_sec2.get('level_label')}** — {_sec2.get('score')}/100 · {_sec2.get('action')}"
                    if _sec2.get("status") == "WARNING":
                        st.warning(_txt2 + " — " + "; ".join(_sec2.get("factors", [])))
                    else:
                        st.caption(_txt2)

                matched_intents = res.get("matched_keywords", [])
                if matched_intents:
                    st.info(f"Bản đồ tri thức (Hardware Knowledge Graph) nhận diện nhu cầu: **{', '.join(matched_intents)}**")

                m1, m2, m3 = st.columns(3)
                m1.metric("Nhu cầu nhận diện", ", ".join(matched_intents) if matched_intents else "Nhu cầu ngữ nghĩa")
                m2.metric("Độ phù hợp cao nhất", f"{res['results'][0]['similarity_score']:.1f}%")
                m3.metric("Số linh kiện đề xuất", f"{len(res['results'])} sản phẩm")

                st.markdown("---")
                st.markdown(sub_header(f"{len(res['results'])} linh kiện phù hợp nhất trong kho"), unsafe_allow_html=True)

                df_sem = pd.DataFrame(res["results"])
                df_sem_display = df_sem[["ma_sku", "ten", "danh_muc", "thuong_hieu", "gia_niem_yet", "bao_hanh_thang", "similarity_score"]].copy()
                df_sem_display.rename(
                    columns={
                        "ma_sku": "Mã SKU",
                        "ten": "Tên Linh Kiện",
                        "danh_muc": "Danh Mục",
                        "thuong_hieu": "Thương Hiệu",
                        "gia_niem_yet": "Giá Niêm Yết (VNĐ)",
                        "bao_hanh_thang": "Bảo Hành (Tháng)",
                        "similarity_score": "Độ Phù Hợp (%)",
                    },
                    inplace=True,
                )
                df_sem_display["Giá Niêm Yết (VNĐ)"] = df_sem_display["Giá Niêm Yết (VNĐ)"].apply(lambda x: f"{x:,.0f}")
                df_sem_display["Độ Phù Hợp (%)"] = df_sem_display["Độ Phù Hợp (%)"].apply(lambda x: f"{x:.1f}%")

                st.dataframe(df_sem_display, use_container_width=True)

                st.session_state.history.insert(
                    0,
                    {
                        "Thời gian": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                        "Động cơ AI": "AI 2 (Semantic Search)",
                        "Câu hỏi": query_to_run,
                        "Chi tiết / Intent": ", ".join(matched_intents) if matched_intents else "Tương đồng Cosine",
                        "Số dòng": len(res["results"]),
                        "Thời gian (ms)": res.get("execution_time_ms", 1.0),
                        "Trạng thái": "Thành công",
                    },
                )

            # ======================= TRƯỜNG HỢP 3: NGOÀI PHẠM VI CẢ 2 =======================
            else:
                st.warning("Hệ thống không nhận diện được mẫu câu hỏi này.")
                st.markdown(
                    """
                    **Hệ thống hỗ trợ 2 nhóm câu hỏi chính:**
                    1. **Câu hỏi nghiệp vụ CSDL**:  Top 5 sản phẩm đắt nhất, Tìm linh kiện giá trên 5 triệu, Đơn hàng đã hủy, Doanh thu theo tháng...
                    2. **Câu hỏi tư vấn phần cứng**:  PC chơi game nặng, Cấu hình đồ họa render video, Máy tính văn phòng học tập, Mở nhiều tab đa nhiệm...
                    """
                )
                st.session_state.history.insert(
                    0,
                    {
                        "Thời gian": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                        "Động cơ AI": "Không xác định",
                        "Câu hỏi": query_to_run,
                        "Chi tiết / Intent": "UNKNOWN",
                        "Số dòng": 0,
                        "Thời gian (ms)": 0.0,
                        "Trạng thái": "Ngoài phạm vi",
                    },
                )


# ------------------------------------------------------------------------------
# TAB 3: AI 3 - GIÁM SÁT AN NINH ZERO-TRUST
# ------------------------------------------------------------------------------
with tab_ai3:
    st.markdown(section_header(
        "Giám sát an toàn truy vấn (Zero-Trust)",
        "Chấm điểm rủi ro 0–100 cho từng truy vấn theo cấu trúc SQL, bảng nhạy cảm, số dòng trích xuất, "
        "khung giờ, địa chỉ IP, tần suất và độ lệch so với thói quen của người dùng (Isolation Forest).",
        "Zero-Trust Sentinel"), unsafe_allow_html=True)

    # Chỉ số kiểm toán (đọc từ nhật ký thật, bỏ lịch sử mẫu dùng để huấn luyện)
    _aud_all = [r for r in read_audit_log(limit=5000) if r.get("source") != "seed_lich_su"]
    _aud_pass = sum(1 for r in _aud_all if r.get("allowed"))
    _aud_block = sum(1 for r in _aud_all if r.get("allowed") is False)
    _aud_scores = [float(r["score"]) for r in _aud_all if isinstance(r.get("score"), (int, float))]
    _k1, _k2, _k3, _k4 = st.columns(4)
    _k1.markdown(kpi_card("Tổng truy vấn kiểm tra", f"{len(_aud_all):,}", "Nhật ký kiểm toán thật"), unsafe_allow_html=True)
    _k2.markdown(kpi_card("Cho phép (Pass)", f"{_aud_pass:,}",
                          f"{(_aud_pass / len(_aud_all) * 100 if _aud_all else 0):.0f}% tổng số", "good"), unsafe_allow_html=True)
    _k3.markdown(kpi_card("Bị chặn (Blocked)", f"{_aud_block:,}",
                          f"{(_aud_block / len(_aud_all) * 100 if _aud_all else 0):.0f}% tổng số", "bad" if _aud_block else ""), unsafe_allow_html=True)
    _k4.markdown(kpi_card("Điểm rủi ro trung bình", f"{(sum(_aud_scores) / len(_aud_scores) if _aud_scores else 0):.1f}",
                          "0–100"), unsafe_allow_html=True)

    st.markdown(sub_header("Kịch bản kiểm tra"), unsafe_allow_html=True)
    sc_c1, sc_c2, sc_c3, sc_c4 = st.columns(4)
    with sc_c1:
        if st.button("Kịch bản 1: Truy vấn an toàn (Giờ hành chính)", key="sec_sc_1", use_container_width=True):
            st.session_state["sec_sql"] = "SELECT ten, gia_niem_yet FROM san_pham WHERE gia_niem_yet > 5000000 LIMIT 10;"
            st.session_state["sec_sql_field"] = st.session_state["sec_sql"]
            st.session_state["sec_ip"] = "127.0.0.1"
            st.session_state["sec_hour"] = 10
            st.session_state["sec_rows"] = 10
            st.session_state["sec_failed"] = 0
            st.session_state["sec_qps"] = 1.0
    with sc_c2:
        if st.button("Kịch bản 2: Nghi vấn trộm dữ liệu (Ban đêm)", key="sec_sc_2", use_container_width=True):
            st.session_state["sec_sql"] = "SELECT ho_ten, so_dien_thoai, email FROM khach_hang;"
            st.session_state["sec_sql_field"] = st.session_state["sec_sql"]
            st.session_state["sec_ip"] = "192.168.1.50"
            st.session_state["sec_hour"] = 2  # 2 giờ sáng
            st.session_state["sec_rows"] = 1500
            st.session_state["sec_failed"] = 1
            st.session_state["sec_qps"] = 2.0
    with sc_c3:
        if st.button("Kịch bản 3: Tấn công phá hoại SQL Injection", key="sec_sc_3", use_container_width=True):
            st.session_state["sec_sql"] = "SELECT * FROM don_hang; DROP TABLE san_pham; --"
            st.session_state["sec_sql_field"] = st.session_state["sec_sql"]
            st.session_state["sec_ip"] = "203.113.152.1"
            st.session_state["sec_hour"] = 15
            st.session_state["sec_rows"] = 50
            st.session_state["sec_failed"] = 3
            st.session_state["sec_qps"] = 4.0
    with sc_c4:
        if st.button("Kịch bản 4: Truy vấn dồn dập (QPS cao từ IP lạ)", key="sec_sc_4", use_container_width=True):
            st.session_state["sec_sql"] = "SELECT * FROM thanh_toan LIMIT 200;"
            st.session_state["sec_sql_field"] = st.session_state["sec_sql"]
            st.session_state["sec_ip"] = "118.69.182.4"
            st.session_state["sec_hour"] = 23
            st.session_state["sec_rows"] = 200
            st.session_state["sec_failed"] = 2
            st.session_state["sec_qps"] = 12.0

    st.markdown("<br>", unsafe_allow_html=True)

    col_sec_sql, col_sec_params = st.columns([3, 2])
    with col_sec_sql:
        # Ô SQL gắn với session_state qua key: nút kịch bản ghi thẳng vào key này nên ô luôn cập nhật
        if "sec_sql_field" not in st.session_state:
            st.session_state["sec_sql_field"] = st.session_state.get("sec_sql", "SELECT ho_ten, so_dien_thoai FROM khach_hang;")
        sec_sql_input = st.text_area(
            "Câu lệnh SQL cần kiểm tra an ninh:",
            height=130,
            key="sec_sql_field",
        )
        # admin / manager là tài khoản thật có hồ sơ thói quen (đủ lịch sử để tính z-score);
        # các role còn lại là tài khoản giả lập chưa có lịch sử
        sec_user_role = st.selectbox(
            "Role / Người dùng thực hiện:",
            ["admin", "manager", "analyst_readonly", "app_user", "sale_staff", "guest_external"],
            help="admin và manager có hồ sơ thói quen nên AI 3 tính được độ lệch z-score; các tài khoản khác chưa có lịch sử.",
        )

    with col_sec_params:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            sec_ip_val = st.text_input("Địa chỉ IP (MÔ PHỎNG):", value=st.session_state.get("sec_ip", "127.0.0.1"))
            sec_hour_val = st.slider("Khung giờ (0 - 23h):", 0, 23, st.session_state.get("sec_hour", datetime.now().hour))
            sec_rows_val = st.slider("Số dòng ước tính:", 1, 3000, st.session_state.get("sec_rows", 100))
        with col_p2:
            sec_failed_val = st.slider("Sai mật khẩu (MÔ PHỎNG):", 0, 5, st.session_state.get("sec_failed", 0))
            current_real_qps = rate_tracker.get_qps(st.session_state.get("session_id", "web_session"))
            sec_qps_val = st.slider("Tần suất truy vấn QPS (Đo thật: {:.1f}):".format(current_real_qps), 0.5, 20.0, float(st.session_state.get("sec_qps", 1.0)), step=0.5)

    if st.button("Chấm điểm rủi ro an ninh", type="primary"):
        with st.spinner("Đang phân tích các yếu tố an ninh thời gian thực..."):
            sec_eval = AISecurityGuard.evaluate_risk(
                sql_query=sec_sql_input,
                user=sec_user_role,
                ip_address=sec_ip_val,
                hour=sec_hour_val,
                estimated_rows=sec_rows_val,
                failed_logins=sec_failed_val,
                qps=sec_qps_val,
            )

        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("Điểm rủi ro (Risk Score)", f"{sec_eval['score']} / 100")
        col_r2.metric("Mức độ an ninh", sec_eval["level_label"])
        col_r3.metric("Quyết định", "CHO PHÉP" if sec_eval["allowed"] else "CHẶN THỰC THI")

        st.markdown("---")
        if sec_eval["allowed"]:
            st.info(f"Hành động kiểm soát tự động: **{sec_eval['action']}**")
        else:
            st.error(f"Hành động kiểm soát tự động: **{sec_eval['action']}**")

        st.markdown(sub_header("Các yếu tố rủi ro ghi nhận"), unsafe_allow_html=True)
        for factor in sec_eval["factors"]:
            st.markdown(f"- {factor}")

        anom = sec_eval.get("anomaly")
        if anom:
            with st.expander("Thành phần học máy: Phát hiện hành vi bất thường (Isolation Forest)", expanded=bool(anom.get("is_anomaly"))):
                a1, a2, a3 = st.columns(3)
                a1.metric("Điểm bất thường", f"{anom['anomaly_score']:.2f}", "NGOẠI LAI" if anom["is_anomaly"] else "bình thường")
                a2.metric("Lệch thói quen người dùng (z)", "chưa đủ lịch sử" if anom.get("user_zscore") is None else f"{anom['user_zscore']}")
                a3.metric(
                    "Mẫu đã học",
                    anom.get("trained_real_samples", 0) + anom.get("trained_seed_samples", 0),
                    f"{anom.get('trained_real_samples', 0)} thật · {anom.get('trained_seed_samples', 0)} lịch sử nạp",
                    delta_color="off",
                )
                st.caption("Mô hình học hành vi bình thường (giờ, số dòng, số bảng, LIMIT, QPS...) từ hồ sơ nền và nhật ký kiểm toán; tự huấn luyện lại sau mỗi 50 bản ghi mới.")

        if not sec_eval["allowed"] and sec_eval.get("recommended_dba_actions"):
            st.markdown("---")
            st.markdown(sub_header("Đề xuất thu hồi quyền (DBA thực thi)"), unsafe_allow_html=True)
            for dba_cmd in sec_eval["recommended_dba_actions"]:
                st.code(dba_cmd, language="sql")

    # Hiển thị nhật ký kiểm toán Audit Trail
    st.markdown("---")
    st.markdown(sub_header("Giám sát AI 1 (TEX2SQL) và AI 2 (Semantic Search)"), unsafe_allow_html=True)
    st.caption("Mọi câu hỏi ở tab Truy vấn đều được AI 3 chấm điểm trước khi chạy: AI 1 theo câu SQL sinh ra, AI 2 theo nội dung câu hỏi và độ phủ danh mục sản phẩm đã lấy trong phiên.")
    eng_stats = summarize_by_engine(limit=2000)
    mon_cols = st.columns(2)
    _in = eng_stats.get("Đầu vào", {"tong": 0, "canh_bao": 0, "chan": 0})
    st.caption(f"Chốt chặn đầu vào (đọc mọi câu hỏi trước khi định tuyến): {_in['chan']} câu bị chặn, {_in['canh_bao']} câu cảnh báo.")
    for _col, _eng, _title in [(mon_cols[0], "AI 1", "AI 1 · Text-to-SQL"), (mon_cols[1], "AI 2", "AI 2 · Semantic Search")]:
        _st = eng_stats.get(_eng, {"tong": 0, "canh_bao": 0, "chan": 0})
        with _col:
            st.markdown(f"**{_title}**")
            c_a, c_b, c_c = st.columns(3)
            c_a.metric("Yêu cầu", _st["tong"])
            c_b.metric("Cảnh báo", _st["canh_bao"])
            c_c.metric("Bị chặn", _st["chan"])
    _sid = st.session_state.get("session_id", "web_session")
    _cat = len(getattr(get_engine(), "products", []) or [])
    if _cat:
        st.caption(f"Độ phủ danh mục phiên hiện tại (AI 2): {coverage_tracker.seen_count(_sid)}/{_cat} sản phẩm "
                   f"({coverage_tracker.coverage(_sid, _cat):.0%}). Cảnh báo từ 30%, chặn khi kết hợp thêm yếu tố khác.")

    # ---------------- DỮ LIỆU HUẤN LUYỆN MÔ HÌNH HỌC MÁY (đọc từ nhật ký -> còn nguyên sau F5) ----------------
    st.markdown(sub_header("Dữ liệu huấn luyện mô hình phát hiện bất thường"), unsafe_allow_html=True)
    from app.audit_seeder import training_data_stats, seed_history, remove_seeded_history
    from app.ai_anomaly_detector import BASELINE_SAMPLES, get_anomaly_detector

    # Thông báo của lần nạp/xóa trước (giữ qua lần chạy lại ngay sau khi bấm nút)
    _seed_msg = st.session_state.pop("seed_msg", None)
    if _seed_msg:
        (st.success if _seed_msg[0] == "ok" else st.error)(_seed_msg[1])

    _ts = training_data_stats()
    _det = get_anomaly_detector()
    try:
        _det.ensure_trained()
    except Exception:
        pass
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Lịch sử nạp", f"{_ts['seeded']:,} bản ghi")
    t2.metric("Dữ liệu thật", f"{_ts['real']:,} bản ghi")
    t3.metric("Người dùng đủ hồ sơ", f"{_ts['users_with_profile']}/{len(_ts['users'])}")
    t4.metric("Mô hình đang học", f"{_det.n_real_samples + _det.n_seed_samples:,} mẫu",
              f"+ {BASELINE_SAMPLES} mẫu nền", delta_color="off")
    if _ts["date_from"]:
        st.caption(f"Khoảng thời gian dữ liệu: {_ts['date_from']} → {_ts['date_to']}. ")

    if _ts["total_usable"]:
        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown("**Số truy vấn bình thường theo ngày**")
            if _ts["per_day"]:
                st.bar_chart(pd.DataFrame(_ts["per_day"]).set_index("Ngày"), height=220)
        with g2:
            st.markdown("**Hồ sơ hành vi từng người dùng**")
            st.dataframe(pd.DataFrame(_ts["users"]), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu huấn luyện. Bấm «Nạp lịch sử mẫu» để mô hình có dữ liệu học.")

    _sd1, _sd2, _sd3 = st.columns([2, 1, 1])
    with _sd1:
        _n_seed = st.select_slider("Số bản ghi lịch sử", options=[200, 400, 600, 1000], value=600, key="seed_n")
    with _sd2:
        if st.button("Nạp lịch sử mẫu", key="seed_btn", use_container_width=True, disabled=not is_admin(st.session_state)):
            with st.spinner("Đang mô phỏng lịch sử truy vấn và huấn luyện lại mô hình..."):
                _res = seed_history(n_records=int(_n_seed))
            if _res.get("success"):
                st.session_state["seed_msg"] = ("ok",
                    f"Đã nạp {_res['written']} bản ghi (AI 1: {_res['by_engine']['AI 1']}, AI 2: {_res['by_engine']['AI 2']}), "
                    f"thay thế {_res.get('replaced_old', 0)} bản ghi mẫu cũ. Bỏ qua {_res['skipped_not_normal']} câu không bình thường. "
                    f"{'Số dòng lấy từ EXPLAIN thật.' if _res['used_db_explain'] else 'Không kết nối được CSDL, số dòng suy từ LIMIT.'}")
            else:
                st.session_state["seed_msg"] = ("err", _res.get("error", "Nạp thất bại."))
            st.rerun()
    with _sd3:
        if st.button("Xóa lịch sử mẫu", key="seed_rm_btn", use_container_width=True, disabled=not is_admin(st.session_state)):
            st.session_state["seed_msg"] = ("ok", f"Đã xóa {remove_seeded_history()} bản ghi lịch sử mẫu.")
            st.rerun()

    st.markdown(sub_header("Nhật ký kiểm toán (Audit Trail)"), unsafe_allow_html=True)
    log_filter = st.radio("Lọc theo nguồn:", ["Tất cả", "Đầu vào", "AI 1", "AI 2", "Lệnh SQL"], horizontal=True, key="audit_engine_filter")
    recent_logs = [r for r in read_audit_log(limit=2000) if r.get("source") != "seed_lich_su"]
    if log_filter == "Đầu vào":
        recent_logs = [r for r in recent_logs if r.get("stage") == "Đầu vào" or r.get("engine") == "Đầu vào"]
    elif log_filter == "AI 1":
        recent_logs = [r for r in recent_logs if r.get("engine") == "AI 1"]
    elif log_filter == "AI 2":
        recent_logs = [r for r in recent_logs if r.get("engine") == "AI 2"]
    elif log_filter == "Lệnh SQL":
        recent_logs = [r for r in recent_logs if r.get("engine") not in ("AI 1", "AI 2", "Đầu vào") and r.get("stage") != "Đầu vào"]
    recent_logs = recent_logs[:30]
    if recent_logs:
        df_logs = pd.DataFrame(recent_logs)
        # Bản ghi nhật ký cũ có thể thiếu các cột mới -> bổ sung để không lỗi KeyError
        for _c in ("engine", "stage", "question"):
            if _c not in df_logs.columns:
                df_logs[_c] = None
        df_logs["engine"] = df_logs["engine"].fillna("Lệnh SQL (cũ)")
        # Bản ghi cũ (trước khi có cột stage) ghi engine = "Đầu vào"
        _old = df_logs["engine"] == "Đầu vào"
        df_logs.loc[_old, "stage"] = "Đầu vào"
        df_logs["stage"] = df_logs["stage"].fillna("Thực thi")
        show_cols = [c for c in ["timestamp", "engine", "stage", "user", "question", "sql", "score", "status", "allowed", "factors"] if c in df_logs.columns]
        df_show = df_logs[show_cols].copy()
        if "factors" in df_show.columns:
            df_show["factors"] = df_show["factors"].apply(lambda v: "; ".join(map(str, v)) if isinstance(v, list) else (v or ""))
        if "allowed" in df_show.columns:
            df_show["allowed"] = df_show["allowed"].map({True: "Cho phép", False: "Chặn"}).fillna("")
        df_show = df_show.rename(columns={
            "timestamp": "Thời điểm", "engine": "Nguồn", "stage": "Giai đoạn", "user": "Người dùng",
            "question": "Câu hỏi", "sql": "SQL", "score": "Điểm rủi ro", "status": "Mức", "allowed": "Quyết định",
            "factors": "Yếu tố",
        })

        def _hl_blocked(row):
            # Dòng bị chặn tô nền đỏ nhạt, dòng cảnh báo tô vàng nhạt (không chớp nháy)
            if row.get("Quyết định") == "Chặn":
                return ["background-color: #fef2f2; color: #7f1d1d"] * len(row)
            if str(row.get("Mức", "")).upper() == "WARNING":
                return ["background-color: #fffbeb; color: #78350f"] * len(row)
            return [""] * len(row)

        st.dataframe(df_show.style.apply(_hl_blocked, axis=1), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có bản ghi nhật ký an ninh nào cho bộ lọc này.")


# ------------------------------------------------------------------------------
# TAB 4: AI 4 - CỐ VẤN LẬP CHỈ MỤC (INDEX ADVISOR)
# ------------------------------------------------------------------------------
with tab_ai4:
    st.markdown(section_header(
        "Khuyến nghị tối ưu hiệu năng: chỉ mục",
        "Phân tích kế hoạch thực thi (EXPLAIN FORMAT JSON) theo bộ luật để tìm nút quét tuần tự tốn kém, "
        "đề xuất đúng loại chỉ mục (B-Tree, Partial, GIN pg_trgm, JSONB) và đo chi phí trước/sau bằng HypoPG nếu máy chủ có cài.",
        "Index Advisor"), unsafe_allow_html=True)

    st.markdown(sub_header("Chọn truy vấn cần thẩm định"), unsafe_allow_html=True)
    idx_col1, idx_col2, idx_col3 = st.columns(3)
    with idx_col1:
        if st.button("Truy vấn 1: Lọc khoảng giá sản phẩm", key="idx_btn_1", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT id, ten, gia_niem_yet FROM san_pham WHERE gia_niem_yet > 10000000;"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]
    with idx_col2:
        if st.button("Truy vấn 2: Lọc đơn hàng theo khách hàng", key="idx_btn_2", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT * FROM don_hang WHERE khach_hang_id = 150;"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]
    with idx_col3:
        if st.button("Truy vấn 3: Tổng hợp đơn hàng theo trạng thái", key="idx_btn_3", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT trang_thai, COUNT(*) FROM don_hang GROUP BY trang_thai;"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]

    idx_col4, idx_col5, idx_col6 = st.columns(3)
    with idx_col4:
        if st.button("Truy vấn 4: Đơn hoàn thành giá trị lớn (Partial Index)", key="idx_btn_4", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT id, ngay_dat FROM don_hang WHERE trang_thai = 'hoan_thanh' AND tong_tien > 50000000;"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]
    with idx_col5:
        if st.button("Truy vấn 5: Tìm tên chứa 'rtx' (GIN pg_trgm)", key="idx_btn_5", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT id, ten FROM san_pham WHERE ten ILIKE '%rtx%';"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]
    with idx_col6:
        if st.button("Truy vấn 6: Lọc thông số JSONB socket", key="idx_btn_6", use_container_width=True):
            st.session_state["idx_sql"] = "SELECT id, ten FROM san_pham WHERE thong_so_ky_thuat->>'socket' = 'AM5';"
            st.session_state["idx_sql_field"] = st.session_state["idx_sql"]

    st.markdown("<br>", unsafe_allow_html=True)

    # Ô SQL gắn với session_state qua key: nút mẫu ghi thẳng vào key này nên ô luôn cập nhật
    if "idx_sql_field" not in st.session_state:
        st.session_state["idx_sql_field"] = st.session_state.get("idx_sql", "SELECT id, ten, gia_niem_yet FROM san_pham WHERE gia_niem_yet > 10000000;")
    idx_sql_input = st.text_area(
        "Câu lệnh SQL cần phân tích kế hoạch thực thi (EXPLAIN):",
        height=100,
        key="idx_sql_field",
    )

    if st.button("Phân tích kế hoạch thực thi", type="primary"):
        if not idx_sql_input.strip():
            st.warning("Vui lòng nhập câu lệnh SQL trước khi phân tích.")
        else:
            with st.spinner("Đang chạy EXPLAIN (FORMAT JSON, COSTS TRUE) trên PostgreSQL..."):
                idx_analysis = AIIndexAdvisor.analyze_query(idx_sql_input)

            if not idx_analysis.get("success"):
                st.error(f"Lỗi: {idx_analysis.get('error')}")
            else:
                m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                m_c1.metric("Chi phí ước tính (Cost)", f"{idx_analysis['root_cost']:.2f}")
                m_c2.metric("Số dòng kế hoạch", f"{idx_analysis['root_rows']:,}")
                m_c3.metric("Số nút Seq Scan", idx_analysis["seq_scans_count"])
                m_c4.metric("Số đề xuất Index", len(idx_analysis["recommendations"]))

                st.markdown("---")
                st.markdown(f"Kết luận: **{idx_analysis['status']}**")

                if idx_analysis["needs_index"] and idx_analysis["recommendations"]:
                    st.warning("Phát hiện nút quét tuần tự cần tối ưu. Đề xuất:")
                    _rec_rows = []
                    for _r in idx_analysis["recommendations"]:
                        _ev = _r.get("evidence", {})
                        _rec_rows.append({
                            "Bảng dữ liệu": _r["table"],
                            "Cột đề xuất": ", ".join(_r.get("recommended_columns", [])),
                            "Loại chỉ mục": _r.get("index_type", "B-Tree"),
                            "Chi phí trước": f"{_ev['cost_before']:.1f}" if _ev.get("measured") else f"{_r['current_cost']:.1f}",
                            "Chi phí sau": f"{_ev['cost_after']:.1f}" if _ev.get("measured") else "chưa đo (cần HypoPG)",
                            "Lệnh CREATE INDEX": _r["recommended_sql"],
                        })
                    st.dataframe(pd.DataFrame(_rec_rows), use_container_width=True, hide_index=True)
                    for rec in idx_analysis["recommendations"]:
                        cols_str = ", ".join(rec.get("recommended_columns", []))
                        st.markdown(
                            f"""
                            - **Bảng mục tiêu:** `{rec['table']}` | **Cột đề xuất:** `{cols_str}`
                            - **Chi phí hiện tại:** `{rec['current_cost']:.1f}` | **Điều kiện:** `{rec['filter_condition']}`
                            - **Lý do đề xuất:** {rec['reason']}
                            """
                        )
                        st.markdown(f"**Loại chỉ mục:** `{rec.get('index_type', 'B-Tree')}`")
                        ev = rec.get("evidence", {})
                        if ev.get("measured"):
                            e1, e2, e3 = st.columns(3)
                            e1.metric("Chi phí trước", f"{ev['cost_before']:.1f}")
                            e2.metric("Chi phí sau (HypoPG)", f"{ev['cost_after']:.1f}")
                            e3.metric("Cải thiện", f"{ev.get('improvement_percent', 0)}%")
                        elif ev.get("note"):
                            st.caption(f"Đo lường: {ev['note']}")
                        st.markdown("**Lệnh đề xuất** (nút sao chép ở góc phải khối mã):")
                        st.code(rec["recommended_sql"], language="sql")
                        st.caption(f"Ghi chú DBA: {rec.get('ddl_note', '')}")
                else:
                    st.success("Kế hoạch thực thi đã tối ưu: không có nút quét tuần tự cần xử lý hoặc bảng đã có chỉ mục phù hợp.")

                # Hiển thị bảng bỏ qua (Skipped Tables) minh bạch lý do
                if idx_analysis.get("skipped"):
                    with st.expander("Các bảng quét tuần tự được giữ nguyên và lý do"):
                        for item in idx_analysis["skipped"]:
                            st.markdown(f"- **`{item['table']}`** (`{item['reason_code']}`): {item['explanation']}")

                with st.expander("Cây kế hoạch JSON từ PostgreSQL"):
                    st.json(idx_analysis.get("raw_plan", {}))

    st.markdown("---")
    st.markdown(sub_header("Phân tích khối lượng công việc thật (pg_stat_statements)"), unsafe_allow_html=True)
    st.caption("Lấy các truy vấn tốn tổng thời gian nhiều nhất trên máy chủ rồi chạy cố vấn chỉ mục cho từng câu.")
    if st.button("Phân tích top 5 truy vấn nặng nhất", key="idx_workload_btn"):
        with st.spinner("Đang đọc pg_stat_statements..."):
            wl = AIIndexAdvisor.analyze_workload(top_n=5)
        if not wl.get("success"):
            st.warning(wl.get("error"))
        else:
            for item in wl["workload"]:
                ana = item.get("analysis") or {}
                n_rec = len(ana.get("recommendations", [])) if ana.get("success") else 0
                with st.expander(f"{item['total_ms']} ms tổng | {item['calls']} lần gọi | {n_rec} đề xuất — {str(item['query'])[:90]}"):
                    st.code(item["query"], language="sql")
                    if item.get("note"):
                        st.caption(item["note"])
                    for rec in ana.get("recommendations", []) if ana.get("success") else []:
                        st.markdown(f"`{rec.get('index_type')}` trên `{rec['table']}`")
                        st.code(rec["recommended_sql"], language="sql")


# ------------------------------------------------------------------------------
# TAB 5: AI 5 - DỰ BÁO PHÂN VÙNG (PREDICTIVE PARTITIONING)
# ------------------------------------------------------------------------------
with tab_ai5:
    st.markdown(section_header(
        "Quy hoạch lưu trữ: phân vùng bảng đơn hàng",
        "Dự báo số đơn theo tháng (so sánh OLS, Holt và baseline bằng backtest), ước tính thời điểm chạm ngưỡng "
        "dung lượng và sinh kế hoạch chuyển bảng don_hang sang phân vùng theo tháng.",
        "Partitioning Planner"), unsafe_allow_html=True)

    with st.expander("Kịch bản giả sử (What-if): tăng trưởng mạnh hơn hoặc hạ ngưỡng phân vùng", expanded=True):
        wi_c1, wi_c2 = st.columns(2)
        with wi_c1:
            wi_growth = st.select_slider("Hệ số tăng trưởng đơn hàng", options=[1, 2, 5, 10, 50, 100, 500], value=1)
        with wi_c2:
            wi_rows = st.select_slider("Ngưỡng phân vùng (số đơn)", options=[10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000], value=1_000_000)

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_partition_forecast(growth: float, thr_rows: int):
        return AIPredictivePartitioningEngine.analyze_and_forecast(growth_multiplier=growth, threshold_rows=thr_rows)

    with st.spinner("Đang phân tích dữ liệu lịch sử và so sánh các mô hình dự báo..."):
        part_data = _cached_partition_forecast(float(wi_growth), int(wi_rows))

    if not part_data.get("success"):
        st.error(f"Lỗi: {part_data.get('error')}")
    else:
        # ---------------- KẾT QUẢ KỊCH BẢN GIẢ SỬ (so với hiện trạng) ----------------
        base_data = _cached_partition_forecast(1.0, 1_000_000)

        def _days_txt(d):
            return d if isinstance(d, str) else f"{d:,.0f} ngày"

        def _avg_fc(d):
            fcs = d.get("forecast_months", [])
            return sum(f["don_du_bao"] for f in fcs) / len(fcs) if fcs else 0

        cap = part_data["capacity_assessment"]
        base_cap = base_data.get("capacity_assessment", {}) if base_data.get("success") else {}
        st.markdown(sub_header("Kết quả kịch bản"), unsafe_allow_html=True)
        k1, k2, k3 = st.columns(3)
        avg_now, avg_base = _avg_fc(part_data), _avg_fc(base_data) if base_data.get("success") else 0
        k1.metric(
            "Đơn dự báo / tháng",
            f"{avg_now:,.0f}",
            f"x{wi_growth} so với hiện trạng ({avg_base:,.0f})" if wi_growth != 1 else "hiện trạng",
        )
        k2.metric(
            f"Thời gian chạm ngưỡng {cap['threshold_rows']:,} đơn",
            _days_txt(cap["days_until_threshold"]),
            f"hiện trạng: {_days_txt(base_cap.get('days_until_threshold', '—'))}" if (wi_growth != 1 or wi_rows != 1_000_000) else None,
            delta_color="off",
        )
        k3.metric("Quyết định", {"PARTITION_SOON": "PHÂN VÙNG NGAY", "MONITOR": "THEO DÕI", "NOT_NEEDED": "CHƯA CẦN"}.get(cap["recommendation"], cap["recommendation"]))
        _msg = f"**{cap['rec_label']}** — ước tính chạm ngưỡng: {_days_txt(cap['days_until_threshold'])}."
        if cap["recommendation"] == "PARTITION_SOON":
            st.error(_msg + " Nên chạy kế hoạch di chuyển bên dưới.")
        elif cap["recommendation"] == "MONITOR":
            st.warning(_msg + " Chuẩn bị kế hoạch phân vùng và theo dõi hằng tháng.")
        else:
            st.success(_msg)
        st.markdown("---")

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Tổng đơn hàng lịch sử", f"{part_data['total_orders']:,} đơn")
        p2.metric("Dung lượng Cluster CSDL", f"{part_data['cluster_size_mb']} MB")
        p3.metric("Byte TB / Đơn hàng", f"{part_data['bytes_per_order']:.1f} B")
        p4.metric("Độ tin cậy hồi quy (R²)", f"{part_data['model_metrics']['r_squared']:.3f}")

        st.caption(part_data["model_metrics"].get("r_squared_note", ""))
        if part_data["model_metrics"].get("model_comparison"):
            st.markdown(sub_header(f"So sánh mô hình bằng backtest ({part_data['model_metrics'].get('backtest_months')} tháng cuối) · chọn {part_data['model_metrics']['best_model']}"), unsafe_allow_html=True)
            _cmp = pd.DataFrame(part_data["model_metrics"]["model_comparison"]).T
            _cmp.index = _cmp.index.map({"OLS": "Hồi quy tuyến tính (OLS)", "HOLT": "Làm trơn hàm mũ Holt", "NAIVE": "Baseline trung bình 3 tháng"})
            st.dataframe(_cmp.rename(columns={"mae": "MAE", "rmse": "RMSE", "mape": "MAPE (%)"}), use_container_width=True)
        dq = part_data.get("data_quality", {})
        if dq.get("empty_months_filled"):
            st.caption(f"Đã lấp {len(dq['empty_months_filled'])} tháng không có đơn bằng 0: {', '.join(dq['empty_months_filled'])}")
        st.info(f"Đối chứng mô hình: Backtest MAE = {part_data['model_metrics']['backtest_mae']} đơn (Baseline 3 tháng = {part_data['model_metrics']['baseline_mae']} đơn). Đánh giá: {'Mô hình vượt trội hơn Baseline' if part_data['model_metrics']['beats_baseline'] else 'Cần thêm thời gian theo dõi'}.")

        st.markdown("---")

        col_fc_table, col_fc_ddl = st.columns([1, 1])

        with col_fc_table:
            st.markdown(sub_header("Dự báo 3 tháng tiếp theo"), unsafe_allow_html=True)
            df_fc = pd.DataFrame(part_data["forecast_months"])
            df_fc.rename(
                columns={
                    "thang": "Tháng Dự Báo",
                    "don_du_bao": "Dự Báo Số Đơn",
                    "khoang_tin_cay_95": "Khoảng Tin Cậy 95%",
                },
                inplace=True,
            )
            st.dataframe(df_fc[["Tháng Dự Báo", "Dự Báo Số Đơn", "Khoảng Tin Cậy 95%"]], use_container_width=True)

        with col_fc_ddl:
            st.markdown(sub_header("Kế hoạch chuyển đổi và DDL phân vùng"), unsafe_allow_html=True)
            if part_data.get("is_partitioned"):
                st.markdown("Bảng `don_hang` đã ở trạng thái phân vùng. Các lệnh tạo partition mới:")
                for ddl_stmt in part_data.get("generated_ddl", []):
                    st.code(ddl_stmt, language="sql")
            else:
                st.markdown("Bảng `don_hang` hiện là bảng chuẩn (chưa phân vùng). Kế hoạch di chuyển 5 bước an toàn:")
                for step in part_data.get("migration_plan", []):
                    st.markdown(f"**Bước {step['step']}: {step['title']}**")
                    st.code(step["sql"], language="sql")
                    st.caption(step["note"])

    # ---------------- THỰC HIỆN PHÂN VÙNG TRÊN BẢN SAO MINH HỌA ----------------
    from app import partition_demo

    @st.cache_data(ttl=300, show_spinner=False)
    def _c_part_status():
        return partition_demo.copy_status()

    @st.cache_data(ttl=300, show_spinner=False)
    def _c_part_months():
        return partition_demo.available_months()

    st.markdown(sub_header("Thực hiện phân vùng"), unsafe_allow_html=True)
    st.caption(
        "Tạo bảng don_hang_phan_vung theo đúng kế hoạch ở trên (mỗi tháng 1 phân vùng + 3 tháng tới + phân vùng DEFAULT), "
        "chép toàn bộ đơn hàng sang rồi so sánh truy vấn với bảng gốc. Bảng don_hang thật, khóa ngoại, trigger và RLS "
        "giữ nguyên; bản sao chỉ tài khoản quản trị CSDL đọc được."
    )
    _pmsg = st.session_state.pop("part_demo_msg", None)
    if _pmsg:
        (st.success if _pmsg[0] == "ok" else st.error)(_pmsg[1])

    _pst = _c_part_status()
    _pb1, _pb2, _ = st.columns([1.4, 1.1, 3])
    if is_admin(st.session_state):
        with _pb1:
            if st.button("Tạo lại bản sao phân vùng" if _pst.get("exists") else "Thực hiện phân vùng",
                         type="primary", use_container_width=True, key="part_demo_create"):
                with st.spinner("Đang tạo bảng phân vùng và chép dữ liệu (1 giao dịch, lỗi sẽ tự hoàn tác)..."):
                    _pr = partition_demo.create_partitioned_copy()
                if _pr.get("success"):
                    st.session_state["part_demo_msg"] = ("ok",
                        f"Đã phân vùng: chép {_pr['copied_rows']:,}/{_pr['source_rows']:,} đơn vào {_pr['partitions']} phân vùng ({_pr['range']}).")
                    st.session_state["part_demo_ddl"] = _pr.get("ddl", "")
                else:
                    st.session_state["part_demo_msg"] = ("err", _pr.get("error", "Không tạo được bản sao."))
                _c_part_status.clear()
                st.rerun()
        with _pb2:
            if _pst.get("exists") and st.button("Xóa bản sao", use_container_width=True, key="part_demo_drop"):
                _dr = partition_demo.drop_partitioned_copy()
                st.session_state["part_demo_msg"] = ("ok", "Đã xóa bảng don_hang_phan_vung và các phân vùng.") if _dr.get("success") \
                    else ("err", _dr.get("error", "Không xóa được."))
                st.session_state.pop("part_demo_ddl", None)
                _c_part_status.clear()
                st.rerun()
    else:
        st.info("Vai trò Manager chỉ được xem. Thực hiện phân vùng dành cho Admin.")

    if not _pst.get("success"):
        st.warning(f"Không đọc được trạng thái bản sao: {_pst.get('error')}")
    elif _pst.get("exists"):
        _parts = _pst["partitions"]
        _monthly = [p for p in _parts if p["khoang"] != "DEFAULT"]
        _with_rows = [p for p in _monthly if p["so_dong"] > 0]
        _q1, _q2, _q3 = st.columns(3)
        _q1.markdown(kpi_card("Số phân vùng", f"{len(_parts)}", f"{len(_monthly)} theo tháng + 1 DEFAULT"), unsafe_allow_html=True)
        _q2.markdown(kpi_card("Số đơn trong bảng phân vùng", f"{_pst['total_rows']:,}", "Chép từ bảng don_hang", "good"),
                     unsafe_allow_html=True)
        _q3.markdown(kpi_card("Phân vùng đang có dữ liệu", f"{len(_with_rows)}",
                              f"{len(_monthly) - len(_with_rows)} phân vùng trống chờ tháng mới"), unsafe_allow_html=True)

        _df_parts = pd.DataFrame([{"Tháng": p["phan_vung"].rsplit("_y", 1)[-1].replace("m", "-"), "Số đơn": p["so_dong"]}
                                  for p in _monthly]).set_index("Tháng")
        st.markdown("**Số đơn trong từng phân vùng**")
        st.bar_chart(_df_parts, color=CHART_BLUE, height=220)
        with st.expander("Danh sách phân vùng và khoảng giá trị"):
            st.dataframe(pd.DataFrame([{"Phân vùng": p["phan_vung"], "Khoảng ngày_đặt": p["khoang"], "Số đơn": p["so_dong"],
                                        "Dung lượng": smart_backup_engine.format_size(p["bytes"])} for p in _parts]),
                         use_container_width=True, hide_index=True)
        if st.session_state.get("part_demo_ddl"):
            with st.expander("Các lệnh DDL vừa thực thi"):
                st.code(st.session_state["part_demo_ddl"], language="sql")

        # So sánh truy vấn 1 tháng: bảng gốc vs bảng phân vùng (partition pruning)
        st.markdown("**So sánh truy vấn doanh thu 1 tháng: bảng gốc và bảng phân vùng**")
        _months = _c_part_months()
        _cm1, _cm2 = st.columns([2, 1])
        with _cm1:
            _msel = st.selectbox("Tháng cần truy vấn", _months, index=min(4, len(_months) - 1) if _months else 0,
                                 key="part_demo_month", label_visibility="collapsed")
        with _cm2:
            _do_cmp = st.button("Chạy so sánh (EXPLAIN ANALYZE)", use_container_width=True, key="part_demo_cmp")
        if _do_cmp and _msel:
            _y, _m = map(int, _msel.split("-"))
            st.session_state["part_demo_cmp_res"] = partition_demo.compare_month_query(_y, _m)
        _cmp = st.session_state.get("part_demo_cmp_res")
        if _cmp and not _cmp.get("success"):
            st.error(_cmp.get("error"))
        elif _cmp:
            _l, _r = st.columns(2)
            for _col, _key, _title in ((_l, "goc", "Bảng gốc don_hang"), (_r, "phan_vung", "Bảng phân vùng don_hang_phan_vung")):
                _d = _cmp[_key]
                with _col:
                    st.markdown(f"**{_title}** · tháng {_cmp['month']}")
                    _m1, _m2 = st.columns(2)
                    _m1.metric("Chi phí ước tính", f"{_d['cost']}")
                    _m2.metric("Thời gian thực thi", f"{_d['time_ms']} ms")
                    st.caption("Bảng / phân vùng được quét: " + ", ".join(_d["scanned"]))
                    st.code(_d["sql"], language="sql")
            _n_scan = len(_cmp["phan_vung"]["scanned"])
            _same = "giống hệt" if _cmp.get("same_result") else "KHÁC NHAU"
            st.info(
                f"Partition pruning: bảng phân vùng chỉ quét {_n_scan}/{len(_parts)} phân vùng của tháng {_cmp['month']} "
                f"thay vì toàn bộ bảng. Kết quả hai bảng {_same}: {_cmp['goc']['so_don']:,} đơn, "
                f"{_cmp['goc']['doanh_thu']:,.0f} VNĐ."
            )



# ------------------------------------------------------------------------------
# TAB 5: AI 6 - BACKUP DỮ LIỆU THÔNG MINH (AI SMART BACKUP & RECOVERY)
# ------------------------------------------------------------------------------
with tab_ai6:
    st.markdown(section_header(
        "Quản trị sao lưu và phục hồi",
        "Phân loại bảng theo tốc độ thay đổi để đặt tần suất backup, chấm điểm rủi ro mất dữ liệu 0–100 từ số liệu thật, "
        "dự báo dung lượng và kiểm tra toàn vẹn từng bản backup bằng SHA-256.",
        "Backup Intelligence"), unsafe_allow_html=True)

    # 1. PHÂN TÍCH TẦN SUẤT THAY ĐỔI DỮ LIỆU (CHANGE RATE ANALYSIS)
    st.markdown(sub_header("1. Tốc độ thay đổi theo bảng (HOT / WARM / COLD)"), unsafe_allow_html=True)
    cr_data = _c_change_rate()

    if cr_data.get("success"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng số bảng giám sát", f"{len(cr_data.get('tables', []))} bảng")
        c2.metric("Bảng HOT (> 50%)", f"{cr_data.get('hot_count', 0)} bảng (1 giờ)")
        c3.metric("Bảng WARM (20-50%)", f"{cr_data.get('warm_count', 0)} bảng (6 giờ)")
        c4.metric("Bảng COLD (< 20%)", f"{cr_data.get('cold_count', 0)} bảng (24 giờ)")

        df_cr = pd.DataFrame(cr_data.get("tables", []))
        if not df_cr.empty:
            df_cr_display = df_cr[[
                "bang", "insert", "update", "delete", "tong_thay_doi", "so_dong_hien_tai", "change_rate_pct", "phan_loai", "tan_suat_backup"
            ]].copy()
            df_cr_display.rename(
                columns={
                    "bang": "Tên Bảng",
                    "insert": "Dòng INSERT",
                    "update": "Dòng UPDATE",
                    "delete": "Dòng DELETE",
                    "tong_thay_doi": "Tổng Biến Động",
                    "so_dong_hien_tai": "Dòng Hiện Tại",
                    "change_rate_pct": "Tỷ Lệ Đổi (%)",
                    "phan_loai": "Phân Loại Nhiệt",
                    "tan_suat_backup": "Tần Suất Đề Xuất",
                },
                inplace=True,
            )
            st.dataframe(df_cr_display, use_container_width=True)
    else:
        st.error(f"Lỗi phân tích Change Rate: {cr_data.get('error')}")

    st.markdown("---")

    # 2. ĐÁNH GIÁ RỦI RO MẤT DỮ LIỆU (DATA LOSS RISK SCORING) & DỰ BÁO DUNG LƯỢNG (OLS)
    col_risk, col_forecast = st.columns([1, 1])

    with col_risk:
        st.markdown(sub_header("2. Rủi ro mất dữ liệu (0–100)"), unsafe_allow_html=True)
        
        use_real_env = st.toggle("Dùng số liệu đo thật từ hệ thống", value=True,
                                 help="Đọc lần backup gần nhất, checksum, archive_mode, pg_stat_archiver, dung lượng ổ đĩa thật. Tắt để dùng tham số mô phỏng bên dưới.")
        # Mô phỏng các tham số môi trường
        with st.expander("Tùy chỉnh tham số mô phỏng rủi ro", expanded=False):
            sim_hours = st.slider("Số giờ kể từ lần backup cuối:", 1, 72, 18)
            sim_offsite = st.checkbox("Đã cấu hình backup Offsite / Remote", value=False)
            sim_verified = st.checkbox("Đã kiểm tra toàn vẹn Checksum SHA-256", value=True)
            sim_disk_free = st.slider("Dung lượng ổ đĩa trống (%):", 5, 95, 75)
            sim_wal = st.checkbox("Bật chế độ ghi nhật ký WAL (archive_mode)", value=True)

        risk_res = _c_risk(
            last_backup_hours_ago=float(sim_hours),
            has_offsite=sim_offsite,
            verified=sim_verified,
            disk_free_pct=float(sim_disk_free),
            archive_mode_on=sim_wal,
            use_real=use_real_env,
        )
        if use_real_env and risk_res.get("environment", {}).get("sources"):
            with st.expander("Nguồn số liệu thật đã dùng"):
                for k, v in risk_res["environment"]["sources"].items():
                    st.caption(f"{k}: {v}")

        _env = risk_res.get("environment") or {}
        if use_real_env and _env.get("disk_free_pct") is not None:
            _used = 100.0 - float(_env["disk_free_pct"])
            st.markdown("**Ổ đĩa chứa thư mục backup**")
            st.markdown(meter(_used, f"Đã dùng {_used:.1f}% · còn trống {_env['disk_free_pct']}%"), unsafe_allow_html=True)

        r_score = risk_res["risk_score"]
        r_level = risk_res["risk_level"]
        r_color = risk_res["badge_color"]

        st.metric("Điểm rủi ro (Risk Score)", f"{r_score} / 100", f"Mức: {r_level}")
        st.progress(min(1.0, r_score / 100.0))

        if r_level == "NGUY HIỂM":
            st.error(f"Khuyến nghị hành động: {risk_res['action']}")
        elif r_level == "CẢNH BÁO":
            st.warning(f"Khuyến nghị hành động: {risk_res['action']}")
        else:
            st.success(f"Khuyến nghị hành động: {risk_res['action']}")

        st.caption("**Các yếu tố đóng góp vào rủi ro:**")
        for f in risk_res.get("factors", []):
            st.write(f"• {f}")

    with col_forecast:
        st.markdown(sub_header("3. Dự báo dung lượng CSDL (hồi quy OLS)"), unsafe_allow_html=True)
        fc_data = _c_forecast_size()

        if fc_data.get("success"):
            st.metric("Dung lượng hiện tại", f"{fc_data.get('current_size_mb', 0)} MB")
            
            # Biểu đồ đường dự báo
            hist_list = fc_data.get("history", [])
            chart_df = pd.DataFrame(hist_list)
            if not chart_df.empty:
                chart_df.rename(columns={"ngay_ghi": "Thời gian", "db_size_mb": "Dung lượng (MB)"}, inplace=True)
                st.line_chart(chart_df.set_index("Thời gian")["Dung lượng (MB)"], color=CHART_BLUE)

            st.caption(f"Hệ số tăng trưởng OLS: `{fc_data.get('slope_mb_per_day', fc_data.get('slope_mb_per_step'))} MB/ngày` (Độ khớp $R^2$: `{fc_data.get('r_squared')}`)")

            # Thẻ dự báo 30 - 60 - 90 ngày
            f_cols = st.columns(3)
            for i, f_item in enumerate(fc_data.get("forecasts", [])):
                with f_cols[i]:
                    st.metric(
                        f"Sau {f_item['days']} ngày",
                        f"{f_item['predicted_mb']} MB",
                        f"+{f_item['growth_pct']}%",
                    )
        else:
            st.info("Chưa có đủ điểm dữ liệu lịch sử trong `backup_size_log`.")

    st.markdown("---")

    # 3. BẢNG ĐIỀU KHIỂN THỰC THI BACKUP THỰC TẾ
    st.markdown(sub_header("4. Sinh lệnh và thực thi backup"), unsafe_allow_html=True)

    col_b1, col_b2 = st.columns([1, 1])

    with col_b1:
        st.markdown("**Chọn loại hình backup:**")
        bk_type = st.radio(
            "Loại backup:",
            options=["Full (toàn bộ CSDL)", "Schema (chỉ cấu trúc DDL)", "Table (riêng 1 bảng)"],
            horizontal=False,
            label_visibility="collapsed",
        )

        selected_tbl = None
        type_key = "full"
        if "Full" in bk_type:
            type_key = "full"
        elif "Schema" in bk_type:
            type_key = "schema"
        else:
            type_key = "table"
            all_tables = [t["bang"] for t in cr_data.get("tables", [])] or ["don_hang", "chi_tiet_don_hang", "ton_kho"]
            selected_tbl = st.selectbox("Chọn bảng cần backup:", all_tables)

        cmd_info = smart_backup_engine.generate_backup_commands(type_key, selected_tbl)
        st.markdown("**Lệnh `pg_dump` tự động sinh:**")
        st.code(cmd_info.get("command", ""), language="bash")
        st.markdown("**Lệnh `pg_restore` khi cần phục hồi:**")
        st.code(cmd_info.get("restore_command", ""), language="bash")

    with col_b2:
        st.markdown("**Thực thi backup**")
        st.caption("Chạy pg_dump thật, tính mã băm SHA-256 và ghi vào bảng backup_history.")
        
        if is_admin(st.session_state):
            btn_do_backup = st.button("Chạy backup ngay", type="primary", use_container_width=True)
            if btn_do_backup:
                with st.spinner("Đang thực thi bản backup và kiểm tra toàn vẹn SHA-256..."):
                    bk_res = smart_backup_engine.execute_backup(type_key, selected_tbl)
                st.cache_data.clear()  # lịch sử backup / dung lượng đã thay đổi

                if bk_res.get("success"):
                    st.success(f"Đã tạo bản backup thành công: `{bk_res.get('filename')}`")
                    st.write(f"• **Dung lượng**: `{bk_res.get('size_mb')} MB`")
                    st.write(f"• **SHA-256 Checksum**: `{bk_res.get('checksum_sha256')}`")
                    st.write(f"• **Lệnh đã thực thi**: `{bk_res.get('command')}`")
                    st.rerun()
                else:
                    st.error(f"Lỗi thực thi backup: {bk_res.get('error')}")
        else:
            st.info("Vai trò Manager chỉ được xem. Thực thi backup dành cho Admin.")

    st.markdown("---")

    # 4. NHẬT KÝ LỊCH SỬ BACKUP (AUDIT & INTEGRITY LOG) KÈM NÚT KHÔI PHỤC TỪNG BẢN
    st.markdown(sub_header("5. Lịch sử backup và phục hồi"), unsafe_allow_html=True)
    st.caption("Mỗi bản backup lưu kèm mã băm SHA-256. Khi khôi phục, hệ thống so lại mã băm của tệp trước khi nạp vào CSDL.")

    hist_logs = _c_backup_history(10)

    _LOAI = {"full": "Full", "schema": "Schema", "table": "Table"}
    if hist_logs:
        _w = [1.8, 0.9, 1.0, 2.6, 1.5, 1.2]
        h_cols = st.columns(_w)
        for _hc, _ht in zip(h_cols, ["Thời điểm", "Loại", "Dung lượng nén", "SHA-256", "Toàn vẹn", "Thao tác"]):
            _hc.markdown(f"<span class='kpi-label'>{_ht}</span>", unsafe_allow_html=True)

        for log in hist_logs:
            r_col1, r_col2, r_col3, r_col4, r_col5, r_col6 = st.columns(_w)
            r_col1.caption(f"{log['thoi_gian']}")
            _lb = str(log.get("loai_backup", ""))
            r_col2.markdown(badge(_LOAI.get(_lb.split("_")[0].lower(), _lb), "neutral"), unsafe_allow_html=True)
            r_col3.caption(log.get("size_text") or f"{log['dung_luong_mb']} MB")
            r_col4.code(f"{(log.get('checksum_sha256') or '')[:20]}…", language="text")
            _ok_status = str(log.get("trang_thai", "")).lower() in ("thanh_cong", "success")
            # Tìm tệp theo tên trong thư mục backups hiện tại (kể cả bản ghi cũ lưu đường dẫn thư mục trước khi đổi tên)
            _file_ok = bool(log.get("file_exists"))
            if _ok_status and log.get("checksum_sha256") and _file_ok:
                r_col5.markdown(badge("OK", "healthy", dot=True), unsafe_allow_html=True)
            elif _ok_status and log.get("checksum_sha256"):
                r_col5.markdown(badge("Thiếu tệp backup", "warning", dot=True), unsafe_allow_html=True)
            else:
                r_col5.markdown(badge(str(log.get("trang_thai", "Lỗi")), "danger", dot=True), unsafe_allow_html=True)

            with r_col6:
                if is_admin(st.session_state):
                    btn_restore_row = st.button("Khôi phục", key=f"restore_btn_{log['id']}", use_container_width=True)
                    if btn_restore_row:
                        with st.spinner(f"Đang xác minh mã băm và khôi phục bản #{log['id']}..."):
                            rest_res = smart_backup_engine.restore_backup(log["id"])
                        st.cache_data.clear()  # dữ liệu vừa được khôi phục

                        if rest_res.get("success"):
                            st.success(f"Khôi phục thành công bản #{log['id']}!")
                            msg_txt = rest_res.get('message')
                            cmd_txt = rest_res.get('restore_command')
                            st.info(f"• **Thông điệp**: {msg_txt}\n\n• **Lệnh**: `{cmd_txt}`")
                        else:
                            st.error(f"Khôi phục thất bại: {rest_res.get('error')}")
                else:
                    st.caption("Chỉ Admin")

        st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.info("Chưa có bản ghi backup nào trong nhật ký `backup_history`.")


# ------------------------------------------------------------------------------
# TAB 6: KHÁM PHÁ LƯỢC ĐỒ (SCHEMA EXPLORER)
# ------------------------------------------------------------------------------
with tab_schema:
    st.markdown(section_header(
        "Lược đồ dữ liệu schema LinhKien",
        "14 bảng nghiệp vụ và các bảng hệ thống (tài khoản, nhật ký backup, ánh xạ phân quyền). "
        "Số dòng là ước tính từ thống kê của PostgreSQL (pg_class.reltuples).",
        "Schema Explorer"), unsafe_allow_html=True)

    _BANG_NGHIEP_VU = [
        "danh_muc", "thuong_hieu", "nha_cung_cap", "san_pham", "san_pham_nha_cung_cap", "ton_kho", "nhan_vien",
        "khach_hang", "dia_chi", "don_hang", "chi_tiet_don_hang", "thanh_toan", "phieu_nhap", "chi_tiet_phieu_nhap",
    ]
    schema_info = _c_schema_info()
    if not schema_info.get("success"):
        st.error(f"Không thể nạp thông tin schema: {schema_info.get('error')}")
    else:
        tables_dict = schema_info.get("tables", {})
        catalog = _c_table_catalog()
        # Bỏ các bảng con của phân vùng (lich_su_thay_doi_gia_2026_10...) khỏi danh sách chọn
        visible = [t for t in tables_dict if not catalog or t in catalog]
        business = [t for t in _BANG_NGHIEP_VU if t in visible]
        system_tbls = sorted(t for t in visible if t not in _BANG_NGHIEP_VU)
        table_names = business + system_tbls

        selected_tbl = st.selectbox(
            "Chọn bảng dữ liệu:", table_names,
            format_func=lambda t: f"{t}  ·  {'nghiệp vụ' if t in _BANG_NGHIEP_VU else 'hệ thống'}",
        )

        def _catalog_cards(names):
            cols = st.columns(4)
            for i, t in enumerate(names):
                info = catalog.get(t, {})
                meta = f"{int(info.get('so_dong', 0)):,} dòng · {info.get('so_fk', 0)} khóa ngoại · {info.get('so_index', 0)} chỉ mục"
                if info.get("phan_vung"):
                    meta += " · phân vùng"
                sel = " selected" if t == selected_tbl else ""
                cols[i % 4].markdown(
                    f'<div class="catalog-card{sel}"><div class="t">{t}</div><div class="m">{meta}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown(sub_header(f"Bảng nghiệp vụ ({len(business)})"), unsafe_allow_html=True)
        _catalog_cards(business)
        if system_tbls:
            with st.expander(f"Bảng hệ thống ({len(system_tbls)})"):
                _catalog_cards(system_tbls)

        tbl_meta = tables_dict.get(selected_tbl, {})
        tbl_desc = tbl_meta.get("description") or "Bảng dữ liệu trong hệ thống LinhKien_DB"
        st.markdown(sub_header(f"Bảng {selected_tbl} · {len(tbl_meta.get('columns', []))} cột"), unsafe_allow_html=True)
        st.caption(tbl_desc)

        columns_data = tbl_meta.get("columns", [])
        if columns_data:
            df_cols = pd.DataFrame(columns_data)
            df_cols.rename(
                columns={
                    "name": "Tên cột",
                    "type": "Kiểu dữ liệu",
                    "nullable": "Cho phép Null?",
                    "description": "Chú thích / Diễn giải",
                },
                inplace=True,
            )
            st.dataframe(df_cols, use_container_width=True, hide_index=True)

        st.markdown(sub_header("5 bản ghi mẫu"), unsafe_allow_html=True)
        preview_res = execute_query(f'SELECT * FROM "{config.DB_SCHEMA}"."{selected_tbl}" LIMIT 5;')
        if preview_res["success"] and preview_res["data"]:
            df_preview = pd.DataFrame(preview_res["data"])
            st.dataframe(df_preview, use_container_width=True)
        else:
            st.info("Bảng hiện tại chưa có dữ liệu.")


# ------------------------------------------------------------------------------
# TAB 7: DASHBOARD THỐNG KÊ
# ------------------------------------------------------------------------------
with tab_dashboard:
    st.markdown(section_header(
        "Tổng quan hoạt động cửa hàng",
        "Số liệu đọc trực tiếp từ LinhKien_DB (lưu đệm 60 giây; bấm «Làm mới dữ liệu» ở thanh bên để cập nhật ngay).",
        "Dashboard"), unsafe_allow_html=True)

    summary = _c_dashboard_summary()
    rev = summary["total_revenue"]
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card("Tổng sản phẩm", f"{summary['total_products']:,}", "Đang quản lý trong kho"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Tổng đơn hàng", f"{summary['total_orders']:,}",
                         f"Hoàn thành: {summary['total_completed_orders']:,}", "good"), unsafe_allow_html=True)
    c3.markdown(kpi_card("Tổng khách hàng", f"{summary['total_customers']:,}", "Đã đăng ký"), unsafe_allow_html=True)
    c4.markdown(kpi_card("Tổng doanh thu", f"{rev / 1_000_000_000:.2f} tỷ", f"{rev:,.0f} VNĐ", "good"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown(sub_header("Doanh thu theo tháng (đơn hoàn thành)"), unsafe_allow_html=True)
        monthly_data = _c_monthly_revenue()
        if monthly_data:
            df_monthly = pd.DataFrame(monthly_data)
            df_monthly["doanh_thu_trieu"] = df_monthly["doanh_thu"] / 1_000_000
            df_monthly.set_index("thang", inplace=True)
            st.bar_chart(df_monthly["doanh_thu_trieu"], color=CHART_BLUE)
            st.caption("Đơn vị: Triệu VNĐ")
        else:
            st.info("Chưa có dữ liệu doanh thu hàng tháng.")

    with col_chart2:
        st.markdown(sub_header("Doanh thu và số đơn theo kênh bán"), unsafe_allow_html=True)
        channel_sql = """
        SELECT 
            kenh_ban AS "Kênh bán",
            COUNT(id) AS "Số đơn hàng",
            COALESCE(SUM(tong_tien), 0) AS "Doanh thu"
        FROM don_hang
        WHERE trang_thai = 'hoan_thanh'
        GROUP BY kenh_ban
        ORDER BY "Doanh thu" DESC;
        """
        ch_res = _c_query(channel_sql)
        if ch_res["success"] and ch_res["data"]:
            df_channel = pd.DataFrame(ch_res["data"])
            df_channel["Doanh thu (Triệu)"] = (df_channel["Doanh thu"] / 1_000_000).map(lambda v: f"{v:,.1f}")
            st.dataframe(
                df_channel[["Kênh bán", "Số đơn hàng", "Doanh thu (Triệu)"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Chưa có dữ liệu kênh bán hàng.")

    st.markdown("---")

    st.markdown(sub_header("Linh kiện tồn kho thấp (cần nhập thêm)"), unsafe_allow_html=True)
    low_stocks = _c_low_stock(15)
    if low_stocks:
        df_low = pd.DataFrame(low_stocks)
        df_low.rename(
            columns={
                "ma_sku": "Mã SKU",
                "ten_san_pham": "Tên Linh Kiện",
                "danh_muc": "Danh Mục",
                "so_luong_ton": "Số Lượng Tồn",
                "muc_ton_toi_thieu": "Mức Tối Thiểu",
                "gia_niem_yet": "Giá Niêm Yết (VNĐ)",
            },
            inplace=True,
        )
        st.dataframe(
            df_low[["Mã SKU", "Tên Linh Kiện", "Danh Mục", "Số Lượng Tồn", "Mức Tối Thiểu", "Giá Niêm Yết (VNĐ)"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("Tất cả các sản phẩm đều đảm bảo mức tồn kho an toàn.")


# ------------------------------------------------------------------------------
# TAB 8: LỊCH SỬ TRUY VẤN
# ------------------------------------------------------------------------------
with tab_history:
    st.markdown(section_header(
        "Lịch sử truy vấn trong phiên",
        "Các câu hỏi đã chạy ở tab Truy vấn trong phiên đăng nhập hiện tại; lọc theo phân hệ hoặc trạng thái và xuất CSV.",
        "Query History"), unsafe_allow_html=True)

    col_h_info, col_h_clear = st.columns([5, 1])
    with col_h_info:
        st.caption(f"Tổng số lượt truy vấn: **{len(st.session_state.history)}**")

    with col_h_clear:
        if is_admin(st.session_state):
            if st.button("Xóa lịch sử", use_container_width=True):
                st.session_state.history = []
                st.rerun()
        else:
            st.caption("Manager không thể xóa lịch sử")

    if st.session_state.history:
        df_hist = pd.DataFrame(st.session_state.history)
        f1, f2 = st.columns(2)
        with f1:
            _eng_opts = sorted(df_hist["Động cơ AI"].dropna().unique().tolist()) if "Động cơ AI" in df_hist else []
            _eng_sel = st.multiselect("Lọc theo phân hệ", _eng_opts, default=[], placeholder="Tất cả phân hệ")
        with f2:
            _st_opts = sorted(df_hist["Trạng thái"].dropna().unique().tolist()) if "Trạng thái" in df_hist else []
            _st_sel = st.multiselect("Lọc theo trạng thái", _st_opts, default=[], placeholder="Tất cả trạng thái")
        if _eng_sel:
            df_hist = df_hist[df_hist["Động cơ AI"].isin(_eng_sel)]
        if _st_sel:
            df_hist = df_hist[df_hist["Trạng thái"].isin(_st_sel)]
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        csv_hist = df_hist.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="Xuất CSV",
            data=csv_hist,
            file_name=f"lich_su_text2sql_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("Chưa có lượt truy vấn nào trong phiên này. Hãy chạy một câu hỏi ở tab Truy vấn hoặc chọn câu hỏi mẫu ở thanh bên.")
