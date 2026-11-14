# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

## Bài nộp của Đào Ngọc Hân (2A202603779 · L3B)

Corpus: **Nghị định 13/2023/NĐ-CP** về bảo vệ dữ liệu cá nhân (Công báo số 685 + 686 ngày 30-4-2023), 37 trang PDF, 36 trang nội dung.

| Thành phần | Đường dẫn |
|---|---|
| Thông tin học viên | [STUDENT.md](STUDENT.md) |
| Báo cáo cá nhân | [report/individual/2A202603779_DaoNgocHan.md](report/individual/2A202603779_DaoNgocHan.md) |
| Manifest corpus (nguồn, quyền, trang, sha256) | [data/manifest.json](data/manifest.json) |
| Benchmark 22 câu + gold | [benchmark/](benchmark/) |
| Nhật ký thí nghiệm A/B/C | [artifacts/experiment_log.csv](artifacts/experiment_log.csv) |
| Corpus PDF | `starter/data/nghi_dinh_13_2023_nd_cp.pdf` |
| Kết quả, trace, nhãn audit | [starter/results/](starter/results/) |

### Chạy lại từ đầu

```powershell
# 1) Môi trường Python (dùng .venv ở repo root)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r starter\requirements.txt

# 2) Database: PostgreSQL 16 + pgvector 0.8.7
cd starter
Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
..\.venv\Scripts\python.exe scripts\check_setup.py

# 3) Toàn bộ pipeline (10 bước), in bảng Hit@1/Hit@3
..\.venv\Scripts\python.exe -m src.run
```

`src.run` dừng và trả mã lỗi nếu bất kỳ bước nào fail; không có fallback sang vector mock. Chi tiết từng bước và cách chạy riêng lẻ: [starter/README.md](starter/README.md).

### Kết quả chính (top-3, `intfloat/multilingual-e5-base`, pgvector cosine)

| Chiến lược | dev Hit@1 | dev Hit@3 | test Hit@1 | test Hit@3 |
|---|---|---|---|---|
| A_fixed (500/150) | 12/16 | 16/16 | 5/6 | 5/6 |
| B_para (700 + breadcrumb) | 15/16 | 16/16 | 6/6 | 6/6 |
| C_para_filter (= B + filter) | 15/16 | 16/16 | 6/6 | 6/6 |

Chọn **B_para**, dùng **C_para_filter** khi câu hỏi cung cấp được filter. Lý do và đánh đổi trong báo cáo cá nhân.

---

## Mô tả đề bài

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
