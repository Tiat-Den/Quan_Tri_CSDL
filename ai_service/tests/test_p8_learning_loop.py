"""
Kiểm thử P8 — HỌC TỪ CÂU HỎI CHƯA HIỂU (Human-in-the-loop) cho AI 1 và AI 2.

Phần 1 (không cần CSDL): che dữ liệu cá nhân, khóa gộp câu trùng, mô hình học máy học thêm mẫu,
ghi đè mô hình theo luồng, bí danh học thêm của Knowledge Graph, intent người dùng chọn từ gợi ý.

Phần 2 (cần CSDL lk_demo / LinhKien_DB đã chạy database/hoc_tu_cau_chua_hieu.sql + kết nối quản trị):
ghi nhật ký, duyệt, ràng buộc CHECK, phân quyền role text2sql_readonly, huấn luyện lại có kiểm soát.
Tự động BỎ QUA khi không kết nối được CSDL, chưa bật ALLOW_ADMIN_CONNECTION hoặc chưa có bảng.
"""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_2_semantic import knowledge_graph as kg_mod  # noqa: E402
from app.ai_1_text2sql import learning_loop as ll  # noqa: E402
from app.ai_1_text2sql import ml_intent_classifier as mic  # noqa: E402
from app.ai_2_semantic.knowledge_graph import HardwareKnowledgeGraph, get_knowledge_graph, use_knowledge_graph  # noqa: E402
from app.ai_1_text2sql.ml_intent_classifier import MLIntentClassifier, get_ml_classifier, use_classifier  # noqa: E402
from app.ai_1_text2sql.pipeline import interpret  # noqa: E402
from app.router import route  # noqa: E402
from app.ai_1_text2sql.text_normalizer import remove_diacritics  # noqa: E402

TABLES = '"LinhKien".cau_hoi_chua_hieu, "LinhKien".lich_su_huan_luyen'

# Mô hình chỉ dữ liệu gốc, huấn luyện một lần và dùng chung cho các bài kiểm thử không cần CSDL
_BASE_MODEL = None


def _base_model() -> MLIntentClassifier:
    global _BASE_MODEL
    if _BASE_MODEL is None:
        _BASE_MODEL = MLIntentClassifier()
        _BASE_MODEL.ensure_trained()
    return _BASE_MODEL


def _reset_globals():
    """Trả mô hình / Knowledge Graph toàn cục về trạng thái chưa khởi tạo."""
    mic._instance = None
    kg_mod._kg_instance = None


def _db_ready() -> bool:
    """Có kết nối quản trị + đã chạy script hoc_tu_cau_chua_hieu.sql hay chưa."""
    try:
        from app.db import get_connection
        conn = get_connection(use_admin=True)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('\"LinhKien\".cau_hoi_chua_hieu'), "
                            "to_regclass('\"LinhKien\".lich_su_huan_luyen')")
                a, b = cur.fetchone()
                return a is not None and b is not None
        finally:
            conn.close()
    except Exception:
        return False


DB_OK = _db_ready()
SKIP_MSG = "Cần CSDL + ALLOW_ADMIN_CONNECTION + đã chạy database/hoc_tu_cau_chua_hieu.sql"


# ==============================================================================
# PHẦN 1. KIỂM THỬ THUẦN (KHÔNG CẦN CSDL)
# ==============================================================================
class TestMaskPII(unittest.TestCase):
    def test_masks_email_and_phones(self):
        """Email và các kiểu viết số điện thoại Việt Nam đều bị che trước khi lưu."""
        cases = {
            "liên hệ huy.ngo+test@gmail.com nhé": "<email>",
            "gọi 0912345678 giúp": "<sđt>",
            "sđt 0912 345 678": "<sđt>",
            "số +84 912 345 678": "<sđt>",
            "số 0912.345.678": "<sđt>",
            "số 84912345678": "<sđt>",
        }
        for text, token in cases.items():
            with self.subTest(text=text):
                out = ll.mask_pii(text)
                self.assertIn(token, out)
                self.assertNotRegex(out, r"\d{3}[\s.]?\d{3}[\s.]?\d{3}")
                self.assertNotIn("@", out)

    def test_masks_long_digit_strings(self):
        """Dãy số dài (CCCD, số tài khoản...) bị che."""
        out = ll.mask_pii("cccd 079203012345 và stk 123456789012345")
        self.assertNotRegex(out, r"\d{9,}")
        self.assertIn("<số>", out)

    def test_ordinary_numbers_kept(self):
        """Số bình thường trong câu hỏi (top N, giá, năm) KHÔNG bị che."""
        for text in ["top 5 sản phẩm đắt nhất", "giá trên 5 triệu", "doanh thu năm 2025",
                     "giá từ 10000000 đến 20000000", "doanh thu tháng 05 2025", "card 12GB giá 8400000"]:
            with self.subTest(text=text):
                self.assertEqual(ll.mask_pii(text), text)

    def test_empty_input(self):
        self.assertEqual(ll.mask_pii(None), "")
        self.assertEqual(ll.mask_pii(""), "")


