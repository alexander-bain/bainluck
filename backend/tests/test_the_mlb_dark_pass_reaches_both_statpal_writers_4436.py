"""The MLB dark pass reaches BOTH StatPal writers. #4436, CERT-2531's follow-up.

Ship parent #2867 (pillar: MATCHING) — *every game exists on the site before any
market lists it; nothing goes blank when ESPN does*. This is the nonblocking
follow-up CERT-2531 named when it granted D113's token:

    `4436-MLB-DARK-PASS-REACHES-BOTH-STATPAL-WRITERS`: preserve the independent
    runtime-chain check above as a direct repository test.

The grader ran that chain by hand at the exact SHA and watched it work. A check
that lives only in a cert report is not a guard — the next change to either half
gets no red. This file is that check, in the repository.

WHAT IS ACTUALLY UNGUARDED — MEASURED, NOT ASSUMED
═══════════════════════════════════════════════════
The obvious story is that the seam is unguarded: the gate suite
(`test_mlb_fails_over_and_the_ruling_still_cannot_skip_the_structure_4436.py`)
stops at the verdict, the actor suites
(`test_standing_statpal_is_a_serving_state_4434.py`,
`test_authority_failover_3473.py`) start from a `FailoverDecision` the test
itself built, so a `decide()` returning a code the actor does not branch on
would slip between them.

**That story is mostly wrong, and a nine-mutant matrix says so.** Dropping
`FAILOVER-ESPN-DARK` from `FAILOVER_CODES`, deleting either writer call,
mis-counting the outage as a flip, calling the schedule writer twice — every one
is already caught, six by `#3473` and one by the gate file. Seven of nine
mutants this file kills are killed by an existing suite too. Redundant coverage
is worth having and is not worth claiming as a hole.

**The two that nothing else catches are per-sport ones**, and they are the
reason the follow-up names a SPORT:

  * an actor branch narrowed by sport key
    (`if decision.code in FAILOVER_CODES and sport_key != "baseball_mlb"`);
  * an early return for one sport inside `_serve_schedule_from_statpal`.

Both leave `#3473` green, because every existing actor test drives the chain
with the NFL or a constructed sport, and both leave the gate file green, because
MLB's gate still permits. Nothing in the repository asserted that BASEBALL, by
name, reaches the writers — so a one-sport kill-switch or exclusion was
invisible. That is a plausible regression, not a contrived one: narrowing a
branch to exclude a misbehaving sport is exactly what an operator reaches for
during an incident.

So the general clause is narrower than the tempting one: it is not that a seam
between two well-tested halves is unguarded. It is that **coverage parameterised
over one sport does not cover another, however generic the code under it looks**
— and the only way to know which is which is to cut the mutant and run both.

WHY THE CONTROL IS HERE
═══════════════════════
`test_an_unruled_sport_on_the_same_dark_pass_writes_nothing` is not decoration.
Without it, an actor that served every sport it was handed — or a monkeypatch
wired to the wrong module — would pass the positive arm for the wrong reason.
The control shows the gate is what does the work: same pass, same readings, same
patched writers, and the NHL (still waiting on D50's streak, `#4436`'s
`test_the_nhl_still_waits`) gets nothing written for it.

WHAT THIS FILE DOES NOT RE-TEST
═══════════════════════════════
Livescore COALESCING across several dark sports — one live write for three
sports, `failover_live_sports_covered` at 3 — is CERT-2052's property and is
already asserted in `test_authority_failover_3473.py`. Re-asserting it here
would pin the same behaviour in two files, which is how a shared property comes
to be retuned in one place and silently contradicted in the other.
"""

import pytest

from app.config.authority_by_sport import flip_permitted
from app.utils.authority_failover import (
    DARK,
    FAILOVER_CODES,
    FAILOVER_ESPN_DARK,
    FIXTURES,
    decide,
)

MLB = "baseball_mlb"
NHL = "icehockey_nhl"


def _decision_for(sport_key):
    """The decision production computes for `sport_key` on an ESPN-dark pass.

    Every input is the real thing: `flip_permitted` reads the shipped config,
    and `decide` reads `AUTHORITY_BY_SPORT` for the standing value. Nothing here
    is a stand-in except the two readings, which is the pass being described.

    The ledger is `[]` deliberately. That is not "no data" as a convenience —
    it is the state `_decide_failovers` actually hands the gate when the durable
    agreement read FAILS (#4443), so it is the arm on which a ruled sport must
    be permitted or the failover is still gated on the monitor being readable.
    """
    return decide(
        sport_key,
        espn=DARK,
        gate=flip_permitted(sport_key, []),
        statpal=FIXTURES,
        statpal_live=FIXTURES,
    )


@pytest.fixture
def writer_calls(monkeypatch):
    """Both StatPal writers, replaced by recorders, in call order.

    Patched on `app.tasks.statpal_sync` rather than on `espn_sync`, because the
    actor imports them inside the function body at call time — patching the
    importing module would bind nothing.

    The list preserves ORDER, which carries a real claim: the per-sport schedule
    write happens inside the loop and the single live write after it, so
    `["schedule:…", "live"]` is the sequence and `["live", "schedule:…"]` would
    be a live pass over fixtures that had not been written yet.
    """
    import app.tasks.statpal_sync as statpal_sync

    calls: list[str] = []

    async def _schedules(sport_key):
        calls.append(f"schedule:{sport_key}")
        return {"ok": True}

    async def _livescores():
        calls.append("live")
        return {"ok": True}

    monkeypatch.setattr(statpal_sync, "_sync_statpal_schedules", _schedules)
    monkeypatch.setattr(statpal_sync, "_sync_statpal_livescores", _livescores)
    return calls


