"""
TRANG 1: ĐĂNG NHẬP HỆ THỐNG QUẢN TRỊ CSDL (LOGIN PORTAL)
Tách biệt hoàn toàn, giao diện căn giữa, không hiển thị Sidebar hay nội dung nhạy cảm.
"""

import time

import streamlit as st
from app.auth import authenticate
from app.db import check_db_connection
from app.session_token import create_token
from app.ui_theme import BASE_CSS, badge

MAX_LOGIN_FAILS = 5
LOGIN_LOCK_SECONDS = 60


def show_login_page():
    # Giao diện chuẩn Enterprise (UI_UPGRADE_DESIGN.md) + ẩn thanh bên khi chưa đăng nhập
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
        /* Ẩn gợi ý "Press Enter to submit form" trong ô nhập (Enter vẫn đăng nhập được) */
        [data-testid="InputInstructions"] { display: none !important; }
        .login-wrap { text-align: center; margin: 3.2rem 0 1.1rem 0; }
        .login-title { color: inherit; font-size: 1.45rem; font-weight: 700; letter-spacing: -0.01em; margin: 0.7rem 0 0.25rem 0; }
        .login-subtitle { color: inherit; opacity: 0.68; font-size: 0.88rem; margin: 0; }
        [data-testid="stForm"] {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 10px;
            padding: 1.6rem 1.6rem 1.3rem 1.6rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        }
        .login-foot { text-align: center; color: #64748b; font-size: 0.76rem; margin-top: 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Toàn bộ nội dung trang đăng nhập nằm trong 1 khung: đăng nhập thành công thì xóa khung ngay
    # trước khi chuyển trang, để form cũ không còn hiện mờ phía dưới trong lúc dashboard đang tải.
    page = st.empty()
    login_ok = False
    with page.container():
        st.markdown(
            f"""
            <div class="login-wrap">
                <div class="login-title">Hệ Thống Quản Trị CSDL Cửa Hàng Linh Kiện</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c_left, c_center, c_right = st.columns([1, 1.15, 1])

        with c_center:

            st.write("")

            # Ô nhập liệu Username & Password
            val_user = st.session_state.get("login_user_input", "")
            val_pwd = st.session_state.get("login_pwd_input", "")

            # Dùng st.form: nhấn Enter ở ô mật khẩu là gửi form (không cần bấm nút),
            # và gõ phím không làm trang chạy lại liên tục như text_input đứng riêng.
            with st.form("login_form", clear_on_submit=False, border=True):
                username = st.text_input("Tài khoản", value=val_user, placeholder="Nhập tên đăng nhập", key="txt_user")
                password = st.text_input("Mật khẩu", value=val_pwd, type="password", placeholder="Nhập mật khẩu", key="txt_pwd")
                btn_submit = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)

            # Chống dò mật khẩu: sai MAX_LOGIN_FAILS lần liên tiếp -> khóa đăng nhập LOGIN_LOCK_SECONDS giây
            remaining = int(st.session_state.get("login_lock_until", 0) - time.time())

            if btn_submit and remaining > 0:
                st.session_state.login_failed = False
                st.error(f"Đăng nhập tạm khóa do nhập sai {MAX_LOGIN_FAILS} lần liên tiếp. Thử lại sau {remaining} giây.")
            elif btn_submit:
                with st.spinner("Đang xác thực thông tin..."):
                    user_info = authenticate(username, password)

                if user_info:
                    fails_before = st.session_state.get("login_fail_count", 0)
                    st.session_state.current_user = user_info
                    st.session_state.login_failed = False
                    st.session_state.login_fail_count = 0
                    # Số lần nhập sai THẬT trước khi đăng nhập được -> AI 3 dùng làm một yếu tố rủi ro
                    st.session_state["sec_failed"] = min(fails_before, 5)
                    # Lưu TOKEN CÓ CHỮ KÝ lên URL để F5 không mất đăng nhập (không thể tự sửa thành admin)
                    for _k in ("session_user", "session_role", "session_name"):
                        if _k in st.query_params:
                            del st.query_params[_k]
                    st.query_params["t"] = create_token(user_info)
                    login_ok = True
                elif not (db_state := check_db_connection()).get("connected"):
                    # Không kết nối được CSDL: báo đúng nguyên nhân, KHÔNG tính là nhập sai mật khẩu
                    st.session_state.login_failed = False
                    st.error(
                        "Không kết nối được tới cơ sở dữ liệu PostgreSQL nên chưa kiểm tra được tài khoản. "
                        "Hãy kiểm tra dịch vụ PostgreSQL đang chạy và thông tin trong ai_service/.env."
                    )
                    st.caption(f"Chi tiết: {db_state.get('error') or 'không rõ'}")
                else:
                    st.session_state.login_failed = True
                    st.session_state.login_fail_count = st.session_state.get("login_fail_count", 0) + 1
                    if st.session_state.login_fail_count >= MAX_LOGIN_FAILS:
                        st.session_state.login_lock_until = time.time() + LOGIN_LOCK_SECONDS
                        st.session_state.login_fail_count = 0

            if st.session_state.get("login_failed", False):
                st.error("Tên đăng nhập hoặc mật khẩu không chính xác. Vui lòng thử lại.")

            st.markdown(
                '<div class="login-foot">Phiên đăng nhập được ký số, tự hết hạn sau 4 giờ</div>',
                unsafe_allow_html=True,
            )


    if login_ok:
        page.empty()
        st.rerun()

show_login_page()
