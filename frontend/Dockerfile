FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
ARG NEXT_PUBLIC_HYC_PUBLIC_DEMO=0
ENV NEXT_PUBLIC_HYC_PUBLIC_DEMO=$NEXT_PUBLIC_HYC_PUBLIC_DEMO
RUN pnpm build

FROM node:24-alpine
WORKDIR /app
# Next standalone defaults HOSTNAME to the container hostname, which makes the
# in-container loopback healthcheck unavailable. Keep the service reachable
# within the container network while Compose continues to publish it only on
# the host loopback interface.
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
