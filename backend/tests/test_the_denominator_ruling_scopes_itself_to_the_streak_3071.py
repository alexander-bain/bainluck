"""The open-denominator disclosure may only claim what it actually binds.

PILLAR: TRUTH. SHIP: the operator deciding a source-of-record flip stops being
told there is an unresolved safety question governing a sport whose flip has no
denominator in it.

#3071, the disclosure's SCOPE only — the floor itself (Question A, and the value
of N) is Alex's and that issue stays open for it. `MINIMUM_SCORED_DENOMINATOR`
is untouched at 2 and no gate state moves.

The defect, read off production 2026-09-19 (authority/495):
`minimum_denominator_ruling` is served on all 7 governing blocks and opened
"#3071 (Question A) is open: the minimum denominator FOR A FLIP is unruled."
Three of those 7 — every key in `ruled_without_streak` — reach `flip_permitted`
and are answered `True` by D104 = A4 *before the streak is consulted at all*. No
denominator, floored or not, decides their flip. The sentence announced an open
question about a decision that does not have one.

This is #5139's rot ~80 lines below the clause #5139 repaired, and
`test_the_summary_names_no_sport_5139` is structurally blind to it: that guard
refuses prose that names a MEMBER of the ruled set, and this constant names no
sport. It over-claims SCOPE instead.

The guards below fail for different reasons, because the repair has more than
one way to come undone. They are listed without a count: a sentence that counts
its own collection is #3519's rot, and writing one at the top of the file that
exists to refuse stale prose would be the joke telling itself.

  * `test_the_ruling_does_not_claim_to_govern_a_flip` — the regression itself.
    Scope prose that promotes "the streak" to "a flip" is the whole defect.
  * `test_every_field_the_ruling_cites_is_actually_served` — the #4274 class.
    This lane has already shipped prose citing a `days[]` the payload did not
    contain; a sentence that tells a reader to go and read a field earns that
    field being there. Generalised, so it also covers whatever the next edit
    decides to cite.
  * `test_the_ruling_is_broadcast_unchanged_on_every_sport` — the reach. One
    constant, every row, ruled and unruled alike, is WHY a scope error mattered
    at all; it also keeps the two guards above from passing on an empty set.
  * `test_the_ruling_names_no_sport` — #5139's rule, applied to the constant its
    own guard cannot reach. Prose that names no member cannot rot as the set
    grows, and the set grew again in #7089.
  * `test_the_floor_itself_is_untouched_and_no_gate_moves` — the fence. This
    ship is a wording change; Question A is Alex's. Pinned beside the wording so
    a reader can see the floor was not quietly answered on the way past.

Every one was proven non-vacuous by mutation (authority/495): naming a sport,
citing an absent field, moving the floor to 200 and dropping the broadcast each
red exactly their own guard and no other. The 200 mutant is worth noting — it is
the one `scripts/authority_024_mutation_battery.py` cannot write, because it
anchors on the literal "MINIMUM_SCORED_DENOMINATOR = 2", which is a PREFIX of
"= 200" (authority/085 recorded the trap; this closes it).
"""

from __future__ import annotations

import re

import pytest

from app.routes import admin_providers
from app.utils.authority_agreement import (
    MINIMUM_DENOMINATOR_RULING,
    MINIMUM_SCORED_DENOMINATOR,
    SHADOW_STAMPERS,
    governing_identity,
)


@pytest.fixture
def call(monkeypatch):
    """Invoke the agreement endpoint with auth stubbed and metrics controlled.

    A local copy of the endpoint suite's fixture, for the reason
    `test_authority_summary_names_no_sport_5139` gives: a pytest fixture is not
    visible outside the module that defines it, and promoting this one to
    `conftest.py` would widen its blast radius across ~19,000 tests for the sake
    of one assertion here. `FakeSession` IS imported from that suite, because a
    second fake answering the endpoint's censuses differently is a fake that can
    agree with a bug.
    """

    async def _call(*, metrics, session):
        monkeypatch.setattr(
            admin_providers, "_check_admin_secret", lambda *a, **k: None
        )
        import app.tasks.redis_state as redis_state

        monkeypatch.setattr(redis_state, "get_task_metrics", lambda name: metrics)
        return await admin_providers.statpal_authority_agreement(
            request=None, secret="x", db=session
        )

    return _call


#: Sport nouns that hide inside a compound population key.
#:
#: `americanfootball_nfl` splits into `americanfootball`, and a sentence would
#: say "football"; same for `icehockey` -> "hockey". Taken from #5139's guard
#: rather than re-derived, because without it this test would pass on the exact
#: wording it exists to refuse.
COMPOUND_HEADS = ("football", "hockey")


