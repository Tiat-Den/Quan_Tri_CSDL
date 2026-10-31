"""
MODULE AI 4: CỐ VẤN TỰ ĐỘNG ĐỀ XUẤT CHỈ MỤC TỐI ƯU (SMART INDEX ADVISOR)
Khảo sát pg_class / pg_index, cây quyết định và sinh DDL an toàn CONCURRENTLY.
"""
from app.ai_4_index_advisor import ai_index_advisor
from app.ai_4_index_advisor.ai_index_advisor import AIIndexAdvisor

__all__ = ["ai_index_advisor", "AIIndexAdvisor"]
