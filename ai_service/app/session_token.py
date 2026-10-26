"""
PHIÊN ĐĂNG NHẬP CÓ CHỮ KÝ (Signed Session Token) — chống giả mạo đăng nhập qua đường link.

Lỗ hổng cũ: web_app.py khôi phục phiên từ URL ?session_user=...&session_role=admin
-> ai cũng có thể tự gõ đường link để vào thẳng quyền admin mà không cần mật khẩu.

Cách mới: sau khi đăng nhập đúng, server tạo một token
    base64(username | role | họ tên | hạn dùng) + "." + HMAC-SHA256(khóa bí mật của server)
Chỉ server biết khóa bí mật nên không ai tự tạo hoặc sửa token được (đổi role -> sai chữ ký).
Token có hạn dùng (mặc định 4 giờ) và mã phiên ngẫu nhiên (jti): khi đăng xuất, jti bị đưa vào danh sách
thu hồi trên server, nên đường link cũ (lịch sử trình duyệt, ảnh chụp màn hình) không dùng lại được. Khóa bí mật lấy từ biến môi trường APP_SECRET_KEY,
nếu chưa có thì tự sinh ngẫu nhiên và lưu ở logs/.session_secret (thư mục logs đã bị .gitignore).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

TOKEN_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(4 * 3600)))
_SECRET_FILE = Path(__file__).resolve().parent.parent / "logs" / ".session_secret"
_REVOKED_FILE = Path(__file__).resolve().parent.parent / "logs" / ".revoked_sessions.json"
_secret_cache: Optional[bytes] = None


def _secret() -> bytes:
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.getenv("APP_SECRET_KEY", "").strip()
    if env:
        _secret_cache = env.encode("utf-8")
        return _secret_cache
    try:
        if _SECRET_FILE.exists():
            _secret_cache = _SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
            if _secret_cache:
                return _secret_cache
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        _SECRET_FILE.write_text(key, encoding="utf-8")
        try:
            os.chmod(_SECRET_FILE, 0o600)
        except Exception:
            pass
        _secret_cache = key.encode("utf-8")
    except Exception:
        # Không ghi được tệp -> khóa chỉ sống trong tiến trình (token mất hiệu lực khi khởi động lại)
        _secret_cache = secrets.token_hex(32).encode("utf-8")
    return _secret_cache


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user: Dict[str, Any], ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = {
        "u": user["username"],
        "r": user["role"],
        "n": user.get("ho_ten", ""),
        "exp": int(time.time()) + ttl,
        "jti": secrets.token_hex(8),
    }
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _load_revoked() -> Dict[str, int]:
    try:
        data = json.loads(_REVOKED_FILE.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items()}
    except Exception:
        return {}


def _decode(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Kiểm tra định dạng + chữ ký + hạn dùng; trả về payload hoặc None. Không bao giờ ném ngoại lệ."""
    try:
        if not token or not isinstance(token, str) or token.count(".") != 1 or len(token) > 1000:
            return None
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig.encode("utf-8"), expected.encode("ascii")):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except Exception:
        return None


def revoke_token(token: Optional[str]) -> bool:
    """Thu hồi token khi đăng xuất (lưu jti đến lúc token hết hạn)."""
    payload = _decode(token)
    if not payload or not payload.get("jti"):
        return False
    now = int(time.time())
    revoked = {k: v for k, v in _load_revoked().items() if v > now}  # dọn mục đã hết hạn
    revoked[payload["jti"]] = int(payload["exp"])
    try:
        _REVOKED_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _REVOKED_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(revoked), encoding="utf-8")
        os.replace(tmp, _REVOKED_FILE)
        return True
    except Exception:
        return False


def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Trả về thông tin người dùng nếu token hợp lệ, đúng chữ ký, còn hạn và chưa bị thu hồi; ngược lại None."""
    payload = _decode(token)
    if not payload or payload.get("r") not in ("admin", "manager") or not payload.get("u"):
        return None
    if not payload.get("jti") or payload["jti"] in _load_revoked():
        return None
    return {"username": payload["u"], "role": payload["r"], "ho_ten": payload.get("n") or payload["u"]}
