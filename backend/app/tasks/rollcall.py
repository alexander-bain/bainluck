"""The daily ground-truth roll call (C-ROLLCALL-BUILD-1) — the beat.

Once a day this asks the outside world what fixtures exist, then asserts the
axiom Alex issued on 2026-08-26: for MLB, NBA, NHL, NFL, WNBA and the PGA/LPGA
tour, **every published fixture is in our product exactly once, with every
source we carry attached to it.** Not 95%. Not "up from last week". A gap is a
defect and it gets named, the same day it appears.

It exists because three separate incident classes were each found by a human who
happened to look: #1779/#1798/#1811 (games we never created), #2213 (41
duplicate MLB groups, one game rendering as forty-one cards), and the ingestion
outage `C-ROLLCALL-PREP-1` measured at ``0/15`` Kalshi game linkage on a full
MLB slate. Each was invisible for weeks and each was obvious in one table.

What it does NOT do, deliberately: it does not repair anything. Read-only
against events and markets; the only rows it writes are its own scorecard and
the GitHub issue the shared filing rail files for it. Applying a repair from a
detector is how a wrong detection becomes data loss (gotcha #21).

Truth sources — ESPN scoreboard for the team leagues, Datagolf for golf (Alex's
golf ruling: ESPN has no tour-event truth we can use). A truth read that FAILS
is a third state, never folded into "no fixtures": the league is reported
``truth_unavailable``, it does not count as graded, and the run's terminal falls
to ``partial`` so ``ENFORCED_TASKS`` sees it. Gotcha #53 in the detector.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any

from app.utils.rollcall import (
    AXIOM_LEAGUES,
    FINGERPRINT_MARKER,
    MEASURED_DOMAINS,
    REDIS_KEY_TEMPLATE,
    REDIS_TTL_SECONDS,
    SCORECARD_SCHEMA,
    AxiomLeague,
    FixtureRow,
    axiom_is_red,
    axiom_offenders,
    baseline_verdict,
    build_rollcall_issue_body,
    build_rollcall_issue_title,
    coverage_percent,
    fixture_matches,
    rollcall_fingerprint,
    rollcall_terminal,
    score_fixtures,
    team_nickname,
)

logger = logging.getLogger(__name__)

#: Per-run wall-clock bound, comfortably inside the task's soft limit. A
#: sentinel that can run long is one that gets SIGKILLed mid-write.
DEADLINE_SECONDS = 480.0

#: Half-width of the window in which one of our events may satisfy a fixture.
#: 18h matches ``schedule_coverage``'s window so the two detectors cannot
#: disagree about what "today" means.
WINDOW_HOURS = 18

#: How far an unstamped event may sit from a fixture's published start and
#: still be that fixture. Six hours comfortably covers a rain delay, a
#: provisional start time and a timezone-rounded feed, and comfortably does NOT
#: reach the next day's game in the same series — which is the whole point (see
#: :func:`_attach`). An event further out than this from every fixture that
#: names it is left unclaimed rather than assigned to the wrong day.
MAX_NAME_SKEW_HOURS = 6.0

#: Bounds on the one-to-one assignment in :func:`_attach`. A same-matchup group
#: bigger than this on a single day is not a doubleheader, it is a data
#: pathology, and the honest answer to a pathology is a refusal rather than an
#: approximation. Enumeration is over fixtures (``(events+1) ** fixtures``), so
#: four fixtures against twelve events is ~28k leaves — bounded and fast.
MAX_GROUP_FIXTURES = 4
MAX_GROUP_EVENTS = 12

ESPN_TRUTH_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={date}"
DATAGOLF_TRUTH_URL = "https://feeds.datagolf.com/get-schedule?tour={tour}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Truth reads
# ---------------------------------------------------------------------------


async def _espn_fixtures(league: AxiomLeague, day: str) -> list[dict[str, Any]]:
    """Today's published fixtures for an ESPN-truth league.

    Raises on a failed read — the caller turns that into ``truth_unavailable``
    rather than an empty slate.
    """
    from app.services.espn_api import ESPNAPIService

    service = ESPNAPIService()
    try:
        events = await service.get_scoreboard(
            league.truth_key, date=day.replace("-", "")
        )
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
    out = []
    for ev in events:
        home = getattr(ev.home_team, "display_name", None) or getattr(
            ev.home_team, "name", ""
        ) if ev.home_team else ""
        away = getattr(ev.away_team, "display_name", None) or getattr(
            ev.away_team, "name", ""
        ) if ev.away_team else ""
        out.append({
            "espn_id": str(ev.espn_id),
            "home": home,
            "away": away,
            "kickoff": ev.date.isoformat() if getattr(ev, "date", None) else None,
            "label": f"{away} @ {home}".strip(),
        })
    return out


async def _datagolf_fixtures(league: AxiomLeague, day: str) -> list[dict[str, Any]]:
    """Tour events whose window contains ``day``.

    A golf "fixture" is a tournament, not a game: the event is live from its
    start date through its computed end date, so the day's slate is every tour
    event whose window covers today. An empty tour week is an off-day and is
    silent, exactly like an ESPN off-day.
    """
    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        schedule = await service.get_schedule(tour=league.truth_key)
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass

    today = _date.fromisoformat(day)
    out = []
    for t in schedule:
        if not t.start_date:
            continue
        try:
            start = _date.fromisoformat(t.start_date)
            end = _date.fromisoformat(t.end_date) if t.end_date else start
        except ValueError:
            continue
        if start <= today <= end:
            out.append({
                "espn_id": None,
                "datagolf_event_id": t.event_id,
                "home": t.event_name or "",
                "away": "",
                "kickoff": t.start_date,
                "label": t.event_name or f"datagolf:{t.event_id}",
            })
    return out


# ---------------------------------------------------------------------------
# Our side
# ---------------------------------------------------------------------------


async def _our_events(session, sport_keys: tuple[str, ...], day: str) -> list[dict]:
    """Every event of these sports in the day's ±18h window, with linkage.

    One query per league, and the source columns are computed in SQL so the
    fixture loop never issues a query per fixture — a sentinel that scales with
    the slate is one that starts timing out in October.
    """
    from sqlalchemy import text

    day_noon = datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    rows = (await session.execute(
        text("""
            SELECT e.id,
                   e.espn_id,
                   e.home_team_name,
                   e.away_team_name,
                   e.commence_time,
                   (e.espn_id IS NOT NULL
                    OR jsonb_typeof(e.win_probability_sources->'espn') = 'number')
                       AS has_espn,
                   (jsonb_typeof(e.win_probability_sources->'betting') = 'number')
                       AS has_odds_api,
                   EXISTS (SELECT 1 FROM futures_markets fm
                           WHERE fm.event_id = e.id AND fm.source = 'kalshi')
                       AS has_kalshi,
                   EXISTS (SELECT 1 FROM futures_markets fm
                           WHERE fm.event_id = e.id AND fm.source = 'polymarket')
                       AS has_polymarket
            FROM events e
            JOIN sports s ON s.id = e.sport_id
            WHERE s.key = ANY(:sport_keys)
              AND e.commence_time BETWEEN :lo AND :hi
        """),
        {
            "sport_keys": list(sport_keys),
            "lo": day_noon - timedelta(hours=WINDOW_HOURS),
            "hi": day_noon + timedelta(hours=WINDOW_HOURS),
        },
    )).mappings().all()
    return [dict(r) for r in rows]


def _as_utc(value: Any) -> datetime | None:
    """Parse a timestamp from either side of the comparison, or give up.

    Returns ``None`` rather than guessing — a caller that cannot tell two times
    apart must decline the match, not assume it (the alternative is the
    adjacent-day collapse :func:`_attach` documents).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _skew_hours(ours: Any, theirs: Any) -> float | None:
    """Absolute hours between our start time and the fixture's, or ``None``."""
    a, b = _as_utc(ours), _as_utc(theirs)
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