def _sport_words() -> set[str]:
    """Every word a sentence could use to name one of the published populations.

    Derived from `SHADOW_STAMPERS` rather than typed out, so the vocabulary
    grows when a population is added: a guard whose subject is a growing list
    may not hold a snapshot of that list.
    """
    words: set[str] = set()
    for key in SHADOW_STAMPERS:
        parts = key.split("_")
        words.update(parts)
        for part in parts:
            for head in COMPOUND_HEADS:
                if part.endswith(head) and part != head:
                    words.add(head)
    # The tokens that are not a sport: `tennis_singles`/`tennis_doubles` are
    # draw shapes and `soccer` is an id space, but all three ARE names a stale
    # sentence could pin itself to, so they stay in the vocabulary. What comes
    # out are words that cannot identify anything on their own.
    return {word for word in words if len(word) > 3}


def _healthy_block(sport_key: str) -> dict:
    """The governing block a sport scores on a clean, well-populated day.

    The real builder, not a hand-written dict: the whole class of defect this
    file is about is prose and payload drifting apart, so a fixture that states
    what the block "should" contain would be asserting the answer.

    The counts are the shape the defect was found on — production's football row
    on 2026-09-19, agreeing with StatPal about all 321 fixtures. A population
    with no governing number ruled ignores them and returns its PENDING block,
    which is what makes this usable for all seven keys.
    """
    return governing_identity(
        sport_key,
        {
            "both": 321,
            "statpal_only": 0,
            "ours_only": 0,
            "pct": 100.0,
            "ours_covered_pct": 100.0,
        },
    )


def test_the_ruling_does_not_claim_to_govern_a_flip():
    """The open question binds the STREAK; for a ruled sport it binds nothing.

    The regression guard. `flip_permitted` answers a key in
    `FLIP_RULED_WITHOUT_STREAK` from the ruling before it reads a single ledger
    day, so a denominator cannot be a precondition of that sport's flip. A
    disclosure served on that sport's own row may not say otherwise.
    """
    text = MINIMUM_DENOMINATOR_RULING

    assert "for a flip is unruled" not in text, (
        "the disclosure has gone back to claiming the open denominator governs "
        "A FLIP. It is served on every sport's block, including every key in "
        "`ruled_without_streak`, whose flip D104 = A4 permits before the streak "
        "is read at all. Scope it to the streak: " + repr(text)
    )

    # Positive half, so the guard cannot be satisfied by deleting the sentence:
    # it must still say what it DOES bind, and name the exemption a reader needs
    # in order to tell whether it binds the row in front of them.
    assert "STREAK" in text, (
        "the disclosure no longer says the open question is about a streak, so "
        "a reader cannot tell what it binds: " + repr(text)
    )
    assert "ruled_without_streak" in text, (
        "the disclosure does not point at `ruled_without_streak`, so a reader "
        "of a ruled sport's row has no way to learn the sentence is moot for "
        "them. That list is the only non-rotting way to say it (#5139): " + repr(text)
    )


@pytest.mark.asyncio
async def test_every_field_the_ruling_cites_is_actually_served(call):
    """A sentence that sends the reader to a field earns that field existing.

    The #4274 class, generalised. Each streak block's `note` once ended "the
    denominator those days were measured over is on each entry in `days[]`" and
    the served payload had no `days[]` — prose and payload drifted apart with
    nothing watching the join. This asserts the join for whatever the ruling
    cites, so the next edit is covered too rather than only today's two names.
    """
    from tests.test_authority_agreement_endpoint import FakeSession

    out = await call(
        metrics={"last_result_summary": {}},
        session=FakeSession(anchors=1, column_agrees=1),
    )

    cited = set(re.findall(r"`([a-z_]+)`", MINIMUM_DENOMINATOR_RULING))
    assert cited, (
        "the ruling cites no field at all — either the backtick convention "
        "changed or the sentence stopped telling the reader where to look, and "
        "this guard would then be asserting nothing"
    )

    # Where a reader could actually find them: the top level of the payload, and
    # the governing block the sentence is served on.
    #
    # The two halves come from two producers on purpose. `ruled_without_streak`
    # is assembled by the endpoint, so only the endpoint can vouch for it. The
    # governing keys come from `governing_identity` itself rather than from a
    # served row, because `FakeSession` carries no ledger snapshot and every
    # `agreement` it produces is `None` — reading the block off that payload
    # would check the join against nothing and pass (gotcha #53's shape: an
    # absent block and a correct one are not the same answer).
    top_level = set(out)
    governing_keys = set(_healthy_block("americanfootball_nfl"))

    assert "denominators" in governing_keys, (
        "the reference governing block carries no `denominators`, so this "
        "guard's own notion of what a block contains is wrong"
    )

    available = top_level | governing_keys
    missing = sorted(cited - available)
    assert not missing, (
        f"the ruling sends the reader to {missing}, which nothing serves. "
        f"Cited: {sorted(cited)}. Available at the top level: "
        f"{sorted(top_level)}; on a governing block: {sorted(governing_keys)}"
    )


