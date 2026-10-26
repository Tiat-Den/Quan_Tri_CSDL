-- ==============================================================================
-- NÂNG CẤP BẢO MẬT + CHẤT LƯỢNG DỮ LIỆU + TỐI ƯU HIỆU NĂNG  (LinhKien_DB)
--
-- Vá các lỗ hổng phát hiện khi kiểm tra CSDL:
--   PHẦN A. BẢO MẬT
--     A1. RLS không thể lách: bỏ biến app.current_nhan_vien_id (người dùng tự SET được),
--         thay bằng bảng ánh xạ role -> nhân viên + hàm SECURITY DEFINER.
--         Manager và dịch vụ AI đọc toàn bộ đơn qua chính sách riêng (trước đây manager thấy 0 đơn).
--         Mở rộng RLS sang chi_tiet_don_hang và thanh_toan (trước đây nhân viên xem được chi tiết mọi đơn).
--     A2. Mật khẩu ứng dụng: bcrypt có salt (pgcrypto) thay cho SHA-256 không salt; role chỉ đọc
--         KHÔNG còn đọc được cột password_hash, đăng nhập qua hàm xác thực SECURITY DEFINER.
--   PHẦN B. RÀNG BUỘC (SẠCH - ĐÚNG): CHECK còn thiếu, regex mã SKU, mỗi khách 1 địa chỉ mặc định...
--   PHẦN C. TỐI ƯU: index cho 10 khóa ngoại, Partial / Hash / GIN pg_trgm, autovacuum,
--         phân vùng thật (Range Partitioning) cho bảng lịch sử giá, hàm làm mới báo cáo.
--   PHẦN D. SỐNG: trigger tự tính tổng tiền phiếu nhập.
--   PHẦN E. TÁI TẠO ĐỦ HỆ THỐNG: bảng backup_history / backup_size_log của AI 6 có trong script SQL.
--
-- Chạy bằng tài khoản postgres trong pgAdmin (Query Tool trên LinhKien_DB) hoặc:
--   psql -U postgres -d LinhKien_DB -f database/nang_cap_bao_mat_toi_uu.sql
-- Script chạy lại nhiều lần an toàn (idempotent). Ràng buộc mới được thêm dạng NOT VALID rồi
-- VALIDATE riêng: nếu dữ liệu cũ vi phạm, chỉ in NOTICE, dữ liệu MỚI vẫn bị chặn.
-- Sau khi chạy: chạy thêm  python database/bao_tri.py  (VACUUM ANALYZE, không chạy được trong transaction).
-- ==============================================================================
SET search_path TO "LinhKien", public;
SET client_min_messages TO notice;

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Bảng phục vụ AI 6 (trước đây chỉ được tạo lúc chạy ứng dụng -> script SQL không tái tạo đủ hệ thống)
CREATE TABLE IF NOT EXISTS "LinhKien".backup_size_log (
    id          SERIAL PRIMARY KEY,
    ngay_ghi    TIMESTAMP NOT NULL DEFAULT NOW(),
    db_size_mb  NUMERIC(12,2) NOT NULL CHECK (db_size_mb >= 0)
);
CREATE TABLE IF NOT EXISTS "LinhKien".backup_history (
    id              SERIAL PRIMARY KEY,
    thoi_gian       TIMESTAMP NOT NULL DEFAULT NOW(),
    loai_backup     VARCHAR(20) NOT NULL,
    duong_dan       TEXT NOT NULL,
    dung_luong_mb   NUMERIC(12,2),
    checksum_sha256 VARCHAR(64),
    trang_thai      VARCHAR(20) DEFAULT 'thanh_cong',
    ghi_chu         TEXT
);

-- ==============================================================================
-- PHẦN A1. ROW-LEVEL SECURITY KHÔNG THỂ LÁCH
-- ==============================================================================
-- Gỡ chính sách cũ (dựa vào biến phiên có thể tự SET) trước khi tạo lại
DROP POLICY IF EXISTS p_don_hang_nhan_vien ON "LinhKien".don_hang;

-- Bảng ánh xạ: role PostgreSQL nào là nhân viên nào (chỉ DBA ghi được)
CREATE TABLE IF NOT EXISTS "LinhKien".tai_khoan_nhan_vien (
    ten_role      NAME PRIMARY KEY,
    nhan_vien_id  INT  NOT NULL UNIQUE REFERENCES "LinhKien".nhan_vien(id)
);
COMMENT ON TABLE "LinhKien".tai_khoan_nhan_vien IS
    'Ánh xạ role đăng nhập PostgreSQL -> nhân viên; dùng cho chính sách RLS (không thể giả mạo bằng SET biến phiên)';

