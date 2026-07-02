# 02 — Kiến trúc tổng thể & Component Design

> Chương **8–9** của docx: Solution Architecture, Container/Deployment view, Component Design.
> Kèm **mapping với code hiện tại** và **danh sách module cần tạo mới**.

---

## 8.1. Context Diagram (dạng text)

```
[User]
  │ chat message
  ▼
[Jupyter Notebook Local Web Client]
  │ HTTP REST
  ▼
[Tool Watcher API Server]
  │ command execution              │ read context
  ▼                                ▼
[OpenCode CLI]              [Watcher Audit, State, OCR Result, Rule Result]
  │ provider API call
  ▼
[Llama API | Azure OpenAI API]
```

## 8.2. Container Diagram

| Container | Trách nhiệm | Công nghệ | Trạng thái |
|---|---|---|---|
| Jupyter Client | Giao diện chatbox local | Jupyter, ipywidgets, requests | 🆕 |
| API Server | Expose REST + điều phối request | FastAPI, Uvicorn | 🆕 |
| Chat Orchestrator | Tạo prompt, gắn context, gọi AI adapter | Python service layer | 🆕 |
| OpenCode CLI Adapter | Gọi OpenCode CLI + chuẩn hóa output | subprocess, timeout | 🆕 |
| Watcher Core | Capture, OCR, Rule Engine, Notification | Python modules | ✅ Đã có (`app/core`, `app/services`) |
| Storage | State, audit, conversation, log | JSON / SQLite / file | ✅ Một phần (`app/db`) + 🆕 conversation |

## 8.3. Deployment View

```
Local machine / internal workstation
 ├─ Tool Watcher API Server : http://127.0.0.1:8000
 ├─ Jupyter Notebook        : http://127.0.0.1:8888
 ├─ OpenCode CLI            : trong PATH
 ├─ Watcher data directory  : ./data
 └─ Environment variables   : API keys (Azure/Llama), SMTP
```

---

## 9. Component Design — module cần tạo

| Module (đề xuất) | Vai trò | Ghi chú triển khai |
|---|---|---|
| `app/api/api_server.py` | Khởi động FastAPI app | Load config, mount routes, bind 127.0.0.1 |
| `app/api/routes/chat_routes.py` | Endpoint `/chat` | Validate request → gọi orchestrator |
| `app/api/routes/watcher_routes.py` | `/watcher/run`, `/watcher/latest-result`, `/watcher/audit/{id}` | Kết nối watcher core |
| `app/services/chat_orchestrator.py` | Điều phối hội thoại | Build prompt → call adapter → format reply |
| `app/services/prompt_builder.py` | Tạo prompt chuẩn | Inject OCR / rule / audit / user message |
| `app/services/opencode_cli_adapter.py` | Gọi OpenCode CLI | Timeout, parse stdout/stderr/exit code |
| `app/services/conversation_store.py` | Lưu lịch sử chat | Memory (MVP) → SQLite (sau) |
| `app/provider_config.py` | Quản lý provider | Llama / Azure OpenAI |
| `app/services/watcher_context_service.py` | Đọc latest watcher result | Trả context đã chuẩn hóa |

### Component Interaction
```
Chat Route
 └─> Chat Orchestrator
       ├─> Watcher Context Service   (đọc OCR + rule gần nhất)
       ├─> Prompt Builder            (ráp prompt)
       ├─> OpenCode CLI Adapter ─> OpenCode CLI ─> Provider
       └─> Conversation Store        (lưu message + reply)
 └─> Response DTO
```

---

## 🔗 Mapping với code hiện tại (điểm tích hợp)

| Nhu cầu mới | Tái dùng từ code cũ |
|---|---|
| Watcher Context Service đọc "latest result" | `Repository.list_screenshots()`, `get_ocr_for_screenshot()`, `list_rule_evaluations()`, `list_notifications()` trong `app/db/repository.py` |
| `/watcher/run` trigger thủ công | `CaptureService.capture_targets()` trong `app/services/capture_service.py` |
| Cấu trúc kết quả 1 lần chụp | `TargetResult` (capture_service.py) + `NotificationOutcome` (notification_service.py) |
| Load YAML config | `config.load_app_config()` — **mở rộng** thêm khối `server`, `chat`, `ai`, `opencode` (xem [10](10-appendix-config-prompt.md)) |
| Đường dẫn / dirs | `app/config.py` (`DATA_DIR`, `OCR_DIR`, `SCREENSHOT_DIR`, `LOG_DIR`) |
| Logging | `config.setup_logging()` |

> **Quyết định cần chốt (T05):** "latest result" lấy từ đâu?
> - **Cách A (khuyên dùng MVP):** query trực tiếp SQLite qua `Repository` (không thêm file).
> - **Cách B:** sau mỗi capture, ghi `./data/latest_result.json` (đúng như YAML mẫu `watcher_context.latest_result_path`).
>   Tiện cho việc đọc context không cần mở DB, nhưng phải giữ đồng bộ.

---

## ✅ Checklist thiết kế (làm trước khi code)
- [ ] Chốt package layout: tạo `app/api/` (+ `routes/`) hay để phẳng trong `app/services/`
- [ ] Chốt cách đọc latest result (Cách A hay B ở trên)
- [ ] Chốt DTO dùng chung (Pydantic model): `ChatRequest`, `ChatResponse`, `ErrorResponse`, `WatcherContext`
- [ ] Chốt thư viện: FastAPI + Uvicorn + Pydantic → thêm vào `requirements.txt`
- [ ] Chốt entry point riêng cho API (`run_api.py`) tách khỏi `run.py` (desktop UI)

## Definition of Done (chương này)
- Có sơ đồ package + danh sách file mới được đội đồng thuận.
- Đã bổ sung `requirements.txt` (fastapi, uvicorn, requests, ipywidgets…).
- Đã thống nhất nguồn "latest result".

---

👉 Tiếp theo: [03-api-specification.md](03-api-specification.md)
