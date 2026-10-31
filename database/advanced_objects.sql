-- ====================================================================
-- CSDL: LinhKien_DB (Schema: "LinhKien")
-- ĐỐI TƯỢNG CSDL NÂNG CAO CHO HỌC PHẦN QUẢN TRỊ CSDL
-- --------------------------------------------------------------------
-- Bao gồm 5 nhóm đối tượng:
-- 1. Bán cấu trúc NoSQL: JSONB specs & GIN Index
-- 2. Ràng buộc toàn vẹn nâng cao: Regex Phone & Email CHECK Constraints
-- 3. Views & Materialized Views (kèm Unique Index phục vụ Concurrent Refresh)
-- 4. PL/pgSQL Stored Functions & Triggers (Auto Total, Inventory Deduction, Price Audit)
-- 5. An ninh bảo mật: RBAC, Row-Level Security (RLS) & Column-Level Security (CLS)
-- ====================================================================

SET search_path TO "LinhKien", public;

-- ====================================================================
-- NHÓM 1: BÁN CẤU TRÚC NoSQL (JSONB & GIN INDEX)
-- ====================================================================

-- 1.1 Thêm cột thong_so_ky_thuat kiểu JSONB vào bảng san_pham
ALTER TABLE "LinhKien".san_pham 
ADD COLUMN IF NOT EXISTS thong_so_ky_thuat JSONB;

COMMENT ON COLUMN "LinhKien".san_pham.thong_so_ky_thuat IS 'Thông số kỹ thuật bán cấu trúc NoSQL dạng JSONB (socket, vram, bus, panel, switch, dpi...)';

-- 1.2 Tạo chỉ mục GIN hỗ trợ tìm kiếm siêu tốc trên thuộc tính JSONB
CREATE INDEX IF NOT EXISTS idx_san_pham_thong_so_gin 
ON "LinhKien".san_pham USING GIN (thong_so_ky_thuat);

-- 1.3 Cập nhật dữ liệu JSONB phong phú, chi tiết theo danh mục sản phẩm

-- CPU: socket, cores, threads, tdp, igpu
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'socket', CASE 
        WHEN sp.ten ILIKE '%Ryzen%7%' OR sp.ten ILIKE '%Ryzen%9%' OR sp.ten ILIKE '%Ryzen 5 7%' THEN 'AM5'
        WHEN sp.ten ILIKE '%Ryzen%' THEN 'AM4'
        ELSE 'LGA1700'
    END,
    'cores', CASE 
        WHEN sp.ten ILIKE '%14900K%' THEN 24
        WHEN sp.ten ILIKE '%14700K%' THEN 20
        WHEN sp.ten ILIKE '%13700K%' THEN 16
        WHEN sp.ten ILIKE '%7950X%' THEN 16
        WHEN sp.ten ILIKE '%14400F%' OR sp.ten ILIKE '%13400F%' THEN 10
        WHEN sp.ten ILIKE '%7800X3D%' OR sp.ten ILIKE '%5700X%' THEN 8
        WHEN sp.ten ILIKE '%12400F%' OR sp.ten ILIKE '%5600%' OR sp.ten ILIKE '%7600%' THEN 6
        ELSE 4
    END,
    'threads', CASE 
        WHEN sp.ten ILIKE '%14900K%' OR sp.ten ILIKE '%7950X%' THEN 32
        WHEN sp.ten ILIKE '%14700K%' THEN 28
        WHEN sp.ten ILIKE '%13700K%' THEN 24
        WHEN sp.ten ILIKE '%14400F%' OR sp.ten ILIKE '%13400F%' OR sp.ten ILIKE '%7800X3D%' OR sp.ten ILIKE '%5700X%' THEN 16
        WHEN sp.ten ILIKE '%12400F%' OR sp.ten ILIKE '%5600%' OR sp.ten ILIKE '%7600%' THEN 12
        ELSE 8
    END,
    'tdp', CASE 
        WHEN sp.ten ILIKE '%7950X%' THEN '170W'
        WHEN sp.ten ILIKE '%14900K%' OR sp.ten ILIKE '%14700K%' OR sp.ten ILIKE '%13700K%' THEN '125W'
        WHEN sp.ten ILIKE '%7800X3D%' THEN '120W'
        ELSE '65W'
    END,
    'igpu', CASE 
        WHEN sp.ten ILIKE '%F' OR sp.ten ILIKE '%5600%' OR sp.ten ILIKE '%5700X%' THEN false
        ELSE true
    END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'CPU';

