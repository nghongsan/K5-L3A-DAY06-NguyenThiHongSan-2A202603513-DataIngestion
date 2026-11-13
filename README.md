# Bài làm Day 06 — Data Ingestion (OpenStax Python, chương 4–6)

**Corpus:** OpenStax *Introduction to Python Programming*, PDF tr. 95–174 (77 trang nội dung, CC BY-NC-SA 4.0); xem [data/manifest.json](data/manifest.json).
**Embedding:** `intfloat/multilingual-e5-small` (local, 384d, CPU, $0) · **Vector store:** Chroma 1.5.9 persistent, cosine (HNSW).
**Chiến lược:** A fixed 500/50 · B theo đoạn/heading ≤800 · C = B + filter `chapter`. **Chọn C** theo tiêu chí dev đã chốt trước.
**Kết quả:** [results/summary.md](results/summary.md) · **Trang HTML xem trace từng câu:** [report/results_explorer.html](report/results_explorer.html) (tải về rồi mở bằng trình duyệt; bản online: https://claude.ai/artifact/QxChknDJMRB9KmUuUQ4zUH) · **Báo cáo:** [report/individual/2A202603513_NguyenThiHongSan.md](report/individual/2A202603513_NguyenThiHongSan.md)

## Cách chạy lại

Cần Python 3.11–3.12 (đã chạy với 3.12.3 trên macOS arm64). Không cần Docker hay API key.

```bash
./scripts/download_corpus.sh                 # tải PDF + kiểm tra sha256 snapshot
cd starter
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt              # lần đầu sẽ tải model e5-small (~470MB) từ Hugging Face
python -m src.run ingest                     # đọc, chuẩn hóa, kiểm evidence benchmark, chunk, embed, lưu A/B/C, kiểm tra nạp lại
python -m src.run retrieve --split dev       # chạy dev (chọn chiến lược ở bước này)
python -m src.run retrieve --split test      # chạy test sau khi đã chốt
python -m src.run audit                      # xuất mẫu coherence để chấm tay
python -m scripts.reingest_change_test       # kiểm tra nạp lại không trùng + xóa chunk cũ khi tài liệu đổi
python -m src.summarize_results              # gộp chỉ số + nhãn tay -> results/summary.md
python -m scripts.build_explorer             # sinh trang HTML report/results_explorer.html từ results/
```

| Thư mục / file | Nội dung |
|---|---|
| `starter/src/` | ingestion, chunking, embeddings, store (Chroma), evaluation, run |
| `benchmark/questions.json` | 25 câu (19 dev / 6 test), gold page + evidence, 5 câu có filter |
| `results/traces_{dev,test}.jsonl` | top-3 đầy đủ: text, score, metadata, cờ hit |
| `results/metrics_*.json`, `results/summary.md` | Hit@1 / Evidence Hit@3 (n/N), thời gian |
| `results/audit/*_labels.csv` | nhãn tay coherence, metadata, grounding |
| `results/ingest_log.json`, `results/reingest_test.json`, `results/run_info.json` | log trang rỗng/lỗi, kiểm tra nạp lại, phiên bản & thời gian |
| `artifacts/experiment_log.csv` | cấu hình, giả thuyết, tiêu chí chọn, kết quả |

---

# Đề bài gốc

# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

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
