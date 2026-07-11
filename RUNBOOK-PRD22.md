# RUNBOOK — PRD 2.2 Demo (Event Review · Rule Governance · Console SOS · ChromaDB · HF TTS)

Kịch bản demo 7 bước cho Phase 1 MVP + 2 tính năng ML tuỳ chọn (ChromaDB,
Hugging Face TTS). Toàn bộ bằng chứng (test log, screenshot, audio, waveform)
của lần chạy gần nhất nằm ở [`workshop/110726/evidence/`](workshop/110726/evidence)
(chạy ngày 11/07/2026) — dùng làm tài liệu tham khảo song song khi demo trực tiếp.

Chuẩn bị:

```powershell
# 1) môi trường lõi (bắt buộc)
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1b) (tuỳ chọn) ChromaDB + Hugging Face TTS — offline, KHÔNG cần GPU
.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2) chạy API server (console này sẽ là nơi RÚ SOS 🚨)
.venv\Scripts\python.exe -m uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
# ...hoặc đơn giản hơn: run.cmd api   (tự tạo venv + cài deps lần đầu)

# 3) đăng nhập web admin: http://127.0.0.1:8000/admin  (admin / mật khẩu của bạn)
```

Migration `002_prd22.sql` chạy tự động lúc khởi động (idempotent). Lần đầu sẽ
tạo backup `data/screenwatcher.db.pre-prd22.bak` và sync các rule YAML vào
`rules_db` (status ACTIVE, `created_by=yaml_sync`).

> 💡 Không có API key LLM? Đặt `ai.mock: true` trong `config/rules.yaml` —
> AI Review chạy chế độ mock offline, vẫn tạo Draft Rule để demo đủ flow.
> Server evidence dùng `prd22.ai_review.mock: true` (không cần key) — xem
> `write_demo_server()` trong [`workshop/capture_evidence.py`](workshop/capture_evidence.py).

---

## Bước 1 — Incident Rule → console tự rú 🚨 (chưa cần mở UI)

1. Vào `/admin/rules/new` (admin) tạo **Incident Rule** (GR22-002: incident rule
   phải do user tạo):
   - Rule id: `payment_declined_incident`
   - Type: `any_keywords`, Condition: `{"keywords": ["payment declined", "declined"], "ignore_case": true}`
   - Severity: `critical`, Status: `ACTIVE`, tick ✅ **Incident rule**
2. Mở `test_pages/03_payment_fraud_vi.html` trong Chrome (có chữ *Payment
   declined*) rồi chạy capture (tab **Capture & OCR**, hoặc
   `POST /api/watcher/executions`).
   - Không có màn hình thật? Bơm event trực tiếp:
     ```powershell
     $tok = (Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/auth/login -ContentType application/json -Body '{"username":"admin","password":"admin123"}').access_token
     Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/events -Headers @{Authorization="Bearer $tok"} -ContentType application/json -Body '{"raw_text":"Payment declined for order #123","screen":"Payment dashboard"}'
     ```
3. **Kết quả:** trong vòng 3 giây, terminal đang chạy uvicorn in
   `🚨🚨🚨 [SOS] CRITICAL — Incident rule 'payment_declined_incident' matched…`
   kèm tiếng beep — lặp lại mỗi `sos_alert.cooldown_seconds` (300s) cho đến khi
   acknowledge. UI đóng vẫn rú, vì job chạy trong process server
   (`app/jobs/sos_watcher_job.py`).
   Bằng chứng thật: [`30_console_sos.txt`](workshop/110726/evidence/30_console_sos.txt)
   — tạo lúc `10:24:58`, rú lúc `10:25:00`.

## Bước 2 — Acknowledge qua `/admin/sos` → console dừng rú

1. Mở `/admin/sos` — panel PENDING có badge đỏ nhấp nháy, tự refresh 2s (HTMX).
   Ảnh chụp: [`s03_sos_pending.png`](workshop/110726/evidence/s03_sos_pending.png).
2. Bấm **✔ Acknowledge**.
3. **Kết quả:** row chuyển xuống "Recently acknowledged" với
   `acknowledged_by=admin` + thời điểm (GR22-004); console không beep nữa;
   `audit_logs` có `sos.acknowledge`. Bằng chứng: acknowledge lúc `10:25:06`
   trong `30_console_sos.txt`, chi tiết JSON ở
   [`40_flow_responses.json`](workshop/110726/evidence/40_flow_responses.json)
   (`sos_ack.acknowledged_by = "admin"`, double-ack → HTTP 400).