class TestNormalizeKey(unittest.TestCase):
    def test_variants_share_same_key(self):
        """Câu khác nhau về hoa thường, dấu câu, khoảng trắng -> cùng một khóa gộp."""
        variants = ["Nhân viên nào bán GIỎI nhất?",
                    "  nhân   viên nào, bán giỏi nhất!!! ", "NHÂN VIÊN NÀO BÁN GIỎI NHẤT..."]
        keys = {ll.normalize_key(v) for v in variants}
        self.assertEqual(keys, {"nhân viên nào bán giỏi nhất"})

    def test_diacritics_kept_to_avoid_false_merge(self):
        """Giữ dấu tiếng Việt: 'bán chạy' và 'bàn chạy' là hai câu khác nhau."""
        self.assertNotEqual(ll.normalize_key("bán chạy"), ll.normalize_key("bàn chạy"))

    def test_keeps_pii_placeholders_and_truncates(self):
        self.assertEqual(ll.normalize_key("gọi <sđt> nhé"), "gọi <sđt> nhé")
        self.assertLessEqual(len(ll.normalize_key("a " * 400)), 300)
        self.assertEqual(ll.normalize_key(None), "")

    def test_different_questions_different_keys(self):
        self.assertNotEqual(ll.normalize_key("đơn hủy"), ll.normalize_key("đơn hủy nhiều nhất"))


class TestMLExtraSamples(unittest.TestCase):
    PHRASE = "quả táo xanh cạnh lá chuối vàng"

    def test_learns_new_phrasing(self):
        """Mẫu Admin đã duyệt (extra_samples) giúp mô hình hiểu cách diễn đạt mới."""
        base_top = _base_model().predict_proba(self.PHRASE)[0][0]
        self.assertNotEqual(base_top, "TOTAL_REVENUE")
        extras = [(self.PHRASE, "TOTAL_REVENUE"), (self.PHRASE + " nhé", "TOTAL_REVENUE"),
                  ("táo xanh lá chuối vàng", "TOTAL_REVENUE")]
        cand = MLIntentClassifier(extra_samples=extras)
        cand.ensure_trained()
        self.assertEqual(cand.predict_proba(self.PHRASE)[0][0], "TOTAL_REVENUE")
        self.assertEqual(cand.n_samples, cand.n_base_samples + 3)

    def test_base_dataset_excludes_extras(self):
        """base_dataset() chỉ trả dữ liệu gốc -> dùng kiểm tra mô hình mới không 'quên' kiến thức cũ."""
        cand = MLIntentClassifier(extra_samples=[(self.PHRASE, "TOTAL_REVENUE"), ("", "X"), ("abc", "")])
        self.assertEqual(len(cand.extra_samples), 1)  # mẫu rỗng bị loại
        texts, labels = cand.base_dataset()
        base_texts, base_labels = MLIntentClassifier().base_dataset()
        self.assertEqual(texts, base_texts)
        self.assertEqual(labels, base_labels)
        self.assertNotIn(self.PHRASE, texts)
        self.assertGreater(len(texts), 50)


class TestThreadLocalOverride(unittest.TestCase):
    def setUp(self):
        _reset_globals()

    def tearDown(self):
        _reset_globals()

    def test_use_classifier_only_affects_current_thread(self):
        """Mô hình ứng viên chỉ có hiệu lực trong luồng đánh giá, người dùng khác vẫn dùng mô hình đang chạy."""
        global_model = MLIntentClassifier()
        candidate = MLIntentClassifier()
        mic._instance = global_model
        seen = {}
        with use_classifier(candidate):
            self.assertIs(get_ml_classifier(), candidate)
            t = threading.Thread(target=lambda: seen.setdefault("other", get_ml_classifier()))
            t.start()
            t.join()
        self.assertIs(seen["other"], global_model)
        self.assertIs(get_ml_classifier(), global_model)

    def test_use_knowledge_graph_only_affects_current_thread(self):
        global_kg = HardwareKnowledgeGraph()
        cand_kg = HardwareKnowledgeGraph()
        kg_mod._kg_instance = global_kg
        seen = {}
        with use_knowledge_graph(cand_kg):
            self.assertIs(get_knowledge_graph(), cand_kg)
            t = threading.Thread(target=lambda: seen.setdefault("other", get_knowledge_graph()))
            t.start()
            t.join()
        self.assertIs(seen["other"], global_kg)
        self.assertIs(get_knowledge_graph(), global_kg)

    def test_nested_override_restores_previous(self):
        a, b = MLIntentClassifier(), MLIntentClassifier()
        mic._instance = MLIntentClassifier()
        with use_classifier(a):
            with use_classifier(b):
                self.assertIs(get_ml_classifier(), b)
            self.assertIs(get_ml_classifier(), a)


