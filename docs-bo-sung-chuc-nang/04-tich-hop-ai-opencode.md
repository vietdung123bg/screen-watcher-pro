# 04 — Tích hợp AI với OpenCode CLI

> Chương **11** của docx (+ prompt template ở chương 21). Đầu vào của task **T04 (OpenCode CLI Adapter)**.

---

## Vai trò

OpenCode CLI là **lớp trung gian** giữa Tool Watcher Server và AI provider → server **không phụ thuộc SDK riêng**
của từng provider. Đổi Llama ↔ Azure OpenAI chỉ cần đổi **config model/provider** (YAML/env), Chat Orchestrator giữ nguyên.

```
Chat Orchestrator → OpenCode CLI Adapter → OpenCode CLI → [Llama | Azure OpenAI]
```

---

## 11.1. Trách nhiệm của Adapter (`opencode_cli_adapter.py`)
- [ ] Nhận prompt từ Chat Orchestrator
- [ ] Tạo command line tương ứng provider + model
- [ ] Chạy OpenCode CLI bằng `subprocess` với working directory an toàn
- [ ] Áp dụng **timeout** (tránh treo API request)
- [ ] Thu `stdout`, `stderr`, `exit code`
- [ ] Chuẩn hóa kết quả thành `AIResponse`

## 11.2. Command Execution Pattern
```bash
opencode run --model azure/gpt-4o-mini "<prompt>"
# hoặc
opencode run --model llama/local-model "<prompt>"
```
> `command`, `run_args`, `safe_mode` lấy từ khối `opencode:` trong YAML (xem [10](10-appendix-config-prompt.md)).

## 11.3. Prompt Composition
```
System role:
Bạn là AI assistant hỗ trợ vận hành Tool Watcher.

Watcher context:
OCR text: {{ocr_text}}
Matched rules: {{matched_rules}}
Execution time: {{execution_time}}
Email status: {{email_status}}

User question:
{{message}}

Instruction:
Trả lời ngắn gọn, dựa trên dữ liệu được cung cấp.
Nếu dữ liệu không đủ, nói rõ là chưa đủ dữ liệu.
```
> Prompt template đầy đủ (dạng "trạng thái / bằng chứng / nhận định / hành động đề xuất") ở [10-appendix-config-prompt.md](10-appendix-config-prompt.md).

---

## 🧱 Đề xuất kiểu dữ liệu `AIResponse`
```python
@dataclass
class AIResponse:
    reply: str
    model: str
    provider: str
    status: str            # "success" | "error"
    error_code: str | None = None
    raw_stdout: str = ""
    duration_ms: int = 0
```

## 🔀 Provider config (`provider_config.py`)
- Đọc `ai.provider` + `ai.model` từ YAML.
- Map tên provider → prefix model (`azure/...`, `llama/...`).
- Lấy API key từ **environment variables** (không hard-code):
  `AZURE_OPENAI_API_KEY`, `LLAMA_API_KEY` (tên biến khai trong `secrets:` của YAML).
- Validate khi start server (rule chống "provider config sai" — xem [08](08-testing-risk.md)).

---

## ✅ Checklist thực hiện (T04)
- [ ] Hàm build command từ provider/model + prompt
- [ ] Chạy `subprocess.run(..., timeout=cfg.timeout_seconds, cwd=working_dir)`
- [ ] Bắt `TimeoutExpired` → trả `error_code=OPENCODE_TIMEOUT, retryable=true`
- [ ] Bắt exit code ≠ 0 / stderr → `error_code=PROVIDER_UNAVAILABLE`
- [ ] Parse stdout → `AIResponse.reply`
- [ ] **Mock mode**: cờ để trả reply giả lập (phục vụ test/demo khi không có provider) → [08](08-testing-risk.md)
- [ ] Không log API key / secret (mask) → [07](07-data-security.md)

## Definition of Done
- Gọi được OpenCode CLI thật **và** chạy mock mode.
- Timeout & lỗi provider trả `AIResponse` với `error_code` đúng, không làm crash server.
- Đổi provider Llama ↔ Azure chỉ bằng sửa YAML (không sửa code).

---

👉 Tiếp theo: [05-jupyter-chatbox-client.md](05-jupyter-chatbox-client.md)
