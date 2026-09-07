"""D55 / #2879 — a StatPal id is only an id INSIDE ITS SPORT.

The defect these tests exist for was latent, not live, and that is the whole
reason they are written as a property rather than as a specimen. Before D55,
`statpal_anchor_key` chose its namespace by counting digits:

    ^\\d{6}$  -> "s6"      (observed on MLB, 91 live production anchors)
    ^\\d{10}$ -> "s10"
    anything else -> None, i.e. NOT ANCHORABLE

Nothing was corrupted by that, because only one sport had ever been written.
It gave three different wrong answers the moment a second sport arrived:

  * NFL `contestid` is 6 digits (`280445`-`280772`, 374 measured 2026-09-03) and
    would have been filed as `s6:` — MLB's space — under a unique key,
    `(source, source_id, id_kind)`, that spans every sport in the table.
  * Tennis fixture ids are 7 digits (`2629673`) and matched neither regex, so
    tennis resolved to `None` and was not anchorable at all. That failure is
    silent by construction: the shadow-stamping task would report a clean run
    having stamped nothing.
  * NBA/NHL were unmeasured, which is the same problem in a different costume.

So the guard below is deliberately NOT "a 6-digit NFL id differs from a 6-digit
MLB id". Stated that way it is a fact about two examples, and the next provider
walks straight past it. Stated as **no two sports can produce the same
`source_id` from the same fixture id**, it is a fact about the key function, and
it fails for any future rule that ignores the sport — including a cleverer digit
rule, a range check, or a hash.

Each test names the control arm it would pass vacuously without.
"""

from __future__ import annotations

import logging

import pytest

from app.services.anchor_channel import anchor_key_for_claim
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    SOURCE_STATPAL,
    STATPAL_NS_SHORT,
    STATPAL_QUALIFIER_ABSENT,
    STATPAL_QUALIFIER_BLANK,
    STATPAL_QUALIFIER_SEPARATOR,
    statpal_anchor_key,
    statpal_bare_fixture_id,
    statpal_namespace,
    statpal_qualifier_refusal,
    statpal_sport_from_source_id,
)
from app.utils.sport_keys import SPORT_LEAGUE_MAP

#: One fixture id, deliberately 6-digit, because 6 digits is the length at which
#: the pre-D55 rule collapsed NFL onto MLB. A shape the old rule *recognised* is
#: the hard case; a shape it refused would make the test pass for the wrong
#: reason.
SHARED_SIX_DIGIT_ID = "280445"  # a real NFL contestid, measured 2026-09-03

#: Measured on `tennis/daily/d1`, 2026-09-03. Seven digits: the pre-D55 rule
#: returned `None` for this and tennis was therefore unanchorable.
TENNIS_FIXTURE_ID = "2629673"

#: A real production MLB id from the 91 live `s6:` anchors (354453-364938).
MLB_FIXTURE_ID = "354453"


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


def test_no_two_sports_can_produce_the_same_statpal_source_id():
    """The property, over the whole sport-key vocabulary, from ONE fixture id.

    29 sports in, 29 distinct `source_id`s out. Any rule that derives the
    namespace from the id rather than from the sport gives 1, whatever else it
    is doing — which is what the control arm below asserts, so this test is not
    quietly passing on an empty set.
    """
    sports = sorted(SPORT_LEAGUE_MAP)
    assert len(sports) > 5, "vocabulary too small for this to prove anything"

    keys = {
        statpal_anchor_key(SHARED_SIX_DIGIT_ID, sport_key=s).source_id
        for s in sports
    }
    assert len(keys) == len(sports)


