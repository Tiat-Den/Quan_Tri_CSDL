"""
MODULE AI 5: DỰ BÁO DUNG LƯỢNG & TỰ ĐỘNG PHÂN VÙNG BẢNG (PREDICTIVE PARTITIONING)
Cải tiến toàn diện theo tài liệu kỹ thuật (A5-1 đến A5-7):
- Gom nhóm theo tháng (không gom ngày tích lũy gây phồng ảo R^2).
- Hồi quy tuyến tính trên số đơn từng tháng riêng biệt, kèm khoảng dự báo tin cậy 95% (±1.96 * SE).
- Backtest đối chứng với Baseline (trung bình trượt 3 tháng gần nhất) và tính MAE, RMSE, MAPE.
- Đo lường dung lượng thật qua pg_total_relation_size và tính byte trung bình/đơn hàng.
- Sinh DDL chính xác: nếu bảng chưa phân vùng (relkind='r') thì sinh migration_plan 5 bước rõ ràng;
  nếu bảng đã phân vùng (relkind='p') mới sinh lệnh PARTITION OF.
- Ghi chú trung thực về quy mô dữ liệu (~8.000 đơn chưa cần phân vùng ngay).
- [Tối ưu] Lấp tháng trống bằng generate_series, loại tháng hiện tại chưa kết thúc.
- [Tối ưu] So sánh 3 mô hình OLS / Holt / Baseline bằng backtest, tự chọn mô hình MAE nhỏ nhất.
- [Tối ưu] Kịch bản "giả sử" (what-if): nhân tốc độ tăng trưởng, đổi ngưỡng phân vùng.
- [Tối ưu] Kế hoạch di chuyển dùng LIKE sao chép đúng cấu trúc bảng thật, sinh phân vùng theo dữ liệu thực.
"""

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app import config
from app.db import execute_query

PARTITION_THRESHOLD_ROWS = getattr(config, "PARTITION_THRESHOLD_ROWS", 1000000)
PARTITION_THRESHOLD_BYTES = getattr(config, "PARTITION_THRESHOLD_BYTES", 1073741824)  # 1 GB
BACKTEST_MONTHS = getattr(config, "BACKTEST_MONTHS", 3)
MIN_MONTHS = getattr(config, "MIN_MONTHS", 4)


class LinearRegressionPredictor:
    """Mô hình Hồi quy tuyến tính OLS: y = a*x + b."""

    def __init__(self):
        self.slope: float = 0.0        # Tốc độ tăng trưởng
        self.intercept: float = 0.0    # Điểm cắt trục tung
        self.r_squared: float = 0.0    # Hệ số xác định R^2
        self.residual_std: float = 0.0 # Độ lệch chuẩn phần dư

    def fit(self, x_vals: List[float], y_vals: List[float]):
        n = len(x_vals)
        if n < 2:
            raise ValueError("Cần ít nhất 2 điểm dữ liệu để hồi quy.")

        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n

        cov_xy = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(n))
        var_x = sum((x_vals[i] - mean_x) ** 2 for i in range(n))

        if var_x == 0:
            self.slope = 0.0
            self.intercept = mean_y
            self.r_squared = 0.0
            self.residual_std = 0.0
            return

        self.slope = cov_xy / var_x
        self.intercept = mean_y - self.slope * mean_x

        # Tính R^2 và Residual Standard Error
        ss_tot = sum((y - mean_y) ** 2 for y in y_vals)
        ss_res = sum((y_vals[i] - (self.slope * x_vals[i] + self.intercept)) ** 2 for i in range(n))
        self.r_squared = max(1.0 - (ss_res / ss_tot), 0.0) if ss_tot != 0 else 1.0
        self.residual_std = math.sqrt(ss_res / max(n - 2, 1))

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


