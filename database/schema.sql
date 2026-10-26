-- ============================================================
-- CSDL: Cửa hàng linh kiện máy tính (LinhKien_DB)
-- Dùng cho đề tài Text-to-SQL tiếng Việt trên PostgreSQL
-- Cách chạy:
--   createdb LinhKien_DB
--   psql -d LinhKien_DB -f schema.sql
-- ============================================================

DROP SCHEMA IF EXISTS "LinhKien" CASCADE;
CREATE SCHEMA "LinhKien";
SET search_path TO "LinhKien", public;

-- Tự động đặt search_path cho database để mọi kết nối tự ưu tiên schema LinhKien
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path TO "LinhKien", public', current_database());
END
$$;

-- ------------------------------------------------------------
-- 1. DANH MỤC SẢN PHẨM
-- ------------------------------------------------------------
CREATE TABLE danh_muc (
    id              SERIAL PRIMARY KEY,
    ten             VARCHAR(100) NOT NULL UNIQUE,
    mo_ta           TEXT,
    danh_muc_cha_id INT REFERENCES danh_muc(id)
);

CREATE TABLE thuong_hieu (
    id          SERIAL PRIMARY KEY,
    ten         VARCHAR(100) NOT NULL UNIQUE,
    quoc_gia    VARCHAR(50)
);

CREATE TABLE nha_cung_cap (
    id              SERIAL PRIMARY KEY,
    ten             VARCHAR(150) NOT NULL,
    so_dien_thoai   VARCHAR(20),
    email           VARCHAR(100),
    tinh_thanh      VARCHAR(50)
);

CREATE TABLE san_pham (
    id              SERIAL PRIMARY KEY,
    ma_sku          VARCHAR(30) NOT NULL UNIQUE,
    ten             VARCHAR(200) NOT NULL,
    danh_muc_id     INT NOT NULL REFERENCES danh_muc(id),
    thuong_hieu_id  INT NOT NULL REFERENCES thuong_hieu(id),
    gia_niem_yet    NUMERIC(14,0) NOT NULL CHECK (gia_niem_yet >= 0),
    gia_von         NUMERIC(14,0) NOT NULL CHECK (gia_von >= 0),
    bao_hanh_thang  INT NOT NULL DEFAULT 12,
    ngay_ra_mat     DATE,
    dang_kinh_doanh BOOLEAN NOT NULL DEFAULT TRUE
);

-- Quan hệ nhiều-nhiều: một sản phẩm có thể nhập từ nhiều nhà cung cấp
CREATE TABLE san_pham_nha_cung_cap (
    san_pham_id       INT NOT NULL REFERENCES san_pham(id),
    nha_cung_cap_id   INT NOT NULL REFERENCES nha_cung_cap(id),
    gia_nhap_gan_nhat NUMERIC(14,0),
    PRIMARY KEY (san_pham_id, nha_cung_cap_id)
);

-- ------------------------------------------------------------
-- 2. KHÁCH HÀNG & NHÂN VIÊN
-- ------------------------------------------------------------
CREATE TABLE khach_hang (
    id              SERIAL PRIMARY KEY,
    ho_ten          VARCHAR(100) NOT NULL,
    email           VARCHAR(100) UNIQUE,
    so_dien_thoai   VARCHAR(20),
    gioi_tinh       VARCHAR(10) CHECK (gioi_tinh IN ('nam', 'nu', 'khac')),
    ngay_sinh       DATE,
    ngay_dang_ky    DATE NOT NULL,
    loai_khach      VARCHAR(20) NOT NULL DEFAULT 'le'
                    CHECK (loai_khach IN ('le', 'si', 'doanh_nghiep'))
);

