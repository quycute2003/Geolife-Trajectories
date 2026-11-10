# CP1 B3 — cleaning sensitivity v1

Chuẩn bị 2026-11-05. Code/notebook đã chuẩn bị; chưa chạy B3 trên GeoLife.

Giữ fixed-anchor 100 m, dwell 10 phút, max gap 5 phút và baseline config. Không chạy grouping
hoặc Home/Office, không đổi policy production, không ghi đè preprocessing/stays hoặc corpus B2.
Giữ vote20 trừ khi phát hiện lỗi tái hiện được; stay-diff không phải accuracy và không chọn bằng F1.

## Sáu policy

| Policy | Quy tắc |
|---|---|
| vote20 | Baseline spatial_vote_context_v2, threshold 20 m |
| vote10/vote50 | Cùng voting/context/tie logic, chỉ đổi threshold 10/50 m |
| mean20 | Gộp toàn nhóm cùng timestamp nếu mọi cặp cách nhau ≤20 m; nhóm xa quarantine, không vote/context |
| no_merge | Quarantine toàn nhóm multi-position cùng timestamp, ngắt segment tại thời điểm đó |
| duplicate_altitude | Giữ vote20; dedup thêm altitude_m vào key user/trajectory/time/lat/lon |

Validity và duplicate policy của năm nhánh conflict giống core. Contrast altitude dùng altitude
parsed (feet → mét, -777 → NaN), không so định dạng chuỗi hoặc các trường PLT không dùng cho suy luận.
Các rows cùng tọa độ/giờ nhưng khác altitude được giữ để vote/mean có provenance; không để lại hai
fix cùng timestamp. Chọn coordinate đại diện bằng mean nhóm được chọn, altitude bằng mean giá trị
hợp lệ; mọi contributor và rejected row đều có ID để truy vết.

Mỗi PLT đọc một lần, raw record_id là số hàng dữ liệu vật lý (bắt đầu 0, không gồm 6 dòng header).
Source manifest có file path, size, mtime và SHA256; ID không phụ thuộc quyết định cleaning.
Raw counts phải bằng cleaned + invalid/duplicate + merged extras + separated conflict rows.
Phương trình theo source_point_count cũng được kiểm tra. Quarantine gây ngắt segment dù hai fix
xung quanh còn cách nhau dưới 5 phút. Không bỏ high-speed point hoặc point thiếu altitude.

## Phạm vi, parity và reuse

Đọc đủ 182 users/18.670 trajectories. Mỗi trajectory tính vote20 làm chuẩn; các policy không có
conflict chịu tác động tái dùng output vote20, contrast altitude chỉ tính lại khi duplicate key
thay đổi. counts_per_trajectory.csv ghi reused_vote20 để thể hiện provenance phần tái dùng.
File provenance/removed của nhánh tái dùng được tham chiếu từ vote20, không nhân bản dữ liệu.

Đối chiếu preprocessing counters và stays vote20 với saved NB02/NB03 ở mỗi user. Stays so exact
trajectory/start/end/point_count, tọa độ và duration atol 1e-9, rtol 0. Sai parity làm job failed.
Tất cả event cuối được xử lý overlap theo cùng rule first-chronological như core; rejected giữ riêng.

## Stay-diff

Graph nối events cùng user/trajectory có temporal overlap dương; không dùng spatial gate vì
cleaning có thể dịch tâm. Các endpoint chỉ chạm nhau không tạo cạnh. Connected components được
phân loại unchanged/changed, lost/new, split/merge và complex many-to-many; không ép 1-to-1.

Ở component 1-to-1, so start/end chính xác, tâm haversine tolerance 1e-6 m, dwell tolerance
1e-9 phút, point_count và SHA256 danh sách raw contributor IDs. Membership không dùng segment ID
hay cluster ID. Thay altitude chỉ được ghi membership changed nếu contributor khác; không tự
gọi là geometry thay đổi. Split/merge tính theo component và ghi counts events hai đầu để có mẫu số.

## Output và ngân sách

NB08 chạy độc lập, namespace artifacts/benchmark/b3/cleaning_v1; đã có output thì từ chối ghi đè.
Output gồm audit.json, counts_per_trajectory/user/totals, conflict_provenance/removed theo policy,
stays theo user/policy, stay_diff.csv và stay_diff_per_user.csv. Notebook vẽ counts/dwell-diff;
số stay tăng hoặc giảm không tự chứng minh tốt hơn.

Budget đọc ledger sau generation B2, bao gồm reserve 3.600 giây đã công bố; nếu có job khác phải
cộng thêm trước chạy. Trần compute tích lũy 24 giờ, B3 job tối đa 12 giờ và RAM checkpoint
≤min(8 GiB, 50% RAM khả dụng đầu job). Failed/partial không gọi là full-data; giữ audit cả lượt fail.
Chưa có runtime thực tế B3; không cam kết thời gian hoặc gọi test dữ liệu giả là kết quả dataset.