class TestKGLearnedAliases(unittest.TestCase):
    def setUp(self):
        self.kg = HardwareKnowledgeGraph()
        self.need = "render video"
        self.base = list(self.kg.needs[self.need].aliases)

    def test_learned_alias_detected(self):
        self.assertNotIn(self.need, [n.name for n in self.kg.detect_needs("máy để edit clip tiktok")])
        self.assertEqual(self.kg.apply_learned_aliases({self.need: ["edit clip"]}), 1)
        self.assertIn(self.need, [n.name for n in self.kg.detect_needs("máy để edit clip tiktok")])

    def test_idempotent(self):
        """Gọi nhiều lần không nhân bản bí danh (luôn dựng lại từ bí danh gốc)."""
        for _ in range(3):
            self.kg.apply_learned_aliases({self.need: ["edit clip"]})
        self.assertEqual(self.kg.needs[self.need].aliases, self.base + ["edit clip"])
        # Gỡ cụm từ học -> trở về bí danh gốc
        self.assertEqual(self.kg.apply_learned_aliases({}), 0)
        self.assertEqual(self.kg.needs[self.need].aliases, self.base)
        self.assertEqual(self.kg.learned_aliases, {})

    def test_ignores_unknown_need_and_short_phrase(self):
        n = self.kg.apply_learned_aliases({"nhu cầu không tồn tại": ["abc xyz"], self.need: ["ab", "  ", None]})
        self.assertEqual(n, 0)
        self.assertNotIn("nhu cầu không tồn tại", self.kg.needs)
        self.assertEqual(self.kg.needs[self.need].aliases, self.base)

    def test_no_duplicate_of_existing_alias(self):
        """Cụm từ trùng bí danh gốc / tên nhu cầu (kể cả khác dấu, hoa thường) không được thêm lại."""
        dup = [self.base[0].upper(), remove_diacritics(self.base[0]), "Render Video", "edit clip", "EDIT  CLIP"]
        self.assertEqual(self.kg.apply_learned_aliases({self.need: dup}), 1)
        self.assertEqual(self.kg.needs[self.need].aliases, self.base + ["edit clip"])


class TestForcedIntentAndSuggestions(unittest.TestCase):
    def setUp(self):
        _reset_globals()
        mic._instance = _base_model()  # không phụ thuộc CSDL

    def tearDown(self):
        _reset_globals()

    def test_whitelisted_forced_intent(self):
        """Người dùng bấm gợi ý 'Ý bạn là ...' -> dùng intent đó, matched_rule = user_choice."""
        res = interpret("nhân viên nào bán giỏi nhất", forced_intent="EMPLOYEE_PERFORMANCE")
        self.assertTrue(res.success)
        self.assertEqual(res.intent, "EMPLOYEE_PERFORMANCE")
        self.assertEqual(res.matched_rule, "user_choice")
        self.assertIsNotNone(res.sql)

    def test_forced_intent_still_checks_unused_entities(self):
        """Intent ép buộc vẫn qua chính sách thực thể thừa (không trả kết quả sai lệch)."""
        res = interpret("doanh thu hãng ASUS", forced_intent="TOTAL_REVENUE")
        if "brand_name" in res.entities:
            self.assertFalse(res.success)

    def test_non_whitelisted_forced_intent_ignored(self):
        for bad in ["DROP_ALL", "OUT_OF_SCOPE", "UNKNOWN", "employee_performance"]:
            with self.subTest(bad=bad):
                res = interpret("thời tiết hôm nay thế nào", forced_intent=bad)
                self.assertNotEqual(res.matched_rule, "user_choice")
                self.assertEqual(res.intent, "UNKNOWN")  # vẫn phân loại bình thường -> ngoài phạm vi
                self.assertFalse(res.success)

    def test_ml_suggestions(self):
        sugg = ll.ml_suggestions("nhân viên nào bán giỏi nhất")
        self.assertLessEqual(len(sugg), 3)
        self.assertTrue(sugg)
        for s in sugg:
            self.assertIn(s["intent"], ll.learnable_intents())
            self.assertNotEqual(s["intent"], mic.OUT_OF_SCOPE)
            self.assertTrue(0.0 <= s["p"] <= 1.0)
        self.assertEqual(ll.ml_suggestions("select * from users; --"), [])
        self.assertEqual(ll.ml_suggestions(""), [])


class TestPureValidation(unittest.TestCase):
    def test_log_unknown_rejects_without_db(self):
        """Lý do không hợp lệ / câu rỗng bị từ chối ngay, không cần tới CSDL."""
        self.assertFalse(ll.log_unknown("câu gì đó", "ly_do_la", background=False))
        self.assertFalse(ll.log_unknown("   ", "ngoai_pham_vi", background=False))
        self.assertFalse(ll.log_unknown("", "ngoai_pham_vi", background=False))
        self.assertFalse(ll.log_unknown("?!", "ngoai_pham_vi", background=False))

    def test_review_validation_before_db(self):
        self.assertFalse(ll.review(1, "intent", "", label="TOTAL_REVENUE")["success"])
        self.assertFalse(ll.review(1, "intent", "admin", label="DROP_ALL")["success"])
        self.assertFalse(ll.review(1, "nhu_cau", "admin", label="không có", phrase="abc def")["success"])
        self.assertFalse(ll.review(1, "nhu_cau", "admin", label="render video", phrase=" ab ")["success"])
        self.assertFalse(ll.review(1, "nhu_cau", "admin", label="render video", phrase="x" * 121)["success"])
        self.assertFalse(ll.review(1, "xoa_het", "admin")["success"])
        self.assertFalse(ll.list_questions("trang_thai_la")["success"])


