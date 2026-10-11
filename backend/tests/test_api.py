from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.rates import RateSnapshot, convert

FAKE = RateSnapshot(
    rates={"USD": 1.0, "RUB": 80.0, "IDR": 16000.0, "BTC": 1 / 100_000, "ETH": 1 / 4_000},
    change_24h={"BTC": 1.5, "ETH": -0.7},
    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    sources=["test"],
)


@pytest.fixture
def client(monkeypatch):
    async def fake_get(force=False):
        return FAKE

    monkeypatch.setattr(main.service, "get", fake_get)
    return TestClient(main.app)


def test_convert_math():
    assert convert(FAKE.rates, 1, "BTC", "RUB") == pytest.approx(8_000_000)
    assert convert(FAKE.rates, 1000, "RUB", "IDR") == pytest.approx(200_000)
    assert convert(FAKE.rates, 1, "ETH", "BTC") == pytest.approx(0.04)
    assert convert(FAKE.rates, 100, "USD", "RUB") == pytest.approx(8_000)


def test_rates_endpoint(client):
    body = client.get("/api/rates").json()
    assert body["base"] == "USD"
    assert set(body["rates"]) >= {"RUB", "USD", "IDR", "BTC", "ETH"}


def test_convert_endpoint(client):
    body = client.get("/api/convert", params={"amount": 2, "from": "eth", "to": "rub"}).json()
    assert body["result"] == pytest.approx(640_000)


def test_convert_usd(client):
    body = client.get("/api/convert", params={"amount": 0.5, "from": "BTC", "to": "usd"}).json()
    assert body["result"] == pytest.approx(50_000)


def test_unsupported_currency(client):
    r = client.get("/api/convert", params={"amount": 1, "from": "EUR", "to": "RUB"})
    assert r.status_code == 400
