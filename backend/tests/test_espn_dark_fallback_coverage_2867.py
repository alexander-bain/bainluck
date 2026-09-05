"""lane1/130 (#2867 step 7) — what actually survives an ESPN outage, per sport.

The authority lane handed lane1 a sketch for step 7 ("nothing goes blank when
ESPN does"): on a dark scoreboard, read StatPal into ``espn_data[key]`` so the
ESPN passes run against StatPal rows. This file is the measurement that says
that sketch is the wrong shape, and pins the shape that is already correct.

**ESPN darkness is already detected and already refuses to lie.** lane1/045 shut
that half: ``get_scoreboard`` returns ``None`` for "did not answer" and ``[]``
for "no games", five call sites branch on it, and
``test_espn_authority_dark_045.py`` guards every one — including an AST sweep of
new callers. Nothing here re-tests that.

**The half the sketch aims at is already served, by a different path.** For the
sports where a fallback could fire at all, StatPal does not need to borrow
ESPN's passes, because it already has its own, on beat, with its own provenance:

    transition-event-statuses    60s   scheduled -> live -> closed from
                                       commence_time alone. No API client. This
                                       is what makes the next line reachable
                                       during an outage.
    sync-statpal-livescores      30s   scores + period for `status='live'` rows.
    sync-statpal-schedules-*     1h    creates events via find_or_create_event
                                       under a `statpal` claim (ruling 048).

So routing StatPal fixtures through the ESPN passes would not fill a gap. It
would add a SECOND writer for games StatPal already writes, through a different
identity path (`create_events_from_unmatched_espn`), attributed to ESPN — which
contradicts the handoff's own first test ("rows carry StatPal provenance") and
is a twin factory for exactly the sports it can serve. This lane spends its
nights counting twins; it will not ship a new source of them.

**What the coverage actually is.** Three tiers, and only the first is resilient
for the ship's first clause (*every game exists on the site*):

    tier 1  discovery-resilient   4 sports.  StatPal schedule sync on beat, so
                                             a game ESPN never reports is still
                                             created.
    tier 2  livescore-only        8 sports.  In STATPAL_SPORT_MAPPING, but no
                                             scheduled schedule-sync, so StatPal
                                             can only UPDATE a row something
                                             else already created. Cannot
                                             discover.
    tier 3  no fallback          14 sports.  Not in STATPAL_SPORT_MAPPING at all.
                                             An outage holds last known state,
                                             which is the correct behaviour and
                                             the only available one.

The tier boundary is the point. `flip_permitted` gates the flip on a seven-day
agreement ledger, and agreement is measured over the games BOTH sources see —
it is silent about whether StatPal can see a game ESPN missed. A tier-2 sport
can post a perfect agreement streak and still be unable to discover anything.
Agreement is not coverage, and nothing today couples them; these tests are that
coupling, written down where a change to either side trips over it.

Every number below is derived, never typed twice: the tiers are computed from
the two mappings and the live beat schedule, so adding an ESPN sport, adding a
StatPal mapping, or dropping a schedule beat moves a sport between tiers and
fails here rather than silently narrowing what survives an outage.
"""

import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import authority_by_sport
from app.config.authority_by_sport import flip_permitted
from app.tasks import celery_app
from app.utils import statpal_discovery_coverage
from app.utils.authority_agreement import GATE_MEETS
from app.utils.authority_streak import REQUIRED_STREAK_DAYS
from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING

# The beat entry that breaks the circular dependency. Without it, `status='live'`
# is written only by sources that can themselves be dark, and every StatPal live
# path below — all of which filter on `status='live'` — goes dead in an outage
# while still looking healthy. Named, because the coupling is invisible at both
# ends.
LIVE_TRANSITION_TASK = "app.tasks.transition_event_statuses"

STATPAL_SCHEDULE_TASK = "app.tasks.sync_statpal_schedules"
STATPAL_LIVESCORE_TASK = "app.tasks.sync_statpal_livescores"