# ==============================================================================
# PHẦN 2. KIỂM THỬ CẦN CSDL
# ==============================================================================
@unittest.skipUnless(DB_OK, SKIP_MSG)
class _DBTestBase(unittest.TestCase):
    def setUp(self):
        self._truncate()
        _reset_globals()

    def tearDown(self):
        self._truncate()
        _reset_globals()

    @staticmethod
    def _truncate():
        from app.db import get_connection
        conn = get_connection(use_admin=True)
        try:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE {TABLES} RESTART IDENTITY")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _admin(sql, params=()):
        return ll._admin_fetch(sql, params)

    @staticmethod
    def _admin_exec(sql, params=()):
        from app.db import get_connection
        conn = get_connection(use_admin=True)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _log(self, q, reason="ngoai_pham_vi", **kw):
        self.assertTrue(ll.log_unknown(q, reason, background=False, **kw))
        rows = self._admin('SELECT id FROM "LinhKien".cau_hoi_chua_hieu WHERE cau_chuan_hoa = %s',
                           (ll.normalize_key(ll.mask_pii(q.strip())),))
        self.assertEqual(len(rows), 1, f"Không ghi được câu: {q}")
        return rows[0]["id"]

    def _teach_intent(self, q, label):
        rid = self._log(q)
        res = ll.review(rid, "intent", "tester", label=label)
        self.assertTrue(res["success"], res)
        return rid


class TestDBLogging(_DBTestBase):
    def test_insert_and_dedupe(self):
        """Câu trùng (khác hoa thường / dấu câu / khoảng trắng) được gộp, so_lan_gap tăng dần."""
        rid = self._log("Nhân viên nào bán giỏi nhất?", suggestions=[{"intent": "EMPLOYEE_PERFORMANCE", "p": 0.4}],
                        user="khach1")
        self._log("nhân viên nào bán giỏi nhất", user="khach2")
        self._log("  NHÂN VIÊN NÀO BÁN GIỎI NHẤT!!! ", user="khach3")
        self.assertTrue(ll.record_choice("nhân viên nào bán giỏi nhất", "EMPLOYEE_PERFORMANCE", background=False))
        rows = self._admin('SELECT * FROM "LinhKien".cau_hoi_chua_hieu')
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["id"], rid)
        self.assertEqual(r["so_lan_gap"], 3)
        self.assertEqual(r["trang_thai"], "cho_duyet")
        self.assertEqual(r["nguoi_hoi_cuoi"], "khach3")
        self.assertEqual(r["intent_nguoi_dung_chon"], "EMPLOYEE_PERFORMANCE")
        self.assertEqual(r["goi_y_ml"][0]["intent"], "EMPLOYEE_PERFORMANCE")  # gợi ý rỗng không ghi đè
        self.assertFalse(r["da_huan_luyen"])
        self.assertGreaterEqual(r["lan_cuoi"], r["lan_dau"])

    def test_pii_masked_in_storage(self):
        self._log("gửi báo giá cho tôi qua huy@gmail.com hoặc 0912 345 678")
        r = self._admin('SELECT cau_hoi, cau_chuan_hoa FROM "LinhKien".cau_hoi_chua_hieu')[0]
        self.assertNotIn("huy@gmail.com", r["cau_hoi"])
        self.assertNotIn("0912", r["cau_hoi"])
        self.assertIn("<email>", r["cau_hoi"])
        self.assertIn("<sđt>", r["cau_hoi"])
        self.assertNotRegex(r["cau_chuan_hoa"], r"\d{6,}")

    def test_invalid_reason_and_chosen_intent(self):
        self.assertFalse(ll.log_unknown("câu bất kỳ", "bi_ai3_chan", background=False))
        self.assertEqual(self._admin('SELECT count(*) AS n FROM "LinhKien".cau_hoi_chua_hieu')[0]["n"], 0)
        self._log("câu gợi ý lạ", reason="hoi_lai")
        self.assertFalse(ll.record_choice("câu gợi ý lạ", "DROP_ALL", background=False))
        r = self._admin('SELECT ly_do, intent_nguoi_dung_chon FROM "LinhKien".cau_hoi_chua_hieu')[0]
        self.assertEqual(r["ly_do"], "hoi_lai")
        self.assertIsNone(r["intent_nguoi_dung_chon"])

    def test_choice_votes_majority_and_no_count_bump(self):
        """Phiếu chọn gợi ý: nhiều phiếu nhất thắng, không tăng số lần gặp, không đổi câu đã duyệt."""
        q = "nhân viên nào bán giỏi nhất"
        rid = self._log(q)
        for it in ("EMPLOYEE_PERFORMANCE", "TOTAL_REVENUE", "EMPLOYEE_PERFORMANCE"):
            ll.record_choice(q, it, background=False)
        r = self._admin('SELECT so_lan_gap, lua_chon_dem, intent_nguoi_dung_chon FROM "LinhKien".cau_hoi_chua_hieu')[0]
        self.assertEqual(r["so_lan_gap"], 1)
        self.assertEqual(r["lua_chon_dem"], {"EMPLOYEE_PERFORMANCE": 2, "TOTAL_REVENUE": 1})
        self.assertEqual(r["intent_nguoi_dung_chon"], "EMPLOYEE_PERFORMANCE")
        ll.review(rid, "bo_qua", "admin")
        for _ in range(3):
            ll.record_choice(q, "TOTAL_REVENUE", background=False)
        r = self._admin('SELECT intent_nguoi_dung_chon FROM "LinhKien".cau_hoi_chua_hieu')[0]
        self.assertEqual(r["intent_nguoi_dung_chon"], "EMPLOYEE_PERFORMANCE")
        # Câu chưa từng được ghi -> không tạo dòng mới
        ok = self._admin('SELECT "LinhKien".fn_ghi_lua_chon_goi_y(%s, %s) AS ok', ("câu chưa có", "TOTAL_REVENUE"))
        self.assertFalse(ok[0]["ok"])

    def test_background_logging(self):
        """Ghi nền (luồng phụ) không chặn luồng chính và vẫn ghi được."""
        self.assertTrue(ll.log_unknown("câu ghi nền thử nghiệm", "ai2_khong_ket_qua"))
        import time
        for _ in range(50):
            if self._admin('SELECT count(*) AS n FROM "LinhKien".cau_hoi_chua_hieu')[0]["n"]:
                break
            time.sleep(0.1)
        self.assertEqual(self._admin('SELECT count(*) AS n FROM "LinhKien".cau_hoi_chua_hieu')[0]["n"], 1)

    def test_count_and_list(self):
        self._log("câu thứ nhất chưa hiểu")
        self._log("câu thứ hai chưa hiểu")
        self._log("câu thứ hai chưa hiểu")
        c = ll.count_by_status()
        self.assertTrue(c["success"])
        self.assertEqual(c["counts"]["cho_duyet"], 2)
        self.assertEqual(c["trained"], 0)
        rows = ll.list_questions("cho_duyet")["rows"]
        self.assertEqual([r["so_lan_gap"] for r in rows], [2, 1])  # câu hay gặp lên trước


