# DANH SÁCH 20 TRUY VẤN VÀNG (GOLD QUERIES)
## HỆ THỐNG TEXT-TO-SQL RULE-BASED CHO CỬA HÀNG LINH KIỆN MÁY TÍNH

Tài liệu này định nghĩa bộ 20 câu hỏi mục tiêu, ánh xạ Intent, trích xuất thực thể và câu lệnh SQL chuẩn (Gold SQL) trên cơ sở dữ liệu `LinhKien_DB` (schema `"LinhKien"`).

---

## BẢNG TỔNG HỢP CÁC TRUY VẤN

| STT | Câu hỏi tiếng Việt | Intent | Cấp độ | Bảng liên quan |
| :---: | :--- | :--- | :---: | :--- |
| 1 | Danh sách sản phẩm đang bán | `LIST_PRODUCTS` | Cơ bản | `san_pham` |
| 2 | Tìm sản phẩm có giá trên 5 triệu | `FILTER_PRODUCTS_BY_PRICE` | Cơ bản | `san_pham` |
| 3 | Các linh kiện có giá từ 1 triệu đến 3 triệu | `FILTER_PRODUCTS_BY_PRICE_RANGE` | Cơ bản | `san_pham` |
| 4 | Top 5 sản phẩm đắt nhất | `TOP_PRODUCTS_BY_PRICE_DESC` | Cơ bản | `san_pham` |
| 5 | Top 10 linh kiện rẻ nhất | `TOP_PRODUCTS_BY_PRICE_ASC` | Cơ bản | `san_pham` |
| 6 | Đếm tổng số đơn hàng của cửa hàng | `COUNT_ORDERS` | Cơ bản | `don_hang` |
| 7 | Danh sách các đơn hàng đã hủy | `ORDERS_BY_STATUS` | Cơ bản | `don_hang` |
| 8 | Liệt kê tất cả card màn hình VGA | `FILTER_BY_CATEGORY` | Trung bình | `san_pham`, `danh_muc` |
| 9 | Tìm các sản phẩm của hãng ASUS | `FILTER_BY_BRAND` | Trung bình | `san_pham`, `thuong_hieu` |
| 10 | Những sản phẩm nào sắp hết hàng trong kho? | `LOW_STOCK` | Trung bình | `san_pham`, `ton_kho` |
| 11 | Thống kê số lượng đơn hàng theo từng trạng thái | `ORDERS_COUNT_BY_STATUS` | Trung bình | `don_hang` |
| 12 | Thống kê số đơn và doanh thu theo từng kênh bán | `ORDERS_BY_CHANNEL` | Trung bình | `don_hang` |
| 13 | Khách hàng hay thanh toán qua những phương thức nào nhất? | `PAYMENT_METHODS_STATS` | Trung bình | `thanh_toan` |
| 14 | Thống kê số lượng khách hàng theo từng tỉnh thành | `CUSTOMERS_BY_CITY` | Trung bình | `khach_hang`, `dia_chi` |
| 15 | Top 5 sản phẩm bán chạy nhất của cửa hàng | `BEST_SELLING_PRODUCTS` | Nâng cao | `san_pham`, `chi_tiet_don_hang`, `don_hang` |
| 16 | Top 5 khách hàng mua nhiều tiền nhất | `TOP_SPENDING_CUSTOMERS` | Nâng cao | `khach_hang`, `don_hang` |
| 17 | Thống kê doanh thu theo từng tháng trong năm 2025 | `SALES_BY_MONTH` | Nâng cao | `don_hang` |
| 18 | Doanh số bán hàng của từng nhân viên | `EMPLOYEE_PERFORMANCE` | Nâng cao | `nhan_vien`, `don_hang` |
| 19 | Tổng doanh thu của tất cả đơn hàng đã hoàn thành | `TOTAL_REVENUE` | Nâng cao | `don_hang` |
| 20 | Tổng tiền nhập hàng từ các nhà cung cấp | `SUPPLIER_PURCHASE_TOTAL` | Nâng cao | `nha_cung_cap`, `phieu_nhap` |

---

## CHI TIẾT TỪNG TRUY VẤN VÀ CẤU TRÚC ÁNH XẠ

