# GeoLife Home / Office / POI Inference

Dự án dùng dữ liệu GPS GeoLife để suy luận vị trí có thể là nhà, nơi làm việc
và các địa điểm thường ghé (POI).

## Pipeline

`GPS thô → làm sạch → phát hiện lần dừng → gom địa điểm → suy luận theo thời gian`

Hai model dùng chung bước làm sạch, phát hiện lần dừng và suy luận vai trò.
`heuristic-v1` gom các lần dừng theo bán kính quanh điểm neo cố định.
`dbscan-v1` gom theo mật độ bằng DBSCAN với khoảng cách Haversine.
Pipeline có giao diện CLI và API kiểm thử local. [Kiến trúc](docs/architecture.md) · [OpenAPI](openapi.yaml)

## Phiên bản suy luận

| Trường | Ý nghĩa |
|---|---|
| `model_version` | Cách gom cụm, `dbscan-v1` (mặc định) hoặc `heuristic-v1`. |
| `pipeline_version` | Phiên bản core thực thi các bước suy luận, hiện là `0.2.0`. |
| `config_version` | Bộ tham số khớp với cấu hình thực chạy. `baseline-v1` dùng bán kính lần dừng 100 m và tối thiểu 10 phút. `stay150-experiment-v1` chỉ tăng bán kính lần dừng lên 150 m. Các cấu hình khác mang tên `custom`. |
| `config_sha256` | Dấu vân tay của toàn bộ cấu hình thực chạy. Response và `run-audit.json` cũng ghi đầy đủ các tham số trong `config`. |

Trong request v1, dùng `"config_version": "stay150-experiment-v1"` để thử 150 m hoặc dùng
`config` để gửi tham số riêng. Nếu bỏ cả hai, API dùng `baseline-v1`. Để quay về 100 m,
gửi lại cùng GPS và `model_version` với `"config_version": "baseline-v1"`.
CLI chọn cùng preset bằng `--config-version stay150-experiment-v1`. Đặt `--output` riêng cho
mỗi lần chạy để giữ kết quả đối chiếu. Khi tái lập cấu hình `custom`, dùng các giá trị trong
`config` của kết quả đã lưu.

## Chạy API bằng Docker

Khởi động Docker Desktop ở chế độ Linux containers. Từ PowerShell ở gốc repo, build image và chạy container:

```powershell
docker build -t geolife-api:0.2.0-cp2 .
docker run --rm --name geolife-api-local --cpus 2 --memory 2g -p 127.0.0.1:8001:8000 geolife-api:0.2.0-cp2
```

Dockerfile cài các thư viện API theo `uv.lock`. API lắng nghe cổng `8000` trong container.
Mapping `127.0.0.1:8001:8000` cho phép máy local gọi `http://127.0.0.1:8001/v1/locations/infer`.
Image chứa code và OpenAPI. Dữ liệu GPS và kết quả CLI nằm trên máy để phục vụ đối chiếu.

Khi container báo API đã lắng nghe, mở PowerShell thứ hai ở gốc repo và chạy kiểm tra:

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/check_local_api.py --port 8001
```

Script đối chiếu user 101 với JSON CLI đã lưu, thử hai preset trên cùng ba điểm GPS tổng hợp,
và kiểm tra lỗi `422` khi thiếu `latitude`. Dừng container bằng `Ctrl+C` ở cửa sổ đang chạy.

## Thử API với PostgreSQL local

Dùng một database PostgreSQL local dành cho GeoLife. Từ PowerShell ở gốc repo, đặt
`GEOLIFE_POSTGRES_DSN` theo kết nối thực tế. Ví dụ dưới đây dùng PostgreSQL trên cổng `55432`.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
$env:GEOLIFE_POSTGRES_DSN = 'host=127.0.0.1 port=55432 dbname=postgres user=geolife'
uv pip install --python .venv/Scripts/python.exe 'psycopg[binary]==3.3.0'
py -X utf8 scripts/import_postgres.py --user-id 101
py -X utf8 -m geolife_inference.api
```

Mở PowerShell thứ hai ở gốc repo để gửi request `{"user_id":"101"}` tới
`POST /v2/locations/infer` và đối chiếu với JSON CLI đã lưu.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/check_local_api.py --postgres
```

API tra lịch sử theo ID chuỗi trong snapshot `geolife-1.3`, dùng `dbscan-v1` và `baseline-v1`.
Để đổi snapshot, đặt cùng `GEOLIFE_SNAPSHOT_ID` khi import, khởi động API và kiểm tra.
Import lại cùng dữ liệu trong cùng snapshot giữ nguyên số bản ghi. API trả `404` nếu
snapshot thiếu lịch sử cho ID, và `422` nếu lịch sử vượt 100.000 điểm.

Khi PostgreSQL đang chạy, dùng lệnh sau để kiểm tra import lặp, ID `001`, lịch sử một điểm
và lịch sử 100.001 điểm. Script mở API trên cổng tạm và tự dọn snapshot kiểm tra.

```powershell
$env:GEOLIFE_POSTGRES_DSN = 'host=127.0.0.1 port=55432 dbname=postgres user=geolife'
py -X utf8 scripts/check_local_api.py --postgres-edge-cases
```

## Build và thử Lambda local

Mở Docker Desktop ở chế độ Linux containers. Dùng PostgreSQL local đã nạp user `101` như trên.
Từ PowerShell ở gốc repo, build image một lần và chạy hai container với `MODEL_VERSION` tương ứng.
Ví dụ dùng PostgreSQL Windows trên cổng `55432`, qua địa chỉ Docker Desktop `host.docker.internal`.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
$lambdaDsn = 'host=host.docker.internal port=55432 dbname=postgres user=geolife'
docker buildx build --platform linux/amd64 --provenance=false --load -f Dockerfile.lambda -t geolife-lambda:local .
docker run -d --rm --name geolife-lambda-heuristic-19002 -p 127.0.0.1:19002:8080 -e "GEOLIFE_POSTGRES_DSN=$lambdaDsn" -e MODEL_VERSION=heuristic-v1 geolife-lambda:local
docker run -d --rm --name geolife-lambda-dbscan -p 127.0.0.1:19001:8080 -e "GEOLIFE_POSTGRES_DSN=$lambdaDsn" -e MODEL_VERSION=dbscan-v1 geolife-lambda:local
```

