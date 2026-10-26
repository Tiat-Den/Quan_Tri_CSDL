"""
AI 5 — THỰC HIỆN PHÂN VÙNG TRÊN BẢN SAO MINH HỌA (không đụng tới bảng don_hang thật)

Tạo bảng "LinhKien".don_hang_phan_vung theo đúng kế hoạch AI 5 sinh ra:
  - PARTITION BY RANGE (ngay_dat), mỗi tháng 1 phân vùng + 3 tháng tới + phân vùng DEFAULT
  - khóa chính (id, ngay_dat) — bảng phân vùng bắt buộc khóa chính chứa cột phân vùng
  - chép toàn bộ dữ liệu don_hang sang, ANALYZE
Sau đó so sánh EXPLAIN ANALYZE cùng một truy vấn theo tháng trên bảng gốc và bảng phân vùng
để thấy "partition pruning": bảng phân vùng chỉ quét đúng phân vùng của tháng cần tìm.

An toàn:
  - Bảng gốc don_hang, khóa ngoại, trigger, RLS, view... giữ nguyên; web và các tab khác không bị ảnh hưởng.
  - Toàn bộ thao tác chạy trong 1 giao dịch: lỗi giữa chừng thì tự hoàn tác.
  - Bản sao không cấp quyền cho role chỉ đọc / nhân viên (chỉ postgres đọc được) vì không có RLS.
  - Có hàm xóa bản sao.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from app.db import get_connection

SCHEMA = "LinhKien"
COPY_TABLE = "don_hang_phan_vung"
FORECAST_MONTHS = 3


def _add_month(d: date, n: int = 1) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _admin_conn():
    conn = get_connection(use_admin=True)
    conn.autocommit = False
    return conn


def _close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def copy_status() -> Dict[str, Any]:
    """Bản sao đã tồn tại chưa, gồm những phân vùng nào, mỗi phân vùng bao nhiêu dòng."""
    conn = None
    try:
        conn = get_connection(use_admin=True)
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f'"{SCHEMA}".{COPY_TABLE}',))
            if not cur.fetchone()[0]:
                return {"success": True, "exists": False, "partitions": [], "total_rows": 0}
            cur.execute(
                f"""
                SELECT c.relname,
                       pg_get_expr(c.relpartbound, c.oid) AS bound,
                       (SELECT count(*) FROM pg_inherits i2 WHERE i2.inhparent = c.oid) AS sub,
                       pg_total_relation_size(c.oid) AS bytes
                FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = '"{SCHEMA}".{COPY_TABLE}'::regclass
                ORDER BY c.relname
                """
            )
            parts = []
            for name, bound, _sub, size in cur.fetchall():
                cur.execute(f'SELECT count(*) FROM "{SCHEMA}"."{name}"')
                parts.append({"phan_vung": name, "khoang": bound, "so_dong": cur.fetchone()[0], "bytes": size})
            cur.execute(f'SELECT count(*) FROM "{SCHEMA}".{COPY_TABLE}')
            total = cur.fetchone()[0]
        return {"success": True, "exists": True, "partitions": parts, "total_rows": total}
    except Exception as exc:
        return {"success": False, "error": str(exc), "exists": False, "partitions": []}
    finally:
        if conn is not None:
            _close(conn)


def create_partitioned_copy() -> Dict[str, Any]:
    """Tạo (hoặc tạo lại) bảng don_hang_phan_vung phân vùng theo tháng và chép dữ liệu sang."""
    conn = None
    try:
        conn = _admin_conn()
        with conn.cursor() as cur:
            cur.execute(f'SELECT min(ngay_dat)::date, max(ngay_dat)::date, count(*) FROM "{SCHEMA}".don_hang')
            d_min, d_max, n_src = cur.fetchone()
            if not n_src:
                return {"success": False, "error": "Bảng don_hang chưa có dữ liệu để phân vùng."}

            steps: List[str] = []
            cur.execute(f'DROP TABLE IF EXISTS "{SCHEMA}".{COPY_TABLE} CASCADE')
            # LIKE ... INCLUDING CONSTRAINTS: chép đúng cột, kiểu dữ liệu, NOT NULL, CHECK (không chép DEFAULT
            # để bản sao không dùng chung sequence id với bảng thật)
            ddl = (f'CREATE TABLE "{SCHEMA}".{COPY_TABLE} (LIKE "{SCHEMA}".don_hang INCLUDING CONSTRAINTS) '
                   f'PARTITION BY RANGE (ngay_dat)')
            cur.execute(ddl)
            steps.append(ddl + ";")
            pk = f'ALTER TABLE "{SCHEMA}".{COPY_TABLE} ADD PRIMARY KEY (id, ngay_dat)'
            cur.execute(pk)
            steps.append(pk + ";")

            start = date(d_min.year, d_min.month, 1)
            stop = _add_month(date(d_max.year, d_max.month, 1), 1 + FORECAST_MONTHS)  # + 3 tháng dự báo
            m, n_parts = start, 0
            while m < stop:
                nxt = _add_month(m)
                name = f"{COPY_TABLE}_y{m.year}m{m.month:02d}"
                stmt = (f'CREATE TABLE "{SCHEMA}"."{name}" PARTITION OF "{SCHEMA}".{COPY_TABLE} '
                        f"FOR VALUES FROM ('{m.isoformat()}') TO ('{nxt.isoformat()}')")
                cur.execute(stmt)
                if n_parts < 2:
                    steps.append(stmt + ";")
                n_parts += 1
                m = nxt
            steps.append(f"-- ... tổng cộng {n_parts} phân vùng theo tháng ({start:%m/%Y} → {_add_month(stop, -1):%m/%Y})")
            dflt = f'CREATE TABLE "{SCHEMA}".{COPY_TABLE}_default PARTITION OF "{SCHEMA}".{COPY_TABLE} DEFAULT'
            cur.execute(dflt)
            steps.append(dflt + ";")

            # Chỉ mục trên bảng cha tự tạo trên từng phân vùng
            idx = f'CREATE INDEX ON "{SCHEMA}".{COPY_TABLE} (khach_hang_id)'
            cur.execute(idx)
            steps.append(idx + ";")
            ins = f'INSERT INTO "{SCHEMA}".{COPY_TABLE} SELECT * FROM "{SCHEMA}".don_hang'
            cur.execute(ins)
            n_copied = cur.rowcount
            steps.append(ins + ";")
            # Bản sao không có RLS -> chỉ postgres được đọc. Thu hồi cả quyền mặc định (ALTER DEFAULT PRIVILEGES)
            # đã tự cấp cho role chỉ đọc, trên bảng cha VÀ từng phân vùng (đọc thẳng phân vùng cũng bị chặn).
            cur.execute(
                """SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                   WHERE i.inhparent = %s::regclass""", (f'"{SCHEMA}".{COPY_TABLE}',))
            for tbl in [COPY_TABLE] + [r[0] for r in cur.fetchall()]:
                cur.execute(f"""DO $$ DECLARE r TEXT; BEGIN
                    EXECUTE 'REVOKE ALL ON "{SCHEMA}"."{tbl}" FROM PUBLIC';
                    FOREACH r IN ARRAY ARRAY['text2sql_readonly','manager_readonly','nhan_vien_ban_hang'] LOOP
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                            EXECUTE format('REVOKE ALL ON "{SCHEMA}".%I FROM %I', '{tbl}', r);
                        END IF;
                    END LOOP; END $$""")
            cur.execute(
                f"""COMMENT ON TABLE "{SCHEMA}".{COPY_TABLE} IS
                'Bản sao minh họa phân vùng của don_hang (AI 5). Không dùng cho nghiệp vụ; xóa được bất cứ lúc nào.'"""
            )
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'ANALYZE "{SCHEMA}".{COPY_TABLE}')
        return {
            "success": True,
            "source_rows": n_src,
            "copied_rows": n_copied,
            "partitions": n_parts + 1,
            "range": f"{start:%m/%Y} → {_add_month(stop, -1):%m/%Y}",
            "ddl": "\n".join(steps),
        }
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return {"success": False, "error": f"Đã hoàn tác toàn bộ, CSDL không thay đổi. Lỗi: {exc}"}
    finally:
        if conn is not None:
            _close(conn)


def drop_partitioned_copy() -> Dict[str, Any]:
    conn = None
    try:
        conn = get_connection(use_admin=True)
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{SCHEMA}".{COPY_TABLE} CASCADE')
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        if conn is not None:
            _close(conn)


def _plan_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Tóm tắt cây EXPLAIN: chi phí, thời gian, các bảng/phân vùng thật sự được quét."""
    scanned: List[str] = []

    def walk(node):
        rel = node.get("Relation Name")
        if rel:
            scanned.append(f"{rel} ({node.get('Node Type')})")
        for child in node.get("Plans", []) or []:
            walk(child)

    walk(plan["Plan"])
    return {
        "cost": round(float(plan["Plan"].get("Total Cost", 0)), 1),
        "time_ms": round(float(plan.get("Execution Time", 0)), 3),
        "scanned": scanned,
    }


