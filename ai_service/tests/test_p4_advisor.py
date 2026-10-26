import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_index_advisor import AIIndexAdvisor


class TestP4IndexAdvisor(unittest.TestCase):
    def test_get_table_columns_allowlist(self):
        """Kiểm tra trích xuất allowlist cột hợp lệ của bảng."""
        cols_sp = AIIndexAdvisor.get_table_columns("san_pham")
        self.assertIn("ten", cols_sp)
        self.assertIn("gia_niem_yet", cols_sp)
        # gia_von đã bị xóa khỏi allowlist cột của san_pham
        self.assertNotIn("gia_von", cols_sp)

        cols_dh = AIIndexAdvisor.get_table_columns("don_hang")
        self.assertIn("khach_hang_id", cols_dh)
        self.assertIn("ngay_dat", cols_dh)
        self.assertIn("trang_thai", cols_dh)

    def test_extract_candidate_columns_equality(self):
        """Kiểm tra bóc tách cột điều kiện so sánh bằng."""
        valid_cols = {"gia_niem_yet", "danh_muc", "thuong_hieu"}
        mock_node = {"Filter": "(gia_niem_yet = 5000000::numeric)"}
        eq_cols, rg_cols, is_non_sargable, rewrite = AIIndexAdvisor._extract_candidate_columns(mock_node, valid_cols)
        self.assertEqual(eq_cols, ["gia_niem_yet"])
        self.assertEqual(rg_cols, [])
        self.assertFalse(is_non_sargable)

    def test_extract_candidate_columns_range(self):
        """Kiểm tra bóc tách cột điều kiện so sánh khoảng."""
        valid_cols = {"gia_niem_yet", "so_luong_ton"}
        mock_node = {"Filter": "(gia_niem_yet > 10000000::numeric)"}
        eq_cols, rg_cols, is_non_sargable, rewrite = AIIndexAdvisor._extract_candidate_columns(mock_node, valid_cols)
        self.assertEqual(eq_cols, [])
        self.assertEqual(rg_cols, ["gia_niem_yet"])
        self.assertFalse(is_non_sargable)

    def test_extract_candidate_columns_non_sargable_extract(self):
        """Kiểm tra phát hiện điều kiện non-sargable EXTRACT(YEAR)."""
        valid_cols = {"ngay_dat", "tong_tien"}
        mock_node = {"Filter": "(EXTRACT(year FROM ngay_dat) = 2025::numeric)"}
        eq_cols, rg_cols, is_non_sargable, rewrite = AIIndexAdvisor._extract_candidate_columns(mock_node, valid_cols)
        self.assertTrue(is_non_sargable)
        self.assertIsNotNone(rewrite)
        self.assertIn("ngay_dat >=", rewrite)

    def test_extract_candidate_columns_non_sargable_wildcard(self):
        """Kiểm tra phát hiện điều kiện non-sargable ký tự đại diện % ở đầu."""
        valid_cols = {"ten", "mo_ta"}
        mock_node = {"Filter": "(ten ~~* '%rtx%')"}
        eq_cols, rg_cols, is_non_sargable, rewrite = AIIndexAdvisor._extract_candidate_columns(mock_node, valid_cols)
        self.assertTrue(is_non_sargable)
        self.assertIsNotNone(rewrite)
        self.assertIn("pg_trgm", rewrite)

    def test_analyze_query_execution_plan(self):
        """Kiểm tra chạy phân tích kế hoạch thực thi EXPLAIN JSON trên DB thực tế."""
        # Chọn các cột được cấp phép (không dùng SELECT * vì gia_von đã bị khóa quyền ở cấp cột CLS)
        sql = "SELECT id, ten, gia_niem_yet FROM san_pham WHERE gia_niem_yet > 20000000;"
        res = AIIndexAdvisor.analyze_query(sql)
        self.assertTrue(res["success"])
        self.assertIn("status", res)
        self.assertIn("recommendations", res)
        self.assertIn("skipped", res)
        self.assertIsInstance(res["recommendations"], list)
        self.assertIsInstance(res["skipped"], list)

    def test_sql_security_block_destructive(self):
        """Kiểm tra chặn câu lệnh nguy hiểm không được chạy qua EXPLAIN."""
        res = AIIndexAdvisor.analyze_query("DROP TABLE san_pham;")
        self.assertFalse(res["success"])
        self.assertIn("không vượt qua kiểm tra an ninh", res["error"])


if __name__ == "__main__":
    unittest.main()
