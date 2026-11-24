# Kế hoạch CP2 · Triển khai và phát hành canary cho GeoLife

Cập nhật **2026-11-24**. CP2 bàn giao API gợi ý điểm đến, hai phiên bản model truy vết được
và bằng chứng scale-to-zero, canary, promote và rollback. Đã diễn tập trên Docker Desktop với
Knative Serving, Kourier và PostgreSQL local. Bước còn lại là kiểm chứng API nội bộ trên GKE
với Cloud SQL for PostgreSQL. Yêu cầu AWS ban đầu được ghi trong [quy trình đã thử](cp2-sqlite-deploy.md).

Client gửi `user_id` tại `POST /v2/locations/infer`. API đọc lịch sử GeoLife rồi trả gợi ý
Home, Office, POI và metadata bản thực thi. Hai Revision dùng cùng snapshot PostgreSQL
`geolife-1.3-full-v1` và cấu hình `baseline-v1`. Các lượt kiểm tra SQLite dùng snapshot demo
`geolife-1.3-demo-v1` được ghi lại ở các mục bên dưới.

Bản cloud đã chốt PostgreSQL cho hai Revision. Nạp snapshot `geolife-1.3-full-v1` và kết quả
đã tính cho các lịch sử dài bằng `scripts/import_postgres.py --sqlite`. API dùng cùng request
`user_id`. Xem [hướng dẫn PostgreSQL](cp2-knative-deploy.md#postgresql-cho-bản-cloud).

```text
Dữ liệu       GeoLife PLT → snapshot SQLite → PostgreSQL local hoặc Cloud SQL
Suy luận      Client → Kourier áp dụng Knative Route
                     → heuristic-v1 hoặc dbscan-v1 → API đọc PostgreSQL
Truy vết      Revision / image / config / snapshot → hồ sơ phát hành và MLflow local
```

## 1. Tuần 3 · API local và đối chiếu

- [x] Chốt contract cho request có `user_id` dạng chuỗi. Response ghi `model_version`,
  `pipeline_version`, `config_version`, `config_sha256` và `data_snapshot_id`.
  Vai trò thiếu bằng chứng trả `unknown`.
- [x] Kiểm tra đầu cuối HTTP → PostgreSQL local → pipeline với user `101`. HTTP 200
  và toàn bộ trường trong JSON CLI khớp. Có 13.738 điểm GPS, 29 lần dừng, 3 cụm, Home
  `predicted` và Office `unknown` ở bản DBSCAN. ID vắng trả 404, ID kiểu số trả 422.
- [x] Kiểm thử import lặp, ID `"001"`, lịch sử một điểm và lịch sử 100.001 điểm qua
  PostgreSQL local. Import lặp giữ 13.738 bản ghi. ID `"001"` được giữ nguyên. Lịch sử
  một điểm trả hai vai trò `unknown`. Lịch sử 100.001 điểm trả 422 `history_too_large`.
- [x] Chuẩn bị snapshot SQLite có 120.508 điểm của user `101`, `117`, `125` và `145`.
  Kiểm tra HTTP local với SQLite cho user `101` trên cả hai model, khớp JSON CLI
  và qua các ca ID vắng, ID kiểu số.

## 2. Tuần 3 · So sánh phiên bản và tiêu chí release

- [x] So ghép cặp `heuristic-v1` và `dbscan-v1` từ JSON CLI của toàn bộ 182 user với
  `baseline-v1`. Coverage và 10.339 lần dừng khớp. Đã ghi số cụm, nhiễu, tỷ lệ
  gợi ý, mức đồng thuận và kết quả từng user. [Báo cáo CP2](../reports/cp2/release.md)
- [x] Chạy ba ca GPS tổng hợp có đáp án cho mỗi model qua WSGI. Sáu lượt đạt kết quả
  kỳ vọng với dung sai tọa độ 25 m. GeoLife chưa có nhãn Home và Office độc lập để đo độ đúng.
- [x] Lưu số đo handler trên Docker local với PostgreSQL làm tham chiếu lịch sử.
  Có 30 lượt trên ba độ dài lịch sử và hai model. Ca dài 96.522 điểm có handler p50
  1,95–2,05 giây, peak RSS 251,7–253,5 MiB. Đây là số đo handler Lambda local.
  [Benchmark và tiêu chí đã đề xuất](../reports/cp2/release.md#benchmark-lambda-local)
- [ ] Đo baseline đầu cuối trên Knative qua Kourier, gồm cold start và request khi pod
  đã sẵn sàng. Dùng số đo cluster để cập nhật ngưỡng đề xuất cho lỗi, timeout và p95.
  Chạy lại các ca chức năng trên image HTTP đã đóng gói.

## 3. Tuần 4 · Triển khai local và xác minh phiên bản

- [x] Chuẩn bị Dockerfile HTTP có target `sqlite-demo`, [manifest Knative](../infra/knative/geolife-demo.yaml),
  [script rollout](../scripts/knative_rollout.py) và [hướng dẫn chạy](cp2-knative-deploy.md).
  Bộ test gần nhất có 126 ca pass. Đã kiểm tra trình tự rollout bằng mô phỏng và bộ đếm
  request bằng HTTP local.
- [x] Tạo cluster Docker Desktop với provisioner Kubeadm, kiểm tra phiên bản server và cài
  Knative Serving + Kourier tương thích. Build image local
  `dev.local/geolife-api:0.2.0-sqlite-demo` từ snapshot đã lưu.
- [x] Deploy Knative Service `geolife-inference` trong namespace `geolife-knative`.
  Blue là Revision `geolife-inference-blue` với `heuristic-v1`. Sau khi Blue sẵn sàng,
  chạy `stage` để tạo Green là `geolife-inference-green` với `dbscan-v1`.
- [x] Qua Kourier port-forward, kiểm tra `/health`, `/version` và suy luận user `101`
  tại URL có tag của từng Revision. Đối chiếu JSON CLI, hash cấu hình và snapshot.
- [x] Ngừng gọi API và kiểm tra danh sách pod của từng Revision trống. Gọi suy luận cho user
  `101` qua URL tag, quan sát pod mới Ready và đối chiếu CLI. Request đầu Blue 5.037 ms,
  Green 6.177 ms. Request ngay sau lần lượt 543 ms và 568 ms.
- [x] Dựng MLflow Model Registry local và đăng ký hai bản. Mỗi bản ghi phiên bản model,
  Revision, Git commit, tag và ID image local, pipeline, hash cấu hình, snapshot và
  tham chiếu kết quả kiểm tra. MLflow 3.18.0 tại localhost:5001 có version 1 `heuristic-v1`
  và version 2 `dbscan-v1` trong `geolife-home-office`. Cả hai `READY`, alias đúng,
  khớp CLI cho toàn bộ snapshot demo và có ID image local trong báo cáo đăng ký.
  [Hướng dẫn registry](cp2-knative-deploy.md#chuẩn-bị-mlflow-model-registry-local)

## 4. Tuần 4 · Canary, promote và rollback

CP2 trình diễn **canary**. Kiểm thử bản ứng viên qua URL có tag trước khi cấp traffic live.
Tag `blue` là bản hiện tại (`heuristic-v1`), tag `green` là bản thử nghiệm (`dbscan-v1`).

| Bước | Bản hiện tại | Bản thử nghiệm | Kiểm tra |
| --- | ---: | ---: | --- |
| Stage | 100% | 0% | Gọi URL kiểm thử của bản ứng viên và so với CLI |
| Canary | 90% | 10% | Gửi request vào cùng URL live, kiểm tra hai model đều nhận traffic |
| Promote | 0% | 100% | Cùng URL live trả `dbscan-v1` |
| Rollback | 100% | 0% | Cùng URL live trả lại `heuristic-v1` |

- [x] Sau khi kiểm tra hai Revision, chạy `canary` rồi `sample --requests 100`.
  Script gọi suy luận user `101` qua URL live và ghi số lượt theo `model_version`,
  tổng lỗi và p95 của request thành công theo model. Tỷ lệ quan sát có thể lệch
  tỷ lệ đặt. Lượt ngày 17/11 có 88 Blue, 12 Green, 0 lỗi; p95 tương ứng 594 ms và 5.219 ms.
  [Kết quả canary](../reports/cp2/release.md#canary-knative-local-ngày-2026-11-17)
- [ ] Khi đánh giá hiệu năng để chọn phiên bản, ghi cỡ mẫu theo từng model, độ dài
  lịch sử, cold start, lỗi và timeout. Đối chiếu [ngưỡng đề xuất](../reports/cp2/release.md#ngưỡng-canary-đề-xuất-cho-demo)
  sau khi cập nhật baseline trên Knative. Ngưỡng đề xuất hiện dùng tối thiểu 100 lượt
  hợp lệ **cho mỗi model**, nên mẫu canary minh họa chưa đủ để kết luận đạt ngưỡng.
  Đã đo riêng hai URL tag trên user `101` sau warmup, mỗi model 100 lượt và 0 lỗi.
  P95 Green 563 ms, Blue 594 ms. Hai lượt cold start của user `101` đều dưới 10 giây.
  Còn kiểm tra các độ dài lịch sử khác và đo theo deadline 10 giây.
- [x] Rollback sau canary về Blue và xác nhận HTTP trên cùng URL live khớp CLI heuristic.
  Chuỗi lệnh rollback và toàn bộ lượt kiểm thử mất 11,5309006 giây theo Stopwatch của người dùng.
- [x] Sau promote, xác nhận cùng URL live trả HTTP 200, `dbscan-v1` và kết quả user `101`
  khớp JSON CLI. Các ca ID vắng, ID sai kiểu đều qua. Thời gian đổi Route riêng còn chờ đo.
- [ ] Bàn giao sơ đồ, URL local, hồ sơ hai phiên bản, kết quả đối chiếu CLI và bằng
  chứng scale-to-zero, canary, promote, rollback. Dừng port-forward và dọn tài nguyên
  demo sau khi lưu kết quả.

Shadow là phương án tham chiếu. Bản hiện tại trả lời client và ứng viên nhận bản sao request để đối chiếu kết quả.

## 5. Kiểm chứng bản triển khai Google Cloud

- [ ] Push image API target `postgres` lên GHCR ở chế độ private và lưu image digest.
- [ ] Nạp snapshot `geolife-1.3-full-v1` vào Cloud SQL với 182 user, 24.876.978 điểm GPS
  và 108 kết quả tính trước. Hai Revision dùng chung snapshot và tài khoản chỉ đọc.
- [ ] Triển khai Knative/Kourier trên GKE. Kiểm tra `/health`, `/version` và đối chiếu API
  v2 với JSON CLI cho user `101` và `153` trên cả hai Revision.
- [ ] Chạy canary 90/10 trên cùng URL. Lưu số lượt theo model, tỷ lệ lỗi và p95. Kiểm chứng
  promote lên 100% ứng viên và rollback về 100% bản ban đầu trên URL đó.
- [ ] Ghi image digest, snapshot, phiên bản model và kết quả kiểm tra cloud vào báo cáo CP2.

[Các lệnh triển khai và kiểm chứng](cp2-knative-deploy.md#postgresql-cho-bản-cloud)

## 6. Kết quả triển khai trước khi đổi hướng

Bản Lambda đã build, chạy được bằng emulator local và cho kết quả khớp JSON CLI.
Đã push image demo vào ECR tại `ap-southeast-2`. CloudFormation dừng ở bước tạo Lambda
với lỗi 403, nên endpoint AWS chưa chạy. Quy trình được ghi lại trong
[hướng dẫn AWS](cp2-sqlite-deploy.md). Sau khi đổi hướng, người dùng đã tạo cluster Kubernetes
`v1.36.1`, kiểm tra hai Revision, canary, rollback và promote qua Kourier. Đã có số đo sau
warmup và cold start có kiểm tra vòng đời pod cho user `101`. Các độ dài lịch sử khác còn cần đo trên Knative.
