# Kiểm thử (Testing) — Screen Watcher Pro

Bộ test tự động bằng **pytest**, tập trung vào phần **AI chat / tools / provider / notebook client /
mock data / render markdown**. Test chạy **hoàn toàn offline**: không gọi LLM thật, không cần mạng,
không đụng DB thật.

## Cách chạy

```cmd
run.cmd test
```
hoặc thủ công (trong `.venv` đã cài `requirements.txt`, gồm cả `pytest`):
```powershell
python -m pytest -q
```

- Cấu hình ở [`pytest.ini`](pytest.ini): `testpaths = tests`.
- Nguyên tắc cô lập: LLM SDK được thay bằng **fake streaming client**; OpenCode CLI bằng **fake CLI**
  (fixture trong [`tests/conftest.py`](tests/conftest.py)); mock data / repo dùng **SQLite tạm**
  (`tmp_path`), không chạm `data/screenwatcher.db`.

## Kết quả gần nhất

```
platform win32 — Python 3.11, pytest 9.1
collected 63 items
tests\test_chat_agent_engine.py .......... (14)
tests\test_chatbox_client.py ........ (11)
tests\test_jupyter_tab.py ...... (6)
tests\test_mock_data.py .... (4)
tests\test_opencode_adapter.py ................ (23)
tests\test_rich_text.py ..... (5)
======================= 63 passed =======================
```

> **63/63 passed.** (Riêng 2 test render Markdown cần Tk sẽ **tự skip** nếu chạy trên môi trường
> không có display — CI headless; trên Windows có desktop thì chạy đầy đủ.)

## Phạm vi từng file test

| File | Số test | Bao phủ |
|------|:------:|---------|
| `tests/test_opencode_adapter.py` | 23 | Adapter OpenCode CLI: dựng prompt (scope guardrail, greetings in-scope, **định hướng khi không có tool**, câu từ chối **tiếng Anh**), map model theo provider, chạy subprocess (thành công / lỗi exit / stdout rỗng / timeout / thiếu binary), strip ANSI, mode argv vs stdin. |
| `tests/test_chat_agent_engine.py` | 14 | `ChatAgent`: chọn engine `sdk`/`opencode` qua `ai.engine`/`CHAT_ENGINE`, mock mode, prompt mang watcher-context; **SDK streaming** ráp reply từ token + phát sự kiện `meta/thinking/delta/tool_call/tool_result/final`; `chat_stream` đúng thứ tự; **batch nhiều tool trong 1 bước** (chạy song song); `get_alert_recipients` đọc config. |
| `tests/test_chatbox_client.py` | 11 | Client notebook (`app/ai/chatbox`): `send_message`/`login` (stub `requests`), thông báo lỗi thân thiện (timeout/connection/401), **và integration** boot **server FastAPI thật** (uvicorn, `ai.mock`, DB tạm) → `/health` → login → chat → latest; session id UUID. |
| `tests/test_jupyter_tab.py` | 6 | Helper tab Jupyter: `build_command` (dùng `--no-browser`, bind host/port), `notebook_url` (giữ token, trỏ đúng notebook), `build_webview_command`, và module webview import được **khi chưa cài pywebview**. |
| `tests/test_rich_text.py` | 5 | Renderer Markdown/HTML của chatbot: `html_to_markdown` (b/strong, code, link, list), giữ nguyên identifier có `_`; và (cần Tk) `insert_markdown` áp tag + loại ký tự thô, không in nghiêng nhầm underscore. |
| `tests/test_mock_data.py` | 4 | Mock data: `seed_first_run` idempotent + **latest là bản có rule khớp**; `generate_mock_data` clamp count 1–5 + fallback scenario; tool chat `generate_mock_data` **admin-only** (viewer bị từ chối). |

## Những gì test ĐÃ bao phủ

- Đường **SDK streaming** + tool-calling (gồm gom nhiều tool call thành 1 lượt LLM, chạy song song).
- Kiểm soát phạm vi chatbot (từ chối off-topic) + vai trò **support/định hướng** khi không có tool.
- Engine OpenCode CLI (mọi nhánh lỗi) và định tuyến engine.
- Client notebook + **server REST thật** (integration, mock AI).
- Sinh/seed **mock data** và phân quyền tool.
- Render Markdown/HTML trong chatbot.

## Hạn chế / chưa bao phủ (sẽ phát triển tiếp)

- **Chưa test UI Tkinter thật** (các tab desktop) ngoài helper — GUI khó tự động hoá; hiện chỉ test
  logic tách rời (renderer, helper Jupyter).
- **Chưa test OCR/capture thật** (cần Windows + cửa sổ trình duyệt + gọi Qwen3-VL) — pipeline capture
  chưa có test tự động.
- **Chưa test gửi email SMTP thật** (Gmail/Brevo) — chỉ có mô tả lỗi; nên thêm test với SMTP giả.
- **Chưa test provider LLM thật** (chỉ fake client) — không kiểm định hành vi model thật.
- **Chưa có test cho REST streaming (SSE)** ở tầng HTTP và cho tab (API Server/Jupyter auto-start).
- Chưa đo **coverage** (thêm `pytest-cov`) và chưa chạy trong **CI**.
