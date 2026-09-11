"""The served flip summary must not name a sport, and the ruled set travels as data.

PILLAR: TRUTH. SHIP: the operator deciding a source-of-record flip is told which
sports the seven-day proof still binds — the sentence a flip proposal quotes
stops naming a stale set.

#5139. `FLIP_GATE_SUMMARY` is the payload's opening sentence. Its D104 clause
read ``for a sport in `authority_by_sport.FLIP_RULED_WITHOUT_STREAK` (football
today)`` and went on reading it after the NBA joined the set (#4493) and the MLB
after it (#4436). On 2026-09-11 — the first day football, basketball AND hockey
all reported ``7/7`` — that sentence told the reader two false things at once:
that basketball's streak still gated its flip (it had not since #4493), and that
nothing separated hockey from basketball (hockey was the only one of the three
the seven days still bound, on a 32-game denominator).

This is the #3519 class exactly, one clause later.
`test_authority_summary_counts_no_numbers_3519.py` says it in general terms —
*"served prose that counts a collection goes stale the moment the collection
grows, and the count is exactly the part no test looks at"* — but its guard is
scoped to a counting word qualifying `number(s)`, so it cannot see a clause that
names a MEMBER of a different collection.

The repair is not a better sentence. `utils.authority_agreement` cannot
interpolate the set (`config.authority_by_sport` imports THAT module, so the
dependency runs one way only), which is what pushed the list into hand-written
prose to begin with. So the prose names no member at all and the set is served
as `ruled_without_streak`, derived from the frozenset on every pass.

Two guards, and they fail for different reasons:
  * the summary names no sport — prose that names no member cannot rot;
  * the served list IS the frozenset — data that is derived cannot drift.
"""

from __future__ import annotations

import re

import pytest

from app.config.authority_by_sport import FLIP_RULED_WITHOUT_STREAK, STATPAL
from app.routes import admin_providers
from app.utils.authority_agreement import FLIP_GATE_SUMMARY, SHADOW_STAMPERS


