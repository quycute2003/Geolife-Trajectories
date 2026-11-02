# Kế hoạch 6 tuần — Home / Office / POI Inference

Kế hoạch chính của dự án. Cập nhật checkbox và kết quả kiểm chứng sau từng phase.
Ngày bắt đầu: 2026-10-31. Ngôn ngữ: Python 3.11+, dùng `py` trên Windows.

## Hướng làm hiện tại — notebook trước, đi từng bước

**Cập nhật theo yêu cầu người dùng ngày 2026-10-31:** tiến độ triển khai vừa qua quá nhanh
so với mục tiêu học và hiểu dữ liệu. Chuyển sang quy trình khám phá có giải thích, chart
và nhận xét trong Jupyter notebook. Các checkbox baseline phía dưới ghi lại việc đã chạy,
không có nghĩa người dùng đã hiểu, review hoặc chấp nhận các quyết định đó.

Code, reports và OpenAPI hiện có được giữ làm bản thử để tham khảo; không coi các ngưỡng,
cleaning rules hay kết quả suy luận là đã chốt. Bắt đầu lại bằng notebook khám phá dữ liệu gốc.

### Cách làm việc

- **Quy tắc phạm vi mới nhất:** mọi phân tích/xử lý từ đây mặc định chạy toàn bộ dataset. Không tự giới hạn 1–3 users hoặc lấy mẫu points. Có thể xử lý theo từng trajectory/user để tiết kiệm RAM nhưng phải bao phủ đủ tất cả rồi tổng hợp. Các kết quả subset trước đây chỉ là lịch sử.
- **Lượt cập nhật hiện tại:** chỉ sửa notebook 02; người dùng tự chạy. Không tự thực thi preprocessing toàn dataset.
- Mỗi notebook chia cell ngắn: mục đích → code → bảng/chart → nhận xét. Theo yêu cầu mới nhất, không có phần quiz/tự kiểm tra hoặc yêu cầu người dùng điền câu trả lời.
- Giải thích ý nghĩa của chart, đơn vị, mẫu số và phạm vi dữ liệu đang xem.
- Phân biệt dữ liệu raw/parsed với dữ liệu sau cleaning; không dùng output đã làm sạch làm raw baseline.
- Thống kê vấn đề trước, nêu lý do chọn rule rồi mới áp dụng. Không tự động xóa high-speed points.
- Giữ thứ tự: hiểu dữ liệu → cleaning và so sánh → stays → grouping/inference → API design.
- Kết thúc từng notebook bằng các phát hiện, điều còn chưa chắc và lựa chọn cần thảo luận.
- Dừng để cùng người dùng đọc kết quả trước khi chuyển chặng; không tự triển khai toàn bộ các notebook một lượt.
- Synthetic fixtures chỉ phục vụ unit tests; không dùng làm kết quả dataset. Kết quả phân tích phải nêu số users/trajectories/rows thực tế đã xử lý và xác nhận đủ phạm vi.
- Notebook chạy từ môi trường riêng qua `py`; chỉ có một bản làm việc trong `notebooks/`, ảnh/cache ở `artifacts/overview/`. Không tự commit/push dữ liệu lên GitHub.
- Mốc tuần là thứ tự học dự kiến, không ép chạy kịp lịch bằng cách bỏ qua phần chưa hiểu.
- Ghi rõ phần nào đã chạy, kết quả và giới hạn thực tế; trao đổi khi cần làm rõ quyết định, không kiểm tra kiến thức người dùng trong notebook.
- Mỗi quyết định ghi ngắn: đang giải quyết vấn đề gì, lựa chọn nào được thử, bằng chứng nào ủng hộ,
  rủi ro nào còn lại. Giải thích input → thao tác → output ngắn gọn ngay cạnh phần xử lý.

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

- [ ] Notebook 03: một trajectory nhỏ, khoảng cách tới anchor theo thời gian, vẽ candidate/stay/gap;
  thử threshold theo từng yếu tố và giải thích vì sao stays thay đổi.
- [ ] Notebook 04: so radius matching với DBSCAN trên cùng stays; vẽ noise/cluster extent và đếm ngày ghé.
- [ ] Notebook 05: overlap night/work windows, midnight cases, score components và alternatives;
  visual review, sensitivity và failure cases, không dùng prediction làm nhãn.
- [ ] Tổng hợp các quyết định đã thảo luận vào code/docs; chạy tests phù hợp.
- [ ] Cùng đọc request/response/errors trong OpenAPI bằng ví dụ; chuẩn bị mentor review package.

