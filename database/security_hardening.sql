-- ==============================================================================
-- PHÂN QUYỀN BẢO MẬT BỔ SUNG (SECURITY HARDENING) CHO text2sql_readonly
-- Tước quyền truy cập cột nhạy cảm 'gia_von' trên bảng san_pham (Least Privilege)
-- ==============================================================================
SET search_path TO "LinhKien", public;

REVOKE ALL ON "LinhKien".san_pham FROM text2sql_readonly;
GRANT SELECT (id, ma_sku, ten, danh_muc_id, thuong_hieu_id, gia_niem_yet,
              bao_hanh_thang, ngay_ra_mat, dang_kinh_doanh, thong_so_ky_thuat)
      ON "LinhKien".san_pham TO text2sql_readonly;
REVOKE SELECT (gia_von) ON "LinhKien".san_pham FROM text2sql_readonly;
