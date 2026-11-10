# Assumptions, algorithms và failure cases

## Trạng thái sau benchmark — 2026-11-06

Các công thức và mặc định core 0.2.0 dưới đây vẫn mô tả **baseline 100 m/10 phút**.
Người dùng chọn **fixed-anchor 150 m/10 phút** để tiếp tục và so downstream B5 với baseline;
cleaning vote20 và score Home/Office giữ nguyên. Lựa chọn không đồng nghĩa đã vượt cổng B4 hoặc
đã sửa default CLI/service. Grouping eps vẫn **100 m**, DBSCAN MinPts **3**; không đổi theo stay radius.

B4 đã so 48 cấu hình tổng hợp và 40 trên GPS thật; B5 đủ 182 user. Chi tiết và giới hạn:
[benchmark](../reports/cp1/benchmark.md), [evaluation](evaluation.md).

- Cả 100/150 m đều là engineering assumptions: 150 m chịu outlier tốt hơn nhưng có FP/merge cao hơn.
  **100 m/10 phút chưa được chứng minh tối ưu**; 150 m cũng chưa được chứng nhận tối ưu.
- ST-DBSCAN spatial eps giới hạn neighborhood, không giới hạn toàn cluster; bộ 150 m/300 giây/3
  đã tạo event nối dài 9,06 giờ/888,6 km. Không dùng F1 cao ở vài ô tổng hợp để bỏ qua failure này.
- Score phức tạp không tự là xác suất/tốt hơn rule đơn giản. B5 cho thấy khác biệt lớn về abstention;
  agreement trên nhóm cùng predicted không xác minh độ đúng hoặc ổn định trên mọi user.
- Mặc định timezone core vẫn Asia/Shanghai. **B5 ablation** tra zone mọi GPS fix và cluster center,
  IANA offset lịch sử, không chọn zone đa số của user. Gán valid pair theo fix trái là giả định tối
  đa 5 phút; polygon hiện tại không xác minh biên zone lịch sử/giờ sinh hoạt tại mọi vùng.
- Core Home/Office không có semantic ground truth. F1/precision/recall B4 chỉ được chấm trên
  đáp án event tổng hợp, không chuyển thành accuracy role trên GeoLife thật.

## Thời gian và dữ liệu

- GeoLife date/time được hiểu là UTC theo User Guide 1.3. Không dùng timezone của máy.
- Timezone hành vi mặc định `Asia/Shanghai`, có config và warning trong mọi result.
  Không tự xác định timezone bằng GPS. Với travel ngoài zone, phải chạy lại với lựa chọn thích hợp.
- Altitude feet → meters bằng 0.3048; -777 → missing. Altitude không tham gia inference.
- Invalid rows bị loại, exact duplicates theo user/trajectory/time/lat/lon bị loại.
  Altitude không thuộc duplicate key. Core 0.2.0 dùng spatial/context voting như NB02,
  không còn chọn lat/lon nhỏ nhất; threshold mặc định 20 m, có config.
- Khoảng thời gian giữa hai điểm hợp lệ liên tiếp cùng trajectory/observation_segment <= max gap được coi là observed interval.
  Invalid rows bị loại có thể để lại interval ngắn đủ điều kiện; không chứng minh quan sát liên tục.
- Tốc độ >100 m/s được cảnh báo, **không xóa**, vì có nhiều phương tiện và sampling artifacts.

## Stay detection

Điểm đầu là anchor cố định. Duyệt từng điểm: nếu khoảng cách tới anchor >100m,
gap tới điểm trước >5min, hoặc timestamp không tăng, đóng candidate ở điểm trước rồi
bắt đầu candidate mới tại điểm hiện tại. Chỉ xuất stay có duration >=10min và ít nhất hai
timestamps khác nhau. Flush candidate cuối trajectory. Không dùng timestamp của điểm đã rời vùng
làm end time. Representative là median latitude/circular-unwrapped longitude.

Các điểm có thể cách nhau tới 2 lần bán kính anchor; ngưỡng không phải pairwise diameter.
Rule reset có thể bỏ lỡ stay bắt đầu giữa candidate ngắn; jitter/outlier có thể cắt stay.
Slow walking hoặc tắc đường có thể thỏa rule. Không suy người đó ở trong một tòa nhà.
Gaps làm giảm recall nhưng không được cộng thành dwell hàng giờ.

