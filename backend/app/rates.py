"""Rate providers and an in-memory cache.

All rates are expressed as "units of currency per 1 USD", so any pair can be
converted through USD: amount * rates[to] / rates[from].

Primary source is Coinbase, the provider Google's converter cites for crypto.
Its public exchange-rates endpoint covers fiat and crypto in one call and
updates intraday. The other providers only fill in what Coinbase did not return.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

CURRENCIES = ("RUB", "USD", "IDR", "BTC", "ETH")
FIAT = ("RUB", "IDR")
CRYPTO = {"BTC": "bitcoin", "ETH": "ethereum"}

COINBASE_RATES_URL = "https://api.coinbase.com/v2/exchange-rates"
COINBASE_STATS_URL = "https://api.exchange.coinbase.com/products/{}-USD/stats"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
# Free tier updates once a day and asks for attribution; fallback only.
ER_API_URL = "https://open.er-api.com/v6/latest/USD"
# Free, no key, served from jsDelivr; covers both fiat and crypto. Last resort.
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


async def fetch_coinbase(client: httpx.AsyncClient) -> dict[str, float]:
    r = await client.get(COINBASE_RATES_URL, params={"currency": "USD"})
    r.raise_for_status()
    raw = r.json()["data"]["rates"]
    return {c: float(raw[c]) for c in CURRENCIES if c != "USD" and c in raw}


async def fetch_coinbase_change(client: httpx.AsyncClient) -> dict[str, float]:
    async def one(code: str) -> tuple[str, float]:
        r = await client.get(COINBASE_STATS_URL.format(code))
        r.raise_for_status()
        s = r.json()
        opened, last = float(s["open"]), float(s["last"])
        return code, round((last - opened) / opened * 100, 2)

    return dict(await asyncio.gather(*(one(c) for c in CRYPTO)))


async def fetch_fiat(client: httpx.AsyncClient) -> dict[str, float]:
    r = await client.get(ER_API_URL)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != "success":
        raise RuntimeError(f"er-api error: {data.get('error-type')}")
    return {c: float(data["rates"][c]) for c in FIAT}


async def fetch_crypto(client: httpx.AsyncClient) -> tuple[dict[str, float], dict[str, float]]:
    r = await client.get(
        COINGECKO_URL,
        params={"ids": ",".join(CRYPTO.values()), "vs_currencies": "usd", "include_24hr_change": "true"},
    )
    r.raise_for_status()
    data = r.json()
    rates, change = {}, {}
    for code, cg_id in CRYPTO.items():
        rates[code] = 1.0 / float(data[cg_id]["usd"])
        if (ch := data[cg_id].get("usd_24h_change")) is not None:
            change[code] = round(float(ch), 2)
    return rates, change


async def fetch_fallback(client: httpx.AsyncClient) -> dict[str, float]:
    r = await client.get(FAWAZ_URL)
    r.raise_for_status()
    usd = r.json()["usd"]
    return {c: float(usd[c.lower()]) for c in CURRENCIES}


class RateService:
    def __init__(self, ttl: float = 60.0, timeout: float = 8.0, transport: httpx.AsyncBaseTransport | None = None):
        self.ttl = ttl
        self.timeout = timeout
        self.transport = transport
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
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers={"User-Agent": "kurs-converter/1.0"}
        ) as client:
            rates: dict[str, float] = {"USD": 1.0}
            change: dict[str, float] = {}
            sources: list[str] = []

            cb, cb_change = await asyncio.gather(
                fetch_coinbase(client), fetch_coinbase_change(client), return_exceptions=True
            )
            if isinstance(cb, Exception):
                log.warning("Coinbase rates failed: %s", cb)
            else:
                rates.update(cb)
                sources.append("coinbase.com")
            if isinstance(cb_change, Exception):
                log.warning("Coinbase stats failed: %s", cb_change)
            else:
                change.update(cb_change)

            missing = lambda: [c for c in CURRENCIES if c not in rates]  # noqa: E731

            if any(c in FIAT for c in missing()):
                try:
                    fiat = await fetch_fiat(client)
                    rates.update({c: v for c, v in fiat.items() if c in missing()})
                    sources.append("open.er-api.com")
                except Exception as exc:
                    log.warning("Fiat fallback failed: %s", exc)

            if any(c in CRYPTO for c in missing()) or not change:
                try:
                    crypto, cg_change = await fetch_crypto(client)
                    rates.update({c: v for c, v in crypto.items() if c in missing()})
                    change = change or cg_change
                    sources.append("coingecko.com")
                except Exception as exc:
                    log.warning("Crypto fallback failed: %s", exc)

            if missing():
                fb = await fetch_fallback(client)
                rates.update({c: fb[c] for c in missing()})
                sources.append("fawazahmed0/currency-api")

        return RateSnapshot(rates, change, datetime.now(timezone.utc), sources)


def convert(rates: dict[str, float], amount: float, src: str, dst: str) -> float:
    return amount * rates[dst] / rates[src]
