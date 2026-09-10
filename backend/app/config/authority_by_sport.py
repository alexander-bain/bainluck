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
may change.

**Amended by program step 7 (#3473):** this file said "the consumer that acts on
it is lane1's to build", and one now exists that is not lane1's and does not
need to be. `utils/authority_failover` reads the switch to answer who serves a
sport on a pass where ESPN went silent — a question about PROVIDER SELECTION,
which is this lane's, not about event identity, which is lane1's. Every sport
being `ESPN` still means today's behaviour is byte-for-byte what it was, and the
failover's own gate (`flip_permitted`) is what decides whether ESPN's silence may
be covered at all.

**That gate no longer refuses every sport (D104 = A4, 2026-09-09).**
`americanfootball_nfl` is in `FLIP_RULED_WITHOUT_STREAK` and is permitted without
a certification streak, so on a pass where ESPN goes dark for football, StatPal's
schedule and livescore writers now run. Every sport is still `ESPN` in the map
above and that is not a contradiction: the map is the STANDING source of record
and the gate is the FALLBACK, and on a pass where ESPN answers, football is
processed exactly as it always was.

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
    MEASUREMENT_POPULATION_SCOPES,
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

#: Every module under `app/` that reads the switch. **Two: the page that reports
#: its value, and the failover that acts on it.**
#:
#: **This set gained its first actor in program step 7 (#3473), and the sentence
#: it used to carry is retired.** Until then the honest statement was that
#: changing a line above would change one string on an admin page and nothing
#: else — no ingest task, no registry path, no serving route asked
#: `authority_for` anything. That was not a defect in step 6; a dark switch is
#: what step 6 was for. It was written down because of WHEN it would stop being
#: harmless: NFL, NBA and NHL were at gate `MEETS`, day 2 of 7 (production,
#: 2026-09-06 05:44Z), so the earliest a genuine seven existed was around
#: 2026-09-11, and on that day someone would have read a YOUR-TURN entry, edited
#: one line, watched the row change from `espn` to `statpal` and reasonably
#: concluded the site now ran on StatPal. It would not have.
#:
#: It does now, in one specific and bounded way. `utils/authority_failover`
#: reads `authority_for` to answer "who serves this sport on this pass", and a
#: sport set to `STATPAL` here is reported as served by StatPal standing rather
#: than as an outage override. That is a real behavioural difference, so the
#: row's note no longer says `INERT`.
#:
#: What has NOT changed, and must not be read into the above: flipping a line
#: still does not move the event graph. `event_registry` and the matcher are
#: lane1's under D50 and neither reads this file. What acts is
#: `espn_sync._act_on_failovers`, which on an ESPN-dark pass awaits StatPal's
#: OWN writers in-line — `_sync_statpal_schedules(sport_key)` and
#: `_sync_statpal_livescores()`, the async implementations behind beats that
#: already run for these sports. It dispatches no Celery task (an earlier cut
#: did; CERT-2050 refused it) and it introduces no new path into the registry:
#: those writers enter it through the door they always used.
#:
#: Kept as a declared set with an AST guard over `app/` rather than as prose,
#: because prose about what reads a symbol is exactly the claim that rots the
#: day someone wires the first real consumer.
#: `test_authority_switch_is_wired_3442` walks the tree, so wiring one fails CI
#: until this set and the sentence above are brought back into line with it.
#: A grep would not do: the one real consumer writes its import inside a
#: function AND across four lines, and either alone defeats a substring scan.
SWITCH_CONSUMERS: frozenset[str] = frozenset(
    {
        # Reports `authority_for(sport_key)` as the row's `authority.current`.
        # A reader, not an actor: it changes nothing about what the site serves.
        "app.routes.admin_providers",
        # ACTS on it (#3473). Decides who serves a sport on a pass where ESPN
        # went silent, and a sport already flipped here is served by StatPal
        # standing rather than by an outage override.
        #
        # A decision module rather than the task that serves — and it counts
        # as wiring, which is worth stating because the distinction
        # `SWITCH_REPORTERS` draws is "reports it" against "acts on it" and this
        # is neither. It DECIDES, and its decision is acted on: the switch is
        # live through it exactly as if the caller had read the switch directly.
        # `test_the_decision_module_has_an_actor` is what stops that reasoning
        # from being a story — it fails if nothing under `app/` calls it, which
        # is the RIDER RULE ("a pure function nothing calls is architecture-only")
        # enforced in CI rather than remembered.
        "app.utils.authority_failover",
    }
)

#: The one consumer that reads the switch WITHOUT acting on it: the admin page
#: whose whole job is to report the switch's value back. Named rather than
#: inlined into the test below it, because "reports it" and "acts on it" is the
#: distinction the whole disclosure turns on.
SWITCH_REPORTERS: frozenset[str] = frozenset({"app.routes.admin_providers"})


def switch_is_wired(consumers: Iterable[str]) -> bool:
    """Does anything ACT on the switch, as opposed to reporting its value?

    Takes the consumer set rather than reading the module global, so a test can
    ask it about a tree that does not exist yet — a predicate that can only ever
    be asked about today's answer is a restatement of today's answer.
    """
    return bool(frozenset(consumers) - SWITCH_REPORTERS)


def switch_wiring_note(wired: bool, serves: bool) -> str:
    """What the agreement row says about the switch, in an operator's words.

    A function of the derived facts, so neither sentence can outlive the
    condition it describes: nobody has to remember to delete one.

    **Three states, because the switch has had three lives and the middle one
    is the trap (#4947).** Dark (nothing reads it), wired-but-accounting-only
    (something reads it and the only difference is which counter moves), and
    wired-and-serving (the actor dispatches writers on the strength of it).
    The middle sentence was served for a day after it stopped being true: #4434
    gave `_act_on_failovers` a `STANDING_STATPAL` branch that runs StatPal's own
    schedule and livescore writers, and this note went on describing a flip as
    bookkeeping. `SWITCH_CONSUMERS`' tree walk could not catch it — it asks
    whether anything READS the switch, and the answer had not changed. What
    moved was what the reader DOES, which is why `SWITCH_ACTOR_SERVES` is
    declared beside it with a guard of its own.
    """
    if wired and serves:
        return (
            "WIRED, AND IT SERVES — read all of this before flipping. "
            "`utils/authority_failover` reads this switch (program step 7, "
            "#3473) and `espn_sync._act_on_failovers` ACTS on it (#4434), so "
            "TWO things change when a sport is set to `statpal`, on a pass "
            "where ESPN is silent for it. First: StatPal's own schedule and "
            "livescore writers RUN for that sport — the same two an outage "
            "failover would have run — so the flip changes what is WRITTEN, "
            "not only what is counted. Second: the sport is counted apart from "
            "outage failovers rather than as one, because a sport served by "
            "its own source of record is in its normal state and not in a "
            "degradation. And if StatPal's standby cannot cover the sport on "
            "that pass, it is counted UNCOVERED rather than served, so a flip "
            "cannot quietly report coverage it does not have. "
            "WHAT A FLIP DOES NOT DO, and this is the wrong conclusion to draw "
            "from the word `statpal` appearing here: it does not suppress the "
            "ESPN path. A flipped sport still takes its scores, clock, win "
            "probability, stat model and box scores from ESPN on every pass "
            "ESPN answers, because `_sync_espn_live_events` selects sports by "
            "what ESPN returned and not by this switch. Serving a sport "
            "entirely from StatPal is a further build step and is not this "
            "one; it would remove an ESPN win-probability source from the "
            "blend, which is a product decision (PRD: 'the blend is the "
            "product') and not plumbing. Nor does a flip move the event graph "
            "— `event_registry` and the matcher do not read this file."
        )
    if wired:
        return (
            "WIRED, AND NARROWLY — read the second half before flipping. "
            "`utils/authority_failover` reads this switch (program step 7, "
            "#3473), so ONE thing changes when a sport is set to `statpal`: on "
            "a pass where ESPN is silent for it, the sport is reported as "
            "served by StatPal and is excluded from outage-failover accounting "
            "rather than counted as a sport that failed over. "
            "WHAT A FLIP DOES NOT DO, and this is the wrong conclusion to draw "
            "from the word `statpal` appearing here: it does not suppress the "
            "ESPN path. A flipped sport still takes its scores, clock, win "
            "probability, stat model and box scores from ESPN on every pass "
            "ESPN answers, because `_sync_espn_live_events` selects sports by "
            "what ESPN returned and not by this switch. Serving a sport "
            "entirely from StatPal is a further build step and is not this "
            "one; it would remove an ESPN win-probability source from the "
            "blend, which is a product decision (PRD: 'the blend is the "
            "product') and not plumbing. Nor does a flip move the event graph "
            "— `event_registry` and the matcher do not read this file."
        )
    return (
        "INERT: flipping a sport changes this page's `authority.current` and "
        "nothing else — no ingest task, registry path or serving route reads "
        "`config.authority_by_sport`. The gate below measures whether StatPal "
        "COULD be trusted as the source of record; wiring anything to ACT on "
        'the answer is program step 7 ("nothing goes blank when ESPN does") and '
        "is not built. Do not read a flip as a change to what the site serves."
    )


#: Whether reading the switch changes anything the site does. Derived, never
#: declared, so it cannot disagree with the set above.
#:
#: Published on the agreement row beside the gate, because an operator deciding
#: whether to flip is exactly the person who must not have to read this file.
SWITCH_IS_WIRED: bool = switch_is_wired(SWITCH_CONSUMERS)

#: Does the actor that reads the switch SERVE a flipped sport, or only account
#: for it differently? (#4947)
#:
#: **`SWITCH_IS_WIRED` cannot answer this, and that is why this exists.** That
#: flag is derived from `SWITCH_CONSUMERS`, which is derived from a tree walk
#: for *imports* — it says something reads `authority_for` and nothing about
#: what the reader then does. Between #3473 and #4434 the honest answer here was
#: `False`: the failover module read the switch, and a flip moved a sport from
#: the failover column to a standing one and changed no write. #4434 gave
#: `espn_sync._act_on_failovers` a `STANDING_STATPAL` branch that calls
#: `_serve_schedule_from_statpal` and appends to `served` (hence
#: `_serve_live_from_statpal`), so a flip now changes what is WRITTEN on an
#: ESPN-dark pass. Every test stayed green while the served sentence went on
#: calling a flip bookkeeping, because no guard was pointed at this question.
#:
#: Declared rather than computed at import, for the same reason
#: `SWITCH_CONSUMERS` is: parsing another module's function body at startup to
#: decide what an admin string says would make a config import depend on the
#: shape of a task. The honesty comes from the guard, not from the literal —
#: `test_the_standing_branch_serves_and_the_note_says_so` walks
#: `_act_on_failovers` and fails in BOTH directions, so this line cannot
#: disagree with the tree any longer than it takes CI to run.
SWITCH_ACTOR_SERVES: bool = True

SWITCH_WIRING_NOTE: str = switch_wiring_note(SWITCH_IS_WIRED, SWITCH_ACTOR_SERVES)

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
#: Thirteen sports are in `STATPAL_SPORT_MAPPING` and four are on the beat; since
#: #3193, **all four parse**. The seven soccer leagues are livescore-only ON PURPOSE
#: — the soccer season-schedule endpoint returns thousands of global fixtures and
#: overwhelms a single run — so their absence is a standing fact, not a gap to close
#: in passing.
#:
#: `golf_pga` used to be named here as livescore-only too, and that was WRONG in a
#: way worth keeping the correction for (#4691). It was not livescore-only; it was
#: unreachable on every path. The livescore sync finds its sports by joining `Sport`
#: to a live `Event`, so it is gated on a `sports` row exactly as the schedule sync
#: is, and `golf_pga` has never had one. A sport cannot be "livescore-only" through
#: a door that is shut for the same reason the other doors are. The key is retired
#: from the map as of 2026-09-10; the reason now lives in
#: `sport_keys.RETIRED_STATPAL_SPORT_KEYS`, and `schedule_sentinel` had already
#: declared PGA NOT COVERED — *field event, no per-game schedule to reconcile*.
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
        # Moved up from the dict below by #3193, which is what that entry said to
        # do the day someone taught `_extract_match_items` the stage nesting. The
        # ingest parser now reads 17 of 17 on the pinned payload, so the hourly
        # beat can create an NFL game ESPN missed.
        #
        # This removes a REFUSAL REASON that had become false; it does not flip
        # anything. NFL's clock is 1/7, and `flip_permitted` still refuses on the
        # streak — which is the honest refusal, where "the beat creates nothing"
        # had stopped being one.
        "americanfootball_nfl",
    }
)

