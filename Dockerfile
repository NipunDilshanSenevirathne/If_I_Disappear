# If I Disappear: one container serves the web app and the API.
#   docker build -t if-i-disappear .
#   docker run -p 8080:8080 -v iid-data:/data if-i-disappear            # judge mode, sample home
#   docker run -p 8080:8080 -v iid-data:/data --env-file .env if-i-disappear  # live, with your key
# It runs as user 1000, the user Hugging Face Spaces runs every container as (deploy/huggingface).

# 1. Build the web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tsc --noEmit -p . && npx vite build --outDir /web/dist --emptyOutDir

# 2. The server
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 iid \
 && mkdir -p /data && chown iid /data
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/fixtures/sample ./fixtures/sample
COPY --from=web /web/dist ./static
ENV IID_DATA_DIR=/data \
    PORT=8080 \
    IID_WARM_CLIPS=1 \
    PYTHONUNBUFFERED=1
USER iid
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/api/health')"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