def _matchup_key(home: str, away: str) -> tuple[str, str] | None:
    """Orientation-free identity of a matchup, or ``None`` when unusable.

    Equality of this key is exactly :func:`fixture_matches` — both sides agree
    on the club token, in either orientation — so grouping on it partitions the
    slate into the sets whose members can compete for one another. That is what
    lets the assignment below be solved one small group at a time instead of
    once over the whole day.
    """
    h, a = team_nickname(home or ""), team_nickname(away or "")
    if not (h and a):
        return None
    return (h, a) if h <= a else (a, h)


#: How many equally-optimal assignments are collected before the group is
#: refused outright. Only reached by a pathological group; a doubleheader with
#: a duplicated pair produces four.
MAX_OPTIMA = 512


def _optimal_assignments(
    costs: dict[tuple[int, int], float], n_fixtures: int, n_events: int
) -> tuple[list[dict[int, int]], bool]:
    """Every max-cardinality, min-total-skew one-to-one assignment of a group.

    ``costs[(f, e)]`` is the skew in hours of each admissible pairing, indexed
    by position within the group. Cardinality is maximised FIRST — binding two
    games beats binding one of them very well — and total skew breaks the
    remaining ties. Returns ``(assignments, truncated)``.

    Optimising the TOTAL is what the delayed-doubleheader defect needs. Each row
    picking its own nearest fixture independently sends both rows of a
    17:00/20:00 pair to the 20:00 fixture when the first is delayed to 19:00,
    because 19:00 really is nearer to 20:00 than to 17:00. Only the total is a
    doubleheader-safe objective.

    ALL the optima are returned, not just one, because the caller cannot judge
    whether a tie matters until it has seen what each option would actually
    publish — see :func:`_attach`. Exhaustive over fixtures, which is the small
    side and is capped by :data:`MAX_GROUP_FIXTURES` before this is called.
    """
    best_key: tuple[int, float] | None = None
    found: list[dict[int, int]] = []
    truncated = False

    def walk(f: int, used: frozenset[int], chosen: dict[int, int], cost: float) -> None:
        nonlocal best_key, found, truncated
        if f == n_fixtures:
            key = (-len(chosen), round(cost, 6))
            if best_key is None or key < best_key:
                best_key, found, truncated = key, [dict(chosen)], False
            elif key == best_key:
                if len(found) >= MAX_OPTIMA:
                    truncated = True
                else:
                    found.append(dict(chosen))
            return
        for e in range(n_events):
            if e in used or (f, e) not in costs:
                continue
            chosen[f] = e
            walk(f + 1, used | {e}, chosen, cost + costs[(f, e)])
            del chosen[f]
        walk(f + 1, used, chosen, cost)  # this fixture takes nobody

    walk(0, frozenset(), {}, 0.0)
    return found, truncated


