FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY ["designe 1.0/package.json", "designe 1.0/package-lock.json", "./"]
RUN npm ci
COPY ["designe 1.0/", "./"]
ARG NEXT_PUBLIC_SITE_URL
ARG INROU_STAGING=0
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}
ENV INROU_STAGING=${INROU_STAGING} NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app /app/backend/app
COPY backend/migrations /app/backend/migrations
COPY deploy /app/deploy
COPY --from=frontend --chown=node:node /web/.next/standalone /app/web
COPY --from=frontend --chown=node:node /web/.next/static /app/web/.next/static
COPY --from=frontend --chown=node:node /web/public /app/web/public
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
USER node
EXPOSE 10000
CMD ["python", "/app/deploy/serve.py"]
