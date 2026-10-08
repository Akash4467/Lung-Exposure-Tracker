"""Place search through our server: cached, Nominatim first, Photon when it fails."""

import httpx
import pytest

from lung.services.context import AppContext

from .test_api_app import _session

pytestmark = pytest.mark.integration


async def test_search_is_cached(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)
    r = await client.get(
        "/v1/geo/search", params={"q": "gaur city", "lat": 28.6, "lon": 77.2}, headers=h
    )
    assert r.status_code == 200, r.text
    (place,) = r.json()["places"]
    assert place == {
        "label": "Gaur City",
        "detail": "Ghaziabad, Uttar Pradesh",
        "lat": 28.61,
        "lon": 77.43,
    }
    again = await client.get(
        "/v1/geo/search", params={"q": "  Gaur   City ", "lat": 28.6, "lon": 77.2}, headers=h
    )
    assert again.json()["places"] == [place]
    assert ctx.geocoder.calls == ["nominatim:gaur city"]  # type: ignore[union-attr]  # cached


async def test_photon_when_nominatim_fails(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)
    ctx.geocoder.nominatim_down = True  # type: ignore[union-attr]
    r = await client.get("/v1/geo/search", params={"q": "goa beach"}, headers=h)
    assert r.json()["places"][0]["detail"] == "from Photon"


async def test_short_queries_and_reverse(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)
    assert (await client.get("/v1/geo/search", params={"q": "go"}, headers=h)).json() == {
        "places": []
    }
    r = await client.get("/v1/geo/reverse", params={"lat": 28.6352, "lon": 77.0946}, headers=h)
    assert r.json()["place"]["label"] == "Jail Road"
    assert (await client.get("/v1/geo/search", params={"q": "goa"})).status_code == 401
