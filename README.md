# Screen Watcher Pro — Desktop App

Ứng dụng **desktop (Windows)** giám sát thông tin hiển thị trên màn hình theo đúng
luồng nghiệp vụ trong tài liệu *Screen Watcher*:

> **Chụp cửa sổ (Chrome/Edge) → OCR (Qwen3-VL) → Rule Engine → Cooldown → Email cảnh báo**

Điểm khác biệt so với bản cơ bản: sau khi OCR, app **đánh giá rule trong file YAML**,
**chống spam bằng cooldown**, **gửi email cho owner**, và có **một phần giao diện
giải thích chi tiết VÌ SAO gửi / KHÔNG gửi email** cho từng rule.

Phần chụp màn hình + OCR **tái sử dụng từ `main_qwen_ocr.py`** (tìm cửa sổ thật,
foreground bằng AttachThreadInput + minimize/restore, chụp bbox DPI-aware,
OCR Việt/Anh/Hàn qua Qwen3-VL trên OpenRouter).

Pain point được giải quyết (theo tài liệu): **P01** (thông tin chỉ trên màn hình),
**P02** (kiểm tra thủ công), **P03** (không có cảnh báo tự động), **P04** (không có
bằng chứng kiểm tra).

> 📘 **Hướng dẫn sử dụng giao diện chi tiết** (giới thiệu từng tab, chức năng Chụp/OCR,
> quản lý người dùng, email, history, cách sửa config): xem [GUIDE.md](GUIDE.md).

---

## 1. Chức năng

### Cho người dùng
- **Chọn 1 trình duyệt**: **Chrome** hoặc **Edge** (radio — chỉ chọn 1 tại một thời điểm).
- **Tìm cửa sổ theo tiến trình** (`chrome.exe` / `msedge.exe`) — chính xác kể cả khi
  trình duyệt mở nhiều tab (mất hậu tố tiêu đề) hoặc đang minimize.
- **Tự mở app nếu chưa chạy** (tùy chọn launch).
- **OCR đa ngôn ngữ** (Việt + Anh + Hàn).
- **Xem kết quả ngay trong tab Chụp** — khu vực kết quả là Notebook 5 tab:
  **📝 Nhật ký · 🖼 Ảnh chụp (preview) · 📄 Kết quả OCR · ✉ Giải thích gửi email ·
  📧 Email đã gửi** (email gửi ở chính lần chụp này).
  Chụp xong app tự nhảy sang tab *Ảnh chụp*. (Tab *Lịch sử* vẫn xem lại được mọi lần chụp.)
- **Preview ảnh có zoom**: nút ➖/➕/⤢, cuộn chuột để zoom, kéo để di chuyển;
  **nháy đúp (hoặc nút 🔍)** mở ảnh trong **cửa sổ riêng** cũng có zoom in/out + pan.
  Áp dụng cho cả tab *Chụp* lẫn tab *Lịch sử*.
- **Đánh giá rule + gửi email tự động** sau khi OCR.
- **Gửi email THẬT** qua SMTP với preset provider **Gmail / Outlook / Office 365**
  (vd `owner@example.com`). Đính kèm ảnh screenshot. Xem mục 5 để cấu hình.
- **Gửi thử (Send test email)**: tab **⚙ Rules & Email** có ô nhập địa chỉ + nút
  *✉ Send test email* — ép gửi thật để kiểm tra SMTP (kể cả khi đang DRY-RUN).
- **Xem email đã gửi**: ở **2 nơi** — tab cấp cao **📧 Sent Emails** (tất cả email theo
  quyền) và **tab con trong Capture & OCR** (chỉ email của lần chụp vừa rồi). Chọn 1 dòng để
  xem **toàn bộ nội dung** (tiêu đề, người nhận, lý do, body) — nội dung lưu trong DB.
- **Gửi lại email (resend)**: nút *✉ Resend* trong danh sách email — gửi lại thủ công
  (bỏ qua cooldown). Chạy được cả khi gửi thật lẫn DRY-RUN; chỉ hiện với tài khoản có quyền `capture.run`.
- **Bảng giải thích chi tiết** ("Vì sao gửi / KHÔNG gửi email"):
  với mỗi rule ghi rõ *có khớp không → vì sao → hành động (gửi/cooldown/...) → vì sao → người nhận*.
- Chạy **nền không treo UI** (thread + progress bar + nhật ký).

### Rule Engine (đọc `config/rules.yaml`)
5 loại rule giống tài liệu:

| Loại | Ý nghĩa |
|------|---------|
| `contains` | text CÓ chứa `value` |
| `not_contains` | text KHÔNG chứa `value` (kích hoạt khi vắng mặt) |
| `regex` | `pattern` khớp bất kỳ đâu |
| `all_keywords` | có ĐỦ tất cả `keywords` |
| `any_keywords` | có ÍT NHẤT MỘT `keywords` |

### Cooldown & Email (Business Rule trong tài liệu)
- **BR03**: rule khớp + có owner + hết cooldown → gửi email.
- **BR04**: rule khớp nhưng còn cooldown → KHÔNG gửi lại (giải thích còn bao lâu).
- **BR05**: OCR rỗng → ghi cảnh báo, không đánh giá rule, không gửi.
- **BR06**: SMTP lỗi → ghi nhận `send_failed` kèm **mô tả lỗi chi tiết** (loại exception +
  nguyên nhân khả dĩ: sai mật khẩu, sender chưa verify, timeout, DNS… — xem mục 7), giữ
  cooldown để thử lại.
