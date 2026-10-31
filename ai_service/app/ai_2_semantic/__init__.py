"""
MODULE AI 2: TÌM KIẾM NGỮ NGHĨA & TƯ VẤN CẤU HÌNH LINH KIỆN
Kiến trúc Hybrid Ranking (TF-IDF Word + Char N-gram + Knowledge Graph).
"""
from app.ai_2_semantic import ai_semantic_search, knowledge_graph
from app.ai_2_semantic.ai_semantic_search import (
    AISemanticSearchEngine,
    flatten_specs,
    get_engine,
    semantic_search_engine,
)
from app.ai_2_semantic.knowledge_graph import (
    HardwareKnowledgeGraph,
    HardwareNeed,
    get_knowledge_graph,
)

__all__ = [
    "ai_semantic_search",
    "knowledge_graph",
    "AISemanticSearchEngine",
    "get_engine",
    "semantic_search_engine",
    "flatten_specs",
    "HardwareKnowledgeGraph",
    "get_knowledge_graph",
    "HardwareNeed",
]
