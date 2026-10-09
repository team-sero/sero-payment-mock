"""payment-mock: S.E.R.O 테스트 환경의 가짜 외부 결제사.

* POST /payments: 주문번호와 금액을 받아, 정해진 지연(기본 0.8초) 뒤에 승인이나 거절로 답한다
* POST /admin/config: 오류율, 오류 상태 코드, 지연, 동시 처리 상한을 바꾼다. 본문이 비어 있으면 기본값으로 돌아간다
* 장애는 재시작 없이 이 설정으로만 넣고 뺀다. 재시작하면 쿠버네티스에 흔적이 남기 때문이다
* 설정은 프로세스 메모리에만 있다. 그래서 워커 1개, 레플리카 1개로 돌린다
"""
import asyncio
import logging
import random
from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import get_settings

log = logging.getLogger("payment_mock")


class FaultConfig(BaseModel):
    """관리 API로 바꾸는 설정. 보내지 않은 항목은 기본값이 된다."""

    error_rate: float = Field(0.0, ge=0.0, le=1.0, description="이 비율만큼 결제 요청에 오류로 답한다 (0~1)")
    error_status: int = Field(503, ge=500, le=599, description="오류로 답할 때의 상태 코드")
    latency_ms: int = Field(800, ge=0, le=60_000, description="모든 결제 응답 전에 기다리는 시간")
    max_concurrency: int | None = Field(
        None, ge=1, description="동시에 처리하는 결제 수 상한. 넘친 요청은 거절하지 않고 기다린다. null이면 상한 없음"
    )


class PaymentRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    amount: int = Field(ge=0, description="원 단위 결제 금액")


class PaymentResult(BaseModel):
    status: Literal["APPROVED", "DECLINED"]
    order_id: str
    amount: int
    payment_id: str | None = None
    reason: str | None = None


class Gate:
    """동시 처리 상한. 상한을 넘은 요청은 자리가 날 때까지 기다린다(S27 재시도 폭주의 대기열)."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.waiting = 0
        self._cond = asyncio.Condition()

    async def enter(self, limit: Callable[[], int | None]) -> None:
        async with self._cond:
            self.waiting += 1
            try:
                # 상한은 매번 새로 읽는다. 관리 API로 바뀌면 wake()가 기다리던 요청을 깨운다
                await self._cond.wait_for(lambda: limit() is None or self.in_flight < limit())
            finally:
                self.waiting -= 1
            self.in_flight += 1

    async def leave(self) -> None:
        async with self._cond:
            self.in_flight -= 1
            self._cond.notify_all()

    async def wake(self) -> None:
        async with self._cond:
            self._cond.notify_all()


settings = get_settings()
faults = FaultConfig()
gate = Gate()
rng = random.Random()

app = FastAPI(title="payment-mock")


@app.post("/payments", response_model=PaymentResult)
async def create_payment(body: PaymentRequest):
    await gate.enter(lambda: faults.max_concurrency)
    try:
        await asyncio.sleep(faults.latency_ms / 1000)
        if rng.random() < faults.error_rate:
            return JSONResponse({"detail": "payment provider error"}, status_code=faults.error_status)
        if body.amount > settings.payment_limit:
            return PaymentResult(status="DECLINED", order_id=body.order_id, amount=body.amount, reason="LIMIT_EXCEEDED")
        return PaymentResult(
            status="APPROVED", order_id=body.order_id, amount=body.amount, payment_id=f"pay_{uuid4().hex[:20]}"
        )
    finally:
        await gate.leave()


def _config_view() -> dict:
    return {**faults.model_dump(), "in_flight": gate.in_flight, "waiting": gate.waiting}


@app.get("/admin/config")
async def read_config():
    """지금 설정과, 처리 중인 결제 수(in_flight), 상한 때문에 기다리는 결제 수(waiting)."""
    return _config_view()


@app.post("/admin/config")
async def write_config(body: FaultConfig | None = None):
    """설정을 통째로 바꾼다. 본문이 없거나 {}이면 기본값(오류 0, 지연 800ms, 상한 없음)으로 되돌린다."""
    global faults
    faults = body or FaultConfig()
    log.info("fault config changed: %s", faults.model_dump())
    await gate.wake()
    return _config_view()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}