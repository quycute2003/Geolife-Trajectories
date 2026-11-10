# CP1 B5 — So Home/Office giữa bán kính stay và rule

Chuẩn bị ngày **2026-11-06**, trước khi chạy B5. Người dùng chọn fixed-anchor **150 m/10 phút**
để so downstream với baseline **100 m/10 phút**. Đây là khảo sát do người dùng quyết định,
không phải ứng viên đã vượt cổng B4; không sửa B4 lock, kết quả hoặc mở corpus xác nhận cuối.

## Phạm vi và thiết kế

- Đủ **182 user** theo manifest preprocessing, gồm cả user không có stay/cluster/prediction.
- Tái dùng hai cấu hình fixed-anchor từ B4 real completed; không chạy lại detector/preprocessing.
- Bốn tổ hợp: 100 m + score, 100 m + rule đơn giản, 150 m + score, 150 m + rule đơn giản.
- Báo riêng cho `heuristic-v1` và `dbscan-v1`: **8 nhánh**, mỗi nhánh có Home và Office.
  Tham số gom địa điểm giữ nguyên NB04/NB05 (eps 100 m, MinPts 3 cho DBSCAN); 150 m ở đây là
  bán kính tạo stay, không phải bán kính gom địa điểm. Gom lại từ stays của từng nhánh.
- Cấu hình rule/coverage và timezone cơ sở lấy nguyên audit NB05, không âm thầm đổi thresholds.
  Baseline 100 m + score phải parity với NB05 về trạng thái, lý do, tọa độ và score/dwell/ngày ghé.
- B5 mô tả toàn dataset; không dùng nó để xác nhận tuyên bố B4 trên phần final đã giữ riêng.

## Hai cách gán vai trò

**Score hiện tại:** dùng nguyên `inference.py`, gồm recurrence 30%, duration 25%, temporal
consistency 20%, coverage 15%, relative strength 10%; giữ mọi eligibility/share/score/margin.
Score là bằng chứng heuristic, không phải xác suất. Không tune trọng số bằng output B5.

**Rule đơn giản:** cùng eligibility như score (≥3 ngày, ≥60 phút theo role; Office ≥2 tuần).
Home xếp giảm dần số ngày có ghé đêm, rồi tổng dwell đêm; Office xếp giảm dần số ngày ghé trong
giờ làm việc thứ Hai–thứ Sáu, rồi dwell tương ứng. Chỉ chọn top duy nhất theo cặp tiêu chí;
hòa cả hai (dwell atol 1e-8 phút) hoặc không đủ eligibility thì unknown. Không dùng cluster ID
phá hòa. Rule này không có ngưỡng score/share/margin: báo rõ khác biệt abstention, không diễn
giải nhiều prediction hơn thành tốt hơn. Hai rule được xét độc lập cho Home và Office.

## Đối chiếu và mẫu số

- Tỷ lệ predicted/unknown, reason, input context (không stay/không cluster/có cluster), và tầng
  số ngày có GPS trong khung role: 0, 1–2, 3–6, ≥7. Cùng manifest và user trên hai phía.
- Khi đổi rule: giữ stay, grouping, coverage, timezone cố định. Khi đổi stay radius: giữ rule và
  tham số grouping cố định; memberships có thể đổi nên gom lại riêng.
- Agreement địa điểm = khoảng cách tâm ≤200 m trên user cả hai phía đều predicted; báo mẫu số.
  Báo khoảng cách trung vị, số đổi >200 m, predicted→unknown và unknown→predicted.
  Cluster ID chỉ dùng nội bộ một lượt, không xác lập agreement giữa hai lượt.
- Membership keys đi kèm prediction để audit, không coi việc key khác do endpoint stay thay đổi
  là bằng chứng hai địa điểm khác nhau. Không có ground truth Home/Office, không tính accuracy/F1.

## Dịch cửa sổ ±1 giờ

Giữ UTC elapsed time và mọi ngưỡng; dịch đồng thời cửa sổ đêm và giờ làm việc −1/+1 giờ.
Tính lại temporal features và coverage từ GPS, không chỉ dịch nhãn đầu ra. Giữ cùng grouping.
Gắn cờ điều tra khi >10% user cả hai cùng predicted đổi vị trí >200 m, hoặc tỷ lệ predicted
đổi >5 điểm phần trăm. Đây là ngưỡng thiết kế để xem xét, không phải tiêu chí accuracy.

## Timezone ablation

- Tra IANA cho **mọi GPS fix trong cache B4**, theo lô; ghi counts zone và user bị ảnh hưởng.
  Không gán một timezone đa số cho cả user đi qua nhiều vùng. Mọi cluster cũng được tra zone
  tại tâm đại diện; features cluster được tính với zone đó, giữ nguyên stays/membership/rules.
