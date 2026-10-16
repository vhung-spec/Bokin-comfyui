# Bokin ComfyUI – Upscale ảnh kiểu Shakker

Bộ node ComfyUI riêng để **phóng to ảnh và thêm chi tiết** giống tính năng Upscale / Hi-Res của Shakker.
Bộ này dùng lại các model có sẵn trên thị trường: 4x-UltraSharp, RealESRGAN, SD1.5, SDXL, Flux và ControlNet Tile.

## Cách hoạt động

```
Ảnh gốc ──► ① Phóng to bằng model ──► ② Vẽ lại chi tiết từng ô ──► ③ Sửa màu ──► Ảnh kết quả
             (4x-UltraSharp,           (SD1.5 / SDXL / Flux,          (wavelet:
              RealESRGAN...)            img2img denoise thấp,          giữ màu gốc,
                                        + ControlNet Tile tùy chọn)    giữ chi tiết mới)
```

1. **Phóng to bằng model** ESRGAN để có đúng kích thước mong muốn (vd. 2x). Ảnh lúc này to nhưng vẫn "bệt".
2. **Vẽ lại chi tiết**: ảnh được chia thành các ô (tile) 1024px. Mỗi ô được chạy img2img ở mức denoise thấp nên model diffusion thêm được kết cấu thật (da, tóc, vải, lá...). Các ô chồng lên nhau và được trộn mềm ở mép, nên không lộ đường nối. Mọi ô dùng chung một bản đồ nhiễu nên vùng chồng lấn khớp nhau.
3. **Sửa màu**: lấy màu và độ sáng tổng thể từ ảnh phóng to ở bước 1, giữ phần chi tiết mới. Ảnh không bị ám màu hay lệch màu giữa các ô.

## Cách 1 – App Bokin Upscaler (dễ nhất, không cần biết ComfyUI)

App gồm ComfyUI, bộ node Bokin và một giao diện riêng giống Shakker:
- kéo thả ảnh, chọn 1.5x / 2x / 3x / 4x và chế độ (Nhanh / Giữ nguyên / Cân bằng / Sáng tạo)
- thanh tiến trình kèm xem trước từng ô đang vẽ
- thanh trượt so sánh trước / sau, nút tải ảnh về

Bộ cài tự lo mọi thứ (Python, PyTorch, ComfyUI, model) trong một thư mục riêng, không cần quyền quản trị, không đụng tới Python có sẵn trên máy.

**Yêu cầu:** Internet, 5–25 GB ổ đĩa trống (tùy bộ model). Nên có GPU NVIDIA; không có GPU thì chỉ nên dùng chế độ Nhanh.

### Windows – cài bằng một dòng lệnh (khuyên dùng)

1. Bấm **Start**, gõ `PowerShell`, mở **Windows PowerShell** (không cần quyền Admin).
2. Dán lệnh sau rồi bấm Enter:

   ```powershell
   irm https://raw.githubusercontent.com/vhung-spec/Bokin-comfyui/claude/fervent-heisenberg-17b0js/installer/windows/web-install.ps1 | iex
   ```

3. Chọn bộ model khi được hỏi (SDXL khuyên dùng với GPU 8 GB+). Việc tải mất 10–40 phút tùy mạng.
4. Mở app bằng shortcut **Bokin Upscaler** trên Desktop.

Cách này không tải file qua trình duyệt nên Chrome không chặn. Chạy lại lệnh để cập nhật.
Gỡ cài đặt: xóa thư mục `%LOCALAPPDATA%\BokinUpscaler` và shortcut trên Desktop.

### Windows – file cài đặt .exe

1. Tải `BokinUpscaler-Setup.exe`: vào tab **Actions → Bokin app** của repo, mở lần chạy mới nhất, mục *Artifacts*.
   Chrome có thể chặn tải với lý do "tệp nguy hiểm", vì file chưa ký số và còn mới. Khi đó hãy dùng cách một dòng lệnh ở trên.
