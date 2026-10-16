# Workflow cho TensorArt – Bokin Photoreal Upscale (Flux)

File `Bokin_Flux_Photoreal_Upscale_TensorArt.json` làm cùng việc với Bokin Upscale: phóng to ảnh lên khoảng **4K** rồi vẽ lại chi tiết để ảnh **giống ảnh chụp thật**. Khác với app Bokin, workflow này chỉ dùng các node TensorArt có sẵn: node chuẩn của ComfyUI và 3 node của **Comfyui_TTP_Toolset**. Vì vậy nó import được lên TensorArt.

## Cách dùng trên TensorArt

1. Mở trình tạo workflow của TensorArt, kéo thả file `.json` vào (hoặc dùng chức năng import).
2. Nếu ô nào báo **không tìm thấy model**, bấm vào ô đó và chọn bản tương ứng trong danh sách của TensorArt:

   | Ô | Chọn |
   |---|---|
   | Load Diffusion Model | **FLUX.1 dev** (không chọn `flux2_*`) |
   | Load CLIP (Dual) | `clip_l` + `t5xxl_fp8_e4m3fn`, type `flux` |
   | Load VAE | `ae.safetensors` |
   | Load Upscale Model | `4x_RealisticRescaler` (hoặc `4x_NMKD-Siax`, `4x-UltraSharp`) |

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

## Chỉnh nhanh

- **Mức sáng tạo** (`BasicScheduler → denoise`): 0.25 giữ sát ảnh gốc, 0.30 cân bằng, 0.35 thêm nhiều chi tiết nhưng dễ sinh chi tiết lạ.
- **Kích thước ra** (`Scale to 4K → megapixels`): 8 ≈ 4K, 4 ≈ 2.7K, 16 ≈ 5.6K. Mức 16 tốn gấp đôi.
- **Tiết kiệm credit:** giảm `steps` từ 20 xuống 12. Mặc định 20 steps nên tốn khoảng gấp đôi workflow cũ (10 steps).
- **Ảnh chân dung cận mặt:** đặt `width_factor` và `height_factor` = 2 để ô to hơn, không cắt ngang khuôn mặt.
- **Nếu TensorArt có LoRA realism cho FLUX.1:** chèn `LoraLoaderModelOnly` ngay sau Load Diffusion Model.

## Đã kiểm tra

- Mở trong ComfyUI v0.40.0 có cài Comfyui_TTP_Toolset: đủ 25 node, không thiếu node nào, xuất ra prompt hợp lệ.
- Chạy thử toàn bộ đường xử lý, gồm phóng to, chia 9 ô, vẽ lại từng ô, gom và ghép. Lần chạy này thay model FLUX.1 bằng model SD1.5 trọng số ngẫu nhiên, vì máy test không có FLUX.1. Ảnh ra đúng kích thước.
- **Chưa** chạy trên TensorArt và chưa chạy với FLUX.1 thật. Tên file model trên TensorArt có thể khác, khi đó chọn lại theo bảng trên.
