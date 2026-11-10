# Evaluation — benchmark stay và kiểm tra Home/Office

Cập nhật **2026-11-06**. Phương pháp hiện tại là benchmark B1–B5; kết quả và decision table ở
[reports/cp1/benchmark.md](../reports/cp1/benchmark.md). Các scripts/worksheet subset từ tháng 10
là lịch sử, không phải quy trình đánh giá hiện tại.

## Phân biệt nguồn bằng chứng

1. **Đáp án tổng hợp:** stop/latent moving biết trước theo generator B2; dùng event metrics cho stay.
   Đúng trong thế giới đã sinh, không chứng minh mô hình mô phỏng khớp mọi dữ liệu thật.
2. **GPS thật:** counts/dwell, độ nhạy, overlap/split/merge, case study và kiểm tra phủ định bằng
   nhãn phương tiện. Không có đáp án stay hoàn chỉnh hoặc semantic Home/Office.
3. **Prediction:** score/JSON/CSV là output thuật toán, không dùng lại làm reference để tính accuracy.

Ngày **2026-11-04** đã bỏ gán nhãn thủ công: công không khả thi và một người đọc cùng GPS trace
không xác minh được đúng/sai độc lập. Worksheet/manual-review CSV cũ được giữ làm lịch sử đã đóng,
không còn là dependency, reference hoặc bước chờ reviewer. Không cần mentor duyệt để tiếp tục.

## Phạm vi và chia dữ liệu

Dataset local: 182 user, 18.670 trajectories, 24.876.978 raw → 24.177.772 cleaned points.
B2 có 162 user nguồn sau điều kiện nguồn, chia selection/final 81/81; mỗi phía 66 exact-copy groups.
Nhóm exact-copy không tách hai phía; seed generation riêng. Profile sau preprocessing dùng theo
phần tương ứng, detector chỉ nhận observations/segment, không nhận truth/latent path/labels.

GeoLife đã được EDA trước; không coi tập cuối là test hoàn toàn sạch hoặc tuyên bố mọi near-duplicate
đã được phát hiện. Final corpus chưa sinh/mở; không dùng B5 full-data để xác nhận giả thuyết B4 final.
B4 real chạy đủ 182 user nhưng bảng selection dùng đúng 81 source users selection. B5 khảo sát đủ
182 user sau khi người dùng chọn fixed-anchor 150 m/10 phút so với baseline 100 m/10 phút.

## B3 cleaning

6 policies; giữ detector 100 m/10 phút và không nhân chéo với toàn grid B4. Kiểm counts cân bằng,
provenance và parity vote20 đủ dataset; báo event graph unchanged/changed/lost/new/split/merge theo user.
Không có truth cleaning, **không chọn bằng F1**. Giữ vote20 khi không lộ lỗi audit cụ thể.
Chi tiết: [cleaning_results.md](../reports/cp1/cleaning_results.md).

## B4 stay: metric và điều kiện kết luận

- 5 detector × 4 radii × 2 durations =40 tổ hợp chung; thêm 8 bộ ST-DBSCAN duy nhất, tổng 48 trên
  tổng hợp. 40 tổ hợp chung đã chạy real; 8 ST phụ mới chạy tổng hợp.
- Cùng cases/seeds/observations/truth; không sinh stop bằng output detector. Giữ truth mất hết observations.
- Matching event one-to-one tối đa tổng temporal IoU, IoU≥0,5 và tâm≤100 m. Macro đều theo user,
  từng kịch bản; seed counts gộp trong user, bootstrap theo nhóm nguồn exact-copy.
- Báo precision, recall, F1, endpoint/tâm, split/merge, FP/giờ và mẫu số. Hard negatives không có
  positives nên không dùng F1 làm metric chính. Không gom mọi kịch bản thành một con số chất lượng.
- GPS thật báo độ nhạy/counts/dwell và event matching giữa cấu hình, không gọi chúng là accuracy.
  r_motor chỉ dùng phần stay có nhãn hợp lệ; báo số user/mẫu số và label coverage. Không đo FN.
