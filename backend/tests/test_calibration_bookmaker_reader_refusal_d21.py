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


#: CERT-497. A row shaped like one the WRITER actually emits — every key in
#: ``_precompute_bookmaker_calibration``'s literal (backfill_winners.py, the
#: ``buckets.append({...})`` block), not the three keys a test happens to assert
#: on. Two fixtures in this file used to be 2-3 key dicts, which is how the
#: row-level hole below survived D21: the guards proved the reader's behaviour
#: on payloads its only writer cannot produce.
def _row(category="basketball_nba", *, bucket_idx=5, n=100, winners=40, **over):
    # `avg_prob`/`sum_prob` are DERIVED so a healthy fixture stays internally
    # consistent, but the derivation is guarded: several arms below deliberately
    # pass a non-numeric `n` or `winners` to build a defective row, and the
    # factory must produce that row rather than raise while constructing it.
    try:
        derived_avg = winners / n if n else 0.0
        derived_sum = float(winners)
    except (TypeError, ZeroDivisionError):
        derived_avg, derived_sum = 0.0, 0.0
    row = {
        "bucket_idx": bucket_idx,
        "source": "odds_api_bookmaker",
        "category": category,
        "price_moved": None,
        "n": n,
        "winners": winners,
        "avg_prob": derived_avg,
        "sum_prob": derived_sum,
        "sum_sq_err": 0.5,
    }
    row.update(over)
    return row


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

def test_a_present_but_empty_curve_REFUSES_because_the_writer_cannot_write_one():
    """INVERTED by CERT-485 P1-b. This guard used to assert the opposite.

    Its old docstring argued that ``[]`` "is a written answer" and refusing it
    would be "a hard stop on a legitimate state" — and in the same sentence it
    said the writer "reports ``no_work`` and writes NOTHING on zero rows". Both
    cannot be true. The writer is the tiebreaker and it is unambiguous
    (``backfill_winners.py``, the ``elif not buckets:`` arm): on zero buckets it
    sets ``terminal = "no_work"``, logs, and never reaches the ``setex``. The
    ONLY way to reach ``setex`` is a non-empty ``buckets``.

    So ``[]`` is not a state the writer can produce. It is a corrupt value, and
    under gotcha #53 a corrupt value must be named, not quietly returned as
    "no rows this cycle" — which is precisely the silent 96K shortfall D21
    exists to end, re-entered through a shape nobody checked.

    Inverted rather than deleted, the same way 12-CAL's census guard was: the
    argument that was wrong is worth more standing next to the one that
    replaced it.
    """
    rows, excluded, degraded = _read(_Redis("[]"), refuse=False)
    assert rows == []
    assert excluded == 0
    assert degraded == UNREADABLE


# ---------------------------------------------------------------------------
# 1b. CERT-485 P1-b — VALID JSON OF THE WRONG SHAPE.
#
#     `json.loads` succeeding proves the bytes were JSON. It proves nothing
#     about them being a list of bookmaker rows. Before this fix the reader
#     iterated `raw` and called `row.get` with no check between, so:
#
#       {}     -> iterated zero keys and returned ([], 0, None). SILENT. The
#                 exact 96K shortfall D21 was written to end, re-entered.
#       null   -> TypeError: 'NoneType' object is not iterable
#       [1]    -> AttributeError: 'int' object has no attribute 'get'
#
#     and the two exceptions escaped `refuse=False` as well, so they 500'd the
#     public fallback — the same defect D21's first cut had, one layer in.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,label",
    [
        ("{}", "an object where a list belongs"),
        ("null", "a JSON null"),
        ("[1]", "a list of scalars"),
        ('["a"]', "a list of strings"),
        ('[{"category":"x"},2]', "a list that is only partly rows"),
        ('"a string"', "a bare JSON string"),
        ("3", "a bare number"),
    ],
)
def test_valid_json_of_the_wrong_shape_refuses_by_name(payload, label):
    """Every non-row shape is UNREADABLE, on the producer path."""
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(payload))
    assert UNREADABLE in str(excinfo.value), label


@pytest.mark.parametrize(
    "payload",
    ["{}", "null", "[1]", '["a"]', '[{"category":"x"},2]', '"a string"', "3", "[]"],
)
def test_the_serve_path_never_raises_on_a_wrong_shape(payload):
    """...and the SERVE path degrades instead of raising, for every one of them.

    This is the half that makes P1-b a public-endpoint bug and not just a
    producer one: `null` and `[1]` raised straight through `refuse=False`.
    """
    rows, excluded, degraded = _read(_Redis(payload), refuse=False)
    assert rows == []
    assert excluded == 0
    assert degraded == UNREADABLE


