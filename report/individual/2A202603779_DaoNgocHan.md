# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

**Corpus.** Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân, bản đăng Công báo số 685 + 686 ngày 30-4-2023. File PDF có 37 trang vật lý, in trang 3–39. Trong đó 36 trang được tính là trang nội dung: 29 trang thân nghị định và 7 trang biểu mẫu phụ lục (Mẫu số 01–06 nằm trên p31–p37). Trang bị loại là p30, bìa phụ lục chỉ liệt kê tên 6 mẫu. Quy tắc đếm là trang phải có ít nhất 500 ký tự không phải khoảng trắng sau chuẩn hóa. Cả 37 trang đều trích được chữ nên không cần OCR.

Văn bản quy phạm pháp luật công bố công khai trên Công báo. File có chữ ký số của Cổng Thông tin điện tử Chính phủ, ký ngày 28-4-2023, và không có `/Producer` hay XMP, nên nguồn được ghi theo chữ ký và dòng tiêu đề Công báo chứ không theo metadata công cụ. Danh sách trang, sha256 và ghi chú quyền nằm trong `data/manifest.json`, kiểm tra bằng `starter/scripts/verify_manifest.py`.

Các đường dẫn script và kết quả trong báo cáo tính từ repo root.

**Chuẩn hóa.** Văn bản được đưa về NFC, bỏ ký tự vô hình và ký tự điều khiển, gộp khoảng trắng ngang nhưng giữ khoảng cột (từ hai dấu cách trở lên thì tách thành dòng riêng) để không dính "CHÍNH PHỦ" vào "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" hay "Nơi nhận:" vào khối chữ ký. Dòng tiêu đề chạy "CÔNG BÁO/Số 685 + 686/Ngày 30-4-2023 <số trang>" bị bỏ khỏi nội dung, số trang in giữ lại trong `printed_page`. Các dòng bị ngắt được nối theo thụt lề, thu được 625 đoạn.

Lỗi đáng kể nhất là chế độ trích xuất mặc định của pypdf cắt âm tiết tiếng Việt ngay tại dấu thanh, "dữ liệu" thành "d ữ li ệu". Kiểm tra riêng trang 5 đã thấy gần 100 chỗ như vậy. Vì thế pipeline dùng `extraction_mode="layout"`; chế độ `plain` chỉ còn là fallback và có cảnh báo. Kết quả đọc: 0 trang rỗng, 0 cảnh báo.

Giới hạn: 7 trang biểu mẫu nhiều dòng chấm nên ít ngữ nghĩa, ví dụ trang 34 có 1.135 ký tự nhưng chỉ 303 ký tự không phải dòng chấm. Trang 29 còn chuỗi `aky]` là phần hiển thị chữ ký số trong file gốc; mình để nguyên chứ không sửa nội dung nguồn.

**Embedding và vector store.** Model là `intfloat/multilingual-e5-base`, 768 chiều, chạy local trên CPU với `sentence-transformers 6.3.0` và `torch 2.15.0`. Prefix dùng đúng chuẩn E5: `passage: ` cho document, `query: ` cho câu hỏi; vector được L2-normalize nên cosine tương đương dot product. Store là PostgreSQL 16.16 với pgvector 0.8.7 chạy bằng Docker Compose, bảng `chunks`, metric cosine (`<=>`), tìm kiếm exact chứ không dựng HNSW vì corpus chỉ khoảng 200 chunk. Chi phí API bằng 0. Lệnh chạy đầy đủ: `cd starter && python -m src.run`.

Trước khi chốt, có thử hai model nhỏ hơn (`MiniLM-L12-v2` 384d và `mpnet-base-v2` 768d). Cả hai cho Hit@3 trên dev thấp hơn e5. Mấy lần chạy đó không lưu artifact nên chỉ ghi lại như ghi chú chọn model, không dùng làm số liệu trong báo cáo.

