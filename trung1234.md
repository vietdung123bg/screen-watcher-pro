# Phân tích yêu cầu: AI Chat cho Screen Watcher Pro (Component C → G)

> Bám vào kiến trúc thực tế của app hiện tại: SQLite + `Repository`, OCR qua OpenRouter (Qwen3-VL), GUI Tkinter notebook, config `.env` + `config/rules.yaml`.

## Bối cảnh quan trọng trước khi phân tích

App hiện tại **chưa có HTTP server** và **chưa có lớp AI nào**. Các mã FR/T (FR04–FR09, T04–T06) đến từ tài liệu spec bên ngoài, **không có trong repo**. Nghĩa là ngoài 5 component C–G, còn ngầm cần **2 thứ chưa được nêu tên**:

1. **Một HTTP server** (`POST /chat`) — vì D yêu cầu "validate config khi start server" và G gọi `POST /chat`. Đề xuất **FastAPI** (hợp với startup-validate của D). Đây là *xương sống* mà C, D, E, F cắm vào.
2. **Một `AIResponse` model** (dataclass) — vì C "trả AIResponse". Cần định nghĩa dùng chung.

**Thứ tự phụ thuộc / thứ tự build đề xuất:** `D → C → E → F → server /chat → G`.

---

## C. OpenCode CLI Adapter (`opencode_cli_adapter.py`) — 🆕 T04

**Bản chất:** wrapper `subprocess` quanh binary `opencode`, biến (prompt + config) → `AIResponse`. Đây là *chỗ duy nhất* được phép chạm CLI.

| Khía cạnh | Phân tích |
|---|---|
| Đầu vào | prompt (đã build sẵn), `ai.working_dir`, model string (từ D) |
| Đầu ra | `AIResponse(reply, ok, error_code, raw?, latency_ms?)` |
| Điểm cần chốt | Truyền prompt qua **arg** hay **stdin**? Prompt chứa OCR text tiếng Việt/Hàn + có thể rất dài → **nên dùng stdin** hoặc temp file, tránh giới hạn độ dài arg và lỗi escaping/shell-injection. Bắt buộc `subprocess.run([...], shell=False)` với list args. |

**Yêu cầu bắt buộc — đánh giá:**

- **Timeout** → `subprocess.run(..., timeout=N)`, bắt `subprocess.TimeoutExpired` → `error_code="OPENCODE_TIMEOUT"`. ✅ đúng, nhưng spec đang **thiếu 3 case**: binary không tồn tại (`FileNotFoundError` → `OPENCODE_NOT_FOUND`), exit code ≠ 0 (`OPENCODE_ERROR`), và mock.
- **Working dir an toàn** → `cwd=ai.working_dir`; validate path tồn tại + là thư mục, fail sớm nếu không.
- **Mock mode** → rất cần thiết: máy dev (macOS) và CI thường không có provider thật. Bật qua `ai.mock: true` trong YAML **hoặc** khi thiếu API key. Reply giả lập có prefix rõ (`[MOCK]`) để không nhầm reply thật.
- **Không log secret** → adapter **không** in `os.environ` hay full command nếu key nằm trong đó. Vì key lấy từ env (D) nên **không** nằm trên command line → tốt. Chỉ log `model` + `latency`, **không** log prompt đầy đủ (chứa OCR nhạy cảm) — chỉ log độ dài.

**Khuyến nghị:** `AIResponse` là dataclass ổn định, adapter **không bao giờ raise ra ngoài** — mọi lỗi gói vào `error_code`. Server/G chỉ đọc `ok` + `error_code`.

---

## D. Provider Config (`provider_config.py`) — 🆕 FR04 (Must)

**Bản chất:** map `ai.provider` (`llama` | `azure`) → prefix model + nguồn API key, để đổi provider **chỉ bằng sửa YAML**.

