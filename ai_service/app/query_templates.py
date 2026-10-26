"""
Định nghĩa các mẫu SQL an toàn (Query Templates) cho 20 Intent vàng
CSDL: LinhKien_DB, Schema: "LinhKien"
"""

TEMPLATES = {
    # 1. Danh sách sản phẩm đang bán
    "LIST_PRODUCTS": """
SELECT id, ma_sku, ten, gia_niem_yet, bao_hanh_thang 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
LIMIT %s;
""".strip(),

    # 2. Lọc sản phẩm theo giá (> hoặc <)
    "FILTER_PRODUCTS_BY_PRICE_GT": """
SELECT id, ten, gia_niem_yet 
FROM san_pham 
WHERE gia_niem_yet > %s AND dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC;
""".strip(),

    "FILTER_PRODUCTS_BY_PRICE_LT": """
SELECT id, ten, gia_niem_yet 
FROM san_pham 
WHERE gia_niem_yet < %s AND dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC;
""".strip(),

    # 3. Các linh kiện có giá từ Min đến Max
    "FILTER_PRODUCTS_BY_PRICE_RANGE": """
SELECT id, ten, gia_niem_yet 
FROM san_pham 
WHERE gia_niem_yet BETWEEN %s AND %s AND dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC;
""".strip(),

    # 4. Top N sản phẩm đắt nhất
    "TOP_PRODUCTS_BY_PRICE_DESC": """
SELECT ten, gia_niem_yet 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet DESC 
LIMIT %s;
""".strip(),

    # 5. Top N linh kiện rẻ nhất
    "TOP_PRODUCTS_BY_PRICE_ASC": """
SELECT ten, gia_niem_yet 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC 
LIMIT %s;
""".strip(),

    # 6. Đếm tổng số đơn hàng của cửa hàng
    "COUNT_ORDERS": """
SELECT COUNT(*) AS tong_so_don 
FROM don_hang;
""".strip(),

    # 7. Danh sách các đơn hàng theo trạng thái
    "ORDERS_BY_STATUS": """
SELECT id, ngay_dat, kenh_ban, tong_tien 
FROM don_hang 
WHERE trang_thai = %s 
ORDER BY ngay_dat DESC 
LIMIT %s;
""".strip(),

    # 8. Liệt kê sản phẩm theo danh mục
    "FILTER_BY_CATEGORY": """
SELECT sp.id, sp.ten, dm.ten AS danh_muc, sp.gia_niem_yet 
FROM san_pham sp 
JOIN danh_muc dm ON sp.danh_muc_id = dm.id 
WHERE dm.ten ILIKE %s;
""".strip(),

    # 9. Tìm các sản phẩm của hãng
    "FILTER_BY_BRAND": """
SELECT sp.id, sp.ten, th.ten AS thuong_hieu, sp.gia_niem_yet 
FROM san_pham sp 
JOIN thuong_hieu th ON sp.thuong_hieu_id = th.id 
WHERE th.ten ILIKE %s;
""".strip(),

    # 10. Những sản phẩm sắp hết hàng trong kho (A1-8: thêm dang_kinh_doanh)
    "LOW_STOCK": """
SELECT sp.ten, tk.so_luong_ton, tk.muc_ton_toi_thieu 
FROM san_pham sp 
JOIN ton_kho tk ON sp.id = tk.san_pham_id 
WHERE tk.so_luong_ton <= tk.muc_ton_toi_thieu AND sp.dang_kinh_doanh = TRUE 
ORDER BY tk.so_luong_ton ASC;
""".strip(),

    # 11. Thống kê số lượng đơn hàng theo từng trạng thái
    "ORDERS_COUNT_BY_STATUS": """
SELECT trang_thai, COUNT(*) AS so_don 
FROM don_hang 
GROUP BY trang_thai 
ORDER BY so_don DESC;
""".strip(),

    # 12. Thống kê số đơn và doanh thu theo từng kênh bán
    "ORDERS_BY_CHANNEL": """
SELECT kenh_ban, COUNT(*) AS so_don, SUM(tong_tien) AS tong_doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh' 
GROUP BY kenh_ban 
ORDER BY tong_doanh_thu DESC;
""".strip(),

    # 13. Thống kê phương thức thanh toán
    "PAYMENT_METHODS_STATS": """
SELECT phuong_thuc, COUNT(*) AS so_lan, SUM(so_tien) AS tong_tien 
FROM thanh_toan 
WHERE trang_thai = 'da_thanh_toan' 
GROUP BY phuong_thuc 
ORDER BY so_lan DESC;
""".strip(),

    # 14. Thống kê số lượng khách hàng theo từng tỉnh thành (A1-8: lọc mac_dinh = TRUE)
    "CUSTOMERS_BY_CITY": """
SELECT dc.tinh_thanh, COUNT(DISTINCT kh.id) AS so_khach 
FROM khach_hang kh 
JOIN dia_chi dc ON kh.id = dc.khach_hang_id AND dc.mac_dinh = TRUE 
GROUP BY dc.tinh_thanh 
ORDER BY so_khach DESC;
""".strip(),

    # 15. Top N sản phẩm bán chạy nhất
    "BEST_SELLING_PRODUCTS": """
SELECT sp.id, sp.ten, SUM(ct.so_luong) AS tong_da_ban 
FROM chi_tiet_don_hang ct 
JOIN don_hang dh ON ct.don_hang_id = dh.id 
JOIN san_pham sp ON ct.san_pham_id = sp.id 
WHERE dh.trang_thai = 'hoan_thanh' 
GROUP BY sp.id, sp.ten 
ORDER BY tong_da_ban DESC 
LIMIT %s;
""".strip(),

    # 16. Top N khách hàng mua nhiều tiền nhất (A1-8: che số điện thoại)
    "TOP_SPENDING_CUSTOMERS": """
SELECT kh.id, kh.ho_ten, CONCAT(SUBSTRING(kh.so_dien_thoai, 1, 6), '****') AS so_dien_thoai, SUM(dh.tong_tien) AS tong_chi_tieu 
FROM khach_hang kh 
JOIN don_hang dh ON kh.id = dh.khach_hang_id 
WHERE dh.trang_thai = 'hoan_thanh' 
GROUP BY kh.id, kh.ho_ten, kh.so_dien_thoai 
ORDER BY tong_chi_tieu DESC 
LIMIT %s;
""".strip(),

    # 17. Thống kê doanh thu theo từng tháng trong năm
    "SALES_BY_MONTH": """
SELECT TO_CHAR(ngay_dat, 'YYYY-MM') AS thang, COUNT(*) AS so_don, SUM(tong_tien) AS doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh' AND EXTRACT(YEAR FROM ngay_dat) = %s 
GROUP BY TO_CHAR(ngay_dat, 'YYYY-MM') 
ORDER BY thang ASC;
""".strip(),

    # 18. Doanh số bán hàng của từng nhân viên (A1-8: LEFT JOIN và lọc dang_lam_viec = TRUE)
    "EMPLOYEE_PERFORMANCE": """
SELECT nv.id, nv.ho_ten, nv.chuc_vu, COUNT(dh.id) AS so_don_ban, COALESCE(SUM(dh.tong_tien), 0) AS tong_doanh_so 
FROM nhan_vien nv 
LEFT JOIN don_hang dh ON nv.id = dh.nhan_vien_id AND dh.trang_thai = 'hoan_thanh' 
WHERE nv.dang_lam_viec = TRUE 
GROUP BY nv.id, nv.ho_ten, nv.chuc_vu 
ORDER BY tong_doanh_so DESC;
""".strip(),

    # 19. Tổng doanh thu của tất cả đơn hàng đã hoàn thành
    "TOTAL_REVENUE": """
SELECT SUM(tong_tien) AS tong_doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh';
""".strip(),

    # 20. Tổng tiền nhập hàng từ các nhà cung cấp
    "SUPPLIER_PURCHASE_TOTAL": """
SELECT ncc.id, ncc.ten, COUNT(pn.id) AS so_phieu_nhap, SUM(pn.tong_tien) AS tong_tien_nhap 
FROM nha_cung_cap ncc 
JOIN phieu_nhap pn ON ncc.id = pn.nha_cung_cap_id 
GROUP BY ncc.id, ncc.ten 
ORDER BY tong_tien_nhap DESC;
""".strip(),
}