2. Chạy file. Nếu Windows SmartScreen cảnh báo, bấm **More info → Run anyway**.
3. Chọn bộ model rồi bấm Install. Một cửa sổ PowerShell sẽ hiện tiến độ tải.
4. Mở app bằng shortcut **Bokin Upscaler** trên Desktop.

Gỡ cài đặt: **Settings → Apps → Bokin Upscaler → Uninstall**.

Cách khác: tải mã nguồn (Code → Download ZIP), giải nén rồi chạy `installer\windows\Install-Bokin.bat`.

### Linux / macOS

```bash
git clone https://github.com/vhung-spec/Bokin-comfyui.git
bash Bokin-comfyui/installer/install.sh            # cài vào ~/BokinUpscaler
```

Mở app bằng shortcut, hoặc chạy `~/BokinUpscaler/bokin-upscaler.sh` (macOS: `Bokin Upscaler.command`).

### Dùng app

- Khi mở app, một cửa sổ console sẽ chạy ComfyUI ở chế độ nền. Giữ cửa sổ này mở trong lúc dùng app; đóng nó là tắt app.
- Ảnh kết quả được lưu tự động vào thư mục **Pictures/Bokin Upscaler**.
- Muốn dùng checkpoint khác: chép file `.safetensors` vào `ComfyUI/models/checkpoints` trong thư mục cài
  (Windows: `%LOCALAPPDATA%\BokinUpscaler`, Linux/macOS: `~/BokinUpscaler`) rồi mở lại app.
- Nút **Mở ComfyUI** trên app mở giao diện ComfyUI đầy đủ, kèm các workflow mẫu bên dưới.

## Cách 2 – Cài vào ComfyUI có sẵn

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/vhung-spec/Bokin-comfyui.git
```

Khởi động lại ComfyUI. Bộ node không cần cài thêm thư viện Python nào ngoài những gì ComfyUI đã có.
Nên dùng bản ComfyUI mới (2025 trở lên).
Giao diện app có sẵn tại `http://127.0.0.1:8188/bokin`.

### Tải model

Dùng script có sẵn (Windows / Linux / macOS, chỉ cần Python):

```bash
python custom_nodes/Bokin-comfyui/scripts/download_models.py /đường/dẫn/ComfyUI sdxl
#   preset: fast | sd15 | sdxl | flux | all   (có thể ghi nhiều preset)
```

Hoặc tải thủ công và đặt vào đúng thư mục:

