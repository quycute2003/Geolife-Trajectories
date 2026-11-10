# Kế hoạch 6 tuần — Home / Office / POI Inference

Kế hoạch chính của dự án. Cập nhật checkbox và kết quả kiểm chứng sau từng phase.
Ngày bắt đầu: 2026-10-31. Ngôn ngữ: Python 3.11+, dùng `py` trên Windows.

**Ưu tiên hiện tại (2026-11-04): bổ sung benchmark CP1 trước CP2.** Baseline offline đã
hoàn thành về triển khai; chưa chứng minh thuật toán/ngưỡng hiện tại là lựa chọn tốt nhất.
Phần “Bổ sung CP1 — benchmark và lựa chọn có bằng chứng” bên dưới là kế hoạch đang theo.
B1 đã bắt đầu bằng kiểm kê saved outputs và chuẩn bị NB06; chưa chạy scan GeoLife mới hoặc thay thuật toán.

## Hướng làm hiện tại — notebook trước, đi từng bước

**Cập nhật theo yêu cầu người dùng ngày 2026-10-31:** tiến độ triển khai vừa qua quá nhanh
so với mục tiêu học và hiểu dữ liệu. Chuyển sang quy trình khám phá có giải thích, chart
và nhận xét trong Jupyter notebook. Các checkbox baseline phía dưới ghi lại việc đã chạy,
không có nghĩa người dùng đã hiểu, review hoặc chấp nhận các quyết định đó.

Code, reports và OpenAPI hiện có được giữ làm bản thử để tham khảo; không coi các ngưỡng,
cleaning rules hay kết quả suy luận là đã chốt. Bắt đầu lại bằng notebook khám phá dữ liệu gốc.

### Cách làm việc

- **Quy tắc phạm vi mới nhất:** mọi phân tích/xử lý từ đây mặc định chạy toàn bộ dataset. Không tự giới hạn 1–3 users hoặc lấy mẫu points. Có thể xử lý theo từng trajectory/user để tiết kiệm RAM nhưng phải bao phủ đủ tất cả rồi tổng hợp. Các kết quả subset trước đây chỉ là lịch sử.
- **Lượt cập nhật hiện tại (2026-11-03):** người dùng đã chạy CLI 0.2.0 DBSCAN đủ 182 users / 18.670 files; saved outputs khớp NB02–05 trong float tolerance. Đã tạo worksheet review 32 dòng/8 trường hợp và báo cáo CP1; OpenAPI đã validate 188 examples/responses để người dùng trình bày trực tiếp. Heuristic CLI mới chưa chạy lại; chưa triển khai HTTP API.
- Mỗi notebook chia cell ngắn: mục đích → code → bảng/chart → nhận xét. Theo yêu cầu mới nhất, không có phần quiz/tự kiểm tra hoặc yêu cầu người dùng điền câu trả lời.
- Giải thích ý nghĩa của chart, đơn vị, mẫu số và phạm vi dữ liệu đang xem.
- Phân biệt dữ liệu raw/parsed với dữ liệu sau cleaning; không dùng output đã làm sạch làm raw baseline.
- Thống kê vấn đề trước, nêu lý do chọn rule rồi mới áp dụng. Không tự động xóa high-speed points.
- Giữ thứ tự: hiểu dữ liệu → cleaning và so sánh → stays → grouping/inference → API design.
- Kết thúc từng notebook bằng các phát hiện, điều còn chưa chắc và lựa chọn cần thảo luận.
- Dừng để cùng người dùng đọc kết quả trước khi chuyển chặng; không tự triển khai toàn bộ các notebook một lượt.
- Synthetic fixtures chỉ phục vụ unit tests; không dùng làm kết quả dataset. Kết quả phân tích phải nêu số users/trajectories/rows thực tế đã xử lý và xác nhận đủ phạm vi.
- Notebook chạy từ môi trường riêng qua `py`; chỉ có một bản làm việc trong `notebooks/`, kết quả ở các thư mục `artifacts/` theo bước (overview, preprocessing, stays, locations, inference). Không tự commit/push dữ liệu lên GitHub.
- Mốc tuần là thứ tự học dự kiến, không ép chạy kịp lịch bằng cách bỏ qua phần chưa hiểu.
- Ghi rõ phần nào đã chạy, kết quả và giới hạn thực tế; trao đổi khi cần làm rõ quyết định, không kiểm tra kiến thức người dùng trong notebook.
- Mỗi quyết định ghi ngắn: đang giải quyết vấn đề gì, lựa chọn nào được thử, bằng chứng nào ủng hộ,
  rủi ro nào còn lại. Giải thích input → thao tác → output ngắn gọn ngay cạnh phần xử lý.

## Bổ sung CP1 — benchmark và lựa chọn có bằng chứng

Không ước lượng giờ công; tiến độ theo bước và dependency; trần compute 24 giờ giữ nguyên.

### Quyết định phương pháp — 2026-11-04

**Bỏ hoàn toàn gán nhãn thủ công (annotation) và reference tay.** Không khả thi về công;
một người đọc cùng trace GPS mà detector sử dụng chỉ đo mức khớp với cách đọc trace, không
đo đúng/sai thực tế. Quyết định này thay thế thiết kế đánh giá tay trước đó. Benchmark mới
chỉ có đáp án thật trong thế giới tổng hợp đã sinh; không suy đáp án đó thành sự thật trên GeoLife.

**Mục tiêu trước CP2:** so detector/ngưỡng bằng đáp án tổng hợp; đo độ nhạy trên dữ liệu thật;
audit cleaning; kiểm tra phủ định bằng nhãn phương tiện và ổn định Home/Office.
Giữ baseline khi bằng chứng chưa phân biệt được lựa chọn. Chưa triển khai HTTP/Docker/AWS.

### Phạm vi, tiến độ giữ nguyên và sản phẩm

- Giữ core 0.2.0/config/artifacts làm baseline, không ghi đè outputs/settings/ghi chú NB01–05.
- **Tiến độ đã ghi nhận ngày 2026-11-04:** kiểm kê đủ **182 users**, **69 label files**;
  top 5 chiếm **25,80%** raw points, user 153 chiếm **8,67%**. DBSCAN CLI full-data đã đối chiếu
  saved outputs, **difference_count = 0**. B1 scan và heuristic CLI 0.2.0 đã chạy đủ full-data;
  parity CLI/notebook xác nhận đủ 182 users, 10.339 stays.
- Đã tạo NB06 và report; cell scan ban đầu mặc định `RUN_B1_SCAN=False`, hiện setting lưu là `True`
  sau lượt chạy. Profile scan, labels, nguồn di chuyển và resource audit đã được đọc; không chạy lại
  cell scan. B2 preparation và corpus selection trong NB07 đã completed, kiểm tra đủ scope/hash; B3 đã completed/kiểm tra; B4–B6 chưa triển khai.
- Inventory/diagnostics và các cấu hình thật được chọn chạy phải bao phủ toàn dataset theo manifest;
  xử lý tuần tự để tiết kiệm RAM. Tận dụng kết quả cũ khi cùng input/config. Không âm thầm lấy
  vài user/points rồi gọi là full-data. Bộ tổng hợp có cohort nguồn riêng, công bố mọi user đủ/không đủ.
- B1 dùng `notebooks/06_cp1_benchmark.ipynb`; B2 tách riêng sang
  `notebooks/07_cp1_b2_synthetic.ipynb`; B3 dùng `notebooks/08_cp1_b3_cleaning.ipynb`. Kết quả ở `artifacts/benchmark/`,
  báo cáo `reports/cp1/benchmark.md`; không tạo các bản notebook hoặc helper trùng nhau.
  Assistant chuẩn bị nội dung; người dùng chủ động chạy các job full-data và cùng đọc kết quả.
- **Trần compute tích lũy: 24 giờ**, gồm CLI còn thiếu và mọi job benchmark mới; tái dùng cache
  chỉ khi provenance khớp. Mỗi cấu hình tối đa 12 giờ; RAM mục tiêu ≤min(8 GiB, 50% RAM khả dụng
  lúc bắt đầu). B1 dự toán trước chạy, ghi rõ timing có/không tính I/O và cách đo RAM.
  Vượt budget thì ghi incomplete, giữ baseline và nêu phần chưa kiểm chứng; không bỏ ca khó để thắng.
- Theo yêu cầu cập nhật ngày 2026-11-05, B4 dùng **8 cấu hình chung × 5 detector = 40 tổ hợp**.
  Mỗi cấu hình chạy đủ mọi thuật toán, cùng cases/splits/seeds và metrics. B3 tối đa 6 cleaning;
  Khảo sát tham số ST-DBSCAN riêng có 9 bộ, gồm 1 bộ trùng grid chung nên thêm tối đa 8 tổ hợp.
  B4 tối đa 48 tổ hợp định danh, B3+B4 tối đa 54 tổ hợp; không nhân cleaning với mọi detector.
  Trần compute 24 giờ và RAM giữ nguyên. Nếu không đủ budget thì báo incomplete và danh sách job
  chưa chạy, không âm thầm bỏ thuật toán/cấu hình hoặc tuyên bố đã so đầy đủ. Timing kiểm tra trên
  cùng workload; tái dùng cache chỉ khi provenance khớp. Chưa có số đo bảo đảm đủ quỹ cho toàn grid.
- Các số quota, seed, mức nhiễu và tiêu chí đổi cấu hình dưới đây là **quyết định thiết kế**,
  phải khóa trong protocol trước xem kết quả kiểm tra cuối; không phải hằng số tối ưu từ paper.
  Không tick công việc mới khi mới viết code, chưa có đủ audit/kết quả.

### Truy vết nhận xét mentor

Đối chiếu với ghi chú cuộc họp **2026-11-03** người dùng gửi trong chat; cột xử lý là cách dự án
thực hiện, không phải lời mentor nguyên văn. **Người dùng tự quyết định hướng đi và triển khai;
nhận xét mentor chỉ là thông tin tham khảo.**

| Nhận xét/rủi ro | Bước xử lý và bằng chứng |
|---|---|
| Local time cần thư viện để xử lý an toàn | B1 rà IANA/DST và vùng chưa xác định; B5 timezone ablation |
| Không bỏ timestamp trùng, chỉ xóa khi mọi trường giống nhau | B1 phân loại duplicates/altitude/conflicts; B3 counts, provenance và stay-diff |
| Xem lại detector, neo và so với thuật toán khác | B2 generator độc lập detector; B4 so fixed-anchor, median-updated và ST-DBSCAN đối chứng |
| User chiếm nhiều dữ liệu có thể gây bias | B1 profile mọi user; B4 kết quả theo user/tầng, không lấy point count làm trọng số chất lượng |
| Tránh leakage; chọn mẫu sau preprocess | B2 tách user nền/seed, dùng profile sau cleaning theo từng phần; cấm chọn bằng kết quả kiểm tra cuối |
| Rule/ngày làm việc cần benchmark, dịch giờ và xem theo thời gian | B5 baseline đơn giản, unknown, dịch ±1 giờ; lịch lễ/qua năm chỉ mở rộng nếu đủ dữ liệu |
| Assumptions chưa rõ phải thử nghiệm | B2 ma trận nhiễu/gaps; B4 plateau và hard negatives; B6 decision table |
| Nhãn phương tiện giúp tìm stay trong hành trình | B4 kiểm tra phủ định trên 69 user có file nhãn, báo coverage và giới hạn bằng chứng yếu |

### B1 — Kiểm kê, parity và profile nguồn cho generator

- [x] Kiểm kê audits/config/version/fingerprints và bảng mọi user: raw/cleaned points, tỷ trọng,
  trajectories, stays, observed days/time union, coverage đêm/làm việc và nhãn phương tiện.
  Dùng saved outputs trước, chỉ quét mới phần thiếu. Không thay số tiến độ đã đo.
