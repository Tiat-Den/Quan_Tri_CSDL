"""
Module quản lý ngữ cảnh phiên người dùng (Session Context) và kiểm soát tần suất truy vấn (Rate Tracker).
Phục vụ Module AI 3 (Zero-Trust Security Guard) theo đặc tả A3-3.
"""
import collections
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SessionContext:
    """Ngữ cảnh phiên thực thi của người dùng."""
    session_id: str = "default_session"
    user: str = "guest"
    ip: str = "127.0.0.1"
    ip_source: str = "simulated"  # 'real' hoặc 'simulated'
    hour: Optional[int] = None
    failed_logins: int = 0
    qps: float = 1.0
    simulated_fields: List[str] = field(default_factory=lambda: ["ip", "failed_logins"])

    def __post_init__(self):
        if self.hour is None:
            self.hour = datetime.now().hour


class RateTracker:
    """
    Theo dõi và đo lường QPS thật dựa trên lịch sử truy vấn theo phiên trong cửa sổ trượt (Sliding Window).
    """

    def __init__(self, window_seconds: float = 10.0):
        self.window_seconds = window_seconds
        self._history: Dict[str, collections.deque] = collections.defaultdict(collections.deque)

    def record_hit(self, session_id: str) -> float:
        """Ghi nhận một lượt truy vấn mới và trả về QPS tức thời trong cửa sổ trượt."""
        now = time.time()
        q = self._history[session_id]
        q.append(now)

        # Loại bỏ các mốc thời gian ngoài cửa sổ
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

        # Tính QPS = tổng số truy vấn trong cửa sổ / thời gian cửa sổ
        return round(len(q) / self.window_seconds, 2)

    def get_qps(self, session_id: str) -> float:
        """Lấy QPS hiện tại của phiên mà không ghi nhận hit mới."""
        now = time.time()
        q = self._history.get(session_id)
        if not q:
            return 0.0

        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

        return round(len(q) / self.window_seconds, 2)


# Singleton rate tracker
rate_tracker = RateTracker(window_seconds=10.0)


def mask_sensitive_value(col_name: str, value: Any) -> Any:
    """Mã hóa / làm mờ (Masking) các trường dữ liệu nhạy cảm."""
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return val_str

    col_lower = col_name.lower()

    if "email" in col_lower and "@" in val_str:
        user_part, domain_part = val_str.split("@", 1)
        if len(user_part) <= 1:
            masked_user = "*"
        else:
            masked_user = user_part[0] + "***"
        return f"{masked_user}@{domain_part}"

    if "so_dien_thoai" in col_lower or "phone" in col_lower or "sdt" in col_lower:
        if len(val_str) >= 7:
            return val_str[:4] + "***" + val_str[-3:]
        return val_str[:2] + "***"

    if "dia_chi" in col_lower or "address" in col_lower:
        parts = val_str.split()
        if len(parts) >= 2:
            return parts[0] + " *** " + (parts[-1] if len(parts) > 2 else "")
        return "***"

    return value


def mask_sensitive_columns(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Áp dụng Dynamic Data Masking trên danh sách kết quả truy vấn đối với các cột nhạy cảm.
    """
    if not rows:
        return []

    sensitive_target_keys = {"email", "so_dien_thoai", "dia_chi_chi_tiet", "sdt", "phone"}
    masked_rows = []

    for row in rows:
        new_row = {}
        for k, v in row.items():
            k_lower = k.lower()
            if any(target in k_lower for target in sensitive_target_keys):
                new_row[k] = mask_sensitive_value(k, v)
            else:
                new_row[k] = v
        masked_rows.append(new_row)

    return masked_rows


class CatalogCoverageTracker:
    """
    Theo dõi các sản phẩm mà mỗi phiên đã nhận được từ AI 2 (tìm kiếm ngữ nghĩa).
    Độ phủ = số sản phẩm khác nhau đã xem / tổng số sản phẩm trong danh mục.
    Độ phủ cao là dấu hiệu đang vét dữ liệu danh mục và giá, bất kể hỏi nhanh hay chậm.
    """

    def __init__(self):
        self._seen: Dict[str, set] = collections.defaultdict(set)

    def add(self, session_id: str, product_ids: List[Any]):
        self._seen[session_id].update(product_ids)

    def seen_count(self, session_id: str) -> int:
        return len(self._seen.get(session_id, ()))

    def coverage(self, session_id: str, catalog_size: int) -> float:
        if catalog_size <= 0:
            return 0.0
        return min(1.0, self.seen_count(session_id) / catalog_size)

    def reset(self, session_id: str):
        self._seen.pop(session_id, None)


coverage_tracker = CatalogCoverageTracker()
