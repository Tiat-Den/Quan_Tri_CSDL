"""
Module trích xuất thực thể và điều kiện lọc (Entities & Conditions) cho AI Text-to-SQL.
Hỗ trợ bóc tách giá tiền theo chuẩn Decimal, khoảng giá kế thừa đơn vị,
bóc tách danh mục, thương hiệu, trạng thái đơn hàng, kênh bán và phương thức thanh toán.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from app.schema_catalog import (
    BRANDS,
    CATEGORIES,
    CATEGORY_ALIASES,
    CHANNELS,
    ORDER_STATUSES,
    PAYMENT_METHODS,
)
from app.text_normalizer import remove_diacritics

MAX_PRICE = Decimal("1000000000000")  # 10^12 VNĐ


def get_unit_multiplier(text: str) -> Optional[Decimal]:
    """Xác định hệ số nhân từ đơn vị tiền tệ tiếng Việt trong chuỗi."""
    s = text.lower()
    if re.search(r"(?:(?<=\d)|(?<=\s)|^)(tỷ|ty|tỉ)(?=\s|$|[^\w])", s):
        return Decimal("1000000000")
    if re.search(r"(?:(?<=\d)|(?<=\s)|^)(triệu|trieu|tr|củ|cu)(?=\s|$|[^\w])", s):
        return Decimal("1000000")
    if re.search(r"(?:(?<=\d)|(?<=\s)|^)(k|nghìn|nghin|ngàn|ngan)(?=\s|$|[^\w])", s):
        return Decimal("1000")
    if re.search(r"(?:(?<=\d)|(?<=\s)|^)(đ|vnd|dong|đồng)(?=\s|$|[^\w])", s):
        return Decimal("1")
    return None


def parse_vietnamese_number(
    text: str,
    default_unit_multiplier: Optional[Decimal] = None,
    return_tuple: bool = False,
) -> Any:
    """
    Chuyển đổi chuỗi số tiếng Việt sang số nguyên VNĐ sử dụng Decimal (A1-3):
    - '5 triệu' -> 5000000
    - '1,5 triệu' / '1.5 tr' -> 1500000
    - '5.000.000' (phân nhóm nghìn) -> 5000000
    - '500k' -> 500000
    - '1tr5' -> 1500000
    - '5' (số trần < 10.000 không đơn vị) -> None (hoặc (None, True) nếu return_tuple=True)
    - Chuỗi vượt ngưỡng 10^12 hoặc quá 100 chữ số -> None (không ném ngoại lệ)

    Trả về: int hoặc None (nếu return_tuple=False); (val_int, needs_clarification) nếu return_tuple=True.
    """
    if not text:
        return (None, False) if return_tuple else None

    s = text.strip().lower()
    if len(s) > 100:
        return (None, False) if return_tuple else None

    # Hỗ trợ dạng 1tr5, 2củ3
    m_split = re.match(r"^(\d+)\s*(?:tr|trieu|triệu|cu|củ)\s*(\d+)$", s)
    if m_split:
        try:
            main_part = Decimal(m_split.group(1))
            sub_str = m_split.group(2)
            sub_val = Decimal(sub_str) / (Decimal(10) ** len(sub_str))
            total = (main_part + sub_val) * Decimal(1_000_000)
            if Decimal(0) <= total <= MAX_PRICE:
                val_int = int(total)
                return (val_int, False) if return_tuple else val_int
            return (None, False) if return_tuple else None
        except (InvalidOperation, ValueError, OverflowError):
            return (None, False) if return_tuple else None

    # Hỗ trợ dạng 1k5
    m_k_split = re.match(r"^(\d+)\s*(?:k|nghìn|nghin|ngàn|ngan)\s*(\d+)$", s)
    if m_k_split:
        try:
            main_part = Decimal(m_k_split.group(1))
            sub_str = m_k_split.group(2)
            sub_val = Decimal(sub_str) / (Decimal(10) ** len(sub_str))
            total = (main_part + sub_val) * Decimal(1_000)
            if Decimal(0) <= total <= MAX_PRICE:
                val_int = int(total)
                return (val_int, False) if return_tuple else val_int
            return (None, False) if return_tuple else None
        except (InvalidOperation, ValueError, OverflowError):
            return (None, False) if return_tuple else None

    # Xác định multiplier từ đơn vị
    multiplier = None
    if re.search(r"(?:(?<=\d)|(?<=\s)|^)(tỷ|ty|tỉ)(?=\s|$|[^\w])", s):
        multiplier = Decimal("1000000000")
        s = re.sub(r"(?:(?<=\d)|(?<=\s)|^)(tỷ|ty|tỉ)(?=\s|$|[^\w])", "", s).strip()
    elif re.search(r"(?:(?<=\d)|(?<=\s)|^)(triệu|trieu|tr|củ|cu)(?=\s|$|[^\w])", s):
        multiplier = Decimal("1000000")
        s = re.sub(r"(?:(?<=\d)|(?<=\s)|^)(triệu|trieu|tr|củ|cu)(?=\s|$|[^\w])", "", s).strip()
    elif re.search(r"(?:(?<=\d)|(?<=\s)|^)(k|nghìn|nghin|ngàn|ngan)(?=\s|$|[^\w])", s):
        multiplier = Decimal("1000")
        s = re.sub(r"(?:(?<=\d)|(?<=\s)|^)(k|nghìn|nghin|ngàn|ngan)(?=\s|$|[^\w])", "", s).strip()
    elif re.search(r"(?:(?<=\d)|(?<=\s)|^)(đ|vnd|dong|đồng)(?=\s|$|[^\w])", s):
        multiplier = Decimal("1")
        s = re.sub(r"(?:(?<=\d)|(?<=\s)|^)(đ|vnd|dong|đồng)(?=\s|$|[^\w])", "", s).strip()
    elif default_unit_multiplier is not None:
        multiplier = default_unit_multiplier

    # Kiểm tra phân nhóm nghìn: e.g. 5.000.000 hoặc 5,000,000
    if re.match(r"^\d{1,3}([.,]\d{3})+$", s):
        clean_num = re.sub(r"[.,]", "", s)
        try:
            val = Decimal(clean_num)
            mult = multiplier if multiplier is not None else Decimal("1")
            total = val * mult
            if Decimal(0) <= total <= MAX_PRICE:
                val_int = int(total)
                return (val_int, False) if return_tuple else val_int
            return (None, False) if return_tuple else None
        except (InvalidOperation, ValueError, OverflowError):
            return (None, False) if return_tuple else None

    # Số thập phân (e.g. 1.5 hoặc 1,5)
    s = s.replace(",", ".")
    m_num = re.match(r"^([\d\.]+)$", s)
    if not m_num:
        return (None, False) if return_tuple else None

    try:
        val = Decimal(m_num.group(1))
    except (InvalidOperation, ValueError, OverflowError):
        return (None, False) if return_tuple else None

    if multiplier is None:
        # Số trần không có đơn vị
        if val < Decimal("10000"):
            return (None, True) if return_tuple else None
        total = val
    else:
        total = val * multiplier

    if Decimal(0) <= total <= MAX_PRICE:
        val_int = int(total)
        return (val_int, False) if return_tuple else val_int
    return (None, False) if return_tuple else None


def extract_price_condition(text: str) -> Dict[str, Any]:
    """
    Trích xuất điều kiện lọc theo giá tiền (A1-3):
    - Khoảng giá: 'từ X đến Y' (áp đơn vị của Y cho X nếu X khuyết đơn vị)
    - Toán tử >=: 'từ X trở lên', 'ít nhất X', 'tối thiểu X', '>='
    - Toán tử <=: 'không quá X', 'tối đa X', '<='
    - Toán tử >: 'giá trên X', 'lớn hơn X', 'cao hơn X', '>'
    - Toán tử <: 'giá dưới X', 'nhỏ hơn X', 'thấp hơn X', '<'
    """
    res: Dict[str, Any] = {}
    clean = text.lower().strip()

    # 1. Khoảng giá: từ X đến Y
    pattern_range = (
        r"(?:từ|tu|trong khoảng|trong khoang)\s+"
        r"([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)\s+"
        r"(?:đến|den|tới|toi|-)\s+"
        r"([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)"
    )
    m_range = re.search(pattern_range, clean)
    if m_range:
        s1 = m_range.group(1).strip()
        s2 = m_range.group(2).strip()
        unit2 = get_unit_multiplier(s2)
        unit1 = get_unit_multiplier(s1)
        v2, c2 = parse_vietnamese_number(s2, return_tuple=True)
        v1, c1 = parse_vietnamese_number(s1, default_unit_multiplier=unit2 if unit1 is None else None, return_tuple=True)
        if c1 or c2:
            return {
                "needs_clarification": True,
                "clarification": "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: từ 1 triệu đến 3 triệu.",
            }
        if v1 is not None and v2 is not None:
            res["operator"] = "BETWEEN"
            res["min_price"] = min(v1, v2)
            res["max_price"] = max(v1, v2)
            return res

    # 2. Toán tử >= (từ X trở lên, ít nhất X, tối thiểu X, >= X)
    pattern_gte = (
        r"(?:từ|tu)\s+([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)\s+(?:trở lên|tro len)"
        r"|(?:ít nhất|it nhat|tối thiểu|toi thieu|>=)\s*([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)"
    )
    m_gte = re.search(pattern_gte, clean)
    if m_gte:
        s_val = (m_gte.group(1) or m_gte.group(2) or "").strip()
        val, need_c = parse_vietnamese_number(s_val, return_tuple=True)
        if need_c:
            return {
                "needs_clarification": True,
                "clarification": "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: 5 triệu.",
            }
        if val is not None:
            res["operator"] = ">="
            res["price_value"] = val
            return res

    # 3. Toán tử <= (không quá X, tối đa X, <= X)
    pattern_lte = (
        r"(?:không quá|khong qua|tối đa|toi da|<=)\s*"
        r"([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)"
    )
    m_lte = re.search(pattern_lte, clean)
    if m_lte:
        s_val = m_lte.group(1).strip()
        val, need_c = parse_vietnamese_number(s_val, return_tuple=True)
        if need_c:
            return {
                "needs_clarification": True,
                "clarification": "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: 5 triệu.",
            }
        if val is not None:
            res["operator"] = "<="
            res["price_value"] = val
            return res

    # 4. Toán tử > (trên, lớn hơn, cao hơn, >)
    pattern_gt = (
        r"(?:giá|gia|sản phẩm|san pham|linh kiện|linh kien)?\s*"
        r"(?:trên|tren|lớn hơn|lon hon|cao hơn|cao hon|>)\s*"
        r"([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)"
    )
    m_gt = re.search(pattern_gt, clean)
    if m_gt:
        s_val = m_gt.group(1).strip()
        val, need_c = parse_vietnamese_number(s_val, return_tuple=True)
        if need_c:
            return {
                "needs_clarification": True,
                "clarification": "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: 5 triệu.",
            }
        if val is not None:
            res["operator"] = ">"
            res["price_value"] = val
            return res

    # 5. Toán tử < (dưới, nhỏ hơn, thấp hơn, <)
    pattern_lt = (
        r"(?:giá|gia|sản phẩm|san pham|linh kiện|linh kien)?\s*"
        r"(?:dưới|duoi|nhỏ hơn|nho hon|thấp hơn|thap hon|<)\s*"
        r"([\d\.,\s]+(?:triệu|trieu|tr|cu|củ|k|nghìn|nghin|ngàn|ngan|đ|vnd|dong|tỷ|ty|tỉ)?)"
    )
    m_lt = re.search(pattern_lt, clean)
    if m_lt:
        s_val = m_lt.group(1).strip()
        val, need_c = parse_vietnamese_number(s_val, return_tuple=True)
        if need_c:
            return {
                "needs_clarification": True,
                "clarification": "Bạn muốn nói giá bao nhiêu đồng? Ví dụ: 5 triệu.",
            }
        if val is not None:
            res["operator"] = "<"
            res["price_value"] = val
            return res

    return res


def extract_top_n(text: str) -> Optional[int]:
    """
    Trích xuất số N trong cụm 'top N' hoặc 'N sản phẩm', 'N khách hàng'
    Ví dụ: 'top 5' -> 5, 'top 10' -> 10, '5 khách hàng' -> 5, '3 sản phẩm đắt nhất' -> 3
    """
    clean = text.lower()
    # 'top 5', 'top 10'
    m = re.search(r'\btop\s*(\d+)\b', clean)
    if m:
        return int(m.group(1))

    # '5 sản phẩm đắt nhất', '5 khách hàng mua nhiều nhất'
    m = re.search(
        r'\b(\d+)\s*(?:sản phẩm|san pham|linh kiện|linh kien|khách hàng|khach hang|khách|khach|món|đơn|don)\b',
        clean,
    )
    if m:
        return int(m.group(1))

    return None


def extract_category(text: str) -> Optional[str]:
    """
    Trích xuất tên danh mục linh kiện (A1-2):
    Đối sánh trên cả dạng có dấu và không dấu, hỗ trợ bí danh tiếng Anh (monitor, keyboard, psu, gpu...)
    Trả về tên danh mục chuẩn có dấu trong DB (12 danh mục).
    """
    if not text:
        return None

    clean = text.lower()
    no_accent = remove_diacritics(clean)

    # 1. Tra cứu theo CATEGORY_ALIASES trên chuỗi không dấu (ưu tiên cụm từ dài nhất)
    sorted_aliases = sorted(CATEGORY_ALIASES.keys(), key=lambda a: len(a), reverse=True)
    for alias in sorted_aliases:
        alias_clean = alias.lower()
        pattern = r'\b' + re.escape(alias_clean) + r'\b'
        if re.search(pattern, clean) or re.search(pattern, no_accent):
            return CATEGORY_ALIASES[alias]

    # 2. Đối sánh trực tiếp trên 12 danh mục chuẩn
    sorted_cats = sorted(CATEGORIES, key=lambda c: len(c), reverse=True)
    for cat in sorted_cats:
        c_lower = cat.lower()
        c_no_accent = remove_diacritics(c_lower)
        pattern = r'\b' + re.escape(c_lower) + r'\b'
        pattern_no = r'\b' + re.escape(c_no_accent) + r'\b'
        if re.search(pattern, clean) or re.search(pattern_no, no_accent):
            return cat

    return None


def extract_brand(text: str) -> Optional[str]:
    """
    Trích xuất tên thương hiệu (A1-2):
    Đối sánh trên cả có dấu và không dấu cho 30 hãng sản xuất chuẩn trong DB.
    """
    if not text:
        return None

    clean = text.lower()
    no_accent = remove_diacritics(clean)

    sorted_brands = sorted(BRANDS, key=lambda b: len(b), reverse=True)
    for brand in sorted_brands:
        b_lower = brand.lower()
        b_no_accent = remove_diacritics(b_lower)
        pattern = r'\b' + re.escape(b_lower) + r'\b'
        pattern_no = r'\b' + re.escape(b_no_accent) + r'\b'
        if re.search(pattern, clean) or re.search(pattern_no, no_accent):
            return brand

    return None


def extract_order_status(text: str) -> Optional[str]:
    """
    Trích xuất trạng thái đơn hàng (A1-6):
    Loại bỏ 'mới' trần để tránh nhầm với 'sản phẩm mới'. Chỉ nhận khi có ngữ cảnh đơn hàng.
    """
    if not text:
        return None

    clean = text.lower()
    no_accent = remove_diacritics(clean)

    sorted_keywords = sorted(ORDER_STATUSES.keys(), key=lambda k: len(k), reverse=True)
    for keyword in sorted_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        pattern_no = r'\b' + re.escape(remove_diacritics(keyword)) + r'\b'
        if re.search(pattern, clean) or re.search(pattern_no, no_accent):
            return ORDER_STATUSES[keyword]

    return None


def extract_year(text: str) -> Optional[int]:
    """
    Trích xuất năm (ví dụ: 'năm 2025' -> 2025, '2025' -> 2025)
    """
    clean = text.lower()
    m = re.search(r'(?:năm|nam)\s*(20\d\d)\b', clean)
    if m:
        return int(m.group(1))

    m = re.search(r'\b(20\d\d)\b', clean)
    if m:
        return int(m.group(1))

    return None


def extract_channel(text: str) -> Optional[str]:
    """
    Trích xuất kênh bán hàng (A1-6):
    - Website: 'website', 'trang web', 'online', 'qua web', 'kênh web'
    - Shopee: 'shopee', 'shoppee', 'qua shopee', 'kênh shopee'
    - Facebook: 'facebook', 'fb', 'fanpage'
    - Cửa hàng: 'tại quầy', 'trực tiếp', 'kênh cửa hàng', 'tại cửa hàng', 'ở cửa hàng'
      (Không nhận 'của hãng' hoặc cụm sở hữu chung 'của cửa hàng')
    """
    if not text:
        return None

    clean = text.lower()
    no_accent = remove_diacritics(clean)

    # 1. Kênh Cửa hàng / Tại quầy (yêu cầu ngữ cảnh kênh hoặc giới từ 'tại', 'kênh', 'qua')
    if re.search(r'\b(tại quầy|tai quay|trực tiếp|truc tiep)\b', clean) or \
       re.search(r'\b(kênh|kenh|tại|tai|ở|o|qua|bán tại|ban tai)\s+(?:cửa hàng|cua hang)\b', clean) or \
       re.search(r'\b(kenh|tai|o|qua)\s+cua\s+hang\b', no_accent):
        return "cua_hang"

    # 2. Kênh Shopee
    if re.search(r'\b(shopee|shoppi|shope|shoppee)\b', clean) or \
       re.search(r'\b(shopee|shoppi|shope|shoppee)\b', no_accent):
        return "shopee"

    # 3. Kênh Facebook
    if re.search(r'\b(facebook|fb|fanpage)\b', clean) or \
       re.search(r'\b(facebook|fb|fanpage)\b', no_accent):
        return "facebook"

    # 4. Kênh Website / Online
    if re.search(r'\b(website|trang web|online)\b', clean) or \
       re.search(r'\b(website|trang web|online)\b', no_accent):
        return "website"

    if re.search(r'\b(qua|kênh|kenh|trên|tren|mua|đặt|dat)\s+web\b', clean) or \
       re.search(r'\b(qua|kenh|tren|mua|dat)\s+web\b', no_accent) or \
       re.search(r'\bweb\s+(?:bán|ban|hàng|hang)\b', no_accent):
        return "website"

    return None


def extract_payment_method(text: str) -> Optional[str]:
    """
    Trích xuất phương thức thanh toán (A1-6):
    Đã bỏ 'the' trần. Nhận diện các phương thức: tiền mặt, chuyển khoản, thẻ, ví điện tử, trả góp.
    """
    if not text:
        return None

    clean = text.lower()
    no_accent = remove_diacritics(clean)

    # Kiểm tra từ 'thẻ'/'the' khi có ngữ cảnh thanh toán
    if re.search(r'\b(thanh toán|thanh toan|qua|bằng|bang)\s+(?:thẻ|the)\b', clean) or \
       re.search(r'\b(?:thẻ|the)\s+(?:tín dụng|tin dung|atm|visa|mastercard|pos)\b', clean):
        return "the"

    sorted_keywords = sorted(PAYMENT_METHODS.keys(), key=lambda k: len(k), reverse=True)
    for keyword in sorted_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        pattern_no = r'\b' + re.escape(remove_diacritics(keyword)) + r'\b'
        if re.search(pattern, clean) or re.search(pattern_no, no_accent):
            return PAYMENT_METHODS[keyword]

    return None
