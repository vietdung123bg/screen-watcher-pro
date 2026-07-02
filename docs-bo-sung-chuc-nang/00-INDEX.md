# 📚 Bổ sung chức năng — Tool Watcher API Server + Jupyter AI Chatbox

> Bộ tài liệu này **chia nhỏ** file `PHỤ LỤC BỔ SUNG CHỨC NĂNG.docx` (21 chương)
> thành các file markdown theo dõi được, có **checklist thực hiện** và **mapping với code hiện tại**.
> Nguồn gốc: *Product Requirement Appendix v1.0 — 01/07/2026*.

---

## 🎯 Mục tiêu phần mở rộng (tóm tắt 1 dòng)

Biến **Screen Watcher** (desktop app đang chạy: chụp màn hình → OCR → rule → email) thành
**AI assisted operation assistant**: thêm **API Server** (FastAPI) + **Jupyter chatbox** (web client)
+ tích hợp **OpenCode CLI** gọi **Llama API / Azure OpenAI API** để hỏi đáp trên dữ liệu watcher.

```
[User] → [Jupyter Notebook web client] --HTTP--> [Tool Watcher API Server]
                                                        │
                                        đọc context ↙   ↘ gọi AI
                          [OCR / Rule / Audit / State]    [OpenCode CLI] → [Llama | Azure OpenAI]
```

---

## 🗂 Danh sách file & mapping với chương trong docx

| File | Nội dung | Chương docx | Loại |
|------|----------|-------------|------|
| [00-INDEX.md](00-INDEX.md) | Trang chủ, tiến độ tổng, cách dùng | Mục lục | 🧭 Điều hướng |
| [01-boi-canh-muc-tieu.md](01-boi-canh-muc-tieu.md) | Bối cảnh, pain point, tầm nhìn, mục tiêu, metrics, personas, scope | 1–7 | 📖 Ngữ cảnh |
| [02-kien-truc-tong-the.md](02-kien-truc-tong-the.md) | Kiến trúc giải pháp, container, component, module mới + mapping code cũ | 8–9 | 🏗 Thiết kế |
| [03-api-specification.md](03-api-specification.md) | Đặc tả 5 endpoint, request/response, error | 10 | 🏗 Thiết kế |
| [04-tich-hop-ai-opencode.md](04-tich-hop-ai-opencode.md) | OpenCode CLI adapter, command pattern, prompt composition | 11 | 🏗 Thiết kế |
| [05-jupyter-chatbox-client.md](05-jupyter-chatbox-client.md) | Web client Jupyter, trách nhiệm, code skeleton | 12 | 🏗 Thiết kế |
| [06-yeu-cau-fr-nfr.md](06-yeu-cau-fr-nfr.md) | Functional (FR01–FR10) + Non-functional requirements | 13–14 | ✅ Checklist |
| [07-data-security.md](07-data-security.md) | Data objects, store, conversation, security & governance | 15–16 | 🏗 Thiết kế |
| [08-testing-risk.md](08-testing-risk.md) | Chiến lược test, demo scenarios, rủi ro & giảm thiểu | 18–19 | ✅ Checklist |
| [09-ke-hoach-trien-khai.md](09-ke-hoach-trien-khai.md) | User story, backlog, sprint T01–T08, MVP, roadmap, workshop | 17, 20 | 📋 Task board |
| [10-appendix-config-prompt.md](10-appendix-config-prompt.md) | YAML config mẫu + prompt template | 21 | 📎 Phụ lục |

> 👉 **Bắt đầu thực hiện**: đọc [01](01-boi-canh-muc-tieu.md) để nắm bối cảnh → [02](02-kien-truc-tong-the.md) để thấy kiến trúc → rồi bám [09-ke-hoach-trien-khai.md](09-ke-hoach-trien-khai.md) làm task board chính (T01→T08).

---

## 📊 Tiến độ tổng thể (Master Checklist)

