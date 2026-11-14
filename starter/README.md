# Starter · PostgreSQL + pgvector

Bộ khởi động **tùy chọn** cho lab cá nhân. Docker Compose tạo PostgreSQL + pgvector local; các file trong `src/` là **khung pseudocode có TODO**, chưa đọc tài liệu, tạo embedding, lưu vector hay chạy benchmark. Bạn cần tự hiện thực. Vẫn có thể chọn Qdrant, Chroma hoặc vector store tương đương theo [GUIDE.md](../GUIDE.md).

## Cấu trúc

```text
starter/
├── docker-compose.yml     # PostgreSQL 16 + pgvector, chỉ mở cổng local
├── init.sql               # bật extension khi tạo database mới
├── requirements.txt       # psycopg, pypdf và python-dotenv
├── .env.example           # cấu hình mẫu; copy thành .env
├── scripts/check_setup.py # kiểm tra kết nối và extension (đã chạy được)
├── src/
│   ├── models.py          # cấu trúc dữ liệu mẫu
│   ├── ingestion.py       # TODO: đọc / chuẩn hóa tài liệu
│   ├── chunking.py        # TODO: chia chunk
│   ├── embeddings.py      # TODO: chọn model API hoặc local
│   ├── store.py           # TODO: lưu vector, metadata và filter
│   ├── evaluation.py      # TODO: chấm truy xuất, lưu trace
│   └── run.py             # TODO: kết nối các bước thành pipeline
├── data/                  # bạn tự chuẩn bị corpus được phép sử dụng
└── results/               # lưu kết quả của bạn
```

## 1. Cài và kiểm tra database

Cần Docker Desktop hoặc Docker Engine + Compose, Python **3.11–3.14**, và mạng để tải image/dependencies lần đầu. Các lệnh sau chạy từ thư mục `starter/`:

```bash
cd starter
python3 -m venv .venv
```

Kích hoạt `.venv`: macOS/Linux dùng `source .venv/bin/activate`; Windows PowerShell dùng `.venv\Scripts\Activate.ps1`. Sau đó:

