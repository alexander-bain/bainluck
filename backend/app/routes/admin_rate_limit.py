"""Admin read-out of rate-limit configuration that is otherwise invisible (#4635).

Today this carries one thing: whether D70's trusted-address allowlist is actually
granting anybody the 600/min ceiling. That question had no answer from outside the
dyno, and the absence cost the fleet ≥17 hours of silently throttling itself on
2026-09-10 — see `app.utils.rate_limit.trusted_allowlist_state` for the measurement
and for why the configured count alone would not have said so.

ADMIN, NOT PUBLIC, DELIBERATELY. #4635: a public surface advertises that an
allowlist exists, which is an invitation to probe for its contents. Auth is applied
at the router (``ADMIN_ROUTER_DEPENDENCIES`` in ``main.py``); this module is
read-only and holds no write path, so it takes no destructive token.
"""

import logging

from fastapi import APIRouter

from app.utils.rate_limit import trusted_allowlist_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/rate-limit", tags=["admin-rate-limit"])


@router.get("/trusted-allowlist")
async def get_trusted_allowlist_state() -> dict:
    """Is D70's trusted allowlist armed, and is it matching anything?

    Returns counts and a verdict. **It never returns an address**, and there is no
    parameter that would make it — the allowlist's value identifies an operator's
    network, and the rule that keeps it out of tracked files keeps it out of here.

    ``verdict`` is the whole answer; the counts are there to be argued with:

    * ``unset`` — nothing configured. The default, not a defect.
    * ``armed_no_traffic_yet`` — configured, but this process has served no
      non-admin request since boot. Ask again once it has.
    * ``armed_and_matching`` — configured and observed granting the ceiling.
    * ``armed_but_matching_nothing`` — configured, requests arriving, zero matches.
      Something that used to match has stopped, or never did.

    Scoped to the process that answers, which is named in ``dyno``: the counters
    are in memory, so a fleet with several web dynos gives several answers and each
    is true about its own. ``observed_seconds`` is how long that process has been
    counting — a zero over four seconds says nothing, a zero over four hours says
    a great deal.
    """
    return trusted_allowlist_state()
