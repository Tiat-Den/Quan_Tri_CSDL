"""
HỌC TỪ CÂU HỎI CHƯA HIỂU (Human-in-the-loop) CHO AI 1 VÀ AI 2.

Vòng lặp 4 bước:
1. GHI NHẬT KÝ: câu AI 1 / AI 2 chưa trả lời được được ghi vào bảng "LinhKien".cau_hoi_chua_hieu
   (gộp câu trùng, đếm số lần gặp, kèm 3 intent mô hình đoán gần nhất). Tiến trình web ghi bằng kết nối
   quản trị qua hàm fn_ghi_cau_hoi_chua_hieu() (giống security_alert_log); role chatbot text2sql_readonly
   vừa luôn ở chế độ read-only, vừa không có quyền gọi hàm này -> SQL do AI sinh ra không ghi được bảng.
   KHÔNG ghi: câu bị AI 3 chặn (dữ liệu độc không được làm dữ liệu huấn luyện); SĐT / email bị che.
2. NHÃN TỰ NHIÊN: khi người dùng bấm nút gợi ý "Ý bạn là ...", lựa chọn đó được lưu kèm câu hỏi.
3. DUYỆT (chỉ Admin): gán câu vào intent có sẵn (AI 1), vào nhu cầu Knowledge Graph (AI 2),
   đánh dấu "cần mẫu SQL mới" hoặc bỏ qua. KHÔNG tự học khi chưa duyệt -> chống đầu độc dữ liệu.
4. HUẤN LUYỆN LẠI CÓ KIỂM SOÁT: dựng mô hình ứng viên = dữ liệu gốc + câu đã duyệt, đánh giá trên
   bộ 50 câu chuẩn (eval/text2sql_gold_50.json). Chỉ áp dụng khi số câu đúng KHÔNG giảm; ngược lại
   giữ mô hình cũ và báo câu nào bị hỏng. Mỗi lần chạy được ghi vào bảng lich_su_huan_luyen.

Giới hạn (nói rõ khi bảo vệ): AI 1 chỉ học được CÁCH DIỄN ĐẠT MỚI cho loại câu hỏi đã có mẫu SQL.
Loại câu hỏi hoàn toàn mới phải viết thêm mẫu SQL -> đánh dấu "cần mẫu SQL mới" để làm sau.
"""
import json
import logging
import os
import re
import threading
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.db import execute_query, get_connection
logger = logging.getLogger("ai_service.learning_loop")

_cand1 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval", "text2sql_gold_50.json")
_cand2 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "text2sql_gold_50.json")
GOLD_PATH = _cand1 if os.path.exists(_cand1) else _cand2

REASONS = {
    "ngoai_pham_vi": "Ngoài phạm vi",
    "hoi_lai": "Phải hỏi lại (độ tin cậy thấp)",
    "dieu_kien_chua_ho_tro": "Điều kiện chưa hỗ trợ",
    "ai2_khong_ket_qua": "AI 2 không tìm thấy linh kiện",
}
STATUSES = {
    "cho_duyet": "Chờ duyệt",
    "da_gan_nhan": "Đã gán nhãn",
    "can_mau_sql_moi": "Cần mẫu SQL mới",
    "bo_qua": "Bỏ qua",
}
MIN_PHRASE_LEN = 3
MAX_PHRASE_LEN = 120

_retrain_lock = threading.Lock()

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# SĐT Việt Nam: 0912345678, 0912 345 678, 0912.345.678, 0912 - 345 - 678, +84 912 345 678, (+84) 912..., +84 (0) 912...
_RE_PHONE = re.compile(r"(?<![\w+])(?:\(?\+?84\)?|0)[\s.\-()]*(?:\d[\s.\-()]*){7,10}\d(?!\d)")
_RE_LONG_NUMBER = re.compile(r"(?<!\d)\d{9,}(?!\d)")


# ==============================================================================
# TIỆN ÍCH
# ==============================================================================
def learnable_intents() -> Dict[str, str]:
    """Intent có thể gán nhãn = intent đã có mẫu SQL và nhãn tiếng Việt (danh sách trắng)."""
    from app.ai_1_text2sql.pipeline import INTENT_LABELS
    return dict(INTENT_LABELS)


def knowledge_needs() -> List[str]:
    """Tên các nhu cầu trong Knowledge Graph (AI 2) có thể gán nhãn."""
    from app.ai_2_semantic.knowledge_graph import get_knowledge_graph
    return sorted(get_knowledge_graph().needs.keys())


