"""
Module nhận diện ý định (Intent Classifier) theo luật và thứ tự ưu tiên cho AI Text-to-SQL.
Hỗ trợ đối tượng kết quả giàu thông tin IntentResult (vẫn hỗ trợ unpacking tuple),
độ tin cậy thực tế (1.0, 0.8, 0.6, 0.0), biên dịch sẵn Regex hằng số và siết chặt ngữ cảnh.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from app.text_normalizer import remove_diacritics
from app.entity_extractor import (
    extract_brand,
    extract_channel,
    extract_category,
    extract_order_status,
    extract_price_condition,
)


@dataclass
class IntentResult:
    """Đối tượng kết quả phân loại ý định (A1-1). Hỗ trợ tuple unpacking cũ (intent, confidence)."""
    intent: str
    confidence: float
    matched_rule: str = ""
    alternatives: List[str] = field(default_factory=list)

    def __iter__(self):
        yield self.intent
        yield self.confidence

    def __getitem__(self, item):
        if item == 0:
            return self.intent
        elif item == 1:
            return self.confidence
        raise IndexError("IntentResult index out of range (chỉ hỗ trợ 0: intent, 1: confidence)")

    def __repr__(self):
        return f"IntentResult(intent='{self.intent}', confidence={self.confidence}, rule='{self.matched_rule}')"


# Bật/tắt bộ dự phòng học máy (dùng để so sánh "chỉ luật" và "luật + ML" khi đánh giá)
ML_FALLBACK_ENABLED = os.getenv("ML_FALLBACK_ENABLED", "1") != "0"

# ==============================================================================
# BIÊN DỊCH TRƯỚC TẤT CẢ CÁC REGEX CỦA LUẬT INTENT (Tối ưu hóa hiệu năng & A1-5)
# ==============================================================================

# 1. TOP_SPENDING_CUSTOMERS
RE_TOP_SPENDING_1 = re.compile(
    r'\b(khách hàng|khach hang|khách|khach)\b.{0,80}?\b(mua nhiều tiền nhất|mua nhieu tien nhat|nhiều tiền nhất|nhieu tien nhat|chi tiêu nhiều nhất|chi tieu nhieu nhat|chi tiêu cao nhất|chi tieu cao nhat|tổng chi tiêu cao nhất|tong chi tieu cao nhat|vip|mua nhiều nhất|mua nhieu nhat|mua nhieu tien)\b',
    re.IGNORECASE,
)
RE_TOP_SPENDING_2 = re.compile(
    r'\b(mua nhiều tiền nhất|mua nhieu tien nhat|nhiều tiền nhất|nhieu tien nhat|chi tiêu nhiều nhất|chi tieu nhieu nhat)\b.{0,80}?\b(khách hàng|khach hang|khách|khach)\b',
    re.IGNORECASE,
)
RE_TOP_SPENDING_NO = re.compile(
    r'\b(khach hang|khach)\b.{0,80}?\b(mua nhieu tien nhat|chi tieu nhieu nhat|mua nhieu nhat|vip)\b',
    re.IGNORECASE,
)

# 2. BEST_SELLING_PRODUCTS
RE_BEST_SELLING = re.compile(
    r'\b(bán chạy nhất|ban chay nhat|bán chạy|ban chay|bán được nhiều nhất|ban duoc nhieu nhat)\b',
    re.IGNORECASE,
)

# Từ gợi ý chủ thể là người bán hàng (không dấu)
RE_SELLER_HINT = re.compile(r'\b(nhan vien|ban sale|sale|nguoi ban|nhan su)\b', re.IGNORECASE)

# 3. EMPLOYEE_PERFORMANCE
RE_EMPLOYEE_1 = re.compile(
    r'\b(nhân viên|nhan vien)\b.{0,80}?\b(doanh số|doanh so|bán được|ban duoc|doanh thu|bán hàng|ban hang)\b',
    re.IGNORECASE,
)
RE_EMPLOYEE_2 = re.compile(
    r'\b(doanh số|doanh so|doanh thu|bán hàng|ban hang)\b.{0,80}?\b(nhân viên|nhan vien)\b',
    re.IGNORECASE,
)
RE_EMPLOYEE_NO = re.compile(
    r'\b(nhan vien nao ban duoc|doanh so ban hang cua tung nhan vien|hieu qua ban hang cua nhan vien)\b',
    re.IGNORECASE,
)

# 4. ORDERS_BY_CHANNEL
RE_CHANNEL_1 = re.compile(
    r'\b(kênh bán|kenh ban|kênh bán hàng|kenh ban hang|kênh shopee|kenh shopee|kênh shoppi|kenh shoppi|qua shopee|qua shoppi|qua website|qua facebook|qua kênh|từ kênh|tu kenh)\b',
    re.IGNORECASE,
)
RE_CHANNEL_2 = re.compile(
    r'\b(đơn hàng|don hang|liệt kê|liet ke|thống kê|thong ke|danh sách|danh sach)\b.{0,80}?\b(kênh|kenh|shopee|shoppi|website|facebook)\b',
    re.IGNORECASE,
)

RE_CHANNEL_CONTEXT = re.compile(
    r'\b(kenh|qua|doanh so|doanh thu|don|ban duoc|ban hang|so luong don)\b',
    re.IGNORECASE,
)

# 5. PAYMENT_METHODS_STATS
RE_PAYMENT_1 = re.compile(
    r'\b(phương thức thanh toán|phuong thuc thanh toan|hình thức thanh toán|hinh thuc thanh toan|thanh toán qua những|thanh toan qua|cách thanh toán|cach thanh toan)\b',
    re.IGNORECASE,
)
RE_PAYMENT_2 = re.compile(
    r'\b(thanh toán|thanh toan)\b.{0,80}?\b(chuyển khoản|chuyen khoan|ngân hàng|ngan hang|tiền mặt|tien mat|ví điện tử|vi dien tu|thẻ|the)\b',
    re.IGNORECASE,
)

# 6. CUSTOMERS_BY_CITY
RE_CITY_1 = re.compile(
    r'\b(tỉnh thành|tinh thanh|tỉnh nào|tinh nao|thành phố|thanh pho|tỉnh|tinh)\b.{0,80}?\b(khách hàng|khach hang|khách|khach)\b',
    re.IGNORECASE,
)
RE_CITY_2 = re.compile(
    r'\b(khách hàng|khach hang|khách|khach)\b.{0,80}?\b(tỉnh thành|tinh thanh|tỉnh nào|tinh nao|thành phố|thanh pho|tỉnh|tinh|phân bố|phan bo)\b',
    re.IGNORECASE,
)

# 7. SUPPLIER_PURCHASE_TOTAL
RE_SUPPLIER = re.compile(
    r'\b(nhà cung cấp|nha cung cap|nhập hàng|nhap hang|phiếu nhập|phieu nhap)\b',
    re.IGNORECASE,
)

# 8. SALES_BY_MONTH
RE_SALES_MONTH_1 = re.compile(
    r'\b(doanh thu|doanh so)\b.{0,80}?\b(theo từng tháng|theo tung thang|theo tháng|theo thang|từng tháng|tung thang|tháng nào)\b',
    re.IGNORECASE,
)
RE_SALES_MONTH_2 = re.compile(
    r'\b(theo từng tháng|theo tung thang|theo tháng|theo thang|từng tháng|tung thang|tháng nào)\b.{0,80}?\b(doanh thu|doanh so)\b',
    re.IGNORECASE,
)
RE_SALES_MONTH_YEAR = re.compile(
    r'\b(doanh thu năm 20\d\d theo tháng|doanh thu nam 20\d\d theo thang)\b',
    re.IGNORECASE,
)

# 9. TOTAL_REVENUE
RE_TOTAL_REVENUE = re.compile(
    r'\b(tổng doanh thu|tong doanh thu|tổng tiền kiếm được|tong tien kiem duoc|tiền kiếm được|tien kiem duoc|kiếm được bao nhiêu tiền|kiem duoc bao nhieu tien|doanh thu của cửa hàng|doanh thu cua cua hang|tổng số tiền bán|tong so tien ban|doanh thu cửa hàng|doanh thu cua hang|doanh thu đơn hàng hoàn thành|doanh thu don hang hoan thanh|doanh thu đơn hoàn thành|doanh thu don hoan thanh)\b',
    re.IGNORECASE,
)

# 10. COUNT_ORDERS (Đếm tổng số đơn hoặc đếm đơn có điều kiện)
RE_COUNT_ORDERS = re.compile(
    r'\b(đếm tổng số đơn|dem tong so don|tổng số đơn hàng|tong so don hang|bao nhiêu đơn hàng|bao nhieu don hang|bao nhiêu đơn|bao nhieu don|đếm số đơn hàng|dem so don hang|đếm đơn hàng|dem don hang|đếm đơn|dem don|có bao nhiêu đơn|co bao nhieu don)\b',
    re.IGNORECASE,
)

# 11. ORDERS_COUNT_BY_STATUS
RE_COUNT_STATUS_1 = re.compile(
    r'\b(đơn hàng|don hang|số đơn|so don|thống kê đơn)\b.{0,80}?\b(theo từng trạng thái|theo tung trang thai|theo trạng thái|theo trang thai)\b',
    re.IGNORECASE,
)
RE_COUNT_STATUS_2 = re.compile(
    r'\b(theo từng trạng thái|theo tung trang thai|theo trạng thái|theo trang thai)\b.{0,80}?\b(đơn hàng|don hang|số đơn|so don)\b',
    re.IGNORECASE,
)

# 12. ORDERS_BY_STATUS
RE_ORDERS_STATUS_WORD = re.compile(
    r'\b(đơn hàng|don hang|đơn|don)\b',
    re.IGNORECASE,
)
RE_ORDERS_STATUS_PHRASE = re.compile(
    r'\b(bị hủy|bi huy|đã hủy|da huy|hoàn thành|hoan thanh|đang giao|dang giao|trả hàng|tra hang)\b',
    re.IGNORECASE,
)

# 13. LOW_STOCK
RE_LOW_STOCK = re.compile(
    r'\b(sắp hết hàng|sap het hang|hết hàng|het hang|tồn kho thấp|ton kho thap|dưới mức tồn|duoi muc ton|tồn kho tối thiểu|ton kho toi thieu)\b',
    re.IGNORECASE,
)

# 14. TOP_PRODUCTS_BY_PRICE_DESC / ASC
RE_PRICE_DESC_EXPLICIT = re.compile(
    r'\b(đắt nhất|dat nhat|mắc nhất|mac nhat|giá cao nhất|gia cao nhat)\b',
    re.IGNORECASE,
)
RE_PRICE_ASC_EXPLICIT = re.compile(
    r'\b(rẻ nhất|re nhat|thấp nhất|thap nhat|giá rẻ nhất|gia re nhat|giá thấp nhất|gia thap nhat)\b',
    re.IGNORECASE,
)
RE_SUPERLATIVE_GENERIC = re.compile(
    r'\b(cao nhất|cao nhat)\b',
    re.IGNORECASE,
)
# Từ khóa chỉ thực thể phi sản phẩm (chặn nuốt vào TOP_PRODUCTS)
RE_NON_PRODUCT_ENTITY = re.compile(
    r'\b(doanh thu|doanh so|tồn kho|ton kho|tỉnh|tinh|tháng|thang|nhân viên|nhan vien|khách|khach|lợi nhuận|loi nhuan)\b',
    re.IGNORECASE,
)
# Ngữ cảnh sản phẩm / linh kiện
RE_PRODUCT_CONTEXT = re.compile(
    r'\b(sản phẩm|san pham|linh kiện|linh kien|giá|gia|đắt|dat|mắc|mac|rẻ|re|món|hàng|hang)\b',
    re.IGNORECASE,
)

# 16. LIST_PRODUCTS
RE_LIST_PRODUCTS = re.compile(
    r'\b(danh sách sản phẩm|danh sach san pham|liệt kê sản phẩm|liet ke san pham|cac san pham|các sản phẩm|san pham dang ban|sản phẩm đang bán|xem sản phẩm|xem san pham|còn kinh doanh|con kinh doanh|hiển thị sản phẩm|hien thi san pham)\b',
    re.IGNORECASE,
)


def classify_intent(normalized_text: str) -> IntentResult:
    """
    Phân loại ý định của câu hỏi theo 20 Intent vàng và thứ tự ưu tiên chặt chẽ (A1-1, A1-5).
    Trả về: IntentResult(intent, confidence, matched_rule, alternatives)
    """
    if not normalized_text:
        return IntentResult(intent="UNKNOWN", confidence=0.0, matched_rule="empty_query")

    text = normalized_text.lower().strip()
    no_accent = remove_diacritics(text)

    # -------------------------------------------------------------
    # 1. TOP_SPENDING_CUSTOMERS: Top khách hàng mua nhiều tiền nhất
    # -------------------------------------------------------------
    if RE_TOP_SPENDING_1.search(text) or RE_TOP_SPENDING_2.search(text) or RE_TOP_SPENDING_NO.search(no_accent):
        return IntentResult("TOP_SPENDING_CUSTOMERS", 1.0, "rule_1_top_spending_customers")

    # -------------------------------------------------------------
    # 2. BEST_SELLING_PRODUCTS: Top sản phẩm bán chạy nhất
    # -------------------------------------------------------------
    # Loại trừ ngữ cảnh "người bán" (vd: "bạn sale nào bán được nhiều nhất") để không nhầm sang sản phẩm
    if (RE_BEST_SELLING.search(text) or RE_BEST_SELLING.search(no_accent)) and not RE_SELLER_HINT.search(no_accent):
        return IntentResult("BEST_SELLING_PRODUCTS", 1.0, "rule_2_best_selling_products")

    # -------------------------------------------------------------
    # 3. EMPLOYEE_PERFORMANCE: Doanh số / hiệu quả bán hàng của nhân viên
    # -------------------------------------------------------------
    if RE_EMPLOYEE_1.search(text) or RE_EMPLOYEE_2.search(text) or RE_EMPLOYEE_NO.search(no_accent):
        return IntentResult("EMPLOYEE_PERFORMANCE", 1.0, "rule_3_employee_performance")

    # -------------------------------------------------------------
    # 4. ORDERS_BY_CHANNEL: Thống kê số đơn và doanh thu theo kênh bán
    # -------------------------------------------------------------
    if RE_CHANNEL_1.search(text) or RE_CHANNEL_2.search(text):
        return IntentResult("ORDERS_BY_CHANNEL", 1.0, "rule_4_orders_by_channel")
    # Dự phòng: từ điển kênh bán nhận ra kênh online (kể cả cách viết khác) + có ngữ cảnh bán hàng
    # ("doanh số của kênh ...", "đơn ... facebook"). Không áp dụng cho "cửa hàng" vì từ này quá chung.
    _ch = extract_channel(text)
    if _ch in ("shopee", "facebook", "website") and RE_CHANNEL_CONTEXT.search(no_accent):
        return IntentResult("ORDERS_BY_CHANNEL", 0.9, "rule_4_orders_by_channel_dictionary")

    # -------------------------------------------------------------
    # 5. PAYMENT_METHODS_STATS: Thống kê phương thức thanh toán
    # -------------------------------------------------------------
    if RE_PAYMENT_1.search(text) or RE_PAYMENT_2.search(text):
        return IntentResult("PAYMENT_METHODS_STATS", 1.0, "rule_5_payment_methods_stats")

    # -------------------------------------------------------------
    # 6. CUSTOMERS_BY_CITY: Thống kê khách hàng theo tỉnh thành
    # -------------------------------------------------------------
    if RE_CITY_1.search(text) or RE_CITY_2.search(text):
        return IntentResult("CUSTOMERS_BY_CITY", 1.0, "rule_6_customers_by_city")

    # -------------------------------------------------------------
    # 7. SUPPLIER_PURCHASE_TOTAL: Tổng tiền nhập hàng từ các nhà cung cấp
    # -------------------------------------------------------------
    if RE_SUPPLIER.search(text) or RE_SUPPLIER.search(no_accent):
        return IntentResult("SUPPLIER_PURCHASE_TOTAL", 1.0, "rule_7_supplier_purchase_total")

    # -------------------------------------------------------------
    # 8. SALES_BY_MONTH: Doanh thu theo từng tháng (hoặc tháng nào cao nhất)
    # -------------------------------------------------------------
    if RE_SALES_MONTH_1.search(text) or RE_SALES_MONTH_2.search(text) or RE_SALES_MONTH_YEAR.search(text) or \
       ("doanh thu" in no_accent and ("thang" in no_accent or "thang nao" in no_accent)):
        return IntentResult("SALES_BY_MONTH", 1.0, "rule_8_sales_by_month")

    # -------------------------------------------------------------
    # 9. COUNT_ORDERS (Đưa lên TRƯỚC ORDERS_BY_STATUS theo A1-5)
    # -------------------------------------------------------------
    if RE_COUNT_ORDERS.search(text) or RE_COUNT_ORDERS.search(no_accent):
        return IntentResult("COUNT_ORDERS", 1.0, "rule_9_count_orders")

    # -------------------------------------------------------------
    # 10. TOTAL_REVENUE (Đưa lên TRƯỚC ORDERS_BY_STATUS theo A1-5)
    # -------------------------------------------------------------
    if RE_TOTAL_REVENUE.search(text) or RE_TOTAL_REVENUE.search(no_accent):
        return IntentResult("TOTAL_REVENUE", 1.0, "rule_10_total_revenue")

    # -------------------------------------------------------------
    # 11. ORDERS_COUNT_BY_STATUS: Thống kê số lượng đơn theo từng trạng thái
    # -------------------------------------------------------------
    if RE_COUNT_STATUS_1.search(text) or RE_COUNT_STATUS_2.search(text):
        return IntentResult("ORDERS_COUNT_BY_STATUS", 1.0, "rule_11_orders_count_by_status")

    # -------------------------------------------------------------
    # 12. ORDERS_BY_STATUS: Danh sách đơn hàng theo trạng thái cụ thể
    # -------------------------------------------------------------
    status = extract_order_status(text)
    if status is not None and (
        RE_ORDERS_STATUS_WORD.search(text) or RE_ORDERS_STATUS_PHRASE.search(text)
    ):
        return IntentResult("ORDERS_BY_STATUS", 1.0, "rule_12_orders_by_status")

    # -------------------------------------------------------------
    # 13. LOW_STOCK: Cảnh báo tồn kho thấp / sắp hết hàng
    # -------------------------------------------------------------
    if RE_LOW_STOCK.search(text) or RE_LOW_STOCK.search(no_accent):
        return IntentResult("LOW_STOCK", 1.0, "rule_13_low_stock")

    # -------------------------------------------------------------
    # 14. TOP_PRODUCTS_BY_PRICE_DESC / ASC: Xếp hạng sản phẩm theo giá (A1-5)
    # Chỉ kích hoạt khi có ngữ cảnh sản phẩm/giá và KHÔNG chứa từ chỉ thực thể phi sản phẩm
    # -------------------------------------------------------------
    has_non_product = bool(RE_NON_PRODUCT_ENTITY.search(text))
    has_product_context = bool(RE_PRODUCT_CONTEXT.search(text))

    if not has_non_product:
        if RE_PRICE_DESC_EXPLICIT.search(text) or RE_PRICE_DESC_EXPLICIT.search(no_accent):
            return IntentResult("TOP_PRODUCTS_BY_PRICE_DESC", 1.0, "rule_14_top_price_desc_explicit")

        if RE_PRICE_ASC_EXPLICIT.search(text) or RE_PRICE_ASC_EXPLICIT.search(no_accent):
            return IntentResult("TOP_PRODUCTS_BY_PRICE_ASC", 1.0, "rule_14_top_price_asc_explicit")

        if RE_SUPERLATIVE_GENERIC.search(text) or RE_SUPERLATIVE_GENERIC.search(no_accent):
            if has_product_context:
                return IntentResult("TOP_PRODUCTS_BY_PRICE_DESC", 1.0, "rule_14_top_price_desc_context")
            else:
                # "cao nhất" trần không có ngữ cảnh -> confidence 0.6
                return IntentResult(
                    "TOP_PRODUCTS_BY_PRICE_DESC", 0.6, "rule_14_superlative_generic_low_conf",
                    ["TOP_PRODUCTS_BY_PRICE_DESC", "SALES_BY_MONTH", "TOP_SPENDING_CUSTOMERS"],
                )

    # -------------------------------------------------------------
    # 15. LỌC SẢN PHẨM THEO GIÁ (BETWEEN, >, <, >=, <=)
    # -------------------------------------------------------------
    price_cond = extract_price_condition(text)
    if price_cond:
        op = price_cond.get("operator")
        if op == "BETWEEN":
            return IntentResult("FILTER_PRODUCTS_BY_PRICE_RANGE", 1.0, "rule_15_price_range")
        elif op in (">", "<", ">=", "<="):
            return IntentResult("FILTER_PRODUCTS_BY_PRICE", 1.0, "rule_15_price_filter")

    # -------------------------------------------------------------
    # 16. FILTER_BY_CATEGORY: Lọc sản phẩm theo danh mục (12 danh mục)
    # -------------------------------------------------------------
    category = extract_category(text)
    if category is not None:
        return IntentResult("FILTER_BY_CATEGORY", 1.0, "rule_16_filter_by_category")

    # -------------------------------------------------------------
    # 17. FILTER_BY_BRAND: Lọc sản phẩm theo hãng sản xuất (30 hãng)
    # -------------------------------------------------------------
    brand = extract_brand(text)
    if brand is not None:
        return IntentResult("FILTER_BY_BRAND", 1.0, "rule_17_filter_by_brand")

    # -------------------------------------------------------------
    # 18. LIST_PRODUCTS: Liệt kê danh sách sản phẩm chung
    # -------------------------------------------------------------
    if RE_LIST_PRODUCTS.search(text) or RE_LIST_PRODUCTS.search(no_accent):
        return IntentResult("LIST_PRODUCTS", 1.0, "rule_18_list_products")

    if re.match(r'^(sản phẩm|san pham|linh kiện|linh kien)$', text):
        return IntentResult("LIST_PRODUCTS", 0.9, "rule_18_list_products_short")

    # -------------------------------------------------------------
    # 19. DỰ PHÒNG HỌC MÁY (ML Fallback): TF-IDF + Logistic Regression
    # Chỉ chạy khi toàn bộ luật không khớp. Độ tin cậy = xác suất của mô hình.
    # -------------------------------------------------------------
    return _ml_fallback(text)


def _ml_fallback(text: str) -> IntentResult:
    """Gọi bộ phân loại học máy khi luật regex không nhận diện được câu hỏi."""
    if not ML_FALLBACK_ENABLED:
        return IntentResult("UNKNOWN", 0.0, "rule_unknown")
    try:
        from app.ml_intent_classifier import (
            ML_ACCEPT_THRESHOLD,
            ML_SUGGEST_THRESHOLD,
            get_ml_classifier,
        )
        ml_intent, prob, alternatives = get_ml_classifier().predict(text)
    except Exception:  # Lỗi ML không được làm sập luồng chính
        return IntentResult("UNKNOWN", 0.0, "rule_unknown")

    if ml_intent is None:
        return IntentResult("UNKNOWN", 0.0, "ml_out_of_scope", alternatives)

    prob = round(prob, 3)
    if prob >= ML_ACCEPT_THRESHOLD:
        # Kẹp tối thiểu 0.7 để pipeline chấp nhận (ngưỡng chấp nhận đã kiểm soát chất lượng)
        return IntentResult(ml_intent, max(prob, 0.7), "ml_fallback_accept", alternatives)
    if prob >= ML_SUGGEST_THRESHOLD:
        # Không đủ chắc chắn: trả confidence thấp để pipeline hỏi lại kèm gợi ý
        return IntentResult(ml_intent, min(prob, 0.69), "ml_fallback_suggest", [ml_intent] + alternatives)
    return IntentResult("UNKNOWN", 0.0, "ml_low_confidence", [ml_intent] + alternatives)
