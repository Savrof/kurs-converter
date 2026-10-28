"""What the service layer promises on top of the providers: a cache that
spares the upstreams, and last-known rates rather than an error when a refresh
fails. Both matter to a caller, and neither was covered before."""

import asyncio

import pytest

from conftest import CBR_HOST, COINBASE_EXCHANGE, COINBASE_TABLE, COINGECKO_HOST, ER_API_HOST

ALL_HOSTS = {COINBASE_EXCHANGE, ER_API_HOST, COINBASE_TABLE, CBR_HOST, COINGECKO_HOST}


def test_second_call_within_ttl_does_not_touch_the_network(api):
    service = api.service(ttl=3600)
    asyncio.run(service.get())
    api.calls.clear()
    asyncio.run(service.get())
    assert api.calls == []


def test_force_refetches_even_inside_the_ttl(api):
    service = api.service(ttl=3600)
    asyncio.run(service.get())
    api.calls.clear()
    asyncio.run(service.get(force=True))
    assert ER_API_HOST in api.hosts_called()


def test_expired_ttl_refetches(api):
    service = api.service(ttl=0)
    asyncio.run(service.get())
    api.calls.clear()
    asyncio.run(service.get())
    assert ER_API_HOST in api.hosts_called()


def test_concurrent_callers_share_one_refresh(api):
    service = api.service(ttl=3600)

    async def both():
        return await asyncio.gather(service.get(), service.get(), service.get())

    snaps = asyncio.run(both())
    assert api.calls.count(ER_API_HOST) == 1
    assert snaps[0] is snaps[1] is snaps[2]


def test_a_failed_refresh_serves_the_last_known_rates(api):
    service = api.service(ttl=0)
    first = asyncio.run(service.get())

    api.down = set(ALL_HOSTS)
    again = asyncio.run(service.get())

    assert again is first  # the caller gets rates, not an exception


def test_a_failed_first_refresh_raises(api):
    api.down = set(ALL_HOSTS)
    with pytest.raises(Exception):
        asyncio.run(api.service().get())