class HoltLinearPredictor:
    """
    Làm trơn hàm mũ kép Holt (Holt's Linear Trend): mức (level) + xu hướng (trend) được cập nhật
    theo trọng số alpha/beta, phản ứng nhanh hơn hồi quy tuyến tính khi tốc độ tăng trưởng thay đổi.
    alpha, beta được chọn bằng Grid Search tối thiểu hóa sai số dự báo một bước (SSE).
    """

    def __init__(self):
        self.alpha = 0.5
        self.beta = 0.3
        self.level = 0.0
        self.trend = 0.0
        self.residual_std = 0.0

    @staticmethod
    def _run(y: List[float], alpha: float, beta: float) -> Tuple[float, float, float, List[float]]:
        level, trend = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
        sse, errors = 0.0, []
        for t in range(1, len(y)):
            pred = level + trend
            err = y[t] - pred
            errors.append(err)
            sse += err * err
            new_level = alpha * y[t] + (1 - alpha) * (level + trend)
            trend = beta * (new_level - level) + (1 - beta) * trend
            level = new_level
        return level, trend, sse, errors

    def fit(self, y_vals: List[float]):
        if len(y_vals) < 3:
            raise ValueError("Cần ít nhất 3 điểm dữ liệu cho mô hình Holt.")
        best = None
        grid = [i / 10 for i in range(1, 10)]
        for a in grid:
            for b in grid:
                level, trend, sse, errors = self._run(y_vals, a, b)
                if best is None or sse < best[0]:
                    best = (sse, a, b, level, trend, errors)
        _, self.alpha, self.beta, self.level, self.trend, errors = best
        n = len(errors)
        self.residual_std = math.sqrt(sum(e * e for e in errors) / max(n - 2, 1)) if n else 0.0

    def forecast(self, steps_ahead: int) -> float:
        return self.level + steps_ahead * self.trend


def _metrics(preds: List[float], actual: List[float]) -> Dict[str, float]:
    k = len(actual)
    mae = sum(abs(preds[i] - actual[i]) for i in range(k)) / k
    rmse = math.sqrt(sum((preds[i] - actual[i]) ** 2 for i in range(k)) / k)
    mape = sum(abs((preds[i] - actual[i]) / max(actual[i], 1.0)) for i in range(k)) / k * 100
    return {"mae": mae, "rmse": rmse, "mape": mape}


def forecast_series(order_counts: List[float], horizon: int = 3, backtest_months: int = BACKTEST_MONTHS) -> Dict[str, Any]:
    """
    So sánh 3 mô hình trên chuỗi số đơn theo tháng bằng BACKTEST (giữ lại k tháng cuối làm tập kiểm tra):
      - OLS  : hồi quy tuyến tính y = a*x + b
      - HOLT : làm trơn hàm mũ kép (mức + xu hướng)
      - NAIVE: trung bình trượt 3 tháng (baseline đối chứng)
    Chọn mô hình có MAE nhỏ nhất, huấn luyện lại trên toàn bộ dữ liệu và dự báo `horizon` tháng tới.
    Hàm thuần (không cần CSDL) để kiểm thử độc lập.
    """
    n = len(order_counts)
    k = min(backtest_months, max(1, n - 3))
    train, test = order_counts[:-k], order_counts[-k:]

    candidates: Dict[str, Dict[str, Any]] = {}

    ols = LinearRegressionPredictor()
    ols.fit(list(range(len(train))), train)
    candidates["OLS"] = _metrics([max(0.0, ols.predict(len(train) + i)) for i in range(k)], test)

    if len(train) >= 3:
        holt = HoltLinearPredictor()
        holt.fit(train)
        candidates["HOLT"] = _metrics([max(0.0, holt.forecast(i + 1)) for i in range(k)], test)

    base_val = sum(train[-3:]) / min(len(train), 3)
    candidates["NAIVE"] = _metrics([base_val] * k, test)

    best_name = min(candidates, key=lambda m: candidates[m]["mae"])

    # Huấn luyện lại mô hình thắng trên toàn bộ chuỗi
    full_ols = LinearRegressionPredictor()
    full_ols.fit(list(range(n)), order_counts)
    if best_name == "HOLT":
        model = HoltLinearPredictor()
        model.fit(order_counts)
        preds = [max(0.0, model.forecast(i)) for i in range(1, horizon + 1)]
        resid_std = model.residual_std
    elif best_name == "NAIVE":
        val = sum(order_counts[-3:]) / min(n, 3)
        preds = [val] * horizon
        diffs = [order_counts[i] - sum(order_counts[max(0, i - 3):i]) / max(1, min(3, i)) for i in range(1, n)]
        resid_std = math.sqrt(sum(d * d for d in diffs) / max(len(diffs) - 1, 1)) if diffs else 0.0
    else:
        preds = [max(0.0, full_ols.predict(n - 1 + i)) for i in range(1, horizon + 1)]
        resid_std = full_ols.residual_std

    return {
        "best_model": best_name,
        "backtest_months": k,
        "comparison": {m: {kk: round(v, 1) for kk, v in mt.items()} for m, mt in candidates.items()},
        "predictions": preds,
        "residual_std": resid_std,
        "ols": full_ols,
        "beats_baseline": candidates[best_name]["mae"] <= candidates["NAIVE"]["mae"],
    }


