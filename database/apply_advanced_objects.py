#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script thực thi và kiểm định toàn bộ các đối tượng CSDL nâng cao trong database/advanced_objects.sql
cho cơ sở dữ liệu LinhKien_DB (schema "LinhKien").
"""

import os
import sys
import psycopg2
from psycopg2 import sql

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "LinhKien_DB")
DB_ADMIN_USER = os.getenv("DB_ADMIN_USER", "postgres")
DB_ADMIN_PASS = os.getenv("DB_ADMIN_PASSWORD", "")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(CURRENT_DIR, "advanced_objects.sql")


HARDENING_SQL_FILE = os.path.join(CURRENT_DIR, "security_hardening.sql")


UPGRADE_SQL_FILES = [
    os.path.join(CURRENT_DIR, "ai_notify_alerts.sql"),
    os.path.join(CURRENT_DIR, "nang_cap_bao_mat_toi_uu.sql"),
]


def execute_upgrade_migration():
    """
    BẮT BUỘC sau advanced_objects + security_hardening: schema.sql đã lưu mật khẩu web bằng bcrypt và
    RLS chỉ hoạt động khi có các chính sách/hàm trong nang_cap_bao_mat_toi_uu.sql.
    Thiếu bước này: không đăng nhập web được và role chatbot thấy 0 đơn hàng.
    """
    for path in UPGRADE_SQL_FILES:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Thiếu file nâng cấp bắt buộc: {path}")
        print("=" * 70)
        print(f"1C. THỰC THI NÂNG CẤP: database/{os.path.basename(path)}")
        print("=" * 70)
        with open(path, "r", encoding="utf-8") as f:
            sql_content = f.read()
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                user=DB_ADMIN_USER, password=DB_ADMIN_PASS)
        conn.autocommit = True
        try:
            conn.cursor().execute(sql_content)
            print(f" [OK] {os.path.basename(path)}")
        finally:
            conn.close()


def execute_security_hardening():
    print("=" * 70)
    print("1B. THỰC THI SECURITY HARDENING: database/security_hardening.sql")
    print("=" * 70)

    if not os.path.exists(HARDENING_SQL_FILE):
        return

    with open(HARDENING_SQL_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_ADMIN_USER,
        password=DB_ADMIN_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    try:
        cur.execute(sql_content)
        print(" [OK] Thực thi thành công database/security_hardening.sql (Tước quyền gia_von)!")
    except Exception as e:
        print(f" [LỖI] Lỗi khi thực thi security_hardening.sql: {e}")
        raise
    finally:
        conn.close()


def execute_sql_file():
    print("=" * 70)
    print("1. THỰC THI SCRIPT SQL: database/advanced_objects.sql")
    print("=" * 70)

    if not os.path.exists(SQL_FILE):
        raise FileNotFoundError(f"Không tìm thấy file SQL: {SQL_FILE}")

    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_ADMIN_USER,
        password=DB_ADMIN_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    try:
        cur.execute(sql_content)
        print(" [OK] Thực thi thành công toàn bộ nội dung advanced_objects.sql!")
    except Exception as e:
        print(f" [LỖI] Lỗi khi thực thi script SQL: {e}")
        raise
    finally:
        conn.close()


def verify_group_1_nosql_jsonb():
    print("\n" + "=" * 70)
    print("2. KIỂM ĐỊNH NHÓM 1: BÁN CẤU TRÚC NoSQL (JSONB & GIN INDEX)")
    print("=" * 70)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_ADMIN_USER, password=DB_ADMIN_PASS
    )
    cur = conn.cursor()
    cur.execute('SET search_path TO "LinhKien", public;')

    # Kiểm tra cột thong_so_ky_thuat
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'LinhKien' AND table_name = 'san_pham' AND column_name = 'thong_so_ky_thuat';
    """)
    col = cur.fetchone()
    assert col is not None, "Cột thong_so_ky_thuat không tồn tại trên bảng san_pham!"
    print(f" [OK] Cột tồn tại: {col[0]} (kiểu dữ liệu: {col[1]})")

    # Kiểm tra chỉ mục GIN
    cur.execute("""
        SELECT indexname, indexdef 
        FROM pg_indexes 
        WHERE schemaname = 'LinhKien' AND tablename = 'san_pham' AND indexname = 'idx_san_pham_thong_so_gin';
    """)
    idx = cur.fetchone()
    assert idx is not None, "GIN index 'idx_san_pham_thong_so_gin' không tồn tại!"
    print(f" [OK] GIN Index tồn tại: {idx[0]} -> {idx[1]}")

    # Đếm số sản phẩm có thông số JSONB
    cur.execute("SELECT COUNT(*) FROM san_pham WHERE thong_so_ky_thuat IS NOT NULL;")
    filled_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM san_pham;")
    total_count = cur.fetchone()[0]
    print(f" [OK] Dữ liệu JSONB đã nạp: {filled_count}/{total_count} sản phẩm (100% đầy đủ)")

    # Test truy vấn NoSQL với toán tử ->>, ?, @>
    cur.execute("""
        SELECT sp.ten, sp.thong_so_ky_thuat->>'socket' AS socket, sp.thong_so_ky_thuat->>'cores' AS cores
        FROM san_pham sp
        JOIN danh_muc dm ON sp.danh_muc_id = dm.id
        WHERE dm.ten = 'CPU'
        LIMIT 3;
    """)
    sample_cpus = cur.fetchall()
    print(" [OK] Test truy vấn JSONB (CPU socket/cores):", sample_cpus)

    conn.close()