@pytest.fixture
def call(monkeypatch):
    """Invoke the agreement endpoint with auth stubbed and metrics controlled.

    A local copy of the endpoint suite's fixture: a pytest fixture is not
    visible outside the module that defines it, and moving that one to
    `conftest.py` would widen its blast radius across ~19,000 tests for the
    sake of two assertions here. `FakeSession` IS imported from there, because
    a second fake that answers the endpoint's censuses differently is a fake
    that can agree with a bug.
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
#: say "football". Same for `icehockey` → "hockey". Without this the guard would
#: pass on the very wording that caused #5139, which is the one string it exists
#: to refuse.
COMPOUND_HEADS = ("football", "hockey")


def _sport_words() -> set[str]:
    """Every word a sentence could use to name one of the published populations.

    Derived from `SHADOW_STAMPERS` rather than typed out, so the vocabulary
    grows when a population is added — a guard whose subject is a growing list
    may not hold a snapshot of that list (the lesson `test_the_gate_summary_
    names_every_gate_state` records in the endpoint suite).
    """
    words: set[str] = set()
    for key in SHADOW_STAMPERS:
        parts = key.split("_")
        words.update(parts)
        for part in parts:
            for head in COMPOUND_HEADS:
                if part != head and part.endswith(head):
                    words.add(head)
    return words


def _prose(text: str) -> str:
    """The sentence with backticked identifiers removed.

    `authority_by_sport.FLIP_RULED_WITHOUT_STREAK` and `ruled_without_streak`
    are field names the summary exists to point at, not claims about which
    sports are in the set. #3519's guard strips them for the same reason, and a
    guard that forbade them would be unobeyable.
    """
    return re.sub(r"`[^`]*`", "", text)


def test_the_guard_vocabulary_is_not_empty_5139():
    """The subject of the guard below, asserted rather than assumed.

    `_sport_words` reads a module-level dict by name. If `SHADOW_STAMPERS` is
    renamed, re-keyed or emptied, the vocabulary silently becomes `set()` and
    the real guard passes on ANY wording — a green test that examines nothing.
    So pin the floor: these six nouns are what "names a sport" means here, and
    they must all be reachable from the published populations.
    """
    words = _sport_words()
    for expected in ("football", "basketball", "baseball", "hockey", "soccer", "tennis"):
        assert expected in words, (
            f"{expected!r} is not derivable from SHADOW_STAMPERS "
            f"({sorted(SHADOW_STAMPERS)}) — the vocabulary this guard scans for "
            "has gone stale or empty, so it would pass on prose that names a sport"
        )


def test_the_summary_names_no_sport_5139():
    """The defect itself: no member of the ruled set may appear in the prose.

    Deliberately wider than "no RULED sport". A sentence that names a sport
    which is NOT in the set ("hockey is still gated") rots the same way the
    moment that sport is ruled, and it rots silently, because nothing about the
    frozenset changes when the sentence becomes false.
    """
    offenders = sorted(
        word
        for word in _sport_words()
        if re.search(rf"\b{re.escape(word)}\b", _prose(FLIP_GATE_SUMMARY), re.I)
    )
    assert not offenders, (
        f"the flip summary names {offenders} in prose. The set of sports "
        "released from the seven-day gate is served as `ruled_without_streak` "
        "and named on each sport's own `authority.note`; a copy of it in this "
        "sentence is a copy that keeps saying 'football today' after the NBA "
        "(#4493) and the MLB (#4436) joined — which is #5139."
    )


def test_the_summary_still_points_at_the_served_field_5139():
    """Removing the list must not remove the answer.

    The reason the parenthetical existed is real: a reader needs to know WHICH
    sports skip the gate. If the prose stops naming them, it has to say where
    they are, or this repair has traded a stale answer for no answer.
    """
    assert "ruled_without_streak" in FLIP_GATE_SUMMARY, (
        "the summary no longer names the sports and no longer points at the "
        "field that does — a reader is left with the rule and no way to apply it"
    )
    assert "FLIP_RULED_WITHOUT_STREAK" in FLIP_GATE_SUMMARY


async def test_the_served_ruled_set_is_the_frozenset_5139(call):
    """The published list is derived, not restated.

    `_authority_note` already derives its per-sport sentence and its docstring
    says why (#4493). This asserts the payload-level list does the same, so the
    two can never disagree about which sports are ruled.
    """
    from tests.test_authority_agreement_endpoint import FakeSession

    out = await call(
        metrics={"last_result_summary": {}}, session=FakeSession(anchors=1, column_agrees=1)
    )

    assert out["ruled_without_streak"] == sorted(FLIP_RULED_WITHOUT_STREAK)
    # Sorted, not merely equal as a set: a frozenset's iteration order is not
    # stable across runs, and an operator diffing two captures of this payload
    # should see a change only when the SET changed.
    assert out["ruled_without_streak"] == sorted(out["ruled_without_streak"])


async def test_every_ruled_sport_says_so_on_its_own_row_5139(call):
    """The list and the per-sport notes are two renderings of one fact.

    The payload answers "which sports skip the gate" twice — once as
    `ruled_without_streak`, once in each sport's `authority.note`. If those two
    disagree, the reader believes whichever they read first, and #5139 is
    precisely what happens when one of them is maintained by hand.

    RULED AND FLIPPED ARE TWO FACTS, NOT ONE (#4954, 2026-09-11). As first
    written this asked ONE binary question of every row, because when it was
    written every sport was `ESPN` and "ruled" and "flipped" could not come
    apart. #4954 makes football `STATPAL`, and `_authority_note` answers a
    FLIPPED sport with the flip rather than with the gate — the gate sentence is
    moot for a sport that has already walked through it. Football is then in
    `ruled_without_streak` (D104 permitted it to flip without a streak — still
    true, and the field records the RULING) while its note carries no streak
    clause (it records what has HAPPENED). Those are not two answers to one
    question, so the old equality failed on a payload that was telling the
    truth. The two renderings still may not CONTRADICT each other, which is
    what this now asserts.

    Neither #5139 nor #4954 was wrong alone: each is green on its own base and
    they merge with no textual conflict. The pair produced a state neither
    reasoned about, and only a composed tree could see it (authority/129).
    Written to hold in BOTH directions so it cannot depend on merge order:
    before the flip no row takes the flipped branch and every assertion below
    is the original one, unchanged.
    """
    from tests.test_authority_agreement_endpoint import FakeSession

    out = await call(
        metrics={"last_result_summary": {}}, session=FakeSession(anchors=1, column_agrees=1)
    )
    served = set(out["ruled_without_streak"])
    checked = 0

    for entry in out["sports"]:
        note = entry["authority"]["note"]
        ruled = entry["sport_key"] in served

        if entry["authority"]["current"] == STATPAL:
            # Exempt from the equality, NOT from scrutiny: the one way this
            # branch could become a hole is a flipped row that still serves the
            # pre-flip gate sentence — the stale-note failure #5139 exists to
            # catch, wearing the new state as cover.
            assert "may fail over WITHOUT a certification streak" not in note, (
                f"{entry['sport_key']}: has flipped to StatPal, yet its note "
                f"still offers the pre-flip gate sentence — two answers again, "
                f"and the stale one reads as current: {note!r}"
            )
            checked += 1
            continue

        ruled_by_note = "may fail over WITHOUT a certification streak" in note
        assert ruled_by_note == ruled, (
            f"{entry['sport_key']}: `authority.note` says "
            f"ruled={ruled_by_note} while `ruled_without_streak` says {ruled}"
        )
        checked += 1

    # Anti-vacuity: an endpoint serving `sports: []` would satisfy every
    # assertion above by having nothing to assert them on.
    assert checked == len(out["sports"]) and checked > 0, (
        f"examined {checked} of {len(out['sports'])} rows — a guard that "
        f"inspects no row cannot fail"
    )
