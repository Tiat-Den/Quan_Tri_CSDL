"""
Module bộ định tuyến truy vấn thông minh (Intelligent Query Router - A2-5)
Tự động phân luồng câu hỏi giữa AI 1 (Text-to-SQL Rule Engine) và AI 2 (Semantic Search & Knowledge Graph).
Dựa trên tín hiệu nhu cầu phần cứng, từ khóa tư vấn, và độ tin cậy phân loại ý định.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.intent_classifier import classify_intent
from app.knowledge_graph import get_knowledge_graph
from app.text_normalizer import normalize_text, remove_diacritics

# Các mẫu câu hoặc từ khóa đặc trưng cho nhu cầu tư vấn cấu hình phần cứng (AI 2 - A2-5)
CONSULTATION_SIGNALS_REGEX = re.compile(
    r'\b(tư vấn|tu van|gợi ý|goi y|nên mua|nen mua|phù hợp|phu hop|cấu hình|cau hinh|build pc|build|dàn máy|dan may|tốt nhất cho|tot nhat cho|mạnh nhất|manh nhat|tốt nhất|tot nhat|nhanh nhất|nhanh nhat)\b'
    r'|\b(để|de|cho)\s+(?:laptop\s+|máy\s+|pc\s+|dàn\s+)?(chơi|choi|làm|lam|học|hoc|dựng|dung|render|stream|văn phòng|van phong|đồ họa|do hoa|game)\b',
    re.IGNORECASE,
)

# Các từ khóa thông số kỹ thuật phần cứng JSONB (AI 2 - A2-5)
SPEC_SIGNALS_REGEX = re.compile(
    r'\b(vram|socket|lga\d+|am[45]|bus\s*\d*|tdp|gddr\d*|ips|hz|refresh rate|tần số quét|tan so quet|công suất|cong suat|wattage|modular)\b',
    re.IGNORECASE,
)


@dataclass
class RouteDecision:
    """Kết quả định tuyến truy vấn."""
    engine: str  # 'ai1', 'ai2', hoặc 'unknown'
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    detected_needs: list = field(default_factory=list)


def route(question: str) -> RouteDecision:
    """
    Phân loại câu hỏi và quyết định bộ xử lý phù hợp nhất (A2-5):
    1. Nếu có tín hiệu tư vấn cấu hình rõ ràng hoặc khớp nhu cầu Knowledge Graph -> AI 2.
    2. Nếu AI 1 nhận diện với độ tin cậy cao (>= 0.8) và không có tín hiệu tư vấn -> AI 1.
    3. Ngược lại, nếu phát hiện được nhu cầu phần cứng -> AI 2, còn không -> UNKNOWN.
    """
    raw_question = question.strip() if question else ""
    if not raw_question:
        return RouteDecision(engine="unknown", reason="Câu hỏi rỗng")

    norm_text = normalize_text(raw_question)
    no_accent = remove_diacritics(norm_text)

    # 1. Kiểm tra tín hiệu tư vấn và thông số kỹ thuật phần cứng JSONB
    has_consult_signal = bool(CONSULTATION_SIGNALS_REGEX.search(norm_text)) or \
                         bool(CONSULTATION_SIGNALS_REGEX.search(no_accent))
    has_spec_signal = bool(SPEC_SIGNALS_REGEX.search(norm_text)) or \
                      bool(SPEC_SIGNALS_REGEX.search(no_accent))

    # 2. Kiểm tra nhu cầu từ Knowledge Graph
    kg = get_knowledge_graph()
    detected_needs = kg.detect_needs(norm_text)
    detected_need_names = [need.name for need in detected_needs]

    # 3. Đánh giá phân loại AI 1 (Text-to-SQL)
    intent_res = classify_intent(norm_text)
    intent = getattr(intent_res, "intent", str(intent_res[0]))
    confidence = getattr(intent_res, "confidence", float(intent_res[1]))

    # Điểm đánh giá để minh bạch hóa quyết định
    scores = {
        "ai1_confidence": confidence,
        "has_consult_signal": 1.0 if (has_consult_signal or has_spec_signal) else 0.0,
        "kg_needs_count": float(len(detected_needs)),
    }

    # QUY TẮC ĐỊNH TUYẾN CHÍNH THỨC (A2-5):
    # - Nếu có tín hiệu tư vấn hoặc tìm theo thông số kỹ thuật JSONB (vram, socket, bus...) -> Ưu tiên AI 2
    if has_consult_signal or has_spec_signal:
        return RouteDecision(
            engine="ai2",
            reason="Phát hiện từ khóa tư vấn hoặc thông số kỹ thuật phần cứng JSONB phù hợp với AI 2 (Semantic Search).",
            scores=scores,
            detected_needs=detected_need_names,
        )

    # - Nếu AI 1 khớp với độ tin cậy cao và không có tín hiệu tư vấn
    if confidence >= 0.8 and intent != "UNKNOWN":
        return RouteDecision(
            engine="ai1",
            reason=f"Khớp Intent Text-to-SQL '{intent}' với độ tin cậy {confidence * 100:.0f}%.",
            scores=scores,
            detected_needs=detected_need_names,
        )

    # - Nếu có nhu cầu phần cứng cụ thể (e.g. 'Tôi muốn mua CPU Intel mạnh nhất')
    if detected_needs:
        return RouteDecision(
            engine="ai2",
            reason="Phát hiện nhu cầu sử dụng phần cứng cụ thể theo Knowledge Graph.",
            scores=scores,
            detected_needs=detected_need_names,
        )

    # - Nếu AI 1 nhận diện mức độ trung bình
    if confidence > 0.0 and intent != "UNKNOWN":
        return RouteDecision(
            engine="ai1",
            reason=f"Khớp Intent '{intent}' (độ tin cậy vừa phải).",
            scores=scores,
            detected_needs=detected_need_names,
        )

    return RouteDecision(
        engine="unknown",
        reason="Không nhận diện được Intent CSDL hoặc nhu cầu phần cứng phù hợp.",
        scores=scores,
        detected_needs=detected_need_names,
    )
