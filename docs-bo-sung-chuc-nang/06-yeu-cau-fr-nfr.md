# 06 — Yêu cầu Chức năng (FR) & Phi chức năng (NFR)

> Chương **13–14** của docx. Dùng làm **checklist nghiệm thu**.

---

## 13. Functional Requirements

| ID | Requirement | Priority | Acceptance | ☑ |
|----|-------------|----------|------------|----|
| FR01 | Server expose `/health` | Must | `GET /health` trả status ok | [ ] |
| FR02 | Server expose `/chat` | Must | Client gửi message → nhận reply | [ ] |
| FR03 | Server gọi OpenCode CLI để xử lý message | Must | Có stdout được parse thành reply | [ ] |
| FR04 | Hỗ trợ provider Llama **hoặc** Azure OpenAI | Must | Đổi provider bằng config | [ ] |
| FR05 | Bổ sung latest watcher context vào prompt | Must | AI trả lời dựa trên OCR + rule | [ ] |
| FR06 | Jupyter Notebook có chatbox client | Must | User nhập message + xem bot reply | [ ] |
| FR07 | `/watcher/latest-result` trả dữ liệu mới nhất | Should | Có execution id, OCR text, rule result | [ ] |
| FR08 | `/watcher/run` trigger watcher thủ công | Should | Trả execution status | [ ] |
| FR09 | Conversation store lưu lịch sử theo session | Could | Xem lại message trong session | [ ] |
| FR10 | API trả error response chuẩn | Must | Không trả stack trace thô | [ ] |

> Chi tiết endpoint: [03](03-api-specification.md) · AI: [04](04-tich-hop-ai-opencode.md) · Client: [05](05-jupyter-chatbox-client.md).

---

## 14. Non-Functional Requirements

| Category | Requirement | Target MVP | ☑ |
|----------|-------------|------------|----|
| Performance | API không treo vô hạn khi AI chậm | Timeout 120–180s | [ ] |
| Reliability | Lỗi AI provider không crash server | Trả error JSON chuẩn | [ ] |
| Security | API mặc định bind localhost | host `127.0.0.1` | [ ] |
| Security | API key không hard-code | Environment variables | [ ] |
| Maintainability | Provider & model config-driven | YAML config | [ ] |
| Observability | Log đủ request id, session id, duration | Python logging | [ ] |
| Portability | Chạy Windows & Linux | Python ≥ 3.9 | [ ] |
| Testability | Có mock OpenCode CLI adapter | Unit + integration test | [ ] |

> Security chi tiết: [07](07-data-security.md) · Test: [08](08-testing-risk.md).

---

## Definition of Done
- Toàn bộ **Must** (FR01–FR06, FR10) đạt acceptance.
- NFR bind localhost, timeout, error JSON, config-driven được kiểm chứng.

---

👉 Tiếp theo: [07-data-security.md](07-data-security.md)
