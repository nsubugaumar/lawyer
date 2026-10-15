# LexDesk website and web app (Next.js), built once, served small.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG LEXDESK_API_ORIGIN=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 LEXDESK_API_ORIGIN=$LEXDESK_API_ORIGIN
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S lexdesk && adduser -S lexdesk -G lexdesk
COPY --from=build --chown=lexdesk:lexdesk /app/.next/standalone ./
COPY --from=build --chown=lexdesk:lexdesk /app/.next/static ./.next/static
COPY --from=build --chown=lexdesk:lexdesk /app/public ./public
USER lexdesk
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
