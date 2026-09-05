"""Which provider is the source of record for a sport's event graph. #2867, D50.

**SHIP: when a sport's seven days finally land, the flip that makes StatPal its
source of record is one line in this file — and until then, this file is the
thing that says out loud, per sport, that it has not happened.** (Pillar:
MATCHING. Program step 6, riding the lane's ship: *every game exists on the site
before any market lists it; nothing goes blank when ESPN does.*)

**Every sport here is `ESPN`. Nothing has flipped. Nothing flips by importing
this module.**

WHY A FILE FOR A DICTIONARY THAT IS ALL ONE VALUE
═════════════════════════════════════════════════
D50: *nothing user-visible flips without a measured 7-day ≥99.5% agreement row
from the bus AND a YOUR-TURN entry Alex has seen.* Two halves. The measurement
half has been built and is publishing (`utils/authority_agreement`,
`/api/admin/statpal/authority-agreement`). The other half — the act of flipping —
had no home at all. A flip with no home is a flip that happens as a scattered
diff across the registry on the day somebody decides the number looks good
enough, with the seven days recalled rather than checked.

So the switch exists before the number does, and it exists with its gate
attached: `flip_permitted` is the D50 sentence in code, and it answers with a
reason rather than a boolean, because "no" has six different meanings here and
only one of them is a defect.

WHAT THIS FILE DOES NOT DO
══════════════════════════
It does not resolve anything. `event_registry` and the matcher are lane1's
(D50), and nothing in this module reads or writes an event. It publishes a
per-sport setting and the question that has to be answered before that setting
may change; the consumer that acts on it is lane1's to build, and every sport
being `ESPN` means the consumer's behaviour today is byte-for-byte what it is
now.

It also does not count the seven days itself. `authority_streak.compute_streak`
does that — it shipped with authority/021, it walks the durable ledger's own
`days[]`, and it already knows the difference between a day that carries and a
day that resets. A second implementation of "consecutive" would be a second
answer to the only question D50 asks.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GOVERNING_IDENTITY_NUMBERS,
    MEASUREMENT_POPULATIONS,
    SHADOW_STAMPERS,
)

# `REQUIRED_STREAK_DAYS` and `compute_streak` both shipped with authority/021.
# Imported, never restated: the seven-day count has one owner.
from app.utils.authority_streak import REQUIRED_STREAK_DAYS, compute_streak

#: The two answers a sport's authority setting can hold.
ESPN = "espn"
STATPAL = "statpal"

#: What a sport falls back to when it is not named below, and what every named
#: sport holds today.
#:
#: ESPN, and not "unset". An unknown sport key must resolve to the behaviour the
#: site has always had, not to a state the caller has to interpret — a typo in a
#: sport key is a bug to find, never a reason for a surface to change provider.
DEFAULT_AUTHORITY = ESPN

#: **The switch. One line per sport, and a flip is a change to one of them.**
#:
#: Dark: every value is `ESPN`. A sport is listed here — rather than left to
#: `DEFAULT_AUTHORITY` — because the authority lane has built a dark id join for
#: it and is measuring it daily. Being listed says "this one is being watched",
#: never "this one is close".
#:
#: Changing a value is not sufficient on its own and is not meant to be:
#: `flip_permitted` has to say yes first, and D50's second half (a YOUR-TURN
#: entry Alex has seen) is not a thing code can check. `test_authority_flip_switch`
#: fails if a value here is `STATPAL` without the evidence recorded in
#: `FLIP_EVIDENCE`, so the one-line change carries its receipts or CI stops it.
AUTHORITY_BY_SPORT: dict[str, str] = {
    "americanfootball_nfl": ESPN,
    "basketball_nba": ESPN,
    "icehockey_nhl": ESPN,
    "baseball_mlb": ESPN,
}

#: The sports StatPal can DISCOVER a game in — not merely agree about one.
#:
#: **Agreement is not coverage** (lane1, 2026-09-05, reviewing this lane's step-7
#: handoff; the invariant is pinned by their PR #3178). The agreement streak
#: `flip_permitted` reads is measured over the fixtures BOTH sources see, and the
#: intersection is precisely where the two agree by construction. It says nothing
#: about whether StatPal would have found a game ESPN never reported — which is
#: this lane's entire ship (*every game exists on the site before any market lists
#: it*). A sport can post seven perfect days and discover nothing.
#:
#: What makes a sport discoverable is one concrete thing, and **it is not that a
#: beat exists** (CERT-1875, which struck exactly that mistake in this file's first
#: version). It is that the scheduled task's own service call returns fixtures for
#: that sport. The only StatPal path that CREATES events is
#: `sync_statpal_schedules` → `StatPalAPIService.get_fixtures(sport)` →
#: `_parse_fixtures` → `find_or_create_event` under a `statpal` claim. A sport
#: whose payload that chain cannot parse has an hourly task that creates nothing,
#: hour after hour, greenly.
#:
#: Twelve sports are in `STATPAL_SPORT_MAPPING` and four are on the beat; of those
#: four, **three parse**. `golf_pga` and the seven soccer leagues are livescore-only
#: ON PURPOSE — the soccer season-schedule endpoint returns thousands of global
#: fixtures and overwhelms a single run — so their absence is a standing fact, not
#: a gap to close in passing.
#:
#: **`tennis_atp` and `tennis_wta` are the other live case**: both mapped, neither
#: on the beat, and tennis is the next sport this lane stamps.
#:
#: Kept as an explicit set rather than derived at import time, because `app.config`
#: importing `app.tasks` is a circular-import hazard the repo has paid for.
#: `test_authority_flip_switch` derives the beat side from
#: `celery_app.conf.beat_schedule` AND proves each listed sport's real pinned
#: payload parses non-empty, so this cannot rot in either direction.
DISCOVERY_SCHEDULED_SPORTS: frozenset[str] = frozenset(
    {
        "basketball_nba",
        "icehockey_nhl",
        "baseball_mlb",
    }
)

#: On the discovery beat, and discovering nothing. Each entry is a live defect,
#: named rather than silently dropped from the set above.
#:
#: **NFL, found by CERT-1875 and reproduced on the pinned real payload.** The
#: `season-schedule` response nests its games `scores.tournament.stage[] → week[] →
#: matches → match`, two levels below where `_extract_match_items` looks (it knows
#: `tournament.match` and `tournament.week`). Measured on
#: `statpal_nfl_season_schedule_20260903.json`, which retains **17** of the live
#: season's matches: the authority parser reads 17 of 17, the ingest parser reads
#: **0**. So the hourly `sync-statpal-schedules-nfl` beat has been creating no NFL
#: events at all. (The count is the FIXTURE's, deliberately — it is a reduced
#: sample, and quoting the live season's game count beside a reduced-fixture
#: measurement is how a number gets attributed to a file that never held it. The
#: live population, if you want one, is the agreement row's own denominator: 322.)
#:
#: The reason this was invisible: **the authority read path parses it fine.**
#: `get_schedule_fixtures("nfl")` → `_parse_nfl_season_schedule` walks the stage
#: nesting correctly, which is why NFL's agreement row reads 99.69% and its
#: seven-day clock is running. Two parsers over one payload, one of them blind, and
#: the blind one is the only one that writes. That is the shape: *the number that
#: looks good comes from the path that does not create anything.*
#:
#: Being listed here is not a permanent exemption — it is a bug with a name. The
#: fix is to teach the ingest parser the stage nesting (or route it through
#: `_parse_nfl_season_schedule`), which is a change to what a live task WRITES and
#: therefore its own ship, not a line in a config. `test_authority_flip_switch`
#: asserts each excluded sport still parses zero, so the day someone fixes it the
#: test fails and says to move the sport into the set above.
DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE: dict[str, str] = {
    "americanfootball_nfl": (
        "sync-statpal-schedules-nfl runs hourly and creates nothing: "
        "get_fixtures('nfl') parses 0 of the 17 matches in the pinned real "
        "payload because they nest under "
        "scores.tournament.stage[].week[].matches.match, which "
        "_extract_match_items does not walk. The authority read path "
        "(_parse_nfl_season_schedule) reads all 17 of the same payload, which is "
        "why the agreement row looks healthy. CERT-1875"
    ),
}

#: Stamped and measured daily, with no `sync_statpal_schedules` beat AT ALL.
#:
#: A third list rather than an entry in the one above, because that dict's name
#: makes a claim — *a beat exists and it parses nothing* — that is false here,
#: and filing tennis under it would assert a scheduled task nobody has written.
#: The distinction is not pedantry: the two states have different fixes. NFL's is
#: to teach an existing hourly task a nesting; tennis's is to decide whether to
#: schedule one at all, which is a bigger question because it would create events
#: under a `statpal` claim — the registry's door, and lane1's under D50.
#:
#: Tennis is a WORSE case than NFL, not a lesser one, and the second clause is
#: the reason it must be named rather than left to "no beat yet": **the ingest
#: parser could not read tennis even if a beat called it.** Measured on the
#: pinned real payloads with the shipped parsers — 0 of 7 fixtures on
#: `statpal_tennis_daily_20260903.json` and 0 of 11 on the livescores fixture,
#: against 7 and 11 on the authority path.
#:
#: **The blindness has TWO independent causes, and this was found by mutation
#: rather than by reading.** The first was the one on record; repairing it alone
#: still yields zero, so a fix that stopped there would ship a beat that creates
#: nothing while the ticket read closed:
#:
#:   1. `_extract_match_items` never reaches the matches. Tennis's
#:      `scores.tournament` is a LIST of draws and the extractor guards
#:      `isinstance(tournament, dict)`. Teaching it the list shape makes 7 items
#:      reachable — and the count stays 0, because of:
#:   2. `_parse_single_fixture` returns `None` for every one of them. It reads
#:      `item["home"]` and `item["away"]`; a tennis match carries neither, it
#:      carries `player: [{name: "G. Monfils"}, {name: "L. Tien"}]`. Both team
#:      names come out empty and the fixture is dropped.
#:
#: So this is not NFL's stage-nesting gap wearing a different hat, and it is not
#: one shape gap either — it is a container mismatch and a record mismatch, in
#: two different functions. Fixing NFL's fixes neither (#3193).
#:
#: So a tennis agreement streak, however perfect, could only ever prove that we
#: agree about the matches we already had — never that StatPal would have found
#: one we missed, which is this lane's whole ship. `flip_permitted` refuses these
#: keys earlier and for a stronger reason (they are measurement populations, not
#: sport keys), and this list is what stops that earlier refusal from letting the
#: discovery question go unrecorded.
DISCOVERY_NO_BEAT_AND_NO_PARSE: dict[str, str] = {
    "tennis_singles": (
        "no sync-statpal-schedules-tennis beat exists, and the ingest parser "
        "could not read tennis if one did: get_fixtures('tennis') parses 0 of "
        "the 7 fixtures in statpal_tennis_daily_20260903.json and 0 of 11 in the "
        "livescores fixture, because scores.tournament is a LIST of draws and "
        "_extract_match_items guards isinstance(tournament, dict). The authority "
        "read path (_parse_tennis_daily) reads both payloads, which is why the "
        "agreement row can be measured at all. #3193"
    ),
    "tennis_doubles": (
        "same blind parser as tennis_singles — one endpoint family serves both "
        "draws, so neither is discoverable and the doubles draw is additionally "
        "the one the linker refuses to write links for. #3193"
    ),
}

#: For each sport that has flipped: the seven-day evidence it flipped on.
#:
#: Empty, because nothing has flipped. Each entry, when there is one, holds the
#: `days` it flipped on — the durable ledger's own `days[]` entries, copied as
#: they stood, so the evidence is the same objects `compute_streak` walked and
#: not a retelling of them — and `your_turn`, naming the entry Alex saw.
#:
#: The reason this is a separate map rather than a field on the switch: a flip
#: back to ESPN must be one line and must not require deleting the evidence that
#: the flip forward was earned. Rolling back is the move that has to be cheapest.
FLIP_EVIDENCE: dict[str, dict[str, Any]] = {}


def authority_for(sport_key: Optional[str]) -> str:
    """Which provider is the source of record for `sport_key` right now.

    Total: every input has an answer and none of them raise. A `KeyError` out of
    a config lookup in a Celery task is an outage in a sport we were not even
    changing, and `None`/unknown must mean "the site's existing behaviour", which
    is ESPN.
    """
    if not sport_key:
        return DEFAULT_AUTHORITY
    return AUTHORITY_BY_SPORT.get(sport_key, DEFAULT_AUTHORITY)


def flip_permitted(
    sport_key: str, ledger_days: Iterable[dict[str, Any]]
) -> tuple[bool, str]:
    """May `sport_key` be flipped to StatPal, given its durable ledger's days?

    `ledger_days` is the `days[]` list from that sport's
    `authority-agreement-ledger:<sport_key>` snapshot — the same entries
    `authority_streak.fold_day` writes, one per UTC day, each carrying its
    `state`. The counting is `compute_streak`'s, not this module's.

    Returns `(permitted, why)`, and `why` is the point of the function. "No" has
    SIX meanings here:

      * no dark id join for this sport at all, so there is nothing to flip TO;
      * no WORKING discovery pass — either no beat at all, or a beat whose
        service call parses nothing (NFL today) — so agreeing about the games we
        already have is the only thing this sport's streak could ever prove. Fix
        the path, do not wait for days;
      * no governing number ruled, so no day could ever have advanced (D63);
      * no ledger at all — not measured, which is not a streak of zero;
      * a streak that is real and not seven days long yet;
      * a streak broken by a day under the bar, or by a day nobody recorded.

    Only the last is a problem. Returning a bare `False` for all six is how a
    sport that needs a ruling gets waited on instead, which is the failure this
    lane spent 9/4 unwinding on MLB. The last two share a wording — both are
    reported with `compute_streak`'s own `stopped_by` detail, which names the day
    and the reason rather than making the reader go and look.

    A `True` here is still not permission to flip. It is the first half of D50;
    the second half is a YOUR-TURN entry Alex has seen, and no function can
    check that.
    """
    if sport_key in MEASUREMENT_POPULATIONS:
        # Asked before everything else, because this one is not a "no" about
        # tennis at all — it is a "wrong question". `tennis_singles` is a draw we
        # measure, not a row anything joins on: our tennis matches live under 42
        # different `sports.key`s. A caller that flipped this string would flip
        # nothing and would believe it had, which is worse than a refusal.
        #
        # The honest flip for tennis is per real `sports.key`, and it needs a
        # ruling that says which of the 42 the measured draw stands for. That
        # ruling does not exist and this file will not invent it.
        return False, (
            f"{sport_key} is a MEASUREMENT POPULATION, not a sport key — our "
            "tennis rows are spread over 42 `sports.key`s and none of them is "
            "this string. There is nothing here to flip; a flip for tennis is "
            "per real sport key and needs a ruling naming which keys a draw's "
            "row stands for"
        )
    if sport_key not in SHADOW_STAMPERS:
        return False, (
            f"{sport_key} has no shadow stamper, so there is no id join to flip "
            "onto — this is a build step, not a wait"
        )
    if sport_key not in DISCOVERY_SCHEDULED_SPORTS:
        # Asked BEFORE the ledger is read, deliberately. This one cannot be
        # answered by more days — a sport with no discovery pass would post the
        # same seven MEETS days forever, because the only fixtures it is scored
        # over are the ones we already have. Reading the streak first and
        # reporting "6/7" would describe it as a wait.
        broken = DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE.get(sport_key)
        return False, (
            f"{sport_key} has no working StatPal discovery pass, so its agreement "
            "streak is measured only over games we already have — it cannot show "
            "StatPal finding one we missed, which is the whole point of the flip. "
            + (
                f"The beat exists and does nothing: {broken}. Fixing that path is "
                "a build step, not a wait"
                if broken
                else "This is a build step (a `sync_statpal_schedules` beat), "
                "not a wait"
            )
        )
    if not GOVERNING_IDENTITY_NUMBERS.get(sport_key):
        return False, (
            f"{sport_key} has no governing identity number (D63), so no daily "
            "row can advance its streak however good the agreement is — this "
            "needs a ruling, not more days"
        )
    streak = compute_streak(ledger_days)
    if streak is None:
        # `None` is not zero. An empty ledger has never been measured, and
        # reporting it as "0/7 consecutive days" would describe a sport that
        # failed a bar it was never held to (gotcha #53).
        return False, (
            f"{sport_key} has no agreement ledger yet — not measured, which is "
            "not a streak of zero. The first daily pass starts it"
        )
    days = streak["days"]
    if days < REQUIRED_STREAK_DAYS:
        return False, (
            f"{sport_key} is {days}/{REQUIRED_STREAK_DAYS} consecutive days at or "
            f"above {FLIP_BAR_PCT}% — a wait, not a defect. "
            f"{(streak.get('stopped_by') or {}).get('detail', '')}".strip()
        )
    return True, (
        f"{sport_key} has {days}/{REQUIRED_STREAK_DAYS} consecutive days at or "
        f"above {FLIP_BAR_PCT}%. D50's measured half is met; the flip still "
        "needs a YOUR-TURN entry Alex has seen, which is not checkable here"
    )
