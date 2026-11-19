# CP2 · So sánh model và tiêu chí release

## So sánh trên GeoLife

Hai lượt CLI đã lưu bao phủ **182 user, 18.670 trajectories, 24.876.978 điểm gốc**
và **24.177.772 điểm sau làm sạch**. Cả hai dùng pipeline `0.2.0`, `baseline-v1` và
toàn bộ lịch sử của từng user. Phạm vi trong audit, coverage, chẩn đoán trước gom cụm
và **10.339 bản ghi lần dừng** khớp. Audit cũ chưa lưu hash của GPS đầu vào. [Báo cáo CP1](../cp1/benchmark.md)

| Chỉ số | `heuristic-v1` | `dbscan-v1` |
| --- | ---: | ---: |
| Cụm | 3.577 | 552 |
| Lần dừng bị gắn nhãn nhiễu | 0 | 3.296 (31,88%) |
| POI | 265 | 202 |
| User có gợi ý Home | 28 (15,38%) | 37 (20,33%) |
| User có gợi ý Office | 8 (4,40%) | 18 (9,89%) |

| Vai trò | Cả hai `unknown` | Heuristic `unknown` → DBSCAN gợi ý | Heuristic gợi ý → DBSCAN `unknown` | Cả hai gợi ý | Cách nhau ≤200 m | Trung vị khoảng cách |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Home | 145 | 9 | 0 | 28 | 28/28 | 0,42 m |
| Office | 164 | 10 | 0 | 8 | 8/8 | 2,54 m |