> ✅ **Bản web đã được dựng** trong thư mục [`web/`](../web/README.md): FastAPI server +
> Web UI (thay desktop) + API mới (`/health`, `/chat`, `/watcher/*`) + OpenCode CLI adapter.
> Chạy: `python web/run_web.py` → http://127.0.0.1:8000

### Phase 1 — MVP (mục tiêu workshop)
- [x] **T01** — Thiết kế API contract + request/response model → `web/backend/schemas.py`
- [x] **T02** — FastAPI server skeleton (`/health`) → `web/backend/app.py`, `routers/health_routes.py`
- [x] **T03** — Endpoint `/chat` → `routers/chat_routes.py`, `ai/chat_orchestrator.py`
- [x] **T04** — OpenCode CLI Adapter (+ mock mode) → `ai/opencode_cli_adapter.py`, `ai/provider_config.py`
- [x] **T05** — Watcher context service (đọc latest result) → `ai/watcher_context_service.py`
- [~] **T06** — Chatbox client → **Web UI tab "AI Chat"** đã có (`frontend/app.js`); Jupyter notebook client (ipywidgets) tùy chọn bổ sung → [05](05-jupyter-chatbox-client.md)
- [~] **T07** — Test case + mock provider → mock provider ✅; bộ unit/integration test tự động chưa viết → [08](08-testing-risk.md)
- [ ] **T08** — Demo script + slide → [09](09-ke-hoach-trien-khai.md)

> Ngoài API, bản web còn **chuyển toàn bộ UI desktop sang trình duyệt**: đăng nhập + buộc đổi
> mật khẩu, Chụp & OCR, Lịch sử, Rules & Email, Email đã gửi (+ gửi lại/gửi thử), Quản lý người dùng.

### Sau MVP (Phase 2–4)
- [ ] Conversation store bền vững (SQLite), streaming, retry, prompt tốt hơn
- [ ] Web UI production, Auth, multi-user, audit viewer
- [ ] RAG, MCP, workflow automation, action suggestion

> Chi tiết từng task (owner role, estimate, definition of done) nằm trong [09-ke-hoach-trien-khai.md](09-ke-hoach-trien-khai.md).

---

## 🧩 Cái gì ĐÃ CÓ vs cái gì LÀM MỚI

| Thành phần | Trạng thái | Vị trí |
|-----------|-----------|--------|
| Capture + OCR + Rule Engine | ✅ Đã có | `app/core/` |
| Cooldown + Email + decision trace | ✅ Đã có | `app/services/notification_service.py` |
| Orchestrate pipeline chụp | ✅ Đã có | `app/services/capture_service.py` |
| DB (screenshots/ocr/rule/notif) + repository | ✅ Đã có | `app/db/` |
| RBAC + Auth | ✅ Đã có | `app/services/auth.py` |
| Desktop UI (Tkinter) | ✅ Đã có | `app/ui/` |
| **API Server (FastAPI)** | 🆕 Làm mới | `app/api/` (đề xuất) |
| **Chat Orchestrator + Prompt Builder** | 🆕 Làm mới | `app/services/` |
| **OpenCode CLI Adapter** | 🆕 Làm mới | `app/services/` |
| **Watcher Context Service** | 🆕 Làm mới | `app/services/` |
| **Provider config (Llama/Azure)** | 🆕 Làm mới | `app/` + YAML |
| **Conversation Store** | 🆕 Làm mới | `app/services/` |
| **Jupyter chatbox (web client)** | 🆕 Làm mới | `notebooks/` (đề xuất) |

---

## 📌 Quy ước checkbox
- `[ ]` chưa làm · `[~]` đang làm · `[x]` xong.
- Mỗi file thực hiện đều có mục **"Definition of Done"** để biết khi nào coi là hoàn thành.

## ⚠️ Ghi nhớ
- Khi code thay đổi theo yêu cầu mới → **cập nhật `README.md`** cho khớp (quy ước dự án).
- API mặc định **bind `127.0.0.1`**, không hard-code API key (dùng environment variables).
