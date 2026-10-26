-- ==============================================================================
-- CẢNH BÁO AI THỜI GIAN THỰC BẰNG TRIGGER + LISTEN/NOTIFY
--
-- Gồm 2 luồng cảnh báo:
--   1. Kênh 'ai_security_alert' : AI 3 (Zero-Trust Guard) ghi cảnh báo mức HIGH vào bảng
--      security_alert_log -> trigger phát pg_notify.
--   2. Kênh 'ai_order_anomaly'  : Trigger trên don_hang tự tính z-score của tổng tiền đơn
--      so với phân phối 90 ngày gần nhất; đơn lệch > 3 độ lệch chuẩn -> pg_notify.
--
-- Lắng nghe:
--   python ai_service/security_listener.py
-- ==============================================================================
SET search_path TO "LinhKien", public;

-- ------------------------------------------------------------------------------
-- 1. BẢNG NHẬT KÝ CẢNH BÁO AN NINH (AI 3)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "LinhKien".security_alert_log (
    id            BIGSERIAL PRIMARY KEY,
    thoi_diem     TIMESTAMP     NOT NULL DEFAULT NOW(),
    nguoi_dung    VARCHAR(100)  NOT NULL,
    dia_chi_ip    VARCHAR(64),
    diem_rui_ro   NUMERIC(5,1)  NOT NULL CHECK (diem_rui_ro BETWEEN 0 AND 100),
    muc_do        VARCHAR(10)   NOT NULL CHECK (muc_do IN ('NORMAL', 'WARNING', 'HIGH')),
    cau_sql       TEXT,
    cac_yeu_to    JSONB         NOT NULL DEFAULT '[]'::jsonb,
    da_xu_ly      BOOLEAN       NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE "LinhKien".security_alert_log IS 'Cảnh báo an ninh do AI 3 sinh ra; mỗi bản ghi mới phát pg_notify kênh ai_security_alert';

CREATE INDEX IF NOT EXISTS idx_security_alert_chua_xu_ly
    ON "LinhKien".security_alert_log (thoi_diem DESC)
    WHERE da_xu_ly = FALSE;                               -- Partial index: chỉ cảnh báo chưa xử lý

CREATE OR REPLACE FUNCTION "LinhKien".fn_notify_security_alert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'ai_security_alert',
        json_build_object(
            'id',          NEW.id,
            'thoi_diem',   NEW.thoi_diem,
            'nguoi_dung',  NEW.nguoi_dung,
            'ip',          NEW.dia_chi_ip,
            'diem_rui_ro', NEW.diem_rui_ro,
            'muc_do',      NEW.muc_do,
            'cau_sql',     left(NEW.cau_sql, 300),
            'cac_yeu_to',  NEW.cac_yeu_to
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_security_alert_notify ON "LinhKien".security_alert_log;
CREATE TRIGGER trg_security_alert_notify
    AFTER INSERT ON "LinhKien".security_alert_log
    FOR EACH ROW EXECUTE FUNCTION "LinhKien".fn_notify_security_alert();

-- ------------------------------------------------------------------------------
-- 2. PHÁT HIỆN ĐƠN HÀNG BẤT THƯỜNG BẰNG Z-SCORE NGAY TRONG CSDL
--    (tong_tien được trigger fn_cap_nhat_tong_tien_don_hang cập nhật sau khi thêm chi tiết,
--     nên lắng nghe sự kiện UPDATE OF tong_tien)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION "LinhKien".fn_notify_order_anomaly()
RETURNS TRIGGER AS $$
DECLARE
    v_avg   NUMERIC;
    v_std   NUMERIC;
    v_n     BIGINT;
    v_z     NUMERIC;
BEGIN
    IF NEW.tong_tien IS NULL OR NEW.tong_tien <= 0 THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.tong_tien IS NOT DISTINCT FROM OLD.tong_tien THEN
        RETURN NEW;
    END IF;

    SELECT AVG(tong_tien), STDDEV_SAMP(tong_tien), COUNT(*)
      INTO v_avg, v_std, v_n
      FROM "LinhKien".don_hang
     WHERE id <> NEW.id
       AND tong_tien > 0
       AND ngay_dat >= NOW() - INTERVAL '90 days';

    -- Cần đủ dữ liệu để thống kê có ý nghĩa
    IF v_n < 30 OR v_std IS NULL OR v_std = 0 THEN
        RETURN NEW;
    END IF;

    v_z := (NEW.tong_tien - v_avg) / v_std;

    IF abs(v_z) > 3 THEN
        PERFORM pg_notify(
            'ai_order_anomaly',
            json_build_object(
                'don_hang_id',  NEW.id,
                'khach_hang_id', NEW.khach_hang_id,
                'kenh_ban',     NEW.kenh_ban,
                'tong_tien',    NEW.tong_tien,
                'trung_binh_90_ngay', round(v_avg, 0),
                'z_score',      round(v_z, 2),
                'thong_diep',   'Đơn hàng có tổng tiền lệch ' || round(v_z, 1) || ' độ lệch chuẩn so với 90 ngày gần nhất'
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_order_anomaly_notify ON "LinhKien".don_hang;
CREATE TRIGGER trg_order_anomaly_notify
    AFTER INSERT OR UPDATE OF tong_tien ON "LinhKien".don_hang
    FOR EACH ROW EXECUTE FUNCTION "LinhKien".fn_notify_order_anomaly();

-- ------------------------------------------------------------------------------
-- 3. KỊCH BẢN DEMO (chạy tarong pgAdmin khi security_listener.py đang lắng nghe)
-- ------------------------------------------------------------------------------
-- a) Giả lập AI 3 phát hiện truy vấn nguy cơ cao:
-- INSERT INTO "LinhKien".security_alert_log (nguoi_dung, dia_chi_ip, diem_rui_ro, muc_do, cau_sql, cac_yeu_to)
-- VALUES ('sale_staff', '118.69.182.4', 95, 'HIGH', 'SELECT * FROM khach_hang',
--         '["Truy cập bảng nhạy cảm khach_hang", "Ngoài giờ làm việc (2h sáng)"]');
--
-- b) Tạo một đơn hàng giá trị bất thường để kích hoạt cảnh báo z-score:
-- UPDATE "LinhKien".don_hang SET tong_tien = 999000000 WHERE id = (SELECT MAX(id) FROM "LinhKien".don_hang);
