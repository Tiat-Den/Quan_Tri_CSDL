"""
Module xác thực người dùng tầng ứng dụng (Authentication & RBAC).
Hệ thống: Cửa hàng linh kiện máy tính (LinhKien_DB)

Bảo mật (sau nâng cấp database/nang_cap_bao_mat_toi_uu.sql):
- Mật khẩu lưu bằng bcrypt (pgcrypto crypt + gen_salt('bf')) — có salt, chậm có chủ đích, chống dò.
- Ứng dụng KHÔNG đọc trực tiếp bảng app_users (role chỉ đọc đã bị REVOKE). Việc so khớp mật khẩu
  nằm trong hàm SECURITY DEFINER "LinhKien".fn_xac_thuc_nguoi_dung(username, password),
  hàm chỉ trả về đúng/sai + thông tin cơ bản, không bao giờ trả password_hash.
- Tương thích ngược: nếu CSDL chưa chạy bản nâng cấp (chưa có hàm), dùng cách cũ SHA-256.
- Hash SHA-256 cũ được nâng cấp dần lên bcrypt ngay lần đăng nhập thành công kế tiếp.
"""

import hashlib
import logging
import threading
from typing import Any, Dict, Optional

from app import config
from app.db import get_connection, execute_query, execute_admin_query

logger = logging.getLogger(__name__)

SQL_AUTH_FUNCTION = 'SELECT * FROM "LinhKien".fn_xac_thuc_nguoi_dung(%s, %s);'
SQL_AUTH_LEGACY = """
SELECT id, username, ho_ten, role, active
FROM "LinhKien".app_users
WHERE username = %s AND password_hash = %s AND active = TRUE;
"""


def hash_password(password: str) -> str:
    """SHA-256 (định dạng cũ) — chỉ còn dùng để tương thích với CSDL chưa nâng cấp."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _admin_exec(sql: str, params: tuple) -> bool:
    """Chạy một lệnh ghi nhỏ bằng kết nối quản trị (nếu được bật). Lỗi không làm hỏng đăng nhập."""
    if not getattr(config, "ALLOW_ADMIN_CONNECTION", False):
        return False
    conn = None
    try:
        conn = get_connection(use_admin=True)
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return True
    except Exception as exc:  # pragma: no cover - phụ thuộc DB thật
        logger.warning("Không cập nhật được app_users: %s", exc)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _post_login_updates(user_id: int, password_to_upgrade: Optional[str]) -> None:
    _admin_exec('UPDATE "LinhKien".app_users SET lan_dang_nhap_cuoi = NOW() WHERE id = %s;', (user_id,))
    # Nâng cấp hash SHA-256 cũ -> bcrypt (chỉ khi CSDL đã có pgcrypto, tức là đã chạy bản nâng cấp)
    if password_to_upgrade is not None:
        _admin_exec(
            'UPDATE "LinhKien".app_users SET password_hash = crypt(%s, gen_salt(\'bf\', 10)) WHERE id = %s;',
            (password_to_upgrade, user_id),
        )


def _function_missing(res: Dict[str, Any]) -> bool:
    err = (res.get("error") or "").lower()
    return "fn_xac_thuc_nguoi_dung" in err and ("does not exist" in err or "không tồn tại" in err)


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Xác thực đăng nhập. Trả về dict người dùng nếu đúng, None nếu sai.
    1. Gọi hàm CSDL fn_xac_thuc_nguoi_dung qua role chỉ đọc (không cần superuser).
    2. Nếu CSDL chưa nâng cấp (chưa có hàm) -> so khớp SHA-256 kiểu cũ.
    3. Đăng nhập đúng: cập nhật lần đăng nhập cuối; nếu hash còn là SHA-256 thì đổi sang bcrypt.
    """
    if not username or not password:
        return None
    username = username.strip()

    res = execute_query(SQL_AUTH_FUNCTION, (username, password))
    legacy = False
    if not res.get("success") and _function_missing(res):
        legacy = True
        res = execute_query(SQL_AUTH_LEGACY, (username, hash_password(password)))
        if not res.get("success") and getattr(config, "ALLOW_ADMIN_CONNECTION", False):
            res = execute_admin_query(SQL_AUTH_LEGACY, (username, hash_password(password)))
    elif not res.get("success"):
        logger.error("Xác thực thất bại do lỗi CSDL: %s", res.get("error"))

    if not (res.get("success") and res.get("data")):
        return None

    user = res["data"][0]
    # Ghi "lần đăng nhập cuối" (và nâng cấp hash nếu cần) trong LUỒNG NỀN: mở kết nối quản trị + bcrypt
    # mất thêm vài trăm ms, người dùng không cần chờ việc này mới vào được dashboard.
    upgrade = (not legacy) and bool(user.get("can_nang_cap_hash"))
    threading.Thread(target=_post_login_updates, args=(user["id"], password if upgrade else None),
                     daemon=True).start()

    return {
        "id": user["id"],
        "username": user["username"],
        "ho_ten": user["ho_ten"],
        "role": user["role"],
    }


def account_still_valid(username: str, role: str) -> bool:
    """
    Dùng khi khôi phục phiên từ token (F5): tài khoản phải còn hoạt động và vai trò không đổi.
    CSDL chưa nâng cấp (chưa có hàm fn_vai_tro_nguoi_dung) -> chấp nhận token như trước.
    """
    res = execute_query('SELECT "LinhKien".fn_vai_tro_nguoi_dung(%s) AS role;', (username,))
    if res.get("success") and res.get("data"):
        return res["data"][0].get("role") == role
    err = (res.get("error") or "").lower()
    return "fn_vai_tro_nguoi_dung" in err and ("does not exist" in err or "không tồn tại" in err)


def is_admin(session_state) -> bool:
    """Kiểm tra user hiện tại có phải Quản trị viên (Admin) không."""
    user = session_state.get("current_user")
    return user is not None and user.get("role") == "admin"


def is_manager(session_state) -> bool:
    """Kiểm tra user hiện tại có phải Quản lý cửa hàng (Manager) không."""
    user = session_state.get("current_user")
    return user is not None and user.get("role") == "manager"


def get_current_role(session_state) -> str:
    """Lấy vai trò hiện tại: 'admin', 'manager', hoặc 'guest'."""
    user = session_state.get("current_user")
    if user:
        return user.get("role", "guest")
    return "guest"
