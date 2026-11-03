FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline
COPY . .
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=$VITE_BASE_PATH
RUN npm run build
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1/health || exit 1
