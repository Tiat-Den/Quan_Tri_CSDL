"""
Kiểm thử offline cho đợt vá lỗ hổng bảo mật:
- Token phiên có chữ ký (không thể giả mạo role qua URL)
- Đăng nhập gọi hàm CSDL fn_xac_thuc_nguoi_dung, fallback SHA-256 khi CSDL chưa nâng cấp
- Tài khoản admin trên web chạy câu hỏi chatbot bằng role CHỈ ĐỌC, không phải superuser
"""
import base64
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import session_token  # noqa: E402
from app import auth  # noqa: E402
from app import db  # noqa: E402


class TestSessionToken(unittest.TestCase):
    def setUp(self):
        session_token._secret_cache = b"khoa-kiem-thu"
        self.user = {"username": "manager", "role": "manager", "ho_ten": "Quản Lý"}

    def test_token_hop_le(self):
        tok = session_token.create_token(self.user)
        self.assertEqual(session_token.verify_token(tok), self.user)

    def test_sua_role_thanh_admin_bi_tu_choi(self):
        tok = session_token.create_token(self.user)
        body, sig = tok.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        payload["r"] = "admin"
        fake_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        self.assertIsNone(session_token.verify_token(f"{fake_body}.{sig}"))

    def test_token_het_han(self):
        tok = session_token.create_token(self.user, ttl=-1)
        self.assertIsNone(session_token.verify_token(tok))

    def test_khoa_khac_khong_dung_duoc(self):
        tok = session_token.create_token(self.user)
        session_token._secret_cache = b"khoa-khac"
        self.assertIsNone(session_token.verify_token(tok))

    def test_rac(self):
        for bad in (None, "", "abc", "a.b.c", "x" * 2000, "admin", "abc.đđđ", "é.é", 123):
            self.assertIsNone(session_token.verify_token(bad))

    def test_dang_xuat_thu_hoi_token(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(session_token, "_REVOKED_FILE", Path(d) / "revoked.json"):
                tok = session_token.create_token(self.user)
                other = session_token.create_token(self.user)
                self.assertTrue(session_token.revoke_token(tok))
                self.assertIsNone(session_token.verify_token(tok))
                self.assertIsNotNone(session_token.verify_token(other))


class _SyncThread:
    """Thay threading.Thread trong kiểm thử: chạy ngay, đồng bộ."""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._t, self._a, self._k = target, args, kwargs or {}

    def start(self):
        self._t(*self._a, **self._k)


class TestAuthenticate(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(auth.threading, "Thread", _SyncThread)
        p.start()
        self.addCleanup(p.stop)

    ROW = {"id": 1, "username": "admin", "ho_ten": "Quản Trị", "role": "admin", "can_nang_cap_hash": False}

    def test_goi_ham_csdl_khong_doc_bang(self):
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": [self.ROW]}) as q, \
             mock.patch.object(auth, "_admin_exec", return_value=True):
            user = auth.authenticate(" admin ", "admin123")
        sql, params = q.call_args[0]
        self.assertIn("fn_xac_thuc_nguoi_dung", sql)
        self.assertEqual(params, ("admin", "admin123"))
        self.assertEqual(user["role"], "admin")
        self.assertNotIn("password_hash", user)

    def test_sai_mat_khau(self):
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": []}):
            self.assertIsNone(auth.authenticate("admin", "sai"))
        self.assertIsNone(auth.authenticate("", "x"))

    def test_nang_cap_hash_cu_len_bcrypt(self):
        row = dict(self.ROW, can_nang_cap_hash=True)
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": [row]}), \
             mock.patch.object(auth, "_admin_exec", return_value=True) as w:
            auth.authenticate("admin", "admin123")
        sqls = [c[0][0] for c in w.call_args_list]
        self.assertTrue(any("gen_salt('bf'" in s for s in sqls))

    def test_fallback_khi_csdl_chua_nang_cap(self):
        missing = {"success": False, "data": [], "error": 'function "LinhKien".fn_xac_thuc_nguoi_dung(unknown, unknown) does not exist'}
        ok = {"success": True, "data": [dict(self.ROW)]}
        with mock.patch.object(auth, "execute_query", side_effect=[missing, ok]) as q, \
             mock.patch.object(auth, "_admin_exec", return_value=True) as w:
            user = auth.authenticate("admin", "admin123")
        self.assertEqual(user["username"], "admin")
        self.assertEqual(q.call_args_list[1][0][1][1], auth.hash_password("admin123"))
        self.assertFalse(any("gen_salt" in c[0][0] for c in w.call_args_list))


class TestAccountStillValid(unittest.TestCase):
    def test_tai_khoan_bi_khoa_hoac_doi_vai_tro(self):
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": [{"role": None}]}):
            self.assertFalse(auth.account_still_valid("admin", "admin"))
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": [{"role": "manager"}]}):
            self.assertFalse(auth.account_still_valid("admin", "admin"))
        with mock.patch.object(auth, "execute_query", return_value={"success": True, "data": [{"role": "admin"}]}):
            self.assertTrue(auth.account_still_valid("admin", "admin"))

    def test_csdl_chua_nang_cap_van_dung_duoc(self):
        missing = {"success": False, "error": "function fn_vai_tro_nguoi_dung(unknown) does not exist"}
        with mock.patch.object(auth, "execute_query", return_value=missing):
            self.assertTrue(auth.account_still_valid("admin", "admin"))
        with mock.patch.object(auth, "execute_query", return_value={"success": False, "error": "timeout"}):
            self.assertFalse(auth.account_still_valid("admin", "admin"))


class TestLeastPrivilege(unittest.TestCase):
    def test_admin_web_khong_dung_superuser(self):
        with mock.patch.object(db, "get_connection", return_value="conn") as gc:
            db.get_connection_by_role("admin")
        gc.assert_called_once_with(use_admin=False)


if __name__ == "__main__":
    unittest.main()


class _FakeConn:
    def __init__(self):
        self.closed = 0

    def get_transaction_status(self):
        return 0  # TRANSACTION_STATUS_IDLE

    def rollback(self):
        pass

    def close(self):
        self.closed = 1


class TestConnectionPool(unittest.TestCase):
    def setUp(self):
        db.close_all_pooled_connections()
        self.addCleanup(db.close_all_pooled_connections)

    def test_tai_su_dung_va_tach_rieng_theo_role(self):
        made = []
        def fake_get(use_admin=False):
            c = _FakeConn(); made.append(("admin" if use_admin else "ro", c)); return c
        with mock.patch.object(db, "get_connection", side_effect=fake_get):
            c1, reused = db._acquire_connection("readonly", False, None)
            self.assertFalse(reused)
            db._release_connection("readonly", c1, healthy=True)
            c2, reused = db._acquire_connection("readonly", False, None)
            self.assertIs(c1, c2)
            self.assertTrue(reused)
            # kết nối readonly không bao giờ bị đưa cho yêu cầu admin
            c3, _ = db._acquire_connection("admin", True, None)
            self.assertIsNot(c3, c1)

    def test_ket_noi_loi_bi_dong_khong_tra_ve_pool(self):
        c = _FakeConn()
        db._release_connection("readonly", c, healthy=False)
        self.assertTrue(c.closed)
        self.assertEqual(db._POOL.get("readonly", []), [])
