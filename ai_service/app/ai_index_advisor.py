"""
MODULE AI 4: CỐ VẤN TỰ ĐỘNG ĐỀ XUẤT INDEX (SMART AUTO-INDEXING ADVISOR)
Cải tiến toàn diện theo tài liệu kỹ thuật (A4-1 đến A4-6):
- Khảo sát thực tế catalog PostgreSQL: reltuples, kích thước bảng, index hiện có qua pg_class & pg_index.
- Cây quyết định theo luật (Rule-Based Decision Tree) minh bạch với reason_code và danh sách skipped.
- Trích xuất cột chuẩn xác theo allowlist cột (không gán cứng 'id'), hỗ trợ Composite Index và Non-sargable suggestions.
- Đo lường thực tế qua HypoPG (chỉ mục giả định, nếu máy chủ đã cài) hoặc báo cáo trung thực, không bịa số.
- Đề xuất đúng loại chỉ mục: B-Tree, B-Tree nhiều cột, Partial Index (cột ít giá trị), GIN pg_trgm
  (ILIKE '%...%'), GIN jsonb_path_ops / chỉ mục biểu thức cho cột JSONB.
- Phân tích khối lượng công việc thật từ pg_stat_statements (analyze_workload).
- Sinh DDL an toàn theo chuẩn PostgreSQL (CONCURRENTLY cho bảng thường, non-concurrently cho bảng phân vùng).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app import config
from app.db import execute_query, validate_sql_security
from app.schema_catalog import ALLOWLIST_TABLES

logger = logging.getLogger("ai_service.index_advisor")

MIN_TABLE_ROWS = getattr(config, "MIN_TABLE_ROWS", 1000)
MAX_SELECTIVITY = getattr(config, "MAX_SELECTIVITY", 0.2)

# Cột ít giá trị phân biệt (low-cardinality): lọc "cột = hằng số" trên các cột này
# phù hợp với PARTIAL INDEX (chỉ mục một phần) thay vì đưa cột vào khóa chỉ mục.
LOW_CARDINALITY_COLUMNS = {"trang_thai", "kenh_ban", "dang_kinh_doanh", "phuong_thuc"}
JSONB_COLUMNS = {"thong_so_ky_thuat"}

# "(trang_thai)::text = 'hoan_thanh'::text"  hoặc  "dang_kinh_doanh = true"
_RE_PARTIAL_EQ = re.compile(
    r"\(?(\w+)\)?(?:::\w+)?\s*=\s*('(?:[^']|'')*'|true|false)(?:::[\w ]+)?",
    re.IGNORECASE,
)
_RE_JSONB_TEXT_KEY = re.compile(r"\(?(\w+)\s*->>\s*'([^']+)'\)?", re.IGNORECASE)


class AIIndexAdvisor:
    """
    Module AI Chẩn đoán Kế hoạch thực thi & Cố vấn Chỉ mục theo luật (Smart Index Advisor).
    """

    @classmethod
    def get_table_stats(cls, table_name: str) -> Dict[str, Any]:
        """
        Truy vấn thông số thống kê thực tế từ PostgreSQL catalogs (pg_class, pg_index, pg_attribute) - A4-1.
        """
        clean_tbl = table_name.lower().strip()
        stats = {
            "reltuples": 1000.0,
            "bytes": 0,
            "relkind": "r",
            "existing_indexes": {},  # index_name -> leading_column
        }

        # 1. Lấy reltuples, bytes, relkind
        sql_class = """
        SELECT c.reltuples, pg_relation_size(c.oid) AS size_bytes, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'LinhKien' AND c.relname = %s;
        """
        res_class = execute_query(sql_class, [clean_tbl])
        if res_class["success"] and res_class["data"]:
            row = res_class["data"][0]
            stats["reltuples"] = max(float(row.get("reltuples", 0.0)), 0.0)
            stats["bytes"] = int(row.get("size_bytes", 0))
            stats["relkind"] = str(row.get("relkind", "r"))

        # 2. Lấy danh sách index hiện có và cột dẫn đầu
        sql_idx = """
        SELECT i.relname AS index_name, a.attname AS leading_column
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ix.indkey[0]
        WHERE n.nspname = 'LinhKien' AND t.relname = %s;
        """
        res_idx = execute_query(sql_idx, [clean_tbl])
        if res_idx["success"] and res_idx["data"]:
            for r in res_idx["data"]:
                stats["existing_indexes"][r["index_name"]] = r["leading_column"].lower()

        return stats

    @classmethod
    def get_table_columns(cls, table_name: str) -> Set[str]:
        """Lấy danh sách các cột hợp lệ của bảng từ allowlist (A4-1)."""
        tbl = table_name.lower().strip()
        cols = ALLOWLIST_TABLES.get(tbl, [])
        return {c.lower() for c in cols}

    @classmethod
    def _extract_plan_nodes(cls, plan_node: dict, collected: list):
        """Duyệt đệ quy toàn bộ cây kế hoạch thực thi PostgreSQL."""
        collected.append(plan_node)
        for child in plan_node.get("Plans", []):
            cls._extract_plan_nodes(child, collected)

    @classmethod
    def _extract_candidate_columns(cls, node: dict, valid_columns: Set[str]) -> Tuple[List[str], List[str], bool, Optional[str]]:
        """
        Bóc tách các cột ứng viên từ Filter, Index Cond, Sort Key... (A4-3).
        Trả về: (equality_cols, range_cols, is_non_sargable, rewrite_suggestion).
        """
        filt = str(node.get("Filter", ""))
        hash_cond = str(node.get("Hash Cond", ""))
        merge_cond = str(node.get("Merge Cond", ""))
        sort_keys = node.get("Sort Key", [])
        if isinstance(sort_keys, list):
            sort_str = " ".join(str(k) for k in sort_keys)
        else:
            sort_str = str(sort_keys)

        combined_text = f"{filt} {hash_cond} {merge_cond} {sort_str}"

        # Kiểm tra non-sargable (ví dụ EXTRACT(YEAR FROM col) hoặc ILIKE '%...%')
        is_non_sargable = False
        rewrite_suggestion = None

        if "extract(" in combined_text.lower():
            is_non_sargable = True
            m_ext = re.search(r'extract\((\w+)\s+from\s+(\w+)\)\s*=\s*(\d+)', combined_text, re.IGNORECASE)
            if m_ext:
                unit, col_name, yr = m_ext.group(1).lower(), m_ext.group(2).lower(), m_ext.group(3)
                if unit in ("year", "nam"):
                    next_yr = str(int(yr) + 1)
                    rewrite_suggestion = f"Đề xuất viết lại điều kiện sargable: `{col_name} >= '{yr}-01-01' AND {col_name} < '{next_yr}-01-01'`"

        if "~~*" in combined_text or "ilike" in combined_text.lower():
            if re.search(r"['\"]%[^'\"]+['\"]", combined_text):
                is_non_sargable = True
                rewrite_suggestion = "Điều kiện tìm kiếm chứa ký tự đại diện `%` ở đầu: Đề xuất cài extension `pg_trgm` và tạo GIN Index `USING gin (col gin_trgm_ops)`."

        # Bóc tách tên cột: loại bỏ cast kiểu dữ liệu ::text, ::numeric, ngoặc, tiền tố
        clean_text = re.sub(r'::[a-zA-Z0-9_]+', '', combined_text)
        tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', clean_text)

        equality_cols = []
        range_cols = []

        # Phân biệt so sánh bằng (=) vs so sánh khoảng (<, >, between)
        for token in tokens:
            col = token.lower()
            if col in valid_columns:
                # Kiểm tra so sánh bằng
                eq_pattern = rf'{col}\s*='
                range_pattern = rf'{col}\s*(?:>=|<=|>|<|between)'
                if re.search(eq_pattern, clean_text, re.IGNORECASE):
                    if col not in equality_cols:
                        equality_cols.append(col)
                elif re.search(range_pattern, clean_text, re.IGNORECASE):
                    if col not in range_cols and col not in equality_cols:
                        range_cols.append(col)
                elif col not in equality_cols and col not in range_cols:
                    # Cột trong SORT KEY hoặc JOIN
                    range_cols.append(col)

        return equality_cols, range_cols, is_non_sargable, rewrite_suggestion

    @staticmethod
    def _detect_partial_predicate(filter_text: str, valid_columns: Set[str]) -> Optional[Tuple[str, str]]:
        """
        Phát hiện điều kiện "cột_ít_giá_trị = hằng số" để đề xuất PARTIAL INDEX.
        Ví dụ Filter: ((trang_thai)::text = 'hoan_thanh'::text) -> ("trang_thai", "'hoan_thanh'")
        """
        for m in _RE_PARTIAL_EQ.finditer(filter_text or ""):
            col, val = m.group(1).lower(), m.group(2)
            if col in LOW_CARDINALITY_COLUMNS and col in valid_columns:
                return col, val
        return None

    @staticmethod
    def _detect_jsonb_access(filter_text: str) -> Optional[Dict[str, str]]:
        """
        Phát hiện truy vấn trên cột JSONB:
        - toán tử chứa @>  -> GIN (jsonb_path_ops)
        - trích khóa ->>   -> chỉ mục biểu thức B-Tree trên (cột ->> 'khóa')
        """
        text = filter_text or ""
        for col in JSONB_COLUMNS:
            if col not in text:
                continue
            if "@>" in text:
                return {"column": col, "kind": "containment"}
            m = _RE_JSONB_TEXT_KEY.search(text)
            if m and m.group(1).lower() == col:
                return {"column": col, "kind": "text_key", "key": m.group(2)}
        return None

    @classmethod
    def _measure_with_hypopg(cls, sql: str, params: Optional[list], index_stmt: str) -> Dict[str, Any]:
        """
        Đo THẬT mức giảm chi phí bằng chỉ mục giả định HypoPG (không tạo index thật, không khóa bảng):
        1. hypopg_create_index(<lệnh CREATE INDEX>) trong cùng phiên kết nối.
        2. EXPLAIN lại truy vấn -> lấy Total Cost mới và kiểm tra planner có chọn index đó không.
        3. hypopg_reset() dọn dẹp.
        Trả về {"measured": False} nếu máy chủ chưa cài extension hypopg.
        """
        result = {"measured": False, "method": "none"}
        try:
            from app.db import get_connection
            conn = get_connection()
        except Exception as e:
            result["note"] = f"Không mở được kết nối đo HypoPG: {e}"
            return result
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'hypopg';")
                if cur.fetchone() is None:
                    result["note"] = "Chưa cài extension hypopg (CREATE EXTENSION hypopg;) nên chưa đo được chi phí sau khi có index."
                    return result
                cur.execute("SELECT indexrelid FROM hypopg_create_index(%s);", (index_stmt,))
                cur.execute(f"EXPLAIN (FORMAT JSON, COSTS TRUE) {sql}", params or None)
                plan = cur.fetchone()[0][0]["Plan"]
                plan_text = str(plan)
                cur.execute("SELECT hypopg_reset();")
            result.update({
                "measured": True,
                "method": "hypopg",
                "cost_after": round(float(plan.get("Total Cost", 0.0)), 2),
                "index_used": "Index" in plan_text,  # Index Scan / Bitmap Index Scan trên index giả định
            })
        except Exception as e:
            result["note"] = f"HypoPG đo thất bại: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return result

    @classmethod
    def _make_recommendation(
        cls, *, rel_name: str, relkind: str, idx_name: str, key_expr: str, using: str,
        where: Optional[str], index_type: str, cols: List[str], node_cost: float, node_rows: float,
        reltuples: float, selectivity: float, filter_cond: str, clean_sql: str, params: Optional[list],
        reason: str, prerequisite: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sinh DDL an toàn đúng ngữ cảnh (A4-5) và đo chi phí sau khi có index bằng HypoPG (A4-4)."""
        using_clause = f" USING {using}" if using and using != "btree" else ""
        where_clause = f" WHERE {where}" if where else ""
        target = f'"LinhKien"."{rel_name}"'
        if relkind == "p":
            ddl = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {target}{using_clause} ({key_expr}){where_clause};"
            ddl_note = "Bảng đã phân vùng (Partitioned): Không dùng CONCURRENTLY; lệnh sẽ tự động tạo index trên tất cả phân vùng con."
        else:
            ddl = f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {target}{using_clause} ({key_expr}){where_clause};"
            ddl_note = ("Lệnh DDL chỉ mang tính đề xuất cho DBA: chạy bằng tài khoản quản trị, KHÔNG đặt trong "
                        "BEGIN/COMMIT (CONCURRENTLY không chạy được trong transaction). Sau khi tạo, chạy "
                        "EXPLAIN ANALYZE để xác nhận Index Scan.")
        if prerequisite:
            ddl = prerequisite + "\n" + ddl

        evidence = {
            "table_rows": int(reltuples),
            "plan_rows": int(node_rows),
            "selectivity": round(selectivity, 3),
            "cost_before": round(node_cost, 2),
            "cost_after": None,
            "improvement_percent": None,
            "measured": False,
            "method": "none",
        }
        hypo_stmt = f"CREATE INDEX ON {target}{using_clause} ({key_expr}){where_clause}"
        measure = cls._measure_with_hypopg(clean_sql, params, hypo_stmt)
        if measure.get("measured"):
            root_before = node_cost
            after = measure["cost_after"]
            evidence.update({
                "cost_after": after,
                "measured": True,
                "method": "hypopg",
                "improvement_percent": round((1 - after / root_before) * 100, 1) if root_before > 0 else None,
            })
        elif measure.get("note"):
            evidence["note"] = measure["note"]

        return {
            "table": rel_name,
            "index_type": index_type,
            "current_cost": round(node_cost, 2),
            "plan_rows": int(node_rows),
            "filter_condition": filter_cond if filter_cond else "Quét tuần tự trong truy vấn liên kết",
            "recommended_columns": cols,
            "recommended_sql": ddl,
            "ddl_note": ddl_note,
            "evidence": evidence,
            "reason": reason,
        }

    @classmethod
    def analyze_workload(cls, top_n: int = 5) -> Dict[str, Any]:
        """
        Phân tích KHỐI LƯỢNG CÔNG VIỆC thật thay vì một câu lệnh đơn lẻ:
        lấy các truy vấn tốn tổng thời gian nhiều nhất từ pg_stat_statements rồi chạy advisor cho từng câu.
        Truy vấn đã chuẩn hóa có tham số $1, $2 được phân tích bằng EXPLAIN (GENERIC_PLAN) (PostgreSQL 16+).
        """
        res_ext = execute_query("SELECT 1 AS ok FROM pg_extension WHERE extname = 'pg_stat_statements';")
        if not res_ext.get("success") or not res_ext.get("data"):
            return {
                "success": False,
                "error": "Chưa bật pg_stat_statements (thêm shared_preload_libraries = 'pg_stat_statements' "
                         "vào postgresql.conf, khởi động lại, rồi CREATE EXTENSION pg_stat_statements;).",
            }
        res_ver = execute_query("SELECT current_setting('server_version_num')::int AS v;")
        server_ver = int(res_ver["data"][0]["v"]) if res_ver.get("success") and res_ver.get("data") else 0

        # Ưu tiên hàm SECURITY DEFINER fn_top_truy_van (nang_cap_bao_mat_toi_uu.sql): thấy thống kê của mọi phiên
        # nhưng chỉ câu SELECT đã chuẩn hóa — role chỉ đọc không cần quyền pg_read_all_stats (quyền đó lộ mật khẩu).
        res = execute_query('SELECT * FROM "LinhKien".fn_top_truy_van(%s);', [int(top_n)])
        if not res.get("success"):
            res = execute_query(
                """
                SELECT query, calls, round(total_exec_time::numeric, 2) AS total_ms,
                       round(mean_exec_time::numeric, 2) AS mean_ms, rows
                FROM pg_stat_statements
                WHERE query ILIKE 'select%%' AND query NOT ILIKE '%%pg_%%'
                ORDER BY total_exec_time DESC
                LIMIT %s;
                """,
                [int(top_n)],
            )
        if not res.get("success"):
            return {"success": False, "error": res.get("error", "Không đọc được pg_stat_statements")}

        items = []
        for row in res.get("data", []):
            q = str(row["query"]).strip().rstrip(";")
            has_params = bool(re.search(r"\$\d+", q))
            if has_params and server_ver < 160000:
                items.append({**row, "analysis": None, "note": "Câu có tham số $n cần PostgreSQL 16+ (EXPLAIN GENERIC_PLAN)."})
                continue
            analysis = cls.analyze_query(q, generic_plan=has_params)
            items.append({**row, "analysis": analysis})
        return {"success": True, "server_version": server_ver, "workload": items}

    @classmethod
    def analyze_query(cls, sql_query: str, params: list = None, generic_plan: bool = False) -> Dict[str, Any]:
        """
        Phân tích kế hoạch thực thi câu lệnh SQL và đưa ra khuyến nghị Index bằng Cây quyết định theo luật (A4-2).
        """
        clean_sql = sql_query.strip().rstrip(";")
        is_safe, sec_err = validate_sql_security(clean_sql)
        if not is_safe:
            return {
                "success": False,
                "error": f"Câu lệnh không vượt qua kiểm tra an ninh AST: {sec_err}",
                "needs_index": False,
                "recommendations": [],
                "skipped": [],
            }

        # 1. Chạy EXPLAIN (FORMAT JSON, COSTS TRUE)
        explain_opts = "FORMAT JSON, COSTS TRUE" + (", GENERIC_PLAN" if generic_plan else "")
        explain_sql = f"EXPLAIN ({explain_opts}) {clean_sql}"
        res = execute_query(explain_sql, params)

        if not res["success"] or not res["data"]:
            return {
                "success": False,
                "error": f"Không thể lấy kế hoạch thực thi: {res.get('error', 'Lỗi không xác định')}",
                "needs_index": False,
                "recommendations": [],
                "skipped": [],
            }

        try:
            plan_json = res["data"][0]["QUERY PLAN"][0]["Plan"]
        except (KeyError, IndexError, TypeError):
            return {
                "success": False,
                "error": "Định dạng JSON của Execution Plan không hợp lệ.",
                "needs_index": False,
                "recommendations": [],
                "skipped": [],
            }

        # 2. Duyệt các node trong Execution Plan
        nodes = []
        cls._extract_plan_nodes(plan_json, nodes)

        root_cost = plan_json.get("Total Cost", 0.0)
        root_rows = plan_json.get("Plan Rows", 0)

        # 3. Phân tích Decision Tree tìm Seq Scan
        recommendations = []
        skipped = []

        for node in nodes:
            node_type = str(node.get("Node Type", ""))
            rel_name = str(node.get("Relation Name", "")).lower()

            if "seq scan" not in node_type.lower() or not rel_name:
                continue

            node_cost = float(node.get("Total Cost", 0.0))
            node_rows = float(node.get("Plan Rows", 0.0))
            filter_cond = str(node.get("Filter", ""))

            # Lấy thống kê thực tế catalog của bảng (A4-1)
            tbl_stats = cls.get_table_stats(rel_name)
            reltuples = tbl_stats["reltuples"]
            relkind = tbl_stats["relkind"]
            existing_indexes = tbl_stats["existing_indexes"]
            valid_cols = cls.get_table_columns(rel_name)

            # CÂY QUYẾT ĐỊNH THEO LUẬT (A4-2):
            # Nhánh 1: Bảng có reltuples < MIN_TABLE_ROWS -> bỏ qua (SMALL_TABLE)
            if reltuples > 0 and reltuples < MIN_TABLE_ROWS:
                skipped.append({
                    "table": rel_name,
                    "reason_code": "SMALL_TABLE",
                    "explanation": f"Bảng `{rel_name}` có số dòng nhỏ ({int(reltuples)} dòng < {MIN_TABLE_ROWS}), quét tuần tự trong bộ nhớ đệm nhanh hơn quét chỉ mục.",
                    "table_rows": reltuples,
                    "plan_rows": node_rows,
                })
                continue

            # Nhánh 2: Trích xuất cột điều kiện
            eq_cols, rg_cols, is_non_sargable, rewrite_sugg = cls._extract_candidate_columns(node, valid_cols)
            candidate_cols = eq_cols + [c for c in rg_cols if c not in eq_cols]

            if not candidate_cols:
                skipped.append({
                    "table": rel_name,
                    "reason_code": "NO_FILTER",
                    "explanation": f"Không tìm thấy cột điều kiện lọc/liên kết hợp lệ thuộc bảng `{rel_name}`.",
                    "table_rows": reltuples,
                    "plan_rows": node_rows,
                })
                continue

            # Nhánh 3: Cột ứng viên đầu tiên đã có index dẫn đầu -> ALREADY_INDEXED
            leading_cand = candidate_cols[0]
            indexed_by = None
            for idx_name, lead_col in existing_indexes.items():
                if lead_col == leading_cand:
                    indexed_by = idx_name
                    break

            if indexed_by:
                skipped.append({
                    "table": rel_name,
                    "reason_code": "ALREADY_INDEXED",
                    "explanation": f"Cột `{leading_cand}` đã là cột dẫn đầu của chỉ mục `{indexed_by}` hiện có.",
                    "table_rows": reltuples,
                    "plan_rows": node_rows,
                })
                continue

            # Nhánh 4a: Tìm kiếm chuỗi có ký tự đại diện % ở đầu -> GIN pg_trgm (vẫn tạo được chỉ mục)
            if is_non_sargable and rewrite_sugg and "pg_trgm" in rewrite_sugg:
                trgm_cols = [c for c in candidate_cols if c in valid_cols][:1]
                if trgm_cols:
                    col = trgm_cols[0]
                    idx_name = f"idx_{rel_name}_{col}_trgm"[:63]
                    recommendations.append(cls._make_recommendation(
                        rel_name=rel_name, relkind=relkind, idx_name=idx_name,
                        key_expr=f"{col} gin_trgm_ops", using="gin", where=None,
                        index_type="GIN (pg_trgm)", cols=[col], node_cost=node_cost, node_rows=node_rows,
                        reltuples=reltuples, selectivity=(node_rows / reltuples) if reltuples else 0.0,
                        filter_cond=filter_cond, clean_sql=clean_sql, params=params,
                        prerequisite="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
                        reason=f"Điều kiện ILIKE '%...%' trên `{rel_name}.{col}` không dùng được B-Tree; chỉ mục GIN trigram hỗ trợ tìm chuỗi con.",
                    ))
                    continue

            # Nhánh 4b: Điều kiện non-sargable cần viết lại câu truy vấn
            if is_non_sargable and rewrite_sugg:
                skipped.append({
                    "table": rel_name,
                    "reason_code": "NON_SARGABLE",
                    "explanation": f"Điều kiện trên bảng `{rel_name}` không tối ưu cho chỉ mục thông thường. {rewrite_sugg}",
                    "table_rows": reltuples,
                    "plan_rows": node_rows,
                })
                continue

            # Nhánh 5: Độ chọn lọc > MAX_SELECTIVITY (quét quá nhiều dòng -> Seq Scan hợp lý)
            if reltuples > 0:
                selectivity = node_rows / reltuples
                if selectivity > MAX_SELECTIVITY:
                    skipped.append({
                        "table": rel_name,
                        "reason_code": "LOW_SELECTIVITY",
                        "explanation": f"Độ chọn lọc thấp ({int(node_rows)}/{int(reltuples)} dòng = {selectivity:.1%} > {MAX_SELECTIVITY:.0%}), PostgreSQL quét tuần tự là phương án tối ưu.",
                        "table_rows": reltuples,
                        "plan_rows": node_rows,
                        "selectivity": round(selectivity, 3),
                    })
                    continue
            else:
                selectivity = 0.05

            # Nhánh 6: ĐỦ ĐIỀU KIỆN ĐỀ XUẤT INDEX (A4-3, A4-5)
            jsonb_access = cls._detect_jsonb_access(filter_cond)
            partial = cls._detect_partial_predicate(filter_cond, valid_cols)

            if jsonb_access:
                # 6a. Cột JSONB: GIN cho toán tử @>, chỉ mục biểu thức cho ->> 'khóa'
                jcol = jsonb_access["column"]
                if jsonb_access["kind"] == "containment":
                    key_expr, using, itype = f"{jcol} jsonb_path_ops", "gin", "GIN (jsonb_path_ops)"
                    idx_name = f"idx_{rel_name}_{jcol}_gin"[:63]
                else:
                    jkey = re.sub(r"[^a-zA-Z0-9_]", "", jsonb_access["key"])
                    key_expr, using, itype = f"({jcol} ->> '{jkey}')", "btree", "B-Tree biểu thức JSONB"
                    idx_name = f"idx_{rel_name}_{jcol}_{jkey}"[:63]
                recommendations.append(cls._make_recommendation(
                    rel_name=rel_name, relkind=relkind, idx_name=idx_name, key_expr=key_expr, using=using,
                    where=None, index_type=itype, cols=[jcol], node_cost=node_cost, node_rows=node_rows,
                    reltuples=reltuples, selectivity=selectivity, filter_cond=filter_cond,
                    clean_sql=clean_sql, params=params,
                    reason=f"Truy vấn dữ liệu bán cấu trúc trên cột JSONB `{rel_name}.{jcol}` đang quét tuần tự.",
                ))
                continue

            if partial and len(candidate_cols) > 1:
                # 6b. PARTIAL INDEX: cột ít giá trị đưa vào mệnh đề WHERE, cột còn lại làm khóa chỉ mục
                p_col, p_val = partial
                key_cols = [c for c in candidate_cols if c != p_col][:3]
                where = f"{p_col} = {p_val}"
                idx_name = f"idx_{rel_name}_{'_'.join(key_cols)}_{re.sub(r'[^a-z0-9_]', '', p_val.lower())}"[:63]
                recommendations.append(cls._make_recommendation(
                    rel_name=rel_name, relkind=relkind, idx_name=idx_name, key_expr=", ".join(key_cols),
                    using="btree", where=where, index_type="B-Tree (Partial)", cols=key_cols,
                    node_cost=node_cost, node_rows=node_rows, reltuples=reltuples, selectivity=selectivity,
                    filter_cond=filter_cond, clean_sql=clean_sql, params=params,
                    reason=(f"Điều kiện cố định `{where}` trên cột ít giá trị: chỉ mục một phần nhỏ hơn và "
                            f"nhanh hơn chỉ mục toàn bảng, chỉ chứa các dòng truy vấn thực sự cần."),
                ))
                continue

            # 6c. B-Tree thường / nhiều cột: cột so sánh bằng đứng trước, cột khoảng/sort đứng sau
            final_cols = candidate_cols[:3]
            idx_name = f"idx_{rel_name}_{'_'.join(final_cols)}"[:63]
            recommendations.append(cls._make_recommendation(
                rel_name=rel_name, relkind=relkind, idx_name=idx_name, key_expr=", ".join(final_cols),
                using="btree", where=None,
                index_type="B-Tree nhiều cột (Composite)" if len(final_cols) > 1 else "B-Tree",
                cols=final_cols, node_cost=node_cost, node_rows=node_rows, reltuples=reltuples,
                selectivity=selectivity, filter_cond=filter_cond, clean_sql=clean_sql, params=params,
                reason=f"Phát hiện Seq Scan trên bảng `{rel_name}` thỏa mãn toàn bộ tiêu chí Cây quyết định: chi phí {node_cost:.1f}, độ chọn lọc {selectivity:.1%} < {MAX_SELECTIVITY:.0%}.",
            ))

        needs_index = len(recommendations) > 0

        return {
            "success": True,
            "root_cost": round(root_cost, 2),
            "root_rows": int(root_rows),
            "needs_index": needs_index,
            "status": "CẦN TỐI ƯU HÓA (ĐỀ XUẤT CHỈ MỤC)" if needs_index else "TỐI ƯU / KHÔNG CẦN CHỈ MỤC MỚI",
            "seq_scans_count": len(recommendations) + len(skipped),
            "recommendations": recommendations,
            "skipped": skipped,
            "raw_plan": plan_json,
        }
