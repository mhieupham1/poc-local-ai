FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/local-ai

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --chmod=0555 docker/gateway/entrypoint.sh /usr/local/bin/local-ai-gateway

RUN python -m pip install --no-cache-dir uv==0.11.3 \
    && uv sync --frozen --no-dev --no-editable \
    && addgroup --system --gid 10001 localai \
    && adduser --system --uid 10001 --ingroup localai --no-create-home localai

ENV PATH="/opt/local-ai/.venv/bin:${PATH}"

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/local-ai-gateway"]
