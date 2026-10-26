"""Kiểm thử offline các hàm làm sạch dữ liệu của database/etl_lam_sach_du_lieu.py."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database")))
import etl_lam_sach_du_lieu as etl  # noqa: E402


class TestLamSach(unittest.TestCase):
    def test_ho_ten(self):
        self.assertEqual(etl.chuan_hoa_ho_ten("  nguyễn   VĂN  a "), "Nguyễn Văn A")
        self.assertIsNone(etl.chuan_hoa_ho_ten("   "))
        self.assertIsNone(etl.chuan_hoa_ho_ten("abc123"))

    def test_sdt(self):
        for raw in ("+84 912.345.678", "84912345678", "0912 345 678", "912345678"):
            self.assertEqual(etl.chuan_hoa_sdt(raw), ("0912345678", None))
        self.assertIsNone(etl.chuan_hoa_sdt("12345")[0])
        self.assertEqual(etl.chuan_hoa_sdt(""), (None, None))

    def test_email(self):
        self.assertEqual(etl.chuan_hoa_email("  An.Tran@GMAIL.COM "), ("an.tran@gmail.com", None))
        self.assertIsNotNone(etl.chuan_hoa_email("sai-email@")[1])

    def test_ngay_va_ma_hoa(self):
        for raw in ("20/04/1971", "1971-04-20", "20-04-1971", "20.04.1971"):
            self.assertEqual(etl.chuan_hoa_ngay(raw), date(1971, 4, 20))
        self.assertIsNone(etl.chuan_hoa_ngay("31/02/1990"))
        self.assertEqual(etl.chuan_hoa_gioi_tinh("Nữ"), "nu")
        self.assertEqual(etl.chuan_hoa_gioi_tinh("M"), "nam")
        self.assertEqual(etl.chuan_hoa_loai_khach("Doanh nghiệp"), "doanh_nghiep")
        self.assertEqual(etl.chuan_hoa_loai_khach(""), "le")

    def test_dong_loi_bi_loai(self):
        d, loi, _ = etl.lam_sach_dong({"ho_ten": " ", "email": "a@b.com"})
        self.assertIsNone(d)
        d, loi, _ = etl.lam_sach_dong({"ho_ten": "Trần Văn Lỗi", "email": "sai@", "so_dien_thoai": "123"})
        self.assertIsNone(d)
        self.assertIn("liên lạc", loi[0])

    def test_ngay_sinh_phi_ly_bi_bo(self):
        d, _, cb = etl.lam_sach_dong({"ho_ten": "Lê Tương Lai", "so_dien_thoai": "0987654000",
                                      "ngay_sinh": "2099-01-01"}, hom_nay=date(2026, 10, 1))
        self.assertIsNone(d["ngay_sinh"])
        self.assertEqual(d["ngay_dang_ky"], date(2026, 10, 1))

    def test_khu_trung(self):
        a = {"email": "x@gmail.com", "so_dien_thoai": "0911111111"}
        b = {"email": "y@gmail.com", "so_dien_thoai": "0911111111"}
        c = {"email": "da.co@gmail.com", "so_dien_thoai": None}
        giu, trung = etl.khu_trung_lap([(1, a), (2, b), (3, c)], {"da.co@gmail.com"}, set())
        self.assertEqual([i for i, _ in giu], [1])
        self.assertEqual([i for i, _ in trung], [2, 3])

    def test_du_lieu_ban_sau_lam_sach_qua_rang_buoc(self):
        import re
        rows = etl.sinh_dong_ban(40, [("cu@gmail.com", "0900000001")])
        sach = [etl.lam_sach_dong(r)[0] for r in rows]
        sach = [d for d in sach if d]
        self.assertGreater(len(sach), 35)
        for d in sach:
            self.assertRegex(d["so_dien_thoai"] or "0900000000", r"^0[0-9]{9,10}$")
            self.assertEqual(d["ho_ten"], re.sub(r"\s+", " ", d["ho_ten"]).strip())
            self.assertIn(d["loai_khach"], ("le", "si", "doanh_nghiep"))


if __name__ == "__main__":
    unittest.main()
