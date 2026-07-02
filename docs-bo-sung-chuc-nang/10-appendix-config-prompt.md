# 10 — Phụ lục: YAML Config & Prompt Template

> Chương **21** của docx. Cấu hình mẫu + prompt template để copy khi triển khai.

---

## 21.1. YAML Config mẫu

> Bổ sung các khối `server / chat / ai / opencode / watcher_context / logging` vào cấu hình.
> Có thể gộp vào `config/rules.yaml` hiện tại hoặc tách file `config/api.yaml` riêng (khuyên tách để không lẫn với rule).

```yaml
app:
  name: screen-watcher-ai-extension
  environment: workshop
  timezone: Asia/Ho_Chi_Minh

server:
  host: 127.0.0.1
  port: 8000
  enable_cors: true

chat:
  include_latest_watcher_context_default: true
  max_message_length: 4000
  max_context_chars: 6000
  conversation_store: memory

ai:
  engine: opencode_cli
  provider: azure_openai        # azure_openai | llama
  model: azure/gpt-4o-mini
  timeout_seconds: 120
  working_dir: ./workspace

opencode:
  command: opencode
  run_args:
    - run
  safe_mode: true

watcher_context:
  latest_result_path: ./data/latest_result.json
  audit_dir: ./data/audit
  allow_manual_trigger_from_api: true

logging:
  level: INFO
  log_dir: ./logs
```

> ⚠️ `watcher_context.latest_result_path` → nếu chọn **Cách B** (ghi file JSON) ở [02](02-kien-truc-tong-the.md).
> Nếu chọn **Cách A** (query SQLite trực tiếp) thì key này không bắt buộc.

---

## 21.2. Prompt Template mẫu

```
Bạn là AI assistant hỗ trợ vận hành Tool Watcher.

Nguyên tắc trả lời:
1. Chỉ dựa trên dữ liệu được cung cấp.
2. Nếu dữ liệu không đủ, nói rõ là chưa đủ dữ liệu.
3. Trả lời ngắn gọn theo các mục: trạng thái, bằng chứng, nhận định, hành động đề xuất.

Dữ liệu watcher:
{{watcher_context}}

Câu hỏi của user:
{{user_message}}
```

---

## 21.3. Kết luận

Phần mở rộng đưa Tool Watcher từ **automation observer tool** → **AI assisted operation assistant**.
Trong phạm vi workshop, thiết kế minh họa cách nhóm dùng AI xuyên suốt vòng đời phát triển:
phân tích vấn đề → thiết kế giải pháp → lập trình → kiểm thử → demo → trình bày.

---

## 🔧 Biến môi trường liên quan (`.env`)
```
OPENROUTER_API_KEY=...          # đã có (OCR Qwen3-VL)
WATCHER_SMTP_PASSWORD=...        # đã có (email)
AZURE_OPENAI_API_KEY=...         # 🆕 nếu dùng Azure OpenAI
LLAMA_API_KEY=...                # 🆕 nếu dùng Llama
```

---

👈 Về đầu: [00-INDEX.md](00-INDEX.md)