**Metadata.** Ngoài ba trường bắt buộc `document_id`, `source`, `page` (trang vật lý 1–37), có thêm `printed_page` lấy từ dòng tiêu đề, `page_type` (`noi_dung` / `phu_luc_bieu_mau` / `phu_luc_muc_luc`) suy từ vị trí phần Phụ lục, `chapter` (Chương I–IV) và `article` (Điều 1–44). Hai trường sau lấy từ `starter/results/structure.json` do `extract_structure.py` trích từ chính văn bản. `article` cho phép giới hạn truy xuất trong một điều, còn `page_type` dùng để loại biểu mẫu khi câu hỏi chỉ hỏi quy định.

## Cấu hình và benchmark

Ba cấu hình:

**A_fixed** cắt cửa sổ 500 ký tự, overlap 150. Overlap được chọn bằng cách đo trên dev số chuỗi evidence nằm trọn trong ít nhất một chunk: 50 cho 13/16, 100 cho 15/16, 150 cho 16/16, 200 cũng 16/16 nhưng thêm 23 chunk. Dải 140–160 cho cùng kết quả nên đây không phải con số khớp sát nút.

**B_para** gom trọn đoạn theo heading, ngân sách 700 ký tự cho phần thân, thêm breadcrumb dạng `[Chương > Mục > Điều]`. Heading Chương/Mục/Điều luôn mở chunk mới nên một chunk không trộn hai điều, và đó là điều kiện để filter theo `article` có nghĩa. Mốc 700 xấp xỉ một điều trung bình, đồng thời giữ số chunk gần A (136 so với 199) để chênh lệch kích thước index không lẫn vào so sánh A–B.

**C_para_filter** giữ nguyên chunk, vector, store, metric và top-k của B, chỉ thêm bước lọc metadata theo câu hỏi. B và C khác nhau đúng một yếu tố.

**Benchmark.** Bộ câu hỏi có 22 câu, viết xong trước khi chạy bất kỳ cấu hình nào, chia 16 dev và 6 test. Có 11 câu hỏi thẳng, 6 câu diễn đạt lại và 5 câu dạng điều kiện/ngoại lệ. Test giữ những chủ đề không dùng để chỉnh: bồi thường thiệt hại, ngoại lệ xóa dữ liệu, trách nhiệm Bên Xử lý, kiểm tra chuyển dữ liệu ra nước ngoài, Mẫu số 06 và Điều 38.

Bốn câu có filter: D15, D16, T04 lọc `page_type=phu_luc_bieu_mau`; T06 lọc `article=Điều 38`. Hai câu nằm ở test. Đây là đúng chỗ corpus có nhiễu thật: thân nghị định nhắc tên "Mẫu số 01/02/06" ở Điều 14 và 25, nên nếu không lọc thì trang quy định lấn top-3.

Evidence được kiểm bằng `starter/scripts/verify_benchmark.py`, chạy corpus qua chính hàm `load_pdf` mà retriever dùng, rồi đối chiếu từng chuỗi evidence với trang gold sau chuẩn hóa và kiểm thêm `printed_page`, `article`, các ngưỡng 20/15/5. Kết quả 22/22 evidence khớp, 0 cảnh báo. Đã thử phá hoại bằng cách thay evidence của D01 bằng một câu không có trong văn bản; script báo `FAIL` đúng như mong đợi.

**Tiêu chí chọn, chốt trước khi xem test:** Evidence Hit@3 trên dev, rồi grounding trung bình trên dev, rồi coherence, cuối cùng là tài nguyên (số chunk, thời gian). Cấu hình nào có filter tuân thủ dưới 100% trên câu có filter thì loại. Tiêu chí ghi trong `benchmark/questions.json` ở khóa `selection_criteria_precommitted`.

### Chunking

