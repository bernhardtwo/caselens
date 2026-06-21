# syntax=docker/dockerfile:1
# Build context is apps/web:
#   docker build -f apps/web/Dockerfile -t caselens-web apps/web

FROM node:22-slim AS builder
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
