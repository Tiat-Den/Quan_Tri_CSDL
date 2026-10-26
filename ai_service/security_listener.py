"""
TIẾN TRÌNH LẮNG NGHE CẢNH BÁO AI THỜI GIAN THỰC (PostgreSQL LISTEN/NOTIFY)

Lắng nghe 2 kênh do trigger trong database/ai_notify_alerts.sql phát ra:
  - ai_security_alert : cảnh báo an ninh mức HIGH từ AI 3 (Zero-Trust Guard)
  - ai_order_anomaly  : đơn hàng có tổng tiền bất thường (z-score > 3) phát hiện ngay trong CSDL

Cách chạy (mở một cửa sổ terminal riêng trong buổi demo):
    python ai_service/security_listener.py

Mỗi cảnh báo được in ra màn hình và ghi thêm vào ai_service/logs/realtime_alerts.jsonl.
Dừng bằng Ctrl + C.
"""
import json
import os
import select
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import psycopg2  # noqa: E402
import psycopg2.extensions  # noqa: E402

from app import config  # noqa: E402

CHANNELS = ("ai_security_alert", "ai_order_anomaly")
ALERT_LOG = os.path.join(CURRENT_DIR, "logs", "realtime_alerts.jsonl")


def connect():
    """Kết nối bằng tài khoản quản trị (LISTEN cần kết nối riêng, không qua role chỉ đọc)."""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=getattr(config, "DB_ADMIN_USER", "postgres"),
        password=getattr(config, "DB_ADMIN_PASSWORD", ""),
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def format_alert(channel: str, payload: dict) -> str:
    if channel == "ai_security_alert":
        factors = payload.get("cac_yeu_to") or []
        lines = [
            f"🚨 [AI 3 - AN NINH] {payload.get('muc_do')} | Điểm rủi ro {payload.get('diem_rui_ro')}/100",
            f"   Người dùng: {payload.get('nguoi_dung')} | IP: {payload.get('ip')}",
            f"   SQL: {payload.get('cau_sql')}",
        ]
        lines += [f"   - {f}" for f in factors]
        return "\n".join(lines)
    if channel == "ai_order_anomaly":
        return (
            f"⚠️  [ĐƠN HÀNG BẤT THƯỜNG] Đơn #{payload.get('don_hang_id')} ({payload.get('kenh_ban')}) "
            f"tổng {int(float(payload.get('tong_tien', 0))):,} đ | TB 90 ngày "
            f"{int(float(payload.get('trung_binh_90_ngay', 0))):,} đ | z = {payload.get('z_score')}"
        )
    return f"[{channel}] {payload}"


def main():
    conn = connect()
    cur = conn.cursor()
    for ch in CHANNELS:
        cur.execute(f"LISTEN {ch};")
    print(f"Đang lắng nghe kênh: {', '.join(CHANNELS)} trên CSDL {config.DB_NAME} ... (Ctrl + C để dừng)")
    os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)
    try:
        while True:
            if select.select([conn], [], [], 5) == ([], [], []):
                continue  # hết 5 giây chờ, tiếp tục lắng nghe
            conn.poll()
            while conn.notifies:
                note = conn.notifies.pop(0)
                try:
                    payload = json.loads(note.payload)
                except Exception:
                    payload = {"raw": note.payload}
                stamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{stamp}] " + format_alert(note.channel, payload))
                with open(ALERT_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": datetime.now().isoformat(), "channel": note.channel,
                                        "payload": payload}, ensure_ascii=False) + "\n")
    except KeyboardInterrupt:
        print("\nĐã dừng tiến trình lắng nghe.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
