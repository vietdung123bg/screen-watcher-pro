# Kiểm thử (Testing) — Screen Watcher Pro

Bộ test tự động bằng **pytest**, hiện tập trung vào phần **AI chat / tools / provider / notebook client /
mock data / render markdown**. Test chạy **hoàn toàn offline**: không gọi LLM thật, không cần mạng,
không đụng DB thật.

Theo [`pdg.md`](pdg.md) và [`bpd.md`](bpd.md), phạm vi kiểm thử của Screen Watcher Pro cần được
mở rộng theo hướng Rule Engine có thể **giải thích được, kiểm thử được, version được, audit được và
đo lường được**. Tài liệu này vì vậy gồm cả kết quả test hiện tại và checklist kiểm thử cần dùng khi
thêm hoặc thay đổi rule.

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

## Chuẩn kiểm thử Rule Engine theo PDG/BPD

Mỗi rule production, nhất là rule `Major`/`Critical`, nên có test evidence trước khi active. Bộ test
tối thiểu:

| Loại test | Mục tiêu | Ví dụ |
|----------|----------|-------|
| Positive | Event hợp lệ phải tạo alert | `CPU usage 95%`, env `prod` → `Alert/Critical` |
| Negative | Event không liên quan không được alert | `CPU usage normal` → `No Alert` |
| Boundary | Kiểm tra ngưỡng sát mép | `CPU 89` → `No Alert`, `CPU 90` → `Alert` |
| Conflict | Rule cụ thể phải thắng rule tổng quát theo priority/scope | CPU batch-window Warning không ghi đè CPU prod Critical nếu scope không đúng |
| Suppression | Maintenance/known-noise không tạo alert sai | backup window → suppress Warning |
| Dedup | Event lặp trong cooldown không spam email/ticket | CPU 95/96/97 trong 5 phút → 1 alert |
| Regression | Rule mới không làm hỏng hành vi cũ | replay dataset lịch sử sau mỗi thay đổi rule |

Test evidence nên lưu hoặc đính kèm:

- Input event/OCR text, metadata, screenshot hoặc fixture tương ứng.
- Rule ID, version/config được test, owner và severity kỳ vọng.
- Expected result, actual result, trạng thái pass/fail.
- Decision trace: điều kiện nào match/không match, suppression/dedup có áp dụng không.
- Timestamp, tester hoặc CI job, và link log/report nếu có.

## Checklist kiểm thử khi đổi rule

Trước khi publish rule mới hoặc version mới:

- Rule request đã có lý do nghiệp vụ, target system/screen, owner và expected alert behavior.
- Condition đủ cụ thể; tránh keyword-only nếu có structured field tốt hơn.
- Severity phản ánh business impact, không chỉ dựa vào từ khóa kỹ thuật.
- Có dedup key, cooldown và suppression policy rõ ràng.
- Có positive, negative, boundary, suppression và dedup test.
- Có regression test hoặc replay dataset cho case lịch sử quan trọng.
- Có rollback plan: khôi phục file/config/version trước đó nếu rule gây alert storm.
- Với rule high-risk, chạy dry run hoặc mô phỏng trước khi bật gửi email thật.

## Kết quả gần nhất

```
platform win32 — Python 3.13, pytest 9.1
collected 71 items
tests\test_chat_agent_engine.py .......... (14)
tests\test_chatbox_client.py ........ (11)
tests\test_issue_memory_and_voice.py ..... (5)
tests\test_jupyter_tab.py ...... (6)
tests\test_mock_data.py .... (4)
tests\test_opencode_adapter.py ................ (23)
tests\test_rule_engine_metadata.py ... (3)
tests\test_rich_text.py ..... (5)
======================= 69 passed, 2 skipped =======================
```

> **69 passed, 2 skipped.** (Riêng 2 test render Markdown cần Tk sẽ **tự skip** nếu chạy trên môi trường
> không có display — CI headless; trên Windows có desktop thì chạy đầy đủ.)

## Phạm vi từng file test