- [x] Chạy **heuristic-v1 CLI full-data** vào output riêng, đối chiếu NB02–05 và per-user counts.
  10.339/10.339 stays và role outputs khớp trong dung sai số thực. Lượt đo riêng ghi whole-run
  timing/RAM; audit gốc không ghi input fingerprint hoặc runtime theo stage/user. Không gọi kết quả
  notebook là kết quả CLI hoặc dùng runtime preprocessing thay runtime detector.
- [x] Kiểm kê toàn bộ **69 label files**: số dòng, modes, intervals/gaps/overlap và quy ước timestamp.
  Giữ nhóm thiếu/nhãn mâu thuẫn riêng; số user có motorized labels hợp lệ có thể nhỏ hơn 69.
- [x] Tạo **profile theo user** từ dữ liệu đã preprocess: phân bố chu kỳ lấy mẫu dương, độ dài/run
  gaps, biến động sampling theo trajectory/ngày, tỷ lệ missing altitude và nhảy tọa độ.
  Giữ cả chuỗi sampling/gap blocks để generator tái lấy mẫu theo block, không chỉ lấy dt trung bình.
- [x] Ước lượng proxy nhiễu từ residual sau local smoothing trên các đoạn tốc độ/heading tương đối
  ổn định, kèm giả định và contamination bởi chuyển động thật. Không gọi residual là GPS error truth;
  không lấy bán kính stay detector làm profile nhiễu. Báo quantiles và user không đủ dữ liệu ước lượng.
- [x] Chuẩn bị nguồn đoạn di chuyển sau cleaning: ưu tiên interval nhãn phương tiện, kiểm tra speed;
  hoặc đoạn ≥10 phút có ≥90% valid pair speed ≥2 m/s và không run speed<0,5 m/s dài >30 giây.
  Chỉ dùng pairs cùng trajectory/segment, 0 < gap ≤5 phút. Đây là filter nguồn, không phải nhãn stop thật;
  báo số đoạn/user/modes và lý do loại. Chốt danh sách nguồn trước khi chạy detector trên tổng hợp.
- [x] Diagnostics gaps toàn dataset: số gaps và union giờ theo ngưỡng 5/15/60 phút; trừ phần được
  files khác cùng user quan sát để không đếm missing giả. Báo unobserved-support hours /
  (observed union hours + unobserved-support hours) trong support giữa first–last fixes từng trajectory.
  Không tính thời gian không có support giữa files; **không gọi missing hours là dwell bị mất**.
- [x] Rà duplicate mọi trường có ý nghĩa so với key hiện tại bỏ altitude; xem conflicts/vote bị phình
  do lặp và timestamps trùng xuyên files. Có 14 duplicate rows khác altitude; không thấy file overlap
  giữa các trajectory cùng user. Giữ trace, không tự gộp xuyên trajectory hoặc sửa policy.
- [x] Rà UTC → IANA timezone → local time tại ngày quan sát bằng thư viện, trên toàn bộ stay centers;
  DST, user qua nhiều vùng, vùng biên/không tra được zone và fallback. Có 13 users với stay ngoài
  Asia/Shanghai; 346/10.339 stay starts đổi giờ/ngày theo zone tại vị trí. Đưa ý nghĩa “local time”
  sang quyết định B5; không mặc định Asia/Shanghai đúng mọi vị trí. Profile sampling/gaps dùng UTC.
- [x] Đo runtime/RAM whole-run CLI và lập feasibility snapshot: 864,70 giây, peak working set
  1,47 GiB; ngưỡng lúc chạy là 551 MiB (RAM khả dụng đầu lượt 1,156 GB), nên vượt mục tiêu mềm 2,72×.
  Profile scan đạt 137,18 giây / 279 MiB. Generator/grid chưa chạy, vì vậy chưa có runtime thực tế;
  ghi rõ phạm vi chưa đo trong feasibility table, giữ trần compute 24 giờ.

**Tiêu chí xong:** inventory/provenance mọi user, profile có audit và mẫu số, nguồn di chuyển đã
liệt kê, heuristic parity có kết quả, và feasibility snapshot ghi cả giới hạn RAM cùng công việc
chưa đo. B1 audit/profile đã hoàn tất; 14 altitude-only duplicates chuyển sang B3, timezone ablation
chuyển sang B5. Không coi việc này là benchmark chất lượng detector.

### B2 — Protocol và generator có đáp án tổng hợp

**Chuẩn bị ngày 2026-11-05:** protocol chi tiết ở `reports/cp1/benchmark_protocol.md`, generator
ở `src/geolife_inference/benchmark_synthetic.py`, NB07 mục 1–4 có hai job chủ động chạy.
Preparation GeoLife đã completed ngày 2026-11-05: đủ 24.177.772 points/18.670 trajectories,
19.892 nguồn đã audit; 19.460 nguồn hợp lệ, 162 users chia 81/81. Selection corpus đã completed
và kiểm tra ngày 2026-11-05: 81 users, 28.755 cases, 36.183.328 observations, 29.565 truth events;
162 output hashes khớp. Final chưa sinh theo protocol. Phụ lục B4 mới cần khóa trước chạy detector.
Protocol B2 v1 khóa ST-DBSCAN ban đầu ở eps spatial 100 m, eps time 300 giây, MinPts 3, dwell
10 phút; phụ lục B4 theo yêu cầu mới mở rộng đủ grid chung, giữ eps_time/MinPts cố định.
Ma trận triển khai gồm 36 ô chính + 35 ô stress/bổ sung, 5 seed/user/ô; quota và toàn bộ cohort
phải được xác nhận bằng audit completed trước khi chốt B2. Dwell/cadence/noise chi tiết theo protocol.

- [ ] Chốt mục tiêu: **sự kiện stop được chèn vào hành trình tổng hợp**, có tâm/start/end trong latent
  path và manifest đáp án trước tạo nhiễu. Không suy nhãn Home/Office từ các stop này. Đo riêng
  đèn đỏ/nghẽn đường như dừng trong hành trình; GPS giống hệt nhau có thể không phân biệt được
  chờ xe và ghé địa điểm, nên không tuyên bố giải được ngữ nghĩa chỉ từ hình học.
- [ ] Chèn stop tại vị trí trên đoạn di chuyển thật đã chọn ở B1: giữ latent position trong duration
  biết trước, nối lại hành trình với tọa độ liên tục, dời phần timestamp phía sau theo thời gian chèn.
  Lấy sampling cadence và gaps theo block từ **chính user nguồn**. Giữ source IDs, tọa độ/timestamp
  trước/sau biến đổi và event manifest; không tạo teleport hoặc ngầm lấp gaps.
- [ ] Chỉ phần được generator kiểm soát trạng thái mới có đáp án: nền di chuyển được resample theo
  latent path có tiến triển dương; đoạn thật còn nghi có dừng không tự coi là negative truth.
  Bộ tổng hợp là nguồn duy nhất có đáp án biết trước; nhãn phương tiện thật không thay đáp án đó.
- [ ] **Không sinh stop bằng logic detector:** không gọi detector để chọn/giữ ca, không ràng buộc
  mọi point trong bán kính 50/100/200 m, không reset theo anchor hoặc cắt nhiễu cho baseline thắng.
  Stop state/endpoints có trước quá trình đo; raw observations có thể trôi xa tâm hoặc bị mất hoàn toàn.
- [ ] **Ma trận chính 36 ô:** 4 nhóm duration **[3,10), [10,20), [20,60], >60 phút** × 3 mức
  nhiễu mục tiêu **5/15/30 m RMS** × 3 họ nhiễu **Gaussian, drift chậm/random walk, outlier**.
  Duration >60 phút giới hạn 180 phút cho budget; quét cả lân cận các mốc 5/10/20/60, ghi duration thật.
  Gaussian dùng hai trục độc lập; drift/random walk có tương quan theo thời gian; outlier dùng mixture
  với 1%/5% fixes lỗi lớn (offset đuôi dài 3–10 lần scale), không chỉ Gaussian quanh một tâm.
  Scale theo RMS kỳ vọng của quá trình trước rút seed, không normalize/cắt từng event sau sinh để
  ép vào bán kính. Báo empirical RMS/quantiles/tương quan thực sinh và mọi sai lệch so mức mục tiêu;
  không giả ba họ có cùng phân phối dù cùng scale.
- [ ] Biện minh 5/15/30 m bằng proxy profile B1 và literature assumptions đã ghi nguồn khi triển khai;
  quét đủ cả ba mức ở mọi detector. Nếu quantiles nguồn nằm ngoài dải thì bổ sung stress scale trước
  khóa protocol và dự toán lại; không chọn mức sau khi nhìn baseline để làm nó thắng.
- [ ] **Các nhóm bổ sung bắt buộc, báo riêng:** dropout giữa stop theo block gaps của user và stress
  mất liên tục 25%/50% duration; hai stop có tâm cách 25/75/150 m, giữa chúng có chuyển động và
  khoảng cách thời gian 2/10 phút; hard negatives đi chậm, đèn đỏ 1–3 phút, kẹt xe dạng creeping và
  di chuyển thuần. Không chèn sự kiện stop mục tiêu vào hard negatives; công bố latent state/progress.
  Đèn đỏ có thể dừng vật lý ngắn nhưng không phải lần ghé được chèn; không đổi tên nó để né FP.
  Ca mất hết quan sát vẫn giữ trong bảng theo khả năng quan sát, không loại để tăng điểm.
- [ ] Khóa danh sách ô phụ và quota trước chạy: tối thiểu 5 seed/ô/user nguồn đủ điều kiện;
  mọi ô phải có ≥10 user nguồn độc lập ở mỗi phần chọn cấu hình/kiểm tra cuối. Nếu không đủ thì
  báo thiếu bằng chứng và giữ baseline; không giả nhiều seed là nhiều user độc lập.
  Không nhân chéo toàn bộ modifiers nếu vượt compute; ghi tổ hợp thực chạy và ô chưa có kết quả.
- [ ] **Tách nguồn và seed:** seed chia user `20261104`, chia 50/50 user nguồn đủ điều kiện;
  user có trajectory/sự kiện sao chép phải cùng một phần. Seed sinh chọn cấu hình từ `100000+i`,
  seed kiểm tra cuối từ `200000+i` (i=0..4 cho mỗi ô/user), dùng SHA256 của ID ô/user và seed để
  tạo stream riêng ổn định giữa các lần chạy, không dùng built-in hash phụ thuộc session.
  Không dùng profile riêng hoặc nền của user kiểm tra để chọn cấu hình; profile riêng của họ chỉ để
  sinh phép kiểm tra đã khóa. Mọi scale chung/thiết kế chỉ chọn bằng phần chọn cấu hình.
  Công khai GeoLife đã EDA toàn bộ nên tách nguồn này không xóa kiến thức trước đó.
- [ ] **Kiểm tra quy mô cohort trước khóa protocol và trước xem kết quả detector mới:** sau chia
  50/50, lập bảng cho từng nửa: số user nguồn; số có nhãn phương tiện hợp lệ/có mẫu số phủ định;
  số có ≥5 stays theo baseline đã lưu; giao của các nhóm trên. Ghi cả IDs và mẫu số, không chỉ tổng.
  Nếu đã có saved outputs tương thích ở các đầu cạnh radius thì đếm thêm cohort chung ≥5 stays
  tại hai đầu; chưa có thì ghi unknown, không chạy/xem detector mới chỉ để chọn lại phép chia.
  Baseline count chỉ là kiểm tra điều kiện cần/giới hạn trên cho cohort ổn định, không bảo đảm
  ứng viên sẽ có đủ stays hoặc coverage nhãn sau chạy.
  Nhánh phủ định (c) dùng user có nhãn/mẫu số dương; nhánh ổn định (c) cần ≥15 user chung đủ stays.
  Báo cả giao hai nhánh để thể hiện độ phủ; không ngầm coi toàn 69 user có nhãn đều thuộc mỗi nửa.
  Nếu baseline đã cho thấy cohort ổn định không thể đủ 15, hoặc phần phủ định không có mẫu số,
  ghi trước **“(c) sẽ chưa xác nhận được do thiếu cohort”**. Nếu bảng đã ghi cảnh báo này do
  **bất kỳ nhánh nào** (phủ định hoặc ổn định, ở phần chọn hay phần kiểm tra cuối) thiếu cohort,
  B4 chuyển sang **chế độ mô tả**: vẫn chạy ma trận tổng hợp trên phần khảo sát đã định, độ nhạy
  thật và phủ định, báo số kèm mẫu số; **không chọn ứng viên, không chạy lượt xác nhận cuối**.
  Quyết định là giữ baseline, ghi rõ thiếu cohort ở nhánh nào và việc bỏ lượt xác nhận; không kết
  luận ứng viên kém. Compute tiết kiệm được ưu tiên cho các tổ hợp grid còn thiếu trên full-data
  nếu còn quỹ 24 giờ sau các việc bắt buộc còn áp dụng. Không coi job đã bỏ là còn phải giữ ngân sách.
  Nếu bound trước chạy **chưa kết luận được**, giữ quy trình chọn/xác nhận hiện tại và kiểm tra
  cohort sau chạy, không hứa đủ. Không đổi seed/chia lại, hạ quota hoặc xem kiểm tra cuối để vượt điều kiện.
