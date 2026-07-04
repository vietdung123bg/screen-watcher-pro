# Ảnh minh hoạ (Screenshots) — shot list

Các file `*.png` ở đây hiện là **PLACEHOLDER**. Hãy **chụp màn hình thật** rồi **ghi đè đúng tên
file** (giữ nguyên tên) — README.md/GUIDE.md sẽ tự hiển thị ảnh mới.

## Cách chụp trên Windows
- Cửa sổ đang focus: **Alt + PrintScreen** → dán vào Paint → lưu PNG.
- Vùng tuỳ chọn: **Win + Shift + S** (Snipping) → lưu PNG.
- Nên phóng to cửa sổ, zoom ~100–125% cho chữ rõ.

## Danh sách ảnh cần chụp (mỗi chức năng: trước khi chạy → bắt đầu chạy → kết quả)

| File | Chức năng | Bước | Chụp gì |
|------|-----------|------|---------|
| `01_signin.png` | Sign in | Màn hình | Màn hình đăng nhập (admin / admin123). |
| `02_capture_before.png` | Capture & OCR | **Before** | Tab Capture, đã chọn Chrome/Edge, **chưa** bấm Capture. |
| `03_capture_running.png` | Capture & OCR | **Running** | Ngay khi bấm **Capture & OCR** — progress bar + tab Log đang chạy. |
| `04_capture_result.png` | Capture & OCR | **Result** | Sau khi xong: tab OCR result / Email explanation / Sent emails. |
| `05_history.png` | History & Results | Result | Chọn 1 execution → ảnh + OCR + giải thích (tái dựng từ DB). |
| `06_rules.png` | Rules & Email | Before | Rule đang nạp + chế độ email (DRY-RUN / thật) + Cooldown ON/OFF. |
| `07_rules_send_test.png` | Rules & Email | Running | Nhập địa chỉ + bấm **Send test email**. |
| `08_sent_emails.png` | Sent Emails | Result | Danh sách email đã gửi/mô phỏng/thất bại + nội dung 1 email. |
| `09_user_management.png` | User Management | Result | Bảng user (admin): thêm / đổi role / bật-tắt / xóa. |
| `10_api_server.png` | API Server | Running | Tab API Server trạng thái **● Running** (tự khởi động cùng app). |
| `11_api_swagger.png` | API Server | Result | Swagger UI tại `http://127.0.0.1:8000/docs` trên trình duyệt. |
| `12_chatbot_before.png` | Chatbot | Before | New chat + panel **Chat history** bên trái. |
| `13_chatbot_streaming.png` | Chatbot | Running | Đang trả lời (stream theo token) + dòng *⚙ using {tool}…*. |
| `14_chatbot_result.png` | Chatbot | Result | Trả lời hiển thị **định dạng Markdown** (đậm/tiêu đề/list/code/link). |
| `15_jupyter.png` | Jupyter | Running | Cửa sổ notebook chatbox mở **trong app** (WebView2). |

> Gợi ý cho ảnh Chatbot: dùng câu như *"Liệt kê rule đang match và đánh giá hiện trạng"* để câu trả
> lời có markdown (đậm, bullet, code) — thấy rõ tính năng render. Với ảnh finance, mở
> `test_pages/13_payment_fraud_en.html` rồi Capture để rule `payment_keywords` khớp.