| File | Số test | Bao phủ |
|------|:------:|---------|
| `tests/test_opencode_adapter.py` | 23 | Adapter OpenCode CLI: dựng prompt (scope guardrail, greetings in-scope, **định hướng khi không có tool**, câu từ chối **tiếng Anh**), map model theo provider, chạy subprocess (thành công / lỗi exit / stdout rỗng / timeout / thiếu binary), strip ANSI, mode argv vs stdin. |
| `tests/test_chat_agent_engine.py` | 14 | `ChatAgent`: chọn engine `sdk`/`opencode` qua `ai.engine`/`CHAT_ENGINE`, mock mode, prompt mang watcher-context; **SDK streaming** ráp reply từ token + phát sự kiện `meta/thinking/delta/tool_call/tool_result/final`; `chat_stream` đúng thứ tự; **batch nhiều tool trong 1 bước** (chạy song song); `get_alert_recipients` đọc config. |
| `tests/test_chatbox_client.py` | 11 | Client notebook (`app/ai/chatbox`): `send_message`/`login` (stub `requests`), thông báo lỗi thân thiện (timeout/connection/401), **và integration** boot **server FastAPI thật** (uvicorn, `ai.mock`, DB tạm) → `/health` → login → chat → latest; session id UUID. |
| `tests/test_issue_memory_and_voice.py` | 5 | Issue vectorstore: event đầu là `new_issue`, event lặp là `known_issue`; watcher context/chat tool đọc issue memory; voice alert fallback beep; UI explanation hiển thị issue mới/cũ. |
| `tests/test_jupyter_tab.py` | 6 | Helper tab Jupyter: `build_command` (dùng `--no-browser`, bind host/port), `notebook_url` (giữ token, trỏ đúng notebook), `build_webview_command`, và module webview import được **khi chưa cài pywebview**. |
| `tests/test_rich_text.py` | 5 | Renderer Markdown/HTML của chatbot: `html_to_markdown` (b/strong, code, link, list), giữ nguyên identifier có `_`; và (cần Tk) `insert_markdown` áp tag + loại ký tự thô, không in nghiêng nhầm underscore. |
| `tests/test_mock_data.py` | 4 | Mock data: `seed_first_run` idempotent + **latest là bản có rule khớp**; `generate_mock_data` clamp count 1–5 + fallback scenario; tool chat `generate_mock_data` **admin-only** (viewer bị từ chối). |
| `tests/test_rule_engine_metadata.py` | 3 | Rule Engine metadata: metadata trong rule YAML được load, được giữ qua evaluation, không ảnh hưởng match, và metadata sai kiểu được normalize về `{}`. |

## Những gì test ĐÃ bao phủ

- Đường **SDK streaming** + tool-calling (gồm gom nhiều tool call thành 1 lượt LLM, chạy song song).
- Kiểm soát phạm vi chatbot (từ chối off-topic) + vai trò **support/định hướng** khi không có tool.
- Engine OpenCode CLI (mọi nhánh lỗi) và định tuyến engine.
- Client notebook + **server REST thật** (integration, mock AI).
- Sinh/seed **mock data** và phân quyền tool.
- Render Markdown/HTML trong chatbot.
- Một phần kiểm chứng quanh `get_alert_recipients`, mock watcher result và quyền tool admin/user.
- Metadata trên từng rule trong `rules.yaml` được parse và bảo toàn qua `RuleEvaluation`.
- Issue memory bằng vectorstore local: phân loại `new_issue`/`known_issue`, đưa vào watcher context và tool chat.
- Voice alert optional: bật TTS nhưng chưa có runner vẫn fallback beep, không làm hỏng pipeline.

## Hạn chế / chưa bao phủ (sẽ phát triển tiếp)

- **Chưa có test chuyên sâu cho Rule Engine runtime**: operator `contains`/`not_contains`/`regex`/
  `all_keywords`/`any_keywords`, priority, severity mapping, owner missing, cooldown enabled/disabled,
  dry-run email và decision trace cần được tách thành test riêng.
- **Chưa có regression dataset cho rule** theo chuẩn BPD: positive/negative/boundary/conflict/
  suppression/dedup/replay historical events.
- **Chưa test lifecycle/governance**: Draft/Testing/Approved/Active/Deprecated/Disabled, versioning,
  approval, rollback, rule diff, audit trail và stale/retirement workflow hiện mới là định hướng trong BPD/PDG.
- **Chưa test UI Tkinter thật** (các tab desktop) ngoài helper — GUI khó tự động hoá; hiện chỉ test
  logic tách rời (renderer, helper Jupyter).
- **Chưa test OCR/capture thật** (cần Windows + cửa sổ trình duyệt + gọi Qwen3-VL) — pipeline capture
  chưa có test tự động.
- **Chưa test gửi email SMTP thật** (Gmail/Brevo) — chỉ có mô tả lỗi; nên thêm test với SMTP giả.
- **Chưa test provider LLM thật** (chỉ fake client) — không kiểm định hành vi model thật.
- **Chưa có test cho REST streaming (SSE)** ở tầng HTTP và cho tab (API Server/Jupyter auto-start).
- Chưa đo **coverage** (thêm `pytest-cov`) và chưa chạy trong **CI**.

## Test roadmap theo BPD/PDG

Ưu tiên tiếp theo nên là:

1. Thêm unit test cho `app/core/rule_engine.py` với fixture event/rule rõ ràng.
2. Thêm test cho `notification_service`: owner lookup, cooldown, dry-run, send failure và status
   `sent` / `simulated` / `skipped_cooldown` / `no_owner` / `send_failed` / `skipped_empty`.
3. Thêm replay fixture nhỏ cho các scenario nghiệp vụ: CPU Critical, false positive từ historical chart,
   maintenance suppression và obsolete rule.
4. Thêm test audit/evidence: mỗi rule evaluation phải có lý do, matched terms và notification decision.
5. Khi có lifecycle/versioning, thêm test transition và rollback theo luồng BPD.
