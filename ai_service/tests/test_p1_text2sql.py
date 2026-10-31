"""
Kiểm thử nghiệm thu toàn diện cho Phase P1 (AI 1 Text-to-SQL Engine).
Bao gồm A1-1 đến A1-8: IntentResult giàu thông tin, chuẩn hóa số, bóc tách giá Decimal,
ghép nhiều điều kiện (composite filters), chính sách điều kiện thừa và kiểm soát giới hạn.
"""
import sys
import os
import unittest
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_1_text2sql.text_normalizer import normalize_text, remove_diacritics
from app.ai_1_text2sql.intent_classifier import classify_intent, IntentResult
from app.ai_1_text2sql.entity_extractor import (
    extract_price_condition,
    extract_top_n,
    extract_category,
    extract_brand,
    extract_order_status,
    extract_channel,
    extract_payment_method,
    parse_vietnamese_number,
)
from app.ai_1_text2sql.pipeline import interpret


class TestPhase1TextToSQL(unittest.TestCase):

    def test_a1_1_intent_result_rich_and_tuple_unpack(self):
        """A1-1: classify_intent trả về IntentResult nhưng hỗ trợ unpacking (intent, conf)"""
        res = classify_intent("bán chạy nhất")
        self.assertIsInstance(res, IntentResult)
        self.assertEqual(res.intent, "BEST_SELLING_PRODUCTS")
        self.assertEqual(res.confidence, 1.0)
        self.assertTrue(len(res.matched_rule) > 0)

        # Kiểm tra unpacking cũ
        intent, conf = classify_intent("bán chạy nhất")
        self.assertEqual(intent, "BEST_SELLING_PRODUCTS")
        self.assertEqual(conf, 1.0)

    def test_a1_2_normalization_and_unaccented_category(self):
        """A1-2: Chuẩn hóa bảo toàn dấu phẩy số; nhận diện danh mục không dấu và tiếng Anh"""
        norm = normalize_text("Giá 1,5 triệu và 5.000.000")
        self.assertIn("1,5", norm)
        self.assertIn("5.000.000", norm)

        # Nhận diện danh mục không dấu
        cat_tests = [
            ("Liệt kê tất cả man hinh", "Màn hình"),
            ("Danh sach ban phim", "Bàn phím"),
            ("tim chuot", "Chuột"),
            ("Danh sách card đồ họa gpu", "VGA"),
            ("tìm nguồn psu", "Nguồn"),
        ]
        for q, exp_cat in cat_tests:
            with self.subTest(query=q):
                norm_q = normalize_text(q)
                cat = extract_category(norm_q)
                self.assertEqual(cat, exp_cat)

    def test_a1_3_price_parsing_acceptance_table(self):
        """A1-3: Bảng test bắt buộc trích xuất giá tiền với Decimal"""
        cases = [
            ("Tìm sản phẩm giá trên 1,5 triệu", ">", 1500000, False),
            ("Tìm sản phẩm giá trên 5.000.000", ">", 5000000, False),
            ("Các linh kiện có giá từ 1 đến 3 triệu", "BETWEEN", (1000000, 3000000), False),
            ("Sản phẩm giá trên 2 tỷ", ">", 2000000000, False),
            ("Sản phẩm giá dưới 500k", "<", 500000, False),
            ("Giá từ 5 triệu trở lên", ">=", 5000000, False),
            ("Giá trên 5", None, None, True),
        ]
        for q, exp_op, exp_val, exp_clarify in cases:
            with self.subTest(query=q):
                res = extract_price_condition(q)
                if exp_clarify:
                    self.assertTrue(res.get("needs_clarification"))
                else:
                    self.assertEqual(res.get("operator"), exp_op)
                    if exp_op == "BETWEEN":
                        self.assertEqual(res.get("min_price"), exp_val[0])
                        self.assertEqual(res.get("max_price"), exp_val[1])
                    else:
                        self.assertEqual(res.get("price_value"), exp_val)

        # Trường hợp chuỗi số khổng lồ không ném exception
        huge_q = "giá trên " + ("9" * 400) + " triệu"
        try:
            res_huge = extract_price_condition(huge_q)
            self.assertFalse(res_huge.get("price_value"))
        except Exception as e:
            self.fail(f"Không được ném ngoại lệ khi số quá lớn: {e}")

    def test_a1_4_composite_filters(self):
        """A1-4: Bảng test bắt buộc ghép nhiều điều kiện không bỏ sót ràng buộc"""
        composite_cases = [
            ("RAM giá dưới 2 triệu", ["danh_muc", "gia_niem_yet < %s"], ["RAM", 2000000]),
            ("Sản phẩm ASUS giá trên 5 triệu", ["thuong_hieu", "gia_niem_yet > %s"], ["ASUS", 5000000]),
            ("Top 5 sản phẩm đắt nhất của hãng ASUS", ["thuong_hieu", "ORDER BY sp.gia_niem_yet DESC", "LIMIT %s"], ["ASUS", 5]),
            ("Tìm CPU Intel", ["danh_muc", "thuong_hieu"], ["CPU", "Intel"]),
            ("Màn hình Dell", ["danh_muc", "thuong_hieu"], ["Màn hình", "Dell"]),
            ("Đơn hàng qua Shopee", ["kenh_ban = %s"], ["shopee"]),
            ("Thanh toán bằng tiền mặt", ["phuong_thuc = %s"], ["tien_mat"]),
            ("Đơn hàng đã hủy năm 2025", ["trang_thai = %s", "EXTRACT(YEAR FROM ngay_dat) = %s"], ["da_huy", 2025]),
        ]
        for q, exp_sql_parts, exp_params in composite_cases:
            with self.subTest(query=q):
                res = interpret(q)
                self.assertTrue(res.success, f"Thất bại với câu: {q} | Lỗi: {res.explanation}")
                for part in exp_sql_parts:
                    self.assertIn(part, res.sql, f"Thiếu '{part}' trong SQL của câu '{q}'")
                for p in exp_params:
                    matched = (p in res.params) or (f"%{p}%" in res.params)
                    self.assertTrue(matched, f"Thiếu param '{p}' trong params của câu '{q}': {res.params}")

        # Trường hợp điều kiện không hỗ trợ -> success=False, needs_clarification=True
        unsupported = interpret("Doanh thu theo tháng của hãng ASUS")
        self.assertFalse(unsupported.success)
        self.assertTrue(unsupported.needs_clarification)
        self.assertIn("ASUS", unsupported.clarification or unsupported.explanation)

    def test_a1_5_intent_rule_priorities(self):
        """A1-5: Thứ tự ưu tiên Intent chặt chẽ, không nuốt intent của nhau"""
        self.assertEqual(classify_intent("Tháng nào doanh thu cao nhất")[0], "SALES_BY_MONTH")
        self.assertEqual(classify_intent("Có bao nhiêu đơn đã hủy")[0], "COUNT_ORDERS")
        self.assertEqual(classify_intent("Doanh thu đơn hàng hoàn thành")[0], "TOTAL_REVENUE")

        # Cụm từ phi sản phẩm không kích hoạt TOP_PRODUCTS_BY_PRICE_DESC
        self.assertNotEqual(classify_intent("Sản phẩm tồn kho cao nhất")[0], "TOP_PRODUCTS_BY_PRICE_DESC")
        self.assertNotEqual(classify_intent("Tỉnh nào có doanh thu cao nhất")[0], "TOP_PRODUCTS_BY_PRICE_DESC")

    def test_a1_6_cleaner_entity_dictionaries(self):
        """A1-6: Không nhận nhầm 'san' trong 'san pham' thành kênh shopee"""
        res = interpret("Danh sách sản phẩm đang bán")
        self.assertTrue(res.success)
        self.assertNotIn("channel", res.entities)

        # "Tìm các sản phẩm của hãng ASUS" không nhận nhầm 'của hãng' thành kênh cửa hàng
        res_asus = interpret("Tìm các sản phẩm của hãng ASUS")
        self.assertTrue(res_asus.success)
        self.assertNotIn("channel", res_asus.entities)
        self.assertEqual(res_asus.entities.get("brand_name"), "ASUS")

    def test_a1_7_limit_clamping_and_performance(self):
        """A1-7: Kẹp limit tối đa và kiểm soát hiệu năng với đầu vào 100 KB"""
        res_clamp = interpret("Top 1000 sản phẩm rẻ nhất")
        self.assertTrue(res_clamp.success)
        self.assertIn(100, res_clamp.params)
        self.assertTrue(len(res_clamp.warnings) > 0)

        # Kiểm tra tốc độ với đầu vào 100 KB
        huge_text = "Tìm sản phẩm " + ("linh kiện " * 15000)
        t0 = time.perf_counter()
        res_perf = interpret(huge_text)
        duration = time.perf_counter() - t0
        self.assertLess(duration, 0.2, f"Quá chậm: {duration}s")


if __name__ == "__main__":
    unittest.main()
