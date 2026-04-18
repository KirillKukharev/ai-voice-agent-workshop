FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl unzip ffmpeg \
        build-essential cmake make g++ gcc \
        libboost-all-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app/backend

COPY pyproject.toml ./
# Pin matches backend/uv.lock. Avoid git fetch (GnuTLS/libcurl flakiness in slim images).
RUN set -eux; \
    ten_vad_sha=22a3bcd4509d0faaa8eef4881e8af5f39c178950; \
    mkdir -p /opt/vendor; \
    curl -fL --retry 5 --retry-delay 15 --retry-all-errors --http1.1 \
      -o /tmp/ten-vad.tgz \
      "https://github.com/TEN-framework/ten-vad/archive/${ten_vad_sha}.tar.gz"; \
    tar -xzf /tmp/ten-vad.tgz -C /opt/vendor; \
    rm /tmp/ten-vad.tgz; \
    mv "/opt/vendor/ten-vad-${ten_vad_sha}" /opt/vendor/ten-vad; \
    sed -i 's|ten-vad = { git = "https://github.com/TEN-framework/ten-vad.git" }|ten-vad = { path = "/opt/vendor/ten-vad" }|' pyproject.toml; \
    curl -LsSf https://astral.sh/uv/install.sh | sh; \
    export PATH="/root/.local/bin:$PATH"; \
    uv sync --no-dev --extra speech-to-text --extra gigaam --no-install-project

COPY wazo-docker/speech_to_text/ ./
RUN export PATH="/root/.local/bin:$PATH" && uv pip install -e ./GigaAM

ENV PATH="/root/.local/bin:/opt/app/backend/.venv/bin:$PATH"
EXPOSE 8000
ENTRYPOINT ["bash", "/opt/app/backend/scripts/entrypoint.sh"]
