-- ==============================================================================
-- HỌC TỪ CÂU HỎI CHƯA HIỂU (Human-in-the-loop) CHO AI 1 VÀ AI 2
-- ------------------------------------------------------------------------------
-- 1. Bảng cau_hoi_chua_hieu : nhật ký các câu AI 1 / AI 2 chưa trả lời được (gộp câu trùng).
-- 2. Bảng lich_su_huan_luyen: mỗi lần Admin bấm "Huấn luyện lại" (áp dụng hay bị từ chối, vì sao).
-- 3. fn_ghi_cau_hoi_chua_hieu(): gom toàn bộ logic ghi (gộp câu trùng, cắt độ dài, giới hạn 5.000 câu
--    chờ duyệt) vào một hàm. Tiến trình web gọi hàm này bằng kết nối quản trị (giống security_alert_log);
--    role chatbot text2sql_readonly KHÔNG có quyền gọi -> câu SQL do AI sinh ra không thể ghi bảng này.
-- 4. fn_mau_hoc_da_duyet(): role chỉ đọc lấy các mẫu ĐÃ DUYỆT + ĐÃ HUẤN LUYỆN để dựng lại mô hình
--    khi khởi động web (chỉ thấy câu đã duyệt, không đọc được câu hỏi thô chờ duyệt của người khác).
-- Việc duyệt / huấn luyện lại chỉ Admin làm, qua kết nối quản trị (giống sao lưu, phân vùng).
--
-- Chạy được nhiều lần (idempotent). Chạy bằng tài khoản quản trị (postgres) trên LinhKien_DB.
-- ==============================================================================
SET search_path TO "LinhKien", public;

CREATE TABLE IF NOT EXISTS "LinhKien".cau_hoi_chua_hieu (
    id                  BIGSERIAL PRIMARY KEY,
    cau_hoi             VARCHAR(300) NOT NULL,                 -- câu gốc (đã che SĐT / email)
    cau_chuan_hoa       VARCHAR(300) NOT NULL,                 -- chữ thường, bỏ dấu, gọn khoảng trắng -> gộp câu trùng
    ly_do               VARCHAR(30)  NOT NULL,
    goi_y_ml            JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- [{"intent": ..., "p": ...}] mô hình đoán gần nhất
    lua_chon_dem        JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- {"INTENT": số lần người dùng bấm gợi ý này}
    intent_nguoi_dung_chon VARCHAR(50),                        -- intent được người dùng chọn NHIỀU NHẤT (gợi ý cho Admin)
    so_lan_gap          INTEGER      NOT NULL DEFAULT 1,
    lan_dau             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    lan_cuoi            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    nguoi_hoi_dau       VARCHAR(50),                           -- dùng để giới hạn số câu mới mỗi người / ngày
    nguoi_hoi_cuoi      VARCHAR(50),
    trang_thai          VARCHAR(20)  NOT NULL DEFAULT 'cho_duyet',
    loai_nhan           VARCHAR(10),                           -- 'intent' (AI 1) | 'nhu_cau' (AI 2)
    nhan                VARCHAR(80),                           -- tên intent hoặc tên nhu cầu Knowledge Graph
    cum_tu_hoc          VARCHAR(120),                          -- AI 2: cụm từ thêm làm bí danh của nhu cầu
    ghi_chu             VARCHAR(300),
    nguoi_duyet         VARCHAR(50),
    thoi_diem_duyet     TIMESTAMPTZ,
    da_huan_luyen       BOOLEAN      NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_chh_cau_chuan_hoa UNIQUE (cau_chuan_hoa),
    CONSTRAINT chk_chh_ly_do CHECK (ly_do IN ('ngoai_pham_vi', 'hoi_lai', 'dieu_kien_chua_ho_tro', 'ai2_khong_ket_qua')),
    CONSTRAINT chk_chh_trang_thai CHECK (trang_thai IN ('cho_duyet', 'da_gan_nhan', 'can_mau_sql_moi', 'bo_qua')),
    CONSTRAINT chk_chh_so_lan CHECK (so_lan_gap >= 1),
    CONSTRAINT chk_chh_thoi_gian CHECK (lan_cuoi >= lan_dau),
    CONSTRAINT chk_chh_goi_y_mang CHECK (jsonb_typeof(goi_y_ml) = 'array'),
    CONSTRAINT chk_chh_lua_chon_dem CHECK (jsonb_typeof(lua_chon_dem) = 'object'),
    CONSTRAINT chk_chh_intent_chon CHECK (intent_nguoi_dung_chon IS NULL OR intent_nguoi_dung_chon ~ '^[A-Z_]{3,50}$'),
    CONSTRAINT chk_chh_loai_nhan CHECK (loai_nhan IS NULL OR loai_nhan IN ('intent', 'nhu_cau')),
    -- Đã gán nhãn <=> có đủ loại nhãn + nhãn; nhu cầu AI 2 bắt buộc có cụm từ học
    CONSTRAINT chk_chh_nhan_day_du CHECK (
        (trang_thai = 'da_gan_nhan') = (loai_nhan IS NOT NULL AND nhan IS NOT NULL)
    ),
    -- Loại nhãn và nhãn luôn đi cùng nhau; cụm từ học chỉ dành cho nhu cầu AI 2
    CONSTRAINT chk_chh_loai_va_nhan CHECK ((loai_nhan IS NULL) = (nhan IS NULL)),
    CONSTRAINT chk_chh_cum_tu_chi_ai2 CHECK (cum_tu_hoc IS NULL OR coalesce(loai_nhan, '') = 'nhu_cau'),
    -- (coalesce: CHECK coi NULL là "đạt", nên phải đổi NULL thành giá trị sai rõ ràng)
    CONSTRAINT chk_chh_nhu_cau_co_cum_tu CHECK (loai_nhan IS DISTINCT FROM 'nhu_cau' OR coalesce(length(btrim(cum_tu_hoc)), 0) >= 3),
    CONSTRAINT chk_chh_intent_dinh_dang CHECK (loai_nhan IS DISTINCT FROM 'intent' OR coalesce(nhan, '') ~ '^[A-Z_]{3,50}$'),
    -- Mọi trạng thái khác "chờ duyệt" phải ghi rõ ai duyệt, lúc nào
    CONSTRAINT chk_chh_co_nguoi_duyet CHECK (
        trang_thai = 'cho_duyet' OR (nguoi_duyet IS NOT NULL AND thoi_diem_duyet IS NOT NULL)
    ),
    -- Chỉ câu đã gán nhãn mới có thể đã được huấn luyện
    CONSTRAINT chk_chh_huan_luyen CHECK (NOT da_huan_luyen OR trang_thai = 'da_gan_nhan')
);

