"""Has Polymarket's own EVENT record said this match is over? (#3017)

A rung beside the venue-settlement rung in
``espn_sync._transition_event_statuses_impl``, for the one population that has
no better witness: a row with no ESPN id and no StatPal fixture id, carried on
the live board only by Polymarket markets.

## The witness

Gamma's ``/events/{id}`` record for a sports fixture carries a sports-data block
beside the markets: ``gameId``, ``live``, ``ended``, ``period``, ``score``,
``finishedTimestamp``. It is id-keyed through the market we already store
(``group_id = 'polymarket:<event id>'``), so reading it is not name-and-time
absorption (ruling 048) — the venue is describing the fixture it listed.

It speaks EARLIER than the settlement witness. Measured 2026-09-24 14:2xZ on
shopper pass 0039's specimens: every moneyline leg was still ``closed: false``
while the event record already read

* ``1069107`` China PR vs. Maldives — ``ended: true``, ``period: VFT``, ``3-0``;
* ``1004365`` Korea Republic vs. Ecuador — ``ended: true``, ``VFT``, ``3-0``;
* ``1004368`` China PR vs. Palestine — ``ended: true``, ``period: CAN``,
  ``finishedTimestamp`` 00:00Z, eleven hours BEFORE the 11:35Z kickoff. The
  match was cancelled, and our page read **LIVE 71%**.

Until then the only thing that takes such a row off the board is the staleness
arm, at the unobserved bound plus half an hour (3.0h for soccer).

## What a ruling here writes, and what it does not

``suspended`` — the same word, and the same reasons, as
``SUSPEND_ON_VENUE_SETTLEMENT_SQL``. It is the one terminal-ish state that is
honest for BOTH a finished match and a cancelled one: the page reads "No result
reported" rather than a Final, and nothing is graded off NULL scores. The score
in the record is not written — it is the venue's feed, not a result of ours, and
a cancelled match's ``0-0`` is exactly the value that must never be printed as
one. ``completed_at`` is not written either: a cancelled match's
``finishedTimestamp`` precedes its kickoff and would break gotcha #46.

## The refusals, each for a way of being wrong

* **``ended`` must be the literal ``True``.** Absent fields are the common case
  (a week-old fixture can still read ``period: NS``), and absence says nothing.
* **``live`` must not be ``True``.** A record that says both is contradicting
  itself; the conservative reading is that play is on.
* **A ``gameId`` must be present.** It is what marks the record as backed by a
  sports-data feed at all; the flags on a record without one are not a feed's.
* **``finishedTimestamp`` must be present and not in the future.** The esports
  records read ``ended: true`` per MAP (``period: '2/3'``) with no finish time;
  requiring one keeps that whole shape out — the same derivative-settles-the-
  match class the settlement rung's conjunct 1 was written for.
* **The record's ``startTime`` must be within** :data:`START_AGREEMENT_WINDOW`
  **of our kickoff.** A market attached to the wrong fixture (last season's, a
  sibling round's) is a matching defect; this rail must not amplify it into a
  live match taken off the board.
* **Every sports record on the row must agree.** A row carries several Gamma
  events for one fixture (the match, "More Markets", corners). If any of them
  says ``live``, or has not ended, or names a different ``gameId``, the row is
  held: the venue has not finished telling one story.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from app.utils.event_completion import EVENT_SUSPENDED

#: How far the Gamma record's ``startTime`` may sit from our ``commence_time``
#: and still describe the same fixture. Wide enough for a venue-stamped kickoff
#: that drifts (gotcha #14 lives on this population), narrow enough that no
#: two fixtures of one pairing on consecutive days can both pass.
START_AGREEMENT_WINDOW = timedelta(hours=12)

#: A finish time a few minutes ahead of our clock is skew, not a prophecy.
FINISH_CLOCK_SKEW = timedelta(minutes=5)

GROUP_ID_PREFIX = "polymarket:"

_GAMMA_EVENT_ID = re.compile(r"^[0-9]+$")


def gamma_event_id_from_group(group_id) -> Optional[str]:
    """``'polymarket:1004368'`` → ``'1004368'``; anything else → ``None``.

    Numeric only: ``/events?id=`` addresses a numeric event id, and a group key
    of any other shape is one this rail has no standing to read.
    """
    if not isinstance(group_id, str) or not group_id.startswith(GROUP_ID_PREFIX):
        return None
    tail = group_id[len(GROUP_ID_PREFIX) :].strip()
    return tail if _GAMMA_EVENT_ID.match(tail) else None


def _parse_instant(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def gamma_record_is_sports(payload) -> bool:
    """Does this Gamma event carry a sports-data block at all?"""
    return isinstance(payload, dict) and payload.get("gameId") not in (None, "", 0)


def gamma_record_says_ended(payload, *, commence_time, now) -> bool:
    """Does ONE Gamma event record say the fixture at ``commence_time`` is over?

    Pure over the payload dict. See the module docstring for why each refusal
    is here.
    """
    if not gamma_record_is_sports(payload):
        return False
    if payload.get("ended") is not True:
        return False
    if payload.get("live") is True:
        return False
    finished = _parse_instant(payload.get("finishedTimestamp"))
    if finished is None or commence_time is None or now is None:
        return False
    if finished > _aware(now) + FINISH_CLOCK_SKEW:
        return False
    start = _parse_instant(payload.get("startTime"))
    if start is None:
        return False
    return abs(start - _aware(commence_time)) <= START_AGREEMENT_WINDOW


def row_verdict(payloads: Iterable[dict], *, commence_time, now) -> Optional[str]:
    """Rule one event row from every Gamma record its markets point at.

    Returns the ``period`` the venue reported (``'VFT'``, ``'CAN'``, …) when the
    row may leave the live board, or ``None`` to hold it. Records with no
    sports block are ignored — they are not a feed and they cannot contradict
    one — but at least one sports record must exist and every sports record must
    independently say ended, about one ``gameId``.
    """
    sports = [p for p in payloads if gamma_record_is_sports(p)]
    if not sports:
        return None
    if len({str(p.get("gameId")) for p in sports}) != 1:
        return None
    for p in sports:
        if not gamma_record_says_ended(p, commence_time=commence_time, now=now):
            return None
    period = sports[0].get("period")
    return str(period) if period not in (None, "") else "ended"


def row_carries_no_authority_id(espn_id, statpal_fixture_id) -> bool:
    """True when neither play-reporting authority is anchored on the row.

    An anchored row has a better witness that reports a real result; this rail
    is for the rows that have nothing else. Blank strings are not ids.
    """
    for provider_id in (espn_id, statpal_fixture_id):
        if provider_id is not None and str(provider_id).strip() != "":
            return False
    return True


#: The candidates: rows on the live board past kickoff, no authority anchor, no
#: completion, and every Polymarket group id their markets carry. The authority
#: and completion tests are asked again in Python and a third time in the write.
#:
#: ``starts_with`` rather than ``LIKE 'polymarket:%'`` — a colon inside a
#: ``text()`` literal parses as a bind parameter (gotcha #45).
VENUE_EVENT_ENDED_CANDIDATES_SQL = """
    SELECT e.id              AS event_id,
           e.home_team_name  AS home_team_name,
           e.away_team_name  AS away_team_name,
           e.commence_time   AS commence_time,
           e.espn_id         AS espn_id,
           e.statpal_fixture_id AS statpal_fixture_id,
           array_agg(DISTINCT fm.group_id) AS group_ids
      FROM events e
      JOIN futures_markets fm ON fm.event_id = e.id
     WHERE e.status = 'live'
       AND e.commence_time <= :now
       AND e.completed_at IS NULL
       AND NULLIF(btrim(e.espn_id), '') IS NULL
       AND NULLIF(btrim(e.statpal_fixture_id), '') IS NULL
       AND fm.source = 'polymarket'
       AND starts_with(fm.group_id, :group_prefix)
     GROUP BY e.id
"""

#: Compare-and-set. ``status = 'live'`` plus both authority tests plus
#: ``completed_at IS NULL`` repeated in the WHERE: the SELECT and this UPDATE are
#: two statements, and an authority that anchors or settles the row in between
#: must win, with a zero rowcount here rather than a demotion of its verdict.
#: No leading newline — the suite's fake sessions dispatch on
#: ``sql.startswith("UPDATE")``, as the sibling constant notes.
SUSPEND_ON_VENUE_EVENT_ENDED_SQL = f"""UPDATE events
       SET status = '{EVENT_SUSPENDED}'
     WHERE id = ANY(:event_ids)
       AND status = 'live'
       AND completed_at IS NULL
       AND NULLIF(btrim(espn_id), '') IS NULL
       AND NULLIF(btrim(statpal_fixture_id), '') IS NULL
"""
