# Mentor review — CP1 submission package

Status: **Ready for user to forward for review; mentor approval pending**.
Không có email/message tự động được gửi tới mentor. Người dùng cần xác nhận approval trong chat
trước khi triển khai HTTP endpoints. Tiếp tục cải thiện pipeline không phải approval API.

## Tài liệu cần đọc

1. `openapi.yaml`: OpenAPI 3.1 draft, POST `/v1/locations/infer`, examples và schemas.
2. `reports/cp1/results.md`: real-data diagnostics và parameter sensitivity.
3. `docs/assumptions.md`: algorithms, confidence formula, windows và abstention.
4. `docs/architecture.md`, `docs/evaluation.md`: boundaries và evaluation procedure.

## Quyết định cần mentor

- [ ] UTC-only input; chọn IANA timezone, mặc định Asia/Shanghai có warning.
- [ ] Night 22–06, work Mon–Fri 09–18, và cách diễn giải ca đêm/travel/coverage thiếu.
- [ ] Score là heuristic evidence, không probability; weights và abstention thresholds rõ ràng.
- [ ] Có thể Home/Office trùng nhau hoặc `unknown`; POI là recurring place.
- [ ] Request dùng inline points một user, không mở server filesystem/dataset URLs.
- [ ] Malformed/invalid input là 400/422; insufficient evidence/empty input là completed 200.
- [ ] Limits đề xuất: 100k points, 20 MiB decoded, 20k stays, 60s deadline; cần load tests khi xây API.
- [ ] Bearer auth, user authorization, HTTPS, no-store, không log GPS và retention mặc định bằng 0.
- [ ] Chấp nhận OpenAPI 3.1.0 và version `/v1`; thay đổi không tương thích cần version mới.
- [ ] **Mentor phê duyệt OpenAPI** — chưa hoàn tất.

## Validation hiện có

`py -X utf8 scripts/validate_contract.py --results artifacts/evaluation`
validate OpenAPI structure và JSON Schema + formats của request/error/response examples,
cùng tám real-data responses (hai model x bốn users). Tests kiểm tra thêm rejection cases.
Không có HTTP routing/auth/load/resource enforcement để test; chưa thuộc CP1 implementation.
Không có bằng chứng đo Home/Office accuracy. Cần independent reviewer/labels cho kết luận semantic.