def _attach(fixtures: list[dict], events: list[dict]) -> list[FixtureRow]:
    """Bind each truth fixture to the DB events that claim it.

    Two passes, and the rule between them is the whole correctness argument:

    * **An event carrying an ``espn_id`` is claimed by that id and by nothing
      else.** Its identity is already settled by an id-anchored correspondence,
      so the name pass must not be able to take it. Without this, two stamped
      rows for two different games — identical team names, a doubleheader or a
      series — both fall to whichever fixture the name loop reaches first, and
      the second fixture reads ``missing`` while the first reads ``dupes=2``.
      Two fabricated defects out of a healthy pair.
    * **An event with no id is claimed by name.** That is deliberate and it is
      the thing being hunted: an id-less duplicate must be VISIBLE (ruling 048 —
      a duplicate is visible and reversible, a wrong absorption is neither).

    A stamped row whose id is not on today's board is therefore claimed by
    nobody. That is honest: either it is an adjacent-day game inside the ±18h
    window, or its stamp is wrong — and a wrong stamp showing up as an
    unclaimed row beats it silently satisfying the wrong fixture.

    **The name pass is bounded in TIME as well as in name, and this is the
    correctness argument the first production read paid for.** A baseball
    series plays the identical matchup on three consecutive days, so inside a
    ±18h window "Dodgers @ Tigers" names two or three real, distinct, perfectly
    healthy games. Matching on names alone, the first live run reported MLB as
    ``17 fixtures, 17 duplicated`` — a total-outage headline manufactured
    entirely by the matcher out of an ordinary Thursday. An unstamped event may
    therefore only reach a fixture within :data:`MAX_NAME_SKEW_HOURS`, so
    tomorrow's series game falls to nobody: tomorrow's fixture is not on today's
    board.

    **And the name pass is ONE-TO-ONE, which is the correctness argument
    CERT-434 paid for.** Bounding in time is not enough on its own. Two games at
    17:00 and 20:00, the first pushed to 19:00 by rain: each row picking its own
    nearest fixture independently sends BOTH to the 20:00 fixture, because 19:00
    genuinely is nearer to 20:00 than to its own 17:00. The sentinel then files
    ``g1 missing`` and ``g2 dupes=2`` about two healthy games and points the
    repair lane at deduplicating real rows. Same-matchup fixtures and rows are
    therefore solved together as a bounded minimum-TOTAL-skew assignment
    (:func:`_optimal_assignments`): the pairing costing ``2.0 + 0.0`` beats the
    one costing ``1.0 + 3.0``, and each game lands on its own fixture.

    Three properties of that solve carry their own weight:

    * **Refusal beats a coin flip — but only over a tie that MATTERS.** Every
      optimal pairing is enumerated and each is turned into the rows it would
      actually publish. If they all publish the same thing the tie is cosmetic
      and is ignored: two of our rows recorded at the same minute really are
      interchangeable, and refusing there would mute a real duplicate. Only when
      the options disagree about which fixture holds what is the whole group
      marked :attr:`FixtureRow.ambiguous` — not graded, not an offender, cannot
      make a league red. Measured on the 2026-08-29 slate, which carries two
      genuine doubleheaders: zero refusals.
    * **Duplicates still surface.** Rows left over once every fixture in the
      group holds one land on their nearest fixture anyway, so three rows for a
      two-game doubleheader still read ``dupes=2`` on one of them. The fix must
      not become a way of hiding the thing the sentinel is for.
    * **A fixture already settled by id is occupied, not available.** It cannot
      win an id-less row in the assignment, so a delayed row takes the EMPTY
      fixture beside it rather than piling onto the stamped one for being
      nearer. It can still receive a leftover, which is a real duplicate.
    """
    by_espn: dict[str, list[dict]] = {}
    for ev in events:
        if ev.get("espn_id"):
            by_espn.setdefault(str(ev["espn_id"]), []).append(ev)

    claims: list[list[dict]] = [[] for _ in fixtures]
    claimed_ids: set[int] = set()
    for idx, fx in enumerate(fixtures):
        if fx.get("espn_id"):
            for ev in by_espn.get(str(fx["espn_id"]), []):
                if ev["id"] not in claimed_ids:
                    claims[idx].append(ev)
                    claimed_ids.add(ev["id"])

    # Group fixtures and the id-less rows by matchup. `_matchup_key` equality is
    # `fixture_matches`, so two members of different groups can never claim each
    # other and each group is solvable on its own.
    fx_groups: dict[tuple[str, str], list[int]] = {}
    for idx, fx in enumerate(fixtures):
        key = _matchup_key(fx.get("home") or "", fx.get("away") or "")
        if key is not None:
            fx_groups.setdefault(key, []).append(idx)

    ev_groups: dict[tuple[str, str], list[dict]] = {}
    for ev in events:
        if ev.get("espn_id") or ev["id"] in claimed_ids:
            continue
        key = _matchup_key(
            ev.get("home_team_name") or "", ev.get("away_team_name") or ""
        )
        if key is not None and key in fx_groups:
            ev_groups.setdefault(key, []).append(ev)

    ambiguous: set[int] = set()
    for key, group_evs in ev_groups.items():
        fx_idxs = fx_groups[key]
        # Skew of every admissible (fixture, event) pair. An unparseable start
        # or one outside the window is simply not admissible — declining beats
        # guessing, and an unclaimed row is a legible answer.
        skews: dict[tuple[int, int], float] = {}
        for gi, idx in enumerate(fx_idxs):
            for ge, ev in enumerate(group_evs):
                skew = _skew_hours(
                    ev.get("commence_time"), fixtures[idx].get("kickoff")
                )
                if skew is not None and skew <= MAX_NAME_SKEW_HOURS:
                    skews[(gi, ge)] = skew
        if not skews:
            continue

        def place(pairs: dict[int, int]) -> list[list[int]]:
            """Where every row in the group ends up under one assignment.

            Leftovers — rows for which no one-to-one slot remained — fall to
            their nearest admissible fixture. That is how a genuine duplicate
            stays visible once every fixture in the group already holds a row:
            the fix must not become a way of hiding what the sentinel is for.
            """
            out: list[list[int]] = [[] for _ in fx_idxs]
            for gi, ge in pairs.items():
                out[gi].append(ge)
            for ge in range(len(group_evs)):
                if ge in pairs.values():
                    continue
                best: tuple[float, int] | None = None
                for gi in range(len(fx_idxs)):
                    skew = skews.get((gi, ge))
                    if skew is not None and (best is None or skew < best[0]):
                        best = (skew, gi)
                if best is not None:
                    out[best[1]].append(ge)
            return out

        # Only fixtures the id pass left empty compete for a one-to-one slot.
        slots = [gi for gi, idx in enumerate(fx_idxs) if not claims[idx]]
        if len(slots) > MAX_GROUP_FIXTURES or len(group_evs) > MAX_GROUP_EVENTS:
            ambiguous.update(fx_idxs)
            placement = place({})
        else:
            options, truncated = _optimal_assignments(
                {(slots.index(gi), ge): c
                 for (gi, ge), c in skews.items() if gi in slots},
                len(slots), len(group_evs),
            )
            placements = [
                place({slots[f]: e for f, e in pairs.items()}) for pairs in options
            ] or [place({})]
            # A tie only matters if it changes what gets PUBLISHED. Two rows at
            # the same minute are interchangeable — every optimal pairing puts
            # the same two rows on the same fixture, so there is nothing to
            # refuse and a real duplicate is still reported. Refuse only when
            # the options genuinely disagree about which fixture holds what.
            distinct = {
                tuple(tuple(sorted(f)) for f in p) for p in placements
            }
            if truncated or len(distinct) > 1:
                ambiguous.update(fx_idxs)
            placement = placements[0]

        for gi, ges in enumerate(placement):
            for ge in ges:
                claims[fx_idxs[gi]].append(group_evs[ge])
                claimed_ids.add(group_evs[ge]["id"])

    # Input order, not solve order — a fixture's claims read the way the events
    # arrived, so the payload is stable across runs of the same slate.
    order = {ev["id"]: i for i, ev in enumerate(events)}
    for idx in range(len(fixtures)):
        claims[idx].sort(key=lambda e: order[e["id"]])

    rows: list[FixtureRow] = []
    for idx, fx in enumerate(fixtures):
        claimed = claims[idx]
        conflicts: list[dict[str, Any]] = []
        if not claimed:
            # Nothing claimed this fixture. Before calling it missing, look for
            # a row that names it AT ITS TIME but carries somebody else's id —
            # a wrong stamp, not an absent game. Measured on the first live run:
            # BOS @ NYY 2026-08-29 17:05Z, event 14877917 stamped 401815659
            # while the board says 401874913.
            for ev in events:
                if ev["id"] in claimed_ids or not ev.get("espn_id"):
                    continue
                if not fixture_matches(
                    ev.get("home_team_name") or "", ev.get("away_team_name") or "",
                    fx.get("home") or "", fx.get("away") or "",
                ):
                    continue
                skew = _skew_hours(ev.get("commence_time"), fx.get("kickoff"))
                if skew is not None and skew <= MAX_NAME_SKEW_HOURS:
                    conflicts.append(
                        {"event_id": ev["id"], "espn_id": str(ev["espn_id"])}
                    )
        sources: dict[str, bool] = {}
        if len(claimed) == 1:
            ev = claimed[0]
            sources = {
                "kalshi": bool(ev.get("has_kalshi")),
                "polymarket": bool(ev.get("has_polymarket")),
                "espn": bool(ev.get("has_espn")),
                "odds_api": bool(ev.get("has_odds_api")),
            }
        rows.append(FixtureRow(
            label=fx.get("label") or "",
            kickoff=fx.get("kickoff"),
            event_ids=[e["id"] for e in claimed],
            sources=sources,
            truth_ref=fx.get("espn_id") or fx.get("datagolf_event_id"),
            id_conflicts=conflicts,
            ambiguous=idx in ambiguous,
        ))
    return rows


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------


