"""Shared fake for the rate providers.

One place describes what each upstream returns, so a test says only how it
differs from the happy path: which hosts are down, or what a host answers.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app.rates import RateService

NOW = int(datetime.now(timezone.utc).timestamp())

TICKER = {
    "BTC": {"price": "111800.25", "time": "2026-10-12T05:30:00Z"},
    "ETH": {"price": "4120.50", "time": "2026-10-12T05:30:00Z"},
}
STATS = {"BTC": {"open": "110000", "last": "111800"}, "ETH": {"open": "4200", "last": "4120"}}
ER_API = {"result": "success", "time_last_update_unix": NOW - 7 * 3600, "rates": {"RUB": 84.4, "IDR": 16400.0}}
CB_TABLE = {"data": {"currency": "USD", "rates": {"RUB": "85.03", "IDR": "16420"}}}
CBR = {"Date": "2026-10-12T11:30:00+03:00", "Valute": {"USD": {"Value": 83.9512, "Previous": 84.21}}}
COINGECKO = {
    "bitcoin": {"usd": 111000, "usd_24h_change": 1.1, "last_updated_at": NOW - 120},
    "ethereum": {"usd": 4100, "usd_24h_change": -0.9, "last_updated_at": NOW - 120},
}

COINBASE_EXCHANGE = "api.exchange.coinbase.com"
ER_API_HOST = "open.er-api.com"
COINBASE_TABLE = "api.coinbase.com"
CBR_HOST = "www.cbr-xml-daily.ru"
COINGECKO_HOST = "api.coingecko.com"


class FakeApi:
    """Routes every upstream call, and records what was asked for.

    `down` holds hosts that answer 503; `bodies` overrides one host's payload.
    Both are plain attributes, so a test can change them between calls to
    simulate a provider that fails only after the first success.
    """

    def __init__(self, down=(), bodies=None):
        self.down = set(down)
        self.bodies = dict(bodies or {})
        self.calls: list[str] = []

    def service(self, **kwargs) -> RateService:
        return RateService(transport=httpx.MockTransport(self._handle), **kwargs)

    def hosts_called(self) -> set[str]:
        return set(self.calls)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.calls.append(host)
        if host in self.down:
            return httpx.Response(503)
        if host in self.bodies:
            return httpx.Response(200, json=self.bodies[host])
        if host == COINBASE_EXCHANGE:
            code = path.split("/")[2].split("-")[0]
            return httpx.Response(200, json=TICKER[code] if path.endswith("ticker") else STATS[code])
        if host == ER_API_HOST:
            return httpx.Response(200, json=ER_API)
        if host == COINBASE_TABLE:
            return httpx.Response(200, json=CB_TABLE)
        if host == CBR_HOST:
            return httpx.Response(200, json=CBR)
        if host == COINGECKO_HOST:
            return httpx.Response(200, json=COINGECKO)
        return httpx.Response(404)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()