Nếu stay từ các trajectory files cùng user chồng thời gian: giữ event có start sớm nhất
(tie: trajectory ID), loại toàn bộ event sau bị overlap và đếm audit. Bảo thủ, có thể mất
phần hợp lệ cuối event. Không khẳng định user ở hai nơi cùng lúc. Events chỉ chạm boundary vẫn hợp lệ.

## Grouping

- `heuristic-v1`: sort stays theo start/trajectory; gán vào anchor gần nhất trong eps=100m,
  tie theo thứ tự tạo. Nếu không có, tạo anchor mới. Anchor là representative của stay đầu,
  không di chuyển; không density threshold, không noise. Phụ thuộc thứ tự và có thể chia một nơi.
- `dbscan-v1`: cluster stay representatives mỗi user độc lập, coordinates `[lat,lon]`
  radians, eps=100/EarthRadius, min_samples=3 kể cả chính stay. Noise giữ -1 trong CSV và diagnostics.
  Ba stays không đồng nghĩa ba ngày độc lập; inference còn yêu cầu recurrence theo ngày.
  Density connectivity có thể kéo dài cluster; báo max/p95 distance từ cluster representative,
  warning khi max radius >2*eps. Cluster IDs không ổn định qua model/config khác.
- Cluster representative dùng median; radius là khoảng cách stay centers, không bao trọn mọi GPS point.

## Temporal features và coverage

Stays là half-open intervals `[start,end)`. Union overlapping/touching intervals trong cùng cluster
để không double count. Mỗi union interval là một observed visit episode; không nối gaps.
Một lần ghé thật có thể bị chia thành nhiều episodes. Do đó recurrence chủ yếu dùng distinct days,
không dùng số GPS points. Một stay qua nửa đêm có thể đóng góp hai calendar dates.

Night = [22:00,24:00) + [00:00,06:00) mỗi local date; work = [09:00,18:00) Mon–Fri.
Tính elapsed minutes giao với từng cửa sổ, không gán toàn stay theo giờ bắt đầu.
Week là ISO year-week. Chuyển boundary về UTC trước khi trừ để tính DST elapsed time.
Không mô hình hóa ngày lễ, lịch ca đêm hoặc travel timezone tự động.

Coverage = union các adjacent-point intervals đủ sampling gap, gồm cả khi đang di chuyển.
Observed days đếm ngày có GPS point; observed role days đếm ngày có positive observed-window overlap.
Day fraction = observed days / inclusive calendar span; time fraction = observed minutes /
elapsed minutes từ điểm đầu tới cuối. Không phải xác suất logger hoạt động hoặc coverage trong nhà.

## Score và abstention

Với mỗi role, `D`=role dwell, `N`=role days, `O`=user observed role days, `T`=user observed minutes,
`S`=D/tổng role dwell ở tất cả non-noise clusters (0 nếu mẫu số 0):

`score = .30*min(N/5,1) + .25*min(D/600,1) + .20*min(N/max(O,1),1) + .15*min(T/1440,1) + .10*S`.

Weights/scales do project đề xuất, chưa học hoặc calibrated. Relative share bỏ noise nên có thể
quá lạc quan khi noise lớn; luôn xem noise proportion và alternatives.
Role phải có >=3 ngày, >=60 role minutes; Office thêm >=2 ISO weeks có work-window overlap.
Chọn eligible candidate có score cao nhất, chỉ predict nếu score >=.5, share >=.5 và score hơn
mọi competitor ít nhất .05. Competitor có thể chưa đủ eligibility. Nếu không đạt, `unknown`
với reason và tối đa ba alternatives. Các min ngưỡng là config; ambiguity margin .05 là baseline constant.

Home/Office được chọn độc lập, có thể trùng. Work-from-home được hỗ trợ về cấu trúc nhưng không
được xác nhận từ GPS. POIs là clusters còn lại có >=3 distinct dates, tối đa 10, xếp days rồi dwell.
Night-shift, multiple homes, travel hoặc sparse logging có thể khiến role sai/unknown.
Không báo Accuracy/Precision/Recall/F1; score chỉ mô tả bằng chứng dưới các giả định này.

