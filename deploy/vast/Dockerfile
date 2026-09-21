ARG VAST_VLLM_BASE=vastai/vllm:v0.29.0-cuda-12.9@sha256:fbe67daa667156429258c9f2ed8f25cc49afc1cfc3abf353a7f3644e07230909
FROM ${VAST_VLLM_BASE}

LABEL org.opencontainers.image.source="https://github.com/mhieupham1/poc-local-ai" \
      org.opencontainers.image.description="Single-domain Qwen3-VL and BGE-M3 PoC for Vast.ai"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    VLLM_CACHE_ROOT=/workspace/.cache/vllm \
    PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8080:18000:/:Local AI API"

WORKDIR /opt/local-ai

RUN rm -f \
    /etc/supervisor/conf.d/vllm.conf \
    /etc/supervisor/conf.d/ray.conf \
    /etc/supervisor/conf.d/model-ui.conf \
    /etc/vast_capabilities.d/30-vllm.yaml

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY benchmarks ./benchmarks
COPY deploy/vast/patch-caddy-manager.py /tmp/patch-caddy-manager.py

RUN uv sync --frozen --no-dev --no-editable && \
    python3 /tmp/patch-caddy-manager.py \
      /opt/portal-aio/caddy_manager/caddy_config_manager.py && \
    rm -f /tmp/patch-caddy-manager.py

COPY deploy/vast/ROOT /

RUN chmod 0555 /opt/supervisor-scripts/local-ai-common.sh \
    /opt/supervisor-scripts/local-ai-embedding.sh \
    /opt/supervisor-scripts/local-ai-llm.sh \
    /opt/supervisor-scripts/local-ai-gateway.sh \
    /opt/supervisor-scripts/local-ai-redact-caddy-output.sh \
    /opt/supervisor-scripts/local-ai-protect-caddyfile.sh \
    /opt/supervisor-scripts/caddy.sh

EXPOSE 1111 8080