def _write_redis(day: str, payload: dict) -> bool:
    from app.tasks.redis_state import get_redis_client

    try:
        client = get_redis_client()
        if client is None:
            return False
        client.setex(
            REDIS_KEY_TEMPLATE.format(date=day), REDIS_TTL_SECONDS, json.dumps(payload)
        )
        return True
    except Exception as exc:
        logger.warning("rollcall: redis write failed for %s: %s", day, exc)
        return False


def read_redis_history(days: int = 30, before: str | None = None) -> list[dict]:
    """The trailing scorecards a measured domain's baseline is cut from.

    Reads whole days, newest first, skipping the day being graded. A missing day
    is simply absent — an off-day or a run that did not happen is not a zero.
    """
    from app.tasks.redis_state import get_redis_client

    out: list[dict] = []
    try:
        client = get_redis_client()
        if client is None:
            return out
        anchor = _date.fromisoformat(before) if before else _utc_now().date()
        for back in range(1, days + 1):
            key = REDIS_KEY_TEMPLATE.format(date=(anchor - timedelta(days=back)).isoformat())
            raw = client.get(key)
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        logger.warning("rollcall: redis history read failed: %s", exc)
    return out


async def _write_scores(session, day: str, cards: list[dict]) -> int:
    """Upsert one row per ``(date, league)``. Idempotent by design.

    Written through Core SQL rather than ORM attribute assignment because the
    payload columns are JSONB (gotcha #4), and per-league so one malformed card
    cannot lose the whole day's record.
    """
    from sqlalchemy import text

    written = 0
    for card in cards:
        try:
            await session.execute(
                text("""
                    INSERT INTO rollcall_scores (
                        score_date, league, axiom, events_external, graded,
                        ambiguous, matched_1,
                        dupes, missing, mis_stamped, clean, per_source, verdict,
                        offenders, justification, generated_at
                    ) VALUES (
                        :d, :league, :axiom, :ext, :graded, :ambiguous,
                        :m1, :dupes, :missing,
                        :mis_stamped, :clean,
                        CAST(:per_source AS jsonb), :verdict, CAST(:offenders AS jsonb),
                        :justification, now()
                    )
                    ON CONFLICT (score_date, league) DO UPDATE SET
                        axiom = EXCLUDED.axiom,
                        events_external = EXCLUDED.events_external,
                        graded = EXCLUDED.graded,
                        ambiguous = EXCLUDED.ambiguous,
                        matched_1 = EXCLUDED.matched_1,
                        dupes = EXCLUDED.dupes,
                        missing = EXCLUDED.missing,
                        mis_stamped = EXCLUDED.mis_stamped,
                        clean = EXCLUDED.clean,
                        per_source = EXCLUDED.per_source,
                        verdict = EXCLUDED.verdict,
                        offenders = EXCLUDED.offenders,
                        justification = EXCLUDED.justification,
                        generated_at = now()
                """),
                {
                    "d": day,
                    "league": card["league"],
                    "axiom": bool(card.get("axiom", True)),
                    "ext": int(card.get("events_external", 0) or 0),
                    # A measured-domain card has no binder and therefore no
                    # refusals: its whole population is graded.
                    "graded": int(
                        card.get("graded", card.get("events_external", 0)) or 0
                    ),
                    "ambiguous": int(card.get("ambiguous", 0) or 0),
                    "m1": int(card.get("matched_1", 0) or 0),
                    "dupes": int(card.get("dupes", 0) or 0),
                    "missing": int(card.get("missing", 0) or 0),
                    "mis_stamped": int(card.get("mis_stamped", 0) or 0),
                    "clean": int(card.get("clean", 0) or 0),
                    "per_source": json.dumps(card.get("per_source") or {}),
                    "verdict": card.get("verdict", "unmeasurable"),
                    "offenders": json.dumps(card.get("offenders") or []),
                    "justification": card.get("justification"),
                },
            )
            await session.commit()
            written += 1
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "rollcall: score row failed for %s/%s: %s", day, card.get("league"), exc
            )
    return written


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def _grade_axiom_league(session, league: AxiomLeague, day: str) -> dict:
    """One league, isolated. A poison league never starves its siblings."""
    if league.truth == "datagolf":
        fixtures = await _datagolf_fixtures(league, day)
        truth_url = DATAGOLF_TRUTH_URL.format(tour=league.truth_key)
    else:
        from app.utils.sport_keys import SPORT_LEAGUE_MAP

        fixtures = await _espn_fixtures(league, day)
        path = SPORT_LEAGUE_MAP.get(league.truth_key, ("", ""))
        truth_url = ESPN_TRUTH_URL.format(
            sport=path[0], league=path[1], date=day.replace("-", "")
        )

    events = await _our_events(session, league.sport_keys, day)
    rows = _attach(fixtures, events)
    card = score_fixtures(rows, league.axiom_sources)
    offenders = axiom_offenders(rows, league.axiom_sources)
    red = axiom_is_red(card, league.axiom_sources)

    if card["events_external"] == 0:
        verdict = "off_day"
    elif card["graded"] == 0:
        # Truth published fixtures and the binder could resolve none of them.
        # That is a third state and it gets its own word: `pass` would claim an
        # observation this run did not make, `red` would file the alarm the
        # refusal exists to prevent, and `off_day` would deny the slate existed.
        verdict = "ambiguous"
    else:
        verdict = "red" if red else "pass"

    card.update({
        "league": league.key,
        "axiom": True,
        "axiom_sources": list(league.axiom_sources),
        "verdict": verdict,
        "offenders": offenders,
        "justification": "; ".join(league.exclusions) or None,
        "truth_url": truth_url,
        "truth": league.truth,
    })
    return card


