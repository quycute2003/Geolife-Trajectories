# CP1 — Home / Office / POI inference

Cập nhật **2026-11-06**. Baseline offline và các lượt benchmark B1–B5 đã có kết quả đủ phạm vi.
Báo cáo hiện tại: [benchmark.md](benchmark.md). OpenAPI vẫn là bản thiết kế, chưa có HTTP server.

## Lựa chọn để tiếp tục

- **Cleaning:** giữ vote20 (`spatial_vote_context_v2`, 20 m), có provenance và ngắt segment khi
  timestamp conflict chưa giải quyết được.
- **Stay:** người dùng chọn **fixed-anchor 150 m/10 phút**, gap tối đa 5 phút. Giữ **100 m/10 phút**
  làm đối chứng. 150 m là lựa chọn có trade-off, **chưa phải winner qua các cổng xác nhận B4**.
- **Home/Office:** tiếp tục score hiện tại; rule theo số ngày ghé rồi dwell là đối chứng về
  mức trả kết quả/unknown. Grouping heuristic và DBSCAN vẫn được báo riêng.
- **Core/config/artifacts baseline 0.2.0 giữ nguyên 100 m/10 phút**. Lượt cập nhật báo cáo không
  đổi mặc định service/CLI, không mở final hoặc bắt đầu CP2. Slide để cập nhật riêng sau.

## Bài toán và luồng xử lý

`GPS UTC → cleaning → stays → gom địa điểm → temporal features/coverage → Home/Office/POI`

Home/Office là nhãn heuristic từ hành vi theo thời gian. Thiếu hoặc mâu thuẫn bằng chứng thì trả
`unknown`; evidence score không phải xác suất. GPS không tự cho biết chính xác một nơi là nhà
hay văn phòng. Không có semantic ground truth trên GeoLife để đo accuracy Home/Office.

## Kết quả và phạm vi chính

| Phần | Kết quả đã kiểm chứng |
|---|---|
| Dataset | **182 user / 18.670 trajectories**, 24.876.978 raw → **24.177.772 cleaned points** |
| Baseline parity | CLI DBSCAN và heuristic full-data khớp notebook; B5 100 m + score tái lập NB05 đủ 182 user |
| B2 tổng hợp | 81 source users selection, 66 exact-copy groups, **28.755 cases**, 71 kịch bản × 5 seeds |
| B3 cleaning | 6 policies đủ dataset; giữ vote20, không xếp hạng accuracy cleaning |
| B4 detector | **48 cấu hình tổng hợp**, **40 cấu hình GPS thật**; chưa mở lượt xác nhận cuối |
| B5 vai trò | 2 radii × 2 grouping × 2 rule × 2 role × 6 scenario × 182 user = **17.472 decision rows** |

Đáp án event chỉ có trên bộ tổng hợp theo thiết kế. B4 báo metric theo từng kịch bản, macro theo
user; số liệu GPS dùng chọn/khảo sát B4 chỉ lấy **81 user selection** dù job thực thi đủ 182.
B5 báo đủ **182 user**, sau khi người dùng đã chọn hai nhánh để so downstream.

## Bằng chứng cho lựa chọn stay

Tăng fixed-anchor 100→150 m ở dwell 10 phút giúp F1 stop tổng hợp 20–60 phút/outlier 30 m tăng
**0,411→0,536**, đồng thời FP/giờ chuyển động thuần tăng **0,025→0,074**, F1 hai stop gần nhau
75 m/2 phút giảm **0,705→0,436**. 150 m không thắng mọi tiêu chí.

ST-DBSCAN 150 m/10 phút, eps_time 300 giây/MinPts 3 có F1 cao ở một số ô tổng hợp nhưng trên
user 010 tạo event **9,06 giờ**, đầu–cuối cách **888,6 km**. Chaining và cách đổi cluster thành
stay chưa phù hợp ở bộ này. 9 bộ tham số ST đã khảo sát trên tổng hợp; 8 bộ phụ chưa chạy real.

## Home/Office: coverage và unknown

Kết quả **DBSCAN gom stays**, eps 100 m/MinPts 3; mỗi role có mẫu số **182 user**:

