# Test Pages — Pain Point mô phỏng đời thực

Bộ trang HTML giả lập **dashboard/console vận hành thật** để test Screen Watcher Pro:
mở trong **Chrome** hoặc **Edge** → app chụp + OCR → đánh giá rule → quyết định gửi mail.
Các trang phủ **tiếng Anh, tiếng Hàn, tiếng Việt và mix** để thử thách OCR.

## Cách dùng

1. Mở `index.html` (hoặc một trang bất kỳ) bằng **Chrome** hoặc **Edge**.
   - Phóng to cửa sổ, để zoom ~100–125% cho chữ rõ → OCR chính xác hơn.
2. Mở app **Screen Watcher Pro** (`python run.py`), tab **📸 Chụp & OCR**.
3. Tích **Chrome** hoặc **Edge** (đúng trình duyệt đang mở trang) → **Chụp & OCR**.
4. Xem panel **"Vì sao gửi / KHÔNG gửi email"** và tab **🗂 Lịch sử & Kết quả**.

> Mặc định `email.enabled: false` → DRY-RUN (mô phỏng gửi). Đổi sang `true` + cấu hình
> SMTP trong `config/rules.yaml` nếu muốn gửi mail thật.

## Bảng trang & rule kích hoạt (đã kiểm chứng bằng rule engine)

### Pain point cơ bản

| Trang | Ngôn ngữ | Tình huống | Rule khớp | Owner nhận mail |
|-------|----------|------------|-----------|-----------------|
| `01_ops_dashboard_en.html` | English | NOC/incident console production | `error_detected`, `daily_sync_failed`, `success_no_alert` | ops_team |
| `02_db_backup_ko.html` | 한국어 + EN | Giám sát DB / backup / replication | `error_detected`, `daily_sync_failed` | ops_team |
| `03_payment_fraud_vi.html` | Tiếng Việt | Cổng thanh toán / cảnh báo gian lận | `error_detected`, `payment_keywords` | ops_team + finance_team |
| `04_global_ops_mixed.html` | VI + EN + KO | NOC toàn cầu 3 vùng (mix nặng) | `error_detected`, `daily_sync_failed`, `payment_keywords` | ops_team + finance_team |
| `05_all_healthy.html` | EN + VI | Mọi thứ "Completed" / bình thường | (không có) | — (KHÔNG gửi mail) |
| `13_payment_fraud_en.html` | English | Payments ops console — CHỈ cảnh báo thanh toán (không có ERROR/FAILED/TIMEOUT) | `payment_keywords` | **chỉ finance_team** |

### Mô phỏng tool monitoring phổ biến

| Trang | Tool mô phỏng | Ngôn ngữ | Rule khớp | Owner nhận mail |
|-------|---------------|----------|-----------|-----------------|
| `06_grafana_en.html` | **Grafana** (dashboard + Alert rules) | English | `error_detected`, `daily_sync_failed` | ops_team |
| `07_datadog_vi.html` | **Datadog** (Monitors) | Tiếng Việt + EN | `error_detected`, `daily_sync_failed`, `payment_keywords` | ops_team + finance_team |
| `08_alertmanager_ko.html` | **Prometheus Alertmanager** | 한국어 + EN | `error_detected`, `daily_sync_failed` | ops_team |
| `09_kibana_mixed.html` | **Kibana / Elastic** (Logs Discover) | VI + EN + KO | `error_detected`, `daily_sync_failed` | ops_team |
| `10_sentry_en.html` | **Sentry** (Issues / error tracking) | English | `error_detected`, `daily_sync_failed`, `success_no_alert` | ops_team |
| `11_pagerduty_vi.html` | **PagerDuty** (Incidents) | Tiếng Việt + EN | `error_detected`, `daily_sync_failed`, `payment_keywords`, `success_no_alert` | ops_team + finance_team |
| `12_cloudwatch_ko.html` | **AWS CloudWatch** (Alarms) | 한국어 + EN | `error_detected`, `daily_sync_failed` | ops_team |

## Mục đích từng trang

- **01 — Production Ops Console (EN):** bảng sự cố + log stream với `ERROR`, `FAILED`,
  `TIMEOUT`, batch *"Daily Sync Failed"*. Không có chữ "Completed" → `success_no_alert`
  cũng kích hoạt. Trường hợp "nhiều rule cùng bắn".

- **02 — DB Monitoring (KO+EN):** tiếng Hàn (백업 실패, 복제 지연...) **trộn** từ khóa lỗi
  tiếng Anh. Thử khả năng OCR Hangul + chữ Latin trong cùng ảnh. Có dòng "Completed"
  nên `success_no_alert` không bắn (giống dashboard thật có cả job thành công).

- **03 — Payment/Fraud (VI):** tiếng Việt đầy dấu (đ, ữ, ơ, ₫...) + từ khóa thanh toán
  `declined`, `chargeback`, `fraud` và `TIMEOUT`. Kích hoạt **2 owner group khác nhau**
  (ops_team vì TIMEOUT, finance_team vì fraud) — minh họa định tuyến mail theo rule.

- **04 — Global Ops (MIX 3 ngôn ngữ):** Việt + Anh + Hàn trộn dày đặc trong 3 cột vùng
  miền + ticker. Thử thách OCR cao nhất; kích hoạt gần như mọi rule.

- **05 — All Healthy (EN+VI):** tất cả "Completed"/"Thành công", **không** có
  ERROR/FAILED/TIMEOUT/declined/chargeback/fraud, và **có** chữ "Completed" → không rule
  nào khớp. Dùng để demo phần giải thích **"vì sao KHÔNG gửi mail"**.

- **13 — NovaPay Payments Console (EN):** dashboard vận hành thanh toán trông như thật
  (KPI, bảng giao dịch, disputes) với `declined`/`chargeback`/`fraud` ở cỡ chữ lớn, đậm.
  **Cố ý KHÔNG có** ERROR/FAILED/TIMEOUT/Daily Sync → **chỉ** rule `payment_keywords` khớp,
  nên mail chỉ gửi cho **finance_team** — trang chuyên để test luồng gửi mail cho finance.

## Mẹo demo cooldown (BR04)

Chụp **trang 01 hai lần liên tiếp** bằng cùng trình duyệt:
- Lần 1: `error_detected`/`daily_sync_failed` → *Mô phỏng gửi (DRY-RUN)*.
- Lần 2: vẫn khớp nhưng → *Không gửi (đang cooldown)* kèm thời gian còn lại.

## Lưu ý OCR

- OCR là mô hình thị giác (Qwen3-VL) nên có thể đọc sai vài ký tự nếu chữ quá nhỏ/mờ.
  Phóng to cửa sổ và tăng zoom giúp tăng độ chính xác.
- Nếu chỉnh sửa nội dung trang, nhớ giữ đúng từ khóa rule (`ERROR`, `FAILED`, `TIMEOUT`,
  `Daily`+`Sync`+`Failed`, `declined`/`chargeback`/`fraud`) để kết quả khớp như bảng trên.
