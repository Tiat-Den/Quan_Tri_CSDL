"""
NẠP LỊCH SỬ HÀNH VI MẪU CHO MÔ HÌNH HỌC MÁY CỦA AI 3 (Isolation Forest + hồ sơ người dùng)

Vấn đề: mô hình phát hiện bất thường cần nhiều truy vấn BÌNH THƯỜNG để học, và hồ sơ z-score
của từng người dùng cần tối thiểu 10 truy vấn của chính người đó. Hệ thống mới chạy nên nhật ký
kiểm toán còn rất ít.

Giải pháp: mô phỏng ~30 ngày làm việc của các tài khoản thật (admin, manager):
- Câu hỏi lấy từ bộ câu hỏi thật của dự án (20 câu vàng, câu diễn đạt lại, câu tư vấn AI 2).
- Mỗi câu chạy qua ĐÚNG luồng thật: AI 1 dịch sang SQL -> EXPLAIN lấy số dòng (nếu có CSDL)
  -> AI 3 trích đặc trưng bằng cây cú pháp; AI 2 chấm điểm theo câu hỏi.
- Chỉ giữ các truy vấn được AI 3 đánh giá NORMAL theo luật (để mô hình học hành vi BÌNH THƯỜNG).
- Thời điểm được trải trong giờ làm việc của từng người; mọi bản ghi gắn nhãn
  "source": "seed_lich_su" để phân biệt với dữ liệu phát sinh thật và có thể xóa riêng.
"""
import json
import math
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_r1 = Path(__file__).resolve().parent.parent
_r2 = Path(__file__).resolve().parent.parent.parent
ROOT = _r1 if (_r1 / "logs").exists() else _r2
SEED_SOURCE = "seed_lich_su"

# Thói quen làm việc của từng tài khoản: (giờ bắt đầu, giờ kết thúc, tỷ lệ dùng AI 2)
USER_PROFILES = {
    "admin": {"hours": (8, 18), "ai2_ratio": 0.2},
    "manager": {"hours": (9, 21), "ai2_ratio": 0.45},
}