Ngưỡng 200 m từ CP1 mô tả mức đồng thuận theo khoảng cách Haversine giữa hai gợi ý.
GeoLife thiếu nhãn Home và Office độc lập nên độ đúng của các gợi ý bổ sung chưa được xác nhận.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/compare_release_models.py
```

Script tạo `summary.json`, `user-metrics.csv` và `user-role-comparison.csv` trong
`artifacts/cp2/model-comparison/`.

## Ca kiểm tra bắt buộc

Các ca GPS tổng hợp dùng `baseline-v1`, timezone `Asia/Shanghai` và dung sai **25 m**
cho mỗi tọa độ gợi ý.

| Ca | Home kỳ vọng | Office kỳ vọng |
| --- | --- | --- |
| Năm lần ghé đêm và năm lần ghé giờ làm, qua hai tuần | 39,9000° N · 116,3000° E | 39,9300° N · 116,3400° E |
| Năm lần ghé đêm, qua hai tuần | 39,9000° N · 116,3000° E | `unknown` |
| Một lần dừng 10 phút | `unknown` | `unknown` |

Cả hai model đã qua ba ca khi gọi API v1 qua WSGI. Chạy lại bằng lệnh sau.

```powershell
py -X utf8 -m pytest -q tests/test_contract_cli.py -k release_location_expectations
```

Trước canary, kiểm tra các ca tọa độ trên bản đã đóng gói và xác nhận model, pipeline, hash
cấu hình và snapshot thực thi. Với API v2, đối chiếu user `101` với JSON CLI của từng model.
Kiểm tra cả ID vắng, ID sai kiểu, ID có số 0 đầu, lịch sử ngắn và lịch sử vượt giới hạn.

## Benchmark Lambda local

Ngày 2026-11-12, cùng image `geolife-lambda:local` (`def73db5f385`) chạy với PostgreSQL local,
snapshot `geolife-1.3`, pipeline `0.2.0` và `baseline-v1`. Mỗi cặp lịch sử và model có
một container riêng, giới hạn 2 CPU và 2 GiB, một lượt warmup và năm lượt đo. Ba user được
chọn theo p10, p50 và max về số điểm trong 128 lịch sử có từ 1 đến 100.000 điểm.

| User | Điểm GPS | Model | DB p50 (ms) | Suy luận p50 (ms) | Handler p50 (ms) | Handler max (ms) | Peak RSS (MiB) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 117 · ngắn | 341 | `heuristic-v1` | 33,8 | 55,0 | 89,1 | 99,9 | 169,0 |
| 117 · ngắn | 341 | `dbscan-v1` | 36,1 | 63,0 | 100,2 | 195,3 | 170,5 |
| 145 · điển hình | 9.907 | `heuristic-v1` | 137,1 | 103,2 | 247,4 | 364,1 | 177,5 |
| 145 · điển hình | 9.907 | `dbscan-v1` | 134,8 | 96,7 | 232,9 | 256,7 | 177,5 |
| 125 · dài | 96.522 | `heuristic-v1` | 1.175,5 | 892,6 | 2.050,4 | 2.360,0 | 251,7 |
| 125 · dài | 96.522 | `dbscan-v1` | 1.082,0 | 867,2 | 1.951,8 | 2.244,6 | 253,5 |

Cả 30 lượt đo đều trả HTTP 200 ở handler. Với lịch sử điển hình và dài, đọc DB chiếm
55,4–58,2% thời gian handler theo trung vị tỷ lệ của từng lượt. Số đo DB gồm mở kết nối,
truy vấn, nhận dữ liệu và dựng DataFrame. Peak RSS tính cho tiến trình Python từ khi khởi
động đến hết lượt đo. [Lệnh benchmark](../../README.md#đo-hiệu-năng-lambda-local)

Số đo từng lượt và image ID đầy đủ nằm trong `artifacts/cp2/lambda-local-benchmark.json`.
Kế hoạch hiện tại đo cold start và p95 đầu cuối trên [Knative local](../../docs/cp2-knative-deploy.md)
trước khi chốt ngưỡng canary.

## Canary Knative local ngày 2026-11-17

Người dùng đã tạo cluster Docker Desktop Kubernetes `v1.36.1`, cài Knative Serving và Kourier,
deploy Blue và Green. Hai Revision qua Kourier đều trả HTTP 200, khớp toàn bộ JSON CLI user `101`
và qua kiểm tra ID vắng, ID kiểu số. Một lượt `sample --requests 100` qua URL live cho kết quả sau.

| Model | Trọng số | Request thành công | p95 phía client |
| --- | ---: | ---: | ---: |
| `heuristic-v1` | 90% | 88 | 594 ms |
| `dbscan-v1` | 10% | 12 | 5.219 ms |

Tổng 100 lượt có 0 lỗi. Lượt đo này xác nhận chia traffic trên cluster. Cỡ mẫu theo model
chưa đạt mức 100 lượt mỗi bản trong bảng đề xuất. Script tính p95 theo nearest rank, nên p95
của 12 lượt Green là giá trị lớn nhất trong mẫu. Chưa có từng latency và log cold start để
xác định nguyên nhân. P95 Green vượt mốc đề xuất 5 giây và cần đo bổ sung trước khi chọn promote.

Sau lượt canary, người dùng rollback về Blue và kiểm tra cùng URL live. HTTP 200,
`model_version=heuristic-v1`, kết quả user `101` khớp CLI; các ca ID vắng và ID sai kiểu đều qua.
Stopwatch phía PowerShell ghi 11,5309006 giây cho chuỗi lệnh rollback và toàn bộ lượt kiểm thử.
Thời gian này gồm các lệnh CLI và request kiểm tra. Độ trễ đổi Route riêng chưa được đo tách.

Sau thời gian rảnh, hai request liên tiếp đến `/version` của Blue đều trả 200, cùng cấu hình.
Lần đầu mất 4,283861 giây, lần sau 0,010708 giây. Chưa có output xác nhận pod bằng 0 và sự kiện
pod trong lượt báo cáo, nên đây là số đo sau thời gian rảnh và lượt ngay sau đó. Cần đối chiếu
vòng đời pod để xác nhận cold start. Endpoint `/version` chỉ trả metadata; thời gian suy luận
GPS cần đo riêng qua `/v2/locations/infer`.

### Đo riêng từng Revision sau warmup

Người dùng chạy `sample --track green --warmup 1 --requests 100`, sau đó chạy tương tự cho
Blue. Cả hai gọi suy luận user `101`, cùng snapshot và cấu hình, tuần tự qua Kourier.

| Model | Warmup được loại khỏi p95 | Lượt đo thành công | Lỗi | p95 lượt đo |
| --- | ---: | ---: | ---: | ---: |
| `dbscan-v1` | 4.969 ms | 100 | 0 | 563 ms |
| `heuristic-v1` | 5.000 ms | 100 | 0 | 594 ms |

P95 Green bằng khoảng 94,8% p95 Blue. Với workload user `101` sau warmup, hai bản đạt cỡ mẫu
và các mốc p95 đề xuất. Lượt đo này dùng từng URL tag tuần tự, khác với lượt canary có hai bản
nhận traffic xen kẽ. Các lần warmup chậm phù hợp với khả năng có chi phí khởi động; chưa có
log vòng đời pod để xác nhận nguyên nhân của từng request. Client hiện chờ tối đa 60 giây,
nên phép đo chưa kiểm tra deadline 10 giây ở bảng đề xuất. Các độ dài lịch sử khác còn cần đo.

Sau promote, người dùng gọi lại URL live và xác nhận HTTP 200, `model_version=dbscan-v1`,
pipeline `0.2.0`, cấu hình `baseline-v1`, kết quả user `101` khớp JSON CLI. Có 13.738 điểm,
29 lần dừng, 3 địa điểm, Home `predicted`, Office `unknown`. Các ca ID vắng và ID kiểu số đều qua.

## Scale-to-zero và cold start trên Knative ngày 2026-11-18

Đo qua Kourier trên Docker Desktop với `POST /v2/locations/infer`, body chỉ có `user_id=101`
và snapshot `geolife-1.3-demo-v1` (13.738 điểm cho user này). Với từng URL tag, xác nhận danh sách
pod của Revision trống, gửi hai request liên tiếp rồi quan sát pod mới Ready. Route live lúc đo
có Blue 0% và Green 100%.

| Revision | Pod trước lượt gọi đầu | Lượt gọi đầu | Lượt gọi ngay sau | Pod sau lượt đo |
| --- | ---: | ---: | ---: | --- |
| Blue (`heuristic-v1`) | 0 | 5.037 ms | 543 ms | 2 pod, có pod Ready |
| Green (`dbscan-v1`) | 0 | 6.177 ms | 568 ms | 2 pod, có pod Ready |

Cả bốn request trả HTTP 200 và khớp toàn bộ JSON CLI sau khi bổ sung metadata config và snapshot
cho bản đối chiếu. Số đo là thời gian phía client qua port-forward. Mỗi dòng là một cặp request;
số p95 sau warmup ở lượt 100 request đã ghi riêng. `artifacts/cp2/knative-cold-start.json` lưu dấu
thời gian, tên và UID pod mới, latency chưa làm tròn và kết quả đối chiếu.

## Canary Knative với PostgreSQL ngày 2026-11-19

Hai Revision trong `geolife-knative-postgres` dùng image `dev.local/geolife-api:0.2.0-postgres`
và cùng snapshot PostgreSQL `geolife-1.3-full-v1`. Snapshot có 182 user, 24.876.978 điểm GPS
và 108 kết quả tính trước cho lịch sử dài. API qua hai URL preview khớp toàn bộ JSON CLI cho
`101` (13.738 điểm, suy luận khi gọi) và `153` (2.156.994 điểm, dùng kết quả tính trước).

| Revision | Trọng số canary | Request thành công | P95 đầu cuối |
| --- | ---: | ---: | ---: |
| Blue `heuristic-v1` | 90% | 88/100 | 938 ms |
| Green `dbscan-v1` | 10% | 12/100 | 890 ms |

Gửi 100 request suy luận cho `101` qua URL live, ghi nhận 0 lỗi. P95 mô tả lần diễn tập,
với 12 mẫu ở Green. Promote trả `dbscan-v1`, rollback trả `heuristic-v1` trên cùng URL, đều
khớp CLI. Đổi Route về Blue mất khoảng 1,3 giây. Toàn bộ thao tác rollback và kiểm tra API
mất 8,55 giây. Sau diễn tập, live ở Blue 100% và Green vẫn có URL preview.

Khi từng Revision đang ở 0 pod, request suy luận đầu tiên của Blue mất 6.437 ms và Green
mất 6.688 ms. Request kế tiếp lần lượt mất 938 ms và 781 ms. Đây là phép đo từng cặp request
qua URL preview khi làm nóng Revision.

Lượt đầu dừng ở canary khi PostgreSQL ngừng chạy và API trả 503. Instance ban đầu báo lỗi
checkpoint khi khởi động lại. Lượt hoàn tất dùng một instance nạp lại từ snapshot full tại
`artifacts/cp2/postgres-knative-rehearsal/data`. Xem `artifacts/cp2/knative-postgres-rollout.log`
cho lần đầu và `artifacts/cp2/knative-postgres-restored.log` cho lần hoàn tất.

## Kiểm tra gói MLflow ngày 2026-11-18

Đã tạo script `scripts/register_mlflow_models.py` và wrapper thực thi
`scripts/mlflow_geolife_model.py`. Gói model có code, cấu hình và snapshot SQLite để gọi
suy luận bằng `user_id`. Hai thuật toán được lưu thành version của `geolife-home-office`
và gắn alias theo tên thuật toán sau khi tải lại version và kiểm tra thành công.

Lượt kiểm tra dùng MLflow 3.18.0 với thư viện core đã khóa, backend riêng tại
`artifacts/cp2/mlflow-check/`. Từng model được tải trong tiến trình mới chạy ngoài repo;
đã xác nhận import code từ bundle và đối chiếu mọi trường JSON CLI cho toàn bộ snapshot:
user `101`, `117`, `125`, `145`, tổng 120.508 GPS points. Cả hai bản khớp trước và sau
đăng ký; ID số, rỗng, quá dài và vắng đều bị từ chối. Ba regression tests qua, gồm tải
model sau khi xóa artifact nguồn và từ chối snapshot/config trong bundle bị sửa.

Lượt đăng ký vào server local tại `http://127.0.0.1:5001` đã hoàn tất. Trong
`geolife-home-office`, alias `heuristic-v1` trỏ version 1 và alias `dbscan-v1` trỏ version 2.
Cả hai `READY`, run `FINISHED`, tag `cli_parity=passed`. Báo cáo
`artifacts/cp2/mlflow/registration.json` xác nhận hai bản tải lại đều khớp CLI trên toàn bộ
snapshot demo. Cả hai ghi ID image local
`sha256:9af6aa69e5b48342e37b566c6b01b8e7489db523c91d65527f8c9cfc13ba864e`.
Tên Knative Revision trong manifest là liên kết khai báo. Đối chiếu registry sử dụng gói model đã lưu.

