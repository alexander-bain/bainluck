"""D21 (#1978, CAL-P150) — an absent per-bookmaker curve must refuse BY NAME.

THE DEFECT. The producer read ``bainluck:bookmaker_calibration`` inside a
``try: ... except Exception: pass``. When ``_precompute_bookmaker_calibration``
stopped finishing inside its soft time limit it stopped writing that key; the
key aged out of its 24 h TTL; the reader turned the absence into ZERO rows; and
those rows are concatenated into ``all_rows``, so the candidate went out
~96,026 outcomes short. The publish gate refused it every beat for a reason
that named the SYMPTOM — a population move — and could not name the CAUSE.
``/calibration`` served a day-old curve, silently, from 2026-08-29T00:36:47Z
until the writer was run by hand. Chain measured in ``fef05751`` and
``alex-inbox/calibration-907``.

THE FIX IS SMALL AND THE ARGUMENT FOR IT IS NOT "IT PUBLISHES MORE". It
publishes exactly as often: the gate already refused the short candidate. What
changes is that the refusal now carries which key, which writer, and how much
is missing. Which is why the interesting guard in this file is not the raise —
it is :func:`test_a_present_but_empty_curve_is_not_a_refusal`. A fix that turned
every quiet state into a hard failure would have replaced one outage with
another.

RED-FIRST, AND DELIBERATELY GRADED. Every test reaches the new symbol through
the module object rather than importing it by name, so at base this file
COLLECTS and the tests FAIL (``AttributeError``) — exit code 1, a result. A
``from ... import read_bookmaker_curve_rows`` would have made base exit 2 on a
collection error, which per gotcha #124 is "could not check", not a red.

GOTCHA #53 IS THE WHOLE SUBJECT: an empty answer is a response shape, not an
absence. Absent, unreachable and unparseable were indistinguishable from each
other AND from success under ``pass``. They are now distinguished from success
(the point) and from each other (two reason codes, because "Redis is down" and
"the writer has not landed a sweep" want different operators).
"""

import json
import re
from pathlib import Path

import pytest

from app.tasks import precompute_calibration as pc

#: Spelled out as well as imported. Asserting only ``pc.CONST in message``
#: checks the constant against itself — widening it to ``""`` would keep every
#: assertion below green while the contract went unpinned.
ABSENT = "bookmaker_curve_key_absent"
UNREADABLE = "bookmaker_curve_key_unreadable"
KEY = "bainluck:bookmaker_calibration"


class _Redis:
    """The narrowest possible stand-in: one ``get``, and a way to make it fail.

    Not a mock library double. The reader's whole contract is what it does with
    three shapes of answer from one call, so a fake that can produce exactly
    those three shapes is a more honest instrument than one that can produce
    anything.
    """

    def __init__(self, value=None, *, raises=False):
        self._value = value
        self._raises = raises
        self.asked = []

    def get(self, key):
        self.asked.append(key)
        if self._raises:
            raise ConnectionError("redis is not reachable")
        return self._value


def _read(rc, *, refuse=True):
    return pc.read_bookmaker_curve_rows(rc, refuse=refuse)


# ---------------------------------------------------------------------------
# 1. The three failures that used to be silent.
# ---------------------------------------------------------------------------

def test_an_absent_key_refuses_by_name():
    rc = _Redis(None)
    with pytest.raises(RuntimeError) as exc:
        _read(rc)

    message = str(exc.value)
    assert ABSENT in message
    assert pc.BOOKMAKER_CURVE_ABSENT_REFUSAL == ABSENT
    # The refusal has to be actionable, not merely named. An operator reading
    # it in a Sentry title must learn WHICH key and WHOSE job it is without
    # opening the source — that is the whole difference from the gate's
    # "population moved" refusal, which was accurate and useless.
    assert KEY in message
    assert "precompute_bookmaker_calibration" in message
    assert "prior snapshot preserved" in message
    assert rc.asked == [KEY], (
        "the reader must ask for the key this module names, not a literal that "
        f"can drift away from it (asked {rc.asked!r})"
    )