- **Bật/tắt cooldown để TEST**: đặt `cooldown.enabled: false` trong `config/rules.yaml`
  → cooldown **TẮT**, rule khớp sẽ **luôn gửi** (bỏ qua thời gian chờ), tiện kiểm thử
  đường gửi mail nhiều lần mà không phải đợi 15–60 phút. Đặt lại `true` để bật BR04.
  Trạng thái ON/OFF hiển thị ngay ở tab **⚙ Rules & Email** (dòng *Cooldown*).
- **DRY-RUN**: đặt `email.enabled: false` trong YAML để **mô phỏng** gửi (an toàn khi demo) — vẫn ghi quyết định + cập nhật cooldown.

### Quản trị (admin)
- Quản lý người dùng: thêm, đổi vai trò, reset mật khẩu, bật/tắt, xóa.
- **Bắt buộc đổi mật khẩu lần đầu**: tài khoản **admin mặc định** (và bất kỳ user nào
  vừa được tạo / vừa bị reset mật khẩu) sẽ **bị buộc đổi mật khẩu ngay sau khi đăng nhập**
  trước khi vào được app — tránh để mật khẩu mặc định `admin123` tồn tại lâu dài.
- Tab **⚙ Rules & Email**: xem rule đang nạp + trạng thái cấu hình email + gửi thử email.

### Phân quyền (RBAC)

| Vai trò | Quyền |
|---------|-------|
| **admin** | toàn quyền (gồm xem dữ liệu mọi người + quản lý user) |
| **operator** | `capture.run`, `screenshot.view`, `ocr.view`, `rule.view` |
| **viewer** | `screenshot.view`, `ocr.view`, `rule.view` (chỉ xem) |

| Mã quyền | Ý nghĩa |
|----------|---------|
| `capture.run` | Chụp màn hình và chạy OCR |
| `screenshot.view` / `screenshot.view_all` | Xem screenshot của mình / của mọi người |
| `ocr.view` | Xem OCR text |
| `rule.view` | Xem rule, kết quả đánh giá, quyết định gửi email |
| `user.manage` | Quản lý người dùng & phân quyền |

---

## 2. Cấu trúc dự án

```
screen-watcher-pro/
├── run.cmd                         # Windows launcher: desktop/api/notebook/demo/test
├── run.py                          # Entry point — nạp config + DB + UI
├── RUNBOOK.md                      # Kịch bản chạy demo workshop + 2 câu chat bắt buộc
├── requirements.txt
├── .ocr.env / .smtp.env / .chatbot.env  # secrets (gitignored); *.example đi kèm
├── config/
│   ├── rules.example.yaml          # mẫu cấu hình (commit lên repo)
│   └── rules.yaml                  # ★ cấu hình thật (gitignored) — copy từ example
├── app/
│   ├── config.py                   # đường dẫn, model OCR, load_app_config (YAML)
│   ├── context.py                  # AppContext dùng chung
│   ├── core/                       # ★ tái sử dụng từ main_qwen_ocr.py
│   │   ├── capture.py              #   tìm cửa sổ + foreground + chụp bbox
│   │   ├── ocr.py                  #   OCR Qwen3-VL (OpenRouter)
│   │   └── rule_engine.py          #   đánh giá 5 loại rule + sinh lý do
│   ├── db/
│   │   ├── database.py             # SQLite schema + seed RBAC + admin
│   │   └── repository.py           # CRUD: user/screenshot/ocr/rule/notif/cooldown
│   ├── services/
│   │   ├── auth.py                 # đăng nhập, đổi mật khẩu, hash (PBKDF2), quyền
│   │   ├── email_service.py        # gửi SMTP (kèm ảnh) + chế độ DRY-RUN
│   │   ├── notification_service.py # ★ rule→cooldown→email + "decision trace"
│   │   └── capture_service.py      # điều phối toàn pipeline
│   └── ui/                         # Tkinter (không cần lib GUI ngoài)
│       ├── login_window.py
│       ├── change_password_window.py  # màn hình buộc đổi mật khẩu lần đầu
│       ├── main_window.py          # notebook, hiện tab theo quyền
│       ├── capture_tab.py          # chụp & OCR + 5 tab con (preview zoom/OCR/giải thích/email)
│       ├── history_tab.py          # preview ảnh (zoom) + OCR + giải thích (từ DB)
│       ├── rules_tab.py            # xem rule & trạng thái email
│       ├── emails_tab.py           # EmailListView (bảng+nội dung+Gửi lại) & tab Email cấp cao
│       ├── users_tab.py            # quản lý user (admin)
│       ├── image_viewer.py         # canvas ảnh có zoom/pan + cửa sổ ảnh riêng
│       └── explain.py              # render phần "vì sao gửi / không gửi"
├── data/
│   ├── screenshots/                # ảnh PNG
│   ├── ocr_results/                # bản .txt OCR
│   └── screenwatcher.db            # SQLite (tự tạo)
└── logs/
```

---

## 3. Thực thể quản lý (Database — SQLite)

```
roles ──< role_permissions >── permissions
  │
users ──< capture_sessions ──< screenshots ──1:1── ocr_results
  │                                  │
  │                                  ├──< rule_evaluations   (mỗi rule × screenshot)
  │                                  └──< notifications      (quyết định gửi/không)
  └──< audit_logs
cooldown_state   (theo rule_id — chống gửi lặp)
```

