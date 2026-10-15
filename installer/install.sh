#!/usr/bin/env bash
# Bokin Upscaler - installer for Linux and macOS.
#
#   bash installer/install.sh [--dir DIR] [--models sdxl|sd15|fast|flux|none] [--torch auto|cuda|cpu|skip]
#                             [--no-shortcut] [--yes]
#
# Downloads uv (a small Python manager), creates the app's Python environment
# and runs installer/setup.py. Default folder: ~/BokinUpscaler.
# Safe to run again: finished steps are skipped.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${BOKIN_HOME:-$HOME/BokinUpscaler}"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --dir=*) INSTALL_DIR="${1#--dir=}"; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) TARGET=x86_64-unknown-linux-gnu ;;
  Linux-aarch64 | Linux-arm64) TARGET=aarch64-unknown-linux-gnu ;;
  Darwin-arm64) TARGET=aarch64-apple-darwin ;;
  Darwin-x86_64) TARGET=x86_64-apple-darwin ;;
  *) echo "Hệ điều hành chưa được hỗ trợ: $(uname -s) $(uname -m)" >&2; exit 1 ;;
esac

mkdir -p "$INSTALL_DIR/tools"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"
TOOLS="$INSTALL_DIR/tools"
export UV_PYTHON_INSTALL_DIR="$TOOLS/python"
export UV_CACHE_DIR="$TOOLS/uv-cache"
export UV_PYTHON_PREFERENCE=only-managed  # never depend on a system Python
export PYTHONUTF8=1

if [ ! -x "$TOOLS/uv" ]; then
  echo "Downloading uv..."
  curl -fsSL "https://github.com/astral-sh/uv/releases/latest/download/uv-$TARGET.tar.gz" \
    | tar -xz -C "$TOOLS" --strip-components 1
fi

VENV="$INSTALL_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating the Python 3.12 environment..."
  "$TOOLS/uv" venv --python 3.12 "$VENV"
fi

exec "$VENV/bin/python" "$SRC/installer/setup.py" --dir "$INSTALL_DIR" --uv "$TOOLS/uv" ${ARGS[@]+"${ARGS[@]}"}
