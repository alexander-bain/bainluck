"""May this provider's start time replace the one already on the row? (#8653)

**SHIP: a game's page and card show the real first-pitch time, not a schedule
StatPal never updated.** (Pillar: TRUTH.)

The registry already owns the one start-time authority rule —
:func:`app.services.event_registry.commence_time_write_authorized` (#2018),
``odds_api 1 < statpal 2 < espn 3 < mlb_schedule_repair 4`` — and its docstring
says every rail writing ``events.commence_time`` is meant to share it. Two rails
did not:

* ``espn_helpers`` corrected a row's start only when
  ``commence_time_source != "statpal"`` — ESPN deferring to StatPal, the ranking
  upside down;
* ``statpal_sync``'s schedule pass overwrote any start more than five minutes
  off, with no authority check at all, and stamped ``statpal`` — which then
  locked ESPN out through the first rail.

So a StatPal schedule that never heard about a reschedule won every argument.
Measured on production 2026-09-25 16:50Z: Cubs @ Red Sox doubleheader game 2
(``15318545``) served 22:05Z while MLB (``824706``) said 21:35Z and ESPN
(``401817074``) 21:30Z — the page told a reader first pitch was half an hour
later than it was. Of the 7 rows then holding a ``statpal`` start AND an
``espn_id`` (now-1d .. now+10d), 6 agreed with ESPN to the minute; this was the
seventh, and ESPN was right.

This module adds no rule. It is the one call every such rail makes, so the
ranking they obey is the registry's and cannot drift from it. Three more ESPN
start-time rails carried the same "StatPal outranks ESPN" refusal, each citing
another as its source, and now ask here too: ``anchor_schedule``'s clause 4
(``REFUSED_OUTRANKED``), ``espn_sync``'s unstarted-fixture recovery (#6280) and
``espn_tennis_anchor.authority_write``.

**A provider may still revise its own stamp** (``same_record_revision`` when the
row's stamp names the incoming provider). That is what both rails did before for
their own values, and refusing it would freeze whatever a provider published
first — the placeholder problem q066b exists for.
"""

from __future__ import annotations

from typing import Optional


def provider_may_set_start(
    current_source: Optional[str], incoming_source: str
) -> bool:
    """True when ``incoming_source`` may overwrite a start stamped ``current_source``.

    ``current_source`` is the row's ``commence_time_source`` (``None`` for a row
    that never recorded one — which confers no immunity, per the registry rule).
    """
    # Imported here, not at module level: `event_registry` imports
    # `espn_helpers` at import time, and `espn_helpers` imports this module, so a
    # top-level import would close the cycle on a half-initialised module.
    from app.services.event_registry import commence_time_write_authorized

    authorized, _reason = commence_time_write_authorized(
        current_source,
        incoming_source,
        same_record_revision=current_source == incoming_source,
    )
    return authorized
