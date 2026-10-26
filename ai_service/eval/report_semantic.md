# BÁO CÁO ĐÁNH GIÁ ĐỊNH LƯỢNG AI 2: SEMANTIC SEARCH ENGINE (A2-6)

**Thời gian thực hiện:** 2026-10-20 21:47:40  
**Môi trường:** Local Python Offline, PostgreSQL `LinhKien_DB` (schema `LinhKien`)  
**Bộ ngữ liệu kiểm thử:** `eval/semantic_gold.json` (22 câu hỏi mẫu)

---

## 1. TỔNG QUAN CHỈ SỐ CHẤT LƯỢNG

| Chỉ số đánh giá | Giá trị thực tế | Ngưỡng kỳ vọng | Trạng thái |
|---|---|---|---|
| **Precision@3 (theo danh mục)** | **88.3%** | &ge; 70.0% | **ĐẠT (PASS)** |
| **Mean Reciprocal Rank (MRR)** | **0.950** | &ge; 0.800 | **ĐẠT (PASS)** |
| **Độ chính xác thỏa đặc tả (Spec Predicate)** | **84.6%** | &ge; 80.0% | **ĐẠT (PASS)** |
| **Tỷ lệ lọc câu hỏi vô nghĩa (Nonsense Rejection)** | **100.0%** | 100.0% | **ĐẠT (PASS)** |

---

## 2. SO SÁNH TRƯỚC VÀ SAU CẢI TIẾN (HYBRID VS TF-IDF THUẦN)

| Tiêu chí so sánh | Phiên bản cũ (TF-IDF Đơn giản) | Phiên bản mới (Hybrid AI 2) |
|---|---|---|
| **Mô hình hóa đặc trưng** | Chỉ TF-IDF từ vựng cơ bản | Lai: TF-IDF Word (0.5) + Char N-gram 3-5 (0.2) + KG Boost (0.3) |
| **Khả năng chịu lỗi chính tả** | Kém (sai một ký tự mất điểm) | Tốt (nhờ subword Char WB: *rtx4070*, *ryzen7*) |
| **Khớp thông số JSONB** | Không hỗ trợ (chỉ đọc text) | Đọc sâu JSONB: *vram, socket, panel, refresh_rate, wattage* |
| **Lọc ngân sách & tồn kho** | Không có (chỉ so độ tương đồng) | Tích hợp bộ đọc giá, lọc cứng ngân sách, ưu tiên hàng có sẵn |
| **Xử lý câu vô nghĩa** | Ép độn đủ 3 kết quả rác | Lọc ngưỡng `MIN_RELEVANCE_SCORE`, trả rỗng kèm giải thích |

---

## 3. BẢNG CHI TIẾT KẾT QUẢ TỪNG TRUY VẤN