def compare_month_query(year: int, month: int) -> Dict[str, Any]:
    """EXPLAIN ANALYZE cùng một truy vấn doanh thu 1 tháng trên bảng gốc và bảng phân vùng."""
    m = date(int(year), int(month), 1)
    nxt = _add_month(m)
    sql_tpl = ('SELECT count(*) AS so_don, sum(tong_tien) AS doanh_thu FROM "{schema}".{table} '
               "WHERE ngay_dat >= '{a}' AND ngay_dat < '{b}'")
    conn = None
    try:
        conn = get_connection(use_admin=True)
        out: Dict[str, Any] = {"success": True, "month": f"{m:%m/%Y}"}
        with conn.cursor() as cur:
            cur.execute("SET max_parallel_workers_per_gather = 0")  # kế hoạch gọn, dễ so sánh
            for key, table in (("goc", "don_hang"), ("phan_vung", COPY_TABLE)):
                sql = sql_tpl.format(schema=SCHEMA, table=table, a=m.isoformat(), b=nxt.isoformat())
                cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)
                raw = cur.fetchone()[0]
                plan = raw[0] if isinstance(raw, list) else raw
                cur.execute(sql)
                so_don, doanh_thu = cur.fetchone()
                out[key] = dict(_plan_summary(plan), sql=sql + ";", so_don=so_don, doanh_thu=float(doanh_thu or 0))
        out["same_result"] = (out["goc"]["so_don"], out["goc"]["doanh_thu"]) == (
            out["phan_vung"]["so_don"], out["phan_vung"]["doanh_thu"])
        return out
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        if conn is not None:
            _close(conn)


def available_months() -> List[str]:
    """Các tháng có đơn hàng (YYYY-MM), mới nhất trước."""
    conn = None
    try:
        conn = get_connection(use_admin=True)
        with conn.cursor() as cur:
            cur.execute(f"""SELECT DISTINCT to_char(date_trunc('month', ngay_dat), 'YYYY-MM') AS m
                           FROM "{SCHEMA}".don_hang ORDER BY m DESC""")
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn is not None:
            _close(conn)