| | A_fixed (500/150) | B_para (700 + breadcrumb) |
|---|---|---|
| Số chunk | 199 | 136 |
| Ký tự trung bình | 460,6 | 527,2 |
| Trung vị | 497 | 607,5 |
| Min–max | 160–500 | 133–808 |
| Độ lệch chuẩn | 86,4 | 184,7 |
| Trang được phủ | 36/36 | 36/36 |
| Điều phân biệt được | 41 | 44 |
| Chunk dưới 100 ký tự | 0 | 0 |

Cả hai đều giữ đủ metadata truy nguồn. Ngoài các trường chung như `chunk_id`, `document_id`, `source`, `page`, `printed_page`, `page_type`, `article`, `chapter`, `form`, `strategy`, `chunk_index`, `char_count`, A có thêm `start_offset`/`end_offset`, B có thêm `section`, `articles`, `breadcrumb`, `body_char_count`, `paragraph_count`. Kiểm tra tự động cho thấy 0 chunk thiếu `page` hay `source`, 0 trang nội dung bị bỏ sót.

Mình kiểm thêm một thứ không phải Hit@k: mỗi chuỗi evidence có nằm trọn trong ít nhất một chunk hay không (`starter/scripts/check_chunk_coverage.py`). A và B đều đạt 16/16 dev và 6/6 test, tức cả hai chưa phá evidence trước khi truy xuất. Trung bình mỗi evidence nằm trong 1,32 chunk ở A và 1,09 chunk ở B.

Coherence chấm trên 10 vị trí chốt trước (10 trang nội dung đầu, mỗi trang lấy đoạn dài nhất). A được 1,40/2 với 4 điểm 2 và 6 điểm 1; cả 6 mẫu điểm 1 đều do chunk mở đầu giữa từ hoặc mất chủ ngữ, ví dụ ", Bên Kiểm soát…", "ên Kiểm soát…", "ng ý của chủ thể…". B được 2,00/2, cả 10 mẫu đều trọn ý và có breadcrumb. Phần này tự chấm nên có nguy cơ thiên lệch; nhãn và lý do từng mẫu nằm trong `starter/results/coherence_samples.csv`.

### Vector và ba chiến lược

Nạp lại: chạy hai lượt liên tiếp, `chunk_id` là khóa chính và dùng `ON CONFLICT DO UPDATE`, đồng thời xóa các chunk cũ không còn được sinh ra. Lượt hai nạp đủ 199/199 chunk cho A và 136/136 cho B, `duplicate_rows = 0`.

Filter tuân thủ 4/4 câu có filter. Top-3 đổi ở 2/4 câu có filter và giữ nguyên ở cả 18 câu không filter, đúng như kỳ vọng.

Độ trễ 22 truy vấn mỗi chiến lược, đã gồm round-trip DB: trung vị A 114,2 ms, B 98,4 ms, C 91,5 ms; trung bình A 123,4 ms, B 115,6 ms, C 91,5 ms. Qua ba lần chạy trên cùng máy, trung vị A rơi vào 89–114 ms, B 77–98 ms, C 61–92 ms. Thứ tự A > B > C giữ nguyên nhưng độ lớn chênh lệch không ổn định, nên chỉ đọc thứ tự chứ không đọc giá trị tuyệt đối. Truy vấn đầu chịu cold-start (max A 265,5 ms, max B 321,5 ms) nên trung vị đáng tin hơn trung bình.

## Kết quả

| Strategy | Split | Hit@1 | Evidence Hit@3 | Chunk | Thời gian ingest | Chi phí |
|---|---|---|---|---|---|---|
| A_fixed | dev | 12/16 | 16/16 | 199 | embed 40,8s + write 0,9s | 0 USD |
| A_fixed | test | 5/6 | 5/6 | 199 | — | 0 USD |
| B_para | dev | 15/16 | 16/16 | 136 | embed 35,1s + write 1,5s | 0 USD |
| B_para | test | 6/6 | 6/6 | 136 | — | 0 USD |
| C_para_filter | dev | 15/16 | 16/16 | 136 | dùng lại vector B | 0 USD |
| C_para_filter | test | 6/6 | 6/6 | 136 | — | 0 USD |

