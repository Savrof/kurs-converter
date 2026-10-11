import asyncio

import httpx
import pytest

from app.rates import RateService

COINBASE = {"data": {"currency": "USD", "rates": {
    "RUB": "81.9", "IDR": "16420", "BTC": "0.00000894", "ETH": "0.000242", "EUR": "0.92",
}}}
STATS = {"BTC": {"open": "110000", "last": "111800"}, "ETH": {"open": "4200", "last": "4120"}}
ER_API = {"result": "success", "rates": {"RUB": 80.0, "IDR": 16000.0}}
COINGECKO = {"bitcoin": {"usd": 100000, "usd_24h_change": 1.0}, "ethereum": {"usd": 4000, "usd_24h_change": -1.0}}


def make_service(down=()):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        calls.append(host)
        if host in down:
            return httpx.Response(503)
        if host == "api.coinbase.com":
            return httpx.Response(200, json=COINBASE)
        if host == "api.exchange.coinbase.com":
            return httpx.Response(200, json=STATS[path.split("/")[2].split("-")[0]])
        if host == "open.er-api.com":
            return httpx.Response(200, json=ER_API)
        if host == "api.coingecko.com":
            return httpx.Response(200, json=COINGECKO)
        return httpx.Response(404)

    return RateService(transport=httpx.MockTransport(handler)), calls


def test_coinbase_alone_covers_everything():
    service, calls = make_service()
    snap = asyncio.run(service.get())
    assert snap.sources == ["coinbase.com"]
    assert snap.rates["RUB"] == pytest.approx(81.9)
    assert snap.rates["BTC"] == pytest.approx(0.00000894)
    assert snap.change_24h["BTC"] == pytest.approx(1.64)
    assert snap.change_24h["ETH"] == pytest.approx(-1.9)
    assert "open.er-api.com" not in calls and "api.coingecko.com" not in calls


def test_falls_back_when_coinbase_is_down():
    service, _ = make_service(down={"api.coinbase.com", "api.exchange.coinbase.com"})
    snap = asyncio.run(service.get())
    assert snap.sources == ["open.er-api.com", "coingecko.com"]
    assert snap.rates["RUB"] == pytest.approx(80.0)
    assert snap.rates["BTC"] == pytest.approx(1 / 100000)
    assert snap.change_24h["BTC"] == pytest.approx(1.0)


def test_only_missing_currency_is_filled_from_fallback():
    COINBASE["data"]["rates"].pop("IDR")
    try:
        service, _ = make_service()
        snap = asyncio.run(service.get())
    finally:
        COINBASE["data"]["rates"]["IDR"] = "16420"
    assert snap.rates["RUB"] == pytest.approx(81.9)      # still Coinbase
    assert snap.rates["IDR"] == pytest.approx(16000.0)   # from er-api
    assert snap.sources == ["coinbase.com", "open.er-api.com"]
