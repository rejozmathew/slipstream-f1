# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 slipstream

USER slipstream
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["python", "-m", "slipstream"]
CMD ["serve", "/data", "--host", "0.0.0.0", "--port", "8000", "--catalog-years", "3"]

FROM node:22-alpine AS web-builder

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS web

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000
WORKDIR /app
COPY --from=web-builder --chown=node:node /app/dist/standalone ./
# vinext beta's standalone emitter currently omits its React peer runtime.
COPY --from=web-builder --chown=node:node /app/node_modules/react ./node_modules/react
COPY --from=web-builder --chown=node:node /app/node_modules/react-dom ./node_modules/react-dom
COPY --from=web-builder --chown=node:node /app/node_modules/react-server-dom-webpack ./node_modules/react-server-dom-webpack
COPY --from=web-builder --chown=node:node /app/node_modules/scheduler ./node_modules/scheduler
USER node
EXPOSE 3000
CMD ["node", "server.js"]
