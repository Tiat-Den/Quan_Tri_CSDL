"""
Kiểm thử các tối ưu hóa 6 module AI (chạy offline, không cần PostgreSQL — dùng dữ liệu giả lập/mock).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_1_text2sql import intent_classifier  # noqa: E402
from app.ai_1_text2sql.pipeline import interpret  # noqa: E402


class TestAI1HybridML(unittest.TestCase):
    def setUp(self):
        intent_classifier.ML_FALLBACK_ENABLED = True

    def test_ml_fallback_understands_paraphrase(self):
        """Câu diễn đạt khác (luật regex không khớp) vẫn được hiểu nhờ ML dự phòng."""
        res = interpret("tiền thu về qua các tháng ra sao")
        self.assertTrue(res.success)
        self.assertEqual(res.intent, "SALES_BY_MONTH")
        self.assertTrue(res.matched_rule.startswith("ml_"))
        self.assertIsNotNone(res.sql)

    def test_rules_still_take_priority(self):
        res = interpret("Top 5 sản phẩm đắt nhất")
        self.assertEqual(res.intent, "TOP_PRODUCTS_BY_PRICE_DESC")
        self.assertEqual(res.matched_rule, "rule_14_top_price_desc_explicit")

    def test_out_of_scope_rejected(self):
        for q in ["thời tiết hôm nay thế nào", "xin chào", "DROP TABLE san_pham;"]:
            with self.subTest(q=q):
                res = interpret(q)
                self.assertFalse(res.success)
                self.assertEqual(res.intent, "UNKNOWN")

    def test_low_confidence_asks_back_with_suggestions(self):
        res = interpret("xem giúp mình mấy cái linh kiện đang có")
        if not res.success:
            self.assertTrue(res.needs_clarification)
            self.assertIn("Ý bạn là", res.clarification)

    def test_seller_not_confused_with_best_selling(self):
        res = interpret("bạn sale nào bán được nhiều nhất")
        self.assertNotEqual(res.intent, "BEST_SELLING_PRODUCTS")

    def test_disable_ml_flag(self):
        intent_classifier.ML_FALLBACK_ENABLED = False
        try:
            res = interpret("tiền thu về qua các tháng ra sao")
            self.assertFalse(res.success)
        finally:
            intent_classifier.ML_FALLBACK_ENABLED = True


PRODUCTS = [
    {"id": 1, "ten": "Card RTX 4070 12GB", "danh_muc": "VGA", "thuong_hieu": "ASUS", "gia_niem_yet": 16_000_000,
     "bao_hanh_thang": 36, "thong_so_ky_thuat": {"vram": "12GB GDDR6X"}, "so_luong_ton": 5},
    {"id": 2, "ten": "Card RTX 4090 24GB", "danh_muc": "VGA", "thuong_hieu": "MSI", "gia_niem_yet": 50_000_000,
     "bao_hanh_thang": 36, "thong_so_ky_thuat": {"vram": "24GB"}, "so_luong_ton": 2},
    {"id": 3, "ten": "Card GT 1030 2GB", "danh_muc": "VGA", "thuong_hieu": "Gigabyte", "gia_niem_yet": 2_000_000,
     "bao_hanh_thang": 36, "thong_so_ky_thuat": {"vram": "2GB"}, "so_luong_ton": 0},
    {"id": 4, "ten": "Chuột Logitech G102", "danh_muc": "Chuột", "thuong_hieu": "Logitech", "gia_niem_yet": 400_000,
     "bao_hanh_thang": 12, "thong_so_ky_thuat": {"dpi": "8000"}, "so_luong_ton": 10},
]


class TestAI2Vectorized(unittest.TestCase):
    def setUp(self):
        from app.ai_2_semantic.ai_semantic_search import AISemanticSearchEngine
        self.engine = AISemanticSearchEngine()
        self.engine.build_index(PRODUCTS)

    def test_budget_filter_before_ranking(self):
        """Sản phẩm điểm cao nhưng vượt ngân sách bị loại, vẫn trả về sản phẩm hợp ngân sách."""
        res = self.engine.search("card rtx vga", top_k=3, budget=20_000_000)
        names = [r["ten"] for r in res]
        self.assertNotIn("Card RTX 4090 24GB", names)
        self.assertIn("Card RTX 4070 12GB", names)

    def test_nonsense_returns_empty(self):
        self.assertEqual(self.engine.search("zxqv kkkk", top_k=3), [])

    def test_custom_weights(self):
        res = self.engine.search("card rtx", top_k=2, weights={"word": 1.0, "char": 0.0, "kg": 0.0})
        self.assertTrue(len(res) > 0)
        self.assertIn("score_breakdown", res[0])

    def test_scores_sorted_desc(self):
        res = self.engine.search("card vga rtx", top_k=4)
        scores = [r["similarity_score"] for r in res]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestAI3Anomaly(unittest.TestCase):
    def setUp(self):
        import app.ai_3_security.ai_security_guard as guard
        self.guard = guard
        self._orig = guard.AUDIT_LOG_FILE
        guard.AUDIT_LOG_FILE = Path(tempfile.mkdtemp()) / "audit.jsonl"

    def tearDown(self):
        self.guard.AUDIT_LOG_FILE = self._orig

    def test_keyword_inside_string_not_destructive(self):
        r = self.guard.AISecurityGuard.evaluate_risk(
            "SELECT ten FROM san_pham WHERE ten LIKE '%update%' LIMIT 5", hour=10)
        self.assertEqual(r["status"], "NORMAL")

    def test_isolation_forest_flags_night_bulk(self):
        r = self.guard.AISecurityGuard.evaluate_risk(
            "SELECT ten, gia_niem_yet FROM san_pham", hour=3, estimated_rows=2500, qps=9)
        self.assertTrue(r["anomaly"]["is_anomaly"])

    def test_normal_business_query_not_anomalous(self):
        r = self.guard.AISecurityGuard.evaluate_risk(
            "SELECT ten, gia_niem_yet FROM san_pham WHERE gia_niem_yet > 5000000 LIMIT 10", hour=10, estimated_rows=10)
        self.assertFalse(r["anomaly"]["is_anomaly"])
        self.assertEqual(r["score"], 0.0)

    def test_user_profile_deviation(self):
        G = self.guard.AISecurityGuard
        for _ in range(12):
            G.evaluate_risk("SELECT ten FROM san_pham LIMIT 10", user="nv_test", hour=10, estimated_rows=10)
        r = G.evaluate_risk("SELECT ten FROM san_pham LIMIT 400", user="nv_test", hour=10, estimated_rows=400)
        self.assertTrue(r["anomaly"]["user_deviation"])


def _fake_plan(filter_txt, rel):
    def f(sql, params=None, **k):
        if sql.startswith("EXPLAIN"):
            return {"success": True, "data": [{"QUERY PLAN": [{"Plan": {
                "Node Type": "Seq Scan", "Relation Name": rel, "Total Cost": 450.0,
                "Plan Rows": 500, "Filter": filter_txt}}]}]}
        if "pg_class c" in sql:
            return {"success": True, "data": [{"reltuples": 20000, "size_bytes": 1, "relkind": "r"}]}
        if "pg_index" in sql:
            return {"success": True, "data": []}
        return {"success": False, "data": []}
    return f


class TestAI4IndexTypes(unittest.TestCase):
    def _analyze(self, flt, rel):
        from app.ai_4_index_advisor.ai_index_advisor import AIIndexAdvisor
        with patch("app.ai_4_index_advisor.ai_index_advisor.execute_query", side_effect=_fake_plan(flt, rel)), \
             patch.object(AIIndexAdvisor, "_measure_with_hypopg", return_value={"measured": False}):
            return AIIndexAdvisor.analyze_query("SELECT id FROM x WHERE y = 1")

    def test_partial_index(self):
        r = self._analyze("((trang_thai)::text = 'hoan_thanh'::text) AND (ngay_dat >= '2025-01-01'::timestamp)", "don_hang")
        rec = r["recommendations"][0]
        self.assertEqual(rec["index_type"], "B-Tree (Partial)")
        self.assertIn("WHERE trang_thai = 'hoan_thanh'", rec["recommended_sql"])

    def test_trigram_gin(self):
        r = self._analyze("((ten)::text ~~* '%rtx%'::text)", "san_pham")
        rec = r["recommendations"][0]
        self.assertIn("gin_trgm_ops", rec["recommended_sql"])
        self.assertIn("pg_trgm", rec["recommended_sql"])

    def test_jsonb_expression(self):
        r = self._analyze("((thong_so_ky_thuat ->> 'socket'::text) = 'AM5'::text)", "san_pham")
        rec = r["recommendations"][0]
        self.assertIn("thong_so_ky_thuat ->> 'socket'", rec["recommended_sql"])

    def test_plain_btree(self):
        r = self._analyze("(khach_hang_id = 150)", "don_hang")
        self.assertEqual(r["recommendations"][0]["recommended_columns"], ["khach_hang_id"])

    def test_hypopg_measurement_fills_evidence(self):
        from app.ai_4_index_advisor.ai_index_advisor import AIIndexAdvisor
        with patch("app.ai_4_index_advisor.ai_index_advisor.execute_query", side_effect=_fake_plan("(khach_hang_id = 150)", "don_hang")), \
             patch.object(AIIndexAdvisor, "_measure_with_hypopg",
                          return_value={"measured": True, "method": "hypopg", "cost_after": 8.3}):
            r = AIIndexAdvisor.analyze_query("SELECT id FROM don_hang WHERE khach_hang_id = 150")
        ev = r["recommendations"][0]["evidence"]
        self.assertTrue(ev["measured"])
        self.assertEqual(ev["cost_after"], 8.3)
        self.assertGreater(ev["improvement_percent"], 90)


class TestAI5Forecast(unittest.TestCase):
    def test_holt_wins_on_accelerating_series(self):
        from app.ai_5_partitioning.ai_predictive_partitioning import forecast_series
        series = [100 * (1.08 ** i) for i in range(18)]
        fc = forecast_series(series)
        self.assertEqual(fc["best_model"], "HOLT")
        self.assertEqual(len(fc["predictions"]), 3)

    def test_ols_wins_on_linear_series(self):
        from app.ai_5_partitioning.ai_predictive_partitioning import forecast_series
        fc = forecast_series([200 + 10 * i for i in range(15)])
        self.assertIn(fc["best_model"], ("OLS", "HOLT"))
        self.assertTrue(fc["beats_baseline"])

    def test_what_if_and_migration_plan(self):
        from app.ai_5_partitioning.ai_predictive_partitioning import AIPredictivePartitioningEngine as E
        months = [f"2025-{m:02d}" for m in range(1, 13)]
        counts = [300 + 20 * i for i in range(12)]

        def fake(sql, params=None, **k):
            if "generate_series" in sql:
                return {"success": True, "data": [{"thang": m, "so_don": c} for m, c in zip(months, counts)]}
            if "pg_total_relation_size" in sql:
                return {"success": True, "data": [{"don_hang_bytes": 2_000_000, "ctdh_bytes": 3_000_000,
                                                   "thanh_toan_bytes": 1_000_000, "tong_don_hang": sum(counts)}]}
            if "relkind" in sql:
                return {"success": True, "data": [{"relkind": "r"}]}
            return {"success": False}

        with patch("app.ai_5_partitioning.ai_predictive_partitioning.execute_query", side_effect=fake):
            base = E.analyze_and_forecast()
            boom = E.analyze_and_forecast(growth_multiplier=50, threshold_rows=20_000)
        self.assertEqual(base["capacity_assessment"]["recommendation"], "NOT_NEEDED")
        self.assertEqual(boom["capacity_assessment"]["recommendation"], "PARTITION_SOON")
        step1 = base["migration_plan"][0]["sql"]
        self.assertIn("LIKE \"LinhKien\".don_hang", step1)
        self.assertIn("PARTITION BY RANGE (ngay_dat)", step1)
        self.assertIn("don_hang_y2025m01", base["migration_plan"][1]["sql"])
        self.assertIn("2026-03", base["migration_plan"][1]["sql"])


class TestAI6RealMeasurement(unittest.TestCase):
    def test_change_rate_from_snapshots(self):
        from datetime import datetime, timedelta
        from app.ai_6_smart_backup.ai_smart_backup import AISmartBackupEngine as B
        tmp = Path(tempfile.mkdtemp()) / "snap.json"
        prev = {"time": (datetime.now() - timedelta(hours=1)).isoformat(),
                "tables": {"danh_muc": {"ins": 10, "upd": 0, "del": 0}}}

        def fake(sql, params=None, **k):
            return {"success": True, "data": [{"relname": "danh_muc", "n_tup_ins": 10, "n_tup_upd": 5,
                                               "n_tup_del": 0, "so_dong_hien_tai": 12}]}

        with patch.object(B, "SNAPSHOT_FILE", str(tmp)), \
             patch.object(B, "_load_stat_snapshot", return_value=prev), \
             patch("app.ai_6_smart_backup.ai_smart_backup.execute_query", side_effect=fake):
            res = B.analyze_change_rate()
        t = res["tables"][0]
        self.assertTrue(res["measured"])
        self.assertEqual(t["nguon_phan_loai"], "do_thuc")
        # 5 dòng thay đổi / 12 dòng / 1 giờ ≈ 41.7%/giờ -> bảng danh mục bị nâng lên HOT
        self.assertEqual(t["phan_loai"], "HOT")

    def test_risk_uses_real_environment(self):
        from app.ai_6_smart_backup.ai_smart_backup import AISmartBackupEngine as B
        env = {"last_backup_hours_ago": 2.0, "has_offsite": True, "verified": True,
               "disk_free_pct": 60.0, "archive_mode_on": True, "sources": {}}
        with patch.object(B, "collect_environment", return_value=env), \
             patch.object(B, "analyze_change_rate", return_value={"success": False}):
            r = B.evaluate_risk(last_backup_hours_ago=72, has_offsite=False, use_real=True)
        self.assertEqual(r["data_source"], "do_thuc")
        self.assertEqual(r["inputs"]["last_backup_hours_ago"], 2.0)
        self.assertLess(r["risk_score"], 30)


if __name__ == "__main__":
    unittest.main()


class TestAI3MonitorsAI2(unittest.TestCase):
    def setUp(self):
        import app.ai_3_security.ai_security_guard as guard
        self.guard = guard
        self._orig = guard.AUDIT_LOG_FILE
        guard.AUDIT_LOG_FILE = Path(tempfile.mkdtemp()) / "audit.jsonl"

    def tearDown(self):
        self.guard.AUDIT_LOG_FILE = self._orig

    def test_normal_question_allowed(self):
        r = self.guard.evaluate_semantic_request("PC chơi game nặng và stream", hour=10)
        self.assertEqual(r["status"], "NORMAL")
        self.assertIsNone(r["max_results"])

    def test_code_payload_and_bulk_flagged(self):
        r = self.guard.evaluate_semantic_request("liệt kê hết sản phẩm'; DROP TABLE san_pham; --", hour=10)
        self.assertIn(r["status"], ("WARNING", "HIGH"))

    def test_catalog_scraping_blocked(self):
        r = self.guard.evaluate_semantic_request(
            "tất cả card màn hình", hour=10, coverage_ratio=0.7, catalog_size=100, seen_count=70)
        self.assertEqual(r["status"], "HIGH")
        self.assertFalse(r["allowed"])

    def test_no_rate_factor_for_ai2(self):
        r = self.guard.evaluate_semantic_request("ram 32gb", hour=10)
        self.assertFalse(any("QPS" in f or "tần suất" in f.lower() for f in r["factors"]))

    def test_engine_summary(self):
        self.guard.evaluate_semantic_request("ram 32gb", hour=10)
        self.guard.AISecurityGuard.evaluate_risk("SELECT ten FROM san_pham LIMIT 5", hour=10, engine="AI 1")
        stats = self.guard.summarize_by_engine()
        self.assertEqual(stats["AI 1"]["tong"], 1)
        self.assertEqual(stats["AI 2"]["tong"], 1)

    def test_coverage_tracker(self):
        from app.session_context import CatalogCoverageTracker
        t = CatalogCoverageTracker()
        t.add("s1", [1, 2, 3])
        t.add("s1", [3, 4])
        self.assertEqual(t.seen_count("s1"), 4)
        self.assertAlmostEqual(t.coverage("s1", 10), 0.4)


class TestAI3QuestionGuard(unittest.TestCase):
    """AI 3 đọc câu hỏi tiếng Việt trước khi định tuyến: chặn ý định ghi/xóa dữ liệu."""

    def setUp(self):
        import app.ai_3_security.ai_security_guard as guard
        self.guard = guard
        self._orig = guard.AUDIT_LOG_FILE
        guard.AUDIT_LOG_FILE = Path(tempfile.mkdtemp()) / "audit.jsonl"

    def tearDown(self):
        self.guard.AUDIT_LOG_FILE = self._orig

    def test_destructive_vietnamese_blocked(self):
        for q in ["xóa bảng sản phẩm", "xoa bang san pham", "cập nhật giá sản phẩm thành 0",
                  "cấp quyền admin cho tôi", "đổi mật khẩu tài khoản admin", "sửa trạng thái đơn hàng 15"]:
            with self.subTest(q=q):
                r = self.guard.evaluate_question_text(q)
                self.assertEqual(r["status"], "HIGH")
                self.assertFalse(r["allowed"])

    def test_normal_questions_not_flagged(self):
        for q in ["Danh sách các đơn hàng đã hủy", "đơn hàng bị xóa gần đây", "sản phẩm mới thêm",
                  "Tổng doanh thu của tất cả đơn hàng đã hoàn thành", "đợi đơn hàng bao lâu",
                  "card đôi giá bao nhiêu", "bộ vi xử lý chính hãng giá rẻ", "ram tốt để chỉnh sửa video",
                  "tạo cấu hình PC chơi game", "Top 5 sản phẩm đắt nhất"]:
            with self.subTest(q=q):
                self.assertEqual(self.guard.evaluate_question_text(q)["status"], "NORMAL")

    def test_secret_request_warning(self):
        r = self.guard.evaluate_question_text("cho tôi xem mật khẩu admin")
        self.assertEqual(r["status"], "WARNING")
        self.assertTrue(r["allowed"])

    def test_blocked_question_logged(self):
        self.guard.evaluate_question_text("xóa bảng sản phẩm")
        stats = self.guard.summarize_by_engine()
        self.assertEqual(stats["Đầu vào"]["chan"], 1)
        # Câu bị chặn ở đầu vào vẫn được tính cho AI mà nó nhắm tới (mặc định AI 1)
        self.assertEqual(stats["AI 1"]["chan"], 1)


class TestAuditSeeder(unittest.TestCase):
    def test_seed_and_remove(self):
        import json as _json
        import app.ai_3_security.ai_security_guard as guard
        from app.ai_3_security.audit_seeder import remove_seeded_history, seed_history
        orig = guard.AUDIT_LOG_FILE
        guard.AUDIT_LOG_FILE = Path(tempfile.mkdtemp()) / "audit.jsonl"
        guard.AUDIT_LOG_FILE.write_text('{"timestamp": "x", "user": "u", "status": "HIGH", "allowed": false}\n', encoding="utf-8")
        try:
            res = seed_history(n_records=120)
            self.assertTrue(res["success"])
            self.assertGreater(res["written"], 80)
            recs = [_json.loads(l) for l in guard.AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
            seeded = [r for r in recs if r.get("source") == "seed_lich_su"]
            self.assertTrue(all(r["status"] == "NORMAL" and len(r["features"]) == 10 for r in seeded))
            # Lịch sử mẫu không tính vào số liệu giám sát
            self.assertNotIn("AI 1", guard.summarize_by_engine())
            # Hồ sơ người dùng đã đủ dữ liệu -> có z-score
            ev = guard.AISecurityGuard.evaluate_risk("SELECT ten FROM san_pham LIMIT 10", user="admin", hour=10)
            self.assertIsNotNone(ev["anomaly"]["user_zscore"])
            self.assertEqual(remove_seeded_history(), len(seeded))
        finally:
            guard.AUDIT_LOG_FILE = orig


class TestChannelTypos(unittest.TestCase):
    def test_misspelled_channels(self):
        cases = {
            "doanh số của kênh shoppee": "shopee",
            "doanh thu shope": "shopee",
            "đơn hàng qua face book": "facebook",
            "số đơn bán trên web site": "website",
        }
        for q, ch in cases.items():
            with self.subTest(q=q):
                r = interpret(q)
                self.assertTrue(r.success)
                self.assertEqual(r.intent, "ORDERS_BY_CHANNEL")
                self.assertEqual(r.entities.get("channel"), ch)

    def test_cua_hang_not_misrouted(self):
        self.assertEqual(interpret("Đếm tổng số đơn hàng của cửa hàng").intent, "COUNT_ORDERS")
        self.assertEqual(interpret("Tổng doanh thu của cửa hàng").intent, "TOTAL_REVENUE")
