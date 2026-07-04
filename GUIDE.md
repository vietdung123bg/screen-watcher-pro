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
13. [Tab 🚀 API Server — mở REST API](#13-tab--api-server--mở-rest-api)
13a. [Tab 📓 Jupyter — mở notebook chatbox](#13a-tab--jupyter--mở-notebook-chatbox)
14. [REST API (cho client ngoài)](#14-rest-api-cho-client-ngoài)

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

# 2) Biến môi trường — 3 file tách theo chức năng (đều gitignore)
Copy-Item .ocr.env.example     .ocr.env       # OPENROUTER_API_KEY (OCR) + OCR_MODEL (Qwen3-VL)
Copy-Item .smtp.env.example    .smtp.env      # WATCHER_SMTP_PASSWORD (chỉ khi gửi mail thật)
Copy-Item .chatbot.env.example .chatbot.env   # PROVIDER + key/model chatbot (xem §14.0)
```
Mở `.ocr.env` điền **OPENROUTER_API_KEY** (lấy MIỄN PHÍ tại <https://openrouter.ai/keys>).
Cả 3 file nạp tự động và đọc lại mỗi request (đổi key/provider không cần restart).
Chi tiết các trường xem [mục 5](#5-sửa-file-cấu-hình) và [§14.0](#140-chọn-llm-provider-ở-env-động).

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

### Buộc đổi mật khẩu lần đầu (Change password)
Vì lý do bảo mật, một số tài khoản **bắt buộc đổi mật khẩu ngay sau khi đăng nhập** trước khi
vào được giao diện chính:

- **Tài khoản admin mặc định** (`admin` / `admin123`) — để mật khẩu mặc định không tồn tại lâu.
- **User vừa được admin tạo** trong tab *User Management*.
- **User vừa bị admin reset mật khẩu**.

Màn hình **Change password** yêu cầu:
1. **Current password** — mật khẩu hiện tại (vừa dùng để đăng nhập).
2. **New password** — mật khẩu mới **≥ 6 ký tự** và **khác** mật khẩu hiện tại.
3. **Confirm new password** — gõ lại để khớp.

Đổi thành công → app mở thẳng giao diện chính; cờ buộc-đổi được gỡ nên các lần đăng nhập
sau không hỏi lại. (Trong DB: cột `users.must_change_password` chuyển từ `1` về `0`.)

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
| **🚀 API Server** | `user.manage` | Bật/tắt REST API server ngay trong app (chỉ admin) |
| **📓 Jupyter** | `user.manage` | Khởi động Jupyter server mở `chatbox.ipynb` (chỉ admin) |
| **💬 Chatbot** | mọi user đăng nhập | Trò chuyện với trợ lý AI; AI gọi tool DB theo đúng quyền của bạn |

Ví dụ: `admin` thấy đủ tab; `operator`/`viewer` thấy các tab theo quyền + **Chatbot**
(luôn có cho mọi tài khoản đăng nhập).

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
  password_env: WATCHER_SMTP_PASSWORD     # TÊN biến môi trường chứa mật khẩu (ở .smtp.env)
```
- `enabled: false` → **DRY-RUN**: rule vẫn được đánh giá, quyết định vẫn ghi, cooldown vẫn
  cập nhật, nhưng **không gửi thật** (hiển thị *"Simulated send (DRY-RUN)"*). Rất hợp để demo.
- **Provider preset**: đặt `provider: gmail` (hoặc `outlook`/`office365`/`outlook-personal`)
  thì không cần khai `smtp_host`/`smtp_port`. Gmail cần **App Password 16 ký tự**.
- **Brevo / SendGrid** (khuyến nghị): `provider: custom` + khai `smtp_host` thủ công.
  Xem [README.md mục 5.1](README.md) để tạo SMTP relay Brevo.
- 🔐 **Mật khẩu không bao giờ nằm trong YAML** — chỉ đặt **tên biến** ở `password_env`,
  còn giá trị thật để trong `.smtp.env`.

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

### 5.5. Các file `.env` (tách 3 file, đều gitignore)
```ini
# .ocr.env  — OCR
OPENROUTER_API_KEY=sk-or-v1-...              # BẮT BUỘC để OCR chạy
OCR_MODEL=qwen/qwen3-vl-30b-a3b-instruct     # model OCR (đã đưa ra khỏi code)

# .smtp.env — email
WATCHER_SMTP_PASSWORD=...                     # mật khẩu/SMTP key — chỉ cần khi gửi mail thật

# .chatbot.env — LLM chatbot (xem §14.0)
PROVIDER=OPENROUTER                           # OPENAI | AZURE_OPENAI | OPENROUTER | LOCAL
OPENROUTER_MODEL=openai/gpt-4o-mini
# (OpenAI/Azure/Local: *_API_KEY / *_MODEL / *_ENDPOINT tương ứng)
WATCHER_JWT_SECRET=                           # secret ký JWT (để trống = secret dev)
WATCHER_API_TOKEN=                            # chỉ khi server.require_api_token: true
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

### OCR service (Qwen3-VL qua OpenRouter) — core/[ocr.py](app/core/ocr.py)
OCR service biến ảnh PNG vừa chụp thành text:

- **Model & nhà cung cấp**: gửi ảnh tới **Qwen3-VL** (mô hình thị giác đa phương thức) qua
  **OpenRouter**, dùng client tương thích OpenAI. Cần `OPENROUTER_API_KEY` trong `.ocr.env`
  (lấy MIỄN PHÍ tại <https://openrouter.ai/keys>); nếu thiếu, bước OCR báo lỗi rõ ràng.
- **Đa ngôn ngữ & nguyên văn**: prompt yêu cầu trích **toàn bộ** text nhìn thấy và giữ nguyên
  **Việt (có dấu) + Anh + Hàn (한글)** — không dịch, không phiên âm, không bỏ ký tự — giữ đúng
  thứ tự đọc và ngắt dòng giữa các khối.
- **Tiền xử lý ảnh**: trước khi gửi, ảnh được **thu nhỏ về cạnh dài tối đa 1600px**
  (`OCR_MAX_IMAGE_DIM` trong [config.py](app/config.py); đặt `0` để gửi nguyên kích thước) rồi
  mã hóa thành data URL PNG base64. Việc này tiết kiệm token và tăng tốc. `temperature=0` cho
  kết quả ổn định.
- **Kết quả trả về**: text + số ký tự + thời gian (ms) (+ token usage). Một bản `.txt` được lưu
  cạnh ảnh trong `data/ocr_results/`, và text được lưu vào database (bảng `ocr_results`).
- **Đổi model**: qua biến môi trường `OCR_MODEL`. Mặc định `qwen/qwen3-vl-30b-a3b-instruct`;
  lựa chọn khác: `qwen/qwen3-vl-235b-a22b-instruct` (mạnh nhất, chậm hơn) và
  `qwen/qwen3-vl-8b-instruct` (nhẹ nhất, nhanh nhất).
- **Mẹo tăng độ chính xác**: phóng to cửa sổ và để zoom ~100–125% cho chữ rõ — OCR là mô hình
  thị giác nên chữ quá nhỏ/mờ có thể bị đọc sai.
- **OCR rỗng**: nếu không trích được text, app ghi cảnh báo và bỏ qua đánh giá rule + gửi mail (BR05).

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
  (admin/operator/viewer). Trùng username sẽ báo lỗi. User mới **bị buộc đổi mật khẩu** ở
  lần đăng nhập đầu tiên (mật khẩu admin đặt chỉ là tạm thời).
- **🔑 Change role** — chọn dòng → đổi vai trò.
- **♺ Reset password** — chọn dòng → nhập mật khẩu mới (ẩn ký tự). Mật khẩu này là **tạm thời**:
  user sẽ **bị buộc tự đổi** ở lần đăng nhập kế tiếp.
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
| `OPENROUTER_API_KEY is not configured` | Tạo `.ocr.env`, dán API key OCR. |
| `No Google Chrome window found (chrome.exe)` | Mở trình duyệt, hoặc tick **Launch the app if it is not running**. |
| `Could not bring the window to the foreground` | App khác đang giữ focus → click vào trình duyệt rồi chụp lại. |
| Gửi email **thất bại** (`SEND FAILED — …`) | App ghi **mô tả lỗi chi tiết** ở tab *Email explanation* / *Sent emails* và full traceback trong `logs/`. Đọc mô tả để biết nguyên nhân: *Authentication failed* (sai login/mật khẩu — Gmail cần App Password, Brevo cần SMTP key), *Sender refused* (`from` chưa verify), *Connection timed out* (firewall/sai cổng), *DNS lookup failed* (sai `smtp_host`/mất mạng), *TLS/SSL handshake failed* (sai `use_tls`/cổng). Dùng **Send test email** để chẩn đoán nhanh. |
| `Missing SMTP password` | Chưa set `WATCHER_SMTP_PASSWORD` trong `.smtp.env`. |
| Muốn xem rule khớp mà **không gửi mail thật** | Đặt `email.enabled: false` (DRY-RUN). |
| Muốn **test gửi mail nhiều lần** không bị cooldown chặn | Đặt `cooldown.enabled: false`, khởi động lại. |
| Quên mật khẩu admin | Xóa `data/screenwatcher.db` (mất dữ liệu cũ) để tạo lại admin mặc định. |
| Sửa `rules.yaml`/`.env` không thấy đổi | **Khởi động lại app** — cấu hình chỉ nạp lúc chạy. |

---

## 13. Tab 🚀 API Server — mở REST API

Chỉ hiện với **admin** (`user.manage`). Server REST API **tự khởi động cùng app** ngay khi admin
đăng nhập — **không cần bấm Start**.

- **Host / Port** — mặc định `127.0.0.1` / `8000`.
- **Tự khởi động** — khi mở tab (lúc admin đăng nhập) server tự chạy, trạng thái là **● Running**
  kèm URL. Nút **▶ Start server** lúc này **bị mờ** (đã chạy sẵn).
- **■ Stop** — dừng server. Sau khi dừng, nút **▶ Start** mới **bật lại** để bạn chạy lại thủ công.
- **🌐 Open API docs** — mở Swagger UI (`/docs`) trên trình duyệt để thử API trực tiếp.

Ghi chú:
- Chạy **tiến trình con** riêng (1 worker) nên không treo app; **tự tắt khi bạn thoát app**.
- Nếu cổng đang bận (auto-start thất bại) trạng thái về **○ Stopped** và nút Start bật lại để thử lại.
- Đọc/ghi **cùng `data/screenwatcher.db`** với app (mở connection riêng) — chạy song song được.
- Log server ghi vào `logs/api_server.log`.

---

## 13a. Tab 📓 Jupyter — mở notebook chatbox

Chỉ hiện với **admin** (`user.manage`). Khởi động **Jupyter server** phục vụ `notebooks/chatbox.ipynb`
— client notebook gọi REST API (server API đã tự chạy ở tab 🚀 API Server).

- **Tự khởi động cùng app**: khi admin đăng nhập, Jupyter server tự chạy (song song với API Server)
  và giao diện notebook tự mở trong cửa sổ WebView2 — **không cần bấm Start**.
- **Host / Port** — mặc định `127.0.0.1` / `8888`.
- **▶ Start Jupyter** — (dùng khi đã Stop) chạy `jupyter notebook … --no-browser` trong **tiến trình
  con**. App **tự đọc URL kèm token** từ log Jupyter; khi có URL, **tự mở giao diện Jupyter trong một
  cửa sổ WebView2 do app quản lý** (một tiến trình con riêng, dùng pywebview).
- **📓 Open in app** — mở lại cửa sổ WebView2 nếu đã đóng.
- **🌐 Browser** — mở `chatbox.ipynb` (kèm token) bằng trình duyệt ngoài.
- **■ Stop** — dừng Jupyter server **và** đóng cửa sổ WebView2.

Ghi chú:
- Cần **Jupyter** (`pip install notebook`) và **pywebview** (`pip install pywebview`) cho cửa sổ trong
  app — cả hai đã có trong `requirements.txt`. Thiếu Jupyter → tab báo *"Jupyter is not installed…"*;
  thiếu pywebview → tự mở bằng **trình duyệt ngoài** (kèm gợi ý cài).
- Cửa sổ WebView2 dùng engine Edge (có sẵn trên Windows 11). Chạy tiến trình riêng nên không treo
  app; **cả server lẫn cửa sổ tự tắt khi thoát app**. Log server ghi vào `logs/jupyter.log`.
- Trong notebook: đăng nhập `admin / admin123` rồi chạy các cell để chat qua watcher API.

---

## 13b. Tab 💬 Chatbot — trợ lý AI

Có cho **mọi tài khoản đăng nhập**. Chat trực tiếp trong app với trợ lý AI:
- Gõ câu hỏi (vd *"latest watcher result?"*, *"list all users"*, *"create a user bob role operator"*,
  *"delete user bob"*) → **Send**.
- AI trả lời và **gọi tool truy vấn/thao tác DB theo đúng quyền của bạn**: user thường chỉ xem dữ
  liệu của mình; admin mới **tạo/liệt kê/xóa user, xóa execution**. Vượt quyền → AI báo
  *"You are a {role} and do not have permission to {thing}."* (vd *"You are a viewer and do not have
  permission to delete a user account."*).
- **Hỗ trợ & định hướng:** nhờ giải quyết vấn đề **về app** mà **chưa có tool** để tự thao tác
  (đổi mật khẩu, sửa hồ sơ, đổi role / bật–tắt user, sửa rule/owner/cấu hình email, gửi/gửi lại
  email) → AI **không từ chối**: nói rõ không làm trực tiếp được rồi **hướng dẫn từng bước** (làm ở
  tab nào trong app desktop, hoặc endpoint REST nào), và dùng `get_alert_recipients` khi bạn hỏi về
  email nhận alert.
- **Phạm vi (scope):** trợ lý **chỉ** hỗ trợ về app (watcher/OCR/rule/email/execution/tài khoản/
  trạng thái) + chào hỏi cơ bản. Hỏi chủ đề ngoài app (nấu ăn, sửa xe, thể thao…) → từ chối một câu
  **tiếng Anh**: *"This question is outside the scope of the Tool Watcher Assistant..."*. Trả lời theo
  ngôn ngữ người hỏi; riêng câu từ chối luôn tiếng Anh.
- **🆕 New chat** (góc trên) — bắt đầu phiên hội thoại mới.
- **Panel Chat history (bên trái)** — liệt kê các phiên chat đã lưu. **Bấm vào một phiên để mở lại
  và tiếp tục chat** (nội dung cũ được nạp lại làm ngữ cảnh). Nút **⟳** để tải lại danh sách.
  - **User thường**: chỉ thấy **phiên của chính mình** (cột *Conversation*, *Last activity*).
  - **Admin**: thấy phiên của **toàn bộ người dùng** (thêm cột *User*), nhưng **chỉ tiếp tục được
    phiên của chính mình**. Chọn phiên của người khác → mở **chỉ đọc** 🔒 (ô nhập + nút Send bị khóa,
    có banner "Read-only: viewing {user}'s conversation"). Đây đúng luật mà REST API áp dụng qua
    `ChatStore.ensure_session` (phiên của người khác → `PermissionError`).
- **Hiển thị provider + model đang dùng** ở góc phải header (vd *"Provider: openrouter · Model: openai/gpt-4o-mini"*), cập nhật khi bấm New chat.
- LLM chạy **nền** nên UI không treo. Provider/model chọn ở `.chatbot.env` (xem §14.0).
- **Trả lời dạng streaming**: câu trả lời hiện dần **theo token** thay vì đợi xong mới hiện. Khi
  trợ lý đang gọi tool, dòng trạng thái hiển thị *⚙ using {tên_tool}…*.
- **Định dạng Markdown/HTML**: câu trả lời được render **đậm/nghiêng, tiêu đề, danh sách, `code` +
  khối code, blockquote, link** (Markdown; HTML cơ bản cũng được chuyển đổi) — token stream ra thô,
  khi hoàn tất tự format lại. Lịch sử hội thoại khi mở lại cũng hiển thị đã định dạng.
- **Hội thoại được lưu vào DB theo từng user** (bảng `chat_sessions`/`chat_messages`) — tối ưu
  ghi nặng: chỉ lưu tin nhắn user + trả lời cuối, kèm metadata (model/provider/latency).
- **Log chi tiết LLM** (cả app desktop lẫn API, cùng dùng `ChatAgent` → ghi vào `logs/`): mỗi
  lượt chat log `chat START` (user/role/session/provider/model/engine/ctx_used/số history),
  câu hỏi của user, context đã chèn; mỗi bước gọi LLM log số stream chunk; **suy nghĩ (thinking)**
  của model (`reasoning` và/hoặc content trước khi gọi tool); từng **tool call** (tên + tham số +
  người gọi) và **tool result**; cuối cùng là `chat REPLY` kèm latency + độ dài.

## 14. REST API (cho client ngoài)

### 14.0. Chọn LLM provider ở `.chatbot.env` (động)
Chatbot (tab & API `/api/chat`) dùng LLM qua OpenAI-compatible API. Chọn provider bằng
`PROVIDER=` trong **`.chatbot.env`** (đọc lại mỗi request → đổi không cần restart):
`OPENROUTER` (mặc định, `OPENROUTER_MODEL=openai/gpt-4o-mini`, key dùng chung `OPENROUTER_API_KEY`
từ `.ocr.env`), `OPENAI` (`OPENAI_API_KEY`/`OPENAI_MODEL`), `AZURE_OPENAI` (cần `AZURE_OPENAI_ENDPOINT`
+ deployment + `AZURE_OPENAI_API_VERSION`), `LOCAL` (Ollama/LM Studio, `LOCAL_LLM_ENDPOINT`).
`ENDPOINT` chỉ bắt buộc với Azure/Local. Knob không bí mật (`timeout_seconds` 120,
`max_context_chars` 6000, `mock`) ở `config/rules.yaml` mục `ai:`. Xem provider/model đang dùng:
**`GET /api/chat/provider`** hoặc nhãn trên tab Chatbot.

Server FastAPI (`app/ai/`) cung cấp REST API cho client ngoài (Jupyter, script, web…), tái dùng
đúng RBAC của app. Tự chạy cùng app qua tab **🚀 API Server** (admin), hoặc dòng lệnh:

```powershell
uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1

Server FastAPI (`app/ai/`) cung cấp REST API cho client ngoài (Jupyter, script, web…), tái dùng
đúng RBAC của app. Tự chạy cùng app qua tab **🚀 API Server** (admin), hoặc dòng lệnh:

```powershell
uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
```
Tài liệu tương tác: **http://127.0.0.1:8000/docs** (mỗi API có ví dụ hợp lệ điền sẵn).

### 14.1. Xác thực bằng JWT
1. **Chưa có tài khoản** → tự đăng ký: `POST /api/auth/register` (tạo user thường, trả luôn token).
2. **Đăng nhập**: `POST /api/auth/login` với `{"username","password"}` (mặc định `admin`/`admin123`).
3. Gắn header **`Authorization: Bearer <access_token>`** cho mọi endpoint được bảo vệ.

Secret ký token lấy từ `.chatbot.env` (`WATCHER_JWT_SECRET`); thời hạn ở `config/rules.yaml`
(`auth.access_token_minutes`, mặc định 60 phút).

### 14.2. Phân quyền (admin vs user)
- **User** (mọi tài khoản đăng nhập): chat, xem/trigger watcher, tự sửa hồ sơ & đổi mật khẩu
  **của mình** — **KHÔNG** xóa, **KHÔNG** đổi `role`/`is_active` của mình, **KHÔNG** quản lý user khác.
- **Admin**: thêm quyền **xóa** (soft delete) và **quản lý mọi user**.
- Không đủ quyền → **403** với message **"You don't have permission to access action."**
- **Xem screenshot/OCR**: user chỉ thấy execution **do chính mình chụp**; admin thấy **tất cả**.

### 14.2b. Bảng tool của chatbot & quyền

Trợ lý AI gọi các **tool** để truy vấn/thao tác DB, mỗi tool **tự kiểm quyền theo người hỏi**
(định nghĩa trong `app/ai/chat_agent.py`). Tool bị chặn do sai quyền → chatbot trả *"You are a {role}
and do not have permission to {thing}."*; nhờ việc chưa có tool hỗ trợ → *"I cannot perform this action
because there is no tool to support it."* ("admin" = role `admin` hoặc có quyền `user.manage`):

| Tool | Mục đích | Tham số | User | Admin | Endpoint tương ứng |
|------|----------|---------|:--:|:--:|----------|
| `get_my_profile` | Hồ sơ của chính mình | — | ✅ | ✅ | `GET /api/user/profile` |
| `get_latest_watcher_result` | KQ watcher mới nhất (user: của mình; admin: tất cả) | — | ✅ | ✅ | `GET /api/watcher/executions/latest` |
| `get_alert_recipients` | Email nhận alert: owner group + email, rule→group, email bật/tắt (đọc `config/rules.yaml`, không lộ secret) | — | ✅ | ✅ | — |
| `get_execution` | Xem 1 execution (user: chỉ của mình; admin: bất kỳ) | `execution_id` | ✅ | ✅ | `GET /api/watcher/executions/{id}` |
| `trigger_capture` | Chụp + OCR + rule | `targets`, `launch` | ✅ | ✅ | `POST /api/watcher/executions` |
| `list_users` | Liệt kê tất cả user | — | ❌ | ✅ | `GET /api/admin/users` |
| `get_user` | Xem 1 user theo username | `username` | ❌ | ✅ | `GET /api/admin/users/{id}` |
| `create_user` | Tạo user mới + gán role | `username`, `password`, `role?`, `email?`… | ❌ | ✅ | `POST /api/admin/users` |
| `delete_user` | Soft-delete user (không xóa admin) | `username` | ❌ | ✅ | `DELETE /api/admin/users/{id}` |
| `delete_execution` | Soft-delete 1 execution | `execution_id` | ❌ | ✅ | `DELETE /api/watcher/executions/{id}` |

### 14.3. Danh sách endpoint

| Nhóm | Method | Endpoint | Quyền |
|------|--------|----------|-------|
| system | GET | `/health` | công khai |
| auth | POST | `/api/auth/register` | công khai |
| auth | POST | `/api/auth/login` | công khai |
| user | GET · PUT | `/api/user/profile` | user/admin (của mình) |
| user | POST | `/api/user/change-password` | user/admin (của mình) |
| admin | GET | `/api/admin/users` · `/api/admin/users/{id}` | admin |
| admin | POST | `/api/admin/users` | admin |
| admin | PUT | `/api/admin/users/{id}` | admin |
| admin | DELETE | `/api/admin/users/{id}` | admin (không xóa được tài khoản admin) |
| ai-chat | POST | `/api/chat` | user/admin — `session_id` phải là **UUID** (bỏ trống/UUID chưa có → phiên mới; UUID của mình → nối tiếp; text như "demo" → 422). Thêm `"stream": true` để nhận **SSE** (event `meta`/`thinking`/`delta`/`tool_call`/`tool_result`/`done`, kết `[DONE]`) |
| ai-chat | GET | `/api/chat/provider` | user/admin — provider + model đang dùng |
| ai-chat | POST | `/api/chat/sessions` | user/admin — tạo phiên mới, trả `session_id` |
| ai-chat | GET | `/api/chat/sessions` · `/api/chat/sessions/{id}` | user/admin (của mình; admin: bất kỳ) |
| ai-chat | DELETE | `/api/chat/sessions/{id}` | user/admin (soft delete phiên của mình; admin: bất kỳ) |
| watcher | POST | `/api/watcher/executions` | user/admin (trigger chụp thật) |
| watcher | GET | `/api/watcher/executions/latest` | user/admin (user: của mình) |
| watcher | GET | `/api/watcher/executions/{id}` | user/admin (user: của mình) |
| watcher | DELETE | `/api/watcher/executions/{id}` | admin (soft delete) |

> Chi tiết body/mục đích từng endpoint: xem [README.md mục 7.1](README.md).

### 14.4. Khóa chính UUID
Mọi `id` (kể cả `execution_id`) là **UUIDv7** (chuỗi, time-ordered). DB cũ (id INTEGER) sẽ
**tự migrate** sang UUID khi khởi động (tạo backup `screenwatcher.db.pre-uuid.bak`, giữ nguyên dữ liệu).

### 14.5. Ví dụ nhanh (PowerShell)
```powershell
# đăng nhập admin -> lấy access_token
curl.exe -X POST http://127.0.0.1:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin123\"}"

$T = "PASTE_ACCESS_TOKEN"
curl.exe http://127.0.0.1:8000/api/user/profile -H "Authorization: Bearer $T"
curl.exe http://127.0.0.1:8000/api/watcher/executions/latest -H "Authorization: Bearer $T"
curl.exe -X POST http://127.0.0.1:8000/api/watcher/executions -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d "{\"targets\":[\"chrome\"]}"
```

### 14.6. Chatbox Jupyter
```powershell
jupyter notebook notebooks/chatbox.ipynb
```
```python
from app.ai.chatbox import launch_chatbox
launch_chatbox("http://127.0.0.1:8000", username="admin", password="admin123")
```
Lỗi validate trả **422** với JSON nêu rõ field sai; lỗi/mã trạng thái khác xem
[README.md mục 7.1](README.md).
