from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .rates import CURRENCIES, RateService, convert

app = FastAPI(title="FX Converter", version="1.0.0")
service = RateService(ttl=float(os.getenv("RATES_TTL", "60")))

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/rates")
async def rates(refresh: bool = False):
    try:
        snap = await service.get(force=refresh)
    except Exception as exc:  # no data at all yet
        raise HTTPException(503, f"Rate providers unavailable: {exc}") from exc
    return snap.to_dict()


@app.get("/api/convert")
async def convert_endpoint(
    amount: float = Query(..., ge=0),
    src: str = Query(..., alias="from"),
    dst: str = Query(..., alias="to"),
):
    src, dst = src.upper(), dst.upper()
    for code in (src, dst):
        if code not in CURRENCIES:
            raise HTTPException(400, f"Unsupported currency {code}. Use one of {', '.join(CURRENCIES)}")
    snap = await service.get()
    as_of = {c: (snap.meta[c].as_of.isoformat() if snap.meta[c].as_of else None)
             for c in (src, dst) if c in snap.meta}
    return {
        "from": src,
        "to": dst,
        "amount": amount,
        "result": convert(snap.rates, amount, src, dst),
        "rate": convert(snap.rates, 1, src, dst),
        # when each side's rate was produced by its provider; null when unstated
        "as_of": as_of,
        "fetched_at": snap.fetched_at.isoformat(),
    }


# In production, serve the built React app from the same process.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