def _question_pool() -> Dict[str, List[str]]:
    ai1, ai2 = [], []
    try:
        with open(ROOT / "eval" / "text2sql_gold_50.json", encoding="utf-8") as f:
            ai1 += [c["q"] for c in json.load(f)["cases"] if c["intent"] != "UNKNOWN"]
    except Exception:
        pass
    try:
        with open(ROOT / "app" / "data" / "intent_training.json", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if not k.startswith("_") and k != "OUT_OF_SCOPE" and isinstance(v, list):
                ai1 += v
    except Exception:
        pass
    try:
        with open(ROOT / "eval" / "semantic_gold.json", encoding="utf-8") as f:
            ai2 += [c["query"] for c in json.load(f) if c.get("expected_categories")]
    except Exception:
        pass
    if not ai2:
        ai2 = ["PC chơi game nặng và stream", "Cấu hình làm đồ họa render video",
               "Máy tính văn phòng học tập giá rẻ", "Linh kiện mở nhiều tab đa nhiệm mượt"]
    return {"ai1": ai1, "ai2": ai2}


def _plan_rows(sql: str, params: list, cache: Dict[str, Optional[int]]) -> int:
    """Số dòng ước tính: EXPLAIN thật nếu có CSDL, nếu không thì suy từ LIMIT."""
    key = sql + repr(params)
    if key in cache and cache[key] is not None:
        return cache[key]
    rows = None
    try:
        from app.db import execute_query
        res = execute_query(f"EXPLAIN (FORMAT JSON) {sql.strip().rstrip(';')}", params)
        if res.get("success") and res.get("data"):
            rows = int(res["data"][0]["QUERY PLAN"][0]["Plan"].get("Plan Rows", 0))
            cache["__explain_ok__"] = 1
    except Exception:
        rows = None
    if rows is None:
        m = re.search(r"\blimit\s+(%s|\d+)", sql, re.IGNORECASE)
        if m and m.group(1).isdigit():
            rows = int(m.group(1))
        elif m and params:
            rows = int(params[-1]) if str(params[-1]).isdigit() else 20
        else:
            rows = 20
    cache[key] = rows
    return rows


def seed_history(n_records: int = 600, days: int = 30, seed: int = 2026, replace: bool = True) -> Dict[str, Any]:
    """
    Sinh và ghi n_records bản ghi hành vi bình thường vào logs/security_audit.jsonl.
    replace=True: xóa lịch sử mẫu cũ trước khi nạp (bấm nạp nhiều lần không bị nhân đôi dữ liệu).
    """
    import app.ai_security_guard as guard

    from app.ai_3_security.ai_anomaly_detector import build_features
    from app.ai_1_text2sql.pipeline import interpret

    rng = random.Random(seed)
    pool = _question_pool()
    real_log = guard.AUDIT_LOG_FILE

    # Dịch sẵn các câu AI 1 sang SQL một lần
    translated = []
    for q in pool["ai1"]:
        r = interpret(q)
        if r.success and r.sql:
            translated.append((q, r.sql, list(r.params)))
    if not translated:
        return {"success": False, "error": "Không dịch được câu hỏi mẫu nào sang SQL."}

    plan_cache: Dict[str, Optional[int]] = {}
    users = list(USER_PROFILES)
    now = datetime.now()
    written = {"AI 1": 0, "AI 2": 0}
    skipped = 0
    lines = []

    # Chấm điểm với write_log=False: không ghi nhật ký, không phát cảnh báo; chỉ ghi bản ghi đã gắn mốc lịch sử
    for i in range(n_records):
        user = users[i % len(users)]
        prof = USER_PROFILES[user]
        day = now - timedelta(days=rng.randint(1, days))
        if day.weekday() == 6 and rng.random() < 0.7:  # Chủ nhật ít làm việc
            day -= timedelta(days=1)
        hour = rng.randint(prof["hours"][0], prof["hours"][1] - 1)
        ts = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
        qps = round(min(max(rng.lognormvariate(-1.2, 0.5), 0.05), 2.0), 2)

        if rng.random() < prof["ai2_ratio"]:
            q = rng.choice(pool["ai2"])
            ev = guard.evaluate_semantic_request(q, user=user, hour=hour, use_anomaly=False, write_log=False)
            if ev["status"] != "NORMAL":
                skipped += 1
                continue
            feats = build_features(hour=hour, rows=rng.randint(1, 15), n_tables=1, n_columns=0,
                                   has_star=False, has_limit=True, has_agg=False, qps=0.0, sql_len=len(q))
            rec = {"engine": "AI 2", "question": q, "sql": "", "score": ev["score"], "factors": ev["factors"]}
        else:
            q, sql, params = rng.choice(translated)
            rows = _plan_rows(sql, params, plan_cache)
            ev = guard.AISecurityGuard.evaluate_risk(
                sql, user=user, hour=hour, qps=qps, plan_rows=rows, use_anomaly=False, engine="AI 1", question=q,
                write_log=False,
            )
            if ev["status"] != "NORMAL":
                skipped += 1
                continue
            ast_info = guard.AISecurityGuard._parse_sql_ast(sql)
            feats = build_features(
                hour=hour, rows=rows, n_tables=len(ast_info["tables"]), n_columns=len(ast_info["columns"]),
                has_star=ast_info["has_star"], has_limit=ast_info["has_limit"], has_agg=ast_info["has_agg"],
                qps=qps, sql_len=len(sql),
            )
            rec = {"engine": "AI 1", "question": q, "sql": sql[:300], "score": ev["score"], "factors": ev["factors"]}

        lines.append({
            "timestamp": ts.isoformat(),
            **rec,
            "stage": "Thực thi",
            "user": user,
            "ip": "127.0.0.1",
            "status": "NORMAL",
            "allowed": True,
            "features": feats,
            "anomaly_score": None,
            "source": SEED_SOURCE,
        })
        written[rec["engine"]] += 1

    # Ghi theo thứ tự thời gian, ĐẶT TRƯỚC nhật ký thật để nhật ký hiển thị gần nhất vẫn là dữ liệu thật.
    # Đọc - lọc - ghi trong cùng một khóa và thay tệp nguyên tử (os.replace) để không mất dòng của phiên khác.
    lines.sort(key=lambda r: r["timestamp"])
    removed_old = 0
    with guard.AUDIT_LOG_LOCK:
        existing = []
        if real_log.exists():
            with open(real_log, encoding="utf-8") as f:
                for l in f:
                    if not l.strip():
                        continue
                    if replace and f'"source": "{SEED_SOURCE}"' in l:
                        removed_old += 1  # thay thế lịch sử mẫu cũ, chỉ khi bản mới đã sẵn sàng
                        continue
                    existing.append(l if l.endswith("\n") else l + "\n")
        real_log.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = real_log.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.writelines(existing)
        os.replace(tmp_path, real_log)

    # Buộc mô hình huấn luyện lại ở lần chấm điểm tiếp theo
    try:
        from app.ai_3_security.ai_anomaly_detector import get_anomaly_detector
        get_anomaly_detector()._model = None
    except Exception:
        pass

    return {
        "success": True,
        "written": sum(written.values()),
        "by_engine": written,
        "skipped_not_normal": skipped,
        "users": users,
        "days": days,
        "used_db_explain": bool(plan_cache.get("__explain_ok__")),
        "replaced_old": removed_old,
    }


def remove_seeded_history() -> int:
    """Xóa toàn bộ bản ghi lịch sử mẫu (giữ nguyên nhật ký phát sinh thật)."""
    import app.ai_security_guard as guard

    log = guard.AUDIT_LOG_FILE
    if not log.exists():
        return 0
    kept, removed = [], 0
    with guard.AUDIT_LOG_LOCK:
        with open(log, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                try:
                    if json.loads(l).get("source") == SEED_SOURCE:
                        removed += 1
                        continue
                except Exception:
                    pass
                kept.append(l if l.endswith("\n") else l + "\n")
        tmp_path = log.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(kept)
        os.replace(tmp_path, log)
    try:
        from app.ai_3_security.ai_anomaly_detector import get_anomaly_detector
        get_anomaly_detector()._model = None
    except Exception:
        pass
    return removed


def training_data_stats() -> Dict[str, Any]:
    """
    Thống kê dữ liệu huấn luyện đọc trực tiếp từ nhật ký (bền vững qua F5 / khởi động lại):
    số bản ghi lịch sử nạp và dữ liệu thật, hồ sơ từng người dùng, phân bố theo ngày.
    """
    import app.ai_security_guard as guard
    from app.ai_3_security.ai_anomaly_detector import FEATURE_NAMES, MIN_USER_HISTORY

    log = guard.AUDIT_LOG_FILE
    recs = []
    if log.exists():
        with open(log, encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    try:
                        recs.append(json.loads(l))
                    except Exception:
                        pass
    usable = [
        r for r in recs
        if r.get("status") == "NORMAL" and isinstance(r.get("features"), list) and len(r["features"]) == len(FEATURE_NAMES)
    ]
    seeded = [r for r in usable if r.get("source") == SEED_SOURCE]
    real = [r for r in usable if r.get("source") != SEED_SOURCE]

    per_user: Dict[str, Dict[str, Any]] = {}
    per_day: Dict[str, Dict[str, int]] = {}
    for r in usable:
        u = r.get("user") or "?"
        d = per_user.setdefault(u, {"so_truy_van": 0, "lich_su_nap": 0, "that": 0, "_hours": [], "_rows": []})
        d["so_truy_van"] += 1
        d["lich_su_nap" if r.get("source") == SEED_SOURCE else "that"] += 1
        f = r["features"]
        # Khôi phục giờ từ sin/cos và số dòng từ log1p
        d["_hours"].append((math.degrees(math.atan2(f[0], f[1])) / 15.0) % 24)
        d["_rows"].append(math.expm1(f[2]))
        day = str(r.get("timestamp", ""))[:10]
        if day:
            bucket = per_day.setdefault(day, {"Lịch sử nạp": 0, "Dữ liệu thật": 0})
            bucket["Lịch sử nạp" if r.get("source") == SEED_SOURCE else "Dữ liệu thật"] += 1

    users = []
    for u, d in sorted(per_user.items(), key=lambda x: -x[1]["so_truy_van"]):
        users.append({
            "Người dùng": u,
            "Truy vấn bình thường": d["so_truy_van"],
            "Lịch sử nạp": d["lich_su_nap"],
            "Dữ liệu thật": d["that"],
            "Giờ làm TB": round(sum(d["_hours"]) / len(d["_hours"]), 1) if d["_hours"] else None,
            "Số dòng TB": round(sum(d["_rows"]) / len(d["_rows"]), 1) if d["_rows"] else None,
            "Hồ sơ z-score": "Đủ" if d["so_truy_van"] >= MIN_USER_HISTORY else f"Thiếu (cần {MIN_USER_HISTORY})",
        })
    days = sorted(per_day)
    return {
        "seeded": len(seeded),
        "real": len(real),
        "total_usable": len(usable),
        "users": users,
        "users_with_profile": sum(1 for u in users if u["Hồ sơ z-score"] == "Đủ"),
        "per_day": [{"Ngày": d, **per_day[d]} for d in days],
        "date_from": days[0] if days else None,
        "date_to": days[-1] if days else None,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    if "--remove" in sys.argv:
        print(f"Đã xóa {remove_seeded_history()} bản ghi lịch sử mẫu.")
    else:
        print(json.dumps(seed_history(), ensure_ascii=False, indent=2))