# Source files that must stay clear of ESPN, because their whole value during an
# outage is that they do not consult the authority that is dark.
STATPAL_SYNC_SRC = Path(__file__).resolve().parents[1] / "app" / "tasks" / "statpal_sync.py"


def _scheduled_discovery_sports() -> set[str]:
    """Sport keys with a StatPal *schedule* sync actually on the beat.

    Read from the beat schedule rather than from a list, because the list is the
    thing that rots. A schedule sync is what creates a game nobody else reported;
    a livescore sync only updates one that already exists.
    """
    sports = set()
    for entry in celery_app.conf.beat_schedule.values():
        if entry.get("task") != STATPAL_SCHEDULE_TASK:
            continue
        sport_key = (entry.get("kwargs") or {}).get("sport_key")
        if sport_key:
            sports.add(sport_key)
    return sports


def _tiers() -> tuple[set[str], set[str], set[str]]:
    """(discovery-resilient, livescore-only, no-fallback) over ESPN's sports."""
    espn = set(ESPN_SPORT_MAPPING)
    statpal = set(STATPAL_SPORT_MAPPING)
    discovery = espn & statpal & _scheduled_discovery_sports()
    livescore_only = (espn & statpal) - discovery
    none_at_all = espn - statpal
    return discovery, livescore_only, none_at_all


# ── The chain that makes an outage survivable at all ────────────────────────


def test_the_live_transition_runs_without_any_authority():
    """`scheduled -> live` must not need the source that can go dark.

    Every StatPal live path filters `status='live'`. If the only writer of that
    status were an API-driven task, a dark authority would strand a game in
    `scheduled` while it was being played, and the StatPal fallback would never
    see it — two tolerances in series that admit nothing.
    """
    entries = [
        (name, entry)
        for name, entry in celery_app.conf.beat_schedule.items()
        if entry.get("task") == LIVE_TRANSITION_TASK
    ]
    assert entries, (
        f"{LIVE_TRANSITION_TASK} is not on the beat schedule. Every StatPal "
        "live-score path filters on status='live'; without this task that "
        "status depends on a source that can be dark, and the fallback dies "
        "silently during exactly the outage it exists for (#2867 step 7)."
    )
    for name, entry in entries:
        schedule = entry["schedule"]
        assert float(schedule) <= 300.0, (
            f"Beat entry '{name}' runs every {schedule}s. This task is the only "
            "ESPN-independent writer of status='live'; a slow cadence delays "
            "every StatPal score update behind it."
        )


@pytest.mark.parametrize("task_name", [STATPAL_SCHEDULE_TASK, STATPAL_LIVESCORE_TASK])
def test_the_statpal_write_paths_are_on_the_beat(task_name):
    """A fallback that is not scheduled is not a fallback."""
    tasks = {entry.get("task") for entry in celery_app.conf.beat_schedule.values()}
    assert task_name in tasks, (
        f"{task_name} is not scheduled. It is one of the two paths by which a "
        "game reaches the site while ESPN is dark (#2867 step 7)."
    )