def test_control_the_pre_d55_rule_fails_the_invariant_above():
    """The arm that proves the test above can fail.

    Until step 3 this exercised the real legacy branch, because it was still
    reachable by passing no sport. The branch is gone, so the old rule is
    reconstructed here from the one piece of it that legitimately survives —
    `statpal_namespace`, which still answers the *comparison* question
    `compare_statpal_ids` asks — and shown to collapse.

    Reconstructing it is not a weaker test than exercising it was. The invariant
    above is a claim about a whole class of rules, not about one deleted
    function, and a control arm that can only be written by keeping the defect
    alive is a reason to keep the defect alive.
    """
    sports = sorted(SPORT_LEAGUE_MAP)
    digit_derived = {
        f"{statpal_namespace(SHARED_SIX_DIGIT_ID)}:{SHARED_SIX_DIGIT_ID}"
        for _ in sports
    }
    assert digit_derived == {f"{STATPAL_NS_SHORT}:{SHARED_SIX_DIGIT_ID}"}
    assert len(digit_derived) == 1 < len(sports)


def test_the_nfl_and_mlb_specimens_that_forced_the_ruling():
    """The concrete case, kept as documentation of the live risk.

    NFL `280445` and MLB `354453` do not collide on their digits today — the
    ranges do not overlap — so this is not a demonstration of a live corruption.
    It is a demonstration that the KEY no longer depends on that accident.
    """
    nfl = statpal_anchor_key(SHARED_SIX_DIGIT_ID, sport_key="americanfootball_nfl")
    mlb_same_digits = statpal_anchor_key(
        SHARED_SIX_DIGIT_ID, sport_key="baseball_mlb"
    )

    assert nfl.source == mlb_same_digits.source == SOURCE_STATPAL
    assert nfl.id_kind == mlb_same_digits.id_kind == ANCHOR_KIND_GAME
    assert nfl.source_id == "americanfootball_nfl:280445"
    assert mlb_same_digits.source_id == "baseball_mlb:280445"
    assert nfl.source_id != mlb_same_digits.source_id

    # And the pre-D55 rule could not tell them apart at all.
    assert statpal_namespace(SHARED_SIX_DIGIT_ID) == statpal_namespace(
        MLB_FIXTURE_ID
    )


def test_a_seven_digit_tennis_fixture_is_anchorable_once_the_sport_is_known():
    """The silent half of #2879: not a wrong anchor, NO anchor.

    Step 4 of the AUTHORITY program could have been built, tested, deployed and
    stamped nothing, because `None` here means "write nothing" and nothing about
    that is loud.
    """
    # `None` unqualified — under the old rule because seven digits matched
    # neither regex, and now because an unqualified call is refused outright.
    # Same answer, and after step 3 it is the answer for EVERY id shape rather
    # than only for the shapes the digit rule happened not to recognise.
    assert statpal_anchor_key(TENNIS_FIXTURE_ID) is None

    key = statpal_anchor_key(TENNIS_FIXTURE_ID, sport_key="tennis_atp")
    assert key is not None
    assert key.source_id == f"tennis_atp:{TENNIS_FIXTURE_ID}"
    assert key.id_kind == ANCHOR_KIND_GAME
    assert key.may_anchor_absorption is True


# ---------------------------------------------------------------------------
# Refusals — every one of them narrows what may anchor, never widens it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_id", [None, "", "   "])
def test_an_absent_fixture_id_refuses_even_with_a_sport(fixture_id):
    assert statpal_anchor_key(fixture_id, sport_key="baseball_mlb") is None


@pytest.mark.parametrize("sport_key", [None, "", "   ", "tennis:atp", "a:b:c"])
def test_an_unusable_sport_qualifier_refuses_rather_than_emitting_an_ambiguous_key(
    sport_key,
):
    """Every qualifier we cannot use gets the same answer: no key.

    A qualifier containing the separator produces a key that cannot be split
    back apart, and `anchor_is_current` re-derives the sport by splitting it, so
    it would be a key whose own reader misreads it. The blank cases and `None`
    refuse for the plainer reason that there is nothing to qualify with.

    `None` joined this list at step 3, and its arrival is the whole ruling.
    While the bridge existed the three had to be told apart — `None` meant
    "caller not updated yet" and had a digit rule to fall back on, so collapsing
    it into the others would have darkened the channel. With the bridge gone
    there is nothing to fall back to and the distinction has no content left:
    all three are a caller that cannot name the sport, and D55 says such a call
    writes nothing rather than guessing.
    """
    assert statpal_anchor_key(MLB_FIXTURE_ID, sport_key=sport_key) is None


