-- ==============================================================================
-- KỊCH BẢN THAO TÁC DEMO THỰC HÀNH BẢO VỆ TIỂU LUẬN CUỐI KỲ
-- MÔN HỌC: QUẢN TRỊ CƠ SỞ DỮ LIỆU (POSTGRESQL)
-- ĐỀ TÀI: HỆ THỐNG TRUY VẤN CSDL BẰNG TIẾNG VIỆT & BỘ 5 AI QUẢN TRỊ LINH KIỆN
-- CSDL: LinhKien_DB | Schema: "LinhKien"
-- ==============================================================================
-- HƯỚNG DẪN DÀNH CHO SINH VIÊN BẢO VỆ:
-- 1. Mở công cụ pgAdmin 4 hoặc DBeaver, kết nối vào database "LinhKien_DB".
-- 2. Mở Query Tool (Cửa sổ soạn thảo SQL).
-- 3. Sao chép và bấm chạy (F5 hoặc Ctrl+Enter) từng khối lệnh theo thứ tự bên dưới.
-- 4. Mỗi phần đều có lời thuyết minh mẫu để bạn trình bày tự tin trước Thầy Cô.
-- ==============================================================================

-- THIẾT LẬP MÔI TRƯỜNG LÀM VIỆC BAN ĐẦU
SET search_path TO "LinhKien", public;


-- ==============================================================================
-- PHẦN 1: DEMO KHỞI TẠO VÀ RÀNG BUỘC TOÀN VẸN DỮ LIỆU (FAIL-SAFE DEMO)
-- Mục tiêu: Chứng minh CSDL có đầy đủ ràng buộc chặt chẽ và cơ chế Fail-Safe.
-- Khi có dữ liệu bẩn / thao tác sai, PostgreSQL sẽ CHẶN ĐỨNG và BÁO LỖI ĐỎ.
-- ==============================================================================

-- [Bước 1.1] Xem tổng quan 14 bảng dữ liệu và 1 bảng audit trong schema "LinhKien"
-- Lời nói với Thầy: "Thưa Thầy, CSDL của nhóm em gồm 14 bảng nghiệp vụ chuẩn hóa 3NF và 1 bảng kiểm toán log giá."
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'LinhKien'
ORDER BY table_name;


-- [Bước 1.2 - BẮT BUỘC] Thử nghiệm cố tình nhập SAI định dạng Số điện thoại (Regex Constraint)
-- Lời nói với Thầy: "Bây giờ em sẽ cố tình INSERT một khách hàng có số điện thoại sai chuẩn (12345678) để chứng minh ràng buộc Regex bảo vệ dữ liệu."
-- KẾT QUẢ KỲ VỌNG: PostgreSQL quăng thông báo LỖI ĐỎ: 
-- "new row for relation "khach_hang" violates check constraint "chk_khach_hang_sdt""
INSERT INTO khach_hang (ho_ten, email, so_dien_thoai, gioi_tinh, ngay_dang_ky)
VALUES ('Nguyễn Văn Lỗi', 'loi_sdt@gmail.com', '12345678', 'nam', CURRENT_DATE);


-- [Bước 1.3 - BẮT BUỘC] Thử nghiệm cố tình nhập SAI định dạng Email
-- Lời nói với Thầy: "Tương tự, nếu nhân viên nhập email sai định dạng không có @ hoặc tên miền, hệ thống sẽ chặn ngay."
-- KẾT QUẢ KỲ VỌNG: PostgreSQL quăng thông báo LỖI ĐỎ: 
-- "new row for relation "khach_hang" violates check constraint "chk_khach_hang_email""
INSERT INTO khach_hang (ho_ten, email, so_dien_thoai, gioi_tinh, ngay_dang_ky)
VALUES ('Trần Thị Lỗi', 'email_nay_khong_hop_le', '0912345678', 'nu', CURRENT_DATE);


