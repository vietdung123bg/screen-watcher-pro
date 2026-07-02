# 03 — API Specification

> Chương **10** của docx. Đặc tả 5 endpoint của Tool Watcher API Server.
> Đây là đầu vào của task **T01 (API contract)**, **T02 (skeleton)**, **T03 (`/chat`)**.

---

## 10.1. API Summary

| Method | Endpoint | Mục đích | Priority |
|---|---|---|---|
| GET | `/health` | Kiểm tra server còn hoạt động | Must |
| POST | `/chat` | Nhận message từ Jupyter → trả lời bằng AI | Must |
| POST | `/watcher/run` | Trigger watcher thủ công | Should |
| GET | `/watcher/latest-result` | Lấy kết quả watcher gần nhất | Should |
| GET | `/watcher/audit/{execution_id}` | Lấy audit artifact theo execution id | Could |

---

## 10.2. `POST /chat`

**Request**
```json
{
  "session_id": "local-demo-session",
  "message": "Hãy tóm tắt trạng thái watcher gần nhất",
  "include_latest_watcher_context": true,
  "max_context_chars": 6000
}
```

**Response (success)**
```json
{
  "session_id": "local-demo-session",
  "reply": "Watcher gần nhất phát hiện rule daily_sync_failed...",
  "model": "azure/gpt-4o-mini",
  "provider": "azure_openai",
  "status": "success",
  "execution_context_used": true
}
```

**Field notes**
| Field | Kiểu | Ghi chú |
|---|---|---|
| `session_id` | string | Khóa gom hội thoại (conversation store) |
| `message` | string | Bắt buộc, giới hạn `max_message_length` (mặc định 4000) |
| `include_latest_watcher_context` | bool | Mặc định lấy từ config `chat.include_latest_watcher_context_default` |
| `max_context_chars` | int | Cắt bớt OCR/context trước khi vào prompt (mặc định 6000) |
| `execution_context_used` | bool | Cờ audit: AI có thật sự dùng watcher context không |

---

## 10.3. Error Response (chuẩn hóa — FR10)

```json
{
  "status": "error",
  "error_code": "OPENCODE_TIMEOUT",
  "message": "OpenCode CLI không phản hồi trong 120 giây",
  "retryable": true
}
```

**Bộ error_code đề xuất**
| error_code | Khi nào | retryable |
|---|---|---|
| `OPENCODE_TIMEOUT` | Adapter vượt timeout | true |
| `PROVIDER_UNAVAILABLE` | Provider/model lỗi, config sai | false |
| `INVALID_REQUEST` | Thiếu message / JSON sai | false |
| `CONTEXT_UNAVAILABLE` | Không đọc được latest watcher result | true |
| `INTERNAL_ERROR` | Lỗi không lường trước | true |

> ⚠️ **Không** trả stack trace thô cho client. Log chi tiết ở server, trả JSON gọn cho client.

---

## Đặc tả các endpoint còn lại

### `GET /health`
- Response: `{ "status": "ok" }` (có thể kèm `version`, `provider`, `uptime`).

### `POST /watcher/run`
- Trigger `CaptureService.capture_targets(...)`. Trả `execution status` + `execution_id`.
- Cần cờ config `watcher_context.allow_manual_trigger_from_api: true` mới cho chạy.

### `GET /watcher/latest-result`
- Trả `execution_id`, `ocr_text`, `matched_rules`, `execution_time`, `email_status` gần nhất.

### `GET /watcher/audit/{execution_id}`
- Trả audit artifact: screenshot path, OCR text, result JSON theo execution id.

---

## ✅ Checklist thực hiện
- [ ] Định nghĩa Pydantic model: `ChatRequest`, `ChatResponse`, `ErrorResponse`
- [ ] `GET /health` trả `{status: ok}` (T02)
- [ ] `POST /chat` validate input → gọi orchestrator → trả `ChatResponse` (T03)
- [ ] Middleware/handler bắt exception → map sang `ErrorResponse` chuẩn (FR10)
- [ ] `GET /watcher/latest-result` đọc từ context service (T05)
- [ ] `POST /watcher/run` gọi capture service (Should)
- [ ] `GET /watcher/audit/{execution_id}` (Could — có thể để Phase 2)
- [ ] Bật CORS cho Jupyter (`enable_cors: true`) nếu cần

## Definition of Done
- `GET /health` và `POST /chat` chạy được, test bằng `curl`/Notebook.
- Lỗi luôn trả JSON theo schema `ErrorResponse`, không lộ traceback.

---

👉 Tiếp theo: [04-tich-hop-ai-opencode.md](04-tich-hop-ai-opencode.md)