### CẤP ĐỘ 1: CƠ BẢN (1 Bảng - Lọc, Sắp xếp, Giới hạn)

#### 1. `LIST_PRODUCTS`
* **Câu hỏi mẫu:** "Danh sách sản phẩm đang bán", "Liệt kê các sản phẩm còn kinh doanh", "Hiển thị sản phẩm"
* **Intent:** `LIST_PRODUCTS`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện các từ khóa "danh sách sản phẩm", "liệt kê sản phẩm" $\rightarrow$ lọc sản phẩm có `dang_kinh_doanh = TRUE`.
* **SQL Chuẩn:**
```sql
SELECT id, ma_sku, ten, gia_niem_yet, bao_hanh_thang 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
LIMIT 50;
```

---

#### 2. `FILTER_PRODUCTS_BY_PRICE`
* **Câu hỏi mẫu:** "Tìm sản phẩm có giá trên 5 triệu", "Linh kiện giá lớn hơn 5000000", "Sản phẩm trên 10 triệu"
* **Intent:** `FILTER_PRODUCTS_BY_PRICE`
* **Thực thể trích xuất:**
  * `operator`: `>` (hoặc `>=`)
  * `price_value`: `5000000`
* **Giải thích luật:** Nhận diện từ khóa so sánh giá "trên / lớn hơn" kèm số tiền `5 triệu` (= 5.000.000 VNĐ).
* **SQL Chuẩn:**
```sql
SELECT id, ten, gia_niem_yet 
FROM san_pham 
WHERE gia_niem_yet > 5000000 AND dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC;
```

---

#### 3. `FILTER_PRODUCTS_BY_PRICE_RANGE`
* **Câu hỏi mẫu:** "Các linh kiện có giá từ 1 triệu đến 3 triệu", "Sản phẩm trong khoảng 2 triệu đến 5 triệu"
* **Intent:** `FILTER_PRODUCTS_BY_PRICE_RANGE`
* **Thực thể trích xuất:**
  * `min_price`: `1000000`
  * `max_price`: `3000000`
* **Giải thích luật:** Nhận diện cấu trúc "từ [giá 1] đến [giá 2]" $\rightarrow$ tạo điều kiện `BETWEEN ... AND ...`.
* **SQL Chuẩn:**
```sql
SELECT id, ten, gia_niem_yet 
FROM san_pham 
WHERE gia_niem_yet BETWEEN 1000000 AND 3000000 AND dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC;
```

---

#### 4. `TOP_PRODUCTS_BY_PRICE_DESC`
* **Câu hỏi mẫu:** "Top 5 sản phẩm đắt nhất", "5 linh kiện có giá cao nhất"
* **Intent:** `TOP_PRODUCTS_BY_PRICE_DESC`
* **Thực thể trích xuất:**
  * `limit`: `5`
  * `order`: `DESC`
* **Giải thích luật:** Nhận diện "top [N]" và cụm từ "đắt nhất / giá cao nhất" $\rightarrow$ `ORDER BY gia_niem_yet DESC LIMIT N`.
* **SQL Chuẩn:**
```sql
SELECT ten, gia_niem_yet 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet DESC 
LIMIT 5;
```

---

#### 5. `TOP_PRODUCTS_BY_PRICE_ASC`
* **Câu hỏi mẫu:** "Top 10 linh kiện rẻ nhất", "10 sản phẩm giá thấp nhất"
* **Intent:** `TOP_PRODUCTS_BY_PRICE_ASC`
* **Thực thể trích xuất:**
  * `limit`: `10`
  * `order`: `ASC`
* **Giải thích luật:** Nhận diện "top [N]" và cụm từ "rẻ nhất / giá thấp nhất" $\rightarrow$ `ORDER BY gia_niem_yet ASC LIMIT N`.
* **SQL Chuẩn:**
```sql
SELECT ten, gia_niem_yet 
FROM san_pham 
WHERE dang_kinh_doanh = TRUE 
ORDER BY gia_niem_yet ASC 
LIMIT 10;
```

---

