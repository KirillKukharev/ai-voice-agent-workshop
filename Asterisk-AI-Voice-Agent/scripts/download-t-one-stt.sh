#!/usr/bin/env bash
# Download T-one Russian STT weights into models/stt/t-one/ (matches Admin UI catalog).
# After run: open Admin UI → System → Models and refresh (F5). No DB/registry update needed.
#
# Usage:
#   ./scripts/download-t-one-stt.sh              # model.onnx only
#   ./scripts/download-t-one-stt.sh --with-kenlm # + kenlm.bin (beam_search)
#   ./scripts/download-t-one-stt.sh -y           # non-interactive
#
# If curl gets a Git LFS pointer instead of the real file, install huggingface_hub and run:
#   pip install huggingface_hub
#   huggingface-cli download t-tech/T-one --local-dir ./models/stt/t-one
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
OUT_DIR="${ROOT_DIR}/models/stt/t-one"
ASSUME_YES=0
WITH_KENLM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-kenlm) WITH_KENLM=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' is required" >&2; exit 1; }
}

need_cmd curl

file_size() {
  if stat -c%s "$1" >/dev/null 2>&1; then stat -c%s "$1"
  else stat -f%z "$1"
  fi
}

is_lfs_pointer() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local sz
  sz="$(file_size "$f")"
  # Real model.onnx is hundreds of MB; LFS stub is a tiny text file
  if [[ "$sz" -gt 1048576 ]]; then return 1; fi
  head -c 160 "$f" | grep -q "version https://git-lfs.github.com/spec/v1"
}

download_one() {
  local url="$1"
  local dest="$2"
  local label="$3"
  echo "⬇️  ${label}"
  echo "    ${url}"
  tmp="${dest}.part.$$"
  rm -f "$tmp"
  if ! curl -fL --connect-timeout 30 --retry 3 --retry-delay 2 -o "$tmp" "$url"; then
    rm -f "$tmp"
    return 1
  fi
  if is_lfs_pointer "$tmp"; then
    echo "    ⚠️  Received Git LFS pointer, not binary. Trying another source or use huggingface-cli." >&2
    rm -f "$tmp"
    return 1
  fi
  mv -f "$tmp" "$dest"
  echo "    ✅ $(basename "$dest") ($(file_size "$dest") bytes)"
  return 0
}

try_urls() {
  local primary="$1"
  local mirror="$2"
  local dest="$3"
  local label="$4"
  if download_one "$primary" "$dest" "$label"; then return 0; fi
  if [[ -n "$mirror" ]] && download_one "$mirror" "$dest" "$label"; then return 0; fi
  return 1
}

MODEL_URL_HF="https://huggingface.co/t-tech/T-one/resolve/main/model.onnx"
MODEL_URL_MIRROR="https://hf-mirror.com/t-tech/T-one/resolve/main/model.onnx"
KENLM_URL_HF="https://huggingface.co/t-tech/T-one/resolve/main/kenlm.bin"
KENLM_URL_MIRROR="https://hf-mirror.com/t-tech/T-one/resolve/main/kenlm.bin"

mkdir -p "$OUT_DIR"

if [[ "$ASSUME_YES" -eq 0 ]]; then
  echo "Target directory: ${OUT_DIR}"
  read -r -p "Continue? [y/N]: " ans || true
  case "$ans" in y|Y|yes|YES) ;; *) echo "Aborted."; exit 1;; esac
fi

if try_urls "$MODEL_URL_HF" "$MODEL_URL_MIRROR" "${OUT_DIR}/model.onnx" "model.onnx"; then
  :
else
  echo ""
  echo "❌ Could not download model.onnx. Try:"
  echo "   pip install huggingface_hub"
  echo "   huggingface-cli download t-tech/T-one --local-dir ${OUT_DIR}"
  exit 1
fi

if [[ "$WITH_KENLM" -eq 1 ]]; then
  if ! try_urls "$KENLM_URL_HF" "$KENLM_URL_MIRROR" "${OUT_DIR}/kenlm.bin" "kenlm.bin"; then
    echo "⚠️  kenlm.bin download failed (optional for greedy decoder)." >&2
  fi
fi

echo ""
echo "Done. Set in .env (or YAML):"
echo "  TONE_MODEL_PATH=${OUT_DIR}"
echo "  LOCAL_STT_BACKEND=tone"
if [[ "$WITH_KENLM" -eq 1 ]] && [[ -f "${OUT_DIR}/kenlm.bin" ]]; then
  echo "  TONE_DECODER_TYPE=beam_search"
  echo "  TONE_KENLM_PATH=${OUT_DIR}/kenlm.bin"
fi
echo ""
echo "Admin UI: open System → Models and refresh the page — the scanner reads models/stt/ on each load."
echo "Docker: ensure ./models is mounted on local_ai_server (see docker-compose.yml)."
