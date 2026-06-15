"""FastAPI 앱 — 대시보드용 JSON API.

    uvicorn api.main:app --reload --port 8000

라우트는 얇게: DashboardService에 위임. 상태는 Repository(인메모리/SQL)에 영속.

[인증] GOOGLE_CLIENT_ID + ADMIN_ALLOWED_EMAILS 가 설정되면 관리자 인증이 켜진다.
       공개 라우트(health/config/auth)를 제외한 모든 API는 세션 토큰을 요구한다.
       설정이 없으면(로컬 개발) 인증은 비활성 → 누구나 접근(편의).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.auth import (
    AuthError,
    create_session_token,
    verify_google_id_token,
    verify_session_token,
)
from api.schemas import (
    ConfirmPurchaseIn,
    GoogleAuthIn,
    ListingOut,
    OrderOut,
    PublicationOut,
    StatsOut,
)
from api.scheduler import MonitorScheduler
from api.service import DashboardService

service = DashboardService()
scheduler = MonitorScheduler(service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()       # 가격·재고 점검 주기 실행 시작
    yield
    scheduler.shutdown()


app = FastAPI(title="직구곰 admin API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(service.settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 인증 의존성 ──────────────────────────────────────────────
def require_admin(authorization: str | None = Header(default=None)) -> str | None:
    """세션 토큰 검증 → 이메일. 인증 비활성이면 통과(로컬 개발)."""
    s = service.settings
    if not s.auth_enabled:
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        email = verify_session_token(authorization.split(" ", 1)[1], s.session_secret)
    except AuthError as e:
        raise HTTPException(401, str(e))
    if email.lower() not in s.admin_allowed_emails:
        raise HTTPException(403, "관리자 화이트리스트에 없는 계정")
    return email


# 보호 라우터 — 여기 붙는 모든 라우트는 require_admin 통과 필요
protected = APIRouter(dependencies=[Depends(require_admin)])


# ── 공개 라우트 ──────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "modes": service.modes}


@app.get("/api/config")
def get_config() -> dict:
    """어댑터/LLM 모드(real/mock)·운영 파라미터·인증 상태. 키(시크릿)는 노출 안 함."""
    return service.config()


@app.post("/api/auth/google")
def auth_google(body: GoogleAuthIn) -> dict:
    """Google ID 토큰 → 검증·화이트리스트 확인 → 세션 토큰 발급."""
    s = service.settings
    if not s.auth_enabled:
        raise HTTPException(400, "서버에 인증이 설정돼 있지 않습니다")
    try:
        email = verify_google_id_token(body.credential, s.google_client_id)
    except AuthError as e:
        raise HTTPException(401, str(e))
    if email.lower() not in s.admin_allowed_emails:
        raise HTTPException(403, "이 계정은 관리자 화이트리스트에 없습니다")
    return {"token": create_session_token(email, s.session_secret), "email": email}


# ── 보호 라우트 ──────────────────────────────────────────────
@protected.get("/api/stats", response_model=StatsOut)
def get_stats() -> dict:
    return service.stats()


def _listings_view() -> list[ListingOut]:
    """listing + 채널별 발행 결과(publications)를 묶어 응답 모델로 조립."""
    pubs: dict[str, list[PublicationOut]] = {}
    for p in service.repo.list_all_publications():
        pubs.setdefault(p.listing_id, []).append(PublicationOut(
            channel=p.channel, status=p.status, channel_product_no=p.channel_product_no))
    return [ListingOut(
        id=r.id, title=r.title, status=r.status, note=r.note, price_krw=r.price_krw,
        market_score=r.market_score, recommendation=r.recommendation,
        channel_product_no=r.channel_product_no, publications=pubs.get(r.id, []))
        for r in service.repo.list_listings()]


@protected.get("/api/listings", response_model=list[ListingOut])
def list_listings() -> list:
    return _listings_view()


@protected.post("/api/listings/{listing_id}/approve", response_model=ListingOut)
def approve_listing(listing_id: str):
    try:
        return service.approve_listing(listing_id)
    except KeyError:
        raise HTTPException(404, f"listing {listing_id} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@protected.post("/api/sourcing/run", response_model=list[ListingOut])
def run_sourcing() -> list:
    service.run_sourcing()
    return _listings_view()


@protected.get("/api/orders", response_model=list[OrderOut])
def list_orders() -> list:
    return service.repo.list_orders()


@protected.post("/api/orders/{order_id}/approve", response_model=OrderOut)
def approve_order(order_id: str):
    try:
        return service.approve_order(order_id)
    except KeyError:
        raise HTTPException(404, f"order {order_id} not found")


@protected.post("/api/orders/{order_id}/confirm", response_model=OrderOut)
def confirm_order_purchase(order_id: str, body: ConfirmPurchaseIn):
    """운영자가 Amazon 실매입을 마친 뒤 주문번호·송장을 기록 → 매입 확정."""
    try:
        return service.confirm_purchase(order_id, body.amazon_order_no,
                                        tracking_no=body.tracking_no)
    except KeyError:
        raise HTTPException(404, f"order {order_id} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@protected.post("/api/orders/{order_id}/reject", response_model=OrderOut)
def reject_order(order_id: str):
    try:
        return service.reject_order(order_id)
    except KeyError:
        raise HTTPException(404, f"order {order_id} not found")


@protected.post("/api/monitor/run")
def run_monitor() -> dict:
    """가격·재고 점검을 즉시 실행(스케줄러와 동일 동작). 변경분 반환."""
    changes = service.monitor_sweep()
    return {"changed": len(changes), "changes": changes}


@protected.get("/api/monitor/last")
def monitor_last() -> dict:
    """스케줄러의 마지막 자동 점검 결과."""
    return scheduler.last_run or {"at": None, "changed": 0, "changes": []}


@protected.post("/api/dev/simulate/{listing_id}")
def dev_simulate(listing_id: str, event: str = "oos") -> dict:
    """[데모 전용] 원본가/재고 변동을 흉내 내 점검 동작을 시연한다.

    event: oos(품절) | restock(재입고) | drop(가격하락) | spike(가격급등)
    실서비스에는 없는 엔드포인트(SampleSource 시뮬레이션용).
    """
    src = service._source
    if not hasattr(src, "set_out_of_stock"):
        raise HTTPException(400, "simulation not supported on this source")
    base = src.get_product(listing_id).price       # 상품별 기준가 상대로 변동
    if event == "oos":
        src.set_out_of_stock(listing_id, True)
    elif event == "restock":
        src.set_out_of_stock(listing_id, False)
    elif event == "drop":
        src.set_source_price(listing_id, base * Decimal("0.7"))   # -30%
    elif event == "spike":
        src.set_source_price(listing_id, base * Decimal("1.3"))   # +30%
    else:
        raise HTTPException(400, f"unknown event '{event}'")
    return {"listing_id": listing_id, "event": event}


app.include_router(protected)
