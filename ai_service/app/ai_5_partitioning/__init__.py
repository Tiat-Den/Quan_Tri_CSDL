"""
MODULE AI 5: DỰ BÁO DUNG LƯỢNG & TỰ ĐỘNG PHÂN VÙNG BẢNG (PREDICTIVE PARTITIONING)
Hồi quy tuyến tính OLS, khoảng tin cậy 95%, so sánh mô hình Holt/Baseline và lộ trình migration.
"""
from app.ai_5_partitioning import ai_predictive_partitioning, partition_demo
from app.ai_5_partitioning.ai_predictive_partitioning import (
    AIPredictivePartitioningEngine,
    HoltLinearPredictor,
    LinearRegressionPredictor,
    forecast_series,
)

__all__ = [
    "ai_predictive_partitioning",
    "partition_demo",
    "AIPredictivePartitioningEngine",
    "LinearRegressionPredictor",
    "HoltLinearPredictor",
    "forecast_series",
]
