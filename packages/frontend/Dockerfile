FROM node:22-bookworm-slim AS build

WORKDIR /app

ENV CI=true
ARG VITE_API_URL=/v1
ENV VITE_API_URL=$VITE_API_URL

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/frontend/package.json packages/frontend/package.json
RUN pnpm install --frozen-lockfile

COPY packages/frontend packages/frontend
RUN pnpm --filter frontend build

FROM nginx:1.27-alpine

COPY packages/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/packages/frontend/dist /usr/share/nginx/html

EXPOSE 80
