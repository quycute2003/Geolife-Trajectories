# CP1 B4 — phụ lục protocol trước chạy detector

Chuẩn bị 2026-11-05. Code và notebook được kiểm bằng dữ liệu giả; chưa có kết quả detector trên
corpus B2 hoặc GeoLife. Đây là phụ lục cho protocol B2 v1 đã khóa, theo các yêu cầu bổ sung trong
chat trước khi xem kết quả B4. Không sửa generator, nguồn/seed/truth hoặc artifacts B1–B3.

## Phạm vi và grid

Giữ cleaning vote20. Năm detector: fixed_anchor, median_updated, medoid_updated,
max_neighbor_updated, st_dbscan. Grid chung radius {50,100,150,200 m} × min dwell {10,20 phút},
đủ 40 tổ hợp. Fixed-anchor 100 m/10 phút là đối chứng hiện tại, vẫn neo tại fix đầu.
Các phương pháp đều dùng cùng observations, truth, cases/splits và max gap 300 giây.

ST-DBSCAN trong so chung giữ temporal eps 300 giây, MinPts 3 (gồm point đang xét). Khảo sát riêng
tại 100 m/10 phút dùng eps_time {60,180,300 giây} × MinPts {3,5,10}; một bộ gốc được tái dùng,
thêm 8 bộ, tổng 48 cấu hình định danh. Không thay ST-DBSCAN trên plot chung bằng bộ tốt hơn của
khảo sát riêng. Nghiên cứu phụ chỉ dùng selection tổng hợp, chưa chạy full-data/final cho 8 bộ phụ.

Radius là point-to-center bound ở bốn detector chuỗi; ở ST-DBSCAN nó là spatial neighborhood eps.
Chaining có thể tạo cluster rộng hơn 2×radius. Không tuyên bố cùng tham số là cùng hình học hoặc
đã tối ưu tham số riêng của từng thuật toán.

## Detector

Mọi detector nhận duy nhất arrays timestamp UTC, latitude/longitude và observation_segment.
Chạy từng synthetic case hoặc từng trajectory thật độc lập; tách khi segment đổi hoặc gap >300 giây.
Không đưa latent path, truth, noise scale, label phương tiện hoặc source ID vào detector.

- Fixed-anchor: kiểm khoảng cách từng point tới fix đầu, điểm vi phạm bắt đầu ứng viên mới.
  Tâm output là median lat/lon (longitude unwrap), như core 0.2.0, không phải point neo.
- Median-updated: thêm tạm point mới, tính median toàn prefix, yêu cầu mọi point cách median ≤R.
  Vi phạm thì phát prefix trước point mới nếu đủ dwell, rồi khởi tạo tại point mới.
- Medoid-updated: cùng quy tắc prefix, nhưng tâm là GPS fix có tổng haversine tới mọi point nhỏ
  nhất. Tie float64 chọn fix sớm nhất. Output dùng chính tọa độ medoid đã chấp nhận.
- Max-neighbor-updated: thử tâm tại các fix của prefix, tối đa hóa count trong R, hòa chọn fix
  sớm nhất; chỉ chấp nhận khi tâm tốt nhất phủ toàn prefix. Không cắt bỏ fixes ngoài bán kính.
  Vì thế tối ưu này tương đương chọn fix sớm nhất còn phủ được toàn prefix; các tâm đã fail không
  thể trở lại hợp lệ khi prefix dài thêm. Không phải tìm tâm tự do của vòng tròn hoặc subset nhiều nhất.
- ST-DBSCAN: neighborhood AND haversine ≤spatial eps và |Δtime|≤temporal eps. Core có ít nhất
  MinPts hàng xóm gồm self; expand theo thứ tự point, border thuộc cluster được tìm trước.
  Cluster → min/max timestamp và median tọa độ; bỏ cluster không đủ dwell. Giữ cả các event spans
  chồng nhau của các cluster để phép chấm bắt duplicate/merge/split, không dùng fixed-anchor lọc lại.

