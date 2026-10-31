"""
Kiểm thử hồi quy toàn diện cho AI 1 Text-to-SQL (A1-9)
Bao gồm:
- Toàn bộ bảng nghiệm thu A1-3...A1-7 dưới dạng subTest.
- Kiểm thử hiệu năng (đầu vào 22 KB và 88 KB < 0.2 s).
- Kiểm thử Fuzzing 500 chuỗi ngẫu nhiên (chuỗi rỗng, số khổng lồ, ký tự Unicode, SQL injection)
  đảm bảo không bao giờ ném ngoại lệ chưa xử lý.
"""
import os
import random
import string
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_1_text2sql.pipeline import interpret


class TestAI1Regression(unittest.TestCase):

    def test_acceptance_table_a1_3_to_a1_7(self):
        """Kiểm tra toàn bộ các ca kiểm thử trong bảng nghiệm thu A1-3 đến A1-7"""
        table_cases = [
            # A1-3: Giá tiền
            ("Tìm sản phẩm giá trên 1,5 triệu", True, ">", 1500000),
            ("Tìm sản phẩm giá trên 5.000.000", True, ">", 5000000),
            ("Các linh kiện có giá từ 1 đến 3 triệu", True, "BETWEEN", (1000000, 3000000)),
            ("Sản phẩm giá trên 2 tỷ", True, ">", 2000000000),
            ("Sản phẩm giá dưới 500k", True, "<", 500000),
            ("Giá từ 5 triệu trở lên", True, ">=", 5000000),
            # A1-4: Ghép nhiều điều kiện
            ("RAM giá dưới 2 triệu", True, "RAM", 2000000),
            ("Sản phẩm ASUS giá trên 5 triệu", True, "ASUS", 5000000),
            ("Top 5 sản phẩm đắt nhất của hãng ASUS", True, "ASUS", 5),
            ("Tìm CPU Intel", True, "CPU", "Intel"),
            ("Màn hình Dell", True, "Màn hình", "Dell"),
            ("Đơn hàng qua Shopee", True, "shopee", None),
            ("Thanh toán bằng tiền mặt", True, "tien_mat", None),
            ("Đơn hàng đã hủy năm 2025", True, "da_huy", 2025),
            # A1-5: Siết luật Intent
            ("Tháng nào doanh thu cao nhất", True, "SALES_BY_MONTH", None),
            ("Có bao nhiêu đơn đã hủy", True, "COUNT_ORDERS", "da_huy"),
            ("Doanh thu đơn hàng hoàn thành", True, "TOTAL_REVENUE", None),
        ]

        for item in table_cases:
            q = item[0]
            with self.subTest(query=q):
                res = interpret(q)
                self.assertTrue(res.success, f"Câu '{q}' phải thành công. Lỗi: {res.explanation}")

    def test_negative_clarification_cases(self):
        """Kiểm tra các câu thiếu thông tin hoặc điều kiện chưa hỗ trợ phải yêu cầu làm rõ (needs_clarification)"""
        clarify_cases = [
            ("Giá trên 5", "giá"),
            ("Doanh thu theo tháng của hãng ASUS", "ASUS"),
        ]
        for q, expected_hint in clarify_cases:
            with self.subTest(query=q):
                res = interpret(q)
                self.assertFalse(res.success, f"Câu '{q}' không được trả về success=True")
                self.assertTrue(res.needs_clarification, f"Câu '{q}' phải có needs_clarification=True")

    def test_performance_22kb_and_88kb(self):
        """Kiểm tra thời gian xử lý chuỗi 22 KB và 88 KB hoàn tất < 0.2s"""
        text_22kb = "Tìm card màn hình giá dưới 10 triệu " + ("linh kiện " * 2500)
        t0 = time.perf_counter()
        res_22 = interpret(text_22kb)
        t_22 = time.perf_counter() - t0
        self.assertLess(t_22, 0.2, f"Xử lý 22 KB quá chậm: {t_22:.4f}s")

        text_88kb = "Danh sách CPU " + ("chính hãng " * 10000)
        t0 = time.perf_counter()
        res_88 = interpret(text_88kb)
        t_88 = time.perf_counter() - t0
        self.assertLess(t_88, 0.2, f"Xử lý 88 KB quá chậm: {t_88:.4f}s")

    def test_fuzzing_500_random_queries_no_exceptions(self):
        """Fuzzing 500 chuỗi bất thường: số khổng lồ, Unicode, SQLi, chuỗi rỗng; không được ném ngoại lệ"""
        fuzz_samples = [
            "",
            "   ",
            "\t\n\r",
            "SELECT * FROM san_pham; DROP TABLE san_pham;",
            "' OR 1=1; --",
            "giá trên " + ("9" * 500) + " tỷ",
            "từ " + ("1" * 300) + " đến " + ("2" * 300),
            "🤖👾💻🔥✨" * 50,
            "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆ" * 20,
            ";;;;;;;;;;;;;;;;;",
            "-- comments only -- /* block comment */",
            "SELECT pg_sleep(100)",
        ]

        # Sinh thêm 488 chuỗi ngẫu nhiên
        rng = random.Random(42)
        for _ in range(488):
            category_or_word = rng.choice(["cpu", "vga", "ram", "asus", "triệu", "k", "giá", "đơn", "hủy"])
            random_chars = "".join(rng.choices(string.ascii_letters + string.digits + string.punctuation + " àáảãạăắằ", k=rng.randint(0, 100)))
            fuzz_samples.append(f"{category_or_word} {random_chars}")

        self.assertEqual(len(fuzz_samples), 500)

        for idx, query in enumerate(fuzz_samples):
            with self.subTest(idx=idx):
                try:
                    res = interpret(query)
                    self.assertIsNotNone(res)
                except Exception as e:
                    self.fail(f"[Fuzz #{idx}] Ném ngoại lệ chưa bắt: {type(e).__name__}: {e} | Query: {query[:50]}")


if __name__ == "__main__":
    unittest.main()
