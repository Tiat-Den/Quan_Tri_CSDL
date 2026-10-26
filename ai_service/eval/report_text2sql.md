# BÁO CÁO ĐÁNH GIÁ AI 1: TEXT-TO-SQL (LUẬT + HỌC MÁY)

**Bộ kiểm thử:** `eval/text2sql_gold_50.json` (50 câu: 20 câu gốc, 25 câu diễn đạt lại không có trong dữ liệu huấn luyện, 5 câu ngoài phạm vi)

## 1. So sánh tổng hợp

| Chỉ số | Chỉ luật regex | Luật + ML dự phòng |
|---|---|---|
| Intent Accuracy (50 câu) | 50.0% | **90.0%** |
| Câu gốc (20) | 100.0% | 100.0% |
| Câu diễn đạt lại (25) | 0.0% | **80.0%** |
| Từ chối đúng câu ngoài phạm vi (5) | 100.0% | 100.0% |
| Số câu chưa trả lời được (hệ thống hỏi lại) | 25 | 5 |
| Execution Accuracy (cần DB) | — | — |

## 2. Chi tiết từng câu (cấu hình Luật + ML)

| # | Câu hỏi | Kỳ vọng | Dự đoán | Độ tin cậy | Cơ chế | Đúng |
|---|---|---|---|---|---|---|
| 1 | Danh sách sản phẩm đang bán | `LIST_PRODUCTS` | `LIST_PRODUCTS` | 1.00 | `rule_18_list_products` | ✅ |
| 2 | Tìm sản phẩm có giá trên 5 triệu | `FILTER_PRODUCTS_BY_PRICE` | `FILTER_PRODUCTS_BY_PRICE` | 1.00 | `rule_15_price_filter` | ✅ |
| 3 | Các linh kiện có giá từ 1 triệu đến 3 triệu | `FILTER_PRODUCTS_BY_PRICE_RANGE` | `FILTER_PRODUCTS_BY_PRICE_RANGE` | 1.00 | `rule_15_price_range` | ✅ |
| 4 | Top 5 sản phẩm đắt nhất | `TOP_PRODUCTS_BY_PRICE_DESC` | `TOP_PRODUCTS_BY_PRICE_DESC` | 1.00 | `rule_14_top_price_desc_explicit` | ✅ |
| 5 | Top 10 linh kiện rẻ nhất | `TOP_PRODUCTS_BY_PRICE_ASC` | `TOP_PRODUCTS_BY_PRICE_ASC` | 1.00 | `rule_14_top_price_asc_explicit` | ✅ |
| 6 | Đếm tổng số đơn hàng của cửa hàng | `COUNT_ORDERS` | `COUNT_ORDERS` | 1.00 | `rule_9_count_orders` | ✅ |
| 7 | Danh sách các đơn hàng đã hủy | `ORDERS_BY_STATUS` | `ORDERS_BY_STATUS` | 1.00 | `rule_12_orders_by_status` | ✅ |
| 8 | Liệt kê tất cả card màn hình VGA | `FILTER_BY_CATEGORY` | `FILTER_BY_CATEGORY` | 1.00 | `rule_16_filter_by_category` | ✅ |
| 9 | Tìm các sản phẩm của hãng ASUS | `FILTER_BY_BRAND` | `FILTER_BY_BRAND` | 1.00 | `rule_17_filter_by_brand` | ✅ |
| 10 | Những sản phẩm nào sắp hết hàng trong kho? | `LOW_STOCK` | `LOW_STOCK` | 1.00 | `rule_13_low_stock` | ✅ |
| 11 | Thống kê số lượng đơn hàng theo từng trạng thái | `ORDERS_COUNT_BY_STATUS` | `ORDERS_COUNT_BY_STATUS` | 1.00 | `rule_11_orders_count_by_status` | ✅ |
| 12 | Thống kê số đơn và doanh thu theo từng kênh bán | `ORDERS_BY_CHANNEL` | `ORDERS_BY_CHANNEL` | 1.00 | `rule_4_orders_by_channel` | ✅ |
| 13 | Khách hàng hay thanh toán qua những phương thức nào nhất? | `PAYMENT_METHODS_STATS` | `PAYMENT_METHODS_STATS` | 1.00 | `rule_5_payment_methods_stats` | ✅ |
| 14 | Thống kê số lượng khách hàng theo từng tỉnh thành | `CUSTOMERS_BY_CITY` | `CUSTOMERS_BY_CITY` | 1.00 | `rule_6_customers_by_city` | ✅ |
| 15 | Top 5 sản phẩm bán chạy nhất của cửa hàng | `BEST_SELLING_PRODUCTS` | `BEST_SELLING_PRODUCTS` | 1.00 | `rule_2_best_selling_products` | ✅ |
| 16 | Top 5 khách hàng mua nhiều tiền nhất | `TOP_SPENDING_CUSTOMERS` | `TOP_SPENDING_CUSTOMERS` | 1.00 | `rule_1_top_spending_customers` | ✅ |
| 17 | Thống kê doanh thu theo từng tháng trong năm 2025 | `SALES_BY_MONTH` | `SALES_BY_MONTH` | 1.00 | `rule_8_sales_by_month` | ✅ |
| 18 | Doanh số bán hàng của từng nhân viên | `EMPLOYEE_PERFORMANCE` | `EMPLOYEE_PERFORMANCE` | 1.00 | `rule_3_employee_performance` | ✅ |
| 19 | Tổng doanh thu của tất cả đơn hàng đã hoàn thành | `TOTAL_REVENUE` | `TOTAL_REVENUE` | 1.00 | `rule_10_total_revenue` | ✅ |
| 20 | Tổng tiền nhập hàng từ các nhà cung cấp | `SUPPLIER_PURCHASE_TOTAL` | `SUPPLIER_PURCHASE_TOTAL` | 1.00 | `rule_7_supplier_purchase_total` | ✅ |
| 21 | cửa hàng có tổng cộng mấy đơn rồi | `COUNT_ORDERS` | `COUNT_ORDERS` | 0.70 | `ml_fallback_accept` | ✅ |
| 22 | số order từ trước tới giờ | `COUNT_ORDERS` | `UNKNOWN` | 0.46 | `ml_fallback_suggest` | ❓ hỏi lại |
| 23 | những món nào kho sắp cạn | `LOW_STOCK` | `LOW_STOCK` | 0.92 | `ml_fallback_accept` | ✅ |
| 24 | hàng nào cần bổ sung thêm vào kho | `LOW_STOCK` | `LOW_STOCK` | 0.83 | `ml_fallback_accept` | ✅ |
| 25 | mỗi trạng thái xử lý có mấy đơn | `ORDERS_COUNT_BY_STATUS` | `ORDERS_COUNT_BY_STATUS` | 0.85 | `ml_fallback_accept` | ✅ |
| 26 | đơn đến từ sàn nào là nhiều | `ORDERS_BY_CHANNEL` | `ORDERS_BY_CHANNEL` | 0.70 | `ml_fallback_accept` | ✅ |
| 27 | bán online so với bán tại cửa hàng thế nào | `ORDERS_BY_CHANNEL` | `UNKNOWN` | 0.34 | `ml_fallback_suggest` | ❓ hỏi lại |
| 28 | người mua thường trả tiền kiểu gì | `PAYMENT_METHODS_STATS` | `PAYMENT_METHODS_STATS` | 0.78 | `ml_fallback_accept` | ✅ |
| 29 | khách trả góp hay trả thẳng nhiều hơn | `PAYMENT_METHODS_STATS` | `PAYMENT_METHODS_STATS` | 0.88 | `ml_fallback_accept` | ✅ |
| 30 | người mua tập trung ở tỉnh thành phố nào | `CUSTOMERS_BY_CITY` | `UNKNOWN` | 0.52 | `ml_fallback_suggest` | ❓ hỏi lại |
| 31 | khu vực nào có đông người mua | `CUSTOMERS_BY_CITY` | `CUSTOMERS_BY_CITY` | 0.77 | `ml_fallback_accept` | ✅ |
| 32 | mặt hàng nào được khách chuộng nhất | `BEST_SELLING_PRODUCTS` | `BEST_SELLING_PRODUCTS` | 0.82 | `ml_fallback_accept` | ✅ |
| 33 | sản phẩm hot nhất hiện nay là gì | `BEST_SELLING_PRODUCTS` | `UNKNOWN` | 0.35 | `ml_fallback_suggest` | ❓ hỏi lại |
| 34 | người nào chi nhiều tiền mua hàng nhất | `TOP_SPENDING_CUSTOMERS` | `TOP_SPENDING_CUSTOMERS` | 0.88 | `ml_fallback_accept` | ✅ |
| 35 | ai là người mua chịu chi nhất | `TOP_SPENDING_CUSTOMERS` | `TOP_SPENDING_CUSTOMERS` | 0.83 | `ml_fallback_accept` | ✅ |
| 36 | tiền bán được qua từng tháng | `SALES_BY_MONTH` | `SALES_BY_MONTH` | 0.90 | `ml_fallback_accept` | ✅ |
| 37 | tháng nào kinh doanh tốt nhất | `SALES_BY_MONTH` | `UNKNOWN` | 0.55 | `ml_fallback_suggest` | ❓ hỏi lại |
| 38 | bạn sale nào bán được nhiều nhất | `EMPLOYEE_PERFORMANCE` | `EMPLOYEE_PERFORMANCE` | 0.78 | `ml_fallback_accept` | ✅ |
| 39 | xếp hạng người bán hàng giỏi | `EMPLOYEE_PERFORMANCE` | `EMPLOYEE_PERFORMANCE` | 0.70 | `ml_fallback_accept` | ✅ |
| 40 | shop đã thu về tổng bao nhiêu tiền | `TOTAL_REVENUE` | `TOTAL_REVENUE` | 0.75 | `ml_fallback_accept` | ✅ |
| 41 | tổng số tiền thu được từ bán hàng | `TOTAL_REVENUE` | `TOTAL_REVENUE` | 0.81 | `ml_fallback_accept` | ✅ |
| 42 | đối tác nào cung ứng hàng nhiều nhất | `SUPPLIER_PURCHASE_TOTAL` | `SUPPLIER_PURCHASE_TOTAL` | 0.93 | `ml_fallback_accept` | ✅ |
| 43 | cửa hàng đang bán những mặt hàng gì | `LIST_PRODUCTS` | `LIST_PRODUCTS` | 0.92 | `ml_fallback_accept` | ✅ |
| 44 | linh kiện nào giá chát nhất | `TOP_PRODUCTS_BY_PRICE_DESC` | `TOP_PRODUCTS_BY_PRICE_DESC` | 0.75 | `ml_fallback_accept` | ✅ |
| 45 | món nào giá mềm nhất shop | `TOP_PRODUCTS_BY_PRICE_ASC` | `TOP_PRODUCTS_BY_PRICE_ASC` | 0.73 | `ml_fallback_accept` | ✅ |
| 46 | hôm nay trời có mưa không | `UNKNOWN` | `UNKNOWN` | 0.00 | `ml_out_of_scope` | ✅ |
| 47 | chào bạn nhé | `UNKNOWN` | `UNKNOWN` | 0.00 | `ml_out_of_scope` | ✅ |
| 48 | kể chuyện cười đi | `UNKNOWN` | `UNKNOWN` | 0.00 | `ml_out_of_scope` | ✅ |
| 49 | DROP TABLE san_pham | `UNKNOWN` | `UNKNOWN` | 0.00 | `ml_out_of_scope` | ✅ |
| 50 | tỷ giá đô la hôm nay | `UNKNOWN` | `UNKNOWN` | 0.00 | `ml_out_of_scope` | ✅ |