| Thư mục `ComfyUI/models/...` | File | Nguồn |
|---|---|---|
| `upscale_models` | `4x-UltraSharp.pth` (ảnh thật, đa dụng) | [lokCX/4x-Ultrasharp](https://huggingface.co/lokCX/4x-Ultrasharp) |
| `upscale_models` | `RealESRGAN_x4plus.pth` | [Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases) |
| `upscale_models` | `RealESRGAN_x4plus_anime_6B.pth` (anime) | [Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases) |
| `controlnet` | `xinsir-controlnet-tile-sdxl-1.0.safetensors` | [xinsir/controlnet-tile-sdxl-1.0](https://huggingface.co/xinsir/controlnet-tile-sdxl-1.0) (đổi tên từ `diffusion_pytorch_model.safetensors`) |
| `controlnet` | `control_v11f1e_sd15_tile_fp16.safetensors` | [comfyanonymous/ControlNet-v1-1_fp16_safetensors](https://huggingface.co/comfyanonymous/ControlNet-v1-1_fp16_safetensors) |
| `checkpoints` | `sd_xl_base_1.0.safetensors` | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) |
| `checkpoints` | `v1-5-pruned-emaonly-fp16.safetensors` | [Comfy-Org/stable-diffusion-v1-5-archive](https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive) |
| `checkpoints` | `flux1-dev-fp8.safetensors` (~17 GB) | [Comfy-Org/flux1-dev](https://huggingface.co/Comfy-Org/flux1-dev) |

Checkpoint gốc chỉ là mặc định. Kết quả sẽ đẹp hơn nhiều nếu bạn dùng checkpoint đã fine-tune tải từ Civitai hoặc Shakker:

- Ảnh thật: Juggernaut XL, RealVisXL (SDXL); Realistic Vision (SD1.5)
- Anime: Illustrious, NoobAI (SDXL)

Chỉ cần chọn checkpoint đó trong node **Load Checkpoint**.

## Workflow mẫu

Kéo thả file trong thư mục [`example_workflows/`](example_workflows) vào ComfyUI. Bạn cũng có thể mở chúng từ **Templates → Custom nodes → Bokin-comfyui**.

| Workflow | Dùng khi | VRAM gợi ý |
|---|---|---|
| `Bokin_Upscale_Fast.json` | Chỉ phóng to nhanh bằng model, không vẽ lại | 2 GB+ |
| `Bokin_Upscale_SD15.json` | Máy yếu, ảnh SD1.5 | 4–6 GB |
| `Bokin_Upscale_SDXL.json` | **Khuyên dùng** – SDXL + ControlNet Tile, giống Shakker nhất | 8 GB+ |
| `Bokin_Upscale_Flux.json` | Chi tiết chân thực nhất, chậm nhất | 12 GB+ (fp8) |

Cách dùng: chọn ảnh ở **Load Image**, chỉnh `upscale_by` và `mode` rồi bấm **Run**.
Ô **Save Image** là kết quả. Ô **Before** là ảnh chỉ phóng to bằng model, để so sánh trước/sau.

## Workflow cho TensorArt

TensorArt không cho cài node riêng, nên không chạy được bộ node Bokin. Thư mục [`tensorart/`](tensorart) có sẵn 3 workflow Flux: phóng to kiểu ảnh chụp (ra ~4K, hoặc đúng 4x), và bản cho ảnh phong cảnh 16:9 (ra đúng 3840×2160), chỉ dùng các node TensorArt có (node chuẩn của ComfyUI và Comfyui_TTP_Toolset), kèm hướng dẫn chọn model và chỉnh thông số.

## Các node

### Bokin Upscale (Shakker-style)

Node chính, làm cả 3 bước trên.

| Tham số | Ý nghĩa |
|---|---|
| `upscale_by` | Hệ số phóng to: 1.5 / 2 / 3 / 4… Để **1.0** nếu chỉ muốn làm nét và thêm chi tiết mà không đổi kích thước. |
| `mode` | Mức "sáng tạo" (denoise), xem bảng dưới. |
| `seed`, `steps`, `cfg`, `sampler_name`, `scheduler` | Giống KSampler. Chỉnh theo checkpoint đang dùng. |
| `denoise` | Chỉ dùng khi `mode = Custom`. 0 = không vẽ lại. |
| `tile_size` | Kích thước ô: **1024** cho SDXL/Flux, **512–768** cho SD1.5. Giảm nếu thiếu VRAM. |
| `tile_overlap` | Phần chồng giữa các ô (mặc định 128). Tăng lên nếu thấy đường nối. |
| `passes` | Chia việc phóng to thành nhiều lần, vd. 4x với `passes = 2` là hai lần x2, mỗi lần đều vẽ lại. Đẹp hơn với hệ số lớn nhưng chậm hơn. |
| `color_fix` | `wavelet` (khuyên dùng), `adain`, hoặc `none`. |
| `upscale_model` *(tùy chọn)* | Model ESRGAN. Bỏ trống thì phóng to bằng bicubic. |
| `control_net` *(tùy chọn)* | ControlNet Tile: giữ bố cục nên dùng được denoise cao hơn. |
| `controlnet_strength`, `controlnet_end` | Độ mạnh và thời điểm kết thúc ControlNet (gợi ý 0.5–0.8 và 0.8–1.0). |

Bảng `mode`, tương ứng mức Creativity của Shakker:

| Mode | Denoise khi không có ControlNet | Denoise khi có ControlNet Tile | Khi nào dùng |
|---|---|---|---|
| Faithful | 0.20 | 0.35 | Ảnh chân dung, sản phẩm, logo: giữ sát bản gốc |
| **Balanced** | 0.30 | 0.50 | Mặc định, hợp với đa số ảnh |
| Creative | 0.45 | 0.70 | Ảnh mờ hoặc nhỏ cần "tái tạo" nhiều chi tiết |
| Custom | `denoise` | `denoise` | Tự chỉnh |

Kết quả trả về:

- `image`: ảnh kết quả
- `base_upscale`: ảnh chỉ phóng to bằng model

### Bokin Upscale Fast (model only)

Phóng to bằng model ESRGAN tới **đúng** hệ số `upscale_by`, ví dụ dùng model 4x nhưng ra ảnh 2x. Node này không cần checkpoint.

### Bokin Color Match

Đưa màu của một ảnh về giống ảnh tham chiếu mà vẫn giữ chi tiết (`wavelet` / `adain`, có `strength`).
Hữu ích khi ghép với các workflow khác.

## Thiết lập gợi ý

| Checkpoint | steps | cfg | sampler / scheduler |
|---|---|---|---|
| SDXL thường | 20–30 | 5–7 | dpmpp_2m / karras |
| SDXL Lightning / Hyper / Turbo | 6–8 | 1.5–2 | dpmpp_sde hoặc euler / karras hoặc sgm_uniform |
| SD1.5 | 20–30 | 6–8 | dpmpp_2m / karras |
| Flux.1 dev | 20 | **1.0** (dùng FluxGuidance 2.5–3.5) | euler / simple |

Mẹo:

- **Prompt**: mô tả ngắn nội dung ảnh, vd. "portrait of a woman, freckles, soft light", rồi thêm từ khóa chất lượng. Kết quả sẽ tốt hơn prompt chung chung.
- **Xuất hiện mặt hoặc vật thể lạ trong ảnh**: denoise quá cao. Hạ `mode` xuống, hoặc nối thêm ControlNet Tile.
- **Ảnh chưa đủ nét**: tăng `mode`, hoặc dùng `passes = 2` khi phóng ≥ 3x.
- **Lỗi hết VRAM**: giảm `tile_size` (1024 → 768), dùng checkpoint fp16/fp8.
- **Lộ đường nối giữa các ô**: tăng `tile_overlap` (192–256) và giữ `color_fix = wavelet`.

## Phát triển

Logic chia ô, trộn mép và sửa màu nằm trong `bokin/tiling.py`, `bokin/color.py` và `bokin/presets.py`.
Các file này chỉ phụ thuộc PyTorch, nên test được mà không cần ComfyUI:

```bash
pip install torch pytest
pytest tests
```

Node ComfyUI nằm trong `bokin/nodes_upscale.py`. Trang app nằm ở `web_app/index.html`, được phục vụ tại `/bokin` bởi `bokin/app_routes.py`.

Bộ cài nằm trong `installer/`:

| File | Vai trò |
|---|---|
| `setup.py` | Phần cài đặt chung cho mọi hệ điều hành: ComfyUI, PyTorch, node pack, model, shortcut |
| `windows/setup.ps1`, `windows/Install-Bokin.bat` | Khởi động bộ cài trên Windows (tải uv + Python) |
| `windows/web-install.ps1` | Cài bằng một dòng lệnh `irm … \| iex`: tải mã nguồn rồi chạy `setup.ps1` |
| `install.sh` | Khởi động bộ cài trên Linux / macOS |
| `windows/bokin.iss` | Script Inno Setup để build `BokinUpscaler-Setup.exe` |
| `bokin_launcher.py` | Chạy ComfyUI chạy nền và mở cửa sổ app |
| `smoke_test.py` | Kiểm tra bản đã cài: mở app, upscale thử một ảnh |

Workflow `.github/workflows/app.yml` chạy unit test, cài thử app trên Linux và Windows, rồi build file `.exe`. Khi push một tag `v*`, workflow tạo GitHub Release kèm file cài.