def test_the_wrong_shape_refusal_names_the_key_an_operator_must_look_at():
    """A refusal that does not say WHERE is a refusal an operator cannot act on."""
    _, _, degraded = _read(_Redis("{}"), refuse=False)
    assert degraded == UNREADABLE
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis("{}"))
    assert KEY in str(excinfo.value)


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
            _row("basketball_nba", bucket_idx=5, n=100, winners=40),
            _row("soccer_epl", bucket_idx=5, n=40, winners=18),
            _row("soccer_uefa_champs_league", bucket_idx=6, n=2, winners=1),
            _row("icehockey_nhl", bucket_idx=7, n=7, winners=3),
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


def test_a_row_with_a_null_n_is_now_refused_and_this_assertion_was_INVERTED():
    """🔴 CERT-497. THIS TEST'S EXPECTATION WAS DELIBERATELY REVERSED. Read why.

    It used to assert ``rows == [] and excluded == 0 and degraded is None`` on
    the payload ``[{"category": "soccer_epl", "n": None}]`` — i.e. it PINNED A
    SILENT ZERO as correct. That is the identical shape CERT-497 constructed
    against the shipped head (``[{"category": "soccer_epl"}]``), and it is the
    96K-outcome shortfall D21 was written to end, re-entered one level down.
    The guard was not wrong about the mechanism; it was wrong about the verdict.

    The exclusion count is still robust to a missing ``n`` — the reader's
    ``int(row.get("n") or 0)`` coalesce is untouched — but it is never REACHED
    for this payload any more, because a row whose ``n`` is null did not come
    from the writer. ``slot["n"]`` is an integer counter incremented once per
    outcome, so null is not "a bucket with no rows", it is a corrupt aggregate,
    and gotcha #53 forbids the two sharing an answer. A payload holding one is
    refused whole rather than read past.

    Inverting a green test is the loudest thing this rework does, so it is named
    in the function name and disclosed in the cert block rather than quietly
    edited into agreement with the new code.
    """
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(json.dumps([{"category": "soccer_epl", "n": None}])))
    assert UNREADABLE in str(excinfo.value)

    # And the serve path still degrades instead of raising — the D21 lesson
    # (two callers, one of them unconsidered) applies to this arm too.
    rows, excluded, degraded = _read(
        _Redis(json.dumps([{"category": "soccer_epl", "n": None}])), refuse=False
    )
    assert rows == [] and excluded == 0 and degraded == UNREADABLE, (
        "the public endpoint must report the reason, never 500 and never a "
        "silent zero"
    )


# ---------------------------------------------------------------------------
# 1c. CERT-497 P1 — A LIST OF DICTS IS NOT A LIST OF BOOKMAKER ROWS.
#
#     P1-b proved the CONTAINER and stopped there. The cert then constructed
#     three payloads that clear the container gate and still reproduce both of
#     D21's original failure modes — one silent, two fatal — because the rows
#     go on to be `SimpleNamespace(**row)`d and read as bare attributes.
#
#     The first case is the one that matters most and is the least visible: it
#     does not crash. It returns `([], 0, None)` — a healthy-looking zero with
#     NO reason in the payload, which is the 96K shortfall wearing D21's own
#     clothes.
# ---------------------------------------------------------------------------

#: The three CERT-497 reproductions, verbatim from the finding, plus the value
#: traps that the obvious `isinstance` spelling would wave through.
_ROW_LEVEL_DEFECTS = [
    ([{"category": "soccer_epl"}], "CERT-497 repro: the SILENT zero"),
    ([{}], "CERT-497 repro: crash on r.n, past the refusal boundary"),
    ([{"category": "baseball_mlb", "n": 5}], "CERT-497 repro: crash on r.winners"),
    ([_row(n=True)], "n=true — isinstance(True, int) is True, so this counts 1"),
    ([_row(winners="40")], "winners as a numeric STRING"),
    ([_row(bucket_idx=[5])], "an unhashable bucket_idx poisons the merge key"),
    ([_row(sum_prob=float("nan"))], "NaN propagates to a null avg_prob"),
    ([_row(sum_sq_err=float("inf"))], "inf does the same"),
    ([_row(n=0)], "n=0 contributes nothing but drags the denominator"),
    ([_row(n=10, winners=11)], "winners > n publishes a rate above 100%"),
    ([_row(category=None)], "a null category is not a by_category line"),
    ([_row(price_moved="yes")], "price_moved must stay a bool or null"),
    ([_row(), _row(category="icehockey_nhl", n=7, winners=99)], "the SECOND row"),
    # 🔴 CERT-502 P1. PROVENANCE, not shape. Every row below is COMPLETE and
    # type-correct and would have been admitted with `degraded=None`; `r.source`
    # is part of the merge key, so each one moves bookmaker mass into another
    # source's published curve while leaving the outcome COUNT untouched — which
    # is exactly the shape the population gate cannot see.
    ([_row(source="kalshi")], "CERT-502 repro: contaminates the KALSHI curve"),
    ([_row(source="polymarket")], "CERT-502: any other real source"),
    ([_row(source="odds_api")], "CERT-502: the neighbouring events curve"),
    ([_row(source="")], "CERT-502: an empty source is still a str"),
    ([_row(source="Odds_API_Bookmaker")], "CERT-502: case must match exactly"),
    ([_row(), _row(category="icehockey_nhl", source="kalshi")], "one bad row of two"),
]


