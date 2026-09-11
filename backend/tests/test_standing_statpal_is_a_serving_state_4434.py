"""A flipped sport is asked whether its standby can actually serve it. #4434, D104.

**SHIP: when a sport's source of record is StatPal, an ESPN outage stops leaving
it blank — and when nobody can serve it, that is the loudest state on the pass
instead of the quietest.** (Pillar: TRUTH. Parent #2867.)

THE DEFECT THIS FILE PINS
═════════════════════════
`decide` asked `standing == STATPAL` FIRST and returned immediately — before the
gate, before the standby was read, before every "can StatPal actually cover
this?" question the failover path asks. `STANDING_STATPAL` was in neither
`FAILOVER_CODES` nor `BLANK_CODES`, so `_act_on_failovers` fell to its `else`
branch and dispatched nothing. Measured on the real functions with
`AUTHORITY_BY_SPORT["americanfootball_nfl"] = STATPAL`:

    decide(ESPN dark, StatPal HAS fixtures, gate open)
      code        = STANDING-STATPAL
      serving     = statpal
      failed_over = False
    _act_on_failovers wrote: NOTHING
    failover_serving: 0 | failover_uncovered: 0

**The sport reported `serving: statpal`, wrote no fixtures, no score and no
clock, and was counted as neither served nor uncovered.** Silent in both
directions. That is CERT-2044's failure mode — "the failover claiming to serve
down a path it had never checked" — reintroduced by the flip.

The early return was correct for the world it was written in: a DARK switch,
where a flip could only ever be a label. It stops being correct the moment a
flip is real, which is what D104 makes it.

WHAT IS DELIBERATELY *NOT* HERE
═══════════════════════════════
**The flip itself.** This ship made the standing path SAFE to flip; it did not
flip anything. `americanfootball_nfl` was flipped afterwards, on 2026-09-11, by
#4954 — a separate PR carrying D50's receipts, and this file's precondition is
what it names as having made it survivable.
`test_the_flip_this_ship_made_safe_was_performed_by_a_different_ship` pins that
separation (it was `test_the_switch_itself_still_did_not_move`, which asserted
every value was `espn`; the sentence stopped being available on the day the
guard succeeded).

**The inversion.** Genuinely making StatPal the primary ingest means inverting
`espn_sync`'s loops so StatPal is read first and ESPN backs it up. That is
separate, larger, and not started — so on a pass where ESPN DOES answer, a
standing sport is still processed by the ordinary ESPN loops, and `decide` still
says so in capitals. `test_espn_answering_still_reports_the_flip_with_its_limit`
pins that boundary so the out-of-scope half cannot be mistaken for a regression.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    ESPN,
    FLIP_EVIDENCE,
    STATPAL,
    flip_permitted,
)
from app.utils.authority_failover import (
    BLANK_CODES,
    BOTH_QUIET,
    DARK,
    EMPTY,
    FAILOVER_CODES,
    FIXTURES,
    LIVE_PATH_DARK,
    LIVE_PATH_SILENT_ON_THE_GAME,
    NO_SCHEDULE_BOARD,
    NOT_GATED,
    NOT_READ,
    NOTHING_TO_SERVE,
    STANDBY_CANNOT_COVER_WINDOW,
    STANDBY_DARK,
    STANDBY_NOT_READ,
    STANDING_STATPAL,
    decide,
    is_unserved,
)

NFL = "americanfootball_nfl"


def _shut_gate() -> tuple[bool, str]:
    """A REAL refusal from the REAL gate, for the "the gate is not consulted" tests.

    Driven through `flip_permitted` rather than hand-written as `(False, "...")`
    for the reason the 3473 suite gives: a control that cannot notice the gate
    changing under it is not a control. An unknown sport key is refused by the
    gate's own first question, and the assertion below is what makes a future
    gate that permits everything loud here rather than silently vacuous.
    """
    gate = flip_permitted("standing_4434_unknown_specimen", [])
    assert gate[0] is False, (
        "the control is broken: the real gate now permits an unknown sport, so "
        f"every 'the gate is not consulted' assertion below is vacuous. {gate[1]}"
    )
    return gate


def _standing(**kw):
    """`decide` for a flipped sport, with a SHUT gate unless told otherwise.

    The shut gate is the point, not an incidental: a standing sport must reach
    its standby questions without the gate's permission, because the gate asks
    "may this sport flip?" and this one already has.
    """
    kw.setdefault("gate", _shut_gate())
    return decide(NFL, standing=STATPAL, **kw)


# ── The standby questions a standing sport must answer ──────────────────────
#
# One test per refusal in #4434's acceptance list. Each pins BOTH halves: the
# code, and whether the actor will treat it as a fault.


def test_a_standing_sport_with_an_unread_standby_does_not_claim_to_serve():
    """The caller-bug case. Before #4434 this returned `serving: statpal`.

    `NOT_READ` is not a reading — it is the absence of one — and a standing
    sport claiming to be served on the strength of a question nobody asked is
    exactly the receipt CERT-2044 exists to prevent.
    """
    decision = _standing(espn=DARK)

    assert decision.code == STANDBY_NOT_READ
    assert decision.serving == ESPN
    assert decision.failed_over is False
    assert decision.standing is True, (
        "the decision must still record that this sport is flipped, or an "
        "operator reading the receipt cannot tell this refusal apart from an "
        "ordinary un-flipped sport's"
    )
    assert is_unserved(decision) is False, (
        "a caller bug is not a provider fault; it is reported, not alarmed"
    )


@pytest.mark.parametrize(
    "schedule,live,expected",
    [
        (DARK, DARK, STANDBY_DARK),
        (DARK, FIXTURES, STANDBY_DARK),
        (FIXTURES, DARK, LIVE_PATH_DARK),
        (FIXTURES, EMPTY, LIVE_PATH_SILENT_ON_THE_GAME),
    ],
)
def test_a_standing_sport_whose_standby_fails_is_counted_uncovered(
    schedule, live, expected
):
    """**The acceptance's headline.** A flipped sport nobody can serve is the
    MOST alarming state on the pass, not an exempt one.

    All four are states in which the site genuinely goes blank for this sport:
    ESPN is silent and the source of record it was flipped to either did not
    answer, or answered about the schedule and cannot say what is happening in
    the game. Before #4434 every one of them returned `serving: statpal` and
    incremented nothing.
    """
    decision = _standing(espn=DARK, statpal=schedule, statpal_live=live)

    assert decision.code == expected
    assert decision.failed_over is False
    assert decision.standing is True
    assert is_unserved(decision) is True, (
        f"{expected} for a flipped sport is the blank state and must be counted "
        "and logged as a fault"
    )
    assert decision.code in BLANK_CODES


def test_no_schedule_board_is_a_fault_for_a_standing_sport_and_benign_otherwise():
    """The one severity that DIVERGES between the two paths, and why.

    `STANDBY_CANNOT_COVER_WINDOW` is deliberately not in `BLANK_CODES`: for a
    failover CANDIDATE it means "StatPal publishes no board for this window"
    (soccer and tennis, permanently, #4320) — a boundary of its product, a fact
    about our build state, benign.

    For a sport that has ALREADY been flipped to StatPal it means the source of
    record cannot cover its own sport. Same code, opposite severity, so the
    judgement cannot live in a code-level set alone — which is why `is_unserved`
    takes the decision and not the code.
    """
    standing = _standing(espn=DARK, statpal=NO_SCHEDULE_BOARD, statpal_live=EMPTY)
    assert standing.code == STANDBY_CANNOT_COVER_WINDOW
    assert is_unserved(standing) is True, (
        "a flipped sport whose source of record publishes no board for the "
        "window is unserved, however benign the same code is for a candidate"
    )

    # THE PAIRED CONTROL, without which the assertion above could pass by
    # putting the code in `BLANK_CODES` and breaking soccer and tennis.
    candidate = decide(
        NFL,
        espn=DARK,
        statpal=NO_SCHEDULE_BOARD,
        statpal_live=EMPTY,
        gate=flip_permitted(NFL, []),
        standing=ESPN,
    )
    assert candidate.code == STANDBY_CANNOT_COVER_WINDOW
    assert is_unserved(candidate) is False, (
        "#4320's benign refusal regressed: soccer and tennis would now alarm on "
        "every pass"
    )
    assert STANDBY_CANNOT_COVER_WINDOW not in BLANK_CODES


@pytest.mark.parametrize(
    "espn,expected",
    [(EMPTY, BOTH_QUIET), (DARK, NOTHING_TO_SERVE)],
)
def test_a_standing_sport_with_nothing_on_is_not_a_blank(espn, expected):
    """Neither refusal is a fault, on either path. A quiet slate is a quiet
    slate however the switch is set, and "both sources agree there is no game"
    must never alarm — it is the case an empty ESPN board may not be read as a
    failure on its own.
    """
    decision = _standing(espn=espn, statpal=EMPTY, statpal_live=EMPTY)

    assert decision.code == expected
    assert decision.standing is True
    assert is_unserved(decision) is False
    assert decision.code not in BLANK_CODES


# ── And the state where it does serve ───────────────────────────────────────


def test_a_standing_sport_with_a_healthy_standby_serves_and_is_not_a_failover():
    """The other half of the ship. Reached only AFTER every question above.

    `failed_over` stays False and the code stays out of `FAILOVER_CODES`: a
    flipped sport is not degraded, and counting it as a failover would report it
    as being in an outage for as long as it stayed flipped. That was the correct
    half of the original early return and it survives intact.
    """
    decision = _standing(espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES)

    assert decision.code == STANDING_STATPAL
    assert decision.serving == STATPAL
    assert decision.failed_over is False
    assert decision.standing is True
    assert decision.code not in FAILOVER_CODES
    assert is_unserved(decision) is False


def test_the_gate_is_not_consulted_for_a_standing_sport():
    """A sport that has already flipped does not need permission to flip.

    Every `_standing(...)` call in this file runs against a REAL shut gate, so
    this pins what they all quietly depend on. The paired control is the same
    shut gate on the un-flipped path, which must still refuse at `NOT_GATED`
    before the standby is looked at — otherwise this test would be passing
    because the gate had stopped refusing anybody.
    """
    served = _standing(espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES)
    assert served.code == STANDING_STATPAL

    candidate = decide(
        NFL, espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES,
        gate=_shut_gate(), standing=ESPN,
    )
    assert candidate.code == NOT_GATED, (
        "the control is broken: the shut gate no longer refuses an un-flipped "
        f"sport, so 'the gate is not consulted' proves nothing. {candidate.why}"
    )


def test_espn_answering_still_reports_the_flip_with_its_limit():
    """**The out-of-scope boundary, pinned so it is not read as a regression.**

    On a pass where ESPN answers with fixtures, a standing sport is still
    processed by the ordinary ESPN loops — they select on what ESPN returned and
    not on this switch — and `decide` still says so. Making that untrue is the
    INVERSION, which is a separate and larger build; this ship does not touch it.

    So this state keeps its pre-#4434 answer, caveat and all. It is also the one
    reading `_decide_failovers` never passes in, because it skips a sport ESPN
    answered for before `decide` is called.
    """
    decision = _standing(espn=FIXTURES)

    assert decision.code == STANDING_STATPAL
    assert decision.serving == STATPAL
    assert decision.failed_over is False
    assert "NOTE THE LIMIT" in decision.why, (
        "the receipt must keep carrying the caveat, or an operator reads "
        "`serving: statpal` as ESPN having been suppressed"
    )


def test_the_standing_flag_travels_on_the_receipt():
    """`as_receipt` is what an operator actually reads on the task summary.

    A `standing` that exists only inside the dataclass is invisible where the
    decision is consumed, which is the same failure as the producer's
    disambiguation dying in the control flow.
    """
    receipt = _standing(espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES).as_receipt()

    assert receipt["standing"] is True
    assert receipt["serving"] == STATPAL
    assert receipt["failed_over"] is False

    ordinary = decide(NFL, espn=DARK, gate=_shut_gate(), standing=ESPN).as_receipt()
    assert ordinary["standing"] is False


@pytest.mark.parametrize("espn", [DARK, EMPTY, FIXTURES, NOT_READ, NO_SCHEDULE_BOARD])
@pytest.mark.parametrize("schedule", [DARK, EMPTY, FIXTURES, NOT_READ, NO_SCHEDULE_BOARD])
@pytest.mark.parametrize("live", [DARK, EMPTY, FIXTURES, NOT_READ, NO_SCHEDULE_BOARD])
def test_nothing_changed_for_a_sport_that_has_not_flipped(espn, schedule, live):
    """**The inertness proof, and the reason this ship is safe to land today.**

    No sport is standing — `AUTHORITY_BY_SPORT` is all ESPN — so every decision
    production makes runs the un-flipped path, and this ship must therefore
    change nothing a user or an operator sees until somebody flips a sport.

    Written as an invariant rather than as a diff against a git blob, so it
    keeps holding: for a candidate, `is_unserved` is exactly the old
    `code in BLANK_CODES` test, and `standing` is never set. A future refusal
    added to the standing path that leaks into the candidate path reds here.

    Proved once against master's own `decide` at build time as well — 250
    combinations of (espn, schedule, live, gate) with `standing=espn`, 0
    differences in code, serving, failed_over or why.
    """
    for gate in ((True, "seven MEETS"), (False, "not measured yet")):
        decision = decide(
            NFL, espn=espn, statpal=schedule, statpal_live=live,
            gate=gate, standing=ESPN,
        )
        assert decision.standing is False
        assert is_unserved(decision) == (decision.code in BLANK_CODES), (
            "the standing path's severity rule leaked onto a candidate: "
            f"{decision.code} now answers differently to `BLANK_CODES`"
        )


def test_the_flip_this_ship_made_safe_was_performed_by_a_different_ship():
    """This ship made the flip SAFE; it did not perform it — and one has now happened.

    Was `test_the_switch_itself_still_did_not_move`, asserting
    `set(AUTHORITY_BY_SPORT.values()) == {ESPN}`. It existed so that "someone
    flipped a sport in a PR that only claimed to make flipping survivable"
    could not pass unseen.

    #4954 flipped `americanfootball_nfl` on 2026-09-11, in a PR that claimed
    exactly that and nothing else — which is the outcome this guard wanted, not
    a breach of it. Re-derived onto the property that still separates the two:
    **a sport in the switch carries FLIP_EVIDENCE, and this file's own
    subject-matter (the standing-serving machinery) is not what put it there.**

    The `precondition` assertion is the load-bearing half. It is how a reader
    of THIS file learns that its ship is what made that flip survivable, and it
    is what would red if a future flip were taken without it — the 2026-09-09
    measurement (authority/085) was that a flip before #4434 went silently
    blank during an ESPN outage.
    """
    flipped = {k: v for k, v in AUTHORITY_BY_SPORT.items() if v != ESPN}
    for key in flipped:
        evidence = FLIP_EVIDENCE.get(key)
        assert evidence, (
            f"{key} was flipped to StatPal with no FLIP_EVIDENCE entry — that "
            "is a flip arriving in a diff, which is what this guard is for"
        )
        assert "#4434" in (evidence.get("precondition") or ""), (
            f"{key} was flipped without naming #4434 as its precondition. "
            "Before this ship, STANDING_STATPAL was in neither FAILOVER_CODES "
            "nor BLANK_CODES and a flipped sport went blank during an ESPN "
            "outage, counted as neither served nor uncovered (authority/085, "
            "2026-09-09). A flip that does not know that is a flip taken on "
            "the old measurement"
        )


# ── At the actor: the writers run, and the blank alarms ─────────────────────


@pytest.mark.asyncio
async def test_a_standing_sport_dispatches_the_writers_counted_apart(monkeypatch):
    """**The ship at the actor.** Fixtures, score and clock actually get written.

    Before #4434 this pass wrote nothing at all: `STANDING_STATPAL` was in
    neither set the actor branches on, so it fell to the `else` and logged an
    INFO. Counted as `standing_serving` rather than `failover_serving` because
    it is not an outage — the sport is being served by its source of record,
    which is the normal state for a flipped sport, and folding it into the
    failover count would report a permanent degradation.
    """
    import app.tasks.statpal_sync as statpal_sync
    from app.tasks.espn_sync import _act_on_failovers

    calls: list[str] = []

    async def _schedules(sport_key):
        calls.append(f"schedule:{sport_key}")
        return {"ok": True}

    async def _livescores():
        calls.append("live")
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)

    decision = _standing(espn=DARK, statpal=FIXTURES, statpal_live=FIXTURES)
    stats: dict = {"errors": []}
    await _act_on_failovers({NFL: decision}, stats)

    assert calls == [f"schedule:{NFL}", "live"], (
        f"the standing sport's writers did not run: {calls}"
    )
    assert stats["standing_serving"] == 1
    assert stats.get("failover_serving", 0) == 0, (
        "a flipped sport is not in an outage and must not be counted as one"
    )
    assert stats["failover_schedule_writes"] == 1
    assert stats["failover_live_writes"] == 1
    assert stats["failover"][0]["code"] == STANDING_STATPAL


@pytest.mark.asyncio
async def test_a_standing_sport_with_a_dark_standby_is_uncovered_at_the_actor(
    monkeypatch,
):
    """The alarm half, at the actor. Nothing is dispatched and it is COUNTED.

    The pre-#4434 behaviour for this exact state was: no write, no count, one
    INFO line. A sport whose source of record is dark during an ESPN outage is
    the state the site is blank in, and it was the quietest thing on the pass.
    """
    import app.tasks.statpal_sync as statpal_sync
    from app.tasks.espn_sync import _act_on_failovers

    calls: list[str] = []

    async def _schedules(sport_key):
        calls.append(f"schedule:{sport_key}")
        return {"ok": True}

    async def _livescores():
        calls.append("live")
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)

    decision = _standing(espn=DARK, statpal=DARK, statpal_live=DARK)
    stats: dict = {"errors": []}
    await _act_on_failovers({NFL: decision}, stats)

    assert calls == [], "nothing may be dispatched to a standby that is dark"
    assert stats["failover_uncovered"] == 1
    assert stats.get("standing_serving", 0) == 0
    assert stats.get("failover_serving", 0) == 0


@pytest.mark.asyncio
async def test_the_actor_asks_the_decision_not_the_code_set(monkeypatch):
    """**Found by mutation — M8, the one survivor of the first sweep.**

    Reverting the actor's `is_unserved(decision)` to the old
    `decision.code in BLANK_CODES` left every other test in this file green,
    because the severity divergence was pinned at the pure function and nowhere
    at the call site. So a flipped sport StatPal publishes no board for — soccer
    or tennis, the two this is permanently true of — would go back to logging an
    INFO and counting nothing, which is the exact shape of the #4434 defect one
    layer up.

    This is the paired actor assertion for
    `test_no_schedule_board_is_a_fault_for_a_standing_sport_and_benign_otherwise`.
    """
    import app.tasks.statpal_sync as statpal_sync
    from app.tasks.espn_sync import _act_on_failovers

    calls: list[str] = []

    async def _schedules(sport_key):
        calls.append(f"schedule:{sport_key}")
        return {"ok": True}

    async def _livescores():
        calls.append("live")
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)

    decision = _standing(espn=DARK, statpal=NO_SCHEDULE_BOARD, statpal_live=EMPTY)
    assert decision.code not in BLANK_CODES, (
        "the premise moved: this test only has teeth while the code is OUTSIDE "
        "`BLANK_CODES`, which is what makes the actor's question observable"
    )

    stats: dict = {"errors": []}
    await _act_on_failovers({NFL: decision}, stats)

    assert calls == [], "nothing may be dispatched to a standby with no board"
    assert stats["failover_uncovered"] == 1, (
        "the actor fell back to a code-level set: a flipped sport whose source "
        "of record publishes no board for its window is unserved, and this is "
        "the pass on which nobody notices"
    )
    assert stats.get("standing_serving", 0) == 0


@pytest.mark.asyncio
async def test_the_caller_reads_the_standby_for_a_flipped_sport(monkeypatch):
    """End to end through `_decide_failovers`, with the switch really flipped.

    Proves the composition rather than the pieces: the caller re-reads the
    standby on `STANDBY_NOT_READ` and re-decides, and that retry has to work for
    a standing sport too or the acceptance is unreachable in production however
    correct the pure function is.
    """
    import app.tasks.espn_sync as espn_sync
    import app.tasks.statpal_sync as statpal_sync

    # The module-level import is the same dict object `authority_for` reads, so
    # mutating it here really does flip the sport for the duration of the test.
    monkeypatch.setitem(AUTHORITY_BY_SPORT, NFL, STATPAL)

    reads: list[str] = []

    async def _standby(sport_key):
        reads.append(sport_key)
        return FIXTURES, FIXTURES

    monkeypatch.setattr(espn_sync, "_statpal_standby_reading", _standby)

    async def _schedules(sport_key):
        return {"ok": True}

    async def _livescores():
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)

    stats: dict = {"errors": []}
    decisions = await espn_sync._decide_failovers({}, {NFL}, stats)
    await espn_sync._act_on_failovers(decisions, stats)

    assert reads == [NFL], (
        "the caller never read the standby for a flipped sport, so the standing "
        f"path can never reach its serving state in production. Reads: {reads}"
    )
    assert decisions[NFL].code == STANDING_STATPAL
    assert stats["standing_serving"] == 1
