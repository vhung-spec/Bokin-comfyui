#!/usr/bin/env bash
# Tải các model mà workflow Bokin dùng vào thư mục ComfyUI.
#
#   bash scripts/download_models.sh <thư mục ComfyUI> [fast|sd15|sdxl|flux|all ...]
#
# Ví dụ:  bash scripts/download_models.sh ~/ComfyUI sdxl
# Repo HuggingFace cần đăng nhập (gated): đặt biến HF_TOKEN trước khi chạy.
# File đã tải xong sẽ được bỏ qua; file tải dở sẽ được tải tiếp.
set -euo pipefail

if [ $# -lt 1 ]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

COMFY="$1"
shift
PRESETS=("${@:-fast}")
MODELS="$COMFY/models"
[ -d "$MODELS" ] || { echo "Không thấy $MODELS - kiểm tra lại đường dẫn ComfyUI." >&2; exit 1; }

HF=https://huggingface.co
GH=https://github.com/xinntao/Real-ESRGAN/releases/download
FAILED=()

fetch() { # <thư mục con> <tên file> <url>
  local dir="$MODELS/$1" file="$2" url="$3"
  mkdir -p "$dir"
  if [ -f "$dir/$file" ] && [ ! -f "$dir/$file.part" ]; then
    echo "✓ đã có  $1/$file"
    return
  fi
  echo "↓ tải    $1/$file"
  local auth=()
  if [ -n "${HF_TOKEN:-}" ] && [[ "$url" == "$HF"/* ]]; then
    auth=(-H "Authorization: Bearer $HF_TOKEN")
  fi
  if curl -fL --retry 3 -C - ${auth[@]+"${auth[@]}"} -o "$dir/$file.part" "$url"; then
    mv "$dir/$file.part" "$dir/$file"
  else
    echo "✗ lỗi khi tải $url" >&2
    FAILED+=("$1/$file  <-  $url")
  fi
}

upscalers() {
  fetch upscale_models 4x-UltraSharp.pth "$HF/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth"
  fetch upscale_models RealESRGAN_x4plus.pth "$GH/v0.1.0/RealESRGAN_x4plus.pth"
  fetch upscale_models RealESRGAN_x4plus_anime_6B.pth "$GH/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
}

sd15() {
  fetch checkpoints v1-5-pruned-emaonly-fp16.safetensors \
    "$HF/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors"
  fetch controlnet control_v11f1e_sd15_tile_fp16.safetensors \
    "$HF/comfyanonymous/ControlNet-v1-1_fp16_safetensors/resolve/main/control_v11f1e_sd15_tile_fp16.safetensors"
}

sdxl() {
  fetch checkpoints sd_xl_base_1.0.safetensors \
    "$HF/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
  fetch controlnet xinsir-controlnet-tile-sdxl-1.0.safetensors \
    "$HF/xinsir/controlnet-tile-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors"
}

flux() {
  # ~17 GB, giấy phép non-commercial của Black Forest Labs.
  fetch checkpoints flux1-dev-fp8.safetensors "$HF/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors"
}

for preset in "${PRESETS[@]}"; do
  case "$preset" in
    fast) upscalers ;;
    sd15) upscalers; sd15 ;;
    sdxl) upscalers; sdxl ;;
    flux) upscalers; flux ;;
    all) upscalers; sd15; sdxl; flux ;;
    *) echo "Preset không hợp lệ: $preset (chọn fast, sd15, sdxl, flux, all)" >&2; exit 1 ;;
  esac
done
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Không tải được (hãy tải thủ công vào thư mục models tương ứng):" >&2
  printf '  %s\n' "${FAILED[@]}" >&2
  exit 1
fi
echo "Xong. Khởi động lại ComfyUI (hoặc bấm R) để thấy model mới."
