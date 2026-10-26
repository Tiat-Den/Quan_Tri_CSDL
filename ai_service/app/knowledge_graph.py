"""
Module đồ thị tri thức phần cứng máy tính (Hardware Knowledge Graph) cho AI 2.
Nạp định nghĩa tri thức từ app/data/knowledge_graph.json, kiểm tra cấu trúc schema lúc nạp
và cung cấp hàm detect_needs() nhận diện nhu cầu người dùng với ranh giới từ nguyên bản (A2-3).
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.text_normalizer import remove_diacritics

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
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), "data", "knowledge_graph.json")
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

                self.needs[need_name] = HardwareNeed(
                    name=need_name,
                    aliases=aliases,
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


# Singleton Knowledge Graph
_kg_instance: Optional[HardwareKnowledgeGraph] = None

def get_knowledge_graph() -> HardwareKnowledgeGraph:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = HardwareKnowledgeGraph()
    return _kg_instance