Thời gian trên là của lượt nạp thứ hai. Tổng hai lượt mất 194,1s, chạy trên CPU; ba lần chạy liên tiếp cho 186,3s, 210,4s và 194,1s nên con số này chỉ mang tính tham khảo.

| Strategy | Coherence /2 (n=10) | Metadata đủ và đúng | Filter tuân thủ | Grounding 0/1/2 | Trung bình /2 |
|---|---|---|---|---|---|
| A_fixed | 1,40 | 17/18 | N/A | 0/2/4 | 1,67 |
| B_para | 2,00 | 18/18 | N/A | 0/0/6 | 2,00 |
| C_para_filter | 2,00 | 18/18 | 4/4 | 0/0/6 | 2,00 |

A và B không áp dụng filter nên cột tuân thủ để N/A, không phải vì bộ test không có câu filter.

### Audit thủ công

**Metadata.** 54 bản ghi, tính bằng 6 câu test nhân top-3 nhân 3 chiến lược, đối chiếu với chính trang nguồn chứ không tin nhãn đã lưu. Cách làm: tìm lại vị trí bắt đầu của chunk trong text trang rồi xem Điều nào đang mở tại offset đó.

| Chiến lược | Tất cả trường đúng | `page` | `printed_page` | `page_type` | `article` | `form` |
|---|---|---|---|---|---|---|
| A_fixed | 17/18 | 18/18 | 18/18 | 18/18 | 17/18 | 18/18 |
| B_para | 18/18 | 18/18 | 18/18 | 18/18 | 18/18 | 18/18 |
| C_para_filter | 18/18 | 18/18 | 18/18 | 18/18 | 18/18 | 18/18 |

Lỗi từng mắc: `fixed_size` gán Điều đang mở ở đầu trang cho mọi cửa sổ trên trang, nên một cửa sổ nằm sau heading "Điều N." khác bị gắn nhãn Điều cũ. Lỗi lộ ra khi đối chiếu với trang nguồn, và cách sửa là lấy `article` theo offset bắt đầu của chính chunk. Artifact của lần chạy đầu không giữ lại nên không nêu con số lần đó. Sau khi sửa, A còn 1/18 lỗi: chunk `p028:A_fixed:003` mở đầu ở cuối Điều 38 nhưng phần lớn nội dung là Điều 39. Đây là giới hạn thật của cửa sổ cắt theo ký tự, ghi lại chứ không chỉnh cho đẹp.

**Grounding.** Thang 0/1/2, chấm trên cả 6 câu test, chỉ đánh giá evidence retrieval chứ không phải độ chính xác câu trả lời của LLM.

A được 1,67/2, hai câu bị 1 điểm. T02 thiếu điểm c "đã được công khai" vì chunk bị cắt sau điểm b. T03 đúng trang 28 nhưng chunk chỉ có khoản 1–2 của Điều 39, thiếu khoản 5. B và C đều 2,00/2.

Đường dẫn để kiểm tra lại:

- Trace top-3 đầy đủ: `starter/results/retrieval_traces.jsonl` (66 bản ghi).
- Chỉ số tổng hợp: `starter/results/retrieval_metrics.json`.
- Nhãn coherence và lý do: `starter/results/coherence_samples.csv`; cách chọn mẫu: `coherence_samples.json`.
- Audit metadata: `starter/results/metadata_audit.csv`, tổng hợp ở `audit_summary.json`.
- Nhãn grounding: `starter/results/grounding_labels.csv`.
- Cấu hình và giả thuyết A/B/C: `artifacts/experiment_log.csv`.

## Phân tích và kết luận

### A và B

