# Assumptions, algorithms và failure cases

## Thời gian và dữ liệu

- GeoLife date/time được hiểu là UTC theo User Guide 1.3. Không dùng timezone của máy.
- Timezone hành vi mặc định `Asia/Shanghai`, có config và warning trong mọi result.
  Không tự xác định timezone bằng GPS. Với travel ngoài zone, phải chạy lại với lựa chọn thích hợp.
- Altitude feet → meters bằng 0.3048; -777 → missing. Altitude không tham gia inference.
- Invalid rows bị loại, exact duplicates theo user/trajectory/time/lat/lon bị loại.
  Altitude không thuộc duplicate key. Equal timestamps khác tọa độ giữ lat/lon nhỏ nhất
  theo thứ tự từ điển, ghi audit. Đây là quyết định deterministic, không khẳng định điểm giữ lại đúng.
- Khoảng thời gian giữa hai điểm hợp lệ liên tiếp <= max gap được coi là observed interval.
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
nhóm vượt ngưỡng được cách ly khỏi cleaned output và lưu toàn bộ distinct input fixes để review.
Các nhóm cách ly làm ngắt observation segment để tránh coi khoảng giữa hai đầu là stationary evidence.
Exact duplicate positions chỉ góp một trọng số; altitude mean bỏ missing, all-missing giữ NaN.
Ngưỡng mặc định None, chưa có kết quả full-data scan/cleaning được khẳng định trong lần sửa này.

Counts tách invalid/exact duplicate removals, rows absorbed into means và unresolved rows.
Mỗi điểm gộp có source_point_count, ID đại diện và provenance; mean không có nghĩa là tọa độ ground truth.
Core preprocessing được gọi sau khi notebook đã xử lý conflicts và phải không còn drop conflict nào.
Core/CLI đọc raw vẫn dùng policy baseline cũ được mô tả ở trên; chỉ đồng bộ sau khi policy/ngưỡng được chốt.
