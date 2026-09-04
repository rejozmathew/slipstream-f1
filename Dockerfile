# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS web-builder

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.13-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SLIPSTREAM_MODE=full
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[pirelli-pdf]" \
    && groupadd --gid 10001 slipstream \
    && useradd --create-home --uid 10001 --gid slipstream slipstream \
    && install -d -o slipstream -g slipstream /data
COPY --from=web-builder /app/dist ./web

COPY --chmod=755 deploy/docker-entrypoint.sh /usr/local/bin/slipstream-entrypoint

# The entrypoint prepares the mount root, then execs Slipstream as UID 10001.
USER root
VOLUME ["/data"]
EXPOSE 3344
ENTRYPOINT ["slipstream-entrypoint"]
CMD ["serve", "/data", "--host", "0.0.0.0", "--port", "3344", "--web-dir", "/app/web"]