def test_an_empty_string_is_absent_too():
    """The TTL-expiry and the never-written cases arrive differently.

    ``redis-py`` returns ``None`` for a missing key, but a decoded empty value
    is ``""`` and is equally unusable. Both are the outage shape, so both take
    the same reason code — the alternative is a second silent path with a new
    name.
    """
    with pytest.raises(RuntimeError) as exc:
        _read(_Redis(""))
    assert ABSENT in str(exc.value)


def test_an_unreachable_redis_refuses_with_a_different_name():
    with pytest.raises(RuntimeError) as exc:
        _read(_Redis(raises=True))

    message = str(exc.value)
    assert UNREADABLE in message
    assert pc.BOOKMAKER_CURVE_UNREADABLE_REFUSAL == UNREADABLE
    assert ABSENT not in message, (
        "an unreachable Redis is not an absent key and must not be reported as "
        "one: the first is an infrastructure page, the second is a writer that "
        "has not landed a sweep. Collapsing them re-creates the defect one "
        "level up."
    )
    # The original exception must survive as the cause. A refusal that
    # swallowed the ConnectionError would be a smaller version of `except: pass`
    # — better named, still throwing away the only evidence of what happened.
    assert isinstance(exc.value.__cause__, ConnectionError)


def test_an_unparseable_value_refuses_as_unreadable():
    with pytest.raises(RuntimeError) as exc:
        _read(_Redis("{not json at all"))
    assert UNREADABLE in str(exc.value)
    assert exc.value.__cause__ is not None


# ---------------------------------------------------------------------------
# 2. THE CONTROL. The quiet states that must stay quiet.
# ---------------------------------------------------------------------------

def test_a_present_but_empty_curve_is_not_a_refusal():
    """The guard that stops this fix from becoming the next outage.

    A present key holding ``[]`` is not the shape that caused the incident. The
    writer fails closed — it reports ``no_work`` and writes NOTHING on zero rows
    — so an empty list is a written answer, and answering "no bookmaker rows
    this cycle" is exactly what gotcha #53 asks an absence to be distinguished
    FROM. Turning it into a refusal would trade a silent 96K shortfall for a
    hard stop on a legitimate state, and this file would still be green.
    """
    rows, excluded, degraded = _read(_Redis("[]"))
    assert rows == []
    assert excluded == 0
    assert degraded is None


def test_the_happy_path_still_parses_and_still_drops_soccer():
    """The pre-existing behaviour, pinned, because it is what the fix must not
    disturb: the read-side soccer_* exclusion (#1011 / Queue #158).

    The per-bookmaker writer devigs soccer moneyline without a draw term, so its
    soccer buckets dominate the by_category lines with ~40K draw-inflated
    outcomes. They are dropped here, read-side, and COUNTED — the count is
    published, so losing it would silently change a number on the page.
    """
    payload = json.dumps(
        [
            {"category": "basketball_nba", "bucket_idx": 5, "n": 100},
            {"category": "soccer_epl", "bucket_idx": 5, "n": 40},
            {"category": "soccer_uefa_champs_league", "bucket_idx": 6, "n": 2},
            {"category": "icehockey_nhl", "bucket_idx": 7, "n": 7},
        ]
    )
    rows, excluded, degraded = _read(_Redis(payload))

    assert degraded is None
    assert [r.category for r in rows] == ["basketball_nba", "icehockey_nhl"]
    assert excluded == 42, (
        "both soccer buckets must be counted into the published `excluded` "
        "total, not merely dropped"
    )
    # Attribute access, not dict access: the rows are concatenated with ORM-ish
    # rows in `all_rows` and every downstream reader uses attributes.
    assert rows[0].n == 100 and rows[0].bucket_idx == 5


def test_a_row_with_a_null_n_does_not_break_the_exclusion_count():
    rows, excluded, degraded = _read(
        _Redis(json.dumps([{"category": "soccer_epl", "n": None}]))
    )
    assert rows == [] and excluded == 0 and degraded is None