COMMENT ON TABLE "LinhKien".cau_hoi_chua_hieu IS
    'Câu hỏi AI 1/AI 2 chưa hiểu, chờ Admin duyệt để làm dữ liệu huấn luyện (human-in-the-loop).';

-- Màn hình duyệt: lấy câu chờ duyệt, câu hay gặp nhất lên trước (chỉ mục một phần)
CREATE INDEX IF NOT EXISTS idx_chh_cho_duyet
    ON "LinhKien".cau_hoi_chua_hieu (so_lan_gap DESC, lan_cuoi DESC)
    WHERE trang_thai = 'cho_duyet';
-- Dựng lại mô hình lúc khởi động: chỉ đọc các mẫu đã gán nhãn
CREATE INDEX IF NOT EXISTS idx_chh_da_gan_nhan
    ON "LinhKien".cau_hoi_chua_hieu (loai_nhan, da_huan_luyen)
    WHERE trang_thai = 'da_gan_nhan';

CREATE TABLE IF NOT EXISTS "LinhKien".lich_su_huan_luyen (
    id                  BIGSERIAL PRIMARY KEY,
    thoi_diem           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    nguoi_thuc_hien     VARCHAR(50)  NOT NULL,
    so_mau_goc          INTEGER      NOT NULL CHECK (so_mau_goc >= 0),
    so_mau_hoc_intent   INTEGER      NOT NULL CHECK (so_mau_hoc_intent >= 0),
    so_cum_tu_nhu_cau   INTEGER      NOT NULL CHECK (so_cum_tu_nhu_cau >= 0),
    do_chinh_xac_cu     NUMERIC(5,2) CHECK (do_chinh_xac_cu BETWEEN 0 AND 100),
    do_chinh_xac_moi    NUMERIC(5,2) CHECK (do_chinh_xac_moi BETWEEN 0 AND 100),
    ket_qua             VARCHAR(10)  NOT NULL CHECK (ket_qua IN ('ap_dung', 'tu_choi')),
    ghi_chu             TEXT
);

