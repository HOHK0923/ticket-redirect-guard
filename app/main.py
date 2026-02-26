"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.middleware import GuardMiddleware
from app.redis_client import close_redis
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(
    title="Ticket Redirect Guard",
    description="Bot/macro traffic mitigation PoC for ticketing backends",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(GuardMiddleware)
app.include_router(router)
