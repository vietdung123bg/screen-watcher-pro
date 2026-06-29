# Hướng dẫn sử dụng — Screen Watcher Pro

Tài liệu này giới thiệu **giao diện**, cách **chạy app**, cách **sửa file cấu hình** và giải
thích **từng tab / chức năng** (Chụp & OCR, Lịch sử, Rules & Email, Email đã gửi, Quản lý
người dùng).

> Giao diện app hiển thị bằng **tiếng Anh**. Tài liệu này dùng tiếng Việt để giải thích,
> nhưng giữ nguyên **tên tab/nút tiếng Anh** đúng như trên app để bạn dễ đối chiếu.
>
> Phần cài đặt SMTP/Brevo chuyên sâu xem thêm ở [README.md](README.md) (mục 5 & 5.1).

---

## Mục lục
1. [Tổng quan](#1-tổng-quan)
2. [Cài đặt & chạy app](#2-cài-đặt--chạy-app)
3. [Đăng nhập & phân quyền](#3-đăng-nhập--phân-quyền-rbac)
4. [Tổng quan giao diện](#4-tổng-quan-giao-diện)
5. [Sửa file cấu hình](#5-sửa-file-cấu-hình)
6. [Tab 📸 Capture & OCR — Chụp & OCR](#6-tab--capture--ocr--chụp--ocr)
7. [Tab 🗂 History & Results — Lịch sử](#7-tab--history--results--lịch-sử)
8. [Tab ⚙ Rules & Email](#8-tab--rules--email)
9. [Tab 📧 Sent Emails — Email đã gửi](#9-tab--sent-emails--email-đã-gửi)
10. [Tab 👥 User Management — Quản lý người dùng](#10-tab--user-management--quản-lý-người-dùng)
11. [Luồng quyết định gửi email & Cooldown](#11-luồng-quyết-định-gửi-email--cooldown)
12. [Xử lý sự cố nhanh](#12-xử-lý-sự-cố-nhanh)

---

## 1. Tổng quan

Screen Watcher Pro là app **desktop Windows** giám sát thông tin hiển thị trên màn hình.
Luồng nghiệp vụ:

```
Chụp cửa sổ (Chrome/Edge) → OCR (Qwen3-VL) → Rule Engine → Cooldown → Email cảnh báo
```

- **Chụp**: chụp đúng cửa sổ trình duyệt bạn chọn (kể cả khi đang minimize).
- **OCR**: trích xuất text đa ngôn ngữ (Việt + Anh + Hàn).
- **Rule Engine**: so text với các rule trong `config/rules.yaml`.
- **Cooldown**: chống gửi email lặp lại quá dày.
- **Email**: gửi cảnh báo (kèm ảnh) cho nhóm owner; mỗi quyết định đều có **giải thích chi tiết**.

---

## 2. Cài đặt & chạy app

### Yêu cầu
- **Windows** + **Python ≥ 3.10**.

### Cài đặt
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Tạo file cấu hình (lần đầu)
```powershell
# 1) Cấu hình rule + email (file thật bị gitignore, copy từ mẫu)
Copy-Item config\rules.example.yaml config\rules.yaml

# 2) Biến môi trường: API key OCR (+ mật khẩu SMTP nếu gửi mail thật)
Copy-Item .env.example .env
```
Mở `.env` điền **OPENROUTER_API_KEY** (lấy MIỄN PHÍ tại <https://openrouter.ai/keys>).
Chi tiết các trường xem [mục 5](#5-sửa-file-cấu-hình).

### Chạy
```powershell
python run.py
```
Entry point [run.py](run.py) sẽ: tạo thư mục dữ liệu → nạp `rules.yaml` → khởi tạo SQLite
(+ seed RBAC và tài khoản admin mặc định) → mở màn hình đăng nhập.

> Dữ liệu sinh ra: ảnh ở `data/screenshots/`, text OCR ở `data/ocr_results/`,
> database `data/screenwatcher.db`, log ở `logs/`.

---

## 3. Đăng nhập & phân quyền (RBAC)

### Màn hình đăng nhập (Sign in)
- Mở app → nhập **Username** / **Password** → **Sign in** (Enter cũng được).
- Tài khoản mặc định lần đầu: **`admin` / `admin123`** (gợi ý hiện sẵn trên màn hình).
- Đăng nhập sai sẽ báo rõ: *"Tài khoản không tồn tại."*, *"Mật khẩu không đúng."* hoặc
  *"Tài khoản đã bị vô hiệu hóa."*

Mật khẩu được lưu **băm PBKDF2-HMAC-SHA256 + salt** (không lưu plaintext).

### 3 vai trò có sẵn

| Vai trò | Quyền | Nhìn thấy dữ liệu |
|---------|-------|-------------------|
| **admin** | tất cả 6 quyền (gồm quản lý user) | của **mọi người** |
| **operator** | `capture.run`, `screenshot.view`, `ocr.view`, `rule.view` | chỉ **của mình** |
| **viewer** | `screenshot.view`, `ocr.view`, `rule.view` (chỉ xem) | chỉ **của mình** |

### Bảng mã quyền

| Mã quyền | Ý nghĩa |
|----------|---------|
| `capture.run` | Chụp màn hình + chạy OCR (và gửi lại email) |
| `screenshot.view` | Xem screenshot **của mình** |
| `screenshot.view_all` | Xem screenshot **của mọi người** (chỉ admin) |
| `ocr.view` | Xem text OCR |
| `rule.view` | Xem rule, kết quả đánh giá & quyết định gửi email |
| `user.manage` | Quản lý người dùng & phân quyền |

> **Tab nào hiện ra phụ thuộc quyền.** Tài khoản không có quyền nào sẽ thấy thông báo
> *"Your account has no permissions assigned."*

---

## 4. Tổng quan giao diện

Sau khi đăng nhập là **cửa sổ chính**:
- **Thanh tiêu đề**: tên app + họ tên & vai trò của bạn + nút **Sign out** (đăng xuất).
- **Dải tab (Notebook)** hiển thị **theo quyền**:

| Tab | Hiện khi có quyền | Chức năng |
|-----|-------------------|-----------|
| **📸 Capture & OCR** | `capture.run` | Chụp + OCR + đánh giá rule + gửi email |
| **🗂 History & Results** | `screenshot.view` | Xem lại mọi lần chụp (ảnh, OCR, giải thích) |
| **⚙ Rules & Email** | `rule.view` | Xem rule đang nạp + trạng thái email + gửi thử |
| **📧 Sent Emails** | `rule.view` | Danh sách email đã gửi/mô phỏng/thất bại + gửi lại |
| **👥 User Management** | `user.manage` | Quản lý người dùng (chỉ admin) |

Ví dụ: `admin` thấy đủ 5 tab; `operator` thấy 4 tab (trừ User Management);
`viewer` thấy History & Results, Rules & Email, Sent Emails (không chụp được).

---

## 5. Sửa file cấu hình

Mọi cấu hình rule/owner/email/cooldown nằm trong **`config/rules.yaml`**.
**Sửa xong phải khởi động lại app** (`python run.py`) để nạp lại.

> ⚠ `config/rules.yaml` bị gitignore (chứa thông tin riêng). Nếu chưa có, copy từ
> `config/rules.example.yaml`. Nếu file lỗi/thiếu, app vẫn chạy với cấu hình rỗng và
> hiện cảnh báo `⚠` ở tab **⚙ Rules & Email**.

### 5.1. Rules — định nghĩa rule

5 loại rule (xem [rule_engine.py](app/core/rule_engine.py)):

| `type` | Khớp khi… | Trường cần khai |
|--------|-----------|-----------------|
| `contains` | text **CÓ** chứa chuỗi | `value` |
| `not_contains` | text **KHÔNG** chứa chuỗi (kích hoạt khi vắng mặt) | `value` |
| `regex` | biểu thức chính quy khớp bất kỳ đâu | `pattern` |
| `all_keywords` | có **ĐỦ tất cả** từ khóa | `keywords: [...]` |
| `any_keywords` | có **ít nhất một** từ khóa | `keywords: [...]` |

```yaml
rules:
  - id: error_detected                 # BR01: id phải DUY NHẤT
    name: "Error detected (ERROR/FAILED/TIMEOUT)"
    type: regex
    pattern: "(ERROR|FAILED|TIMEOUT)"
    ignore_case: true                  # không phân biệt hoa/thường
    severity: high                     # high | medium | low (đưa vào tiêu đề mail)
    owner_group: ops_team              # BR02: phải trỏ tới một nhóm trong `owners`
    cooldown_minutes: 15               # thời gian chờ riêng cho rule này
```

### 5.2. Owners — nhóm nhận cảnh báo
```yaml
owners:
  ops_team:
    emails:
      - owner@example.com              # người NHẬN — đổi tùy ý, KHÔNG cần verify
  finance_team:
    emails:
      - finance-owner@example.com
```
`owner_group` của rule phải khớp một key ở đây, nếu không → quyết định ghi
*"Not sent (no owner)"*.

### 5.3. Email (SMTP)
```yaml
email:
  enabled: true            # true = GỬI THẬT; false = DRY-RUN (chỉ mô phỏng, an toàn demo)
  provider: custom         # gmail | outlook | office365 | outlook-personal | custom
  smtp_host: smtp-relay.brevo.com
  smtp_port: 587
  use_tls: true
  username: xxxx@smtp-brevo.com           # LOGIN SMTP (không phải mật khẩu)
  from: your-verified-sender@gmail.com    # NGƯỜI GỬI — phải verify ở nhà cung cấp
  password_env: WATCHER_SMTP_PASSWORD     # TÊN biến môi trường chứa mật khẩu (ở .env)
```
- `enabled: false` → **DRY-RUN**: rule vẫn được đánh giá, quyết định vẫn ghi, cooldown vẫn
  cập nhật, nhưng **không gửi thật** (hiển thị *"Simulated send (DRY-RUN)"*). Rất hợp để demo.
- **Provider preset**: đặt `provider: gmail` (hoặc `outlook`/`office365`/`outlook-personal`)
  thì không cần khai `smtp_host`/`smtp_port`. Gmail cần **App Password 16 ký tự**.
- **Brevo / SendGrid** (khuyến nghị): `provider: custom` + khai `smtp_host` thủ công.
  Xem [README.md mục 5.1](README.md) để tạo SMTP relay Brevo.
- 🔐 **Mật khẩu không bao giờ nằm trong YAML** — chỉ đặt **tên biến** ở `password_env`,
  còn giá trị thật để trong `.env`.

### 5.4. Cooldown — chống spam (kèm công tắc TEST)
```yaml
cooldown:
  default_minutes: 15      # dùng khi rule không khai cooldown_minutes
  enabled: true            # true = BẬT cooldown (BR04). false = TẮT để test → luôn gửi.
```
- `enabled: true` (mặc định): rule khớp trong thời gian chờ sẽ **không gửi lại** (BR04).
- `enabled: false`: **tắt cooldown để test** → rule khớp **luôn gửi**, bỏ qua thời gian chờ.
  Tiện kiểm thử đường gửi mail nhiều lần mà không phải đợi 15–60 phút.
  Trạng thái ON/OFF hiển thị ngay ở tab **⚙ Rules & Email** (dòng *Cooldown*).

### 5.5. File `.env`
```ini
OPENROUTER_API_KEY=sk-or-v1-...          # BẮT BUỘC để OCR chạy
WATCHER_SMTP_PASSWORD=...                # mật khẩu/SMTP key — chỉ cần khi gửi mail thật
# OCR_MODEL=qwen/qwen3-vl-30b-a3b-instruct   # (tùy chọn) đổi model OCR
```

---

## 6. Tab 📸 Capture & OCR — Chụp & OCR

Tab chính để **chụp + OCR + đánh giá rule + gửi email**, chạy **nền** (không treo UI).

### Khu vực điều khiển (phía trên)
1. **Choose a browser to capture (pick one)** — radio chọn **một** trình duyệt:
   **Google Chrome** hoặc **Microsoft Edge**.
2. **Launch the app if it is not running** (mặc định ✔) — tự mở trình duyệt nếu chưa chạy.
3. **Note** — ghi chú tùy chọn cho lần chụp (lưu kèm phiên chụp).
4. Nút **📸 Capture & OCR** + thanh tiến trình (progress bar) chạy khi đang xử lý.

> ⚠ Khi bấm chụp, trong ~1 giây cửa sổ trình duyệt được **đưa lên trên cùng** — đừng click
> sang app khác lúc đó, nếu không ảnh có thể sai cửa sổ.

### Chức năng "Chụp" hoạt động thế nào (core/[capture.py](app/core/capture.py))
- **Tìm đúng cửa sổ theo TÊN TIẾN TRÌNH** (`chrome.exe` / `msedge.exe`) thay vì theo tiêu đề
  → chính xác kể cả khi trình duyệt mở nhiều tab (mất hậu tố tiêu đề).
- Bỏ qua cửa sổ **cloaked** (ở virtual desktop khác) và cửa sổ quá nhỏ; nếu có nhiều cửa sổ
  thì chọn cái **diện tích lớn nhất**.
- **Đưa cửa sổ lên foreground tin cậy**: thử nhẹ bằng `AttachThreadInput`, không được thì
  **minimize/restore** (tối đa 6 lần). Nếu vẫn thất bại → hủy chụp để tránh chụp nhầm.
- **Chụp theo bbox thật, DPI-aware** (`DwmGetWindowAttribute`) → đúng trên màn hình scale >100%.
- Nếu chưa mở trình duyệt và đã tick *Launch…* → app tự mở rồi chờ tối đa **15 giây**.

### Chức năng "OCR" hoạt động thế nào (core/[ocr.py](app/core/ocr.py))
- Gửi ảnh tới **Qwen3-VL qua OpenRouter** (cần `OPENROUTER_API_KEY`).
- **Đa ngôn ngữ**: giữ nguyên Việt (có dấu) + Anh + Hàn (한글), không dịch, không bỏ ký tự.
- Ảnh được **thu nhỏ về tối đa 1600px** trước khi gửi để tiết kiệm token/tăng tốc.
- Trả về text + số ký tự + thời gian (ms). Bản `.txt` được lưu cạnh ảnh trong `data/ocr_results/`.

### Khu vực kết quả — 5 tab con
Sau khi chụp xong, app **tự nhảy sang tab 🖼 Screenshot**. Các tab con:

| Tab con | Nội dung |
|---------|----------|
| **📝 Log** | Nhật ký real-time từng bước (✔ thành công, △ cảnh báo, ✖ lỗi) + tóm tắt rule |
| **🖼 Screenshot** | Ảnh vừa chụp, có **zoom/pan** (xem bên dưới) |
| **📄 OCR result** | Toàn bộ text OCR + nguồn + số ký tự |
| **✉ Email explanation** | Giải thích **vì sao gửi / KHÔNG gửi** từng rule (xem [mục 11](#11-luồng-quyết-định-gửi-email--cooldown)) |
| **📧 Sent emails** | Các email gửi/mô phỏng **trong chính lần chụp này** (chọn dòng để xem nội dung, Resend) |

### Thao tác zoom ảnh (dùng chung cho Capture & History)
- Nút **➖ Zoom out** / **➕ Zoom in** / **⤢ Fit** (vừa khung).
- **Cuộn chuột** để zoom, **kéo** để di chuyển.
- **Nháy đúp** (hoặc nút **🔍 Open in new window**) để mở ảnh ở **cửa sổ riêng** cũng có zoom/pan.

---

## 7. Tab 🗂 History & Results — Lịch sử

Xem lại **mọi lần chụp** (tái dựng từ database), kể cả sau khi đóng/mở lại app.

- Nút **⟳ Refresh** + nhãn đếm số screenshot và phạm vi (*all users* / *yours*).
- **Bảng danh sách** các cột: **ID, Time, User, App, Window title, Status, Chars**.
  - `admin` (có `screenshot.view_all`) thấy của **mọi người**; vai trò khác chỉ thấy **của mình**.
- **Chọn 1 dòng** → khu chi tiết:
  - **Bên trái — Screenshot preview**: ảnh có zoom/pan + nút **🔍 New window**.
  - **Bên phải — 2 tab**:
    - **OCR result**: text OCR + model + số ký tự + thời gian (cần quyền `ocr.view`).
    - **Why email sent / not sent**: bảng giải thích quyết định (cần quyền `rule.view`).

---

## 8. Tab ⚙ Rules & Email

Xem nhanh **app đang nạp gì** và **gửi thử email** để kiểm tra SMTP.

### Configuration status (config/rules.yaml)
Hiển thị trạng thái cấu hình đang chạy:
- **Email mode**: `REAL SEND` hay `DRY-RUN (simulate, not actually sent)`.
- **Provider**, **SMTP host**\:**port**, **Sender** (`from`), **Password env**.
- **Rules**: số rule đã nạp; **Owner groups**: số email mỗi nhóm.
- **Default cooldown**: số phút mặc định.
- **Cooldown**: **ON (BR04 active)** hoặc **OFF — testing mode: matched rules always send**
  (phản ánh `cooldown.enabled`).
- Nếu file cấu hình lỗi/thiếu → dòng cảnh báo `⚠` màu đỏ.

### Send a test email (verify SMTP) — *chỉ với quyền `capture.run`*
- Ô **To** (mặc định điền sẵn địa chỉ `from`/`username`) + nút **✉ Send test email**.
- **Ép gửi THẬT** kể cả khi đang DRY-RUN → dùng để kiểm tra cấu hình SMTP.
- Thành công → *"✔ Sent"*; thất bại → *"✖ Failed"* kèm **mô tả lỗi chi tiết**
  (sai mật khẩu, sender chưa verify, timeout, DNS sai… — xem [mục 12](#12-xử-lý-sự-cố-nhanh)).

### Rules
Bảng liệt kê rule: **ID, Name, Type, Condition, Severity, Owner, Cooldown**.

---

## 9. Tab 📧 Sent Emails — Email đã gửi

Danh sách **mọi email** đã **gửi / mô phỏng (DRY-RUN) / thất bại** (phạm vi theo quyền:
admin xem tất cả, người khác xem của mình).

- **Bảng** các cột: **Time, Captured by, Browser, Rule, Status, Recipients, Subject**.
- **Chọn 1 dòng** → khung **Email content** hiện đầy đủ: Status, Time, Source, Rule (+owner),
  Recipients, Subject, **Reason** (lý do gửi/không), và **toàn bộ body** email.
- Nút **✉ Resend selected email** (*chỉ với quyền `capture.run`*): **gửi lại thủ công**,
  **bỏ qua cooldown**. Trong DRY-RUN chỉ mô phỏng. Có hộp xác nhận trước khi gửi.
- Nút **🔄 Refresh** để tải lại danh sách.

> Tab con **📧 Sent emails** trong Capture & OCR dùng **cùng widget này** nhưng chỉ hiển thị
> email của **lần chụp vừa rồi**.

---

## 10. Tab 👥 User Management — Quản lý người dùng

Chỉ hiện với **admin** (`user.manage`). Bảng cột: **ID, Username, Full name, Role, Active**.

Thanh nút:
- **➕ Add user** — mở hộp thoại nhập **Username, Full name, Password, Role**
  (admin/operator/viewer). Trùng username sẽ báo lỗi.
- **🔑 Change role** — chọn dòng → đổi vai trò.
- **♺ Reset password** — chọn dòng → nhập mật khẩu mới (ẩn ký tự).
- **⏻ Enable/disable** — bật/tắt tài khoản (tài khoản tắt không đăng nhập được).
- **🗑 Delete** — xóa tài khoản (có xác nhận).
- **⟳ Refresh** — tải lại danh sách.

> 🔒 Không thể **tự vô hiệu hóa** hoặc **tự xóa** tài khoản đang đăng nhập.

---

## 11. Luồng quyết định gửi email & Cooldown

Sau khi OCR, [notification_service.py](app/services/notification_service.py) đánh giá từng rule
và ghi lại **vì sao gửi / không gửi** (Business Rule trong tài liệu):

| Tình huống | Trạng thái | Quy tắc |
|------------|------------|---------|
| Rule không khớp | *Rule not matched* | — |
| Khớp nhưng owner_group không có email | *Not sent (no owner)* | BR02 |
| Khớp + có owner + **hết** cooldown | **EMAIL SENT** (hoặc *Simulated* nếu DRY-RUN) | **BR03** |
| Khớp nhưng **còn** cooldown | *Not sent (in cooldown)* (kèm thời gian còn lại) | **BR04** |
| OCR rỗng | *Skipped (empty OCR)* — không đánh giá rule | **BR05** |
| Gửi SMTP lỗi | *Send FAILED* (kèm mô tả lỗi) — **giữ cooldown để thử lại** | **BR06** |

**Cooldown** lưu theo `rule_id` trong bảng `cooldown_state` (tồn tại qua các lần chạy app).
- Khi gửi thành công/mô phỏng → cập nhật mốc thời gian gửi gần nhất.
- Khi gửi **thất bại** → KHÔNG cập nhật → lần chụp sau được thử lại ngay (BR06).

### Demo cooldown nhanh
Mở trang có chữ `ERROR` (hoặc `Daily Sync Failed`), chụp **2 lần liên tiếp**:
- Lần 1: rule khớp → *EMAIL SENT* / *Simulated send (DRY-RUN)*.
- Lần 2: rule vẫn khớp nhưng → *Not sent (in cooldown)* kèm thời gian còn lại (BR04).

### Test gửi mail nhiều lần (tắt cooldown)
Đặt `cooldown.enabled: false` trong `config/rules.yaml` → khởi động lại → mỗi lần chụp rule khớp
**đều gửi** (giải thích ghi *"cooldown is DISABLED → always sends"*). Đặt lại `true` để bật BR04.

> Reset cooldown để test lại từ đầu (khi `enabled: true`):
> ```powershell
> python -c "import sqlite3; c=sqlite3.connect(r'data/screenwatcher.db'); c.execute('DELETE FROM cooldown_state'); c.commit()"
> ```

---

## 12. Xử lý sự cố nhanh

| Hiện tượng | Khắc phục |
|------------|-----------|
| `OPENROUTER_API_KEY is not configured` | Tạo `.env`, dán API key OCR. |
| `No Google Chrome window found (chrome.exe)` | Mở trình duyệt, hoặc tick **Launch the app if it is not running**. |
| `Could not bring the window to the foreground` | App khác đang giữ focus → click vào trình duyệt rồi chụp lại. |
| Gửi email **thất bại** (`SEND FAILED — …`) | App ghi **mô tả lỗi chi tiết** ở tab *Email explanation* / *Sent emails* và full traceback trong `logs/`. Đọc mô tả để biết nguyên nhân: *Authentication failed* (sai login/mật khẩu — Gmail cần App Password, Brevo cần SMTP key), *Sender refused* (`from` chưa verify), *Connection timed out* (firewall/sai cổng), *DNS lookup failed* (sai `smtp_host`/mất mạng), *TLS/SSL handshake failed* (sai `use_tls`/cổng). Dùng **Send test email** để chẩn đoán nhanh. |
| `Missing SMTP password` | Chưa set `WATCHER_SMTP_PASSWORD` trong `.env`. |
| Muốn xem rule khớp mà **không gửi mail thật** | Đặt `email.enabled: false` (DRY-RUN). |
| Muốn **test gửi mail nhiều lần** không bị cooldown chặn | Đặt `cooldown.enabled: false`, khởi động lại. |
| Quên mật khẩu admin | Xóa `data/screenwatcher.db` (mất dữ liệu cũ) để tạo lại admin mặc định. |
| Sửa `rules.yaml`/`.env` không thấy đổi | **Khởi động lại app** — cấu hình chỉ nạp lúc chạy. |