- [ ] **Matching chốt trước:** one-to-one, temporal IoU ≥0,5 và khoảng cách tâm ≤100 m;
  tối đa tổng IoU rồi tie-break bằng event ID. Matching trên timestamps latent tuyệt đối;
  intervals [start,end), không bù gap. Tâm prediction lấy đại diện do detector xuất, truth là tâm latent.
  TP = matched, FP = unmatched predictions, FN = unmatched inserted events; F1 = 2TP/(2TP+FP+FN).
  Precision khi không predictions và F1 khi không positives/predictions là NA, không tự gán 1.
  Có positives nhưng không prediction thì recall/F1 = 0. Hard negatives không có positives:
  đo FP/giờ, không tính F1 giả tạo.
- [ ] **Đối chứng ST-DBSCAN để phát hiện stay:** áp dụng lên GPS thô để gom điểm thành các stay
  event, không phải gom các stay đã phát hiện thành địa điểm ghé lặp lại như bước grouping hiện tại.
  Ghi rõ đây là time-space density clustering theo Birant & Kut (2007), khác detector chuỗi
  fixed-anchor. Khóa trước cách ánh xạ cấu hình sang không gian và thời gian
  (`eps_spatial`, `eps_time`, `MinPts`), xử lý theo từng user/trajectory/observation_segment,
  không nối qua max-gap hoặc unresolved boundaries; chuyển cluster thành event bằng min/max timestamp
  và median tọa độ, rồi áp dụng dwell tối thiểu chung. Bản protocol B2 đã khóa một bộ tham số
  ban đầu; phụ lục B4 trước chạy detector sẽ mở rộng radius/duration theo đủ 8 cấu hình chung.
  Trong so sánh chung, giữ eps_time =300 giây và MinPts =3 ở mọi cấu hình; eps_spatial =radius cấu hình và lọc cluster
  bằng duration tương ứng. Đây là adaptation dự án, không gọi là default hay optimum của paper.
  eps_spatial chỉ ràng buộc lân cận; chaining có thể làm đường kính cluster >2×radius, khác với
  kiểm tra mọi point quanh một tâm. Báo khác biệt semantics này khi so sánh cùng giá trị radius.
- [ ] **Metrics từng ô, không gộp một số:** precision/recall/event F1, lỗi start/end/tâm (median/p95
  trên matched events, kèm matched fraction), split/merge từ temporal overlap graph và spatial gate
  cố định, FP/giờ trên đoạn di chuyển thuần. Nối cạnh graph nếu overlap >0 và tâm cách ≤100 m;
  truth có ≥2 prediction neighbors là split, prediction có ≥2 truth neighbors là merge.
  Tỷ lệ split tính trên truth events, merge trên predicted events; báo cả counts và mẫu số.
  FP/giờ dùng tổng giờ latent moving đã biết của từng user, báo thêm observed exposure để hiểu dropout.
  Tổng hợp macro theo user trong mỗi ô và báo phân phối/tầng profile; không lấy raw point count làm trọng số.
- [ ] Đóng băng protocol/grid, input/profile/generator/code hashes, seed manifest và bảng đáp án
  trước tuning. Kiểm thử tính liên tục, timestamps/endpoints và các họ nhiễu bằng invariants của
  generator, không dùng kết quả detector làm điều kiện generator đúng. Trong quy trình chọn/xác nhận,
  chỉ mở kết quả kiểm tra cuối một lần cho một ứng viên đã chọn; sửa sau khi xem thì kết quả đó
  không còn là kiểm tra xác nhận. Chế độ mô tả không chạy/mở lượt xác nhận và không chọn ứng viên.

**Tiêu chí xong:** generator tái lập theo seed, đáp án độc lập detector, manifest nguồn tách biệt,
ma trận/quota/matching/metrics và các ngưỡng B4 đã khóa; bảng đếm cohort từng nửa kèm khả năng
xác nhận (c), đủ nguồn và dự toán nằm trong budget. Thiếu cohort không được ghi thành đã đạt (c).

### B3 — Cleaning: counts, provenance và stay-diff toàn dataset

**Hoàn tất và đọc kết quả ngày 2026-11-05:** NB08 chạy đủ sáu policy trên 182 users,
18.670 trajectories/24.876.978 raw points; vote20 parity đủ 182 users và 1.110 output hashes khớp.
Báo cáo `reports/cp1/cleaning_results.md`; quyết định giữ vote20. Tác động toàn dataset nhỏ nhưng
no_merge làm user 141 mất cả 7 stays, nên báo cả per-user. Job ~65 phút 19 giây, peak ~465 MiB.
Sau run sửa riêng warning concat empty frames thành revision v1.1, không đổi outputs/audit v1.

- [x] Tối đa **6 cấu hình**: vote10/vote20/vote50, mean20, no-merge và một contrast duplicate.
  Các nhánh conflict giữ cùng invalid/duplicate policy; mean20 chỉ mean khi mọi cặp ≤20 m,
  nhóm xa tách riêng không context vote; no-merge tách mọi timestamp đa vị trí và ngắt segment.
  Contrast duplicate chỉ đổi key mọi trường nguồn có ý nghĩa, giữ vote20; no-op nếu không có khác biệt.
- [x] Ghi counts input/output/invalid/duplicates/merged/tách riêng, vote/context, segment boundaries
  và source IDs; kiểm tra count invariants mọi user. Không giữ hai fixes cùng giờ gây speed vô hạn;
  altitude khác nhau cần policy có provenance, không tự lấy tùy ý một giá trị.
- [x] Giữ detector/config/grouping/role rules cố định; chạy đủ trajectory/user bị ảnh hưởng, gộp
  phần không đổi từ cache với manifest chứng minh đủ 182 user. So stays bằng thời gian/provenance
  fixes nguồn, không dùng local segment/cluster IDs làm định danh xuyên runs.
- [x] Báo unchanged/changed start/end/tâm/membership/dwell, lost/new, split/merge theo overlap graph,
  số user đổi và tổng dwell delta. Chốt tolerances số thực và graph trước chạy; không ép split/merge
  thành ghép one-to-one. Không thêm bộ đánh giá tay.
- [x] **Không chọn winner cleaning bằng F1. Giữ vote20**, trừ khi audit phát hiện lỗi cụ thể có thể
  tái hiện (sai count, mất provenance, xử lý duplicate/context sai quy tắc). Khi đó sửa lỗi, tăng
  version khi semantics đổi và kiểm tra lại; counts ít/nhiều hơn không tự chứng minh tọa độ đúng.
  Conflicts chỉ chiếm phần nhỏ dữ liệu: có thể ít stays đổi; điều đó không chứng minh 20 m tối ưu.

**Tiêu chí xong:** audit đủ toàn dataset, bảng stay-diff và provenance tái lập được, quyết định giữ
vote20 hoặc hồ sơ lỗi cụ thể; chưa có kết quả thì không chọn policy bằng cảm giác.

### B4 — Detector: tổng hợp, độ nhạy thật và kiểm tra phủ định

**Chuẩn bị ngày 2026-11-05:** notebook độc lập `notebooks/09_cp1_b4_detectors.ipynb`,
phụ lục khóa trước chạy `reports/cp1/detector_protocol.md` và bộ chạy/chấm/plot đã có.
Đã kiểm bằng dữ liệu giả: thuật toán, baseline parity, matching, nhãn mâu thuẫn, checkpoint/resume,
grid và các figure; đây chưa phải kết quả B4 trên corpus B2 hoặc GeoLife. NB09 mặc định chạy
selection tổng hợp trước; lượt dữ liệu thật và xác nhận cuối tắt. Không tick các mục kết quả dưới đây.

**Điều chỉnh thực thi ngày 2026-11-05:** theo yêu cầu người dùng, chuyển selection tổng hợp sang
3 tiến trình theo user bằng `benchmark_parallel.py`; giữ checkpoint serial và lock v1, execution
lock riêng chỉ cho cách chạy. NB09 chạy/quan sát job nền, không đổi corpus/grid/thuật toán/chấm.
Timing tổng hợp lẫn serial/parallel chỉ mô tả; gate (d) tiếp tục dùng timing real tuần tự.
RAM là tổng coordinator + workers, trần compute không nhân theo số worker. B4 chưa hoàn tất.

**Cùng ngày, mở rộng lên 10 theo yêu cầu người dùng:** sau khi 026/027/028 completed, giữ đủ
17 user/51 file checkpoint và resume bằng `benchmark_parallel_scaled.py`. Scaling policy/hash
riêng, dùng nguyên engine v1; không sửa thuật toán hoặc phép chấm. Trần compute/RAM giữ nguyên,
NB09 và bảng theo dõi đọc 10 worker. Chưa có kết quả B4 đủ scope để đánh dấu hoàn tất.

- [ ] So năm cách phát hiện: (1) fixed-anchor baseline theo stay-point distance/time của Zheng et al. (2009),
  (2) tâm median cập nhật có giới hạn độ phân tán, (3) ST-DBSCAN đối chứng theo cấu hình đã khóa
  ở B2, (4) medoid-updated và (5) max-neighbor-updated theo đặc tả bổ sung dưới đây. Code fixed-anchor hiện giữ quy tắc khoảng cách từ điểm neo và thời lượng, nhưng dùng median
  tọa độ đại diện thay vì mean, đồng thời reset theo max-gap/observation segments và loại event chồng
  thời gian; ghi rõ đây là adaptation, không tuyên bố tái lập nguyên bản. Median-updated là biến thể
  cần kiểm tra, không gán là thuật toán đã công bố. Với median-updated, khởi tạo ứng viên ở fix đầu;
  sau mỗi fix mới, tính lại median lat/lon của toàn ứng viên (longitude unwrap), rồi kiểm tra khoảng
  cách haversine từ **mọi fix ứng viên** tới median đó. Nếu có fix nào vượt radius, kết thúc ứng viên
  trước fix vi phạm; phát event nếu đạt dwell tối thiểu, rồi khởi tạo ứng viên mới tại fix vi phạm.
  Gap/segment boundary cũng kết thúc ứng viên. Không tìm tâm vòng tròn chứa nhiều điểm nhất, không
  bỏ qua outlier để giữ ứng viên và không kéo event qua fix vi phạm. ST-DBSCAN dùng raw points theo
  B2, không nhầm với DBSCAN gom các stay đã phát hiện.
  Kiểm tra reset/neo, jitter, đi chậm, gaps/segments và cuối trajectory. Giữ cleaning/grouping/role
  rules cố định để không lẫn tác động.
