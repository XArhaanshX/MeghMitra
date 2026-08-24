# Self-contained pnpm workspace (apps/app is its own project -- see
# pnpm-workspace.yaml). Build context is apps/app itself:
#
#   docker build -f apps/app/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://api-meghmitra.upayan.dev \
#     -t meghmitra-web apps/app

FROM node:22-slim AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-slim AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* vars are inlined into the client bundle at `next build` time,
# not read at container runtime -- must be supplied as a build arg (see
# src/env.ts, validated via @t3-oss/env-nextjs).
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN pnpm build

# next.config.ts sets `output: "standalone"` -- .next/standalone is a
# self-contained server bundle with only the deps actually used at runtime.
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