- Coverage: valid pair cùng trajectory/segment, 0 < Δt ≤5 phút. Gán pair cho timezone của fix
  bên trái; ghi số/thời lượng pair mà hai đầu khác zone. Đây là giả định sample-and-hold tối đa
  5 phút, không nội suy vị trí biên múi giờ. Union intervals trong từng zone; local dates trùng
  tên ngày khi di chuyển được tính một lần. UTC elapsed minutes không thay đổi.
- Tính lại ngày có GPS/đêm/giờ làm việc và mọi role features/inference. Ngày/offset lịch sử
  xử lý bằng `zoneinfo`/IANA; bản đồ polygon địa lý hiện tại không bảo đảm biên zone lịch sử.
- Tra không ra zone: fallback Asia/Shanghai, công bố số fix/user; không âm thầm loại dữ liệu.
  Khác tên zone được ghi là affected kể cả offset tại thời điểm đó trùng; số role đổi báo riêng.
- Báo transitions trên đủ 182 user và riêng tập affected cùng mẫu số; nếu không có affected
  thì ghi no-op, không tạo ra giả định có thay đổi. Kiểm tra coverage UTC cơ sở parity với NB05.
- Pinned `timezonefinder==9.0.0`, `timezonefinder-data==3.2026.3.post1`; versions còn lại ghi lock.
  API: [TimezoneFinder](https://timezonefinder.readthedocs.io/en/latest/4_api.html).

## Hai giai đoạn

Mỗi user: bắt đầu từ 00:00 Asia/Shanghai của ngày GPS đầu tiên; hai khối **28 ngày liên tiếp**.
Không chọn cặp giai đoạn dựa theo prediction. Coverage chỉ dùng GPS nằm trong khối, intervals
observed được cắt tại biên thời gian. Chỉ dùng stay nằm trọn trong khối (kể cả endpoint cuối
phải trước biên phải); ghi số stay giao biên bị loại để tránh dùng tâm/endpoints có GPS ngoài khối.
Gom địa điểm **riêng trong từng khối**, không dùng clusters/context của toàn thời gian.

User/role đủ để so khi **cả hai khối** có ≥7 observed days và ≥60 phút GPS coverage trong khung
role. Mỗi aggregate cần ≥15 user/role đủ điều kiện, không phụ thuộc họ predicted hay unknown.
Thiếu cohort thì ghi `insufficient_cohort`, vẫn công bố mẫu số và số liệu mô tả, không gọi là đã
đánh giá ổn định. Chuyển nhà/đổi việc có thể là thay đổi thật; không suy output đổi là accuracy giảm.

## Chạy, checkpoint và ngân sách

Notebook độc lập `10_cp1_b5_roles.ipynb`, kernel Python (GeoLife). Người dùng chạy full-data.
Đầu ra riêng `artifacts/benchmark/b5/roles_v1`; baseline/B4/cache nguồn chỉ đọc.
Stage `main` dùng stays/coverage nhỏ; `context` đọc cache GPS B4 theo trajectory một lượt để tính
coverage ±1 giờ, hai khối và local timezone; `ablations` tái dùng context. Summary/plots hiện trực
tiếp trong notebook. Không cần chạy lại NB02–09 hoặc tạo lại corpus B2.

Khóa hashes code, protocol, nguồn và versions trước chạy. Checkpoint theo user ở main/context/
ablations, tái dùng khi checksum khớp; user đang dở tính lại. Không sửa code/config đã khóa trong
cùng namespace hoặc ghi đè stage completed. Chưa chạy thì không tick PLAN.

Ledger B5 nối tiếp B4 và mọi attempt/stage B5: tổng **24 giờ**, mỗi nhánh radius/grouping tối đa
**12 giờ** qua các stage/attempt; RAM working set ≤min(8 GiB, 50% RAM khả dụng đầu attempt).
Kiểm tra giữa user/trajectory/lô timezone và nhánh; vượt thì ghi incomplete. Đây là giám sát bằng
checkpoint, không phải hard limit của hệ điều hành. Không tự tăng ngân sách hoặc bỏ user khó.

## Sản phẩm và giới hạn

Bảng rates/reasons/coverage strata; paired comparisons/transitions; timezone inventory; eligibility
theo thời gian; plot tiếng Việt. Kết quả là độ nhạy và ổn định, không phải semantic correctness.
Chưa dùng mức predicted/unknown, agreement hoặc chính thành phần score làm nhãn đúng/sai.
Giữ hai nhánh để đối chiếu; không tự đổi model production hoặc khai báo winner B4.
