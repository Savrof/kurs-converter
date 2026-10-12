import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.rates import RateService

NOW = int(datetime.now(timezone.utc).timestamp())
TICKER = {"BTC": {"price": "111800.25", "time": "2026-10-12T05:30:00Z"},
          "ETH": {"price": "4120.50", "time": "2026-10-12T05:30:00Z"}}
STATS = {"BTC": {"open": "110000", "last": "111800"}, "ETH": {"open": "4200", "last": "4120"}}
ER_API = {"result": "success", "time_last_update_unix": NOW - 7 * 3600, "rates": {"RUB": 84.4, "IDR": 16400.0}}
CB_TABLE = {"data": {"currency": "USD", "rates": {"RUB": "85.03", "IDR": "16420"}}}
CBR = {"Date": "2026-10-12T11:30:00+03:00", "Valute": {"USD": {"Value": 83.9512, "Previous": 84.21}}}
COINGECKO = {
    "bitcoin": {"usd": 111000, "usd_24h_change": 1.1, "last_updated_at": NOW - 120},
    "ethereum": {"usd": 4100, "usd_24h_change": -0.9, "last_updated_at": NOW - 120},
}


def make_service(down=()):
    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host in down:
            return httpx.Response(503)
        if host == "api.exchange.coinbase.com":
            code = path.split("/")[2].split("-")[0]
            return httpx.Response(200, json=TICKER[code] if path.endswith("ticker") else STATS[code])
        if host == "open.er-api.com":
            return httpx.Response(200, json=ER_API)
        if host == "api.coinbase.com":
            return httpx.Response(200, json=CB_TABLE)
        if host == "www.cbr-xml-daily.ru":
            return httpx.Response(200, json=CBR)
        if host == "api.coingecko.com":
            return httpx.Response(200, json=COINGECKO)
        return httpx.Response(404)

    return RateService(transport=httpx.MockTransport(handler))


def test_primary_sources_and_their_timestamps():
    snap = asyncio.run(make_service().get())
    assert snap.rates["RUB"] == pytest.approx(84.4)          # dated er-api, not the undated table
    assert snap.rates["BTC"] == pytest.approx(1 / 111800.25)
    assert snap.meta["RUB"].source == "open.er-api.com"
    assert snap.meta["BTC"].source == "Coinbase Exchange"
    # every primary rate carries the provider's own time
    assert all(snap.meta[c].as_of is not None for c in ("RUB", "IDR", "BTC", "ETH"))
    assert snap.change_24h["BTC"] == pytest.approx(1.64)


def test_official_rub_is_reported_separately():
    snap = asyncio.run(make_service().get())
    assert snap.official["RUB"]["rate"] == pytest.approx(83.9512)
    assert snap.official["RUB"]["source"] == "ЦБ РФ"
    assert snap.official["RUB"]["as_of"].startswith("2026-10-12")
    assert snap.rates["RUB"] != snap.official["RUB"]["rate"]  # market and official stay distinct


def test_undated_coinbase_table_is_only_a_fallback():
    snap = asyncio.run(make_service(down={"open.er-api.com"}).get())
    assert snap.rates["RUB"] == pytest.approx(85.03)
    assert snap.meta["RUB"].source == "Coinbase"
    assert snap.meta["RUB"].as_of is None  # reported as unknown rather than invented


def test_coingecko_fallback_for_crypto():
    snap = asyncio.run(make_service(down={"api.exchange.coinbase.com"}).get())
    assert snap.rates["BTC"] == pytest.approx(1 / 111000)
    assert snap.meta["BTC"].source == "CoinGecko"
    assert snap.meta["BTC"].as_of is not None


def test_official_rate_stands_in_when_no_market_source_has_rub():
    """er-api and the Coinbase table both answer, but neither carries RUB."""
    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "api.exchange.coinbase.com":
            code = path.split("/")[2].split("-")[0]
            return httpx.Response(200, json=TICKER[code] if path.endswith("ticker") else STATS[code])
        if host == "open.er-api.com":
            return httpx.Response(200, json={**ER_API, "rates": {"IDR": 16400.0}})
        if host == "api.coinbase.com":
            return httpx.Response(200, json={"data": {"rates": {"IDR": "16420"}}})
        if host == "www.cbr-xml-daily.ru":
            return httpx.Response(200, json=CBR)
        return httpx.Response(404)

    snap = asyncio.run(RateService(transport=httpx.MockTransport(handler)).get())
    assert snap.rates["RUB"] == pytest.approx(83.9512)
    assert snap.meta["RUB"].source == "ЦБ РФ (официальный)"


def test_incomplete_set_is_an_error_not_a_guess():
    service = make_service(down={"open.er-api.com", "api.coinbase.com", "www.cbr-xml-daily.ru"})
    with pytest.raises(RuntimeError, match="No rate for"):
        asyncio.run(service.get())


def test_fetched_at_is_not_presented_as_the_data_time():
    snap = asyncio.run(make_service().get())
    payload = snap.to_dict()
    assert "fetched_at" in payload and "updated_at" not in payload
    assert payload["meta"]["RUB"]["as_of"] != payload["fetched_at"]