| Khía cạnh | A_fixed | B_para | Chênh lệch |
|---|---|---|---|
| dev Hit@1 | 12/16 | 15/16 | +3 câu |
| dev Hit@3 | 16/16 | 16/16 | ngang |
| test Hit@1 | 5/6 | 6/6 | +1 câu |
| test Hit@3 | 5/6 | 6/6 | +1 câu |
| Coherence | 1,40/2 | 2,00/2 | +0,60 |
| Metadata đúng | 17/18 | 18/18 | +1 |
| Grounding | 1,67/2 | 2,00/2 | +0,33 |
| Số chunk | 199 | 136 | −32% |
| Số Điều phân biệt | 41 | 44 | +3 |
| Truy vấn (trung vị) | 114,2 ms | 98,4 ms | −15,8 ms |

B hơn ở mọi chỉ số và dùng ít chunk hơn 32%. Có một chỉ số ngang nhau là dev Hit@3, nhưng cả hai đều chạm trần 16/16 nên nó không nói lên nhiều. Chỗ đáng chú ý là Hit@1 lệch 3 câu: A thường tìm đúng trang nhưng trả về ở hạng 2–3, nghĩa là agent phải đọc thêm mới trả lời được.

Lý do nằm ở chỗ A cắt ngang ý. Coherence 1,40 với 6/10 mẫu bị cắt giữa từ hoặc mất chủ ngữ, và grounding 1,67 đi theo đúng cơ chế đó: evidence có trong top-3 nhưng thiếu đúng điều kiện để trả lời.

### B và C

Chunk, vector, store, metric và top-k giữ nguyên; filter chỉ áp cho 4 câu có filter. Hit@1 và Hit@3 không đổi vì B vốn đã đúng ở cả 4 câu đó. Nhưng ở tầng top-3 thì filter có tác dụng:

| Câu | B (không filter) | C (có filter) |
|---|---|---|
| D15 (Mẫu số 01) | `[p31, p1, p32]`, p1 là thân nghị định ngoài phạm vi | `[p31, p32, p37]`, toàn biểu mẫu |
| T04 (Mẫu số 06) | `[p37, p21, p20]`, p21 và p20 là Điều 24 ngoài phạm vi | `[p37, p37, p35]`, toàn biểu mẫu |

Với agent đọc top-3, C bỏ được 3 lượt đọc ngoài phạm vi trên hai câu này: p1 ở D15, p21 và p20 ở T04. Đó là lý do vẫn giữ C dù chỉ số hit không nhích.

### Hai ví dụ sai

**D14, B_para trượt Hit@1.** Câu này hỏi thời hạn cấp bản sao dữ liệu. Gold là trang 12, Điều 14, "trong 72 giờ". Top-1 trả về trang 8, Điều 9 với score 0,8817, nội dung nói về quyền được cung cấp dữ liệu nhưng không có thời hạn; top-2 đúng trang 12 với 0,8805. Hai điều 9 và 14 mô tả cùng một quyền ở hai mức chi tiết, câu hỏi dùng "bản sao" còn văn bản dùng "cung cấp cho bản thân dữ liệu". Đây là giới hạn của dense embedding trước hai đoạn gần nghĩa, không phải lỗi chunking. Nếu câu hỏi nêu rõ điều thì filter `article=Điều 14` xử lý được.

**T03, A_fixed trượt cả Hit@3.** Gold là trang 28, Điều 39 khoản 5. Top-2 đúng trang 28 với score 0,8895 nhưng chunk chỉ chứa tiêu đề Điều 39 và khoản 1–2; khoản 5 nằm ở chunk khác cùng trang. Top-1 là trang 5, Điều 3 với 0,8925, nói chung về bảo mật dữ liệu. Ở đây định nghĩa hit yêu cầu chuỗi evidence nằm trong chính chunk, nên chunk đúng trang nhưng sai đoạn không được tính. B sửa được vì chunk Điều 39 của B chứa trọn khoản 5.

