# Research notes — sources and adaptations

## Cập nhật thực nghiệm — 2026-11-06

B1–B5 đã chạy, gồm full-data cleaning/stay/role diagnostics. Kết quả cập nhật ở
[benchmark.md](../reports/cp1/benchmark.md); nguồn/phương pháp khóa ở
[detector_protocol.md](../reports/cp1/detector_protocol.md) và
[role_protocol.md](../reports/cp1/role_protocol.md). Không có lượt tìm paper hoặc tái tạo paper mới
trong cập nhật này. Ghi chú A–D bên dưới là snapshot nguồn tham khảo ngày 2026-10-31, không phải
trạng thái triển khai hiện tại; câu “chỉ subset” khi đó đã được các lượt full-data sau thay thế.

Các adaptation đã kiểm bằng dữ liệu của dự án:

- So fixed-anchor, median-updated, medoid-updated, max-neighbor-updated và ST-DBSCAN trên cùng
  observations/cases. Cùng radius không có nghĩa cùng ràng buộc hình học; không gọi mọi bộ đã tối ưu.
- ST-DBSCAN dùng neighborhood AND space/time; chuyển cluster thành min/max timestamp event có thể
  nối cả hành trình. Case user 010 dài 9,06 giờ/888,6 km là bằng chứng local, không quy kết mọi
  biến thể ST-DBSCAN hoặc kết quả paper. 9 bộ tham số chỉ khảo sát tổng hợp; 8 bộ phụ chưa chạy real.
- Người dùng chọn fixed-anchor 150 m/10 phút để tiếp tục vì trade-off đã đọc; không phải thông số
  chuyển giao từ paper hoặc winner đã vượt cổng B4. Baseline 100 m/core 0.2.0 được giữ nguyên.
- Score và rule số ngày/dwell được so riêng ở B5 trên cả 100/150 m; score giữ ít predictions hơn,
  ít đổi nơi trên nhóm cùng predicted khi dịch giờ, nhưng vẫn có predicted↔unknown và không có
  nhãn độc lập để xác nhận tốt hơn. Không dùng output model làm nhãn.
- B2 source groups/seeds tách selection/final, bootstrap theo exact-copy groups; GeoLife đã EDA
  và không chứng minh mọi near-duplicate được phát hiện. Final chưa sinh/mở.

Đọc/kiểm tra ngày 2026-10-31. Không tái tạo toàn bộ thuật toán hoặc kết quả của paper.

## A. GeoLife User Guide 1.3

Nguồn: [Microsoft landing page](https://www.microsoft.com/en-us/research/publication/geolife-gps-trajectory-dataset-user-guide/)
và User Guide-1.3.pdf bên trong ZIP do người dùng cung cấp, sections 1, 2.2, 4, 7.
Guide có số trajectory không nhất quán: introductory section là 17.621; version comparison
là 18.670 và 24.876.978 points. Local inventory xác nhận hai số sau bằng cách đếm file và record lines.
Guide xác nhận GMT, sáu header, altitude feet/-777, các vùng ngoài Beijing và sampling không đều.
Adaptation: UTC nội bộ, timezone config có warning, audit missing/gaps; không suy universal Beijing-local.
69 label files thực tế khác 73 users được nhắc trong guide. Labels là transportation, không phải Home/Office.
Chỉ thực hiện EDA/inference subset; toàn dataset mới đếm dòng và kiểm tra CRC, chưa validate từng record.

## B. Differential stay-point detection

Rafael Pérez-Torres, César Torres-Huitzil, Hiram Galeana-Zapién (2016),
[Full On-Device Stay Points Detection in Smartphones for Location-Based Mobile Applications](https://www.mdpi.com/1424-8220/16/10/1693),
[author article on PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5087481/), sections 3.1, 4.1.
MDPI direct fetch trả 429; nội dung sections liên quan đọc được qua PMC indexed text.
Paper mô tả differential distance/time checks và event-driven adaptations; buffered variant dùng mean coordinate.
Project dùng offline anchor scan, median representative, explicit maximum gap và flush cuối trajectory.
End time là last in-radius fix, tránh cộng thời gian đến điểm departure. Không triển khai Android middleware,
sensor duty cycling hoặc energy experiments. Ngưỡng 100m/10min/5min là hypotheses của project,
không khẳng định là thông số paper. GPS jitter/slow movement và missing data là failure cases.

## C. Individual life patterns

Yang Ye, Yu Zheng, Yukun Chen, Jianhua Feng, Xing Xie (2009),
[Mining Individual Life Pattern Based on Location History](https://www.microsoft.com/en-us/research/publication/mining-individual-life-pattern-based-on-location-history/),
[full paper PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/Mining20Individual20Life20Pattern20Based20on20Location20History.pdf), sections IV, VI.A.2.
PDF được truy cập và đọc các đoạn stay detection/clustering và parameter settings.
Framework biến GPS thành stays rồi geographic regions; paper dùng OPTICS. Experimental settings
trong paper: 200m/30min stays; clustering NoP=4, 150m. Project chọn DBSCAN đơn giản hơn,
100m/min_samples=3 ban đầu, kiểm tra sensitivity thay vì coi settings chuyển giao trực tiếp.
Chỉ mượn hướng modelling và temporal evidence; không tái tạo LP-Mine pattern-mining framework.
Density connectivity có thể gộp nhiều địa điểm; project báo cluster extent và giữ noise.

## D. Engineering references và quyết định riêng

- [scikit-learn 1.7 DBSCAN](https://scikit-learn.org/1.7/modules/generated/sklearn.cluster.DBSCAN.html):
  density clustering, noise -1, neighborhood/min_samples và khả năng tốn bộ nhớ. Sử dụng trên stays per user.
- [Haversine metric](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.pairwise.haversine_distances.html):
  latitude/longitude radians; eps meters chia spherical radius 6.371.008,8m. Không Euclidean trên degrees.
- [Python zoneinfo](https://docs.python.org/3.11/library/zoneinfo.html): IANA zones; dùng tzdata trên Windows.
- [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0): contract-only, JSON Schema nullable/validation/examples.

Fixed-anchor heuristic grouping, recurrence gates, score weights, role windows, ambiguity margin và
overlap conflict policy là engineering hypotheses do project định nghĩa. Justification: dễ kiểm tra,
không phụ thuộc nhãn, cho phép abstention và so sánh cùng contract. Giới hạn: không calibrated,
sampling bias, unequal coverage, không semantic validation. Chi tiết và công thức: `assumptions.md`.