CREATE TABLE dia_chi (
    id                  SERIAL PRIMARY KEY,
    khach_hang_id       INT NOT NULL REFERENCES khach_hang(id),
    tinh_thanh          VARCHAR(50) NOT NULL,
    quan_huyen          VARCHAR(50),
    dia_chi_chi_tiet    VARCHAR(200),
    mac_dinh            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE nhan_vien (
    id              SERIAL PRIMARY KEY,
    ho_ten          VARCHAR(100) NOT NULL,
    chuc_vu         VARCHAR(50) NOT NULL,
    ngay_vao_lam    DATE NOT NULL,
    dang_lam_viec   BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- 3. BÁN HÀNG
-- ------------------------------------------------------------
CREATE TABLE don_hang (
    id              SERIAL PRIMARY KEY,
    khach_hang_id   INT NOT NULL REFERENCES khach_hang(id),
    nhan_vien_id    INT REFERENCES nhan_vien(id),   -- NULL nếu đặt online
    dia_chi_giao_id INT REFERENCES dia_chi(id),
    ngay_dat        TIMESTAMP NOT NULL,
    ngay_giao       TIMESTAMP,                      -- NULL nếu chưa giao
    trang_thai      VARCHAR(20) NOT NULL
                    CHECK (trang_thai IN ('moi', 'dang_xu_ly', 'dang_giao',
                                          'hoan_thanh', 'da_huy', 'tra_hang')),
    kenh_ban        VARCHAR(20) NOT NULL
                    CHECK (kenh_ban IN ('cua_hang', 'website', 'shopee', 'facebook')),
    tong_tien       NUMERIC(14,0) NOT NULL DEFAULT 0
);

CREATE TABLE chi_tiet_don_hang (
    id              SERIAL PRIMARY KEY,
    don_hang_id     INT NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    san_pham_id     INT NOT NULL REFERENCES san_pham(id),
    so_luong        INT NOT NULL CHECK (so_luong > 0),
    don_gia         NUMERIC(14,0) NOT NULL,         -- giá thực bán tại thời điểm đặt
    giam_gia        NUMERIC(14,0) NOT NULL DEFAULT 0
);

CREATE TABLE thanh_toan (
    id                  SERIAL PRIMARY KEY,
    don_hang_id         INT NOT NULL REFERENCES don_hang(id) ON DELETE CASCADE,
    phuong_thuc         VARCHAR(20) NOT NULL
                        CHECK (phuong_thuc IN ('tien_mat', 'chuyen_khoan', 'the', 'vi_dien_tu', 'tra_gop')),
    so_tien             NUMERIC(14,0) NOT NULL,
    ngay_thanh_toan     TIMESTAMP,
    trang_thai          VARCHAR(20) NOT NULL
                        CHECK (trang_thai IN ('cho_thanh_toan', 'da_thanh_toan', 'hoan_tien'))
);

-- ------------------------------------------------------------
-- 4. KHO
-- ------------------------------------------------------------
CREATE TABLE ton_kho (
    san_pham_id         INT PRIMARY KEY REFERENCES san_pham(id),
    so_luong_ton        INT NOT NULL DEFAULT 0 CHECK (so_luong_ton >= 0),
    muc_ton_toi_thieu   INT NOT NULL DEFAULT 5,
    ngay_cap_nhat       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE phieu_nhap (
    id                  SERIAL PRIMARY KEY,
    nha_cung_cap_id     INT NOT NULL REFERENCES nha_cung_cap(id),
    nhan_vien_id        INT REFERENCES nhan_vien(id),
    ngay_nhap           DATE NOT NULL,
    tong_tien           NUMERIC(14,0) NOT NULL DEFAULT 0
);

CREATE TABLE chi_tiet_phieu_nhap (
    id              SERIAL PRIMARY KEY,
    phieu_nhap_id   INT NOT NULL REFERENCES phieu_nhap(id) ON DELETE CASCADE,
    san_pham_id     INT NOT NULL REFERENCES san_pham(id),
    so_luong        INT NOT NULL CHECK (so_luong > 0),
    gia_nhap        NUMERIC(14,0) NOT NULL
);

-- ------------------------------------------------------------
-- 5. INDEX (các cột hay lọc/JOIN)
-- ------------------------------------------------------------
CREATE INDEX idx_san_pham_danh_muc     ON san_pham(danh_muc_id);
CREATE INDEX idx_san_pham_thuong_hieu  ON san_pham(thuong_hieu_id);
CREATE INDEX idx_don_hang_khach_hang   ON don_hang(khach_hang_id);
CREATE INDEX idx_don_hang_ngay_dat     ON don_hang(ngay_dat);
CREATE INDEX idx_ctdh_don_hang         ON chi_tiet_don_hang(don_hang_id);
CREATE INDEX idx_ctdh_san_pham         ON chi_tiet_don_hang(san_pham_id);
CREATE INDEX idx_thanh_toan_don_hang   ON thanh_toan(don_hang_id);
CREATE INDEX idx_phieu_nhap_ngay       ON phieu_nhap(ngay_nhap);

-- ------------------------------------------------------------
-- 6. MÔ TẢ BẢNG / CỘT (dùng cho schema linking của hệ thống AI)
-- ------------------------------------------------------------
COMMENT ON TABLE danh_muc IS 'Danh mục sản phẩm (CPU, RAM, VGA, Mainboard...), hỗ trợ danh mục cha-con';
COMMENT ON TABLE thuong_hieu IS 'Thương hiệu sản xuất (ASUS, MSI, Intel, AMD, Kingston...)';
COMMENT ON TABLE nha_cung_cap IS 'Nhà cung cấp / nhà phân phối mà cửa hàng nhập hàng';
COMMENT ON TABLE san_pham IS 'Sản phẩm linh kiện đang và đã từng kinh doanh';
COMMENT ON TABLE san_pham_nha_cung_cap IS 'Liên kết nhiều-nhiều: sản phẩm có thể nhập từ nhiều nhà cung cấp';
COMMENT ON TABLE khach_hang IS 'Khách hàng đã đăng ký hoặc từng mua hàng';
COMMENT ON TABLE dia_chi IS 'Địa chỉ giao hàng của khách, một khách có thể có nhiều địa chỉ';
COMMENT ON TABLE nhan_vien IS 'Nhân viên bán hàng và nhân viên kho';
COMMENT ON TABLE don_hang IS 'Đơn bán hàng cho khách (mỗi đơn gồm nhiều dòng chi tiết)';
COMMENT ON TABLE chi_tiet_don_hang IS 'Từng dòng sản phẩm trong đơn hàng';
COMMENT ON TABLE thanh_toan IS 'Các lần thanh toán của đơn hàng (một đơn có thể trả nhiều lần)';
COMMENT ON TABLE ton_kho IS 'Số lượng tồn kho hiện tại của từng sản phẩm';
COMMENT ON TABLE phieu_nhap IS 'Phiếu nhập hàng từ nhà cung cấp';
COMMENT ON TABLE chi_tiet_phieu_nhap IS 'Từng dòng sản phẩm trong phiếu nhập';

COMMENT ON COLUMN san_pham.gia_niem_yet IS 'Giá bán niêm yết hiện tại (VNĐ)';
COMMENT ON COLUMN san_pham.gia_von IS 'Giá vốn trung bình (VNĐ), dùng tính lợi nhuận';
COMMENT ON COLUMN san_pham.bao_hanh_thang IS 'Thời gian bảo hành tính theo tháng';
COMMENT ON COLUMN san_pham.dang_kinh_doanh IS 'FALSE nếu sản phẩm đã ngừng kinh doanh';
COMMENT ON COLUMN khach_hang.loai_khach IS 'le = khách lẻ, si = khách sỉ, doanh_nghiep = công ty';
COMMENT ON COLUMN khach_hang.ngay_dang_ky IS 'Ngày khách đăng ký tài khoản / lần đầu mua';
COMMENT ON COLUMN don_hang.ngay_dat IS 'Thời điểm khách đặt đơn';
COMMENT ON COLUMN don_hang.ngay_giao IS 'Thời điểm giao thành công, NULL nếu chưa giao';
COMMENT ON COLUMN don_hang.trang_thai IS 'moi, dang_xu_ly, dang_giao, hoan_thanh, da_huy, tra_hang';
COMMENT ON COLUMN don_hang.kenh_ban IS 'Kênh bán: cua_hang (trực tiếp), website, shopee, facebook';
COMMENT ON COLUMN don_hang.nhan_vien_id IS 'Nhân viên phụ trách, NULL nếu khách tự đặt online';
COMMENT ON COLUMN don_hang.tong_tien IS 'Tổng tiền đơn hàng sau giảm giá (VNĐ)';
COMMENT ON COLUMN chi_tiet_don_hang.don_gia IS 'Giá thực bán một đơn vị tại thời điểm đặt (có thể khác giá niêm yết hiện tại)';
COMMENT ON COLUMN chi_tiet_don_hang.giam_gia IS 'Số tiền giảm giá cho cả dòng (VNĐ)';
COMMENT ON COLUMN thanh_toan.phuong_thuc IS 'tien_mat, chuyen_khoan, the, vi_dien_tu, tra_gop';
COMMENT ON COLUMN ton_kho.muc_ton_toi_thieu IS 'Dưới mức này thì cần nhập thêm hàng';
COMMENT ON COLUMN phieu_nhap.ngay_nhap IS 'Ngày hàng về kho';

-- ------------------------------------------------------------
-- 7. TÀI KHOẢN CHỈ ĐỌC cho hệ thống Text-to-SQL
-- (đổi mật khẩu trước khi dùng thật)
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'text2sql_readonly') THEN
        CREATE ROLE text2sql_readonly LOGIN PASSWORD 'doi_mat_khau_nay';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO text2sql_readonly', current_database());
    ALTER ROLE text2sql_readonly SET search_path TO "LinhKien", public;
END
$$;

GRANT USAGE ON SCHEMA "LinhKien" TO text2sql_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA "LinhKien" TO text2sql_readonly;
REVOKE SELECT (gia_von) ON "LinhKien".san_pham FROM text2sql_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA "LinhKien" GRANT SELECT ON TABLES TO text2sql_readonly;


-- ============================================================================
-- BẢNG: app_users (Tài khoản người dùng tầng ứng dụng Streamlit Web App)
-- ============================================================================
CREATE TABLE IF NOT EXISTS "LinhKien".app_users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(64) NOT NULL,          -- SHA-256 hex digest
    ho_ten          VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'manager')),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    ngay_tao        TIMESTAMP NOT NULL DEFAULT NOW(),
    lan_dang_nhap_cuoi TIMESTAMP
);