class TestDBReview(_DBTestBase):
    def test_review_validation(self):
        rid = self._log("câu cần duyệt thử")
        self.assertIn("không có mẫu SQL", ll.review(rid, "intent", "admin", label="DROP_ALL")["error"])
        self.assertIn("Knowledge Graph", ll.review(rid, "nhu_cau", "admin", label="bay lên trời", phrase="abc")["error"])
        self.assertIn("Cụm từ", ll.review(rid, "nhu_cau", "admin", label="render video", phrase="ab")["error"])
        self.assertIn("không hợp lệ", ll.review(rid, "xoa", "admin")["error"])
        self.assertIn("người duyệt", ll.review(rid, "bo_qua", "   ")["error"])
        self.assertIn("Không tìm thấy", ll.review(999999, "bo_qua", "admin")["error"])
        r = self._admin('SELECT trang_thai FROM "LinhKien".cau_hoi_chua_hieu WHERE id = %s', (rid,))[0]
        self.assertEqual(r["trang_thai"], "cho_duyet")

    def test_status_transitions(self):
        rid = self._log("máy để edit clip tiktok", reason="ai2_khong_ket_qua")
        get = lambda: self._admin('SELECT * FROM "LinhKien".cau_hoi_chua_hieu WHERE id = %s', (rid,))[0]  # noqa

        self.assertEqual(ll.review(rid, "nhu_cau", "admin", label="render video", phrase="  Edit   CLIP ")["status"],
                         "da_gan_nhan")
        r = get()
        self.assertEqual((r["loai_nhan"], r["nhan"], r["cum_tu_hoc"]), ("nhu_cau", "render video", "edit clip"))
        self.assertEqual(r["nguoi_duyet"], "admin")
        self.assertIsNotNone(r["thoi_diem_duyet"])

        self.assertTrue(ll.review(rid, "intent", "admin2", label="TOTAL_REVENUE", note="ghi chú")["success"])
        r = get()
        self.assertEqual((r["loai_nhan"], r["nhan"], r["cum_tu_hoc"], r["ghi_chu"]),
                         ("intent", "TOTAL_REVENUE", None, "ghi chú"))

        for action in ("can_mau_sql_moi", "bo_qua"):
            self.assertEqual(ll.review(rid, action, "admin")["status"], action)
            r = get()
            self.assertIsNone(r["loai_nhan"])
            self.assertIsNone(r["nhan"])
            self.assertEqual(r["nguoi_duyet"], "admin")

        self.assertEqual(ll.review(rid, "mo_lai", "admin")["status"], "cho_duyet")
        r = get()
        self.assertEqual(r["trang_thai"], "cho_duyet")
        self.assertIsNone(r["nguoi_duyet"])
        self.assertIsNone(r["thoi_diem_duyet"])
        self.assertFalse(r["da_huan_luyen"])

    def test_relabel_resets_trained_flag(self):
        rid = self._teach_intent("câu đã từng huấn luyện", "TOTAL_REVENUE")
        self._admin_exec('UPDATE "LinhKien".cau_hoi_chua_hieu SET da_huan_luyen = TRUE WHERE id = %s', (rid,))
        self.assertEqual(ll.count_by_status()["trained"], 1)
        ll.review(rid, "intent", "admin", label="SALES_BY_MONTH")
        c = ll.count_by_status()
        self.assertEqual(c["trained"], 0)
        self.assertEqual(c["labeled_untrained"], 1)


