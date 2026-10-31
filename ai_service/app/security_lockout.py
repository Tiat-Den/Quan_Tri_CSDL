"""
KHÓA TẠM THỜI THEO TÀI KHOẢN (AI 3 Zero-Trust - Session Lockout)

Trước đây thời điểm hết khóa nằm trong st.session_state, mà mỗi lần người dùng bấm F5 Streamlit tạo
phiên mới -> khóa biến mất. Module này lưu khóa PHÍA MÁY CHỦ, gắn theo tên tài khoản:
  - F5, mở tab mới, đăng xuất rồi đăng nhập lại đều vẫn bị khóa cho tới khi hết hạn;
  - ghi thêm ra logs/security_lockouts.json để khởi động lại web cũng không xóa được khóa đang hiệu lực.
"""
import json
import os
import threading
import time
from typing import Dict

LOCKOUT_SECONDS = 60

_LOCK = threading.Lock()
_STORE: Dict[str, float] = {}
_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "security_lockouts.json")
_loaded = False


def _key(username: str) -> str:
    return (username or "").strip().lower() or "anonymous"


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        for k, v in (data or {}).items():
            if isinstance(v, (int, float)) and v > now:
                _STORE[str(k)] = float(v)
    except Exception:
        pass


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_STORE, f)
        os.replace(tmp, _FILE)
    except Exception:
        pass  # Không ghi được file thì vẫn còn khóa trong bộ nhớ máy chủ


def lock(username: str, seconds: int = LOCKOUT_SECONDS) -> float:
    """Khóa tài khoản trong `seconds` giây (không rút ngắn khóa đang còn dài hơn). Trả về thời điểm hết khóa."""
    with _LOCK:
        _load()
        k = _key(username)
        until = max(_STORE.get(k, 0.0), time.time() + seconds)
        _STORE[k] = until
        now = time.time()
        for old in [x for x, v in _STORE.items() if v <= now]:
            _STORE.pop(old, None)
        _save()
        return until


def remaining(username: str) -> int:
    """Số giây còn bị khóa (0 = không bị khóa)."""
    with _LOCK:
        _load()
        until = _STORE.get(_key(username), 0.0)
    left = until - time.time()
    return int(left) + 1 if left > 0 else 0


def unlock(username: str) -> None:
    with _LOCK:
        _load()
        if _STORE.pop(_key(username), None) is not None:
            _save()
