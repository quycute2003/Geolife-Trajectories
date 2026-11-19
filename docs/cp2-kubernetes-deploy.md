# CP2 · GeoLife trên Kubernetes local

> Demo với scale-to-zero và canary theo trọng số dùng [Knative Serving](cp2-knative-deploy.md).

Demo chạy trên Docker Desktop với một snapshot SQLite chỉ đọc gồm user `101`, `117`, `125`
và `145`. Hai Deployment dùng chung image. Blue chạy `heuristic-v1`, Green chạy `dbscan-v1`.
Service `geolife-live` phục vụ Blue lúc bắt đầu, còn `geolife-preview` cho phép kiểm thử Green.
Cả hai đọc cùng snapshot `geolife-1.3-demo-v1` với cấu hình `baseline-v1`.

## Khởi động

Mở Docker Desktop, chọn **Kubernetes → Create cluster → Kubeadm** và đợi cluster sẵn sàng.
Chạy các lệnh sau trong PowerShell tại thư mục gốc của repo.

```powershell
kubectl --context docker-desktop get nodes
docker buildx build --load --target sqlite-demo --build-context demo_snapshot=artifacts/cp2/sqlite -t geolife-api:0.2.0-sqlite-demo .
kubectl --context docker-desktop apply -f infra/k8s/geolife-demo.yaml
kubectl --context docker-desktop -n geolife rollout status deployment/geolife-blue --timeout=180s
kubectl --context docker-desktop -n geolife rollout status deployment/geolife-green --timeout=180s
```

Nếu chưa có `artifacts/cp2/sqlite/geolife.sqlite3`, tạo snapshot từ dữ liệu GeoLife local trước
khi build.

```powershell
.\.venv\Scripts\python.exe scripts/export_sqlite_snapshot.py --users 101 117 125 145 --snapshot geolife-1.3-demo-v1
```

## Kiểm thử Blue và Green

Giữ cửa sổ PowerShell này mở trong lúc kiểm thử. Proxy chỉ lắng nghe trên loopback và chỉ
cho phép ba route của hai Service demo.

```powershell
kubectl --context docker-desktop proxy --address 127.0.0.1 --port 18080 --accept-paths '^/api/v1/namespaces/geolife/services/geolife-(live|preview):http/proxy/(health|version|v2/locations/infer)$'
```

Trong cửa sổ PowerShell thứ hai tại thư mục repo, kiểm tra API với JSON CLI của user `101`.

```powershell
$live = '/api/v1/namespaces/geolife/services/geolife-live:http/proxy'
$preview = '/api/v1/namespaces/geolife/services/geolife-preview:http/proxy'
$snapshot = 'geolife-1.3-demo-v1'
$blue = 'artifacts/pipeline/heuristic-v1/101-heuristic-v1.json'
$green = 'artifacts/pipeline/dbscan-v1/101-dbscan-v1.json'
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --base-path $live --snapshot $snapshot --expected $blue
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --base-path $preview --snapshot $snapshot --expected $green
```

## Chuyển traffic và rollback

Sau khi cả hai kiểm thử đều báo `full CLI match`, chuyển Service live sang Green, rồi gọi lại
cùng URL live. Blue vẫn sẵn sàng để quay về.

```powershell
kubectl --context docker-desktop -n geolife set selector service/geolife-live 'app=geolife-inference,track=green'
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --base-path $live --snapshot $snapshot --expected $green

$rollback = [Diagnostics.Stopwatch]::StartNew()
kubectl --context docker-desktop -n geolife set selector service/geolife-live 'app=geolife-inference,track=blue'
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --base-path $live --snapshot $snapshot --expected $blue
if ($LASTEXITCODE -eq 0) { "Rollback và kiểm tra API mất $($rollback.Elapsed.TotalSeconds) giây" }
```

Nếu EndpointSlice chưa cập nhật ngay sau khi đổi selector, đợi vài giây rồi kiểm tra lại bằng
cùng URL. Số đo gồm lệnh đổi selector và toàn bộ lượt kiểm thử API từ máy local.

Kết quả cần lưu gồm phiên bản trước và sau khi chuyển, kết quả đối chiếu CLI, và thời gian
rollback. Blue-green ở đây chuyển toàn bộ request mới sang phiên bản được chọn. Kiểm tra
Green qua preview trong lúc Blue phục vụ live là bước chuẩn bị trước khi chuyển.

Khi xong, dừng `kubectl proxy` bằng `Ctrl+C`. Xóa tài nguyên demo bằng lệnh sau nếu cần dọn.

```powershell
kubectl --context docker-desktop delete -f infra/k8s/geolife-demo.yaml
```
