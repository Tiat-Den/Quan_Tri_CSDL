"""
Kiểm thử nghiệm thu cho Phase P0 (Nền tảng & Bảo mật cơ sở CSDL)
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import config
from app.db import (
    validate_sql_security,
    get_connection,
    execute_query,
    DatabaseConnectionError,
)
from app.ai_1_text2sql.pipeline import interpret


class TestPhase0Foundations(unittest.TestCase):

    def test_p0_4_sql_security_acceptance(self):
        """P0-4: Bảng test bắt buộc, các câu lệnh độc hại đều phải bị từ chối"""
        rejected_queries = [
            "SELECT * INTO bang_moi FROM san_pham",
            "SELECT pg_sleep(10)",
            "SELECT pg_read_file('/etc/passwd')",
            "EXPLAIN ANALYZE SELECT 1",
            "EXPLAIN (ANALYZE) SELECT 1",
            "SELECT 1; SELECT 2",
            "WITH x AS (DELETE FROM don_hang RETURNING *) SELECT * FROM x",
            "SELECT lo_import('/etc/passwd')",
        ]
        for q in rejected_queries:
            with self.subTest(query=q):
                valid, err = validate_sql_security(q)
                self.assertFalse(valid, f"Câu lệnh phải bị từ chối: {q}")
                self.assertTrue(len(err) > 0)

        # Câu lệnh phải được chấp nhận
        valid_queries = [
            "EXPLAIN (FORMAT JSON) SELECT 1",
            "SELECT id, ten, gia_niem_yet FROM san_pham WHERE dang_kinh_doanh = TRUE LIMIT %s;",
        ]
        for q in valid_queries:
            with self.subTest(query=q):
                valid, err = validate_sql_security(q)
                self.assertTrue(valid, f"Câu lệnh phải được chấp nhận: {q} (Lỗi: {err})")

    @patch("app.db.psycopg2.connect")
    def test_p0_1_no_admin_fallback_by_default(self, mock_connect):
        """P0-1: Mật khẩu sai cho text2sql_readonly -> ném DatabaseConnectionError, gọi connect đúng 1 lần"""
        import psycopg2
        mock_connect.side_effect = psycopg2.OperationalError("password authentication failed")

        with patch.object(config, "ALLOW_ADMIN_FALLBACK", False):
            with self.assertRaises(DatabaseConnectionError):
                get_connection(use_admin=False)
            self.assertEqual(mock_connect.call_count, 1)

    @patch("app.db.get_connection")
    def test_p0_3_row_limit_and_truncation(self, mock_get_conn):
        """P0-3: Con trỏ trả 1000 dòng -> row_count == MAX_ROWS (500), truncated is True"""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        mock_cur.description = [("id",), ("ten",)]
        # Giả lập trả về 1000 dòng
        mock_cur.fetchmany.return_value = [(i, f"SP {i}") for i in range(1000)]

        with patch.object(config, "MAX_ROWS", 500):
            res = execute_query("SELECT id, ten FROM san_pham;")
            self.assertTrue(res["success"])
            self.assertEqual(res["row_count"], 500)
            self.assertTrue(res["truncated"])
            self.assertEqual(len(res["data"]), 500)

    def test_p0_7_pipeline_shared(self):
        """P0-7: interpret() trả về dataclass InterpretResult đầy đủ thông tin"""
        res = interpret("Danh sách sản phẩm đang bán")
        self.assertTrue(res.success)
        self.assertEqual(res.intent, "LIST_PRODUCTS")
        self.assertGreater(res.confidence, 0.0)
        self.assertIsNotNone(res.sql)
        self.assertIn("FROM san_pham", res.sql)


if __name__ == "__main__":
    unittest.main()
