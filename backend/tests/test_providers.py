"""Which provider each rate comes from, and whether its timestamp is real.

The order matters: a dated source always beats an undated one, and the Bank of
Russia rate stays a separate, labelled figure rather than quietly becoming
"the" rate.
"""

import asyncio

import pytest

from conftest import CBR_HOST, COINBASE_EXCHANGE, COINBASE_TABLE, COINGECKO_HOST, ER_API_HOST


def snapshot(api, down=()):
    api.down = set(down)
    return asyncio.run(api.service().get())


def test_primary_sources_and_their_timestamps(api):
    snap = snapshot(api)
    assert snap.rates["RUB"] == pytest.approx(84.4)          # dated er-api, not the undated table
    assert snap.rates["BTC"] == pytest.approx(1 / 111800.25)
    assert snap.meta["RUB"].source == "open.er-api.com"
    assert snap.meta["BTC"].source == "Coinbase Exchange"
    # every primary rate carries the provider's own time
    assert all(snap.meta[c].as_of is not None for c in ("RUB", "IDR", "BTC", "ETH"))
    assert snap.change_24h["BTC"] == pytest.approx(1.64)


def test_official_rub_is_reported_separately(api):
    snap = snapshot(api)
    assert snap.official["RUB"]["rate"] == pytest.approx(83.9512)
    assert snap.official["RUB"]["source"] == "ЦБ РФ"
    assert snap.official["RUB"]["as_of"].startswith("2026-10-12")
    assert snap.rates["RUB"] != snap.official["RUB"]["rate"]  # market and official stay distinct


def test_undated_coinbase_table_is_only_a_fallback(api):
    snap = snapshot(api, down={ER_API_HOST})
    assert snap.rates["RUB"] == pytest.approx(85.03)
    assert snap.meta["RUB"].source == "Coinbase"
    assert snap.meta["RUB"].as_of is None  # reported as unknown rather than invented


def test_an_er_api_error_payload_counts_as_a_failure(api):
    """200 OK with result="error" must not be read as rates."""
    api.bodies[ER_API_HOST] = {"result": "error", "error-type": "quota-reached"}
    snap = snapshot(api)
    assert snap.meta["RUB"].source == "Coinbase"


def test_coingecko_fallback_for_crypto(api):
    snap = snapshot(api, down={COINBASE_EXCHANGE})
    assert snap.rates["BTC"] == pytest.approx(1 / 111000)
    assert snap.meta["BTC"].source == "CoinGecko"
    assert snap.meta["BTC"].as_of is not None
    assert snap.change_24h["BTC"] == pytest.approx(1.1)


def test_official_rate_stands_in_when_no_market_source_has_rub(api):
    """Both fiat sources answer, but neither carries RUB."""
    api.bodies[ER_API_HOST] = {"result": "success", "rates": {"IDR": 16400.0}}
    api.bodies[COINBASE_TABLE] = {"data": {"rates": {"IDR": "16420"}}}
    snap = snapshot(api)
    assert snap.rates["RUB"] == pytest.approx(83.9512)
    assert snap.meta["RUB"].source == "ЦБ РФ (официальный)"


def test_no_fiat_source_is_an_error_not_a_guess(api):
    with pytest.raises(RuntimeError, match="No rate for"):
        snapshot(api, down={ER_API_HOST, COINBASE_TABLE, CBR_HOST})


def test_no_crypto_source_is_an_error_not_a_guess(api):
    with pytest.raises(RuntimeError, match="No rate for"):
        snapshot(api, down={COINBASE_EXCHANGE, COINGECKO_HOST})


def test_fetched_at_is_not_presented_as_the_data_time(api):
    payload = snapshot(api).to_dict()
    assert "fetched_at" in payload and "updated_at" not in payload
    assert payload["meta"]["RUB"]["as_of"] != payload["fetched_at"]
