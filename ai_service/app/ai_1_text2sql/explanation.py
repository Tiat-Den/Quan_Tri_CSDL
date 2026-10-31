"""
Module tạo lời giải thích logic theo quy tắc (Rule-based Explanation) cho 20 Intent vàng.
Hỗ trợ nêu đầy đủ mọi điều kiện đã áp dụng từ used_entities (A1-4).
"""
from typing import Any, Dict, Optional, Set

from app.config import MAX_LIMIT


def generate_explanation(
    intent: str,
    entities: Dict[str, Any],
    used_entities: Optional[Set[str]] = None,
) -> str:
    """
    Tạo lời giải thích dễ hiểu theo luật đã kích hoạt cho 20 Intent vàng.
    Liệt kê đầy đủ mọi điều kiện lọc đã đi vào câu SQL (A1-4).
    """
    applied_notes = []

    # 1. LIST_PRODUCTS
    if intent == "LIST_PRODUCTS":
        base_exp = "Nhận diện yêu cầu liệt kê các sản phẩm đang kinh doanh. Áp dụng template truy vấn bảng `san_pham` với điều kiện `dang_kinh_doanh = TRUE`."

    # 2. FILTER_PRODUCTS_BY_PRICE
    elif intent == "FILTER_PRODUCTS_BY_PRICE":
        op = entities.get("operator", ">")
        val = entities.get("price_value", 0)
        formatted_val = f"{val:,.0f} VNĐ"
        if op == ">":
            base_exp = f"Nhận diện yêu cầu lọc sản phẩm có giá lớn hơn {formatted_val}. Áp dụng template lọc `gia_niem_yet > %s` và sắp xếp giá tăng dần."
        elif op == ">=":
            base_exp = f"Nhận diện yêu cầu lọc sản phẩm có giá từ {formatted_val} trở lên. Áp dụng template lọc `gia_niem_yet >= %s` và sắp xếp giá tăng dần."
        elif op == "<=":
            base_exp = f"Nhận diện yêu cầu lọc sản phẩm có giá không quá {formatted_val}. Áp dụng template lọc `gia_niem_yet <= %s` và sắp xếp giá tăng dần."
        else:
            base_exp = f"Nhận diện yêu cầu lọc sản phẩm có giá nhỏ hơn {formatted_val}. Áp dụng template lọc `gia_niem_yet < %s` và sắp xếp giá tăng dần."

    # 3. FILTER_PRODUCTS_BY_PRICE_RANGE
    elif intent == "FILTER_PRODUCTS_BY_PRICE_RANGE":
        min_p = entities.get("min_price", 0)
        max_p = entities.get("max_price", 0)
        base_exp = f"Nhận diện yêu cầu lọc sản phẩm trong khoảng giá từ {min_p:,.0f} VNĐ đến {max_p:,.0f} VNĐ. Áp dụng điều kiện `gia_niem_yet BETWEEN %s AND %s`."

    # 4. TOP_PRODUCTS_BY_PRICE_DESC
    elif intent == "TOP_PRODUCTS_BY_PRICE_DESC":
        n = entities.get("limit", 5)
        base_exp = f"Nhận diện yêu cầu xem Top {n} sản phẩm đắt nhất/giá cao nhất. Áp dụng sắp xếp `ORDER BY gia_niem_yet DESC LIMIT %s`."

    # 5. TOP_PRODUCTS_BY_PRICE_ASC
    elif intent == "TOP_PRODUCTS_BY_PRICE_ASC":
        n = entities.get("limit", 10)
        base_exp = f"Nhận diện yêu cầu xem Top {n} sản phẩm rẻ nhất/giá thấp nhất. Áp dụng sắp xếp `ORDER BY gia_niem_yet ASC LIMIT %s`."

    # 6. COUNT_ORDERS
    elif intent == "COUNT_ORDERS":
        base_exp = "Nhận diện yêu cầu đếm tổng số đơn hàng của cửa hàng. Áp dụng hàm tổng hợp `COUNT(*)` trên bảng `don_hang`."

    # 7. ORDERS_BY_STATUS
    elif intent == "ORDERS_BY_STATUS":
        status = entities.get("status", "da_huy")
        base_exp = f"Nhận diện yêu cầu xem danh sách đơn hàng theo trạng thái '{status}'. Áp dụng bộ lọc `trang_thai = %s` trên bảng `don_hang` sắp xếp theo ngày đặt mới nhất."

    # 8. FILTER_BY_CATEGORY
    elif intent == "FILTER_BY_CATEGORY":
        cat = entities.get("category_name", "VGA")
        base_exp = f"Nhận diện danh mục linh kiện '{cat}'. Áp dụng phép `JOIN danh_muc` và tìm kiếm tương đối `dm.ten ILIKE %s`."

    # 9. FILTER_BY_BRAND
    elif intent == "FILTER_BY_BRAND":
        brand = entities.get("brand_name", "ASUS")
        base_exp = f"Nhận diện thương hiệu hãng '{brand}'. Áp dụng phép `JOIN thuong_hieu` và tìm kiếm tương đối `th.ten ILIKE %s`."

    # 10. LOW_STOCK
    elif intent == "LOW_STOCK":
        base_exp = "Nhận diện yêu cầu kiểm tra hàng tồn kho thấp/sắp hết hàng. Áp dụng phép `JOIN ton_kho` với điều kiện `tk.so_luong_ton <= tk.muc_ton_toi_thieu`."

    # 11. ORDERS_COUNT_BY_STATUS
    elif intent == "ORDERS_COUNT_BY_STATUS":
        base_exp = "Nhận diện yêu cầu thống kê số lượng đơn hàng theo từng trạng thái. Áp dụng `COUNT(*)` và gom nhóm `GROUP BY trang_thai` trên bảng `don_hang`."

    # 12. ORDERS_BY_CHANNEL
    elif intent == "ORDERS_BY_CHANNEL":
        base_exp = "Nhận diện yêu cầu phân tích số đơn và doanh thu theo từng kênh bán hàng. Áp dụng `GROUP BY kenh_ban` trên các đơn hàng hoàn thành."

    # 13. PAYMENT_METHODS_STATS
    elif intent == "PAYMENT_METHODS_STATS":
        base_exp = "Nhận diện yêu cầu thống kê phương thức thanh toán phổ biến. Áp dụng `COUNT(*)` và `SUM(so_tien)` gom nhóm `GROUP BY phuong_thuc` trên các giao dịch đã thanh toán."

    # 14. CUSTOMERS_BY_CITY
    elif intent == "CUSTOMERS_BY_CITY":
        base_exp = "Nhận diện yêu cầu thống kê phân bố khách hàng theo khu vực. Áp dụng phép `JOIN dia_chi`, đếm `COUNT(DISTINCT kh.id)` và gom nhóm `GROUP BY dc.tinh_thanh`."

    # 15. BEST_SELLING_PRODUCTS
    elif intent == "BEST_SELLING_PRODUCTS":
        n = entities.get("limit", 5)
        base_exp = f"Nhận diện yêu cầu tìm Top {n} sản phẩm bán chạy nhất. Áp dụng phép JOIN 3 bảng `san_pham`, `chi_tiet_don_hang`, `don_hang` để tính tổng số lượng bán trên các đơn hoàn thành."

    # 16. TOP_SPENDING_CUSTOMERS
    elif intent == "TOP_SPENDING_CUSTOMERS":
        n = entities.get("limit", 5)
        base_exp = f"Nhận diện yêu cầu tìm Top {n} khách hàng chi tiêu nhiều nhất. Áp dụng phép `JOIN don_hang` tính tổng tiền mua sắm `SUM(dh.tong_tien)` trên các đơn hoàn thành."

    # 17. SALES_BY_MONTH
    elif intent == "SALES_BY_MONTH":
        year = entities.get("year", 2025)
        base_exp = f"Nhận diện yêu cầu thống kê doanh thu theo từng tháng trong năm {year}. Áp dụng gom nhóm `TO_CHAR(ngay_dat, 'YYYY-MM')` và lọc năm `EXTRACT(YEAR FROM ngay_dat) = %s`."

    # 18. EMPLOYEE_PERFORMANCE
    elif intent == "EMPLOYEE_PERFORMANCE":
        base_exp = "Nhận diện yêu cầu đánh giá doanh số bán hàng của từng nhân viên. Áp dụng phép `JOIN nhan_vien` với `don_hang`, tính tổng số đơn và doanh số bán được trên các đơn hoàn thành."

    # 19. TOTAL_REVENUE
    elif intent == "TOTAL_REVENUE":
        base_exp = "Nhận diện yêu cầu tính tổng doanh thu toàn bộ cửa hàng. Áp dụng hàm tính tổng `SUM(tong_tien)` trên tất cả đơn hàng có trạng thái `hoan_thanh`."

    # 20. SUPPLIER_PURCHASE_TOTAL
    elif intent == "SUPPLIER_PURCHASE_TOTAL":
        base_exp = "Nhận diện yêu cầu thống kê chi phí nhập hàng theo từng nhà cung cấp. Áp dụng phép `JOIN phieu_nhap` và gom nhóm `GROUP BY ncc.id, ncc.ten`."

    else:
        return "Câu hỏi chưa thuộc phạm vi các luật được hỗ trợ. Vui lòng thử lại với các câu hỏi mẫu."

    # Nêu thêm các điều kiện bổ sung nếu có ghép điều kiện (Composite filters)
    extra_details = []
    if entities.get("category_name") and intent != "FILTER_BY_CATEGORY":
        extra_details.append(f"Danh mục: {entities['category_name']}")
    if entities.get("brand_name") and intent != "FILTER_BY_BRAND":
        extra_details.append(f"Hãng: {entities['brand_name']}")
    if entities.get("channel") and intent != "ORDERS_BY_CHANNEL":
        extra_details.append(f"Kênh: {entities['channel']}")
    if entities.get("payment_method") and intent != "PAYMENT_METHODS_STATS":
        extra_details.append(f"Phương thức: {entities['payment_method']}")
    if entities.get("status") and intent not in ("ORDERS_BY_STATUS", "ORDERS_COUNT_BY_STATUS"):
        extra_details.append(f"Trạng thái: {entities['status']}")
    if entities.get("year") and intent != "SALES_BY_MONTH":
        extra_details.append(f"Năm: {entities['year']}")

    user_limit = entities.get("limit")
    if user_limit is not None and user_limit > MAX_LIMIT:
        extra_details.append(f"Giới hạn Top {user_limit} được kẹp còn {MAX_LIMIT} theo cấu hình an toàn")

    if extra_details:
        base_exp += " Kết hợp các điều kiện lọc: " + "; ".join(extra_details) + "."

    return base_exp
