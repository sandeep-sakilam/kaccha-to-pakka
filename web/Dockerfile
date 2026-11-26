FROM node:22-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx vite build

FROM caddy:2-alpine
COPY --from=build /web/dist /srv
COPY Caddyfile.web /etc/caddy/Caddyfile
EXPOSE 80