#### 6. `COUNT_ORDERS`
* **Câu hỏi mẫu:** "Đếm tổng số đơn hàng của cửa hàng", "Cửa hàng có bao nhiêu đơn hàng?"
* **Intent:** `COUNT_ORDERS`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện cụm từ "đếm số đơn hàng", "tổng số đơn hàng", "bao nhiêu đơn" $\rightarrow$ hàm `COUNT(*)`.
* **SQL Chuẩn:**
```sql
SELECT COUNT(*) AS tong_so_don 
FROM don_hang;
```

---

#### 7. `ORDERS_BY_STATUS`
* **Câu hỏi mẫu:** "Danh sách các đơn hàng đã hủy", "Những đơn hàng bị hủy", "Đơn nào đã hủy?"
* **Intent:** `ORDERS_BY_STATUS`
* **Thực thể trích xuất:**
  * `status`: `'da_huy'`
* **Giải thích luật:** Nhận diện từ khóa trạng thái "đã hủy" $\rightarrow$ lọc cột `trang_thai = 'da_huy'`.
* **SQL Chuẩn:**
```sql
SELECT id, ngay_dat, kenh_ban, tong_tien 
FROM don_hang 
WHERE trang_thai = 'da_huy' 
ORDER BY ngay_dat DESC 
LIMIT 20;
```

---

### CẤP ĐỘ 2: TRUNG BÌNH (JOIN 2 Bảng - Gom nhóm & Cảnh báo)

#### 8. `FILTER_BY_CATEGORY`
* **Câu hỏi mẫu:** "Liệt kê tất cả card màn hình VGA", "Danh sách CPU", "Tìm các loại bàn phím"
* **Intent:** `FILTER_BY_CATEGORY`
* **Thực thể trích xuất:**
  * `category_name`: `VGA`
* **Giải thích luật:** Trích xuất tên danh mục trong từ điển (CPU, RAM, VGA, Mainboard...) $\rightarrow$ `JOIN danh_muc`.
* **SQL Chuẩn:**
```sql
SELECT sp.id, sp.ten, dm.ten AS danh_muc, sp.gia_niem_yet 
FROM san_pham sp 
JOIN danh_muc dm ON sp.danh_muc_id = dm.id 
WHERE dm.ten ILIKE '%VGA%';
```

---

#### 9. `FILTER_BY_BRAND`
* **Câu hỏi mẫu:** "Tìm các sản phẩm của hãng ASUS", "Linh kiện thương hiệu Corsair", "Sản phẩm MSI"
* **Intent:** `FILTER_BY_BRAND`
* **Thực thể trích xuất:**
  * `brand_name`: `ASUS`
* **Giải thích luật:** Trích xuất tên hãng (ASUS, MSI, Intel, AMD, Corsair...) $\rightarrow$ `JOIN thuong_hieu`.
* **SQL Chuẩn:**
```sql
SELECT sp.id, sp.ten, th.ten AS thuong_hieu, sp.gia_niem_yet 
FROM san_pham sp 
JOIN thuong_hieu th ON sp.thuong_hieu_id = th.id 
WHERE th.ten ILIKE '%ASUS%';
```

---

#### 10. `LOW_STOCK`
* **Câu hỏi mẫu:** "Những sản phẩm nào sắp hết hàng trong kho?", "Cảnh báo tồn kho thấp", "Sản phẩm dưới mức tồn tối thiểu"
* **Intent:** `LOW_STOCK`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện từ khóa "hết hàng", "tồn kho thấp", "sắp hết" $\rightarrow$ so sánh `so_luong_ton <= muc_ton_toi_thieu`.
* **SQL Chuẩn:**
```sql
SELECT sp.ten, tk.so_luong_ton, tk.muc_ton_toi_thieu 
FROM san_pham sp 
JOIN ton_kho tk ON sp.id = tk.san_pham_id 
WHERE tk.so_luong_ton <= tk.muc_ton_toi_thieu 
ORDER BY tk.so_luong_ton ASC;
```

---

#### 11. `ORDERS_COUNT_BY_STATUS`
* **Câu hỏi mẫu:** "Thống kê số lượng đơn hàng theo từng trạng thái", "Số đơn theo trạng thái"
* **Intent:** `ORDERS_COUNT_BY_STATUS`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện yêu cầu thống kê đơn theo "trạng thái" $\rightarrow$ `GROUP BY trang_thai`.
* **SQL Chuẩn:**
```sql
SELECT trang_thai, COUNT(*) AS so_don 
FROM don_hang 
GROUP BY trang_thai 
ORDER BY so_don DESC;
```

