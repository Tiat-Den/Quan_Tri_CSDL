"""
Module đồ thị tri thức phần cứng máy tính (Hardware Knowledge Graph) cho AI 2.
Nạp định nghĩa tri thức từ app/data/knowledge_graph.json, kiểm tra cấu trúc schema lúc nạp
và cung cấp hàm detect_needs() nhận diện nhu cầu người dùng với ranh giới từ nguyên bản (A2-3).
"""
import json
import logging
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ai_1_text2sql.text_normalizer import remove_diacritics

logger = logging.getLogger("ai_service.knowledge_graph")


@dataclass
class HardwareNeed:
    """Đại diện cho một nhu cầu phần cứng máy tính trong đồ thị tri thức."""
    name: str
    aliases: List[str] = field(default_factory=list)
    category_weights: Dict[str, float] = field(default_factory=dict)
    spec_hints: Dict[str, str] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)


class HardwareKnowledgeGraph:
    """Quản lý và tra cứu đồ thị tri thức phần cứng (Knowledge Graph)."""

    def __init__(self, data_path: Optional[str] = None):
        self.needs: Dict[str, HardwareNeed] = {}
        self._base_aliases: Dict[str, List[str]] = {}
        self.learned_aliases: Dict[str, List[str]] = {}
        if data_path is None:
            _p1 = os.path.join(os.path.dirname(__file__), "data", "knowledge_graph.json")
            _p2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge_graph.json")
            data_path = _p1 if os.path.exists(_p1) else _p2
        self.data_path = data_path
        self._load_and_validate()

    def _load_and_validate(self):
        """Nạp tệp JSON và xác thực schema nghiêm ngặt."""
        p = Path(self.data_path)
        if not p.exists():
            logger.warning("Không tìm thấy tệp knowledge_graph.json tại %s. Khởi tạo rỗng.", self.data_path)
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            if not isinstance(raw_data, dict):
                raise ValueError("Knowledge Graph JSON gốc phải là dictionary.")

            for need_name, content in raw_data.items():
                if not isinstance(content, dict):
                    raise ValueError(f"Nhu cầu '{need_name}' phải có nội dung dạng dict.")

                aliases = content.get("aliases", [])
                category_weights = content.get("category_weights", {})
                spec_hints = content.get("spec_hints", {})
                keywords = content.get("keywords", [])

                self._base_aliases[need_name] = list(aliases)
                self.needs[need_name] = HardwareNeed(
                    name=need_name,
                    aliases=list(aliases),
                    category_weights=category_weights,
                    spec_hints=spec_hints,
                    keywords=keywords,
                )

            logger.info("Đã nạp thành công %d nhu cầu phần cứng từ Knowledge Graph.", len(self.needs))
        except Exception as e:
            logger.error("Lỗi khi nạp Knowledge Graph JSON: %s", e)
            raise

    def detect_needs(self, query: str) -> List[HardwareNeed]:
        """
        Nhận diện các nhu cầu phần cứng có trong câu truy vấn (A2-3):
        - Đối sánh trên chuỗi không dấu (no_accent)
        - So khớp theo ranh giới từ nguyên bản (word boundary), không khớp chuỗi con tùy tiện
        """
        if not query:
            return []

        q_clean = query.strip().lower()
        q_no_accent = remove_diacritics(q_clean)

        detected = []
        for need in self.needs.values():
            matched = False

            # 1. Kiểm tra tên chính của nhu cầu
            main_patterns = [need.name.lower(), remove_diacritics(need.name.lower())]
            for pat in main_patterns:
                pat_esc = re.escape(pat)
                if re.search(r'(?:\b|^)' + pat_esc + r'(?:\b|$)', q_clean) or \
                   re.search(r'(?:\b|^)' + pat_esc + r'(?:\b|$)', q_no_accent):
                    matched = True
                    break

            # 2. Kiểm tra các bí danh (aliases)
            if not matched:
                for alias in need.aliases:
                    alias_lower = alias.lower()
                    alias_no = remove_diacritics(alias_lower)
                    if re.search(r'(?:\b|^)' + re.escape(alias_lower) + r'(?:\b|$)', q_clean) or \
                       re.search(r'(?:\b|^)' + re.escape(alias_no) + r'(?:\b|$)', q_no_accent):
                        matched = True
                        break

            if matched:
                detected.append(need)

        return detected

    def get_need_by_name(self, name: str) -> Optional[HardwareNeed]:
        return self.needs.get(name)

    def apply_learned_aliases(self, learned: Dict[str, List[str]]) -> int:
        """
        Học từ câu chưa hiểu (AI 2): bí danh của mỗi nhu cầu = bí danh gốc trong JSON + cụm từ Admin đã duyệt.
        Gọi lại nhiều lần vẫn đúng (luôn dựng lại từ bí danh gốc). Bỏ qua nhu cầu không tồn tại.
        Trả về số cụm từ học thêm thực sự được áp dụng.
        """
        applied: Dict[str, List[str]] = {}
        for need_name, base in self._base_aliases.items():
            existing = {remove_diacritics(a.lower()).strip() for a in base}
            existing.add(remove_diacritics(need_name.lower()).strip())
            extra = []
            for phrase in (learned or {}).get(need_name, []):
                phrase = re.sub(r"\s+", " ", (phrase or "").strip().lower())
                key = remove_diacritics(phrase)
                if len(key) >= 3 and key not in existing:
                    existing.add(key)
                    extra.append(phrase)
            self.needs[need_name].aliases = list(base) + extra
            if extra:
                applied[need_name] = extra
        self.learned_aliases = applied
        return sum(len(v) for v in applied.values())


# Singleton Knowledge Graph
_kg_instance: Optional[HardwareKnowledgeGraph] = None
_kg_lock = threading.Lock()
# KG "ứng viên" chỉ có hiệu lực trong luồng đang đánh giá (Admin bấm Huấn luyện lại)
_kg_override = threading.local()


def _load_learned_aliases() -> Dict[str, List[str]]:
    """Cụm từ nhu cầu đã duyệt + đã huấn luyện trong CSDL. Lỗi -> chỉ dùng tri thức gốc."""
    try:
        from app.ai_1_text2sql.learning_loop import load_trained_samples
        _intents, needs = load_trained_samples()
        return needs
    except Exception as ex:  # pragma: no cover
        logger.info("Không nạp được cụm từ học thêm cho Knowledge Graph (%s).", ex)
        return {}


def get_knowledge_graph() -> HardwareKnowledgeGraph:
    override = getattr(_kg_override, "instance", None)
    if override is not None:
        return override
    global _kg_instance
    if _kg_instance is None:
        with _kg_lock:
            if _kg_instance is None:
                kg = HardwareKnowledgeGraph()
                kg.apply_learned_aliases(_load_learned_aliases())
                _kg_instance = kg
    return _kg_instance


@contextmanager
def use_knowledge_graph(kg: HardwareKnowledgeGraph):
    """Tạm dùng `kg` CHỈ trong luồng hiện tại (đánh giá trước khi áp dụng cụm từ học thêm)."""
    previous = getattr(_kg_override, "instance", None)
    _kg_override.instance = kg
    try:
        yield kg
    finally:
        _kg_override.instance = previous
