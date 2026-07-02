# 01 — Bối cảnh, Mục tiêu & Phạm vi

> Gộp chương **1–7** của docx: Executive Summary, Business Context, Vision/Objectives/Metrics,
> Stakeholders/Personas, Scope, Business Flow, Product Concept. Đây là phần **"vì sao làm"** — đọc để hiểu ngữ cảnh trước khi build.

---

## 1. Executive Summary

Bản gốc Tool Watcher tập trung: **chạy theo lịch → chụp màn hình → OCR → kiểm tra rule → gửi email**.
Phần mở rộng biến Tool Watcher thành **backend có API**, cho phép tương tác qua **Jupyter Notebook** dạng chatbox.

Luồng: Client gửi message → Server bổ sung context (OCR text, rule result, audit) → dùng **OpenCode CLI**
gọi **Llama API / Azure OpenAI API** → tổng hợp & phản hồi.

**Thông điệp sản phẩm:** Tool Watcher không chỉ quan sát & cảnh báo → trở thành **AI assisted operation assistant**,
giúp hỏi đáp và phân tích kết quả giám sát bằng ngôn ngữ tự nhiên.

| Điểm mở rộng | Giá trị |
|---|---|
| Expose API | Hoạt động như local server thay vì chỉ CLI theo lịch |
| Jupyter Chatbox | Giao diện chat nhanh cho demo/kiểm thử, không cần web app hoàn chỉnh |
| OpenCode CLI Adapter | Tách logic AI provider khỏi nghiệp vụ watcher, dễ đổi Llama ↔ Azure |
| AI assisted analysis | Hỏi AI về OCR, rule matched, trạng thái gần nhất, hành động đề xuất |

---

## 2. Business Context & Problem Statement

**Bối cảnh:** Nhiều hệ thống legacy không có API/webhook/log tập trung, chỉ hiển thị qua UI. Tool Watcher giải quyết
phần đầu (quan sát + cảnh báo). Nhưng **sau cảnh báo**, người vận hành vẫn phải tự mở log/screenshot để phân tích.

**Problem Statement:** Cần cơ chế **tương tác nhanh** để hỏi đáp / kiểm thử / phân tích dữ liệu watcher
**mà không cần xây frontend production**. Jupyter Notebook phù hợp: chạy local, widget đơn giản, gọi API bằng Python.

### Pain points cần giải quyết
| Pain Point | Tác động | Hướng giải quyết |
|---|---|---|
| Không có giao diện hỏi đáp | Phải tự đọc log & ảnh | Jupyter chatbox hỏi đáp trực tiếp |
| Kết quả OCR khó hiểu | Text dài, nhiễu, thiếu ngữ cảnh | AI tóm tắt OCR, chỉ điểm đáng chú ý |
| Rule matched thiếu giải thích | Owner không rõ vì sao cảnh báo | AI giải thích rule + keyword + severity |
| Demo workshop cần nhanh | Web frontend tốn thời gian | Jupyter là client demo đủ dùng |
| Nhiều AI provider | Khó hard-code từng provider | OpenCode CLI làm lớp tích hợp |

---

## 3. Product Vision, Objectives & Success Metrics

**Vision:** Tool Watcher = AI assisted operation assistant — vừa giám sát tự động vừa trao đổi ngôn ngữ tự nhiên
để hiểu nhanh trạng thái, nguyên nhân, hành động đề xuất.

**Objectives:**
- Expose API phục vụ chat, trigger watcher, truy vấn latest result.
- Jupyter Notebook làm local chatbox client (demo + test).
- Server dùng OpenCode CLI gọi Llama / Azure OpenAI.
- AI dùng context từ OCR text, matched rules, audit result, execution log.
- Kiến trúc **config-driven**: đổi provider/model/behavior không sửa code.

**Success Metrics (target MVP):**
| Metric | Target | Ý nghĩa |
|---|---|---|
| API readiness | Có `/health`, `/chat`, `/watcher/latest-result` | Đủ năng lực tích hợp client |
| Demo readiness | Chat được từ Jupyter trên máy local | Đáp ứng workshop |
| AI provider switch | Đổi Llama ↔ Azure bằng config | Chứng minh kiến trúc mở rộng |
| Context usefulness | AI trả lời dựa trên latest OCR + rule | Không phải chatbot rỗng |
| Operational safety | Timeout + error message rõ ràng | Không treo client khi AI chậm |

---

## 4. Stakeholders & Personas

