#!/usr/bin/env bash
set -e

# Ensure Vosk RU model exists and align canonical dir used by app
CANON_DIR="/opt/app/backend/models/vosk-model-ru-0.22"
SMALL_DIR="/opt/app/backend/models/vosk-model-small-ru-0.22"

mkdir -p /opt/app/backend/models

# Work inside models dir only for download/unpack
(
  cd /opt/app/backend/models
  if [ ! -d "$SMALL_DIR" ] && [ ! -d "$CANON_DIR" ]; then
    echo "Vosk model not found, attempting to download SMALL model..."
    if command -v curl >/dev/null 2>&1; then
      curl -L --max-time 10 -o vosk-model-small-ru-0.22.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip || true
    elif command -v wget >/dev/null 2>&1; then
      wget --timeout=10 -O vosk-model-small-ru-0.22.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip || true
    else
      echo "Neither curl nor wget is available; skipping model download"
    fi
    if [ -f vosk-model-small-ru-0.22.zip ]; then
      unzip -o vosk-model-small-ru-0.22.zip || true
    fi
  fi

  if [ -d "$SMALL_DIR" ] && [ ! -d "$CANON_DIR" ]; then
    ln -sfn "$SMALL_DIR" "$CANON_DIR" || true
  fi
)

export VOSK_MODEL_DIR="$CANON_DIR"

# Ensure working dir is app root so uvicorn can import main
cd /opt/app/backend
exec uvicorn main:app --host 0.0.0.0 --port 8000
