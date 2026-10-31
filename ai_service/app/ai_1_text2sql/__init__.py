"""
MODULE AI 1: TEXT-TO-SQL RULE ENGINE
Chuyển đổi câu hỏi quản trị kinh doanh tiếng Việt sang truy vấn PostgreSQL an toàn.
"""
from app.ai_1_text2sql import (
    entity_extractor,
    explanation,
    intent_classifier,
    learning_loop,
    ml_intent_classifier,
    pipeline,
    query_templates,
    sql_builder,
    text_normalizer,
)
from app.ai_1_text2sql.explanation import generate_explanation
from app.ai_1_text2sql.intent_classifier import IntentResult, classify_intent
from app.ai_1_text2sql.pipeline import InterpretResult, interpret
from app.ai_1_text2sql.sql_builder import build_sql
from app.ai_1_text2sql.text_normalizer import normalize_text, remove_diacritics

__all__ = [
    "interpret",
    "InterpretResult",
    "classify_intent",
    "IntentResult",
    "build_sql",
    "normalize_text",
    "remove_diacritics",
    "generate_explanation",
    "pipeline",
    "text_normalizer",
    "intent_classifier",
    "entity_extractor",
    "query_templates",
    "sql_builder",
    "explanation",
    "ml_intent_classifier",
    "learning_loop",
]
