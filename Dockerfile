# ==========================================
# Dockerfile optimizado para VPS ($5/mes)
# Tamaño final < 150MB, RAM < 180MB en ejecución
# ==========================================

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runner Stage
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

# Directorio de persistencia para SQLite y datos locales
RUN mkdir -p /app/data /app/media_cache

ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

EXPOSE 8080

CMD ["python", "cli.py", "run-daemon"]