- [ ] **Bổ sung theo yêu cầu ngày 2026-11-05, trước khi xem kết quả detector:** thêm hai đối chứng
  riêng; fixed-anchor vẫn chọn fix đầu, không đổi baseline. Cả hai chạy đủ grid radius/duration
  chung, max gap 5 phút; dùng cùng cases/matching/metrics với các detector khác.
  **Medoid-updated:** sau khi thêm tạm fix mới vào ứng viên liên tiếp, chọn một fix GPS trong ứng viên
  có tổng khoảng cách haversine đến mọi fix khác nhỏ nhất; hòa thì chọn fix sớm nhất. Kiểm tra mọi
  fix tới medoid; nếu có fix vượt radius thì đóng ứng viên trước fix mới và khởi tạo lại tại fix mới.
  **Max-neighbor-updated:** trên cùng ứng viên liên tiếp, thử từng fix GPS làm tâm, đếm số fix cách
  tâm ≤radius; chọn tâm có count lớn nhất, hòa thì chọn fix sớm nhất. Chỉ giữ ứng viên nếu tâm tốt
  nhất phủ **toàn bộ** fix ứng viên; không có tâm như vậy thì đóng ứng viên trước fix mới và bắt đầu
  lại tại fix mới. Không tự bỏ các fix ngoài bán kính hoặc gom các lần quay lại ở thời gian khác.
  Cả hai chỉ phát stay nếu duration đạt ngưỡng; gap/segment/end-of-trajectory xử lý như baseline.
  Đây là quét greedy theo prefix, không bảo đảm tìm được đoạn dài nhất toàn trajectory; không tìm
  tâm tự do ngoài các fix GPS. Tâm chọn khi phát event cũng là medoid/max-neighbor tương ứng.
  Hai biến thể chạy đủ 8 cấu hình chung; các tổ hợp duration 10 phút được xét theo (a)–(d).
  Đăng ký phụ lục B4 và hash đặc tả này trước chạy detector; giữ nguyên protocol/corpus B2 đã khóa,
  không sửa code generator hay artifacts đang chạy. Báo riêng đây là bổ sung trước đánh giá B4.
- [ ] **Grid chung cho đủ 5 detector** fixed-anchor, median-updated, medoid-updated,
  max-neighbor-updated và ST-DBSCAN là tích đầy đủ **radius {50,100,150,200 m} × duration {10,20 phút}**:
  **(50 m, 10 phút), (100 m, 10 phút), (150 m, 10 phút), (200 m, 10 phút),
  (50 m, 20 phút), (100 m, 20 phút), (150 m, 20 phút), (200 m, 20 phút)**; max gap 5 phút.
  Tổng **8 cấu hình × 5 detector =40 tổ hợp**. Bỏ cấu hình detector duration 5 phút theo yêu cầu;
  không chỉ chạy duration 20 phút ở radius 100 m. Mọi thuật toán chạy cùng grid, cases và metrics.
  Chạy đủ matrix tổng hợp và phạm vi dữ liệu thật theo manifest cho từng tổ hợp; tái dùng baseline
  khi input/config khớp. Bộ tổng hợp B2 vẫn giữ các nhóm dwell ngắn để đo giới hạn recall; không
  loại truth ngắn hoặc sinh lại corpus chỉ vì bỏ ngưỡng detector 5 phút.
  Trong vòng chọn/xác nhận, tập được xét thay baseline vẫn là **duration 10 phút**: 5 detector ×
  4 radius =20 tổ hợp gồm đối chứng baseline. Duration 20 phút được so đủ mọi radius/thuật toán để
  khảo sát trade-off; chưa dùng để tuyên bố đã tối ưu duration hoặc tự mở rộng luật (a)–(d).
  Phụ lục B4 phải khóa grid/implementation hashes và phạm vi ứng viên mới trước khi xem kết quả
  detector; corpus B2 đang sinh được giữ nguyên, không cần sinh lại chỉ vì thêm thuật toán.
- [ ] **Plot theo cấu hình chung:** mỗi cặp radius/duration có một figure so đủ 5 thuật toán,
  cùng axes/đơn vị/cases. Dùng các panel theo nhóm dwell/noise/dropout, không gộp mọi tình huống
  thành một F1. Báo event F1 macro theo user với bootstrap bất định theo nhóm nguồn sao chép khi có;
  hard negatives dùng panel FP/giờ riêng. Lỗi tâm/start/end, split/merge và runtime/RAM có bảng/plot
  bổ sung cùng legend thuật toán. Không có output cho một tổ hợp thì ghi missing/incomplete rõ ràng,
  không vẽ thành 0 hoặc bỏ khỏi legend để tạo cảm giác so sánh đủ.
- [ ] **Khảo sát tham số ST-DBSCAN riêng:** giữ radius 100 m, dwell 10 phút, max gap 5 phút;
  grid eps_time **{60,180,300 giây} × MinPts {3,5,10}**, tổng 9 bộ tham số, gồm bộ gốc (300,3)
  được tái dùng từ grid chung nếu provenance khớp. Đây là các mức thăm dò do dự án chọn, không
  phải giá trị tối ưu từ paper. Dùng đúng cùng cases/seed của phần selection để so từng bộ tham số;
  chạy trên tổng hợp, báo theo kịch bản và tầng cadence GPS dày/thưa, kèm runtime/RAM.
  Vẽ heatmap/đường độ nhạy riêng cho F1 và FP/giờ; không trộn các biến thể ST-DBSCAN vào legend
  so 5 detector. Giữ ST-DBSCAN (300,3) trong mọi plot chung, kể cả khi khảo sát riêng tìm bộ tốt hơn.
  Khảo sát này chỉ mô tả trade-off, không mở final để chọn tham số, không tự thay ST-DBSCAN của
  tập ứng viên chính hoặc luật (a)–(d). Muốn đánh giá xác nhận bộ tham số khác phải đăng ký câu hỏi/
  ứng viên riêng trước mở final. Khóa hash phụ lục B4 trước xem kết quả; trần compute 24 giờ vẫn
  là tổng cho cả so sánh chung và khảo sát riêng, không cấp lại ngân sách cho mỗi nhóm thí nghiệm.
- [ ] **Áp dụng chế độ đã ghi ở B2:** nếu biết trước bất kỳ nhánh (c) nào thiếu cohort thì chỉ mô tả:
  vẫn chạy ma trận tổng hợp trên phần khảo sát, độ nhạy thật và phủ định toàn scope đã định,
  báo metrics/counts kèm mẫu số; **không chọn ứng viên và không chạy lượt xác nhận cuối**.
  Giữ baseline, ghi rõ thiếu cohort và xác nhận đã được bỏ; ưu tiên compute tiết kiệm cho các tổ hợp grid full-data còn thiếu khi còn ngân sách 24 giờ và không bỏ các việc bắt buộc còn áp dụng.
  Nếu cohort chưa kết luận được trước chạy thì giữ quy trình chọn/xác nhận bên dưới.
- [ ] Trong quy trình chọn/xác nhận, chạy ma trận tổng hợp B2 trên phần chọn cấu hình, báo đầy đủ
  metrics từng ô. Chọn một ứng viên đủ điều kiện theo luật định trước, khóa rồi mới mở phần kiểm tra
  cuối; không chọn theo một F1 chung che ô yếu. Bullet này không áp dụng ở chế độ mô tả.
- [ ] **Độ nhạy thật trên toàn dataset:** số stay/tổng dwell theo user, overlap events giữa cấu hình,
  split/merge và matched temporal Jaccard; giữ noise/missing runs. Hai cạnh radius bắt buộc là
  (100 m, 10 phút) ↔ (50 m, 10 phút) và (100 m, 10 phút) ↔ (200 m, 10 phút), dùng cùng hai cạnh cho
  cả 5 detector khi tính ổn định/plateau và điều kiện (c); cùng cạnh số học không có nghĩa radius
  có cùng ý nghĩa hình học ở mọi thuật toán. Không kết luận nhiều stays hơn là tốt hơn. Cạnh
  duration tới 20 phút ở từng radius chỉ bổ sung mô tả, không tham gia (c); vẫn chạy và báo đủ grid đã chốt.
  Plateau chỉ được gắn cờ khi ≥80% user có ≥5 stays ở hai đầu cạnh có |Δstay count| và |Δdwell|
  ≤10%, cùng event-match Jaccard ≥0,8. Không có cạnh đạt thì báo chưa tìm thấy plateau trong grid,
  không thêm cấu hình ngoài quota hoặc tự gọi 100 m/10 phút tối ưu.
- [ ] **Phủ định bằng nhãn phương tiện:** trên 69 user có file nhãn, ghép intervals cùng user/UTC,
  hợp nhất overlaps để không đếm hai lần, loại vùng nhãn mâu thuẫn theo policy đã khóa. Báo
  r_motor = thời lượng stay giao ô tô/bus/tàu / thời lượng stay có bất kỳ nhãn mode hợp lệ;
  coverage có nhãn trên toàn stays, per-mode/per-user và số user thực có mẫu số. Thiếu coverage là NA.
  **Kỳ vọng gần 0, mốc cảnh báo thiết kế 1%**; vượt mốc phải phân tích và ghi giới hạn.
  Đây là bằng chứng yếu chỉ bắt FP rõ ràng, **không đo FN**; interval trên xe có thể gồm chờ/đón trả,
  nên overlap không tự chứng minh từng stay sai. Không dùng mode để lọc rồi chấm bằng chính mode đó.
- [ ] **Giai đoạn áp dụng luật (a)–(d) trong quy trình chọn/xác nhận:** trước hết đánh giá đủ
  bốn điều kiện trên **phần chọn
  cấu hình**; chỉ các ứng viên duration 10 phút qua hết mới được xét chọn. Các chỉ số thật (c) và
  timing theo user (d) phục vụ quyết định dùng đúng nhóm user tương ứng với phần chọn nguồn ở B2.
  Toàn dataset vẫn được xử lý/kiểm kê; user ngoài cohort nguồn chỉ dùng mô tả, không chọn ứng viên.
  Khóa một ứng viên/config rồi **lặp lại đủ (a)–(d) trên phần kiểm tra cuối**, dùng user/seed đã tách.
  Với (c)/(d), lọc đúng cohort xác nhận từ outputs/timing có provenance; có thể tái dùng cache hợp lệ,
  không ngầm chạy lại toàn pipeline. Trần compute 24 giờ là tích lũy hai giai đoạn, không cấp lại.
  Kết quả chọn cấu hình chỉ dùng sàng lọc, không phải bằng chứng xác nhận. Không có ứng viên qua
  lượt chọn hoặc lượt kiểm tra cuối không qua/thiếu quota ở bất kỳ điều kiện nào thì **giữ baseline**;
  không mở lại kiểm tra cuối để thử ứng viên thứ hai.
- [ ] **Quy tắc đổi khỏi baseline — mọi điều kiện đều bắt buộc, khóa trước chạy:**

