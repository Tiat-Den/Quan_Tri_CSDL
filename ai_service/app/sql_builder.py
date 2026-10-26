"""
Module lắp ráp câu SQL từ template và tham số an toàn (SQL Builder) cho 20 Intent vàng.
Hỗ trợ ghép nhiều điều kiện đồng thời (Composite Filters: danh mục + hãng + giá + limit),
chống bỏ sót ràng buộc thầm lặng (A1-4) và bảo toàn tính tương thích hoàn hảo.
"""
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config import DEFAULT_LIMIT, MAX_LIMIT
from app.query_templates import TEMPLATES


class SQLBuildResult:
    """
    Kết quả dựng SQL kèm danh sách thực thể đã sử dụng (A1-4).
    Hỗ trợ cả tuple unpacking (sql, params) để không phá vỡ 24 unit test cũ,
    vừa cung cấp thuộc tính .used_entities cho pipeline kiểm tra điều kiện thừa.
    """
    def __init__(self, sql: Optional[str], params: List[Any], used_entities: Optional[Set[str]] = None):
        self.sql = sql
        self.params = params
        self.used_entities = used_entities or set()

    def __iter__(self):
        yield self.sql
        yield self.params

    def __getitem__(self, idx):
        if idx == 0:
            return self.sql
        elif idx == 1:
            return self.params
        elif idx == 2:
            return self.used_entities
        raise IndexError("SQLBuildResult chỉ hỗ trợ chỉ số 0: sql, 1: params, 2: used_entities")

    def __len__(self):
        return 2

    def __repr__(self):
        return f"SQLBuildResult(sql={bool(self.sql)}, params_count={len(self.params)}, used_entities={self.used_entities})"


def _build_composite_product_sql(intent: str, entities: Dict[str, Any]) -> SQLBuildResult:
    """Bộ dựng SQL hợp nhất cho các intent truy vấn sản phẩm hỗ trợ nhiều điều kiện kết hợp (A1-4)."""
    used_entities: Set[str] = set()
    params: List[Any] = []
    where_clauses: List[str] = ["sp.dang_kinh_doanh = TRUE"]
    joins: List[str] = []

    # 1. Lọc theo Danh mục
    cat = entities.get("category_name")
    if cat:
        joins.append("JOIN danh_muc dm ON sp.danh_muc_id = dm.id")
        where_clauses.append("dm.ten ILIKE %s")
        params.append(f"%{cat}%")
        used_entities.add("category_name")

    # 2. Lọc theo Thương hiệu / Hãng
    brand = entities.get("brand_name")
    if brand:
        joins.append("JOIN thuong_hieu th ON sp.thuong_hieu_id = th.id")
        where_clauses.append("th.ten ILIKE %s")
        params.append(f"%{brand}%")
        used_entities.add("brand_name")

    # 3. Lọc theo Giá
    op = entities.get("operator")
    if op == "BETWEEN":
        min_p = entities.get("min_price", 0)
        max_p = entities.get("max_price", 0)
        where_clauses.append("sp.gia_niem_yet BETWEEN %s AND %s")
        params.extend([min_p, max_p])
        used_entities.update({"operator", "min_price", "max_price"})
    elif op in (">", ">=", "<", "<="):
        price = entities.get("price_value", 0)
        where_clauses.append(f"sp.gia_niem_yet {op} %s")
        params.append(price)
        used_entities.update({"operator", "price_value"})

    # 4. Sắp xếp (Order By)
    if intent == "TOP_PRODUCTS_BY_PRICE_DESC":
        order_by = "ORDER BY sp.gia_niem_yet DESC"
    elif intent == "TOP_PRODUCTS_BY_PRICE_ASC":
        order_by = "ORDER BY sp.gia_niem_yet ASC"
    elif op:
        order_by = "ORDER BY sp.gia_niem_yet ASC"
    else:
        order_by = "ORDER BY sp.id ASC"

    # 5. Giới hạn (Limit)
    user_limit = entities.get("limit")
    if user_limit is not None:
        try:
            limit_val = min(max(1, int(user_limit)), MAX_LIMIT)
        except (ValueError, TypeError):
            limit_val = DEFAULT_LIMIT
        used_entities.add("limit")
    else:
        if intent in ("TOP_PRODUCTS_BY_PRICE_DESC", "TOP_PRODUCTS_BY_PRICE_ASC"):
            limit_val = 5 if intent == "TOP_PRODUCTS_BY_PRICE_DESC" else 10
        elif intent == "LIST_PRODUCTS":
            limit_val = DEFAULT_LIMIT
            used_entities.add("limit")
        else:
            limit_val = MAX_LIMIT

    # Xác định các cột SELECT
    select_cols = ["sp.id", "sp.ten", "sp.gia_niem_yet"]
    if cat:
        select_cols.append("dm.ten AS danh_muc")
    if brand:
        select_cols.append("th.ten AS thuong_hieu")
    if intent == "LIST_PRODUCTS" and not cat and not brand and not op:
        select_cols = ["sp.id", "sp.ma_sku", "sp.ten", "sp.gia_niem_yet", "sp.bao_hanh_thang"]

    join_str = ("\n" + "\n".join(joins)) if joins else ""
    where_str = "\nWHERE " + "\n  AND ".join(where_clauses)
    sql = f"SELECT {', '.join(select_cols)}\nFROM san_pham sp{join_str}{where_str}\n{order_by}\nLIMIT %s;"
    params.append(limit_val)

    return SQLBuildResult(sql, params, used_entities)