### Chọn gì và đánh đổi

Chọn B_para, và dùng C_para_filter khi câu hỏi có filter đáng tin. B đạt trần ở cả ba tiêu chí chất lượng trên dev và test, đồng thời dùng ít chunk nhất và truy vấn nhanh nhất. C không cải thiện hit nhưng giảm nhiễu top-3; câu không có filter thì C chạy y như B nên không mất gì.

Đánh đổi đã chấp nhận:

- B phụ thuộc chất lượng ranh giới đoạn từ bước trích xuất. PDF không có thụt lề đáng tin thì `by_paragraph` gộp sai và lợi thế biến mất.
- B cần heading "Điều N." để thẳng hàng chunk. Văn bản không có cấu trúc sẽ thoái hóa gần giống A.
- C cần filter đúng và có trong nguồn. Store chặn tên trường lạ nhưng không kiểm tra giá trị có tồn tại, nên filter sai sẽ loại mất trang đúng mà không báo lỗi.

### Hạn chế

- Test chỉ 6 câu, lệch 1 câu là 16,7 điểm phần trăm. Không thể nói B tốt hơn A một cách tổng quát, chỉ nói được trên corpus và bộ câu hỏi này B không kém A ở khía cạnh nào.
- Coherence và grounding đều tự chấm sau khi đã biết kết quả hit. Nguy cơ thiên lệch là có thật; từng nhãn được công bố kèm lý do để người khác chấm lại.
- Corpus chỉ một văn bản, chưa kiểm chứng được hành vi trên nhiều tài liệu hay nhiều định dạng.
- Dense embedding thuần: D14 cho thấy hai điều gần nghĩa có thể đảo hạng. Hybrid BM25 nhiều khả năng giúp vì "72 giờ" là tín hiệu từ khóa mạnh.
- Exact search chấp nhận được ở quy mô 199 + 136 chunk nhưng không đại diện cho corpus lớn.
- Thời gian đo trên một máy, mỗi chiến lược 22 truy vấn. Ba lần chạy liên tiếp lệch nhau khoảng 5% ở thời gian embed của A và 21% của B, tổng thời gian lệch 13%; độ trễ trung vị lệch 27–49% nên chỉ dùng để so thứ tự.

### Nếu làm lại

1. Tăng test lên 15–20 câu để khoảng tin cậy đủ hẹp cho kết luận so sánh.
2. Thử hybrid BM25 + dense cho các câu có con số hoặc thuật ngữ chính xác như "72 giờ", "01 lần/năm".
3. Chunk theo cấu trúc Điều thay vì ngân sách ký tự. Corpus này có 44 điều với độ dài vừa phải nên khả thi.
4. Đo lại D14 và T03 với filter `article` để định lượng mức cải thiện khi câu hỏi nêu rõ điều.
5. Nhờ người khác chấm chéo coherence và grounding mà không cho xem trước kết quả hit.
6. Đưa kiểm tra idempotent vào CI. Cơ chế hai lượt đã có nhưng hiện chỉ chạy thủ công.

## Công cụ AI và cách kiểm tra

Theo `RULES.md`, bài làm có dùng AI hỗ trợ. Phạm vi là soạn khung code pipeline và các script kiểm chứng, rồi rà lại diễn đạt báo cáo và đối chiếu số liệu với artifact. Phần nhãn coherence và grounding tự chấm, không nhờ AI.

Mọi con số trong báo cáo đều đọc từ file do pipeline sinh ra trong `starter/results/`, không có số nào tự đặt. Ba script `verify_manifest.py`, `verify_benchmark.py` và `check_chunk_coverage.py` sẽ báo lỗi khi dữ liệu lệch; đã thử phá hoại một lần để chắc là chúng không phải lúc nào cũng pass.

Người viết chịu trách nhiệm về nội dung báo cáo và có thể giải thích từng bước của pipeline cũng như từng con số ở trên.