```bash
python -m pip install -r requirements.txt
# macOS/Linux: cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Kỳ vọng: hiện tên database, phiên bản PostgreSQL và pgvector, sau đó `Setup OK`. Đây **chỉ là kiểm tra hạ tầng**, không phải kết quả benchmark. Docker bind cổng `127.0.0.1:${DAY6_PG_PORT:-55433}` và mật khẩu cố định **chỉ dùng local cho lab**; nếu cổng bận (Windows + Hyper-V hay reserve dải 55425-55624), đặt `DAY6_PG_PORT` trong `starter/.env` rồi sửa `DATABASE_URL` cho khớp — không cần sửa `docker-compose.yml`. `init.sql` chỉ chạy khi volume mới được tạo; nếu database sẵn có chưa bật extension, xem log Docker và kiểm tra cấu hình thay vì xóa volume chứa dữ liệu.

Dừng container nhưng giữ dữ liệu:

```bash
docker compose -p day6_student_starter stop
```

## 2. Chọn embedding model

Điền key tương ứng trong `.env` nếu dùng OpenRouter, OpenAI hoặc Gemini; **không commit `.env`**. Model local không cần API key. `requirements.txt` chỉ có dependencies cơ bản: tự cài SDK hoặc thư viện local phù hợp với model bạn chọn và ghi lại version/lệnh cài trong báo cáo. Ghi tên model và số chiều; dùng cùng model cho toàn bộ chiến lược và vector query tương thích vector document.

## 3. Hoàn thiện pipeline

1. Đặt corpus vào `data/` hoặc cung cấp manifest/hướng dẫn truy cập. Đọc [GUIDE.md](../GUIDE.md) về **30 trang nội dung**, quyền dữ liệu và metadata.
2. Hoàn thiện từng hàm TODO trong `src/`. Lưu ID tài liệu, nguồn, trang/vị trí và ít nhất một trường filter có ích.
3. Xây ít nhất ba cấu hình; ví dụ A fixed-size, B theo đoạn, C như B nhưng có filter. Cần cùng corpus, model và benchmark; nạp lại không nhân đôi và xử lý chunk cũ khi dữ liệu đổi.
4. Tự viết ít nhất 20 câu hỏi kèm evidence, tách dev/test trước khi thử theo [BENCHMARK.md](../BENCHMARK.md). Lưu trace top-3 và báo cáo đủ năm tiêu chí.
5. Sau khi hoàn thiện, chạy `python -m src.run` từ thư mục `starter/`. Trước khi làm TODO, lệnh này **chủ động báo `NotImplementedError`**.

Lưu code, cấu hình, kết quả và lệnh chạy để người chấm tái lập; không commit key, dữ liệu mật hoặc dữ liệu không có quyền chia sẻ.

## 4. Tái lập bằng chứng corpus (checkpoint 1)

Các script dưới đây sinh ra bằng chứng đã commit trong `results/` và trong `../data/manifest.json`. Chạy từ thư mục `starter/` theo đúng thứ tự:

```bash
python scripts/audit_pages.py        # -> results/page_audit.csv, page_audit.json, ingest.log
python scripts/extract_structure.py  # -> results/structure.json
python scripts/verify_manifest.py    # đối chiếu ../data/manifest.json với hai artifact trên
python scripts/verify_benchmark.py   # -> results/benchmark_check.json; kiểm chứng evidence benchmark
python scripts/export_chunks.py      # -> results/chunks_A_fixed.jsonl, chunks_B_para.jsonl, chunk_stats.json
python scripts/check_chunk_coverage.py  # -> results/chunk_coverage.json; evidence có nằm trọn trong chunk không
python scripts/pick_coherence_samples.py # -> results/coherence_samples.csv; chốt 10 vị trí chấm coherence
python scripts/label_coherence.py    # THỦ CÔNG: điền nhãn coherence đã chấm, không nằm trong src.run
python scripts/ingest_vectors.py     # -> pgvector; results/ingest_vectors.json
python scripts/run_retrieval.py      # -> results/retrieval_metrics.json, retrieval_traces.jsonl
python scripts/audit_retrieval.py    # -> results/metadata_audit.csv, grounding_labels.csv, audit_summary.json
```

Hoặc chạy toàn bộ chuỗi bằng một lệnh: `python -m src.run` (10 bước, dừng và trả mã lỗi nếu bước nào fail). `label_coherence.py` không nằm trong chuỗi này vì nhãn coherence là **chấm thủ công**, không phải bước tự động; artifact `coherence_samples.csv` đã commit chứa nhãn đã chấm.

`verify_manifest.py` thất bại (exit code 1, in `FAIL:`) khi manifest lệch với artifact — ví dụ sai sha256, sai số trang, sai ngưỡng `min_content_chars`, sai tổng ký tự, hoặc sai số trang biểu mẫu. Đây là kiểm tra drift, không phải kiểm tra chất lượng truy xuất.

`verify_benchmark.py` thất bại khi một chuỗi evidence không xuất hiện trên trang gold sau chuẩn hóa, khi `printed_page` sai, khi `article` không có trong `structure.json`, khi thiếu ngưỡng 20 câu / 15 dev / 5 test / 3 câu filter / 1 câu filter ở test, hoặc khi test tái dùng evidence của dev.

`export_chunks.py` xuất hai cấu hình chunk và thống kê; thất bại nếu có chunk thiếu `page`/`source` hoặc có trang nội dung không được chunk nào phủ.

`check_chunk_coverage.py` kiểm tra **trần lý thuyết**: mỗi chuỗi evidence của benchmark có nằm trọn trong ít nhất một chunk không. Đây không phải Hit@k — một chunk chứa evidence vẫn có thể không lọt top-3 — nhưng nếu không chunk nào chứa, chiến lược đã phá evidence trước cả bước truy xuất.

Môi trường Python của bài nộp này nằm ở **repo root** (`.venv/`), không phải `starter/.venv/`. Khi đứng trong `starter/` trên Windows PowerShell, gọi interpreter bằng `..\.venv\Scripts\python.exe`.

Lưu ý về môi trường của bài nộp này: `starter/scripts/audit_pages.py` ghi đè `results/page_audit.*` và `results/ingest.log`; `extract_structure.py` ghi đè `results/structure.json`. Không script nào sửa corpus trong `data/`.
