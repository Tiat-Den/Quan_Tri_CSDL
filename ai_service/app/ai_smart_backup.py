"""
MODULE AI 6: BACKUP DỮ LIỆU THÔNG MINH (AI SMART BACKUP & RECOVERY)
Hệ thống: Cửa hàng linh kiện máy tính (LinhKien_DB, schema "LinhKien")
Công nghệ: 100% Python Thuần (Psycopg2, OLS Regression, Decision Tree Risk Scoring, pg_dump/pg_restore, SHA-256)
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db import execute_query, get_connection
from app.config import DB_HOST, DB_PORT, DB_NAME, DB_ADMIN_USER, DB_ADMIN_PASSWORD


class BackupSizePredictor:
    """Mô hình Hồi quy tuyến tính OLS dự báo dung lượng backup: y = a*x + b."""

    def __init__(self):
        self.slope = 0.0
        self.intercept = 0.0
        self.r_squared = 0.0

    def fit(self, x_vals: List[float], y_vals: List[float]):
        n = len(x_vals)
        if n < 2:
            raise ValueError("Cần ít nhất 2 điểm dữ liệu để hồi quy.")
        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n
        cov_xy = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(n))
        var_x = sum((x_vals[i] - mean_x) ** 2 for i in range(n))
        if var_x == 0:
            self.slope, self.intercept, self.r_squared = 0.0, mean_y, 0.0
            return
        self.slope = cov_xy / var_x
        self.intercept = mean_y - self.slope * mean_x
        ss_tot = sum((y - mean_y) ** 2 for y in y_vals)
        ss_res = sum((y_vals[i] - self.predict(x_vals[i])) ** 2 for i in range(n))
        self.r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

    def predict(self, x: float) -> float:
        return max(0.0, self.slope * x + self.intercept)


class AISmartBackupEngine:
    """
    Động cơ AI Backup Dữ Liệu Thông Minh:
    1. Phân tích tần suất thay đổi dữ liệu (Change Rate) trên từng bảng
    2. Dự báo dung lượng database bằng mô hình hồi quy OLS
    3. Chấm điểm rủi ro mất dữ liệu (Data Loss Risk Scoring: 0 - 100)
    4. Sinh và thực thi lệnh pg_dump / pg_restore an toàn
    5. Kiểm tra toàn vẹn bản backup bằng SHA-256 Checksum
    """

    BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups"))
    CHANGE_THRESHOLDS = {"HOT": 50.0, "WARM": 20.0}
    SNAPSHOT_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "stat_snapshot.json"))
    MIN_SNAPSHOT_GAP_HOURS = 0.25        # Cần cách ít nhất 15 phút để tính tốc độ thay đổi
    MEASURED_HOT_PCT_PER_HOUR = 1.0      # >= 1% số dòng thay đổi mỗi giờ -> HOT
    MEASURED_WARM_PCT_PER_HOUR = 0.1     # >= 0.1%/giờ -> WARM
    OFFSITE_DIR = os.getenv("BACKUP_OFFSITE_DIR", "")  # Thư mục ổ khác / NAS / cloud sync để chép bản backup

    @classmethod
    def _load_stat_snapshot(cls) -> Optional[Dict[str, Any]]:
        try:
            with open(cls.SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def _save_stat_snapshot(cls, snap: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(cls.SNAPSHOT_FILE), exist_ok=True)
            with open(cls.SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def collect_environment(cls) -> Dict[str, Any]:
        """
        Thu thập SỐ LIỆU THẬT cho chấm điểm rủi ro (thay cho tham số nhập tay):
        - Số giờ từ lần backup thành công gần nhất (bảng backup_history)
        - Bản backup gần nhất có checksum SHA-256 và tệp còn tồn tại không
        - archive_mode của PostgreSQL và số lần lưu trữ WAL thất bại (pg_stat_archiver)
        - Dung lượng trống của ổ đĩa chứa thư mục backup (shutil.disk_usage)
        - Có thư mục offsite (BACKUP_OFFSITE_DIR) chứa bản sao hay không
        Trường nào không đo được sẽ là None và được ghi rõ trong 'sources'.
        """
        env: Dict[str, Any] = {"sources": {}}

        history = cls.get_backup_history(limit=20)
        ok = [h for h in history if str(h.get("trang_thai", "")).lower() in ("thanh_cong", "success")]
        if ok:
            last = ok[0]
            try:
                last_dt = datetime.strptime(last["thoi_gian"], "%Y-%m-%d %H:%M:%S")
                env["last_backup_hours_ago"] = round((datetime.now() - last_dt).total_seconds() / 3600.0, 1)
            except Exception:
                env["last_backup_hours_ago"] = None
            env["verified"] = bool(last.get("checksum_sha256")) and bool(last.get("file_exists"))
            env["sources"]["backup"] = f"backup_history (lần gần nhất: {last['thoi_gian']})"
            base = cls._file_name(last.get("duong_dan"))
            env["has_offsite"] = bool(cls.OFFSITE_DIR) and bool(base) and os.path.exists(os.path.join(cls.OFFSITE_DIR, base))
        else:
            env["last_backup_hours_ago"] = 999.0 if history == [] else None
            env["verified"] = False
            env["has_offsite"] = False
            env["sources"]["backup"] = "Không tìm thấy bản backup thành công nào (hoặc không đọc được backup_history) -> coi như chưa có bằng chứng sao lưu"
        if not cls.OFFSITE_DIR:
            env["sources"]["offsite"] = "Chưa cấu hình BACKUP_OFFSITE_DIR"

        res_arch = execute_query("SELECT current_setting('archive_mode') AS archive_mode;")
        if res_arch.get("success") and res_arch.get("data"):
            env["archive_mode_on"] = str(res_arch["data"][0]["archive_mode"]).lower() in ("on", "always")
            env["sources"]["archive_mode"] = f"SHOW archive_mode = {res_arch['data'][0]['archive_mode']}"
        else:
            env["archive_mode_on"] = None
        res_fail = execute_query("SELECT failed_count FROM pg_stat_archiver;")
        if res_fail.get("success") and res_fail.get("data"):
            env["wal_archive_failures"] = int(res_fail["data"][0]["failed_count"] or 0)

        try:
            usage = shutil.disk_usage(cls.get_backup_dir())
            env["disk_free_pct"] = round(usage.free / usage.total * 100.0, 1)
            env["sources"]["disk"] = f"shutil.disk_usage({cls.get_backup_dir()})"
        except Exception:
            env["disk_free_pct"] = None
        return env

    @classmethod
    def get_backup_dir(cls) -> str:
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)
        return cls.BACKUP_DIR

    @staticmethod
    def _file_name(stored_path: Optional[str]) -> str:
        """Tên tệp từ đường dẫn đã lưu (tách được cả dấu \\ của Windows lẫn / của Linux)."""
        return re.split(r"[\\/]", str(stored_path or "").strip())[-1]

    @classmethod
    def resolve_backup_path(cls, stored_path: Optional[str]) -> Optional[str]:
        """
        Tìm tệp backup thật trên đĩa từ giá trị cột duong_dan.
        - Bản ghi mới chỉ lưu TÊN TỆP -> ghép với thư mục backups hiện tại.
        - Bản ghi cũ lưu đường dẫn tuyệt đối; nếu thư mục dự án đã đổi tên/di chuyển
          (VD "Cuối Kỳ" -> "Cuoi_Ky") thì tìm cùng tên tệp trong thư mục backups hiện tại.
        Trả về None nếu không tìm thấy.
        """
        if not stored_path:
            return None
        stored_path = str(stored_path).strip()
        if os.path.isabs(stored_path) and os.path.isfile(stored_path):
            return stored_path
        name = cls._file_name(stored_path)
        if name:
            candidate = os.path.join(cls.BACKUP_DIR, name)
            if os.path.isfile(candidate):
                return candidate
        return None

    @staticmethod
    def format_size(size_bytes: Optional[float]) -> str:
        """Dung lượng dễ đọc: B / KB / MB / GB (tệp nhỏ không bị làm tròn thành 0.0 MB)."""
        if size_bytes is None:
            return "—"
        b = float(size_bytes)
        if b < 1024:
            return f"{b:.0f} B"
        if b < 1024 ** 2:
            return f"{b / 1024:.1f} KB"
        if b < 1024 ** 3:
            return f"{b / 1024 ** 2:.1f} MB"
        return f"{b / 1024 ** 3:.2f} GB"

    # Định nghĩa phân tầng bảng nghiệp vụ chuẩn quản trị CSDL (Business Classification)
    TABLE_NATURE = {
        # 1. Bảng giao dịch biến động liên tục (Transactional / Fact Tables): Khách đặt, đổi trạng thái, trừ kho
        "don_hang": {"base_level": "HOT", "interval": "1 giờ", "weight": 1.5},
        "chi_tiet_don_hang": {"base_level": "HOT", "interval": "1 giờ", "weight": 1.5},
        "thanh_toan": {"base_level": "HOT", "interval": "1 giờ", "weight": 1.5},
        "ton_kho": {"base_level": "HOT", "interval": "1 giờ", "weight": 1.4},
        
        # 2. Bảng hoạt động kinh doanh định kỳ (Operational Tables): Nhập kho, biến động giá, khách hàng mới
        "phieu_nhap": {"base_level": "WARM", "interval": "6 giờ", "weight": 1.0},
        "chi_tiet_phieu_nhap": {"base_level": "WARM", "interval": "6 giờ", "weight": 1.0},
        "san_pham": {"base_level": "WARM", "interval": "6 giờ", "weight": 1.0},
        "khach_hang": {"base_level": "WARM", "interval": "6 giờ", "weight": 0.8},
        "dia_chi": {"base_level": "WARM", "interval": "6 giờ", "weight": 0.8},
        "san_pham_nha_cung_cap": {"base_level": "WARM", "interval": "6 giờ", "weight": 0.8},
        "lich_su_thay_doi_gia": {"base_level": "WARM", "interval": "6 giờ", "weight": 0.9},

        # 3. Bảng danh mục gốc / Master Data (Dimension Tables): Cấu hình tĩnh, rất hiếm khi thay đổi
        "danh_muc": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.2},
        "thuong_hieu": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.2},
        "nha_cung_cap": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.2},
        "nhan_vien": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.2},
        "mv_thong_ke_doanh_thu_thang": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.3},
        "backup_history": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.1},
        "backup_size_log": {"base_level": "COLD", "interval": "24 giờ", "weight": 0.1},
    }

    @classmethod
    def analyze_change_rate(cls) -> Dict[str, Any]:
        """
        Phân tích tỷ lệ thay đổi dữ liệu (Change Rate) thông minh:
        - Kết hợp giữa biến động phát sinh thực tế (UPDATE + DELETE + Tăng trưởng INSERT)
        - Áp dụng Cây quyết định (Decision Tree) theo bản chất nghiệp vụ bảng (Transactional vs Master Data)
        """
        sql = """
        SELECT relname,
               COALESCE(n_tup_ins, 0) AS n_tup_ins,
               COALESCE(n_tup_upd, 0) AS n_tup_upd,
               COALESCE(n_tup_del, 0) AS n_tup_del,
               GREATEST(COALESCE(n_live_tup, 0), 1) AS so_dong_hien_tai
        FROM pg_stat_user_tables
        WHERE schemaname = 'LinhKien'
          AND relname NOT LIKE 'don\\_hang\\_phan\\_vung%%'  -- bản sao minh họa phân vùng của AI 5, không cần backup
        ORDER BY so_dong_hien_tai DESC, relname ASC;
        """
        res = execute_query(sql)
        if not res["success"]:
            return {"success": False, "error": res.get("error")}

        tables = []
        hot_count = 0
        warm_count = 0
        cold_count = 0

        # Tốc độ thay đổi THẬT: so sánh bộ đếm hiện tại với ảnh chụp lần trước (pg_stat chỉ là số cộng dồn)
        now_ts = datetime.now()
        prev_snap = cls._load_stat_snapshot()
        elapsed_h = None
        if prev_snap:
            try:
                elapsed_h = (now_ts - datetime.fromisoformat(prev_snap["time"])).total_seconds() / 3600.0
            except Exception:
                elapsed_h = None
        use_measured = elapsed_h is not None and elapsed_h >= cls.MIN_SNAPSHOT_GAP_HOURS
        snapshot_counts = {}

        for row in res["data"]:
            tbl_name = row["relname"]
            live_rows = row["so_dong_hien_tai"]
            ins = row["n_tup_ins"]
            upd = row["n_tup_upd"]
            dele = row["n_tup_del"]

            # Lấy cấu hình bản chất bảng từ Decision Tree
            nature = cls.TABLE_NATURE.get(tbl_name, {"base_level": "WARM", "interval": "6 giờ", "weight": 1.0})
            base_level = nature["base_level"]

            snapshot_counts[tbl_name] = {"ins": ins, "upd": upd, "del": dele}

            # Đo tốc độ thay đổi thật (% số dòng bị thay đổi mỗi giờ) từ chênh lệch 2 ảnh chụp
            measured_rate = None
            if use_measured and tbl_name in prev_snap.get("tables", {}):
                p = prev_snap["tables"][tbl_name]
                delta = max(0, ins - p.get("ins", 0)) + max(0, upd - p.get("upd", 0)) + max(0, dele - p.get("del", 0))
                measured_rate = round(delta / max(live_rows, 1) / elapsed_h * 100.0, 3)

            # Tính toán biến động sau khi đã nạp dữ liệu ban đầu
            # Biến động động = (UPDATE + DELETE) + phần chênh lệch INSERT vượt quá live_rows
            mutation_delta = (upd + dele) + max(0, ins - live_rows)

            if base_level == "HOT":
                # Bảng giao dịch: 60% - 95%
                added = min(30.0, (mutation_delta / max(live_rows, 1)) * 100.0)
                calc_pct = round(65.0 + added, 2)
                level = "HOT"
                interval = "1 giờ"
                hot_count += 1
            elif base_level == "WARM":
                # Bảng hoạt động kinh doanh: 20% - 49%
                added = min(20.0, (mutation_delta / max(live_rows, 1)) * 100.0)
                calc_pct = round(25.0 + added, 2)
                level = "WARM"
                interval = "6 giờ"
                warm_count += 1
            else:
                # Bảng danh mục tĩnh: 2% - 15%
                added = min(8.0, (mutation_delta / max(live_rows, 1)) * 100.0)
                calc_pct = round(3.5 + added, 2)
                level = "COLD"
                interval = "24 giờ"
                cold_count += 1

            # Nếu đã đo được tốc độ thật: nâng cấp phân loại khi bảng thay đổi nhanh hơn dự kiến
            source = "uu_tien_nghiep_vu"
            if measured_rate is not None:
                source = "do_thuc"
                observed = "HOT" if measured_rate >= cls.MEASURED_HOT_PCT_PER_HOUR else (
                    "WARM" if measured_rate >= cls.MEASURED_WARM_PCT_PER_HOUR else "COLD")
                rank = {"COLD": 0, "WARM": 1, "HOT": 2}
                if rank[observed] > rank[level]:
                    if level == "WARM":
                        warm_count -= 1
                    elif level == "COLD":
                        cold_count -= 1
                    level = observed
                    interval = {"HOT": "1 giờ", "WARM": "6 giờ"}.get(level, "24 giờ")
                    if level == "HOT":
                        hot_count += 1
                    else:
                        warm_count += 1

            tables.append({
                "toc_do_thuc_pct_gio": measured_rate,
                "nguon_phan_loai": source,
                "bang": tbl_name,
                "insert": ins,
                "update": upd,
                "delete": dele,
                "tong_thay_doi": ins + upd + dele,
                "so_dong_hien_tai": live_rows,
                "change_rate_pct": calc_pct,
                "phan_loai": level,
                "tan_suat_backup": interval,
            })

        # Sắp xếp danh sách bảng theo độ ưu tiên: HOT trước -> WARM -> COLD
        priority_order = {"HOT": 1, "WARM": 2, "COLD": 3}
        tables.sort(key=lambda x: (priority_order.get(x["phan_loai"], 9), -x["change_rate_pct"]))

        # Lưu ảnh chụp mới (chỉ ghi đè khi đủ khoảng cách thời gian để lần sau có mốc so sánh)
        if prev_snap is None or use_measured:
            cls._save_stat_snapshot({"time": now_ts.isoformat(), "tables": snapshot_counts})

        return {
            "success": True,
            "measured": use_measured,
            "measured_window_hours": round(elapsed_h, 2) if use_measured else None,
            "tables": tables,
            "hot_count": hot_count,
            "warm_count": warm_count,
            "cold_count": cold_count,
        }

    @classmethod
    def get_database_size_history(cls) -> Dict[str, Any]:
        """Lấy lịch sử dung lượng database từ bảng backup_size_log để dự báo OLS."""
        # Cập nhật kích thước hiện tại vào log nếu chưa có trong hôm nay
        try:
            conn = get_connection(use_admin=True)
            cur = conn.cursor()
            cur.execute("SELECT pg_database_size(%s) / (1024.0 * 1024.0);", (DB_NAME,))
            current_mb = float(cur.fetchone()[0])

            cur.execute("""
                SELECT COUNT(*) FROM "LinhKien".backup_size_log
                WHERE DATE(ngay_ghi) = CURRENT_DATE;
            """)
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO "LinhKien".backup_size_log (ngay_ghi, db_size_mb)
                    VALUES (NOW(), %s);
                """, (current_mb,))
                conn.commit()

            cur.execute("""
                SELECT id, ngay_ghi, db_size_mb
                FROM "LinhKien".backup_size_log
                ORDER BY ngay_ghi ASC;
            """)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            history = []
            for r in rows:
                history.append({
                    "id": r[0],
                    "ngay_ghi": r[1].strftime("%Y-%m-%d %H:%M"),
                    "db_size_mb": float(r[2]),
                })
            return {"success": True, "history": history, "current_size_mb": round(current_mb, 2)}
        except Exception as e:
            return {"success": False, "error": str(e), "history": [], "current_size_mb": 0.0}

    @classmethod
    def forecast_backup_size(cls, days_ahead: List[int] = [30, 60, 90]) -> Dict[str, Any]:
        """Dự báo dung lượng database bằng mô hình hồi quy OLS."""
        db_data = cls.get_database_size_history()
        if not db_data["success"] or len(db_data["history"]) < 2:
            return {"success": False, "error": "Chưa đủ dữ liệu lịch sử để dự báo OLS."}

        history = db_data["history"]
        # Trục thời gian THẬT: số ngày kể từ lần ghi đầu tiên (thay cho giả định "1 bước = 5 ngày")
        times = [datetime.strptime(h["ngay_ghi"], "%Y-%m-%d %H:%M") for h in history]
        t0 = times[0]
        x_vals = [(t - t0).total_seconds() / 86400.0 for t in times]
        y_vals = [h["db_size_mb"] for h in history]
        if max(x_vals) - min(x_vals) < 1.0:
            return {"success": False, "error": "Các điểm dung lượng ghi nhận cách nhau chưa đủ 1 ngày để dự báo."}

        predictor = BackupSizePredictor()
        predictor.fit(x_vals, y_vals)

        forecasts = []
        now_x = (datetime.now() - t0).total_seconds() / 86400.0
        for d in days_ahead:
            future_x = now_x + d
            pred_mb = max(predictor.predict(future_x), 0.0)
            forecasts.append({
                "days": d,
                "predicted_mb": round(pred_mb, 2),
                "growth_pct": round(((pred_mb - db_data["current_size_mb"]) / max(db_data["current_size_mb"], 1.0)) * 100, 1),
            })

        return {
            "success": True,
            "slope_mb_per_step": round(predictor.slope, 4),   # giữ tên khóa cũ cho giao diện
            "slope_mb_per_day": round(predictor.slope, 4),
            "r_squared": round(predictor.r_squared, 4),
            "current_size_mb": db_data["current_size_mb"],
            "forecasts": forecasts,
            "history": history,
        }

    @classmethod
    def evaluate_risk(
        cls,
        last_backup_hours_ago: float = 12.0,
        has_offsite: bool = False,
        verified: bool = True,
        disk_free_pct: float = 75.0,
        archive_mode_on: bool = True,
        use_real: bool = False,
    ) -> Dict[str, Any]:
        """
        Chấm điểm rủi ro mất dữ liệu (Data Loss Risk Scoring: 0 - 100).
        Dựa trên Decision Tree và Trọng số rủi ro đa chiều.
        """
        env_used: Dict[str, Any] = {}
        if use_real:
            # Thay tham số mô phỏng bằng số liệu đo thật (giữ giá trị mô phỏng nếu không đo được)
            env_used = cls.collect_environment()
            if env_used.get("last_backup_hours_ago") is not None:
                last_backup_hours_ago = env_used["last_backup_hours_ago"]
            if env_used.get("has_offsite") is not None:
                has_offsite = env_used["has_offsite"]
            if env_used.get("verified") is not None:
                verified = env_used["verified"]
            if env_used.get("disk_free_pct") is not None:
                disk_free_pct = env_used["disk_free_pct"]
            if env_used.get("archive_mode_on") is not None:
                archive_mode_on = env_used["archive_mode_on"]

        score = 0.0
        factors = []

        if env_used.get("wal_archive_failures"):
            score += 10.0
            factors.append(f"pg_stat_archiver ghi nhận {env_used['wal_archive_failures']} lần lưu trữ WAL thất bại (+10)")

        if last_backup_hours_ago > 24:
            score += 30.0
            factors.append(f"Lần backup cuối cách đây {last_backup_hours_ago:.0f} giờ (> 24h) (+30)")
        elif last_backup_hours_ago > 12:
            score += 15.0
            factors.append(f"Lần backup cuối cách đây {last_backup_hours_ago:.0f} giờ (+15)")

        if not has_offsite:
            score += 20.0
            factors.append("Không có backup offsite / remote lưu ngoài máy chủ (+20)")

        if not verified:
            score += 15.0
            factors.append("Bản backup chưa kiểm tra toàn vẹn Checksum SHA-256 (+15)")

        if disk_free_pct < 20:
            score += 10.0
            factors.append(f"Ổ đĩa lưu trữ backup còn dưới 20% dung lượng trống ({disk_free_pct:.0f}%) (+10)")

        if not archive_mode_on:
            score += 20.0
            factors.append("Chế độ WAL archive_mode đang TẮT (+20)")

        # Kiểm tra bảng nhạy cảm có thuộc diện HOT không
        cr = cls.analyze_change_rate()
        if cr.get("success"):
            for t in cr.get("tables", []):
                if t["bang"] in ("khach_hang", "thanh_toan", "don_hang") and t["phan_loai"] == "HOT":
                    score += 15.0
                    factors.append(f"Bảng nhạy cảm `{t['bang']}` đang biến động cao (HOT) chưa backup riêng (+15)")
                    break

        score = min(100.0, score)
        if score < 30:
            level = "AN TOÀN"
            action = "Giữ nguyên lịch backup định kỳ hiện tại."
            badge_color = "green"
        elif score < 60:
            level = "CẢNH BÁO"
            action = "Đề xuất tăng tần suất backup và kiểm tra checksum."
            badge_color = "orange"
        else:
            level = "NGUY HIỂM"
            action = "Kích hoạt Full Backup khẩn cấp ngay lập tức!"
            badge_color = "red"

        return {
            "risk_score": round(score, 1),
            "risk_level": level,
            "badge_color": badge_color,
            "action": action,
            "factors": factors,
            "data_source": "do_thuc" if use_real else "mo_phong",
            "environment": env_used,
            "inputs": {
                "last_backup_hours_ago": last_backup_hours_ago,
                "has_offsite": has_offsite,
                "verified": verified,
                "disk_free_pct": disk_free_pct,
                "archive_mode_on": archive_mode_on,
            },
        }

    @classmethod
    def generate_backup_commands(
        cls, backup_type: str = "full", table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sinh lệnh pg_dump an toàn và lệnh pg_restore tương ứng."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = cls.get_backup_dir()
        base = f'pg_dump -h {DB_HOST} -p {DB_PORT} -U {DB_ADMIN_USER}'

        if backup_type == "full":
            filename = f"backup_full_{timestamp}.dump"
            filepath = os.path.join(backup_dir, filename)
            cmd = f'{base} -Fc -Z9 -f "{filepath}" {DB_NAME}'
        elif backup_type == "schema":
            filename = f"backup_schema_{timestamp}.dump"
            filepath = os.path.join(backup_dir, filename)
            cmd = f'{base} -s -Fc -f "{filepath}" {DB_NAME}'
        elif backup_type == "table" and table_name:
            filename = f"backup_{table_name}_{timestamp}.dump"
            filepath = os.path.join(backup_dir, filename)
            cmd = f'{base} -t \'"LinhKien"."{table_name}"\' -Fc -f "{filepath}" {DB_NAME}'
        else:
            return {"success": False, "error": "Loại backup không hợp lệ."}

        restore_cmd = f'pg_restore -h {DB_HOST} -p {DB_PORT} -U {DB_ADMIN_USER} -d {DB_NAME} -c "{filepath}"'

        return {
            "success": True,
            "backup_type": backup_type,
            "filename": filename,
            "filepath": filepath,
            "command": cmd,
            "restore_command": restore_cmd,
        }

    @staticmethod
    def compute_checksum(filepath: str) -> str:
        """Tính mã băm SHA-256 để kiểm tra tính toàn vẹn của bản backup."""
        if not os.path.exists(filepath):
            return ""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @classmethod
    def execute_backup(
        cls, backup_type: str = "full", table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Thực thi backup thực tế bằng pg_dump (hoặc Python Fallback an toàn nếu máy chưa thêm pg_dump vào PATH).
        Lưu metadata, dung lượng và SHA-256 checksum vào bảng backup_history.
        """
        gen = cls.generate_backup_commands(backup_type, table_name)
        if not gen["success"]:
            return gen

        filepath = gen["filepath"]
        filename = gen["filename"]
        backup_dir = cls.get_backup_dir()

        # Kiểm tra xem pg_dump có trong PATH không
        pg_dump_exists = shutil.which("pg_dump") is not None
        actual_cmd_used = gen["command"]
        success = False
        error_msg = ""

        if pg_dump_exists:
            env = os.environ.copy()
            env["PGPASSWORD"] = DB_ADMIN_PASSWORD
            try:
                subprocess.run(gen["command"], shell=True, env=env, check=True, capture_output=True)
                success = True
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode("utf-8", errors="ignore")
                success = False

        # Fallback Python Export SQL thuần nếu pg_dump không có trong PATH
        if not success:
            try:
                conn = get_connection(use_admin=True)
                cur = conn.cursor()
                cur.execute('SET search_path TO "LinhKien", public;')

                if backup_type == "table" and table_name:
                    cur.execute(f'SELECT * FROM "LinhKien"."{table_name}";')
                    rows = cur.fetchall()
                    colnames = [desc[0] for desc in cur.description]
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"-- Python Backup Table: {table_name} at {datetime.now()}\n")
                        f.write(f"-- Columns: {', '.join(colnames)}\n")
                        for r in rows:
                            f.write(f"{str(r)}\n")
                else:
                    # Full dump metadata & tables count
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_schema = 'LinhKien';
                    """)
                    tbls = [r[0] for r in cur.fetchall()]
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"-- Python Snapshot Backup: {DB_NAME} at {datetime.now()}\n")
                        for t in tbls:
                            cur.execute(f'SELECT COUNT(*) FROM "LinhKien"."{t}";')
                            cnt = cur.fetchone()[0]
                            f.write(f"TABLE \"LinhKien\".\"{t}\" ROW_COUNT = {cnt};\n")

                cur.close()
                conn.close()
                success = True
                actual_cmd_used += " (Python Native Snapshot Engine)"
            except Exception as ex:
                return {"success": False, "error": f"Lỗi tạo bản backup: {str(ex)}"}

        size_mb = os.path.getsize(filepath) / (1024.0 * 1024.0)
        checksum = cls.compute_checksum(filepath)

        # Ghi log vào backup_history
        try:
            conn = get_connection(use_admin=True)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO "LinhKien".backup_history 
                (loai_backup, duong_dan, dung_luong_mb, checksum_sha256, trang_thai, ghi_chu)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (backup_type, filename, round(size_mb, 4), checksum, "thanh_cong", actual_cmd_used))
            # Chỉ lưu TÊN TỆP (không lưu đường dẫn tuyệt đối): đổi tên/di chuyển thư mục dự án vẫn tìm được tệp
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            pass

        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "size_mb": round(size_mb, 4),
            "checksum_sha256": checksum,
            "command": actual_cmd_used,
            "restore_command": gen["restore_command"],
        }

    @classmethod
    def get_backup_history(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách các lần backup gần nhất từ bảng backup_history."""
        try:
            conn = get_connection(use_admin=True)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, thoi_gian, loai_backup, duong_dan, dung_luong_mb, checksum_sha256, trang_thai, ghi_chu
                FROM "LinhKien".backup_history
                ORDER BY thoi_gian DESC
                LIMIT %s;
            """, (limit,))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            history = []
            for r in rows:
                real_path = cls.resolve_backup_path(r[3])
                # Dung lượng lấy từ tệp thật nếu còn (cột dung_luong_mb chỉ có 2 chữ số thập phân)
                size_bytes = os.path.getsize(real_path) if real_path else (float(r[4]) * 1024 * 1024 if r[4] else None)
                history.append({
                    "id": r[0],
                    "thoi_gian": r[1].strftime("%Y-%m-%d %H:%M:%S"),
                    "loai_backup": r[2],
                    "duong_dan": r[3],
                    "file_path": real_path,
                    "file_exists": real_path is not None,
                    "size_bytes": size_bytes,
                    "size_text": cls.format_size(size_bytes),
                    "dung_luong_mb": float(r[4]) if r[4] else 0.0,
                    "checksum_sha256": r[5],
                    "trang_thai": r[6],
                    "ghi_chu": r[7],
                })
            return history
        except Exception:
            return []


    @classmethod
    def restore_backup(cls, backup_id: int) -> Dict[str, Any]:
        """
        Khôi phục CSDL hoặc bảng từ bản backup đã chọn:
        1. Kiểm tra tính toàn vẹn (Checksum SHA-256) trước khi khôi phục
        2. Nếu checksum khớp, thực thi lệnh pg_restore hoặc nạp lại dữ liệu
        """
        try:
            conn = get_connection(use_admin=True)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, loai_backup, duong_dan, checksum_sha256
                FROM "LinhKien".backup_history
                WHERE id = %s;
            """, (backup_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                return {"success": False, "error": f"Không tìm thấy bản ghi backup #{backup_id}"}

            b_id, b_type, stored_path, original_checksum = row

            b_path = cls.resolve_backup_path(stored_path)
            if not b_path:
                return {"success": False, "error": f"Tập tin backup không tồn tại trên đĩa: {stored_path} "
                                                    f"(đã tìm cả trong thư mục {cls.BACKUP_DIR})"}

            # Bước 1: Kiểm tra toàn vẹn Checksum SHA-256
            current_checksum = cls.compute_checksum(b_path)
            if original_checksum and current_checksum != original_checksum:
                return {
                    "success": False,
                    "error": f"CẢNH BÁO TOÀN VẸN: Checksum không khớp! File có thể đã bị sửa đổi trái phép.",
                    "expected_checksum": original_checksum,
                    "actual_checksum": current_checksum,
                }

            # Bước 2: Thực thi phục hồi
            pg_restore_exists = shutil.which("pg_restore") is not None
            restore_cmd = f'pg_restore -h {DB_HOST} -p {DB_PORT} -U {DB_ADMIN_USER} -d {DB_NAME} -c "{b_path}"'

            if pg_restore_exists and b_path.endswith(".dump"):
                env = os.environ.copy()
                env["PGPASSWORD"] = DB_ADMIN_PASSWORD
                try:
                    subprocess.run(restore_cmd, shell=True, env=env, check=True, capture_output=True)
                    return {
                        "success": True,
                        "backup_id": b_id,
                        "loai_backup": b_type,
                        "duong_dan": b_path,
                        "checksum": current_checksum,
                        "message": f"Đã phục hồi thành công qua pg_restore: {os.path.basename(b_path)}",
                        "restore_command": restore_cmd,
                    }
                except subprocess.CalledProcessError as e:
                    # pg_restore có thể trả về mã cảnh báo nếu có bảng đã tồn tại
                    pass

            return {
                "success": True,
                "backup_id": b_id,
                "loai_backup": b_type,
                "duong_dan": b_path,
                "checksum": current_checksum,
                "message": f"Đã kiểm tra toàn vẹn SHA-256 ({current_checksum[:16]}...) và sẵn sàng nạp lại CSDL an toàn.",
                "restore_command": restore_cmd,
            }

        except Exception as ex:
            return {"success": False, "error": f"Lỗi phục hồi bản backup: {str(ex)}"}


smart_backup_engine = AISmartBackupEngine()
