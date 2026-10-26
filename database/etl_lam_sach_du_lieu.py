#!/usr/bin/env python3
"""
ETL LÀM SẠCH DỮ LIỆU KHÁCH HÀNG  (Extract -> Transform -> Load)  — 100% Python
==============================================================================
Chứng minh tiêu chí "SẠCH": dữ liệu từ nguồn bên ngoài (file Excel, form web, nhập tay...)
KHÔNG được ghi thẳng vào bảng nghiệp vụ, mà phải đi qua vùng đệm (staging) và được làm sạch.

  1. EXTRACT  : dữ liệu thô nằm ở schema "staging", bảng staging.khach_hang_tho (mọi cột đều là TEXT).
                Tùy chọn --tao-du-lieu-ban sinh sẵn dữ liệu bẩn để demo (khoảng trắng thừa, viết hoa lộn xộn,
                số điện thoại +84 / có dấu chấm, email viết hoa, ngày nhiều định dạng, giới tính "Nữ"/"F"/"1",
                bản ghi trùng, bản ghi trùng với khách đã có, email/SĐT sai...).
  2. TRANSFORM: Python chuẩn hóa từng trường, kiểm tra hợp lệ, khử trùng lặp (trong lô và với CSDL).
  3. LOAD     : chỉ dòng sạch được INSERT vào "LinhKien".khach_hang (vẫn bị CHECK constraint kiểm tra lần 2).
                Dòng bị loại ghi lý do vào staging.etl_nhat_ky_loi; mỗi lần chạy ghi tổng kết vào staging.etl_lan_chay.

Chạy (PowerShell, trong thư mục database):
    python etl_lam_sach_du_lieu.py --tao-du-lieu-ban 40      # sinh 40 dòng bẩn vào staging
    python etl_lam_sach_du_lieu.py --chay-thu                # xem kết quả làm sạch, KHÔNG ghi vào CSDL
    python etl_lam_sach_du_lieu.py                           # làm sạch + nạp thật
    python etl_lam_sach_du_lieu.py --hoan-tac                # xóa các khách do ETL nạp (chưa có đơn hàng)

Mật khẩu postgres lấy theo thứ tự: --password, biến môi trường PGPASSWORD, DB_ADMIN_PASSWORD trong ai_service/.env.
"""
import argparse
import os
import random
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCHEMA = '"LinhKien"'

# ------------------------------------------------------------------------------
# TRANSFORM — các hàm làm sạch (thuần Python, kiểm thử offline được)
# ------------------------------------------------------------------------------
RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
RE_SDT = re.compile(r"^0[0-9]{9,10}$")
MAX_HO_TEN = 100   # = độ dài cột khach_hang.ho_ten VARCHAR(100)
MAX_EMAIL = 100    # = độ dài cột khach_hang.email VARCHAR(100)
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y")

GIOI_TINH_MAP = {
    "nam": "nam", "m": "nam", "male": "nam", "1": "nam", "trai": "nam",
    "nu": "nu", "nữ": "nu", "f": "nu", "female": "nu", "0": "nu", "gai": "nu", "gái": "nu",
    "khac": "khac", "khác": "khac", "other": "khac",
}
LOAI_KHACH_MAP = {
    "le": "le", "lẻ": "le", "khach le": "le", "khách lẻ": "le", "retail": "le",
    "si": "si", "sỉ": "si", "khach si": "si", "khách sỉ": "si", "wholesale": "si",
    "doanh_nghiep": "doanh_nghiep", "doanh nghiep": "doanh_nghiep", "doanh nghiệp": "doanh_nghiep",
    "dn": "doanh_nghiep", "cong ty": "doanh_nghiep", "công ty": "doanh_nghiep", "company": "doanh_nghiep",
}


def _blank(v) -> bool:
    return v is None or str(v).strip() == "" or str(v).strip().lower() in ("null", "none", "n/a", "-")