-- ------------------------------------------------------------------------------
-- Ghi (hoặc cộng dồn) một câu chưa hiểu. Tiến trình web gọi bằng kết nối quản trị:
--   SELECT "LinhKien".fn_ghi_cau_hoi_chua_hieu(%s, %s, %s, %s::jsonb, %s);
-- Chống làm đầy bảng: tối đa 5.000 câu chờ duyệt và 200 câu MỚI mỗi người / 24 giờ
-- (câu đã có thì luôn được cộng dồn). Khóa tư vấn (advisory lock) để hai yêu cầu song song không
-- cùng vượt giới hạn.
-- ------------------------------------------------------------------------------
DROP FUNCTION IF EXISTS "LinhKien".fn_ghi_cau_hoi_chua_hieu(TEXT, TEXT, TEXT, JSONB, TEXT, TEXT);
CREATE OR REPLACE FUNCTION "LinhKien".fn_ghi_cau_hoi_chua_hieu(
    p_cau_hoi        TEXT,
    p_cau_chuan_hoa  TEXT,
    p_ly_do          TEXT,
    p_goi_y          JSONB DEFAULT '[]'::jsonb,
    p_nguoi_hoi      TEXT  DEFAULT NULL
) RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = "LinhKien", pg_temp
AS $$
DECLARE
    v_id         BIGINT;
    v_chuan_hoa  TEXT := left(btrim(coalesce(p_cau_chuan_hoa, '')), 300);
    v_goi_y      JSONB := CASE WHEN jsonb_typeof(p_goi_y) = 'array' THEN p_goi_y ELSE '[]'::jsonb END;
    v_nguoi      TEXT := nullif(left(btrim(coalesce(p_nguoi_hoi, '')), 50), '');
BEGIN
    IF length(v_chuan_hoa) < 2 OR btrim(coalesce(p_cau_hoi, '')) = '' THEN
        RETURN NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM cau_hoi_chua_hieu WHERE cau_chuan_hoa = v_chuan_hoa) THEN
        PERFORM pg_advisory_xact_lock(hashtext('LinhKien.cau_hoi_chua_hieu.gioi_han'));
        IF (SELECT count(*) FROM cau_hoi_chua_hieu WHERE trang_thai = 'cho_duyet') >= 5000 THEN
            RETURN NULL;
        END IF;
        IF v_nguoi IS NOT NULL AND (
            SELECT count(*) FROM cau_hoi_chua_hieu
            WHERE nguoi_hoi_dau = v_nguoi AND lan_dau > now() - interval '24 hours'
        ) >= 200 THEN
            RETURN NULL;
        END IF;
    END IF;

    INSERT INTO cau_hoi_chua_hieu AS c
        (cau_hoi, cau_chuan_hoa, ly_do, goi_y_ml, nguoi_hoi_dau, nguoi_hoi_cuoi)
    VALUES
        (left(btrim(p_cau_hoi), 300), v_chuan_hoa, p_ly_do, v_goi_y, v_nguoi, v_nguoi)
    ON CONFLICT (cau_chuan_hoa) DO UPDATE SET
        so_lan_gap = c.so_lan_gap + 1,
        lan_cuoi = now(),
        nguoi_hoi_cuoi = EXCLUDED.nguoi_hoi_cuoi,
        goi_y_ml = CASE WHEN jsonb_array_length(EXCLUDED.goi_y_ml) > 0 THEN EXCLUDED.goi_y_ml ELSE c.goi_y_ml END
    RETURNING c.id INTO v_id;

    RETURN v_id;
END;
$$;