## Ngưỡng canary đề xuất cho demo

Dùng `heuristic-v1` làm bản Blue đối chứng và `dbscan-v1` làm bản Green thử nghiệm. Cả hai dùng chung snapshot,
`baseline-v1` và tập request hợp lệ có các độ dài lịch sử đã đo. Chạy riêng các ca cố ý gửi input sai.

| Tiêu chí | Ngưỡng đề xuất |
| --- | --- |
| Chức năng | Qua toàn bộ ca bắt buộc và metadata khớp với bản thực thi. |
| Cỡ mẫu | Tối thiểu 100 lượt gọi hợp lệ được gán cho mỗi bản. |
| Mã HTTP bất ngờ | Tối đa 1% số lượt hợp lệ được gán cho mỗi bản. |
| Timeout phía client | Deadline 10 giây, 0 timeout trong mẫu của mỗi bản. |
| p95 đầu cuối | Tối đa 5 giây mỗi bản. p95 DBSCAN đồng thời tối đa 120% p95 heuristic khi đo cùng tập request và mức tải. |

Đo latency từ lúc client gửi request đến khi nhận xong response. Tính p95 trên các lượt thành công
và báo kèm số lỗi, timeout và cỡ mẫu theo version. Dùng log phía server để quy lỗi cho version
khi response thiếu metadata. Ghi riêng số lỗi chưa quy được version và xử lý chúng trước khi promote.
Mốc 5 giây, deadline 10 giây và mức chênh 20% là ngưỡng ban đầu cho demo. Xác nhận lại bằng
số đo baseline Knative và thời gian chờ của màn hình chọn điểm đến. Mẫu canary 100 request tổng
trong hướng dẫn chạy dùng để minh họa phân luồng. Khi so với bảng trên, dùng cỡ mẫu theo từng model.

**Đánh giá để chọn phiên bản** dùng các ca chức năng trên bản đã đóng gói và số đo từ Knative.
**Cải thiện độ đúng của gợi ý** cần tập có nhãn độc lập và tiêu chí cải thiện được chốt trước.