| Bảng | Vai trò | Cột chính |
|------|---------|-----------|
| `roles` / `permissions` / `role_permissions` | RBAC | quan hệ vai trò–quyền (n-n) |
| `users` | Người dùng | `id (UUIDv7, TEXT), username, password_hash, salt, full_name, email, first_name, last_name, phone, role_id, is_active, must_change_password, deleted_at` |
| `capture_sessions` | Một lần bấm "Chụp & OCR" | `user_id, targets, note` |
| `screenshots` | Mỗi ảnh (1 target) = 1 execution | `id (UUIDv7), target_app, window_title, file_path, width, height, status, error, deleted_at` |
| `ocr_results` | OCR text của ảnh | `screenshot_id, model, text, char_count, duration_ms` |
| `rule_evaluations` | Kết quả từng rule trên 1 ảnh | `rule_id, matched, severity, owner_group, reason, matched_terms` |
| `notifications` | Quyết định gửi cho rule khớp + nội dung email | `rule_id, recipients, status, reason, subject, body` |
| `cooldown_state` | Lần gửi gần nhất theo rule | `rule_id, owner_group, last_sent_at` |
| `audit_logs` | Nhật ký hành động | `user_id, action, detail` |
| `chat_sessions` | Phiên hội thoại chatbot theo user | `id, user_id, title, message_count (denormalized), created_at, updated_at, last_message_at, metadata (JSON), deleted_at` |
| `chat_messages` | Tin nhắn (chỉ user + assistant cuối) | `id, session_id, user_id, role, content, error_code, metadata (JSON: model/provider/latency), created_at` |

- `notifications.status`: `sent` / `simulated` / `skipped_cooldown` / `no_owner` / `send_failed` / `skipped_empty`.
  `subject` + `body` chỉ lưu khi có gửi/mô phỏng/thất bại (để xem lại trong tab *Email đã gửi*).
- `users.must_change_password`: `1` = buộc đổi mật khẩu ở lần đăng nhập kế tiếp (admin mặc định,
  user mới tạo, user vừa bị reset). Đổi mật khẩu thành công sẽ tự đặt lại về `0`.
- Mật khẩu lưu **PBKDF2-HMAC-SHA256 + salt**, không lưu plaintext. Mật khẩu SMTP lấy từ **biến môi trường**, không nằm trong file cấu hình.
- **Tất cả khóa chính đều là UUIDv7** (users, screenshots/`execution_id`, ocr_results, capture_sessions, rule_evaluations, notifications, audit_logs, roles, permissions) — time-ordered nên index locality tốt, gần như tuần tự (nhanh như autoincrement) mà vẫn duy nhất toàn cục; mọi FK là TEXT. DB cũ (id INTEGER) sẽ **tự migrate sang UUID khi khởi động** (tự tạo backup `screenwatcher.db.pre-uuid.bak`, remap toàn bộ FK).

---

## 4. Cài đặt

Yêu cầu: **Windows** + **Python ≥ 3.10**.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Tạo file cấu hình từ mẫu (vì `config/rules.yaml` được gitignore — chứa thông tin riêng):

```powershell
Copy-Item config\rules.example.yaml config\rules.yaml
# rồi sửa owners/email trong config\rules.yaml theo nhu cầu
```

Tạo **3 file env** từ mẫu (đã tách theo chức năng; đều được `.gitignore`):

```powershell
Copy-Item .ocr.env.example     .ocr.env       # OPENROUTER_API_KEY (OCR) + OCR_MODEL (Qwen3-VL)
Copy-Item .smtp.env.example    .smtp.env      # WATCHER_SMTP_PASSWORD (chỉ khi gửi email thật)
Copy-Item .chatbot.env.example .chatbot.env   # PROVIDER + key/model chatbot (xem mục 7.1)
```

