"""
Kiểm thử toàn diện bộ xử lý Text-to-SQL Rule Engine cho 20 câu hỏi vàng theo Query.md
Chạy: python -m unittest discover tests
"""
import sys
import os
import unittest

# Đưa thư mục ai_service vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_1_text2sql.text_normalizer import normalize_text
from app.ai_1_text2sql.intent_classifier import classify_intent
from app.ai_1_text2sql.entity_extractor import (
    extract_price_condition, extract_top_n, extract_category,
    extract_brand, extract_order_status, extract_year, parse_vietnamese_number
)
from app.ai_1_text2sql.sql_builder import build_sql
from app.ai_1_text2sql.explanation import generate_explanation


class TestTextToSqlPipeline(unittest.TestCase):

    # -----------------------------------------------------------------
    # CẤP ĐỘ 1: CƠ BẢN (Truy vấn 1 - 7)
    # -----------------------------------------------------------------

    def test_01_list_products(self):
        """1. LIST_PRODUCTS: Danh sách sản phẩm đang bán"""
        questions = [
            "Danh sách sản phẩm đang bán",
            "Liệt kê các sản phẩm còn kinh doanh",
            "Hiển thị sản phẩm",
            "sản phẩm đang bán",
            "xem sản phẩm"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, conf = classify_intent(norm)
            self.assertEqual(intent, "LIST_PRODUCTS", f"Sai intent với câu: {q}")
            sql, params = build_sql(intent, {})
            self.assertIsNotNone(sql)
            self.assertIn("FROM san_pham", sql)
            self.assertIn("dang_kinh_doanh = TRUE", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertGreater(len(params), 0)
            exp = generate_explanation(intent, {})
            self.assertIn("dang_kinh_doanh = TRUE", exp)

    def test_02_filter_products_by_price(self):
        """2. FILTER_PRODUCTS_BY_PRICE: Tìm sản phẩm có giá trên / dưới"""
        gt_questions = [
            ("Tìm sản phẩm có giá trên 5 triệu", 5000000),
            ("Linh kiện giá lớn hơn 5000000", 5000000),
            ("Sản phẩm trên 10 triệu", 10000000),
            ("sản phẩm giá cao hơn 2tr", 2000000),
        ]
        for q, expected_price in gt_questions:
            norm = normalize_text(q)
            intent, conf = classify_intent(norm)
            self.assertEqual(intent, "FILTER_PRODUCTS_BY_PRICE", f"Sai intent với câu: {q}")
            entities = extract_price_condition(norm)
            self.assertEqual(entities.get("operator"), ">")
            self.assertEqual(entities.get("price_value"), expected_price, f"Sai giá cho: {q}")
            sql, params = build_sql(intent, entities)
            self.assertIn("gia_niem_yet > %s", sql)
            self.assertEqual(params[0], expected_price)
            exp = generate_explanation(intent, entities)
            self.assertIn("gia_niem_yet > %s", exp)

        # Kiểm tra lọc giá dưới
        lt_q = "Sản phẩm dưới 2 triệu"
        norm_lt = normalize_text(lt_q)
        intent_lt, _ = classify_intent(norm_lt)
        self.assertEqual(intent_lt, "FILTER_PRODUCTS_BY_PRICE")
        entities_lt = extract_price_condition(norm_lt)
        self.assertEqual(entities_lt.get("operator"), "<")
        self.assertEqual(entities_lt.get("price_value"), 2000000)
        sql_lt, params_lt = build_sql(intent_lt, entities_lt)
        self.assertIn("gia_niem_yet < %s", sql_lt)
        self.assertEqual(params_lt[0], 2000000)

    def test_03_filter_products_by_price_range(self):
        """3. FILTER_PRODUCTS_BY_PRICE_RANGE: Các linh kiện có giá từ X đến Y"""
        questions = [
            ("Các linh kiện có giá từ 1 triệu đến 3 triệu", 1000000, 3000000),
            ("Sản phẩm trong khoảng 2 triệu đến 5 triệu", 2000000, 5000000),
            ("linh kiện từ 500k đến 2tr", 500000, 2000000),
        ]
        for q, exp_min, exp_max in questions:
            norm = normalize_text(q)
            intent, conf = classify_intent(norm)
            self.assertEqual(intent, "FILTER_PRODUCTS_BY_PRICE_RANGE", f"Sai intent với câu: {q}")
            entities = extract_price_condition(norm)
            self.assertEqual(entities.get("operator"), "BETWEEN")
            self.assertEqual(entities.get("min_price"), exp_min)
            self.assertEqual(entities.get("max_price"), exp_max)
            sql, params = build_sql(intent, entities)
            self.assertIn("gia_niem_yet BETWEEN %s AND %s", sql)
            self.assertEqual(params[0], exp_min)
            self.assertEqual(params[1], exp_max)
            exp = generate_explanation(intent, entities)
            self.assertIn("BETWEEN", exp)

    def test_04_top_products_by_price_desc(self):
        """4. TOP_PRODUCTS_BY_PRICE_DESC: Top 5 sản phẩm đắt nhất"""
        questions = [
            ("Top 5 sản phẩm đắt nhất", 5),
            ("5 linh kiện có giá cao nhất", 5),
            ("sản phẩm đắt nhất", 5),
        ]
        for q, exp_limit in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "TOP_PRODUCTS_BY_PRICE_DESC", f"Sai intent: {q}")
            top_n = extract_top_n(norm) or exp_limit
            sql, params = build_sql(intent, {"limit": top_n})
            self.assertIn("ORDER BY gia_niem_yet DESC", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertEqual(params[0], exp_limit)

    def test_05_top_products_by_price_asc(self):
        """5. TOP_PRODUCTS_BY_PRICE_ASC: Top 10 linh kiện rẻ nhất"""
        questions = [
            ("Top 10 linh kiện rẻ nhất", 10),
            ("10 sản phẩm giá thấp nhất", 10),
            ("sản phẩm rẻ nhất", 10),
        ]
        for q, exp_limit in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "TOP_PRODUCTS_BY_PRICE_ASC", f"Sai intent: {q}")
            top_n = extract_top_n(norm) or exp_limit
            sql, params = build_sql(intent, {"limit": top_n})
            self.assertIn("ORDER BY gia_niem_yet ASC", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertEqual(params[0], exp_limit)

    def test_06_count_orders(self):
        """6. COUNT_ORDERS: Đếm tổng số đơn hàng của cửa hàng"""
        questions = [
            "Đếm tổng số đơn hàng của cửa hàng",
            "Cửa hàng có bao nhiêu đơn hàng?",
            "tổng số đơn hàng",
            "đếm số đơn hàng"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "COUNT_ORDERS", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("COUNT(*) AS tong_so_don", sql)
            self.assertIn("FROM don_hang", sql)
            self.assertEqual(params, [])

    def test_07_orders_by_status(self):
        """7. ORDERS_BY_STATUS: Danh sách các đơn hàng đã hủy"""
        questions = [
            "Danh sách các đơn hàng đã hủy",
            "Những đơn hàng bị hủy",
            "Đơn nào đã hủy?"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "ORDERS_BY_STATUS", f"Sai intent: {q}")
            status = extract_order_status(norm)
            self.assertEqual(status, "da_huy")
            sql, params = build_sql(intent, {"status": status, "limit": 20})
            self.assertIn("FROM don_hang", sql)
            self.assertIn("WHERE trang_thai = %s", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertEqual(params[0], "da_huy")
            self.assertEqual(params[1], 20)

    # -----------------------------------------------------------------
    # CẤP ĐỘ 2: TRUNG BÌNH (Truy vấn 8 - 14)
    # -----------------------------------------------------------------

    def test_08_filter_by_category(self):
        """8. FILTER_BY_CATEGORY: Liệt kê tất cả card màn hình VGA"""
        questions = [
            ("Liệt kê tất cả card màn hình VGA", "VGA"),
            ("Danh sách CPU", "CPU"),
            ("Tìm các loại bàn phím", "Bàn phím"),
        ]
        for q, exp_cat in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "FILTER_BY_CATEGORY", f"Sai intent: {q}")
            cat = extract_category(norm)
            self.assertIsNotNone(cat)
            sql, params = build_sql(intent, {"category_name": cat})
            self.assertIn("JOIN danh_muc dm ON sp.danh_muc_id = dm.id", sql)
            self.assertIn("WHERE dm.ten ILIKE %s", sql)
            self.assertEqual(params[0], f"%{cat}%")

    def test_09_filter_by_brand(self):
        """9. FILTER_BY_BRAND: Tìm các sản phẩm của hãng ASUS"""
        questions = [
            ("Tìm các sản phẩm của hãng ASUS", "ASUS"),
            ("Linh kiện thương hiệu Corsair", "Corsair"),
            ("Sản phẩm MSI", "MSI"),
        ]
        for q, exp_brand in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "FILTER_BY_BRAND", f"Sai intent: {q}")
            brand = extract_brand(norm)
            self.assertEqual(brand, exp_brand)
            sql, params = build_sql(intent, {"brand_name": brand})
            self.assertIn("JOIN thuong_hieu th ON sp.thuong_hieu_id = th.id", sql)
            self.assertIn("WHERE th.ten ILIKE %s", sql)
            self.assertEqual(params[0], f"%{exp_brand}%")

    def test_10_low_stock(self):
        """10. LOW_STOCK: Những sản phẩm nào sắp hết hàng trong kho?"""
        questions = [
            "Những sản phẩm nào sắp hết hàng trong kho?",
            "Cảnh báo tồn kho thấp",
            "Sản phẩm dưới mức tồn tối thiểu"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "LOW_STOCK", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("JOIN ton_kho tk ON sp.id = tk.san_pham_id", sql)
            self.assertIn("WHERE tk.so_luong_ton <= tk.muc_ton_toi_thieu", sql)
            self.assertEqual(params, [])

    def test_11_orders_count_by_status(self):
        """11. ORDERS_COUNT_BY_STATUS: Thống kê số lượng đơn hàng theo từng trạng thái"""
        questions = [
            "Thống kê số lượng đơn hàng theo từng trạng thái",
            "Số đơn theo trạng thái",
            "đơn hàng theo từng trạng thái"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "ORDERS_COUNT_BY_STATUS", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("GROUP BY trang_thai", sql)
            self.assertIn("ORDER BY so_don DESC", sql)
            self.assertEqual(params, [])

    def test_12_orders_by_channel(self):
        """12. ORDERS_BY_CHANNEL: Thống kê số đơn và doanh thu theo từng kênh bán"""
        questions = [
            "Thống kê số đơn và doanh thu theo từng kênh bán",
            "Doanh thu theo kênh bán hàng",
            "theo kênh bán"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "ORDERS_BY_CHANNEL", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("GROUP BY kenh_ban", sql)
            self.assertIn("WHERE trang_thai = 'hoan_thanh'", sql)
            self.assertEqual(params, [])

    def test_13_payment_methods_stats(self):
        """13. PAYMENT_METHODS_STATS: Khách hàng hay thanh toán qua những phương thức nào nhất?"""
        questions = [
            "Khách hàng hay thanh toán qua những phương thức nào nhất?",
            "Thống kê hình thức thanh toán",
            "phương thức thanh toán"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "PAYMENT_METHODS_STATS", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("FROM thanh_toan", sql)
            self.assertIn("GROUP BY phuong_thuc", sql)
            self.assertEqual(params, [])

    def test_14_customers_by_city(self):
        """14. CUSTOMERS_BY_CITY: Thống kê số lượng khách hàng theo từng tỉnh thành"""
        questions = [
            "Thống kê số lượng khách hàng theo từng tỉnh thành",
            "Khách hàng phân bố ở tỉnh nào nhiều nhất?",
            "khách hàng theo tỉnh"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "CUSTOMERS_BY_CITY", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("JOIN dia_chi dc ON kh.id = dc.khach_hang_id", sql)
            self.assertIn("GROUP BY dc.tinh_thanh", sql)
            self.assertEqual(params, [])

    # -----------------------------------------------------------------
    # CẤP ĐỘ 3: NÂNG CAO (Truy vấn 15 - 20)
    # -----------------------------------------------------------------

    def test_15_best_selling_products(self):
        """15. BEST_SELLING_PRODUCTS: Top 5 sản phẩm bán chạy nhất của cửa hàng"""
        questions = [
            "Top 5 sản phẩm bán chạy nhất của cửa hàng",
            "Những sản phẩm bán được nhiều nhất",
            "sản phẩm bán chạy nhất"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "BEST_SELLING_PRODUCTS", f"Sai intent: {q}")
            top_n = extract_top_n(norm) or 5
            sql, params = build_sql(intent, {"limit": top_n})
            self.assertIn("FROM chi_tiet_don_hang ct", sql)
            self.assertIn("JOIN don_hang dh ON ct.don_hang_id = dh.id", sql)
            self.assertIn("ORDER BY tong_da_ban DESC", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertEqual(params[0], top_n)

    def test_16_top_spending_customers(self):
        """16. TOP_SPENDING_CUSTOMERS: Top 5 khách hàng mua nhiều tiền nhất"""
        questions = [
            "Top 5 khách hàng mua nhiều tiền nhất",
            "Khách hàng VIP mua nhiều nhất",
            "khách hàng chi tiêu nhiều nhất"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "TOP_SPENDING_CUSTOMERS", f"Sai intent: {q}")
            top_n = extract_top_n(norm) or 5
            sql, params = build_sql(intent, {"limit": top_n})
            self.assertIn("FROM khach_hang kh", sql)
            self.assertIn("JOIN don_hang dh ON kh.id = dh.khach_hang_id", sql)
            self.assertIn("ORDER BY tong_chi_tieu DESC", sql)
            self.assertIn("LIMIT %s", sql)
            self.assertEqual(params[0], top_n)

    def test_17_sales_by_month(self):
        """17. SALES_BY_MONTH: Thống kê doanh thu theo từng tháng trong năm 2025"""
        questions = [
            ("Thống kê doanh thu theo từng tháng trong năm 2025", 2025),
            ("Doanh thu năm 2025 theo tháng", 2025),
            ("doanh thu theo tháng", 2025),
        ]
        for q, exp_year in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "SALES_BY_MONTH", f"Sai intent: {q}")
            year = extract_year(norm) or exp_year
            sql, params = build_sql(intent, {"year": year})
            self.assertIn("TO_CHAR(ngay_dat, 'YYYY-MM')", sql)
            self.assertIn("EXTRACT(YEAR FROM ngay_dat) = %s", sql)
            self.assertEqual(params[0], exp_year)

    def test_18_employee_performance(self):
        """18. EMPLOYEE_PERFORMANCE: Doanh số bán hàng của từng nhân viên"""
        questions = [
            "Doanh số bán hàng của từng nhân viên",
            "Nhân viên nào bán được nhiều tiền nhất?",
            "doanh số của nhân viên"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "EMPLOYEE_PERFORMANCE", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("FROM nhan_vien nv", sql)
            self.assertIn("JOIN don_hang dh ON nv.id = dh.nhan_vien_id", sql)
            self.assertIn("ORDER BY tong_doanh_so DESC", sql)
            self.assertEqual(params, [])

    def test_19_total_revenue(self):
        """19. TOTAL_REVENUE: Tổng doanh thu của tất cả đơn hàng đã hoàn thành"""
        questions = [
            "Tổng doanh thu của tất cả đơn hàng đã hoàn thành",
            "Cửa hàng kiếm được bao nhiêu tiền doanh thu?",
            "tổng doanh thu",
            "tổng tiền kiếm được"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "TOTAL_REVENUE", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("SELECT SUM(tong_tien) AS tong_doanh_thu", sql)
            self.assertIn("WHERE trang_thai = 'hoan_thanh'", sql)
            self.assertEqual(params, [])

    def test_20_supplier_purchase_total(self):
        """20. SUPPLIER_PURCHASE_TOTAL: Tổng tiền nhập hàng từ các nhà cung cấp"""
        questions = [
            "Tổng tiền nhập hàng từ các nhà cung cấp",
            "Chi phí nhập hàng theo từng nhà cung cấp",
            "tiền nhập hàng"
        ]
        for q in questions:
            norm = normalize_text(q)
            intent, _ = classify_intent(norm)
            self.assertEqual(intent, "SUPPLIER_PURCHASE_TOTAL", f"Sai intent: {q}")
            sql, params = build_sql(intent, {})
            self.assertIn("FROM nha_cung_cap ncc", sql)
            self.assertIn("JOIN phieu_nhap pn ON ncc.id = pn.nha_cung_cap_id", sql)
            self.assertIn("ORDER BY tong_tien_nhap DESC", sql)
            self.assertEqual(params, [])

    # -----------------------------------------------------------------
    # BẢO MẬT & NGOÀI PHẠM VI (UNKNOWN & MALICIOUS)
    # -----------------------------------------------------------------

    def test_unknown_and_malicious(self):
        """Kiểm tra xử lý các câu hỏi ngoài phạm vi và mã độc SQL Injection"""
        q_outside = "Thời tiết hôm nay thế nào?"
        norm = normalize_text(q_outside)
        intent, _ = classify_intent(norm)
        self.assertEqual(intent, "UNKNOWN")
        sql, _ = build_sql(intent, {})
        self.assertIsNone(sql)

        q_drop = "DROP TABLE san_pham; DELETE FROM don_hang;"
        norm_drop = normalize_text(q_drop)
        intent_drop, _ = classify_intent(norm_drop)
        self.assertEqual(intent_drop, "UNKNOWN")
        sql_drop, _ = build_sql(intent_drop, {})
        self.assertIsNone(sql_drop)

    # -----------------------------------------------------------------
    # KIỂM THỬ BÓC TÁCH THỰC THỂ (ENTITY EXTRACTION)
    # -----------------------------------------------------------------

    def test_entity_extraction_helpers(self):
        """Kiểm tra các hàm bóc tách thực thể chuyên biệt"""
        # Số tiếng Việt
        self.assertEqual(parse_vietnamese_number("5 triệu"), 5000000)
        self.assertEqual(parse_vietnamese_number("1.5 tr"), 1500000)
        self.assertEqual(parse_vietnamese_number("500k"), 500000)
        self.assertEqual(parse_vietnamese_number("500 nghìn"), 500000)
        self.assertEqual(parse_vietnamese_number("5000000"), 5000000)

        # Top N
        self.assertEqual(extract_top_n("top 5 sản phẩm"), 5)
        self.assertEqual(extract_top_n("10 linh kiện"), 10)
        self.assertEqual(extract_top_n("top 3 khách hàng"), 3)

        # Danh mục
        self.assertEqual(extract_category("tìm vga"), "VGA")
        self.assertEqual(extract_category("mua cpu intel"), "CPU")
        self.assertEqual(extract_category("bàn phím cơ"), "Bàn phím")

        # Hãng
        self.assertEqual(extract_brand("hãng asus"), "ASUS")
        self.assertEqual(extract_brand("ram corsair"), "Corsair")
        self.assertEqual(extract_brand("ổ cứng western digital"), "Western Digital")

        # Trạng thái
        self.assertEqual(extract_order_status("đơn bị hủy"), "da_huy")
        self.assertEqual(extract_order_status("đơn đã hoàn thành"), "hoan_thanh")

        # Năm
        self.assertEqual(extract_year("trong năm 2025"), 2025)
        self.assertEqual(extract_year("năm 2024"), 2024)

    # -----------------------------------------------------------------
    # KIỂM THỬ END-TO-END 20 CÂU HỎI VÀNG MỤC TIÊU (QUERY.MD BẢNG TỔNG HỢP)
    # -----------------------------------------------------------------

    def test_all_20_gold_queries_end_to_end(self):
        """Kiểm tra chính xác 20 câu hỏi vàng mục tiêu trong Bảng tổng hợp Query.md"""
        from app.main import interpret_question
        from app.schemas import InterpretRequest

        gold_queries = [
            (1, "Danh sách sản phẩm đang bán", "LIST_PRODUCTS"),
            (2, "Tìm sản phẩm có giá trên 5 triệu", "FILTER_PRODUCTS_BY_PRICE"),
            (3, "Các linh kiện có giá từ 1 triệu đến 3 triệu", "FILTER_PRODUCTS_BY_PRICE_RANGE"),
            (4, "Top 5 sản phẩm đắt nhất", "TOP_PRODUCTS_BY_PRICE_DESC"),
            (5, "Top 10 linh kiện rẻ nhất", "TOP_PRODUCTS_BY_PRICE_ASC"),
            (6, "Đếm tổng số đơn hàng của cửa hàng", "COUNT_ORDERS"),
            (7, "Danh sách các đơn hàng đã hủy", "ORDERS_BY_STATUS"),
            (8, "Liệt kê tất cả card màn hình VGA", "FILTER_BY_CATEGORY"),
            (9, "Tìm các sản phẩm của hãng ASUS", "FILTER_BY_BRAND"),
            (10, "Những sản phẩm nào sắp hết hàng trong kho?", "LOW_STOCK"),
            (11, "Thống kê số lượng đơn hàng theo từng trạng thái", "ORDERS_COUNT_BY_STATUS"),
            (12, "Thống kê số đơn và doanh thu theo từng kênh bán", "ORDERS_BY_CHANNEL"),
            (13, "Khách hàng hay thanh toán qua những phương thức nào nhất?", "PAYMENT_METHODS_STATS"),
            (14, "Thống kê số lượng khách hàng theo từng tỉnh thành", "CUSTOMERS_BY_CITY"),
            (15, "Top 5 sản phẩm bán chạy nhất của cửa hàng", "BEST_SELLING_PRODUCTS"),
            (16, "Top 5 khách hàng mua nhiều tiền nhất", "TOP_SPENDING_CUSTOMERS"),
            (17, "Thống kê doanh thu theo từng tháng trong năm 2025", "SALES_BY_MONTH"),
            (18, "Doanh số bán hàng của từng nhân viên", "EMPLOYEE_PERFORMANCE"),
            (19, "Tổng doanh thu của tất cả đơn hàng đã hoàn thành", "TOTAL_REVENUE"),
            (20, "Tổng tiền nhập hàng từ các nhà cung cấp", "SUPPLIER_PURCHASE_TOTAL"),
        ]

        for stt, question, expected_intent in gold_queries:
            with self.subTest(stt=stt, question=question):
                req = InterpretRequest(question=question)
                resp = interpret_question(req)
                self.assertTrue(resp.success, f"[Câu {stt}] Thất bại khi phân tích câu: '{question}'")
                self.assertEqual(
                    resp.intent, expected_intent,
                    f"[Câu {stt}] Sai intent! Nhận: '{resp.intent}', Kỳ vọng: '{expected_intent}'"
                )
                self.assertIsNotNone(resp.sql, f"[Câu {stt}] SQL không được sinh ra cho: '{question}'")
                self.assertTrue(len(resp.sql.strip()) > 0)
                self.assertIsInstance(resp.params, list)
                self.assertTrue(len(resp.explanation) > 0)

    def test_get_supported_intents(self):
        """Kiểm tra endpoint get_supported_intents trả về đầy đủ 20 intent"""
        from app.main import get_supported_intents
        intents_info = get_supported_intents()
        self.assertEqual(len(intents_info), 20, "get_supported_intents phải trả về đúng 20 intent")
        intent_names = [item.intent for item in intents_info]
        expected_20 = [
            "LIST_PRODUCTS", "FILTER_PRODUCTS_BY_PRICE", "FILTER_PRODUCTS_BY_PRICE_RANGE",
            "TOP_PRODUCTS_BY_PRICE_DESC", "TOP_PRODUCTS_BY_PRICE_ASC", "COUNT_ORDERS",
            "ORDERS_BY_STATUS", "FILTER_BY_CATEGORY", "FILTER_BY_BRAND", "LOW_STOCK",
            "ORDERS_COUNT_BY_STATUS", "ORDERS_BY_CHANNEL", "PAYMENT_METHODS_STATS",
            "CUSTOMERS_BY_CITY", "BEST_SELLING_PRODUCTS", "TOP_SPENDING_CUSTOMERS",
            "SALES_BY_MONTH", "EMPLOYEE_PERFORMANCE", "TOTAL_REVENUE", "SUPPLIER_PURCHASE_TOTAL"
        ]
        for exp in expected_20:
            self.assertIn(exp, intent_names, f"Thiếu intent {exp} trong get_supported_intents")


if __name__ == "__main__":
    unittest.main()