---

#### 12. `ORDERS_BY_CHANNEL`
* **Câu hỏi mẫu:** "Thống kê số đơn và doanh thu theo từng kênh bán", "Doanh thu theo kênh bán hàng"
* **Intent:** `ORDERS_BY_CHANNEL`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện yêu cầu phân tích theo "kênh bán" (cửa hàng, website, shopee, facebook) trên đơn hoàn thành.
* **SQL Chuẩn:**
```sql
SELECT kenh_ban, COUNT(*) AS so_don, SUM(tong_tien) AS tong_doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh' 
GROUP BY kenh_ban 
ORDER BY tong_doanh_thu DESC;
```

---

#### 13. `PAYMENT_METHODS_STATS`
* **Câu hỏi mẫu:** "Khách hàng hay thanh toán qua những phương thức nào nhất?", "Thống kê hình thức thanh toán"
* **Intent:** `PAYMENT_METHODS_STATS`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện "phương thức thanh toán / hình thức trả tiền" $\rightarrow$ `GROUP BY phuong_thuc` trên bảng `thanh_toan`.
* **SQL Chuẩn:**
```sql
SELECT phuong_thuc, COUNT(*) AS so_lan, SUM(so_tien) AS tong_tien 
FROM thanh_toan 
WHERE trang_thai = 'da_thanh_toan' 
GROUP BY phuong_thuc 
ORDER BY so_lan DESC;
```

---

#### 14. `CUSTOMERS_BY_CITY`
* **Câu hỏi mẫu:** "Thống kê số lượng khách hàng theo từng tỉnh thành", "Khách hàng phân bố ở tỉnh nào nhiều nhất?"
* **Intent:** `CUSTOMERS_BY_CITY`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện "khách hàng theo tỉnh thành" $\rightarrow$ `JOIN dia_chi` và `GROUP BY tinh_thanh`.
* **SQL Chuẩn:**
```sql
SELECT dc.tinh_thanh, COUNT(DISTINCT kh.id) AS so_khach 
FROM khach_hang kh 
JOIN dia_chi dc ON kh.id = dc.khach_hang_id 
GROUP BY dc.tinh_thanh 
ORDER BY so_khach DESC;
```

---

### CẤP ĐỘ 3: NÂNG CAO (JOIN 3 Bảng - Phân tích kinh doanh & Xếp hạng phức tạp)

#### 15. `BEST_SELLING_PRODUCTS`
* **Câu hỏi mẫu:** "Top 5 sản phẩm bán chạy nhất của cửa hàng", "Những sản phẩm bán được nhiều nhất"
* **Intent:** `BEST_SELLING_PRODUCTS`
* **Thực thể trích xuất:**
  * `limit`: `5`
* **Giải thích luật:** Nhận diện "bán chạy nhất" $\rightarrow$ `JOIN chi_tiet_don_hang` tính `SUM(so_luong)` trên các đơn `hoan_thanh`.
* **SQL Chuẩn:**
```sql
SELECT sp.id, sp.ten, SUM(ct.so_luong) AS tong_da_ban 
FROM chi_tiet_don_hang ct 
JOIN don_hang dh ON ct.don_hang_id = dh.id 
JOIN san_pham sp ON ct.san_pham_id = sp.id 
WHERE dh.trang_thai = 'hoan_thanh' 
GROUP BY sp.id, sp.ten 
ORDER BY tong_da_ban DESC 
LIMIT 5;
```

---

#### 16. `TOP_SPENDING_CUSTOMERS`
* **Câu hỏi mẫu:** "Top 5 khách hàng mua nhiều tiền nhất", "Khách hàng VIP mua nhiều nhất"
* **Intent:** `TOP_SPENDING_CUSTOMERS`
* **Thực thể trích xuất:**
  * `limit`: `5`