#: On the discovery beat, and discovering nothing. Each entry is a live defect,
#: named rather than silently dropped from the set above.
#:
#: **Empty since #3193.** NFL was the only entry, found by CERT-1875: its
#: `season-schedule` response nests games `scores.tournament.stage[] → week[] →
#: matches → match`, two levels below where `_extract_match_items` looked, so the
#: hourly `sync-statpal-schedules-nfl` beat created no NFL events at all while
#: reporting success. The tell was that **the authority read path parsed it fine**
#: — `_parse_nfl_season_schedule` walks the nesting — so NFL's agreement row read
#: 99.69% and its clock ran on a number produced by the path that does not write.
#: *Two parsers over one payload, one of them blind, and the blind one is the only
#: one that creates.*
#:
#: `_extract_match_items` learned the nesting and now reads 17 of 17 on the same
#: pinned payload, so NFL moved into the set above. Kept as a named, empty dict
#: rather than deleted, because the shape it describes is not NFL-specific and the
#: next sport to land in it should land somewhere that already explains itself.
#:
#: **What made it safe to fix, measured on production 2026-09-05:** teaching the
#: parser and starting to create events are the same change — a StatPal listing
#: claim is not id-anchored (ruling 048), and an id-less claim never absorbs, it
#: CREATES. The count of new rows a fixed parser would write is exactly the number
#: of StatPal fixtures we do not already hold under a matching id, and the NFL
#: agreement row publishes that as `statpal_only: 0` over 322 games. Both future
#: NFL events carried a StatPal id, so Step 1 finds them. Zero new rows.
#:
#: **Tennis is NOT the next entry here, and must not be added without reading
#: this.** The same measurement says the opposite for tennis: `STATPAL_SPORT_MAPPING`
#: claims it under `tennis_atp`/`tennis_wta`, the tennis linker anchors under
#: `tennis_atp_us_open`/`tennis_wta_us_open`, and registry Step 1 is sport-scoped
#: (D55/#2879) — so it would refuse the rows it should match and create a second
#: copy of every US Open match, hourly. Tennis belongs in the third list below,
#: for the reason given there; the parser is the easy half and is not the risk.
DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE: dict[str, str] = {}

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

