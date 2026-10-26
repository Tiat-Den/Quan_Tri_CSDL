"""
Module chuẩn hóa câu hỏi tiếng Việt cho AI Text-to-SQL Rule Engine.
Hỗ trợ cắt giới hạn độ dài an toàn, bảo toàn dấu thập phân/phân cách nghìn giữa các chữ số,
và sinh song song hai biểu diễn: có dấu (accented) và không dấu (no_accent).
"""
import re
import unicodedata
from typing import Tuple

from app import config

# Bảng chuyển đổi ký tự tiếng Việt có dấu sang không dấu
VIETNAMESE_ACCENT_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd',
}

# Regex loại bỏ dấu câu nhưng bảo tồn dấu phẩy và chấm nằm giữa hai chữ số
PUNCT_EXCEPT_NUMERIC = re.compile(
    r'(?<!\d)[,.]|[,.](?!\d)|[?!:;\'"“”‘’\(\)\[\]\{\}\/\\~`@#$%^&*+=<>|]',
    re.UNICODE
)

# Regex chuẩn hóa khoảng trắng thừa
SPACES_REGEX = re.compile(r'\s+')


def remove_diacritics(text: str) -> str:
    """Chuyển chuỗi tiếng Việt có dấu thành không dấu chữ thường."""
    if not text:
        return ""
    text = text.lower()
    return "".join(VIETNAMESE_ACCENT_MAP.get(c, c) for c in text)


def normalize_text(text: str) -> str:
    """
    Chuẩn hóa văn bản câu hỏi:
    1. Cắt cứng tại MAX_QUESTION_LEN để bảo vệ chống ReDoS / tràn bộ nhớ.
    2. Chuẩn hóa dạng Unicode NFC và lowercase.
    3. Loại bỏ dấu câu đặc biệt nhưng bảo toàn dấu phẩy/chấm giữa hai chữ số (e.g. 1,5 triệu, 5.000.000).
    4. Chuẩn hóa các cụm từ đồng nghĩa phổ biến trong phần cứng máy tính.
    5. Gộp khoảng trắng liên tiếp.
    """
    if not text:
        return ""

    max_len = getattr(config, "MAX_QUESTION_LEN", 300)
    if len(text) > max_len:
        text = text[:max_len]

    # Chuẩn hóa Unicode NFC
    s = unicodedata.normalize("NFC", text).strip().lower()

    # Thay thế dấu câu không cần thiết (không thay dấu , hoặc . nằm giữa 2 chữ số)
    s = PUNCT_EXCEPT_NUMERIC.sub(' ', s)

    # Chuẩn hóa từ đồng nghĩa linh kiện
    s = re.sub(r'\bcard màn hình\b', 'vga', s)
    s = re.sub(r'\bcard đồ họa\b', 'vga', s)
    s = re.sub(r'\bbo mạch chủ\b', 'mainboard', s)
    s = re.sub(r'\bbộ vi xử lý\b', 'cpu', s)
    s = re.sub(r'\bbộ nhớ trong\b', 'ram', s)
    s = re.sub(r'\bnguồn máy tính\b', 'nguồn', s)
    s = re.sub(r'\bthùng máy\b', 'vỏ case', s)
    s = re.sub(r'\btản nhiệt khí\b', 'tản nhiệt', s)
    s = re.sub(r'\btản nhiệt nước\b', 'tản nhiệt', s)
    s = re.sub(r'\bmàn hình máy tính\b', 'màn hình', s)
    s = re.sub(r'\bbàn phím cơ\b', 'bàn phím', s)
    s = re.sub(r'\bchuột máy tính\b', 'chuột', s)
    s = re.sub(r'\bổ cứng ssd\b', 'ssd', s)
    s = re.sub(r'\bổ cứng hdd\b', 'hdd', s)

    # Chuẩn hóa lỗi gõ phổ biến của tên kênh bán (shoppee, shope, shoppi, sopee -> shopee; face book -> facebook)
    s = re.sub(r'\b(shoppee|shopeee|shope|shoppi|shopi|sopee|shoppe)\b', 'shopee', s)
    s = re.sub(r'\b(face book|facebok|facebookk|phây búc|phay buc)\b', 'facebook', s)
    s = re.sub(r'\b(web site|webside|wedsite)\b', 'website', s)

    # Chuẩn hóa khoảng trắng kép
    s = SPACES_REGEX.sub(' ', s).strip()
    return s


def get_normalized_pair(text: str) -> Tuple[str, str]:
    """
    Trả về cặp (norm_text, no_accent) để phục vụ đối sánh song song
    vừa bảo toàn nhãn tiếng Việt có dấu, vừa đối sánh linh hoạt không dấu.
    """
    norm = normalize_text(text)
    return norm, remove_diacritics(norm)
