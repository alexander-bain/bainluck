"""The contract between the Oscars request path and the task that writes its previews.

`GET /api/oscars` used to generate its six category previews and its movers summary
inline: `app/services/llm.py` is synchronous end to end (35 of 35 helpers), so each
call parked the event loop of the worker process serving the request, and the
`asyncio.gather` around them could not interleave a single one. Measured cost on
production 2026-09-08: **10.83s cold**, against a >2s investigate threshold — paid
not only by the caller but by every other request routed to that process.

So the generation moved to `app/tasks/oscars_previews.py` and the request path only
READS the key that task writes (the house rule: never run LLM calls inside a GET).
This module holds the two sides' shared vocabulary — the key, the cadence and the
envelope shape — so neither can drift from the other.

TTL is deliberately **twice** the refresh interval, following the golf-commentary
precedent: if the beat stops, the previews disappear within one interval instead of
leaving text that quotes a probability the page no longer shows. These blurbs name
percentages ("leading the pack at 27.2%"), so a frozen one is not merely stale, it
is wrong.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# One JSON envelope for all previews, rather than a key per category: the page
# renders them together, so a partial set is a worse answer than a whole one.
PREVIEWS_REDIS_KEY = "bainluck:precompute:oscars_previews"

# Hourly. The blurbs are derived from 24h movement, so this is far more often than
# the content can meaningfully change — the cost is six gpt-4o-mini calls an hour,
# and the benefit is that "generated_at" is never a surprise.
#
# The beat itself is a `crontab(minute="7")`, not this number: an hourly interval
# beat joins the background INTERVAL FLOOR, which the settlement-sweep guard
# reserves for continuous (<=180s) beats. The two are kept in agreement by
# `test_the_cadence_and_the_ttl_still_agree_after_the_crontab_move`, because a
# coupling nothing checks is a coupling that drifts.
PREVIEWS_REFRESH_SECONDS = 3600

# See the module docstring: a stopped beat self-clears rather than freezing.
PREVIEWS_TTL_SECONDS = PREVIEWS_REFRESH_SECONDS * 2


def build_previews_envelope(previews: dict[str, str]) -> str:
    """Serialize the published envelope. Stamps its own age at write time."""
    return json.dumps(
        {
            "previews": previews,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def read_published_previews(rc) -> tuple[dict[str, str], str | None]:
    """Read the published previews. Returns ``({}, None)`` for every failure.

    Absence is a normal state, not an error: before the first run of the beat, and
    for an interval after it stops, there are simply no previews and the page
    renders without them. A Redis outage degrades to the same place — the one thing
    this must never do is raise into a request handler for a decoration.

    ``rc`` is an **async** client (``get_async_redis_client``), and that is the whole
    point of this being a coroutine. The synchronous client is bounded at 5s
    (gotcha #39) but a bound is not a yield: a sync ``get`` on the request path parks
    the event loop for its round trip, which is the exact class of defect this ship
    exists to remove. Trading six 1.8s LLM calls for one 2ms loop-block would still
    leave the loop-blocking pattern in the handler for the next reader to copy.
    """
    try:
        raw = await rc.get(PREVIEWS_REDIS_KEY) if rc is not None else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Oscars previews read failed: %s", exc)
        return {}, None

    # No client, no key, or an expired one all land here — the same answer, because
    # to a reader they are the same thing: no previews today.
    if not raw:
        return {}, None

    try:
        parsed = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, AttributeError) as exc:
        logger.warning("Oscars previews envelope is not JSON: %s", exc)
        return {}, None

    if not isinstance(parsed, dict):
        return {}, None

    previews = parsed.get("previews")
    if not isinstance(previews, dict):
        return {}, None

    # Only str->str survives: the response contract is a map of text blurbs, and a
    # malformed entry should cost its own preview, never the whole page.
    clean = {
        k: v for k, v in previews.items() if isinstance(k, str) and isinstance(v, str)
    }
    generated_at = parsed.get("generated_at")
    return clean, generated_at if isinstance(generated_at, str) else None