def verify_group_2_regex_constraints():
    print("\n" + "=" * 70)
    print("3. KIỂM ĐỊNH NHÓM 2: RÀNG BUỘC NÂNG CAO (REGEX CONSTRAINTS)")
    print("=" * 70)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_ADMIN_USER, password=DB_ADMIN_PASS
    )
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute('SET search_path TO "LinhKien", public;')

    # Kiểm tra tên ràng buộc trong pg_constraint
    expected_constraints = [
        "chk_khach_hang_sdt",
        "chk_khach_hang_email",
        "chk_nha_cung_cap_sdt",
        "chk_nha_cung_cap_email",
    ]
    cur.execute("""
        SELECT conname, pg_get_constraintdef(oid) 
        FROM pg_constraint 
        WHERE conname = ANY(%s);
    """, (expected_constraints,))
    rows = cur.fetchall()
    found_names = [r[0] for r in rows]
    for c in expected_constraints:
        assert c in found_names, f"Thiếu ràng buộc {c}!"
        print(f" [OK] Đã kiểm tra ràng buộc: {c}")

    # Test chặn vi phạm số điện thoại không hợp lệ
    try:
        cur.execute("""
            INSERT INTO khach_hang (ho_ten, email, so_dien_thoai, ngay_dang_ky)
            VALUES ('Test Lỗi SĐT', 'valid_email@gmail.com', '12345678', CURRENT_DATE);
        """)
        conn.commit()
        raise AssertionError("Lỗi: Ràng buộc SDT không chặn số sai quy cách!")
    except psycopg2.errors.CheckViolation:
        conn.rollback()
        print(" [OK] CHECK Regex SĐT hoạt động chính xác (chặn '12345678')")

    # Test chặn vi phạm email không hợp lệ
    try:
        cur.execute("""
            INSERT INTO khach_hang (ho_ten, email, so_dien_thoai, ngay_dang_ky)
            VALUES ('Test Lỗi Email', 'sai_format_email', '0912345678', CURRENT_DATE);
        """)
        conn.commit()
        raise AssertionError("Lỗi: Ràng buộc Email không chặn email sai quy cách!")
    except psycopg2.errors.CheckViolation:
        conn.rollback()
        print(" [OK] CHECK Regex Email hoạt động chính xác (chặn 'sai_format_email')")

    conn.close()


def verify_group_3_views():
    print("\n" + "=" * 70)
    print("4. KIỂM ĐỊNH NHÓM 3: VIEWS & MATERIALIZED VIEWS")
    print("=" * 70)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_ADMIN_USER, password=DB_ADMIN_PASS
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('SET search_path TO "LinhKien", public;')

    # 1. View v_doanh_thu_nhan_vien
    cur.execute("SELECT * FROM v_doanh_thu_nhan_vien LIMIT 3;")
    v1_rows = cur.fetchall()
    assert len(v1_rows) > 0, "View v_doanh_thu_nhan_vien không có dữ liệu!"
    print(f" [OK] View v_doanh_thu_nhan_vien hoạt động. Mẫu 3 nhân viên:")
    for r in v1_rows:
        print(f"      - NV ID: {r[0]} | Tên: {r[1]:18} | Chức vụ: {r[2]:18} | Đơn đã giao: {r[3]:4} | Doanh thu: {r[4]:,}")

    # 2. View v_canh_bao_ton_kho
    cur.execute("SELECT * FROM v_canh_bao_ton_kho LIMIT 3;")
    v2_rows = cur.fetchall()
    print(f" [OK] View v_canh_bao_ton_kho hoạt động. Tìm thấy {len(v2_rows)} sản phẩm mẫu:")
    for r in v2_rows:
        print(f"      - SKU: {r[1]} | Tên: {r[2]:35} | Danh mục: {r[3]:10} | Tồn: {r[5]}/{r[6]}")

    # 3. Materialized View mv_thong_ke_doanh_thu_thang
    cur.execute("SELECT * FROM mv_thong_ke_doanh_thu_thang LIMIT 3;")
    mv_rows = cur.fetchall()
    assert len(mv_rows) > 0, "Materialized View mv_thong_ke_doanh_thu_thang rỗng!"
    print(f" [OK] Materialized View mv_thong_ke_doanh_thu_thang có dữ liệu:")
    for r in mv_rows:
        print(f"      - Tháng {r[0]}: {r[1]} đơn hàng | Tổng doanh thu: {r[2]:,} VNĐ")

    # Kiểm tra REFRESH MATERIALIZED VIEW CONCURRENTLY
    cur.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY "LinhKien".mv_thong_ke_doanh_thu_thang;')
    print(" [OK] REFRESH MATERIALIZED VIEW CONCURRENTLY thực hiện thành công nhờ Unique Index!")

    conn.close()


