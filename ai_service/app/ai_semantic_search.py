"""
MODULE AI 2: TÌM KIẾM NGỮ NGHĨA & TƯ VẤN CẤU HÌNH LINH KIỆN MÁY TÍNH
Kiến trúc Hybrid Ranking: TF-IDF Word (0.5) + TF-IDF Char N-gram (0.2) + Knowledge Graph Category & Spec Boost (0.3).
Hỗ trợ Khởi tạo lười (Lazy Initialization), Lọc cứng ngân sách (Budget Filtering),
và Đề xuất cấu hình PC đồng bộ (Suggest Build Mode).
"""
import json
import logging
import os
import re
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db import execute_query
from app.entity_extractor import extract_price_condition
from app.knowledge_graph import HardwareNeed, get_knowledge_graph
from app.text_normalizer import remove_diacritics

logger = logging.getLogger("ai_service.semantic_search")

# Cấu hình trọng số Hybrid Ranking (có thể ghi đè bằng biến môi trường sau khi dò trọng số
# bằng eval/eval_semantic.py --tune)
WEIGHT_TFIDF_WORD = float(os.getenv("SEM_WEIGHT_WORD", "0.5"))
WEIGHT_TFIDF_CHAR = float(os.getenv("SEM_WEIGHT_CHAR", "0.2"))
WEIGHT_KG_BOOST = float(os.getenv("SEM_WEIGHT_KG", "0.3"))
MIN_RELEVANCE_SCORE = float(os.getenv("SEM_MIN_RELEVANCE", "0.05"))
SPEC_HINT_BONUS = 0.3            # Điểm cộng cho mỗi thông số kỹ thuật khớp gợi ý KG
OUT_OF_STOCK_PENALTY = 0.75      # Sản phẩm hết hàng bị nhân hệ số này
INDEX_TTL_SECONDS = int(os.getenv("SEM_INDEX_TTL_SECONDS", "600"))  # Tự làm mới chỉ mục sau 10 phút


def flatten_specs(specs_data: Any) -> str:
    """
    Biến đổi dữ liệu thông số kỹ thuật JSONB thành chuỗi văn bản không dấu phục vụ Vector hóa (A2-2).
    Đọc các khóa thực tế từ database/advanced_objects.sql:
    socket, vram, bus, tdp, cores, threads, wattage, panel, refresh_rate, switch, dpi...
    """
    if not specs_data:
        return ""

    if isinstance(specs_data, str):
        try:
            specs = json.loads(specs_data)
        except Exception:
            return remove_diacritics(specs_data.lower())
    elif isinstance(specs_data, dict):
        specs = specs_data
    else:
        return ""

    tokens = []
    for k, v in specs.items():
        if v is None:
            continue
        v_str = str(v).lower()
        k_str = str(k).lower()
        tokens.append(f"{k_str} {v_str}")

    joined = " ".join(tokens)
    return remove_diacritics(joined)


