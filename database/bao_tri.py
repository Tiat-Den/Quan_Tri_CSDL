#!/usr/bin/env python3
"""
BẢO TRÌ ĐỊNH KỲ CSDL LinhKien_DB — chứng minh tiêu chí "SỐNG" và "TỐI ƯU" (100% Python)
====================================================================================
Mỗi lần chạy:
  1. VACUUM (ANALYZE) các bảng của schema "LinhKien": dọn dòng chết, cập nhật thống kê cho bộ tối ưu truy vấn.
  2. Làm mới materialized view báo cáo (fn_lam_moi_bao_cao -> REFRESH ... CONCURRENTLY, không khóa người đọc).
  3. Đồng bộ role đăng nhập nv_<id> cho nhân viên mới (RLS), tạo trước phân vùng theo tháng cho bảng lich_su_thay_doi_gia (fn_tao_phan_vung_lich_su_gia).
  4. In báo cáo sức khỏe: tỷ lệ dòng chết, bảng chưa từng ANALYZE, chỉ mục không được dùng,
     tỷ lệ đọc từ cache (cache hit ratio).
  Kết quả được ghi thêm vào ai_service/logs/bao_tri.log.

Chạy:
    python bao_tri.py                 # bảo trì + báo cáo
    python bao_tri.py --chi-bao-cao   # chỉ xem báo cáo sức khỏe, không thay đổi gì

Lên lịch tự động mỗi đêm 2h sáng (Windows Task Scheduler, mở PowerShell):
    schtasks /Create /TN "LinhKien_BaoTri" /SC DAILY /ST 02:00 ^
      /TR "python D:\\PhạmTiếnĐạt\\Quan_tri_csdl\\Cuoi_Ky\\database\\bao_tri.py"

Mật khẩu postgres lấy theo thứ tự: --password, biến môi trường PGPASSWORD, DB_ADMIN_PASSWORD trong ai_service/.env.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "ai_service" / "logs" / "bao_tri.log"


def doc_mat_khau_env() -> str:
    for p in (ROOT / "ai_service" / ".env", ROOT / ".env"):
        try:
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("DB_ADMIN_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def co_ham(cur, ten: str) -> bool:
    cur.execute("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'LinhKien' AND p.proname = %s", (ten,))
    return cur.fetchone() is not None


def bao_cao(cur, out):
    out("\n--- BÁO CÁO SỨC KHỎE ---")
    cur.execute("""
        SELECT relname, n_live_tup, n_dead_tup,
               round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS pct_chet,
               COALESCE(last_analyze, last_autoanalyze) IS NULL AS chua_analyze
        FROM pg_stat_user_tables WHERE schemaname = 'LinhKien'
        ORDER BY n_dead_tup DESC, relname""")
    rows = cur.fetchall()
    chua = [r[0] for r in rows if r[4]]
    nhieu_chet = [r for r in rows if (r[3] or 0) >= 10]
    out(f"Số bảng: {len(rows)} | Chưa từng ANALYZE: {len(chua)}" + (f" ({', '.join(chua[:8])})" if chua else ""))
    out("Bảng có >= 10% dòng chết: " + (", ".join(f"{r[0]} ({r[3]}%)" for r in nhieu_chet) or "không có"))

    cur.execute("""
        SELECT round(100.0 * sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0), 2)
        FROM pg_statio_user_tables WHERE schemaname = 'LinhKien'""")
    out(f"Tỷ lệ đọc từ bộ đệm (cache hit): {cur.fetchone()[0]}%  (tốt khi > 99%)")

    cur.execute("""
        SELECT s.indexrelname, pg_size_pretty(pg_relation_size(s.indexrelid))
        FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid
        WHERE s.schemaname = 'LinhKien' AND s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary
        ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 8""")
    unused = cur.fetchall()
    out("Chỉ mục chưa được dùng lần nào (cân nhắc sau thời gian dài quan sát): "
        + (", ".join(f"{n} ({sz})" for n, sz in unused) or "không có"))

    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    out(f"Dung lượng CSDL: {cur.fetchone()[0]}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Bảo trì định kỳ LinhKien_DB")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--dbname", default="LinhKien_DB")
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--password", default="")
    ap.add_argument("--chi-bao-cao", action="store_true", help="chỉ in báo cáo, không VACUUM/REFRESH")
    a = ap.parse_args()

    import psycopg2
    conn = psycopg2.connect(host=a.host, port=a.port, dbname=a.dbname, user=a.user,
                            password=a.password or os.getenv("PGPASSWORD") or doc_mat_khau_env())
    conn.autocommit = True  # VACUUM không chạy được trong transaction
    lines = []

    def out(msg=""):
        print(msg)
        lines.append(msg)

    out("=" * 70)
    out(f"BẢO TRÌ LinhKien_DB — {datetime.now():%Y-%m-%d %H:%M:%S}")
    out("=" * 70)
    with conn.cursor() as cur:
        if not a.chi_bao_cao:
            cur.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'LinhKien' AND c.relkind IN ('r', 'p', 'm') ORDER BY c.relname")
            bang = [r[0] for r in cur.fetchall()]
            t0 = time.perf_counter()
            for b in bang:
                cur.execute(f'VACUUM (ANALYZE) "LinhKien"."{b}"')
            out(f"[1] VACUUM (ANALYZE) {len(bang)} bảng — {time.perf_counter() - t0:.2f}s")

            if co_ham(cur, "fn_lam_moi_bao_cao"):
                cur.execute('SELECT "LinhKien".fn_lam_moi_bao_cao()')
                out(f"[2] {cur.fetchone()[0]}")
            else:
                out("[2] Bỏ qua: chưa có fn_lam_moi_bao_cao (hãy chạy nang_cap_bao_mat_toi_uu.sql)")

            if co_ham(cur, "fn_dong_bo_tai_khoan_nhan_vien"):
                cur.execute('SELECT "LinhKien".fn_dong_bo_tai_khoan_nhan_vien()')
                out(f"[2b] Đồng bộ role RLS cho {cur.fetchone()[0]} nhân viên (nv_<id>)")

            if co_ham(cur, "fn_tao_phan_vung_lich_su_gia"):
                cur.execute('SELECT "LinhKien".fn_tao_phan_vung_lich_su_gia(3)')
                out(f"[3] Phân vùng lich_su_thay_doi_gia: tạo mới {cur.fetchone()[0]} phân vùng cho 3 tháng tới")
            else:
                out("[3] Bỏ qua: chưa có fn_tao_phan_vung_lich_su_gia")
        bao_cao(cur, out)
    conn.close()

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except OSError:
        pass


if __name__ == "__main__":
    main()