class TestDBConstraints(_DBTestBase):
    def _insert_raw(self, **cols):
        import psycopg2
        base = {"cau_hoi": "x câu", "cau_chuan_hoa": "x cau", "ly_do": "ngoai_pham_vi"}
        base.update(cols)
        keys = ", ".join(base)
        ph = ", ".join(["%s"] * len(base))
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self._admin_exec(f'INSERT INTO "LinhKien".cau_hoi_chua_hieu ({keys}) VALUES ({ph})', tuple(base.values()))

    def test_check_constraints(self):
        cases = {
            "gán nhãn thiếu nhãn": dict(trang_thai="da_gan_nhan", nguoi_duyet="a", thoi_diem_duyet="2026-01-01"),
            "có nhãn nhưng chờ duyệt": dict(loai_nhan="intent", nhan="TOTAL_REVENUE"),
            "nhu cầu thiếu cụm từ": dict(trang_thai="da_gan_nhan", loai_nhan="nhu_cau", nhan="render video",
                                        cum_tu_hoc=" a ", nguoi_duyet="a", thoi_diem_duyet="2026-01-01"),
            "intent sai định dạng": dict(trang_thai="da_gan_nhan", loai_nhan="intent", nhan="drop table",
                                        nguoi_duyet="a", thoi_diem_duyet="2026-01-01"),
            "bỏ qua không có người duyệt": dict(trang_thai="bo_qua"),
            "huấn luyện khi chưa gán nhãn": dict(da_huan_luyen=True),
            "lý do lạ": dict(ly_do="bi_chan"),
            "trạng thái lạ": dict(trang_thai="xoa"),
            "số lần gặp 0": dict(so_lan_gap=0),
            "gợi ý không phải mảng": dict(goi_y_ml='{"a": 1}'),
            "intent chọn sai định dạng": dict(intent_nguoi_dung_chon="x; drop"),
            "loại nhãn lạ": dict(loai_nhan="khac"),
        }
        for name, cols in cases.items():
            with self.subTest(name=name):
                self._insert_raw(**cols)

    def test_history_check(self):
        import psycopg2
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self._admin_exec('INSERT INTO "LinhKien".lich_su_huan_luyen (nguoi_thuc_hien, so_mau_goc, '
                             'so_mau_hoc_intent, so_cum_tu_nhu_cau, ket_qua) VALUES (%s, 1, 0, 0, %s)',
                             ("a", "khac"))

    def test_function_rejects_short_key(self):
        rows = self._admin('SELECT "LinhKien".fn_ghi_cau_hoi_chua_hieu(%s, %s, %s) AS id', ("x", "x", "ngoai_pham_vi"))
        self.assertIsNone(rows[0]["id"])