**Sản phẩm:** baseline CP1 đã hiểu, evaluation notes, OpenAPI draft có validation.
**Điều kiện chuyển bước:** phân biệt point/stay/visit/cluster, giải thích unknown và score;
người dùng xác nhận mentor đã duyệt OpenAPI trước mọi HTTP implementation.

### Tuần 3 — API, đóng gói và model versioning (CP2, chưa triển khai)

**Câu hỏi cốt lõi:** thuật toán offline khác một service ở đâu? Model version gồm thuật toán,
config và code gì? Làm sao gửi lại cùng input và biết bản nào tạo ra output?

- [ ] Sau API approval: làm một request nhỏ → validation → core → response, quan sát lỗi input cụ thể.
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
- [x] NB02 đã sửa conflict policy: scan max-pairwise spread toàn dataset, hiển thị phân phối, yêu cầu đặt ngưỡng theo số liệu; gộp mean nhóm gần và cách ly nhóm xa có truy vết. Core chỉ nhận rows đã xử lý conflict trong notebook; core/CLI raw chưa đổi policy.
- [x] Giữ missing altitude, gắn cờ gap/speed; nhóm conflict chưa giải quyết làm ngắt observation segment. Không tự đặt ngưỡng hoặc chạy dataset.
- [x] Đã xác minh audit full và có đủ ba CSV kết quả. Input 24.876.978 → cleaned 24.177.772 rows; invalid 1, duplicates 146.914, merged extras 551.156, conflict rows tách riêng 1.135. Còn 305 conflict groups chưa giải quyết; không khẳng định cleaned coordinates là ground truth.

### Chặng C — notebooks về stays và địa điểm (sau A/B)

- [ ] Giải thích stay detector bằng một trajectory nhỏ và biểu đồ thời gian/khoảng cách.
- [ ] Thử thresholds có kiểm soát, xem các stays bị mất/thêm, lưu failure cases.
- [ ] Trực quan hóa grouping heuristic/DBSCAN, noise, extent và recurrence.
- [ ] Xem temporal evidence trước khi quyết định Home/Office; cho phép unknown.

### Chặng D — tổng hợp CP1 và review API (sau các phân tích)

- [ ] Tổng hợp kết luận đã được thảo luận từ notebooks; sửa baseline/docs nếu cần.
- [ ] Đánh giá giới hạn, sensitivity và manual-review evidence; không công bố accuracy thiếu nhãn.
- [ ] Đọc lại OpenAPI cùng người dùng rồi chuẩn bị bản mentor review.
- [ ] Mentor approval vẫn là gate riêng trước mọi HTTP endpoint implementation.

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
- **STOP GATE:** OpenAPI phải được mentor duyệt và người dùng xác nhận trước khi triển khai HTTP API.
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

## Phase 4 — Grouping, temporal features, inference

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
- [x] Hoàn thiện architecture, assumptions, research notes, data dictionary, evaluation và mentor checklist.
- [x] OpenAPI 3.x: request/response/errors/examples/UTC/timezone/limits/privacy; validate document và examples.
- [x] Chạy pytest và kiểm tra CLI; cập nhật kết quả thực tế vào PLAN và báo cáo.
- [x] Trình OpenAPI cho người dùng chuyển mentor review. **Không triển khai endpoints.**

## Cấu trúc tối thiểu

`src/geolife_inference/`, `tests/`, `configs/`, `docs/`, `reports/`,
`PLAN.md`, `README.md`, `pyproject.toml`, dependency lock, `openapi.yaml`.
Chỉ tạo module và thư mục khi có nội dung; không tạo placeholder API/AWS.

## Quyết định cần mentor góp ý

1. Night/work windows và phạm vi hợp lý của timezone assumption.
2. Định nghĩa evidence score, abstention và manual proxy labels.
3. Hợp đồng API, resource limits và cách biểu diễn insufficient data.
4. Phê duyệt OpenAPI là milestone bên ngoài; không tự đánh dấu đã duyệt.

## Nhật ký kết quả

- 2026-10-31: Người dùng cho phép thực hiện CP1, yêu cầu giữ kế hoạch trong một file. Bắt đầu Phase 1.

- 2026-10-31: Hoàn tất phần kỹ thuật CP1: loader/preprocessing/stays, hai models, EDA 4 users, 32 experiment runs, docs và OpenAPI. Final suite: 48 passed; 14 contract examples/responses valid; lock checked. Real user 001 rerun tái tạo output chính xác; tám real outputs thỏa dwell/audit invariants.
- Chưa có mentor approval hoặc independent semantic labels. OpenAPI được bàn giao cho người dùng chuyển review; không có endpoints, cloud hoặc GitHub push.
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
