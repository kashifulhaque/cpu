# Stage 1: build the single-page app.
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# Stage 2: the Python service, which also serves the built assets and runs the
# readers' submissions, which call clang and the LLVM tools.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_SYSTEM_PYTHON=1 \
    DATA_DIR=/data

WORKDIR /app

# The exercises drive the real toolchain through backend/app/runner/cputools.py:
# clang compiles C and assembles x86-64, and the llvm package brings opt, llc,
# lli, llvm-objdump, and llvm-objcopy.
RUN apt-get update \
    && apt-get install -y --no-install-recommends clang llvm libc6-dev procps \
    && rm -rf /var/lib/apt/lists/*

# uv installs into the system Python, as pip did, several times faster.
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

COPY backend/requirements.txt ./backend/requirements.txt
RUN uv pip install -r backend/requirements.txt

COPY backend/ ./backend/
COPY content/ ./content/
COPY docs/ ./docs/
COPY --from=frontend /build/dist ./frontend/dist

# The commit this image was built from, reported by /api/health. Declared after
# the COPY steps so changing it does not invalidate the layers above.
ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

RUN useradd --create-home --uid 10001 app
RUN mkdir -p /data
RUN chown -R app:app /data /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