class AISemanticSearchEngine:
    """
    Bộ máy tìm kiếm ngữ nghĩa phần cứng lai (Hybrid Semantic Search Engine).
    Khởi tạo lười (không mở DB khi import) và tự động xây dựng ma trận đặc trưng.
    """

    def __init__(self):
        self.vectorizer_word = TfidfVectorizer(ngram_range=(1, 2))
        self.vectorizer_char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self.products: List[Dict[str, Any]] = []
        self.corpus: List[str] = []
        self.tfidf_matrix_word = None
        self.tfidf_matrix_char = None
        self.kg = get_knowledge_graph()
        self._is_initialized = False
        self._loaded_at = 0.0
        self._lock = threading.Lock()
        # Mảng NumPy tính sẵn phục vụ chấm điểm vector hóa
        self._categories: List[str] = []
        self._prices = np.zeros(0)
        self._stocks = np.zeros(0)
        # Bộ nhớ đệm vector điểm cộng KG theo từng nhu cầu (tính một lần cho mỗi lần lập chỉ mục)
        self._need_boost_cache: Dict[str, np.ndarray] = {}

    def ensure_initialized(self):
        """
        Khởi tạo lười khi có yêu cầu tra cứu đầu tiên (A2-1) và tự làm mới chỉ mục
        khi quá INDEX_TTL_SECONDS (giá, tồn kho thay đổi sẽ được cập nhật mà không cần khởi động lại).
        """
        stale = INDEX_TTL_SECONDS > 0 and (time.time() - self._loaded_at) > INDEX_TTL_SECONDS
        if not self._is_initialized or stale:
            with self._lock:
                if not self._is_initialized or (time.time() - self._loaded_at) > INDEX_TTL_SECONDS > 0:
                    self._load_products()
                    self._is_initialized = True

    def refresh(self):
        """Tải lại toàn bộ dữ liệu từ CSDL và xây dựng lại ma trận vector."""
        with self._lock:
            self._load_products()
            self._is_initialized = True

    def _load_products(self):
        """Tải danh sách sản phẩm từ PostgreSQL LinhKien_DB để xây dựng ma trận Vector (A2-2)."""
        sql = """
        SELECT 
            sp.id,
            sp.ma_sku,
            sp.ten,
            dm.ten AS danh_muc,
            th.ten AS thuong_hieu,
            sp.gia_niem_yet,
            sp.bao_hanh_thang,
            sp.thong_so_ky_thuat,
            COALESCE(tk.so_luong_ton, 0) AS so_luong_ton
        FROM san_pham sp
        JOIN danh_muc dm ON sp.danh_muc_id = dm.id
        JOIN thuong_hieu th ON sp.thuong_hieu_id = th.id
        LEFT JOIN ton_kho tk ON sp.id = tk.san_pham_id
        WHERE sp.dang_kinh_doanh = TRUE
        ORDER BY sp.id ASC;
        """
        try:
            res = execute_query(sql)
            if res["success"] and res["data"]:
                self.build_index(res["data"])
            else:
                logger.warning("Không thể nạp danh sách sản phẩm cho Semantic Search: %s", res.get("error"))
        except Exception as e:
            logger.error("Lỗi kết nối khi nạp sản phẩm cho Semantic Search: %s", e)
        finally:
            self._loaded_at = time.time()

    def build_index(self, products: List[Dict[str, Any]]):
        """
        Lập chỉ mục vector từ danh sách sản phẩm (tách riêng khỏi DB để kiểm thử offline được).
        Tính sẵn mảng danh mục / giá / tồn kho để chấm điểm vector hóa bằng NumPy.
        """
        specs_parsed = []
        corpus = []
        for p in products:
            specs = p.get("thong_so_ky_thuat")
            if isinstance(specs, str):
                try:
                    specs = json.loads(specs)
                except Exception:
                    specs = None
            specs_parsed.append(specs if isinstance(specs, dict) else None)
            ten_no = remove_diacritics(p.get("ten", ""))
            dm_no = remove_diacritics(p.get("danh_muc", ""))
            th_no = remove_diacritics(p.get("thuong_hieu", ""))
            specs_flat = flatten_specs(specs)
            # Xây dựng document chuẩn hóa đơn nhất (không dấu, chữ thường) theo A2-2
            doc = f"{ten_no} {dm_no} {th_no} bao hanh {p.get('bao_hanh_thang', '')} thang {specs_flat}"
            corpus.append(doc.lower())

        self.products = products
        self._specs = specs_parsed
        self.corpus = corpus
        self._categories = [p.get("danh_muc", "") for p in products]
        self._prices = np.array([float(p.get("gia_niem_yet") or 0) for p in products], dtype=float)
        self._stocks = np.array([float(p.get("so_luong_ton") or 0) for p in products], dtype=float)
        self._need_boost_cache = {}

        if corpus:
            self.tfidf_matrix_word = self.vectorizer_word.fit_transform(corpus)
            self.tfidf_matrix_char = self.vectorizer_char.fit_transform(corpus)
            logger.info("Đã lập chỉ mục Vector thành công cho %d sản phẩm.", len(products))
        self._is_initialized = True
        self._loaded_at = time.time()

    def _need_boost_vector(self, need: HardwareNeed) -> np.ndarray:
        """
        Vector điểm cộng của một nhu cầu KG cho toàn bộ sản phẩm:
        trọng số danh mục + SPEC_HINT_BONUS x (số thông số khớp gợi ý). Tính một lần rồi lưu đệm.
        """
        cached = self._need_boost_cache.get(need.name)
        if cached is not None:
            return cached
        cat_w = np.array([need.category_weights.get(c, 0.0) for c in self._categories], dtype=float)
        hint_hits = np.zeros(len(self._categories), dtype=float)
        for hint_k, hint_v in need.spec_hints.items():
            hint_hits += np.array(
                [1.0 if self._check_spec_hint(sp, hint_k, hint_v) else 0.0 for sp in self._specs],
                dtype=float,
            )
        vec = cat_w + SPEC_HINT_BONUS * hint_hits
        self._need_boost_cache[need.name] = vec
        return vec

    def detect_semantic_intent(self, query: str) -> List[str]:
        """Phát hiện các nhu cầu phần cứng thông qua Knowledge Graph (A2-3)."""
        needs = self.kg.detect_needs(query)
        return [need.name for need in needs]

    def _check_spec_hint(self, specs: Any, hint_key: str, hint_val: str) -> bool:
        """Kiểm tra một thông số kỹ thuật có thỏa mãn gợi ý Knowledge Graph hay không."""
        if not specs or not isinstance(specs, dict):
            return False

        spec_val = specs.get(hint_key)
        if spec_val is None:
            return False

        val_str = str(spec_val).lower()

        # Kiểm tra điều kiện số >= (e.g. >=8, >=144)
        if hint_val.startswith(">="):
            try:
                target_num = float(hint_val[2:])
                # Trích xuất số đầu tiên từ val_str (e.g. "12GB GDDR6X" -> 12.0)
                m = re.search(r'(\d+(?:\.\d+)?)', val_str)
                if m:
                    return float(m.group(1)) >= target_num
            except Exception:
                pass
        elif hint_val.lower() in val_str:
            return True

        return False

    def search(
        self,
        query: str,
        top_k: int = 5,
        budget: Optional[int] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm ngữ nghĩa linh kiện theo nhu cầu ngôn ngữ tự nhiên (A2-4).
        Xếp hạng lai (Hybrid Ranking): Word + Char N-gram + Knowledge Graph Boost.
        Tối ưu:
        - Chấm điểm VECTOR HÓA bằng NumPy (không lặp Python qua từng sản phẩm).
        - Lọc ngân sách bằng mặt nạ TRƯỚC khi xếp hạng (không bị thiếu kết quả khi sản phẩm
          điểm cao nhất vượt ngân sách).
        - Cho phép truyền `weights` để dò trọng số tối ưu trên tập đánh giá.
        """
        self.ensure_initialized()
        if not self.corpus or self.tfidf_matrix_word is None or self.tfidf_matrix_char is None:
            return []

        w = {
            "word": WEIGHT_TFIDF_WORD,
            "char": WEIGHT_TFIDF_CHAR,
            "kg": WEIGHT_KG_BOOST,
            "min_score": MIN_RELEVANCE_SCORE,
        }
        if weights:
            w.update(weights)

        q_clean = (query or "").strip()
        if not q_clean:
            return []
        q_no_accent = remove_diacritics(q_clean.lower())

        # 1. Phát hiện ngân sách nếu chưa được truyền tường minh
        if budget is None:
            price_cond = extract_price_condition(q_clean)
            if price_cond:
                if price_cond.get("operator") in ("<", "<="):
                    budget = price_cond.get("price_value")
                elif price_cond.get("operator") == "BETWEEN":
                    budget = price_cond.get("max_price")

        # 2. Nhận diện nhu cầu phần cứng qua Knowledge Graph
        detected_needs: List[HardwareNeed] = self.kg.detect_needs(q_clean)
        detected_names = [need.name for need in detected_needs]

        # 3. Mở rộng truy vấn với từ khóa trong Knowledge Graph
        expansion_terms = []
        for need in detected_needs:
            expansion_terms.extend([remove_diacritics(kw) for kw in need.keywords])
        expanded_query = q_no_accent
        if expansion_terms:
            expanded_query += " " + " ".join(expansion_terms)

        # 4. Độ tương đồng Cosine (ma trận TF-IDF đã chuẩn hóa L2 -> tích vô hướng = cosine)
        sim_word = cosine_similarity(self.vectorizer_word.transform([expanded_query]), self.tfidf_matrix_word).ravel()
        sim_char = cosine_similarity(self.vectorizer_char.transform([expanded_query]), self.tfidf_matrix_char).ravel()

        # 5. Điểm cộng KG vector hóa, chuẩn hóa về [0, 1]
        n = len(self.products)
        if detected_needs:
            kg_boosts = np.zeros(n, dtype=float)
            for need in detected_needs:
                kg_boosts += self._need_boost_vector(need)
            kg_boosts = np.minimum(1.0, kg_boosts / len(detected_needs))
        else:
            kg_boosts = np.zeros(n, dtype=float)

        final_scores = w["word"] * sim_word + w["char"] * sim_char + w["kg"] * kg_boosts
        in_stock = self._stocks > 0
        final_scores = np.where(in_stock, final_scores, final_scores * OUT_OF_STOCK_PENALTY)

        # 6. Mặt nạ hợp lệ: đạt ngưỡng liên quan VÀ trong ngân sách (lọc trước khi xếp hạng)
        valid = final_scores >= w["min_score"]
        if budget is not None:
            valid &= self._prices <= float(budget)
        candidate_idx = np.flatnonzero(valid)
        if candidate_idx.size == 0:
            return []

        # Lấy top_k bằng argpartition (O(n)) rồi sắp xếp phần nhỏ
        k = min(top_k, candidate_idx.size)
        cand_scores = final_scores[candidate_idx]
        top_local = np.argpartition(-cand_scores, k - 1)[:k]
        top_idx = candidate_idx[top_local[np.argsort(-cand_scores[top_local], kind="stable")]]

        results = []
        for idx in top_idx:
            prod = dict(self.products[idx])
            prod["similarity_score"] = round(float(final_scores[idx]) * 100, 1)
            prod["score_breakdown"] = {
                "word_score": round(float(sim_word[idx]) * 100, 1),
                "char_score": round(float(sim_char[idx]) * 100, 1),
                "kg_boost": round(float(kg_boosts[idx]) * 100, 1),
            }
            prod["matched_keywords"] = detected_names
            prod["in_stock"] = bool(in_stock[idx])
            prod["stock_label"] = "Còn hàng" if in_stock[idx] else "Tạm hết hàng"
            results.append(prod)
        return results

    def suggest_build(
        self,
        query: str,
        budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Chế độ gợi ý cấu hình PC hoàn chỉnh (A2-4):
        Chọn sản phẩm có điểm phù hợp nhất cho từng danh mục cốt lõi
        (CPU, Mainboard, RAM, VGA, SSD, Nguồn, Tản nhiệt, Vỏ case).
        """
        self.ensure_initialized()

        core_categories = ["CPU", "Mainboard", "RAM", "VGA", "SSD", "Nguồn"]
        optional_categories = ["Tản nhiệt", "Vỏ case"]

        build_components = []
        total_price = 0
        used_cats = set()

        # Tìm kiếm 30 sản phẩm phù hợp nhất cho nhu cầu
        candidates = self.search(query, top_k=30, budget=None)

        # Với mỗi danh mục, chọn sản phẩm đầu tiên có điểm cao nhất
        for cat in core_categories + optional_categories:
            cat_match = None
            for cand in candidates:
                if cand["danh_muc"] == cat and cand["id"] not in [c["id"] for c in build_components]:
                    cat_match = cand
                    break

            # Nếu trong danh sách ứng viên chưa có danh mục này, tìm riêng cho danh mục đó
            if cat_match is None:
                sub_query = f"{query} {cat}"
                sub_res = self.search(sub_query, top_k=5, budget=None)
                for cand in sub_res:
                    if cand["danh_muc"] == cat:
                        cat_match = cand
                        break

            if cat_match:
                build_components.append(cat_match)
                total_price += int(cat_match.get("gia_niem_yet", 0))
                used_cats.add(cat)

        within_budget = True
        if budget is not None:
            within_budget = total_price <= budget

        return {
            "query": query,
            "detected_needs": self.detect_semantic_intent(query),
            "components": build_components,
            "total_price": total_price,
            "budget": budget,
            "within_budget": within_budget,
            "category_count": len(build_components),
        }


# ==============================================================================
# KHỞI TẠO LƯỜI (LAZY SINGLETON) CHO SEMANTIC SEARCH ENGINE (A2-1)
# ==============================================================================
_engine_singleton: Optional[AISemanticSearchEngine] = None


def get_engine(force_refresh: bool = False) -> AISemanticSearchEngine:
    """Trả về phiên bản singleton của AISemanticSearchEngine (Lazy Initialization)."""
    global _engine_singleton
    if _engine_singleton is None or force_refresh:
        _engine_singleton = AISemanticSearchEngine()
    return _engine_singleton


class _LazyEngineProxy:
    """Proxy lười đảm bảo backward compatibility với lời gọi `semantic_search_engine.search(...)`."""
    def __getattr__(self, name):
        engine = get_engine()
        return getattr(engine, name)


semantic_search_engine = _LazyEngineProxy()