def test_no_id_shape_whatsoever_can_produce_a_key_without_a_sport():
    """The direct anti-regression on step 3, stated over shapes rather than one
    specimen.

    The deleted branch keyed exactly two shapes — 6 digits and 10 — and refused
    everything else. So a test that only checked the tennis id would have passed
    against the *un*-deleted branch, and a test that only checked `354453` would
    not notice a rule that kept `s10`. Both live shapes, both dead shapes and the
    boundary lengths either side of them are asserted together, which is what
    makes this a claim about the rule and not about a value.
    """
    shapes = [
        MLB_FIXTURE_ID,  # 6 digits — was `s6`, the one with 94 live rows
        SHARED_SIX_DIGIT_ID,  # 6 digits — the NFL contestid that forced this
        "1329190539",  # 10 digits — was `s10`
        TENNIS_FIXTURE_ID,  # 7 digits — was refused, for the wrong reason
        "35445",  # 5
        "3544531",  # 7
        "132919053",  # 9
        "13291905390",  # 11
    ]
    for fixture_id in shapes:
        assert statpal_anchor_key(fixture_id) is None, (
            f"{fixture_id!r} produced an anchor key with no sport — the "
            f"digit-derived namespace is back"
        )
        # Non-vacuity: the same id IS anchorable the moment a sport is named,
        # so the refusals above are the missing qualifier and not a broken
        # function that refuses everything.
        assert (
            statpal_anchor_key(fixture_id, sport_key="baseball_mlb").source_id
            == f"baseball_mlb:{fixture_id}"
        )


def test_the_key_module_no_longer_exports_a_way_to_derive_a_legacy_key():
    """`statpal_legacy_source_id` was the last function that turned a fixture id
    into a digit-derived namespace. It is deleted rather than left unused,
    because a dead function is a live one for whoever wires it back up — and the
    grep that finds it is this test, in the file that explains why.

    `statpal_namespace` deliberately survives: it answers a different question
    (are these two raw column values from the same space?) for
    `compare_statpal_ids`, and the module docstring says so.
    """
    import app.utils.provider_anchor_keys as keys

    assert not hasattr(keys, "statpal_legacy_source_id")
    assert hasattr(keys, "statpal_namespace")  # the control arm


def test_every_qualified_key_still_fits_the_column():
    """`source_id` is `VARCHAR(200)`. The longest sport key plus the longest
    fixture id measured must not silently truncate."""
    longest_sport = max(SPORT_LEAGUE_MAP, key=len)
    key = statpal_anchor_key("13291234567890", sport_key=longest_sport)
    assert len(key.source_id) <= 200
    assert key.source_id == key.source_id.strip()


# ---------------------------------------------------------------------------
# Reading a key back — and what a resurrected legacy row is read as
# ---------------------------------------------------------------------------


def test_a_qualified_key_reads_back_as_its_own_sport_and_bare_id():
    """`anchor_is_current` re-derives a key by splitting a stored `source_id`
    into these two halves, so if either read drifts, every live StatPal anchor
    reads as stale and the channel invalidates itself."""
    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    assert statpal_sport_from_source_id(key.source_id) == "baseball_mlb"
    assert statpal_bare_fixture_id(key.source_id) == MLB_FIXTURE_ID