class TestDBPrivileges(_DBTestBase):
    """Role chatbot text2sql_readonly không đọc / ghi được bảng học, chỉ gọi được hàm đọc mẫu đã duyệt."""

    def _ro_exec(self, sql, params=()):
        from app.db import get_connection
        conn = get_connection(use_admin=False)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        finally:
            conn.rollback()
            conn.close()

    def _assert_denied(self, sql, params=()):
        import psycopg2
        with self.assertRaises(psycopg2.Error) as ctx:
            self._ro_exec(sql, params)
        self.assertEqual(ctx.exception.pgcode, "42501", str(ctx.exception))

    def test_readonly_cannot_read_tables(self):
        self._assert_denied('SELECT * FROM "LinhKien".cau_hoi_chua_hieu')
        self._assert_denied('SELECT * FROM "LinhKien".lich_su_huan_luyen')

    def test_readonly_cannot_call_write_function(self):
        self._assert_denied('SELECT "LinhKien".fn_ghi_cau_hoi_chua_hieu(%s, %s, %s)', ("hack", "hack", "ngoai_pham_vi"))
        self.assertEqual(self._admin('SELECT count(*) AS n FROM "LinhKien".cau_hoi_chua_hieu')[0]["n"], 0)

    def test_readonly_can_read_approved_samples_only(self):
        rid = self._teach_intent("câu đã duyệt và huấn luyện", "TOTAL_REVENUE")
        self._admin_exec('UPDATE "LinhKien".cau_hoi_chua_hieu SET da_huan_luyen = TRUE WHERE id = %s', (rid,))
        self._teach_intent("câu đã duyệt chưa huấn luyện", "SALES_BY_MONTH")
        self._log("câu chờ duyệt bí mật")
        rows = self._ro_exec('SELECT cau_hoi, loai_nhan, nhan FROM "LinhKien".fn_mau_hoc_da_duyet()')
        self.assertEqual(rows, [("câu đã duyệt và huấn luyện", "intent", "TOTAL_REVENUE")])
        intents, needs = ll.load_trained_samples()
        self.assertEqual(intents, [("câu đã duyệt và huấn luyện", "TOTAL_REVENUE")])
        self.assertEqual(needs, {})

    def test_privilege_catalog(self):
        r = self._admin(
            "SELECT has_table_privilege('text2sql_readonly', '\"LinhKien\".cau_hoi_chua_hieu', 'SELECT') AS t, "
            "has_function_privilege('text2sql_readonly', "
            "'\"LinhKien\".fn_ghi_cau_hoi_chua_hieu(text,text,text,jsonb,text)', 'EXECUTE') AS w, "
            "has_function_privilege('text2sql_readonly', '\"LinhKien\".fn_mau_hoc_da_duyet()', 'EXECUTE') AS r")[0]
        self.assertEqual((r["t"], r["w"], r["r"]), (False, False, True))