* **Giải thích luật:** Nhận diện "khách hàng mua nhiều tiền nhất / khách VIP" $\rightarrow$ `JOIN don_hang` tính `SUM(tong_tien)`.
* **SQL Chuẩn:**
```sql
SELECT kh.id, kh.ho_ten, kh.so_dien_thoai, SUM(dh.tong_tien) AS tong_chi_tieu 
FROM khach_hang kh 
JOIN don_hang dh ON kh.id = dh.khach_hang_id 
WHERE dh.trang_thai = 'hoan_thanh' 
GROUP BY kh.id, kh.ho_ten, kh.so_dien_thoai 
ORDER BY tong_chi_tieu DESC 
LIMIT 5;
```

---

#### 17. `SALES_BY_MONTH`
* **Câu hỏi mẫu:** "Thống kê doanh thu theo từng tháng trong năm 2025", "Doanh thu năm 2025 theo tháng"
* **Intent:** `SALES_BY_MONTH`
* **Thực thể trích xuất:**
  * `year`: `2025`
* **Giải thích luật:** Nhận diện "doanh thu theo tháng" và năm `2025` $\rightarrow$ `GROUP BY TO_CHAR(ngay_dat, 'YYYY-MM')`.
* **SQL Chuẩn:**
```sql
SELECT TO_CHAR(ngay_dat, 'YYYY-MM') AS thang, COUNT(*) AS so_don, SUM(tong_tien) AS doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh' AND EXTRACT(YEAR FROM ngay_dat) = 2025 
GROUP BY TO_CHAR(ngay_dat, 'YYYY-MM') 
ORDER BY thang ASC;
```

---

#### 18. `EMPLOYEE_PERFORMANCE`
* **Câu hỏi mẫu:** "Doanh số bán hàng của từng nhân viên", "Nhân viên nào bán được nhiều tiền nhất?"
* **Intent:** `EMPLOYEE_PERFORMANCE`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện "doanh số / hiệu quả nhân viên" $\rightarrow$ `JOIN nhan_vien` tính tổng tiền đơn hoàn thành.
* **SQL Chuẩn:**
```sql
SELECT nv.id, nv.ho_ten, nv.chuc_vu, COUNT(dh.id) AS so_don_ban, SUM(dh.tong_tien) AS tong_doanh_so 
FROM nhan_vien nv 
JOIN don_hang dh ON nv.id = dh.nhan_vien_id 
WHERE dh.trang_thai = 'hoan_thanh' 
GROUP BY nv.id, nv.ho_ten, nv.chuc_vu 
ORDER BY tong_doanh_so DESC;
```

---

#### 19. `TOTAL_REVENUE`
* **Câu hỏi mẫu:** "Tổng doanh thu của tất cả đơn hàng đã hoàn thành", "Cửa hàng kiếm được bao nhiêu tiền doanh thu?"
* **Intent:** `TOTAL_REVENUE`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện "tổng doanh thu", "tổng tiền kiếm được" $\rightarrow$ `SUM(tong_tien)` trên các đơn `hoan_thanh`.
* **SQL Chuẩn:**
```sql
SELECT SUM(tong_tien) AS tong_doanh_thu 
FROM don_hang 
WHERE trang_thai = 'hoan_thanh';
```

---

#### 20. `SUPPLIER_PURCHASE_TOTAL`
* **Câu hỏi mẫu:** "Tổng tiền nhập hàng từ các nhà cung cấp", "Chi phí nhập hàng theo từng nhà cung cấp"
* **Intent:** `SUPPLIER_PURCHASE_TOTAL`
* **Thực thể trích xuất:** Không
* **Giải thích luật:** Nhận diện "tiền nhập hàng / nhà cung cấp" $\rightarrow$ `JOIN phieu_nhap` và `GROUP BY nha_cung_cap`.
* **SQL Chuẩn:**
```sql
SELECT ncc.id, ncc.ten, COUNT(pn.id) AS so_phieu_nhap, SUM(pn.tong_tien) AS tong_tien_nhap 
FROM nha_cung_cap ncc 
JOIN phieu_nhap pn ON ncc.id = pn.nha_cung_cap_id 
GROUP BY ncc.id, ncc.ten 
ORDER BY tong_tien_nhap DESC;
```
