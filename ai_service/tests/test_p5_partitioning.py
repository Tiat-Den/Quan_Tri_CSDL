import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_5_partitioning.ai_predictive_partitioning import AIPredictivePartitioningEngine, LinearRegressionPredictor


class TestP5Partitioning(unittest.TestCase):
    def test_linear_regression_perfect_fit(self):
        """Kiểm tra hồi quy tuyến tính OLS với chuỗi dữ liệu hoàn hảo y = 3x + 10."""
        model = LinearRegressionPredictor()
        x_vals = [0.0, 1.0, 2.0, 3.0, 4.0]
        y_vals = [10.0, 13.0, 16.0, 19.0, 22.0]
        model.fit(x_vals, y_vals)
        self.assertAlmostEqual(model.slope, 3.0, places=4)
        self.assertAlmostEqual(model.intercept, 10.0, places=4)
        self.assertAlmostEqual(model.r_squared, 1.0, places=4)
        self.assertAlmostEqual(model.predict(5.0), 25.0, places=4)

    def test_linear_regression_constant_series(self):
        """Kiểm tra hồi quy tuyến tính với chuỗi giá trị hằng số."""
        model = LinearRegressionPredictor()
        x_vals = [0.0, 1.0, 2.0, 3.0]
        y_vals = [50.0, 50.0, 50.0, 50.0]
        model.fit(x_vals, y_vals)
        self.assertAlmostEqual(model.slope, 0.0, places=4)
        self.assertAlmostEqual(model.intercept, 50.0, places=4)
        self.assertAlmostEqual(model.predict(10.0), 50.0, places=4)

    def test_analyze_and_forecast_db(self):
        """Kiểm tra phân tích chuỗi thời gian đơn hàng thực tế từ PostgreSQL."""
        res = AIPredictivePartitioningEngine.analyze_and_forecast()
        self.assertTrue(res["success"])
        self.assertIn("historical_months", res)
        self.assertIn("forecast_months", res)
        self.assertIn("model_metrics", res)
        self.assertIn("capacity_assessment", res)
        self.assertIn("capacity_assessment", res)

        # Kiểm tra dự báo 3 tháng tiếp theo
        forecast = res["forecast_months"]
        self.assertEqual(len(forecast), 3)
        for item in forecast:
            self.assertIn("thang", item)
            self.assertIn("don_du_bao", item)
            self.assertIn("khoang_tin_cay_95", item)
            self.assertGreaterEqual(item["don_du_bao"], 0)

        # Kiểm tra chỉ số đánh giá mô hình
        metrics = res["model_metrics"]
        self.assertIn("r_squared", metrics)
        self.assertIn("backtest_mae", metrics)
        self.assertIn("beats_baseline", metrics)

        # Với CSDL hiện tại (bảng chưa phân vùng relkind='r')
        if not res["is_partitioned"]:
            self.assertEqual(len(res["generated_ddl"]), 0)
            self.assertEqual(len(res["migration_plan"]), 5)
            # Bước 1 phải có PARTITION BY RANGE (ngay_dat)
            step1 = res["migration_plan"][0]
            self.assertIn("PARTITION BY RANGE (ngay_dat)", step1["sql"])


if __name__ == "__main__":
    unittest.main()
