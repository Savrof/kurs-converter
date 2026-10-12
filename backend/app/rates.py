"""Rate providers and an in-memory cache.

All rates are expressed as "units of currency per 1 USD", so any pair can be
converted through USD: amount * rates[to] / rates[from].

Rule of this module: a timestamp is never invented. Every rate carries the
provider's own "as of" time, or None when the provider states none, so the API
can report freshness honestly instead of echoing the time of our own request.

Source order mirrors demo/api.demo.js:
  crypto  Coinbase Exchange ticker (live trade + its timestamp) -> CoinGecko
  fiat    open.er-api.com (daily fixing, but dated) -> Coinbase table (undated)
  RUB     additionally the Bank of Russia official rate, reported separately
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

CB_TICKER_URL = "https://api.exchange.coinbase.com/products/{}-USD/ticker"
CB_STATS_URL = "https://api.exchange.coinbase.com/products/{}-USD/stats"
CB_TABLE_URL = "https://api.coinbase.com/v2/exchange-rates"
ER_API_URL = "https://open.er-api.com/v6/latest/USD"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


@dataclass
class Quote:
    per_usd: float
    source: str
    as_of: datetime | None = None


@dataclass
class RateSnapshot:
    rates: dict[str, float]            # units per 1 USD, includes "USD": 1.0
    meta: dict[str, Quote]             # which source each rate came from, and when
    change_24h: dict[str, float]       # % change of the USD price, crypto only
    fetched_at: datetime               # when WE asked; not a statement about the data
    official: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "base": "USD",
            "rates": self.rates,
            "meta": {
                c: {"source": q.source, "as_of": q.as_of.isoformat() if q.as_of else None}
                for c, q in self.meta.items()
            },
            "change_24h": self.change_24h,
            "official": self.official,
            "fetched_at": self.fetched_at.isoformat(),
        }


def _utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


async def fetch_crypto_coinbase(client: httpx.AsyncClient) -> dict[str, Quote]:
    async def one(code: str) -> tuple[str, Quote]:
        r = await client.get(CB_TICKER_URL.format(code))
        r.raise_for_status()
        t = r.json()
        price = float(t["price"])
        as_of = datetime.fromisoformat(t["time"].replace("Z", "+00:00")) if t.get("time") else None
        return code, Quote(1.0 / price, "Coinbase Exchange", as_of)

    return dict(await asyncio.gather(*(one(c) for c in CRYPTO)))


async def fetch_change_coinbase(client: httpx.AsyncClient) -> dict[str, float]:
    async def one(code: str) -> tuple[str, float]:
        r = await client.get(CB_STATS_URL.format(code))
        r.raise_for_status()
        s = r.json()
        opened, last = float(s["open"]), float(s["last"])
        return code, round((last - opened) / opened * 100, 2)

    return dict(await asyncio.gather(*(one(c) for c in CRYPTO)))


async def fetch_fiat_er_api(client: httpx.AsyncClient) -> dict[str, Quote]:
    r = await client.get(ER_API_URL)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != "success":
        raise RuntimeError(f"er-api error: {data.get('error-type')}")
    ts = data.get("time_last_update_unix")
    as_of = _utc(ts) if ts else None
    return {c: Quote(float(data["rates"][c]), "open.er-api.com", as_of) for c in FIAT if c in data["rates"]}


async def fetch_fiat_coinbase(client: httpx.AsyncClient) -> dict[str, Quote]:
    """Coinbase's reference table: covers fiat, states no time, and has been seen off-market."""
    r = await client.get(CB_TABLE_URL, params={"currency": "USD"})
    r.raise_for_status()
    raw = r.json()["data"]["rates"]
    return {c: Quote(float(raw[c]), "Coinbase", None) for c in FIAT if c in raw}


async def fetch_crypto_coingecko(client: httpx.AsyncClient) -> tuple[dict[str, Quote], dict[str, float]]:
    r = await client.get(
        COINGECKO_URL,
        params={
            "ids": ",".join(CRYPTO.values()),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        },
    )
    r.raise_for_status()
    data = r.json()
    quotes, change = {}, {}
    for code, cg_id in CRYPTO.items():
        row = data[cg_id]
        as_of = _utc(row["last_updated_at"]) if row.get("last_updated_at") else None
        quotes[code] = Quote(1.0 / float(row["usd"]), "CoinGecko", as_of)
        if (ch := row.get("usd_24h_change")) is not None:
            change[code] = round(float(ch), 2)
    return quotes, change


async def fetch_official_rub(client: httpx.AsyncClient) -> dict:
    """Bank of Russia official rate: the legal reference rate, published once a day."""
    r = await client.get(CBR_URL)
    r.raise_for_status()
    data = r.json()
    usd = data["Valute"]["USD"]
    return {
        "rate": float(usd["Value"]),
        "previous": float(usd["Previous"]) if usd.get("Previous") else None,
        "source": "ЦБ РФ",
        "as_of": data.get("Date"),
    }


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
        rates: dict[str, float] = {"USD": 1.0}
        meta: dict[str, Quote] = {}
        change: dict[str, float] = {}
        official: dict[str, dict] = {}

        def take(quotes: dict[str, Quote]) -> None:
            for code, q in quotes.items():
                if code not in rates:
                    rates[code] = q.per_usd
                    meta[code] = q

        def missing() -> list[str]:
            return [c for c in CURRENCIES if c not in rates]

        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers={"User-Agent": "kurs-converter/1.0"}
        ) as client:
            crypto, fiat, cbr, stats = await asyncio.gather(
                fetch_crypto_coinbase(client),
                fetch_fiat_er_api(client),
                fetch_official_rub(client),
                fetch_change_coinbase(client),
                return_exceptions=True,
            )
            for name, result in (("crypto", crypto), ("fiat", fiat), ("cbr", cbr), ("stats", stats)):
                if isinstance(result, Exception):
                    log.warning("%s provider failed: %s", name, result)
            if not isinstance(crypto, Exception):
                take(crypto)
            if not isinstance(fiat, Exception):
                take(fiat)
            if not isinstance(stats, Exception):
                change.update(stats)
            if not isinstance(cbr, Exception):
                official["RUB"] = cbr

            if any(c in FIAT for c in missing()):
                try:
                    take(await fetch_fiat_coinbase(client))
                except Exception as exc:
                    log.warning("Coinbase fiat table failed: %s", exc)

            if any(c in CRYPTO for c in missing()) or not change:
                try:
                    quotes, cg_change = await fetch_crypto_coingecko(client)
                    take(quotes)
                    change = change or cg_change
                except Exception as exc:
                    log.warning("CoinGecko failed: %s", exc)

            if "RUB" in missing() and official.get("RUB"):
                rates["RUB"] = official["RUB"]["rate"]
                meta["RUB"] = Quote(official["RUB"]["rate"], "ЦБ РФ (официальный)", None)

            if missing():
                raise RuntimeError(f"No rate for {', '.join(missing())}")

        return RateSnapshot(rates, meta, change, datetime.now(timezone.utc), official)


def convert(rates: dict[str, float], amount: float, src: str, dst: str) -> float:
    return amount * rates[dst] / rates[src]
