"""
Bộ phân loại ý định HỌC MÁY (ML Intent Classifier) cho AI 1 — dùng làm DỰ PHÒNG cho bộ luật regex.

Kiến trúc lai (Hybrid Rule + ML):
1. Bộ luật regex (intent_classifier.py) chạy trước: nhanh, chính xác tuyệt đối với 20 mẫu câu chuẩn.
2. Khi luật không khớp (UNKNOWN), mô hình học máy dự đoán ý định từ cách diễn đạt khác:
   - Đặc trưng: TF-IDF n-gram từ (1-2) + TF-IDF n-gram ký tự (2-4, chịu lỗi chính tả/viết liền).
   - Mô hình: Logistic Regression đa lớp, trả về xác suất cho từng intent (độ tin cậy THẬT).
   - Lớp OUT_OF_SCOPE giúp mô hình biết từ chối câu ngoài phạm vi (thời tiết, chào hỏi...).
3. Ngưỡng quyết định:
   - xác suất >= ML_ACCEPT_THRESHOLD  -> chấp nhận intent.
   - ML_SUGGEST_THRESHOLD <= p < ML_ACCEPT_THRESHOLD -> hỏi lại người dùng kèm gợi ý.
   - còn lại -> UNKNOWN.

Hoàn toàn offline, chỉ dùng scikit-learn. Dữ liệu huấn luyện: app/data/intent_training.json
+ các câu Admin đã duyệt trong bảng "LinhKien".cau_hoi_chua_hieu (xem app/learning_loop.py).
"""
import json
import logging
import os
import re
import threading
from contextlib import contextmanager
from typing import Iterable, List, Optional, Tuple

from app.ai_1_text2sql.text_normalizer import remove_diacritics

logger = logging.getLogger("ai_service.ml_intent")

_local_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "intent_training.json")
_parent_data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "intent_training.json")
DATA_PATH = _local_data if os.path.exists(_local_data) else _parent_data
OUT_OF_SCOPE = "OUT_OF_SCOPE"

ML_ACCEPT_THRESHOLD = float(os.getenv("ML_ACCEPT_THRESHOLD", "0.55"))
ML_SUGGEST_THRESHOLD = float(os.getenv("ML_SUGGEST_THRESHOLD", "0.30"))
MAX_ML_INPUT_LEN = 300

# Câu chứa từ khóa SQL / ký tự tiêm mã -> không bao giờ để ML đoán (luôn UNKNOWN)
_SQL_LIKE = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|grant|revoke|create|union|pg_sleep)\b|--|;|/\*",
    re.IGNORECASE,
)


