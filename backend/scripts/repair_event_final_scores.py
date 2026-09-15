"""CAL-P002 — repair settled events frozen on a NON-FINAL score.

Invariant: a settled event's stored score IS the game's final score. A violation
means the page shows a wrong final (we held ``BOS 3-1`` where the real final was
``6-3``) and every score-derived grade underneath it stands on a mid-game number.

🔴 TWO DEFECT CLASSES WITH OPPOSITE REMEDIES SHARE THIS RAIL (#1980, queue 380).
Read this before adding anything that writes.

A settled row that disagrees with ESPN can be wrong in TWO different fields, and
the fix for one is the corruption for the other:

* ``score_drifted`` — the row's ``espn_id`` is PROVEN to be its own game and the
  stored score is not that game's final. Remedy: this repair, ``apply=true``.
* ``espn_id_drifted`` — the ``espn_id`` is ITSELF the wrong field; it names a
  different game (usually the same series, one or two slate-days off — measured
  offsets of exactly ±15 and ±30 in ESPN id space). **A score repair here writes
  another game's final onto this row.** Measured 2026-08-19 over the 262 settled
  MLB rows of the last 32 days: 21 rows carry a drifted ``espn_id``, and for
  **8 of them the stored score is already CORRECT** — the score remedy would
  have corrupted a currently-correct score. Remedy: ``event-espn-id`` (attended,
  plan-hashed), never this rail.
* ``espn_id_unresolvable`` — the ``espn_id`` is simply ABSENT from our own
  slate and no single game on that slate is provably ours (a doubleheader, or a
  postponement). Gotcha #53: an empty read is not a fact. No remedy is proven;
  it is REPORTED, never guessed at, and never handed the score remedy.

Until queue 380 the rail computed the linkage classes and then **discarded them
silently**: ``espn_not_found`` was a bare counter with no ledger row at all, and
the sentinel's detector filtered the ledger to ``fix_score``. So the two classes
rendered identically — as nothing — while the failure text the sentinel prints
on every line was the SCORE remedy. Every disposition now lands in the ledger
with an explicit ``defect_class`` and its own ``remedy``, and no row that is not
``proven`` can reach a write.

WHY NOTHING ELSE FIXES THIS. Two rails write settled scores today and both have a
hole this repair fills:

* ``_corrected_final_score`` (``tasks/espn_sync.py``) refuses to write unless our
  stored total is **0** — deliberately, citing gotcha #21 ("a real non-zero stored
  score is NEVER overwritten"). A score frozen at a plausible ``3-2`` is therefore
  structurally uncorrectable by every existing path.
* ``backfill_missing_scores`` (``utils/espn_helpers.py``) is gated on
  ``home_score IS NULL`` and a 7-day window. Same blind spot.

The producer is the wall-clock staleness net (``espn_sync._transition_event_statuses_impl``
and ``odds_polling.detect_and_close_stale_events``): both close an event purely on
elapsed time, keep whatever score the last poll happened to have written, and then
grade ``win_probability_sources.final_result`` to 1.0/0.0 off that mid-game score.
So a frozen 3-2 in the 6th becomes a permanent "home team won".

CAL-P002's measured evidence (2026-08-05, identity-verified vs ESPN finals):

    closed  · NHL/NBA/MLB/WNBA     10 / 399  =  2.5%
    closed  · NCAA Baseball        43 / 388  = 11.1%
    completed · major, 2-9d old    19 /  70  = 27.1%   <- all MLB
    completed · major, 30-60d      43 / 199  = 21.6%   <- all MLB
    completed · major, 100-160d     6 / 200  =  3.0%

Two sub-classes, ONE fix (overwrite with the event's own ESPN final):
  A. frozen in-progress score — NBA ev12080353 held 45-56 (a halftime score) for a
     game ESPN finalled 87-109; MLB/NCAA rows frozen at 0-0.
  B. wrong-game score from the same series — ev15182558 (Giants@Brewers 7/29) held
     ``SF 2-8 MIL``, which is the final of the 7/28 game. Its ``espn_id`` and
     ``commence_time`` both correctly identify the 7/29 game; only the score is
     another game's. (Link-level series mislinkage stays #1466 scope; this repairs
     the score value, not the link.)

SAFETY RAILS (each one earned):
  * Writes ONLY when ESPN reports the game FINAL (``status == "post"``). Writing a
    non-final ESPN score is bug #980/#981 recurring.
  * TEAM-IDENTITY GUARD: our home/away must match ESPN's home/away for that
    ``espn_id`` before we trust its score. The CAL-P002 census found 3 NCAA-Baseball
    rows whose ``espn_id`` points at a different game entirely — repairing off those
    would import a wrong score, not remove one. Identity-blocked rows are reported,
    never written (they are an ``espn_id`` linkage defect, a different repair).
  * ``completed_at`` is derived from the last REAL post-commence snapshot (gotcha
    #22), never ``now()``, and never written if that would invert ``commence_time``
    (gotcha #46). No snapshot ⇒ left NULL and reported.
  * When a corrected score changes the winner, ``win_probability_sources`` is
    re-resolved through the EXISTING ``_apply_final_pm_win_prob`` helper (#1000
    shape-safe). This changes no weights and no blend math — it restamps a derived
    final that was computed from the wrong score.
  * QUEUE 067 — the outcome grades that stood on the replaced score are RETRACTED
    in the same transaction. ``game_score`` and its ``EVENTS_DERIVED_SOURCES``
    siblings are tier 2 but NOT overwritable, so ``backfill_winners``' HAVING
    clause permanently excludes any market carrying one: fixing the score under a
    ``game_score`` grade changed nothing a user saw. Their ``is_winner`` goes to
    NULL — UNKNOWN, never False, which is an affirmative graded loss — which
    drops the market back into that clause for the real grader to re-decide from
    the corrected score. Never re-graded here (this rail cannot parse a 1H spread
    or a prop bound), never applied to a venue settlement, and never to an event
    whose score this pass did not itself prove wrong and fix.
  * Commits per (sport, date) group, so a 30s HTTP timeout leaves consistent,
    resumable progress. Walk the population with ``offset``, advancing by the
    returned ``next_offset`` until ``groups_remaining`` is 0.
  * Oldest-first by default (gotcha #41 — newest-first ordering never reaches the
    old tail).

REACHABILITY (CAL-P002B, 2026-08-07). As first shipped this repair was live but
uncallable on the cohorts that hold the defects, for two independent reasons:

  1. ``limit`` bounded the ESPN calls, not the scan. Every candidate row carried
     two correlated ``MAX()`` subqueries and the slice happened in Python
     afterwards, so cost tracked the whole population and any unscoped call H12'd
     at the 30s router wall (``limit=3`` and ``limit=25`` alike). The group
     selection now happens in SQL, before the work.
  2. It was not resumable. The group predicate is unchanged by the repair, so
     re-invoking returned the same oldest groups forever and ``groups_remaining``
     never fell. Progress now comes from an explicit ``offset`` cursor.

    POST /api/admin/repairs/event-final-scores?apply=false                 # dry-run census
    POST /api/admin/repairs/event-final-scores?apply=true&offset=25        # next batch

    python3 scripts/repair_event_final_scores.py                   # dry-run ledger
    python3 scripts/repair_event_final_scores.py --apply --offset 25

Heroku one-off (gotcha #48 — non-detached does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`). Prefer the endpoint.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Settled events that ESPN can adjudicate: terminal status, a stored score, an
# espn_id to look up, and old enough that "still being played" is not the answer.
#
# ONE definition, three consumers (group census, candidate fetch, after-census) so
# the bound and the work can never drift onto different populations.
_SETTLED_PREDICATE = """
      e.status IN ('closed', 'completed')
      AND e.espn_id IS NOT NULL
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.commence_time < NOW() - INTERVAL '2 days'
      AND s.key = ANY(:sport_keys)