## Bước 3 — Text lạ chưa có rule → AI Review tạo Draft Rule

1. Capture một trang có text bất thường chưa rule nào match (vd
   `test_pages/10_sentry_en.html`), hoặc bơm event:
   `{"raw_text": "Unhandled exception: inventory sync FAILED at step 7", "screen": "Sentry"}`
2. Không rule nào match → event `AI_REVIEW_PENDING` → AI Review cấp 1 chạy nền
   (timeout 120s, context cắt 6000 ký tự).
3. **Kết quả:** `/admin/review-queue` hiện review mới: classification, risk,
   confidence, reason + **Draft Rule** `AI_SUGGESTED / enabled=0`. AI không thể
   tự ACTIVE (GR22-001 — có test chứng minh).
   Ảnh chụp thật: [`s02_review_queue.png`](workshop/110726/evidence/s02_review_queue.png)
   — 2 review: 1 `HIGH/0.85` đề xuất `CREATE_DRAFT_RULE`, 1 `LOW/0.9` đề xuất `IGNORE`.

## Bước 4 — Admin Approve → Rule ACTIVE → lần capture sau match rule mới

1. Ở `/admin/review-queue`, bấm **✔ Approve → ACTIVE** (có thể sửa JSON rule
   trước khi approve = decision EDIT).
2. **Kết quả:** rule chuyển `ACTIVE / enabled=1` (`/admin/rules`), event thành
   `CONFIRMED_ISSUE`, audit ghi `review.approve` + `rule.active`.
3. Capture lại đúng trang đó → lần này event `MATCHED_RULE` bằng rule vừa
   approve (kiểm tra ở `/admin/events`, hoặc `/admin/rules/{id}/test` với
   event_id cũ → PASS).
   Bằng chứng JSON: `40_flow_responses.json.approve` →
   `rule_status: "ACTIVE"`, `event_status: "CONFIRMED_ISSUE"`.

## Bước 5 — Reject Draft Rule (bắt buộc lý do) → audit đầy đủ

1. Tạo thêm một event lạ khác (như bước 3) để có Draft Rule thứ hai.
2. Ở `/admin/review-queue`, nhập **reject reason** (form không cho submit rỗng)
   rồi bấm **✘ Reject**.
3. **Kết quả:** rule chuyển `REJECTED` nhưng **vẫn còn trong DB** kèm
   `reject_reason` (GR22-003 — xem `/admin/rules?status=REJECTED`); event thành
   `IGNORED`; `/admin/audit` có `review.reject` + `rule.rejected` kèm lý do.
   Bằng chứng: `40_flow_responses.json.reject_missing_reason_status = 422`
   (thiếu lý do bị chặn), `.reject.rule_status = "REJECTED"`;
   ảnh [`s08_rules_after.png`](workshop/110726/evidence/s08_rules_after.png) và
   [`s09_audit_after.png`](workshop/110726/evidence/s09_audit_after.png).

---

## Bước 6 — ChromaDB: nhận diện sự cố "đã từng gặp" (tuỳ chọn, cần requirements-ml.txt)

1. Bật `issues.backend: chroma` trong `config/rules.yaml` (mặc định đã bật).
2. Hai cảnh báo **cùng loại** (vd 2 lần "Payment declined … fraud") được đưa
   qua flow rule YAML cũ (capture → OCR → rule match → issue memory) — Chroma
   so khớp theo *ý nghĩa* (vector embedding), không theo câu chữ giống hệt.
3. **Kết quả** (bằng chứng thật, chạy lại được với
   `.venv\Scripts\python.exe workshop\chroma_demo_script.py` — xem
   [`52_chroma_demo.txt`](workshop/110726/evidence/52_chroma_demo.txt)):
   5 cảnh báo đưa vào → chỉ **3 sự cố DUY NHẤT** trong ChromaDB (2 cặp trùng
   được gộp, giống nhau 94–99%). Người trực không bị báo lặp cho cùng một vấn đề.
4. Không cài `chromadb`? App tự fallback về store SQLite có sẵn (không lỗi,
   không cần cấu hình gì thêm) — xem `app/services/issue_vectorstore.py`.

## Bước 7 — Hugging Face TTS: đọc cảnh báo bằng giọng nói (tuỳ chọn)

1. Bật `tts.enabled: true` + `tts.provider: transformers` trong `config/rules.yaml`.
2. Khi có cảnh báo severity cao (`tts.severities`), app tự đọc `tts.alert_text`
   bằng model `facebook/mms-tts-vie` (tiếng Việt, chạy CPU, offline sau lần
   tải đầu) và phát ra loa.
