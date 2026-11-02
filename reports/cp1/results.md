# CP1 experimental results — 2026-10-31

## Cập nhật 2026-11-02 — preprocessing toàn dataset

Người dùng đã chạy NB02 với `spatial_vote_context_v2`, ngưỡng 20m. Audit xác nhận completed,
đủ **182 users / 18.670 trajectories**, không lấy mẫu:

| Outcome | Rows |
|---|---:|
| Input | 24.876.978 |
| Cleaned output | 24.177.772 |
| Invalid removed | 1 |
| Exact duplicates removed | 146.914 |
| Extra rows absorbed into means | 551.156 |
| Conflict points separated for review | 1.135 |

Counts cân bằng ở toàn dataset và mọi user. Có 157.865 conflict groups, 157.560 groups được giải quyết,
305 groups vẫn chưa giải quyết. Trong 1.135 points tách riêng, 384 points nằm ngoài cụm được ưu tiên;
751 points còn lại thuộc các groups chưa phân biệt được. 135 groups được giải quyết bằng context vote.
Giữ 39.806 long gaps và 51.686 high-speed pairs dưới dạng diagnostics, không tự xóa points vì tốc độ.

Rule ưu tiên cụm đông nhất có mọi pair trong ngưỡng; nếu hòa, dùng context không-conflict trong cùng
trajectory ±max_gap_minutes. Nếu vẫn hòa thì giữ riêng. Đây là heuristic, chưa có ground truth xác nhận fixes.
Các đoạn quan sát phải được tôn trọng ở bước stay detection; chưa chạy notebook 03.

Các kết quả **inference/sensitivity bên dưới là thực nghiệm subset trước đây**, không phải đánh giá
Home/Office trên toàn dataset. Core/CLI raw còn dùng baseline conflict policy cũ; NB02 giải quyết conflicts
trước khi gọi core preprocessing. Không có HTTP endpoints hoặc mentor approval được khẳng định.

## Scope và provenance

Python 3.11.4, Windows 11 x64; dependencies trong `uv.lock`.
Dataset ZIP được người dùng cung cấp. SHA256:
`1107c5ac064d0a23c8d021a8736a77e53abc75b227062e6260342c6a8d86bdb6`.
Kiểm tra CRC toàn ZIP bằng `ZipFile.testzip()` trả `None` (không có bad member).
Inventory thật: **182 users, 18.670 PLT, 24.876.978 nonblank data lines, 69 label files**.
Không đồng nghĩa đã parse/validate toàn bộ GPS values. User Guide 1.3 version table khớp PLT/line counts;
introductory count và transportation-label count của guide không khớp bản ZIP.

EDA/inference chỉ dùng users 000, 001, 002 và sparse user 049, tổng **533.308 input records**.
Hai model baseline và sáu thay đổi tham số = **32 actual runs**.
Không ground truth; không Accuracy/F1, không tuyên bố prediction đúng.

## EDA subset

| User | Trajectories | Input points | Observed dates / span days | Median sampling s | Gaps >5min | Segments >100m/s | Observed-time fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000 | 171 | 173.870 | 123 / 256 | 5 | 653 | 14 | 4,12% |
| 001 | 71 | 108.607 | 44 / 54 | 4 | 206 | 13 | 9,14% |
| 002 | 175 | 248.217 | 118 / 151 | 5 | 566 | 67 | 7,62% |
| 049 | 1 | 2.614 | 2 / 2 | 5 | 2 | 0 | 88,57% |

User 049 có khoảng 231,25 observed minutes trên elapsed span 261,08 phút qua hai local dates.
Hai gaps bị loại khỏi observed time; day coverage 2/2 không phải lịch sử đầy đủ nhiều ngày.
Ba users đầu không có invalid coordinates/timestamps trong subset.
User 002 có một invalid altitude và ba conflicting equal timestamps bị loại.
Không exact duplicate records trong subset. High-speed segments được giữ để không xóa nhầm transport;
đặc biệt tốc độ cực đại lớn có thể là noise, cần review và rule riêng nếu muốn lọc.
Sampling p95=5s ở ba users đầu; gaps hàng giờ vẫn tồn tại. Không gán gap thành dwell.

## Baseline comparison

| User | Stays | DBSCAN clusters | DBSCAN noise | Heuristic groups | Home | Office | DBSCAN other POIs |
|---|---:|---:|---:|---:|---|---|---:|
| 000 | 120 | 9 | 44,17% | 52 | candidate | unknown: insufficient evidence | 5 |
| 001 | 44 | 5 | 40,91% | 19 | candidate | unknown: insufficient evidence | 2 |
| 002 | 188 | 6 | 18,62% | 39 | candidate | unknown: ambiguous candidates | 4 |
| 049 | 0 | 0 | 0% convention | 0 | unknown | unknown | 0 |