-- VGA: vram, bus, tdp, pcie, led
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'vram', CASE 
        WHEN sp.ten ILIKE '%4090%' THEN '24GB GDDR6X'
        WHEN sp.ten ILIKE '%4080%' OR sp.ten ILIKE '%4070 Ti%' OR sp.ten ILIKE '%7800 XT%' THEN '16GB GDDR6'
        WHEN sp.ten ILIKE '%4070%' THEN '12GB GDDR6X'
        WHEN sp.ten ILIKE '%3050%' THEN '6GB GDDR6'
        ELSE '8GB GDDR6'
    END,
    'bus', CASE 
        WHEN sp.ten ILIKE '%4090%' THEN '384-bit'
        WHEN sp.ten ILIKE '%4080%' OR sp.ten ILIKE '%4070 Ti%' OR sp.ten ILIKE '%7800 XT%' THEN '256-bit'
        WHEN sp.ten ILIKE '%4070%' THEN '192-bit'
        ELSE '128-bit'
    END,
    'tdp', CASE 
        WHEN sp.ten ILIKE '%4090%' THEN '450W'
        WHEN sp.ten ILIKE '%4080%' THEN '320W'
        WHEN sp.ten ILIKE '%4070 Ti%' OR sp.ten ILIKE '%7800 XT%' THEN '285W'
        WHEN sp.ten ILIKE '%4070%' THEN '200W'
        WHEN sp.ten ILIKE '%4060%' THEN '115W'
        ELSE '130W'
    END,
    'pcie', 'PCIe 4.0 x16',
    'led', 'RGB'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'VGA';

-- RAM: type, bus, capacity, rgb, voltage
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'type', CASE WHEN sp.ten ILIKE '%DDR5%' THEN 'DDR5' ELSE 'DDR4' END,
    'bus', CASE 
        WHEN sp.ten ILIKE '%6000%' THEN '6000MHz'
        WHEN sp.ten ILIKE '%5600%' THEN '5600MHz'
        WHEN sp.ten ILIKE '%4800%' THEN '4800MHz'
        ELSE '3200MHz'
    END,
    'capacity', CASE 
        WHEN sp.ten ILIKE '%32GB%' THEN '32GB (2x16GB)'
        WHEN sp.ten ILIKE '%16GB%' THEN '16GB (1x16GB)'
        ELSE '8GB (1x8GB)'
    END,
    'rgb', CASE WHEN sp.ten ILIKE '%Trident%' OR sp.ten ILIKE '%Lancer%' THEN true ELSE false END,
    'voltage', CASE WHEN sp.ten ILIKE '%DDR5%' THEN '1.25V' ELSE '1.35V' END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'RAM';

-- Mainboard: chipset, socket, form_factor, ram_slots, wifi
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'chipset', CASE 
        WHEN sp.ten ILIKE '%Z790%' THEN 'Intel Z790'
        WHEN sp.ten ILIKE '%B760%' THEN 'Intel B760'
        WHEN sp.ten ILIKE '%B660%' THEN 'Intel B660'
        WHEN sp.ten ILIKE '%B650%' THEN 'AMD B650'
        WHEN sp.ten ILIKE '%B550%' THEN 'AMD B550'
        WHEN sp.ten ILIKE '%B450%' THEN 'AMD B450'
        ELSE 'B760'
    END,
    'socket', CASE 
        WHEN sp.ten ILIKE '%B650%' THEN 'AM5'
        WHEN sp.ten ILIKE '%B550%' OR sp.ten ILIKE '%B450%' THEN 'AM4'
        ELSE 'LGA1700'
    END,
    'form_factor', CASE WHEN sp.ten ILIKE '%-M%' OR sp.ten ILIKE '%M-%' OR sp.ten ILIKE '%M PRO%' THEN 'Micro-ATX' ELSE 'ATX' END,
    'ram_slots', 4,
    'wifi', CASE WHEN sp.ten ILIKE '%WIFI%' OR sp.ten ILIKE '%STRIX%' THEN true ELSE false END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Mainboard';

