# Kết quả thực nghiệm

Toàn bộ artifact của bài nộp nằm trong [`starter/results/`](../starter/results/) vì pipeline chạy trong `starter/` và ghi kết quả tương đối với thư mục đó. Thư mục này chỉ là điểm vào để khớp cấu trúc trong [SUBMISSION.md](../SUBMISSION.md).

| File | Nội dung |
|---|---|
| `retrieval_metrics.json` | Hit@1/Hit@3 dev/test, latency cho A/B/C |
| `retrieval_traces.jsonl` | Trace top-3 đầy đủ, 66 bản ghi = 22 câu × 3 chiến lược |
| `metadata_audit.csv` | Audit metadata từng bản ghi, 54 dòng = 6 câu test × top-3 × 3 |
| `audit_summary.json` | Tổng hợp metadata + grounding |
| `grounding_labels.csv` | Nhãn grounding 0/1/2 kèm lý do |
| `coherence_samples.csv` / `.json` | 10 vị trí chốt trước khi chấm + nhãn coherence |
| `coherence_summary.json` | Điểm coherence trung bình A/B |
| `chunk_stats.json` | Số chunk, phân bố độ dài, độ phủ trang, số Điều |
| `chunks_A_fixed.jsonl` / `chunks_B_para.jsonl` | Hai cấu hình chunk đầy đủ |
| `chunk_coverage.json` | Trần lý thuyết: evidence có nằm trọn trong chunk không |
| `page_audit.csv` / `.json`, `ingest.log` | Log đọc trang, lỗi/rỗng, cảnh báo |
| `structure.json` | Chương/Mục/Điều trích từ văn bản |
| `benchmark_check.json` | Kết quả kiểm chứng evidence benchmark |
| `ingest_vectors.json` | Model, store, thời gian, kiểm tra nạp lại không trùng |
| `setup_check.log` | Kiểm tra PostgreSQL + pgvector |

Chạy lại toàn bộ: xem [README.md](../README.md) ở repo root.
