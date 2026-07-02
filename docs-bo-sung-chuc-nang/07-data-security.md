# 07 — Data, State, Audit, Conversation & Security

> Chương **15–16** của docx.

---

## 15.1. Data Objects

| Object | Mô tả | Nguồn | Trạng thái |
|---|---|---|---|
| `ChatMessage` | Message user gửi từ Notebook | Jupyter client | 🆕 |
| `ChatResponse` | Reply server trả về | API Server | 🆕 |
| `WatcherResult` | Kết quả capture/OCR/rule | Watcher core | ✅ có (`TargetResult`) |
| `AuditArtifact` | Screenshot, OCR text, result JSON | Audit store | ✅ có (file + DB) |
| `ConversationSession` | Lịch sử hội thoại | Conversation store | 🆕 |

## 15.2. Store Responsibilities

| Store | Vai trò | MVP Recommendation | Trạng thái |
|---|---|---|---|
| State Store | Cooldown, last sent, last execution | JSON / SQLite | ✅ có (`cooldown_state` trong SQLite) |
| Audit Store | Screenshot, OCR text, result mỗi lần chạy | File system | ✅ có (`data/screenshots`, `data/ocr_results`, DB) |
| Conversation Store | Lịch sử chat theo session | In-memory (demo) → SQLite (sau) | 🆕 |

> MVP **không cần DB phức tạp** — file system + SQLite là đủ. Khi lên production multi-user,
> Conversation & Audit Store nên chuẩn hóa thành DB có **retention policy**.

### ✅ Checklist Conversation Store (FR09 — Could)
- [ ] Interface: `append(session_id, role, content)`, `get_history(session_id)`
- [ ] MVP: dict in-memory theo `session_id`
- [ ] (Sau MVP) backend SQLite + retention

---

## 16. Security & Governance

- [ ] Server mặc định **chỉ bind `127.0.0.1`** (tránh expose ra mạng ngoài ý muốn)
- [ ] Nếu bind `0.0.0.0` → **bắt buộc** API token hoặc reverse proxy có auth
- [ ] **Không** ghi API key / SMTP password / bearer token vào log
- [ ] **Không** đưa toàn bộ screenshot / OCR nhạy cảm vào prompt nếu không cần
- [ ] Có `max_context_chars` giới hạn dữ liệu gửi sang provider
- [ ] Có **audit flag** để biết AI đã dùng watcher data nào khi trả lời (`execution_context_used`)

### 16.1. Security Config mẫu
```yaml
server:
  host: 127.0.0.1
  port: 8000
  require_api_token: false

security:
  mask_sensitive_log: true
  max_context_chars: 6000
  allow_external_bind: false

secrets:
  azure_openai_api_key_env: AZURE_OPENAI_API_KEY
  llama_api_key_env: LLAMA_API_KEY
```

> Đồng bộ với `.env` hiện có (`OPENROUTER_API_KEY`, `WATCHER_SMTP_PASSWORD`) — thêm 2 biến provider AI.

## Definition of Done
- Server không bind ra ngoài trừ khi bật cờ + token.
- Log đã mask secret; prompt bị giới hạn `max_context_chars`.

---

👉 Tiếp theo: [08-testing-risk.md](08-testing-risk.md)
