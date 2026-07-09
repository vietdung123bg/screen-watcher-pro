# RUNBOOK — PRD 2.2 Demo (Event Review · Rule Governance · Console SOS)

Kịch bản demo 5 bước cho Phase 1 MVP. Chuẩn bị:

```powershell
# 1) môi trường
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) chạy API server (console này sẽ là nơi RÚ SOS 🚨)
.venv\Scripts\python.exe -m uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1

# 3) đăng nhập web admin: http://127.0.0.1:8000/admin  (admin / mật khẩu của bạn)
```

Migration `002_prd22.sql` chạy tự động lúc khởi động (idempotent). Lần đầu sẽ
tạo backup `data/screenwatcher.db.pre-prd22.bak` và sync các rule YAML vào
`rules_db` (status ACTIVE, `created_by=yaml_sync`).

> 💡 Không có API key LLM? Đặt `ai.mock: true` trong `config/rules.yaml` —
> AI Review chạy chế độ mock offline, vẫn tạo Draft Rule để demo đủ flow.

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
     # lấy JWT
     $tok = (Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/auth/login -ContentType application/json -Body '{"username":"admin","password":"admin123"}').access_token
     Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/events -Headers @{Authorization="Bearer $tok"} -ContentType application/json -Body '{"raw_text":"Payment declined for order #123","screen":"Payment dashboard"}'
     ```
3. **Kết quả:** trong vòng 3 giây, terminal đang chạy uvicorn in
   `🚨🚨🚨 [SOS] CRITICAL — Incident rule 'payment_declined_incident' matched…`
   kèm tiếng beep — lặp lại mỗi `sos_alert.cooldown_seconds` (300s) cho đến khi
   acknowledge. UI đóng vẫn rú, vì job chạy trong process server
   (`app/jobs/sos_watcher_job.py`).

## Bước 2 — Acknowledge qua `/admin/sos` → console dừng rú

1. Mở `/admin/sos` — panel PENDING có badge đỏ nhấp nháy, tự refresh 2s (HTMX).
2. Bấm **✔ Acknowledge**.
3. **Kết quả:** row chuyển xuống "Recently acknowledged" với
   `acknowledged_by=admin` + thời điểm (GR22-004); console không beep nữa;
   `audit_logs` có `sos.acknowledge`.

## Bước 3 — Text lạ chưa có rule → AI Review tạo Draft Rule

1. Capture một trang có text bất thường chưa rule nào match (vd
   `test_pages/10_sentry_en.html`), hoặc bơm event:
   `{"raw_text": "Unhandled exception: inventory sync FAILED at step 7", "screen": "Sentry"}`
2. Không rule nào match → event `AI_REVIEW_PENDING` → AI Review cấp 1 chạy nền
   (timeout 120s, context cắt 6000 ký tự).
3. **Kết quả:** `/admin/review-queue` hiện review mới: classification, risk,
   confidence, reason + **Draft Rule** `AI_SUGGESTED / enabled=0`. AI không thể
   tự ACTIVE (GR22-001 — có test chứng minh).

## Bước 4 — Admin Approve → Rule ACTIVE → lần capture sau match rule mới

1. Ở `/admin/review-queue`, bấm **✔ Approve → ACTIVE** (có thể sửa JSON rule
   trước khi approve = decision EDIT).
2. **Kết quả:** rule chuyển `ACTIVE / enabled=1` (`/admin/rules`), event thành
   `CONFIRMED_ISSUE`, audit ghi `review.approve` + `rule.active`.
3. Capture lại đúng trang đó → lần này event `MATCHED_RULE` bằng rule vừa
   approve (kiểm tra ở `/admin/events`, hoặc `/admin/rules/{id}/test` với
   event_id cũ → PASS).

## Bước 5 — Reject Draft Rule (bắt buộc lý do) → audit đầy đủ

1. Tạo thêm một event lạ khác (như bước 3) để có Draft Rule thứ hai.
2. Ở `/admin/review-queue`, nhập **reject reason** (form không cho submit rỗng)
   rồi bấm **✘ Reject**.
3. **Kết quả:** rule chuyển `REJECTED` nhưng **vẫn còn trong DB** kèm
   `reject_reason` (GR22-003 — xem `/admin/rules?status=REJECTED`); event thành
   `IGNORED`; `/admin/audit` có `review.reject` + `rule.rejected` kèm lý do.

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

## Sự cố thường gặp

- **Không nghe beep**: kiểm tra `sos_alert.sound_enabled: true`; trên máy không
  có `winsound` job in `\a` (bell) — một số terminal tắt bell.
- **AI review FAILED / RETRY_REQUIRED**: thiếu API key (.env) hoặc LLM trả về
  JSON sai / timeout — server không crash, xem cột status ở event detail;
  dùng `ai.mock: true` để demo offline.
- **Migration chạy lại**: an toàn — mọi câu lệnh là `IF NOT EXISTS`; file backup
  chỉ tạo một lần trước lần áp dụng đầu tiên.
- **Chạy test**: `.venv\Scripts\python.exe -m pytest tests/ -q`