@pytest.mark.parametrize("legacy_source_id", ["s6:354453", "s10:1329190539"])
def test_a_resurrected_legacy_row_names_no_sport_rather_than_a_sport_called_s6(
    legacy_source_id,
):
    """Production holds zero legacy rows after the re-key, which is exactly why
    this has to be pinned rather than dropped.

    The rows are not unreachable — the re-key's own `--rollback` puts all 94
    back, verbatim, and that restore is D51's condition for having applied it
    unattended. So the reader must keep an opinion about the shape after the
    writer stopped producing it, and the opinion must be `None`: refusing to
    name a sport costs an anchor, whereas answering `"s6"` corroborates the row
    against a sport that does not exist and lets a stale anchor read as current.

    The bare id still parses out, because the rollback path and any audit of the
    backup table need to know which fixture a restored row is about.
    """
    assert statpal_sport_from_source_id(legacy_source_id) is None
    assert statpal_bare_fixture_id(legacy_source_id) == legacy_source_id.split(":")[1]


def test_the_legacy_prefixes_the_reader_defends_against_are_the_ones_that_existed():
    """The reader's defence and the shapes the writer used to emit must name the
    same two things. A third prefix added to one and not the other is either a
    row nobody defends against or a defence against nothing."""
    from app.utils.provider_anchor_keys import (
        STATPAL_LEGACY_SOURCE_ID_PREFIXES,
        STATPAL_NS_LONG,
    )

    assert set(STATPAL_LEGACY_SOURCE_ID_PREFIXES) == {
        f"{STATPAL_NS_SHORT}:",
        f"{STATPAL_NS_LONG}:",
    }
    for prefix in STATPAL_LEGACY_SOURCE_ID_PREFIXES:
        assert statpal_sport_from_source_id(f"{prefix}999999") is None


# ---------------------------------------------------------------------------
# The transition READ, executed rather than described
# ---------------------------------------------------------------------------


