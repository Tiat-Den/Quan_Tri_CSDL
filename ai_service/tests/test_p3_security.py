import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_3_security.ai_security_guard import AISecurityGuard, read_audit_log, write_audit_log
from app.session_context import SessionContext, RateTracker, mask_sensitive_columns


class TestP3SecurityGuard(unittest.TestCase):
    def test_table_driven_acceptance_matrix(self):
        """Kiểm tra ma trận kiểm thử an ninh 8 tình huống chuẩn theo đặc tả A3-4."""
        # 1. SELECT ten FROM san_pham LIMIT 5 | giờ 10, IP 127.0.0.1 -> 0 điểm, NORMAL
        r1 = AISecurityGuard.evaluate_risk("SELECT ten FROM san_pham LIMIT 5", hour=10, ip_address="127.0.0.1")
        self.assertEqual(r1["score"], 0.0)
        self.assertEqual(r1["status"], "NORMAL")
        self.assertTrue(r1["allowed"])

        # 2. SELECT gia_von FROM san_pham | bình thường -> >= 70, HIGH, allowed=False
        r2 = AISecurityGuard.evaluate_risk("SELECT gia_von FROM san_pham", hour=10, ip_address="127.0.0.1")
        self.assertGreaterEqual(r2["score"], 70.0)
        self.assertEqual(r2["status"], "HIGH")
        self.assertFalse(r2["allowed"])
        self.assertTrue(len(r2["recommended_dba_actions"]) > 0)

        # 3. SELECT ho_ten, so_dien_thoai FROM khach_hang LIMIT 10 | bình thường -> 45, WARNING
        r3 = AISecurityGuard.evaluate_risk("SELECT ho_ten, so_dien_thoai FROM khach_hang LIMIT 10", hour=10, ip_address="127.0.0.1")
        self.assertEqual(r3["score"], 45.0)
        self.assertEqual(r3["status"], "WARNING")
        self.assertTrue(r3["allowed"])

        # 4. Như trên nhưng giờ 2, IP 8.8.8.8 -> 100, HIGH
        r4 = AISecurityGuard.evaluate_risk("SELECT ho_ten, so_dien_thoai FROM khach_hang LIMIT 10", hour=2, ip_address="8.8.8.8")
        self.assertEqual(r4["score"], 100.0)
        self.assertEqual(r4["status"], "HIGH")
        self.assertFalse(r4["allowed"])

        # 5. SELECT * FROM khach_hang | bình thường -> >= 70, HIGH
        r5 = AISecurityGuard.evaluate_risk("SELECT * FROM khach_hang", hour=10, ip_address="127.0.0.1")
        self.assertGreaterEqual(r5["score"], 70.0)
        self.assertEqual(r5["status"], "HIGH")
        self.assertFalse(r5["allowed"])

        # 6. SELECT COUNT(*) FROM khach_hang | bình thường -> Không bị tính trích xuất hàng loạt
        r6 = AISecurityGuard.evaluate_risk("SELECT COUNT(*) FROM khach_hang", hour=10, ip_address="127.0.0.1")
        self.assertLess(r6["score"], 40.0)
        self.assertEqual(r6["status"], "NORMAL")
        self.assertTrue(r6["allowed"])

        # 7. DROP TABLE san_pham | bình thường -> HIGH
        r7 = AISecurityGuard.evaluate_risk("DROP TABLE san_pham", hour=10, ip_address="127.0.0.1")
        self.assertGreaterEqual(r7["score"], 80.0)
        self.assertEqual(r7["status"], "HIGH")
        self.assertFalse(r7["allowed"])

        # 8. JOIN 2 bảng nhạy cảm: khach_hang và don_hang -> tính cả 2 bảng
        r8 = AISecurityGuard.evaluate_risk("SELECT k.email FROM khach_hang k JOIN don_hang d ON d.khach_hang_id=k.id LIMIT 5", hour=10, ip_address="127.0.0.1")
        self.assertIn("khach_hang", r8["accessed_tables"])
        self.assertIn("don_hang", r8["accessed_tables"])
        self.assertEqual(r8["score"], 60.0)  # 25 (khach_hang) + 15 (don_hang) + 20 (email)
        self.assertEqual(r8["status"], "WARNING")
        self.assertTrue(r8["allowed"])

    def test_session_context_integration(self):
        """Kiểm tra truyền SessionContext đối tượng phiên thật vào evaluate_risk."""
        ctx = SessionContext(
            session_id="sess_test_123",
            user="sale_rep",
            ip="10.0.0.5",
            hour=14,
            failed_logins=2,
            qps=2.5,
        )
        res = AISecurityGuard.evaluate_risk("SELECT ten FROM san_pham LIMIT 10", ctx=ctx)
        self.assertEqual(res["user"], "sale_rep")
        self.assertEqual(res["ip"], "10.0.0.5")
        self.assertEqual(res["score"], 30.0)  # 2 failed logins * 15 = 30.0
        self.assertEqual(res["status"], "NORMAL")

    def test_rate_tracker(self):
        """Kiểm tra bộ đo tần suất RateTracker cửa sổ trượt."""
        tracker = RateTracker(window_seconds=2.0)
        sess = "user_qps_test"
        for _ in range(5):
            tracker.record_hit(sess)
        qps = tracker.get_qps(sess)
        self.assertGreater(qps, 0)
        self.assertLessEqual(qps, 5.0)

    def test_data_masking(self):
        """Kiểm tra Dynamic Data Masking đối với email, số điện thoại và địa chỉ."""
        sample_rows = [
            {
                "id": 1,
                "ho_ten": "Nguyen Van A",
                "email": "datnguyen@gmail.com",
                "so_dien_thoai": "0912345678",
                "dia_chi_chi_tiet": "123 Đường Cầu Giấy, Hà Nội",
                "tong_chi_tieu": 15000000,
            }
        ]
        masked = mask_sensitive_columns(sample_rows)
        self.assertEqual(len(masked), 1)
        row = masked[0]
        self.assertEqual(row["ho_ten"], "Nguyen Van A")
        self.assertEqual(row["tong_chi_tieu"], 15000000)
        # Kiểm tra che email
        self.assertTrue(row["email"].startswith("d***@"))
        self.assertTrue(row["email"].endswith("@gmail.com"))
        # Kiểm tra che SĐT
        self.assertEqual(row["so_dien_thoai"], "0912***678")
        # Kiểm tra che địa chỉ
        self.assertIn("***", row["dia_chi_chi_tiet"])

    def test_audit_log_write_and_read(self):
        """Kiểm tra ghi và đọc nhật ký an ninh audit log."""
        test_entry = {
            "timestamp": "2026-10-20T21:00:00",
            "user": "test_auditor",
            "ip": "127.0.0.1",
            "sql": "SELECT 1",
            "score": 0.0,
            "status": "NORMAL",
            "allowed": True,
            "factors": ["Test log"],
        }
        write_audit_log(test_entry)
        logs = read_audit_log(limit=10)
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0)
        # Bản ghi mới nhất ở đầu danh sách
        self.assertEqual(logs[0]["user"], "test_auditor")


if __name__ == "__main__":
    unittest.main()