| Stay radius | Rule | Home predicted / unknown | Office predicted / unknown |
|---|---|---:|---:|
| 100 m | Score | 37 / 145 | 18 / 164 |
| 150 m | Score | **39 / 143** | **22 / 160** |
| 100 m | Đơn giản | 49 / 133 | 35 / 147 |
| 150 m | Đơn giản | 56 / 126 | 38 / 144 |

Ở 150 m, heuristic grouping + score cho **29 Home / 8 Office**; kết quả đủ mọi tổ hợp và lý do
unknown ở báo cáo chi tiết. Không dùng số predictions lớn hơn để kết luận thuật toán tốt hơn.

Với score, đổi 100→150 m giữ cùng nơi ≤200 m trên mọi user cả hai cùng predicted, gồm **34/34
Home** và **17/17 Office** ở DBSCAN. Vẫn có user mất/thêm prediction; agreement có điều kiện không
có nghĩa mọi user ổn định hoặc accuracy tăng. Toàn dataset có 10.339 baseline stays so với
**12.636 stays ở 150 m**; grouping DBSCAN tương ứng **552/692 địa điểm**, noise **3.296/4.398 stays**.

## Độ nhạy và giới hạn

- **Dịch giờ ±1:** 150 m + DBSCAN + score không đổi nơi >200 m trên nhóm cùng predicted; Home
  khi +1 giờ vẫn có **7 predicted→unknown và 6 unknown→predicted**. Rule đơn giản có Office đổi
  nơi **5/38 (13,2%)** ở DBSCAN. Score thận trọng hơn, chưa chứng minh chính xác hơn.
- **Timezone:** tra mọi GPS fix tìm **17 user affected**, không fallback. Nhánh 150 m + DBSCAN +
  score không đổi, nhưng rule đơn giản có user 142 đổi Home khoảng **8.700 km**. 13 user B1 là
  screening stay centers; 17 user B5 là screening mọi fixes, khác phạm vi.
- **Qua thời gian:** có 35 user đủ coverage Home, 53 Office qua hai khối 28 ngày; ở nhánh 150 m +
  DBSCAN + score chỉ **3 paired predictions mỗi role**, 2/3 giữ cùng nơi. Chưa kết luận ổn định dài hạn.
- Nhãn phương tiện yếu: baseline B4 có motor overlap macro **36,3%** trong phần có nhãn, vượt
  ngưỡng thiết kế 1%; không diễn giải đó là tỷ lệ toàn bộ stays sai. Final chưa sinh và gate runtime
  chưa xác nhận vì real timing trộn tuần tự/song song. Không đổi ngưỡng sau khi xem kết quả.
- Tổng hợp sạch/có kiểm soát hơn thực tế; GeoLife đã EDA, gaps không cho biết dwell, score không
  calibrated. **100 m/10 phút chưa được chứng minh tối ưu**, 150 m cũng chưa được chứng nhận tối ưu.

Ledger sau B5 **13,522/24 giờ**, có khoản reserve 3.600 giây khởi đầu. B5 main→plots khoảng
**8 phút 26 giây**, peak working set lấy mẫu **248,23 MiB**; đây không phải API latency benchmark.

## Tài liệu và tái lập

- [Benchmark B1–B5 và decision table](benchmark.md): số liệu, nguồn artifact, giới hạn và lịch sử.
- [Cleaning](cleaning_results.md), [protocol detector](detector_protocol.md), [protocol Home/Office](role_protocol.md).
- [Results lịch sử](results.md): các phase baseline/subset đã đóng, không trộn với kết quả mới.
- [Evaluation](../../docs/evaluation.md), [assumptions](../../docs/assumptions.md), [research notes](../../docs/research_notes.md).
- NB06–NB10 tương ứng B1–B5; outputs `artifacts/benchmark/` có audit, hashes và checkpoint.
- `openapi.yaml`: OpenAPI 3.1 draft, validation lịch sử 188 responses/examples; chưa triển khai HTTP,
  auth/resource guards, deployment hoặc load test. Kết quả POI baseline chưa được benchmark semantic mới.
