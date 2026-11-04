# syntax=docker/dockerfile:1

# VectorNote web UI in live mode, served by nginx, which also forwards /api to the API container.
# Build: `docker build -t vectornote-web web`

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Real environment variables beat web/.env.production, which switches on the static demo.
ENV VITE_DEMO_MODE=false \
    VITE_API_URL=/api
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