| Điều kiện | Ngưỡng số cụ thể — quyết định thiết kế |
|---|---|
| (a) Cải thiện rõ trên dữ liệu tổng hợp của giai đoạn đang xét | Áp dụng riêng ở lượt chọn và lượt xác nhận, với cùng ngưỡng; trên cả 2 ô đã chỉ định: duration 10–20 phút/15 m/drift và 20–60 phút/30 m/outlier, ΔF1 macro theo user ≥0,03 tuyệt đối. Cận dưới paired user-bootstrap CI 97,5% >0 ở mỗi ô (5.000 resamples, giữ mọi seed của user; điều chỉnh 2 ô để mức gia đình 95%). Không đạt quota nguồn thì chưa đạt điều kiện; chỉ lượt cuối xác nhận một ứng viên đã khóa |
| (b) Không làm xấu kịch bản khác | Mỗi ô có positives: precision/recall/F1 không giảm quá 0,02 tuyệt đối; median lỗi start/end không tăng >60 giây, median lỗi tâm không tăng >10 m; split/merge không tăng >2 điểm phần trăm. Hard negatives: FP/giờ không tăng >0,05 và moving thuần có FP/giờ ≤0,1, đủ ≥10 giờ latent moving của ≥10 user trong phần dữ liệu đang xét. Ô chưa chạy/thiếu quota không được coi là đạt. Cả hai không dự đoán thì precision/timing NA, so recall/F1 = 0 và FN, không tự tính NA là cải thiện. Timing chỉ so khi cả hai có matched events; luôn báo matched fraction/recall để không được lợi vì chỉ bắt ca dễ |
| (c) Không làm xấu phủ định và ổn định thật | r_motor ≤1% và không tăng >0,1 điểm phần trăm so baseline, cùng mask/coverage. Trên cùng 2 cạnh radius bắt buộc, median user/event Jaccard của detector ứng viên không thấp hơn baseline >0,05; tỷ lệ user có mức đổi tuyệt đối count hoặc dwell >50% không tăng >5 điểm phần trăm. Phủ định dùng cohort có nhãn hợp lệ/mẫu số dương; ổn định tính trên cohort chung đủ ≥5 stays/đầu cạnh, báo số user từng nhánh và tập giao. Dưới 15 user chung ổn định thì chưa xác nhận, không quy thành ứng viên kém |
| (d) Chi phí chấp nhận được | Trên cùng workload/điều kiện timing, runtime ứng viên ≤1,5 lần baseline; RAM không vượt budget B1; mọi runs phải completed/đủ scope và tổng compute mới ≤24 giờ. Không hứa điều này đã đạt khi chưa đo |

**Cách hiểu nhánh ổn định của (c):** đo ở **mức detector, không phải radius**. Hai cạnh đều lấy
(100 m, 10 phút) làm đầu chung; tính một bộ Jaccard/tỷ lệ biến động trên hai cạnh cho mỗi detector.
Mọi cấu hình cùng detector dùng chung bộ số này. Ứng viên fixed-anchor 50/150/200 m có **Δ = 0** so
baseline ở nhánh ổn định (qua mặc nhiên khi cohort đủ để đo, không vượt qua yêu cầu cohort);
bốn radius của từng detector còn lại dùng chung một bộ số của chính detector đó. Với ứng viên chỉ đổi radius, (c) chỉ phân
biệt bằng **r_motor**; bằng chứng riêng theo radius đến từ các ô tổng hợp **(a)(b)**. **Không báo
ổn định/plateau như bằng chứng cho một radius cụ thể.** Ghi riêng nhánh này với kết quả phủ định.

- [ ] Trong quy trình chọn/xác nhận, nếu nhiều ứng viên qua luật trên phần chọn cấu hình,
  ưu tiên ứng viên ít thay đổi semantics/
  đơn giản hơn, sau đó runtime thấp hơn; tie-break bằng config ID đã khóa. Chỉ kiểm tra cuối ứng viên đó
  bằng cùng luật (a)–(d). Không đạt bất kỳ điều kiện nào ở lượt xác nhận: **giữ baseline**, ghi rõ ô nào kém/thiếu bằng chứng. Không gọi
  không khác biệt là tương đương, không sửa ngưỡng chấp nhận sau khi đã xem kết quả.

**Tiêu chí xong:** bảng tổng hợp từng kịch bản, độ nhạy/plateau thật và phủ định có mẫu số,
audit runtime/RAM/phạm vi và hạn chế. Quy trình chọn/xác nhận phải có quyết định theo đủ (a)–(d);
chế độ mô tả phải ghi giữ baseline do thiếu cohort, nhánh thiếu và việc không chọn/không chạy xác nhận cuối.

### B5 — Home/Office: ổn định và timezone ablation

Quyết định của người dùng ngày **2026-11-06**: chọn **fixed-anchor 150 m/10 phút** làm nhánh
thử nghiệm B5, so với baseline **fixed-anchor 100 m/10 phút**. Đây là lựa chọn để so sánh downstream,
không phải kết quả ứng viên đã vượt các cổng B4; giữ nguyên artifacts, ngưỡng và trạng thái xác nhận B4.

Đã chuẩn bị notebook độc lập `notebooks/10_cp1_b5_roles.ipynb` và protocol
`reports/cp1/role_protocol.md`; output riêng `artifacts/benchmark/b5/roles_v1`. Code được kiểm
trên fixture nhỏ; các ô B5 dưới đây chỉ tick sau khi người dùng chạy và kiểm đủ kết quả thật.

- [ ] Chuẩn bị hai nhánh stay 100 m/10 phút và 150 m/10 phút từ checkpoints B4 đủ 182 users;
  kiểm tra provenance, tái dùng baseline khi khớp. Gom địa điểm riêng cho từng nhánh, giữ cùng phương
  pháp và tham số grouping; không dùng nguyên clusters 100 m cho stays 150 m. Lưu output riêng,
  không ghi đè baseline. Coverage GPS đầu vào giữ chung khi timezone/cửa sổ không đổi.
- [ ] So bốn tổ hợp: 100 m + score hiện tại, 100 m + rule đơn giản, 150 m + score hiện tại,
  150 m + rule đơn giản. Trong từng nhánh stay, giữ grouping/timezone/coverage cố định khi so rule;
  khi so hai nhánh stay, giữ rule và tham số grouping/timezone cố định. Nếu so nhiều phương pháp
  grouping thì báo riêng từng phương pháp, không gộp ảnh hưởng grouping vào ảnh hưởng radius/rule.
- [ ] Giữ detector/grouping/timezone/coverage cố định trong từng cặp khi so score hiện tại với baseline đơn giản:
  Home xếp theo số đêm ghé rồi dwell đêm; Office theo ngày ghé rồi dwell giờ làm việc. Giữ eligibility,
  require unique top theo hai tiêu chí, không đủ/hòa thì unknown; ghi khác biệt abstention rõ ràng.
  Giữ rule hiện tại khi chưa có bằng chứng khác, không chọn bằng F1 stay tổng hợp.
- [ ] Báo prediction/unknown rates và reason theo role/user/coverage/method; không tối đa hóa số
  predictions hoặc dùng chính dwell/recurrence trong score làm chứng nhận rule đúng.
  Đối chiếu cùng user giữa bốn tổ hợp: agreement trên cùng predicted users, khoảng cách địa điểm,
  predicted↔unknown và mẫu số; ghép địa điểm theo tọa độ/membership, không theo local cluster IDs.
- [ ] Dịch **cửa sổ rule ±1 giờ**, giữ elapsed UTC và ngưỡng khác; báo vị trí, khoảng cách,
  agreement trên cùng predicted users và predicted↔unknown. Ghép địa điểm theo tọa độ/membership,
  không so local cluster IDs. Gắn cờ nếu >10% ca cùng predicted đổi vị trí >200 m hoặc prediction
  rate đổi >5 điểm phần trăm; đây là ngưỡng điều tra thiết kế, không phải accuracy.
- [ ] Timezone ablation cho **mọi user bị ảnh hưởng** khi zone/offset lịch sử khác Asia/Shanghai:
  giữ cleaned GPS/stays/grouping/rules, chạy lại **coverage, temporal features và inference**,
  gộp cache phần không đổi với audit đủ 182 users. Báo eligible/candidate/role đổi và transitions;
  không có user ảnh hưởng thì ghi no-op sau inventory. Zone chưa xác định báo riêng với fallback.
- [ ] So trước/sau nếu dữ liệu đủ: hai khối 28 ngày liên tiếp, mỗi khối ≥7 observed days và ≥60 phút
  role coverage, tối thiểu 15 user/role để tổng hợp. Chỉ dùng dữ liệu của từng giai đoạn cho kết quả
  giai đoạn đó, không dùng tương lai trong context/clustering. Thiếu thì ghi chưa đánh giá;
  chuyển nhà/đổi việc là khả năng thật, output đổi không tự chứng minh performance giảm.

**Tiêu chí xong:** bảng baseline/unknown/sensitivity/timezone có phạm vi và lý do ổn định hoặc
không ổn định; **không tuyên bố accuracy Home/Office** khi chưa có đáp án thật trên người dùng.

### B6 — Tổng hợp quyết định và giới hạn trước CP2

- [ ] Decision table: giả thuyết → cấu hình → nguồn dữ liệu/đáp án → metrics từng ô → tiêu chí
  đạt/chưa đạt → trade-off → lựa chọn → điều chưa biết. Ghi chế độ đã dùng; nếu mô tả thì nêu nhánh
  thiếu cohort, giữ baseline và lượt xác nhận đã bỏ. Truy vết đủ góp ý mentor và rủi ro phương pháp.
- [ ] Ghi rõ: tổng hợp có đáp án theo thiết kế nhưng thường **sạch hơn thực tế**, latent motion/
  error/dropout model có thể sai; profile nguồn không bảo đảm mô phỏng mọi user hoặc stop trong nhà.
  Nhãn phương tiện chỉ là bằng chứng yếu, không đo FN; gaps thật không cho biết dwell.
  **Không nêu accuracy trên GeoLife thật**, không suy F1 tổng hợp thành Home/Office accuracy.
- [ ] Nếu không có bằng chứng phân biệt thì ghi nguyên ý: **“100 m/10 phút chưa được chứng minh
  tối ưu”**. Giữ baseline là quyết định kỹ thuật hiện tại, không phải kết luận nó tốt nhất.
- [ ] Chỉ cập nhật thuật toán/config khi B4 qua (a)–(d), hoặc sửa lỗi cleaning cụ thể đã audit ở B3;
  ghi version/provenance, kiểm tra boundaries/failure cases và parity notebook/core cần thiết.
  Chưa có bằng chứng thì giữ core 0.2.0; không bắt buộc phải tạo model mới.
- [ ] Khi triển khai sau lượt này, cập nhật NB06/NB07/report/evaluation/research/assumptions theo phương
  pháp mới, lưu dữ liệu tổng hợp và kết quả thật riêng; không ghi đè artifacts baseline hoặc tự push/deploy.
  Ghi mọi mục chưa chạy và compute đã dùng; không tick bằng dự toán.

**Tiêu chí xong:** báo cáo tái lập, đủ giới hạn và decision table; người dùng quyết định phiên bản
đưa vào service. CP2 chỉ dự kiến khi dependency/job thực sự hoàn tất.

### Thứ tự phụ thuộc

**B1 → B2 → B3 → B4 → B5 → B6.** Chỉ chuyển bước khi dependency và đầu ra bắt buộc tương ứng
đã hoàn tất hoặc phần chưa thể xác nhận được ghi rõ theo chế độ áp dụng.

- **B1:** hoàn tất kiểm kê/profile/parity và dự toán compute để cung cấp nguồn cho B2.
- **B2:** dùng đầu ra B1 để khóa protocol, generator, phép chia nguồn/seed và bảng cohort;
  ghi chế độ mô tả nếu đã biết (c) không thể xác nhận, hoặc tiếp tục quy trình hiện tại nếu chưa kết luận được.
- **B3:** dùng dữ liệu/provenance đã kiểm kê để audit cleaning và stay-diff; giữ vote20 trừ lỗi cụ thể.
- **B4:** dùng protocol B2 và cleaning B3 đã chốt; thực hiện chế độ mô tả hoặc quy trình chọn/xác nhận
  theo điều kiện cohort. Ghi compute thực dùng và trạng thái mọi job, không coi chưa chạy là đạt.
- **B5:** dùng detector/config được giữ hoặc xác nhận ở B4 để kiểm tra Home/Office, unknown và timezone.
- **B6:** tổng hợp outputs B1–B5, decision table, giới hạn và các job/phép đo chưa hoàn tất.

**CP2 chỉ bắt đầu khi dependency/job thực sự hoàn tất, không cam kết ngày.** Người dùng chủ động
chạy tuần tự các job khi code/input/protocol sẵn sàng; tổng compute vẫn trong 24 giờ, không cấp lại
ngân sách theo bước hoặc chế độ. Không tự tạo automation/khởi job hoặc tăng grid để giữ tiến độ.

### Mở rộng không chặn CP2

