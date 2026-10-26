"""
PHÁT HIỆN HÀNH VI TRUY VẤN BẤT THƯỜNG (Anomaly Detection) — thành phần HỌC MÁY của AI 3.

Bộ chấm điểm theo luật (ai_security_guard.py) chỉ bắt được những mẫu tấn công đã biết trước.
Module này học "hành vi bình thường" rồi phát hiện truy vấn lệch khỏi nó, kể cả khi không vi phạm luật nào:

1. Isolation Forest (scikit-learn, học không giám sát):
   - Mỗi truy vấn được biểu diễn bằng vector đặc trưng: giờ (sin/cos), log(số dòng), số bảng,
     số cột, SELECT *, có LIMIT, có hàm tổng hợp, log(QPS), độ dài câu SQL.
   - Huấn luyện trên: (a) hồ sơ hành vi nền khởi tạo (giờ hành chính, truy vấn nhỏ có LIMIT),
     (b) các truy vấn NORMAL thật trong logs/security_audit.jsonl. Mô hình tự huấn luyện lại
     khi nhật ký có thêm RETRAIN_EVERY bản ghi mới.
2. Hồ sơ riêng từng người dùng (z-score): nếu số dòng truy xuất lệch > 3 độ lệch chuẩn so với
   lịch sử của chính người đó -> cảnh báo (vd: nhân viên thường xem 10 dòng bỗng lấy 2.000 dòng).

Không gọi API ngoài; hoàn toàn offline.
"""
import json
import logging
import math
import threading
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("ai_service.anomaly")

FEATURE_NAMES = [
    "hour_sin", "hour_cos", "log_rows", "n_tables", "n_columns",
    "has_star", "has_limit", "has_agg", "log_qps", "sql_len_log",
]
RETRAIN_EVERY = 50          # Huấn luyện lại sau mỗi 50 bản ghi nhật ký mới
MIN_USER_HISTORY = 10       # Số truy vấn tối thiểu để lập hồ sơ riêng một người dùng
USER_Z_THRESHOLD = 3.0
BASELINE_SAMPLES = 400
RANDOM_SEED = 42
MAX_LOG_RECORDS = 5000      # Giới hạn số bản ghi nhật ký đọc mỗi lần (tránh chậm khi log lớn)


def build_features(
    hour: int,
    rows: int,
    n_tables: int,
    n_columns: int,
    has_star: bool,
    has_limit: bool,
    has_agg: bool,
    qps: float,
    sql_len: int,
) -> List[float]:
    """Chuyển thông tin một truy vấn thành vector đặc trưng số."""
    angle = 2 * math.pi * (hour % 24) / 24.0
    return [
        math.sin(angle),
        math.cos(angle),
        math.log1p(max(rows, 0)),
        float(n_tables),
        float(min(n_columns, 30)),
        1.0 if has_star else 0.0,
        1.0 if has_limit else 0.0,
        1.0 if has_agg else 0.0,
        math.log1p(max(qps, 0.0)),
        math.log1p(max(sql_len, 0)),
    ]


