"""
HỆ THỐNG THIẾT KẾ GIAO DIỆN CHUẨN ENTERPRISE (theo UI_UPGRADE_DESIGN.md).
Đồng bộ 100% Light Theme sạch sẽ, loại bỏ hoàn toàn xung đột màu sắc và 'mùi AI'.
Không chứa logic nghiệp vụ - chỉ thay đổi hiển thị thị giác.
"""
from html import escape

# Design tokens
BRAND = "#0284c7"
BRAND_HOVER = "#0369a1"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#64748b"
BORDER = "#e2e8f0"
BORDER_STRONG = "#cbd5e1"
SURFACE = "#ffffff"
SURFACE_SUBTLE = "#f1f5f9"
HEALTHY, WARNING, DANGER = "#059669", "#d97706", "#dc2626"
CHART_BLUE = BRAND

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Reset toàn trang sang font Inter và nền sáng cao cấp */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: #f8fafc !important;
    color: #0f172a !important;
}

/* Ẩn header mặc định màu mè của Streamlit */
header[data-testid="stHeader"] {
    background: transparent !important;
}

/* ---------- 1. SIDEBAR SẠCH SẼ & ĐỒNG BỘ ---------- */
section[data-testid="stSidebar"] {
    background-color: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
    box-shadow: 1px 0 3px rgba(0, 0, 0, 0.02) !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding-top: 1.5rem !important;
}
section[data-testid="stSidebar"] * {
    color: #334155;
}

.side-brand {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0f172a !important;
    letter-spacing: -0.01em;
}
.side-brand-sub {
    font-size: 0.78rem;
    color: #64748b !important;
    margin-top: 0.15rem;
    margin-bottom: 0.8rem;
}
.side-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #64748b !important;
    margin: 1.1rem 0 0.45rem 0;
}

/* Thẻ hồ sơ người dùng trong Sidebar */
.user-card {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 0.85rem;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    margin: 0.5rem 0 0.75rem 0;
}
.user-avatar {
    width: 36px;
    height: 36px;
    border-radius: 6px;
    background: #0284c7;
    color: #ffffff !important;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.95rem;
    flex-shrink: 0;
}
.user-name {
    font-size: 0.88rem;
    font-weight: 600;
    color: #0f172a !important;
    line-height: 1.3;
}

/* Thẻ kết nối CSDL trong Sidebar */
.db-card {
    padding: 0.75rem 0.85rem;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    font-size: 0.8rem;
    line-height: 1.65;
    color: #334155 !important;
    margin-bottom: 0.6rem;
}
.db-card b {
    color: #0f172a !important;
    font-weight: 600;
}

/* Danh sách module trong Sidebar */
.module-list {
    list-style: none;
    padding: 0;
    margin: 0;
}
.module-list li {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.45rem 0.5rem;
    border-radius: 6px;
    font-size: 0.82rem;
    color: #334155 !important;
    transition: background 0.1s ease;
}
.module-list li:hover {
    background-color: #f1f5f9;
}
.module-list .code {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 0.72rem;
    background: #e2e8f0;
    color: #0f172a !important;
    padding: 0.12rem 0.38rem;
    border-radius: 4px;
    font-weight: 600;
    white-space: nowrap;   /* "AI 1" luôn nằm trên 1 dòng */
    flex-shrink: 0;        /* không bị co hẹp khi tên phân hệ dài */
}
.module-list .name {
    font-weight: 600;
    color: #0f172a !important;
}

/* ---------- 2. KHUNG TIÊU ĐỀ CHÍNH (ENTERPRISE HEADER) ---------- */
.enterprise-header {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1.25rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
.enterprise-header h1 {
    font-size: 1.32rem !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    margin: 0 !important;
    letter-spacing: -0.01em;
}
.enterprise-header p {
    font-size: 0.82rem !important;
    color: #64748b !important;
    margin: 0.25rem 0 0 0 !important;
}
.enterprise-header .meta {
    font-size: 0.8rem;
    color: #475569 !important;
    background: #f1f5f9;
    padding: 0.35rem 0.65rem;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    white-space: nowrap;
    font-weight: 500;
}

/* ---------- 3. TIÊU ĐỀ KHU VỰC TRONG TAB ---------- */
.section-head {
    margin: 0.5rem 0 1rem 0;
}
.section-head .eyebrow {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #0284c7;
    margin-bottom: 0.2rem;
}
.section-head h3 {
    font-size: 1.15rem;
    font-weight: 600;
    color: #0f172a;
    margin: 0.1rem 0 0.25rem 0;
}
.section-head p {
    font-size: 0.86rem;
    color: #475569;
    margin: 0;
    line-height: 1.5;
}
.sub-head {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0f172a;
    margin: 1.1rem 0 0.5rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid #e2e8f0;
}

/* ---------- 4. SỬA LỖI THANH TAB CỦA STREAMLIT ---------- */
div[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #e2e8f0 !important;
    gap: 0.25rem !important;
    justify-content: flex-start !important;
}
button[data-baseweb="tab"] {
    padding: 0.65rem 0.95rem !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
}
button[data-baseweb="tab"] p {
    font-size: 0.88rem !important;
    color: #64748b !important;
    font-weight: 500 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    border-bottom: 2px solid #0284c7 !important;
    background: transparent !important;
}
button[data-baseweb="tab"][aria-selected="true"] p {
    color: #0284c7 !important;
    font-weight: 600 !important;
}

/* ---------- 5. SỬA LỖI Ô NHẬP LIỆU & NÚT BẤM ---------- */
div[data-baseweb="input"] {
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 6px !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}
div[data-baseweb="input"]:focus-within {
    border-color: #0284c7 !important;
    box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15) !important;
}
div[data-baseweb="input"] input {
    background-color: #ffffff !important;
    color: #0f172a !important;
    font-size: 0.92rem !important;
}
div[data-baseweb="input"] input::placeholder {
    color: #94a3b8 !important;
}