Các detector chuỗi là greedy, không tìm đoạn dài nhất toàn trajectory. Khi kết thúc segment/file,
ứng viên cuối cũng được xét dwell. Điểm đầu/cuối đã quan sát là endpoints, không bù GPS gap.
Median dùng bound tam giác để tránh scan khi chắc chắn trong R; medoid cộng dồn distance sums;
max-neighbor dùng tính đơn điệu của full-prefix coverage. Các tối ưu giữ đúng thuật toán đã định,
không lấy mẫu point hoặc approximate. Medoid vẫn O(n²) theo độ dài ứng viên, là rủi ro compute.

## Chấm tổng hợp và uncertainty

Truth giữ nguyên cả event không có observation. Matching one-to-one tối đa tổng temporal IoU,
IoU≥0,5 và tâm cách≤100 m. Ties trong 1e-12 tổng IoU chọn lexicographic truth/prediction index
(events đã có thứ tự thời gian xác định). Không đổi matching theo radius hoặc detector.
Graph split/merge dùng temporal overlap >0 và tâm≤100 m, không ngưỡng IoU. TP/FP/FN, zero/NA
theo B2: không prediction nhưng có truth → F1/recall 0; không positives → F1 NA, báo FP/giờ.

Gộp counts của 5 seed trong từng user/cell rồi tính event precision/recall/F1; macro theo user,
không theo point count. Lỗi start/end/tâm và temporal IoU lưu từ từng matched event; median/p95
theo user/cell. Bảng macro dùng median của user medians cho các cột *_median, mean của user p95
cho các cột *_p95; báo số user có giá trị, matched fraction và counts để hiểu missingness.
Không so median lỗi trên những user đã mất matching như thể đó là cải thiện.

Plot F1 có 95% bootstrap intervals, 1.000 resamples; gate (a) dùng 5.000 resamples, interval 97,5%
cho mỗi trong hai ô (family 95%). Seed 20261105. Bootstrap theo nhóm exact-copy đã khóa ở B2,
giữ các seed và user thuộc cùng nhóm đi cùng nhau; mỗi draw tính lại mean user có trọng số số user
trong nhóm. Không coi user/seed/source sao chép là quan sát độc lập.

Mỗi cấu hình chung có figure 4 nhóm dwell × 3 họ nhiễu, x là RMS (bao gồm stress); legend đủ 5
detector. Figure bổ sung cho dropout/two stops/negatives, FP/giờ riêng. Cell hoàn toàn unobservable
có bảng riêng. Khảo sát ST-DBSCAN có heatmap riêng; cadence tiers ≤5 giây, >5–30 giây, >30 giây.
Selection plots là exploratory; final chỉ so baseline với một ứng viên đã khóa, không có final
plots cho mọi ứng viên. Final không được dùng để sửa generator hoặc tuning.

## Dữ liệu thật, phủ định và ổn định

Chạy đủ 182 users/18.670 trajectories/24.177.772 cleaned points cho 40 cấu hình. Fixed-anchor
100 m/10 phút phải khớp saved baseline: file/start/end/point_count exact, coordinates atol 1e-9°.
Không chạy preprocessing/grouping/Home/Office ở B4. Stays và dwell thật không phải truth quality.

Nhãn 69 files GMT/UTC: union cùng mode, loại vùng chồng mode mâu thuẫn. r_motor mỗi user = tổng
stay duration overlap car/taxi/bus/train/subway / tổng duration overlap bất kỳ mode hợp lệ.
Tính theo event exposures (spans chồng nhau đóng góp riêng ở cả tử/mẫu); báo coverage/mẫu số.
Gate so trên user có mẫu số dương ở cả baseline và ứng viên, báo users mất mẫu số, không suy FN.

