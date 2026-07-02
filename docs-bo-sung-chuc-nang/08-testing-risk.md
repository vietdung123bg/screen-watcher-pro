# 08 — Testing Strategy & Risk Assessment

> Chương **18–19** của docx. Đầu vào của task **T07 (test + mock provider)**.

---

## 18. Testing Strategy

| Test Type | Mục tiêu | Ví dụ | ☑ |
|---|---|---|----|
| Unit Test | Kiểm tra từng module | Prompt Builder, Config Loader, Adapter parser | [ ] |
| API Test | Kiểm tra endpoint | `/health`, `/chat`, `/watcher/latest-result` | [ ] |
| Integration Test | Server gọi OpenCode CLI | Mock OpenCode hoặc model thật | [ ] |
| Notebook Test | Kiểm tra chatbox | Gửi message + hiển thị reply | [ ] |
| Error Test | Kiểm tra lỗi | Timeout, provider unavailable, invalid JSON | [ ] |
| Security Test | Log & secret | Không lộ API key trong log | [ ] |

### 18.1. Demo Test Scenarios (dùng cho workshop)
- [ ] Server start OK, `/health` trả ok
- [ ] Jupyter gửi message đơn giản → nhận reply
- [ ] Watcher latest result có OCR text `failed`
- [ ] User hỏi "trạng thái watcher gần nhất là gì" → AI nhắc rule matched + hành động đề xuất
- [ ] Đổi provider config Llama → Azure OpenAI, chạy lại demo OK

> **Mock provider (T07):** adapter cần mock mode (xem [04](04-tich-hop-ai-opencode.md)) để test/demo không phụ thuộc provider thật.

---

## 19. Risk Assessment & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| OpenCode CLI timeout | Client chờ lâu / lỗi demo | Medium | Cấu hình timeout + mock mode |
| Provider config sai | Không gọi được AI | Medium | Validate config khi start server |
| OCR context quá dài | Prompt vượt giới hạn model | **High** | Giới hạn `max_context_chars` + summarize |
| AI hallucination | Trả lời không dựa dữ liệu | Medium | Prompt yêu cầu nói rõ khi thiếu dữ liệu |
| API local bị expose | Rủi ro bảo mật | Low (demo) | Bind localhost + token nếu ra mạng |
| Notebook widget lỗi | Demo không mượt | Medium | Fallback `input()` loop / requests đơn giản |

### ✅ Việc cần làm từ bảng rủi ro
- [ ] Validate provider/model/key khi start server (fail fast)
- [ ] Hàm cắt/summarize OCR trước khi vào prompt
- [ ] Chỉ dẫn prompt "nếu thiếu dữ liệu, nói rõ chưa đủ"
- [ ] Mock mode cho adapter
- [ ] Fallback client không dùng widget

## Definition of Done
- Có bộ unit + API test chạy pass (kể cả mock).
- Đã chạy đủ 5 demo scenario trên máy local.

---

👉 Tiếp theo: [09-ke-hoach-trien-khai.md](09-ke-hoach-trien-khai.md)