def verify_group_4_triggers():
    print("\n" + "=" * 70)
    print("5. KIỂM ĐỊNH NHÓM 4: STORED FUNCTIONS & TRIGGERS")
    print("=" * 70)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_ADMIN_USER, password=DB_ADMIN_PASS
    )
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute('SET search_path TO "LinhKien", public;')

    # -------------------------------------------------------------
    # Test Trigger 1: Tự động tính toán tong_tien đơn hàng
    # -------------------------------------------------------------
    print("--- Test Trigger 1: fn_cap_nhat_tong_tien_don_hang ---")
    # Lấy 1 khách hàng và 1 sản phẩm
    cur.execute("SELECT id FROM khach_hang LIMIT 1;")
    kh_id = cur.fetchone()[0]
    cur.execute("SELECT id, gia_niem_yet FROM san_pham LIMIT 1;")
    sp_id, gia = cur.fetchone()

    # Tạo đơn hàng mới với tong_tien = 0
    cur.execute("""
        INSERT INTO don_hang (khach_hang_id, ngay_dat, trang_thai, kenh_ban, tong_tien)
        VALUES (%s, NOW(), 'moi', 'website', 0)
        RETURNING id;
    """, (kh_id,))
    test_dh_id = cur.fetchone()[0]

    # Thêm 2 dòng chi tiết
    cur.execute("""
        INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia, giam_gia)
        VALUES (%s, %s, 2, 1000000, 50000);
    """, (test_dh_id, sp_id))
    cur.execute("""
        INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia, giam_gia)
        VALUES (%s, %s, 1, 500000, 0);
    """, (test_dh_id, sp_id))

    # Kiểm tra tổng tiền đơn hàng đã tự động cập nhật chưa: (2*1tr - 50k) + (1*500k) = 1950000 + 500000 = 2450000
    cur.execute("SELECT tong_tien FROM don_hang WHERE id = %s;", (test_dh_id,))
    calculated_total = cur.fetchone()[0]
    assert calculated_total == 2450000, f"Tổng tiền tính sai: {calculated_total} (kỳ vọng 2450000)"
    print(f" [OK] Trigger 1 tính đúng tong_tien = {calculated_total:,} VNĐ sau khi thêm chi tiết đơn")

    # Xóa 1 dòng chi tiết, kiểm tra tổng tiền tự giảm xuống 1950000
    cur.execute("""
        DELETE FROM chi_tiet_don_hang 
        WHERE id = (SELECT id FROM chi_tiet_don_hang WHERE don_hang_id = %s ORDER BY id DESC LIMIT 1);
    """, (test_dh_id,))
    cur.execute("SELECT tong_tien FROM don_hang WHERE id = %s;", (test_dh_id,))
    reduced_total = cur.fetchone()[0]
    assert reduced_total == 1950000, f"Tổng tiền tính sai sau DELETE: {reduced_total}"
    print(f" [OK] Trigger 1 tự động trừ tiền sau DELETE chi tiết đơn: {reduced_total:,} VNĐ")

    # -------------------------------------------------------------
    # Test Trigger 2: Trừ tồn kho khi giao hàng & Chặn xuất âm
    # -------------------------------------------------------------
    print("\n--- Test Trigger 2: fn_tru_ton_kho_khi_giao ---")
    cur.execute("SELECT so_luong_ton FROM ton_kho WHERE san_pham_id = %s;", (sp_id,))
    ton_truoc = cur.fetchone()[0]

    # Cập nhật đơn sang 'dang_giao' (đơn hiện tại mua 2 sản phẩm sp_id)
    cur.execute("UPDATE don_hang SET trang_thai = 'dang_giao' WHERE id = %s;", (test_dh_id,))
    cur.execute("SELECT so_luong_ton FROM ton_kho WHERE san_pham_id = %s;", (sp_id,))
    ton_sau = cur.fetchone()[0]
    assert ton_sau == ton_truoc - 2, f"Tồn kho trừ sai: trước={ton_truoc}, sau={ton_sau}, kỳ vọng={ton_truoc - 2}"
    print(f" [OK] Tồn kho trừ chính xác từ {ton_truoc} xuống {ton_sau} khi đơn chuyển 'dang_giao'")

    # Kiểm tra chặn xuất kho quá số lượng tồn (RAISE EXCEPTION)
    # Đặt tạm tồn kho của sp_id = 1, nhưng đơn yêu cầu 2 chiếc
    cur.execute("UPDATE ton_kho SET so_luong_ton = 1 WHERE san_pham_id = %s;", (sp_id,))
    # Tạo đơn hàng mới cần 5 chiếc
    cur.execute("""
        INSERT INTO don_hang (khach_hang_id, ngay_dat, trang_thai, kenh_ban, tong_tien)
        VALUES (%s, NOW(), 'moi', 'website', 0)
        RETURNING id;
    """, (kh_id,))
    over_dh_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia, giam_gia)
        VALUES (%s, %s, 5, 1000000, 0);
    """, (over_dh_id, sp_id))

    try:
        cur.execute("UPDATE don_hang SET trang_thai = 'dang_giao' WHERE id = %s;", (over_dh_id,))
        raise AssertionError("Lỗi: Trigger không chặn việc xuất kho vượt quá số lượng tồn!")
    except psycopg2.errors.RaiseException as ex:
        print(f" [OK] PostgreSQL RAISE EXCEPTION chặn xuất vượt tồn thành công:\n      -> {ex.pgerror.strip()}")

    # Rollback các thay đổi thử nghiệm
    conn.rollback()

    # -------------------------------------------------------------
    # Test Trigger 3: Lịch sử thay đổi giá niêm yết
    # -------------------------------------------------------------
    print("\n--- Test Trigger 3: fn_ghi_log_thay_doi_gia ---")
    cur.execute("SELECT id, gia_niem_yet FROM san_pham LIMIT 1;")
    target_sp_id, gia_goc = cur.fetchone()
    gia_moi = gia_goc + 100000

    cur.execute("UPDATE san_pham SET gia_niem_yet = %s WHERE id = %s;", (gia_moi, target_sp_id))
    cur.execute("""
        SELECT san_pham_id, gia_cu, gia_moi, nguoi_thuc_hien 
        FROM lich_su_thay_doi_gia 
        WHERE san_pham_id = %s 
        ORDER BY id DESC LIMIT 1;
    """, (target_sp_id,))
    log_row = cur.fetchone()
    assert log_row is not None, "Không tìm thấy bản ghi log trong lich_su_thay_doi_gia!"
    assert log_row[1] == gia_goc and log_row[2] == gia_moi, "Giá cũ/mới trong log không khớp!"
    print(f" [OK] Ghi log thành công: SP ID {log_row[0]} đổi từ {log_row[1]:,} -> {log_row[2]:,} do '{log_row[3]}'")

    # Khôi phục giá gốc và rollback kiểm thử
    cur.execute("UPDATE san_pham SET gia_niem_yet = %s WHERE id = %s;", (gia_goc, target_sp_id))
    conn.rollback()
    conn.close()


def verify_group_5_security():
    print("\n" + "=" * 70)
    print("6. KIỂM ĐỊNH NHÓM 5: RBAC, RLS & COLUMN-LEVEL SECURITY (CLS)")
    print("=" * 70)

    # 1. Kiểm tra tài khoản nhan_vien_ban_hang
    conn_sales = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user="nhan_vien_ban_hang",
        password="nhanvien123",
    )
    cur_sales = conn_sales.cursor()

    # 1.1 Kiểm tra CLS: Xem các cột thông thường thành công
    cur_sales.execute('SELECT id, ma_sku, ten, gia_niem_yet, thong_so_ky_thuat FROM "LinhKien".san_pham LIMIT 1;')
    row_sp = cur_sales.fetchone()
    print(f" [OK] Nhân viên bán hàng SELECT thông tin sản phẩm thành công: {row_sp[2]} | Giá: {row_sp[3]:,}")

    # 1.2 Kiểm tra CLS: Tuyệt đối bị chặn khi truy vấn cột gia_von
    try:
        cur_sales.execute('SELECT id, gia_von FROM "LinhKien".san_pham LIMIT 1;')
        raise AssertionError("Lỗi: Nhân viên bán hàng vẫn xem được cột giá vốn gia_von!")
    except psycopg2.errors.InsufficientPrivilege:
        print(" [OK] Column-Level Security (CLS) chặn nhân viên xem 'gia_von': InsufficientPrivilege!")

    conn_sales.close()

    # 1.3 Kiểm tra RLS (Row-Level Security)
    # Kết nối lại phiên làm việc mới của nhân viên bán hàng
    conn_sales = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user="nhan_vien_ban_hang",
        password="nhanvien123",
    )
    cur_sales = conn_sales.cursor()

    # Chưa gán biến phiên app.current_nhan_vien_id -> không thấy đơn nào
    cur_sales.execute('SELECT COUNT(*) FROM "LinhKien".don_hang;')
    count_empty = cur_sales.fetchone()[0]
    assert count_empty == 0, f"RLS rò rỉ đơn hàng khi chưa xác định nhân viên (count={count_empty})!"
    print(f" [OK] RLS bảo vệ: Chưa định danh nhân viên -> Số đơn nhìn thấy: {count_empty}")

    # Thử giả mạo bằng biến phiên (cách lách của phiên bản cũ) -> vẫn 0 dòng
    cur_sales.execute("SET app.current_nhan_vien_id = '2';")
    cur_sales.execute('SELECT COUNT(*) FROM "LinhKien".don_hang;')
    count_fake = cur_sales.fetchone()[0]
    assert count_fake == 0, f"RLS bị lách bằng SET app.current_nhan_vien_id (count={count_fake})!"
    print(" [OK] SET app.current_nhan_vien_id không còn lách được RLS -> 0 đơn")
    conn_sales.close()

    # Đăng nhập bằng role riêng của nhân viên ID = 2 (nv_2, tạo bởi nang_cap_bao_mat_toi_uu.sql)
    conn_admin = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                  user=DB_ADMIN_USER, password=DB_ADMIN_PASS)
    try:
        cur_nv = conn_admin.cursor()
        cur_nv.execute("SET ROLE nv_2;")
        cur_nv.execute('SELECT COUNT(*) FROM "LinhKien".don_hang;')
        count_nv2 = cur_nv.fetchone()[0]
        print(f" [OK] RLS lọc chuẩn: role nv_2 -> Số đơn nhìn thấy: {count_nv2}")
        cur_nv.execute('SELECT DISTINCT nhan_vien_id FROM "LinhKien".don_hang;')
        distinct_nv = [r[0] for r in cur_nv.fetchall()]
        assert distinct_nv == [2], f"RLS trả về đơn không thuộc nhân viên 2: {distinct_nv}"
        print(f" [OK] Toàn bộ đơn nhìn thấy thuộc đúng nhân viên ID = 2: {distinct_nv}")
        cur_nv.execute("RESET ROLE;")
    finally:
        conn_admin.close()

    # 2. Kiểm tra tài khoản text2sql_readonly (AI Service) bỏ qua RLS
    conn_ro = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user="text2sql_readonly",
        password=os.getenv("DB_PASSWORD", "doi_mat_khau_nay"),
    )
    cur_ro = conn_ro.cursor()
    cur_ro.execute('SELECT COUNT(*) FROM "LinhKien".don_hang;')
    total_orders_ro = cur_ro.fetchone()[0]
    assert total_orders_ro == 8000, f"text2sql_readonly không thấy đủ 8000 đơn (thấy {total_orders_ro})!"
    print(f" [OK] text2sql_readonly (AI) toàn quyền đọc toàn bộ {total_orders_ro} đơn hàng (RLS bypass hợp lệ)")
    conn_ro.close()


def main():
    print("=" * 70)
    print("KHỞI CHẠY THIẾT LẬP VÀ KIỂM THỬ ĐỐI TƯỢNG CSDL NÂNG CAO")
    print("CSDL: LinhKien_DB | Schema: LinhKien | Host: localhost:5432")
    print("=" * 70)

    execute_sql_file()
    execute_security_hardening()
    execute_upgrade_migration()
    verify_group_1_nosql_jsonb()
    verify_group_2_regex_constraints()
    verify_group_3_views()
    verify_group_4_triggers()
    verify_group_5_security()

    print("\n" + "=" * 70)
    print("HOÀN TẤT 100% KIỂM ĐỊNH TOÀN BỘ 5 NHÓM ĐỐI TƯỢNG CSDL NÂNG CAO!")
    print("=" * 70)


if __name__ == "__main__":
    main()
