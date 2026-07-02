# 09 — Kế hoạch triển khai (Task Board chính)

> Chương **17 & 20** của docx: User Stories, Backlog, Sprint tasks, MVP, Roadmap, Workshop.
> **Đây là file trung tâm để theo dõi tiến độ** — bám các task T01→T08 dưới đây.

---

## 17. User Stories & Acceptance Criteria

| Epic | User Story | Acceptance Criteria |
|---|---|---|
| API Server | Là user, tôi muốn `/health` để kiểm tra trạng thái | `GET /health` trả status ok |
| Chatbox | Là user, tôi muốn nhập câu hỏi trong Notebook | Có input, button, hiển thị reply |
| AI Integration | Là dev, tôi muốn server gọi AI qua OpenCode CLI | Adapter chạy command + parse output |
| Watcher Context | Là operation, tôi muốn AI hiểu watcher result gần nhất | Prompt có OCR text + matched rules |
| Provider Config | Là admin, tôi muốn đổi Llama/Azure qua config | Không sửa code khi đổi provider |
| Error Handling | Là user, tôi muốn lỗi hiển thị dễ hiểu | Timeout & provider error trả JSON chuẩn |

---

## 17.1. Sprint Backlog — Task Board

| Task | Mô tả | Owner Role | Est. | Tài liệu | Trạng thái |
|------|-------|-----------|------|----------|-----------|
| **T01** | Thiết kế API contract + request/response model | BA + Dev | 2h | [03](03-api-specification.md) | [ ] |
| **T02** | Tạo FastAPI server skeleton (`/health`) | Backend Dev | 3h | [02](02-kien-truc-tong-the.md), [03](03-api-specification.md) | [ ] |
| **T03** | Xây endpoint `/chat` | Backend Dev | 3h | [03](03-api-specification.md) | [ ] |
| **T04** | Xây OpenCode CLI Adapter | AI Integration Dev | 4h | [04](04-tich-hop-ai-opencode.md) | [ ] |
| **T05** | Xây watcher context service | Backend Dev | 3h | [02](02-kien-truc-tong-the.md), [07](07-data-security.md) | [ ] |
| **T06** | Tạo Jupyter chatbox (ipywidgets) | Client Dev | 2h | [05](05-jupyter-chatbox-client.md) | [ ] |
| **T07** | Viết test case + mock provider | QA | 3h | [08](08-testing-risk.md) | [ ] |
| **T08** | Chuẩn bị demo script + slide | PO + Presenter | 2h | mục "Workshop" dưới | [ ] |

> **Thứ tự đề xuất:** T01 → T02 → (T04 song song T05) → T03 (ráp orchestrator) → T06 → T07 → T08.

---

## 20.1. MVP Definition (nghiệm thu Phase 1)
- [ ] FastAPI server chạy local
- [ ] `/health` và `/chat` hoạt động
- [ ] Jupyter chatbox gửi message + nhận reply
- [ ] Server gọi OpenCode CLI với provider cấu hình
- [ ] Server gắn latest watcher context vào prompt
- [ ] Có logging, timeout, error response cơ bản

## 20.2. Roadmap

| Phase | Nội dung | Kết quả |
|---|---|---|
| **Phase 1** | API Server, Jupyter Chatbox, OpenCode CLI Adapter | Demo MVP |
| **Phase 2** | Conversation Store, Streaming, Retry, prompt tốt hơn | Trải nghiệm chat tốt hơn |
| **Phase 3** | Web UI, Auth, multi-user, audit viewer | Internal product usable |
| **Phase 4** | RAG, MCP, workflow automation, action suggestion | AI Operation Platform |

## 20.3. Workshop Storyline (kịch bản trình bày — T08)
1. **Vấn đề:** hệ thống legacy chỉ có màn hình, khó giám sát bằng API.
2. **Tool gốc:** Screen Watcher chụp màn hình, OCR, kiểm tra rule, gửi email.
3. **Mở rộng:** expose API + chatbox bằng Jupyter.
4. **AI:** OpenCode CLI gọi Llama/Azure OpenAI phân tích context watcher.
5. **Giá trị:** từ screen monitoring → AI assisted operation chat.

### ✅ Checklist T08
- [ ] Demo script theo 5 scenario ([08](08-testing-risk.md))
- [ ] Slide theo storyline 5 bước
- [ ] Chuẩn bị dữ liệu watcher mẫu (một lần capture có rule matched)

## Definition of Done
- Toàn bộ checklist MVP (20.1) đạt.
- Demo chạy trơn tru trên máy local theo storyline.

---

👉 Phụ lục cấu hình: [10-appendix-config-prompt.md](10-appendix-config-prompt.md)
