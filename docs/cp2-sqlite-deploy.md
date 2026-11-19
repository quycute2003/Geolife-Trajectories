# CP2 · Deploy demo SQLite trên AWS

Image `geolife-lambda:sqlite-demo` chứa snapshot chỉ đọc của bốn user đã dùng để đối chiếu và
benchmark local. Cả Blue và Green dùng cùng image, snapshot và `baseline-v1`.
[Build và kiểm tra local](../README.md#thử-lambda-với-snapshot-sqlite)

## Chuẩn bị

Chốt phạm vi GPS đưa lên AWS và thời gian giữ tài nguyên trước khi push image. Dùng profile
`geolife` và Region `ap-southeast-2` cho toàn bộ tài nguyên demo. Kiểm tra quyền truy cập bằng
`aws sts get-caller-identity --profile geolife --region ap-southeast-2`.

Tạo repository ECR private ở Sydney và push image `geolife-lambda:sqlite-demo`. Cấp cho Lambda
quyền lấy image theo tài liệu AWS và lấy URI ghim theo digest `@sha256:…` từ ECR. Đặt URI đó vào
`$imageUri` trong PowerShell. [Quyền lấy image từ ECR](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html#images-permissions)

## Publish Blue và Green

Khởi tạo stack với Blue là model của `$LATEST`. Khi chưa cung cấp version Blue, stack tạo
Lambda và log group. Sau đó publish version Blue và giữ số version được trả về.

```powershell
$awsArgs = @('--profile', 'geolife', '--region', 'ap-southeast-2')
$stack = 'geolife-sqlite-demo'
$function = "$stack-infer"

aws cloudformation deploy @awsArgs --stack-name $stack --template-file infra/geolife-demo.yaml --capabilities CAPABILITY_IAM --parameter-overrides "ImageUri=$imageUri" "LatestModel=heuristic-v1"
$blue = aws lambda publish-version @awsArgs --function-name $function --query Version --output text
aws lambda wait function-active-v2 @awsArgs --function-name $function --qualifier $blue
```

Kiểm tra `$blue` bằng cách invoke version trực tiếp trước khi tiếp tục. Sau đó cập nhật
`$LATEST` sang DBSCAN. Stack tạo API và alias `prod` trỏ vào Blue trong lần cập nhật này.
Khi stack hoàn tất, publish và kiểm tra riêng version Green.

```powershell
aws cloudformation deploy @awsArgs --stack-name $stack --template-file infra/geolife-demo.yaml --capabilities CAPABILITY_IAM --parameter-overrides "ImageUri=$imageUri" "LatestModel=dbscan-v1" "BlueVersion=$blue" "Traffic=blue"
$green = aws lambda publish-version @awsArgs --function-name $function --query Version --output text
aws lambda wait function-active-v2 @awsArgs --function-name $function --qualifier $green
```

Ví dụ gọi trực tiếp Green. Dùng cùng event với `$blue` để đối chiếu bản Blue. So `ExecutedVersion`,
`model_version`, snapshot và kết quả suy luận với JSON CLI của từng bản.

```powershell
@'
{"version":"2.0","rawPath":"/v2/locations/infer","requestContext":{"http":{"method":"POST"}},"headers":{"content-type":"application/json"},"body":"{\"user_id\":\"101\"}"}
'@ | Set-Content -Encoding ascii tmp/aws-infer-event.json
aws lambda invoke @awsArgs --function-name $function --qualifier $green --payload fileb://tmp/aws-infer-event.json tmp/aws-infer-response.json
```

## Canary và rollback

Lấy `ApiEndpoint` từ outputs của stack. Ba route yêu cầu IAM, nên client cần ký SigV4 và có
quyền `execute-api:Invoke`. Xác nhận request thiếu chữ ký bị từ chối. Đo latency đầu cuối
trên Blue và gọi Green riêng trước khi chia traffic.
[IAM cho HTTP API](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-access-control-iam.html)

Giữ cùng image và số version khi cập nhật stack. Đổi `$traffic` theo từng bước kiểm tra.

| `$traffic` | Blue | Green |
| --- | ---: | ---: |
| `blue` | 100% | 0% |
| `canary` | 90% | 10% |
| `green` | 0% | 100% |

```powershell
$traffic = 'canary'
aws cloudformation deploy @awsArgs --stack-name $stack --template-file infra/geolife-demo.yaml --capabilities CAPABILITY_IAM --parameter-overrides "ImageUri=$imageUri" "LatestModel=dbscan-v1" "BlueVersion=$blue" "GreenVersion=$green" "Traffic=$traffic"
aws lambda get-alias @awsArgs --function-name $function --name prod
```

Theo dõi lỗi, timeout, p95 và cỡ mẫu theo phiên bản trước khi chuyển sang `green`. Rollback bằng
tham số `blue`, rồi gọi lại cùng endpoint để xác nhận. Ghi thời gian từ lúc yêu cầu cập nhật stack
đến lúc Blue phục vụ trở lại. [Tiêu chí release](../reports/cp2/release.md#ngưỡng-canary-đề-xuất-cho-demo)

Sau demo, lưu bằng chứng và thực hiện lịch dọn đã chốt cho stack, image ECR và mục registry.