"""

_GAME_DATE_EXPR = "(e.commence_time AT TIME ZONE 'America/New_York')::date"

# STEP 1 — the cheap bound. A plain GROUP BY over the settled predicate: no
# correlated subqueries, no per-row work. This is what `limit` slices, and it must
# run BEFORE anything expensive.
#
# WHY THIS SHAPE (the CAL-P002B defect): the first cut fetched every candidate row
# — each carrying two correlated MAX() subqueries against win_prob_snapshots and
# odds_snapshots — and only then sliced to `limit` groups in Python. So `limit`
# bounded the ESPN calls but not the scan, cost tracked the whole population at
# ~40ms/row, and every unscoped call H12'd at the 30s router wall (measured
# 2026-08-07: limit=3 and limit=25 alike). The two defect-heavy cohorts,
# baseball_mlb and baseball_ncaa, were exactly the ones too big to reach.
_GROUPS_SQL = f"""
    SELECT s.key AS sport_key,
           {_GAME_DATE_EXPR} AS game_date,
           COUNT(*) AS n
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
    GROUP BY 1, 2
"""

# STEP 2 — candidate rows for the SELECTED groups only. The unnest join makes the
# (sport, date) pair filter exact rather than a cross-product of the two arrays.
# CAST(... AS type[]) rather than `::type[]`: a bind param followed by a `::` cast
# is dropped by SQLAlchemy text() under asyncpg.
_CANDIDATE_SQL = f"""
    SELECT e.id AS event_id, e.espn_id, s.key AS sport_key, e.status AS ev_status,
           e.home_team_name, e.away_team_name, e.home_score, e.away_score,
           e.commence_time, e.completed_at,
           {_GAME_DATE_EXPR} AS game_date
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    JOIN unnest(CAST(:g_sports AS text[]), CAST(:g_dates AS date[]))
           AS g(sport_key, game_date)
      ON g.sport_key = s.key AND g.game_date = {_GAME_DATE_EXPR}
    WHERE {_SETTLED_PREDICATE}
    ORDER BY e.commence_time
"""

_POPULATION_SQL = f"""
    SELECT COUNT(*) AS n
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
"""

# STEP 3 — completed_at derivation, batched and lazy. This is the work that used to
# ride on EVERY candidate row as two correlated subqueries; only rows with a NULL
# completed_at need it, and they are the minority (CAL-P002 census: ~8%).
#
# Shared with the two staleness nets that PRODUCE the gap, so the producer and the
# repair can never disagree about what "when did this game end" means.
from app.utils.event_completion import (  # noqa: E402
    LAST_POST_COMMENCE_SNAPSHOT_SQL as _LAST_SNAPSHOT_SQL,
)

# Queue 067 — the grades computed from the very columns this rail overwrites.
# Imported, never restated: the 038 suite scans `backfill_winners` for sources
# that read `events` and asserts they are all declared in this one set, so a new
# events-derived grader is covered by this retraction the day it is added.
from app.utils.resolution_authority import EVENTS_DERIVED_SOURCES  # noqa: E402

_EVENTS_DERIVED_LIST: list[str] = sorted(EVENTS_DERIVED_SOURCES)

_FIX_SCORE_SQL = """
    UPDATE events SET home_score = :home_score, away_score = :away_score
    WHERE id = :event_id
"""

_FIX_COMPLETED_AT_SQL = """
    UPDATE events SET completed_at = :completed_at WHERE id = :event_id
