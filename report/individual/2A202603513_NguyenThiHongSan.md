# Báo cáo cá nhân — Day 6

> Số liệu dưới đây lấy từ `results/summary.md` (lần chạy cuối 2026-11-13; top-3 của mọi câu giống hệt lần chạy đầu).
> Trang HTML để xem top-3 của A/B/C cho từng câu, có tô evidence gold: `report/results_explorer.html` (bản online: https://claude.ai/artifact/QxChknDJMRB9KmUuUQ4zUH).

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** Giáo trình *Introduction to Python Programming* (OpenStax), chương 4 Decisions, 5 Loops, 6 Functions, tương ứng PDF trang 95–174 (80 trang vật lý). Giấy phép CC BY-NC-SA 4.0 (lấy từ OpenStax CMS API), dùng phi thương mại cho bài học và có ghi nguồn. PDF không commit; có `scripts/download_corpus.sh` kèm kiểm tra sha256. Quy tắc tính trang: trang vật lý PDF; một trang được tính khi còn ≥ 200 ký tự sau khi bỏ footer, link "Access multimedia content" và nhãn "TRY IT". Kết quả: **77 trang nội dung**, 80.667 ký tự. Trang 124, 146, 174 rỗng nên bị loại và đã ghi log. Nếu bỏ thêm 9 trang tóm tắt chương thì vẫn còn 68 trang. Chi tiết trong `data/manifest.json`.
- **Chuẩn hóa, lỗi và giới hạn:** Unicode NFKC; ngoặc kép cong đổi thành ASCII; gộp khoảng trắng nhưng giữ xuống dòng để chunk theo đoạn; bỏ footer và header có số trang in (số trang in được giữ lại trong metadata `printed_page`). Giới hạn: pypdf làm mất thụt lề code Python và đặt một số nhãn sidebar sai thứ tự. Công thức dạng ảnh/MathML bị mất (ví dụ p.164 "The area of a right triangle is , where…", p.170 đơn vị m/s²). Bảng bị làm phẳng thành text. Không có OCR vì PDF có lớp text.
- **Embedding và vector store:** Model `intfloat/multilingual-e5-small` (Sentence Transformers 6.3.0, chạy local trên CPU), 384 chiều, vector chuẩn hóa L2. Query có tiền tố `query: `, document có tiền tố `passage: `. Vector store là Chroma 1.5.9 `PersistentClient` (lưu tại `./chroma_db`), metric cosine, chỉ mục HNSW nên là **tìm kiếm xấp xỉ**. Máy không có Docker nên dùng Chroma thay pgvector, đúng phương án GUIDE cho phép. GPU MPS crash trên macOS 14.4 với torch 2.15 (`NSInvalidArgumentException`) nên đã ghi lỗi và chạy CPU; không có fallback sang vector giả. **Chi phí $0.** Thời gian embed: A 4,1 s, B 3,3 s; tải model 7,9 s. Tổng token (tokenizer e5): A 26.010, B 24.209. Chunk dài nhất 220 token, không chunk nào vượt giới hạn 512 token. Sau khi ingest, mọi truy vấn được đối chiếu với tìm kiếm chính xác (brute-force cosine trên vector đã lưu): **ANN = exact ở 75/75 truy vấn**. Lệnh chạy: xem `README.md`.
- **Metadata:** Trường bắt buộc gồm `document_id`, `source`, `page` (trang vật lý PDF). Trường bổ sung: `chapter` (int), `chapter_title`, `section`, `section_title`, `sections_covered`, `printed_page`, `char_start`, `char_end`, `char_len`, `content_hash`, `strategy_params`. Giá trị chapter/section lấy từ **bookmark (outline) của PDF**, không đoán từ nội dung. `section` là section chứa ký tự đầu tiên của chunk. `sections_covered` liệt kê mọi section mà chunk chạm tới: 17/210 chunk của A vắt qua heading, còn B có 0 chunk như vậy vì không bao giờ cắt qua heading. `char_start`/`char_end` là vị trí chính xác của chunk trong text đã chuẩn hóa của trang. Trường lọc là `chapter`: có 3 giá trị phân biệt và đáng tin, và người học thường biết mình đang học chương nào.

## Cấu hình và benchmark
- **A / B / C:**
  - **A:** cửa sổ cố định 500 ký tự, overlap 50, nằm trong một trang, không lọc. 210 chunk.
  - **B:** chunk theo cấu trúc. Tách tại heading section, nhãn khối (CHECKPOINT, EXAMPLE…) và cuối đoạn; gộp khối nhỏ đến ≥ 200 ký tự; tối đa 800 ký tự; không vượt heading section; nằm trong một trang. 263 chunk.
  - **C:** chunk và vector **giống hệt B**. Khác biệt duy nhất giữa B và C là C thêm `where chapter == N` khi câu hỏi có filter.
- **Bộ câu hỏi:** 25 câu (`benchmark/questions.json`), chia **19 dev / 6 test** trước mọi lần chạy truy xuất. Gồm câu trực tiếp, diễn đạt lại, điều kiện/ngoại lệ, và 5 câu có filter (3 dev: q12, q17, q18; 2 test: t04, t06). Filter là ngữ cảnh giả định ("đang học chương N"), không chứa gold. Evidence được kiểm chứng tự động: cả 27 đoạn evidence đều có trên đúng trang sau chuẩn hóa (`results/benchmark_evidence_check.json`). Câu q13 và t04 có hai trang gold hợp lệ. Nguy cơ rò rỉ: dev và test cùng cuốn sách, cùng văn phong. Ngoài ra, t06 và q07 có chung gold page 111 (hai đoạn liền nhau), và t04 với q13 đều chấp nhận trang tóm tắt 143. Không câu nào dùng chung câu evidence. File `benchmark/questions.csv` là bản dạng bảng của bộ câu hỏi.
- **Tiêu chí chọn (chốt trước khi xem test, ghi trong `artifacts/experiment_log.csv`):** ưu tiên dev Evidence Hit@3, rồi dev Hit@1, rồi grounding, rồi tài nguyên. Dev cho kết quả hòa Evidence Hit@3 (18/19) nên xét Hit@1: C 17/19 > B 16/19 > A 13/19. **Chọn C**, sau đó chạy test một lần.

## Kết quả
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 13/19 | 18/19 | 210 | embed 4,1 s; 20 ms/query | $0 |
| A | test | 3/6 | 4/6 | 210 | 23 ms/query | $0 |
| B | dev | 16/19 | 18/19 | 263 | embed 3,3 s; 21 ms/query | $0 |
| B | test | 5/6 | 5/6 | 263 | 24 ms/query | $0 |
| C | dev | 17/19 | 18/19 | 263 (dùng lại của B) | 21 ms/query | $0 |
| C | test | 5/6 | 5/6 | 263 | 24 ms/query | $0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,80 (10) | 18/18 | test 2/2; dev 1/3 | 0/1/5 → 1,83 |
| B | 1,50 (10) | 18/18 | test 2/2; dev 1/3 | 0/1/5 → 1,83 |
| C | 1,50 (10, cùng chunk với B) | 18/18 | test 2/2; dev 3/3 | 0/1/5 → 1,83 |

**Đường dẫn và cách chọn mẫu:**
- Trace top-3 đầy đủ (text, score, metadata, cờ hit) nằm ở `results/traces_dev.jsonl` và `results/traces_test.jsonl`.
- Nhãn chấm tay nằm ở `results/audit/*_labels.csv`.
- Mẫu coherence: 10 trang chọn theo quy tắc cố định trước khi xem điểm, cứ 8 trang nội dung lấy 1 (95, 103, …, 169). Trên mỗi trang, vị trí là dòng văn xuôi đầu tiên sau giữa trang. Hàm `_offset_of_sample` trong `run.py` thực hiện việc này.
- Metadata: 6 câu test × top-3 = 18 bản ghi cho mỗi cấu hình. Mỗi bản ghi có cột kiểm tra riêng cho source, page (text của chunk có trong trang PDF gốc), printed_page (= page − 10), chapter (theo khoảng trang của bookmark) và section/sections_covered (theo vị trí heading thật trong trang).
- **Ích lợi của metadata:** `chapter` giúp lọc đúng phạm vi (q17: Hit@1 sai ở B, đúng ở C); `page` và `printed_page` giúp người đọc mở đúng trang sách in.
- **Hạn chế của metadata:** `section` chỉ là một giá trị nên không mô tả hết chunk vắt qua section (A); trang mở đầu chương (p.95, 125, 147) không có footer nên `printed_page = -1` trong chunk (`null` trong manifest); các giá trị lọc bị giới hạn ở mức chương.
- **Người chấm:** trợ lý AI (Claude) đề xuất nhãn theo thang của GUIDE, cùng tiêu chí cho mọi cấu hình. Sau đó học viên (Nguyễn Thị Hồng San) đọc lại từng dòng trong `results/audit/` và xác nhận; không nhãn nào phải sửa nên số liệu giữ nguyên. Cột `labeler` ghi rõ quy trình này.

## Phân tích và kết luận
- **A so với B (thay cách chunk):**
  - Trên dev, B hơn A 3 câu ở Hit@1 (16 so với 13); Evidence Hit@3 bằng nhau.
  - Trên test, B hơn A ở cả hai chỉ số: 5/6 so với 3/6 và 5/6 so với 4/6.
  - Coherence tăng từ 0,80 lên 1,50. A thường cắt giữa từ hoặc giữa câu, ví dụ p.111 "…If the input is 60, both if statements are".
  - Đổi lại, B có nhiều chunk hơn (263 so với 210) và độ dài không đều. B cũng hay gộp đáp án trắc nghiệm mồ côi vào đầu đoạn văn kế tiếp, và một chunk ở p.169 chỉ toàn nhãn (coherence 0).
- **B so với C (thay filter):** Filter chỉ có tác dụng với câu mơ hồ giữa các chương.
  - **q17** ("PEP 8 … spaces around =", filter chương 6): B xếp hai chunk PEP 8 của chương 4 (p.110, p.100) trên đáp án đúng p.171, nên Hit@1 sai. C chỉ tìm trong chương 6 nên p.171 lên rank 1.
  - **q18** ("What is a branch?", filter chương 4): B vẫn đúng ở rank 1, nhưng rank 2 là p.147 thuộc chương 6. Vì vậy B tuân thủ filter dev chỉ 1/3, còn C đạt 3/3.
  - Trên test, B vốn đã ở đúng chương với t04 và t06, nên C bằng B. Không thể kết luận C tốt hơn B trên test.
- **Hai ví dụ lỗi:**
  1. **t03 (B/C)**, gold p.162: top-3 là p.163 (câu hỏi gợi ý "A list is mutable. A string is immutable."), p.129 và p.161. Chunk chứa quy tắc đầy đủ (p.162, c02) không vào top-3, dù vẫn còn nguyên trong một chunk. Đây là lỗi xếp hạng của embedding, không phải lỗi chunking. A lại lấy được p.162 ở rank 3 nhưng chunk bị cắt tại "don'" nên vẫn không đủ evidence.
  2. **t02 (A)**, gold p.170: evidence bị tách giữa rank 1 ("…should not be used as default val") và rank 2 ("(such as lists) should not be used as default values."). Chỉ báo `evidence_split_across_chunks` bắt được trường hợp này. Thêm một lỗi trên dev: **q10 (B/C)** có đúng trang 130 nhưng chunk trả về là bảng `range()`, không phải đoạn "inclusive of the start and exclusive of the end".
- **Chiến lược chọn và điều kiện áp dụng:** Chọn **C** cho corpus này. Đó là chunk theo cấu trúc, cộng thêm filter `chapter` khi người dùng cung cấp ngữ cảnh chương. Filter chỉ nên bật khi ngữ cảnh đáng tin; filter sai chương sẽ loại mất đáp án. Grounding thủ công bằng nhau ở cả ba cấu hình (1,83/2), nên lợi thế của B và C nằm chủ yếu ở thứ hạng (Hit@1) và độ mạch lạc, chưa phải ở việc đủ bằng chứng.
- **Hạn chế:**
  - Test chỉ có 6 câu: chênh 1 câu tương ứng 17 điểm phần trăm, nên không tổng quát được ngoài corpus này.
  - Nhãn do AI đề xuất và chỉ một người (học viên) rà soát, nên có thể bị neo theo đề xuất ban đầu; chưa có người chấm thứ hai độc lập.
  - Evidence Hit dùng so khớp chuỗi chặt, nên bỏ qua trường hợp evidence bị cắt một từ cuối (A/t02).
  - HNSW là tìm kiếm xấp xỉ.
  - Thời gian đo trên một máy CPU, một lần chạy, chưa lặp lại.
  - Câu hỏi do tác giả viết sau khi đọc corpus nên có thể dễ hơn câu hỏi thực tế.
  - **Nhật ký sửa lỗi sau khi đã chạy test** (không sửa nào đổi cấu hình hay bộ câu hỏi, và top-3 của mọi câu vẫn giống lần chạy đầu):
    1. Chỉ báo "evidence split" trước đây ghép text, không xử lý được overlap; đã chuyển sang ghép theo khoảng ký tự.
    2. `char_start`/`char_len` bị lệch do strip (33 chunk A, 6 chunk B); đã thay bằng span chính xác `char_start`/`char_end` và thêm `sections_covered`. Text không đổi nên vector không đổi.
    3. **Lỗi index:** khi ingest, bước kiểm tra nạp lại ghi đè (upsert) lại đúng các ID vừa ghi. Ngay sau đó, Chroma trả về rank 3 sai cho q03 và q05 ở C (khác B dù vector giống hệt); chạy lại thì đúng. Đã sửa: upsert bỏ qua chunk không đổi (so `content_hash` + metadata), nên nạp lại ghi 0 chunk; mỗi truy vấn được đối chiếu với brute-force và kết quả lưu ở `ann_equals_exact_top3`.
    4. Thêm truy vấn warm-up trước khi đo ms/query (trước đó A, chiến lược chạy đầu tiên, bị tính cả thời gian khởi động model).
- **Nếu làm lại:**
  - Gắn đáp án trắc nghiệm vào đúng câu hỏi và cho phép chunk nối qua ranh giới trang, vẫn giữ `page_start`/`page_end`.
  - Thêm "contextual header" (chương › section) vào text khi embed.
  - Thử hybrid BM25 cho các câu chứa từ khóa code (`range()`, `elif`).
  - Thêm câu test và người chấm thứ hai.
  - Dùng parser giữ thụt lề code, ví dụ PyMuPDF.

**Công cụ AI:** Claude (Claude Code) hỗ trợ viết code, câu hỏi và đề xuất nhãn chấm (học viên đã rà soát và xác nhận). Mọi số liệu đều sinh từ lần chạy thật; evidence được kiểm bằng script.
