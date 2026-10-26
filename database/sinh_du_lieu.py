#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sinh dữ liệu mẫu cho CSDL LinhKien_DB (xem schema.sql).

Cài thư viện:   pip install psycopg2-binary
Chạy:           python sinh_du_lieu.py --password MAT_KHAU_POSTGRES
Tùy chọn:       --host localhost --port 5432 --dbname LinhKien_DB --user postgres
                --so-khach 1500 --so-don 8000 --so-phieu-nhap 300

Lưu ý: script XÓA sạch dữ liệu cũ trong các bảng trước khi nạp (chạy lại được nhiều lần).
Dữ liệu cố định theo seed nên cả nhóm chạy ra kết quả giống nhau.
"""
import argparse
import bisect
import random
import unicodedata
from datetime import date, datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

SEED = 42
NGAY_BAT_DAU_DON = date(2025, 1, 1)
NGAY_HOM_NAY = date(2026, 10, 5)

# ------------------------------------------------------------
# DỮ LIỆU GỐC
# ------------------------------------------------------------
DANH_MUC = [
    ("CPU", "Bộ vi xử lý"), ("Mainboard", "Bo mạch chủ"), ("RAM", "Bộ nhớ trong"),
    ("VGA", "Card đồ họa"), ("SSD", "Ổ cứng thể rắn"), ("HDD", "Ổ cứng cơ"),
    ("Nguồn", "Bộ nguồn máy tính"), ("Vỏ case", "Thùng máy"),
    ("Tản nhiệt", "Tản nhiệt CPU khí và nước"), ("Màn hình", "Màn hình máy tính"),
    ("Bàn phím", "Bàn phím"), ("Chuột", "Chuột máy tính"),
]
MA_DM = {"CPU": "CPU", "Mainboard": "MB", "RAM": "RAM", "VGA": "VGA", "SSD": "SSD",
         "HDD": "HDD", "Nguồn": "PSU", "Vỏ case": "CASE", "Tản nhiệt": "COOL",
         "Màn hình": "MON", "Bàn phím": "KB", "Chuột": "MOUSE"}
BAO_HANH = {"CPU": 36, "Mainboard": 36, "RAM": 36, "VGA": 36, "SSD": 36, "HDD": 24,
            "Nguồn": 60, "Vỏ case": 12, "Tản nhiệt": 24, "Màn hình": 36,
            "Bàn phím": 12, "Chuột": 12}

THUONG_HIEU = [
    ("Intel", "Mỹ"), ("AMD", "Mỹ"), ("ASUS", "Đài Loan"), ("MSI", "Đài Loan"),
    ("Gigabyte", "Đài Loan"), ("ASRock", "Đài Loan"), ("Kingston", "Mỹ"),
    ("Corsair", "Mỹ"), ("G.Skill", "Đài Loan"), ("ADATA", "Đài Loan"),
    ("Crucial", "Mỹ"), ("Samsung", "Hàn Quốc"), ("Western Digital", "Mỹ"),
    ("Lexar", "Trung Quốc"), ("Seagate", "Mỹ"), ("Toshiba", "Nhật Bản"),
    ("Cooler Master", "Đài Loan"), ("Seasonic", "Đài Loan"), ("DeepCool", "Trung Quốc"),
    ("NZXT", "Mỹ"), ("Lian Li", "Đài Loan"), ("Thermalright", "Trung Quốc"),
    ("Dell", "Mỹ"), ("LG", "Hàn Quốc"), ("AOC", "Đài Loan"), ("Logitech", "Thụy Sĩ"),
    ("Razer", "Mỹ"), ("AKKO", "Trung Quốc"), ("DareU", "Trung Quốc"),
    ("SteelSeries", "Đan Mạch"),
]

# (danh mục, thương hiệu, tên sản phẩm, giá niêm yết VNĐ)
SAN_PHAM = [
    ("CPU", "Intel", "Intel Core i3-12100F", 2400000),
    ("CPU", "Intel", "Intel Core i5-12400F", 3500000),
    ("CPU", "Intel", "Intel Core i5-13400F", 5200000),
    ("CPU", "Intel", "Intel Core i5-14400F", 5900000),
    ("CPU", "Intel", "Intel Core i7-13700K", 10500000),
    ("CPU", "Intel", "Intel Core i7-14700K", 11900000),
    ("CPU", "Intel", "Intel Core i9-14900K", 15500000),
    ("CPU", "AMD", "AMD Ryzen 5 5600", 2900000),
    ("CPU", "AMD", "AMD Ryzen 5 7600", 5600000),
    ("CPU", "AMD", "AMD Ryzen 7 5700X", 4300000),
    ("CPU", "AMD", "AMD Ryzen 7 7800X3D", 11500000),
    ("CPU", "AMD", "AMD Ryzen 9 7950X", 14800000),
    ("Mainboard", "ASUS", "ASUS PRIME B660M-K D4", 2300000),
    ("Mainboard", "ASUS", "ASUS TUF GAMING B760M-PLUS", 4300000),
    ("Mainboard", "ASUS", "ASUS ROG STRIX Z790-E GAMING", 11500000),
    ("Mainboard", "MSI", "MSI PRO B760M-P", 3000000),
    ("Mainboard", "MSI", "MSI MAG B650 TOMAHAWK WIFI", 5800000),
    ("Mainboard", "Gigabyte", "Gigabyte B550M DS3H", 2100000),
    ("Mainboard", "Gigabyte", "Gigabyte Z790 AORUS ELITE", 6900000),
    ("Mainboard", "ASRock", "ASRock B450M-HDV R4.0", 1600000),
    ("Mainboard", "ASRock", "ASRock B650M PRO RS", 3900000),
    ("RAM", "Kingston", "Kingston Fury Beast 8GB DDR4 3200", 650000),
    ("RAM", "Kingston", "Kingston Fury Beast 16GB DDR4 3200", 1150000),
    ("RAM", "Kingston", "Kingston Fury Beast 32GB DDR4 3200", 1900000),
    ("RAM", "Corsair", "Corsair Vengeance 16GB DDR5 5600", 1800000),
    ("RAM", "Corsair", "Corsair Vengeance 32GB (2x16) DDR5 6000", 3500000),
    ("RAM", "G.Skill", "G.Skill Trident Z5 32GB (2x16) DDR5 6000", 3900000),
    ("RAM", "ADATA", "ADATA XPG Lancer 16GB DDR4 3200", 1050000),
    ("RAM", "Crucial", "Crucial 16GB DDR5 4800", 1500000),
    ("VGA", "ASUS", "ASUS DUAL GeForce RTX 3050 6GB", 4200000),
    ("VGA", "MSI", "MSI GeForce RTX 4060 VENTUS 2X 8GB", 8200000),
    ("VGA", "Gigabyte", "Gigabyte GeForce RTX 4060 Ti EAGLE 8GB", 11000000),
    ("VGA", "ASUS", "ASUS TUF GeForce RTX 4070 SUPER 12GB", 18500000),
    ("VGA", "MSI", "MSI GeForce RTX 4070 Ti SUPER 16GB", 24500000),
    ("VGA", "Gigabyte", "Gigabyte GeForce RTX 4080 SUPER 16GB", 30500000),
    ("VGA", "ASUS", "ASUS TUF GeForce RTX 4090 24GB", 52000000),
    ("VGA", "MSI", "MSI Radeon RX 7600 MECH 8GB", 6500000),
    ("VGA", "Gigabyte", "Gigabyte Radeon RX 7800 XT GAMING OC 16GB", 12500000),
    ("VGA", "ASRock", "ASRock Radeon RX 6600 Challenger 8GB", 5100000),
    ("SSD", "Samsung", "Samsung 980 NVMe 500GB", 1200000),
    ("SSD", "Samsung", "Samsung 990 PRO NVMe 1TB", 3200000),
    ("SSD", "Kingston", "Kingston NV2 NVMe 500GB", 950000),
    ("SSD", "Kingston", "Kingston NV2 NVMe 1TB", 1600000),
    ("SSD", "Western Digital", "WD Blue SN580 NVMe 1TB", 1700000),
    ("SSD", "Crucial", "Crucial P3 Plus NVMe 2TB", 3400000),
    ("SSD", "Lexar", "Lexar NM620 NVMe 512GB", 1000000),
    ("HDD", "Western Digital", "WD Blue 1TB 7200rpm", 1150000),
    ("HDD", "Western Digital", "WD Blue 2TB 5400rpm", 1650000),
    ("HDD", "Seagate", "Seagate Barracuda 2TB", 1600000),
    ("HDD", "Seagate", "Seagate Barracuda 4TB", 2500000),
    ("HDD", "Toshiba", "Toshiba P300 1TB", 1100000),
    ("Nguồn", "Corsair", "Corsair CV650 650W 80 Plus Bronze", 1200000),
    ("Nguồn", "Corsair", "Corsair RM750e 750W 80 Plus Gold", 2600000),
    ("Nguồn", "Cooler Master", "Cooler Master MWE 550W Bronze", 950000),
    ("Nguồn", "Cooler Master", "Cooler Master MWE Gold 750W", 2000000),
    ("Nguồn", "MSI", "MSI MAG A650BN 650W", 1100000),
    ("Nguồn", "Seasonic", "Seasonic Focus GX-850 850W Gold", 3600000),
    ("Nguồn", "DeepCool", "DeepCool PK650D 650W", 1050000),
    ("Vỏ case", "NZXT", "NZXT H510", 1800000),
    ("Vỏ case", "Corsair", "Corsair 4000D Airflow", 2300000),
    ("Vỏ case", "Cooler Master", "Cooler Master MasterBox Q300L", 1000000),
    ("Vỏ case", "Lian Li", "Lian Li LANCOOL 216", 2700000),
    ("Vỏ case", "DeepCool", "DeepCool CC560", 1100000),
    ("Vỏ case", "MSI", "MSI MAG FORGE 100R", 1200000),
    ("Tản nhiệt", "DeepCool", "DeepCool AK400", 750000),
    ("Tản nhiệt", "DeepCool", "DeepCool AK620", 1450000),
    ("Tản nhiệt", "Cooler Master", "Cooler Master Hyper 212 Black", 700000),
    ("Tản nhiệt", "Corsair", "Corsair iCUE H100i ELITE 240mm", 3900000),
    ("Tản nhiệt", "NZXT", "NZXT Kraken 240", 3500000),
    ("Tản nhiệt", "Thermalright", "Thermalright Peerless Assassin 120 SE", 850000),
    ("Màn hình", "Dell", "Dell P2422H 24 inch IPS", 4500000),
    ("Màn hình", "LG", "LG 24MR400 24 inch IPS 100Hz", 2600000),
    ("Màn hình", "Samsung", "Samsung Odyssey G5 27 inch 2K 165Hz", 6900000),
    ("Màn hình", "ASUS", "ASUS TUF VG27AQ 27 inch 2K 165Hz", 7200000),
    ("Màn hình", "MSI", "MSI G2412 24 inch 170Hz", 3300000),
    ("Màn hình", "Gigabyte", "Gigabyte M27Q 27 inch 2K 170Hz", 7500000),
    ("Màn hình", "AOC", "AOC 24G2 24 inch 144Hz", 3600000),
    ("Bàn phím", "Logitech", "Logitech K120", 220000),
    ("Bàn phím", "Logitech", "Logitech G213 Prodigy", 1000000),
    ("Bàn phím", "Corsair", "Corsair K70 RGB", 3200000),
    ("Bàn phím", "Razer", "Razer BlackWidow V3", 3500000),
    ("Bàn phím", "AKKO", "AKKO 3068B Plus", 1700000),
    ("Bàn phím", "DareU", "DareU EK87", 600000),
    ("Chuột", "Logitech", "Logitech G102", 400000),
    ("Chuột", "Logitech", "Logitech G502 Hero", 1000000),
    ("Chuột", "Razer", "Razer DeathAdder V2", 1300000),
    ("Chuột", "Corsair", "Corsair Harpoon RGB", 600000),
    ("Chuột", "SteelSeries", "SteelSeries Rival 3", 600000),
]

# Mua sản phẩm thuộc nhóm bên trái thì hay mua kèm nhóm bên phải
MUA_KEM = {
    "CPU": ["Mainboard", "RAM"], "Mainboard": ["RAM"], "VGA": ["Nguồn"],
    "Vỏ case": ["Tản nhiệt"], "SSD": ["HDD"], "Màn hình": ["Bàn phím", "Chuột"],
}

NHA_CUNG_CAP = [
    ("Công ty TNHH Phân phối Tin học Phong Vũ", "0283822xxxx", "dl@phongvu-pp.vn", "TP. Hồ Chí Minh"),
    ("Công ty CP Thế Giới Linh Kiện", "0243987xxxx", "sale@tglk.vn", "Hà Nội"),
    ("Công ty TNHH Viễn Sơn", "0283925xxxx", "info@vienson.vn", "TP. Hồ Chí Minh"),
    ("Công ty CP Thương mại An Phát", "0243568xxxx", "order@anphat.vn", "Hà Nội"),
    ("Công ty TNHH Đại Dương Computer", "0236365xxxx", "kd@daiduong.vn", "Đà Nẵng"),
    ("Công ty TNHH Digiworld Phân phối", "0283930xxxx", "b2b@digiworld.vn", "TP. Hồ Chí Minh"),
    ("Công ty CP Công nghệ Hoàng Hà", "0243777xxxx", "cs@hoangha.vn", "Hà Nội"),
    ("Công ty TNHH Siêu Tốc Linh Kiện", "0292381xxxx", "sieutoc@lk.vn", "Cần Thơ"),
]

NHAN_VIEN = [
    ("Nguyễn Văn Hải", "Quản lý"), ("Trần Thị Mai", "Thu ngân"),
    ("Lê Quốc Khánh", "Nhân viên bán hàng"), ("Phạm Minh Tuấn", "Nhân viên bán hàng"),
    ("Hoàng Thị Lan", "Nhân viên bán hàng"), ("Võ Đức Thịnh", "Nhân viên bán hàng"),
    ("Đặng Ngọc Anh", "Thu ngân"), ("Bùi Văn Long", "Nhân viên kho"),
    ("Đỗ Hữu Phúc", "Nhân viên kho"), ("Huỳnh Gia Bảo", "Nhân viên bán hàng"),
]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng",
      "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
HO_W = [30, 18, 10, 8, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1]
DEM_NAM = ["Văn", "Hữu", "Minh", "Quốc", "Đức", "Thành", "Anh", "Gia", "Hoàng", "Ngọc"]
DEM_NU = ["Thị", "Ngọc", "Thùy", "Thanh", "Khánh", "Bảo", "Mai", "Hồng", "Phương"]
TEN_NAM = ["Hùng", "Dũng", "Nam", "Phúc", "Khoa", "Long", "Tuấn", "Huy", "Bình", "Sơn",
           "Thịnh", "Đạt", "Hiếu", "Trung", "Kiên", "Khang", "Nhân", "Quân"]
TEN_NU = ["Lan", "Hoa", "Linh", "Trang", "Hương", "Mai", "Ngân", "Thảo", "Vy", "Chi",
          "Nhung", "Yến", "Phương", "Quyên", "My", "Uyên", "Hà", "Ngọc"]
TEN_CONG_TY = ["Minh Phát", "Hoàng Gia", "Đại Nam", "Việt Tiến", "Thành Công", "An Khang",
               "Tân Phú", "Sao Mai", "Bình Minh", "Phú Cường", "Gia Huy", "Thiên Long"]

TINH_THANH = {
    "TP. Hồ Chí Minh": (40, ["Quận 1", "Quận 3", "Quận 7", "Bình Thạnh", "Gò Vấp", "Thủ Đức", "Tân Bình"]),
    "Hà Nội": (22, ["Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Thanh Xuân", "Nam Từ Liêm"]),
    "Đà Nẵng": (8, ["Hải Châu", "Thanh Khê", "Sơn Trà"]),
    "Bà Rịa - Vũng Tàu": (7, ["TP. Vũng Tàu", "TP. Bà Rịa", "Long Điền"]),
    "Đồng Nai": (6, ["Biên Hòa", "Long Thành", "Nhơn Trạch"]),
    "Bình Dương": (6, ["Thủ Dầu Một", "Dĩ An", "Thuận An"]),
    "Cần Thơ": (4, ["Ninh Kiều", "Cái Răng", "Bình Thủy"]),
    "Hải Phòng": (3, ["Hồng Bàng", "Lê Chân", "Ngô Quyền"]),
    "Khánh Hòa": (2, ["Nha Trang", "Cam Ranh"]),
    "Lâm Đồng": (2, ["Đà Lạt", "Bảo Lộc"]),
}
DUONG = ["Nguyễn Trãi", "Lê Lợi", "Trần Hưng Đạo", "Hai Bà Trưng", "Võ Văn Tần",
         "Điện Biên Phủ", "Phạm Văn Đồng", "Lý Thường Kiệt", "Nguyễn Huệ", "Cách Mạng Tháng 8"]

# Hệ số mùa vụ theo tháng (Tết, khai trường, cuối năm bán nhiều hơn)
HE_SO_THANG = [1.3, 1.4, 1.0, 0.9, 0.9, 1.0, 0.9, 1.2, 1.3, 1.0, 1.4, 1.5]

KENH_BAN = (["cua_hang", "website", "shopee", "facebook"], [45, 25, 22, 8])
PT_THANH_TOAN = {
    "cua_hang": ["tien_mat", "the", "chuyen_khoan"],
    "website": ["chuyen_khoan", "the", "vi_dien_tu", "tra_gop"],
    "shopee": ["vi_dien_tu", "the"],
    "facebook": ["chuyen_khoan", "tien_mat"],
}


# ------------------------------------------------------------
# HÀM TIỆN ÍCH
# ------------------------------------------------------------
def bo_dau(s):
    s = s.replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def ngay_ngau_nhien(d1, d2):
    return d1 + timedelta(days=random.randint(0, (d2 - d1).days))


def lam_tron(x, buoc=1000):
    return int(round(x / buoc) * buoc)


def sinh_so_dien_thoai():
    dau = random.choice(["090", "091", "093", "097", "098", "086", "038", "070", "077", "079"])
    return dau + "".join(random.choice("0123456789") for _ in range(7))


# ------------------------------------------------------------
# SINH DỮ LIỆU TỪNG BẢNG (trả về danh sách tuple, id đặt sẵn từ 1)
# ------------------------------------------------------------
def sinh_danh_muc_thuong_hieu():
    dm = [(i + 1, ten, mo_ta, None) for i, (ten, mo_ta) in enumerate(DANH_MUC)]
    th = [(i + 1, ten, qg) for i, (ten, qg) in enumerate(THUONG_HIEU)]
    return dm, th


def sinh_san_pham(id_dm, id_th):
    rows, dem = [], {}
    for dm, th, ten, gia in SAN_PHAM:
        dem[dm] = dem.get(dm, 0) + 1
        sku = f"{MA_DM[dm]}-{dem[dm]:03d}"
        gia_von = lam_tron(gia * random.uniform(0.82, 0.92))
        ra_mat = ngay_ngau_nhien(date(2021, 1, 1), date(2024, 12, 31))
        dang_kd = random.random() < 0.92
        rows.append((len(rows) + 1, sku, ten, id_dm[dm], id_th[th], gia, gia_von,
                     BAO_HANH[dm], ra_mat, dang_kd))
    return rows


def sinh_san_pham_ncc(n_sp, n_ncc):
    rows = []
    for sp in range(1, n_sp + 1):
        for ncc in random.sample(range(1, n_ncc + 1), random.randint(1, 3)):
            rows.append((sp, ncc, None))  # gia_nhap_gan_nhat cập nhật sau
    return rows


def sinh_khach_hang(n):
    rows = []
    for i in range(1, n + 1):
        r = random.random()
        loai = "doanh_nghiep" if r < 0.03 else ("si" if r < 0.10 else "le")
        if loai == "doanh_nghiep":
            ten, gioi_tinh, ngay_sinh = "Công ty TNHH " + random.choice(TEN_CONG_TY), None, None
        else:
            nam = random.random() < 0.72  # khách mua linh kiện chủ yếu là nam
            ho = random.choices(HO, HO_W)[0]
            dem = random.choice(DEM_NAM if nam else DEM_NU)
            ten_goi = random.choice(TEN_NAM if nam else TEN_NU)
            ten = f"{ho} {dem} {ten_goi}"
            gioi_tinh = "nam" if nam else "nu"
            ngay_sinh = ngay_ngau_nhien(date(1978, 1, 1), date(2007, 12, 31))
        email = None
        if random.random() > 0.05:
            email = f"{bo_dau(ten).replace(' ', '')[:18]}{i}@{random.choice(['gmail.com', 'gmail.com', 'yahoo.com', 'outlook.com'])}"
        dang_ky = ngay_ngau_nhien(date(2024, 6, 1), date(2026, 9, 30))
        rows.append((i, ten, email, sinh_so_dien_thoai(), gioi_tinh, ngay_sinh, dang_ky, loai))
    return rows


def sinh_dia_chi(khach_hang):
    rows = []
    tinh = list(TINH_THANH)
    w = [TINH_THANH[t][0] for t in tinh]
    for kh in khach_hang:
        for k in range(random.choices([1, 2], [80, 20])[0]):
            t = random.choices(tinh, w)[0]
            qh = random.choice(TINH_THANH[t][1])
            chi_tiet = f"{random.randint(1, 300)} {random.choice(DUONG)}"
            rows.append((len(rows) + 1, kh[0], t, qh, chi_tiet, k == 0))
    return rows


def sinh_ngay_don(n):
    ngay = [NGAY_BAT_DAU_DON + timedelta(days=i) for i in range((NGAY_HOM_NAY - NGAY_BAT_DAU_DON).days + 1)]
    w = [HE_SO_THANG[d.month - 1] * (1.25 if d.weekday() >= 5 else 1.0) for d in ngay]
    ds = []
    for d in random.choices(ngay, w, k=n):
        ds.append(datetime(d.year, d.month, d.day, random.randint(8, 21), random.randint(0, 59)))
    ds.sort()
    return ds


def sinh_don_hang(n_don, khach_hang, dia_chi, san_pham, nhan_vien):
    # --- chuẩn bị ---
    kh_sorted = sorted(khach_hang, key=lambda r: r[6])      # theo ngày đăng ký
    ngay_dk = [r[6] for r in kh_sorted]
    trong_so_kh = [min(random.paretovariate(1.4), 30) for _ in kh_sorted]  # vài khách mua rất nhiều
    dc_cua_kh = {}
    for dc in dia_chi:
        dc_cua_kh.setdefault(dc[1], []).append(dc[0])

    sp_theo_dm = {}
    for sp in san_pham:
        sp_theo_dm.setdefault(sp[3], []).append(sp)
    # id danh mục theo tên (id = vị trí + 1)
    id_dm = {ten: i + 1 for i, (ten, _) in enumerate(DANH_MUC)}
    trong_so_sp = [(1.0 / ((sp[5] / 1e6) ** 0.6)) * (1.0 if sp[9] else 0.3) for sp in san_pham]
    nv_ban = [i + 1 for i, (_, cv) in enumerate(nhan_vien) if cv in ("Nhân viên bán hàng", "Thu ngân")]

    don_hang, chi_tiet, thanh_toan = [], [], []
    for stt, ngay_dat in enumerate(sinh_ngay_don(n_don), start=1):
        k = bisect.bisect_right(ngay_dk, ngay_dat.date())
        if k == 0:
            k = 1
        kh = kh_sorted[random.choices(range(k), trong_so_kh[:k])[0]]
        kenh = random.choices(*KENH_BAN)[0]
        nv = random.choice(nv_ban) if kenh == "cua_hang" else None
        dc = None
        if kenh != "cua_hang" and dc_cua_kh.get(kh[0]):
            dc = dc_cua_kh[kh[0]][0]

        # --- chọn sản phẩm: 1 sản phẩm chính + mua kèm ---
        chinh = random.choices(san_pham, trong_so_sp)[0]
        chon = {chinh[0]: chinh}
        ten_dm_chinh = DANH_MUC[chinh[3] - 1][0]
        for dm_kem in MUA_KEM.get(ten_dm_chinh, []):
            if random.random() < 0.45:
                sp_kem = random.choice(sp_theo_dm[id_dm[dm_kem]])
                chon[sp_kem[0]] = sp_kem
        if random.random() < 0.15:
            them = random.choices(san_pham, trong_so_sp)[0]
            chon[them[0]] = them

        tong = 0
        dong = []
        for sp in chon.values():
            ten_dm = DANH_MUC[sp[3] - 1][0]
            if ten_dm in ("RAM", "HDD", "Chuột", "Bàn phím") and random.random() < 0.25:
                sl = random.randint(2, 4)
            elif ten_dm == "Màn hình" and random.random() < 0.15:
                sl = 2
            else:
                sl = 1
            don_gia = lam_tron(sp[5] * random.uniform(0.95, 1.02))
            giam = lam_tron(don_gia * sl * random.uniform(0.02, 0.06)) if random.random() < 0.3 else 0
            tong += don_gia * sl - giam
            dong.append((sp[0], sl, don_gia, giam))

        # --- trạng thái ---
        so_ngay = (NGAY_HOM_NAY - ngay_dat.date()).days
        if so_ngay <= 5:
            trang_thai = random.choice(["moi", "dang_xu_ly", "dang_giao", "hoan_thanh"])
        else:
            trang_thai = random.choices(["hoan_thanh", "da_huy", "tra_hang"], [89, 7, 4])[0]
        ngay_giao = None
        if trang_thai in ("hoan_thanh", "tra_hang"):
            if kenh == "cua_hang":
                ngay_giao = ngay_dat + timedelta(minutes=random.randint(5, 40))
            else:
                ngay_giao = ngay_dat + timedelta(days=random.randint(1, 5), hours=random.randint(0, 6))

        don_hang.append((stt, kh[0], nv, dc, ngay_dat, ngay_giao, trang_thai, kenh, tong))
        for sp_id, sl, dg, gg in dong:
            chi_tiet.append((len(chi_tiet) + 1, stt, sp_id, sl, dg, gg))

        # --- thanh toán ---
        pt = random.choice(PT_THANH_TOAN[kenh])
        if trang_thai in ("hoan_thanh", "tra_hang"):
            if pt == "tra_gop" and tong > 5_000_000:
                coc = lam_tron(tong * 0.3)
                thanh_toan.append((len(thanh_toan) + 1, stt, pt, coc, ngay_dat, "da_thanh_toan"))
                thanh_toan.append((len(thanh_toan) + 1, stt, pt, tong - coc,
                                   ngay_dat + timedelta(days=30), "da_thanh_toan"))
            else:
                thanh_toan.append((len(thanh_toan) + 1, stt, pt, tong,
                                   ngay_dat + timedelta(minutes=random.randint(1, 30)), "da_thanh_toan"))
            if trang_thai == "tra_hang":
                thanh_toan.append((len(thanh_toan) + 1, stt, pt, tong,
                                   ngay_giao + timedelta(days=random.randint(2, 7)), "hoan_tien"))
        elif trang_thai == "da_huy":
            if pt != "tien_mat" and random.random() < 0.5:
                thanh_toan.append((len(thanh_toan) + 1, stt, pt, tong, None, "cho_thanh_toan"))
        else:
            thanh_toan.append((len(thanh_toan) + 1, stt, pt, tong, None, "cho_thanh_toan"))
    return don_hang, chi_tiet, thanh_toan


def sinh_phieu_nhap(n_phieu, san_pham, spncc, nhan_vien):
    nv_kho = [i + 1 for i, (_, cv) in enumerate(nhan_vien) if cv == "Nhân viên kho"]
    sp_cua_ncc = {}
    for sp_id, ncc_id, _ in spncc:
        sp_cua_ncc.setdefault(ncc_id, []).append(sp_id)
    ncc_co_hang = [n for n, ds in sp_cua_ncc.items() if ds]
    gia_von = {sp[0]: sp[6] for sp in san_pham}
    gia_niem_yet = {sp[0]: sp[5] for sp in san_pham}

    phieu, chi_tiet, gia_gan_nhat = [], [], {}
    for i in range(1, n_phieu + 1):
        ncc = random.choice(ncc_co_hang)
        ngay = ngay_ngau_nhien(date(2024, 12, 1), date(2026, 10, 1))
        ds = sp_cua_ncc[ncc]
        tong = 0
        for sp_id in random.sample(ds, min(len(ds), random.randint(1, 6))):
            gia = gia_niem_yet[sp_id]
            sl = random.randint(1, 4) if gia > 10e6 else (random.randint(2, 10) if gia > 4e6 else random.randint(5, 40))
            gia_nhap = lam_tron(gia_von[sp_id] * random.uniform(0.97, 1.03))
            tong += sl * gia_nhap
            chi_tiet.append((len(chi_tiet) + 1, i, sp_id, sl, gia_nhap))
            gia_gan_nhat[(sp_id, ncc)] = gia_nhap
        phieu.append((i, ncc, random.choice(nv_kho), ngay, tong))
    return phieu, chi_tiet, gia_gan_nhat


def sinh_ton_kho(san_pham):
    rows = []
    for sp in san_pham:
        gia = sp[5]
        if random.random() < 0.15:
            ton = random.randint(0, 8)          # cố ý để một số sản phẩm sắp hết hàng
        elif gia > 15e6:
            ton = random.randint(2, 10)
        else:
            ton = random.randint(8, 60)
        ngay_cn = datetime(2026, 9, 25) + timedelta(days=random.randint(0, 10), hours=random.randint(8, 20))
        rows.append((sp[0], ton, 5 if gia > 15e6 else 10, ngay_cn))
    return rows


# ------------------------------------------------------------
# NẠP VÀO POSTGRESQL
# ------------------------------------------------------------
def nap(cur, bang, cot, rows, page_size=2000):
    if not rows:
        return
    sql = f"INSERT INTO {bang} ({', '.join(cot)}) VALUES %s"
    execute_values(cur, sql, rows, page_size=page_size)
    print(f"  {bang:<26} {len(rows):>7} dòng")


def main():
    ap = argparse.ArgumentParser(description="Sinh dữ liệu mẫu cho CSDL LinhKien_DB")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--dbname", default="LinhKien_DB")
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--password", default="")
    ap.add_argument("--so-khach", type=int, default=1500)
    ap.add_argument("--so-don", type=int, default=8000)
    ap.add_argument("--so-phieu-nhap", type=int, default=300)
    a = ap.parse_args()

    random.seed(SEED)

    dm, th = sinh_danh_muc_thuong_hieu()
    id_dm = {r[1]: r[0] for r in dm}
    id_th = {r[1]: r[0] for r in th}
    sp = sinh_san_pham(id_dm, id_th)
    # Số máy bàn mẫu "0283822xxxx" -> thay xxxx bằng 8888 để thỏa CHECK chk_nha_cung_cap_sdt (^0[0-9]{9,10}$)
    ncc = [(i + 1, t, sdt.replace("xxxx", "8888"), e, tinh) for i, (t, sdt, e, tinh) in enumerate(NHA_CUNG_CAP)]
    nv = [(i + 1, ten, cv, ngay_ngau_nhien(date(2021, 1, 1), date(2025, 6, 30)), i != 6)
          for i, (ten, cv) in enumerate(NHAN_VIEN)]
    spncc = sinh_san_pham_ncc(len(sp), len(ncc))
    kh = sinh_khach_hang(a.so_khach)
    dc = sinh_dia_chi(kh)
    dh, ctdh, tt = sinh_don_hang(a.so_don, kh, dc, sp, NHAN_VIEN)
    pn, ctpn, gia_gan_nhat = sinh_phieu_nhap(a.so_phieu_nhap, sp, spncc, NHAN_VIEN)
    spncc = [(s, n, gia_gan_nhat.get((s, n))) for s, n, _ in spncc]
    tk = sinh_ton_kho(sp)

    conn = psycopg2.connect(host=a.host, port=a.port, dbname=a.dbname, user=a.user, password=a.password)
    try:
        with conn, conn.cursor() as cur:
            cur.execute('SET search_path TO "LinhKien", public')
            print("Xóa dữ liệu cũ...")
            cur.execute("""TRUNCATE chi_tiet_phieu_nhap, phieu_nhap, ton_kho, thanh_toan,
                           chi_tiet_don_hang, don_hang, dia_chi, khach_hang, nhan_vien,
                           san_pham_nha_cung_cap, san_pham, nha_cung_cap, thuong_hieu,
                           danh_muc RESTART IDENTITY CASCADE""")
            print("Nạp dữ liệu:")
            nap(cur, "danh_muc", ["id", "ten", "mo_ta", "danh_muc_cha_id"], dm)
            nap(cur, "thuong_hieu", ["id", "ten", "quoc_gia"], th)
            nap(cur, "nha_cung_cap", ["id", "ten", "so_dien_thoai", "email", "tinh_thanh"], ncc)
            nap(cur, "san_pham", ["id", "ma_sku", "ten", "danh_muc_id", "thuong_hieu_id", "gia_niem_yet",
                                  "gia_von", "bao_hanh_thang", "ngay_ra_mat", "dang_kinh_doanh"], sp)
            nap(cur, "san_pham_nha_cung_cap", ["san_pham_id", "nha_cung_cap_id", "gia_nhap_gan_nhat"], spncc)
            nap(cur, "nhan_vien", ["id", "ho_ten", "chuc_vu", "ngay_vao_lam", "dang_lam_viec"], nv)
            nap(cur, "khach_hang", ["id", "ho_ten", "email", "so_dien_thoai", "gioi_tinh", "ngay_sinh",
                                    "ngay_dang_ky", "loai_khach"], kh)
            nap(cur, "dia_chi", ["id", "khach_hang_id", "tinh_thanh", "quan_huyen", "dia_chi_chi_tiet",
                                 "mac_dinh"], dc)
            nap(cur, "don_hang", ["id", "khach_hang_id", "nhan_vien_id", "dia_chi_giao_id", "ngay_dat",
                                  "ngay_giao", "trang_thai", "kenh_ban", "tong_tien"], dh)
            nap(cur, "chi_tiet_don_hang", ["id", "don_hang_id", "san_pham_id", "so_luong", "don_gia",
                                           "giam_gia"], ctdh)
            nap(cur, "thanh_toan", ["id", "don_hang_id", "phuong_thuc", "so_tien", "ngay_thanh_toan",
                                    "trang_thai"], tt)
            nap(cur, "ton_kho", ["san_pham_id", "so_luong_ton", "muc_ton_toi_thieu", "ngay_cap_nhat"], tk)
            nap(cur, "phieu_nhap", ["id", "nha_cung_cap_id", "nhan_vien_id", "ngay_nhap", "tong_tien"], pn)
            nap(cur, "chi_tiet_phieu_nhap", ["id", "phieu_nhap_id", "san_pham_id", "so_luong", "gia_nhap"],
                ctpn)

            # đồng bộ lại sequence vì đã chèn id thủ công
            for bang in ["danh_muc", "thuong_hieu", "nha_cung_cap", "san_pham", "nhan_vien", "khach_hang",
                         "dia_chi", "don_hang", "chi_tiet_don_hang", "thanh_toan", "phieu_nhap",
                         "chi_tiet_phieu_nhap"]:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{bang}', 'id'), "
                            f"(SELECT COALESCE(MAX(id), 1) FROM {bang}))")
            # TRUNCATE ... nhan_vien CASCADE làm rỗng bảng ánh xạ RLS tai_khoan_nhan_vien -> đồng bộ lại role nv_<id>
            cur.execute("SELECT to_regprocedure('\"LinhKien\".fn_dong_bo_tai_khoan_nhan_vien()') IS NOT NULL")
            if cur.fetchone()[0]:
                cur.execute('SELECT "LinhKien".fn_dong_bo_tai_khoan_nhan_vien()')
                print(f"Đồng bộ tài khoản RLS nhân viên: {cur.fetchone()[0]} role nv_<id>")
        print("Hoàn tất.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
