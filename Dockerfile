# 백엔드(FastAPI) 이미지 — SQLite는 /data 볼륨에 영속.
FROM python:3.12-slim

WORKDIR /app

# 의존성 먼저(레이어 캐시). bcrypt=네이버 OAuth real용.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt bcrypt

# 애플리케이션 코드
COPY api ./api
COPY jikgugom ./jikgugom
COPY config ./config

# 비루트 실행 + SQLite 영속 디렉터리
RUN useradd -m app && mkdir -p /data && chown app:app /data
USER app

ENV DATABASE_URL=sqlite:////data/jikgugom.db
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
