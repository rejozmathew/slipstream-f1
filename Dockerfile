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

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 slipstream \
    && install -d -o slipstream -g slipstream /data
COPY --from=web-builder /app/dist ./web

USER slipstream
VOLUME ["/data"]
EXPOSE 3444
ENTRYPOINT ["python", "-m", "slipstream"]
CMD ["serve", "/data", "--host", "0.0.0.0", "--port", "3444", "--web-dir", "/app/web", "--catalog-years", "3"]
