# 05 — Jupyter Notebook Web Client (Chatbox)

> Chương **12** của docx. Đầu vào của task **T06 (Jupyter chatbox)**.
> Đây là "web app" nhẹ phục vụ demo/kiểm thử — **không chứa logic AI**, chỉ gọi API.

---

## Nguyên tắc
Client chỉ: thu input → gửi HTTP request → hiển thị response. Mọi xử lý AI nằm ở server.

## 12.1. Trách nhiệm của Client
- [ ] Hiển thị chat history
- [ ] Nhận message từ user (input / ipywidgets)
- [ ] Gửi `POST /chat`
- [ ] Hiển thị reply từ server
- [ ] Hiển thị lỗi kết nối / lỗi API rõ ràng

## 12.2. Code Skeleton (ipywidgets)
```python
import requests
import ipywidgets as widgets
from IPython.display import display

API_URL = "http://127.0.0.1:8000/chat"

def send_message(message):
    payload = {
        "session_id": "local-demo-session",
        "message": message,
        "include_latest_watcher_context": True,
    }
    response = requests.post(API_URL, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()["reply"]

chat_history = widgets.Output()
text_input = widgets.Text(placeholder="Nhập câu hỏi cho Tool Watcher...")
button = widgets.Button(description="Gửi")

def on_send(_):
    msg = text_input.value.strip()
    text_input.value = ""
    if not msg:
        return
    with chat_history:
        print("You:", msg)
        print("Bot:", send_message(msg))
        print("---")

button.on_click(on_send)
display(chat_history, text_input, button)
```

> Thiết kế này giảm chi phí frontend, dễ trình diễn, chỉnh sửa ngay khi demo.

---

## ✅ Checklist thực hiện (T06)
- [ ] Tạo notebook `notebooks/chatbox.ipynb` (đề xuất)
- [ ] Cell cài đặt: `requests`, `ipywidgets`
- [ ] Ô nhập + nút Gửi + vùng history
- [ ] `timeout=180` cho request (khớp timeout AI)
- [ ] **Xử lý lỗi**: bắt `requests.exceptions` + response `status=="error"` → in `error_code` + `message` thân thiện
- [ ] **Fallback không widget**: vòng lặp `input()` + `requests` đơn giản (phòng khi ipywidgets lỗi — rủi ro ở [08](08-testing-risk.md))
- [ ] Cho phép đổi `API_URL` / `session_id` ở đầu notebook

## Definition of Done
- Mở notebook, nhập câu hỏi → thấy reply từ server.
- Khi server tắt / lỗi → hiển thị thông báo rõ ràng, không văng traceback dài.

---

👉 Tiếp theo: [06-yeu-cau-fr-nfr.md](06-yeu-cau-fr-nfr.md)