## Policy thử nghiệm mới trong NB02

Theo yêu cầu ngày 2026-11-02, NB02 không dùng lexicographic tie-break cho timestamp conflicts nữa.
Notebook scan mọi conflict group trên toàn dataset và tính maximum pairwise Haversine separation.
Sau khi người dùng chọn ngưỡng từ phân phối, nhóm trong ngưỡng gộp mean lat/lon (longitude unwrap qua ±180°),
nhóm vượt ngưỡng chọn tập đông nhất mà mọi pair nằm trong ngưỡng. Nếu hòa, dùng các timestamps
không-conflict trong cùng trajectory ±max_gap_minutes; mỗi context fix bỏ phiếu cho duy nhất cụm gần nhất
nằm trong ngưỡng. Nếu vẫn hòa/không có phiếu thì giữ riêng toàn timestamp và ngắt observation segment.
Điểm ngoài cụm thắng cũng được giữ riêng để review, nhưng không ngắt segment khi timestamp đã có winner.
Exact duplicate positions chỉ góp một trọng số; altitude mean bỏ missing, all-missing giữ NaN.
NB02 mặc định ngưỡng chưa chọn (None) ở bản đầu; người dùng đã chọn 20 m và chạy toàn dataset.
Core/CLI 0.2.0 mặc định 20 m trong `conflict_merge_threshold_m`, có thể cấu hình lại sau khi review.

Counts tách invalid/exact duplicate removals, rows absorbed into means và unresolved rows.
Mỗi điểm gộp có source_point_count, ID đại diện và provenance; mean không có nghĩa là tọa độ ground truth.
Core preprocessing được gọi sau khi notebook đã xử lý conflicts và phải không còn drop conflict nào.
Core/CLI 0.2.0 đã đồng bộ policy này. Invalid/exact duplicates ở removed_points; mọi distinct conflict fix
ở conflict_points, có group ID/spread/decision/output ID. `conflicting_timestamps_removed` chỉ còn là alias
legacy của merged_extra_points + unresolved_conflict_rows, không dùng nó để gọi mean contributors là deleted.

## NB05 — coverage và suy luận từ kết quả notebook

NB05 dùng assignments/clusters NB04 đã được tạo từ preprocessing voting và các observation segments.
Coverage phải đọc mọi cleaned GPS points, gồm khi di chuyển/người không có stay; không lấy stay days
làm observed days. Chỉ ghép adjacent pairs cùng trajectory/segment với 0 < gap <= max gap.
Các pairs nối tiếp được nén thành interval runs trước khi union across files, giữ nguyên elapsed time
và các boundary theo khung giờ; không nội suy qua unresolved conflicts. Core observation_coverage
đã đồng bộ việc ngắt theo observation_segment. Đường CLI/raw 0.2.0 dùng cùng voting policy với notebook.

Cache coverage khóa theo input fingerprints, timezone/max gap/night/work windows và policy version;
audit kiểm tra số points/trajectories ở từng user khớp NB02. Đổi ngưỡng quyết định không đổi coverage.
Điểm và quyết định Home/Office vẫn dùng cùng baseline weights/rules ở trên; `role_candidates` chỉ
trả thêm toàn bộ bảng ứng viên cho notebook xem, không thay tie-break hoặc abstention.
`share_including_noise` là diagnostic trên role dwell trong tất cả stays, không tự thay relative_share.
User không có cluster vẫn có hàng unknown; POIs có thể chứa ứng viên Home/Office chưa được chọn.
Map chỉ đặt H/O/H+O/P ở cluster đã được chọn, không đặt marker cho unknown.
NB05 đã được người dùng chạy toàn dataset (37 Home / 18 Office cho DBSCAN), nhưng chưa có nhãn thật
để đo accuracy. Core/CLI 0.2.0 đã được kiểm tra parity synthetic cả hai models; CLI DBSCAN full-data và heuristic
full-data (B1) đều đã khớp saved outputs NB02–05 trong float tolerance. B5 100 m + score tiếp tục
parity với NB05 đủ 182 user; đây là parity implementation, không phải accuracy Home/Office.