-- Mỗi nhân viên có một role riêng nv_<id> (NOLOGIN để demo bằng SET ROLE; cấp LOGIN + mật khẩu khi dùng thật),
-- là thành viên của nhóm quyền nhan_vien_ban_hang.
-- Đóng gói thành hàm để gọi lại sau khi sinh lại dữ liệu (sinh_du_lieu.py TRUNCATE nhan_vien CASCADE làm rỗng bảng ánh xạ)
-- hoặc khi tuyển nhân viên mới (bao_tri.py cũng gọi hàm này).
CREATE OR REPLACE FUNCTION "LinhKien".fn_dong_bo_tai_khoan_nhan_vien()
RETURNS INT
LANGUAGE plpgsql
SET search_path = "LinhKien", pg_temp
AS $$
DECLARE r RECORD; n INT := 0;
BEGIN
    FOR r IN SELECT id FROM "LinhKien".nhan_vien ORDER BY id LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nv_' || r.id) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', 'nv_' || r.id);
        END IF;
        EXECUTE format('GRANT nhan_vien_ban_hang TO %I', 'nv_' || r.id);
        INSERT INTO "LinhKien".tai_khoan_nhan_vien (ten_role, nhan_vien_id)
        VALUES ('nv_' || r.id, r.id)
        ON CONFLICT (ten_role) DO UPDATE SET nhan_vien_id = EXCLUDED.nhan_vien_id;
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;
REVOKE ALL ON FUNCTION "LinhKien".fn_dong_bo_tai_khoan_nhan_vien() FROM PUBLIC;
SELECT "LinhKien".fn_dong_bo_tai_khoan_nhan_vien();

-- Hàm tra nhân viên của một role. SECURITY DEFINER: người dùng không cần (và không có) quyền đọc bảng ánh xạ.
-- Chính sách RLS truyền current_user vào hàm: giá trị này do PostgreSQL xác định theo role đăng nhập / SET ROLE,
-- người dùng KHÔNG thể giả mạo bằng SET biến phiên như cách cũ (app.current_nhan_vien_id).
DROP FUNCTION IF EXISTS "LinhKien".fn_nhan_vien_hien_tai();
CREATE OR REPLACE FUNCTION "LinhKien".fn_nhan_vien_cua_role(p_role NAME)
RETURNS INT
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = "LinhKien", pg_temp
AS $$
    SELECT nhan_vien_id FROM "LinhKien".tai_khoan_nhan_vien WHERE ten_role = p_role;
$$;
REVOKE ALL ON FUNCTION "LinhKien".fn_nhan_vien_cua_role(NAME) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION "LinhKien".fn_nhan_vien_cua_role(NAME) TO nhan_vien_ban_hang;
-- Bảng ánh xạ chỉ DBA đọc/ghi (kể cả role chatbot cũng không cần biết role nào là nhân viên nào)
REVOKE ALL ON "LinhKien".tai_khoan_nhan_vien FROM PUBLIC, nhan_vien_ban_hang, text2sql_readonly, manager_readonly;

-- Chính sách mới cho don_hang
ALTER TABLE "LinhKien".don_hang ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_don_hang_doc_toan_bo ON "LinhKien".don_hang;
CREATE POLICY p_don_hang_nhan_vien ON "LinhKien".don_hang
    FOR SELECT TO nhan_vien_ban_hang
    USING (nhan_vien_id = "LinhKien".fn_nhan_vien_cua_role(current_user));
CREATE POLICY p_don_hang_doc_toan_bo ON "LinhKien".don_hang
    FOR SELECT TO text2sql_readonly, manager_readonly
    USING (true);

-- Chặn đường vòng qua VIEW: view thường chạy với quyền CHỦ SỞ HỮU (postgres) nên bỏ qua RLS.
-- security_invoker (PostgreSQL 15+) buộc view áp dụng quyền + RLS của NGƯỜI ĐANG TRUY VẤN.
DO $$
BEGIN
    IF current_setting('server_version_num')::int >= 150000 THEN
        EXECUTE 'ALTER VIEW "LinhKien".v_doanh_thu_nhan_vien SET (security_invoker = true)';
    ELSE
        EXECUTE 'REVOKE SELECT ON "LinhKien".v_doanh_thu_nhan_vien FROM nhan_vien_ban_hang';
    END IF;
