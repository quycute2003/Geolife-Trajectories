# CP2 · GeoLife serverless và canary trên Kubernetes local

Knative Serving chạy một Service với hai Revision. Kourier nhận HTTP và chia request theo
trọng số. Blue là `heuristic-v1`, Green là `dbscan-v1`. Hai Revision đọc chung snapshot
PostgreSQL trong demo chính và có thể giảm về 0 pod khi rảnh. Request tiếp theo có thể mất
thêm thời gian khởi động. Các phần SQLite ghi lại cách chạy lượt kiểm chứng trước đó.

## Cài Knative và Kourier

Mở **Docker Desktop → Kubernetes → Create cluster → Kubeadm**. Chạy PowerShell từ thư mục repo.
Kiểm tra `Server Version` với lệnh sau.

```powershell
kubectl --context docker-desktop version
```

Dùng Knative `v1.24.0` trên Kubernetes server từ `1.35`. Với server `1.34`, dùng cả Serving
và Kourier `v1.23.0`. [Phiên bản được hỗ trợ](https://github.com/knative/community/blob/main/mechanics/RELEASE-SCHEDULE.md)

```powershell
$knative = 'knative-v1.24.0'
kubectl --context docker-desktop apply -f "https://github.com/knative/serving/releases/download/$knative/serving-crds.yaml"
kubectl --context docker-desktop wait --for=condition=Established crd/services.serving.knative.dev --timeout=90s
kubectl --context docker-desktop apply -f "https://github.com/knative/serving/releases/download/$knative/serving-core.yaml"
kubectl --context docker-desktop apply -f "https://github.com/knative-extensions/net-kourier/releases/download/$knative/kourier.yaml"
kubectl --context docker-desktop -n knative-serving rollout status deployment/webhook --timeout=180s
kubectl --context docker-desktop -n kourier-system rollout status deployment/3scale-kourier-gateway --timeout=180s
kubectl --context docker-desktop -n knative-serving patch configmap config-deployment --type merge --patch-file infra/knative/local-images.yaml
```

`dev.local` là tên cho image local trong demo. Cấu hình trên bỏ bước tra digest ở registry
cho tên này. [Cài Knative bằng YAML](https://knative.dev/docs/install/serving/install-serving-with-yaml/)

## Tạo snapshot phục vụ toàn bộ GeoLife

Snapshot `geolife-1.3-full-v1` chứa toàn bộ lịch sử GPS. Lệnh export đọc từng trajectory,
đối chiếu số điểm của mỗi user với hai lượt CLI baseline đã chạy và tạo file riêng.
Với lịch sử trên 100.000 điểm, snapshot lưu kết quả CLI từ lịch sử đầy đủ cho từng phiên bản.
API v2 chọn kết quả theo user, model, pipeline và cấu hình. Lịch sử ngắn hơn tiếp tục được
chạy theo request. Request vẫn chỉ cần `user_id`.

Dùng kết quả CLI của chính dataset đầu vào. Khi dữ liệu GPS, pipeline hoặc cấu hình thay đổi,
chạy lại CLI tương ứng trước khi xuất snapshot mới.

```powershell
.\.venv\Scripts\python.exe scripts/export_sqlite_snapshot.py --all-users --cli-results artifacts/pipeline --snapshot geolife-1.3-full-v1 --output artifacts/cp2/sqlite-full/geolife.sqlite3
```

File SQLite full là nguồn để nạp PostgreSQL. Lượt kiểm thử SQLite 4 user được giữ ở phần
[chạy Blue và kiểm tra Green](#chạy-blue-và-kiểm-tra-green).

## Demo PostgreSQL trên Docker Desktop

Demo dùng snapshot `geolife-1.3-full-v1` đã nạp trong PostgreSQL local. Dùng namespace
`geolife-knative-postgres` để hai Revision PostgreSQL có tên và URL riêng, đồng thời giữ lại
bằng chứng từ lượt SQLite. Chạy từ thư mục gốc repo trong PowerShell.

**1. Chuẩn bị image.** Build target `postgres` khi có mạng cho các lớp còn thiếu. Image này
chứa API và driver PostgreSQL. Dữ liệu nằm trong DB.

```powershell
docker buildx build --load --target postgres -t dev.local/geolife-api:0.2.0-postgres .
```

**2. Chuẩn bị PostgreSQL và DSN.** Bật instance demo ở `artifacts/cp2/postgres-knative-rehearsal/data`
nếu đang dừng. Thư mục này được nạp lại từ snapshot full sau khi instance thử nghiệm ban đầu báo lỗi checkpoint.
Nếu dùng máy khác, đặt `$pgRoot` theo thư mục dữ liệu đã nạp trên máy đó.

```powershell
$pgCtl = 'C:/Program Files/PostgreSQL/18/bin/pg_ctl.exe'
$pgRoot = (Resolve-Path 'artifacts/cp2/postgres-knative-rehearsal').Path
& $pgCtl status -D "$pgRoot/data"
if ($LASTEXITCODE -eq 3) {
  & $pgCtl start -D "$pgRoot/data" -l "$pgRoot/server.log" `
    -o "-p 55433 -h 127.0.0.1 -c unix_socket_directories= -c default_transaction_read_only=on" -w
}
```

Đặt `GEOLIFE_POSTGRES_DSN` trong PowerShell với địa chỉ DB mà pod truy cập được và tài khoản
đọc có quyền SELECT trên `geolife_gps_points` và `geolife_precomputed_inference`. Ví dụ kết nối
tới máy host của Docker Desktop dùng `host=host.docker.internal port=55433` nếu đường kết nối
tới cổng đó qua được. Kiểm thử truy vấn API ở bước 4 để xác nhận cả mạng lẫn quyền DB.
[Kết nối dịch vụ trên host từ Docker Desktop](https://docs.docker.com/desktop/features/networking/networking-how-tos/#connect-a-container-to-a-service-on-the-host)

**3. Triển khai hai Revision.** Cluster đã cài Knative, Kourier và cấu hình image local `dev.local`.
Tạo namespace, dùng Secret PostgreSQL hiện có hoặc đưa DSN qua stdin để tạo mới,
rồi dùng mẫu PostgreSQL với image local.

```powershell
$demoNs = 'geolife-knative-postgres'
$demoImage = 'dev.local/geolife-api:0.2.0-postgres'
$demoCtx = 'docker-desktop'
kubectl --context $demoCtx create namespace $demoNs --dry-run=client -o yaml |
  kubectl --context $demoCtx apply -f -
if ($LASTEXITCODE -ne 0) { throw 'Không tạo được namespace demo.' }
$demoSecret = kubectl --context $demoCtx -n $demoNs get secret geolife-postgres --ignore-not-found -o name
if ($LASTEXITCODE -ne 0) { throw 'Không kiểm tra được Secret demo.' }
if (-not $demoSecret) {
  if (-not $env:GEOLIFE_POSTGRES_DSN) { throw 'Cần đặt GEOLIFE_POSTGRES_DSN cho pod.' }
  @{
    apiVersion = 'v1'
    kind = 'Secret'
    metadata = @{ name = 'geolife-postgres'; namespace = $demoNs }
    stringData = @{ dsn = $env:GEOLIFE_POSTGRES_DSN }
  } | ConvertTo-Json -Depth 4 -Compress | kubectl --context $demoCtx apply --server-side -f -
  if ($LASTEXITCODE -ne 0) { throw 'Không ghi được Secret demo.' }
}

$manifest = Get-Content -Raw -LiteralPath 'infra/knative/geolife-postgres.yaml'
$manifest.Replace('geolife-knative', $demoNs).
  Replace('registry.example.invalid/geolife/inference:0.2.0-postgres', $demoImage).
  Replace('imagePullPolicy: IfNotPresent', 'imagePullPolicy: Never') |
  kubectl --context $demoCtx apply -f -
if ($LASTEXITCODE -ne 0) { throw 'Không triển khai được Knative Service.' }
kubectl --context $demoCtx -n $demoNs wait --for=condition=Ready ksvc/geolife-inference --timeout=180s
if ($LASTEXITCODE -ne 0) { throw 'Blue chưa Ready.' }
.\.venv\Scripts\python.exe scripts/knative_rollout.py stage --namespace $demoNs
```

**4. Kiểm tra rồi chạy rollout.** Mở port-forward Kourier ở cửa sổ riêng như phần bên dưới.
`101` chạy suy luận từ GPS khi gọi. `153` kiểm tra nhánh dùng kết quả đã tính cho lịch sử dài.

```powershell
$snapshot = 'geolife-1.3-full-v1'
$route = kubectl --context $demoCtx -n $demoNs get route geolife-inference -o json | ConvertFrom-Json
$live = ([uri]$route.status.url).Host
$demoModels = @{ blue = 'heuristic-v1'; green = 'dbscan-v1' }
foreach ($track in 'blue','green') {
  $tagHost = ([uri](($route.status.traffic | Where-Object tag -eq $track).url)).Host
  $model = $demoModels[$track]
  foreach ($userId in '101','153') {
    .\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $tagHost --snapshot $snapshot --expected "artifacts/pipeline/$model/$userId-$model.json"
    if ($LASTEXITCODE -ne 0) { throw "Kiểm tra API lỗi cho $track user $userId." }
  }
}
foreach ($action in 'canary','sample','promote','rollback') {
  .\.venv\Scripts\python.exe scripts/knative_rollout.py $action --namespace $demoNs --snapshot $snapshot
  if ($LASTEXITCODE -ne 0) { throw "Rollout dừng tại $action." }
  if ($action -in @('promote','rollback')) {
    $model = if ($action -eq 'promote') { 'dbscan-v1' } else { 'heuristic-v1' }
    .\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $live --snapshot $snapshot --expected "artifacts/pipeline/$model/101-$model.json"
    if ($LASTEXITCODE -ne 0) { throw "Kiểm tra URL live lỗi sau $action." }
  }
}
```

Lưu output PostgreSQL riêng, gồm snapshot, phiên bản và tỷ lệ request quan sát. Tái lập
`stage --namespace geolife-knative-postgres` trước buổi trình bày để có cả hai URL tag.

**5. Mở giao diện đặt xe qua Knative.** Từ PowerShell có quyền truy cập Docker Desktop, chạy:

```powershell
.\.venv\Scripts\python.exe -m geolife_inference.ride_booking --knative --open
```

Giao diện đọc danh sách user bằng kết nối PostgreSQL của Knative, lấy từ Secret `geolife-postgres`
hoặc `GEOLIFE_POSTGRES_DSN` nếu đã đặt. Request gợi ý đi qua Kourier tới URL chính của Knative Service.
Khi bản phục hồi local đã nạp xong, launcher dùng thư mục `artifacts/cp2/postgres-knative-rehearsal/data`
và chỉ khởi động instance này nếu đang dừng. Tiến độ phục hồi nằm trong `artifacts/cp2/knative-postgres-restored.log`.
Lệnh dùng cổng `18081` và mở port-forward khi cổng chưa chạy. Có thể chọn cổng khác bằng
`--kourier-port`. Traffic theo trọng số đã cài trên Route. Mỗi request cho biết model thực tế ở **Phiên bản gợi ý**.
Mục này truy vấn alias trong MLflow qua cổng `5001`, hoặc dùng MLflow client đọc registry local khi server dừng.
Registry hiện lưu bản đăng ký từ `geolife-1.3-demo-v1`. Giao diện báo chênh lệch metadata khi Revision phục vụ
snapshot `geolife-1.3-full-v1`.

## PostgreSQL cho bản cloud

Nạp `geolife-1.3-full-v1` vào PostgreSQL từ máy có quyền ghi và có đường kết nối tới DB.
Đặt `GEOLIFE_POSTGRES_DSN` cho tài khoản nạp dữ liệu rồi chạy tại thư mục repo:

```powershell
.\.venv\Scripts\python.exe scripts/import_postgres.py --sqlite artifacts/cp2/sqlite-full/geolife.sqlite3
```

Script nạp GPS và 108 kết quả đã tính trong cùng một transaction. Chạy lại với cùng file
và cùng snapshot ID dùng bản đã nạp. Dùng snapshot ID mới khi thay dữ liệu.

Build image API cho PostgreSQL với `docker buildx build --target postgres` và push lên
registry private. Dùng image theo digest trong `infra/knative/geolife-postgres.yaml`.
Trong namespace `geolife-knative`, tạo Secret `geolife-postgres` với key `dsn` chứa DSN
của tài khoản đọc. Cấp SELECT trên `geolife_gps_points` và `geolife_precomputed_inference`
cho tài khoản API. Hai Revision dùng chung snapshot PostgreSQL.

Kiểm tra user `101` và user `153` qua API v2 trên cả Blue và Green trước khi đổi traffic.
Khi gọi `check_local_api.py --history` hoặc `knative_rollout.py sample`, truyền
`--snapshot geolife-1.3-full-v1`. `/health` kiểm tra process API. Request v2 kiểm tra
kết nối DB và dữ liệu thật.

## Chạy Blue và kiểm tra Green

Build image từ snapshot SQLite đã có trong `artifacts/cp2/sqlite`. Nếu thiếu snapshot,
xem [lệnh tạo snapshot](cp2-kubernetes-deploy.md#khởi-động).

```powershell
docker buildx build --load --target sqlite-demo --build-context demo_snapshot=artifacts/cp2/sqlite -t dev.local/geolife-api:0.2.0-sqlite-demo .
kubectl --context docker-desktop apply -f infra/knative/geolife-demo.yaml
kubectl --context docker-desktop -n geolife-knative wait --for=condition=Ready ksvc/geolife-inference --timeout=180s
.\.venv\Scripts\python.exe scripts/knative_rollout.py stage
```

Lệnh apply là bước khởi tạo Blue. Sau khi đã chạy `stage`, dùng các lệnh rollout bên dưới
để đổi traffic. `stage` tạo Green và mở URL kiểm thử riêng trong khi live vẫn dùng Blue.
Hai Revision trỏ tới cùng tag local. Khi đổi nội dung image, dùng tag mới để các lượt deploy
có thể truy vết được.

Mở một cửa sổ PowerShell riêng và giữ port-forward chạy trong lúc demo.

```powershell
kubectl --context docker-desktop -n kourier-system port-forward service/kourier-internal 18080:80 --address 127.0.0.1
```

Trong cửa sổ ở repo, lấy hostname live và hostname của hai tag. So sánh kết quả của từng
Revision với JSON CLI của user `101` trước khi chuyển traffic.

```powershell
$route = kubectl --context docker-desktop -n geolife-knative get route geolife-inference -o json | Out-String | ConvertFrom-Json
$live = ([uri]$route.status.url).Host
$blue = ([uri](($route.status.traffic | Where-Object tag -eq 'blue').url)).Host
$green = ([uri](($route.status.traffic | Where-Object tag -eq 'green').url)).Host
$snapshot = 'geolife-1.3-demo-v1'
$blueCli = 'artifacts/pipeline/heuristic-v1/101-heuristic-v1.json'
$greenCli = 'artifacts/pipeline/dbscan-v1/101-dbscan-v1.json'
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $blue --snapshot $snapshot --expected $blueCli
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $green --snapshot $snapshot --expected $greenCli
```

## Canary, promote và rollback

```powershell
.\.venv\Scripts\python.exe scripts/knative_rollout.py canary
.\.venv\Scripts\python.exe scripts/knative_rollout.py sample --requests 100
```

Kết quả mẫu ghi số request, số lỗi, phiên bản trả lời và p95 phía client. `90/10` là trọng số
định tuyến. Số request nhận được dao động theo từng lượt đo. Lưu output bên cạnh kết quả
đối chiếu CLI để làm bằng chứng demo.

Sau khi xem kết quả, chọn promote hoặc rollback. Để demo cả hai, kiểm tra live sau mỗi lần đổi.

```powershell
.\.venv\Scripts\python.exe scripts/knative_rollout.py promote
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $live --snapshot $snapshot --expected $greenCli

$rollback = [Diagnostics.Stopwatch]::StartNew()
.\.venv\Scripts\python.exe scripts/knative_rollout.py rollback
.\.venv\Scripts\python.exe scripts/check_local_api.py --history --port 18080 --host-header $live --snapshot $snapshot --expected $blueCli
if ($LASTEXITCODE -eq 0) { "Rollback và kiểm tra API mất $($rollback.Elapsed.TotalSeconds) giây" }
```

URL live dùng xuyên suốt. Rollback trỏ 100% về Blue và gỡ Green khỏi Route.

## Chuẩn bị MLflow Model Registry local

Cài MLflow trong môi trường riêng khi đang dùng Wi-Fi. Môi trường này chứa client và server
cho registry. Chạy tại thư mục gốc repo.

```powershell
uv venv .venv-registry --python .\.venv\Scripts\python.exe
uv pip install --python .\.venv-registry\Scripts\python.exe -r pyproject.toml 'mlflow==3.18.0'
.\.venv-registry\Scripts\mlflow.exe --version
```

Ngày 18/11, cập nhật `.venv-mlflow` bị Windows khóa DLL pandas rồi numpy và thiếu `RECORD`.
Chuyển sang môi trường sạch `.venv-registry`, cài đồng thời MLflow và thư viện core ngay từ đầu.
Giữ môi trường cũ để xử lý sau; `.venv` và dữ liệu registry không đổi. Dùng cổng 5001 để tránh
server cũ, một worker cho demo local. Cache uv có thể giúp giảm lượng phải tải lại.

Khởi động server trong một PowerShell riêng tại thư mục gốc repo:

```powershell
New-Item -ItemType Directory -Force artifacts/cp2/mlflow | Out-Null
.\.venv-registry\Scripts\mlflow.exe server `
  --host 127.0.0.1 --port 5001 --workers 1 `
  --backend-store-uri sqlite:///artifacts/cp2/mlflow/mlflow.db `
  --artifacts-destination ./artifacts/cp2/mlflow/artifacts
```

Giữ cửa sổ này chạy. Mở http://127.0.0.1:5001, sau đó chạy ở PowerShell khác:

```powershell
.\.venv-registry\Scripts\python.exe -X utf8 scripts/register_mlflow_models.py --tracking-uri http://127.0.0.1:5001
```

Script tạo experiment `geolife-cp2` và registered model `geolife-home-office`. Hai model version
chứa thuật toán, cấu hình và snapshot GPS SQLite; alias `heuristic-v1` và `dbscan-v1` trỏ tới
phiên bản tương ứng. Số version do MLflow cấp, không mặc định luôn là 1 và 2.

Trước khi đăng ký, script tải lại gói đã lưu trong tiến trình riêng chạy ngoài repo và đối chiếu
mọi user có trong snapshot với JSON CLI. Sau khi đăng ký, script tải lại bằng URI version để
kiểm tra lần nữa; alias chỉ được gán sau khi bước này qua. Có thêm kiểm tra ID số, rỗng, quá dài
và ID vắng. Các trường config metadata chưa có trong JSON CLI cũ được bổ sung trước khi so sánh;
snapshot ID phải khớp. Báo cáo lưu tại `artifacts/cp2/mlflow/registration.json`.

Chạy lại cùng source, config, dữ liệu, JSON CLI và thông tin image sẽ kiểm tra rồi dùng lại version
đã qua đối chiếu. Manifest ghi Git commit, trạng thái working tree, hash từng source file, config,
snapshot và ID image lấy qua `docker image inspect`. Liên kết tới Knative Revision là khai báo;
script chưa chứng minh nội dung image trùng source local. Alias MLflow chọn bản thuật toán để tải,
việc đổi traffic vẫn do `knative_rollout.py` thực hiện.

Khi chỉ thử registry mà không có Docker, dùng `--skip-image-inspect`; báo cáo sẽ không có ID image.
Không dùng cờ này để tuyên bố đã xác minh bản đang chạy trên cluster.

## Kiểm tra scale-to-zero

Khi cần đo latency suy luận lúc pod đã chạy, khôi phục tag và đo riêng từng bản. Script in
thời gian warmup rồi loại warmup khỏi p95 của các request được đo.

```powershell
.\.venv\Scripts\python.exe scripts/knative_rollout.py stage
.\.venv\Scripts\python.exe scripts/knative_rollout.py sample --track green --warmup 1 --requests 100
.\.venv\Scripts\python.exe scripts/knative_rollout.py sample --track blue --warmup 1 --requests 100
```

Để đo cold start, ngừng gửi request tới Revision cần đo và chờ danh sách pod của nó trống.
Lấy URL theo tag từ Route hiện tại để giữ nguyên phân bổ traffic live. Ví dụ dưới đây đo Green.

```powershell
$track = 'green'
$route = kubectl --context docker-desktop -n geolife-knative get route geolife-inference -o json | ConvertFrom-Json
$target = $route.status.traffic | Where-Object { $_.tag -eq $track }
$revision = $target.revisionName
$tagHost = ([uri]$target.url).Host
kubectl --context docker-desktop -n geolife-knative get pods -l "serving.knative.dev/revision=$revision"
```

```powershell
$uri = 'http://127.0.0.1:18080/v2/locations/infer'
$headers = @{ Host = $tagHost }
$body = @{ user_id = '101' } | ConvertTo-Json -Compress
$cold = Measure-Command { $coldResult = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType 'application/json' -Body $body }
$warm = Measure-Command { $warmResult = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType 'application/json' -Body $body }
"Cold: $($cold.TotalMilliseconds) ms, model=$($coldResult.model_version)"
"Warm: $($warm.TotalMilliseconds) ms, model=$($warmResult.model_version)"
kubectl --context docker-desktop -n geolife-knative get pods -l "serving.knative.dev/revision=$revision" --watch
```

Chờ pod mới `Ready`, thoát watch bằng Ctrl+C rồi làm tương tự cho tag `blue`. Mỗi cặp đo
hai request suy luận liên tiếp trên cùng user. Đo p95 sau warmup ở lượt riêng.