def test_the_statpal_sync_never_consults_espn():
    """The fallback must not import the authority it stands in for.

    Source-text, not behaviour: the defect this guards is a future edit that
    gates a StatPal read on an ESPN answer ("only poll StatPal for sports ESPN
    didn't cover"), which reads fine and is dead in precisely the outage case.
    Prose mentioning ESPN is fine; a name bound from it is not.
    """
    tree = ast.parse(STATPAL_SYNC_SRC.read_text())

    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and "espn" in (node.module or "").lower():
            offenders.append((node.lineno, f"from {node.module} import ..."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "espn" in alias.name.lower():
                    offenders.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.Attribute) and "espn" in node.attr.lower():
            offenders.append((node.lineno, f"...{node.attr}"))
        elif isinstance(node, ast.Name) and "espn" in node.id.lower():
            offenders.append((node.lineno, node.id))

    assert not offenders, (
        "statpal_sync.py now references ESPN at "
        + ", ".join(f"line {ln}: {what}" for ln, what in offenders)
        + ". The StatPal write path is the ESPN outage fallback; a dependency "
        "on ESPN makes it dead exactly when it is needed (#2867 step 7)."
    )


# ── The coverage map, derived and pinned ────────────────────────────────────


def test_the_three_coverage_tiers_partition_every_espn_sport():
    """The tiers are a partition — no sport is counted twice or missed."""
    discovery, livescore_only, none_at_all = _tiers()
    assert discovery & livescore_only == set()
    assert discovery & none_at_all == set()
    assert livescore_only & none_at_all == set()
    assert discovery | livescore_only | none_at_all == set(ESPN_SPORT_MAPPING)


def test_discovery_resilient_sports_are_exactly_the_four_with_a_schedule_beat():
    """Measured 2026-09-05. A change here is a real change in what survives.

    These are the only sports for which the ship's first clause — *every game
    exists on the site before any market lists it* — holds while ESPN is dark.
    """
    discovery, _, _ = _tiers()
    assert discovery == {
        "americanfootball_nfl",
        "baseball_mlb",
        "basketball_nba",
        "icehockey_nhl",
    }, (
        "The set of ESPN sports that can still DISCOVER a game while ESPN is "
        "dark has changed. If a sport was added, say so in #2867 and move this "
        "assertion. If one was lost, an outage now hides its new games."
    )


def test_livescore_only_sports_cannot_discover_and_that_is_recorded():
    """StatPal maps them, but no schedule sync runs, so they update only.

    Not a bug to fix here — soccer's season-schedule endpoint returns thousands
    of global fixtures and overwhelms a single run, which is why it is off the
    beat. It is a bug to *forget*: these sports read as "StatPal covered" from
    STATPAL_SPORT_MAPPING alone, and they are not, for discovery.
    """
    _, livescore_only, _ = _tiers()
    assert livescore_only == {
        "golf_pga",
        "soccer_epl",
        "soccer_france_ligue_one",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_spain_la_liga",
        "soccer_uefa_champs_league",
        "soccer_usa_mls",
    }, (
        "A sport moved into or out of livescore-only coverage. Being in "
        "STATPAL_SPORT_MAPPING is not the same as having a scheduled StatPal "
        "discovery path (#2867 step 7)."
    )


def test_most_espn_sports_have_no_statpal_counterpart_at_all():
    """14 of 26. For these, holding last known state is the only option.

    Pinned so that a future 'fall back to StatPal' switch cannot be read as
    covering the ESPN catalogue. It covers, at best, four of its twenty-six
    sports for discovery and twelve for scores.
    """
    _, _, none_at_all = _tiers()
    assert len(none_at_all) == 14
    assert len(ESPN_SPORT_MAPPING) == 26
    assert none_at_all == set(ESPN_SPORT_MAPPING) - set(STATPAL_SPORT_MAPPING)
    # The headline sports among them, spelled out: an outage on any of these
    # has no fallback of any kind, today or after the switch ships.
    assert {
        "americanfootball_ncaaf",
        "basketball_ncaab",
        "basketball_wnba",
        "mma_mixed_martial_arts",
    } <= none_at_all


# ── The gate: agreement is not coverage ─────────────────────────────────────
#
# The first cut of this file asserted the coupling over the sets it had just
# defined — `discovery` was BUILT as `mapped & scheduled`, so re-checking that
# each member was mapped and scheduled was true by construction and would have
# stayed true with `flip_permitted` untouched (CERT-1871). The tests below drive
# the production gate instead.


def _run_of(n: int, state: str = GATE_MEETS) -> list[dict]:
    """`n` CONSECUTIVE durable-ledger days ending 2026-09-30, all in one state.

    Consecutive matters: `compute_streak` stops at a day with no stored row, so
    a list of `n` entries with gaps is not a streak of `n`. Same shape as
    `test_authority_flip_switch._run_of`, restated rather than imported so a
    change to that file's helper cannot quietly weaken this one's premise.
    """
    end = date(2026, 9, 30)
    return [
        {"day": (end - timedelta(days=n - 1 - i)).isoformat(), "state": state}
        for i in range(n)
    ]


def _fully_evidenced(monkeypatch, sport_key: str) -> None:
    """Give `sport_key` everything the gate asked for BEFORE discovery coverage.

    A shadow stamper and a governing number, patched onto the names
    `authority_by_sport` bound at import. Without this the gate refuses
    `soccer_epl` at the first clause and the discovery clause is never reached —
    a test that passed for the wrong reason, which is the failure mode that
    produced CERT-1871 in the first place.
    """
    monkeypatch.setattr(
        authority_by_sport,
        "SHADOW_STAMPERS",
        {**authority_by_sport.SHADOW_STAMPERS, sport_key: "stamp_epl_statpal_fixtures"},
    )
    monkeypatch.setattr(
        authority_by_sport,
        "GOVERNING_IDENTITY_NUMBERS",
        {**authority_by_sport.GOVERNING_IDENTITY_NUMBERS, sport_key: ("ours_covered_pct",)},
    )


def test_a_fully_evidenced_livescore_only_sport_is_still_refused(monkeypatch):
    """The regression CERT-1871 asked for, and the reason it is not pedantic.

    `soccer_epl` here has a shadow stamper, a ruled governing number, and seven
    consecutive days at or above the bar — everything D50's measured half asks
    for. It is also livescore-only: no `sync-statpal-schedules` beat, so StatPal
    can never create a fixture nobody else reported.

    Permitting it would make StatPal the source of record for a sport StatPal
    cannot enumerate, breaking the first clause of the ship the switch serves
    (*every game exists on the site*) with the change meant to serve it.
    """
    _fully_evidenced(monkeypatch, "soccer_epl")

    # Premise, asserted rather than assumed: the OTHER four clauses are all
    # satisfied, so a refusal below can only be the discovery clause.
    assert "soccer_epl" in authority_by_sport.SHADOW_STAMPERS
    assert authority_by_sport.GOVERNING_IDENTITY_NUMBERS.get("soccer_epl")
    assert "soccer_epl" not in statpal_discovery_coverage.DISCOVERY_SYNCED_SPORTS

    permitted, why = flip_permitted("soccer_epl", _run_of(REQUIRED_STREAK_DAYS))

    assert not permitted, (
        "flip_permitted authorised a livescore-only sport on agreement evidence "
        "alone. Its streak is scored on the games BOTH sources list, which is "
        f"where they agree by construction; StatPal has no way to discover an "
        "EPL fixture ESPN missed (#2867 step 7, CERT-1871)."
    )
    assert "discovery" in why, (
        f"refused, but for the wrong reason: {why!r}. The reader has to be able "
        "to tell 'no discovery path' from 'no stamper' and 'no ruling' — three "
        "different next actions."
    )
    assert "not a wait" in why, (
        "a missing discovery beat is a build step. Wording it as a wait sends "
        "the reader to count more days, which is the failure this lane spent "
        "9/4 unwinding on MLB."
    )


def test_a_discovery_resilient_sport_with_the_same_evidence_is_permitted():
    """The positive control: the new clause denies the gap, not the gate.

    NBA, on real unpatched config — a shadow stamper, `ours_covered_pct` ruled
    under D63, and a `sync-statpal-schedules-nba` beat. Identical ledger
    evidence to the test above. Without this, a clause that returned `False`
    unconditionally would pass the denial test and dark the whole switch.
    """
    assert "basketball_nba" in statpal_discovery_coverage.DISCOVERY_SYNCED_SPORTS

    permitted, why = flip_permitted("basketball_nba", _run_of(REQUIRED_STREAK_DAYS))

    assert permitted, (
        f"the discovery clause refused a discovery-resilient sport: {why!r}. "
        "NBA has a StatPal schedule sync on the beat; if this fails, the flip "
        "gate is now unreachable for every sport."
    )
    assert "YOUR-TURN" in why, (
        "a permitted flip must still name D50's second half — no function can "
        "check that Alex has seen the entry."
    )


def test_the_gate_reads_the_coverage_set_rather_than_a_hardcoded_sport_list(
    monkeypatch,
):
    """Drop NBA's discovery path and NBA stops being flippable.

    Distinguishes a gate that consults `DISCOVERY_SYNCED_SPORTS` from one that
    happens to name the same four sports inline. The mutation this kills is a
    real edit: retiring a StatPal schedule beat without noticing that a sport's
    flip eligibility rode on it.
    """
    monkeypatch.setattr(
        statpal_discovery_coverage,
        "DISCOVERY_SYNCED_SPORTS",
        statpal_discovery_coverage.DISCOVERY_SYNCED_SPORTS - {"basketball_nba"},
    )

    permitted, why = flip_permitted("basketball_nba", _run_of(REQUIRED_STREAK_DAYS))

    assert not permitted, (
        "NBA is still permitted with its discovery path removed, so the gate is "
        "not actually reading the coverage set (#2867 step 7, CERT-1871)."
    )
    assert "discovery" in why


def test_the_coverage_set_matches_the_beat_and_cannot_rot():
    """`DISCOVERY_SYNCED_SPORTS` is a literal; the beat schedule is the truth.

    The constant is a literal on purpose — deriving it inside
    `statpal_discovery_coverage` would import `app.tasks` from a module the
    config layer imports, pulling Celery into a config import for a four-element
    answer. The cost of the literal is paid here: add or drop a
    `sync-statpal-schedules` beat entry and this fails rather than silently
    widening or narrowing what a flip may cover.
    """
    scheduled = _scheduled_discovery_sports()

    assert statpal_discovery_coverage.DISCOVERY_SYNCED_SPORTS == frozenset(scheduled), (
        "DISCOVERY_SYNCED_SPORTS and the sync-statpal-schedules beat entries "
        "disagree. The beat is the truth; update the constant, and check "
        "whether a sport just gained or lost the ability to be flipped."
    )
    # The converse, over two independent sources: a scheduled StatPal schedule
    # sync for a sport with no STATPAL_SPORT_MAPPING entry cannot resolve a
    # sport at all, so the beat would run and create nothing.
    for sport in scheduled:
        assert sport in STATPAL_SPORT_MAPPING, (
            f"Beat schedules a StatPal schedule sync for '{sport}', which has "
            "no STATPAL_SPORT_MAPPING entry — the run cannot resolve a sport."
        )


def test_no_livescore_only_sport_can_be_flipped_today(monkeypatch):
    """The inventory and the gate, joined — over every tier-2 sport at once.

    The tests above prove the mechanism on one sport. This one closes the set:
    every sport the inventory calls livescore-only is refused by the production
    gate even when handed a perfect ledger. A future sport added to
    `STATPAL_SPORT_MAPPING` without a schedule beat lands here automatically.

    Each sport is fully evidenced first. Without that they are all refused at
    the shadow-stamper clause — true today, and true with the discovery clause
    deleted, which would make this test pass while measuring nothing.
    """
    _, livescore_only, _ = _tiers()
    assert livescore_only, "the tier is empty; this test is no longer measuring"

    for sport in sorted(livescore_only):
        _fully_evidenced(monkeypatch, sport)
        permitted, why = flip_permitted(sport, _run_of(REQUIRED_STREAK_DAYS))
        assert not permitted, (
            f"{sport} is livescore-only but the flip gate permits it on "
            f"agreement evidence alone: {why!r}"
        )
        assert "discovery" in why, (
            f"{sport} is refused, but not for the missing discovery path: "
            f"{why!r}"
        )