# ---------------------------------------------------------------------------
# 2b. THE SERVE PATH. `refuse=False` — and this section exists because the
#     first cut of D21 did not have it and 500'd the public endpoint.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rc,reason",
    [
        (_Redis(None), ABSENT),
        (_Redis(""), ABSENT),
        (_Redis(raises=True), UNREADABLE),
        (_Redis("{not json"), UNREADABLE),
    ],
)
def test_the_serve_path_degrades_instead_of_raising(rc, reason):
    """`/api/calibration`'s cold-cache fallback must not 500 on a dead Redis.

    THE DEFECT THIS PINS IS ONE THIS FIX INTRODUCED AND THE SUITE CAUGHT.
    `compute_calibration_payload` has two callers — the scheduled producer and
    the route's in-request fallback — and the first cut refused for both. That
    turned "Redis is unreachable" into a 500 on the public endpoint, on the very
    path that exists BECAUSE Redis is unreachable. 95 failures on the first full
    calibration run, 55 of them in `test_route_calibration.py`.

    The producer is the only caller that can PUBLISH a short candidate, so it is
    the only one for which short is a correctness question.
    """
    rows, excluded, degraded = _read(rc, refuse=False)
    assert rows == [] and excluded == 0
    assert degraded == reason, (
        "a degraded serve must still NAME what went wrong — a silent [] here is "
        "the original defect with a different caller"
    )


def test_the_producer_and_the_serve_path_disagree_on_purpose():
    """The two paths must not be collapsible into one behaviour.

    Written as one assertion over both so that a future simplification which
    makes them agree — in either direction — fails here with the reason,
    rather than passing whichever half of the suite it did not break.
    """
    with pytest.raises(RuntimeError):
        _read(_Redis(None), refuse=True)

    rows, _, degraded = _read(_Redis(None), refuse=False)
    assert rows == [] and degraded == ABSENT


def test_refuse_is_keyword_only_and_has_no_default():
    """No default, on purpose: a new call site must CHOOSE.

    A default of True silently makes the next caller a publisher; a default of
    False silently makes the next producer publish short. Both are the defect
    this file is about, so the signature refuses to guess.
    """
    import inspect

    sig = inspect.signature(pc.read_bookmaker_curve_rows)
    refuse = sig.parameters["refuse"]
    assert refuse.kind is inspect.Parameter.KEYWORD_ONLY
    assert refuse.default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# 3. The two ways this fix could rot: the old path coming back, and the key
#    drifting away from its writer.
# ---------------------------------------------------------------------------

_SOURCE = Path(pc.__file__).read_text()


def test_the_silent_path_is_gone_from_the_call_site():
    """Read from the source, because the defect WAS a source shape.

    A behavioural test cannot see this: `except: pass` around a call that no
    longer raises is invisible at runtime and would re-swallow the refusal the
    moment the reader started raising again for a new reason.
    """
    call_site = _SOURCE.split("Query 5: Per-bookmaker calibration", 1)
    assert len(call_site) == 2, (
        "PREMISE GONE: the Phase 3 call site is no longer findable by its "
        "heading. Re-aim this guard; do not delete it."
    )
    body = call_site[1].split("Query 6:", 1)[0]

    assert "read_bookmaker_curve_rows(" in body, (
        "Phase 3 no longer routes through the named reader, so the refusal is "
        "unreachable from the build that needs it"
    )
    assert not re.search(r"except\s+Exception\s*:\s*\n\s*pass", body), (
        "the bare `except Exception: pass` is back at the call site. That line "
        "is what a 23-hour silent publish outage looked like from the inside; "
        "if a swallow is genuinely wanted here it needs a reason in writing "
        "and a name, not a pass."
    )


def test_the_reader_and_the_writer_name_the_same_key():
    """The one string both halves must agree on, checked against the writer.

    The reader now has a constant and the writer still has a literal. That
    asymmetry is deliberate — the freeze exception is for the reader — so the
    drift it permits is pinned here instead. A key that agreed with nothing
    would produce exactly the outage this fix reports on, with the fix's own
    refusal message pointing at the wrong writer.
    """
    writer = (
        Path(pc.__file__).parent / "backfill_winners.py"
    ).read_text()
    assert pc.BOOKMAKER_CURVE_REDIS_KEY == KEY
    assert f'"{KEY}"' in writer, (
        "the writer no longer names this key. Either the key moved and the "
        "reader's constant must move with it, or the writer is gone and this "
        "reader is refusing on behalf of nobody."
    )