async def _grade_measured_domain(session, domain, day: str, history: list[dict]) -> dict:
    """A partial domain, graded against its own trailing linkage rate.

    There is no external fixture list here (that is precisely why the domain is
    partial), so the measured quantity is our own linked-share: of the events we
    hold in the window, how many carry a prediction-market link. A 2σ drop from
    the trailing mean is the alarm.
    """
    events = await _our_events(session, domain.sport_keys, day)
    total = len(events)
    linked = sum(
        1 for e in events if e.get("has_kalshi") or e.get("has_polymarket")
    )
    today_rate = (linked / total) if total else None

    prior: list[float] = []
    for snap in history:
        for card in (snap.get("measured") or []):
            if card.get("league") == domain.key and card.get("rate") is not None:
                prior.append(float(card["rate"]))
    verdict, evidence = baseline_verdict(prior, today_rate)

    return {
        "league": domain.key,
        "axiom": False,
        "events_external": total,
        "matched_1": total,
        "dupes": 0,
        "missing": 0,
        "clean": linked,
        "per_source": {},
        "rate": today_rate,
        "verdict": "pass" if verdict == "pass" else ("red" if verdict == "drop" else "unmeasurable"),
        "baseline": evidence,
        "offenders": [],
        "justification": domain.justification,
    }


