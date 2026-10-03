FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# CPU-only torch (much smaller than the default CUDA build) for local HF embeddings.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

COPY backend/ .

RUN mkdir -p /tmp/codelens-repos && useradd --create-home appuser \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /tmp/codelens-repos /home/appuser
ENV HF_HOME=/home/appuser/.cache/huggingface
USER appuser

CMD ["python", "-m", "app.workers.indexing_worker"]