def _baseline_profile(n: int = BASELINE_SAMPLES) -> np.ndarray:
    """
    Hồ sơ hành vi nền khởi tạo (mô phỏng ca làm việc bình thường của cửa hàng) để mô hình hoạt động
    ngay cả khi nhật ký thật còn ít. Khi nhật ký thật đủ lớn, dữ liệu thật chiếm đa số tập huấn luyện.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for _ in range(n):
        hour = int(rng.integers(8, 22))  # Giờ mở cửa cửa hàng 8h - 22h
        has_agg = rng.random() < 0.45
        n_rows = int(np.clip(rng.lognormal(2.3, 1.0), 1, 300)) if not has_agg else int(rng.integers(1, 40))
        n_tables = int(rng.choice([1, 1, 1, 2, 2, 3]))
        # Truy vấn thống kê (COUNT/SUM...) thường không cần LIMIT và ít cột; truy vấn liệt kê thì ngược lại
        has_limit = (rng.random() < 0.2) if has_agg else (rng.random() < 0.85)
        n_columns = int(rng.integers(0, 4)) if has_agg else int(rng.integers(1, 8))
        rows.append(build_features(
            hour=hour,
            rows=n_rows,
            n_tables=n_tables,
            n_columns=n_columns,
            has_star=rng.random() < 0.05,
            has_limit=has_limit,
            has_agg=has_agg,
            qps=float(np.clip(rng.lognormal(-0.7, 0.6), 0.05, 4.0)),
            sql_len=int(rng.integers(30, 400)),
        ))
    return np.array(rows, dtype=float)


class QueryAnomalyDetector:
    """Isolation Forest + hồ sơ z-score theo người dùng."""

    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._trained_on_records = -1
        self.n_real_samples = 0
        self.n_seed_samples = 0

    # ------------------------------------------------------------------
    @staticmethod
    def _load_log_records() -> List[Dict[str, Any]]:
        from app.ai_security_guard import AUDIT_LOG_FILE
        records = []
        if not AUDIT_LOG_FILE.exists():
            return records
        try:
            from collections import deque
            seeded_lines = []
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                recent = deque(maxlen=MAX_LOG_RECORDS)  # dữ liệu thật: chỉ học từ các bản ghi gần nhất
                for line in f:
                    # Lịch sử mẫu (nằm đầu tệp) luôn được giữ để không bị cắt khi nhật ký lớn
                    (seeded_lines if '"source": "seed_lich_su"' in line else recent).append(line)
            for line in seeded_lines + list(recent):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Không đọc được audit log cho anomaly detector: %s", e)
        return records

    def _fit(self, records: List[Dict[str, Any]]):
        from sklearn.ensemble import IsolationForest

        usable = [
            r for r in records
            if isinstance(r.get("features"), list) and len(r["features"]) == len(FEATURE_NAMES)
            and r.get("status") == "NORMAL"
        ]
        real = [r["features"] for r in usable]
        n_seed = sum(1 for r in usable if r.get("source") == "seed_lich_su")
        X = _baseline_profile()
        if real:
            X = np.vstack([X, np.array(real, dtype=float)])
        model = IsolationForest(n_estimators=200, contamination=0.03, random_state=RANDOM_SEED)
        model.fit(X)
        self._model = model
        self.n_real_samples = len(real) - n_seed
        self.n_seed_samples = n_seed
        self._trained_on_records = len(records)
        logger.info("Anomaly detector đã huấn luyện: %d mẫu nền + %d mẫu thật.", BASELINE_SAMPLES, len(real))

    def ensure_trained(self, records: Optional[List[Dict[str, Any]]] = None):
        if records is None:
            records = self._load_log_records()
        need = self._model is None or (len(records) - self._trained_on_records) >= RETRAIN_EVERY
        if need:
            with self._lock:
                if self._model is None or (len(records) - self._trained_on_records) >= RETRAIN_EVERY:
                    self._fit(records)
        return records

    # ------------------------------------------------------------------
    def score(self, features: List[float], user: Optional[str] = None, rows: int = 0) -> Dict[str, Any]:
        """
        Trả về:
          - anomaly_score: 0..1 (càng cao càng bất thường)
          - is_anomaly: mô hình Isolation Forest đánh dấu là ngoại lai
          - user_zscore / user_deviation: lệch so với lịch sử riêng của người dùng
        """
        records = self.ensure_trained()
        x = np.array([features], dtype=float)
        raw = float(self._model.decision_function(x)[0])   # > 0: bình thường, < 0: ngoại lai
        anomaly_score = float(1.0 / (1.0 + math.exp(raw * 12)))  # ánh xạ về [0, 1]
        is_anomaly = bool(self._model.predict(x)[0] == -1)

        user_z = None
        user_dev = False
        if user:
            hist = [
                r["features"][2] for r in records
                if r.get("user") == user and isinstance(r.get("features"), list)
                and len(r["features"]) == len(FEATURE_NAMES) and r.get("status") == "NORMAL"
            ]
            if len(hist) >= MIN_USER_HISTORY:
                mu, sd = float(np.mean(hist)), float(np.std(hist))
                sd = max(sd, 0.25)
                user_z = round((math.log1p(max(rows, 0)) - mu) / sd, 2)
                user_dev = user_z > USER_Z_THRESHOLD

        return {
            "anomaly_score": round(anomaly_score, 3),
            "is_anomaly": is_anomaly,
            "decision_value": round(raw, 4),
            "user_zscore": user_z,
            "user_deviation": user_dev,
            "trained_real_samples": self.n_real_samples,
            "trained_seed_samples": self.n_seed_samples,
        }


_detector: Optional[QueryAnomalyDetector] = None
_detector_lock = threading.Lock()


def get_anomaly_detector() -> QueryAnomalyDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = QueryAnomalyDetector()
    return _detector