"""

# ---------------------------------------------------------------------------
# QUEUE 067 — THE GRADES THAT STOOD ON THE SCORE WE JUST REPLACED.
#
# Fixing `events.home_score`/`away_score` silently invalidates every outcome
# graded FROM those columns, and until now this rail left them exactly as they
# were. That is not a cosmetic gap: `game_score` and its siblings are tier 2 and
# are NOT in OVERWRITABLE_WINNER_SOURCES, so `backfill_winners`' re-resolution
# HAVING clause excludes any market carrying one (lines 1290 / 2000 — "SUM(CASE
# WHEN fo.is_winner AND fo.resolution_source NOT IN <overwritable>) = 0"). A
# grade minted from a wrong final is therefore permanent, and repairing the
# score underneath it changes nothing a user sees.
#
# Measured on production 2026-09-01: 814 `game_score` + 248 `box_score` outcome
# rows are graded on terminal events holding an equal score, on top of 371
# `pass2_loser` and 208 `pass2_guess`. #2496 measures the draw-impossible slice
# at 354 rows across 9 events.
#
# WHY RETRACT AND NOT RE-GRADE. This rail knows the corrected score; it does not
# know how to parse "wins the 1H by over N" or a player-prop bound, and
# re-implementing that here would be a second grader competing with the real
# one. `repair_kalshi_fabricated_loss` is the precedent and its rule is the
# right one: a repair removes a claim it has disproven, and hands the question
# back to the authority that answers it. Setting `is_winner` NULL — UNKNOWN
# truth, never False, which is an affirmative graded LOSS (see the FuturesOutcome
# column comment) — drops the market back into that HAVING clause, and the next
# `backfill_winners` pass re-grades it from the score we just corrected.
#
# So gotcha #21 ("never bulk-reset is_winner without an immediate re-resolve
# source") is satisfied structurally, not by promise: this only ever runs on an
# event whose ESPN final we hold, in the same transaction that writes it.
#
# SCOPED THREE WAYS, because a retraction is data-destructive:
#   * only events this rail PROVED wrong and corrected in this same pass;
#   * only EVENTS_DERIVED_SOURCES — the maintained set of grades computed from
#     our own events columns. A venue's `api_settlement` said what it said and
#     our score being wrong does not touch it (and it outranks these anyway);
#   * only rows that carry one of those sources, so a NULL/ungraded row is not
#     churned.
_RETRACT_EVENTS_DERIVED_GRADES_SQL = """
    UPDATE futures_outcomes fo
       SET is_winner = NULL, resolution_source = NULL
      FROM futures_markets fm
     WHERE fm.id = fo.market_id
       AND fm.event_id = :event_id
       AND fo.resolution_source = ANY(CAST(:sources AS text[]))
"""

# The dry run has to show this, or an operator approves a score fix without
# seeing that it also un-grades rows. Same predicate as the write.
_COUNT_EVENTS_DERIVED_GRADES_SQL = """
    SELECT COUNT(*) AS n
      FROM futures_outcomes fo
      JOIN futures_markets fm ON fm.id = fo.market_id
     WHERE fm.event_id = :event_id
       AND fo.resolution_source = ANY(CAST(:sources AS text[]))
