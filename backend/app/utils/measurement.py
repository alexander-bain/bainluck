"""Best-effort server-side GA4 emission (Measurement Protocol).

The backend has a read-only GA4 Data API client (`services/ga4_api.py`) but no way
to EMIT events. Some funnel steps only exist server-side — notably the Morning
Digest's ``push_sent`` (measurement_spec.md §2: "the 7:05 sends measurable from
day one"). This module adds a single, deliberately minimal, non-blocking emitter.

Config (both required to actually send; else it no-ops with a LOUD warning so it
never silently swallows events — the GITHUB_TOKEN-unset lesson):
  * ``GA4_MEASUREMENT_ID`` — defaults to the public web stream id ``G-CY59Q6K975``.
  * ``GA4_MP_API_SECRET`` — created in GA4 admin (Data Streams → Measurement
    Protocol API secrets) and set in Heroku config. Absent today → logs + returns
    False; the code is forward-compatible for when the secret lands.

Best-effort by contract: a bounded timeout + catch-all, so a slow/failing GA
endpoint can never hang or fail the calling task (gotcha #38/#39 — never let a
network call freeze a task).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_GA4_ENDPOINT = "https://www.google-analytics.com/mp/collect"
_DEFAULT_MEASUREMENT_ID = "G-CY59Q6K975"  # public web stream id (frontend config)


async def emit_ga4_event(
    name: str,
    params: dict,
    *,
    client_id: str = "server",
    timeout: float = 5.0,
) -> bool:
    """Emit one server-side GA4 event via the Measurement Protocol.

    Returns True iff GA accepted the hit (2xx). No-ops (returns False) with a
    warning when ``GA4_MP_API_SECRET`` is unset, and swallows all network errors
    (returns False) so the caller is never blocked. ``client_id`` is required by
    the protocol; server-origin events use a stable synthetic id.
    """
    api_secret = os.getenv("GA4_MP_API_SECRET")
    measurement_id = os.getenv("GA4_MEASUREMENT_ID", _DEFAULT_MEASUREMENT_ID)
    if not api_secret:
        logger.warning(
            "GA4_MP_API_SECRET unset — server-side GA4 event '%s' NOT emitted "
            "(params=%s). Create the Measurement Protocol secret in GA4 admin and "
            "set it in Heroku config to start the funnel.",
            name,
            params,
        )
        return False

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                _GA4_ENDPOINT,
                params={"measurement_id": measurement_id, "api_secret": api_secret},
                json={
                    "client_id": client_id,
                    "events": [{"name": name, "params": params}],
                },
            )
        if resp.status_code >= 300:
            logger.warning(
                "GA4 MP emit '%s' returned HTTP %s", name, resp.status_code
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; never propagate
        logger.warning("GA4 MP emit '%s' failed: %s", name, exc)
        return False
