# CP1 — kết quả và lịch sử thực nghiệm

## Kết quả hiện tại — 2026-11-06

B1–B5 đã có outputs completed theo phạm vi công bố. Đọc [báo cáo benchmark](benchmark.md) cho
số liệu mới, decision table, audits và giới hạn; [summary.md](summary.md) là bản tóm tắt để trình bày.

- Giữ cleaning vote20. Người dùng chọn fixed-anchor **150 m/10 phút** để tiếp tục và giữ
  **100 m/10 phút** làm đối chứng; score Home/Office hiện tại được giữ cùng rule đơn giản để so sánh.
- B4: 48 cấu hình trên tổng hợp, 40 trên GPS thật. Bảng khảo sát B4 dùng 81 source users selection;
  không có winner xác nhận, final chưa sinh/mở, runtime real lẫn tuần tự/song song chỉ mô tả.
- B5: đủ 182 users, 17.472 decision rows, baseline score parity với NB05. Với grouping DBSCAN,
  150 m + score cho **39 Home/143 unknown**, **22 Office/160 unknown**; 100 m + score là 37/145 và 18/164.
  Agreement cao trên nhóm cùng predicted không xác nhận accuracy hoặc ổn định dài hạn.
- Heuristic CLI 0.2.0 đã chạy đủ dataset và parity trong B1; câu “chưa chạy” ở nhật ký dưới là
  trạng thái lịch sử. Gán nhãn thủ công đã bỏ ngày 2026-11-04; các worksheet cũ chỉ là artifacts
  lịch sử, không có vai trò reference/evaluation hiện tại.
- Core/config/artifacts baseline chưa đổi mặc định 100 m/10 phút; chưa triển khai service hoặc CP2.
  Báo cáo được cập nhật, slide chưa thay đổi.

## Nhật ký đã đóng

Các số liệu, test counts và trạng thái dưới đây giữ nguyên theo ngày ghi. Các mục subset không
đại diện toàn dataset. Khi khác trạng thái hiện tại, dùng phần cập nhật ngày 2026-11-06 và báo cáo
benchmark; không lấy các câu “chưa chạy” trong nhật ký làm kết luận hiện tại.

# CP1 experimental results — 2026-10-31

## Cập nhật 2026-11-03 — CLI DBSCAN 0.2.0 khớp NB02–05 toàn dataset

Người dùng đã chạy standalone CLI với config baseline và --audit-points; run-audit ghi completed/full_dataset,
đủ 182 users / 18.670 trajectories. Đối chiếu **mọi users và mọi saved records**, không chạy lại GPS/inference:

| Mục | CLI và notebook |
|---|---:|
| Raw → cleaned points | 24.876.978 → 24.177.772 |
| Stays | 10.339 |
| DBSCAN locations / noise stays | 552 / 3.296 |
| Home predicted / unknown users | 37 / 145 |
| Office predicted / unknown users | 18 / 164 |
| POIs, cộng mọi users | 202 |
| Distinct conflict fixes trong trace | 709.851 |
| Invalid/exact-duplicate removed rows | 146.915 |

Không có sai khác ngoài float tolerance ở các per-user preprocessing counters, stay intervals/positions/
durations/counts, toàn bộ per-stay cluster/noise labels, mọi coverage và location feature fields,
Home/Office status/reason/candidate/components/alternatives và ordered POIs.
Tolerance rtol=1e-10, atol=1e-8; sai lệch số thực lớn nhất quan sát được khoảng 8,9755e-9.
Point traces khớp GPS/time/decision/spread; removed rows khớp theo multiset nội dung/reason.
Record IDs không so trực tiếp vì NB02 gán toàn dataset còn CLI gán theo lượt đọc từng user.

