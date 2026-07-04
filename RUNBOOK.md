# Screen Watcher Pro Runbook

Runbook này dùng cho demo workshop AI08: chạy app, mở API/chatbox, và trình diễn 2 câu chat bắt buộc.

## 1. Chạy nhanh bằng `run.cmd`

Trên Windows, mở Command Prompt hoặc PowerShell tại thư mục repo:

```cmd
run.cmd
```

Mặc định lệnh trên chạy desktop app (`python run.py`). Các mode khác:

```cmd
run.cmd desktop    :: chạy app desktop
run.cmd api        :: chạy FastAPI server ở http://127.0.0.1:8000
run.cmd notebook   :: mở notebooks/chatbox.ipynb
run.cmd demo       :: mở API server trong cửa sổ riêng rồi mở notebook
run.cmd test       :: chạy pytest
```

`run.cmd` sẽ tự tạo `.venv`, cài `requirements.txt`, và copy các file mẫu nếu thiếu:

- `config/rules.example.yaml` -> `config/rules.yaml`
- `.ocr.env.example` -> `.ocr.env`
- `.smtp.env.example` -> `.smtp.env`
- `.chatbot.env.example` -> `.chatbot.env`

Các file env/config sau khi copy vẫn cần điền key thật nếu muốn gọi LLM/OCR/email thật.

## 2. Chuẩn bị demo an toàn

1. Mở dashboard test có cảnh báo, ví dụ:

```text
test_pages/01_ops_dashboard_en.html
test_pages/03_payment_fraud_vi.html
test_pages/07_datadog_vi.html
```

2. Chạy desktop app:

```cmd
run.cmd desktop
```

3. Đăng nhập `admin` / `admin123` nếu DB mới. Nếu app yêu cầu đổi mật khẩu lần đầu, đổi sang mật khẩu demo nội bộ rồi tiếp tục.

4. Vào tab `Capture & OCR`, chọn Chrome hoặc Edge, bấm `Capture & OCR`.

5. Xác nhận tab `History & Results` có execution mới. Đây là dữ liệu mà AI dùng để đánh giá hiện trạng vận hành.

6. Vào tab `Chatbot` trong desktop app, hoặc chạy API + notebook:

```cmd
run.cmd demo
```

## 3. Demo chat bắt buộc

### Câu 1: đánh giá hiện trạng vận hành

Hỏi:

```text
Issue hiện tại đang là gì?
```

Kỳ vọng:

- Assistant trả lời trong phạm vi vận hành Screen Watcher.
- Câu trả lời dựa trên watcher context mới nhất: OCR text, rule match, severity, email decision, execution status.
- Nếu chưa có dữ liệu watcher, assistant nói rõ chưa có dữ liệu đủ để kết luận.
- Đây là case thể hiện trợ lý có thể đưa ra đánh giá hiện trạng vận hành, không chỉ đọc text thô.

Ví dụ phản hồi hợp lệ:

```text
Hiện tại watcher ghi nhận rule error_detected đang match vì OCR có ERROR/TIMEOUT.
Mức độ high, cần kiểm tra dashboard nguồn và xác nhận email cảnh báo đã được gửi hoặc đang ở cooldown.
```

### Câu 2: out-of-scope guardrail

Hỏi:

```text
cách nấu thịt kho tàu thế nào?
```

Kỳ vọng bắt buộc (câu từ chối luôn bằng **tiếng Anh**):

```text
This question is outside the scope of the Tool Watcher Assistant. Please ask about watcher results, OCR, rules, or system status.
```

> Lưu ý: chào hỏi và hỗ trợ cơ bản về app (vd `Chào bạn`, `Bạn giúp được gì?`) **vẫn được trả lời** — chỉ chủ đề hoàn toàn ngoài nghiệp vụ (nấu ăn, sửa xe máy, thể thao…) mới bị từ chối bằng câu trên.

Ý nghĩa demo:

- Assistant bị kiểm soát phạm vi, không trả lời kiến thức chung.
- Với câu ngoài nghiệp vụ, assistant không gọi tool và không bịa nội dung.
- Đây là bằng chứng guardrail: AI assistance phục vụ vận hành, không biến thành chatbot tự do.

## 4. API demo nếu không dùng desktop tab

Chạy server:

```cmd
run.cmd api
```

Mở docs:

```text
http://127.0.0.1:8000/docs
```

Luồng API tối thiểu:

1. `POST /api/auth/login` với `admin` / mật khẩu hiện tại để lấy JWT.
2. `GET /api/watcher/executions/latest` để xác nhận có watcher context.
3. `POST /api/chat` với câu `Issue hiện tại đang là gì?`.
4. `POST /api/chat` với câu `cách nấu thịt kho tàu thế nào?`.

## 5. Evidence khi demo

Tự chụp màn hình các bước khi trình bày (Swagger `/docs`, health check, Jupyter chatbox,
latest watcher result…). Kết quả **kiểm thử tự động** (pytest) xem ở [TESTING.md](TESTING.md).

## 6. Troubleshooting nhanh

`OPENROUTER_API_KEY is not configured`

- Điền key vào `.ocr.env` hoặc `.chatbot.env`.
- Nếu chỉ cần demo UI mà không gọi LLM thật, đặt `ai.mock: true` trong `config/rules.yaml`.

Không có watcher context

- Chạy `Capture & OCR` trước khi hỏi câu 1.
- Hoặc mở `test_pages/*` bằng Chrome/Edge rồi capture lại.

Câu out-of-scope vẫn được trả lời

- Kiểm tra code prompt trong `app/ai/chat_agent.py` và `app/ai/opencode_adapter.py`.
- Chạy lại test scope guard:

```cmd
run.cmd test
```