**Khớp codebase:** pattern này *đã tồn tại* — `app/config.py` (dòng 26–28) đọc key từ env + model từ env. Nên **theo đúng convention đó**, không phát minh cơ chế mới.

| Yêu cầu | Phân tích |
|---|---|
| Map provider→prefix | `azure` → `azure/<model>`, `llama` → `llama/<model>` (khớp command mục C: `--model azure/gpt-4o-mini`). |
| Key từ env | `AZURE_OPENAI_API_KEY`, `LLAMA_API_KEY`. Thêm vào `.env.example`. |
| **Validate fail-fast khi start** | Phần *giá trị nhất*. Check lúc boot server: (1) `provider` thuộc tập hợp lệ; (2) env key tương ứng tồn tại (trừ mock mode); (3) `model` non-empty; (4) `working_dir` tồn tại. Sai → raise + thoát, không cho server chạy với config hỏng. |

**Rủi ro:** đừng để validation *chỉ* chạy lúc request đầu tiên — mất ý nghĩa "fail fast". Gắn vào startup event của server.

**Thiết kế:** nên có object `ProviderConfig` (`provider`, `model_full`, `api_key`, `env_var_name`, `working_dir`, `mock`) mà C nhận vào — tách bạch "đọc/validate config" (D) khỏi "chạy CLI" (C).

---

## E. Watcher Context Service (`watcher_context_service.py`) — 🆕 FR05 (Must), T05

**Component "linh hồn"** — biến chatbot rỗng thành trả lời dựa trên OCR + rule thật.

### Quyết định A vs B → **Chọn A (đọc trực tiếp SQLite). Rõ ràng.**

Lý do bám codebase:

- App **đã có** `Repository` (`app/db/repository.py`) với locking đa luồng (`database.py`, `check_same_thread=False`) và sẵn query cần dùng: `list_screenshots`, `get_ocr_for_screenshot`, `list_rule_evaluations`, `list_notifications`.
- "Latest watcher result" = screenshot mới nhất → `list_screenshots()[0]` (đã `ORDER BY s.id DESC`) → join OCR + rule_evaluations + notifications. Không cần viết mới nhiều, chỉ 1 method tổng hợp.
- Cách B (`data/latest_result.json`) tạo **nguồn sự thật thứ hai** phải đồng bộ với DB → dễ lệch, thêm điểm hỏng, thêm code ghi file trong luồng capture. Không đáng.

**Cảnh báo về A:** `Repository` dùng **1 connection dùng chung** + lock. Nếu server chạy trong **process khác** với GUI (khả năng cao — FastAPI riêng), **không share được connection object đó**. Server cần **mở connection SQLite riêng, read-only**: `sqlite3.connect("file:...?mode=ro", uri=True)`. SQLite chịu nhiều reader → ổn. Đây là điểm dễ vấp nhất của Cách A.

**Đầu ra chuẩn hóa (gọn, đủ nhét prompt, KHÔNG đổ nguyên OCR khổng lồ):**
`target_app`, `window_title`, `captured_at`, `ocr_text` (cắt bớt để tiết kiệm token), `matched_rules[]`, `notifications[]`.

---

## F. Conversation Store (`conversation_store.py`) — 🆕 FR09 (Could)

**Bản chất:** lưu history theo `session_id`. MVP = dict in-memory.

- Là **Could** → làm tối giản, đúng spec: `dict[session_id → list[messages]]`. Không cần DB.
- **Rủi ro cần lường trước để không refactor lớn:**
  1. Memory leak nếu session không xóa → giới hạn N tin nhắn/session hoặc TTL đơn giản.
  2. Nếu server **multi-worker** (uvicorn workers>1), dict in-memory không share giữa worker → chạy **1 worker** cho MVP (ghi rõ giả định này), hoặc chuyển SQLite sau.
- Định nghĩa interface (`append`, `get_history`, `clear`) sao cho bản SQLite sau này drop-in được — không lộ chi tiết dict ra ngoài.