class TestTheSeamBetweenTheGateAndTheActor:
    """The join nothing asserted: does the gate's own output drive the actor?"""

    def test_the_real_config_puts_mlb_in_the_dark_failover_state(self):
        """First link. The shipped config, not a constructed specimen.

        Asserted apart from the chain so a failure says WHICH link broke: this
        one red and the next green means the config moved, not the actor.
        """
        decision = _decision_for(MLB)

        assert decision.code == FAILOVER_ESPN_DARK, decision.why
        assert decision.failed_over is True, decision.why
        assert decision.serving == "statpal", decision.why
        assert decision.standing is False, (
            "MLB is ESPN-standing and this ship did not flip it; a standing "
            "decision here would mean the switch moved, not that failover works"
        )

    def test_that_code_is_one_the_actor_actually_branches_on(self):
        """The seam itself, as a single assertion.

        `_act_on_failovers` serves a sport when `decision.code in
        FAILOVER_CODES`, so a rename or a set edit on either side stops the
        writers dead. Kept for the clear failure message rather than for unique
        coverage: `#3473` catches a `FAILOVER_CODES` edit too (measured — see
        the module docstring). This one names MLB in the assertion, so the red
        says which sport stopped being served.
        """
        assert _decision_for(MLB).code in FAILOVER_CODES, (
            "MLB's dark-pass code is not in the set the actor serves on — the "
            "gate permits, the actor ignores it, and nothing is written"
        )


class TestTheChainReachesBothWriters:
    """End to end: real config in, both StatPal writers called."""

    @pytest.mark.asyncio
    async def test_the_mlb_dark_pass_runs_the_schedule_and_live_writers_once_each(
        self, writer_calls
    ):
        """CERT-2531's runtime-chain check, preserved.

        The grader's words for what it watched at the exact SHA: MLB returns
        `FAILOVER-ESPN-DARK`, selects StatPal, invokes
        `_sync_statpal_schedules("baseball_mlb")` once, and invokes the global
        livescore writer once.

        `once` is load-bearing on both. The schedule writer is per sport and the
        live writer is per pass, so a second schedule call would be a duplicate
        read and a second live call would be CERT-2052's coalescing regression.

        **This is the arm that carries the file's unique coverage.** It asserts
        the sport KEY that reached the writer, so it is the only test in the
        repository that a per-sport exclusion — at the actor branch or inside
        `_serve_schedule_from_statpal` — turns red.
        """
        from app.tasks.espn_sync import _act_on_failovers

        stats: dict = {"errors": []}
        await _act_on_failovers({MLB: _decision_for(MLB)}, stats)

        assert writer_calls == [f"schedule:{MLB}", "live"], (
            f"the MLB dark pass did not reach both writers: {writer_calls}"
        )
        assert stats["failover_schedule_writes"] == 1
        assert stats["failover_live_writes"] == 1
        assert stats["errors"] == [], stats["errors"]

    @pytest.mark.asyncio
    async def test_the_pass_is_counted_as_an_outage_and_not_as_a_flip(
        self, writer_calls
    ):
        """Served, and counted in the right bucket.

        The two counters are not interchangeable. `standing_serving` says a
        sport's source of record is StatPal — a permanent state; MLB in
        `standing_serving` would report the site as permanently degraded for
        baseball for as long as the miscount lasted. This pass is an outage
        MLB rode out, which is `failover_serving`.
        """
        from app.tasks.espn_sync import _act_on_failovers

        stats: dict = {"errors": []}
        await _act_on_failovers({MLB: _decision_for(MLB)}, stats)

        assert stats["failover_serving"] == 1
        assert stats.get("standing_serving", 0) == 0, (
            "an ESPN outage was reported as a flip to StatPal"
        )
        assert stats.get("failover_uncovered", 0) == 0

    @pytest.mark.asyncio
    async def test_the_pass_publishes_a_receipt_naming_baseball(self, writer_calls):
        """The operator's half. An outage ridden out silently is unrecoverable.

        Receipts are per pass rather than edge-triggered, so this is the only
        record that MLB was served by the standby on this pass.
        """
        from app.tasks.espn_sync import _act_on_failovers

        stats: dict = {"errors": []}
        await _act_on_failovers({MLB: _decision_for(MLB)}, stats)

        assert [r["sport_key"] for r in stats["failover"]] == [MLB]
        assert stats["failover"][0]["code"] == FAILOVER_ESPN_DARK
        assert stats["failover"][0]["failed_over"] is True


class TestTheGateIsWhatDoesTheWork:
    """The control that makes the positive arms mean something."""

    @pytest.mark.asyncio
    async def test_an_unruled_sport_on_the_same_dark_pass_writes_nothing(
        self, writer_calls
    ):
        """Same pass, same readings, same patched writers — and no writes.

        The NHL is still waiting on D50's streak (`#4436`'s
        `test_the_nhl_still_waits`), so its gate refuses and its decision never
        enters `FAILOVER_CODES`. If this arm ever goes green alongside a served
        NHL, the actor has stopped consulting the gate and every unruled sport
        is failing over.

        It also proves the positive arms are not passing on a blanket serve or a
        misdirected monkeypatch: the identical fixture records nothing here.
        """
        from app.tasks.espn_sync import _act_on_failovers

        decision = _decision_for(NHL)
        assert decision.code not in FAILOVER_CODES, (
            f"the NHL is failing over on an unruled gate: {decision.why}"
        )

        stats: dict = {"errors": []}
        await _act_on_failovers({NHL: decision}, stats)

        assert writer_calls == [], (
            f"a sport the gate refused reached StatPal's writers: {writer_calls}"
        )
        assert stats.get("failover_serving", 0) == 0
        assert stats.get("failover_schedule_writes", 0) == 0
        assert stats.get("failover_live_writes", 0) == 0
