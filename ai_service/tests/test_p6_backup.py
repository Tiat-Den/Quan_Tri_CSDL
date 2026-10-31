import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_6_smart_backup.ai_smart_backup import smart_backup_engine, BackupSizePredictor


class TestP6SmartBackup(unittest.TestCase):
    def test_backup_size_predictor(self):
        """Kiểm tra mô hình OLS dự báo dung lượng backup."""
        predictor = BackupSizePredictor()
        x_vals = [1.0, 2.0, 3.0, 4.0]
        y_vals = [10.0, 15.0, 20.0, 25.0]
        predictor.fit(x_vals, y_vals)
        self.assertAlmostEqual(predictor.slope, 5.0, places=2)
        self.assertAlmostEqual(predictor.intercept, 5.0, places=2)
        self.assertGreaterEqual(predictor.predict(5.0), 0.0)

    def test_compute_checksum(self):
        """Kiểm tra sinh checksum SHA-256 xác thực toàn vẹn tệp backup."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write("Dữ liệu kiểm tra SHA-256 an toàn")
            tmp_path = tmp.name

        try:
            checksum = smart_backup_engine.compute_checksum(tmp_path)
            self.assertEqual(len(checksum), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in checksum.lower()))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_generate_backup_commands(self):
        """Kiểm tra sinh lệnh pg_dump đúng chuẩn và an toàn."""
        cmds = smart_backup_engine.generate_backup_commands()
        self.assertTrue(cmds["success"])
        self.assertIn("command", cmds)
        self.assertIn("restore_command", cmds)
        self.assertIn("pg_dump", cmds["command"])
        self.assertIn("LinhKien_DB", cmds["command"])
        self.assertIn("-Fc", cmds["command"])

    def test_evaluate_risk(self):
        """Kiểm tra thuật toán chấm điểm rủi ro mất dữ liệu (0 - 100)."""
        risk_res = smart_backup_engine.evaluate_risk()
        self.assertIn("risk_score", risk_res)
        self.assertIn("risk_level", risk_res)
        self.assertIn("factors", risk_res)
        self.assertGreaterEqual(risk_res["risk_score"], 0.0)
        self.assertLessEqual(risk_res["risk_score"], 100.0)

    def test_analyze_change_rate(self):
        """Kiểm tra phân tích tần suất thay đổi dữ liệu HOT/WARM/COLD trên schema LinhKien."""
        res = smart_backup_engine.analyze_change_rate()
        self.assertTrue(res["success"])
        self.assertIn("tables", res)
        tables = res["tables"]
        self.assertIsInstance(tables, list)
        if tables:
            first = tables[0]
            self.assertIn("bang", first)
            self.assertIn("phan_loai", first)
            self.assertIn(first["phan_loai"], ["HOT", "WARM", "COLD"])


if __name__ == "__main__":
    unittest.main()