---

## G. Jupyter Notebook Chatbox (`ipywidgets`) — 🆕 FR06 (Must), T06 — "web client"

**Bản chất:** client thuần — ô nhập + nút Gửi + vùng history → `POST /chat` → hiển thị `reply`. **Không chứa logic AI.** ✅ Ranh giới này đúng và phải giữ nghiêm.

| Khía cạnh | Phân tích |
|---|---|
| Giao tiếp | `requests.post(f"{base_url}/chat", json={session_id, message})`. `base_url` phải cấu hình được. |
| Xử lý lỗi thân thiện | Bắt `ConnectionError` (server chưa chạy) → "Không kết nối được server"; timeout; HTTP 4xx/5xx → hiện `error_code` từ AIResponse chứ không phải traceback. |
| Fallback `input()` loop | Khi `ipywidgets` không render (Jupyter thiếu extension / chạy terminal) → vòng `while` với `input()`. Đúng và thực dụng. |

**Rủi ro nhỏ:** ipywidgets output area cần `clear_output`/append đúng để không nhân đôi history. Là vấn đề UX widget, không phải logic — không đáng lo cho MVP.

---

## Tổng kết & khuyến nghị

**Điểm mạnh của spec:** ranh giới trách nhiệm sạch (adapter chỉ chạy CLI, client chỉ HTTP, context chỉ đọc DB); mock mode + fail-fast là 2 quyết định trưởng thành.

**3 lỗ hổng spec chưa nói mà cần chốt sớm:**

1. **Server `/chat` + `AIResponse`** chưa liệt kê thành component riêng — nhưng C/D/E/F đều cắm vào. Cần đặt tên (vd `chat_server.py` + `models.py`) và chọn framework (đề xuất **FastAPI**, hợp startup-validate của D).
2. **C thiếu 3 error case**: binary không tồn tại, exit≠0, mock — bổ sung vào enum `error_code`.
3. **E + connection**: server phải mở SQLite **read-only riêng**, không tái dùng connection của GUI (khác process).

**Quyết định E chốt ngay:** Cách A (SQLite trực tiếp, read-only connection), tái dùng logic query sẵn có. **Không** dùng `latest_result.json`.

### Thứ tự triển khai đề xuất

| Bước | Việc | Phụ thuộc |
|---|---|---|
| 1 | `models.py` (`AIResponse`) + `provider_config.py` (D) + validate | — |
| 2 | `opencode_cli_adapter.py` (C) + mock mode | D |
| 3 | `watcher_context_service.py` (E) — read-only SQLite | Repository sẵn có |
| 4 | `conversation_store.py` (F) — dict in-memory | — |
| 5 | `chat_server.py` — FastAPI `POST /chat`, startup validate | C, D, E, F |
| 6 | Jupyter chatbox (G) — ipywidgets + fallback `input()` | server /chat |

---

## Đã triển khai — Package `app/ai/`

| File | Component | Nội dung |
|---|---|---|
| `models.py` | — | `AIResponse` + enum error_code (`OPENCODE_TIMEOUT`/`NOT_FOUND`/`ERROR`, `BAD_WORKING_DIR`), `ChatRequest`, `ChatMessage` |
| `provider_config.py` | D | map azure/llama → prefix + env key, validate fail-fast |
| `opencode_cli_adapter.py` | C | subprocess `shell=False`, prompt qua stdin, timeout, mock, không log secret |
| `watcher_context_service.py` | E | SQLite read-only (`mode=ro`), lấy screenshot mới nhất + OCR/rule/email, cắt OCR |
| `conversation_store.py` | F | dict in-memory + trim retention, thread-safe |
| `chat_server.py` | server | FastAPI `POST /chat` + `/health`, validate provider lúc import (fail fast) |
| `chatbox.py` | G | ipywidgets UI + fallback `input()`, lỗi thân thiện |