Heuristic giữ mọi stay trong group nên noise=0 theo định nghĩa; không phải bằng chứng tốt hơn DBSCAN.
Cả hai baseline cho cùng Home/Office statuses ở bốn users; không khẳng định clusters trùng nhau hoàn toàn.
DBSCAN max cluster-center radius lần lượt khoảng 59,3m / 89,4m / 138,0m ở users 000–002.
Cluster radius không bao trọn tất cả raw fixes. Không có overlapping stay events bị loại ở baseline subset.

Trong mẫu bốn users: Home candidate rate=3/4 (75%), Home unknown=1/4 (25%),
Office candidate=0/4, Office unknown=4/4 (100%). Không suy rộng tới 182 users.

## Evidence check và visual review

Đã mở/xem bốn DBSCAN baseline PNG offline, sau khi sửa local focus để travel không làm nén
toàn bộ cụm chính. Reviewer: trợ lý, kiểm tra hình học/temporal diagnostics; chưa có reviewer độc lập.

- User 000: overview có hai vùng quan sát cách xa nhau. Local focus tách được nhiều clusters.
  Home candidate chỉ có **3 night dates** trên 123 observed dates, 261,28 night minutes,
  score **0,522** (sát cutoff). Đây là ứng viên yếu, cần review, không xác nhận nơi ở.
  Office alternative tốt nhất có 4 work dates nhưng 59,65 work minutes, dưới min 60.
- User 001: overview chủ yếu là mạng đường di chuyển; Home có 3 night dates,
  374,42 night minutes, score 0,609. Office có tối đa 2 work dates trong alternative tốt nhất,
  chưa qua recurrence gate. Hình học không cung cấp semantic label.
- User 002: overview có tuyến di chuyển dài và vùng quan sát xa cluster chính. Home candidate
  có 16 night dates, 578,53 night minutes, score 0,873. Office eligible candidate có relative share
  khoảng 0,338; một cluster khác chiếm nhiều work dwell nhưng không đủ office-week recurrence.
  `unknown` tránh ép lựa chọn; không xác định travel hay nơi làm việc thật bằng prediction.
- User 049: overview là một đường di chuyển kéo dài; zero stays và unknown là kết quả quan sát được,
  không có kết luận rằng người dùng không có nhà/nơi làm việc.

Chưa tạo semantic proxy labels. Maps không có basemap/business information; visual review chỉ kiểm tra
geographical plausibility, travel, gaps và hỗ trợ abstention, không đo accuracy.
Artifacts tọa độ, event CSV, role alternatives và review template giữ local trong `artifacts/evaluation/`.

## Parameter sensitivity (DBSCAN)

| Setting | User 000 stays / clusters / Home | User 001 stays / clusters / Home | User 002 stays / clusters / Home |
|---|---|---|---|
| Baseline | 120 / 9 / candidate | 44 / 5 / candidate | 188 / 6 / candidate |
| Stay radius 50m | 69 / 5 / unknown | 26 / 3 / candidate | 102 / 4 / candidate |
| Stay radius 200m | 185 / 12 / candidate | 69 / 6 / candidate | 254 / 11 / candidate |
| Stay duration 20min | 35 / 2 / unknown | 19 / 2 / candidate | 49 / 3 / candidate |
| Max gap 1min | 72 / 6 / unknown | 29 / 3 / candidate | 110 / 5 / candidate |
| DBSCAN eps 200m | 120 / 8 / candidate | 44 / 4 / candidate | 188 / 6 / candidate |
| DBSCAN min_samples 5 | 120 / 5 / candidate | 44 / 3 / candidate | 188 / 5 / candidate |

Office unknown ở mọi setting và sparse user zero stays ở mọi setting.
User 000 thiếu ổn định với stay/gap thresholds. Không chọn settings theo số prediction nhiều nhất.
Bán kính lớn hơn giữ nhiều stays hơn nhưng có thể nhận nhầm slow movement; cần đánh giá độc lập.
Eps lớn hơn có thể gộp density chains; không bảo đảm điểm đo cải thiện.

## Timing và limitations

Baseline pipeline processing time đo một lần/user/model, không gồm ZIP loading/plotting:
DBSCAN khoảng 3,90s / 2,06s / 5,14s / 0,05s; heuristic khoảng 4,16s / 1,95s / 5,24s / 0,04s.
Không lặp benchmark, không đo server latency hoặc sync/async; số đo không chứng minh model nhanh hơn.

Chưa inference toàn dataset; sample không đại diện mọi mobility pattern. Coverage thiếu, timezone assumption,
gaps, night shifts, nhiều nơi ở, slow movement, jitter và greedy resets có thể gây lỗi.
Điểm score và tham số chưa calibrated/optimized. OpenAPI limits chỉ đề xuất, chưa được load test hoặc enforce.
Mentor approval và independent semantic review vẫn đang chờ.
