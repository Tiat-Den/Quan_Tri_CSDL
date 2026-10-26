"""
Catalog danh mục bảng, cột và từ điển thực thể của CSDL LinhKien_DB (schema "LinhKien")
"""

# Allowlist bảng và cột được phép truy vấn trong schema "LinhKien"
# gia_von bị LOẠI BỎ khỏi allowlist của san_pham để đảm bảo Least Privilege
ALLOWLIST_TABLES = {
    "san_pham": ["id", "ma_sku", "ten", "danh_muc_id", "thuong_hieu_id", "gia_niem_yet", "bao_hanh_thang", "ngay_ra_mat", "dang_kinh_doanh", "thong_so_ky_thuat"],
    "danh_muc": ["id", "ten", "mo_ta", "danh_muc_cha_id"],
    "thuong_hieu": ["id", "ten", "quoc_gia"],
    "don_hang": ["id", "khach_hang_id", "nhan_vien_id", "dia_chi_giao_id", "ngay_dat", "ngay_giao", "trang_thai", "kenh_ban", "tong_tien"],
    "chi_tiet_don_hang": ["id", "don_hang_id", "san_pham_id", "so_luong", "don_gia", "giam_gia"],
    "ton_kho": ["san_pham_id", "so_luong_ton", "muc_ton_toi_thieu", "ngay_cap_nhat"],
    "khach_hang": ["id", "ho_ten", "email", "so_dien_thoai", "gioi_tinh", "ngay_sinh", "ngay_dang_ky", "loai_khach"],
    "dia_chi": ["id", "khach_hang_id", "tinh_thanh", "quan_huyen", "dia_chi_chi_tiet", "mac_dinh"],
    "nhan_vien": ["id", "ho_ten", "chuc_vu", "ngay_vao_lam", "dang_lam_viec"],
    "thanh_toan": ["id", "don_hang_id", "phuong_thuc", "so_tien", "ngay_thanh_toan", "trang_thai"],
    "nha_cung_cap": ["id", "ten", "so_dien_thoai", "email", "tinh_thanh"],
    "phieu_nhap": ["id", "nha_cung_cap_id", "nhan_vien_id", "ngay_nhap", "tong_tien"],
    "chi_tiet_phieu_nhap": ["id", "phieu_nhap_id", "san_pham_id", "so_luong", "gia_nhap"],
    "san_pham_nha_cung_cap": ["san_pham_id", "nha_cung_cap_id", "gia_nhap_gan_nhat"],
}

# Danh sách cột dữ liệu nhạy cảm kèm trọng số rủi ro (dành cho AI 3 Security Guard - A3-2)
SENSITIVE_COLUMNS = {
    ("san_pham", "gia_von"): 70.0,
    ("app_users", "password_hash"): 80.0,
    ("khach_hang", "email"): 20.0,
    ("khach_hang", "so_dien_thoai"): 20.0,
    ("dia_chi", "dia_chi_chi_tiet"): 20.0,
    ("khach_hang", "ngay_sinh"): 10.0,
}

# 12 danh mục linh kiện chuẩn trong DB
CATEGORIES = [
    "CPU", "Mainboard", "RAM", "VGA", "SSD", "HDD", 
    "Nguồn", "Vỏ case", "Tản nhiệt", "Màn hình", "Bàn phím", "Chuột"
]

# Ánh xạ từ các từ đồng nghĩa / không dấu / tiếng Anh sang Danh mục chuẩn có dấu (A1-2)
CATEGORY_ALIASES = {
    # CPU
    "cpu": "CPU",
    "vi xu ly": "CPU",
    "bo vi xu ly": "CPU",
    "bộ vi xử lý": "CPU",
    "chip": "CPU",
    "processor": "CPU",
    # Mainboard
    "mainboard": "Mainboard",
    "bo mach chu": "Mainboard",
    "bộ mạch chủ": "Mainboard",
    "bo mạch chủ": "Mainboard",
    "main": "Mainboard",
    "motherboard": "Mainboard",
    # RAM
    "ram": "RAM",
    "bo nho trong": "RAM",
    "bộ nhớ trong": "RAM",
    "memory": "RAM",
    # VGA
    "vga": "VGA",
    "card do hoa": "VGA",
    "card đồ họa": "VGA",
    "card man hinh": "VGA",
    "card màn hình": "VGA",
    "gpu": "VGA",
    # SSD
    "ssd": "SSD",
    "o cung ssd": "SSD",
    "ổ cứng ssd": "SSD",
    # HDD
    "hdd": "HDD",
    "o cung hdd": "HDD",
    "ổ cứng hdd": "HDD",
    "o cung co": "HDD",
    # Nguồn
    "nguon": "Nguồn",
    "nguồn": "Nguồn",
    "nguon may tinh": "Nguồn",
    "nguồn máy tính": "Nguồn",
    "psu": "Nguồn",
    "power supply": "Nguồn",
    # Vỏ case
    "vo case": "Vỏ case",
    "vỏ case": "Vỏ case",
    "case": "Vỏ case",
    "thung may": "Vỏ case",
    "thùng máy": "Vỏ case",
    # Tản nhiệt
    "tan nhiet": "Tản nhiệt",
    "tản nhiệt": "Tản nhiệt",
    "tan nhiet khi": "Tản nhiệt",
    "tản nhiệt khí": "Tản nhiệt",
    "tan nhiet nuoc": "Tản nhiệt",
    "tản nhiệt nước": "Tản nhiệt",
    "cooler": "Tản nhiệt",
    # Màn hình
    "man hinh": "Màn hình",
    "màn hình": "Màn hình",
    "man hinh may tinh": "Màn hình",
    "màn hình máy tính": "Màn hình",
    "monitor": "Màn hình",
    "display": "Màn hình",
    # Bàn phím
    "ban phim": "Bàn phím",
    "bàn phím": "Bàn phím",
    "ban phim co": "Bàn phím",
    "bàn phím cơ": "Bàn phím",
    "keyboard": "Bàn phím",
    # Chuột
    "chuot": "Chuột",
    "chuột": "Chuột",
    "chuot may tinh": "Chuột",
    "chuột máy tính": "Chuột",
    "mouse": "Chuột",
}

