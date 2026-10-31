"""
GÓI ỨNG DỤNG AI SERVICE (HỆ THỐNG QUẢN TRỊ CSDL & 6 ĐỘNG CƠ AI NỘI BỘ)

Cấu trúc phân hệ theo thư mục:
- app.ai_1_text2sql      : Bộ chuyển đổi ngôn ngữ tự nhiên sang SQL (NL2SQL Engine)
- app.ai_2_semantic      : Tìm kiếm ngữ nghĩa & Tư vấn cấu hình linh kiện
- app.ai_3_security      : Giám sát an toàn Zero-Trust & Chống rò rỉ dữ liệu
- app.ai_4_index_advisor : Cố vấn tự động đề xuất chỉ mục tối ưu
- app.ai_5_partitioning  : Dự báo tăng trưởng & Quy hoạch phân vùng bảng
- app.ai_6_smart_backup  : Sao lưu dữ liệu thông minh & Kiểm soát toàn vẹn SHA-256
"""
import sys

# Nạp các phân hệ AI
from app import ai_1_text2sql
from app import ai_2_semantic
from app import ai_3_security
from app import ai_4_index_advisor
from app import ai_5_partitioning
from app import ai_6_smart_backup

# Ánh xạ tương thích ngược (Backward Compatibility Aliases)
# Đảm bảo các mã lệnh cũ import `from app.pipeline import ...` hoặc `import app.ai_security_guard`
# vẫn tiếp tục hoạt động 100% trơn tru mà không làm gãy hệ thống.
_LEGACY_MODULE_MAP = {
    "pipeline": ai_1_text2sql.pipeline,
    "text_normalizer": ai_1_text2sql.text_normalizer,
    "intent_classifier": ai_1_text2sql.intent_classifier,
    "entity_extractor": ai_1_text2sql.entity_extractor,
    "query_templates": ai_1_text2sql.query_templates,
    "sql_builder": ai_1_text2sql.sql_builder,
    "explanation": ai_1_text2sql.explanation,
    "ml_intent_classifier": ai_1_text2sql.ml_intent_classifier,
    "learning_loop": ai_1_text2sql.learning_loop,
    "ai_semantic_search": ai_2_semantic.ai_semantic_search,
    "knowledge_graph": ai_2_semantic.knowledge_graph,
    "ai_security_guard": ai_3_security.ai_security_guard,
    "ai_anomaly_detector": ai_3_security.ai_anomaly_detector,
    "audit_seeder": ai_3_security.audit_seeder,
    "ai_index_advisor": ai_4_index_advisor.ai_index_advisor,
    "ai_predictive_partitioning": ai_5_partitioning.ai_predictive_partitioning,
    "partition_demo": ai_5_partitioning.partition_demo,
    "ai_smart_backup": ai_6_smart_backup.ai_smart_backup,
}

for mod_name, mod_obj in _LEGACY_MODULE_MAP.items():
    sys.modules[f"app.{mod_name}"] = mod_obj


def __getattr__(name: str):
    if name in _LEGACY_MODULE_MAP:
        return _LEGACY_MODULE_MAP[name]
    raise AttributeError(f"module 'app' has no attribute '{name}'")
