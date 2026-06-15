# 배포 가이드 — Docker 한 묶음

백엔드(FastAPI) + 프론트(Next.js) + SQLite 볼륨을 `docker compose`로 한 번에 띄운다.
SQLite는 named volume(`jikgugom_data`)에 영속 → 컨테이너 재생성에도 데이터 유지.

## 1. 사전 준비 — Google OAuth (관리자 로그인)
1. **Google Cloud Console** → 프로젝트 → *API 및 서비스 → 사용자 인증 정보*
2. **OAuth 2.0 클라이언트 ID**(애플리케이션 유형: **웹**) 생성
3. **승인된 JavaScript 원본**에 프론트 주소 추가 (예: `https://admin.example.com`, 로컬은 `http://localhost:3000`)
4. 발급된 **클라이언트 ID**를 `.env`의 `GOOGLE_CLIENT_ID`에 넣기
5. 로그인 허용 계정을 `ADMIN_ALLOWED_EMAILS`에 (쉼표 구분)

> `GOOGLE_CLIENT_ID` + `ADMIN_ALLOWED_EMAILS`가 모두 있으면 인증이 켜진다.
> 둘 중 하나라도 비면 인증 OFF(로컬 개발 편의).

## 2. `.env` 작성
```bash
cp .env.example .env
```
배포 시 최소 항목:
```ini
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
ADMIN_ALLOWED_EMAILS=me@gmail.com
SESSION_SECRET=<openssl rand -hex 32 로 생성>
CORS_ORIGINS=https://admin.example.com        # 프론트 공개 origin
PUBLIC_API_URL=https://api.example.com        # 브라우저가 호출할 백엔드 주소
GEMINI_API_KEY=...                            # 채운 레이어만 real
DEEPL_API_KEY=...
# ALIEXPRESS_APP_KEY / NAVER_CLIENT_ID 등은 준비되면
```
- `SESSION_SECRET`: `openssl rand -hex 32` 로 생성해 넣기(고정해야 재시작 후에도 로그인 유지).
- `CORS_ORIGINS`: 프론트가 백엔드를 호출할 수 있게 프론트 origin을 허용.
- `PUBLIC_API_URL`: **브라우저**가 접근하는 주소(도커 내부 주소 아님).

## 3. 실행
```bash
docker compose up -d --build
# 프론트 http://<host>:3000  /  백엔드 http://<host>:8000
docker compose logs -f        # 로그
docker compose down           # 중지(볼륨=데이터는 유지)
```

## 4. 동작 확인
- `GET /api/health` → `{"status":"ok"}`
- `GET /api/config` → `auth_enabled: true`, `modes`에 real/mock
- 프론트 접속 → **Google 로그인 화면** → 허용 이메일로 로그인 → 대시보드

## 보안 체크
- [ ] `SESSION_SECRET` 무작위·고정, `.env`는 커밋 금지(.gitignore 포함)
- [ ] `CORS_ORIGINS`를 실제 프론트 origin으로 제한(와일드카드 금지)
- [ ] HTTPS는 리버스 프록시(Nginx/Caddy/클라우드 LB)에서 종단 — 컨테이너는 평문 8000/3000
- [ ] 화이트리스트(`ADMIN_ALLOWED_EMAILS`)에 필요한 계정만

## 비고
- PostgreSQL로 전환: `.env`에 `DATABASE_URL=postgresql+psycopg://...` (compose의 backend
  environment 가 sqlite로 덮어쓰므로 그 줄을 지우거나 DB 서비스를 compose에 추가).
- 쿠팡 실어댑터·AliExpress 드롭십 주문 API는 로드맵(Phase 4).
