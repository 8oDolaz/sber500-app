FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json tsconfig.base.json ./
COPY apps/pwa/package.json apps/pwa/
COPY packages/ui-kit/package.json packages/ui-kit/
COPY packages/platform/package.json packages/platform/
COPY packages/analytics/package.json packages/analytics/
COPY packages/api-client/package.json packages/api-client/
COPY packages/app-core/package.json packages/app-core/
RUN pnpm install --frozen-lockfile
COPY . .
ARG VITE_APP_VERSION=0.1.0
ENV VITE_APP_VERSION=$VITE_APP_VERSION
RUN pnpm build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/pwa/dist /usr/share/nginx/html