Report có fingerprints và phạm vi: `artifacts/pipeline/dbscan-v1/notebook-comparison.json` (gitignored).
Schema validation: 182 responses CLI thực + 6 contract examples = 188 lượt pass.
Đây là **kiểm tra tương đương implementation**, không đo accuracy hoặc xác nhận Home/Office thực tế.
CLI heuristic 0.2.0 chưa chạy lại; heuristic notebook đã có kết quả full-data. Manual-review CSV lịch sử
có 130 hàng nhưng 0 proxy labels/reviewers/notes đã điền. Đã chuẩn bị worksheet mới 32 dòng cho 8 users
từ kết quả full-data; cột reviewer vẫn để trống, nên chưa có manual semantic evaluation.

## Cập nhật 2026-11-02 — grouping toàn stays và map (NB04)

Người dùng đã chạy NB04. Audit `completed/full_dataset`, fingerprints input khớp, cùng 10.339 stays
ở cả hai phương pháp, thống kê đủ 182 users:

| Phương pháp | Địa điểm | Stays được gom | Noise stays |
|---|---:|---:|---:|
| Heuristic, radius 100 m | 3.577 | 10.339 | 0 |
| DBSCAN, eps 100 m / min_samples 3 | 552 | 7.043 | 3.296 |

Theo yêu cầu xem map, xuất một HTML tương tác từ CSV có sẵn, không chạy lại grouping.
Map giữ toàn bộ input, có bộ chọn mọi user/toàn bộ và hai phương pháp cạnh nhau, zoom, noise/extent,
popup stay/cluster. Chưa dùng các counts này để kết luận phương pháp nào chính xác hơn.
Phần trên ghi kết quả Home/Office toàn dataset mới nhất; các dòng này ghi lại bước review grouping trước đó.

## Cập nhật 2026-11-02 — stay detection toàn dataset (NB03)

Người dùng đã chạy NB03, audit `completed/full_dataset`. Đọc audit và CSV xác nhận đủ
182 users / 18.670 trajectories / 24.177.772 cleaned points, không lấy mẫu.
Baseline anchor 100 m / 10 phút / max gap 5 phút, tôn trọng observation_segment:

- 10.339 stays của 151 users; 31 users không có stay đạt rule.
- 0 stays chồng thời gian; 215.579,967 phút = 3.592,999 giờ trong stays.
- 2.595.092 cleaned points thuộc stays, khoảng 10,7334% input; không phải tỷ lệ thời gian đứng yên.

Sensitivity cũng đã được người dùng chạy trên toàn bộ 24.177.772 points mỗi cấu hình:

| Cấu hình (radius m / duration phút) | Stays | Giờ trong stays | Overlap |
|---|---:|---:|---:|
| Baseline 100 / 10 | 10.339 | 3.592,999 | 0 |
| 50 / 10 | 6.024 | 2.068,508 | 0 |
| 200 / 10 | 14.371 | 5.188,689 | 0 |
| 100 / 5 | 27.605 | 5.569,005 | 0 |
| 100 / 20 | 3.174 | 1.959,505 | 0 |

Đã trao đổi kết quả và người dùng cho phép chuyển phase. Nhiều stays hơn không chứng minh tốt hơn;
100 m / 10 phút vẫn là baseline, chưa tối ưu bằng nhãn độc lập. Tạo NB04 so heuristic/DBSCAN trên
cùng toàn bộ stays của baseline, với recurrence/dispersion/noise. Kết quả NB04 mới nhất ở phần trên;
kết quả Home/Office mới nhất ở phần CLI/NB05 phía trên.

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
Các đoạn quan sát được tôn trọng ở bước stay detection NB03; kết quả mới nhất ở phần trên.

Các kết quả **inference/sensitivity bên dưới là thực nghiệm subset trước đây**, không phải đánh giá
Home/Office trên toàn dataset. Core/CLI raw 0.1.0 lúc đó còn dùng baseline conflict policy cũ; NB02 giải quyết conflicts
trước khi gọi core preprocessing. Không có HTTP endpoints trong phạm vi CP1.

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
Independent semantic review chưa có; không có nhãn ground truth để đo accuracy.
