# Stage 1 — build the static bundle
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2 — serve it with nginx, reverse-proxying API calls to the backend
# service so the browser only ever talks to one origin (no CORS in prod).
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD wget --quiet --spider http://127.0.0.1/ || exit 1
