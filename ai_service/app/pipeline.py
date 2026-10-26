"""
Module xử lý trung tâm (Pipeline) cho Hệ thống Text-to-SQL Rule Engine.
Tập trung toàn bộ logic chuẩn hóa, phân loại ý định (Intent), bóc tách thực thể (Entities),
sinh mã SQL an toàn (SQL Builder) và giải thích (Explanation).
Tránh trùng lặp logic giữa FastAPI (main.py) và Giao diện Streamlit (dashboard_page.py).
"""
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from app import config
from app.entity_extractor import (
    extract_brand,
    extract_category,
    extract_channel,
    extract_order_status,
    extract_payment_method,
    extract_price_condition,
    extract_top_n,
    extract_year,
)
from app.explanation import generate_explanation
from app.intent_classifier import IntentResult, classify_intent
from app.sql_builder import build_sql
from app.text_normalizer import get_normalized_pair, normalize_text

logger = logging.getLogger("ai_service.pipeline")

# Nhãn tiếng Việt dễ hiểu cho từng intent (dùng khi gợi ý "Ý bạn là...?")
INTENT_LABELS: Dict[str, str] = {
    "LIST_PRODUCTS": "Danh sách sản phẩm đang bán",
    "FILTER_PRODUCTS_BY_PRICE": "Lọc sản phẩm theo giá",
    "FILTER_PRODUCTS_BY_PRICE_RANGE": "Sản phẩm trong khoảng giá",
    "TOP_PRODUCTS_BY_PRICE_DESC": "Top sản phẩm đắt nhất",
    "TOP_PRODUCTS_BY_PRICE_ASC": "Top sản phẩm rẻ nhất",
    "COUNT_ORDERS": "Đếm tổng số đơn hàng",
    "ORDERS_BY_STATUS": "Đơn hàng theo trạng thái",
    "FILTER_BY_CATEGORY": "Sản phẩm theo danh mục",
    "FILTER_BY_BRAND": "Sản phẩm theo hãng",
    "LOW_STOCK": "Sản phẩm sắp hết hàng",
    "ORDERS_COUNT_BY_STATUS": "Số đơn theo từng trạng thái",
    "ORDERS_BY_CHANNEL": "Đơn hàng theo kênh bán",
    "PAYMENT_METHODS_STATS": "Thống kê phương thức thanh toán",
    "CUSTOMERS_BY_CITY": "Khách hàng theo tỉnh thành",
    "BEST_SELLING_PRODUCTS": "Sản phẩm bán chạy nhất",
    "TOP_SPENDING_CUSTOMERS": "Khách hàng chi tiêu nhiều nhất",
    "SALES_BY_MONTH": "Doanh thu theo tháng",
    "EMPLOYEE_PERFORMANCE": "Doanh số theo nhân viên",
    "TOTAL_REVENUE": "Tổng doanh thu",
    "SUPPLIER_PURCHASE_TOTAL": "Tổng tiền nhập theo nhà cung cấp",
}


def _format_suggestions(alternatives: List[str]) -> str:
    labels = [INTENT_LABELS[a] for a in alternatives if a in INTENT_LABELS]
    # Loại trùng, giữ thứ tự
    seen, uniq = set(), []
    for lb in labels:
        if lb not in seen:
            seen.add(lb)
            uniq.append(lb)
    if not uniq:
        return ""
    return " Ý bạn là: " + "; ".join(f"«{lb}»" for lb in uniq[:3]) + "?"