-- SSD: form_factor, interface, read_speed, write_speed, capacity
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'form_factor', 'M.2 2280 NVMe',
    'interface', CASE WHEN sp.ten ILIKE '%990 PRO%' OR sp.ten ILIKE '%SN580%' OR sp.ten ILIKE '%P3 Plus%' THEN 'PCIe 4.0 x4' ELSE 'PCIe 3.0 x4' END,
    'read_speed', CASE 
        WHEN sp.ten ILIKE '%990 PRO%' THEN '7450MB/s'
        WHEN sp.ten ILIKE '%P3 Plus%' THEN '5000MB/s'
        WHEN sp.ten ILIKE '%SN580%' THEN '4150MB/s'
        WHEN sp.ten ILIKE '%NV2%' THEN '3500MB/s'
        ELSE '3100MB/s'
    END,
    'write_speed', CASE 
        WHEN sp.ten ILIKE '%990 PRO%' THEN '6900MB/s'
        WHEN sp.ten ILIKE '%P3 Plus%' THEN '4200MB/s'
        WHEN sp.ten ILIKE '%SN580%' THEN '4150MB/s'
        WHEN sp.ten ILIKE '%NV2%' THEN '2800MB/s'
        ELSE '2000MB/s'
    END,
    'capacity', CASE 
        WHEN sp.ten ILIKE '%2TB%' THEN '2TB'
        WHEN sp.ten ILIKE '%1TB%' THEN '1TB'
        ELSE '500GB'
    END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'SSD';

-- HDD: capacity, form_factor, rpm, cache, interface
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'capacity', CASE 
        WHEN sp.ten ILIKE '%4TB%' THEN '4TB'
        WHEN sp.ten ILIKE '%2TB%' THEN '2TB'
        ELSE '1TB'
    END,
    'form_factor', '3.5 inch',
    'rpm', CASE WHEN sp.ten ILIKE '%5400%' THEN '5400 RPM' ELSE '7200 RPM' END,
    'cache', '64MB',
    'interface', 'SATA 3 (6Gb/s)'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'HDD';

-- Nguồn: wattage, efficiency, modular, fan_size
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'wattage', CASE 
        WHEN sp.ten ILIKE '%850%' THEN '850W'
        WHEN sp.ten ILIKE '%750%' THEN '750W'
        WHEN sp.ten ILIKE '%650%' THEN '650W'
        ELSE '550W'
    END,
    'efficiency', CASE 
        WHEN sp.ten ILIKE '%Gold%' THEN '80 Plus Gold'
        ELSE '80 Plus Bronze'
    END,
    'modular', CASE 
        WHEN sp.ten ILIKE '%Focus%' OR sp.ten ILIKE '%RM750e%' THEN 'Full Modular'
        WHEN sp.ten ILIKE '%Gold%' THEN 'Semi Modular'
        ELSE 'Non-Modular'
    END,
    'fan_size', '120mm'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Nguồn';

-- Màn hình: screen_size, resolution, panel, refresh_rate, sRGB
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'screen_size', CASE WHEN sp.ten ILIKE '%27%' THEN '27 inch' ELSE '24 inch' END,
    'resolution', CASE WHEN sp.ten ILIKE '%2K%' THEN '2560x1440 (2K)' ELSE '1920x1080 (FHD)' END,
    'panel', CASE WHEN sp.ten ILIKE '%IPS%' THEN 'IPS' WHEN sp.ten ILIKE '%G5%' THEN 'VA' ELSE 'IPS' END,
    'refresh_rate', CASE 
        WHEN sp.ten ILIKE '%170Hz%' THEN '170Hz'
        WHEN sp.ten ILIKE '%165Hz%' THEN '165Hz'
        WHEN sp.ten ILIKE '%144Hz%' THEN '144Hz'
        WHEN sp.ten ILIKE '%100Hz%' THEN '100Hz'
        ELSE '60Hz'
    END,
    'sRGB', '99%'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Màn hình';

-- Bàn phím: switch, led, connection
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'switch', CASE 
        WHEN sp.ten ILIKE '%K120%' THEN 'Rubber Dome'
        WHEN sp.ten ILIKE '%G213%' THEN 'Mech-Dome'
        WHEN sp.ten ILIKE '%K70%' THEN 'Cherry MX Red'
        WHEN sp.ten ILIKE '%BlackWidow%' THEN 'Razer Green Switch'
        WHEN sp.ten ILIKE '%3068B%' THEN 'Akko CS Jelly Pink'
        ELSE 'Mechanical Blue Switch'
    END,
    'led', CASE WHEN sp.ten ILIKE '%K120%' THEN 'None' ELSE 'RGB' END,
    'connection', CASE WHEN sp.ten ILIKE '%3068B%' THEN 'Bluetooth / 2.4GHz / USB-C' ELSE 'Wired USB' END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Bàn phím';

