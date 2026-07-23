# AgentCapital AI API container — used for Hugging Face Spaces (free tier) and any
# other Docker host. HF runs containers as uid 1000 with a read-only HOME,
# so the writable data dir is prepared at build time.

FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
RUN python scripts/generate_pdfs.py \
    && mkdir -p data/inbox \
    && chmod -R 777 data

ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