-- [Bước 1.4 - BẮT BUỘC] Thử nghiệm cố tình nhập GIÁ TIỀN ÂM
-- Lời nói với Thầy: "Khi nhập sản phẩm mới, nếu giá bán niêm yết bị nhập số âm, ràng buộc CHECK sẽ từ chối."
-- KẾT QUẢ KỲ VỌNG: PostgreSQL quăng thông báo LỖI ĐỎ: 
-- "new row for relation "san_pham" violates check constraint "san_pham_gia_niem_yet_check""
INSERT INTO san_pham (ma_sku, ten, danh_muc_id, thuong_hieu_id, gia_niem_yet, gia_von)
VALUES ('TEST-SKU-AM', 'Sản phẩm lỗi giá âm', 1, 1, -500000, 100000);


-- [Bước 1.5 - BẮT BUỘC] Thử nghiệm XÓA dữ liệu cha đang bị ràng buộc Khóa ngoại (RESTRICT)
-- Lời nói với Thầy: "Em thử xóa danh mục CPU (id = 1) khi các sản phẩm CPU vẫn đang liên kết."
-- KẾT QUẢ KỲ VỌNG: PostgreSQL quăng thông báo LỖI ĐỎ: 
-- "update or delete on table "danh_muc" violates foreign key constraint on table "san_pham""
DELETE FROM danh_muc WHERE id = 1;


-- [Bước 1.6 - ĐIỂM CỘNG XUẤT SẮC] Thử nghiệm TRIGGER chặn xuất kho khi KHÔNG ĐỦ HÀNG TỒN
-- Lời nói với Thầy: "Em đã lập trình Trigger trg_tru_ton_kho_khi_giao. Khi đơn hàng chuyển sang 'dang_giao' mà kho không đủ hàng, Trigger sẽ RAISE EXCEPTION lỗi đỏ để chống bán âm kho."
DO $$
DECLARE
    v_don_id INT;
BEGIN
    -- Tạo đơn hàng tạm
    INSERT INTO don_hang (khach_hang_id, ngay_dat, trang_thai, kenh_ban, tong_tien)
    VALUES (1, NOW(), 'moi', 'cua_hang', 0) RETURNING id INTO v_don_id;

    -- Thêm món hàng với số lượng 999.999 cái (vượt xa tồn kho)
    INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia)
    VALUES (v_don_id, 1, 999999, 2400000);

    -- Đổi trạng thái sang 'dang_giao' -> TRIGGER KÍCH HOẠT VÀ TUNG LỖI ĐỎ!
    UPDATE don_hang SET trang_thai = 'dang_giao' WHERE id = v_don_id;
END $$;
-- KẾT QUẢ KỲ VỌNG: PostgreSQL báo lỗi đỏ:
-- "Lỗi xuất kho: Sản phẩm ID 1 không đủ số lượng tồn! Thao tác bị hủy."



-- ==============================================================================
-- PHẦN 2: BẢO MẬT PHÂN QUYỀN RBAC, RLS VÀ CỘT NHẠY CẢM (ROLE-PLAYING DEMO)
-- Mục tiêu: Đóng vai nhân viên bán hàng để chứng minh:
-- 1. Bị chặn truy cập cột nhạy cảm 'gia_von' (Column-Level Security).
-- 2. Chỉ nhìn thấy đơn hàng của chính mình (Row-Level Security).
-- ==============================================================================

-- [Bước 2.1] Chuyển đổi ngữ cảnh sang Role nhân viên bán hàng
-- Lời nói với Thầy: "Bây giờ em dùng lệnh SET ROLE để đóng vai một nhân viên bán hàng (nhan_vien_ban_hang)."
SET ROLE nhan_vien_ban_hang;
SELECT CURRENT_USER; -- Hiển thị 'nhan_vien_ban_hang'


-- [Bước 2.2 - COLUMN-LEVEL SECURITY] Nhân viên bán hàng xem thông tin sản phẩm bình thường
-- Lời nói với Thầy: "Nhân viên bán hàng được phép xem mã, tên, giá niêm yết và thông số kỹ thuật để tư vấn khách."
-- KẾT QUẢ: Chạy thành công, hiển thị 5 sản phẩm.
SELECT id, ma_sku, ten, gia_niem_yet, thong_so_ky_thuat 
FROM san_pham 
LIMIT 5;