Gọi trình mô phỏng Lambda và so kết quả từng container với JSON CLI của cùng model.

```powershell
py -X utf8 scripts/check_local_api.py --lambda-runtime --port 19002 --expected artifacts/pipeline/heuristic-v1/101-heuristic-v1.json
py -X utf8 scripts/check_local_api.py --lambda-runtime --port 19001
docker stop geolife-lambda-heuristic-19002 geolife-lambda-dbscan
```

Handler nhận event HTTP API payload format 2.0. Body suy luận chứa `{"user_id":"101"}`.
Image dùng Python 3.12 trên Amazon Linux 2023, ghim `baseline-v1` và mặc định tra snapshot
`geolife-1.3`. Đặt `GEOLIFE_SNAPSHOT_ID` nếu chạy trên snapshot khác.

### Đo hiệu năng Lambda local

Khi Docker Desktop và PostgreSQL đang chạy, dùng image `geolife-lambda:local` đã build.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/benchmark_lambda_local.py
```

Script nạp lịch sử đầy đủ của ba user vào PostgreSQL. Ba user lần lượt có số điểm ở p10, p50 và
mức cao nhất trong 128 lịch sử có từ 1 đến 100.000 điểm. Mỗi cặp user và model chạy trong một
container tạm với 2 CPU và 2 GiB, warmup một lần rồi đo năm lần. File kết quả
`artifacts/cp2/lambda-local-benchmark.json` ghi từng lượt đo, trung vị và peak RSS của tiến trình.
Thời gian handler gồm đọc DB, suy luận và tạo response. Số đo dành cho handler local, còn HTTP,
khởi động container và cold start AWS cần đo riêng.

### Thử Lambda với snapshot SQLite

Chạy từ thư mục gốc trong PowerShell. Snapshot demo chứa toàn bộ lịch sử của user `101`,
`117`, `125` và `145`.

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 scripts/export_sqlite_snapshot.py --users 101 117 125 145 --snapshot geolife-1.3-demo-v1
docker buildx build --platform linux/amd64 --provenance=false --load --target sqlite-demo --build-context demo_snapshot=artifacts/cp2/sqlite -f Dockerfile.lambda -t geolife-lambda:sqlite-demo .
docker run -d --rm --name geolife-sqlite-blue -p 127.0.0.1:19102:8080 -e MODEL_VERSION=heuristic-v1 geolife-lambda:sqlite-demo
docker run -d --rm --name geolife-sqlite-green -p 127.0.0.1:19101:8080 -e MODEL_VERSION=dbscan-v1 geolife-lambda:sqlite-demo
py -X utf8 scripts/check_local_api.py --lambda-runtime --port 19102 --snapshot geolife-1.3-demo-v1 --expected artifacts/pipeline/heuristic-v1/101-heuristic-v1.json
py -X utf8 scripts/check_local_api.py --lambda-runtime --port 19101 --snapshot geolife-1.3-demo-v1
docker stop geolife-sqlite-blue geolife-sqlite-green
```

Các bước đưa image demo lên AWS nằm trong [hướng dẫn triển khai SQLite](docs/cp2-sqlite-deploy.md).

### Demo CP2 trên Kubernetes local

Demo serverless, canary 90/10 và rollback trên cùng URL dùng
[Knative Serving và Kourier](docs/cp2-knative-deploy.md).

Chạy hai phiên bản API với snapshot SQLite, kiểm tra Green qua Service preview rồi chuyển và
rollback qua cùng Service live. [Hướng dẫn triển khai Kubernetes](docs/cp2-kubernetes-deploy.md)

## Dữ liệu và giới hạn

Home và Office là ứng viên suy ra từ hành vi. Kết quả có thể là `unknown`
khi thiếu bằng chứng, và điểm bằng chứng không biểu thị xác suất.
GeoLife không có nhãn độc lập để kiểm chứng độ chính xác Home/Office.
GPS thưa, nhiễu vị trí và giờ sinh hoạt khác giả định đều có thể ảnh hưởng kết quả.

Xem điều khoản sử dụng trong GeoLife User Guide 1.3. Dữ liệu GPS và kết quả
chứa tọa độ cá nhân được giữ ngoài Git.

## Tài liệu dự án

- [Notebook](notebooks/README.md) — khám phá dữ liệu và từng bước của pipeline.
- [Báo cáo benchmark CP1](reports/cp1/benchmark.md) — so sánh làm sạch, phát hiện lần dừng và độ ổn định Home/Office.
- [Kế hoạch](PLAN.md) · [Checkpoint](CHECKPOINT.md) — tiến độ, bàn giao và lệnh chạy.