-- Chuột: dpi, sensor, connection, led
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'dpi', CASE 
        WHEN sp.ten ILIKE '%DeathAdder%' THEN '20000 DPI'
        WHEN sp.ten ILIKE '%G502%' THEN '25600 DPI'
        WHEN sp.ten ILIKE '%Rival%' THEN '8500 DPI'
        ELSE '8000 DPI'
    END,
    'sensor', CASE 
        WHEN sp.ten ILIKE '%G502%' THEN 'Hero 25K Optical'
        WHEN sp.ten ILIKE '%DeathAdder%' THEN 'Focus+ Optical'
        ELSE 'Optical'
    END,
    'connection', 'Wired USB',
    'led', 'RGB'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Chuột';

-- Tản nhiệt: type, tdp_rating, fan_speed, led
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'type', CASE WHEN sp.ten ILIKE '%H100i%' OR sp.ten ILIKE '%Kraken%' THEN 'Tản nhiệt nước AIO 240mm' ELSE 'Tản nhiệt khí tháp đôi' END,
    'tdp_rating', CASE WHEN sp.ten ILIKE '%AK620%' OR sp.ten ILIKE '%Kraken%' OR sp.ten ILIKE '%H100i%' THEN '260W' ELSE '180W' END,
    'fan_speed', '1850 RPM',
    'led', CASE WHEN sp.ten ILIKE '%ELITE%' OR sp.ten ILIKE '%Kraken%' THEN 'ARGB' ELSE 'None' END
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Tản nhiệt';

-- Vỏ case: form_factor_support, side_panel, fans_included, radiator_support
UPDATE "LinhKien".san_pham sp
SET thong_so_ky_thuat = jsonb_build_object(
    'form_factor_support', 'ATX, Micro-ATX, Mini-ITX',
    'side_panel', 'Kính cường lực (Tempered Glass)',
    'fans_included', CASE 
        WHEN sp.ten ILIKE '%216%' THEN '2x 160mm ARGB Front + 1x 140mm Rear'
        WHEN sp.ten ILIKE '%CC560%' THEN '4x 120mm LED'
        WHEN sp.ten ILIKE '%4000D%' THEN '2x 120mm AirGuide'
        ELSE '2x 120mm'
    END,
    'radiator_support', 'Lên đến 360mm'
)
FROM "LinhKien".danh_muc dm
WHERE sp.danh_muc_id = dm.id AND dm.ten = 'Vỏ case';

-- Cập nhật mặc định cho bất kỳ sản phẩm nào còn NULL
UPDATE "LinhKien".san_pham
SET thong_so_ky_thuat = jsonb_build_object('chuan_ket_noi', 'Tieu chuan', 'led', 'Khong')
WHERE thong_so_ky_thuat IS NULL;


-- ====================================================================
-- NHÓM 2: RÀNG BUỘC NÂNG CAO (REGEX CONSTRAINTS)
-- ====================================================================

-- 2.1 Chuẩn hóa số điện thoại nha_cung_cap có ký tự tạm 'xxxx' trước khi gán ràng buộc
UPDATE "LinhKien".nha_cung_cap 
SET so_dien_thoai = regexp_replace(so_dien_thoai, 'xxxx$', '8888') 
WHERE so_dien_thoai LIKE '%xxxx';

