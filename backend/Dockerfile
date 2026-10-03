FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# git is required at runtime to clone user repositories for indexing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only torch (much smaller than the default CUDA build) for local HF embeddings.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser
ENV HF_HOME=/home/appuser/.cache/huggingface
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