COMMENT ON TABLE "LinhKien".app_users IS 'Tài khoản người dùng tầng ứng dụng (Streamlit Web App)';
COMMENT ON COLUMN "LinhKien".app_users.password_hash IS 'Mật khẩu băm bcrypt có salt (pgcrypto), không lưu plaintext';
COMMENT ON COLUMN "LinhKien".app_users.role IS 'admin = Quản trị viên CSDL, manager = Quản lý cửa hàng';

-- Dữ liệu mẫu khởi tạo: mật khẩu băm bcrypt có salt (pgcrypto), KHÔNG lưu SHA-256 không salt.
-- admin / admin123 ; manager / manager123  (đổi ngay khi triển khai thật)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO "LinhKien".app_users (username, password_hash, ho_ten, role) VALUES
('admin',   crypt('admin123',   gen_salt('bf', 10)), 'Quản Trị Viên',    'admin'),
('manager', crypt('manager123', gen_salt('bf', 10)), 'Quản Lý Cửa Hàng', 'manager')
ON CONFLICT (username) DO NOTHING;
-- Role chỉ đọc không được đọc bảng tài khoản (ALTER DEFAULT PRIVILEGES ở trên đã tự cấp SELECT)
REVOKE ALL ON "LinhKien".app_users FROM text2sql_readonly;