Infostop, duration 30 phút, lịch lễ/ngày làm bù, dịch ±2 giờ và so qua năm chỉ thêm khi
có câu hỏi cụ thể, dữ liệu đủ và budget mới được chốt. Không đưa các mục này vào phạm vi bắt buộc.

### Nguồn tham khảo khởi đầu

- Pérez-Torres và cộng sự (2016), [Full On-Device Stay Points Detection](https://pmc.ncbi.nlm.nih.gov/articles/PMC5087481/):
  đối chiếu distance/time detector, đại diện và sampling; ghi rõ adaptation của dự án.
- Zheng và cộng sự (2009), [Mining Interesting Locations and Travel Sequences from GPS Trajectories](https://www.cl.cam.ac.uk/teaching/1718/R249/GPSZheng.pdf):
  mô tả stay-point distance/time dùng các điểm liên tiếp trong bán kính từ điểm neo; fixed-anchor là
  adaptation vì dự án dùng median tọa độ đại diện và reset theo gap/segment.
- Birant & Kut (2007), [ST-DBSCAN: An Algorithm for Clustering Spatial–Temporal Data](https://doi.org/10.1016/j.datak.2006.01.013):
  nguồn thuật toán đối chứng phân cụm mật độ theo chiều không gian và thời gian; cách đổi cluster
  thành event phải được khóa riêng trong B2.
- Kato và cộng sự (2024), [Evaluating and Validating Stay Point Detection Algorithms with different GPS Log Intervals](https://doi.org/10.1016/j.procs.2024.06.095):
  tham khảo đối chứng detector/sampling; kết quả dataset khác không tự chuyển sang GeoLife.
- Verma và cộng sự (2024), [Comparison of home detection algorithms using smartphone GPS data](https://link.springer.com/article/10.1140/epjds/s13688-023-00447-w):
  so rule/data quality/proxy metrics, không biến proxy thành truth của dự án.
- Aslak & Alessandretti (2020), [Infostop](https://arxiv.org/abs/2003.14370): nguồn mở rộng khi có lý do.

## Lộ trình 6 tuần theo hướng hiểu bản chất

### Tuần 1 — Hiểu dữ liệu và cleaning (CP1)

**Câu hỏi cốt lõi:** một GPS point, một trajectory và một lần ghé khác nhau thế nào?
Sampling/gaps/missingness làm giới hạn kết luận của mình ra sao? Vì sao rule cleaning này hợp lý?

- [x] Notebook 01 đã tạo và chạy: inventory, raw sample, quality audit chưa xóa, sampling/gaps. Theo yêu cầu, đã bỏ bốn chart và các cell coverage/recording hours/distance-speed/spatial.
- [x] Đã trao đổi về point/trajectory/visit, subset, sampling/gaps và cách đọc chart; người dùng cho phép chuyển sang notebook 02.
- [x] Notebook 02 đã sửa để xử lý toàn bộ users/trajectories theo luồng, tổng hợp audit và charts trên cả dataset, không lấy mẫu.
- [x] Người dùng đã chạy NB02 toàn dataset. Đã đọc audit xác nhận completed/full_dataset, policy spatial_vote_context_v2, ngưỡng 20m, đủ 182 users/18.670 files; tổng và từng user đều cân bằng input/output/outcomes.

**Sản phẩm:** notebooks có giải thích và nhận xét, raw baseline giữ nguyên, danh sách cleaning decisions.
**Điều kiện chuyển bước:** giải thích được mẫu số mỗi chart, gaps không phải dwell, dữ liệu bị đổi vì sao.

### Tuần 2 — Từ GPS tới nơi thường ghé, inference và API contract (CP1)

**Câu hỏi cốt lõi:** detector tạo stay như thế nào? DBSCAN gom cái gì? Bằng chứng nào đủ để
gọi một nơi là Home/Office, và khi nào nên trả unknown? API contract mô tả điều gì?

- [x] Notebook 03 đã tạo: rule anchor/radius/time, xử lý toàn bộ cleaned dataset theo từng trajectory,
  tôn trọng observation segments; audit phạm vi, bảng stays và hai chart tổng hợp mọi users.
- [x] Người dùng đã chạy NB03 và năm cấu hình sensitivity đủ 24.177.772 cleaned points mỗi lượt;
  baseline có 10.339 stays / 151 users, 0 overlap, 3.592,999 giờ. Đã trao đổi về kết quả và cho phép chuyển bước;
  không coi ngưỡng 100 m / 10 phút là đã tối ưu.
- [x] Notebook 04 đã tạo: so radius matching với DBSCAN trên toàn bộ stays; giữ noise, đo cluster extent,
  đếm ngày/đợt ghé theo Asia/Shanghai và thống kê cả 182 users (kể cả 31 users không có stay).
- [x] Người dùng đã chạy NB04 baseline đủ 10.339 stays, thống kê đủ 182 users; đã xác minh audit completed.
- [x] Thêm map tương tác NB04 phần 7b: so hai phương pháp cạnh nhau, chọn mọi user/toàn dataset, giữ noise,
  popup và vòng độ rộng. Xuất từ CSV có sẵn, không chạy lại grouping.
- [x] Đã cùng đọc map/sensitivity NB04, phân biệt spatial grouping với ngày ghé; người dùng xác nhận xem map bằng trình duyệt và cho phép phase 5.
- [x] Notebook 05 đã tạo: overlap night/work windows, coverage toàn GPS theo luồng có cache,
  score components/alternatives, reasons unknown, POIs, hai chart, map nhãn và sensitivity tùy chọn.
- [x] Người dùng đã chạy NB05 đủ dataset và sensitivity (20 hàng = 5 cấu hình × 2 phương pháp × 2 vai trò), đã trao đổi kết quả/rules; không dùng prediction làm nhãn hoặc báo accuracy.
- [x] Tổng hợp các quyết định đã thảo luận vào code/docs; gần nhất 115 tests pass.
- [x] Hoàn thiện OpenAPI draft, kiểm tra 182 real-data responses + 6 examples (188 pass), chuẩn bị report để người dùng trình bày trực tiếp.
- [ ] Người dùng review worksheet định tính nếu muốn bổ sung nhận xét; không cần nhãn này để trình bày kết quả pipeline.

**Sản phẩm:** baseline CP1 đã hiểu, evaluation notes, OpenAPI draft có validation.
**Điều kiện chuyển bước:** phân biệt point/stay/visit/cluster, giải thích unknown và score;
nếu muốn mở rộng sang HTTP service thì chốt phạm vi ở checkpoint riêng.

### Tuần 3 — API, đóng gói và model versioning (CP2, chưa triển khai)

**Câu hỏi cốt lõi:** thuật toán offline khác một service ở đâu? Model version gồm thuật toán,
config và code gì? Làm sao gửi lại cùng input và biết bản nào tạo ra output?

- [ ] Nếu cần HTTP service: làm một request nhỏ → validation → core → response, quan sát lỗi input cụ thể.
- [ ] So contract examples với API thực tế; bổ sung HTTP tests sau khi có implementation.
- [ ] Đóng gói chạy local, giải thích Docker image/container, config, dependencies và resource limits.
- [ ] So sánh `heuristic-v1` và `dbscan-v1` trên cùng sample/config/evaluation procedure;
  ghi version metadata, artifact provenance và khác biệt output.
- [ ] Chuẩn bị presentation tuần 3 trong `reports/week3/`, tập trung câu hỏi, bằng chứng, điều chưa chắc.

**Sản phẩm:** service local theo contract, hai model versions tái lập được, presentation tuần 3.
**Điều kiện chuyển bước:** người dùng giải thích được data flow, version và cách reproduce/rollback;
không tự dựng registry phức tạp khi metadata đơn giản còn đủ cho bài học.

### Tuần 4 — Triển khai AWS và chiến lược release (CP2, chưa triển khai)

**Câu hỏi cốt lõi:** request đi qua đâu trên AWS? Chi phí phát sinh từ đâu? Vì sao chọn cách deploy
này, và khi model mới có vấn đề thì quay lại bản cũ bằng cách nào?

- [ ] Vẽ kiến trúc nhỏ; so các lựa chọn compute/storage theo nhu cầu và chi phí ước tính có nguồn lúc làm.
- [ ] Chuẩn bị deployment plan cụ thể, permissions, tài nguyên, ngân sách và cleanup/rollback plan
  để người dùng duyệt **trước** khi tạo cloud resources hoặc phát sinh chi phí.
- [ ] Sau khi được phép: deploy service có endpoint kiểm chứng được, xác minh version đang chạy.
- [ ] Giải thích Shadow, Canary, Blue-green bằng sơ đồ/request routing; chọn và demo ít nhất một chiến lược.
- [ ] Ghi log thực nghiệm release/rollback, thay đổi version, ảnh hưởng và giới hạn của demo.

**Sản phẩm:** accessible AWS service, release strategy demo, version/rollback evidence và cost notes.
**Điều kiện chuyển bước:** hiểu đường đi request, cách kiểm tra version và rollback, có endpoint đã xác minh.

### Tuần 5 — Serving và đo latency/error (CP3, chưa triển khai)

**Câu hỏi cốt lõi:** sync trả kết quả lúc nào, async trả cái gì trước? Queue/wait time khác
processing time thế nào? p50/p95 và throughput trả lời những câu hỏi khác nhau ra sao?

- [ ] Định nghĩa request sizes, concurrency, repetitions/warm-up và timing boundaries trước khi đo.
- [ ] Thí nghiệm sync và async trên cùng workload có kiểm soát; chỉ thêm job/queue khi tới chặng này.
- [ ] Notebook/plots: latency distribution, p50/p95, throughput và error rates theo workload;
  phân biệt end-to-end/queue/processing times và các trường hợp timeout.
- [ ] Theo dõi request latency, error rate và input/output quality, tránh ghi GPS cá nhân vào logs.
- [ ] Đọc chart rồi giải thích trade-offs; không kết luận async luôn nhanh hơn hoặc dùng một lần đo làm benchmark.

**Sản phẩm:** benchmark tái lập được, serving comparison và dashboard/monitoring cơ bản.
**Điều kiện chuyển bước:** giải thích được các phép đo, mẫu số, điều kiện thí nghiệm và giới hạn kết luận.

### Tuần 6 — Drift, alerts và tổng kết end-to-end (CP3, chưa triển khai)

**Câu hỏi cốt lõi:** dữ liệu thay đổi thế nào là đáng quan tâm? Drift có chứng minh model sai không?
Alert cần hành động gì? Dữ liệu lịch sử tĩnh khác luồng production đang thay đổi ở đâu?

- [ ] Chọn reference/current windows và metrics có lý do: sampling/gaps, coverage, spatial/temporal features,
  noise/unknown rates; phân biệt data drift, chất lượng input và model performance.
- [ ] Tạo kịch bản thay đổi mô phỏng được ghi rõ (ví dụ logging thưa hơn hoặc đổi temporal coverage),
  giữ baseline đối chứng và không mô tả simulation là sự kiện production thật.
- [ ] Notebook/plots trước/sau, đo phản ứng của detector và thử alert thresholds/false alarms.
- [ ] Thiết lập alert cơ bản và runbook: khi nào báo, người nhận làm gì, khi nào rollback hoặc điều tra dữ liệu.
- [ ] Demo end-to-end có monitoring, tổng kết failure cases/limitations/cost; presentation tuần 6 ở `reports/week6/`.

**Sản phẩm:** drift experiment, alerts/runbook, service demo và presentation tổng kết.
**Điều kiện hoàn tất:** người dùng tự trình bày được hệ thống, tái lập demo và giải thích điều chưa chứng minh.

Các tuần 3–6 hiện chỉ là kế hoạch học và tiêu chí đầu ra; không có hạ tầng/API/monitoring mới được tạo.

### Chặng A — `01_dataset_overview.ipynb` (đã chạy; chờ cùng đọc kết quả)

**Chỉ khảo sát dữ liệu gốc, chưa áp dụng cleaning hoặc inference.**

- [x] Chuẩn bị kernel notebook dùng đúng môi trường dự án, đường dẫn dataset cấu hình ngoài code.
- [x] Đọc cấu trúc ZIP, một PLT mẫu, giải thích từng cột và GMT/altitude units.
- [x] Tổng quan toàn dataset: users, trajectories, record counts; phân phối trajectories/points per user.
- [x] Chọn 1–3 users để xem sâu và ghi rõ lý do chọn; tách số liệu toàn bộ với subset.
- [x] Thống kê raw/parsed missing, invalid, duplicates, conflicting timestamps trước khi xóa.
- [x] Chart sampling intervals và long gaps, ghi rõ cách tính trong từng trajectory.
- [x] Đã trao đổi kết quả EDA; người dùng yêu cầu bắt đầu notebook 02. Đã bỏ phần câu hỏi tự kiểm tra theo yêu cầu.

### Chặng B — `02_preprocessing.ipynb` (đã chạy toàn dataset và xác minh audit)

- [x] Dựa vào Chặng A, giải thích và chọn từng validation/cleaning rule.
- [x] Code giữ PLT gốc, xử lý từng trajectory, xuất theo luồng, có audit từng user và tổng hợp. Scope được lấy từ toàn bộ source.by_user, không hardcode users mẫu.
- [x] Code có bảng số điểm trước/sau, removal reasons không chồng nhau và hai charts toàn dataset; sampling ECDF dùng mọi positive pair, không lấy mẫu/xấp xỉ.
- [x] Code ghi trạng thái running/failed/completed, kiểm tra đủ users/files và count invariants; không bỏ qua file lỗi.
- [x] NB02 đã sửa conflict policy: scan max-pairwise spread toàn dataset, chọn ngưỡng theo số liệu; vote/gộp mean và giữ trace. Từ core 0.2.0, raw core/CLI dùng cùng spatial/context vote; NB02 dùng helper diagnostics cho rows đã resolve để không vote hai lần.
- [x] Giữ missing altitude, gắn cờ gap/speed; nhóm conflict chưa giải quyết làm ngắt observation segment. Không tự đặt ngưỡng hoặc chạy dataset.
- [x] Đã xác minh audit full và có đủ ba CSV kết quả. Input 24.876.978 → cleaned 24.177.772 rows; invalid 1, duplicates 146.914, merged extras 551.156, conflict rows tách riêng 1.135. Còn 305 conflict groups chưa giải quyết; không khẳng định cleaned coordinates là ground truth.

### Chặng C — notebooks về stays và địa điểm (sau A/B)

- [x] Tạo notebook 03 giải thích stay detector bằng rule và ví dụ thời gian; mọi tính toán/chart dùng toàn dataset.
- [x] Người dùng chạy NB03, audit xác nhận đủ input theo NB02; đã đọc số stays/overlap và sensitivity.
- [x] Đã thử threshold NB03 trên toàn dataset, mỗi lần đổi radius hoặc duration; chưa có nhãn xác định đúng/sai.
- [x] Đã tạo NB04 trực quan hóa grouping heuristic/DBSCAN, noise, extent và recurrence trên toàn stays.
- [x] Người dùng đã chạy NB04 full-data; có audit/CSV và map xuất từ cùng baseline.
- [x] Đã trao đổi clustering/noise, eps/min_samples sensitivity và map; người dùng cho phép chuyển sang temporal evidence.
- [x] Tạo NB05 xem temporal evidence trước khi quyết định Home/Office; cho phép unknown và giải thích score/eligibility.
- [x] NB05 baseline và sensitivity đã hoàn tất trên toàn dataset; đã cùng đọc nhãn P, lý do user 003 unknown và cách tính điểm/share/dwell.
- [ ] Ghi manual review có lý do/uncertainty vào bộ kết quả hiện tại; chưa có manual proxy labels được điền.

### Chặng D — tổng hợp CP1 và review API (sau các phân tích)

- [x] Đồng bộ voting/segment NB02 vào core/CLI 0.2.0, config ngưỡng 20 m, point trace và audit counts. Parity tests so đúng reference NB02 và các bước NB03–05 trên synthetic fixtures, cả hai models.
- [x] Người dùng đã chạy CLI DBSCAN full-data; đối chiếu toàn bộ saved outputs với NB02–05, không có khác biệt ngoài float tolerance (max delta khoảng 8,98e-9). Báo cáo artifacts/pipeline/dbscan-v1/notebook-comparison.json.
- [ ] Nếu cần xác nhận parity full-data cho cả hai nhánh CLI, chạy thêm heuristic-v1 và đối chiếu tương tự; notebook heuristic đã có kết quả full-data.
- [ ] Tổng hợp kết luận đã được thảo luận từ notebooks; sửa baseline/docs nếu cần.
- [ ] Đánh giá giới hạn, sensitivity và manual-review evidence; không công bố accuracy thiếu nhãn.
- [x] Hoàn thiện OpenAPI draft và validation trên 188 examples/responses; người dùng sẽ trình bày trực tiếp.
- [ ] Người dùng review worksheet định tính nếu muốn bổ sung nhận xét.

## Bản baseline đã thực hiện — lịch sử kỹ thuật để tham khảo

Các phần sau ghi hiện trạng của bản thử đầu tiên. **Kế hoạch notebook bên trên mới là
thứ tự công việc đang theo.** Không cần xóa hoặc làm lại máy móc những phần đã đúng;
chỉ tái sử dụng sau khi kiểm tra và hiểu trong quá trình phân tích.

## Mục tiêu và giới hạn

- Pipeline offline tái lập được: GeoLife → GPS sạch → stay events → địa điểm → temporal features → Home/Office/POI và evidence.
- Hai cách nhóm địa điểm có cùng input/output: `heuristic-v1` và `dbscan-v1`.
- POI là địa điểm thường ghé, không phải loại hình doanh nghiệp.
- Không có ground truth Home/Office: không công bố accuracy/F1 hoặc xác suất đã hiệu chuẩn.
- Không commit dữ liệu GPS thô hay kết quả chứa tọa độ cá nhân.
- Không AWS, HTTP endpoints, frontend, registry, async infrastructure hoặc monitoring trong CP1.
- CP1 không triển khai HTTP API. OpenAPI là tài liệu thiết kế để trình bày; service chỉ làm nếu người dùng chọn ở checkpoint sau.
- Không push GitHub, tạo tài nguyên cloud, chi tiền hoặc thao tác phá hủy khi chưa được người dùng cho phép.

## Phase 0 — Khảo sát [hoàn tất]

- [x] Windows 11 x64, `py` = Python 3.11.4; Git có sẵn.
- [x] Clone repository trực tiếp vào thư mục hiện tại; remote `quycute2003/Geolife-Trajectories`, nhánh main chưa có commit.
- [x] ZIP được cung cấp có 182 users, 18.670 `.plt`, 69 transportation label files, User Guide 1.3.
- [x] ZIP khoảng 299 MiB; tổng dung lượng giải nén khoảng 1,55 GiB. Chưa giải nén toàn bộ.
- [x] NumPy/pandas/scikit-learn/pytest/tzdata import thành công trong môi trường chung.

## Phase 1 — Setup, loader, data understanding

- [x] Tạo package nhỏ trong `src/geolife_inference/`, cấu hình, README, `.gitignore`, môi trường riêng và lock dependencies.
- [x] Xác minh tài liệu gốc: User Guide 1.3; stay detection 2016; LP-Mine 2009. Ghi nguồn, adaptation và giới hạn.
- [x] Loader đọc ZIP hoặc thư mục `.plt`, bỏ 6 header, UTC, altitude feet / -777, user/trajectory IDs, chronological order.
- [x] Unit tests với synthetic fixtures, kiểm tra một trajectory thật.
- [x] Inventory toàn ZIP; EDA ban đầu users 000, 001, 002: points, thời gian, duplicates/missing, sampling, gaps, distance/speed, coverage.

## Phase 2 — Preprocessing

- [x] Validate coordinates/timestamps, bỏ invalid và exact duplicates với audit counts.
- [x] Haversine meters, diagnostic high speeds; mặc định không xóa high-speed points.
- [x] Giữ trajectory boundaries; xử lý sampling gaps và overlapping observations rõ ràng.
- [x] Tests cho khoảng cách, timestamps, malformed input, duplicates và boundaries.

## Phase 3 — Stay detection

- [x] Anchor-based distance/time detector, representative robust coordinate.
- [x] Khởi đầu 100 m / 10 min / max gap 5 min; đây là giả thuyết cần sensitivity analysis.
- [x] Không suy dwell qua gaps hoặc trajectory boundaries; xử lý cuối trajectory.
- [x] Tests: short/long stop, jitter, slow movement, duplicate timestamps, sparse/gaps, nhiều stays.
- [x] Notebook 03 đọc CSV nén theo khối nhưng giữ nguyên trajectory; detector ngắt khi observation_segment đổi.
- [x] Có output riêng cho các stays chồng thời gian; cùng một policy first-chronological trên toàn user.
- [x] Người dùng đã chạy notebook 03 toàn dataset và review sensitivity: baseline 10.339 stays / 151 users / 0 overlap.

## Phase 4 — Grouping, temporal features, inference

**Tiến độ notebook hiện tại:** người dùng đã chạy NB04 grouping/recurrence/dispersion trên toàn stays;
đã review map/sensitivity và yêu cầu NB05. NB05 đã viết, chưa chạy dataset để gán Home/Office.
Các checkbox baseline dưới đây là lịch sử triển khai.

- [x] `heuristic-v1`: deterministic radius matching của stay events, mô tả quy tắc grouping.
- [x] `dbscan-v1`: per-user, haversine radians, eps 100 m, min_samples 3, giữ noise -1.
- [x] Cluster dispersion, visit episodes, distinct days/weeks, dwell overlap theo local timezone.
- [x] Cấu hình night/work windows; UTC nội bộ; Asia/Shanghai là giả định có khai báo.
- [x] Home/Office có evidence score, alternatives và abstention; cho phép cùng địa điểm, thiếu một hoặc cả hai.
- [x] POIs cần recurrence; JSON output và CLI; tests quan trọng bao gồm midnight/weekend/timezone.

## Phase 5 — Evaluation, docs, OpenAPI

- [x] Chạy pipeline thật trên nhóm development; lưu diagnostics và output riêng tư trong thư mục gitignored.
- [x] So sánh hai model versions và thay đổi distance/time/gap/DBSCAN parameters.
- [x] Hỗ trợ đánh giá thủ công bằng bản đồ offline, review template; không coi predictions là labels.
- [x] Ghi nhận manual inspection thực sự đã làm, failure cases, unknown rate, dispersion và coverage.
- [x] Hoàn thiện architecture, assumptions, research notes, data dictionary và evaluation.
- [x] OpenAPI 3.x: request/response/errors/examples/UTC/timezone/limits/privacy; validate document và examples.
- [x] Chạy pytest và kiểm tra CLI; cập nhật kết quả thực tế vào PLAN và báo cáo.
- [x] Hoàn thiện OpenAPI draft và validation để người dùng trình bày trực tiếp. **Không triển khai endpoints.**

## Cấu trúc tối thiểu

`src/geolife_inference/`, `tests/`, `configs/`, `docs/`, `reports/`,
`PLAN.md`, `README.md`, `pyproject.toml`, dependency lock, `openapi.yaml`.
Chỉ tạo module và thư mục khi có nội dung; không tạo placeholder API/AWS.

## Các giả định cần nêu trong báo cáo

1. Night/work windows và phạm vi hợp lý của timezone assumption.
2. Định nghĩa evidence score, abstention và manual proxy labels.
3. Hợp đồng API, resource limits và cách biểu diễn insufficient data.
4. OpenAPI mô tả thiết kế dự kiến; chưa có service runtime hoặc số đo latency/load.

## Nhật ký kết quả

- 2026-10-31: Người dùng cho phép thực hiện CP1, yêu cầu giữ kế hoạch trong một file. Bắt đầu Phase 1.

- 2026-10-31: Hoàn tất phần kỹ thuật CP1: loader/preprocessing/stays, hai models, EDA 4 users, 32 experiment runs, docs và OpenAPI. Final suite: 48 passed; 14 contract examples/responses valid; lock checked. Real user 001 rerun tái tạo output chính xác; tám real outputs thỏa dwell/audit invariants.
- Chưa có independent semantic labels. OpenAPI là tài liệu thiết kế để người dùng trình bày; không có endpoints, cloud hoặc GitHub push.
- 2026-10-31: Người dùng yêu cầu làm chậm, tỉ mỉ qua notebooks, thống kê và charts trước/sau cleaning. Đã cập nhật kế hoạch; công việc tiếp theo là Chặng A, không tiếp tục mở rộng pipeline hoặc API lúc này.
- 2026-10-31: Cập nhật đầy đủ kế hoạch tuần 1–6 theo câu hỏi/bằng chứng/điều kiện hiểu trước khi chuyển bước. Notebook 01 có 39 cells (19 code), 6 charts, chạy trên ZIP thật; 530.694 subset rows giữ nguyên, chưa cleaning. Bản executed và GPS outputs giữ local; source clear outputs. Chưa đánh dấu người dùng đã review/hiểu. Dừng để cùng đọc phần 1–3.
- 2026-11-02: Theo yêu cầu người dùng, xóa hai notebook chạy thử và sáu ảnh rendered trùng; giữ notebook làm việc, source sạch và sáu biểu đồ có tên mô tả. Sửa runner để không tạo bộ ảnh trùng nữa. Không thay đổi dữ liệu hay ghi chú trong notebook chính.
- 2026-11-02: Theo yêu cầu tiếp theo, xóa ảnh 03–06 và các cell code/giải thích tương ứng khỏi cả source và notebook làm việc; sửa summary để không còn phụ thuộc các biến đã bỏ. Notebook còn 28 cells (13 code), hai chart: user volume và sampling. Không tạo notebook hoặc ảnh dự phòng.
- 2026-11-02: Theo lựa chọn của người dùng, bỏ cơ chế tách source/executed: giữ một notebook tại `notebooks/01_dataset_overview.ipynb`, chạy và ghi chú trực tiếp tại đó. Chuyển hai ảnh và cache sang `artifacts/overview/`; bỏ folder `artifacts/notebooks/`. Cập nhật launcher/runner theo cấu trúc đơn giản này.
- 2026-11-02: Theo yêu cầu, giải nén dataset vào `data/Geolife Trajectories 1.3/` (18.740 files, 1.668.271.069 bytes, đọc ZIP members có CRC verification). Notebook mặc định đọc thư mục này bằng đường dẫn tương đối, không bắt buộc GEOLIFE_DATASET. Cache dùng file metadata fingerprint; không phát sinh notebook/chart mới.
- 2026-11-02: Dọn helper code theo yêu cầu: đã xóa open_notebook.ps1, run_notebook.py, tmp/build_overview.py và cập nhật hướng dẫn. Giữ core pipeline/tests và hai script phục vụ bài là thí nghiệm, validate OpenAPI. Notebook mở/chạy trực tiếp trong VS Code hoặc Jupyter. Thao tác dọn thư mục cache/build metadata bị hệ thống duyệt tự động chặn; các thư mục đó vẫn được giữ nguyên.
- 2026-11-02: Tạo/chạy notebook 02, 25 cells (13 code), hai chart trước–sau. Subset 530.694 → 530.691 rows; loại ba timestamp-conflict extras, giữ một missing altitude, gắn cờ 1.425 long gaps/94 high-speed pairs. Có audit, cleaned CSV gzip và removed rows. Bỏ quiz/câu hỏi tự kiểm tra ở notebook 01; hai notebook chỉ có bước xử lý/kết quả/giải thích. Không triển khai tiếp stay/inference/API.
- 2026-11-02: Người dùng yêu cầu mọi xử lý từ giờ chạy toàn dataset và chỉ sửa notebook 02 để họ tự chạy. Đã bỏ giới hạn ba users, chuyển sang xử lý từng trajectory của mọi user, ghi CSV theo luồng và tổng hợp toàn bộ pair frequencies. Outputs notebook đã xóa; chỉ validate format/cú pháp, không thực thi dataset. Các artifact subset cũ chưa phải kết quả full và sẽ được thay khi người dùng chạy xong.
- 2026-11-02: Theo yêu cầu, NB02 đổi từ chọn lat/lon nhỏ nhất sang scan toàn bộ conflict spread trước, ngưỡng mặc định None, mean nhóm gần/quarantine nhóm xa sau khi chọn ngưỡng. Lưu group stats và provenance, đếm riêng invalid/duplicates/merged extras/unresolved để không nhầm merge là delete. Chỉ kiểm tra cú pháp và bảy trường hợp synthetic; không đọc/chạy dữ liệu GeoLife. Người dùng chạy phần 1–4, đặt ngưỡng ở phần 5 rồi chạy tiếp.
- 2026-11-02: Người dùng tự chạy policy spatial_vote_context_v2 ở ngưỡng 20m. Đã kiểm tra audit completed/full_dataset: đủ 182 users/18.670 trajectories, 24.876.978 input → 24.177.772 output; count invariants đúng ở tổng và mọi user, CSV kết quả tồn tại. 305 groups vẫn unresolved; bước stay detection phải tôn trọng user/trajectory/observation_segment để không nối qua gaps hoặc unresolved timestamps. Chưa tạo/chạy notebook 03.
- 2026-11-02: Người dùng cho phép commit/push trước phase 3. Chuẩn bị commit đầu tiên: 48 pytest tests pass, notebook syntax valid; đồng bộ NB02 trên ổ đĩa với voting policy đã dùng. Không stage dataset/artifacts/môi trường; stage notebook không kèm generated outputs và giữ outputs làm việc trên máy.
- 2026-11-02: Đã push commit `18b8a58` lên origin/main. Theo yêu cầu tiếp theo, tạo NB03 stay detection toàn cleaned dataset, audit từng user, hai chart tổng hợp và sensitivity tùy chọn (mọi cấu hình đều full-data). Sửa detector tôn trọng observation_segment; giữ riêng stays bị overlap. Chỉ kiểm tra bằng synthetic fixtures, không chạy dataset và chưa có số stays toàn dataset.
- 2026-11-02: Người dùng đã chạy NB03 baseline và sensitivity. Đã đọc audit/CSV: đủ 182 users, 18.670 trajectories, 24.177.772 cleaned points; 10.339 stays ở 151 users, 2.595.092 points thuộc stays, 215.579,967 phút, không có overlap. Sensitivity full-data: radius50→6.024, radius200→14.371, duration5→27.605, duration20→3.174 stays. Người dùng cho phép chuyển phase; tạo NB04 grouping hai phương pháp, audit/recurrence/extent và sensitivity tùy chọn. Chỉ kiểm tra synthetic, để người dùng chạy dữ liệu.
- 2026-11-02: Người dùng đã chạy NB04 rồi yêu cầu map để dễ xem. Đã xác minh audit full/completed và fingerprints; xuất một HTML chứa đủ 10.339 stays, 182 users, 3.577 địa điểm heuristic + 552 DBSCAN. Thêm phần 7b vào notebook, giữ nguyên outputs/ghi chú và lựa chọn sensitivity của người dùng. Map có chọn user/toàn bộ, hai phương pháp cạnh nhau, zoom, noise, extent và popup. Chỉ vẽ từ kết quả có sẵn, không chạy lại clustering.
- 2026-11-02: Người dùng xác nhận map mở được bằng trình duyệt, đã đọc sensitivity NB04 và yêu cầu phase 5. Tạo `05_role_inference.ipynb` cho toàn users/cả hai phương pháp, coverage toàn cleaned GPS theo luồng/cache, temporal features, điểm từng ứng viên, quyết định/unknown/POIs, charts/map nhãn và sensitivity rule. Core coverage tôn trọng observation_segment; score được tách hàm để notebook hiển thị mọi ứng viên mà giữ nguyên quyết định baseline. 66 pytest tests pass và năm synthetic integration cases pass; chỉ validate/kiểm tra dữ liệu giả, không chạy GeoLife hoặc tạo số liệu inference thật. Chờ người dùng chạy/review NB05; chưa triển khai API.
- 2026-11-03: Rà soát CP1 theo yêu cầu người dùng. NB05 audit completed/full_dataset: 182 users, 24.177.772 cleaned points, 10.339 stays, 4.129 địa điểm cộng hai phương pháp. Heuristic Home/Office = 28/8 users; DBSCAN = 37/18. Sensitivity audit completed, 20 rows. Manual-review CSV lịch sử có 130 hàng nhưng 0 proxy labels/reviewers/notes được điền; không xem đó là manual evaluation đã hoàn thành. Việc tiếp theo khi đó là đồng bộ core với NB02, ghi manual-review evidence, cập nhật docs và validate OpenAPI; không chạy lại dataset hay triển khai HTTP API trong lượt rà soát.
- 2026-11-03: Người dùng cho phép bước 1. Core/CLI 0.2.0 đã thay lexicographic tie-break bằng spatial_vote_context_v2 giống NB02; Config/TOML có conflict_merge_threshold_m=20, giữ invalid/duplicate và mọi conflict provenance, unresolved timestamps ngắt stays/coverage. CLI mặc định mọi users, có --audit-points và run-audit running/failed/completed. NB02 chỉ đổi import helper diagnostics, giữ outputs/settings và reference voting code. 115 pytest tests pass, gồm 39 ca parity/reference/end-to-end và 3 thresholds bổ sung, CLI all-user/validation/internal-failure tests. OpenAPI draft được đồng bộ config/diagnostics, 14 examples/historical responses valid; lock offline check pass. Không chạy lại GeoLife, không push, không làm HTTP endpoints. Còn full-data CLI rerun (người dùng chạy), manual review và tổng hợp báo cáo.
- 2026-11-03: Người dùng đã chạy CLI DBSCAN xong và yêu cầu đối chiếu notebook. Audit completed/full_dataset: 182 users / 18.670 files, 24.876.978 raw → 24.177.772 cleaned points. So mọi user: NB02 audit counters, 10.339 stays và membership labels NB03/04, toàn bộ coverage/features/candidate components/reasons/alternatives/ordered POIs NB05 đều khớp (float rtol 1e-10, atol 1e-8, delta lớn nhất 8,9755e-9). 709.851 conflict fixes khớp nội dung/decision/spread, 146.915 invalid/duplicate rows khớp multiset nội dung/reason; không so record IDs vì ID theo từng lượt chạy. 182 responses thực + 6 ví dụ contract validate pass. DBSCAN: 552 clusters, 3.296 noise stays, 37 Home, 18 Office, 202 POIs tổng cộng. Chỉ đọc kết quả có sẵn, không chạy lại pipeline; chưa có CLI heuristic mới và manual review hiện chưa được điền.
- 2026-11-03: Chuẩn bị `artifacts/evaluation/manual-review-sample.csv`: 8 users × 2 models × Home/Office = 32 dòng, chọn theo các tình huống khác nhau (user 003 mơ hồ, khác biệt giữa models, Home/Office cùng cluster, cluster phân tán, dữ liệu thưa). Không tự gán nhãn. Cập nhật `docs/evaluation.md` cách mở map, đọc candidate và ghi nhận plausibility/uncertainty; manual review vẫn chờ người dùng xem và điền, không thể dùng làm ground truth hoặc accuracy.
- 2026-11-03: Chốt bộ hồ sơ CP1: tạo `reports/cp1/summary.md`, cập nhật README/results và kiểm tra lại OpenAPI 3.1 cùng 182 real-data DBSCAN responses + 6 contract examples (188 pass). Người dùng sẽ trình bày trực tiếp; worksheet review vẫn để trống để không tự gán nhãn. Heuristic CLI chưa chạy lại.