@pytest.mark.parametrize(
    "payload,label", _ROW_LEVEL_DEFECTS, ids=[d[1] for d in _ROW_LEVEL_DEFECTS]
)
def test_a_dict_that_is_not_a_bookmaker_row_refuses_by_name(payload, label):
    """The producer refuses — it never crashes and never publishes short."""
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(json.dumps(payload)))
    assert UNREADABLE in str(excinfo.value), label


@pytest.mark.parametrize(
    "payload,label", _ROW_LEVEL_DEFECTS, ids=[d[1] for d in _ROW_LEVEL_DEFECTS]
)
def test_the_serve_path_degrades_on_a_bad_row_instead_of_raising(payload, label):
    """...and the public endpoint reports the reason rather than 500ing.

    This is the half CERT-497 named explicitly: `[{}]` did not merely crash the
    producer, it crashed the cold-cache fallback that exists BECAUSE the fast
    path is unavailable. Both callers, every payload — the D21 lesson applied to
    the row level.
    """
    rows, excluded, degraded = _read(_Redis(json.dumps(payload)), refuse=False)
    assert rows == [], label
    assert excluded == 0, label
    assert degraded == UNREADABLE, label


def test_the_silent_zero_is_specifically_dead():
    """The single most important assertion in this section, stated on its own.

    `[{"category": "soccer_epl"}]` used to return `degraded=None`, and a `None`
    degraded reason is what the payload publishes as "nothing to report". No
    payload that fails to produce rows may ever again report no reason.
    """
    rows, excluded, degraded = _read(
        _Redis(json.dumps([{"category": "soccer_epl"}])), refuse=False
    )
    assert (rows, excluded) == ([], 0)
    assert degraded is not None, (
        "a zero-row read with degraded=None is the silent shortfall D21 exists "
        "to end — it must never be reachable again"
    )


def test_the_row_refusal_tells_an_operator_which_row_and_what_is_wrong():
    """A refusal naming only "bad shape" costs an operator a Redis round-trip."""
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(json.dumps([_row(), _row(category="icehockey_nhl", n=None)])))
    message = str(excinfo.value)
    assert KEY in message
    assert "row 1" in message, "the offending INDEX must be named, not just a count"
    assert "'n'" in message, "the offending KEY must be named"


def test_the_row_refusal_never_echoes_the_rows_themselves():
    """`_shape_of`'s discipline, extended to the row validator.

    This string reaches the logs AND the served payload, and the key holds ~96K
    outcomes' worth of rows. A validator that interpolated the row would turn a
    diagnostic into a log flood on the one path already having a bad day.
    """
    poisoned = _row(category="a-category-nobody-would-name-a-sport", n=None)
    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(json.dumps([poisoned])))
    message = str(excinfo.value)
    assert "a-category-nobody-would-name-a-sport" not in message
    assert "odds_api_bookmaker" not in message.split("source odds_api_bookmaker")[-1], (
        "the only permitted mention of the source is the fixed prose about "
        "which curve is missing"
    )


def test_a_payload_of_sound_rows_is_still_read_whole():
    """THE CONTROL, and the reason this validator is not simply "refuse more".

    A guard that can never go green gets ignored (CAL-P147). Every key the
    writer emits, on rows that differ in every dimension the validator inspects
    — including the legitimately-null `price_moved` and a legitimate zero
    `winners` — must pass untouched.
    """
    payload = json.dumps(
        [
            _row("basketball_nba", bucket_idx=0, n=1, winners=0),
            _row("icehockey_nhl", bucket_idx=9, n=5000, winners=5000),
            _row("baseball_mlb", bucket_idx=4, n=7, winners=3, price_moved=True),
            _row("tennis_atp", bucket_idx=4, n=7, winners=3, price_moved=False),
        ]
    )
    rows, excluded, degraded = _read(_Redis(payload))
    assert degraded is None
    assert len(rows) == 4 and excluded == 0
    assert sum(r.n for r in rows) == 5015