Độ ổn định ghép event trong cùng trajectory bằng cùng IoU/space gate; event Jaccard =matched /
(n_left+n_right−matched), không nhầm với median temporal IoU của matched events. Cặp r100→r50,
r100→r200 ở dwell10 là hai cạnh bắt buộc cho (c); common cohort cần ≥5 stays ở mọi đầu cạnh của
cả baseline và detector ứng viên, cùng tập user trên hai cạnh. Cạnh r150 và dwell20 báo mô tả.
Plateau: ≥80% eligible users có Δcount/Δdwell tuyệt đối tương đối≤10% và Jaccard≥0,8.
Nhánh ổn định là mức detector; không gắn bằng chứng này riêng cho một radius.

## Chọn và xác nhận

Áp dụng (a)–(d) trong bản chụp PLAN ở cả selection và final. Có 19 ứng viên mới duration10
(5 detector ×4 radius trừ baseline); duration20 và ST sweep chỉ khảo sát trade-off.
Hai ô (a): dwell [10,20) phút/15 m/drift và [20,60] phút/30 m/outlier; ΔF1≥0,03 và lower CI>0.
(b) dùng đủ từng ô, dung sai precision/recall/F1 0,02; lỗi endpoint +60 giây, tâm +10 m;
split/merge +0,02; negatives FP/h +0,05, pure move ≤0,1 và đủ quota. So lỗi chỉ khi cả hai có
matched events, ghi NA notes và matched fraction. Không gán NA thành đạt accuracy.
(c) r_motor≤1%, tăng≤0,1 điểm phần trăm; stability median Jaccard không giảm>0,05, tail count/
dwell đổi>50% không tăng>5 điểm phần trăm, ≥15 common users. Thiếu cohort là chưa xác nhận.
(d) runtime detector-only trên đúng source users của phần đang xét≤1,5×baseline; RAM trong cap,
job đủ scope và trần compute chung còn hợp lệ. Không dùng runtime B1/B3 gồm preprocessing làm chuẩn.

Nếu nhiều ứng viên qua selection: thứ tự đơn giản cố định fixed-anchor → median → medoid →
max-neighbor → ST-DBSCAN, rồi |radius−100| nhỏ hơn, runtime thấp hơn, config ID. Khóa một winner
và hash gates. Không có winner → giữ baseline và không sinh final. Mode descriptive đã biết từ
B2 cũng không chọn winner/mở final. Xác nhận thất bại không thử ứng viên thứ hai trên cùng final.
Real metrics/timing cho quyết định chỉ dùng đúng user nguồn selection/final tương ứng; không dùng
real final-user outputs để tuning. GeoLife đã EDA trước nên không tuyên bố test hoàn toàn sạch.

## Chạy, timing, checkpoint và giới hạn

NB09 độc lập, register lock trước job: hashes code B4, bản chụp PLAN/phụ lục, B2/B3 audits, profiles,
baseline stays và files nhãn. Sau register không sửa code; thay semantics cần version namespace mới.
Synthetic đọc corpus theo case, I/O dùng chung; real đọc cleaned theo trajectory một lượt cho mọi
config. Timing riêng lệnh detector, thứ tự gọi được xoay bằng hash case/trajectory; scoring/I/O
không cộng vào runtime ratio nhưng có trong ledger compute. Không suy timing Python implementation
thành tốc độ tối ưu lý thuyết của thuật toán. RAM ghi working set process dùng chung, không đo
allocation riêng từng thuật toán hoặc so RAM ratio.

Checkpoint sau từng user có file hashes. Chỉ RESUME=True mới đọc tiếp incomplete run với cùng
lock/code/input; completed checkpoint được giữ nguyên, user đang dở được tính lại. Mọi attempt
được cộng ledger, gồm failed attempts. Mỗi config tối đa 12 giờ detector compute tích lũy;
tổng wall compute B1–B4 và các stage mới vẫn≤24 giờ, RAM≤min(8 GiB,50% khả dụng đầu attempt).
Dừng khi chạm ngưỡng, ghi incomplete; không âm thầm giảm grid/users/cells hoặc approximate medoid.
Full grid chưa có runtime thực tế nên chưa hứa có thể xong trong ngân sách.

