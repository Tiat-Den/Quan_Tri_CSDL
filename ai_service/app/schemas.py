"""
Pydantic Schemas cho API
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InterpretRequest(BaseModel):
    question: str = Field(..., description="Câu hỏi tiếng Việt của người dùng", min_length=1)


class InterpretResponse(BaseModel):
    success: bool = Field(..., description="True nếu nhận diện thành công và sinh được SQL")
    question: str = Field(..., description="Câu hỏi gốc")
    normalized_question: str = Field(..., description="Câu hỏi sau khi chuẩn hóa")
    intent: Optional[str] = Field(None, description="Mã Intent nhận diện được")
    confidence: float = Field(1.0, description="Độ tin cậy của intent (0.0 - 1.0)")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Các thực thể trích xuất được")
    entities_used: List[str] = Field(default_factory=list, description="Các thực thể đã được đưa vào câu truy vấn SQL")
    sql: Optional[str] = Field(None, description="Câu lệnh SQL sinh ra (có placeholder %s)")
    params: List[Any] = Field(default_factory=list, description="Danh sách tham số an toàn đi kèm")
    explanation: str = Field(..., description="Giải thích cách hệ thống hiểu và sinh SQL")
    message: Optional[str] = Field(None, description="Thông báo lỗi hoặc gợi ý nếu không hiểu")
    needs_clarification: bool = Field(False, description="True nếu yêu cầu người dùng làm rõ câu hỏi")
    clarification: Optional[str] = Field(None, description="Gợi ý hoặc câu hỏi làm rõ")
    warnings: List[str] = Field(default_factory=list, description="Danh sách cảnh báo")


class IntentInfo(BaseModel):
    intent: str
    description: str
    sample_questions: List[str]
