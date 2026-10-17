# Bokin Upscale 4K trên web công ty

Trang web nội bộ dành cho nhân viên. Nhân viên làm 3 bước:

1. Chọn **kiểu upscale** (Klein 4K, FLUX.2 Dev 4K, FLUX.1 4K…).
2. Chỉnh **thông số** như denoise, kích thước ra, prompt.
3. Kéo thả ảnh (được chọn nhiều ảnh), chờ 1–3 phút rồi tải ảnh về.

Phía sau, mỗi kiểu upscale là một workflow đã đăng thành AI Tool trên TensorArt, ví dụ `tensorart/Bokin_Flux2_Klein_4K_Upscale_TensorArt.json`. Trang gọi API của TensorArt để chạy AI Tool đó. Nhân viên không cần tài khoản TensorArt, không thấy workflow và không thấy khoá API.

```
Trình duyệt nhân viên ──► server.py (máy chủ công ty, giữ khoá API) ──► TensorArt API ──► workflow Klein
        ◄── ảnh 4K ───────────┘
```

Gồm 3 file:

- `server.py`: máy chủ.
- `index.html`: giao diện.
- `upscalers.json`: danh sách kiểu upscale.

Chỉ cần **Python 3.9 trở lên**, không phải cài thêm thư viện.

## 1. Đăng mỗi workflow thành một AI Tool trên TensorArt

Làm lần lượt cho từng kiểu upscale muốn có trên web: Klein, FLUX.2 Dev, FLUX.1…

1. Mở workflow trên TensorArt và chạy thử một lần cho chắc.
2. Bấm **Các Nút TA** (TA Nodes) và đánh dấu những ô muốn cho nhân viên chỉnh:

   | Node | Ô | Bắt buộc? | Hiện trên web thành |
   |---|---|---|---|
   | Load Image | `image` | **Có** | Ảnh nhân viên tải lên |
   | BasicScheduler | `denoise` | nên có | Thanh trượt "Mức vẽ lại (denoise)" |
   | Scale Image to Total Pixels | `megapixels` | tuỳ chọn | Thanh trượt "Kích thước ra" |
   | CLIP Text Encode | `text` | tuỳ chọn | Ô prompt |

   Ô nào không đánh dấu thì giữ nguyên giá trị trong workflow, nhân viên không đổi được. Ô nào được đánh dấu thì tự hiện lên web, không cần sửa code.
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
export TA_TOOL_ID="mã-ai-tool-klein"             # kiểu Klein 4K
export TA_TOOL_ID_FLUX2_DEV="mã-ai-tool-flux2-dev" # bỏ trống thì kiểu này không hiện
export TA_TOOL_ID_FLUX1="mã-ai-tool-flux1"         # bỏ trống thì kiểu này không hiện
export TAMS_BASE_URL="https://ap-east-1.tensorart.cloud"   # theo trang TAMS
export ACCESS_PASSWORD="mật-khẩu-chung-cho-nhân-viên"
python3 company_web/server.py
```

Trên Windows, tạo file `chay-upscale.bat` nằm cạnh `server.py`:

```bat
set TAMS_API_KEY=khoá-api
set TA_TOOL_ID=mã-ai-tool-klein
set TA_TOOL_ID_FLUX1=mã-ai-tool-flux1
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
| `UPSCALERS_FILE` | `upscalers.json` cạnh `server.py` | Đường dẫn tới danh sách kiểu upscale |
| `TA_IMAGE_NODE_ID` | tự tìm | Mã node Load Image, chỉ cần khi máy chủ báo không tìm thấy ô ảnh |

## Thêm kiểu upscale mới

1. Đăng workflow mới thành AI Tool như ở bước 1.
2. Thêm một mục vào `upscalers.json`:

   ```json
   {
     "key": "scenery-uhd",
     "name": "Phong cảnh 3840×2160",
     "description": "Ảnh 16:9, ra đúng 4K UHD.",
     "tool_id": "mã-ai-tool-mới",
     "params": {
       "denoise": {"label": "Mức vẽ lại", "min": 0.1, "max": 0.35, "step": 0.01, "hint": "0.30 cân bằng"},
       "steps": {"hidden": true}
     }
   }
   ```

   - `tool_id`: ghi thẳng mã AI Tool, hoặc dạng `${TEN_BIEN}` để lấy từ biến môi trường. Biến trống thì kiểu đó bị ẩn.
   - `params`: không bắt buộc. Mỗi ô đã đánh dấu TA Node tự hiện trên web. `params` chỉ dùng để đặt nhãn tiếng Việt và giới hạn cho đẹp:
     - `label`: nhãn hiện trên web.
     - `min`, `max`, `step`: giới hạn thanh trượt. Giá trị ngoài khoảng sẽ bị kéo về trong khoảng, kể cả khi ai đó gửi thẳng lên máy chủ.
     - `default`: giá trị mặc định.
     - `hint`: dòng gợi ý dưới ô.
     - `hidden: true`: giấu ô đó, giữ giá trị trong workflow.
     - `type` (`number`, `select`, `text`) và `options`: chọn kiểu ô.
   - Ô được gọi theo tên field (`denoise`, `megapixels`, `text`…). Nếu workflow có hai field trùng tên, dùng dạng `"<nodeId>.<fieldName>"`, ví dụ `"12.denoise"`.