Tổng hợp sạch và có kiểm soát hơn GPS thật; stop latent cố định, thiếu đi lại trong cùng venue,
GNSS multipath thực và ngữ nghĩa ghé/chờ. Cùng radius ở ST-DBSCAN khác nghĩa hình học. Matching
tolerances là quyết định thiết kế. Không suy F1 tổng hợp thành accuracy GeoLife hoặc Home/Office.

## Nguồn

- [Zheng et al. (2009)](https://www.cl.cam.ac.uk/teaching/1718/R249/GPSZheng.pdf): fixed-anchor distance/time, dự án có adaptation đã ghi.
- [Birant & Kut (2007)](https://doi.org/10.1016/j.datak.2006.01.013): nguồn ST-DBSCAN; ở đây dùng hai chiều space/time, không tái lập toàn bộ xử lý thuộc tính/adjacent clusters của bài gốc.
- [Kato et al. (2024)](https://doi.org/10.1016/j.procs.2024.06.095): đánh giá stay detection theo logging interval, không chuyển kết quả dataset khác thành kết luận GeoLife.

## Phụ lục thực thi 2026-11-05 — 3 tiến trình theo user

Người dùng yêu cầu chuyển phần selection tổng hợp sang 3 tiến trình sau khi đã chạy tuần tự.
Lượt tuần tự đã Interrupt có audit và 14 user completed; giữ nguyên mọi file/hash checkpoint.
Đây là thay đổi cách lập lịch thực thi, không đổi detector, grid, corpus, matching hoặc luật chọn.
Không sửa các module v1 đã khóa. Module `benchmark_parallel.py` có execution lock/hash riêng gắn
với parent lock v1; bản protocol đã chụp lúc register vẫn giữ nguyên để truy vết thay đổi này.

Mỗi worker nhận một user độc lập, chạy đủ 48 tổ hợp và 5 seed/ô. Bộ chấm dùng nguyên module
evaluation v1; đã kiểm kết quả metrics và predictions khớp chính xác bản tuần tự trên fixtures.
Chỉ coordinator ghi audit/checkpoint, chỉ commit sau khi đủ ba file/user. Worker không ghi audit.
Checkpoint có thể đến không theo thứ tự ID; danh sách completed được chuẩn hóa theo ID.
User đang dở phải chạy lại khi resume, thời gian attempt cũ vẫn được giữ trong ledger.

RAM budget áp dụng tổng working set coordinator + các worker ≤min(8 GiB, nửa RAM khả dụng
đầu attempt), không nhân cap cho 3 worker. Trần 24 giờ giữ nghĩa wall time tích lũy; per-config
12 giờ cộng detector seconds của mọi worker/attempt. Chặn coordinator trùng bằng OS file lock,
heartbeat ghi trạng thái và counters, dừng hợp tác bằng stop request hoặc interrupt coordinator.

NB09 khởi động/nhận diện job nền, không cần giữ kernel notebook bận. `parallel.request_stop(OUT)`
yêu cầu dừng, giữ mọi user đã hoàn tất; nút Interrupt notebook không dừng job nền độc lập.
Không mở real/final khi selection còn incomplete. Final và lượt real vẫn dùng runner v1 tuần tự.

Timing selection có cả serial và parallel, lưu execution mode trong timing của các user mới và
danh sách user serial kế thừa trong audit. Không diễn giải chênh timing đó là lợi thế thuật toán.
Plot runtime selection chỉ mô tả thực thi, chịu CPU contention. Gate (d) vẫn dựa timing detector
trên cùng lượt real tuần tự, cùng cohort. Chưa suy tốc độ tăng gấp 3 khi chưa có số đo.

### Mở rộng capacity lên 10 — 2026-11-05

Sau khi user 026/027/028 đã hoàn tất, người dùng yêu cầu chuyển ngay lên 10 tiến trình.
Stop hợp tác lượt 3 worker, kiểm đủ 17 checkpoint/51 file rồi resume phần còn lại. Không chạy
lại user completed; các user đang dở được tính lại, thời gian cũ vẫn cộng ledger.
`benchmark_parallel_scaled.py` chỉ mở policy capacity 1–10 và gọi nguyên coordinator/worker
engine v1; có scaling policy/hash riêng tham chiếu execution lock cũ. Không sửa module v1,
truth, grid, detector, matching, seeds hoặc gates. Đã kiểm workload giả 10 user hoàn tất, hashes
output hợp lệ và source engine giữ nguyên. Chưa có kết quả benchmark completed trên toàn corpus.
Mọi quota 24 giờ/12 giờ mỗi cấu hình và RAM tổng vẫn giữ nguyên. Lượt mới đo lúc bắt đầu khoảng
1,18 GiB peak working set tổng, cap khoảng 1,90 GiB; đây không bảo đảm peak các user sau tương tự.
Timing selection vẫn chỉ mô tả do trộn serial/3/10 worker; gate (d) tiếp tục dùng real tuần tự.


## Phụ lục thực thi 2026-11-06 — dữ liệu thật chạy 10 tiến trình

Người dùng yêu cầu chuyển lượt real từ tuần tự sang song song, chọn mức cao nhất trong khoảng
5–10 tiến trình sau khi kiểm RAM. Dừng notebook bằng Interrupt sau 10 user completed (000–009),
giữ đủ 30 file/hash checkpoint. Thời gian đang dở vẫn được ghi vào attempt cũ, user đang dở chạy lại.

Module benchmark_real_parallel.py là lớp thực thi riêng với execution lock/hash mới gắn lock B4 gốc.
Không sửa detector, evaluation, jobs, generator hoặc các module v1 đã khóa. Cache pickle theo trajectory
được tạo từ đúng iterator cleaned CSV, giữ nguyên float64, row order và observation segments, không
thực hiện preprocessing. Một lượt đọc chuẩn bị đủ 182 user/18.670 trajectory/24.177.772 điểm. Cache
có hash từng user và kiểm quota; mọi thời gian chuẩn bị vẫn cộng ledger.

Kiểm parity trên fixture: metrics ngoài thời gian, events và stability edges khớp chính xác bản tuần tự.
Worker chạy đủ 40 cấu hình/user, chỉ coordinator ghi audit và commit checkpoint. OS lease chặn
coordinator trùng. Heartbeat mỗi giây hiển thị user active, PID worker, tổng RAM và compute.
Tiếp tục bằng RESUME, stop hợp tác bằng real_parallel.request_stop(OUT).

Probe tài nguyên trên trajectory lớn nhất (92.645 điểm) đo working set khoảng 121,6 MiB sau nạp
input/arrays/baseline/labels. Đây là probe nạp dữ liệu, chưa phải peak chạy đủ detector. Ước tính
10 worker cộng dự phòng 25% và coordinator khoảng 1.615,6 MiB, dưới soft cap dự kiến khoảng
1.913,6 MiB lúc đo; không bảo đảm mọi user có peak tương tự. Kiểm tra ngân sách áp dụng tổng
working set coordinator + worker; chạm cap thì dừng hợp tác, giữ checkpoint. Trần 24 giờ wall time
và 12 giờ/config cộng thời gian detector mọi worker/attempt giữ nguyên.

Thay đổi này làm thời gian real trộn tuần tự/song song và chịu CPU contention. Timing chỉ dùng mô tả,
không dùng trực tiếp cho cổng runtime (d) đã chốt theo lượt tuần tự. Audit ghi gate_d_timing_eligible=False.
NB09 chặn bước chọn winner bằng timing này; cần phép đo tuần tự có kiểm soát riêng nếu muốn xác nhận
cổng chi phí. Các bảng stay/dwell/motor/overlap và selection/final source filtering giữ nguyên.
Không tự mở final hoặc đổi baseline khi chuyển cách thực thi. Snapshot protocol đã khóa trước đây giữ nguyên.
