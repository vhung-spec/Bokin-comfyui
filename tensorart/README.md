# Workflow cho TensorArt – Bokin Photoreal Upscale (Flux)

Hai workflow phóng to ảnh rồi vẽ lại chi tiết để ảnh **giống ảnh chụp thật**:

| File | Kích thước ra | Dùng khi |
|---|---|---|
| `Bokin_Flux_Photoreal_Upscale_TensorArt.json` | luôn khoảng **4K (8 MP)**, ảnh gốc to hay nhỏ đều vậy | Muốn chi phí ổn định, ảnh gốc to cỡ nào cũng được |
| `Bokin_Flux_Photoreal_Upscale_4x_TensorArt.json` | **đúng gấp 4** chiều rộng và chiều cao ảnh gốc | Ảnh gốc nhỏ (đến khoảng 1600px), muốn phóng 4x như nút 4x của Shakker |

Khác với app Bokin, hai workflow này chỉ dùng node TensorArt có sẵn: node chuẩn của ComfyUI và 3 node của **Comfyui_TTP_Toolset**. Vì vậy chúng import được lên TensorArt.

## Cách dùng trên TensorArt

1. Mở trình tạo workflow của TensorArt, kéo thả một trong hai file `.json` vào (hoặc dùng chức năng import).
2. Nếu ô nào báo **không tìm thấy model**, bấm vào ô đó và chọn bản tương ứng trong danh sách của TensorArt:

   | Ô | Chọn |
   |---|---|
   | Load Diffusion Model | **`flux1-dev.sft`** (mặc định), hoặc `flux1-dev-fp8.safetensors`. Muốn ảnh thật hơn nữa: `flux1-krea-dev.safetensors` và tăng **FluxGuidance lên 3.5** |
   | Load CLIP (Dual) | `clip_l` + `t5xxl_fp8_e4m3fn`, type `flux` |
   | Load VAE | `ae.safetensors` |
   | Load Upscale Model | `4x_RealisticRescaler` (hoặc `4x_NMKD-Siax`, `4x-UltraSharp`) |

   Lỗi `Invalid input value: field unet_name value must in: [...]` nghĩa là TensorArt không có file mang tên đó. Chọn một tên trong danh sách theo bảng trên. Các ô model khác cũng xử lý tương tự.

   Bốn ô model phải cùng thuộc **FLUX.1**. Dùng FLUX.2 với `clip_l`/`t5xxl`/`ae` chính là lý do workflow "4k-upscale" cũ báo lỗi "Model/system issue".
3. Chọn ảnh ở **Load Image**. Thêm một câu mô tả ảnh vào **đầu** prompt, ví dụ `portrait of an old fisherman, `. Có mô tả thì ảnh ra thật hơn rõ rệt.
4. Bấm **Run**. Muốn dùng như một app thì đánh dấu TA Nodes cho Load Image, prompt, denoise và megapixels, rồi Publish.

## Vì sao chọn các thiết lập này

| Thiết lập | Giá trị | Lý do |
|---|---|---|
| Model vẽ lại | FLUX.1 dev | Model mở cho chi tiết ảnh chụp tốt nhất hiện nay |
| FluxGuidance | **2.2** | Mức mặc định 3.5 hay làm da "nhựa", kiểu ảnh AI. Mức 2–2.5 cho kết cấu tự nhiên hơn |
| Sampler / scheduler | euler / beta, 20 steps | Ổn định khi vẽ lại ảnh có sẵn (img2img) với Flux |
| Denoise | **0.30** | Đủ để thêm lỗ chân lông, sợi tóc, vân vải mà vẫn giữ bố cục |
| Model phóng to | 4x_RealisticRescaler | Được huấn luyện cho kết cấu ảnh thật, xử lý được ảnh nén JPEG |
| Chia ô | 3×3, chồng mép 10%, trộn mép 128px | Mỗi ô khoảng 1 MP, đúng độ phân giải Flux làm tốt nhất, không lộ đường nối |
| Vẽ lại từng ô một | RebatchLatents = 1 | Không dồn 9 ô vào GPU cùng lúc, tránh lỗi thiếu VRAM |
| Chuẩn hoá ảnh gốc | ~1.5 MP | Chi phí và thời gian ổn định, ảnh rất lớn không làm nổ bộ nhớ |

## Bản 4x: chọn số ô theo ảnh gốc

Ở node `TTP_Tile_image_size`, đặt `width_factor` = chiều rộng ảnh gốc ÷ 256 và `height_factor` = chiều cao ÷ 256 (làm tròn). Như vậy mỗi ô khoảng 1 MP, đúng độ phân giải Flux làm tốt nhất.

| Cạnh ảnh gốc | 512px | 768px | 1024px (mặc định) | 1280px | 1536px |
|---|---|---|---|---|---|
| factor | 2 | 3 | 4 | 5 | 6 |

Ví dụ ảnh 1080×1350 thì đặt `width_factor` 4 và `height_factor` 5. Ảnh 1024px phóng 4x ra 4096px (16 MP), tốn khoảng gấp đôi bản 4K. Ảnh gốc trên khoảng 1600px nên dùng bản 4K.

## Chỉnh nhanh

- **Mức sáng tạo** (`BasicScheduler → denoise`): 0.25 giữ sát ảnh gốc, 0.30 cân bằng, 0.35 thêm nhiều chi tiết nhưng dễ sinh chi tiết lạ.
- **Kích thước ra** (`Scale to 4K → megapixels`): 8 ≈ 4K, 4 ≈ 2.7K, 16 ≈ 5.6K. Mức 16 tốn gấp đôi.
- **Tiết kiệm credit:** giảm `steps` từ 20 xuống 12. Mặc định 20 steps nên tốn khoảng gấp đôi workflow cũ (10 steps).
- **Ảnh chân dung cận mặt:** đặt `width_factor` và `height_factor` = 2 để ô to hơn, không cắt ngang khuôn mặt.
- **Nếu TensorArt có LoRA realism cho FLUX.1:** chèn `LoraLoaderModelOnly` ngay sau Load Diffusion Model.

## Đã kiểm tra

- Mở trong ComfyUI v0.40.0 có cài Comfyui_TTP_Toolset: bản 4K có 25 node, bản 4x có 23 node, không thiếu node nào, đều xuất ra prompt hợp lệ.
- Chạy thử toàn bộ đường xử lý, thay model FLUX.1 bằng model SD1.5 trọng số ngẫu nhiên vì máy test không có FLUX.1:
  - Bản 4K: chia 9 ô, ảnh ra đúng kích thước.
  - Bản 4x: ảnh 256×256 cho ra đúng 1024×1024, 16 ô được vẽ lại lần lượt rồi ghép.
- **Chưa** chạy trên TensorArt và chưa chạy với FLUX.1 thật. Tên file model trên TensorArt có thể khác, khi đó chọn lại theo bảng trên.