class AIPredictivePartitioningEngine:
    """
    Module AI Dự báo Tăng trưởng dữ liệu và Phân vùng Bảng CSDL (A5-1 đến A5-7).
    """

    @classmethod
    def analyze_and_forecast(
        cls,
        growth_multiplier: float = 1.0,
        threshold_rows: Optional[int] = None,
        threshold_bytes: Optional[int] = None,
        horizon: int = 3,
    ) -> Dict[str, Any]:
        """
        Phân tích dữ liệu lịch sử đơn hàng theo tháng, đo lường dung lượng thật và lập kế hoạch phân vùng.

        Tham số "giả sử" (what-if) phục vụ demo và lập kế hoạch:
          - growth_multiplier: nhân tốc độ đơn hàng dự báo (vd 50 = cửa hàng mở rộng gấp 50 lần).
          - threshold_rows / threshold_bytes: ngưỡng quyết định phân vùng thay cho cấu hình mặc định.
        """
        thr_rows = int(threshold_rows) if threshold_rows else PARTITION_THRESHOLD_ROWS
        thr_bytes = int(threshold_bytes) if threshold_bytes else PARTITION_THRESHOLD_BYTES
        growth_multiplier = max(float(growth_multiplier or 1.0), 0.01)

        # 1. Chuỗi thời gian theo tháng ĐẦY ĐỦ (A5-1):
        #    - generate_series lấp các tháng không có đơn bằng 0 (GROUP BY thường bỏ sót tháng trống).
        #    - Loại tháng hiện tại chưa kết thúc (số đơn dở dang kéo lệch xu hướng xuống).
        sql = """
        WITH bounds AS (
            SELECT date_trunc('month', MIN(ngay_dat)) AS m_start,
                   LEAST(date_trunc('month', MAX(ngay_dat)),
                         date_trunc('month', NOW()) - INTERVAL '1 month') AS m_end
            FROM "LinhKien".don_hang
        ),
        months AS (
            SELECT generate_series(b.m_start, b.m_end, INTERVAL '1 month') AS m
            FROM bounds b
            WHERE b.m_start IS NOT NULL AND b.m_end >= b.m_start
        )
        SELECT TO_CHAR(m.m, 'YYYY-MM') AS thang,
               COUNT(d.id) AS so_don
        FROM months m
        LEFT JOIN "LinhKien".don_hang d
               ON d.ngay_dat >= m.m AND d.ngay_dat < m.m + INTERVAL '1 month'
        GROUP BY m.m
        ORDER BY m.m ASC;
        """
        res = execute_query(sql)
        if not res["success"] or not res["data"]:
            return {"success": False, "error": "Không thể nạp dữ liệu thống kê đơn hàng từ CSDL."}

        raw_monthly = res["data"]
        if len(raw_monthly) < MIN_MONTHS:
            return {
                "success": False,
                "error": f"Dữ liệu lịch sử có {len(raw_monthly)} tháng, chưa đủ ngưỡng tối thiểu ({MIN_MONTHS} tháng) để huấn luyện mô hình dự báo chuỗi thời gian.",
            }

        month_labels = [r["thang"] for r in raw_monthly]
        order_counts = [float(r["so_don"]) for r in raw_monthly]
        n_months = len(order_counts)
        empty_months = [month_labels[i] for i, c in enumerate(order_counts) if c == 0]

        # 2-3. Backtest so sánh OLS / Holt / Baseline, chọn mô hình tốt nhất (A5-2, A5-3)
        fc = forecast_series(order_counts, horizon=horizon)
        model = fc["ols"]
        cmp = fc["comparison"]
        mae_model = cmp[fc["best_model"]]["mae"]
        rmse_model = cmp[fc["best_model"]]["rmse"]
        mape_model = cmp[fc["best_model"]]["mape"]
        mae_baseline = cmp["NAIVE"]["mae"]
        beats_baseline = fc["beats_baseline"]

        # 4. Dự báo các tháng tiếp theo (kèm khoảng tin cậy 95%) và kịch bản "giả sử"
        last_dt = datetime.strptime(month_labels[-1], "%Y-%m")
        forecast_months = []
        margin = 1.96 * fc["residual_std"]
        for i in range(1, horizon + 1):
            m_year = last_dt.year + ((last_dt.month - 1 + i) // 12)
            m_month = ((last_dt.month - 1 + i) % 12) + 1
            future_label = f"{m_year:04d}-{m_month:02d}"
            base_pred = fc["predictions"][i - 1]
            pred_val = max(0, int(round(base_pred * growth_multiplier)))
            lower_bound = max(0, int(round((base_pred - margin) * growth_multiplier)))
            upper_bound = int(round((base_pred + margin) * growth_multiplier))
            forecast_months.append({
                "thang": future_label,
                "don_du_bao": pred_val,
                "khoang_tin_cay_95": f"[{lower_bound:,} - {upper_bound:,}]",
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            })

        # 5. Đo lường dung lượng thật và ước tính ngày chạm ngưỡng (A5-4)
        sql_size = """
        SELECT 
            pg_total_relation_size('"LinhKien".don_hang') AS don_hang_bytes,
            pg_total_relation_size('"LinhKien".chi_tiet_don_hang') AS ctdh_bytes,
            pg_total_relation_size('"LinhKien".thanh_toan') AS thanh_toan_bytes,
            COUNT(*) AS tong_don_hang
        FROM "LinhKien".don_hang;
        """
        res_size = execute_query(sql_size)
        total_orders = sum(order_counts)
        total_cluster_bytes = 0

        if res_size["success"] and res_size["data"]:
            s_row = res_size["data"][0]
            dh_bytes = int(s_row.get("don_hang_bytes", 0))
            ctdh_bytes = int(s_row.get("ctdh_bytes", 0))
            tt_bytes = int(s_row.get("thanh_toan_bytes", 0))
            total_cluster_bytes = dh_bytes + ctdh_bytes + tt_bytes
            total_orders = int(s_row.get("tong_don_hang", total_orders))

        bytes_per_order = total_cluster_bytes / max(total_orders, 1)

        # Tính tốc độ tăng trưởng dự kiến theo ngày
        avg_monthly_forecast = sum(f["don_du_bao"] for f in forecast_months) / len(forecast_months)
        daily_order_rate = avg_monthly_forecast / 30.5

        remaining_rows = max(thr_rows - total_orders, 0)
        remaining_bytes = max(thr_bytes - total_cluster_bytes, 0)

        if daily_order_rate > 0:
            days_by_rows = remaining_rows / daily_order_rate
            daily_byte_rate = daily_order_rate * bytes_per_order
            days_by_bytes = remaining_bytes / max(daily_byte_rate, 1.0)
            days_until_threshold = min(days_by_rows, days_by_bytes)
        else:
            days_until_threshold = 9999.0

        if days_until_threshold < 90:
            recommendation = "PARTITION_SOON"
            rec_label = "CẦN PHÂN VÙNG SỚM (< 3 THÁNG)"
        elif days_until_threshold < 365:
            recommendation = "MONITOR"
            rec_label = "THEO DÕI ĐỊNH KỲ (< 1 NĂM)"
        else:
            recommendation = "NOT_NEEDED"
            rec_label = "CHƯA CẦN PHÂN VÙNG (DUNG LƯỢNG AN TOÀN)"

        # 6. Kiểm tra trạng thái phân vùng thực tế (relkind) và sinh DDL (A5-5)
        sql_relkind = """
        SELECT c.relkind 
        FROM pg_class c 
        JOIN pg_namespace n ON n.oid = c.relnamespace 
        WHERE n.nspname = 'LinhKien' AND c.relname = 'don_hang';
        """
        res_relkind = execute_query(sql_relkind)
        relkind = "r"
        if res_relkind["success"] and res_relkind["data"]:
            relkind = str(res_relkind["data"][0].get("relkind", "r"))

        is_partitioned = (relkind == "p")
        generated_ddl = []
        migration_plan = []

        if is_partitioned:
            # Nếu bảng đã phân vùng -> Sinh câu lệnh PARTITION OF cho các tháng tương lai
            for f in forecast_months:
                t_label = f["thang"]
                dt_start = datetime.strptime(t_label, "%Y-%m")
                m_next_y = dt_start.year + (dt_start.month // 12)
                m_next_m = (dt_start.month % 12) + 1
                dt_end_str = f"{m_next_y:04d}-{m_next_m:02d}-01"
                part_name = f"don_hang_{t_label.replace('-', '_')}"
                generated_ddl.append(
                    f'CREATE TABLE IF NOT EXISTS "LinhKien".{part_name} '
                    f'PARTITION OF "LinhKien".don_hang '
                    f"FOR VALUES FROM ('{t_label}-01') TO ('{dt_end_str}');"
                )
        else:
            # Nếu bảng chưa phân vùng (relkind='r') -> Không sinh PARTITION OF mà sinh kế hoạch di chuyển 5 bước
            # Danh sách phân vùng: từ tháng đầu tiên có dữ liệu đến hết các tháng dự báo
            first_dt = datetime.strptime(month_labels[0], "%Y-%m")
            last_fc = datetime.strptime(forecast_months[-1]["thang"], "%Y-%m")
            part_lines = []
            cur_y, cur_m = first_dt.year, first_dt.month
            while (cur_y, cur_m) <= (last_fc.year, last_fc.month):
                nxt_y, nxt_m = (cur_y + 1, 1) if cur_m == 12 else (cur_y, cur_m + 1)
                part_lines.append(
                    f'CREATE TABLE "LinhKien".don_hang_y{cur_y}m{cur_m:02d} PARTITION OF "LinhKien".don_hang_partitioned\n'
                    f"    FOR VALUES FROM ('{cur_y}-{cur_m:02d}-01') TO ('{nxt_y}-{nxt_m:02d}-01');"
                )
                cur_y, cur_m = nxt_y, nxt_m
            part_lines.append('CREATE TABLE "LinhKien".don_hang_default PARTITION OF "LinhKien".don_hang_partitioned DEFAULT;')

            # Nếu bảng chưa phân vùng (relkind='r') -> sinh kế hoạch di chuyển, KHÔNG sinh PARTITION OF
            migration_plan = [
                {
                    "step": 1,
                    "title": "Tạo bảng cha phân vùng mới với cấu trúc GIỐNG HỆT bảng don_hang hiện tại",
                    "sql": """CREATE TABLE "LinhKien".don_hang_partitioned (
    LIKE "LinhKien".don_hang INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING COMMENTS
) PARTITION BY RANGE (ngay_dat);

ALTER TABLE "LinhKien".don_hang_partitioned ADD PRIMARY KEY (id, ngay_dat);""",
                    "note": "Dùng LIKE để sao chép đúng cột, kiểu dữ liệu, DEFAULT và ràng buộc CHECK (trang_thai, kenh_ban). "
                            "Khóa chính của bảng phân vùng bắt buộc chứa cột khóa phân vùng `ngay_dat`.",
                },
                {
                    "step": 2,
                    "title": f"Tạo {len(part_lines) - 1} phân vùng theo tháng (dữ liệu lịch sử + {horizon} tháng dự báo) và phân vùng DEFAULT",
                    "sql": "\n".join(part_lines),
                    "note": "Phân vùng DEFAULT đảm bảo đơn hàng ngoài khoảng đã tạo không gây lỗi INSERT.",
                },
                {
                    "step": 3,
                    "title": "Chuyển dữ liệu lịch sử, đồng bộ sequence và nạp thống kê",
                    "sql": """INSERT INTO "LinhKien".don_hang_partitioned SELECT * FROM "LinhKien".don_hang;

ANALYZE "LinhKien".don_hang_partitioned;""",
                    "note": "Hai bảng có cùng thứ tự cột (nhờ LIKE) nên SELECT * khớp; mỗi dòng tự rơi vào đúng phân vùng.",
                },
                {
                    "step": 4,
                    "title": "Xử lý khóa ngoại, trigger và chính sách RLS đang gắn với don_hang",
                    "sql": """-- (a) Khóa ngoại: chi_tiet_don_hang và thanh_toan đang tham chiếu don_hang(id).
--     Bảng phân vùng chỉ nhận FK tham chiếu tới khóa chính đầy đủ (id, ngay_dat):
ALTER TABLE "LinhKien".chi_tiet_don_hang DROP CONSTRAINT IF EXISTS chi_tiet_don_hang_don_hang_id_fkey;
ALTER TABLE "LinhKien".thanh_toan        DROP CONSTRAINT IF EXISTS thanh_toan_don_hang_id_fkey;
--     -> Thêm cột ngay_dat vào 2 bảng con để tạo FK tổ hợp, hoặc kiểm tra tồn tại bằng trigger.

-- (b) Tạo lại các trigger nghiệp vụ trên bảng mới (fn_tru_ton_kho_khi_giao, trg_order_anomaly_notify...).

-- (c) Bật lại Row-Level Security và chính sách cho nhân viên bán hàng:
ALTER TABLE "LinhKien".don_hang_partitioned ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_don_hang_nhan_vien ON "LinhKien".don_hang_partitioned FOR SELECT TO nhan_vien_ban_hang
    USING (nhan_vien_id = "LinhKien".fn_nhan_vien_cua_role(current_user));
CREATE POLICY p_don_hang_doc_toan_bo ON "LinhKien".don_hang_partitioned FOR SELECT
    TO text2sql_readonly, manager_readonly USING (true);

-- (d) Cấp lại quyền đọc cho các role:
GRANT SELECT ON "LinhKien".don_hang_partitioned TO text2sql_readonly, manager_readonly;""",
                    "note": "CẢNH BÁO: trigger, chính sách RLS và quyền GRANT không tự chuyển sang bảng mới; bỏ sót bước này sẽ làm mất bảo mật mức dòng.",
                },
                {
                    "step": 5,
                    "title": "Hoán đổi bảng nguyên tử (Atomic Table Swap)",
                    "sql": """BEGIN;
LOCK TABLE "LinhKien".don_hang IN ACCESS EXCLUSIVE MODE;
-- Chép các đơn phát sinh trong lúc di chuyển (nếu có)
INSERT INTO "LinhKien".don_hang_partitioned
SELECT * FROM "LinhKien".don_hang d
WHERE NOT EXISTS (SELECT 1 FROM "LinhKien".don_hang_partitioned p WHERE p.id = d.id AND p.ngay_dat = d.ngay_dat);
ALTER TABLE "LinhKien".don_hang RENAME TO don_hang_legacy_backup;
ALTER TABLE "LinhKien".don_hang_partitioned RENAME TO don_hang;
ALTER SEQUENCE "LinhKien".don_hang_id_seq OWNED BY "LinhKien".don_hang.id;
COMMIT;""",
                    "note": "Khóa bảng cũ trong thời gian rất ngắn để không mất đơn phát sinh giữa chừng; giữ bảng legacy làm bản dự phòng.",
                },
            ]

        return {
            "success": True,
            "total_orders": total_orders,
            "cluster_size_bytes": total_cluster_bytes,
            "cluster_size_mb": round(total_cluster_bytes / (1024 * 1024), 2),
            "bytes_per_order": round(bytes_per_order, 1),
            "historical_months": month_labels,
            "historical_counts": [int(c) for c in order_counts],
            "forecast_months": forecast_months,
            "model_metrics": {
                "slope": round(model.slope, 2),
                "intercept": round(model.intercept, 2),
                "r_squared": round(model.r_squared, 3),
                "r_squared_note": (
                    f"R² = {model.r_squared:.3f} của đường hồi quy OLS trên số đơn từng tháng. "
                    + ("R² thấp nghĩa là số đơn mỗi tháng gần như đi ngang, không có xu hướng tăng/giảm rõ; "
                       if model.r_squared < 0.3 else "R² cao nghĩa là số đơn có xu hướng rõ theo thời gian; ")
                    + "mô hình dự báo được chọn theo sai số backtest (MAE), không theo R²."
                ),
                "backtest_mae": round(mae_model, 1),
                "backtest_rmse": round(rmse_model, 1),
                "backtest_mape": f"{mape_model:.1f}%",
                "baseline_mae": round(mae_baseline, 1),
                "beats_baseline": beats_baseline,
                "best_model": fc["best_model"],
                "model_comparison": cmp,
                "backtest_months": fc["backtest_months"],
            },
            "data_quality": {
                "months_used": n_months,
                "empty_months_filled": empty_months,
                "excluded_current_month": True,
            },
            "what_if": {
                "growth_multiplier": growth_multiplier,
                "threshold_rows": thr_rows,
                "threshold_bytes": thr_bytes,
            },
            "capacity_assessment": {
                "threshold_rows": thr_rows,
                "threshold_bytes_mb": round(thr_bytes / (1024 * 1024), 0),
                "days_until_threshold": round(days_until_threshold, 1) if days_until_threshold < 3650 else "> 10 năm",
                "recommendation": recommendation,
                "rec_label": rec_label,
            },
            "is_partitioned": is_partitioned,
            "generated_ddl": generated_ddl,
            "migration_plan": migration_plan,
        }
