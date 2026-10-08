"""Checks the real external providers with the keys in .env. Never prints a key.

    uv run python -m lung.devtools.smoke                     # read-only checks
    uv run python -m lung.devtools.smoke --email-to you@x.in # also sends one real test email

Open-Meteo: one hourly pull for Delhi.
OpenRouteService: one real route (Connaught Place -> Noida Sector 62), with road types.
Brevo: key valid, verified senders listed, MAIL_FROM checked, optional test email.
"""

import argparse
import asyncio
from collections import Counter
from typing import Any

import httpx

from lung.domain.geo import LatLon
from lung.integrations.brevo import BrevoMailer
from lung.integrations.open_meteo import OpenMeteoClient
from lung.integrations.openrouteservice import OpenRouteServiceClient
from lung.services.mailer import verification_email
from lung.settings import get_settings

HOME = LatLon(28.6315, 77.2167)  # Connaught Place
OFFICE = LatLon(28.6270, 77.3727)  # Noida Sector 62

results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


async def check_open_meteo(http: httpx.AsyncClient) -> None:
    s = get_settings()
    try:
        om = OpenMeteoClient(http, s.open_meteo_air_base, s.open_meteo_weather_base, 1, 2)
        rows = await om.hourly(HOME.lat, HOME.lon)
        pm = [r.pm25 for r in rows]
        report(
            "open-meteo",
            len(rows) > 48,
            f"{len(rows)} hours, PM2.5 {min(pm):.0f}-{max(pm):.0f} µg/m³, "
            f"wind on {sum(r.wind_speed is not None for r in rows)} hours",
        )
    except Exception as e:
        report("open-meteo", False, f"{type(e).__name__}: {e}")


async def check_ors(http: httpx.AsyncClient) -> None:
    s = get_settings()
    if not s.ors_api_key:
        report(
            "openrouteservice", False, "ORS_API_KEY not set (routes fall back to a straight line)"
        )
        return
    try:
        ors = OpenRouteServiceClient(http, s.ors_base, s.ors_api_key.get_secret_value())
        route = await ors.route(HOME, OFFICE, "two_wheeler", s.route_sample_km, s.route_max_points)
        classes = Counter(x.road_class for x in route.samples)
        report(
            "openrouteservice",
            bool(route.samples),
            f"{route.distance_km:.1f} km by road, {len(route.samples)} samples, "
            f"road types {dict(classes)}",
        )
    except httpx.HTTPStatusError as e:
        report(
            "openrouteservice", False, f"HTTP {e.response.status_code} (403 = bad key, 429 = quota)"
        )
    except Exception as e:
        report("openrouteservice", False, f"{type(e).__name__}: {e}")


async def check_brevo(http: httpx.AsyncClient, email_to: str | None) -> None:
    s = get_settings()
    if not s.brevo_api_key:
        report("brevo", False, "BREVO_API_KEY not set")
        return
    headers = {"api-key": s.brevo_api_key.get_secret_value(), "accept": "application/json"}
    base = s.brevo_base.rstrip("/")
    try:
        acct = await http.get(f"{base}/v3/account", headers=headers)
        if acct.status_code == 401:
            report("brevo key", False, "rejected (401): check or regenerate the key")
            return
        acct.raise_for_status()
        a: dict[str, Any] = acct.json()
        plans = ", ".join(p.get("type", "?") for p in a.get("plan", []))
        report("brevo key", True, f"valid; plan: {plans or 'unknown'}")

        snd = await http.get(f"{base}/v3/senders", headers=headers)
        snd.raise_for_status()
        senders = snd.json().get("senders", [])
        active = [x["email"] for x in senders if x.get("active")]
        report(
            "brevo senders",
            bool(active),
            f"verified: {active or 'none'}"
            + ("" if active else " (verify one in Brevo: Senders, domains & dedicated IPs)"),
        )
        report(
            "MAIL_FROM",
            s.mail_from in active,
            f"{s.mail_from!r} "
            + (
                "is verified"
                if s.mail_from in active
                else "is not a verified sender: set MAIL_FROM in .env"
            ),
        )
    except Exception as e:
        report("brevo", False, f"{type(e).__name__}: {e}")
        return

    if email_to:
        try:
            subject, body = verification_email("123456", 15)
            mailer = BrevoMailer(
                http,
                s.brevo_base,
                s.brevo_api_key.get_secret_value(),
                s.mail_from,
                s.mail_from_name,
            )
            await mailer.send(email_to, f"[smoke test] {subject}", body)
            report("brevo send", True, f"test email accepted for {email_to}; check the inbox")
        except httpx.HTTPStatusError as e:
            report("brevo send", False, f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            report("brevo send", False, f"{type(e).__name__}: {e}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email-to", help="send one real test email to this address")
    args = parser.parse_args()
    async with httpx.AsyncClient(timeout=20) as http:
        await asyncio.gather(check_open_meteo(http), check_ors(http))
        await check_brevo(http, args.email_to)
    failed = [n for n, ok, _ in results if not ok]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} passed"
        + (f"; failed: {', '.join(failed)}" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
