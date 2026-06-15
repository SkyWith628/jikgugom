# 프론트(Next.js) 이미지 — standalone 멀티스테이지(빌드 도구는 최종 이미지에서 제외).
# 빌드 컨텍스트는 레포 루트(docker-compose 참고) → 경로는 dashboard/ 기준.

FROM node:20-alpine AS deps
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY dashboard/ .
# 브라우저가 호출할 백엔드 공개 URL(빌드 시 인라인). Google client_id는 런타임에
# /api/config 로 받으므로 빌드 인자 불필요.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
# standalone 산출물 + 정적 자산
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
