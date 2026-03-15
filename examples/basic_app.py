"""Example: applying GuardMiddleware to a simple FastAPI app.

Run:
    uvicorn examples.basic_app:app --port 8000

Requires Redis running on localhost:6379.
"""

import sys
import pathlib

# Add project root to path so guard package is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from guard import GuardMiddleware
from guard.metrics import metrics
from guard.middleware import guard_log

app = FastAPI(title="My Shopping Mall")

# 1. Add the guard middleware — one line
app.add_middleware(
    GuardMiddleware,
    bypass_paths={"/", "/about", "/health"},  # pages that skip the guard
)


# 2. Your normal routes — guard protects API endpoints automatically

@app.get("/")
async def home():
    return {"page": "Welcome to My Shopping Mall"}


@app.get("/about")
async def about():
    return {"page": "About Us"}


@app.get("/api/products")
async def products():
    return {"products": ["Shirt", "Pants", "Shoes"]}


@app.get("/api/cart/add")
async def add_to_cart(item: str = "Shirt"):
    return {"status": "added", "item": item}


@app.get("/api/checkout")
async def checkout():
    return {"status": "checkout_page"}


@app.get("/api/pay")
async def pay():
    return {"status": "payment_processing"}


# 3. Optional: ops endpoints for monitoring

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


@app.get("/guard-log")
async def get_log():
    return list(guard_log)