- **`.ocr.env`** — key OCR (lấy MIỄN PHÍ tại <https://openrouter.ai/keys>) + `OCR_MODEL` (mặc định `qwen/qwen3-vl-30b-a3b-instruct`).
- **`.smtp.env`** — mật khẩu/SMTP key gửi email cảnh báo.
- **`.chatbot.env`** — cấu hình LLM cho chatbot (chọn `PROVIDER`, model, key). Chatbot dùng OpenRouter sẽ tái dùng key trong `.ocr.env`.

> Cả 3 file được nạp tự động (`.env` cũ vẫn được đọc như fallback). Tất cả đọc lại mỗi request nên đổi key/provider **không cần khởi động lại**.

---

## 5. Cấu hình rule & email — `config/rules.yaml`

> Giao diện app hiện **bằng tiếng Anh**. File README này vẫn tiếng Việt làm tài liệu;
> tên tab/nút mô tả bên dưới là nhãn tiếng Anh đúng như trên app.

```yaml
rules:
  - id: error_detected
    name: "Error detected (ERROR/FAILED/TIMEOUT)"
    type: regex
    pattern: "(ERROR|FAILED|TIMEOUT)"
    ignore_case: true
    severity: high
    owner_group: ops_team
    cooldown_minutes: 15

owners:
  ops_team:
    emails: [owner@example.com]

email:
  enabled: true                          # true = gửi THẬT; false = DRY-RUN (mô phỏng)
  provider: custom                       # dùng Brevo làm SMTP relay (xem mục 5.1)
  smtp_host: smtp-relay.brevo.com
  smtp_port: 587
  use_tls: true
  username: xxxxxxxx@smtp-brevo.com       # SMTP login Brevo (KHÔNG phải mật khẩu)
  from: your-verified-sender@gmail.com    # SENDER — phải verify trong Brevo
  password_env: WATCHER_SMTP_PASSWORD     # SMTP key đặt trong .env

cooldown:
  default_minutes: 15
```

**Phân biệt quan trọng — người GỬI vs người NHẬN:**

| | Trong config | Verify ở Brevo? |
|---|---|---|
| **Người gửi** (`email.from`) | địa chỉ đứng tên gửi | ✅ **Bắt buộc** verify 1 lần |
| **Người nhận** (`owners.*.emails`) | nơi nhận cảnh báo (vd `owner@example.com`) | ❌ Không cần — đổi tùy ý |

→ Đổi **người nhận** sau này chỉ sửa `owners`, **không cần đụng Brevo**. Chỉ khi đổi **người gửi** (`from`) mới phải verify địa chỉ mới.

**Provider preset có sẵn** (nếu gửi trực tiếp, không qua Brevo):

| provider | SMTP | Dùng cho |
|----------|------|----------|
| `gmail` | smtp.gmail.com:587 | Gmail — cần **App Password** 16 ký tự |
| `office365` / `outlook` | smtp.office365.com:587 | Microsoft 365 — ⚠ thường bị **tắt SMTP AUTH**, khó dùng |
| `outlook-personal` | smtp-mail.outlook.com:587 | `@outlook.com` / `@hotmail.com` |
| `custom` | tự khai `smtp_host`/`smtp_port`/`use_tls` | dịch vụ relay như **Brevo / SendGrid** |

> 💡 Tài khoản công ty như `@company.com` (Microsoft 365) **thường bị admin tắt SMTP AUTH** → không gửi trực tiếp được. Giải pháp: dùng dịch vụ relay **Brevo** (mục 5.1) làm SMTP server, gửi *tới* `@company.com`.

---

## 5.1. Tạo SMTP với Brevo để gửi mail (khuyến nghị)

Brevo (free ~300 email/ngày, không cần thẻ) đóng vai trò **SMTP server** lo sẵn deliverability. Quy trình:

### Bước 1 — Đăng ký
Tạo tài khoản tại <https://www.brevo.com> → xác nhận email.

### Bước 2 — Verify người GỬI (sender)
Brevo chỉ cho gửi đứng tên địa chỉ đã xác minh:
1. **Senders, Domains, IPs → Senders → Add a sender**.
2. **Sender name** (vd `Screen Watcher`) + **Email** = địa chỉ **bạn truy cập được** (vd một Gmail của bạn).
3. **Save** → Brevo gửi mã/link xác nhận **vào hộp thư đó** → mở mail bấm xác nhận → hiện **Verified** ✅.

> ⚠ Sender **phải là hộp thư thật bạn mở được** (để lấy mã). KHÔNG dùng được:
> - Địa chỉ ảo/bịa (không có hộp thư → không nhận được mã).
> - Mail tạm (mail.tm…) → Brevo thường **đòi authenticate domain** (cần DNS bạn không sở hữu) → bế tắc.
> - `@company.com` làm *sender* → gửi qua Brevo dễ bị bộ lọc của công ty chặn vì DMARC. `@company.com` nên để ở **người nhận**.

### Bước 3 — Lấy thông tin SMTP
**SMTP & API → SMTP**:
- **SMTP Server:** `smtp-relay.brevo.com` · **Port:** `587`
- **Login:** dạng `xxxxxxxx@smtp-brevo.com` (đây là `username`)
- **SMTP key:** bấm **Generate a new SMTP key** → copy (đây là *mật khẩu*, để vào `.smtp.env`)

### Bước 4 — Điền vào app
`config/rules.yaml` (khối `email`):
```yaml
email:
  enabled: true
  provider: custom
  smtp_host: smtp-relay.brevo.com
  smtp_port: 587
  use_tls: true
  username: xxxxxxxx@smtp-brevo.com     # Login ở Bước 3
  from: your-verified-sender@gmail.com   # sender đã verify ở Bước 2
  password_env: WATCHER_SMTP_PASSWORD
owners:
  ops_team:
    emails: [owner@example.com]            # người nhận — không cần verify
```
`.smtp.env`:
```
WATCHER_SMTP_PASSWORD=<SMTP key ở Bước 3>
```

### Bước 5 — Gửi thử & kiểm tra
1. **Khởi động lại** `python run.py`.
2. Tab **⚙ Rules & Email** → ô **To** = `owner@example.com` → **✉ Send test email**.
3. Kiểm tra hộp thư người nhận (**cả Junk/Spam** lần đầu) và **Brevo → Transactional → Logs** (trạng thái `Delivered` / `Blocked`).

### Lưu ý thực tế
- App báo **"Sent"** chỉ nghĩa Brevo đã **nhận** ở mức SMTP. Trạng thái giao thật xem ở **Brevo Logs**. Nếu Logs báo *"sender ... is not valid"* → bạn **chưa verify** địa chỉ `from` (làm lại Bước 2).
- Người nhận có thể thấy **From = `...@brevosend.com`** thay vì Gmail của bạn. Đây là **bình thường**: vì bạn chưa authenticate domain riêng, Brevo viết lại địa chỉ gửi sang domain đã xác thực của họ để **vượt SPF/DKIM/DMARC** (chính nhờ vậy thư mới vào được inbox). Muốn From hiển thị đúng địa chỉ đẹp → phải **authenticate một domain bạn sở hữu** (thêm DKIM/SPF vào DNS) — không làm được với gmail.com/company.com.
- 🔐 SMTP key chỉ để trong `.smtp.env` (đã `.gitignore`). Nếu lộ → vào Brevo tạo key mới.

Sửa YAML/`.env` xong nhớ **khởi động lại app**.

---

## 6. Chạy & sử dụng

Chạy nhanh trên Windows:

```cmd
run.cmd
```

`run.cmd` tự tạo `.venv`, cài dependencies, copy file mẫu nếu thiếu, rồi chạy desktop app. Các mode khác:

```cmd
run.cmd desktop    :: desktop app
run.cmd api        :: FastAPI server tại http://127.0.0.1:8000
run.cmd notebook   :: Jupyter chatbox
run.cmd demo       :: API server + Jupyter chatbox
run.cmd test       :: pytest
```

Runbook demo workshop: [RUNBOOK.md](RUNBOOK.md).

Chạy thủ công:

```powershell
python run.py
```

1. **Đăng nhập** (Sign in): `admin` / `admin123`. **Lần đầu đăng nhập, app sẽ buộc bạn
   đổi mật khẩu** (nhập mật khẩu hiện tại + mật khẩu mới ≥ 6 ký tự) trước khi vào giao diện
   chính. Sau đó đổi/thêm user trong tab *User Management*.
2. Tab **📸 Capture & OCR**:
   - Chọn **Chrome** hoặc **Edge** (radio, 1 trình duyệt), tích *Launch the app if it is not running* nếu cần.
   - Bấm **Capture & OCR**. Khu vực kết quả có 5 tab: **📝 Log**, **🖼 Screenshot**,
     **📄 OCR result**, **✉ Email explanation**, **📧 Sent emails** (email của lần
     chụp này) — chụp xong tự mở tab *Screenshot*.
   - Trong tab *Screenshot*: ➖/➕/⤢ Fit hoặc cuộn chuột để zoom, kéo để di chuyển,
     **nháy đúp** để mở ảnh ở cửa sổ riêng (cũng có zoom).
   - Trong tab *Sent emails*: chọn 1 email → xem nội dung; nút **✉ Resend** để gửi lại thủ công.
   - ⚠ Trong ~1 giây lúc chụp, cửa sổ trình duyệt được đưa lên trên cùng — đừng click sang app khác.
3. Tab **🗂 History & Results**: chọn 1 dòng → xem **ảnh** (có zoom + cửa sổ riêng),
   **OCR text**, và **giải thích** (tái dựng từ DB).
4. Tab **⚙ Rules & Email**: xem rule đang nạp + chế độ email (DRY-RUN / thật) + **Send test email**.
5. Tab **📧 Sent Emails**: danh sách email đã gửi/mô phỏng/thất bại → chọn 1 dòng để xem
   toàn bộ nội dung (tiêu đề, người nhận, lý do, body), hoặc bấm **✉ Resend**.
6. Tab **👥 User Management** (admin).
7. Tab **🚀 API Server** (admin): bật/tắt server REST API ngay trong app (nút *Start/Stop*), mở nhanh Swagger `/docs`. Server chạy tiến trình riêng, tự tắt khi thoát app.
8. Tab **💬 Chatbot** (mọi user): trò chuyện với trợ lý AI ngay trong app. AI gọi tool truy vấn/thao tác DB **theo đúng quyền của bạn** (vd chỉ admin mới tạo/xóa user qua chat). Có nút **🆕 New chat** (bắt đầu phiên mới) và **hiển thị provider/model đang dùng** ở góc phải. Provider/model chọn ở `.chatbot.env`.

### Demo chat AI có kiểm soát

Sau khi đã có ít nhất 1 kết quả watcher mới (Capture & OCR hoặc `GET /api/watcher/executions/latest` trả `has_data:true`), demo 2 câu:

| Câu hỏi | Kỳ vọng |
|--------|---------|
| `Issue hiện tại đang là gì?` | Assistant đánh giá hiện trạng vận hành dựa trên watcher context mới nhất: OCR, rule match, severity, email/cooldown. Nếu chưa có dữ liệu, assistant nói rõ chưa đủ dữ liệu. |
| `cách nấu thịt kho tàu thế nào?` | Assistant từ chối vì ngoài phạm vi Tool Watcher. Phản hồi bắt buộc: `Câu hỏi này nằm ngoài phạm vi hỗ trợ của Tool Watcher Assistant. Vui lòng hỏi về kết quả giám sát, OCR, rule hoặc trạng thái hệ thống.` |

Case 1 chứng minh trợ lý không chỉ chat chung chung mà có thể đọc hiện trạng vận hành. Case 2 chứng minh AI assistance được kiểm soát phạm vi, không trả lời nội dung ngoài nghiệp vụ.

### Demo cooldown nhanh
Mở một trang có chữ `ERROR` hoặc `Daily Sync Failed`, chụp Chrome **2 lần liên tiếp**:
- Lần 1: rule khớp → *EMAIL SENT* (hoặc *Simulated send (DRY-RUN)* nếu `enabled: false`).
- Lần 2: rule vẫn khớp nhưng → *Not sent (in cooldown)* kèm thời gian còn lại (BR04).

Muốn **test riêng đường gửi mail** mà không bị cooldown chặn: đặt `cooldown.enabled: false`
trong `config/rules.yaml` rồi khởi động lại — mỗi lần chụp rule khớp đều gửi (giải thích ghi
*"cooldown is DISABLED → always sends"*). Đặt lại `true` để kiểm chứng BR04 chặn gửi lặp.

### Trang test pain point có sẵn
Thư mục **`test_pages/`** chứa các dashboard HTML mô phỏng đời thực (Anh / Hàn / Việt
và mix) để test nhanh — mở bằng Chrome/Edge rồi chụp. Xem [test_pages/README.md](test_pages/README.md)
để biết trang nào kích hoạt rule nào.

---

## 7. Xử lý sự cố

| Hiện tượng | Khắc phục |
|------------|-----------|
| `OPENROUTER_API_KEY is not configured` | Tạo `.ocr.env`, dán key OCR. |
| `No Google Chrome window found (chrome.exe)` | Mở trình duyệt đó, hoặc tích *Launch the app if it is not running*. |
| `Could not bring the window to the foreground` | App khác đang giữ focus → click vào trình duyệt rồi chụp lại. |
| Gửi email thất bại (`SEND FAILED — …`) | App nay ghi **mô tả lỗi chi tiết** ngay trong tab *Email explanation* / *Sent emails* và full traceback trong `logs/`. Đọc phần mô tả để biết nguyên nhân: *Authentication failed* (sai `username`/mật khẩu — Gmail cần App Password, Brevo cần SMTP key), *Sender refused* (`from` chưa verify), *Connection timed out* (firewall/sai cổng), *DNS lookup failed* (sai `smtp_host`/mất mạng), *TLS/SSL handshake failed* (sai `use_tls`/cổng). Dùng **Send test email** để chẩn đoán nhanh. |
| `Missing SMTP password` | Chưa set `WATCHER_SMTP_PASSWORD` trong `.smtp.env`. |
| Muốn xem rule khớp mà không gửi mail thật | Để `email.enabled: false` (DRY-RUN). |
| Muốn test gửi mail nhiều lần, không bị cooldown chặn | Đặt `cooldown.enabled: false` trong `config/rules.yaml` rồi khởi động lại (rule khớp sẽ luôn gửi). Đặt lại `true` để bật BR04. |
| Quên mật khẩu admin | Xóa `data/screenwatcher.db` (mất dữ liệu cũ) để tạo lại admin mặc định. |

---

## 7.1. AI Chat & Watcher API (server FastAPI)

Ngoài app desktop, dự án có một **HTTP server** (`app/ai/`) cung cấp REST API: xác thực JWT,
quản lý user, chatbot hỏi–đáp và điều khiển/tra cứu watcher. Chạy **song song được** với app
desktop (đọc kết quả read-only; login/tạo–xóa/quản lý user ghi qua một connection riêng).

**Chạy server** — 2 cách:
- Trong app desktop: mở tab **🚀 API Server** → bấm **Start** (khuyến nghị, không cần dòng lệnh).
- Hoặc dòng lệnh (bắt buộc 1 worker vì conversation store in-memory):

```powershell
uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
```

### Chọn LLM provider (`.chatbot.env` — động)

Chatbot dùng LLM qua **OpenAI-compatible API**; provider/model/key đọc từ **`.chatbot.env`**
(+ `.ocr.env` cho key OpenRouter dùng chung) và **re-load mỗi request** — đổi provider/key
**không cần restart**. Chọn provider bằng `PROVIDER=`; `ENDPOINT` chỉ bắt buộc với Azure/Local:

| `PROVIDER` | Key / Model / Endpoint trong `.chatbot.env` |
|---|---|
| `OPENROUTER` (mặc định) | `OPENROUTER_MODEL` (mặc định `openai/gpt-4o-mini`); key dùng chung `OPENROUTER_API_KEY` từ `.ocr.env` |
| `OPENAI` | `OPENAI_API_KEY`, `OPENAI_MODEL` (endpoint: không cần) |
| `AZURE_OPENAI` | `AZURE_OPENAI_API_KEY`, **`AZURE_OPENAI_ENDPOINT`**, `AZURE_OPENAI_MODEL` (deployment), `AZURE_OPENAI_API_VERSION` |
| `LOCAL` | **`LOCAL_LLM_ENDPOINT`** (vd Ollama `http://localhost:11434/v1`), `LOCAL_LLM_MODEL`, `LOCAL_LLM_API_KEY` (tùy) |

**Model mặc định:** `openai/gpt-4o-mini` (OpenRouter) — tool-calling tốt, rẻ; tương lai đổi OpenAI chỉ cần `PROVIDER=OPENAI`.
Các knob **không bí mật** ở `config/rules.yaml` mục `ai:` (`timeout_seconds` 120, `max_context_chars` 6000, `mock`).
Thiếu key → boot vẫn chạy, báo lỗi rõ lúc chat (`CONFIG_ERROR`, retryable). `mock: true` để chạy không cần LLM.
Xem provider/model đang dùng: **`GET /api/chat/provider`** (hoặc nhãn trên tab Chatbot). Docs: <http://127.0.0.1:8000/docs>.

**Công cụ (tools) của chatbot** — LLM gọi tool để truy vấn/thao tác DB **theo đúng quyền người hỏi**:
`get_my_profile`, `get_latest_watcher_result`, `get_execution`, `trigger_capture` (mọi user); `list_users`,
`get_user`, **`create_user`**, `delete_user`, `delete_execution` (**admin**). Ví dụ: admin nhắn *"create a user
bob role operator"* / *"delete user bob"* → chatbot thực hiện; user thường → *"You are a viewer and do not
have permission to delete a user account."* Mọi lần chat + từng tool call (tên, tham số, kết quả) đều được **ghi log** (`logs/`).

**Hai loại thông báo từ chối** (đều bằng tiếng Anh):
- **Sai quyền** — người dùng nhờ làm việc mà tool có nhưng role không đủ quyền → *"You are a {role} and do not have permission to {thing}."* (ví dụ user thường xóa tài khoản → *"You are a viewer and do not have permission to delete a user account."*).
- **Chưa có tool** — nhờ làm việc mà **chưa có tool nào hỗ trợ** (ví dụ đổi mật khẩu — chưa add tool) → *"I cannot perform this action because there is no tool to support it."*

Bảng tool ↔ quyền (định nghĩa trong `app/ai/chat_agent.py`; tool bị chặn do sai quyền → chatbot báo *"You are a {role} and do not have permission to {thing}."*; "admin" = role `admin` hoặc có quyền `user.manage`):

| Tool | Mục đích | Tham số | User | Admin | Endpoint tương ứng |
|------|----------|---------|:--:|:--:|----------|
| `get_my_profile` | Hồ sơ của chính mình | — | ✅ | ✅ | `GET /api/user/profile` |
| `get_latest_watcher_result` | KQ watcher mới nhất (user: của mình; admin: tất cả) | — | ✅ | ✅ | `GET /api/watcher/executions/latest` |
| `get_execution` | Xem 1 execution (user: chỉ của mình; admin: bất kỳ) | `execution_id` | ✅ | ✅ | `GET /api/watcher/executions/{id}` |
| `trigger_capture` | Chụp + OCR + rule | `targets`, `launch` | ✅ | ✅ | `POST /api/watcher/executions` |
| `list_users` | Liệt kê tất cả user | — | ❌ | ✅ | `GET /api/admin/users` |
| `get_user` | Xem 1 user theo username | `username` | ❌ | ✅ | `GET /api/admin/users/{id}` |
| `create_user` | Tạo user mới + gán role | `username`, `password`, `role?`, `email?`… | ❌ | ✅ | `POST /api/admin/users` |
| `delete_user` | Soft-delete user (không xóa admin) | `username` | ❌ | ✅ | `DELETE /api/admin/users/{id}` |
| `delete_execution` | Soft-delete 1 execution | `execution_id` | ❌ | ✅ | `DELETE /api/watcher/executions/{id}` |

### Xác thực & phân quyền (JWT)

API dùng **JWT Bearer token**, tái dùng đúng hệ thống RBAC (users/roles) của app desktop.

1. Chưa có tài khoản? **Tự đăng ký**: `POST /api/auth/register` (tạo user non-admin, trả luôn JWT). Hoặc nhờ admin tạo qua `POST /api/admin/users`.
2. Đăng nhập lấy token: `POST /api/auth/login` với `{"username","password"}` (mặc định `admin`/`admin123`).
3. Gửi kèm header `Authorization: Bearer <access_token>` cho mọi endpoint được bảo vệ.

Endpoint được đặt tên theo **REST convention**, gom nhóm theo domain (Swagger `/docs` hiển thị tách nhóm): `auth` · `user` (self-service) · `admin` (quản lý user) · `watcher` (resource `executions`) · `chat`.

**Phân quyền theo 2 vai trò:**
- **User** (mọi tài khoản đăng nhập): toàn quyền như admin — chat, xem kết quả, trigger chụp — **trừ xóa**. Về tài khoản: chỉ tự quản lý **acc của mình** (`/api/user/*`: xem/sửa thông tin, đổi mật khẩu).
- **Admin** (role `admin`): thêm quyền **xóa** (soft delete, đánh dấu `deleted_at`, ẩn khỏi kết quả) và **quản lý user** (`/api/admin/users`: tạo/xem/sửa/soft-delete, reset mật khẩu, gán role).

> Secret ký JWT lấy từ `.chatbot.env` (`WATCHER_JWT_SECRET`). Nếu để trống sẽ dùng secret dev **không an toàn** (chỉ demo localhost). Sinh secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Thời hạn token cấu hình ở `config/rules.yaml` mục `auth.access_token_minutes` (mặc định 60 phút).

**Các endpoint:**

| Nhóm | Method | Endpoint | Quyền | Mục đích |
|------|--------|----------|-------|----------|
| System | GET | `/health` | công khai | Kiểm tra server sống + cấu hình provider (không lộ key). |
| Auth | POST | `/api/auth/register` | công khai | **Tự đăng ký** (chưa có tài khoản). Tạo user non-admin + tự đăng nhập (trả JWT). Body: `{"username","password","email?","first_name?","last_name?","phone?","full_name?"}`. Tắt được bằng `auth.allow_self_register:false`. |
| Auth | POST | `/api/auth/login` | công khai | Đăng nhập → trả `access_token` (JWT) + thông tin user. |
| User | GET | `/api/user/profile` | user/admin | Xem thông tin tài khoản của **chính mình** (username, email, first/last name, phone, role...). |
| User | PUT | `/api/user/profile` | user/admin | Sửa thông tin của mình: `username`/`full_name`/`email`/`first_name`/`last_name`/`phone` (chỉ field gửi lên). **Không** đổi được `role`/`is_active` của mình. |
| User | POST | `/api/user/change-password` | user/admin | Đổi mật khẩu của mình. Body: `{"current_password","new_password"}`. |
| Admin | GET | `/api/admin/users` | **admin** | Liệt kê user (ẩn user đã soft-delete). |
| Admin | GET | `/api/admin/users/{id}` | **admin** | Xem 1 user. |
| Admin | POST | `/api/admin/users` | **admin** | Tạo user. Body: `{"username","password","role","email?","first_name?","last_name?","phone?","full_name?"}` (role: `admin`/`operator`/`viewer`). |
| Admin | PUT | `/api/admin/users/{id}` | **admin** | Cập nhật user: `username`/`full_name`/`email`/`first_name`/`last_name`/`phone`/`role`/`is_active`/`new_password` (chỉ field gửi lên). |
| Admin | DELETE | `/api/admin/users/{id}` | **admin** | **Soft delete** user thường. Tài khoản **admin không xóa được** (403 "You cannot delete admin account"). |
| AI Chat | POST | `/api/chat` | user/admin | Hỏi–đáp AI (LLM + tools theo quyền người hỏi). Body: `{"message"(≤4000), "session_id"(**UUID**, tùy chọn), "include_latest_watcher_context"(mặc định true), "max_context_chars"}`. Trả `{status, session_id, reply, model, provider, execution_context_used}` (lỗi: `{status:"error", error_code, message, retryable}`). **Hội thoại lưu theo user.** `session_id` phải là **UUID**: UUID đã có (của mình)→nối tiếp; UUID chưa có→phiên mới với id đó; bỏ trống→phiên mới; text như `"demo"`→**422**. |
| AI Chat | GET | `/api/chat/provider` | user/admin | Provider + model chatbot đang dùng: `{provider, model, mock, key_configured}`. |
| AI Chat | POST | `/api/chat/sessions` | user/admin | Tạo **phiên mới** (rỗng), trả `session_id`. Body tùy chọn: `{"title"}`. |
| AI Chat | GET | `/api/chat/sessions` | user/admin | Liệt kê phiên hội thoại của mình (id, title, message_count, last_message_at). |
| AI Chat | GET | `/api/chat/sessions/{id}` | user/admin | Xem tin nhắn 1 phiên (của mình; admin xem của bất kỳ). Người khác → 403. |
| AI Chat | DELETE | `/api/chat/sessions/{id}` | user/admin | **Soft delete** 1 phiên của mình (admin: bất kỳ). |
| Watcher | POST | `/api/watcher/executions` | user/admin | **Trigger app thật**: chụp → OCR → rule → email. Body: `{"targets":["chrome","edge"],"launch":false}`. Trả execution_id mỗi target. ⚠ Chạy trên máy Windows đang mở trình duyệt đích. |
| Watcher | GET | `/api/watcher/executions/latest` | user/admin | Kết quả execution **mới nhất**. **User thường chỉ thấy của mình**, admin thấy của tất cả. `has_data:false` khi chưa có. |
| Watcher | GET | `/api/watcher/executions/{id}` | user/admin | Chi tiết/audit 1 execution (thêm `file_path`, `status`). **User chỉ xem execution của mình** (của người khác → **403**), admin xem tất cả. **404** nếu không tồn tại/đã xóa. |
| Watcher | DELETE | `/api/watcher/executions/{id}` | **admin** | **Soft delete** 1 execution (`deleted_at`). User thường → **403**. |

> `execution_id` chính là `screenshot_id` — không phát sinh khoá mới, tái dùng schema có sẵn.
> Các endpoint đọc dùng connection **read-only**; `login`, tạo/xóa execution, quản lý user dùng chung 1 connection **ghi**.

**Lỗi & validate:** dữ liệu sai định dạng trả **422** với JSON rõ ràng nêu đúng field lỗi:
```json
{"status":"error","error_code":"VALIDATION_ERROR",
 "message":"Dữ liệu không hợp lệ — email: Email không hợp lệ...",
 "fields":[{"field":"email","message":"..."}]}
```
Quy tắc: `email` phải đúng định dạng (`user@example.com`), `phone` 6–20 ký tự (số/`+ - ( )`/space), `password`/`new_password` ≥ 6 ký tự, `username` ≥ 3 ký tự, `role` ∈ {`admin`,`operator`,`viewer`}. Trên Swagger `/docs`, mỗi API đã có **ví dụ hợp lệ điền sẵn** — bấm *Try it out* là chạy được ngay (không còn `"string"` gây lỗi).

**Mã lỗi thường gặp:** `401 UNAUTHENTICATED` (thiếu token), `401 TOKEN_EXPIRED`/`INVALID_TOKEN`, `403 FORBIDDEN` với message **"You don't have permission to access action."** (không đủ quyền), `409 CONFLICT` (username trùng), `422 VALIDATION_ERROR` (sai định dạng). Mọi khóa chính (`id`, `execution_id`...) là **UUIDv7** — xem [mục 3](#3-thực-thể-quản-lý-database--sqlite).

**Bảo mật / Observability (spec §16):** bind mặc định `127.0.0.1`; key chỉ từ `.env`; không log secret/prompt. Khi expose ra ngoài, đặt `server.require_api_token: true` (rules.yaml) → mọi endpoint (trừ health/docs/auth) yêu cầu header `X-API-Token: <WATCHER_API_TOKEN>`. Message `/chat` giới hạn 4000 ký tự; context watcher giới hạn `ai.max_context_chars`; mỗi request có `X-Request-ID` + log method/path/status/thời lượng.

**Client Jupyter chatbox:**

```powershell
jupyter notebook notebooks/chatbox.ipynb
```

```python
from app.ai.chatbox import launch_chatbox
# đăng nhập tự động để lấy JWT rồi mở chatbox
launch_chatbox("http://127.0.0.1:8000", username="admin", password="admin123")
```

---

## 8. Giới hạn

- Chỉ chạy trên **Windows** (Win32 API để chụp cửa sổ).
- Chụp theo **cửa sổ trình duyệt**, không theo monitor vật lý.
- Chưa có scheduler tự động (Task Scheduler/cron) — app chạy theo thao tác người dùng.
  Rule engine / cooldown / email đã có đầy đủ theo tài liệu.
