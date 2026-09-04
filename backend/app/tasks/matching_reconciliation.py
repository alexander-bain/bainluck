"""Matching reconciliation — the golden set and the invariants, in production (#2706).

WHY A JOB AND NOT JUST A CI TEST. The CI gate
(``tests/test_matching_golden_set_2706.py``) replays the golden pairs against a
frozen fixture, so it catches a change to the matcher's LOGIC before it merges.
It cannot catch the other half: production data moving under a matcher nobody
changed. Every failure this program exists to end arrived that way — the 8/28
ingest wave went unattempted with no code change, the Li–Vekic links landed on a
ghost twin with no code change, and Bublik and Harris were "attached" with zero
price snapshots with no code change. The definition of solved in the program
brief is explicit about who notices: *"nothing the authority knows about is
missing, doubled, or half-sourced for more than an hour without an issue
existing — and the SYSTEM files that issue, not a person."*

WHAT IT CHECKS, every matching cycle:

* **golden** — the 709 adjudicated pairs, against production ``event_id``.
  Positives must be on their event, negatives must be on none. The baseline is
  the state captured with the fixture, so the check is *regression*, not
  perfection — most pairs are the audit's open failure classes and filing them
  every 15 minutes would be noise, not signal.
* **anchor_collision** — INVARIANTS-2026-09-02 query (a): one
  ``(source, source_id, id_kind)`` naming two events. Target 0.
* **event_espn_id_collision** — one ESPN event id worn by two ``events`` rows.
  Target 0 (#2693 step 2). The sibling of ``anchor_collision``, over the column
  that actually steers ESPN's writes; that one reads 0 only because nothing had
  written an anchor for these rows.
* **market_multi_event** — query (b): one market linked to two events. Target 0.
  Open-scoped, deliberately: the unscoped form times out (fp fedd618081365d6b).
* **receipt_coverage** — query (c)'s successor. (c) counted 996 markets with an
  exact-name candidate, unlinked, and *no written reason*, and noted the reason
  was "structural today — futures_markets has no attempt/reject columns". With
  receipts (#2705) it becomes answerable: open unlinked markets with NO receipt.
  Target 0; above 0, "never attempted" is still possible.
* **linked_unsourced** — attached is not sourced. A market can hold an
  ``event_id`` and still write no price, which is what Bublik and Harris looked
  like on 9/2: linked, outcomes priced, and no polymarket curve on the card.
* **receipt_contradicts_link** — the receipt and the database disagree about
  where a market sits. Without this arm a link lost to a sibling market's
  rollback is invisible to every other check here: coverage counts markets with
  NO receipt and this one has one, linked_unsourced joins through the now-NULL
  ``event_id``, and golden only sees its fixed 709 ids. Target 0.

FILING. One deduped issue per SUBJECT via the shared sentinel rail
(``app/tasks/sentinel_filing.py``), so each check has its own fingerprint, its
own issue, and its own RED→GREEN lifecycle: recovery closes the issue instead of
leaving the board to grow. Filing uses the repo's ``GITHUB_TOKEN`` bot identity —
never a person's. Every issue carries the label ``matching-drift`` and links
#2693.

READ-ONLY against market data. This job files GitHub metadata and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

MARKER = "matching-drift-fingerprint"
DRIFT_LABEL = "matching-drift"

#: The adjudicated pairs + the production state they were captured in. Shared
#: with the CI gate on purpose: two copies of the golden set is two golden sets.
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures"
    / "matching_golden_inputs.json"
)

#: Rows named in an issue body. Enough to act on, bounded so the body stays
#: readable; the total is always stated, so truncation is never silent.
MAX_LISTED = 25

#: A non-null ``events.external_id`` IS NOT the same claim as "an outside
#: schedule provider carries this fixture", and the golden check needs the
#: second one. Measured on production 2026-09-03 over all 51,312 anchored
#: events, the column holds exactly three vocabularies:
#:
#: * a 32-char hex Odds API event id — 29,333 events, still written today, and
#:   782 of an 809-event sample carry ``odds_snapshots`` rows. A sportsbook feed
#:   independently lists the fixture, so the matcher is genuinely corroborated.
#: * ``pm_kalshi_*`` / ``pm_polymarket_*`` — 21,978 events the registry CREATED
#:   FROM a prediction market (frozen 2026-02-22..2026-04-16; 24,232 markets
#:   still hang off them). ZERO of 587 sampled carry bookmaker odds. A
#:   prediction market "confirming" an event that a prediction market created is
#:   the matcher answering itself one step removed — the id-less case laundered
#:   through the ingest path, and NOT corroboration.
#: * exactly one row of neither shape — a ``manual_*`` id (see below).
#:
#: And the column is NOT provider-only by construction:
#: ``POST /api/admin/events/create`` (``routes/admin_events.py``) mints
#: ``manual_{sport}_{home}_{away}_{unix_ts}`` — a composite WE synthesise out of
#: our own field values, carried by nobody. Only one such row exists today, but
#: the endpoint can mint another at any time, so the shape is named rather than
#: left to the ``unknown`` fallback.
#:
#: So the discriminator is an ALLOWLIST of the shapes an outside provider
#: writes, never ``IS NOT NULL``: an unrecognised shape is unknown provenance,
#: and gotcha #53 forbids reading an absence of evidence as corroboration.
#:
#: THE STRONGER PREDICATE, once it is reachable: a ``game``-kind
#: ``event_provider_anchors`` row passing ``anchor_is_current()``. Not yet — the
#: channel holds 1,234 ``odds_api``/``game`` anchors against 29,333 Odds API
#: events (4% coverage, 2026-09-03), so switching to it today would call 96% of
#: genuinely corroborated fixtures uncorroborated. Revisit when coverage lands
#: (#1946); the shape check is the honest instrument until then.
_ODDS_API_EVENT_ID = re.compile(r"^[0-9a-f]{32}$")
_MARKET_DERIVED_PREFIXES = ("pm_kalshi_", "pm_polymarket_")
_SYNTHESIZED_PREFIX = "manual_"

#: Provenances that promote a later attachment out of RED. An allowlist, so a
#: new id vocabulary arriving upstream reads as ``unknown`` and stays RED until
#: somebody decides it corroborates — it can never quietly promote itself.
CORROBORATING_PROVENANCE = frozenset({"schedule_provider"})


def anchor_provenance(external_id: str | None, event_row_missing: bool = False) -> str:
    """Who, other than us, says this event exists.

    ``unreadable`` and ``idless`` are kept apart on purpose even though both are
    RED: "we could not read the events row" is not the finding "no provider
    anchors this fixture", and collapsing them would put an unproven claim in an
    issue body.
    """
    if event_row_missing:
        return "unreadable"
    if external_id is None:
        return "idless"
    if _ODDS_API_EVENT_ID.match(external_id):
        return "schedule_provider"
    if external_id.startswith(_MARKET_DERIVED_PREFIXES):
        return "market_derived"
    if external_id.startswith(_SYNTHESIZED_PREFIX):
        return "synthesized"
    return "unknown"


#: THE RE-ADJUDICATION. ``anchor_provenance`` answers "does anyone outside us
#: say this event exists" — a property of the DESTINATION ALONE. It cannot
#: answer "is this the destination this market belongs on", because the market
#: is not in its scope: no teams, no sport, no kickoff, no market id. Promoting
#: on provenance by itself therefore accepts ANY provider-anchored event,
#: including one with the wrong teams in the wrong sport in the wrong week.
#:
#: So a later attachment is promoted out of RED only when a human has
#: adjudicated THIS market onto THIS event. The map is that adjudication, and it
#: is the whole of it: an attachment that is not in here is RED, whatever the
#: destination's id looks like.
#:
#: Adjudicated 2026-09-03 against production, one row at a time. Each was the
#: only fixture in the database with that team pair, and the Kalshi rows were
#: confirmed by TICKER-DERIVED date (gotcha #14 — a Kalshi ``commence_time`` is
#: usually the close, so the stored value is not the evidence; the ticker is):
#:
#: * 59173320 "Campbell vs East Tennessee St." (kalshi
#:   ``KXNCAAFGAME-26AUG29CAMPETSU``) -> 15294048 East Tennessee State
#:   Buccaneers v Campbell Fighting Camels, ``americanfootball_ncaaf_fcs``,
#:   2026-08-29 21:30Z. Ticker date == event date; both FCS programs.
#: * 59692113 "Vitória SC vs. Casa Pia AC - Exact Score" (polymarket 926708)
#:   -> 15297976 Vitória SC v Casa Pia, ``soccer_portugal_primeira_liga``,
#:   2026-09-06 17:00Z. Sole Vitória/Casa Pia fixture in the table.
#: * 59692121 "FC Alverca vs. SC Braga - Exact Score" (polymarket 926700)
#:   -> 15299112 Alverca v Braga, ``soccer_portugal_primeira_liga``,
#:   2026-09-05 17:00Z. Sole Alverca/Braga fixture in the table.
#: * 59700394 "Hamburg vs Mainz" (kalshi ``KXBUNDESLIGAGAME-26SEP06HSVM05``)
#:   -> 15291033 Hamburger SV v FSV Mainz 05,
#:   ``soccer_germany_bundesliga``, 2026-09-06 13:30Z. Ticker date == event
#:   date; HSV/M05 == the ticker's team codes.
#: * 59700643 "Ipswich Town vs Liverpool: Spread" (kalshi
#:   ``KXEPLSPREAD-26SEP04IPSLFC``) -> 15291104 Ipswich Town v Liverpool,
#:   ``soccer_epl``, 2026-09-04 19:00Z. Ticker date == event date; IPS/LFC ==
#:   the ticker's team codes.
#:
#: The two Polymarket props carry a ``commence_time`` of their own creation
#: minute, so time is deliberately NOT part of their evidence; the unique team
#: pair inside one league is.
#:
#: GROWING THIS MAP IS AN ADJUDICATION, NOT A SILENCING. A guard asserts every
#: key is a pair the audit recorded as belonging on NO event, so an entry can
#: never be used to make a real regression disappear, and asserts the map's
#: exact contents, so a row cannot be added without the diff saying so.
ACCEPTED_ATTACHMENTS: dict[int, int] = {
    59173320: 15294048,
    59692113: 15297976,
    59692121: 15299112,
    59700394: 15291033,
    59700643: 15291104,
}

#: A market this old without a single price snapshot is not "sourced".
#: 90 minutes: two 15-minute matching cycles plus the 2-minute live poll's
#: worst case, with room for a slow backfill — short enough to satisfy the
#: brief's one-hour-ish bar, long enough that a market ingested seconds ago is
#: not accused.
#:
#: MEASURED ON ``created_at``, NOT ``updated_at``, and the first draft had it
#: wrong. ``updated_at`` moves on every price poll, so it says nothing about how
#: long a market has been ATTACHED — it let a market linked two minutes ago be
#: accused while its first snapshot was still in flight. Re-measured 2026-09-02
#: twenty minutes apart, the count fell 36 → 18 on its own, which is a check
#: reporting a queue depth and calling it a defect.
UNSOURCED_AFTER_MINUTES = 90

#: How close to kickoff an event has to be before a missing curve is a defect
#: rather than a not-yet. ±6h, not +24h: at a day out the 2-minute live poller
#: has legitimately not reached the event, and counting those is what made the
#: first draft of this check transient.
UNSOURCED_WINDOW_HOURS = 6


# ---------------------------------------------------------------------------
# The checks. Each returns {"key", "red", "count", "detail", "rows"}.
# ---------------------------------------------------------------------------


def _finding(key: str, red: bool, count: int, detail: str, rows=None) -> dict:
    return {
        "key": key, "red": red, "count": count, "detail": detail,
        "rows": rows or [],
    }


def load_golden_baseline() -> tuple[list[dict], dict[int, bool]]:
    """The pairs, and which of them production satisfied at capture time.

    ``event_id_at_capture`` is the state the audit adjudicated against, so the
    baseline is derived from the fixture rather than stored twice. A pair that
    was already wrong on 2026-09-02 is not news every fifteen minutes; a pair
    that was RIGHT and stops being right is exactly the news this job exists
    for.
    """
    data = json.loads(FIXTURE_PATH.read_text())
    pairs = data["pairs"]
    baseline = {}
    for p in pairs:
        at_capture = p["market"].get("event_id_at_capture")
        baseline[int(p["market_id"])] = at_capture == p["correct_event_id"]
    return pairs, baseline


async def check_golden_pairs(session) -> dict:
    """Re-check every adjudicated pair against production's current ``event_id``.

    A NEGATIVE PAIR'S ``None`` IS NOT A PROMISE THAT NOTHING MAY EVER ATTACH.
    548 of the 709 were adjudicated ``correct_event_id: None`` because no correct
    event *existed at capture time* — ``a-no-event``'s note is literally "global
    2+-token check; titles batch-read", i.e. the adjudicator swept the event
    titles and found no candidate. That is a statement about the world on
    2026-09-02, not a property of the market. This check used to read it as
    "must remain attached to nothing" and count every later attachment as a
    regression, which put "we broke it" and "we fixed it" under one RED number.

    Measured on production 2026-09-03, all 39 of the RED rows were negative
    pairs, and five of them had attached to a **provider-anchored** fixture that
    simply did not exist when the pair was adjudicated — "Hamburg vs Mainz" onto
    the real Bundesliga ``Hamburger SV v FSV Mainz 05``, "Ipswich Town vs
    Liverpool: Spread" onto the real EPL fixture. The check was reporting the
    matcher's successes as its failures.

    So a later attachment is judged by WHAT IT ATTACHED TO, and it takes BOTH
    halves to leave RED — that the destination is real, and that it is the right
    destination for THIS market:

    * **accepted** — a human adjudicated this market onto this event
      (``ACCEPTED_ATTACHMENTS``) *and* an outside SCHEDULE PROVIDER still
      anchors it (``anchor_provenance``; today that means an Odds API event id,
      96.7% of which carry bookmaker odds). Reported as ``baseline_stale`` and
      never RED: the matcher is right and the baseline row is what is out of
      date.
    * **unadjudicated** — provider-anchored, but nobody has adjudicated this
      market onto this event. RED. Provenance is a property of the destination
      alone: it cannot tell "Hawaii vs Stanford landed on the real
      Hawaii/Stanford fixture" from "…landed on a real fixture in another sport
      three weeks away", because the market is not in its scope. Reading it as
      acceptance is what this check used to do, and it accepted every
      provider-anchored event in the database.
    * **uncorroborated** — nothing outside the matcher says this event exists.
      RED, as ``self_answered``, and each row carries the provenance that put it
      there: ``idless`` (the matcher created the event and matched its own
      creation), ``market_derived`` (a prediction-market-derived event, which is
      the same self-answer one step removed), ``unknown`` (an id vocabulary
      nobody has adjudicated) or ``unreadable``. Checked before acceptance, so
      an accepted row that LOSES its anchor reports the loss rather than
      passing. The id-less-claim rule (gotcha #32 / ruling 048) means such a row
      can never be absorbed or reconciled later, so it is permanent.

    The provenance discriminator is itself deliberately an allowlist and not
    ``external_id IS NOT NULL``: the proxy would read all 21,978
    prediction-market-derived events as outside corroboration.

    THE DEFAULT IS RED. A negative pair that changes is accused unless both
    halves are satisfied, which is the only shape that cannot quietly widen: a
    new attachment nobody has looked at is exactly the thing worth looking at.

    A POSITIVE pair — one the audit adjudicated onto a specific event — is
    unchanged: it had a known-correct answer, and losing it is a regression with
    no ambiguity at all.
    """
    pairs, baseline = load_golden_baseline()
    by_market = {int(p["market_id"]): p for p in pairs}
    ids = sorted(by_market)
    if not ids:
        return _finding("golden", False, 0, "no golden pairs loaded")

    # LEFT JOIN, not a second query: an unlinked market must still come back as a
    # row, or it reads as vanished (the deleted-market bucket) and the check
    # accuses the twin cleanup of being a matcher failure.
    rows = (await session.execute(
        text(
            "SELECT fm.id, fm.event_id, e.external_id, (e.id IS NULL) AS event_missing "
            "FROM futures_markets fm "
            "LEFT JOIN events e ON e.id = fm.event_id "
            "WHERE fm.id = ANY(:ids)"
        ),
        {"ids": ids},
    )).all()
    current = {
        int(r[0]): (int(r[1]) if r[1] is not None else None, r[2], r[3])
        for r in rows
    }

    regressed, self_answered, unadjudicated, baseline_stale = [], [], [], []
    recovered, vanished = [], []
    by_provenance: dict[str, int] = {}
    for mid, was_ok in baseline.items():
        if mid not in current:
            vanished.append(mid)
            continue
        actual, external_id, event_missing = current[mid]
        expected = by_market[mid]["correct_event_id"]
        now_ok = actual == expected
        if was_ok and not now_ok:
            p = by_market[mid]
            row = {
                "market_id": mid,
                "title": p["title"],
                "failure_class": p["failure_class"],
                "expected_event_id": expected,
                "actual_event_id": actual,
            }
            if expected is not None:
                # The audit knew the right answer and the market left it.
                row["verdict"] = "regressed"
                regressed.append(row)
                continue
            provenance = anchor_provenance(external_id, bool(event_missing))
            row["anchor_provenance"] = provenance
            by_provenance[provenance] = by_provenance.get(provenance, 0) + 1
            accepted = ACCEPTED_ATTACHMENTS.get(mid)
            if accepted is not None:
                # Say where the adjudication put it, so a row that MOVED off an
                # accepted destination reads as that and not as a fresh attach.
                row["accepted_event_id"] = accepted
            if provenance not in CORROBORATING_PROVENANCE:
                # Nothing outside the matcher corroborates it. Checked first
                # because it is the stronger finding: an accepted attachment
                # that has LOST its provider anchor is news, not a pass.
                row["verdict"] = "self_answered"
                self_answered.append(row)
            elif accepted == actual:
                # A human adjudicated THIS market onto THIS event, and an
                # outside schedule provider still anchors it. The matcher is
                # confirmed and the baseline row is what is stale.
                row["verdict"] = "baseline_stale"
                baseline_stale.append(row)
            else:
                # Provider-anchored, but nobody has adjudicated this market onto
                # this event. The destination's id says the FIXTURE is real; it
                # says nothing about whether it is the right fixture for this
                # market, which is the question the golden set exists to answer.
                row["verdict"] = "unadjudicated"
                unadjudicated.append(row)
        elif not was_ok and now_ok:
            recovered.append(mid)

    red_rows = regressed + self_answered + unadjudicated
    # Name WHICH uncorroborated provenance, so "the matcher invented the event"
    # and "an id vocabulary nobody has adjudicated" never hide in one number.
    uncorroborated = ", ".join(
        f"{n} {name}"
        for name, n in sorted(by_provenance.items())
        if name not in CORROBORATING_PROVENANCE
    )
    detail = (
        f"{len(regressed)} adjudicated pairs regressed, {len(self_answered)} "
        f"negative pairs attached to an event no outside provider corroborates "
        f"({uncorroborated or 'none'}), and {len(unadjudicated)} attached to a "
        f"provider-anchored event nobody has adjudicated them onto, of "
        f"{len(baseline)} pairs ({len(baseline_stale)} sit on one of the "
        f"{len(ACCEPTED_ATTACHMENTS)} adjudicated-accepted fixtures that did not "
        f"exist at capture — baseline stale, not a regression; "
        f"{len(recovered)} recovered, {len(vanished)} markets no longer exist)"
    )
    out = _finding("golden", bool(red_rows), len(red_rows), detail, red_rows)
    out["regressed"] = len(regressed)
    out["self_answered"] = len(self_answered)
    out["unadjudicated"] = len(unadjudicated)
    out["baseline_stale"] = len(baseline_stale)
    out["by_provenance"] = by_provenance
    out["recovered"] = len(recovered)
    out["vanished"] = len(vanished)
    return out


async def check_anchor_collision(session) -> dict:
    """INVARIANTS (a): one provider id naming two events. Baseline 0/6,039."""
    rows = (await session.execute(text(
        """
        SELECT source, source_id, id_kind, count(DISTINCT event_id) AS n
        FROM event_provider_anchors
        GROUP BY 1, 2, 3
        HAVING count(DISTINCT event_id) > 1
        LIMIT 200
        """
    ))).all()
    listed = [
        {"source": r[0], "source_id": r[1], "id_kind": r[2], "events": int(r[3])}
        for r in rows
    ]
    return _finding(
        "anchor_collision", bool(listed), len(listed),
        f"{len(listed)} (source, source_id, id_kind) key(s) name more than one "
        "event — the anchor channel is the thing absorption is allowed to trust",
        listed,
    )


async def check_event_espn_id_collision(session) -> dict:
    """One ESPN event id worn by two ``events`` rows. Target 0 (#2693 step 2).

    ``check_anchor_collision`` above asks the same question of
    ``event_provider_anchors``, and it has always answered 0 — because nothing
    had written an anchor for these rows. The column ``espn_sync`` actually
    steers its writes through is ``events.espn_id``, and on 2026-09-02 that one
    was worn by two or more rows for **196 ids, 430 rows**.

    THIS CHECK IS THE DURABLE HALF OF THE REPAIR, and it exists because
    CERT-784 asked the right question: a repair whose population an active
    writer refills is not a repair. The writers are holder-checked now
    (``espn_id_stamp``, #2017), but "we fixed every writer we found" is a claim
    about a census, and this is the measurement that would notice a writer
    nobody censused. It does not depend on the unique index existing — which
    matters, because ``backend/Procfile`` wraps the release-phase Alembic run in
    ``|| echo`` and so cannot fail a deploy on a missing migration (#2741).
    """
    rows = (await session.execute(text(
        """
        SELECT espn_id, count(*) AS n
        FROM events
        WHERE espn_id IS NOT NULL
        GROUP BY espn_id
        HAVING count(*) > 1
        ORDER BY n DESC, espn_id
        LIMIT 200
        """
    ))).all()
    listed = [{"espn_id": r[0], "events": int(r[1])} for r in rows]
    return _finding(
        "event_espn_id_collision", bool(listed), len(listed),
        f"{len(listed)} ESPN event id(s) worn by more than one events row — the "
        "authority writes one game's status, clock and score onto two fixtures",
        listed,
    )


async def check_market_multi_event(session) -> dict:
    """INVARIANTS (b): one market on two events. Open-scoped — see the module docstring."""
    rows = (await session.execute(text(
        """
        SELECT source, external_id, count(DISTINCT event_id) AS n
        FROM futures_markets
        WHERE status = 'open' AND event_id IS NOT NULL
        GROUP BY 1, 2
        HAVING count(DISTINCT event_id) > 1
        LIMIT 200
        """
    ))).all()
    listed = [
        {"source": r[0], "external_id": r[1], "events": int(r[2])} for r in rows
    ]
    return _finding(
        "market_multi_event", bool(listed), len(listed),
        f"{len(listed)} open market(s) linked to more than one event "
        "(scope: open only — the unscoped query times out)",
        listed,
    )


async def check_receipt_coverage(session) -> dict:
    """INVARIANTS (c)'s successor: open unlinked markets with NO receipt.

    (c) counted 996 markets with an exact-name candidate and no written reason,
    and said the gap was structural: ``futures_markets`` had nowhere to write a
    reason. Receipts (#2705) closed that, so the question becomes countable —
    and the number that matters is not "how many are unlinked" but "how many
    have never been LOOKED AT". Above 0, the 8/28 wave can happen again.
    """
    n = await session.scalar(text(
        """
        SELECT count(*)
        FROM futures_markets fm
        WHERE fm.source IN ('kalshi', 'polymarket')
          AND fm.event_id IS NULL
          AND fm.status = 'open'
          AND NOT EXISTS (
              SELECT 1 FROM market_match_receipts r WHERE r.market_id = fm.id
          )
        """
    ))
    n = int(n or 0)
    return _finding(
        "receipt_coverage", n > 0, n,
        f"{n} open unlinked market(s) have never been attempted — while this is "
        "above 0, a whole ingest wave can sit unlooked-at (ARTIFACT-M-20260902-N)",
    )


async def check_linked_unsourced(session) -> dict:
    """Attached is not sourced: a source on the card with no line behind it.

    Bublik and Harris on 2026-09-02 were linked with priced outcomes and NO
    polymarket win_prob_snapshots, so their cards drew no curve. ``event_id`` is
    not the ship; the line on the card is.

    COUNTED PER (EVENT, SOURCE), NOT PER MARKET, and the difference is the whole
    reading. Only the game-winner market feeds the blend — a spread, a total or
    a first-half prop is *supposed* to write nothing — so counting markets
    accuses 300 rows of a fault 264 of them cannot commit. What a user can
    actually see is one thing: this event has that source attached and no curve
    from it. Measured 2026-09-02: 300 markets, **36** event×source pairs, among
    them Auger-Aliassime v Khachanov.
    """
    rows = (await session.execute(text(
        """
        SELECT fm.event_id, fm.source, count(*) AS markets,
               min(e.commence_time) AS commence_time
        FROM futures_markets fm
        JOIN events e ON e.id = fm.event_id
        WHERE fm.source IN ('kalshi', 'polymarket')
          AND fm.status = 'open'
          AND e.status IN ('scheduled', 'live')
          AND e.commence_time BETWEEN NOW() - (:hrs * INTERVAL '1 hour')
                                  AND NOW() + (:hrs * INTERVAL '1 hour')
          AND fm.created_at < NOW() - (:mins * INTERVAL '1 minute')
        GROUP BY 1, 2
        HAVING NOT EXISTS (
            SELECT 1 FROM win_prob_snapshots w
            WHERE w.event_id = fm.event_id AND w.source = fm.source
        )
        ORDER BY 3 DESC
        LIMIT 200
        """
    ), {"mins": UNSOURCED_AFTER_MINUTES,
         "hrs": UNSOURCED_WINDOW_HOURS})).all()
    listed = [
        {"event_id": int(r[0]), "source": r[1], "linked_markets": int(r[2]),
         "commence_time": r[3].isoformat() if r[3] else None}
        for r in rows
    ]
    return _finding(
        "linked_unsourced", bool(listed), len(listed),
        f"{len(listed)} near-term event/source pair(s) are linked but have written "
        "no win-prob snapshot — attached is not sourced, so the card shows the "
        "source and draws no curve",
        listed,
    )


async def check_receipt_contradicts_link(session) -> dict:
    """A receipt that disagrees with the database about where a market sits.

    CERT-772'S FINDING, ANSWERED. Receipts are written on their own session, so
    a market can be claimed as linked and then have its pending ``event_id``
    rolled back by a sibling market's failure in the same pass. Before this
    check, such a row was invisible to every other arm here:
    ``receipt_coverage`` counts markets with NO receipt and this one HAS one;
    ``linked_unsourced`` joins through an ``event_id`` that is now NULL; and
    ``golden`` only ever looks at its fixed 709 ids. All five could report GREEN
    while a market sat unattached and its one-query answer said "linked".

    Two shapes, one subject, because they are the same failure seen from two
    sides:

    * a published receipt whose ``linked_event_id`` disagrees with the market's
      actual ``event_id`` — the contradiction itself;
    * a receipt already downgraded to ``link_not_durable`` by the write-time
      guard — the contradiction caught before publication.

    The second is the healthy path and should still be reported: nonzero means
    the matcher IS losing links, even though the receipt no longer lies about it.
    """
    rows = (await session.execute(text(
        """
        SELECT r.market_id, r.linked_event_id, fm.event_id, r.phase,
               r.last_attempted_at
        FROM market_match_receipts r
        JOIN futures_markets fm ON fm.id = r.market_id
        WHERE r.outcome = 'linked'
          AND r.linked_event_id IS DISTINCT FROM fm.event_id
        LIMIT 200
        """
    ))).all()
    contradictions = [
        {"market_id": int(r[0]), "receipt_says_event_id": int(r[1]) if r[1] is not None else None,
         "database_says_event_id": int(r[2]) if r[2] is not None else None,
         "phase": r[3],
         "last_attempted_at": r[4].isoformat() if r[4] else None}
        for r in rows
    ]

    lost = int(await session.scalar(text(
        "SELECT count(*) FROM market_match_receipts "
        "WHERE reject_reason = 'link_not_durable'"
    )) or 0)

    total = len(contradictions) + lost
    return _finding(
        "receipt_contradicts_link", total > 0, total,
        f"{len(contradictions)} receipt(s) disagree with the database about "
        f"where their market sits, and {lost} were caught by the write-time "
        "guard as link_not_durable — either way the matcher is losing links a "
        "sibling market's failure rolled back",
        contradictions,
    )


CHECKS = (
    check_golden_pairs,
    check_anchor_collision,
    check_event_espn_id_collision,
    check_market_multi_event,
    check_receipt_coverage,
    check_linked_unsourced,
    check_receipt_contradicts_link,
)


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------


def fingerprint_for(key: str) -> str:
    """One stable fingerprint per SUBJECT.

    Per subject, not per finding: a check that goes RED on 40 markets and then
    on 41 is the same problem, and giving it a content-derived fingerprint would
    file a new issue every cycle — the duplicate class the shared rail exists to
    prevent, arrived at from the fingerprint side.
    """
    return hashlib.sha256(f"matching-reconciliation:{key}".encode()).hexdigest()[:12]


#: One stable, COUNT-FREE subject per check — the same per-subject principle as
#: ``fingerprint_for``, applied to the title. A new check must add its key here;
#: ``build_title`` refuses an unknown one rather than inventing a title.
SUBJECTS = {
    # Names EVERY class the golden check files RED, because it files three: a
    # pair that lost a known-correct answer (regressed), a negative pair that
    # attached to an event nobody adjudicated it onto (unadjudicated), and one
    # that attached to an event no schedule provider anchors (self-answered). A
    # subject naming only the first would send a triager looking for
    # regressions on a board where, measured 2026-09-03, all 34 RED rows are
    # the third kind and 0 are regressions.
    "golden": (
        "adjudicated pairs have regressed, or sit on an unadjudicated event, "
        "or on one no schedule provider vouches for"
    ),
    "anchor_collision": "one anchor key names more than one event",
    "event_espn_id_collision": "one ESPN event id is worn by more than one events row",
    "market_multi_event": "an open market is linked to more than one event",
    "receipt_coverage": "open unlinked markets have never been attempted",
    "linked_unsourced": "near-term linked events have written no win-prob snapshot",
    "receipt_contradicts_link": (
        "links are being lost to a sibling market's rolled-back failure"
    ),
}


def build_title(finding: dict) -> str:
    """The SUBJECT, never the count.

    THE RAIL NEVER REFRESHES A TITLE. ``reconcile_issue``'s RED path comments and
    re-points the BODY at the current observation; the title is written once, at
    creation, and is then frozen for the life of the issue. So a title built from
    ``finding['detail']`` — which carries the live count — is a snapshot that
    silently rots while the body moves on beneath it.

    Measured 2026-09-03, every open drift issue's title disagreed with its own
    body: ``golden`` was titled "1 of 709 adjudicated pairs regressed" while the
    body said 39, ``linked_unsourced`` said 30 against 110, and
    ``receipt_contradicts_link`` said 5 against 75. A board is triaged by title,
    so three of the four alerts understated themselves to the only reader they
    have — the ``golden`` one by 39x.

    The count is not lost: ``build_body`` carries it as ``**Count:**`` and the
    body IS refreshed every cycle. What the title carries instead is the thing
    that does not change while the issue is open — which is also why the
    fingerprint is per-subject (see ``fingerprint_for``). Same argument, same
    conclusion, one layer up.
    """
    key = finding["key"]
    try:
        subject = SUBJECTS[key]
    except KeyError:  # pragma: no cover - the guard test is the coverage
        raise KeyError(
            f"matching_reconciliation: check {key!r} has no SUBJECTS entry. Add "
            "one — a title built from the finding's detail freezes a count the "
            "rail can never refresh."
        ) from None
    return f"[Matching Drift] {key}: {subject}"[:256]


def build_body(finding: dict, receipts_hint: str | None = None) -> str:
    fp = fingerprint_for(finding["key"])
    parts = [
        f"## Matching reconciliation — `{finding['key']}` is RED",
        "",
        f"`{MARKER}:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Finding:** {finding['detail']}",
        f"**Count:** {finding['count']}",
        "",
    ]
    if finding["rows"]:
        parts.append(f"### Rows ({min(len(finding['rows']), MAX_LISTED)} of {finding['count']})")
        for row in finding["rows"][:MAX_LISTED]:
            parts.append(f"- `{json.dumps(row, sort_keys=True, default=str)}`")
        if finding["count"] > MAX_LISTED:
            parts.append(f"- …and {finding['count'] - MAX_LISTED} more")
        parts.append("")
    if receipts_hint:
        parts += ["### Receipt", "", receipts_hint, ""]
    parts += [
        "---",
        "Part of the durable matching program (#2693). Step 1 receipts (#2705) "
        "answer *why* a specific market is unattached: "
        "`GET /api/admin/match-receipts?market_id=<id>`.",
        "",
        "*Auto-filed by `app.tasks.matching_reconciliation` (#2706) using the "
        "repo's bot identity. Read-only against market data. Reproduce with "
        "`POST /api/admin/matching-reconciliation/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


def receipts_hint_for(finding: dict) -> str | None:
    """The one query that turns this finding into a diagnosis."""
    if finding["key"] == "golden" and finding["rows"]:
        mid = finding["rows"][0]["market_id"]
        return (
            f"Why market {mid} sits where it does: "
            f"`GET /api/admin/match-receipts?market_id={mid}` — the candidates it "
            "was offered, their scores, and the closed-enum reason."
        )
    if finding["key"] == "receipt_coverage":
        return (
            "Coverage summary: `GET /api/admin/match-receipts` — "
            "`coverage.open_unlinked_without_receipt` is this number, and "
            "`funnel.backlog_dropped` on the matcher's last run says how many "
            "eligible markets that cycle did not reach. Read "
            "`coverage.by_source` and its per-source "
            "`explained_no_game_here` before "
            "reading it as missing links (#2803): what clears this number is a "
            "receipt, and for most of the population that receipt is a refusal. "
            "`coverage.backlog_pass_has_run` true means the pass that drives it "
            "down has run. It is never false: a run whose record write failed "
            "is indistinguishable from no run, so the absent case is null — "
            "check `coverage.backlog_pass.status` before concluding the backlog "
            "pass never ran."
        )
    if finding["key"] == "linked_unsourced" and finding["rows"]:
        eid = finding["rows"][0]["event_id"]
        return f"What the matcher put on event {eid}: `GET /api/admin/match-receipts?event_id={eid}`."
    return None


def file_findings(findings: list[dict], open_issues=None) -> list[dict]:
    """RED/GREEN reconcile, one issue per subject, via the shared rail."""
    from app.tasks.sentinel_filing import reconcile_issue

    results = []
    for finding in findings:
        fp = fingerprint_for(finding["key"])
        if finding["red"]:
            body = build_body(finding, receipts_hint_for(finding))
            res = reconcile_issue(
                red=True,
                fingerprint=fp,
                marker_key=MARKER,
                labels=[
                    "alert-intake", DRIFT_LABEL, "needs-agent",
                    "area:event-details", "priority:p1",
                ],
                title=build_title(finding),
                body=body,
                red_body=body,
                red_comment=(
                    f"Still RED: {finding['detail']} (fingerprint `{fp}`)."
                ),
                open_issues=open_issues,
            )
        else:
            res = reconcile_issue(
                red=False,
                fingerprint=fp,
                marker_key=MARKER,
                green_comment=(
                    f"Matching reconciliation re-checked `{finding['key']}` GREEN "
                    f"— {finding['detail']}. Auto-closing; a recurrence opens a "
                    f"fresh episode."
                ),
                open_issues=open_issues,
            )
        res["check"] = finding["key"]
        results.append(res)
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run_matching_reconciliation(file_issues: bool = True) -> dict[str, Any]:
    """Run every check; file or resolve one issue per subject."""
    findings: list[dict] = []
    errors: list[str] = []

    async with get_task_session() as session:
        for check in CHECKS:
            try:
                findings.append(await check(session))
            except Exception as e:
                # A check that cannot run is UNKNOWN, never GREEN. Recording it
                # as GREEN would close a real issue on the strength of a failed
                # query (gotcha #53 — a failure is not an absence).
                errors.append(f"{check.__name__}: {str(e)[:200]}")
                logger.warning("matching_reconciliation: %s failed: %s", check.__name__, e)

    red = [f for f in findings if f["red"]]
    result: dict[str, Any] = {
        "checks_run": len(findings),
        "checks_failed": len(errors),
        "red": [f["key"] for f in red],
        "findings": [
            {k: v for k, v in f.items() if k != "rows"} for f in findings
        ],
        "errors": errors,
        "filed": [],
    }

    if not file_issues:
        result["filing"] = "skipped"
        return result

    from app.tasks.sentinel_filing import fetch_open_alert_issues

    open_issues = fetch_open_alert_issues()
    result["filed"] = file_findings(findings, open_issues=open_issues)
    logger.info(
        "matching_reconciliation: %d check(s), %d RED, %d unmeasurable — %s",
        len(findings), len(red), len(errors),
        ", ".join(f"{r['check']}={r.get('action')}" for r in result["filed"]),
    )
    return result