-- ------------------------------------------------------------------------------
-- Người dùng bấm gợi ý "Ý bạn là ..." VÀ câu trả lời chạy thành công: cộng 1 phiếu cho intent đó.
-- Không cộng so_lan_gap (cùng một lượt hỏi), chỉ áp dụng cho câu còn CHỜ DUYỆT; intent gợi ý cho
-- Admin = intent có nhiều phiếu nhất (không phải "người bấm cuối cùng thắng").
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION "LinhKien".fn_ghi_lua_chon_goi_y(
    p_cau_chuan_hoa  TEXT,
    p_intent         TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = "LinhKien", pg_temp
AS $$
DECLARE
    v_dem JSONB;
BEGIN
    IF p_intent IS NULL OR p_intent !~ '^[A-Z_]{3,50}$' THEN
        RETURN FALSE;
    END IF;
    UPDATE cau_hoi_chua_hieu c
    SET lua_chon_dem = jsonb_set(c.lua_chon_dem, ARRAY[p_intent],
                                 to_jsonb(coalesce((c.lua_chon_dem ->> p_intent)::int, 0) + 1))
    WHERE c.cau_chuan_hoa = left(btrim(coalesce(p_cau_chuan_hoa, '')), 300) AND c.trang_thai = 'cho_duyet'
    RETURNING c.lua_chon_dem INTO v_dem;
    IF v_dem IS NULL THEN
        RETURN FALSE;
    END IF;
    UPDATE cau_hoi_chua_hieu c
    SET intent_nguoi_dung_chon = (
        SELECT e.key FROM jsonb_each_text(v_dem) e ORDER BY e.value::int DESC, e.key LIMIT 1)
    WHERE c.cau_chuan_hoa = left(btrim(coalesce(p_cau_chuan_hoa, '')), 300);
    RETURN TRUE;
END;
$$;

-- ------------------------------------------------------------------------------
-- Các mẫu ĐÃ DUYỆT và ĐÃ HUẤN LUYỆN (dựng lại mô hình khi khởi động web).
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION "LinhKien".fn_mau_hoc_da_duyet()
RETURNS TABLE (cau_hoi TEXT, loai_nhan TEXT, nhan TEXT, cum_tu_hoc TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = "LinhKien", pg_temp
AS $$
    SELECT c.cau_hoi::text, c.loai_nhan::text, c.nhan::text, c.cum_tu_hoc::text
    FROM cau_hoi_chua_hieu c
    WHERE c.trang_thai = 'da_gan_nhan' AND c.da_huan_luyen
    ORDER BY c.id;
$$;

-- ------------------------------------------------------------------------------
-- PHÂN QUYỀN: bảng và hàm ghi chỉ dành cho quản trị; role web chỉ được gọi hàm ĐỌC mẫu đã duyệt.
-- (ALTER DEFAULT PRIVILEGES trong schema.sql tự cấp SELECT bảng mới cho text2sql_readonly -> thu hồi.)
-- ------------------------------------------------------------------------------
REVOKE ALL ON "LinhKien".cau_hoi_chua_hieu, "LinhKien".lich_su_huan_luyen FROM PUBLIC;
REVOKE ALL ON SEQUENCE "LinhKien".cau_hoi_chua_hieu_id_seq, "LinhKien".lich_su_huan_luyen_id_seq FROM PUBLIC;
REVOKE ALL ON FUNCTION "LinhKien".fn_ghi_cau_hoi_chua_hieu(TEXT, TEXT, TEXT, JSONB, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION "LinhKien".fn_ghi_lua_chon_goi_y(TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION "LinhKien".fn_mau_hoc_da_duyet() FROM PUBLIC;

DO $$
DECLARE r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['text2sql_readonly', 'manager_readonly', 'nhan_vien_ban_hang'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON "LinhKien".cau_hoi_chua_hieu, "LinhKien".lich_su_huan_luyen FROM %I', r);
            EXECUTE format('REVOKE ALL ON SEQUENCE "LinhKien".cau_hoi_chua_hieu_id_seq, "LinhKien".lich_su_huan_luyen_id_seq FROM %I', r);
        END IF;
    END LOOP;
    -- Role của web (Admin dùng text2sql_readonly, Manager dùng manager_readonly) chỉ được ĐỌC mẫu đã duyệt
    FOREACH r IN ARRAY ARRAY['text2sql_readonly', 'manager_readonly'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON FUNCTION "LinhKien".fn_ghi_cau_hoi_chua_hieu(TEXT, TEXT, TEXT, JSONB, TEXT) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION "LinhKien".fn_ghi_lua_chon_goi_y(TEXT, TEXT) FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION "LinhKien".fn_mau_hoc_da_duyet() TO %I', r);
        END IF;
    END LOOP;
END $$;

-- Kiểm tra nhanh sau khi chạy:
--   SELECT has_table_privilege('text2sql_readonly', '"LinhKien".cau_hoi_chua_hieu', 'SELECT');   -- false
--   SELECT has_function_privilege('text2sql_readonly', '"LinhKien".fn_ghi_cau_hoi_chua_hieu(text,text,text,jsonb,text)', 'EXECUTE');  -- false
--   SELECT has_function_privilege('text2sql_readonly', '"LinhKien".fn_mau_hoc_da_duyet()', 'EXECUTE');                                    -- true