@dataclass
class InterpretResult:
    """Cấu trúc dữ liệu kết quả phân tích ngôn ngữ tự nhiên Text-to-SQL (A1-1)."""
    question: str
    normalized_question: str
    intent: str
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    sql: Optional[str] = None
    params: List[Any] = field(default_factory=list)
    explanation: str = ""
    success: bool = True
    matched_rule: str = ""
    alternatives: List[str] = field(default_factory=list)
    used_entities: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển đổi thành từ điển Python chuẩn."""
        return asdict(self)


def interpret(question: str) -> InterpretResult:
    """
    Điểm vào duy nhất để phân tích câu hỏi tự nhiên tiếng Việt sang SQL an toàn:
    1. Kiểm tra độ dài tối đa (MAX_QUESTION_LEN = 300).
    2. Chuẩn hóa câu hỏi tiếng Việt (bảo toàn chữ số thập phân/phân cách nghìn).
    3. Nhận diện ý định (Intent Classifier).
    4. Bóc tách thực thể (Entity Extractor: giá, limit, danh mục, hãng, trạng thái, kênh, thanh toán).
    5. Kiểm tra yêu cầu làm rõ câu hỏi (Needs Clarification).
    6. Dựng câu lệnh SQL tham số hóa (%s) và theo dõi used_entities.
    7. Chính sách thực thể thừa (Unused Entities Policy: từ chối nếu có ràng buộc không thể áp dụng).
    8. Tạo giải thích tự động quy tắc ánh xạ.
    """
    raw_question = question.strip() if question else ""
    if not raw_question:
        return InterpretResult(
            question="",
            normalized_question="",
            intent="UNKNOWN",
            confidence=0.0,
            success=False,
            explanation="Câu hỏi rỗng. Vui lòng nhập câu hỏi cần tra cứu.",
            needs_clarification=True,
            clarification="Vui lòng nhập câu hỏi về linh kiện hoặc đơn hàng.",
        )

    max_len = getattr(config, "MAX_QUESTION_LEN", 300)
    warnings: List[str] = []
    if len(raw_question) > max_len:
        warnings.append(f"Câu hỏi dài hơn giới hạn {max_len} ký tự, đã được cắt ngắn an toàn.")
        raw_question = raw_question[:max_len]

    # 1. Chuẩn hóa tiếng Việt
    norm_text, no_accent = get_normalized_pair(raw_question)

    # 2. Phân loại ý định
    intent_res = classify_intent(norm_text)
    if isinstance(intent_res, tuple):
        intent, confidence = intent_res[0], intent_res[1]
        matched_rule = getattr(intent_res, "matched_rule", "")
        alternatives = getattr(intent_res, "alternatives", [])
    else:
        intent = getattr(intent_res, "intent", str(intent_res))
        confidence = getattr(intent_res, "confidence", 1.0)
        matched_rule = getattr(intent_res, "matched_rule", "")
        alternatives = getattr(intent_res, "alternatives", [])

    # 3. Trích xuất thực thể
    entities: Dict[str, Any] = {}

    price_cond = extract_price_condition(norm_text)
    if price_cond:
        entities.update(price_cond)

    top_n = extract_top_n(norm_text)
    if top_n is not None:
        max_limit = getattr(config, "MAX_LIMIT", 100)
        if top_n <= 0:
            warnings.append(f"Giới hạn top {top_n} <= 0 không hợp lệ, hệ thống bỏ qua giới hạn này.")
        elif top_n > max_limit:
            warnings.append(f"Giới hạn top {top_n} vượt quá mức tối đa {max_limit}, đã được kẹp còn {max_limit}.")
            entities["limit"] = top_n
        else:
            entities["limit"] = top_n

    category = extract_category(norm_text)
    if category is not None:
        entities["category_name"] = category

    brand = extract_brand(norm_text)
    if brand is not None:
        entities["brand_name"] = brand

    order_status = extract_order_status(norm_text)
    if order_status is not None:
        entities["status"] = order_status

    year = extract_year(norm_text)
    if year is not None:
        entities["year"] = year

    channel = extract_channel(norm_text)
    if channel is not None:
        entities["channel"] = channel

    payment_method = extract_payment_method(norm_text)
    if payment_method is not None:
        entities["payment_method"] = payment_method

    # 4. Kiểm tra nếu bộ bóc tách giá yêu cầu làm rõ (e.g. "Giá trên 5")
    if entities.get("needs_clarification"):
        clarification_msg = entities.get("clarification", "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: 5 triệu.")
        return InterpretResult(
            question=raw_question,
            normalized_question=norm_text,
            intent=intent,
            confidence=confidence,
            entities=entities,
            sql=None,
            params=[],
            explanation=clarification_msg,
            success=False,
            matched_rule=matched_rule,
            alternatives=alternatives,
            warnings=warnings,
            needs_clarification=True,
            clarification=clarification_msg,
        )

    # 5. Kiểm tra nếu confidence thấp (e.g. 0.6) hoặc UNKNOWN
    if intent == "UNKNOWN" or confidence == 0:
        return InterpretResult(
            question=raw_question,
            normalized_question=norm_text,
            intent="UNKNOWN",
            confidence=0.0,
            entities=entities,
            sql=None,
            params=[],
            explanation="Hệ thống quy tắc không nhận diện được từ khóa hoặc mẫu câu tương ứng trong CSDL LinhKien_DB.",
            success=False,
            matched_rule=matched_rule,
            alternatives=alternatives,
            warnings=warnings,
            needs_clarification=True,
            clarification="Hệ thống chưa hiểu ý câu hỏi. Bạn có thể chọn câu hỏi mẫu từ danh sách gợi ý."
            + _format_suggestions(alternatives),
        )

    if confidence < 0.7:
        # Khớp mơ hồ hoặc chỉ có từ so sánh trần ("cao nhất" mà không có ngữ cảnh rõ ràng)
        if matched_rule.startswith("ml_"):
            clarification_msg = (
                f"Hệ thống chưa chắc chắn về ý câu hỏi (độ tin cậy {confidence * 100:.0f}%)."
                + _format_suggestions(alternatives or [intent])
            )
        else:
            clarification_msg = "Câu hỏi chưa rõ ngữ cảnh cụ thể (bạn muốn tìm sản phẩm giá cao nhất, hay tháng có doanh thu cao nhất?)."
        return InterpretResult(
            question=raw_question,
            normalized_question=norm_text,
            intent=intent,
            confidence=confidence,
            entities=entities,
            sql=None,
            params=[],
            explanation=clarification_msg,
            success=False,
            matched_rule=matched_rule,
            alternatives=alternatives,
            warnings=warnings,
            needs_clarification=True,
            clarification=clarification_msg,
        )

    # 6. Dựng SQL và Tham số an toàn
    sql_build_res = build_sql(intent, entities)
    sql = sql_build_res.sql
    params = sql_build_res.params
    used_entities = getattr(sql_build_res, "used_entities", set())

    # 7. Chính sách thực thể thừa (Unused Entities Policy - A1-4)
    # Nếu người dùng đưa vào ràng buộc mà template không thể áp dụng, từ chối và yêu cầu làm rõ
    # Thay vì ngấm ngầm trả kết quả sai lệch!
    core_entity_keys = {"category_name", "brand_name", "status", "year", "channel", "payment_method"}
    extracted_core = {k for k in entities.keys() if k in core_entity_keys}
    unused_core = extracted_core - used_entities

    if unused_core:
        cond_descriptions = []
        for k in sorted(unused_core):
            val = entities.get(k)
            if k == "brand_name":
                cond_descriptions.append(f"hãng {val}")
            elif k == "category_name":
                cond_descriptions.append(f"danh mục {val}")
            elif k == "channel":
                cond_descriptions.append(f"kênh {val}")
            elif k == "payment_method":
                cond_descriptions.append(f"phương thức thanh toán {val}")
            elif k == "status":
                cond_descriptions.append(f"trạng thái {val}")
            elif k == "year":
                cond_descriptions.append(f"năm {val}")
            else:
                cond_descriptions.append(f"{k} ({val})")

        detail_msg = f"Chưa áp dụng được điều kiện: {', '.join(cond_descriptions)} cho thống kê này."
        logger.warning("Truy vấn có điều kiện chưa hỗ trợ: %s | Entities: %s", detail_msg, entities)
        return InterpretResult(
            question=raw_question,
            normalized_question=norm_text,
            intent=intent,
            confidence=confidence,
            entities=entities,
            sql=None,
            params=[],
            explanation=detail_msg,
            success=False,
            matched_rule=matched_rule,
            alternatives=alternatives,
            used_entities=list(used_entities),
            warnings=warnings,
            needs_clarification=True,
            clarification=detail_msg,
        )

    # 8. Sinh giải thích quy tắc
    explanation = generate_explanation(intent, entities, used_entities=used_entities)

    return InterpretResult(
        question=raw_question,
        normalized_question=norm_text,
        intent=intent,
        confidence=confidence,
        entities=entities,
        sql=sql,
        params=params,
        explanation=explanation,
        success=True,
        matched_rule=matched_rule,
        alternatives=alternatives,
        used_entities=list(used_entities),
        warnings=warnings,
    )