END $$;
-- Materialized view không hỗ trợ RLS -> nhân viên bán hàng không được xem doanh thu tổng của cửa hàng
REVOKE ALL ON "LinhKien".mv_thong_ke_doanh_thu_thang FROM nhan_vien_ban_hang;

-- Mở rộng RLS: chi tiết đơn và thanh toán chỉ thấy khi thấy được đơn hàng cha
ALTER TABLE "LinhKien".chi_tiet_don_hang ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_ctdh_nhan_vien ON "LinhKien".chi_tiet_don_hang;
DROP POLICY IF EXISTS p_ctdh_doc_toan_bo ON "LinhKien".chi_tiet_don_hang;
CREATE POLICY p_ctdh_nhan_vien ON "LinhKien".chi_tiet_don_hang
    FOR SELECT TO nhan_vien_ban_hang
    USING (EXISTS (SELECT 1 FROM "LinhKien".don_hang d WHERE d.id = don_hang_id));
CREATE POLICY p_ctdh_doc_toan_bo ON "LinhKien".chi_tiet_don_hang
    FOR SELECT TO text2sql_readonly, manager_readonly
    USING (true);

ALTER TABLE "LinhKien".thanh_toan ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_tt_nhan_vien ON "LinhKien".thanh_toan;
DROP POLICY IF EXISTS p_tt_doc_toan_bo ON "LinhKien".thanh_toan;
CREATE POLICY p_tt_nhan_vien ON "LinhKien".thanh_toan
    FOR SELECT TO nhan_vien_ban_hang
    USING (EXISTS (SELECT 1 FROM "LinhKien".don_hang d WHERE d.id = don_hang_id));
CREATE POLICY p_tt_doc_toan_bo ON "LinhKien".thanh_toan
    FOR SELECT TO text2sql_readonly, manager_readonly
    USING (true);

-- ==============================================================================
-- PHẦN A2. MẬT KHẨU ỨNG DỤNG: BCRYPT + HÀM XÁC THỰC, KHÓA CỘT password_hash
-- ==============================================================================
-- Chuyển 2 tài khoản mẫu từ SHA-256 không salt sang bcrypt (chỉ khi còn đúng hash mẫu cũ).
-- Tài khoản có mật khẩu khác: ứng dụng tự nâng cấp lên bcrypt ở lần đăng nhập đúng kế tiếp.
UPDATE "LinhKien".app_users
   SET password_hash = crypt('admin123', gen_salt('bf', 10))
 WHERE username = 'admin'
   AND password_hash = encode(digest('admin123', 'sha256'), 'hex');
UPDATE "LinhKien".app_users
   SET password_hash = crypt('manager123', gen_salt('bf', 10))
 WHERE username = 'manager'
   AND password_hash = encode(digest('manager123', 'sha256'), 'hex');

-- Đổi kiểu trả về cần xóa hàm cũ (nếu chạy lại script)
DROP FUNCTION IF EXISTS "LinhKien".fn_xac_thuc_nguoi_dung(TEXT, TEXT);
-- Hàm xác thực: so khớp bcrypt (hoặc SHA-256 cũ cho tài khoản chưa chuyển đổi) BÊN TRONG CSDL,
-- trả về thông tin người dùng nhưng KHÔNG BAO GIỜ trả về hash. Chỉ đọc -> chạy được trên kết nối read-only.
CREATE OR REPLACE FUNCTION "LinhKien".fn_xac_thuc_nguoi_dung(p_username TEXT, p_password TEXT)
RETURNS TABLE (id INT, username VARCHAR, ho_ten VARCHAR, role VARCHAR, can_nang_cap_hash BOOLEAN)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = "LinhKien", public, pg_temp
AS $$
DECLARE u "LinhKien".app_users%ROWTYPE;
BEGIN
    SELECT * INTO u FROM "LinhKien".app_users a WHERE a.username = btrim(p_username) AND a.active = TRUE;
    IF NOT FOUND THEN
        -- Vẫn tốn một lần băm bcrypt để thời gian phản hồi không lộ ra "tên đăng nhập có tồn tại hay không"
        PERFORM crypt(coalesce(p_password, ''), gen_salt('bf', 10));
        RETURN;
    END IF;
    IF (u.password_hash LIKE '$2%' AND u.password_hash = crypt(p_password, u.password_hash))
       OR (u.password_hash NOT LIKE '$2%' AND u.password_hash = encode(digest(p_password, 'sha256'), 'hex')) THEN
        id := u.id; username := u.username; ho_ten := u.ho_ten; role := u.role;
        can_nang_cap_hash := (u.password_hash NOT LIKE '$2%');
        RETURN NEXT;
    END IF;