-- [Bước 2.3 - COLUMN-LEVEL PRIVILEGE BỊ CHẶN] Nhân viên cố tình xem 'gia_von' của sản phẩm
-- Lời nói với Thầy: "Tuy nhiên, để bảo mật bí mật kinh doanh, cột 'gia_von' đã bị REVOKE. Khi nhân viên cố tình SELECT, hệ thống chặn ngay."
-- KẾT QUẢ KỲ VỌNG: PostgreSQL quăng thông báo LỖI ĐỎ: 
-- "permission denied for column "gia_von" of relation "san_pham""
--   (PostgreSQL 16+ có thể ghi gọn là "permission denied for table san_pham" — vẫn là bị chặn cột gia_von)
SELECT id, ten, gia_von FROM san_pham;


-- [Bước 2.4 - ROW-LEVEL SECURITY (RLS)] Role nhóm chung KHÔNG gắn với nhân viên nào
-- Lời nói với Thầy: "nhan_vien_ban_hang chỉ là role NHÓM, không phải một nhân viên cụ thể,
--   nên chính sách RLS p_don_hang_nhan_vien trả về 0 dòng để chống lộ lọt."
-- KẾT QUẢ: 0 dòng.
SELECT COUNT(*) AS "Số đơn hàng nhìn thấy" FROM don_hang;


-- [Bước 2.5 - CHỨNG MINH ĐÃ VÁ LỖ HỔNG] Thử "tự khai" mình là nhân viên 2 bằng biến phiên
-- Lời nói với Thầy: "Bản cũ lọc RLS theo biến app.current_nhan_vien_id — ai cũng tự SET được nên có thể
--   giả làm nhân viên khác. Bản mới lọc theo CHÍNH TÀI KHOẢN đăng nhập (current_user), nên SET biến vô tác dụng."
SET app.current_nhan_vien_id = '2';
-- KẾT QUẢ: vẫn 0 dòng.
SELECT COUNT(*) AS "Vẫn 0 dòng dù tự khai là NV 2" FROM don_hang;
RESET app.current_nhan_vien_id;
RESET ROLE;


-- [Bước 2.6 - ROW-LEVEL SECURITY (RLS)] Đăng nhập bằng tài khoản riêng của Nhân viên ID = 2
-- Lời nói với Thầy: "Mỗi nhân viên có role riêng nv_<id> (bảng ánh xạ tai_khoan_nhan_vien).
--   RLS gọi hàm fn_nhan_vien_cua_role(current_user) để biết đây là ai, rồi chỉ hiện đơn của người đó."
SET ROLE nv_2;
SELECT CURRENT_USER;  -- nv_2
-- KẾT QUẢ: chỉ thấy đơn của nhân viên 2 (566 đơn trên bộ dữ liệu mẫu).
SELECT COUNT(*) AS "Đơn của nhân viên 2" FROM don_hang;
SELECT id, khach_hang_id, nhan_vien_id, ngay_dat, trang_thai, tong_tien
FROM don_hang
LIMIT 5;

-- Thử giả làm nhân viên 3 -> KHÔNG được, số đơn giữ nguyên
SET app.current_nhan_vien_id = '3';
SELECT COUNT(*) AS "Vẫn chỉ đơn của NV 2" FROM don_hang;
RESET app.current_nhan_vien_id;

-- RLS áp dụng cả bảng con: chi tiết đơn và thanh toán cũng chỉ của NV 2
SELECT COUNT(*) AS "Chi tiết đơn của NV 2" FROM chi_tiet_don_hang;
SELECT COUNT(*) AS "Thanh toán của NV 2" FROM thanh_toan;
-- Không lách được qua VIEW (security_invoker): bảng xếp hạng doanh thu chỉ có số liệu của chính NV 2,
-- các nhân viên khác hiện 0 đơn / 0 đồng. Materialized view doanh thu cửa hàng bị từ chối.
SELECT * FROM v_doanh_thu_nhan_vien;
RESET ROLE;


-- [Bước 2.7 - ROW-LEVEL SECURITY (RLS)] Đăng nhập bằng tài khoản Nhân viên ID = 3
-- Lời nói với Thầy: "Đổi sang nv_3, đơn của nhân viên 2 biến mất, chỉ còn đơn của nhân viên 3."
SET ROLE nv_3;
-- KẾT QUẢ: chỉ thấy đơn của nhân viên 3 (467 đơn trên bộ dữ liệu mẫu).
SELECT COUNT(*) AS "Đơn của nhân viên 3" FROM don_hang;
RESET ROLE;