| Stakeholder | Nhu cầu chính |
|---|---|
| Product Owner | Câu chuyện sản phẩm rõ, demo được, roadmap hợp lý |
| Business Analyst | User story, acceptance criteria, process flow |
| Developer | Kiến trúc, API contract, module design |
| QA | Test case, mock data, expected response |
| Operation Engineer (persona chính) | Hỏi nhanh trạng thái watcher + hành động xử lý |
| Trainer | Thấy rõ cách AI hỗ trợ product delivery |

- **Persona chính:** Operation/Support Engineer theo dõi dashboard legacy — muốn hỏi câu đơn giản
  ("trạng thái gần nhất?", "lỗi có nghiêm trọng không?", "rule nào kích hoạt?") thay vì đọc log dài.
- **Persona phụ:** PO/BA cần demo nhanh trong workshop.

---

## 5. Scope, Assumptions & Constraints

### ✅ In Scope (MVP)
- [ ] FastAPI (hoặc tương đương) expose REST API
- [ ] Jupyter client (requests / ipywidgets) làm chatbox
- [ ] Endpoint `/chat` nhận message → trả reply
- [ ] OpenCode CLI Adapter gọi qua subprocess an toàn
- [ ] Provider = Llama API **hoặc** Azure OpenAI API
- [ ] Server đọc latest watcher result để bổ sung context
- [ ] Logging, timeout, error handling, cấu hình YAML

### 🚫 Out of Scope (MVP)
- Web UI production đa người dùng
- Auth enterprise đầy đủ (SSO/OAuth)
- Realtime streaming bắt buộc
- Multi-tenant + phân quyền phức tạp
- Vector DB / RAG nâng cao
- Triển khai cloud public production

### Assumptions
- Tool Watcher đã tạo được OCR text, rule result, audit artifact. ✅ (đã có trong `app/`)
- Jupyter chạy cùng máy/cùng mạng với API Server.
- OpenCode CLI đã cài + cấu hình provider.
- Azure OpenAI / Llama đã có endpoint, key, model hợp lệ.

### Constraints
- Jupyter chỉ hợp demo/internal test, không phải frontend production.
- OpenCode CLI có thể timeout nếu model chậm → cần timeout + mock mode.
- OCR text dài → cần cắt ngắn / summarize trước khi vào prompt (`max_context_chars`).
- Local API mặc định **chỉ bind `127.0.0.1`**.

---

## 6. Business Flow: As-Is → To-Be

**As-Is:** Scheduler → chụp → OCR → rule → (match) gửi email → owner đọc email → **tự mở screenshot/OCR/log phân tích thủ công**.

**To-Be:**
1. Scheduler **hoặc API** trigger Tool Watcher
2. Tool Watcher tạo OCR text + rule result + audit
3. User mở Jupyter chatbox
4. User hỏi server về trạng thái/lỗi
5. Server bổ sung latest watcher context
6. Server gọi OpenCode CLI → Llama/Azure OpenAI
7. Server trả câu trả lời **có ngữ cảnh** về Notebook

| Khía cạnh | Trước | Sau |
|---|---|---|
| Tương tác | Email thụ động | Hỏi đáp chủ động |
| Phân tích | Đọc log thủ công | AI tóm tắt + giải thích |
| Demo | Xem file riêng lẻ | Demo trực tiếp bằng chatbox |
| Tích hợp AI | Chưa có | Qua OpenCode CLI + provider config |

---

## 7. Product Concept mở rộng

Định vị Tool Watcher là **server nội bộ có API**. Server trả lời không chỉ dựa trên message hiện tại mà còn dựa
trên **context** do watcher thu thập: OCR text, rule result, screenshot path, email status, execution metadata.

### Core Capabilities
| Capability | Mô tả | MVP |
|---|---|---|
| Chat API | Nhận message → trả reply | ✅ Có |
| Watcher context injection | Gắn latest OCR + rule result vào prompt | ✅ Có |
| Manual watcher trigger | Chạy watcher qua API | 🔶 Có thể có |
| OpenCode CLI integration | Gọi AI qua OpenCode CLI | ✅ Có |
| Provider switching | Chọn Llama/Azure qua config | ✅ Có |
| Conversation memory | Lưu session hội thoại | 🔶 Memory / file |
| Streaming | Trả token dần (SSE/WebSocket) | ⏭ Sau MVP |

> **Product message workshop:** AI không thay thế đội phát triển — AI là **cộng sự** hỗ trợ từ phân tích, thiết kế,
> lập trình, kiểm thử đến trình bày. Phần mở rộng chứng minh cách biến dữ liệu giám sát thành **hội thoại vận hành có AI**.

---

👉 Tiếp theo: [02-kien-truc-tong-the.md](02-kien-truc-tong-the.md)