def test_the_ruling_is_broadcast_unchanged_on_every_sport(call):
    """Anti-vacuity for the guards above, and the reach of the defect.

    The scope error mattered because the string is broadcast: one constant,
    every row, ruled and unruled alike — that is why a sentence true of the
    streak-gated sports was served, verbatim, on three that no denominator
    binds. Driven across every population the endpoint publishes, including the
    ones that score `PENDING-NO-GOVERNING-NUMBER`, because those rows carry the
    sentence too (4 of the 7 in production on 2026-09-19 did).
    """
    blocks = {key: _healthy_block(key) for key in SHADOW_STAMPERS}
    assert len(blocks) >= 7, (
        f"only {len(blocks)} populations were driven; production serves 7 and a "
        f"guard over fewer rows than the payload has is not watching the payload"
    )

    served = {key: block["minimum_denominator_ruling"] for key, block in blocks.items()}
    distinct = set(served.values())
    assert distinct == {MINIMUM_DENOMINATOR_RULING}, (
        f"{len(distinct)} distinct ruling strings reached the governing blocks "
        f"across {len(served)} populations; the constant is supposed to be the "
        f"only source"
    )

    # The reach is the point: at least one driven row is a sport the ruling is
    # moot for. If that ever stops being true the scope clause is unnecessary,
    # and whoever removes it should have to say so here.
    assert any(
        block["gate"] == "PENDING-NO-GOVERNING-NUMBER" for block in blocks.values()
    ), "no PENDING row was driven, so the broadcast onto ungoverned rows is untested"


def test_the_ruling_names_no_sport():
    """#5139's rule, applied to the constant #5139's own guard cannot reach.

    That guard is scoped to `FLIP_GATE_SUMMARY`. This constant sits ~80 lines
    below it, is served on every row, and was never covered — which is how it
    kept a justification naming two sports through two changes to the ruled set.
    """
    text = MINIMUM_DENOMINATOR_RULING.lower()
    named = sorted(word for word in _sport_words() if word in text)
    assert not named, (
        f"the ruling names {named}. A sentence that names a member of the ruled "
        f"set goes stale the day that set changes — #5139 for `FLIP_GATE_SUMMARY`, "
        f"and the set changed again in #7089. Point at `ruled_without_streak` "
        f"instead: {MINIMUM_DENOMINATOR_RULING!r}"
    )


def test_the_floor_itself_is_untouched_and_no_gate_moves():
    """This ship is the disclosure's wording. It is NOT Question A's answer.

    #3071 asks for a floor and explicitly says the authority lane does not make
    that ruling. A scope fix that quietly moved the constant would be answering
    it — so the value is pinned here, beside the wording change, where a reader
    of this file can see that nothing was smuggled.
    """
    assert MINIMUM_SCORED_DENOMINATOR == 2, (
        "MINIMUM_SCORED_DENOMINATOR moved. That is Question A (#3071), it is "
        "Alex's, and no scope correction to the disclosure may decide it"
    )

    # The gate a real row scores is a function of values, denominators and the
    # bar — never of the disclosure prose. Driven rather than asserted in the
    # abstract, on the shape the defect was found on (a ruled sport at 100% over
    # a large denominator) and on the one the floor exists for.
    healthy = {
        "both": 321,
        "statpal_only": 0,
        "ours_only": 0,
        "pct": 100.0,
        "ours_covered_pct": 100.0,
    }
    assert governing_identity("americanfootball_nfl", healthy)["gate"] == "MEETS"

    degenerate = {
        "both": 1,
        "statpal_only": 0,
        "ours_only": 0,
        "pct": 100.0,
        "ours_covered_pct": 100.0,
    }
    assert (
        governing_identity("americanfootball_nfl", degenerate)["gate"]
        == "TOO-FEW-TO-SCORE"
    ), "the one-game refusal is the floor's whole job and it must still fire"