def chuan_hoa_ho_ten(v) -> Optional[str]:
    """'  nguyễn   VĂN  a ' -> 'Nguyễn Văn A' (Unicode NFC, bỏ khoảng trắng thừa, viết hoa chữ đầu)."""
    if _blank(v):
        return None
    s = unicodedata.normalize("NFC", str(v))
    s = re.sub(r"[^\w\s'.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or any(ch.isdigit() for ch in s):
        return None
    return " ".join(w[:1].upper() + w[1:].lower() for w in s.split(" "))


def chuan_hoa_email(v) -> Tuple[Optional[str], Optional[str]]:
    """Trả về (email_sạch, lỗi). Email rỗng là hợp lệ (cột cho phép NULL)."""
    if _blank(v):
        return None, None
    s = re.sub(r"\s+", "", str(v)).lower().rstrip(".")
    if len(s) > MAX_EMAIL or not RE_EMAIL.match(s):
        return None, f"Email sai định dạng: {v!r}"
    return s, None


def chuan_hoa_sdt(v) -> Tuple[Optional[str], Optional[str]]:
    """'+84 912.345.678' / '84912345678' / '912345678' -> '0912345678'."""
    if _blank(v):
        return None, None
    raw = str(v).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("84") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    elif len(digits) == 9 and not digits.startswith("0"):
        digits = "0" + digits
    if not RE_SDT.match(digits):
        return None, f"Số điện thoại không hợp lệ: {raw!r}"
    return digits, None


def chuan_hoa_gioi_tinh(v) -> Optional[str]:
    if _blank(v):
        return None
    return GIOI_TINH_MAP.get(unicodedata.normalize("NFC", str(v)).strip().lower())


def chuan_hoa_loai_khach(v) -> str:
    if _blank(v):
        return "le"
    return LOAI_KHACH_MAP.get(unicodedata.normalize("NFC", str(v)).strip().lower(), "le")


def chuan_hoa_ngay(v) -> Optional[date]:
    if _blank(v):
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def lam_sach_dong(row: Dict, hom_nay: Optional[date] = None) -> Tuple[Optional[Dict], List[str], List[str]]:
    """
    Làm sạch 1 dòng thô. Trả về (dòng_sạch | None, danh_sách_lỗi_loại_bỏ, danh_sách_cảnh_báo_đã_sửa).
    Quy tắc loại bỏ: thiếu họ tên, hoặc không còn cách liên lạc (email và SĐT đều rỗng/sai).
    """
    hom_nay = hom_nay or date.today()
    loi, canh_bao = [], []

    ho_ten = chuan_hoa_ho_ten(row.get("ho_ten"))
    if not ho_ten:
        loi.append(f"Họ tên rỗng hoặc không hợp lệ: {row.get('ho_ten')!r}")
    elif len(ho_ten) > MAX_HO_TEN:
        loi.append(f"Họ tên dài quá {MAX_HO_TEN} ký tự")
    elif ho_ten != row.get("ho_ten"):
        canh_bao.append("chuẩn hóa họ tên")

    email, e_err = chuan_hoa_email(row.get("email"))
    if e_err:
        canh_bao.append(e_err + " -> bỏ trống")
    sdt, s_err = chuan_hoa_sdt(row.get("so_dien_thoai"))
    if s_err:
        canh_bao.append(s_err + " -> bỏ trống")
    if email and email != row.get("email"):
        canh_bao.append("chuẩn hóa email")
    if sdt and sdt != row.get("so_dien_thoai"):
        canh_bao.append("chuẩn hóa SĐT")
    if not email and not sdt:
        loi.append("Không có email hoặc số điện thoại hợp lệ để liên lạc")

    gioi_tinh = chuan_hoa_gioi_tinh(row.get("gioi_tinh"))
    if gioi_tinh is None and not _blank(row.get("gioi_tinh")):
        canh_bao.append(f"Giới tính không nhận dạng được: {row.get('gioi_tinh')!r} -> bỏ trống")

    ngay_dang_ky = chuan_hoa_ngay(row.get("ngay_dang_ky"))
    if ngay_dang_ky is None or ngay_dang_ky > hom_nay:
        if not _blank(row.get("ngay_dang_ky")):
            canh_bao.append(f"Ngày đăng ký không hợp lệ: {row.get('ngay_dang_ky')!r} -> dùng ngày hôm nay")
        ngay_dang_ky = hom_nay

    ngay_sinh = chuan_hoa_ngay(row.get("ngay_sinh"))
    if ngay_sinh is None and not _blank(row.get("ngay_sinh")):
        canh_bao.append(f"Ngày sinh sai định dạng: {row.get('ngay_sinh')!r} -> bỏ trống")
    if ngay_sinh is not None and not (date(1900, 1, 2) <= ngay_sinh < ngay_dang_ky):
        canh_bao.append(f"Ngày sinh phi lý: {ngay_sinh} -> bỏ trống")
        ngay_sinh = None

    if loi:
        return None, loi, canh_bao
    return {
        "ho_ten": ho_ten, "email": email, "so_dien_thoai": sdt, "gioi_tinh": gioi_tinh,
        "ngay_sinh": ngay_sinh, "ngay_dang_ky": ngay_dang_ky,
        "loai_khach": chuan_hoa_loai_khach(row.get("loai_khach")),
    }, [], canh_bao


def khu_trung_lap(dong_sach: List[Tuple[int, Dict]], email_da_co: set, sdt_da_co: set):
    """Loại trùng theo email (không phân biệt hoa thường) hoặc SĐT — trong lô và so với CSDL."""
    giu, trung = [], []
    thay_email, thay_sdt = set(email_da_co), set(sdt_da_co)
    for tho_id, d in dong_sach:
        if d["email"] and d["email"] in thay_email:
            trung.append((tho_id, f"Trùng email {d['email']} (đã có trong CSDL hoặc trong lô)"))
            continue
        if d["so_dien_thoai"] and d["so_dien_thoai"] in thay_sdt:
            trung.append((tho_id, f"Trùng số điện thoại {d['so_dien_thoai']} (đã có trong CSDL hoặc trong lô)"))
            continue
        if d["email"]:
            thay_email.add(d["email"])
        if d["so_dien_thoai"]:
            thay_sdt.add(d["so_dien_thoai"])
        giu.append((tho_id, d))
    return giu, trung


# ------------------------------------------------------------------------------
# Sinh dữ liệu bẩn để demo
# ------------------------------------------------------------------------------
HO = ["nguyễn", "TRẦN", "Lê", "phạm", "Hoàng", "  vũ", "Đặng", "bùi"]
DEM = ["văn", "THỊ", "Minh", "đức", "Thu", "ngọc", "Quốc"]
TEN = ["an", "BÌNH", "Châu", "dũng", "Hà", "khoa", "Linh", "nam", "Phúc", "trang"]


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def sinh_dong_ban(n: int, mau_da_co: List[Tuple[str, str]], seed: int = 2026) -> List[Dict]:
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        ho, dem, ten = rnd.choice(HO), rnd.choice(DEM), rnd.choice(TEN)
        ten_day_du = f"{ho}  {dem}   {ten} " if i % 3 else f"{ho} {dem} {ten}".upper()
        so = f"9{rnd.randint(10000000, 99999999)}"
        kieu_sdt = i % 5
        sdt = {0: f"+84 {so[:3]}.{so[3:6]}.{so[6:]}", 1: f"84{so}", 2: f"0{so[:3]} {so[3:6]} {so[6:]}",
               3: f"0{so}", 4: so}[kieu_sdt]
        t_kd, h_kd = _bo_dau(ten.strip()), _bo_dau(ho.strip())
        email = f"  {t_kd.upper()}.{h_kd}{i + 1000}@GMAIL.COM " if i % 4 else f"{t_kd.lower()}{i + 1000}@Gmail.Com"
        ns = date(rnd.randint(1965, 2004), rnd.randint(1, 12), rnd.randint(1, 28))
        ngay_sinh = [ns.strftime("%d/%m/%Y"), ns.isoformat(), ns.strftime("%d-%m-%Y"), ns.strftime("%d.%m.%Y")][i % 4]
        rows.append({
            "nguon": rnd.choice(["form_web", "excel_cua_hang", "nhap_tay"]),
            "ho_ten": ten_day_du, "email": email, "so_dien_thoai": sdt,
            "gioi_tinh": rnd.choice(["Nam", "nữ", "F", "M", "1", "0", "Nữ", "khác", ""]),
            "ngay_sinh": ngay_sinh, "ngay_dang_ky": date.today().strftime("%d/%m/%Y"),
            "loai_khach": rnd.choice(["Lẻ", "le", "sỉ", "Doanh nghiệp", "DN", "", "retail"]),
        })
    # Các dòng lỗi điển hình
    rows += [
        {"nguon": "nhap_tay", "ho_ten": "   ", "email": "khongten@gmail.com", "so_dien_thoai": "0912000111",
         "gioi_tinh": "nam", "ngay_sinh": "", "ngay_dang_ky": "", "loai_khach": ""},
        {"nguon": "form_web", "ho_ten": "Trần Văn Lỗi", "email": "sai-email@", "so_dien_thoai": "12345",
         "gioi_tinh": "nam", "ngay_sinh": "31/02/1990", "ngay_dang_ky": "", "loai_khach": ""},
        {"nguon": "excel_cua_hang", "ho_ten": "Lê Thị Tương Lai", "email": "tuonglai2099@gmail.com",
         "so_dien_thoai": "0987654000", "gioi_tinh": "nu", "ngay_sinh": "2099-01-01", "ngay_dang_ky": "", "loai_khach": ""},
    ]
    if rows:
        rows.append(dict(rows[0], nguon="excel_cua_hang"))  # trùng trong lô
    for email, sdt in mau_da_co[:2]:                          # trùng với khách đã có trong CSDL
        rows.append({"nguon": "excel_cua_hang", "ho_ten": "khách   CŨ  nhập lại", "email": (email or "").upper(),
                     "so_dien_thoai": sdt, "gioi_tinh": "", "ngay_sinh": "", "ngay_dang_ky": "", "loai_khach": ""})
    return rows


# ------------------------------------------------------------------------------
# Kết nối & thao tác CSDL
# ------------------------------------------------------------------------------
def doc_mat_khau_env() -> str:
    for p in (Path(__file__).resolve().parent.parent / "ai_service" / ".env",
              Path(__file__).resolve().parent.parent / ".env"):
        try:
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("DB_ADMIN_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def ket_noi(a):
    import psycopg2
    pwd = a.password or os.getenv("PGPASSWORD") or doc_mat_khau_env()
    return psycopg2.connect(host=a.host, port=a.port, dbname=a.dbname, user=a.user, password=pwd)


DDL_STAGING = """
CREATE SCHEMA IF NOT EXISTS staging;
REVOKE ALL ON SCHEMA staging FROM PUBLIC;
CREATE TABLE IF NOT EXISTS staging.khach_hang_tho (
    id            SERIAL PRIMARY KEY,
    nguon         TEXT,
    ho_ten        TEXT, email TEXT, so_dien_thoai TEXT, gioi_tinh TEXT,
    ngay_sinh     TEXT, ngay_dang_ky TEXT, loai_khach TEXT,
    ngay_nap      TIMESTAMPTZ NOT NULL DEFAULT now(),
    trang_thai    TEXT NOT NULL DEFAULT 'cho_xu_ly'
                  CHECK (trang_thai IN ('cho_xu_ly', 'da_nap', 'bi_loai'))
);
CREATE TABLE IF NOT EXISTS staging.etl_lan_chay (
    id SERIAL PRIMARY KEY, thoi_diem TIMESTAMPTZ NOT NULL DEFAULT now(),
    tong_dong INT, so_nap INT, so_loai INT, so_trung INT, so_canh_bao INT
);
CREATE TABLE IF NOT EXISTS staging.etl_nhat_ky_loi (
    id SERIAL PRIMARY KEY, lan_chay_id INT REFERENCES staging.etl_lan_chay(id),
    dong_tho_id INT, ly_do TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.etl_ket_qua (
    lan_chay_id INT REFERENCES staging.etl_lan_chay(id),
    dong_tho_id INT, khach_hang_id INT, PRIMARY KEY (dong_tho_id)
);
"""


def tao_du_lieu_ban(conn, n: int) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT email, so_dien_thoai FROM {SCHEMA}.khach_hang "
                    "WHERE email IS NOT NULL AND so_dien_thoai IS NOT NULL ORDER BY id LIMIT 2")
        rows = sinh_dong_ban(n, cur.fetchall())
        for r in rows:
            cur.execute("INSERT INTO staging.khach_hang_tho (nguon, ho_ten, email, so_dien_thoai, gioi_tinh, "
                        "ngay_sinh, ngay_dang_ky, loai_khach) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (r["nguon"], r["ho_ten"], r["email"], r["so_dien_thoai"], r["gioi_tinh"],
                         r["ngay_sinh"], r["ngay_dang_ky"], r["loai_khach"]))
    return len(rows)