#: For a parser-blind sport, the thing the PARSER itself waits on — keyed the
#: same way as the map above, and absent for a sport that waits on nothing.
#:
#: 🔴 THIS MAP EXISTS BECAUSE THE SENTENCE ABOVE IT WAS A LIE THAT PRESCRIBED
#: HARM (#4200). `discovery_state` used to end every parser-blind reason with
#: "both are build steps, not a wait" — a flat claim, correct for the id-less
#: arm and false here. The comment inside `discovery_state`, the docstring of
#: `tests/test_statpal_nfl_schedule_parses_3193.py` and #3193's own disposition
#: ("the tennis half is NOT claimed and should not be built as a parser
#: ticket") all record the same blocker; only the string an operator actually
#: reads denied it.
#:
#: The harm is why this is a map rather than a softened adjective. Told the work
#: is unblocked, a reader teaches the parser and schedules the beat, and the
#: beat then creates a second copy of every US Open match HOURLY — registry
#: Step 1 is sport-scoped (D55/#2879) and the tennis linker anchors under
#: `tennis_atp_us_open`/`tennis_wta_us_open` while `STATPAL_SPORT_MAPPING`
#: claims `tennis_atp`/`tennis_wta`. #4155 ("10 US Open singles matches exist
#: twice") is that failure mode already on the site, from a smaller cause.
#:
#: Keyed per sport, and NOT folded into the census strings above, so that the
#: two facts stay separately assertable: the census says the parser cannot read
#: the payload, this says who has to rule before anyone teaches it. A sport with
#: a measured census and no entry here still reads "build steps, not a wait",
#: which is the honest answer for a parser nobody else's ruling governs.
DISCOVERY_PARSER_BLOCKED_ON: dict[str, str] = {
    "tennis_singles": (
        "the tennis_atp vs tennis_atp_us_open key reconciliation, which is "
        "lane1's to rule on (D39/#2693) because it is an identity question: "
        "registry Step 1 is sport-scoped (D55/#2879), so teaching the parser "
        "before those keys are settled would have the beat create a second "
        "copy of every US Open match, hourly, under a non-anchoring claim"
    ),
    "tennis_doubles": (
        "the tennis_wta vs tennis_wta_us_open key reconciliation, which is "
        "lane1's to rule on (D39/#2693) because it is an identity question: "
        "registry Step 1 is sport-scoped (D55/#2879), so teaching the parser "
        "before those keys are settled would have the beat create a second "
        "copy of every US Open match, hourly, under a non-anchoring claim"
    ),
}