-- 2.2 Ràng buộc Regex cho bảng khach_hang và nha_cung_cap
DO $$
BEGIN
    -- Số điện thoại khách hàng: 10-11 chữ số, bắt đầu bằng 0
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_khach_hang_sdt') THEN
        ALTER TABLE "LinhKien".khach_hang 
        ADD CONSTRAINT chk_khach_hang_sdt 
        CHECK (so_dien_thoai IS NULL OR so_dien_thoai ~ '^0[0-9]{9,10}$');
    END IF;

    -- Email khách hàng chuẩn RFC format
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_khach_hang_email') THEN
        ALTER TABLE "LinhKien".khach_hang 
        ADD CONSTRAINT chk_khach_hang_email 
        CHECK (email IS NULL OR email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');
    END IF;

    -- Số điện thoại nhà cung cấp: 10-11 chữ số, bắt đầu bằng 0
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_nha_cung_cap_sdt') THEN
        ALTER TABLE "LinhKien".nha_cung_cap 
        ADD CONSTRAINT chk_nha_cung_cap_sdt 
        CHECK (so_dien_thoai IS NULL OR so_dien_thoai ~ '^0[0-9]{9,10}$');
    END IF;

    -- Email nhà cung cấp chuẩn RFC format
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_nha_cung_cap_email') THEN
        ALTER TABLE "LinhKien".nha_cung_cap 
        ADD CONSTRAINT chk_nha_cung_cap_email 
        CHECK (email IS NULL OR email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');
    END IF;
END $$;


-- ====================================================================
-- NHÓM 3: VIEWS & MATERIALIZED VIEWS
-- ====================================================================

-- 3.1 View thống kê doanh thu và số đơn đã giao của từng nhân viên
CREATE OR REPLACE VIEW "LinhKien".v_doanh_thu_nhan_vien AS
SELECT 
    nv.id AS nhan_vien_id,
    nv.ho_ten,
    nv.chuc_vu,
    COUNT(dh.id) FILTER (WHERE dh.trang_thai = 'hoan_thanh') AS so_don_da_giao,
    COALESCE(SUM(CASE WHEN dh.trang_thai = 'hoan_thanh' THEN dh.tong_tien ELSE 0 END), 0) AS tong_doanh_thu
FROM "LinhKien".nhan_vien nv
LEFT JOIN "LinhKien".don_hang dh ON nv.id = dh.nhan_vien_id
GROUP BY nv.id, nv.ho_ten, nv.chuc_vu
ORDER BY tong_doanh_thu DESC;

COMMENT ON VIEW "LinhKien".v_doanh_thu_nhan_vien IS 'Thống kê tổng doanh số và số đơn đã giao thành công của từng nhân viên';

-- 3.2 View cảnh báo tồn kho thấp (tồn kho <= mức tối thiểu)
CREATE OR REPLACE VIEW "LinhKien".v_canh_bao_ton_kho AS
SELECT 
    sp.id AS san_pham_id,
    sp.ma_sku,
    sp.ten AS ten_san_pham,
    dm.ten AS ten_danh_muc,
    th.ten AS ten_thuong_hieu,
    tk.so_luong_ton,
    tk.muc_ton_toi_thieu,
    (tk.muc_ton_toi_thieu - tk.so_luong_ton) AS so_luong_thieu,
    tk.ngay_cap_nhat
FROM "LinhKien".san_pham sp
JOIN "LinhKien".ton_kho tk ON sp.id = tk.san_pham_id
JOIN "LinhKien".danh_muc dm ON sp.danh_muc_id = dm.id
JOIN "LinhKien".thuong_hieu th ON sp.thuong_hieu_id = th.id
WHERE tk.so_luong_ton <= tk.muc_ton_toi_thieu
ORDER BY tk.so_luong_ton ASC;

COMMENT ON VIEW "LinhKien".v_canh_bao_ton_kho IS 'Danh sách sản phẩm sắp hết hàng cần nhập thêm (tồn kho <= mức tối thiểu)';

-- 3.3 Materialized View tổng hợp doanh thu theo tháng kèm Unique Index hỗ trợ Refresh Concurrently
CREATE MATERIALIZED VIEW IF NOT EXISTS "LinhKien".mv_thong_ke_doanh_thu_thang AS
SELECT 
    TO_CHAR(ngay_dat, 'YYYY-MM') AS thang,
    COUNT(*) AS so_don_hang,
    SUM(tong_tien) AS tong_doanh_thu
FROM "LinhKien".don_hang
WHERE trang_thai = 'hoan_thanh'
GROUP BY TO_CHAR(ngay_dat, 'YYYY-MM')
ORDER BY thang ASC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_thong_ke_thang 
ON "LinhKien".mv_thong_ke_doanh_thu_thang(thang);

COMMENT ON MATERIALIZED VIEW "LinhKien".mv_thong_ke_doanh_thu_thang IS 'Bảng tổng hợp vật lý doanh thu theo tháng (hỗ trợ REFRESH CONCURRENTLY)';


-- ====================================================================
-- NHÓM 4: PL/pgSQL STORED FUNCTIONS & TRIGGERS NGHIỆP VỤ
-- ====================================================================

-- 4.1 Trigger 1: Tự động tính toán lại tong_tien trên don_hang khi thay đổi chi_tiet_don_hang
CREATE OR REPLACE FUNCTION "LinhKien".fn_cap_nhat_tong_tien_don_hang()
RETURNS TRIGGER AS $$
DECLARE
    v_don_hang_id INT;
    v_tong NUMERIC(14,0);
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_don_hang_id := OLD.don_hang_id;
    ELSE
        v_don_hang_id := NEW.don_hang_id;
    END IF;

    -- Tính tổng tiền đơn hàng: SUM(so_luong * don_gia - giam_gia)
    SELECT COALESCE(SUM(so_luong * don_gia - giam_gia), 0)
    INTO v_tong
    FROM "LinhKien".chi_tiet_don_hang
    WHERE don_hang_id = v_don_hang_id;

    UPDATE "LinhKien".don_hang
    SET tong_tien = v_tong
    WHERE id = v_don_hang_id;

    -- Xử lý trường hợp đặc biệt: UPDATE đổi don_hang_id sang đơn khác
    IF TG_OP = 'UPDATE' AND OLD.don_hang_id <> NEW.don_hang_id THEN
        SELECT COALESCE(SUM(so_luong * don_gia - giam_gia), 0)
        INTO v_tong
        FROM "LinhKien".chi_tiet_don_hang
        WHERE don_hang_id = OLD.don_hang_id;

        UPDATE "LinhKien".don_hang
        SET tong_tien = v_tong
        WHERE id = OLD.don_hang_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cap_nhat_tong_tien ON "LinhKien".chi_tiet_don_hang;
CREATE TRIGGER trg_cap_nhat_tong_tien
AFTER INSERT OR UPDATE OR DELETE ON "LinhKien".chi_tiet_don_hang
FOR EACH ROW
EXECUTE FUNCTION "LinhKien".fn_cap_nhat_tong_tien_don_hang();

-- 4.2 Trigger 2: Khi don_hang chuyển sang 'dang_giao' hoặc 'hoan_thanh', tự động trừ tồn kho
-- Nếu số lượng tồn không đủ, RAISE EXCEPTION chặn thao tác và rollback giao dịch!
CREATE OR REPLACE FUNCTION "LinhKien".fn_tru_ton_kho_khi_giao()
RETURNS TRIGGER AS $$
DECLARE
    r RECORD;
    v_ton_hien_tai INT;
BEGIN
    -- Chỉ kích hoạt khi trạng thái chuyển sang 'dang_giao' hoặc 'hoan_thanh' từ trạng thái trước đó
    IF (TG_OP = 'UPDATE' AND (OLD.trang_thai NOT IN ('dang_giao', 'hoan_thanh')) AND (NEW.trang_thai IN ('dang_giao', 'hoan_thanh')))
       OR (TG_OP = 'INSERT' AND NEW.trang_thai IN ('dang_giao', 'hoan_thanh')) THEN

        FOR r IN 
            SELECT san_pham_id, so_luong
            FROM "LinhKien".chi_tiet_don_hang
            WHERE don_hang_id = NEW.id
        LOOP
            -- Lấy số lượng tồn hiện tại và khóa dòng (FOR UPDATE)
            SELECT so_luong_ton INTO v_ton_hien_tai
            FROM "LinhKien".ton_kho
            WHERE san_pham_id = r.san_pham_id
            FOR UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Lỗi xuất kho: Sản phẩm ID % không tồn tại trong kho hàng!', r.san_pham_id;
            END IF;

            IF v_ton_hien_tai < r.so_luong THEN
                RAISE EXCEPTION 'Lỗi xuất kho: Sản phẩm ID % không đủ số lượng tồn (hiện có: %, yêu cầu xuất: %)! Thao tác bị hủy.',
                    r.san_pham_id, v_ton_hien_tai, r.so_luong;
            END IF;

            -- Khấu trừ tồn kho
            UPDATE "LinhKien".ton_kho
            SET so_luong_ton = so_luong_ton - r.so_luong,
                ngay_cap_nhat = NOW()
            WHERE san_pham_id = r.san_pham_id;
        END LOOP;

    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tru_ton_kho_khi_giao ON "LinhKien".don_hang;
CREATE TRIGGER trg_tru_ton_kho_khi_giao
AFTER UPDATE ON "LinhKien".don_hang
FOR EACH ROW
EXECUTE FUNCTION "LinhKien".fn_tru_ton_kho_khi_giao();

-- 4.3 Bảng Audit & Trigger 3: Lịch sử thay đổi giá niêm yết của linh kiện
CREATE TABLE IF NOT EXISTS "LinhKien".lich_su_thay_doi_gia (
    id SERIAL PRIMARY KEY,
    san_pham_id INT NOT NULL REFERENCES "LinhKien".san_pham(id) ON DELETE CASCADE,
    gia_cu NUMERIC(14,0) NOT NULL,
    gia_moi NUMERIC(14,0) NOT NULL,
    ngay_thay_doi TIMESTAMP NOT NULL DEFAULT NOW(),
    nguoi_thuc_hien VARCHAR(50) DEFAULT CURRENT_USER
);

COMMENT ON TABLE "LinhKien".lich_su_thay_doi_gia IS 'Lịch sử kiểm toán (audit log) biến động giá niêm yết của linh kiện';

CREATE OR REPLACE FUNCTION "LinhKien".fn_ghi_log_thay_doi_gia()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.gia_niem_yet IS DISTINCT FROM NEW.gia_niem_yet THEN
        INSERT INTO "LinhKien".lich_su_thay_doi_gia (
            san_pham_id,
            gia_cu,
            gia_moi,
            ngay_thay_doi,
            nguoi_thuc_hien
        ) VALUES (
            OLD.id,
            OLD.gia_niem_yet,
            NEW.gia_niem_yet,
            NOW(),
            CURRENT_USER
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ghi_log_thay_doi_gia ON "LinhKien".san_pham;
CREATE TRIGGER trg_ghi_log_thay_doi_gia
AFTER UPDATE OF gia_niem_yet ON "LinhKien".san_pham
FOR EACH ROW
EXECUTE FUNCTION "LinhKien".fn_ghi_log_thay_doi_gia();


-- ====================================================================
-- NHÓM 5: RBAC, ROW-LEVEL SECURITY (RLS) & COLUMN-LEVEL SECURITY (CLS)
-- ====================================================================

-- 5.1 Tạo Role nhân viên bán hàng
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nhan_vien_ban_hang') THEN
        CREATE ROLE nhan_vien_ban_hang LOGIN PASSWORD 'nhanvien123';
    ELSE
        ALTER ROLE nhan_vien_ban_hang WITH LOGIN PASSWORD 'nhanvien123';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO nhan_vien_ban_hang', current_database());
    ALTER ROLE nhan_vien_ban_hang SET search_path TO "LinhKien", public;
END $$;

-- 5.2 Phân quyền dữ liệu & Column-Level Security (CLS)
-- Cấp quyền USAGE trên schema LinhKien
GRANT USAGE ON SCHEMA "LinhKien" TO nhan_vien_ban_hang;

-- Cấp quyền SELECT trên các bảng danh mục, khách hàng, đơn hàng, kho
GRANT SELECT ON "LinhKien".danh_muc, "LinhKien".thuong_hieu, "LinhKien".nha_cung_cap,
                "LinhKien".khach_hang, "LinhKien".dia_chi, "LinhKien".nhan_vien,
                "LinhKien".don_hang, "LinhKien".chi_tiet_don_hang, "LinhKien".thanh_toan,
                "LinhKien".ton_kho, "LinhKien".v_doanh_thu_nhan_vien, "LinhKien".v_canh_bao_ton_kho
TO nhan_vien_ban_hang;
-- Không cấp materialized view doanh thu cho nhân viên: MV không áp dụng RLS (xem nang_cap_bao_mat_toi_uu.sql)
REVOKE ALL ON "LinhKien".mv_thong_ke_doanh_thu_thang FROM nhan_vien_ban_hang;

-- Thực hiện Column-Level Security (CLS) trên bảng san_pham:
-- Nhân viên bán hàng được xem tên, mã SKU, giá bán niêm yết, thông số kỹ thuật...
-- NHƯNG TUYỆT ĐỐI BỊ CHẶN XEM GIÁ VỐN (gia_von)!
REVOKE ALL ON "LinhKien".san_pham FROM nhan_vien_ban_hang;
GRANT SELECT (id, ma_sku, ten, danh_muc_id, thuong_hieu_id, gia_niem_yet, bao_hanh_thang, ngay_ra_mat, dang_kinh_doanh, thong_so_ky_thuat)
ON "LinhKien".san_pham TO nhan_vien_ban_hang;
REVOKE SELECT (gia_von) ON "LinhKien".san_pham FROM nhan_vien_ban_hang;

-- Cấp quyền SELECT các đối tượng mới cho role text2sql_readonly (tuân thủ Least Privilege, chặn xem gia_von)
GRANT SELECT ON ALL TABLES IN SCHEMA "LinhKien" TO text2sql_readonly;
REVOKE SELECT (gia_von) ON "LinhKien".san_pham FROM text2sql_readonly;
-- Không cho role chỉ đọc đọc bảng tài khoản (password_hash); đăng nhập qua hàm fn_xac_thuc_nguoi_dung
REVOKE ALL ON "LinhKien".app_users FROM text2sql_readonly;
-- Bảng ánh xạ role -> nhân viên (tạo trong nang_cap_bao_mat_toi_uu.sql) chỉ DBA được đọc
DO $$
BEGIN
    IF to_regclass('"LinhKien".tai_khoan_nhan_vien') IS NOT NULL THEN
        EXECUTE 'REVOKE ALL ON "LinhKien".tai_khoan_nhan_vien FROM PUBLIC, text2sql_readonly, manager_readonly, nhan_vien_ban_hang';
    END IF;
    -- Nhật ký câu hỏi chưa hiểu (hoc_tu_cau_chua_hieu.sql) chứa câu hỏi thô của người dùng: chỉ quản trị được đọc
    IF to_regclass('"LinhKien".cau_hoi_chua_hieu') IS NOT NULL THEN
        EXECUTE 'REVOKE ALL ON "LinhKien".cau_hoi_chua_hieu FROM PUBLIC, text2sql_readonly, manager_readonly, nhan_vien_ban_hang';
    END IF;
    IF to_regclass('"LinhKien".lich_su_huan_luyen') IS NOT NULL THEN
        EXECUTE 'REVOKE ALL ON "LinhKien".lich_su_huan_luyen FROM PUBLIC, text2sql_readonly, manager_readonly, nhan_vien_ban_hang';
    END IF;
END $$;
GRANT SELECT ON "LinhKien".mv_thong_ke_doanh_thu_thang TO text2sql_readonly;

-- 5.3 Kích hoạt Row-Level Security (RLS) trên bảng don_hang
ALTER TABLE "LinhKien".don_hang ENABLE ROW LEVEL SECURITY;

-- Chính sách RLS (bản an toàn, không thể giả mạo bằng SET biến phiên) được định nghĩa trong
-- database/nang_cap_bao_mat_toi_uu.sql: bảng ánh xạ tai_khoan_nhan_vien + role nv_<id> + hàm
-- fn_nhan_vien_cua_role(current_user). Thiết kế cũ dùng current_setting('app.current_nhan_vien_id')
-- đã bị loại bỏ vì nhân viên có thể tự SET biến này để xem đơn của người khác.

-- ============================================================================
-- NHÓM 6: PHÂN QUYỀN ROLE: manager_readonly (Tác nhân Manager)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'manager_readonly') THEN
        CREATE ROLE manager_readonly LOGIN PASSWORD 'manager_readonly_pwd';
    ELSE
        ALTER ROLE manager_readonly WITH LOGIN PASSWORD 'manager_readonly_pwd';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO manager_readonly', current_database());
    ALTER ROLE manager_readonly SET search_path TO "LinhKien", public;
END $$;

-- Bảng phục vụ AI 6 (Backup thông minh) - tạo tại đây để script tái tạo được toàn bộ hệ thống
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

-- Cấp quyền Schema LinhKien
GRANT USAGE ON SCHEMA "LinhKien" TO manager_readonly;

-- Cấp SELECT trên tất cả các bảng nghiệp vụ và bảng người dùng
GRANT SELECT ON "LinhKien".danh_muc, "LinhKien".thuong_hieu, "LinhKien".nha_cung_cap,
                "LinhKien".khach_hang, "LinhKien".dia_chi, "LinhKien".nhan_vien,
                "LinhKien".don_hang, "LinhKien".chi_tiet_don_hang, "LinhKien".thanh_toan,
                "LinhKien".ton_kho, "LinhKien".phieu_nhap, "LinhKien".chi_tiet_phieu_nhap,
                "LinhKien".san_pham_nha_cung_cap,
                "LinhKien".backup_history, "LinhKien".backup_size_log
TO manager_readonly;

-- BẢO MẬT MỨC CỘT (COLUMN-LEVEL SECURITY - CLS): ẨN HOÀN TOÀN CỘT gia_von KHỎI MANAGER
REVOKE ALL ON "LinhKien".san_pham FROM manager_readonly;
GRANT SELECT (id, ma_sku, ten, danh_muc_id, thuong_hieu_id, gia_niem_yet,
              bao_hanh_thang, ngay_ra_mat, dang_kinh_doanh, thong_so_ky_thuat)
ON "LinhKien".san_pham TO manager_readonly;

-- Cấp SELECT trên các Views & Materialized Views phục vụ báo cáo
GRANT SELECT ON "LinhKien".v_doanh_thu_nhan_vien, "LinhKien".v_canh_bao_ton_kho,
                "LinhKien".mv_thong_ke_doanh_thu_thang
TO manager_readonly;