| ID | Câu truy vấn người dùng | Danh mục kỳ vọng | Top 3 kết quả trả về | P@3 | MRR | Thỏa Spec |
|---|---|---|---|---|---|---|
| 1 | `Tìm cấu hình chơi game nặng mượt mà` | VGA, CPU, RAM, Màn hình | MSI GeForce RTX 4070 Ti SUPER 16GB (VGA)<br>Gigabyte GeForce RTX 4080 SUPER 16GB (VGA)<br>ASUS TUF GeForce RTX 4090 24GB (VGA) | 1.0 | 1.0 | Có |
| 2 | `Cần màn hình đẹp chuẩn màu thiết kế đồ họa` | Màn hình | Dell P2422H 24 inch IPS (Màn hình)<br>LG 24MR400 24 inch IPS 100Hz (Màn hình)<br>ASUS TUF VG27AQ 27 inch 2K 165Hz (Màn hình) | 1.0 | 1.0 | Có |
| 3 | `Tư vấn CPU và RAM cho render video 4K` | CPU, RAM, VGA | AMD Ryzen 7 5700X (CPU)<br>AMD Ryzen 5 7600 (CPU)<br>AMD Ryzen 5 5600 (CPU) | 1.0 | 1.0 | Có |
| 4 | `Linh kiện văn phòng gõ word excel nhẹ nhàng` | CPU, RAM, SSD, Bàn phím, Chuột | Intel Core i3-12100F (CPU)<br>Samsung 980 NVMe 500GB (SSD)<br>Dell P2422H 24 inch IPS (Màn hình) | 0.67 | 1.0 | Có |
| 5 | `Tìm bàn phím cơ gõ sướng có led rgb` | Bàn phím | DareU EK87 (Bàn phím)<br>AKKO 3068B Plus (Bàn phím)<br>Razer BlackWidow V3 (Bàn phím) | 1.0 | 1.0 | Có |
| 6 | `Tản nhiệt nước cpu mát êm cho máy tính` | Tản nhiệt | NZXT Kraken 240 (Tản nhiệt)<br>Corsair iCUE H100i ELITE 240mm (Tản nhiệt)<br>Thermalright Peerless Assassin 120 SE (Tản nhiệt) | 1.0 | 1.0 | Có |
| 7 | `Nguồn công suất lớn 750w 850w chuẩn gold` | Nguồn | Seasonic Focus GX-850 850W Gold (Nguồn)<br>Corsair CV650 650W 80 Plus Bronze (Nguồn)<br>MSI MAG A650BN 650W (Nguồn) | 1.0 | 1.0 | Có |
| 8 | `Ổ cứng dung lượng lớn lưu trữ nhiều dữ liệu` | HDD, SSD | Seagate Barracuda 2TB (HDD)<br>Toshiba P300 1TB (HDD)<br>WD Blue 1TB 7200rpm (HDD) | 1.0 | 1.0 | Có |
| 9 | `Card đồ họa chơi game fps cao 144hz` | VGA, Màn hình | AOC 24G2 24 inch 144Hz (Màn hình)<br>ASUS TUF VG27AQ 27 inch 2K 165Hz (Màn hình)<br>Samsung Odyssey G5 27 inch 2K 165Hz (Màn hình) | 1.0 | 1.0 | Không |
| 10 | `Bộ nhớ RAM 32gb ddr5 cho đa nhiệm mượt` | RAM | Corsair Vengeance 32GB (2x16) DDR5 6000 (RAM)<br>G.Skill Trident Z5 32GB (2x16) DDR5 6000 (RAM)<br>Kingston Fury Beast 32GB DDR4 3200 (RAM) | 1.0 | 1.0 | Có |
| 11 | `Cần máy làm livestream phát trực tiếp obs` | VGA, CPU, RAM | Kingston Fury Beast 32GB DDR4 3200 (RAM)<br>Corsair Vengeance 32GB (2x16) DDR5 6000 (RAM)<br>G.Skill Trident Z5 32GB (2x16) DDR5 6000 (RAM) | 1.0 | 1.0 | Không |
| 12 | `Cấu hình cho lập trình viên chạy docker` | RAM, CPU, SSD | Kingston Fury Beast 32GB DDR4 3200 (RAM)<br>Corsair Vengeance 32GB (2x16) DDR5 6000 (RAM)<br>G.Skill Trident Z5 32GB (2x16) DDR5 6000 (RAM) | 1.0 | 1.0 | Có |
| 13 | `Ổ cứng lưu trữ máy chủ nas chạy liên tục` | HDD | WD Blue 1TB 7200rpm (HDD)<br>Toshiba P300 1TB (HDD)<br>Seagate Barracuda 2TB (HDD) | 1.0 | 1.0 | Có |
| 14 | `Linh kiện giá rẻ tiết kiệm ngân sách thấp` | CPU, VGA, Mainboard, RAM | Kingston Fury Beast 8GB DDR4 3200 (RAM)<br>Intel Core i3-12100F (CPU)<br>MSI MAG A650BN 650W (Nguồn) | 0.67 | 1.0 | Có |
| 15 | `tim card man hinh gaming choi game` | VGA | Gigabyte Radeon RX 7800 XT GAMING OC 16GB (VGA)<br>AOC 24G2 24 inch 144Hz (Màn hình)<br>ASUS TUF VG27AQ 27 inch 2K 165Hz (Màn hình) | 0.33 | 1.0 | Có |
| 16 | `man hinh dell 2k ips sieu net` | Màn hình | Dell P2422H 24 inch IPS (Màn hình)<br>ASUS TUF VG27AQ 27 inch 2K 165Hz (Màn hình)<br>LG 24MR400 24 inch IPS 100Hz (Màn hình) | 1.0 | 1.0 | Có |
| 17 | `chuot khong day dpi cao choi game fps` | Chuột | Gigabyte Radeon RX 7800 XT GAMING OC 16GB (VGA)<br>AOC 24G2 24 inch 144Hz (Màn hình)<br>ASUS TUF VG27AQ 27 inch 2K 165Hz (Màn hình) | 0.0 | 0.0 | Có |
| 18 | `ssd nvme toc do doc ghi cao` | SSD | Kingston NV2 NVMe 1TB (SSD)<br>Samsung 990 PRO NVMe 1TB (SSD)<br>Samsung 980 NVMe 500GB (SSD) | 1.0 | 1.0 | Có |
| 19 | `mainboard ho tro wifi kem socket am5` | Mainboard | MSI MAG B650 TOMAHAWK WIFI (Mainboard)<br>ASRock B650M PRO RS (Mainboard)<br>MSI PRO B760M-P (Mainboard) | 1.0 | 1.0 | Có |
| 20 | `Card vga rtx4070 ti cho game 4k` | VGA | MSI GeForce RTX 4070 Ti SUPER 16GB (VGA)<br>Gigabyte GeForce RTX 4080 SUPER 16GB (VGA)<br>ASUS TUF GeForce RTX 4090 24GB (VGA) | 1.0 | 1.0 | Có |
| 21 | `thời tiết hôm nay thế nào` | *(Câu vô nghĩa)* | Chính xác (trả về rỗng) | 1.0 | 1.0 | N/A |
| 22 | `mua vé máy bay đi hà nội` | *(Câu vô nghĩa)* | Chính xác (trả về rỗng) | 1.0 | 1.0 | N/A |

---
*Báo cáo được tạo tự động bởi `eval/eval_semantic.py` phục vụ nghiệm thu Tiểu luận môn Quản trị CSDL.*