3. **Kết quả** (bằng chứng thật): file
   [`tts_alert_vi.wav`](workshop/110726/evidence/tts_alert_vi.wav) (6.83 giây,
   16 kHz) + sóng âm [`tts_waveform.png`](workshop/110726/evidence/tts_waveform.png)
   + chi tiết ở [`53_tts_demo.txt`](workshop/110726/evidence/53_tts_demo.txt).
4. Không cài `torch`/`transformers`, hoặc synth lỗi? Tự động chuyển sang
   `tts.command` (runner GGUF ngoài) rồi cuối cùng là **beep** — không bao giờ
   chặn luồng xử lý rule.

---

## Kiểm tra nhanh qua chatbot (tab Chatbot hoặc POST /api/chat)

| Câu hỏi | Tool được gọi |
|---|---|
| "Có SOS nào đang pending không?" | `get_pending_sos_alerts` |
| "Acknowledge SOS \<id\> giúp tôi" | `acknowledge_sos` |
| "Review queue còn gì chờ duyệt?" | `list_review_queue` (operator/admin) |
| "Approve rule AI đề xuất ở review \<id\>" | `approve_ai_suggested_rule` (admin) |
| "Test rule payment_declined_incident với event \<id\>" | `test_rule_with_event` |
| "Liệt kê rule trong DB" | `list_db_rules` |

## Chạy lại toàn bộ evidence (tự động, 1 lệnh)

```powershell
run.cmd evidence              :: lưu vào workshop\<hôm nay, DDMMYY>\evidence\
run.cmd evidence 250712       :: hoặc chỉ định tên thư mục cụ thể
```

`run.cmd evidence` gọi [`workshop/capture_evidence.py`](workshop/capture_evidence.py)
— một script tự động **duy nhất** chạy toàn bộ luồng: pytest (full suite +
PRD22 + Chroma + TTS thật), dựng server demo cô lập (DB riêng, không đụng
`data/screenwatcher.db` thật), seed đủ kịch bản Bước 1–5, chụp screenshot
`/admin` bằng Playwright, bắt log console SOS, chạy demo ChromaDB + HF TTS —
rồi dọn sạch toàn bộ dữ liệu tạm. Có tự retry (3 lần, đổi cổng + server mới
mỗi lần) nếu một request bị timeout do máy đang tải nặng.

Kết quả nằm trong `workshop/<DDMMYY>/evidence/` (đặt tên theo ngày chạy, ví dụ
`110726` = 11/07/2026) — tái sử dụng làm ảnh minh hoạ cho slide/README.

## Sự cố thường gặp

- **Không nghe beep**: kiểm tra `sos_alert.sound_enabled: true`; trên máy không
  có `winsound` job in `\a` (bell) — một số terminal tắt bell.
- **AI review FAILED / RETRY_REQUIRED**: thiếu API key (.env) hoặc LLM trả về
  JSON sai / timeout — server không crash, xem cột status ở event detail;
  dùng `ai.mock: true` (hoặc `prd22.ai_review.mock: true`) để demo offline.
- **Migration chạy lại**: an toàn — mọi câu lệnh là `IF NOT EXISTS`; file backup
  chỉ tạo một lần trước lần áp dụng đầu tiên.
- **ChromaDB không tải model nào** — app tự cấp embedding (dense hashing mặc
  định), nên hoàn toàn offline ngay từ lần chạy đầu tiên.
- **HF TTS lần đầu chậm (~30s)**: đang tải model `facebook/mms-tts-vie` (~1 lần
  duy nhất, cache tại `~/.cache/huggingface`); các lần sau chỉ mất 3–8 giây.
- **`run.cmd evidence` bị treo ở bước seed** (đã sửa, để lại đây làm tài liệu):
  nếu bạn tự viết script tương tự khởi động server demo bằng `subprocess.Popen`,
  KHÔNG dùng `stdout=subprocess.PIPE` rồi chỉ `communicate()` một lần ở cuối —
  buffer OS (64KB trên Windows) đầy giữa chừng sẽ làm server treo (block ngay
  trong request đang xử lý). Ghi log ra **file** thay vì PIPE
  (xem `run_server_flow()` trong `capture_evidence.py`).
- **Chạy test**: `.venv\Scripts\python.exe -m pytest tests/ -q`
  (hoặc `run.cmd test`). Test synth TTS thật (tải/dùng model) chỉ chạy khi có
  cờ `SW_TTS_REAL=1` — mặc định skip để suite luôn nhanh.