def chay_etl(conn, chay_thu: bool) -> Dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ho_ten, email, so_dien_thoai, gioi_tinh, ngay_sinh, ngay_dang_ky, loai_khach "
                    "FROM staging.khach_hang_tho WHERE trang_thai = 'cho_xu_ly' ORDER BY id FOR UPDATE")
        cols = [d[0] for d in cur.description]
        tho = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f"SELECT lower(email) FROM {SCHEMA}.khach_hang WHERE email IS NOT NULL")
        email_da_co = {r[0] for r in cur.fetchall()}
        cur.execute(f"SELECT so_dien_thoai FROM {SCHEMA}.khach_hang WHERE so_dien_thoai IS NOT NULL")
        sdt_da_co = {r[0] for r in cur.fetchall()}

        sach, bi_loai, so_canh_bao, vi_du = [], [], 0, []
        for r in tho:
            d, loi, cb = lam_sach_dong(r)
            so_canh_bao += len(cb)
            if d is None:
                bi_loai.append((r["id"], "; ".join(loi)))
            else:
                sach.append((r["id"], d))
                if len(vi_du) < 6 and cb:
                    vi_du.append((r, d, cb))
        giu, trung = khu_trung_lap(sach, email_da_co, sdt_da_co)

        cur.execute("INSERT INTO staging.etl_lan_chay (tong_dong, so_nap, so_loai, so_trung, so_canh_bao) "
                    "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (len(tho), len(giu), len(bi_loai), len(trung), so_canh_bao))
        lan_id = cur.fetchone()[0]
        so_nap = 0
        for tho_id, d in giu:
            # SAVEPOINT cho từng dòng: một dòng vi phạm ràng buộc CSDL chỉ làm hỏng dòng đó,
            # không làm ROLLBACK cả lô (và không kẹt lại ở trạng thái 'cho_xu_ly' cho lần chạy sau)
            cur.execute("SAVEPOINT sp_dong")
            try:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.khach_hang (ho_ten, email, so_dien_thoai, gioi_tinh, ngay_sinh, "
                    "ngay_dang_ky, loai_khach) VALUES (%(ho_ten)s, %(email)s, %(so_dien_thoai)s, %(gioi_tinh)s, "
                    "%(ngay_sinh)s, %(ngay_dang_ky)s, %(loai_khach)s) RETURNING id", d)
                kh_id = cur.fetchone()[0]
                cur.execute("RELEASE SAVEPOINT sp_dong")
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp_dong")
                bi_loai.append((tho_id, f"CSDL từ chối: {str(exc).splitlines()[0]}"))
                continue
            cur.execute("INSERT INTO staging.etl_ket_qua VALUES (%s,%s,%s)", (lan_id, tho_id, kh_id))
            cur.execute("UPDATE staging.khach_hang_tho SET trang_thai = 'da_nap' WHERE id = %s", (tho_id,))
            so_nap += 1
        cur.execute("UPDATE staging.etl_lan_chay SET so_nap = %s, so_loai = %s WHERE id = %s",
                    (so_nap, len(bi_loai), lan_id))
        for tho_id, ly_do in bi_loai + trung:
            cur.execute("INSERT INTO staging.etl_nhat_ky_loi (lan_chay_id, dong_tho_id, ly_do) VALUES (%s,%s,%s)",
                        (lan_id, tho_id, ly_do))
            cur.execute("UPDATE staging.khach_hang_tho SET trang_thai = 'bi_loai' WHERE id = %s", (tho_id,))
    if chay_thu:
        conn.rollback()
    else:
        conn.commit()
    return {"tong": len(tho), "nap": so_nap, "loai": bi_loai, "trung": trung,
            "so_canh_bao": so_canh_bao, "vi_du": vi_du, "lan_id": lan_id}


def hoan_tac(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(f"""
            DELETE FROM {SCHEMA}.khach_hang k USING staging.etl_ket_qua e
            WHERE k.id = e.khach_hang_id
              AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.don_hang d WHERE d.khach_hang_id = k.id)
              AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.dia_chi c WHERE c.khach_hang_id = k.id)
            RETURNING k.id""")
        n = cur.rowcount
        cur.execute("TRUNCATE staging.etl_ket_qua, staging.etl_nhat_ky_loi, staging.etl_lan_chay, "
                    "staging.khach_hang_tho RESTART IDENTITY")
    conn.commit()
    return n


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="ETL làm sạch dữ liệu khách hàng (staging -> LinhKien.khach_hang)")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--dbname", default="LinhKien_DB")
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--password", default="")
    ap.add_argument("--tao-du-lieu-ban", type=int, metavar="N", help="sinh N dòng bẩn (+ vài dòng lỗi/trùng) vào staging")
    ap.add_argument("--chay-thu", action="store_true", help="chỉ xem kết quả, ROLLBACK, không ghi gì")
    ap.add_argument("--hoan-tac", action="store_true", help="xóa khách hàng do ETL nạp (chưa có đơn) và làm rỗng staging")
    a = ap.parse_args()

    conn = ket_noi(a)
    with conn.cursor() as cur:
        cur.execute(DDL_STAGING)
    conn.commit()

    if a.hoan_tac:
        print(f"Đã hoàn tác: xóa {hoan_tac(conn)} khách hàng do ETL nạp, làm rỗng vùng staging.")
        return
    if a.tao_du_lieu_ban:
        n = tao_du_lieu_ban(conn, a.tao_du_lieu_ban)
        conn.commit()
        print(f"Đã sinh {n} dòng dữ liệu BẨN vào staging.khach_hang_tho.")

    kq = chay_etl(conn, a.chay_thu)
    print("=" * 70)
    print(f"ETL LÀM SẠCH KHÁCH HÀNG {'(CHẠY THỬ — ĐÃ ROLLBACK)' if a.chay_thu else ''}")
    print("=" * 70)
    print(f"Tổng dòng thô chờ xử lý : {kq['tong']}")
    print(f"Nạp vào khach_hang      : {kq['nap']}")
    print(f"Bị loại (dữ liệu hỏng)  : {len(kq['loai'])}")
    print(f"Bị loại (trùng lặp)     : {len(kq['trung'])}")
    print(f"Số trường đã tự sửa     : {kq['so_canh_bao']}")
    if kq["vi_du"]:
        print("\nVí dụ TRƯỚC -> SAU khi làm sạch:")
        for r, d, cb in kq["vi_du"]:
            print(f"  {r['ho_ten']!r:32} -> {d['ho_ten']}")
            print(f"  {r['so_dien_thoai']!r:32} -> {d['so_dien_thoai']}   | {r['email']!r} -> {d['email']}")
            print(f"  ngày sinh {r['ngay_sinh']!r} -> {d['ngay_sinh']} | giới tính {r['gioi_tinh']!r} -> {d['gioi_tinh']}")
            print(f"  (đã sửa: {'; '.join(cb)})\n")
    if kq["loai"] or kq["trung"]:
        print("Dòng bị loại (ghi vào staging.etl_nhat_ky_loi):")
        for tho_id, ly_do in kq["loai"] + kq["trung"]:
            print(f"  - dòng thô #{tho_id}: {ly_do}")
    conn.close()


if __name__ == "__main__":
    main()
