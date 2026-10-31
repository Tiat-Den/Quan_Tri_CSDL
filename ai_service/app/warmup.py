"""
KHỞI ĐỘNG NỀN (warm-up): nạp sẵn các module AI nặng trong lúc người dùng còn ở màn hình đăng nhập.

Lần đầu vào dashboard phải import scikit-learn, pandas, dựng chỉ mục tìm kiếm ngữ nghĩa (AI 2)...
mất vài giây. Hàm start_warmup() chạy việc đó trong một luồng nền ngay khi web vừa mở,
nên khi bấm Đăng nhập thì mọi thứ đã sẵn sàng. Chỉ chạy 1 lần cho mỗi tiến trình web.
"""
import importlib
import logging
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()
status = {"done": False, "seconds": None, "error": None}

_MODULES = (
    "pandas",
    "app.pipeline",
    "app.router",
    "app.ai_semantic_search",
    "app.ai_security_guard",
    "app.ai_anomaly_detector",
    "app.session_context",
    "app.ai_index_advisor",
    "app.ai_predictive_partitioning",
    "app.ai_smart_backup",
)


def _run() -> None:
    t0 = time.perf_counter()
    try:
        for name in _MODULES:
            try:
                importlib.import_module(name)
            except Exception as exc:  # một module lỗi không chặn các module khác
                logger.warning("Warm-up: không nạp được %s: %s", name, exc)
        try:
            from app.ai_2_semantic.ai_semantic_search import get_engine
            get_engine()  # dựng sẵn chỉ mục sản phẩm cho AI 2
        except Exception as exc:
            logger.warning("Warm-up: chưa dựng được chỉ mục AI 2: %s", exc)
        try:
            from app.db import execute_query
            execute_query("SELECT 1 AS ok;")  # mở sẵn 1 kết nối trong pool
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover
        status["error"] = str(exc)
    finally:
        status["seconds"] = round(time.perf_counter() - t0, 2)
        status["done"] = True
        logger.info("Warm-up xong sau %.2fs", status["seconds"])


def start_warmup() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_run, name="ai-warmup", daemon=True).start()
