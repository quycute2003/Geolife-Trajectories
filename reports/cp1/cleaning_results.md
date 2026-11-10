# CP1 B3 — kết quả cleaning sensitivity

Đọc và kiểm tra ngày 2026-11-05. **Giữ vote20**; kết quả này đo độ nhạy, không đánh giá tọa độ đúng/sai.

## Phạm vi và kiểm tra

- Audit `artifacts/benchmark/b3/cleaning_v1/audit.json`: completed, đủ 182 users, 18.670 trajectories,
  24.876.978 raw points cho cả sáu policy; 112.020 hàng trajectory × policy, không trùng khóa.
- Vote20 khớp preprocessing counters và saved stays ở đủ 182 users. Baseline có 10.339 stays,
  tổng dwell 215.579,966667 phút (~3.593 giờ), detector fixed-anchor 100 m/10 phút, gap 5 phút.
- Kiểm tra phương trình counts ở mọi trajectory/policy, 1.110 output SHA256, baseline/code/protocol
  hashes và size/mtime đủ 18.670 raw source files. Raw file SHA256 đã được job lưu trong manifest;
  lượt đọc kết quả không quét/hash lại toàn raw dataset.
- Verification lưu ở `artifacts/benchmark/b3/cleaning_v1_verification.json` trước khi sửa warning.

## Tác động tới stay

| Policy | Tổng stays | User có thay đổi | Baseline stays không còn unchanged | Δdwell (phút) |
|---|---:|---:|---:|---:|
| vote20 | 10.339 | 0 | 0 | 0 |
| vote10 | 10.338 | 5 | 11 | -18,55 |
| vote50 | 10.339 | 3 | 3 | +17,58 |
| mean20 | 10.339 | 4 | 4 | -1,18 |
| no_merge | 10.320 | 9 | 29 | -280,92 |
| duplicate_altitude | 10.339 | 0 | 0 | 0 |

Unchanged yêu cầu khớp cả tọa độ/thời gian/point_count và membership raw contributors trong dung sai.
Cột baseline affected =10.339 − unchanged, không phải tổng số event mới hay số component khác biệt.
Tổng stay bằng nhau không có nghĩa mọi event giống nhau.

| Policy | Changed 1→1 | Lost | New | Split components | Merge components |
|---|---:|---:|---:|---:|---:|
| vote10 | 9 | 2 | 1 | 0 | 0 |
| vote50 | 1 | 0 | 1 | 0 | 1 |
| mean20 | 4 | 0 | 0 | 0 | 0 |
| no_merge | 4 | 23 | 2 | 2 | 0 |
| duplicate_altitude | 0 | 0 | 0 | 0 | 0 |

Graph dùng overlap thời gian dương cùng source trajectory, không spatial gate hoặc ép 1→1.
Ở no_merge, hai split components biến hai baseline events thành bốn variant events. Vote50 có
một merge component gồm hai baseline events, đồng thời xuất hiện một event mới nên tổng stay giữ nguyên.
Không có complex many-to-many component ở lượt này.

## Diễn giải theo policy và user

- **Vote10:** 6/9 changed events chỉ đổi contributor membership, không đổi start/end/tâm/point_count.
  Ba changed events còn lại có thay đổi hình học/thời gian; dịch tâm lớn nhất ~47,78 m ở user 165.
  Ngoài ra có hai event lost và một event new. Các user ảnh hưởng: 055, 065, 075, 141, 165.
- **Vote50:** một event changed ở user 165, end kéo dài 304 giây, tâm dịch ~5,88 m; một event new
  ở 065 và một merge ở 141. Gộp được nhiều conflict hơn chưa chứng minh vị trí đúng hơn.
- **Mean20:** bốn changed events ở 002, 025, 141, 165; không lost/new. Chênh dwell tổng -71 giây;
  tâm dịch lớn nhất ~0,29 m. Đây là thay đổi nhỏ trong lượt này, không chứng minh tương đương mọi dữ liệu.
- **No merge:** tác động lớn nhất nhưng vẫn chỉ 29/10.339 baseline stays không còn unchanged
  (~0,28%). Ảnh hưởng tập trung: user 141 từ 7 xuống 0 stays, 165 từ 18 xuống 11, 065 từ 52 xuống 46.
  Không được dùng mức thay đổi nhỏ toàn dataset để che tác động lớn ở từng user.
- **Contrast altitude:** giữ thêm 14 rows khác altitude ở duplicate key, phát sinh thêm 14 conflict
  groups/merged extras; output point count vẫn 24.177.772 và không thay stay nào. Contrast được tính
  lại ở 5 trajectories; các trajectory còn lại được tái dùng có manifest. Không kết luận altitude
  vô nghĩa cho mọi nhiệm vụ, chỉ không tác động stay detector hiện tại ở dataset này.

## Counts và provenance

| Policy | Output points | Nhóm conflict không resolve | Conflict rows tách riêng |
|---|---:|---:|---:|
| vote20 | 24.177.772 | 305 | 1.135 |
| vote10 | 24.170.105 | 7.972 | 35.984 |
| vote50 | 24.178.012 | 65 | 369 |
| mean20 | 24.177.465 | 612 | 1.901 |
| no_merge | 24.020.212 | 157.865 | 709.851 |
| duplicate_altitude | 24.177.772 | 305 | 1.135 |

Conflict rows tách riêng gồm cả minorities bị vote loại; không đồng nghĩa mọi row thuộc nhóm
unresolved. Không xóa hoặc ghi đè raw data. Nhánh conflict tính lại ở 314 trajectories, còn 18.356
trajectories tái dùng vote20 cho mỗi policy; vẫn kiểm kê đủ mọi user/file.

## Chi phí, warning và quyết định

Job mất **3.918,81 giây (~65 phút 19 giây)**, sampled peak working set **487.596.032 bytes
(~465,01 MiB)**, dưới cap 1.588.623.360 bytes. Ledger sau B3 **8.726,02 giây**, bao gồm khoản
reserve 3.600 giây đã công bố, không phải toàn bộ runtime lịch sử đã đo chính xác.

FutureWarning từ pandas khi concat event frames rỗng không làm job failed. Sau khi kiểm chứng
output v1, module được sửa thành revision **b3-cleaning-v1.1**: bỏ frame rỗng khỏi concat và giữ
schema nếu user không có stay. Kiểm tra fixture xác nhận rows/schema không đổi và không còn warning.
Output, audit và hashes v1 giữ nguyên; code hash hiện tại khác audit v1 là thay đổi đã ghi nhận sau run.
Không cần chạy lại dataset chỉ để bỏ warning.

Counts/parity/provenance audit không phát hiện lỗi buộc đổi policy. **Giữ vote20** cho bước B4;
không gọi 20 m là ngưỡng tối ưu hoặc vote50/vote10 là chính xác hơn/kém hơn vì chưa có truth cleaning.
B4 tiếp tục so detector trên cùng corpus tổng hợp B2, dùng grid và phụ lục đã chốt trước chạy.
