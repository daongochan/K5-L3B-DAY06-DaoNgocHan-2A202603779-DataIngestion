# Benchmark — Nghị định 13/2023/NĐ-CP

Bộ **22 câu** viết và kiểm chứng **trước khi chạy bất kỳ chiến lược nào**.

| File | Nội dung |
|---|---|
| `questions.json` | Nguồn chính: câu hỏi, đáp án, gold page, evidence, split, filter, tiêu chí chọn chiến lược |
| `gold.csv` | Cùng dữ liệu dạng bảng để chấm thủ công và đối chiếu |
| `../starter/results/benchmark_check.json` | Kết quả kiểm chứng tự động |

## Phân chia

| Split | Số câu | Phạm vi |
|---|---|---|
| dev | 16 | Chương I–II (định nghĩa, nguyên tắc, quyền, đồng ý, thời hạn 72 giờ, trẻ em, thông báo vi phạm, hiệu lực) + Phụ lục Mẫu 01–02 |
| test | 6 | Bồi thường thiệt hại, ngoại lệ xóa dữ liệu, trách nhiệm Bên Xử lý, kiểm tra chuyển dữ liệu ra nước ngoài, Mẫu 06, Điều 38 |

Test không dùng lại bất kỳ chuỗi evidence nào của dev (script kiểm tra điều này).

## Kiểu câu hỏi

- `direct` (11): hỏi thẳng một quy định.
- `rephrased` (6): diễn đạt bằng ngôn ngữ đời thường ("doanh nghiệp", "người dùng", "bản sao dữ liệu") thay vì thuật ngữ văn bản.
- `conditional` (5): hỏi có/không kèm ngoại lệ ("có được coi là đồng ý không", "có bị xóa không", "có được hưởng miễn trừ không").

## Kiểm chứng evidence

```bash
# từ starter/
..\.venv\Scripts\python.exe scripts\verify_benchmark.py
```

Script chạy corpus qua **chính pipeline** (`load_pdf`) mà retriever sẽ dùng, rồi kiểm tra:

1. `physical_page` tồn tại và có text.
2. Chuỗi evidence xuất hiện trên trang gold **sau chuẩn hóa** (so khớp sau casefold + gộp khoảng trắng, nên chỉ bỏ qua khác biệt định dạng).
3. `printed_page` khớp số trang in thật của PDF.
4. `article` tồn tại trong `structure.json` và bắt đầu không muộn hơn trang gold.
5. Đủ ngưỡng 20 câu / 15 dev / 5 test / 3 câu filter / 1 câu filter ở test.
6. Test không tái dùng evidence của dev.

Kết quả hiện tại: **22/22 evidence verified, 0 warning**.

Đã thử phá hoại: đổi evidence của D01 thành một câu không có trong văn bản → script báo `FAIL: D01: evidence not found on physical_page 29`. Nghĩa là kiểm chứng có tác dụng thật, không phải luôn pass.

## Câu kiểm tra metadata filter

4 câu, trong đó 2 câu ở test. Filter là **input giả định cung cấp trước**, lấy từ chính câu hỏi:

| ID | Filter | Vì sao cần lọc |
|---|---|---|
| D15 | `page_type=phu_luc_bieu_mau` | Điều 14 (tr.12) nhắc "Mẫu số 01, 02" nên không lọc thì trang quy định lấn top-3 |
| D16 | `page_type=phu_luc_bieu_mau` | Cùng lý do với D15 |
| T04 | `page_type=phu_luc_bieu_mau` | Điều 25 (tr.22) nhắc "Mẫu số 06" |
| T06 | `article=Điều 38` | Điều 39–42 dùng cùng từ vựng "trách nhiệm" nên dễ chiếm top-3 |

Đây là các trường hợp filter **thực sự thay đổi kết quả**, không phải filter trang trí: corpus có nhiễu từ vựng đúng ở các vị trí này.

## Nguy cơ rò rỉ dev/test

Cùng một văn bản nên dev và test chia sẻ từ vựng pháp lý và mẫu câu. Test dùng lại **1 trang gold** với dev (p8: D04 hỏi hạn chế xử lý, T01 hỏi bồi thường) nhưng khác evidence và khác điều. Rủi ro chính là **quen thuộc từ vựng**, không phải trùng đáp án. Không điều chỉnh tham số trên test.

## Độ phủ và độ phân biệt

- **18 trang gold / 36 trang nội dung**, 18 điều/biểu mẫu khác nhau.
- Ba trang được dùng nhiều lần (p29 ×3, p8 ×2, p10 ×2) nhưng mỗi lần hỏi một khoản khác nhau, evidence khác nhau.
- **Bốn câu cùng đáp án "72 giờ" nhưng khác hành động** — đây là bài kiểm tra phân biệt có chủ đích:

  | ID | Hành động | Trang |
  |---|---|---|
  | D04 | Hạn chế xử lý dữ liệu | p8 |
  | D05 | Xóa dữ liệu | p15 |
  | D08 | Thông báo vi phạm cho Bộ Công an | p18 |
  | D14 | Cung cấp dữ liệu cho chủ thể | p12 |

  Một retriever chỉ khớp từ khóa "72 giờ" sẽ trả về trang sai; muốn đúng phải phân biệt được ngữ cảnh hành động. Bốn câu này cố ý nằm cùng dev để đo khả năng phân biệt của từng chiến lược chunking.

- Filter `page_type` được chọn vì corpus có **nhiễu thật**: thân nghị định nhắc tên "Mẫu số 01/02/03/04/05/06" ở các Điều 14, 23, 24, 25 — chính là nơi dễ lấn top-3 khi hỏi về biểu mẫu.
