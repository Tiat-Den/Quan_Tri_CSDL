"""
BỘ ĐIỀU PHỐI ĐA TRANG (STREAMLIT MULTIPAGE ORCHESTRATOR)
Kiến trúc 2 trang độc lập:
1. Trang Đăng Nhập (Login Portal)
2. Trang Quản Trị CSDL & 6 Động Cơ AI (Admin/Manager Dashboard)
"""

import os
import sys
import streamlit as st

# Tự động chạy với Streamlit nếu được gọi trực tiếp bằng `python web_app.py`
if not st.runtime.exists():
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", __file__, "--server.port=8501", "--server.headless=false"]
    sys.exit(stcli.main())

# Thiết lập đường dẫn thư mục làm việc
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Nạp sẵn các module AI nặng trong luồng nền ngay khi web mở (chỉ 1 lần / tiến trình)
from app.warmup import start_warmup

start_warmup()

# Khởi tạo Session State cho phiên làm việc & Tự động phục hồi phiên đăng nhập khi F5
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# Khi F5, session_state bị xóa -> khôi phục đăng nhập từ TOKEN CÓ CHỮ KÝ trên URL (?t=...).
# Không còn tin các tham số session_user / session_role dạng chữ thường (ai cũng tự gõ được).
if st.session_state.current_user is None:
    from app.session_token import verify_token
    from app.auth import account_still_valid

    restored = verify_token(st.query_params.get("t"))
    # Tài khoản bị khóa hoặc đổi vai trò sau khi đăng nhập -> token cũ mất hiệu lực ngay
    if restored and not account_still_valid(restored["username"], restored["role"]):
        restored = None
    if restored:
        st.session_state.current_user = restored
    else:
        # Xóa tham số cũ/không hợp lệ khỏi URL (kể cả session_user/session_role của phiên bản trước)
        for _k in ("t", "session_user", "session_role", "session_name"):
            if _k in st.query_params:
                del st.query_params[_k]

if "history" not in st.session_state:
    st.session_state.history = []

if "query_input" not in st.session_state:
    st.session_state.query_input = ""

if "auto_run" not in st.session_state:
    st.session_state.auto_run = False

if "input_box" not in st.session_state:
    st.session_state.input_box = ""

# Định nghĩa 2 Trang Độc Lập bằng st.Page (Streamlit 1.36+ / 1.66)
login_page = st.Page(
    "views/login_page.py",
    title="Đăng Nhập Hệ Thống",
    icon="🔐",
    default=(st.session_state.current_user is None),
)

dashboard_page = st.Page(
    "views/dashboard_page.py",
    title="Bảng Quản Trị CSDL & 6 AI",
    icon="💻",
    default=(st.session_state.current_user is not None),
)

# Phân quyền định tuyến động (Dynamic Page Navigation)
if st.session_state.current_user is None:
    # Chưa đăng nhập: Chỉ cho phép truy cập duy nhất Trang Đăng Nhập
    pg = st.navigation([login_page], position="hidden")
else:
    # Đã đăng nhập: Mở khóa Trang Quản Trị
    pg = st.navigation([dashboard_page])

pg.run()
