# Bokin Upscale 4K trên web công ty

Trang web nội bộ dành cho nhân viên: kéo thả ảnh (được chọn nhiều ảnh), chờ 1–3 phút, rồi tải ảnh 4K về. Phía sau, trang gọi API của TensorArt để chạy đúng workflow **FLUX.2 Klein** bạn đang dùng (`tensorart/Bokin_Flux2_Klein_4K_Upscale_TensorArt.json`). Nhân viên không cần tài khoản TensorArt, không thấy workflow và không thấy khoá API.

```
Trình duyệt nhân viên ──► server.py (máy chủ công ty, giữ khoá API) ──► TensorArt API ──► workflow Klein
        ◄── ảnh 4K ───────────┘
```

Gồm 2 file: `server.py` (máy chủ) và `index.html` (giao diện). Chỉ cần **Python 3.9 trở lên**, không phải cài thêm thư viện.

## 1. Đăng workflow Klein thành AI Tool trên TensorArt

1. Mở workflow Klein trên TensorArt và chạy thử một lần cho chắc.
2. Bấm **Các Nút TA** (TA Nodes), chọn ô `image` của node **Load Image** để người dùng thay được ảnh. Không cần mở ô nào khác.
3. Bấm **Xuất bản** (Publish) thành AI Tool. Nếu TensorArt cho chọn chế độ riêng tư, nên chọn riêng tư.
4. Lấy **mã AI Tool**: dãy số trong đường link của AI Tool, thường có dạng `tensor.art/template/<mã>`.

## 2. Lấy khoá API

1. Vào [tams.tensor.art/apps](https://tams.tensor.art/apps), tạo một ứng dụng (app).
2. Ghi lại **API key** và **địa chỉ endpoint** (dạng `https://ap-east-1.tensorart.cloud`).
3. Kiểm tra số credit của tài khoản API trên trang TAMS. Credit API có thể tính riêng với gói trên tensor.art. Tôi chưa xác nhận được, nên hãy xem trên trang TAMS.

## 3. Chạy máy chủ

Trên Linux hoặc macOS:

```bash
export TAMS_API_KEY="khoá-api"
export TA_TOOL_ID="mã-ai-tool"
export TAMS_BASE_URL="https://ap-east-1.tensorart.cloud"   # theo trang TAMS
export ACCESS_PASSWORD="mật-khẩu-chung-cho-nhân-viên"
python3 company_web/server.py
```

Trên Windows, tạo file `chay-upscale.bat` nằm cạnh `server.py`:

```bat
set TAMS_API_KEY=khoá-api
set TA_TOOL_ID=mã-ai-tool
set TAMS_BASE_URL=https://ap-east-1.tensorart.cloud
set ACCESS_PASSWORD=mật-khẩu-chung
python server.py
pause
```

Mở `http://<địa-chỉ-máy-chủ>:8080`. Trình duyệt sẽ hỏi tên đăng nhập và mật khẩu: tên gõ gì cũng được, mật khẩu là `ACCESS_PASSWORD`.

Các thiết lập khác:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PORT` | 8080 | Cổng web |
| `HOST` | 0.0.0.0 | Đặt `127.0.0.1` nếu chỉ cho nginx truy cập |
| `MAX_UPLOAD_MB` | 25 | Dung lượng ảnh tối đa mỗi lần tải lên |
| `TA_IMAGE_NODE_ID` | tự tìm | Mã node Load Image, chỉ cần khi máy chủ báo không tìm thấy ô ảnh |

## 4. Đưa lên web công ty

Chọn một trong ba cách:

- **Tên miền con (nên dùng):** ví dụ `upscale.congty.vn`, có HTTPS, trỏ qua nginx về máy chủ này. Thêm một mục menu trên web công ty dẫn tới đó.
- **Nhúng vào trang có sẵn:** `<iframe src="https://upscale.congty.vn" style="width:100%;height:900px;border:0"></iframe>`. Một số trình duyệt chặn hộp đăng nhập trong iframe. Nếu bị chặn, dùng link thay cho iframe.
- **Tự làm giao diện:** đội web gọi thẳng 3 API của máy chủ này:
  - `POST /api/jobs`: thân request là file ảnh, `Content-Type: image/jpeg` hoặc `image/png`. Trả về `{"jobId": "..."}`.
  - `GET /api/jobs/<jobId>`: trả về `{"status": "waiting" | "running" | "done" | "failed", ...}`.
  - `GET /api/jobs/<jobId>/image?name=<tên-file-gốc>`: tải ảnh 4K. Thêm `&view=1` để xem ngay trên trình duyệt.

Cấu hình nginx mẫu:

```nginx
server {
    server_name upscale.congty.vn;
    client_max_body_size 30m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    # listen 443 ssl; ... (chứng chỉ HTTPS, ví dụ certbot)
}
```

Chạy nền bằng systemd (Linux), file `/etc/systemd/system/bokin-upscale.service`:

```ini
[Unit]
Description=Bokin Upscale web
After=network-online.target

[Service]
WorkingDirectory=/opt/bokin/company_web
Environment=TAMS_API_KEY=khoá-api TA_TOOL_ID=mã-ai-tool HOST=127.0.0.1
Environment=TAMS_BASE_URL=https://ap-east-1.tensorart.cloud ACCESS_PASSWORD=mật-khẩu
ExecStart=/usr/bin/python3 server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Sau đó chạy `sudo systemctl enable --now bokin-upscale`.

## Lưu ý

- **Khoá API chỉ nằm trên máy chủ** (biến môi trường), không có trong trang web. Đừng gửi khoá qua chat hay đưa lên Git.
- **Luôn đặt `ACCESS_PASSWORD` và dùng HTTPS.** Mỗi ảnh tốn một lượt credit, nên đừng để trang mở cho người ngoài.
- Ảnh kết quả nằm trên TensorArt và có thể bị xoá sau một thời gian, nên tải về sớm.
- Muốn đổi thông số (denoise, model...) thì sửa workflow trên TensorArt rồi Publish lại AI Tool. Trang web không cần sửa gì, trừ khi mã AI Tool thay đổi.

## Đã kiểm tra

- `tests/test_company_web.py` (5 bài) chạy máy chủ này với một TensorArt giả lập. Giả lập trả lời đúng các API mà node chính thức [ComfyUI_TENSOR_ART](https://github.com/Tensor-Art/ComfyUI_TENSOR_ART) của TensorArt sử dụng. Các bài kiểm tra:
  - Tải ảnh lên đúng địa chỉ và header được cấp.
  - Tạo job với đúng mã AI Tool và đúng ô ảnh của node Load Image.
  - Theo dõi các trạng thái: xếp hàng (có vị trí), đang chạy, xong, lỗi.
  - Tải ảnh về với tên file tiếng Việt.
  - Mật khẩu, chặn file không phải ảnh hoặc quá lớn, chặn mã job lạ, báo thiếu cấu hình.
- Mở trang bằng Chromium, tải lên 3 ảnh của công ty: cả 3 chạy xong và tải về được, không có lỗi trang. Trên màn hình điện thoại (390 px) trang không bị tràn ngang.
- **Chưa** chạy với TensorArt thật vì cần khoá API của bạn. Lần đầu chạy thật, hãy thử 1 ảnh trước.