#: Stamped and measured daily, with no `sync_statpal_schedules` beat, and an
#: ingest parser that READS the fixtures but mints no id for any of them.
#:
#: A fourth list, and the reason is the same one that made the third necessary:
#: the dicts above make claims in their names, and both claims are false here.
#: Soccer's ingest parse is not blind — measured on the pinned production
#: payloads with the shipped parsers, `_extract_match_items` +
#: `_parse_single_fixture` return a fixture for **274 of 274** items in
#: `statpal_soccer_matches_daily_offset1_20260907_fullcensus.json` and **195 of
#: 195** in `statpal_soccer_matches_live_20260907_fullcensus.json`. Filing soccer
#: under `DISCOVERY_NO_BEAT_AND_NO_PARSE` would send the next reader to repair a
#: parser that already works.
#:
#: **What is actually missing is the id, and that is the worse half.** Of those
#: same 274 and 195 fixtures, **0 carry a non-empty `fixture_id`**. The raw items
#: carry no `id` at all — they carry `main_id` and `fallback_id_1/2/3` — and the
#: authority read path anchors on `fallback_id_3` (`soccer:<fallback_id_3>`,
#: #3366) while `main_id` is known to COLLIDE across competitions, which is why
#: it is not the anchor. The ingest parser reaches for none of them.
#:
#: So the consequence is tennis's, arrived at from the other end, and it is
#: ruling 048 that makes it certain: an id-less claim NEVER absorbs, it CREATES.
#: A `sync-statpal-schedules-soccer` beat switched on today would read hundreds
#: of real fixtures an hour, carry no id on any of them, match none of our 39,700
#: existing soccer rows by anchor, and mint a second copy of each — hourly, on
#: the sport with the widest key vocabulary we have. Teaching the ingest parser
#: `fallback_id_3` is the first half of that work and is the half that makes the
#: beat safe; it is not scheduled here, and the beat must not be until it is.
#:
#: This is a build step, not a wait — and it is the same discovery gap #3607
#: measures from the agreement row's side. The write itself goes through
#: `event_registry`, which is lane1's under D50/#2693.
DISCOVERY_PARSES_BUT_MINTS_NO_ID: dict[str, str] = {
    "soccer": (
        "no sync-statpal-schedules-soccer beat exists, and the ingest parser "
        "would mint no id if one did: _extract_match_items + "
        "_parse_single_fixture return a fixture for 274 of 274 items in "
        "statpal_soccer_matches_daily_offset1_20260907_fullcensus.json and 195 "
        "of 195 in the live board, and 0 of either carry a non-empty "
        "fixture_id — soccer items have no `id`, only main_id and "
        "fallback_id_1/2/3, and the authority path anchors on fallback_id_3. "
        "Under ruling 048 an id-less claim creates rather than absorbs, so such "
        "a beat would mint a second copy of every soccer game hourly. #3607"
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

#: Sports Alex ruled may fail over to StatPal **without a certification streak**.
#:
#: D104 = A4, 2026-09-09 10:20am PT, in his words: *"I'm not at all worried about
#: StatPal having schedule coverage for top-tier leagues. We don't need 7 days of
#: proof. If there's anything missing, it was a failure by us to fetch it
#: correctly."*
#:
#: **This is a gate exemption, not a flip.** A key here still holds `ESPN` in
#: `AUTHORITY_BY_SPORT` above, and must: that map is the STANDING source of
#: record, and `authority_failover.decide` treats a `STATPAL` value there as "this
#: sport has already flipped, ESPN's silence is not an outage for it" — which is
#: not a fallback and is not what was asked for. What D104 asked for is D50's own
#: design, ESPN first and StatPal behind it, so what changes is the one question
#: in `decide` that refused every sport: the gate.
#:
#: **It exempts the WAIT and nothing else.** `flip_permitted` consults this set
#: only after its four structural refusals — measurement population, no shadow
#: stamper, no working discovery pass, no governing number (D63). Those say
#: "there is nothing here to flip TO", which is a different sentence from "come
#: back in a week", and a ruling about proof days does not reach them.
#: `baseball_mlb` is the case that keeps this honest: a top-tier league named in
#: the same breath as football, still refused, because it has no governing
#: identity number and that needs a ruling rather than a wait.
#:
#: One release each, because that is what Alex asked for: *"Flip football first
#: (the Thursday kickoff), then the rest in one release each."*
#:
#: Football shipped on #4417 and its resilience hole — a failover still gated on
#: the MONITOR being readable — closed on #4443. `basketball_nba` is the second
#: release, #4493. `icehockey_nhl` is the third and is deliberately still absent:
#: it clears every structural branch and waits only on its streak, so it is a
#: one-line addition here when its release comes. Adding it early would land two
#: flips under a cert that graded one.
#:
#: Each addition was refused on the WAIT ALONE before it was made, read from the
#: live row rather than inferred from the config (standing notice 37). The NBA's
#: row at 2026-09-09 21:19:54Z: `NO-FAILOVER-NOT-GATED`, *"has not cleared D50's
#: measured half: basketball_nba is 5/7 consecutive days at or above 99.5% — a
#: wait, not a defect"*. That is branch 6 and nothing else.
#:
#: Beware the number that looks bad: the NBA's identity `pct` reads 3.39 and the
#: NHL's 2.28, and neither governs its sport. `GOVERNING_IDENTITY_NUMBERS` gives
#: both `("ours_covered_pct",)`, which reads 100.0; only football is governed by
#: `("pct", "ours_covered_pct")`. A reader who checks `pct` concludes these
#: sports are nowhere near ready.
#:
#: The ledger is untouched. It keeps folding a day per sport per pass and keeps
#: being published — Alex kept it explicitly, as a MONITOR: a game StatPal lists
#: that we lack is now OUR fetch bug to fix, filed under #2867, never a reason to
#: say the venue does not cover it (standing notices 26/27).
FLIP_RULED_WITHOUT_STREAK: frozenset[str] = frozenset(
    {"americanfootball_nfl", "basketball_nba"}
)


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


#: The discovery states, as codes a reader can grep for. Published beside the
#: prose so a caller can branch on the state without parsing a sentence.
DISCOVERY_SCHEDULED = "SCHEDULED"
DISCOVERY_BEAT_PARSES_NOTHING = "BEAT-WITHOUT-A-WORKING-PARSE"
DISCOVERY_PARSER_MINTS_NO_ID = "PARSER-MINTS-NO-ID"
#: No beat AND a parser that cannot read the payload if one called it. Distinct
#: from `NO-BEAT`, which prescribes scheduling a beat — the one instruction that
#: cannot pay here (#3193).
DISCOVERY_NO_BEAT_AND_PARSER_BLIND = "NO-BEAT-AND-PARSER-BLIND"
DISCOVERY_NO_BEAT = "NO-BEAT"


def discovery_state(sport_key: str) -> tuple[str, str]:
    """Is there a WORKING StatPal discovery pass for `sport_key`, and if not, why?

    Returns `(code, why)`. Split out of :func:`flip_permitted` by CERT-2245's
    follow-up `SOCCER-3366-IDLESS-REFUSAL-REACHABILITY`, and the reason is the
    interesting part.

    🔴 A REFUSAL REASON THAT NOTHING CAN REACH IS NOT A REFUSAL REASON. Inside
    `flip_permitted` this reasoning sits BELOW the measurement-population check,
    which returns first and unconditionally. `soccer` is a measurement
    population, so the `PARSER-MINTS-NO-ID` branch — written for soccer, about
    soccer, carrying soccer's own 274/274 and 195/195 census — was unreachable
    for the only sport it describes. Every operator reading soccer's agreement
    row got "there is nothing here to flip" and no hint that the parser mints no
    id, which is the build step that has to come FIRST.

    So the fact is computed here, independently of every other refusal, and
    `flip_permitted` and the agreement endpoint both read it. The endpoint
    publishes it for every sport including the measurement populations, because
    the question "does discovery work for this sport?" has an honest answer even
    where "may it be flipped?" does not. Fixing reachability rather than
    deleting the branch: the census is true and load-bearing, it was just
    filed where soccer could never read it.

    🔴 THE SAME DEFECT HAD A SECOND INSTANCE, ONE LIST OVER, AND THIS FUNCTION
    SHIPPED WITH IT. `DISCOVERY_NO_BEAT_AND_NO_PARSE` carries tennis's census —
    0 of 7 and 0 of 11 fixtures parsed on pinned real payloads, from two
    independent causes in two different functions (#3193) — and nothing read
    that map. Both tennis populations fell through to the bare `NO-BEAT`
    ending, which is true (there is no beat) and prescribes the one build step
    that cannot pay: scheduling a beat over a parser that reads nothing. The
    map was written; only the branch that consults it was missing. Four maps in,
    the lesson is that adding a state to the config and adding the arm that
    publishes it are two changes, and the second is the one a reader feels.

    Total, like :func:`authority_for` — every input has an answer and none
    raise.
    """
    if sport_key in DISCOVERY_SCHEDULED_SPORTS:
        return DISCOVERY_SCHEDULED, (
            f"{sport_key} is on the hourly `sync_statpal_schedules` beat and its "
            "ingest parser reads the payload, so discovery can create a game we "
            "missed — which is the thing an agreement streak is evidence about"
        )
    broken = DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE.get(sport_key)
    if broken:
        return DISCOVERY_BEAT_PARSES_NOTHING, (
            f"The beat exists and does nothing: {broken}. Fixing that path is "
            "a build step, not a wait"
        )
    # NOT folded into the bare "build a beat" ending below. They prescribe
    # different work in different orders: told only to schedule a beat, a reader
    # would schedule one over a parser that mints no id, and ruling 048 turns
    # that into a duplicate of every row it reads. The reason has to name the
    # parser first.
    idless = DISCOVERY_PARSES_BUT_MINTS_NO_ID.get(sport_key)
    if idless:
        return DISCOVERY_PARSER_MINTS_NO_ID, (
            f"The parser reads the fixtures and mints no id for them: {idless}. "
            "Teaching it the id comes BEFORE scheduling a beat — this is a "
            "build step, not a wait"
        )
    # The same rule as the id-less arm, for the state that is worse than either:
    # no beat AND a parser that could not read the payload if one called it. The
    # bare "build a beat" ending below prescribes exactly the work that cannot
    # pay — tennis's parser is measured at 0 of 7 and 0 of 11 on pinned real
    # payloads (#3193) — and it is not merely useless: teaching the parser
    # without also settling the sport-key question would have the beat create a
    # second copy of every US Open match hourly, because registry Step 1 is
    # sport-scoped (D55/#2879) and the linker anchors under different keys than
    # `STATPAL_SPORT_MAPPING` claims. So the blindness is named BEFORE the beat.
    blind = DISCOVERY_NO_BEAT_AND_NO_PARSE.get(sport_key)
    if blind:
        # The ordering is the same in both endings; what differs is whether
        # anyone may act on it today. "not a wait" is a claim about the world
        # and it was false for the only sports in this arm (#4200) — say who
        # has to rule first, or say nothing about waiting at all.
        blocked_on = DISCOVERY_PARSER_BLOCKED_ON.get(sport_key)
        if blocked_on:
            return DISCOVERY_NO_BEAT_AND_PARSER_BLIND, (
                f"Neither half of discovery exists for this sport: {blind}. "
                "Teaching the parser comes BEFORE scheduling a beat, but the "
                f"parser itself WAITS ON {blocked_on}"
            )
        return DISCOVERY_NO_BEAT_AND_PARSER_BLIND, (
            f"Neither half of discovery exists for this sport: {blind}. "
            "Teaching the parser comes BEFORE scheduling a beat — both are "
            "build steps, not a wait"
        )
    return DISCOVERY_NO_BEAT, (
        "This is a build step (a `sync_statpal_schedules` beat), not a wait"
    )


#: What a permitted streak's own days say it was counted on, as a clause.
#:
#: **This is disclosure, never a gate (#3071).** The minimum denominator for a
#: flip is UNRULED — `alex-inbox/authority-016` puts it to Alex as question A
#: with a stated default (A1, a floor below which a day scores `NO-SCORE`) and it
#: has not been answered. This module will not invent the answer, so nothing
#: below compares a coverage figure to anything. It states the number and names
#: the open question, and the boolean is decided entirely without it.
#:
#: WHY A `True` HAS TO CARRY THIS. `flip_permitted`'s docstring argues at length
#: that a bare `False` is a failure, because six different "no"s prescribe six
#: different pieces of work and a reader needs to know which one they are in. A
#: `True` that will not say what it was counted on is that same failure with the
#: sign flipped, and it is the more expensive one: on 2026-09-11 `basketball_nba`
#: reaches seven days on 41 of 1,208 fixtures — 3.4% of a season that has not
#: started — and the sentence it would have returned was *"D50's measured half is
#: met"*, full stop. True, and silent about the only fact a person deciding needs.
#: Since #3473 this gate is read by `espn_sync._decide_failovers` as well as by
#: the admin page, so the silence would also be a machine's.
#:
#: Read off the STREAK's own days, `since`..`through`, not off the whole ledger:
#: a retained day before the streak began was not part of what was cleared, and
#: including it would describe a different measurement than the one being
#: permitted. A range is reported rather than a single figure when the days
#: disagree, because a denominator that grew from 3 to 41 over seven days and one
#: that sat at 41 throughout are different facts and the ruling's third candidate
#: option turns on exactly that difference.
def _counted_on(ledger_days: Iterable[dict[str, Any]], streak: dict[str, Any]) -> str:
    since, through = streak.get("since"), streak.get("through")
    window = [
        d
        for d in ledger_days
        if isinstance(d, dict)
        and d.get("day")
        and (since is None or d["day"] >= since)
        and (through is None or d["day"] <= through)
    ]
    pairs = [
        (d.get("both"), d.get("denominator"))
        for d in window
        if isinstance(d.get("both"), int) and isinstance(d.get("denominator"), int)
    ]
    if not pairs:
        # Not "0 of 0" and not silence. A ledger day predating these fields is a
        # day whose denominator we cannot state, and saying so is the disclosure
        # (gotcha #53: an absent answer is not a zero answer).
        return (
            "its days do not record what they were counted on, so this streak's "
            "denominator cannot be stated here"
        )

    def _span(values: set[Any]) -> str:
        lo, hi = min(values), max(values)
        fmt = (lambda v: f"{v:,}") if isinstance(lo, int) else str
        return fmt(lo) if lo == hi else f"{fmt(lo)}–{fmt(hi)}"

    boths = {b for b, _ in pairs}
    denoms = {d for _, d in pairs}
    pcts = {round(100.0 * b / d, 1) for b, d in pairs if d}
    coverage = f" ({_span(pcts)}%)" if pcts else ""
    steady = len(boths) == 1 and len(denoms) == 1
    return (
        f"counted over {_span(boths)} of the {_span(denoms)} fixtures in the "
        f"measured population{coverage}, "
        + (
            "on every day of the streak"
            if steady
            else f"varying across its {len(pairs)} recorded days"
        )
    )


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

      * the key is a MEASUREMENT POPULATION, not a sport key — a wrong question
        rather than a "no" about any sport;
      * no dark id join for this sport at all, so there is nothing to flip TO;
      * no WORKING discovery pass — either no beat at all, or a beat whose
        service call parses nothing — so agreeing about the games we already have
        is the only thing this sport's streak could ever prove. Fix the path, do
        not wait for days;
      * no governing number ruled, so no day could ever have advanced (D63);
      * no ledger at all — not measured, which is not a streak of zero;
      * a streak that is real and not seven days long yet;
      * a streak broken by a day under the bar, or by a day nobody recorded.

    Only the last is a problem. Returning a bare `False` for all of them is how a
    sport that needs a ruling gets waited on instead, which is the failure this
    lane spent 9/4 unwinding on MLB. The last two share a wording — both are
    reported with `compute_streak`'s own `stopped_by` detail, which names the day
    and the reason rather than making the reader go and look.

    **D104 = A4 (Alex, 2026-09-09) retires the last two for a ruled sport, and
    only those two.** A key in `FLIP_RULED_WITHOUT_STREAK` is permitted whatever
    its streak says, because Alex ruled the top-tier leagues need no proof days.
    The ruling is asked AFTER the four structural refusals above and AFTER
    `compute_streak` — after the refusals so it can never be read as a way past
    "there is nothing here to flip TO" (`baseball_mlb` still refuses on D63), and
    after the walk so the permission can report what the monitor currently says.
    The days keep being folded and published either way; only their authority
    over the answer is gone.

    A `True` here was, until D104, the first half of D50, whose second half is a
    YOUR-TURN entry Alex has seen. For a ruled sport that second half is what the
    ruling itself was — Alex naming the leagues and saying to switch now.
    """
    population = MEASUREMENT_POPULATION_SCOPES.get(sport_key)
    if population is not None:
        # Asked before everything else, because this one is not a "no" about the
        # sport at all — it is a "wrong question". `tennis_singles` is a draw we
        # measure and `soccer` is a StatPal id space; neither is a row anything
        # joins on. A caller that flipped one of these strings would flip nothing
        # and would believe it had, which is worse than a refusal.
        #
        # The honest flip is per real `sports.key`, and it needs a ruling saying
        # which keys the measured population stands for. That ruling does not
        # exist for either population and this file will not invent it.
        #
        # The clause naming OUR key vocabulary comes from the population's own
        # record rather than being written here (CERT-1887's rule, applied to a
        # reason rather than a count): a soccer operator told that "our tennis
        # rows are spread over 42 `sports.key`s" has been handed a confident
        # sentence about a sport they did not ask about.
        return False, (
            f"{sport_key} is a MEASUREMENT POPULATION, not a sport key — "
            f"{population.our_keys_note}. There is nothing here to flip; a flip "
            "for this population is per real sport key and needs a ruling naming "
            "which keys its row stands for"
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
        # Read from `discovery_state` rather than restated here, so the reason
        # this refusal gives and the reason the agreement endpoint publishes
        # cannot drift — and so the id-less branch stays exercised by the sports
        # that reach it (CERT-2245's follow-up).
        _, detail = discovery_state(sport_key)
        return False, (
            f"{sport_key} has no working StatPal discovery pass, so its agreement "
            "streak is measured only over games we already have — it cannot show "
            "StatPal finding one we missed, which is the whole point of the flip. "
            + detail
        )
    if not GOVERNING_IDENTITY_NUMBERS.get(sport_key):
        return False, (
            f"{sport_key} has no governing identity number (D63), so no daily "
            "row can advance its streak however good the agreement is — this "
            "needs a ruling, not more days"
        )
    # Materialised ONCE, before anything reads it. `compute_streak` consumes the
    # iterable, and `_counted_on` reads it again afterwards — handed a generator,
    # the second read would see an empty sequence and report "its days do not
    # record what they were counted on" about a ledger that records it perfectly
    # well. Every caller passes a list today; the annotation says `Iterable` and
    # the next one is under no obligation to.
    days_recorded = list(ledger_days)
    streak = compute_streak(days_recorded)
    if sport_key in FLIP_RULED_WITHOUT_STREAK:
        # D104 = A4. Asked AFTER the four structural refusals above, so the
        # ruling exempts the WAIT and cannot be used to skip "there is nothing
        # here to flip TO" — and asked AFTER `compute_streak`, not instead of it,
        # because Alex kept the ledger running as a monitor and a permission that
        # never walked the days could not report what the monitor currently says.
        observed = None if streak is None else streak["days"]
        monitor = (
            "its ledger has not been written yet, so the monitor has nothing to "
            "say about it so far"
            if observed is None
            else f"the monitor still runs and currently reads a run of "
            f"{observed} day(s) at or above {FLIP_BAR_PCT}%"
        )
        return True, (
            f"{sport_key} may fail over to StatPal without a certification "
            "streak: Alex ruled D104 = A4 on 2026-09-09 — no proof days for the "
            "top-tier leagues, and a game StatPal lists that we lack is our "
            f"fetch bug to fix (#2867), not a gap in the venue. So {monitor}, "
            f"and the {REQUIRED_STREAK_DAYS}-day bar no longer gates this sport. "
            "THE LIMIT: this is a fallback BEHIND ESPN, not a standing source of "
            f"record — `AUTHORITY_BY_SPORT` still reads "
            f"`{authority_for(sport_key)}`, so on a pass where ESPN answers "
            "nothing here changes"
        )
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
        f"above {FLIP_BAR_PCT}%, {_counted_on(days_recorded, streak)}. The "
        "minimum denominator for a flip is UNRULED (#3071) — this gate applies "
        "no floor and none of the above narrowed it. D50's measured half is met "
        "as the bar is currently written; the flip still needs a YOUR-TURN entry "
        "Alex has seen, which is not checkable here"
    )
