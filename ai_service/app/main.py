"""
FastAPI Entrypoint cho AI Service (Text-to-SQL Rule Engine)
Hỗ trợ đầy đủ 20 câu hỏi vàng từ Query.md
"""
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.schemas import InterpretRequest, InterpretResponse, IntentInfo
from app.ai_1_text2sql.pipeline import interpret, InterpretResult

app = FastAPI(
    title="LinhKien Text-to-SQL Rule Engine",
    description="Bộ xử lý ngôn ngữ tự nhiên tiếng Việt sang SQL bằng tập luật cho cửa hàng linh kiện máy tính",
    version="2.0.0"
)

# Cấu hình CORS an toàn
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(config, "CORS_ALLOW_ORIGINS", ["http://localhost:8501"]),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    """Kiểm tra tình trạng hoạt động của service"""
    return {
        "status": "healthy",
        "service": "ai_service_rule_based",
        "engine": "python_rule_engine",
        "mode": "local_offline_no_llm_api",
        "intents_supported": 20
    }


@app.get("/intents", response_model=List[IntentInfo], tags=["Schema & Rules"])
def get_supported_intents():
    """Trả về danh sách 20 Intent vàng đang được hỗ trợ cùng câu hỏi mẫu từ Query.md"""
    return [
        IntentInfo(
            intent="LIST_PRODUCTS",
            description="Danh sách sản phẩm đang kinh doanh",
            sample_questions=[
                "Danh sách sản phẩm đang bán",
                "Liệt kê các sản phẩm còn kinh doanh",
                "Hiển thị sản phẩm"
            ]
        ),
        IntentInfo(
            intent="FILTER_PRODUCTS_BY_PRICE",
            description="Tìm sản phẩm có giá trên hoặc dưới một ngưỡng",
            sample_questions=[
                "Tìm sản phẩm có giá trên 5 triệu",
                "Linh kiện giá lớn hơn 5000000",
                "Sản phẩm dưới 2 triệu"
            ]
        ),
        IntentInfo(
            intent="FILTER_PRODUCTS_BY_PRICE_RANGE",
            description="Các linh kiện có giá trong khoảng từ Min đến Max",
            sample_questions=[
                "Các linh kiện có giá từ 1 triệu đến 3 triệu",
                "Sản phẩm trong khoảng 2 triệu đến 5 triệu"
            ]
        ),
        IntentInfo(
            intent="TOP_PRODUCTS_BY_PRICE_DESC",
            description="Top N sản phẩm đắt nhất",
            sample_questions=[
                "Top 5 sản phẩm đắt nhất",
                "5 linh kiện có giá cao nhất"
            ]
        ),
        IntentInfo(
            intent="TOP_PRODUCTS_BY_PRICE_ASC",
            description="Top N linh kiện rẻ nhất",
            sample_questions=[
                "Top 10 linh kiện rẻ nhất",
                "10 sản phẩm giá thấp nhất"
            ]
        ),
        IntentInfo(
            intent="COUNT_ORDERS",
            description="Đếm tổng số đơn hàng của cửa hàng",
            sample_questions=[
                "Đếm tổng số đơn hàng của cửa hàng",
                "Cửa hàng có bao nhiêu đơn hàng?"
            ]
        ),
        IntentInfo(
            intent="ORDERS_BY_STATUS",
            description="Danh sách các đơn hàng theo trạng thái (đã hủy, hoàn thành...)",
            sample_questions=[
                "Danh sách các đơn hàng đã hủy",
                "Những đơn hàng bị hủy",
                "Đơn nào đã hủy?"
            ]
        ),
        IntentInfo(
            intent="FILTER_BY_CATEGORY",
            description="Liệt kê sản phẩm theo danh mục linh kiện (12 danh mục)",
            sample_questions=[
                "Liệt kê tất cả card màn hình VGA",
                "Danh sách CPU",
                "Tìm các loại bàn phím"
            ]
        ),
        IntentInfo(
            intent="FILTER_BY_BRAND",
            description="Tìm các sản phẩm của một thương hiệu/hãng (30 hãng)",
            sample_questions=[
                "Tìm các sản phẩm của hãng ASUS",
                "Linh kiện thương hiệu Corsair",
                "Sản phẩm MSI"
            ]
        ),
        IntentInfo(
            intent="LOW_STOCK",
            description="Những sản phẩm sắp hết hàng trong kho (dưới mức tồn tối thiểu)",
            sample_questions=[
                "Những sản phẩm nào sắp hết hàng trong kho?",
                "Cảnh báo tồn kho thấp",
                "Sản phẩm dưới mức tồn tối thiểu"
            ]
        ),
        IntentInfo(
            intent="ORDERS_COUNT_BY_STATUS",
            description="Thống kê số lượng đơn hàng theo từng trạng thái",
            sample_questions=[
                "Thống kê số lượng đơn hàng theo từng trạng thái",
                "Số đơn theo trạng thái"
            ]
        ),
        IntentInfo(
            intent="ORDERS_BY_CHANNEL",
            description="Thống kê số đơn và doanh thu theo từng kênh bán",
            sample_questions=[
                "Thống kê số đơn và doanh thu theo từng kênh bán",
                "Doanh thu theo kênh bán hàng"
            ]
        ),
        IntentInfo(
            intent="PAYMENT_METHODS_STATS",
            description="Thống kê phương thức thanh toán khách hàng hay dùng",
            sample_questions=[
                "Khách hàng hay thanh toán qua những phương thức nào nhất?",
                "Thống kê hình thức thanh toán"
            ]
        ),
        IntentInfo(
            intent="CUSTOMERS_BY_CITY",
            description="Thống kê số lượng khách hàng theo từng tỉnh thành",
            sample_questions=[
                "Thống kê số lượng khách hàng theo từng tỉnh thành",
                "Khách hàng phân bố ở tỉnh nào nhiều nhất?"
            ]
        ),
        IntentInfo(
            intent="BEST_SELLING_PRODUCTS",
            description="Top N sản phẩm bán chạy nhất của cửa hàng",
            sample_questions=[
                "Top 5 sản phẩm bán chạy nhất của cửa hàng",
                "Những sản phẩm bán được nhiều nhất"
            ]
        ),
        IntentInfo(
            intent="TOP_SPENDING_CUSTOMERS",
            description="Top N khách hàng mua nhiều tiền nhất (khách VIP)",
            sample_questions=[
                "Top 5 khách hàng mua nhiều tiền nhất",
                "Khách hàng VIP mua nhiều nhất"
            ]
        ),
        IntentInfo(
            intent="SALES_BY_MONTH",
            description="Thống kê doanh thu theo từng tháng trong năm (mặc định 2025)",
            sample_questions=[
                "Thống kê doanh thu theo từng tháng trong năm 2025",
                "Doanh thu năm 2025 theo tháng"
            ]
        ),
        IntentInfo(
            intent="EMPLOYEE_PERFORMANCE",
            description="Doanh số bán hàng của từng nhân viên",
            sample_questions=[
                "Doanh số bán hàng của từng nhân viên",
                "Nhân viên nào bán được nhiều tiền nhất?"
            ]
        ),
        IntentInfo(
            intent="TOTAL_REVENUE",
            description="Tổng doanh thu của tất cả đơn hàng đã hoàn thành",
            sample_questions=[
                "Tổng doanh thu của tất cả đơn hàng đã hoàn thành",
                "Cửa hàng kiếm được bao nhiêu tiền doanh thu?"
            ]
        ),
        IntentInfo(
            intent="SUPPLIER_PURCHASE_TOTAL",
            description="Tổng tiền nhập hàng từ các nhà cung cấp",
            sample_questions=[
                "Tổng tiền nhập hàng từ các nhà cung cấp",
                "Chi phí nhập hàng theo từng nhà cung cấp"
            ]
        ),
    ]


@app.post("/interpret", response_model=InterpretResponse, tags=["NLP & SQL"])
def interpret_question(req: InterpretRequest):
    """
    Phân tích câu hỏi tiếng Việt bằng quy tắc và sinh câu lệnh SQL an toàn thông qua Pipeline dùng chung.
    """
    raw_question = req.question.strip()
    if not raw_question:
        raise HTTPException(status_code=400, detail="Câu hỏi không được để trống")

    result = interpret(raw_question)

    return InterpretResponse(
        success=result.success,
        question=result.question,
        normalized_question=result.normalized_question,
        intent=result.intent,
        confidence=result.confidence,
        entities=result.entities,
        entities_used=result.used_entities,
        sql=result.sql,
        params=result.params,
        explanation=result.explanation,
        message="Phân tích thành công bằng bộ xử lý quy tắc cục bộ." if result.success else (result.clarification or "Xin lỗi, câu hỏi nằm ngoài phạm vi hỗ trợ."),
        needs_clarification=result.needs_clarification,
        clarification=result.clarification,
        warnings=result.warnings,
    )


if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