3. Khởi động lại `server.py`. Kiểu mới hiện trên web.

Máy chủ đọc danh sách ô của mỗi AI Tool từ TensorArt và nhớ trong 10 phút. Đánh dấu thêm ô trên TensorArt thì sau tối đa 10 phút, hoặc ngay sau khi khởi động lại, ô mới hiện trên web.

## 4. Đưa lên web công ty

Chọn một trong ba cách:

- **Tên miền con (nên dùng):** ví dụ `upscale.congty.vn`, có HTTPS, trỏ qua nginx về máy chủ này. Thêm một mục menu trên web công ty dẫn tới đó.
- **Nhúng vào trang có sẵn:** `<iframe src="https://upscale.congty.vn" style="width:100%;height:900px;border:0"></iframe>`. Một số trình duyệt chặn hộp đăng nhập trong iframe. Nếu bị chặn, dùng link thay cho iframe.
- **Tự làm giao diện:** đội web gọi thẳng 4 API của máy chủ này:
  - `GET /api/upscalers`: danh sách kiểu upscale và các thông số chỉnh được (nhãn, kiểu, min/max/step, mặc định).
  - `POST /api/jobs?type=<key>&params=<JSON>`: thân request là file ảnh, `Content-Type: image/jpeg` hoặc `image/png`. `params` có dạng `{"denoise":0.15}`; thông số nào bỏ trống thì dùng mặc định. Trả về `{"jobId": "..."}`.
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
- Muốn đổi những gì nhân viên không chỉnh được (model, sampler…) thì sửa workflow trên TensorArt rồi Publish lại AI Tool. Nếu mã AI Tool đổi, cập nhật `tool_id`.
- Trình duyệt nhớ kiểu và thông số mỗi nhân viên chọn lần trước. Bấm "Đặt lại mặc định" để quay về giá trị trong `upscalers.json`.

## Đã kiểm tra

- `tests/test_company_web.py` (8 bài) chạy máy chủ này với một TensorArt giả lập. Giả lập trả lời đúng các API mà node chính thức [ComfyUI_TENSOR_ART](https://github.com/Tensor-Art/ComfyUI_TENSOR_ART) của TensorArt sử dụng. Các bài kiểm tra:
  - Liệt kê kiểu upscale và thông số: nhãn và giới hạn từ `upscalers.json`, ô bị giấu, ô chọn lấy lựa chọn từ TensorArt, AI Tool thiếu ô ảnh báo lỗi rõ ràng, kiểu chưa có mã thì ẩn.
  - Gửi đúng giá trị thông số: mặc định, kéo về trong khoảng, số nguyên và số thập phân. Chặn lựa chọn sai, chữ thay cho số, JSON hỏng, kiểu không tồn tại, và không tải ảnh lên khi request bị chặn.
  - Tải ảnh lên đúng địa chỉ và header được cấp.
  - Tạo job với đúng mã AI Tool, đúng ô ảnh và đúng các thông số.
  - Theo dõi các trạng thái: xếp hàng (có vị trí), đang chạy, xong, lỗi.
  - Tải ảnh về với tên file tiếng Việt.
  - Mật khẩu, chặn file không phải ảnh hoặc quá lớn, chặn mã job lạ, báo thiếu cấu hình.
- Mở trang bằng Chromium:
  - Chọn Klein, chỉnh denoise 0.15, tải 2 ảnh lên. Rồi đổi sang FLUX.1, chỉnh denoise 0.3, tải thêm 1 ảnh.
  - TensorArt giả lập nhận đúng mã AI Tool và đúng denoise cho từng ảnh. Cả 3 ảnh chạy xong và tải về được, không có lỗi trang.
  - Trên màn hình điện thoại (390 px) trang không bị tràn ngang.
- **Chưa** chạy với TensorArt thật vì cần khoá API của bạn. Lần đầu chạy thật, hãy thử 1 ảnh trước.