def test_a_wrong_source_row_is_refused_rather_than_merged_under_that_source():
    """🔴 CERT-502 P1, stated on its own because shape and PROVENANCE differ.

    Every other check in this file proves a row is WELL-FORMED. None of them
    proves it came from its only writer — and on the CERT-497 head a complete,
    type-correct row carrying ``source="kalshi"`` was admitted with
    ``degraded=None``, converted, and merged under Kalshi's bucket key.

    The damage is the quiet kind. The outcome COUNT does not change, so the
    population gate that guards this build cannot see it; ~96K outcomes of
    bookmaker mass simply become part of a different source's published
    calibration curve. Nothing refuses, nothing logs, and the page shows a
    number for Kalshi that Kalshi did not earn.
    """
    payload = json.dumps([_row(source="kalshi")])

    rows, excluded, degraded = _read(_Redis(payload), refuse=False)
    assert rows == [], "a wrong-source row must never reach the merge"
    assert degraded == UNREADABLE
    assert excluded == 0

    with pytest.raises(RuntimeError) as excinfo:
        _read(_Redis(payload))
    assert UNREADABLE in str(excinfo.value)
    assert "'source'" in str(excinfo.value), "the operator must be told WHICH key"


def test_the_expected_source_is_the_literal_the_writer_actually_emits():
    """The provenance check is only as good as the value it compares against.

    Pinned against the writer's own bucket literal, read from source, for the
    same reason as the required-key set: a reader asserting a source string the
    writer stopped emitting would refuse every row of a healthy sweep — a
    self-inflicted outage in the code written to prevent one.
    """
    writer = (Path(pc.__file__).parent / "backfill_winners.py").read_text()
    assert pc.BOOKMAKER_CURVE_SOURCE == "odds_api_bookmaker"
    assert f'"source": "{pc.BOOKMAKER_CURVE_SOURCE}"' in writer, (
        "the writer no longer emits this source literal. Either it moved and "
        "the reader's constant must move with it, or the provenance check is "
        "now refusing every healthy row."
    )


def test_an_UNKNOWN_extra_key_is_tolerated_so_the_writer_can_grow_a_column():
    """Required is a floor, not an exact match.

    The writer and this reader ship in one repo but not necessarily in one
    deploy, and a reader that refuses a row for carrying a key it has not been
    taught about would turn every additive change to the writer into an outage.
    """
    rows, _, degraded = _read(_Redis(json.dumps([_row(a_new_column_from_2027=1)])))
    assert degraded is None and len(rows) == 1


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


def test_the_readers_required_keys_are_the_writers_keys():
    """CERT-497. The companion to the key-agreement guard below, one level in.

    The reader now refuses a row that does not carry every key in
    ``_BOOKMAKER_ROW_REQUIRED_KEYS``. That set was DERIVED — from the eight the
    consumer dereferences, all of which the writer emits — but a derivation is
    only true on the day it is done. If the writer renames ``winners``, nothing
    at runtime notices until the 6 h sweep lands and the reader refuses every
    row of a perfectly healthy curve: a self-inflicted outage in the code whose
    entire job is preventing one.

    So the derivation is pinned against the writer's own literal, read from
    source. Equality, not containment, in BOTH directions:

    * a required key the writer does not emit is the outage above;
    * a writer key that is not required and not the one documented exception
      is a NEW field arriving unclassified, and somebody has to decide whether
      the reader should insist on it. Failing here is that decision being asked
      for — it is not a signal to widen the exception list.
    """
    writer = (Path(pc.__file__).parent / "backfill_winners.py").read_text()

    marker = 'stats["data_points"] += slot["n"]'
    head, sep, _ = writer.partition(marker)
    assert sep, (
        "PREMISE GONE: the writer's bucket-assembly loop is no longer findable. "
        "Re-aim this guard; do not delete it."
    )
    block = head.rpartition("buckets.append(")[2]
    assert block, "PREMISE GONE: `buckets.append(` no longer precedes the loop tail."

    writer_keys = set(re.findall(r'"(\w+)":', block))
    assert "n" in writer_keys and "winners" in writer_keys, (
        "PREMISE GONE: the extracted block is not the bucket literal — it does "
        "not even carry `n` and `winners`. Re-aim this guard."
    )

    required = set(pc._BOOKMAKER_ROW_REQUIRED_KEYS)

    #: The one writer key the reader deliberately does NOT require, because the
    #: merge path already reads it as `getattr(r, "price_moved", None)`.
    tolerated = {"price_moved"}

    assert required - writer_keys == set(), (
        "the reader requires key(s) its only writer does not emit — every row "
        "of a healthy sweep would be refused: %s" % sorted(required - writer_keys)
    )
    assert writer_keys - required == tolerated, (
        "the writer's bucket literal has changed shape. Decide whether the new "
        "key(s) belong in `_BOOKMAKER_ROW_REQUIRED_KEYS` (does the consumer "
        "dereference them?) before touching this assertion: %s"
        % sorted(writer_keys - required - tolerated)
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