/* Nút chính Primary (Xanh doanh nghiệp chuẩn #0284c7) */
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
    background-color: #0284c7 !important;
    color: #ffffff !important;
    border: 1px solid #0284c7 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
    transition: background-color 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
    background-color: #0369a1 !important;
    border-color: #0369a1 !important;
}

/* Nút phụ Secondary (Nền trắng viền xám mảnh chuẩn sạch sẽ) */
.stButton > button[kind="secondary"], .stDownloadButton > button {
    background-color: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}
.stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover {
    background-color: #f8fafc !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

/* ---------- 6. THẺ CHỈ SỐ KPI & HUY HIỆU ---------- */
.kpi-container {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    padding: 1rem 1.15rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
    height: 100%;
}
.kpi-container:hover {
    border-color: #cbd5e1;
}
.kpi-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #64748b;
    letter-spacing: 0.05em;
    margin-bottom: 0.35rem;
}
.kpi-val {
    font-size: 1.6rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.1;
    letter-spacing: -0.02em;
}
.kpi-desc {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.35rem;
}
.kpi-desc.good { color: #059669; }
.kpi-desc.warn { color: #d97706; }
.kpi-desc.bad  { color: #dc2626; }

.badge-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    white-space: nowrap;
}
.badge-status .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    display: inline-block;
}
.badge-healthy {
    background-color: #ecfdf5 !important;
    color: #065f46 !important;
    border: 1px solid #a7f3d0 !important;
}
.badge-warning {
    background-color: #fffbeb !important;
    color: #92400e !important;
    border: 1px solid #fde68a !important;
}
.badge-danger {
    background-color: #fef2f2 !important;
    color: #991b1b !important;
    border: 1px solid #fecaca !important;
}
.badge-neutral {
    background-color: #f1f5f9 !important;
    color: #475569 !important;
    border: 1px solid #e2e8f0 !important;
}

/* ---------- 7. BẢNG DỮ LIỆU & KHỐI MÃ SQL ---------- */
pre, code {
    font-family: 'JetBrains Mono', Consolas, monospace !important;
}
pre {
    background-color: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    font-size: 0.83rem !important;
    color: #0f172a !important;
}
div[data-testid="stDataFrame"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
}
div[data-testid="stExpander"] {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}
div[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    padding: 0.75rem 0.95rem;
}

/* ---------- 8. DANH MỤC LƯỢC ĐỒ & THANH DUNG LƯỢNG ---------- */
.catalog-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px;
    padding: 0.7rem 0.85rem;
    margin-bottom: 0.6rem;
}
.catalog-card .t {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 0.82rem;
    font-weight: 500;
    color: #0f172a;
}
.catalog-card .m {
    font-size: 0.74rem;
    color: #64748b;
    margin-top: 0.25rem;
}
.catalog-card.selected {
    border-color: #0284c7 !important;
    box-shadow: 0 0 0 1px #0284c7 !important;
}

.meter {
    height: 8px;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
    margin: 0.35rem 0 0.25rem 0;
}
.meter > span {
    display: block;
    height: 100%;
    background: #0284c7;
}
.meter.warn > span { background: #d97706; }
.meter.bad > span { background: #dc2626; }
.meter-caption {
    font-size: 0.76rem;
    color: #64748b;
}
</style>
"""


def section_header(title: str, description: str = "", eyebrow: str = "") -> str:
    """HTML tiêu đề khu vực của một tab: nhãn nhỏ (VD: 'AI 4'), tiêu đề, mô tả."""
    eb = f'<div class="eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    desc = f"<p>{escape(description)}</p>" if description else ""
    return f'<div class="section-head">{eb}<h3>{escape(title)}</h3>{desc}</div>'


def sub_header(title: str) -> str:
    return f'<div class="sub-head">{escape(title)}</div>'


def badge(text: str, kind: str = "neutral", dot: bool = False) -> str:
    """kind: healthy | warning | danger | neutral"""
    d = '<span class="dot"></span>' if dot else ""
    return f'<span class="badge-status badge-{kind}">{d}{escape(text)}</span>'


def kpi_card(label: str, value: str, desc: str = "", tone: str = "") -> str:
    """Thẻ chỉ số lớn. tone: '' | good | warn | bad (màu dòng mô tả)."""
    d = f'<div class="kpi-desc {tone}">{escape(desc)}</div>' if desc else ""
    return (f'<div class="kpi-container"><div class="kpi-label">{escape(label)}</div>'
            f'<div class="kpi-val">{escape(value)}</div>{d}</div>')


def meter(pct_used: float, caption: str = "") -> str:
    """Thanh đo tiến độ tối giản (VD: dung lượng ổ đĩa đã dùng)."""
    p = max(0.0, min(100.0, float(pct_used)))
    cls = "bad" if p >= 90 else "warn" if p >= 75 else ""
    cap = f'<div class="meter-caption">{escape(caption)}</div>' if caption else ""
    return f'<div class="meter {cls}"><span style="width:{p:.1f}%"></span></div>{cap}'