-- [Bước 2.8 - BẢO VỆ BẢNG TÀI KHOẢN] Role chatbot không đọc được mật khẩu
-- Lời nói với Thầy: "Mật khẩu web lưu bằng bcrypt. Role chỉ đọc của chatbot bị REVOKE bảng app_users,
--   chỉ được gọi hàm fn_xac_thuc_nguoi_dung — hàm trả về đúng/sai, không bao giờ trả hash."
SET ROLE text2sql_readonly;
-- KẾT QUẢ KỲ VỌNG: LỖI ĐỎ "permission denied for table app_users"
SELECT username, password_hash FROM app_users;
RESET ROLE;
SET ROLE text2sql_readonly;
-- KẾT QUẢ: 1 dòng (đúng mật khẩu) — không có cột password_hash
SELECT * FROM fn_xac_thuc_nguoi_dung('admin', 'admin123');
-- KẾT QUẢ: 0 dòng (sai mật khẩu)
SELECT * FROM fn_xac_thuc_nguoi_dung('admin', 'doan_bua');
RESET ROLE;


-- [Bước 2.9] Quay trở lại quyền quản trị
-- Lời nói với Thầy: "Role quản lý / chatbot (manager_readonly, text2sql_readonly) có chính sách đọc toàn bộ,
--   nên báo cáo tổng hợp vẫn thấy đủ 8.000 đơn hàng."
SET ROLE manager_readonly;
-- KẾT QUẢ: Hiển thị đầy đủ 8.000 đơn hàng!
SELECT COUNT(*) AS "Toàn bộ đơn hàng (role quản lý)" FROM don_hang;
RESET ROLE;




-- ==============================================================================
-- PHẦN 3: TỐI ƯU HÓA HIỆU NĂNG VÀ CHẨN ĐOÁN CHỈ MỤC (PERFORMANCE DEMO)
-- Mục tiêu: Dùng EXPLAIN ANALYZE minh chứng thuật toán Seq Scan vs Index Scan,
-- đo lường chi phí Cost và thời gian thực thi giảm rõ rệt sau khi tối ưu.
-- ==============================================================================

-- [Bước 3.1] Xóa tạm Index trên cột ngày đặt để xem tình trạng CHƯA TỐI ƯU
DROP INDEX IF EXISTS idx_don_hang_ngay_dat;

-- [Bước 3.2] Chạy EXPLAIN (ANALYZE, BUFFERS) trước khi có Index
-- Lời nói với Thầy: "Thưa Thầy, khi chưa có chỉ mục, câu lệnh lọc theo khoảng thời gian phải duyệt tuần tự toàn bộ 8.000 dòng (Seq Scan on don_hang)."
-- KẾT QUẢ: Nhìn vào kết quả thấy dòng "Seq Scan on don_hang", Cost ~ 240.00, Time ~ 3.5ms.
EXPLAIN (ANALYZE, BUFFERS) 
SELECT id, khach_hang_id, ngay_dat, tong_tien 
FROM don_hang 
WHERE ngay_dat >= '2026-06-01' AND ngay_dat <= '2026-06-30';


-- [Bước 3.3] Thực thi tạo Chỉ mục B-Tree (hoặc dùng AI 4 trên Web sinh ra)
-- Lời nói với Thầy: "Em tạo chỉ mục B-Tree trên cột ngay_dat để tối ưu các truy vấn lọc thời gian."
CREATE INDEX idx_don_hang_ngay_dat ON don_hang(ngay_dat);

-- [Bước 3.4] Chạy lại EXPLAIN ANALYZE sau khi đã có Index
-- Lời nói với Thầy: "Sau khi tạo Index, thuật toán chuyển sang Bitmap Index Scan / Index Scan, số block bộ nhớ phải đọc giảm mạnh và thời gian thực thi tối ưu rõ rệt."
-- KẾT QUẢ: Xuất hiện "Bitmap Index Scan on idx_don_hang_ngay_dat", thời gian giảm xuống còn ~0.3ms - 0.7ms (nhanh gấp 5 - 10 lần)!
EXPLAIN (ANALYZE, BUFFERS) 
SELECT id, khach_hang_id, ngay_dat, tong_tien 
FROM don_hang 
WHERE ngay_dat >= '2026-06-01' AND ngay_dat <= '2026-06-30';



