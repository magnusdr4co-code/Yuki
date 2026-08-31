# ==========================================
# Imagen de Yuki — Diva Digital Autónoma
# Multi-stage. Runtime sin compiladores, proceso sin privilegios.
# Válida para VPS ($5/mes) y para Cloud Run.
# ==========================================

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ------------------------------------------
# Runner
# ------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Usuario sin privilegios: un proceso expuesto a internet no corre como root.
RUN useradd --create-home --uid 10001 yuki

COPY --chown=yuki:yuki . .

# Directorios de persistencia y de trabajo creativo
RUN mkdir -p /app/data /app/media_cache /app/output/art /app/output/voice \
             /app/output/music /app/output/posts \
    && chown -R yuki:yuki /app/data /app/media_cache /app/output

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PORT=8080

USER yuki

EXPOSE 8080

# Sonda local (Cloud Run usa su propia sonda de arranque contra /health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# Por defecto se sirve el Salón: es lo que espera una plataforma gestionada,
# que exige un proceso escuchando en $PORT.
# Para presencia autónoma en VPS:            docker run ... python cli.py run-daemon
# Para una tarea suelta (Cloud Run Jobs):    docker run ... python cli.py cron-task --name <tarea>
CMD ["python", "cli.py", "web"]
