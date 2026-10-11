"""Rate providers and an in-memory cache.

All rates are expressed as "units of currency per 1 USD", so any pair can be
converted through USD: amount * rates[to] / rates[from].
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

CURRENCIES = ("RUB", "IDR", "BTC", "ETH")
FIAT = ("RUB", "IDR")
CRYPTO = {"BTC": "bitcoin", "ETH": "ethereum"}

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
ER_API_URL = "https://open.er-api.com/v6/latest/USD"
# Free, no key, served from jsDelivr; covers both fiat and crypto. Used as fallback.
FAWAZ_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"


@dataclass
class RateSnapshot:
    rates: dict[str, float]            # units per 1 USD, includes "USD": 1.0
    change_24h: dict[str, float]       # % change of the USD price, crypto only
    updated_at: datetime
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "base": "USD",
            "rates": self.rates,
            "change_24h": self.change_24h,
            "updated_at": self.updated_at.isoformat(),
            "sources": self.sources,
        }


async def fetch_fiat(client: httpx.AsyncClient) -> tuple[dict[str, float], str]:
    r = await client.get(ER_API_URL)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != "success":
        raise RuntimeError(f"er-api error: {data.get('error-type')}")
    return {c: float(data["rates"][c]) for c in FIAT}, "open.er-api.com"


async def fetch_crypto(client: httpx.AsyncClient) -> tuple[dict[str, float], dict[str, float], str]:
    r = await client.get(
        COINGECKO_URL,
        params={
            "ids": ",".join(CRYPTO.values()),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        },
    )
    r.raise_for_status()
    data = r.json()
    rates, change = {}, {}
    for code, cg_id in CRYPTO.items():
        price_usd = float(data[cg_id]["usd"])
        rates[code] = 1.0 / price_usd
        if (ch := data[cg_id].get("usd_24h_change")) is not None:
            change[code] = round(float(ch), 2)
    return rates, change, "coingecko.com"


async def fetch_fallback(client: httpx.AsyncClient) -> tuple[dict[str, float], str]:
    r = await client.get(FAWAZ_URL)
    r.raise_for_status()
    usd = r.json()["usd"]
    return {c: float(usd[c.lower()]) for c in CURRENCIES}, "fawazahmed0/currency-api"


class RateService:
    def __init__(self, ttl: float = 60.0, timeout: float = 8.0):
        self.ttl = ttl
        self.timeout = timeout
        self._snapshot: RateSnapshot | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, force: bool = False) -> RateSnapshot:
        if not force and self._snapshot and time.monotonic() - self._fetched_at < self.ttl:
            return self._snapshot
        async with self._lock:
            # Another request may have refreshed while we waited.
            if not force and self._snapshot and time.monotonic() - self._fetched_at < self.ttl:
                return self._snapshot
            try:
                self._snapshot = await self._refresh()
                self._fetched_at = time.monotonic()
            except Exception:
                if self._snapshot is None:
                    raise
                log.exception("Rate refresh failed, serving stale data")
            return self._snapshot

    async def _refresh(self) -> RateSnapshot:
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "fx-converter/1.0"}) as client:
            fiat, crypto = await asyncio.gather(
                fetch_fiat(client), fetch_crypto(client), return_exceptions=True
            )
            rates: dict[str, float] = {"USD": 1.0}
            change: dict[str, float] = {}
            sources: list[str] = []

            if isinstance(fiat, Exception):
                log.warning("Fiat provider failed: %s", fiat)
            else:
                rates.update(fiat[0]); sources.append(fiat[1])
            if isinstance(crypto, Exception):
                log.warning("Crypto provider failed: %s", crypto)
            else:
                rates.update(crypto[0]); change.update(crypto[1]); sources.append(crypto[2])

            missing = [c for c in CURRENCIES if c not in rates]
            if missing:
                fb, src = await fetch_fallback(client)
                for c in missing:
                    rates[c] = fb[c]
                sources.append(src)

        return RateSnapshot(rates, change, datetime.now(timezone.utc), sources)


def convert(rates: dict[str, float], amount: float, src: str, dst: str) -> float:
    return amount * rates[dst] / rates[src]