END $$;
REVOKE ALL ON FUNCTION "LinhKien".fn_xac_thuc_nguoi_dung(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION "LinhKien".fn_xac_thuc_nguoi_dung(TEXT, TEXT) TO text2sql_readonly, manager_readonly;

-- Role chỉ đọc không còn đọc được bảng tài khoản (kể cả password_hash)
REVOKE ALL ON "LinhKien".app_users FROM text2sql_readonly, manager_readonly, nhan_vien_ban_hang, PUBLIC;
COMMENT ON COLUMN "LinhKien".app_users.password_hash IS 'bcrypt có salt (pgcrypto crypt/gen_salt bf); chỉ đọc được qua hàm fn_xac_thuc_nguoi_dung';

-- Hàm kiểm tra tài khoản còn hoạt động + vai trò hiện hành (web gọi khi khôi phục phiên đăng nhập sau F5,
-- để tài khoản bị khóa/đổi vai trò mất hiệu lực ngay, không đợi token hết hạn)
CREATE OR REPLACE FUNCTION "LinhKien".fn_vai_tro_nguoi_dung(p_username TEXT)
RETURNS VARCHAR
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = "LinhKien", pg_temp
AS $$
    SELECT u.role FROM "LinhKien".app_users u WHERE u.username = p_username AND u.active = TRUE;
$$;
REVOKE ALL ON FUNCTION "LinhKien".fn_vai_tro_nguoi_dung(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION "LinhKien".fn_vai_tro_nguoi_dung(TEXT) TO text2sql_readonly, manager_readonly;

-- AI 4 cần thống kê truy vấn nhưng KHÔNG được cấp pg_read_all_stats: quyền đó cho đọc nguyên văn
-- lệnh của mọi phiên (kể cả CREATE ROLE ... PASSWORD '...' trong pg_stat_statements và câu đang chạy
-- trong pg_stat_activity). Thay vào đó: hàm SECURITY DEFINER chỉ trả về câu SELECT đã chuẩn hóa ($1, $2...).
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
REVOKE pg_read_all_stats FROM text2sql_readonly;
CREATE OR REPLACE FUNCTION "LinhKien".fn_top_truy_van(p_so_luong INT DEFAULT 5)
RETURNS TABLE (query TEXT, calls BIGINT, total_ms NUMERIC, mean_ms NUMERIC, rows BIGINT)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = "LinhKien", public, pg_temp
AS $$
BEGIN
    RETURN QUERY EXECUTE
        'SELECT s.query, s.calls, round(s.total_exec_time::numeric, 2), round(s.mean_exec_time::numeric, 2), s.rows
           FROM pg_stat_statements s
          WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            AND (s.query ILIKE ''select%'' OR s.query ILIKE ''with%'')
            AND s.query NOT ILIKE ''%pg\_%''
            AND s.query NOT ILIKE ''%password%''
            AND s.query NOT ILIKE ''%crypt(%''
            AND s.query NOT ILIKE ''%fn\_xac\_thuc%''
          ORDER BY s.total_exec_time DESC
          LIMIT $1'
        USING least(greatest(coalesce(p_so_luong, 5), 1), 50);
END $$;
REVOKE ALL ON FUNCTION "LinhKien".fn_top_truy_van(INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION "LinhKien".fn_top_truy_van(INT) TO text2sql_readonly;

-- ==============================================================================
-- PHẦN B. RÀNG BUỘC TOÀN VẸN CÒN THIẾU (SẠCH - ĐÚNG)
-- ==============================================================================
CREATE OR REPLACE FUNCTION pg_temp.them_rang_buoc(p_bang TEXT, p_ten TEXT, p_dieu_kien TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = p_ten) THEN
        EXECUTE format('ALTER TABLE "LinhKien".%I ADD CONSTRAINT %I CHECK (%s) NOT VALID', p_bang, p_ten, p_dieu_kien);
    END IF;
    BEGIN
        EXECUTE format('ALTER TABLE "LinhKien".%I VALIDATE CONSTRAINT %I', p_bang, p_ten);
        RAISE NOTICE '[OK] % trên % (đã kiểm tra cả dữ liệu cũ)', p_ten, p_bang;
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE '[CẢNH BÁO] % trên %: dữ liệu cũ vi phạm, ràng buộc vẫn chặn dữ liệu mới', p_ten, p_bang;
    END;
END $$;

-- Đơn hàng
SELECT pg_temp.them_rang_buoc('don_hang', 'chk_dh_ngay_giao_sau_ngay_dat', 'ngay_giao IS NULL OR ngay_giao >= ngay_dat');
SELECT pg_temp.them_rang_buoc('don_hang', 'chk_dh_tong_tien_khong_am', 'tong_tien >= 0');
SELECT pg_temp.them_rang_buoc('don_hang', 'chk_dh_hoan_thanh_co_ngay_giao', 'trang_thai NOT IN (''hoan_thanh'', ''tra_hang'') OR ngay_giao IS NOT NULL');
SELECT pg_temp.them_rang_buoc('don_hang', 'chk_dh_tai_quay_co_nhan_vien', 'kenh_ban <> ''cua_hang'' OR nhan_vien_id IS NOT NULL');
-- Chi tiết đơn
SELECT pg_temp.them_rang_buoc('chi_tiet_don_hang', 'chk_ctdh_don_gia_khong_am', 'don_gia >= 0');
SELECT pg_temp.them_rang_buoc('chi_tiet_don_hang', 'chk_ctdh_giam_gia_hop_le', 'giam_gia >= 0 AND giam_gia <= so_luong * don_gia');
-- Thanh toán
SELECT pg_temp.them_rang_buoc('thanh_toan', 'chk_tt_so_tien_duong', 'so_tien > 0');
SELECT pg_temp.them_rang_buoc('thanh_toan', 'chk_tt_da_tra_co_ngay', 'trang_thai <> ''da_thanh_toan'' OR ngay_thanh_toan IS NOT NULL');
-- Sản phẩm
SELECT pg_temp.them_rang_buoc('san_pham', 'chk_sp_ma_sku_dinh_dang', 'ma_sku ~ ''^[A-Z]{2,6}-[0-9]{3,5}$''');
SELECT pg_temp.them_rang_buoc('san_pham', 'chk_sp_bao_hanh_hop_le', 'bao_hanh_thang BETWEEN 0 AND 120');
SELECT pg_temp.them_rang_buoc('san_pham', 'chk_sp_ten_khong_rong', 'btrim(ten) <> ''''');
-- Kho, nhập hàng, nhà cung cấp
SELECT pg_temp.them_rang_buoc('ton_kho', 'chk_tk_muc_toi_thieu_khong_am', 'muc_ton_toi_thieu >= 0');
SELECT pg_temp.them_rang_buoc('chi_tiet_phieu_nhap', 'chk_ctpn_gia_nhap_khong_am', 'gia_nhap >= 0');
SELECT pg_temp.them_rang_buoc('phieu_nhap', 'chk_pn_tong_tien_khong_am', 'tong_tien >= 0');
SELECT pg_temp.them_rang_buoc('san_pham_nha_cung_cap', 'chk_spncc_gia_khong_am', 'gia_nhap_gan_nhat IS NULL OR gia_nhap_gan_nhat >= 0');
-- Khách hàng: họ tên đã chuẩn hóa khoảng trắng, ngày sinh hợp lý
SELECT pg_temp.them_rang_buoc('khach_hang', 'chk_kh_ho_ten_chuan_hoa', 'ho_ten = btrim(regexp_replace(ho_ten, ''\s+'', '' '', ''g'')) AND ho_ten <> ''''');
SELECT pg_temp.them_rang_buoc('khach_hang', 'chk_kh_ngay_sinh_hop_ly', 'ngay_sinh IS NULL OR (ngay_sinh > DATE ''1900-01-01'' AND ngay_sinh < ngay_dang_ky)');

-- Ràng buộc dạng chỉ mục (vừa là ràng buộc, vừa là ví dụ PARTIAL / EXPRESSION INDEX)
DO $$
BEGIN
    -- Mỗi khách hàng tối đa MỘT địa chỉ mặc định (partial unique index)
    BEGIN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dia_chi_mot_mac_dinh
            ON "LinhKien".dia_chi (khach_hang_id) WHERE mac_dinh;
        RAISE NOTICE '[OK] uq_dia_chi_mot_mac_dinh';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE '[CẢNH BÁO] Có khách đang có nhiều địa chỉ mặc định, chưa tạo được uq_dia_chi_mot_mac_dinh';
    END;
    -- Email không trùng kể cả khác hoa/thường (expression unique index)
    BEGIN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_khach_hang_email_khong_phan_biet_hoa
            ON "LinhKien".khach_hang (lower(email)) WHERE email IS NOT NULL;
        RAISE NOTICE '[OK] uq_khach_hang_email_khong_phan_biet_hoa';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE '[CẢNH BÁO] Có email trùng khi bỏ qua hoa/thường, chưa tạo được chỉ mục duy nhất';
    END;
END $$;

-- ==============================================================================
-- PHẦN C. TỐI ƯU HIỆU NĂNG
-- ==============================================================================
-- C1. Index cho 10 khóa ngoại còn thiếu (JOIN, kiểm tra RESTRICT khi xóa bản ghi cha, RLS theo nhân viên)
CREATE INDEX IF NOT EXISTS idx_danh_muc_cha            ON "LinhKien".danh_muc (danh_muc_cha_id);
CREATE INDEX IF NOT EXISTS idx_spncc_nha_cung_cap      ON "LinhKien".san_pham_nha_cung_cap (nha_cung_cap_id);
CREATE INDEX IF NOT EXISTS idx_don_hang_dia_chi_giao   ON "LinhKien".don_hang (dia_chi_giao_id);
CREATE INDEX IF NOT EXISTS idx_dia_chi_khach_hang      ON "LinhKien".dia_chi (khach_hang_id);
CREATE INDEX IF NOT EXISTS idx_don_hang_nhan_vien      ON "LinhKien".don_hang (nhan_vien_id);
CREATE INDEX IF NOT EXISTS idx_phieu_nhap_ncc          ON "LinhKien".phieu_nhap (nha_cung_cap_id);
CREATE INDEX IF NOT EXISTS idx_phieu_nhap_nhan_vien    ON "LinhKien".phieu_nhap (nhan_vien_id);
CREATE INDEX IF NOT EXISTS idx_ctpn_phieu_nhap         ON "LinhKien".chi_tiet_phieu_nhap (phieu_nhap_id);
CREATE INDEX IF NOT EXISTS idx_ctpn_san_pham           ON "LinhKien".chi_tiet_phieu_nhap (san_pham_id);

-- C2. PARTIAL INDEX: báo cáo doanh thu chỉ đọc đơn hoàn thành -> index nhỏ, chỉ chứa dòng cần dùng
CREATE INDEX IF NOT EXISTS idx_don_hang_hoan_thanh_ngay
    ON "LinhKien".don_hang (ngay_dat) INCLUDE (tong_tien)
    WHERE trang_thai = 'hoan_thanh';
-- Partial index cảnh báo tồn kho thấp (view v_canh_bao_ton_kho)
CREATE INDEX IF NOT EXISTS idx_ton_kho_sap_het
    ON "LinhKien".ton_kho (so_luong_ton)
    WHERE so_luong_ton <= muc_ton_toi_thieu;

-- C3. HASH INDEX: tra cứu khách theo số điện thoại chỉ dùng phép so sánh bằng (=)
CREATE INDEX IF NOT EXISTS idx_khach_hang_sdt_hash
    ON "LinhKien".khach_hang USING hash (so_dien_thoai);

-- C4. GIN pg_trgm: tìm tên sản phẩm chứa chuỗi bất kỳ (ILIKE '%rtx%') vẫn dùng được chỉ mục
CREATE INDEX IF NOT EXISTS idx_san_pham_ten_trgm
    ON "LinhKien".san_pham USING gin (ten gin_trgm_ops);

-- C5. Autovacuum chủ động hơn cho các bảng giao dịch ghi nhiều
ALTER TABLE "LinhKien".don_hang          SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE "LinhKien".chi_tiet_don_hang SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE "LinhKien".thanh_toan        SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE "LinhKien".ton_kho           SET (autovacuum_vacuum_scale_factor = 0.10, autovacuum_analyze_scale_factor = 0.05);

-- Hàm tự tạo phân vùng cho N tháng tới (bao_tri.py gọi định kỳ)
CREATE OR REPLACE FUNCTION "LinhKien".fn_tao_phan_vung_lich_su_gia(p_so_thang INT DEFAULT 12)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_thang DATE := date_trunc('month', CURRENT_DATE - INTERVAL '1 month')::date;
    v_ten   TEXT;
    v_tao   INT := 0;
BEGIN
    FOR i IN 0..p_so_thang LOOP
        v_ten := 'lich_su_thay_doi_gia_' || to_char(v_thang, 'YYYY_MM');
        IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'LinhKien' AND c.relname = v_ten) THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE "LinhKien".%I PARTITION OF "LinhKien".lich_su_thay_doi_gia FOR VALUES FROM (%L) TO (%L)',
                    v_ten, v_thang, (v_thang + INTERVAL '1 month')::date);
                v_tao := v_tao + 1;
            EXCEPTION WHEN others THEN
                -- Ví dụ: phân vùng DEFAULT đang chứa dữ liệu của tháng này -> bỏ qua, ghi chú cho DBA
                RAISE NOTICE 'Không tạo được phân vùng %: %', v_ten, SQLERRM;
            END;
        END IF;
        v_thang := (v_thang + INTERVAL '1 month')::date;
    END LOOP;
    RETURN v_tao;
END $$;
-- C6. PHÂN VÙNG THẬT (RANGE PARTITIONING) cho bảng lịch sử giá - bảng chỉ ghi thêm, tăng theo thời gian
DO $$
DECLARE
    v_kind CHAR;
BEGIN
    SELECT c.relkind INTO v_kind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'LinhKien' AND c.relname = 'lich_su_thay_doi_gia';

    IF v_kind = 'r' THEN
        ALTER TABLE "LinhKien".lich_su_thay_doi_gia RENAME TO lich_su_thay_doi_gia_cu;
    END IF;
    IF v_kind IS DISTINCT FROM 'p' THEN
        CREATE TABLE "LinhKien".lich_su_thay_doi_gia (
            id              BIGSERIAL,
            san_pham_id     INT NOT NULL REFERENCES "LinhKien".san_pham(id) ON DELETE CASCADE,
            gia_cu          NUMERIC(14,0) NOT NULL,
            gia_moi         NUMERIC(14,0) NOT NULL,
            ngay_thay_doi   TIMESTAMP NOT NULL DEFAULT NOW(),
            nguoi_thuc_hien VARCHAR(50) DEFAULT CURRENT_USER,
            PRIMARY KEY (id, ngay_thay_doi)
        ) PARTITION BY RANGE (ngay_thay_doi);
        CREATE TABLE "LinhKien".lich_su_thay_doi_gia_mac_dinh
            PARTITION OF "LinhKien".lich_su_thay_doi_gia DEFAULT;
        -- Tạo sẵn phân vùng từng tháng TRƯỚC khi chép dữ liệu cũ để dữ liệu rơi đúng phân vùng
        PERFORM "LinhKien".fn_tao_phan_vung_lich_su_gia(12);
        IF v_kind = 'r' THEN
            INSERT INTO "LinhKien".lich_su_thay_doi_gia (san_pham_id, gia_cu, gia_moi, ngay_thay_doi, nguoi_thuc_hien)
            SELECT san_pham_id, gia_cu, gia_moi, ngay_thay_doi, nguoi_thuc_hien FROM "LinhKien".lich_su_thay_doi_gia_cu;
            DROP TABLE "LinhKien".lich_su_thay_doi_gia_cu;
        END IF;
        RAISE NOTICE '[OK] lich_su_thay_doi_gia là bảng phân vùng RANGE theo tháng';
    END IF;
END $$;
SELECT "LinhKien".fn_tao_phan_vung_lich_su_gia(12) AS so_phan_vung_moi;
COMMENT ON TABLE "LinhKien".lich_su_thay_doi_gia IS
    'Lịch sử thay đổi giá (audit) - bảng PHÂN VÙNG RANGE theo tháng trên ngay_thay_doi';
CREATE INDEX IF NOT EXISTS idx_lich_su_gia_san_pham ON "LinhKien".lich_su_thay_doi_gia (san_pham_id);

-- Quyền đọc bảng phân vùng mới
GRANT SELECT ON "LinhKien".lich_su_thay_doi_gia TO text2sql_readonly, manager_readonly;

-- C7. Hàm làm mới báo cáo tổng hợp (Materialized View) - bao_tri.py gọi định kỳ
CREATE OR REPLACE FUNCTION "LinhKien".fn_lam_moi_bao_cao()
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY "LinhKien".mv_thong_ke_doanh_thu_thang;
    RETURN 'Đã làm mới mv_thong_ke_doanh_thu_thang lúc ' || to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS');
END $$;

-- ==============================================================================
-- PHẦN D. DỮ LIỆU "SỐNG": tổng tiền phiếu nhập tự cập nhật theo chi tiết
-- ==============================================================================
CREATE OR REPLACE FUNCTION "LinhKien".fn_cap_nhat_tong_tien_phieu_nhap()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_id INT := COALESCE(NEW.phieu_nhap_id, OLD.phieu_nhap_id);
BEGIN
    UPDATE "LinhKien".phieu_nhap p
       SET tong_tien = COALESCE((SELECT SUM(c.so_luong * c.gia_nhap)
                                   FROM "LinhKien".chi_tiet_phieu_nhap c
                                  WHERE c.phieu_nhap_id = v_id), 0)
     WHERE p.id = v_id;
    IF TG_OP = 'UPDATE' AND OLD.phieu_nhap_id <> NEW.phieu_nhap_id THEN
        UPDATE "LinhKien".phieu_nhap p
           SET tong_tien = COALESCE((SELECT SUM(c.so_luong * c.gia_nhap)
                                       FROM "LinhKien".chi_tiet_phieu_nhap c
                                      WHERE c.phieu_nhap_id = OLD.phieu_nhap_id), 0)
         WHERE p.id = OLD.phieu_nhap_id;
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS trg_cap_nhat_tong_tien_phieu_nhap ON "LinhKien".chi_tiet_phieu_nhap;
CREATE TRIGGER trg_cap_nhat_tong_tien_phieu_nhap
    AFTER INSERT OR UPDATE OR DELETE ON "LinhKien".chi_tiet_phieu_nhap
    FOR EACH ROW EXECUTE FUNCTION "LinhKien".fn_cap_nhat_tong_tien_phieu_nhap();

-- Cập nhật thống kê cho bộ tối ưu truy vấn (nhiều bảng chưa từng được ANALYZE)
ANALYZE "LinhKien".danh_muc, "LinhKien".thuong_hieu, "LinhKien".nha_cung_cap, "LinhKien".san_pham,
        "LinhKien".san_pham_nha_cung_cap, "LinhKien".khach_hang, "LinhKien".dia_chi, "LinhKien".nhan_vien,
        "LinhKien".don_hang, "LinhKien".chi_tiet_don_hang, "LinhKien".thanh_toan, "LinhKien".ton_kho,
        "LinhKien".phieu_nhap, "LinhKien".chi_tiet_phieu_nhap, "LinhKien".app_users;

COMMIT;

-- ==============================================================================
-- KIỂM TRA NHANH SAU KHI CHẠY (kết quả hiện ở tab Data Output)
-- ==============================================================================
SELECT
    (SELECT count(*) FROM pg_policies WHERE schemaname = 'LinhKien')                                        AS so_policy_rls,
    has_column_privilege('text2sql_readonly', '"LinhKien".app_users', 'password_hash', 'SELECT')          AS readonly_doc_password,
    (SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
      WHERE n.nspname = 'LinhKien' AND c.contype = 'c')                                                   AS so_rang_buoc_check,
    (SELECT relkind FROM pg_class WHERE oid = '"LinhKien".lich_su_thay_doi_gia'::regclass)                AS lich_su_gia_relkind,
    (SELECT count(*) FROM pg_inherits WHERE inhparent = '"LinhKien".lich_su_thay_doi_gia'::regclass)      AS so_phan_vung;

-- ==============================================================================
-- KỊCH BẢN DEMO RLS MỚI (chạy từng khối trong pgAdmin bằng tài khoản postgres)
-- ==============================================================================
-- SET ROLE nv_2;   SELECT count(*) FROM "LinhKien".don_hang;          -- chỉ đơn của nhân viên 2
-- SET app.current_nhan_vien_id = '3';  SELECT count(*) FROM "LinhKien".don_hang;   -- vẫn như trên: KHÔNG lách được
-- RESET ROLE; SET ROLE nv_3; SELECT count(*) FROM "LinhKien".don_hang; -- chỉ đơn của nhân viên 3
-- SELECT gia_von FROM "LinhKien".san_pham LIMIT 1;                    -- LỖI: permission denied (bảo mật mức cột)
-- RESET ROLE;
-- SET ROLE text2sql_readonly; SELECT * FROM "LinhKien".app_users;    -- LỖI: permission denied (không đọc được hash)
-- SELECT * FROM "LinhKien".fn_xac_thuc_nguoi_dung('admin', 'admin123');  -- đăng nhập đúng: trả về 1 dòng, không có hash
-- RESET ROLE;