async def run_rollcall(
    date: str | None = None, file_issues: bool = True, now: datetime | None = None
) -> dict:
    """Grade the day's slate and publish the scorecard.

    Returns the payload written to Redis, plus a ``terminal`` the Celery wrapper
    hands to ``task_verdict``.
    """
    from app.tasks.base import get_task_session

    started = _time.monotonic()
    moment = now or _utc_now()
    day = date or moment.strftime("%Y-%m-%d")

    axiom_cards: list[dict] = []
    measured_cards: list[dict] = []
    truth_failures: list[dict] = []
    history = read_redis_history(before=day)

    async with get_task_session() as session:
        for league in AXIOM_LEAGUES:
            if _time.monotonic() - started > DEADLINE_SECONDS:
                truth_failures.append({"league": league.key, "error": "run deadline reached"})
                continue
            try:
                axiom_cards.append(await _grade_axiom_league(session, league, day))
            except Exception as exc:
                logger.warning("rollcall: %s truth read failed: %s", league.key, exc)
                truth_failures.append({"league": league.key, "error": str(exc)[:200]})
                axiom_cards.append({
                    "league": league.key, "axiom": True, "events_external": 0,
                    "matched_1": 0, "dupes": 0, "missing": 0, "clean": 0,
                    "per_source": {}, "verdict": "truth_unavailable",
                    "offenders": [], "justification": f"truth read failed: {str(exc)[:120]}",
                })

        for domain in MEASURED_DOMAINS:
            try:
                measured_cards.append(
                    await _grade_measured_domain(session, domain, day, history)
                )
            except Exception as exc:
                logger.warning("rollcall: %s baseline failed: %s", domain.key, exc)
                measured_cards.append({
                    "league": domain.key, "axiom": False, "events_external": 0,
                    "matched_1": 0, "dupes": 0, "missing": 0, "clean": 0,
                    "per_source": {}, "verdict": "unmeasurable", "offenders": [],
                    "justification": domain.justification,
                })

        graded = [c for c in axiom_cards if c["verdict"] != "truth_unavailable"]
        payload = {
            "schema": SCORECARD_SCHEMA,
            "date": day,
            "generated_at": moment.isoformat(),
            "axiom": axiom_cards,
            "measured": measured_cards,
            "truth_failures": truth_failures,
            "coverage_pct": coverage_percent(graded),
            "leagues_red": [c["league"] for c in axiom_cards + measured_cards
                            if c["verdict"] == "red"],
        }

        redis_ok = _write_redis(day, payload)
        rows_written = await _write_scores(session, day, axiom_cards + measured_cards)

    filings = []
    if file_issues:
        filings = _reconcile(day, axiom_cards)

    payload["redis_written"] = redis_ok
    payload["rows_written"] = rows_written
    payload["filings"] = filings
    payload["duration_s"] = round(_time.monotonic() - started, 2)
    payload["terminal"] = rollcall_terminal(
        leagues_graded=len(graded),
        leagues_expected=len(AXIOM_LEAGUES),
        truth_failures=len(truth_failures),
        mirror_written=rows_written == len(axiom_cards) + len(measured_cards),
    )
    logger.info(
        "rollcall %s: coverage=%s red=%s terminal=%s",
        day, payload["coverage_pct"], payload["leagues_red"], payload["terminal"],
    )
    return payload