class TestDBRetrain(_DBTestBase):
    def test_nothing_to_train(self):
        res = ll.retrain("tester")
        self.assertFalse(res["success"])
        self.assertIn("Chưa có câu", res["error"])

    def test_accepted_intent_sample(self):
        """Dạy 'nhân viên nào bán giỏi nhất' = EMPLOYEE_PERFORMANCE -> được áp dụng và AI 1 trả lời được."""
        q = "nhân viên nào bán giỏi nhất"
        self.assertFalse(interpret(q).success)
        rid = self._teach_intent(q, "EMPLOYEE_PERFORMANCE")
        rep = ll.retrain("tester")
        self.assertTrue(rep["success"], rep)
        self.assertTrue(rep["accepted"], rep.get("note"))
        self.assertGreaterEqual(rep["correct_new"], rep["correct_old"])
        self.assertEqual(rep["learned_ok"], 1)
        self.assertEqual(rep["broken"], [])

        res = interpret(q)
        self.assertTrue(res.success)
        self.assertEqual(res.intent, "EMPLOYEE_PERFORMANCE")
        self.assertEqual(get_ml_classifier().n_samples, get_ml_classifier().n_base_samples + 1)

        r = self._admin('SELECT da_huan_luyen FROM "LinhKien".cau_hoi_chua_hieu WHERE id = %s', (rid,))[0]
        self.assertTrue(r["da_huan_luyen"])
        hist = ll.training_history()["rows"]
        self.assertEqual(hist[0]["ket_qua"], "ap_dung")
        self.assertEqual(hist[0]["so_mau_hoc_intent"], 1)

        # Khởi động lại web: mô hình dựng lại từ CSDL vẫn nhớ câu đã học
        _reset_globals()
        self.assertTrue(interpret(q).success)

    def test_accepted_need_phrase(self):
        """Dạy cụm 'edit clip' cho nhu cầu 'render video' -> bộ định tuyến chuyển câu sang AI 2."""
        q = "máy để edit clip tiktok"
        self.assertNotEqual(route(q).engine, "ai2")
        rid = self._log(q, reason="ai2_khong_ket_qua")
        self.assertTrue(ll.review(rid, "nhu_cau", "tester", label="render video", phrase="edit clip")["success"])
        rep = ll.retrain("tester")
        self.assertTrue(rep["accepted"], rep.get("note"))
        self.assertEqual(rep["phrase_ok"], 1)
        decision = route(q)
        self.assertEqual(decision.engine, "ai2")
        self.assertIn("render video", decision.detected_needs)
        # Khởi động lại: Knowledge Graph nạp lại cụm từ đã học từ CSDL
        _reset_globals()
        self.assertEqual(route(q).engine, "ai2")

    def test_rejected_when_gold_drops(self):
        """Nhãn sai làm giảm số câu chuẩn đúng -> từ chối, giữ mô hình cũ, câu vẫn chưa huấn luyện."""
        old_model = get_ml_classifier()
        old_model.ensure_trained()
        # Câu chuẩn chỉ trả lời được nhờ ML -> gán nhãn sai có chủ đích (kèm biến thể) để làm hỏng
        poisoned = []
        for c in ll.load_gold_cases():
            if c["intent"] == "UNKNOWN":
                continue
            r = interpret(c["q"])
            if r.success and r.matched_rule.startswith("ml_"):
                wrong = "LOW_STOCK" if c["intent"] != "LOW_STOCK" else "TOTAL_REVENUE"
                poisoned.append((c["q"], wrong))
        self.assertGreaterEqual(len(poisoned), 3, "Không đủ câu chuẩn phụ thuộc ML để kiểm thử")
        # Kèm ví dụ thật đã quan sát: dạy câu đơn hủy làm hỏng câu 'đơn đến từ sàn nào là nhiều'
        poisoned += [("cho xem mấy đơn bị hủy giùm", "ORDERS_BY_STATUS"),
                     ("đơn bị hủy có những đơn nào", "ORDERS_BY_STATUS")]
        ids = []
        for q, lb in poisoned:
            ids.append(self._teach_intent(q, lb))
            for suffix in (" nhé", " giúp mình với"):
                ids.append(self._teach_intent(q + suffix, lb))

        before = {c["q"]: interpret(c["q"]).intent for c in ll.load_gold_cases()}
        rep = ll.retrain("tester")
        self.assertTrue(rep["success"], rep)
        self.assertFalse(rep["accepted"])
        self.assertLess(rep["correct_new"], rep["correct_old"])
        self.assertTrue(rep["broken"])
        self.assertIn("Từ chối", rep["note"])

        self.assertIs(get_ml_classifier(), old_model)  # mô hình toàn cục không đổi
        self.assertEqual({c["q"]: interpret(c["q"]).intent for c in ll.load_gold_cases()}, before)
        rows = self._admin('SELECT count(*) FILTER (WHERE da_huan_luyen) AS t, count(*) AS n '
                           'FROM "LinhKien".cau_hoi_chua_hieu')[0]
        self.assertEqual((rows["t"], rows["n"]), (0, len(ids)))
        hist = ll.training_history()["rows"]
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["ket_qua"], "tu_choi")
        self.assertLess(float(hist[0]["do_chinh_xac_moi"]), float(hist[0]["do_chinh_xac_cu"]))

    def test_unteach_reverts_live_model(self):
        """Mở lại câu duy nhất đã học rồi Huấn luyện lại -> mô hình trở về dữ liệu gốc."""
        q = "nhân viên nào bán giỏi nhất"
        rid = self._teach_intent(q, "EMPLOYEE_PERFORMANCE")
        self.assertTrue(ll.retrain("tester")["accepted"])
        self.assertTrue(interpret(q).success)
        self.assertEqual(ll.live_learned_count(), 1)
        self.assertTrue(ll.review(rid, "mo_lai", "tester")["success"])
        rep = ll.retrain("tester")
        self.assertTrue(rep["success"], rep)
        self.assertTrue(rep["accepted"], rep.get("note"))
        self.assertEqual(rep["n_intent_samples"], 0)
        self.assertFalse(interpret(q).success)
        self.assertEqual(ll.live_learned_count(), 0)

    def test_labels_changed_during_retrain_aborts(self):
        """Admin khác đổi nhãn trong lúc đang chấm điểm -> hủy, không đánh dấu mẫu chưa kiểm tra là đã học."""
        rid = self._teach_intent("nhân viên nào bán giỏi nhất", "EMPLOYEE_PERFORMANCE")
        real_eval = ll.evaluate_gold
        calls = {"n": 0}

        def eval_and_relabel(cases):
            calls["n"] += 1
            if calls["n"] == 2:   # đã đọc nhãn, đang chấm mô hình ứng viên
                ll.review(rid, "intent", "admin2", label="TOTAL_REVENUE")
            return real_eval(cases)

        ll.evaluate_gold = eval_and_relabel
        try:
            rep = ll.retrain("tester")
        finally:
            ll.evaluate_gold = real_eval
        self.assertFalse(rep["success"])
        self.assertIn("đổi nhãn", rep["error"])
        r = self._admin('SELECT nhan, da_huan_luyen FROM "LinhKien".cau_hoi_chua_hieu WHERE id = %s', (rid,))[0]
        self.assertEqual((r["nhan"], r["da_huan_luyen"]), ("TOTAL_REVENUE", False))
        self.assertEqual(ll.training_history()["rows"], [])
        self.assertEqual(ll.live_learned_count(), 0)

    def test_concurrent_retrain_locked(self):
        """Hai Admin bấm cùng lúc -> lượt thứ hai bị từ chối ngay."""
        self.assertTrue(ll._retrain_lock.acquire(blocking=False))
        try:
            res = ll.retrain("admin2")
            self.assertFalse(res["success"])
            self.assertIn("Đang có", res["error"])
        finally:
            ll._retrain_lock.release()


if __name__ == "__main__":
    unittest.main()
