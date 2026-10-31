import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.router import route, RouteDecision
from app.ai_2_semantic.ai_semantic_search import get_engine, flatten_specs, AISemanticSearchEngine
from app.ai_2_semantic.knowledge_graph import get_knowledge_graph, HardwareNeed


class TestP2SemanticSearch(unittest.TestCase):
    def test_lazy_initialization(self):
        """Kiểm tra proxy engine không khởi tạo DB ngay khi module được import."""
        engine = get_engine()
        self.assertIsNotNone(engine)
        # Proxy có các thuộc tính ủy nhiệm mà không vỡ
        self.assertTrue(hasattr(engine, "search"))
        self.assertTrue(hasattr(engine, "suggest_build"))

    def test_flatten_specs(self):
        """Kiểm tra bóc tách thông số kỹ thuật JSONB thành văn bản tìm kiếm."""
        specs = {
            "socket": "LGA1700",
            "cores": 16,
            "threads": 24,
            "vram": "12GB GDDR6X",
            "bus": "192-bit",
            "tdp": "200W",
            "panel": "IPS",
            "refresh_rate": "165Hz",
            "wattage": "750W",
            "form_factor": "M.2 NVMe PCIe 4.0",
        }
        text = flatten_specs(specs)
        self.assertIn("lga1700", text)
        self.assertIn("12gb gddr6x", text)
        self.assertIn("192-bit", text)
        self.assertIn("165hz", text)
        self.assertIn("750w", text)

    def test_knowledge_graph_detection(self):
        """Kiểm tra phát hiện nhu cầu từ bản đồ tri thức phần cứng."""
        kg = get_knowledge_graph()
        self.assertGreaterEqual(len(kg.needs), 10)

        needs = kg.detect_needs("Tư vấn cấu hình máy tính chơi game đồ họa nặng và dựng phim 4K")
        names = [n.name for n in needs]
        self.assertTrue(any("gaming" in name.lower() or "do_hoa" in name.lower() or "render" in name.lower() for name in names))

    def test_router_classification(self):
        """Kiểm tra router định tuyến chính xác giữa AI 1, AI 2 và UNKNOWN."""
        # AI 1 queries
        dec1 = route("Top 5 sản phẩm bán chạy nhất của cửa hàng")
        self.assertEqual(dec1.engine.lower(), "ai1")

        dec2 = route("Có bao nhiêu đơn hàng đang xử lý")
        self.assertEqual(dec2.engine.lower(), "ai1")

        # AI 2 queries
        dec3 = route("Tư vấn cấu hình máy tính chơi game đồ họa 3D và render video")
        self.assertEqual(dec3.engine.lower(), "ai2")

        dec4 = route("Tìm card màn hình RTX 4070 hoặc RTX 4060 VRAM cao")
        self.assertEqual(dec4.engine.lower(), "ai2")

        dec5 = route("Linh kiện phù hợp với mainboard socket LGA1700")
        self.assertEqual(dec5.engine.lower(), "ai2")

        # Nonsense queries
        dec6 = route("thời tiết hôm nay thế nào")
        self.assertEqual(dec6.engine.lower(), "unknown")

        dec7 = route("nấu cơm tấm sườn bì chả ngon")
        self.assertEqual(dec7.engine.lower(), "unknown")

    def test_semantic_search_hybrid_execution(self):
        """Kiểm tra động cơ tìm kiếm ngữ nghĩa kết hợp (Hybrid Search) trả về kết quả hợp lệ."""
        engine = get_engine()
        results = engine.search("VGA RTX 4070 chơi game 2K", top_k=3)
        self.assertIsInstance(results, list)
        if results:
            first = results[0]
            self.assertIn("ten", first)
            self.assertIn("similarity_score", first)
            self.assertIn("score_breakdown", first)
            self.assertGreater(first["similarity_score"], 0)

    def test_budget_filter(self):
        """Kiểm tra bộ lọc ngân sách cứng."""
        engine = get_engine()
        budget = 5000000.0  # 5 triệu
        results = engine.search("Màn hình chơi game 144Hz", top_k=5, budget=budget)
        for r in results:
            price = r.get("gia_ban") or 0.0
            if price > 0:
                self.assertLessEqual(price, budget)

    def test_suggest_build(self):
        """Kiểm tra chức năng gợi ý cấu hình PC theo ngân sách."""
        engine = get_engine()
        build = engine.suggest_build("Build PC văn phòng kế toán mượt mà", budget=15000000)
        self.assertIn("query", build)
        self.assertIn("components", build)
        self.assertIn("total_price", build)
        self.assertLessEqual(build["total_price"], 16000000)


if __name__ == "__main__":
    unittest.main()