def _reconcile(day: str, axiom_cards: list[dict]) -> list[dict]:
    """File or resolve ONE issue per league through the shared rail.

    ``truth_unavailable`` leagues are skipped in BOTH directions: a league we
    could not observe must not file (we have no evidence) and must not close an
    open issue (we have no evidence of recovery either).

    A league whose whole slate the binder refused (``ambiguous``) is skipped on
    exactly the same argument, and it is the direction that bites: without this,
    ``red`` reads False, the rail takes the green path, and an open roll-call
    issue gets CLOSED with a comment saying the league is clean — on a day the
    league was never graded at all.
    """
    from app.tasks.sentinel_filing import fetch_open_alert_issues, reconcile_issue

    open_issues = fetch_open_alert_issues()
    out = []
    for card in axiom_cards:
        if card["verdict"] in ("truth_unavailable", "ambiguous"):
            out.append({
                "league": card["league"],
                "action": f"skipped_{card['verdict']}",
            })
            continue
        league = card["league"]
        offenders = card.get("offenders") or []
        red = card["verdict"] == "red"
        fp = rollcall_fingerprint(league, offenders)
        try:
            result = reconcile_issue(
                red=red,
                fingerprint=fp,
                marker_key=FINGERPRINT_MARKER,
                title=build_rollcall_issue_title(league, card),
                title_prefix=f"[rollcall] {league.upper()}:",
                body=build_rollcall_issue_body(
                    league, day, card, offenders, card.get("truth_url", ""),
                    card.get("axiom_sources") or [],
                    [card["justification"]] if card.get("justification") else [],
                ),
                red_body=build_rollcall_issue_body(
                    league, day, card, offenders, card.get("truth_url", ""),
                    card.get("axiom_sources") or [],
                    [card["justification"]] if card.get("justification") else [],
                ),
                green_comment=(
                    f"Roll call {day}: {league.upper()} is clean — "
                    f"{card.get('clean')}/"
                    f"{card.get('graded', card.get('events_external'))} graded "
                    f"fixtures with exactly one event and every axiom source "
                    f"linked."
                    + (
                        f" ({card['ambiguous']} further fixture(s) refused as "
                        f"ambiguous and not graded.)"
                        if card.get("ambiguous") else ""
                    )
                ),
                open_issues=open_issues,
            )
        except Exception as exc:  # one league's filing never sinks the run
            logger.warning("rollcall: filing failed for %s: %s", league, exc)
            result = {"action": "error", "error": str(exc)[:200]}
        result["league"] = league
        out.append(result)
    return out


async def _run_rollcall(date: str | None = None, file_issues: bool = True) -> dict:
    """Celery entry point. Kept thin so the logic above stays testable."""
    return await run_rollcall(date=date, file_issues=file_issues)