def _anchor_fixture_db():
    """A two-table stand-in carrying both key shapes for ONE fixture.

    sqlite, not a mock: the thing under test is a SQL statement, and a mock that
    returns whatever the test tells it to proves the test, not the statement.
    The predicate is portable, so the same text that runs on production runs
    here.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, sport_id INT)")
    conn.execute(
        "CREATE TABLE event_provider_anchors "
        "(event_id INT, source TEXT, source_id TEXT, id_kind TEXT)"
    )
    conn.executemany("INSERT INTO events VALUES (?,?)", [(10, 3), (11, 3)])
    return conn


def _params(key_source_id: str) -> dict:
    return {
        "source": SOURCE_STATPAL,
        "id_kind": ANCHOR_KIND_GAME,
        "source_id": key_source_id,
    }


def test_the_qualified_key_still_resolves_its_own_row():
    """Non-vacuity for everything below: the single-predicate read works.

    Every test in this section that asserts a MISS is worthless without this
    one, because a statement that resolves nothing passes them all.
    """
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    conn = _anchor_fixture_db()
    conn.execute(
        "INSERT INTO event_provider_anchors "
        "VALUES (10,'statpal','baseball_mlb:354453','game')"
    )

    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    row = conn.execute(_FIND_BY_ANCHOR_SQL, _params(key.source_id)).fetchone()
    assert row == (10, 3)


def test_the_read_no_longer_reaches_a_legacy_row_from_a_qualified_key():
    """Step 3's read half, executed against the live statement.

    This is the assertion that would have been catastrophic to make one day
    earlier and is correct today, and the difference is entirely the data: 94
    legacy rows on 2026-09-05, zero after the re-key. So the test is written to
    fail loudly if the OR ever comes back — not because the OR was wrong, but
    because it was right only while its rows existed, and a transition read left
    standing is a second lookup path nobody is maintaining.
    """
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    conn = _anchor_fixture_db()
    conn.execute(
        "INSERT INTO event_provider_anchors VALUES (10,'statpal','s6:354453','game')"
    )

    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    assert conn.execute(_FIND_BY_ANCHOR_SQL, _params(key.source_id)).fetchone() is None

    # The statement text itself, so a reintroduced OR fails here even if some
    # future fixture happens not to exercise it.
    assert "legacy_source_id" not in _FIND_BY_ANCHOR_SQL
    assert " OR " not in _FIND_BY_ANCHOR_SQL


def test_the_read_binds_exactly_three_parameters_and_no_orphan_placeholder():
    """A removed predicate that leaves its bind name behind is the failure mode
    this catches: SQLAlchemy raises on an unbound `:legacy_source_id` only when
    the statement is executed, so an untested path would carry it to production.
    Asserted by executing with precisely the parameter set the caller passes.
    """
    import re as _re

    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    bound = set(_re.findall(r":(\w+)", _FIND_BY_ANCHOR_SQL))
    assert bound == {"source", "source_id", "id_kind"}

    conn = _anchor_fixture_db()
    conn.execute(_FIND_BY_ANCHOR_SQL, _params("baseball_mlb:354453"))


def test_the_read_cannot_widen_a_non_statpal_lookup():
    """A legacy-shaped row under another provider must not answer for it.

    Kept from the two-shape era with its specimen intact: `s6:401816587` is the
    row a widened predicate would find, so the test still has something to fail
    against rather than passing because the widening is gone.
    """
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL
    from app.utils.provider_anchor_keys import SOURCE_ESPN, espn_anchor_key

    conn = _anchor_fixture_db()
    conn.executemany(
        "INSERT INTO event_provider_anchors VALUES (?,?,?,?)",
        [
            (10, "espn", "401816587", "game"),
            (11, "espn", "s6:401816587", "game"),  # the shape a widening would find
        ],
    )

    key = espn_anchor_key("401816587")
    row = conn.execute(
        _FIND_BY_ANCHOR_SQL,
        {
            "source": SOURCE_ESPN,
            "id_kind": ANCHOR_KIND_GAME,
            "source_id": key.source_id,
        },
    ).fetchone()
    assert row == (10, 3)


# ---------------------------------------------------------------------------
# The refusal is loud
# ---------------------------------------------------------------------------


def test_an_unqualified_statpal_claim_writes_no_anchor_and_says_so(caplog):
    """D55's second clause: a key we cannot form raises or tags, never no-ops.

    Before step 3 this line was a deprecation countdown on a call that still got
    an answer. Now it marks a claim that got NO anchor — a hole in the channel,
    which is the `NO_ANCHOR_CHANNEL` state ruling 048's amendment says must
    never be papered over. It got more serious, so it must not get quieter, and
    both halves are asserted: the refusal AND the record of it.
    """
    with caplog.at_level(logging.WARNING, logger="app.services.anchor_channel"):
        key = anchor_key_for_claim("statpal", MLB_FIXTURE_ID)

    assert key is None, "an unqualified StatPal claim must not produce an anchor"
    messages = [r.getMessage() for r in caplog.records]
    assert any("D55" in m for m in messages), (
        "a refused anchor claim must be observable in production logs"
    )
    assert any("REFUSED" in m for m in messages), (
        "the log must say the claim was refused, not that it fell back — the "
        "fallback it used to describe no longer exists"
    )


def test_a_qualified_claim_does_not_warn():
    """The control arm: a warning that fires on the good path is a warning
    everyone learns to ignore, and then nobody sees the real one."""
    import logging as _logging

    records: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record):  # pragma: no cover - trivial
            records.append(record)

    logger = _logging.getLogger("app.services.anchor_channel")
    handler = _Capture(level=_logging.WARNING)
    logger.addHandler(handler)
    try:
        key = anchor_key_for_claim(
            "statpal", MLB_FIXTURE_ID, sport_key="baseball_mlb"
        )
    finally:
        logger.removeHandler(handler)

    assert key.source_id == f"baseball_mlb:{MLB_FIXTURE_ID}"
    assert not [r for r in records if "D55" in r.getMessage()]


def test_a_re_derivation_of_an_existing_key_does_not_warn():
    """`anchor_is_current` and `invalidate_scalar_anchor` re-derive a key from
    one already written rather than claiming. They legitimately have no sport to
    pass for an unrecognised key, and a WARNING on a corroboration would report
    a refusal nobody asked for. Off for corroborations, on for claims, because
    only a claim is a write that did not happen."""
    import logging as _logging

    records: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record):  # pragma: no cover - trivial
            records.append(record)

    logger = _logging.getLogger("app.services.anchor_channel")
    handler = _Capture(level=_logging.WARNING)
    logger.addHandler(handler)
    try:
        anchor_key_for_claim("statpal", MLB_FIXTURE_ID, warn_unqualified=False)
    finally:
        logger.removeHandler(handler)

    assert not [r for r in records if "D55" in r.getMessage()]


# ---------------------------------------------------------------------------
# The refusal is loud for EVERY unusable qualifier, not just an absent one
# (`STATPAL-BLANK-QUALIFIER-REFUSAL-TELEMETRY`, follow-up from CERT-2133)
# ---------------------------------------------------------------------------

#: The qualifiers `statpal_anchor_key` refuses. Shared by the refusal test and
#: the telemetry test BY REFERENCE and not by copy, because the defect being
#: guarded is precisely the two lists disagreeing: before this fix the key
#: module refused all five and the channel warned about exactly one.
UNUSABLE_QUALIFIERS = [None, "", "   ", "tennis:atp", "a:b:c"]


@pytest.mark.parametrize("sport_key", UNUSABLE_QUALIFIERS)
def test_every_refused_qualifier_is_also_reported_not_just_the_absent_one(
    sport_key, caplog
):
    """The property: refusing and reporting are the SAME set.

    This is the live half of the follow-up. `sport_key=None` was warned about
    and `sport_key=""` was not, though the key module has always refused both
    identically — so an empty sport column produced a claim that wrote no anchor
    and said nothing, which is the `NO_ANCHOR_CHANNEL` state ruling 048's
    amendment says must never be papered over. From the operator's side a
    silently refused claim is indistinguishable from a sport that simply had no
    fixture that day, and the second one is fine.

    Stated over the refusal list rather than over `""` alone, so it also fails
    for any FUTURE qualifier rule that starts refusing a sixth shape without
    teaching the channel to say so.

    Control arm: `test_a_qualified_claim_does_not_warn` — without it this would
    pass for a channel that warned unconditionally, which is the same defect
    upside down (a warning on the good path is a warning nobody reads).
    """
    with caplog.at_level(logging.WARNING, logger="app.services.anchor_channel"):
        key = anchor_key_for_claim("statpal", MLB_FIXTURE_ID, sport_key=sport_key)

    assert key is None, f"{sport_key!r} must not produce an anchor"
    messages = [r.getMessage() for r in caplog.records]
    assert any("D55" in m and "REFUSED" in m for m in messages), (
        f"a StatPal claim refused for qualifier {sport_key!r} was not reported — "
        f"the channel is silently dropping anchors"
    )


@pytest.mark.parametrize(
    "sport_key,expected",
    [
        (None, STATPAL_QUALIFIER_ABSENT),
        ("", STATPAL_QUALIFIER_BLANK),
        ("   ", STATPAL_QUALIFIER_BLANK),
        ("tennis:atp", STATPAL_QUALIFIER_SEPARATOR),
        ("a:b:c", STATPAL_QUALIFIER_SEPARATOR),
    ],
)
def test_the_report_says_which_of_the_three_refusals_it_was(
    sport_key, expected, caplog
):
    """Three causes, three fixes — so one undifferentiated line is not enough.

    An absent qualifier is a caller that was never updated. A blank one is a
    caller that WAS updated and is reading an empty column, which is a data bug
    somewhere upstream of here. A separator-bearing one is a caller building the
    qualifier by hand out of something that is not a bare `sports.key`. An
    operator who only knows "refused" has to go and find out which; the log line
    already knows.

    Control arm: the `expected` column is asserted against a distinct token per
    cause, so a message that hard-coded one word would fail four of five rows.
    """
    assert statpal_qualifier_refusal(sport_key) == expected

    with caplog.at_level(logging.WARNING, logger="app.services.anchor_channel"):
        anchor_key_for_claim("statpal", MLB_FIXTURE_ID, sport_key=sport_key)

    messages = [r.getMessage() for r in caplog.records if "D55" in r.getMessage()]
    assert messages, "no refusal was reported at all"
    assert any(expected in m for m in messages), (
        f"the refusal of {sport_key!r} was reported but did not name its cause "
        f"{expected!r}: {messages!r}"
    )


def test_the_rule_and_the_reason_are_one_reading_not_two():
    """`statpal_qualifier_refusal` is what `statpal_anchor_key` DECIDES on.

    The cheap version of this fix re-tests the three conditions inside
    `anchor_channel` to build the message. That version is correct on the day it
    ships and becomes a liar the first time the rule moves, because a log line is
    the one caller nobody re-reads. So the guard is not "both agree today" on a
    fixed list — it is that a refusal reason exists for exactly the qualifiers
    that produce no key, checked over usable and unusable alike.

    Control arm: the usable half. Without it a `statpal_qualifier_refusal` that
    returned a reason for EVERYTHING would satisfy the unusable half completely.
    """
    for sport_key in UNUSABLE_QUALIFIERS:
        assert statpal_qualifier_refusal(sport_key) is not None
        assert statpal_anchor_key(MLB_FIXTURE_ID, sport_key=sport_key) is None

    for sport_key in ["baseball_mlb", "americanfootball_nfl", "tennis_atp", " mlb "]:
        assert statpal_qualifier_refusal(sport_key) is None, (
            f"{sport_key!r} is usable but was given a refusal reason"
        )
        assert statpal_anchor_key(MLB_FIXTURE_ID, sport_key=sport_key) is not None


def test_a_claim_carrying_no_statpal_id_at_all_stays_quiet():
    """The common path must not become noisy.

    Most events have no StatPal fixture id, and a claim for one is not a hole in
    the channel — there is nothing to anchor. Widening the warning from "absent
    qualifier" to "any refusal" must not accidentally widen it to "every event we
    have no StatPal id for", which would bury the real line under thousands.

    This is the control arm that makes the two tests above meaningful rather than
    satisfied by an unconditional `logger.warning`.
    """
    import logging as _logging

    records: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record):  # pragma: no cover - trivial
            records.append(record)

    logger = _logging.getLogger("app.services.anchor_channel")
    handler = _Capture(level=_logging.WARNING)
    logger.addHandler(handler)
    try:
        for source_id in [None, "", "   "]:
            assert anchor_key_for_claim("statpal", source_id) is None
    finally:
        logger.removeHandler(handler)

    assert not [r for r in records if "D55" in r.getMessage()], (
        "a claim with no StatPal id is the ordinary case, not a refused anchor"
    )


# ---------------------------------------------------------------------------
# The re-key script's SQL, coupled to the key module rather than to a memory
# ---------------------------------------------------------------------------


def _rekey_script():
    """The script module itself, not a copy of its text.

    `psycopg2` is imported inside `_connect`, so importing this costs no driver
    and touches no database.
    """
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "rekey_statpal_anchors_2879.py"
    )
    assert path.exists(), f"the re-key script is missing: {path}"
    spec = importlib.util.spec_from_file_location("_rekey_2879", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path.read_text()


def test_the_rekey_script_selects_exactly_the_prefixes_the_key_module_declares():
    """The script's `WHERE source_id LIKE 's6:%'` and the module's
    `STATPAL_LEGACY_SOURCE_ID_PREFIXES` are two statements of one fact. If a
    third legacy prefix is ever added to the module and not to the script, the
    script leaves those rows behind and reports a clean run — the zero-yield
    sweep that reads as a success.

    Asserted against the script's live SQL constants, not against a retyped
    copy of them: a guard that restates the thing it guards passes forever after
    the thing changes.
    """
    from app.utils.provider_anchor_keys import STATPAL_LEGACY_SOURCE_ID_PREFIXES

    module, _ = _rekey_script()
    sql = module.SELECT_LEGACY + module.CREATE_BACKUP

    for prefix in STATPAL_LEGACY_SOURCE_ID_PREFIXES:
        assert f"LIKE '{prefix}%'" in sql, (
            f"the re-key script does not select legacy prefix {prefix!r}"
        )

    # And nothing beyond them, so the sweep cannot widen onto D55 rows.
    import re as _re

    selected = set(_re.findall(r"LIKE '([^']+)%'", sql))
    assert selected == set(STATPAL_LEGACY_SOURCE_ID_PREFIXES)


def test_the_rekey_script_backs_up_before_it_writes_and_ships_its_own_undo():
    """D51's condition for applying a data repair unattended, asserted rather
    than promised in a report."""
    module, src = _rekey_script()

    assert module.BACKUP_TABLE == "event_provider_anchors_backup_2879"
    assert "CREATE TABLE IF NOT EXISTS" in module.CREATE_BACKUP
    assert module.BACKUP_TABLE in module.CREATE_BACKUP
    assert module.BACKUP_TABLE in module.RESTORE
    assert "--rollback" in src

    # The backup must be taken BEFORE the first mutating statement runs, not at
    # the end of the run. A backup written after the change is a copy of the
    # damage.
    assert src.index("cur.execute(CREATE_BACKUP)") < src.index(
        "cur.execute(REKEY_ONE"
    )


def test_the_rekey_script_defaults_to_writing_nothing():
    """A repair whose default is to fire is a repair that fires by typo."""
    _, src = _rekey_script()
    assert '"--apply", action="store_true"' in src
    assert "if not args.apply:" in src


# ---------------------------------------------------------------------------
# Nothing else moved
# ---------------------------------------------------------------------------


def test_the_sport_qualifier_is_ignored_by_every_other_provider():
    """`sport_key` is StatPal's, and passing it must not perturb a provider that
    already has its own ruled key shape — Kalshi's especially, which is
    qualified by sport ALREADY and would be double-qualified by a careless
    edit."""
    from app.utils.provider_anchor_keys import (
        espn_anchor_key,
        kalshi_anchor_key,
        odds_api_anchor_key,
    )

    assert anchor_key_for_claim(
        "espn", "401816587", sport_key="baseball_mlb"
    ) == espn_anchor_key("401816587")
    assert anchor_key_for_claim(
        "odds_api", "abc-def-123", sport_key="baseball_mlb"
    ) == odds_api_anchor_key("abc-def-123")

    ticker = "KXMLBGAME-26APR291840COLCIN"
    assert anchor_key_for_claim(
        "kalshi", ticker, sport_key="americanfootball_nfl"
    ) == kalshi_anchor_key(ticker)


def test_the_three_valued_comparison_still_reads_the_id_shape():
    """D55 removed digit counting from the KEY. It did not remove it from
    `compare_statpal_ids`, which asks a different question — *are these two raw
    `events.statpal_fixture_id` values from the same space?* — that only the
    values can answer, because that column is still an untagged union.

    Pinned here so that deleting the legacy branch later does not take the
    comparison with it by accident."""
    from app.utils.provider_anchor_keys import (
        AGREE,
        CONFLICT,
        INCOMPARABLE,
        compare_statpal_ids,
    )

    assert compare_statpal_ids(MLB_FIXTURE_ID, MLB_FIXTURE_ID) == AGREE
    assert compare_statpal_ids(MLB_FIXTURE_ID, "355999") == CONFLICT
    assert compare_statpal_ids(MLB_FIXTURE_ID, "1329100000") == INCOMPARABLE
    assert compare_statpal_ids(TENNIS_FIXTURE_ID, TENNIS_FIXTURE_ID) == (
        INCOMPARABLE
    ), "a 7-digit id belongs to neither measured space; saying AGREE would guess"