class MLIntentClassifier:
    """Mô hình TF-IDF (word + char) + Logistic Regression, huấn luyện lười (lazy) một lần."""

    def __init__(self, data_path: str = DATA_PATH, extra_samples: Optional[Iterable[Tuple[str, str]]] = None):
        """
        extra_samples: danh sách (câu hỏi, intent) đã được Admin duyệt (học từ câu chưa hiểu),
        được cộng thêm vào dữ liệu gốc. Không ghi đè file intent_training.json -> bộ dữ liệu gốc luôn sạch.
        """
        self.data_path = data_path
        self.extra_samples: List[Tuple[str, str]] = [
            (str(t), str(lb)) for t, lb in (extra_samples or []) if t and lb
        ]
        self._lock = threading.Lock()
        self._model = None
        self.classes_: List[str] = []
        self.n_samples = 0
        self.n_base_samples = 0

    # ------------------------------------------------------------------
    def _load_dataset(self) -> Tuple[List[str], List[str]]:
        with open(self.data_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        texts, labels = [], []
        for intent, samples in raw.items():
            if intent.startswith("_") or not isinstance(samples, list):
                continue
            for s in samples:
                texts.append(self._prep(s))
                labels.append(intent)
        self.n_base_samples = len(texts)
        for text, intent in self.extra_samples:
            prepped = self._prep(text)
            if prepped:
                texts.append(prepped)
                labels.append(intent)
        return texts, labels

    def base_dataset(self) -> Tuple[List[str], List[str]]:
        """Chỉ dữ liệu gốc (dùng để kiểm tra mô hình mới không 'quên' kiến thức cũ)."""
        with open(self.data_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        texts, labels = [], []
        for intent, samples in raw.items():
            if intent.startswith("_") or not isinstance(samples, list):
                continue
            for s in samples:
                texts.append(s)
                labels.append(intent)
        return texts, labels

    @staticmethod
    def _prep(text: str) -> str:
        return remove_diacritics((text or "")[:MAX_ML_INPUT_LEN]).strip()

    def _build(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline, FeatureUnion

        texts, labels = self._load_dataset()
        features = FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
        ])
        model = Pipeline([
            ("features", features),
            ("clf", LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced")),
        ])
        model.fit(texts, labels)
        self._model = model
        self.classes_ = list(model.classes_)
        self.n_samples = len(texts)
        logger.info("Đã huấn luyện ML Intent Classifier: %d mẫu (%d mẫu học thêm), %d lớp.",
                    len(texts), len(texts) - self.n_base_samples, len(self.classes_))

    def ensure_trained(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._build()

    # ------------------------------------------------------------------
    def predict_proba(self, text: str) -> List[Tuple[str, float]]:
        """Trả về danh sách (intent, xác suất) sắp xếp giảm dần."""
        self.ensure_trained()
        prepped = self._prep(text)
        if not prepped:
            return [(OUT_OF_SCOPE, 1.0)]
        probs = self._model.predict_proba([prepped])[0]
        ranked = sorted(zip(self.classes_, probs), key=lambda x: x[1], reverse=True)
        return [(c, float(p)) for c, p in ranked]

    def predict(self, text: str) -> Tuple[Optional[str], float, List[str]]:
        """
        Dự đoán intent cho câu hỏi.
        Trả về (intent | None, xác suất, danh sách intent thay thế gần nhất).
        intent = None nghĩa là ngoài phạm vi hoặc không chắc chắn.
        """
        if not text or _SQL_LIKE.search(text):
            return None, 0.0, []
        ranked = self.predict_proba(text)
        top_intent, top_p = ranked[0]
        alternatives = [c for c, p in ranked[1:4] if c != OUT_OF_SCOPE and p >= 0.10]
        if top_intent == OUT_OF_SCOPE:
            return None, top_p, alternatives
        return top_intent, top_p, alternatives


_instance: Optional[MLIntentClassifier] = None
_instance_lock = threading.Lock()
# Mô hình "ứng viên" chỉ có hiệu lực trong LUỒNG đang đánh giá (khi Admin bấm Huấn luyện lại),
# người dùng khác vẫn dùng mô hình đang chạy cho tới khi ứng viên được chấp nhận.
_override = threading.local()


def _load_learned_samples() -> List[Tuple[str, str]]:
    """Mẫu đã duyệt + đã huấn luyện trong CSDL. Lỗi (chưa chạy script SQL, mất kết nối) -> bỏ qua."""
    try:
        from app.ai_1_text2sql.learning_loop import load_trained_samples
        intents, _needs = load_trained_samples()
        return intents
    except Exception as ex:  # pragma: no cover - không để lỗi CSDL chặn việc dựng mô hình
        logger.info("Không nạp được mẫu học thêm (%s) -> chỉ dùng dữ liệu gốc.", ex)
        return []


def get_ml_classifier() -> MLIntentClassifier:
    override = getattr(_override, "instance", None)
    if override is not None:
        return override
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MLIntentClassifier(extra_samples=_load_learned_samples())
    return _instance


def set_ml_classifier(classifier: MLIntentClassifier) -> None:
    """Thay mô hình đang chạy bằng mô hình mới đã huấn luyện xong (phép gán nguyên tử)."""
    global _instance
    classifier.ensure_trained()
    with _instance_lock:
        _instance = classifier


@contextmanager
def use_classifier(classifier: MLIntentClassifier):
    """Tạm dùng `classifier` CHỈ trong luồng hiện tại (đánh giá mô hình ứng viên)."""
    previous = getattr(_override, "instance", None)
    _override.instance = classifier
    try:
        yield classifier
    finally:
        _override.instance = previous


def ml_suggest_intents(text: str, top_k: int = 3) -> List[str]:
    """Gợi ý các intent gần nhất (dùng để hiển thị 'Ý bạn là...?')."""
    try:
        ranked = get_ml_classifier().predict_proba(text)
    except Exception:  # pragma: no cover - không để lỗi ML làm sập luồng chính
        return []
    return [c for c, p in ranked if c != OUT_OF_SCOPE][:top_k]