def mask_pii(text: str) -> str:
    """Che email, số điện thoại, dãy số dài trước khi lưu câu hỏi (không lưu dữ liệu cá nhân)."""
    t = _RE_EMAIL.sub("<email>", text or "")
    t = _RE_PHONE.sub("<sđt>", t)
    return _RE_LONG_NUMBER.sub("<số>", t)


def normalize_key(text: str) -> str:
    """
    Khóa gộp câu trùng: chữ thường, bỏ dấu câu, gọn khoảng trắng. GIỮ dấu tiếng Việt để không gộp nhầm
    hai câu khác nghĩa (vd "bán" và "bàn").
    """
    t = unicodedata.normalize("NFC", (text or "").lower())
    t = re.sub(r"[^\w<>\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:300]


def ml_suggestions(question: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """3 intent mô hình học máy đoán gần nhất kèm xác suất (bỏ lớp OUT_OF_SCOPE)."""
    try:
        from app.ai_1_text2sql.ml_intent_classifier import OUT_OF_SCOPE, _SQL_LIKE, get_ml_classifier
        if not question or _SQL_LIKE.search(question):
            return []
        labels = learnable_intents()
        ranked = get_ml_classifier().predict_proba(question)
        return [
            {"intent": str(c), "p": round(float(p), 3)}
            for c, p in ranked
            if c != OUT_OF_SCOPE and c in labels
        ][:top_k]
    except Exception as ex:  # pragma: no cover
        logger.debug("Không lấy được gợi ý ML: %s", ex)
        return []


# ==============================================================================
# 1-2. GHI NHẬT KÝ (kết nối quản trị, qua hàm có kiểm soát)
# ==============================================================================
SQL_LOG = 'SELECT "LinhKien".fn_ghi_cau_hoi_chua_hieu(%s, %s, %s, %s::jsonb, %s) AS id'
SQL_CHOICE = 'SELECT "LinhKien".fn_ghi_lua_chon_goi_y(%s, %s) AS ok'


def _write_log(params: Tuple[Any, ...], sql: str = SQL_LOG) -> None:
    res = execute_query(sql, params, use_admin=True)
    if not res.get("success"):
        logger.info("Chưa ghi được câu chưa hiểu (đã chạy database/hoc_tu_cau_chua_hieu.sql chưa?): %s",
                    res.get("error"))


def log_unknown(
    question: str,
    reason: str,
    suggestions: Optional[List[Dict[str, Any]]] = None,
    user: Optional[str] = None,
    background: bool = True,
) -> bool:
    """
    Ghi một câu chưa hiểu. Không bao giờ ném lỗi ra ngoài (nhật ký học không được làm hỏng luồng chính).
    Không gọi hàm này cho câu bị AI 3 chặn. Trả về True nếu đã gửi lệnh ghi.
    """
    try:
        if reason not in REASONS or not question or not question.strip():
            return False
        masked = mask_pii(question.strip())[:300]
        key = normalize_key(masked)
        if len(key) < 2:
            return False
        sugg = [
            {"intent": str(s.get("intent")), "p": float(s.get("p", 0))}
            for s in (suggestions or [])[:3] if isinstance(s, dict) and s.get("intent")
        ]
        params = (masked, key, reason, json.dumps(sugg, ensure_ascii=False), (user or "")[:50] or None)
        if background:
            threading.Thread(target=_write_log, args=(params,), daemon=True).start()
        else:
            _write_log(params)
        return True
    except Exception as ex:  # pragma: no cover
        logger.warning("Lỗi ghi nhật ký câu chưa hiểu: %s", ex)
        return False


def record_choice(question: str, intent: str, background: bool = True) -> bool:
    """
    Người dùng bấm gợi ý "Ý bạn là ..." và câu trả lời CHẠY THÀNH CÔNG (đã qua AI 3): cộng 1 phiếu cho
    intent đó trên câu hỏi tương ứng (chỉ câu còn chờ duyệt, không tăng số lần gặp).
    """
    try:
        if not question or intent not in learnable_intents():
            return False
        key = normalize_key(mask_pii(question.strip())[:300])
        if len(key) < 2:
            return False
        if background:
            threading.Thread(target=_write_log, args=((key, intent), SQL_CHOICE), daemon=True).start()
        else:
            _write_log((key, intent), SQL_CHOICE)
        return True
    except Exception as ex:  # pragma: no cover
        logger.warning("Lỗi ghi lựa chọn gợi ý: %s", ex)
        return False


def load_trained_samples() -> Tuple[List[Tuple[str, str]], Dict[str, List[str]]]:
    """
    Mẫu đã duyệt VÀ đã được chấp nhận huấn luyện (dựng lại mô hình khi khởi động web).
    Trả về (danh sách (câu, intent) cho AI 1, {nhu cầu: [cụm từ]} cho AI 2). Lỗi -> rỗng.
    """
    res = execute_query('SELECT * FROM "LinhKien".fn_mau_hoc_da_duyet()', role="admin")
    if not res.get("success"):
        raise RuntimeError(res.get("error") or "Không đọc được mẫu học")
    labels = learnable_intents()
    intents: List[Tuple[str, str]] = []
    needs: Dict[str, List[str]] = {}
    for r in res.get("data") or []:
        if r.get("loai_nhan") == "intent" and r.get("nhan") in labels:
            intents.append((r["cau_hoi"], r["nhan"]))
        elif r.get("loai_nhan") == "nhu_cau" and r.get("cum_tu_hoc"):
            needs.setdefault(r["nhan"], []).append(r["cum_tu_hoc"])
    return intents, needs


# ==============================================================================
# 3. DUYỆT (chỉ Admin, kết nối quản trị)
# ==============================================================================
def _admin_fetch(sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    conn = get_connection(use_admin=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def count_by_status() -> Dict[str, Any]:
    try:
        rows = _admin_fetch(
            'SELECT trang_thai, count(*) AS so_cau, count(*) FILTER (WHERE da_huan_luyen) AS da_hl '
            'FROM "LinhKien".cau_hoi_chua_hieu GROUP BY trang_thai'
        )
        out = {k: 0 for k in STATUSES}
        trained = 0
        for r in rows:
            out[r["trang_thai"]] = int(r["so_cau"])
            trained += int(r["da_hl"])
        return {"success": True, "counts": out, "trained": trained,
                "labeled_untrained": out["da_gan_nhan"] - trained}
    except Exception as ex:
        return {"success": False, "error": str(ex)}


def list_questions(status: str = "cho_duyet", limit: int = 50) -> Dict[str, Any]:
    if status not in STATUSES:
        return {"success": False, "error": "Trạng thái không hợp lệ."}
    try:
        rows = _admin_fetch(
            'SELECT id, cau_hoi, ly_do, goi_y_ml, intent_nguoi_dung_chon, so_lan_gap, lan_dau, lan_cuoi, '
            '       nguoi_hoi_cuoi, trang_thai, loai_nhan, nhan, cum_tu_hoc, ghi_chu, nguoi_duyet, '
            '       thoi_diem_duyet, da_huan_luyen '
            'FROM "LinhKien".cau_hoi_chua_hieu WHERE trang_thai = %s '
            'ORDER BY so_lan_gap DESC, lan_cuoi DESC LIMIT %s',
            (status, int(limit)),
        )
        return {"success": True, "rows": rows}
    except Exception as ex:
        return {"success": False, "error": str(ex)}


def review(question_id: int, action: str, reviewer: str, label: Optional[str] = None,
           phrase: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    """
    action:
      - "intent"          : gán vào intent có sẵn của AI 1 (label = tên intent)
      - "nhu_cau"         : gán vào nhu cầu Knowledge Graph của AI 2 (label = tên nhu cầu, phrase = cụm từ học)
      - "can_mau_sql_moi" : loại câu hỏi mới, cần viết thêm mẫu SQL (đưa vào danh sách việc cần làm)
      - "bo_qua"          : câu rác / không cần học
      - "mo_lai"          : đưa về chờ duyệt (hoàn tác một quyết định, mẫu bị gỡ khỏi lần huấn luyện sau)
    Một câu đổi nhãn luôn trở lại trạng thái CHƯA huấn luyện (phải bấm Huấn luyện lại mới có hiệu lực).
    """
    reviewer = (reviewer or "").strip()[:50]
    if not reviewer:
        return {"success": False, "error": "Thiếu tên người duyệt."}
    note = (note or "").strip()[:300] or None
    loai, nhan, cum = None, None, None
    if action == "intent":
        if label not in learnable_intents():
            return {"success": False, "error": f"Intent '{label}' không có mẫu SQL tương ứng."}
        status, loai, nhan = "da_gan_nhan", "intent", label
    elif action == "nhu_cau":
        if label not in knowledge_needs():
            return {"success": False, "error": f"Nhu cầu '{label}' không có trong Knowledge Graph."}
        cum = re.sub(r"\s+", " ", (phrase or "").strip().lower())
        if not (MIN_PHRASE_LEN <= len(cum) <= MAX_PHRASE_LEN):
            return {"success": False, "error": f"Cụm từ học phải dài {MIN_PHRASE_LEN}–{MAX_PHRASE_LEN} ký tự."}
        status, loai, nhan = "da_gan_nhan", "nhu_cau", label
    elif action in ("can_mau_sql_moi", "bo_qua"):
        status = action
    elif action == "mo_lai":
        status = "cho_duyet"
    else:
        return {"success": False, "error": "Hành động không hợp lệ."}

    try:
        conn = get_connection(use_admin=True)
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE "LinhKien".cau_hoi_chua_hieu SET trang_thai = %s, loai_nhan = %s, nhan = %s, '
                    '       cum_tu_hoc = %s, ghi_chu = %s, da_huan_luyen = FALSE, '
                    '       nguoi_duyet = CASE WHEN %s = \'cho_duyet\' THEN NULL ELSE %s END, '
                    '       thoi_diem_duyet = CASE WHEN %s = \'cho_duyet\' THEN NULL ELSE now() END '
                    'WHERE id = %s',
                    (status, loai, nhan, cum, note, status, reviewer, status, int(question_id)),
                )
                updated = cur.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as ex:
        return {"success": False, "error": f"Lỗi CSDL: {ex}"}
    if not updated:
        return {"success": False, "error": "Không tìm thấy câu hỏi."}
    return {"success": True, "status": status}


# ==============================================================================
# 4. HUẤN LUYỆN LẠI CÓ KIỂM SOÁT
# ==============================================================================
def load_gold_cases() -> List[Dict[str, Any]]:
    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def evaluate_gold(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chấm bộ câu chuẩn bằng mô hình + Knowledge Graph đang có hiệu lực trong LUỒNG hiện tại.
    Câu có intent: đúng khi bộ định tuyến chọn AI 1 VÀ intent đúng (bắt cả trường hợp cụm từ AI 2
    học thêm "cướp" câu của AI 1). Câu ngoài phạm vi: đúng khi AI 1 không trả lời.
    """
    from app.ai_1_text2sql.pipeline import interpret
    from app.router import route

    correct_ids = set()
    for i, c in enumerate(cases):
        res = interpret(c["q"])
        if c["intent"] == "UNKNOWN":
            ok = not res.success
        else:
            ok = route(c["q"]).engine == "ai1" and res.success and res.intent == c["intent"]
        if ok:
            correct_ids.add(i)
    total = len(cases)
    return {"correct": len(correct_ids), "total": total, "ids": correct_ids,
            "accuracy": round(100.0 * len(correct_ids) / total, 2) if total else 0.0}


def _fetch_labeled() -> List[Dict[str, Any]]:
    return _admin_fetch(
        'SELECT id, cau_hoi, loai_nhan, nhan, cum_tu_hoc, thoi_diem_duyet FROM "LinhKien".cau_hoi_chua_hieu '
        "WHERE trang_thai = 'da_gan_nhan' ORDER BY id"
    )


def live_learned_count() -> int:
    """Số mẫu học thêm ĐANG có hiệu lực trong tiến trình web (mô hình AI 1 + cụm từ AI 2)."""
    try:
        from app.ai_2_semantic.knowledge_graph import get_knowledge_graph
        from app.ai_1_text2sql.ml_intent_classifier import get_ml_classifier
        return len(get_ml_classifier().extra_samples) + sum(
            len(v) for v in get_knowledge_graph().learned_aliases.values())
    except Exception:  # pragma: no cover
        return 0


def _save_history(cur, reviewer: str, base_n: int, n_int: int, n_need: int,
                  acc_old: float, acc_new: float, result: str, note: str) -> None:
    cur.execute(
        'INSERT INTO "LinhKien".lich_su_huan_luyen (nguoi_thuc_hien, so_mau_goc, so_mau_hoc_intent, '
        ' so_cum_tu_nhu_cau, do_chinh_xac_cu, do_chinh_xac_moi, ket_qua, ghi_chu) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (reviewer[:50], base_n, n_int, n_need, acc_old, acc_new, result, note),
    )


class _LabelsChanged(Exception):
    """Có câu được đổi nhãn / mở lại trong lúc đang huấn luyện -> phải chạy lại."""


def _commit_result(used_rows: List[Dict[str, Any]], labeled_ids: set, accepted: bool,
                   history: Tuple[Any, ...]) -> None:
    """
    Ghi kết quả trong MỘT giao dịch: khóa (FOR UPDATE) và đối chiếu lại các câu đã dùng để huấn luyện.
    Nếu nhãn của bất kỳ câu nào đã đổi trong lúc chấm điểm -> hủy toàn bộ (không đánh dấu mẫu chưa được
    kiểm tra là "đã học"). Đánh dấu da_huan_luyen + ghi lịch sử cùng thành công hoặc cùng thất bại.
    """
    conn = get_connection(use_admin=True)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            if accepted:
                ids = [r["id"] for r in used_rows]
                cur.execute(
                    'SELECT id, trang_thai, loai_nhan, nhan, cum_tu_hoc, thoi_diem_duyet '
                    'FROM "LinhKien".cau_hoi_chua_hieu WHERE trang_thai = \'da_gan_nhan\' OR id = ANY(%s) '
                    'ORDER BY id FOR UPDATE', (ids,))
                now_rows = {row[0]: row for row in cur.fetchall()}
                labeled_now = {i for i, row in now_rows.items() if row[1] == "da_gan_nhan"}
                for r in used_rows:
                    row = now_rows.get(r["id"])
                    if (row is None or row[1] != "da_gan_nhan" or row[2] != r["loai_nhan"] or row[3] != r["nhan"]
                            or row[4] != r["cum_tu_hoc"] or row[5] != r["thoi_diem_duyet"]):
                        raise _LabelsChanged()
                if labeled_now != set(labeled_ids):
                    raise _LabelsChanged()   # có câu được gán nhãn / mở lại trong lúc chạy
                cur.execute('UPDATE "LinhKien".cau_hoi_chua_hieu SET da_huan_luyen = (id = ANY(%s)) '
                            "WHERE trang_thai = 'da_gan_nhan' OR da_huan_luyen", (ids,))
            _save_history(cur, *history)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retrain(reviewer: str) -> Dict[str, Any]:
    """
    Dựng mô hình ứng viên từ dữ liệu gốc + mọi câu đang gán nhãn, so sánh với mô hình đang chạy trên
    bộ câu chuẩn rồi mới quyết định áp dụng. Không còn câu nào gán nhãn -> ứng viên = dữ liệu gốc
    (gỡ hết mẫu đã học, dùng khi Admin "Mở lại" một câu dạy sai). Hai Admin bấm cùng lúc -> chỉ một lượt chạy.
    """
    from app.ai_2_semantic.knowledge_graph import HardwareKnowledgeGraph, get_knowledge_graph, use_knowledge_graph
    from app.ai_1_text2sql.ml_intent_classifier import MLIntentClassifier, get_ml_classifier, set_ml_classifier, use_classifier

    if not _retrain_lock.acquire(blocking=False):
        return {"success": False, "error": "Đang có một lượt huấn luyện lại chạy, vui lòng đợi."}
    try:
        try:
            labeled = _fetch_labeled()
        except Exception as ex:
            return {"success": False, "error": f"Không đọc được câu đã duyệt: {ex}"}

        labels = learnable_intents()
        needs_known = set(knowledge_needs())
        used_rows = [r for r in labeled
                     if (r["loai_nhan"] == "intent" and r["nhan"] in labels)
                     or (r["loai_nhan"] == "nhu_cau" and r["nhan"] in needs_known and r.get("cum_tu_hoc"))]
        intent_samples = [(r["cau_hoi"], r["nhan"]) for r in used_rows if r["loai_nhan"] == "intent"]
        need_phrases: Dict[str, List[str]] = {}
        for r in used_rows:
            if r["loai_nhan"] == "nhu_cau":
                need_phrases.setdefault(r["nhan"], []).append(r["cum_tu_hoc"])
        n_need = sum(len(v) for v in need_phrases.values())
        if not used_rows and live_learned_count() == 0:
            return {"success": False, "error": "Chưa có câu nào được gán nhãn để huấn luyện."}

        try:
            cases = load_gold_cases()
        except Exception as ex:
            return {"success": False, "error": f"Thiếu bộ câu chuẩn để kiểm tra ({GOLD_PATH}): {ex}"}

        try:
            old_eval = evaluate_gold(cases)   # mô hình đang chạy
            # Mô hình ứng viên (chỉ có hiệu lực trong luồng này khi đánh giá)
            candidate = MLIntentClassifier(extra_samples=intent_samples)
            candidate.ensure_trained()
            cand_kg = HardwareKnowledgeGraph()
            cand_kg.apply_learned_aliases(need_phrases)
            with use_classifier(candidate), use_knowledge_graph(cand_kg):
                new_eval = evaluate_gold(cases)
                # Tự kiểm tra: mô hình mới đã thật sự "hiểu" các câu vừa dạy chưa
                learned_ok = sum(1 for q, lb in intent_samples if candidate.predict(q)[0] == lb)
                phrase_ok = sum(1 for need, ps in need_phrases.items() for p in ps
                                if need in [n.name for n in cand_kg.detect_needs(p)])
            # Không quên kiến thức cũ: mô hình mới vẫn phải phân loại đúng dữ liệu gốc như mô hình cũ
            base_texts, base_labels = candidate.base_dataset()
            current = get_ml_classifier()
            base_old = sum(1 for t, lb in zip(base_texts, base_labels) if current.predict_proba(t)[0][0] == lb)
            base_new = sum(1 for t, lb in zip(base_texts, base_labels) if candidate.predict_proba(t)[0][0] == lb)
        except Exception as ex:
            logger.exception("Lỗi khi huấn luyện / chấm mô hình ứng viên")
            return {"success": False, "error": f"Lỗi khi huấn luyện mô hình ứng viên, giữ mô hình cũ: {ex}"}

        broken = [cases[i]["q"] for i in sorted(old_eval["ids"] - new_eval["ids"])]
        fixed = [cases[i]["q"] for i in sorted(new_eval["ids"] - old_eval["ids"])]
        accepted = new_eval["correct"] >= old_eval["correct"] and base_new >= base_old

        report = {
            "success": True,
            "accepted": accepted,
            "acc_old": old_eval["accuracy"], "acc_new": new_eval["accuracy"],
            "correct_old": old_eval["correct"], "correct_new": new_eval["correct"], "total": old_eval["total"],
            "base_old": base_old, "base_new": base_new, "base_total": len(base_texts),
            "n_intent_samples": len(intent_samples), "n_need_phrases": n_need,
            "learned_ok": learned_ok, "phrase_ok": phrase_ok,
            "broken": broken, "fixed": fixed,
        }
        if accepted:
            note = (f"Áp dụng: {len(intent_samples)} câu AI 1, {n_need} cụm từ AI 2."
                    if used_rows else "Áp dụng: gỡ hết mẫu học thêm, trở về dữ liệu gốc.")
        else:
            reasons = []
            if new_eval["correct"] < old_eval["correct"]:
                reasons.append(f"bộ câu chuẩn giảm {old_eval['correct']} → {new_eval['correct']} câu đúng")
            if base_new < base_old:
                reasons.append(f"dữ liệu gốc giảm {base_old} → {base_new} câu đúng")
            note = "Từ chối: " + "; ".join(reasons) + (f". Câu bị hỏng: {broken[:5]}" if broken else "")
        report["note"] = note

        history = (reviewer or "admin", len(base_texts), len(intent_samples), n_need,
                   old_eval["accuracy"], new_eval["accuracy"], "ap_dung" if accepted else "tu_choi", note)
        try:
            _commit_result(used_rows, {r["id"] for r in labeled}, accepted, history)
        except _LabelsChanged:
            return {**report, "success": False, "accepted": False,
                    "error": "Có câu vừa được đổi nhãn trong lúc huấn luyện. Giữ mô hình cũ, hãy bấm Huấn luyện lại."}
        except Exception as ex:
            return {**report, "success": False, "accepted": False,
                    "error": f"Không lưu được kết quả huấn luyện, giữ mô hình cũ: {ex}"}

        # Chỉ thay mô hình đang chạy SAU KHI CSDL đã ghi nhận thành công
        if accepted:
            set_ml_classifier(candidate)
            get_knowledge_graph().apply_learned_aliases(need_phrases)
        return report
    finally:
        _retrain_lock.release()


def training_history(limit: int = 5) -> Dict[str, Any]:
    try:
        rows = _admin_fetch(
            'SELECT thoi_diem, nguoi_thuc_hien, so_mau_hoc_intent, so_cum_tu_nhu_cau, do_chinh_xac_cu, '
            '       do_chinh_xac_moi, ket_qua, ghi_chu FROM "LinhKien".lich_su_huan_luyen '
            'ORDER BY id DESC LIMIT %s', (int(limit),))
        return {"success": True, "rows": rows}
    except Exception as ex:
        return {"success": False, "error": str(ex)}