"""

# Default group budget per invocation. Each group is ONE ESPN scoreboard call and
# the client sleeps 0.5s between requests, so this stays inside the 30s HTTP wall.
_GROUP_LIMIT = 25

# A count alone cannot bound wall-clock: a slow ESPN slate makes 25 groups overrun
# the 30s router wall even though 25 is usually comfortable. Check elapsed time
# BEFORE starting each group and stop early, reporting how far we actually got —
# bounding the loop boundary is only correct if the longest single uninterrupted
# op (one scoreboard fetch) fits in the margin. It does: ~1s against a 6s reserve.
_DEADLINE_SECONDS = 22.0
_GROUP_RESERVE_SECONDS = 6.0


def score_is_stale(our_home, our_away, espn_home, espn_away, espn_is_final: bool) -> bool:
    """True when a settled event's stored score disagrees with ESPN's FINAL.

    Deliberately the inverse of ``_corrected_final_score``'s "only when our total is
    0" rule: CAL-P002 proved the frozen-at-a-real-score case is the LARGER half of
    the defect (a frozen 3-2 is invisible to the total==0 test). ESPN's final is the
    authority for a settled game's score; a non-final ESPN reading never is.
    """
    if not espn_is_final:
        return False
    if espn_home is None or espn_away is None:
        return False
    if our_home is None or our_away is None:
        return False
    return (our_home, our_away) != (espn_home, espn_away)


def resolved_home_from_score(home_score: int, away_score: int) -> float:
    """The final win-prob a settled score implies (matches the staleness net)."""
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def _identity_matches(our_home, our_away, espn_home, espn_away) -> bool:
    """Does this ESPN game describe the SAME fixture as our event?

    Guards the case the census found: an ``espn_id`` pointing at a different game.
    Without this, "repair" would import a wrong score instead of removing one.
    """
    from app.utils.name_normalization import names_match

    if not (espn_home and espn_away):
        return False
    return bool(
        names_match(our_home or "", espn_home) and names_match(our_away or "", espn_away)
    )


def _espn_team_name(team) -> str:
    if team is None:
        return ""
    return team.display_name or team.name or team.short_name or ""


def espn_date_matches(our_game_date, espn_dt) -> bool:
    """Does this ESPN game fall on the SAME calendar day as our event?

    THE GUARD THAT TEAM IDENTITY CANNOT PROVIDE. In a playoff series the same two
    teams meet repeatedly, so ``_identity_matches`` passes on every game of the
    series — and CAL-P002 found events whose ``espn_id`` points at a DIFFERENT game
    of their own series:

        ev14861878  our 2026-06-09  ->  espn_id 401874173 is the 06-06 game
        ev14881094  our 2026-06-11  ->  espn_id 401874172 is the 06-04 game
        ev14792938  our 2026-05-27  ->  espn_id 401873385 is the 05-25 game
        ev14639101  our 2026-05-16  ->  espn_id 401871407 is the 05-12 game

    A simulated repair that trusted identity alone imported those neighbours'
    finals and RAISED the KXNHLSPREAD disagreement count 8 -> 14. The batched
    scoreboard-by-date fetch already makes this structurally impossible (a game on
    another date is simply absent from the slate we asked for), but that is a
    property of the fetch strategy, not of the write rule. Pin it here so a future
    per-event ``summary`` fallback cannot silently reintroduce the corruption.

    Both sides are normalized to US/Eastern — the same basis our ``game_date`` is
    computed on — so the comparison is symmetric, not a UTC/local mix.
    """
    if our_game_date is None or espn_dt is None:
        return False
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    dt = espn_dt
    if dt.tzinfo is None:
        from datetime import timezone as _tz

        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(et).date() == our_game_date


# ---------------------------------------------------------------------------
# THE SPLIT (#1980, queue 380) — one vocabulary, shared by this rail and the
# Flow Sentinel, so the guard and the repair can never disagree about which
# defect a row has or which remedy it is owed.
# ---------------------------------------------------------------------------
SCORE_DRIFTED = "score_drifted"
ESPN_ID_DRIFTED = "espn_id_drifted"
ESPN_ID_UNRESOLVABLE = "espn_id_unresolvable"
LINK_PROVEN = "proven"

#: class -> the ONLY remedy that class may be handed. Handing ``espn_id_drifted``
#: the score remedy is the corruption this split exists to make unrepresentable.
DEFECT_REMEDY = {
    SCORE_DRIFTED: (
        "POST /api/admin/repairs/event-final-scores?apply=true "
        "(score repair — the espn_id is proven correct for this row)"
    ),
    ESPN_ID_DRIFTED: (
        "LINKAGE repair, NOT a score repair: POST /api/admin/repairs/event-espn-id"
        "?probe=true (x3, >300s) then ?apply=false then attended "
        "?apply=true&plan_hash=... . Running the score repair on this row writes "
        "ANOTHER GAME'S final onto it"
    ),
    ESPN_ID_UNRESOLVABLE: (
        "NO remedy is proven — adjudicate by hand. The espn_id is absent from "
        "this row's own slate and no single game on that slate is provably ours "
        "(doubleheader / postponement). An empty read is not a fact (gotcha #53). "
        "Explicitly NOT the score repair"
    ),
}


def measurement_coverage(
    *, groups_scanned: int, groups_total: int, events_scanned: int, population: int
) -> dict:
    """How much of the surface this run actually looked at — as data, not prose.

    ``mode`` is ``"full"`` only when every group was scanned. Otherwise it is
    ``"sampled"`` and carries the rate and the population, so a count derived
    from it cannot be quoted as a population by accident. This is the shape the
    Flow Sentinel renders into its title and its issue body.
    """
    full = groups_total > 0 and groups_scanned >= groups_total
    rate = round(groups_scanned / groups_total, 4) if groups_total else None
    return {
        "mode": "full" if full else "sampled",
        "groups_scanned": groups_scanned,
        "groups_total": groups_total,
        "group_sample_rate": rate,
        "events_scanned": events_scanned,
        "population": population,
        "event_sample_rate": (
            round(events_scanned / population, 4) if population else None
        ),
    }


def _nearest_by_start(commence_time, games):
    """The game of ``games`` whose start is closest to ``commence_time``.

    ``None`` when there is nothing to compare — a missing time cannot elect a
    winner, and pretending it can is how a doubleheader gets paired by luck.
    """
    if commence_time is None:
        return None
    dated = [g for g in games if getattr(g, "date", None) is not None]
    if not dated:
        return None
    from datetime import timezone as _tz

    def _delta(g):
        d = g.date
        if d.tzinfo is None:
            d = d.replace(tzinfo=_tz.utc)
        ct = commence_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=_tz.utc)
        return abs((d - ct).total_seconds())

    return min(dated, key=_delta)


def _names_match_strict(a: str, b: str) -> bool:
    """Exact-or-suffix name equality — ``names_match`` WITHOUT its fuzzy stage.

    WHY A SECOND, STRICTER PREDICATE EXISTS. ``names_match`` falls back to a
    >= 0.5 token-overlap score, and two teams that share a city clear it:

        names_match("New York Mets", "New York Yankees")        -> True
        names_match("Los Angeles Dodgers", "Los Angeles Angels") -> True

    So the rail's ``_identity_matches`` guard — the one whose whole job is to
    stop a score being imported off the wrong game — passes on a Mets row
    pointed at a Yankees game. ev15173316 is the live specimen (measured
    2026-08-19): our row is Dodgers @ METS on 2026-07-24, its ``espn_id``
    401816142 is Dodgers @ YANKEES on 2026-07-17. That is not a near miss, it is
    a different fixture, and the loose predicate cannot see it.

    ``_identity_matches`` is deliberately left alone — its tolerance is what lets
    "Bruins" match "Boston Bruins" and it guards a write that already works. This
    stricter predicate is used only to ELECT a target and to detect a
    same-city impostor, never to widen what may be written.
    """
    from app.utils.name_normalization import normalize_name

    na, nb = normalize_name(a or ""), normalize_name(b or "")
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    sw, lw = shorter.split(), longer.split()
    return len(shorter) >= 4 and len(sw) < len(lw) and lw[-len(sw):] == sw


def same_fixture_games(home_team_name, away_team_name, board, game_date=None) -> list:
    """Every game on the slate WE ALREADY FETCHED that is OUR fixture, strictly.

    This is the second signal gotcha #53 demands, and it costs nothing: the
    scoreboard for our own game date is already in hand, so "our espn_id is not
    on our slate" can be upgraded from an empty read into a PROVEN drift with a
    named target whenever exactly one game on that slate is our fixture.

    Strict on BOTH axes, because this elects a repair target:

    * names — ``_names_match_strict``, so a same-city sibling (Mets/Yankees) is
      never proposed as the game a row "actually is";
    * date — the caller's own ET game date, so a board that happens to carry more
      than one day cannot contribute a candidate from the wrong one.
    """
    out = []
    for g in board or []:
        if game_date is not None and not espn_date_matches(
            game_date, getattr(g, "date", None)
        ):
            continue
        if _names_match_strict(
            home_team_name, _espn_team_name(getattr(g, "home_team", None))
        ) and _names_match_strict(
            away_team_name, _espn_team_name(getattr(g, "away_team", None))
        ):
            out.append(g)
    return out


def classify_espn_link(
    *,
    espn_id,
    commence_time,
    game_date,
    home_team_name,
    away_team_name,
    board,
) -> tuple[str, object, str]:
    """Which FIELD is wrong — the score, or the ``espn_id`` that names the game?

    Returns ``(verdict, target_game_or_None, reason)`` where ``verdict`` is
    ``LINK_PROVEN`` / ``ESPN_ID_DRIFTED`` / ``ESPN_ID_UNRESOLVABLE``. Pure over an
    already-fetched slate, so it is unit-testable and adds ZERO network cost.

    Only ``LINK_PROVEN`` may proceed to a score comparison. Everything else is a
    linkage finding and is reported with the linkage remedy.

    THE DOUBLEHEADER ARM IS NOT DECORATION. Both games of a doubleheader sit on
    the same slate with the same two teams, so ``espn_date_matches`` passes and
    ``_identity_matches`` passes on the WRONG sibling — the two guards this rail
    already had are structurally blind to it. Measured 2026-08-19: ev14788546 and
    ev15200380 (Cardinals @ Reds, 2026-08-17) both store ``commence_time``
    17:40Z while ev14788546's ``espn_id`` and score both belong to the 22:40Z
    game. One of the two fields drifted and this rail cannot tell which, so it
    says so instead of picking.
    """
    by_id = {str(g.espn_id): g for g in (board or []) if getattr(g, "espn_id", None) is not None}
    held = by_id.get(str(espn_id))
    sibs = same_fixture_games(home_team_name, away_team_name, board, game_date)

    if held is None:
        if len(sibs) == 1:
            return (
                ESPN_ID_DRIFTED,
                sibs[0],
                "espn_id is absent from this row's own slate while EXACTLY ONE "
                "game on that slate is our fixture — the id names another day's game",
            )
        if len(sibs) > 1:
            return (
                ESPN_ID_UNRESOLVABLE,
                None,
                f"espn_id is absent from this row's own slate and {len(sibs)} games "
                f"on it are our fixture (doubleheader) — no single target is proven",
            )
        return (
            ESPN_ID_UNRESOLVABLE,
            None,
            "espn_id is absent from this row's own slate and NO game on that slate "
            "is our fixture — a postponement or a slate gap reads exactly like a "
            "drift here, so nothing is claimed",
        )

    if not espn_date_matches(game_date, getattr(held, "date", None)):
        return (
            ESPN_ID_DRIFTED,
            sibs[0] if len(sibs) == 1 else None,
            "espn_id resolves to a game on a DIFFERENT date than this row's own",
        )

    if not _identity_matches(
        home_team_name,
        away_team_name,
        _espn_team_name(getattr(held, "home_team", None)),
        _espn_team_name(getattr(held, "away_team", None)),
    ):
        return (
            ESPN_ID_DRIFTED,
            sibs[0] if len(sibs) == 1 else None,
            "espn_id resolves to a DIFFERENT fixture on this row's own slate",
        )

    # THE SAME-CITY IMPOSTOR. ``_identity_matches`` just passed, but it accepts a
    # >= 0.5 token overlap, so a Mets row pointed at a Yankees game clears it.
    # Fires ONLY when the slate holds exactly one STRICT candidate and it is not
    # the id we hold — i.e. only when there is a demonstrably better answer. With
    # no strict alternative this stays silent and the loose match stands, so a
    # source with unusual naming still gets its score repaired.
    if len(sibs) == 1 and str(getattr(sibs[0], "espn_id", "")) != str(espn_id):
        return (
            ESPN_ID_DRIFTED,
            sibs[0],
            "espn_id resolves to a same-city IMPOSTOR fixture on this row's own "
            "slate (it clears the fuzzy name guard but a strictly-matching game "
            "on the same slate is a different id)",
        )

    if len(sibs) > 1:
        nearest = _nearest_by_start(commence_time, sibs)
        if nearest is not None and str(getattr(nearest, "espn_id", "")) != str(espn_id):
            return (
                ESPN_ID_UNRESOLVABLE,
                nearest,
                "doubleheader: this row's commence_time is nearest a DIFFERENT game "
                "of the same fixture, so either espn_id or commence_time drifted and "
                "this rail cannot tell which",
            )

    return (LINK_PROVEN, held, "")


async def repair(
    session,
    apply: bool,
    limit: int = _GROUP_LIMIT,
    sport: str | None = None,
    newest_first: bool = False,
    offset: int = 0,
    deadline_seconds: float = _DEADLINE_SECONDS,
) -> dict:
    """Session-taking core (shared by the CLI and POST /api/admin/repairs/
    event-final-scores). Commits per group when ``apply``; returns a
    before/after census plus a per-event ledger.

    ``limit`` bounds (sport, date) GROUPS — one ESPN scoreboard call each — not
    events. ``offset`` skips that many groups in the SAME deterministic order.

    WHY ``offset`` EXISTS. The original contract was "re-invoke while
    ``groups_remaining > 0``", which could never terminate: the group predicate is
    *unchanged by the repair* (a corrected score is still a settled event with a
    score and an espn_id), so ``ordered[:limit]`` returned the SAME oldest groups
    on every call and ``groups_remaining`` never fell. The rail could only ever
    have touched the first batch. Progress has to come from an explicit cursor,
    not from the work shrinking its own candidate set. Drive it with
    ``next_offset`` — which accounts for an early deadline stop, so it is correct
    even when fewer than ``limit`` groups were scanned.
    """
    import time

    from sqlalchemy import text

    from app.services.espn_api import get_espn_service
    from app.utils.sport_keys import ESPN_SPORT_MAPPING

    s = session
    started = time.monotonic()
    # Gate on the mapping the rest of the ESPN pipeline uses, so this repair never
    # attempts a fetch the other tasks would not make.
    sport_keys = sorted(ESPN_SPORT_MAPPING)
    if sport:
        sport_keys = [k for k in sport_keys if k == sport]
        if not sport_keys:
            return {
                "repair": "event-final-scores",
                "applied": False,
                "error": f"sport '{sport}' is not in ESPN_SPORT_MAPPING",
                "available": sorted(ESPN_SPORT_MAPPING),
            }

    # STEP 1 — bound first. One cheap GROUP BY gives both the census denominator
    # and the orderable group list, so `population` costs no extra scan.
    group_rows = (await s.execute(text(_GROUPS_SQL), {"sport_keys": sport_keys})).all()
    population = sum(int(g.n) for g in group_rows)
    ordered = sorted(
        ((g.sport_key, g.game_date) for g in group_rows),
        key=lambda k: (k[1], k[0]),
        reverse=bool(newest_first),
    )
    offset = max(0, int(offset))
    selected = ordered[offset : offset + max(0, int(limit))]

    # STEP 2 — fetch rows for the SELECTED groups only.
    rows = []
    if selected:
        rows = (await s.execute(text(_CANDIDATE_SQL), {
            "sport_keys": sport_keys,
            "g_sports": [k[0] for k in selected],
            "g_dates": [k[1] for k in selected],
        })).all()

    # Group by (sport_key, ET game date): one ESPN scoreboard call covers a slate.
    groups: dict[tuple[str, object], list] = {}
    for r in rows:
        groups.setdefault((r.sport_key, r.game_date), []).append(r)

    # STEP 3 — completed_at derivation, only for the rows that lack one.
    gap_ids = [r.event_id for r in rows if r.completed_at is None]
    last_snap: dict[int, object] = {}
    if gap_ids:
        last_snap = {
            row.event_id: row.last_snap
            for row in (await s.execute(
                text(_LAST_SNAPSHOT_SQL), {"event_ids": gap_ids}
            )).all()
        }

    espn = get_espn_service()
    stats = {
        "events_scanned": 0,
        "espn_not_found": 0,
        "espn_not_final": 0,
        "date_blocked": 0,
        "identity_blocked": 0,
        "doubleheader_ambiguous": 0,
        # THE SPLIT (#1980). `score_defects` is the score class ONLY; the two
        # linkage classes are counted separately because their remedies are
        # opposite. Never sum them into one headline.
        "espn_id_drifted": 0,
        "espn_id_drifted_with_target": 0,
        "espn_id_unresolvable": 0,
        "score_defects": 0,
        "completed_at_gaps": 0,
        "scores_repaired": 0,
        "completed_at_repaired": 0,
        "blend_repaired": 0,
        "winner_flips": 0,
        # Queue 067. Two counters, not one: what the plan SAYS it will un-grade
        # and what the database actually reported un-graded. A repair that
        # cannot show those agreeing has not shown its write landed.
        "grades_to_retract": 0,
        "grades_retracted": 0,
    }
    ledger: list[dict] = []
    groups_scanned = 0
    stopped_on_deadline = False

    for sport_key, game_date in selected:
        if time.monotonic() - started > deadline_seconds - _GROUP_RESERVE_SECONDS:
            # Stop cleanly with a truthful cursor rather than being cut off
            # mid-group by the router. Already-committed groups stand.
            stopped_on_deadline = True
            break
        groups_scanned += 1
        bucket = groups.get((sport_key, game_date)) or []
        try:
            board = await espn.get_scoreboard(sport_key, game_date.strftime("%Y%m%d"))
        except Exception as exc:  # a dead slate must not kill the whole batch
            ledger.append({
                "sport_key": sport_key, "date": game_date.isoformat(),
                "action": "skip_scoreboard_error", "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        if board is None:
            # AUTHORITY DARK (lane1/045). Every verdict below reads a row's
            # ABSENCE from this board as evidence (`skip_espn_id_off_slate`,
            # and the score comparison that follows a proven link). A board we
            # never received says nothing about any row in the bucket, so the
            # whole group is skipped and named in the ledger.
            ledger.append({
                "sport_key": sport_key, "date": game_date.isoformat(),
                "action": "skip_authority_dark", "events": len(bucket),
            })
            continue
        by_id = {str(e.espn_id): e for e in board if e.espn_id is not None}

        group_writes = 0
        for r in bucket:
            stats["events_scanned"] += 1

            # WHICH FIELD IS WRONG — asked BEFORE any score comparison, because a
            # score comparison against an id that is not this row's game is not a
            # measurement, it is the corruption. Nothing below `LINK_PROVEN` can
            # reach a write; every branch lands in the ledger with its class and
            # its own remedy, so the silent skip is structurally gone.
            verdict, target, reason = classify_espn_link(
                espn_id=r.espn_id,
                commence_time=r.commence_time,
                game_date=r.game_date,
                home_team_name=r.home_team_name,
                away_team_name=r.away_team_name,
                board=board,
            )
            if verdict != LINK_PROVEN:
                held = by_id.get(str(r.espn_id))
                if held is None:
                    stats["espn_not_found"] += 1
                    action = "skip_espn_id_off_slate"
                elif not espn_date_matches(r.game_date, held.date):
                    stats["date_blocked"] += 1
                    action = "skip_espn_id_wrong_date"
                elif not _identity_matches(
                    r.home_team_name, r.away_team_name,
                    _espn_team_name(held.home_team), _espn_team_name(held.away_team),
                ):
                    stats["identity_blocked"] += 1
                    action = "skip_identity_mismatch"
                else:
                    stats["doubleheader_ambiguous"] += 1
                    action = "skip_doubleheader_ambiguous"
                stats[verdict] += 1
                entry = {
                    "event_id": r.event_id, "sport_key": sport_key,
                    "status": r.ev_status, "espn_id": r.espn_id,
                    "matchup": f"{r.home_team_name} vs {r.away_team_name}",
                    "commence_time": (
                        r.commence_time.isoformat() if r.commence_time else None
                    ),
                    "our_date": r.game_date.isoformat() if r.game_date else None,
                    "stored_score": f"{r.home_score}-{r.away_score}",
                    "action": action,
                    "defect_class": verdict,
                    "reason": reason,
                    "remedy": DEFECT_REMEDY[verdict],
                }
                if held is not None:
                    entry["espn_for_stored_id"] = (
                        f"{_espn_team_name(held.away_team)} @ "
                        f"{_espn_team_name(held.home_team)} "
                        f"{held.away_score}-{held.home_score}"
                    )
                    entry["espn_date"] = held.date.isoformat() if held.date else None
                if target is not None:
                    entry["proposed_espn_id"] = str(target.espn_id)
                    entry["proposed_espn_final"] = (
                        f"{target.home_score}-{target.away_score}"
                    )
                    entry["proposed_espn_start"] = (
                        target.date.isoformat() if target.date else None
                    )
                    if verdict == ESPN_ID_DRIFTED:
                        stats["espn_id_drifted_with_target"] += 1
                ledger.append(entry)
                continue

            ee = target
            is_final = ee.status == "post"
            if not is_final:
                stats["espn_not_final"] += 1
                continue

            stale = score_is_stale(
                r.home_score, r.away_score, ee.home_score, ee.away_score, is_final
            )
            needs_completed_at = r.completed_at is None
            if not stale and not needs_completed_at:
                continue

            entry = {
                "event_id": r.event_id, "sport_key": sport_key,
                "status": r.ev_status, "espn_id": r.espn_id,
                "matchup": f"{r.home_team_name} vs {r.away_team_name}",
                "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            }

            new_completed_at = None
            if needs_completed_at:
                stats["completed_at_gaps"] += 1
                # Same rule the producers now use (gotcha #22/#46) — one helper,
                # so a fix on one side cannot leave the other behind.
                from app.utils.event_completion import derive_completed_at

                cand = derive_completed_at(
                    last_snap.get(r.event_id), r.commence_time
                )
                if cand is not None:
                    new_completed_at = cand
                    entry["new_completed_at"] = cand.isoformat()
                else:
                    entry["completed_at_action"] = "skip_no_post_commence_snapshot"

            if stale:
                stats["score_defects"] += 1
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                entry.update({
                    "stored_score": f"{r.home_score}-{r.away_score}",
                    "espn_final": f"{ee.home_score}-{ee.away_score}",
                    "winner_flip": old_res != new_res,
                    "action": "fix_score",
                    # The espn_id was PROVEN this row's own game above, which is
                    # the entire licence for the score remedy on this line.
                    "defect_class": SCORE_DRIFTED,
                    "remedy": DEFECT_REMEDY[SCORE_DRIFTED],
                })
                if old_res != new_res:
                    stats["winner_flips"] += 1

                # Queue 067: name the collateral BEFORE the write, so the
                # dry-run ledger an operator reads is the whole plan.
                n_stale_grades = (await s.execute(
                    text(_COUNT_EVENTS_DERIVED_GRADES_SQL),
                    {"event_id": r.event_id, "sources": _EVENTS_DERIVED_LIST},
                )).one().n
                if n_stale_grades:
                    entry["events_derived_grades"] = n_stale_grades
                    entry["grade_action"] = "retract_for_regrade"
                    stats["grades_to_retract"] += n_stale_grades
            else:
                entry["action"] = "fix_completed_at_only"

            ledger.append(entry)

            if not apply:
                continue

            if stale:
                await s.execute(text(_FIX_SCORE_SQL), {
                    "event_id": r.event_id,
                    "home_score": ee.home_score,
                    "away_score": ee.away_score,
                })
                stats["scores_repaired"] += 1
                group_writes += 1

                # The staleness net already graded the blend off the WRONG score.
                # Restamp it from the corrected one via the existing shape-safe
                # helper (#1000) — no weight or blend-math change.
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                if old_res != new_res:
                    from sqlalchemy import select, update as sql_update

                    from app.models.models import Event
                    from app.tasks.espn_sync import _apply_final_pm_win_prob

                    cur = (await s.execute(
                        select(Event.win_probability_sources).where(Event.id == r.event_id)
                    )).scalar_one_or_none()
                    if cur and "final_result" in (cur or {}):
                        await s.execute(
                            sql_update(Event)
                            .where(Event.id == r.event_id)
                            .values(
                                win_probability_sources=_apply_final_pm_win_prob(cur, new_res)
                            )
                        )
                        stats["blend_repaired"] += 1

                # Queue 067. Same transaction as the score write: the grades
                # derived from the old value never outlive it.
                if n_stale_grades:
                    res = await s.execute(
                        text(_RETRACT_EVENTS_DERIVED_GRADES_SQL),
                        {"event_id": r.event_id, "sources": _EVENTS_DERIVED_LIST},
                    )
                    stats["grades_retracted"] += res.rowcount or 0
                    group_writes += 1

            if new_completed_at is not None:
                await s.execute(text(_FIX_COMPLETED_AT_SQL), {
                    "event_id": r.event_id, "completed_at": new_completed_at,
                })
                stats["completed_at_repaired"] += 1
                group_writes += 1

        if apply and group_writes:
            # Commit per group: a timeout leaves consistent, resumable progress.
            await s.commit()

    after = (await s.execute(text(_POPULATION_SQL), {"sport_keys": sport_keys})).one().n
    next_offset = offset + groups_scanned
    return {
        "repair": "event-final-scores",
        "applied": bool(apply),
        "population": population,
        "population_after": after,
        "groups_total": len(ordered),
        "groups_offset": offset,
        "groups_scanned": groups_scanned,
        "groups_remaining": max(0, len(ordered) - next_offset),
        "next_offset": next_offset,
        "stopped_on_deadline": stopped_on_deadline,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "order": "newest_first" if newest_first else "oldest_first",
        "sport": sport or "all_espn_mapped",
        **stats,
        "defect_rate_scanned": (
            round(stats["score_defects"] / stats["events_scanned"], 4)
            if stats["events_scanned"] else None
        ),
        # COVERAGE, STATED (#1980, queue 380). Every count above is over
        # `events_scanned`, which is a SAMPLE of `population` whenever
        # `groups_remaining > 0`. A reader who cannot see the denominator reads
        # the sample count as the population — the nightly guard reported a
        # specific integer over 0.6% of its surface for weeks. Emitting the
        # coverage next to the counts makes that misreading unavailable.
        "coverage": measurement_coverage(
            groups_scanned=groups_scanned,
            groups_total=len(ordered),
            events_scanned=stats["events_scanned"],
            population=population,
        ),
        "ledger": ledger,
    }


async def run(apply: bool, limit: int, sport: str | None, offset: int = 0) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, limit=limit, sport=sport, offset=offset)

    print(f"=== CAL-P002 event-final-scores ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"population={res['population']} groups={res['groups_scanned']}"
          f"@offset {res['groups_offset']}/{res['groups_total']} "
          f"(remaining {res['groups_remaining']}, next_offset {res['next_offset']})")
    cov = res["coverage"]
    print(f"COVERAGE {cov['mode'].upper()}: {cov['events_scanned']} of "
          f"{cov['population']} events ({cov['groups_scanned']}/{cov['groups_total']} "
          f"groups) — every count below is over the SCANNED set, not the population")
    print(f"scanned={res['events_scanned']} score_defects={res['score_defects']} "
          f"winner_flips={res['winner_flips']} completed_at_gaps={res['completed_at_gaps']}")
    print(f"espn_id_drifted={res['espn_id_drifted']} "
          f"(with a proven target: {res['espn_id_drifted_with_target']}) "
          f"espn_id_unresolvable={res['espn_id_unresolvable']}")
    print(f"identity_blocked={res['identity_blocked']} date_blocked={res['date_blocked']} "
          f"doubleheader_ambiguous={res['doubleheader_ambiguous']} "
          f"not_final={res['espn_not_final']} not_found={res['espn_not_found']}")
    for e in res["ledger"][:40]:
        if e.get("action") == "fix_score":
            print(f"  [score_drifted] ev{e['event_id']} [{e['sport_key']}] {e['matchup']}: "
                  f"{e['stored_score']} -> {e['espn_final']}"
                  + ("  *WINNER FLIP*" if e.get("winner_flip") else ""))
    # The linkage class prints SEPARATELY and never under the score heading —
    # two remedies, two lists. Printing them together is how the wrong one gets
    # applied.
    for e in res["ledger"][:200]:
        if e.get("defect_class") in (ESPN_ID_DRIFTED, ESPN_ID_UNRESOLVABLE):
            tgt = e.get("proposed_espn_id")
            print(f"  [{e['defect_class']}] ev{e['event_id']} [{e['sport_key']}] "
                  f"{e['matchup']} espn_id={e['espn_id']}"
                  + (f" -> proposed {tgt}" if tgt else " -> NO PROVEN TARGET")
                  + f"  ({e.get('reason')})")
    if res["espn_id_drifted"] or res["espn_id_unresolvable"]:
        print("\nNOTE: the linkage rows above are NOT repairable by this rail. "
              "Use event-espn-id (attended). A score repair on them writes another "
              "game's final onto the row.")
    if apply:
        print(f"\nCOMMITTED scores={res['scores_repaired']} "
              f"completed_at={res['completed_at_repaired']} blend={res['blend_repaired']}")
        if res["groups_remaining"]:
            print(f"Re-run with --offset {res['next_offset']} "
                  f"({res['groups_remaining']} groups remaining).")
    else:
        print("\nDRY-RUN — pass --apply to commit.")


if __name__ == "__main__":
    _limit = _GROUP_LIMIT
    _sport = None
    _offset = 0
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            _limit = int(sys.argv[i + 1])
        if a == "--sport" and i + 1 < len(sys.argv):
            _sport = sys.argv[i + 1]
        if a == "--offset" and i + 1 < len(sys.argv):
            _offset = int(sys.argv[i + 1])
    asyncio.run(run("--apply" in sys.argv, _limit, _sport, _offset))