# 30 thương hiệu chuẩn trong DB
BRANDS = [
    "Intel", "AMD", "ASUS", "MSI", "Gigabyte", "ASRock", "Kingston",
    "Corsair", "G.Skill", "ADATA", "Crucial", "Samsung", "Western Digital",
    "Lexar", "Seagate", "Toshiba", "Cooler Master", "Seasonic", "DeepCool",
    "NZXT", "Lian Li", "Thermalright", "Dell", "LG", "AOC", "Logitech",
    "Razer", "AKKO", "DareU", "SteelSeries"
]

# 6 trạng thái đơn hàng và các biến thể tiếng Việt
# Đã loại bỏ "mới"/"moi" trần để tránh gây nhiễu cho "sản phẩm mới" (A1-6)
ORDER_STATUSES = {
    "đơn mới": "moi",
    "don moi": "moi",
    "đơn hàng mới": "moi",
    "don hang moi": "moi",
    "đang xử lý": "dang_xu_ly",
    "dang xu ly": "dang_xu_ly",
    "chờ xử lý": "dang_xu_ly",
    "cho xu ly": "dang_xu_ly",
    "đang giao": "dang_giao",
    "dang giao": "dang_giao",
    "đang vận chuyển": "dang_giao",
    "dang van chuyen": "dang_giao",
    "hoàn thành": "hoan_thanh",
    "hoan thanh": "hoan_thanh",
    "thành công": "hoan_thanh",
    "thanh cong": "hoan_thanh",
    "đã giao": "hoan_thanh",
    "da giao": "hoan_thanh",
    "đã hủy": "da_huy",
    "da huy": "da_huy",
    "bị hủy": "da_huy",
    "bi huy": "da_huy",
    "hủy": "da_huy",
    "huy": "da_huy",
    "trả hàng": "tra_hang",
    "tra hang": "tra_hang",
    "hoàn trả": "tra_hang",
    "hoan tra": "tra_hang",
    "đổi trả": "tra_hang",
    "doi tra": "tra_hang",
}

# 4 kênh bán hàng
# Đã loại bỏ bí danh "sàn"/"san" và "web" trần để tránh khớp nhầm "sản phẩm" (A1-6)
CHANNELS = {
    "cửa hàng": "cua_hang",
    "cua hang": "cua_hang",
    "tại quầy": "cua_hang",
    "tai quay": "cua_hang",
    "trực tiếp": "cua_hang",
    "truc tiep": "cua_hang",
    "website": "website",
    "trang web": "website",
    "online": "website",
    "shopee": "shopee",
    "shoppi": "shopee",
    "shope": "shopee",
    "shoppee": "shopee",
    "facebook": "facebook",
    "fb": "facebook",
    "fanpage": "facebook",
}

# 5 phương thức thanh toán
# Đã loại bỏ "thẻ"/"the" trần để tránh hiểu nhầm câu chữ chung (A1-6)
PAYMENT_METHODS = {
    "tiền mặt": "tien_mat",
    "tien mat": "tien_mat",
    "chuyển khoản": "chuyen_khoan",
    "chuyen khoan": "chuyen_khoan",
    "ngân hàng": "chuyen_khoan",
    "ngan hang": "chuyen_khoan",
    "quẹt thẻ": "the",
    "quet the": "the",
    "thẻ tín dụng": "the",
    "the tin dung": "the",
    "thẻ atm": "the",
    "the atm": "the",
    "thẻ visa": "the",
    "the visa": "the",
    "pos": "the",
    "visa": "the",
    "mastercard": "the",
    "ví điện tử": "vi_dien_tu",
    "vi dien tu": "vi_dien_tu",
    "momo": "vi_dien_tu",
    "zalopay": "vi_dien_tu",
    "vnpay": "vi_dien_tu",
    "trả góp": "tra_gop",
    "tra gop": "tra_gop",
}