- Cổng (a)–(d) khóa trước được giữ nguyên: chưa có winner/final. 150 m có các ô giảm quá dung sai,
  phủ định vượt ngưỡng 1%; timing real trộn tuần tự/song song nên gate runtime chưa xác nhận.
  Không thay ngưỡng sau khi xem kết quả để hợp thức hóa lựa chọn 150 m.

Người dùng vẫn có thể chọn 150 m để tiếp tục vì mục tiêu/trade-off; đó là quyết định kỹ thuật,
không phải kết quả đã vượt protocol. **100 m/10 phút chưa được chứng minh tối ưu**; 150 m cũng vậy.
Protocol khóa: [detector_protocol.md](../reports/cp1/detector_protocol.md).

## B5 Home/Office

Thiết kế 2 radii stay × 2 grouping × 2 rule, mọi user/role có hàng output kể cả unknown.
Giữ cùng phương pháp/tham số grouping khi đổi radius, gom lại riêng từ mỗi bộ stay; khi đổi rule,
giữ stays/grouping/timezone/coverage cố định. Bán kính stay 150 m không làm eps grouping đổi từ 100 m.

- Score NB05 giữ nguyên; simple giữ eligibility, chọn số ngày role rồi dwell, hòa thì unknown;
  simple không có cổng score/share/margin. Báo khác biệt abstention, không tối đa prediction rate.
- Báo predicted/unknown, reason, coverage tiers và transitions trên cùng user. Cluster IDs không
  được so giữa runs như cùng định danh. Agreement vị trí ≤200 m chỉ trên cả hai cùng predicted,
  luôn công bố mẫu số. Counts tổng giữ nguyên có thể che predicted↔unknown ở từng người.
- Dịch cửa sổ ±1 giờ, tính lại features **và coverage**. Cờ điều tra >10% paired predictions đổi
  nơi >200 m hoặc prediction rate đổi >5 điểm % là quyết định thiết kế, không phải accuracy.
- Timezone ablation trên toàn GPS theo vị trí và IANA lịch sử; features cluster theo zone tại tâm,
  pair coverage theo fix trái, giữ UTC elapsed. Báo 17 affected users, fallback và boundary-pair counts;
  thêm bảng riêng affected cohort để phần không đổi không che tác động.
- Hai khối 28 ngày bắt đầu từ local midnight ngày GPS đầu; không chọn theo output. Coverage dùng
  riêng GPS từng khối, stay phải nằm trọn và gom địa điểm riêng, ghi boundary exclusions.
  Cần cả hai khối ≥7 observed days/≥60 phút role coverage và ≥15 user/role để tổng hợp.
  Đồng thời báo số paired predictions: coverage cohort đủ không bảo đảm đủ cỡ mẫu agreement.

Chưa có authoritative Home/Office labels. Không đo accuracy/F1/calibration cho role; không dùng
recurrence/dwell đã tham gia score làm chứng nhận rule đúng. Đổi việc/chuyển nhà hoặc logging thưa
đều có thể gây output đổi; không tự suy thành performance drift.
Protocol: [role_protocol.md](../reports/cp1/role_protocol.md).

## Tái lập và kiểm tra

Notebooks 06–10 tương ứng B1–B5, kernel **Python (GeoLife)**. Outputs riêng trong
`artifacts/benchmark/`; dùng audits completed, manifest, source/code hashes và versions.
Không chạy lại preprocessing/detector khi chỉ cần đọc saved outputs. User không có stay/cluster
vẫn phải nằm trong mẫu số đủ 182. Checkpoint partial không coi là full-data.

Kiểm implementation bằng fixture nhỏ (không lấy chúng làm số liệu GeoLife):

```powershell
$env:VIRTUAL_ENV = (Resolve-Path .venv).Path
py -X utf8 -m pytest tests/test_b4_benchmark.py tests/test_b4_jobs.py tests/test_b5_roles.py -q
```

Giữ nguyên artifacts baseline và namespace đã khóa; thay semantics/config phải có phiên bản/provenance
mới. Ledger tích lũy 24 giờ, mỗi cấu hình/nhánh theo policy tối đa 12 giờ; RAM mềm theo attempt,
không phải OS hard cap. Timing offline không phải API latency, timing mixed serial/parallel chỉ mô tả.
OpenAPI/CLI validation là kiểm contract/parity riêng, không chứng minh semantic correctness.