def build_sql(intent: str, entities: Dict[str, Any]) -> SQLBuildResult:
    """
    Sinh câu lệnh SQL an toàn và danh sách tham số tương ứng cho 20 Intent vàng.
    Hỗ trợ ghép nhiều điều kiện lọc và theo dõi thực thể được dùng (used_entities).
    """
    # Xử lý các intent thuộc nhóm sản phẩm bằng bộ dựng composite nếu có nhiều điều kiện
    product_intents = {
        "LIST_PRODUCTS",
        "FILTER_PRODUCTS_BY_PRICE",
        "FILTER_PRODUCTS_BY_PRICE_RANGE",
        "FILTER_BY_CATEGORY",
        "FILTER_BY_BRAND",
        "TOP_PRODUCTS_BY_PRICE_DESC",
        "TOP_PRODUCTS_BY_PRICE_ASC",
    }

    has_cat = bool(entities.get("category_name"))
    has_brand = bool(entities.get("brand_name"))
    has_price = bool(entities.get("operator"))
    has_top = intent in ("TOP_PRODUCTS_BY_PRICE_DESC", "TOP_PRODUCTS_BY_PRICE_ASC")

    # Kích hoạt composite builder khi có từ 2 điều kiện trở lên kết hợp,
    # hoặc khi có Top N đắt/rẻ nhất kết hợp với hãng hoặc danh mục
    is_composite = (
        (has_cat and has_brand)
        or (has_cat and has_price)
        or (has_brand and has_price)
        or (has_top and (has_cat or has_brand or has_price))
        or (intent == "LIST_PRODUCTS" and (has_cat or has_brand or has_price))
    )

    if intent in product_intents and is_composite:
        return _build_composite_product_sql(intent, entities)

    # 1. Danh sách sản phẩm đang bán
    if intent == "LIST_PRODUCTS":
        limit = entities.get("limit") or DEFAULT_LIMIT
        try:
            limit = min(max(1, int(limit)), MAX_LIMIT)
        except (ValueError, TypeError):
            limit = DEFAULT_LIMIT
        return SQLBuildResult(TEMPLATES["LIST_PRODUCTS"], [limit], {"limit"})

    # 2. Tìm sản phẩm theo giá
    elif intent == "FILTER_PRODUCTS_BY_PRICE":
        operator = entities.get("operator", ">")
        price = entities.get("price_value", 0)
        used = {"operator", "price_value"}
        if operator in (">", ">="):
            tpl = TEMPLATES["FILTER_PRODUCTS_BY_PRICE_GT"]
            if operator == ">=":
                tpl = tpl.replace("gia_niem_yet > %s", "gia_niem_yet >= %s")
            return SQLBuildResult(tpl, [price], used)
        else:
            tpl = TEMPLATES["FILTER_PRODUCTS_BY_PRICE_LT"]
            if operator == "<=":
                tpl = tpl.replace("gia_niem_yet < %s", "gia_niem_yet <= %s")
            return SQLBuildResult(tpl, [price], used)

    # 3. Các linh kiện có giá từ Min đến Max
    elif intent == "FILTER_PRODUCTS_BY_PRICE_RANGE":
        min_p = entities.get("min_price", 0)
        max_p = entities.get("max_price", 0)
        return SQLBuildResult(
            TEMPLATES["FILTER_PRODUCTS_BY_PRICE_RANGE"],
            [min_p, max_p],
            {"operator", "min_price", "max_price"},
        )

    # 4. Top N sản phẩm đắt nhất
    elif intent == "TOP_PRODUCTS_BY_PRICE_DESC":
        top_n = entities.get("limit") or 5
        top_n = min(max(1, int(top_n)), MAX_LIMIT)
        return SQLBuildResult(TEMPLATES["TOP_PRODUCTS_BY_PRICE_DESC"], [top_n], {"limit"})

    # 5. Top N linh kiện rẻ nhất
    elif intent == "TOP_PRODUCTS_BY_PRICE_ASC":
        top_n = entities.get("limit") or 10
        top_n = min(max(1, int(top_n)), MAX_LIMIT)
        return SQLBuildResult(TEMPLATES["TOP_PRODUCTS_BY_PRICE_ASC"], [top_n], {"limit"})

    # 6. Đếm tổng số đơn hàng của cửa hàng (Hỗ trợ lọc thêm status, year, channel)
    elif intent == "COUNT_ORDERS":
        where_clauses = []
        params = []
        used = set()
        if entities.get("status"):
            where_clauses.append("trang_thai = %s")
            params.append(entities["status"])
            used.add("status")
        if entities.get("year"):
            where_clauses.append("EXTRACT(YEAR FROM ngay_dat) = %s")
            params.append(entities["year"])
            used.add("year")
        if entities.get("channel"):
            where_clauses.append("kenh_ban = %s")
            params.append(entities["channel"])
            used.add("channel")

        if where_clauses:
            sql = f"SELECT COUNT(*) AS tong_so_don FROM don_hang WHERE {' AND '.join(where_clauses)};"
            return SQLBuildResult(sql, params, used)
        return SQLBuildResult(TEMPLATES["COUNT_ORDERS"], [], used)

    # 7. Danh sách các đơn hàng theo trạng thái (Hỗ trợ lọc thêm year, channel)
    elif intent == "ORDERS_BY_STATUS":
        status = entities.get("status") or "da_huy"
        top_n = entities.get("limit") or 20
        top_n = min(max(1, int(top_n)), MAX_LIMIT)
        used = {"status", "limit"}

        extra_where = []
        extra_params = []
        if entities.get("year"):
            extra_where.append("AND EXTRACT(YEAR FROM ngay_dat) = %s")
            extra_params.append(entities["year"])
            used.add("year")
        if entities.get("channel"):
            extra_where.append("AND kenh_ban = %s")
            extra_params.append(entities["channel"])
            used.add("channel")

        if extra_where:
            sql = (
                f"SELECT id, ngay_dat, kenh_ban, tong_tien FROM don_hang "
                f"WHERE trang_thai = %s {' '.join(extra_where)} "
                f"ORDER BY ngay_dat DESC LIMIT %s;"
            )
            return SQLBuildResult(sql, [status] + extra_params + [top_n], used)

        return SQLBuildResult(TEMPLATES["ORDERS_BY_STATUS"], [status, top_n], used)

    # 8. Liệt kê sản phẩm theo danh mục
    elif intent == "FILTER_BY_CATEGORY":
        category = entities.get("category_name") or "VGA"
        return SQLBuildResult(TEMPLATES["FILTER_BY_CATEGORY"], [f"%{category}%"], {"category_name"})

    # 9. Tìm các sản phẩm của hãng
    elif intent == "FILTER_BY_BRAND":
        brand = entities.get("brand_name") or "ASUS"
        return SQLBuildResult(TEMPLATES["FILTER_BY_BRAND"], [f"%{brand}%"], {"brand_name"})

    # 10. Những sản phẩm sắp hết hàng trong kho
    elif intent == "LOW_STOCK":
        return SQLBuildResult(TEMPLATES["LOW_STOCK"], [], set())

    # 11. Thống kê số lượng đơn hàng theo từng trạng thái
    elif intent == "ORDERS_COUNT_BY_STATUS":
        return SQLBuildResult(TEMPLATES["ORDERS_COUNT_BY_STATUS"], [], set())

    # 12. Thống kê số đơn và doanh thu theo từng kênh bán (Hỗ trợ lọc channel cụ thể)
    elif intent == "ORDERS_BY_CHANNEL":
        channel = entities.get("channel")
        if channel:
            sql = (
                "SELECT kenh_ban, COUNT(*) AS so_don, SUM(tong_tien) AS tong_doanh_thu "
                "FROM don_hang WHERE trang_thai = 'hoan_thanh' AND kenh_ban = %s "
                "GROUP BY kenh_ban ORDER BY tong_doanh_thu DESC;"
            )
            return SQLBuildResult(sql, [channel], {"channel"})
        return SQLBuildResult(TEMPLATES["ORDERS_BY_CHANNEL"], [], set())

    # 13. Thống kê phương thức thanh toán (Hỗ trợ lọc phương thức cụ thể)
    elif intent == "PAYMENT_METHODS_STATS":
        pm = entities.get("payment_method")
        if pm:
            sql = (
                "SELECT phuong_thuc, COUNT(*) AS so_lan, SUM(so_tien) AS tong_tien "
                "FROM thanh_toan WHERE trang_thai = 'da_thanh_toan' AND phuong_thuc = %s "
                "GROUP BY phuong_thuc ORDER BY so_lan DESC;"
            )
            return SQLBuildResult(sql, [pm], {"payment_method"})
        return SQLBuildResult(TEMPLATES["PAYMENT_METHODS_STATS"], [], set())

    # 14. Thống kê số lượng khách hàng theo từng tỉnh thành
    elif intent == "CUSTOMERS_BY_CITY":
        return SQLBuildResult(TEMPLATES["CUSTOMERS_BY_CITY"], [], set())

    # 15. Top N sản phẩm bán chạy nhất
    elif intent == "BEST_SELLING_PRODUCTS":
        top_n = entities.get("limit") or 5
        top_n = min(max(1, int(top_n)), MAX_LIMIT)
        return SQLBuildResult(TEMPLATES["BEST_SELLING_PRODUCTS"], [top_n], {"limit"})

    # 16. Top N khách hàng mua nhiều tiền nhất
    elif intent == "TOP_SPENDING_CUSTOMERS":
        top_n = entities.get("limit") or 5
        top_n = min(max(1, int(top_n)), MAX_LIMIT)
        return SQLBuildResult(TEMPLATES["TOP_SPENDING_CUSTOMERS"], [top_n], {"limit"})

    # 17. Thống kê doanh thu theo từng tháng trong năm (Mặc định 2025 nếu khuyết)
    elif intent == "SALES_BY_MONTH":
        year = entities.get("year") or 2025
        used = {"year"}
        channel = entities.get("channel")
        if channel:
            sql = (
                "SELECT TO_CHAR(ngay_dat, 'YYYY-MM') AS thang, COUNT(*) AS so_don, SUM(tong_tien) AS doanh_thu "
                "FROM don_hang WHERE trang_thai = 'hoan_thanh' AND EXTRACT(YEAR FROM ngay_dat) = %s AND kenh_ban = %s "
                "GROUP BY TO_CHAR(ngay_dat, 'YYYY-MM') ORDER BY thang ASC;"
            )
            used.add("channel")
            return SQLBuildResult(sql, [year, channel], used)
        return SQLBuildResult(TEMPLATES["SALES_BY_MONTH"], [year], used)

    # 18. Doanh số bán hàng của từng nhân viên
    elif intent == "EMPLOYEE_PERFORMANCE":
        return SQLBuildResult(TEMPLATES["EMPLOYEE_PERFORMANCE"], [], set())

    # 19. Tổng doanh thu đơn hoàn thành (Hỗ trợ lọc thêm year, channel)
    elif intent == "TOTAL_REVENUE":
        where_clauses = ["trang_thai = 'hoan_thanh'"]
        params = []
        used = set()
        if entities.get("status"):
            used.add("status")
            if entities["status"] != "hoan_thanh":
                where_clauses = ["trang_thai = %s"]
                params.append(entities["status"])
        if entities.get("year"):
            where_clauses.append("EXTRACT(YEAR FROM ngay_dat) = %s")
            params.append(entities["year"])
            used.add("year")
        if entities.get("channel"):
            where_clauses.append("kenh_ban = %s")
            params.append(entities["channel"])
            used.add("channel")

        sql = f"SELECT SUM(tong_tien) AS tong_doanh_thu FROM don_hang WHERE {' AND '.join(where_clauses)};"
        return SQLBuildResult(sql, params, used)

    # 20. Tổng tiền nhập hàng từ các nhà cung cấp
    elif intent == "SUPPLIER_PURCHASE_TOTAL":
        return SQLBuildResult(TEMPLATES["SUPPLIER_PURCHASE_TOTAL"], [], set())

    return SQLBuildResult(None, [], set())