-- ==============================================================================
-- PHẦN 4: ĐIỂM NHẤN CÔNG NGHỆ: NoSQL JSONB, VIEWS & TRIGGERS TỰ ĐỘNG
-- Mục tiêu: Trình diễn các kỹ thuật cao cấp gồm bóc tách JSONB (toán tử ->>),
-- GIN Index NoSQL, Materialized View với Concurrent Refresh, và Trigger Audit.
-- ==============================================================================

-- [Bước 4.1 - ĐIỂM NHẤN NoSQL JSONB] Bóc tách thuộc tính bán cấu trúc từ cột JSONB
-- Lời nói với Thầy: "Mỗi linh kiện có thông số khác nhau, nhóm em dùng cột thong_so_ky_thuat JSONB và toán tử ->> để trích xuất dữ liệu không cố định."
-- Truy vấn: Tìm các CPU có Socket là LGA1700 và số Cores >= 8:
SELECT 
    ten AS "Tên CPU",
    thong_so_ky_thuat->>'socket' AS "Socket",
    (thong_so_ky_thuat->>'cores')::INT AS "Số Nhân",
    thong_so_ky_thuat->>'tdp' AS "Điện Năng (TDP)",
    gia_niem_yet AS "Giá Niêm Yết"
FROM san_pham
WHERE danh_muc_id = 1 
  AND thong_so_ky_thuat->>'socket' = 'LGA1700'
ORDER BY "Số Nhân" DESC;


-- [Bước 4.2 - GIN INDEX TRÊN JSONB] Truy vấn NoSQL với toán tử chứa '@>' và GIN Index
-- Lời nói với Thầy: "Nhóm em đã đánh chỉ mục GIN trên cột JSONB. Khi truy vấn tìm các bo mạch chủ có tích hợp Wifi bằng toán tử @>, PostgreSQL dùng ngay Bitmap Index Scan trên GIN index."
EXPLAIN ANALYZE 
SELECT id, ten, thong_so_ky_thuat 
FROM san_pham 
WHERE thong_so_ky_thuat @> '{"wifi": true}';


-- [Bước 4.3 - VIEWS TIÊU CHUẨN] View tổng hợp doanh số nhân viên
-- Lời nói với Thầy: "View v_doanh_thu_nhan_vien che giấu cấu trúc phức tạp, cung cấp dữ liệu sẵn cho ban quản lý."
SELECT * FROM v_doanh_thu_nhan_vien 
ORDER BY "Tổng doanh số (VNĐ)" DESC;


-- [Bước 4.4 - MATERIALIZED VIEW & REFRESH CONCURRENTLY]
-- Lời nói với Thầy: "Bảng vật lý mv_thong_ke_doanh_thu_thang lưu sẵn số liệu doanh thu từng tháng. Nhờ Unique Index, hệ thống có thể làm mới dữ liệu nền bằng lệnh REFRESH CONCURRENTLY mà không khóa bảng."
SELECT * FROM mv_thong_ke_doanh_thu_thang 
ORDER BY thang DESC 
LIMIT 6;

-- Thực hiện làm mới đồng thời (Concurrent Refresh)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_thong_ke_doanh_thu_thang;


-- [Bước 4.5 - TRIGGER TỰ ĐỘNG TÍNH TIỀN ĐƠN HÀNG]
-- Lời nói với Thầy: "Khi nhân viên thêm/xóa chi tiết đơn hàng, Trigger trg_cap_nhat_tong_tien tự động tính toán lại tổng tiền của đơn hàng."
DO $$
DECLARE
    v_test_don_id INT;
BEGIN
    -- 1. Tạo đơn hàng rỗng (tổng tiền = 0)
    INSERT INTO don_hang (khach_hang_id, ngay_dat, trang_thai, kenh_ban, tong_tien)
    VALUES (1, NOW(), 'moi', 'cua_hang', 0) RETURNING id INTO v_test_don_id;
    
    RAISE NOTICE 'Đơn hàng mới tạo (ID: %), Tổng tiền ban đầu: 0 VNĐ', v_test_don_id;

    -- 2. Thêm món 1: 2 CPU i3-12100F (2 x 2.400.000 = 4.800.000 VNĐ)
    INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia)
    VALUES (v_test_don_id, 1, 2, 2400000);

    -- 3. Thêm món 2: 1 RAM 16GB (1 x 1.200.000 = 1.200.000 VNĐ, giảm giá 200.000 VNĐ)
    INSERT INTO chi_tiet_don_hang (don_hang_id, san_pham_id, so_luong, don_gia, giam_gia)
    VALUES (v_test_don_id, 15, 1, 1200000, 200000);

    -- Kiểm tra tổng tiền đơn hàng đã tự động được Trigger cập nhật chưa:
    RAISE NOTICE 'Tổng tiền sau Trigger tự tính: % VNĐ (Kỳ vọng: 5.800.000 VNĐ)', 
        (SELECT tong_tien FROM don_hang WHERE id = v_test_don_id);
END $$;


-- [Bước 4.6 - TRIGGER KIỂM TOÁN LỊCH SỬ THAY ĐỔI GIÁ (AUDIT LOG)]
-- Lời nói với Thầy: "Bất kỳ khi nào giá niêm yết của linh kiện thay đổi, Trigger trg_ghi_log_thay_doi_gia tự động lưu vào bảng kiểm toán lich_su_thay_doi_gia."
-- Cập nhật giá sản phẩm ID=1:
UPDATE san_pham 
SET gia_niem_yet = 2550000 
WHERE id = 1;

-- Xem nhật ký kiểm toán vừa tự động sinh ra:
SELECT * FROM lich_su_thay_doi_gia 
WHERE san_pham_id = 1 
ORDER BY ngay_thay_doi DESC 
LIMIT 3;



-- ==============================================================================
-- PHẦN 5: TRÌNH DIỄN HỆ THỐNG 5 AI TRÊN GIAO DIỆN WEB STREAMLIT
-- Hướng dẫn: Mở trình duyệt Web tại địa chỉ http://localhost:8501
-- (Chạy bằng lệnh: & D:\Python_Dev\python.exe "ai_service/web_app.py")
-- ==============================================================================

-- [Tab 1: AI 1 & AI 2 - Tự động định tuyến câu hỏi]
-- Thử nghiệm 1 (AI 1 CSDL): Gõ "Top 5 sản phẩm đắt nhất" hoặc "Doanh số theo tháng"
-- -> Hệ thống tự động kích hoạt AI 1 (Rule-Based NLP), sinh SQL và trả về bảng dữ liệu.
-- Thử nghiệm 2 (AI 2 Phần cứng): Gõ "PC chơi game nặng và stream" hoặc "Cấu hình đồ họa render"
-- -> Hệ thống tự động kích hoạt AI 2 (TF-IDF & Knowledge Graph), tính độ tương đồng Cosine % và đề xuất linh kiện.

-- [Tab 2: AI 3 - Giám sát An ninh Zero-Trust]
-- Bấm chọn "Kịch bản 2: Nghi vấn trộm dữ liệu (Ban đêm)" hoặc "Kịch bản 3: SQL Injection"
-- -> AI 3 chấm điểm rủi ro (Risk Score) theo thời gian thực và tự động kích hoạt Dynamic RLS hoặc chặn đứng truy vấn.

-- [Tab 3: AI 4 - Cố vấn Lập chỉ mục thông minh (Smart Index Advisor)]
-- Nhập câu truy vấn SQL bất kỳ và bấm "Phân tích kế hoạch thực thi"
-- -> AI 4 duyệt cây EXPLAIN JSON bằng Decision Tree, phát hiện Seq Scan và tự sinh DDL "CREATE INDEX CONCURRENTLY".

-- [Tab 4: AI 5 - Dự báo Phân vùng tự động (Predictive Partitioning)]
-- -> Mô hình Hồi quy Tuyến tính OLS phân tích chuỗi thời gian đơn hàng thực tế (R² ~ 0.999),
-- dự báo tốc độ tăng trưởng và tự động sinh mã DDL phân vùng theo tháng cho PostgreSQL.

-- ==============================================================================
-- KẾT THÚC KỊCH BẢN DEMO
-- ==============================================================================
