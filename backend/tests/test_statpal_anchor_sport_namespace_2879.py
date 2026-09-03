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
    statpal_anchor_key,
    statpal_bare_fixture_id,
    statpal_legacy_source_id,
    statpal_namespace,
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
    """The arm that proves the test can fail.

    The legacy branch is still reachable (a caller that passes no sport), so the
    broken behaviour can be exercised directly rather than described. One
    fixture id, every sport, ONE key: that is the collision, demonstrated.
    """
    sports = sorted(SPORT_LEAGUE_MAP)
    legacy_keys = {
        statpal_anchor_key(SHARED_SIX_DIGIT_ID).source_id for _ in sports
    }
    assert legacy_keys == {f"{STATPAL_NS_SHORT}:{SHARED_SIX_DIGIT_ID}"}
    assert len(legacy_keys) == 1 < len(sports)


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
    assert statpal_anchor_key(TENNIS_FIXTURE_ID) is None  # the old answer

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


@pytest.mark.parametrize("sport_key", ["", "   ", "tennis:atp", "a:b:c"])
def test_an_unusable_sport_qualifier_refuses_rather_than_emitting_an_ambiguous_key(
    sport_key,
):
    """A qualifier containing the separator produces a key that cannot be split
    back apart, and `anchor_is_current` re-derives the sport by splitting it.
    Refuse rather than write a key whose own reader will misread it.

    The blank cases refuse too, and that is the distinction worth pinning:
    `sport_key=None` means *this caller has not been updated yet* and takes the
    legacy branch, while a sport_key that is present but empty means the caller
    tried to qualify and had nothing to qualify with. Collapsing the two would
    let a caller with an empty sport field fall silently back onto the digit
    rule — the exact silence D55 removes.
    """
    assert statpal_anchor_key(MLB_FIXTURE_ID, sport_key=sport_key) is None


def test_only_an_absent_sport_key_takes_the_legacy_branch():
    """The other half of the distinction above, asserted directly so that the
    two cannot drift apart."""
    assert (
        statpal_anchor_key(MLB_FIXTURE_ID, sport_key=None).source_id
        == f"{STATPAL_NS_SHORT}:{MLB_FIXTURE_ID}"
    )


def test_every_qualified_key_still_fits_the_column():
    """`source_id` is `VARCHAR(200)`. The longest sport key plus the longest
    fixture id measured must not silently truncate."""
    longest_sport = max(SPORT_LEAGUE_MAP, key=len)
    key = statpal_anchor_key("13291234567890", sport_key=longest_sport)
    assert len(key.source_id) <= 200
    assert key.source_id == key.source_id.strip()


# ---------------------------------------------------------------------------
# The transition: reading a pre-D55 row back
# ---------------------------------------------------------------------------


def test_a_qualified_key_can_name_the_legacy_row_it_replaces():
    """This is what lets the 91 live rows be cleaned up as a separate, unhurried
    step instead of a flag day. Without it there is a window in which the
    channel is dark for MLB — the `NO_ANCHOR_CHANNEL` state ruling 048's
    amendment forbids walking into on purpose."""
    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    assert statpal_legacy_source_id(key) == f"{STATPAL_NS_SHORT}:{MLB_FIXTURE_ID}"
    assert statpal_sport_from_source_id(key.source_id) == "baseball_mlb"
    assert statpal_bare_fixture_id(key.source_id) == MLB_FIXTURE_ID


def test_a_legacy_key_has_no_sport_to_read_back_and_no_further_translation():
    legacy = statpal_anchor_key(MLB_FIXTURE_ID)
    assert statpal_sport_from_source_id(legacy.source_id) is None
    assert statpal_legacy_source_id(legacy) is None  # already legacy
    assert statpal_bare_fixture_id(legacy.source_id) == MLB_FIXTURE_ID


def test_a_tennis_key_has_no_legacy_equivalent_because_it_never_had_one():
    """Seven digits matched neither old regex, so there is no pre-D55 row for a
    tennis fixture to be reconciled against — and the transition read must not
    invent one."""
    key = statpal_anchor_key(TENNIS_FIXTURE_ID, sport_key="tennis_atp")
    assert statpal_legacy_source_id(key) is None


def test_the_translation_refuses_keys_from_other_providers():
    from app.utils.provider_anchor_keys import espn_anchor_key

    assert statpal_legacy_source_id(espn_anchor_key("401816587")) is None
    assert statpal_legacy_source_id(None) is None


# ---------------------------------------------------------------------------
# The transition READ, executed rather than described
# ---------------------------------------------------------------------------


def _anchor_fixture_db():
    """A two-table stand-in carrying both key shapes for ONE fixture.

    sqlite, not a mock: the thing under test is a SQL statement, and a mock that
    returns whatever the test tells it to proves the test, not the statement.
    The predicate, the OR and the ORDER BY are all portable, so the same text
    that runs on production runs here.
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


def _params(key_source_id: str, legacy_source_id: str) -> dict:
    return {
        "source": SOURCE_STATPAL,
        "id_kind": ANCHOR_KIND_GAME,
        "source_id": key_source_id,
        "legacy_source_id": legacy_source_id,
    }


def test_the_step_2_read_finds_a_pre_d55_row_from_the_qualified_key():
    """The window this closes: lane1 starts passing the sport, the caller derives
    `baseball_mlb:354453`, and every live row still says `s6:354453`. Without the
    two-shape predicate the channel is dark for MLB until the re-key runs."""
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    conn = _anchor_fixture_db()
    conn.execute(
        "INSERT INTO event_provider_anchors VALUES (10,'statpal','s6:354453','game')"
    )

    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    row = conn.execute(
        _FIND_BY_ANCHOR_SQL,
        _params(key.source_id, statpal_legacy_source_id(key)),
    ).fetchone()
    assert row == (10, 3)


def test_when_both_shapes_exist_the_d55_key_wins_deterministically():
    """The normal state between lane1's change and the re-key: the writer has
    added a qualified row beside the legacy one. `LIMIT 1` without the ORDER BY
    would answer by plan, and an identity that changes with the plan is not an
    identity."""
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    conn = _anchor_fixture_db()
    conn.executemany(
        "INSERT INTO event_provider_anchors VALUES (?,?,?,?)",
        [
            (10, "statpal", "s6:354453", "game"),
            (11, "statpal", "baseball_mlb:354453", "game"),
        ],
    )

    key = statpal_anchor_key(MLB_FIXTURE_ID, sport_key="baseball_mlb")
    row = conn.execute(
        _FIND_BY_ANCHOR_SQL,
        _params(key.source_id, statpal_legacy_source_id(key)),
    ).fetchone()
    assert row == (11, 3), "the qualified row is the one that must answer"


def test_a_caller_that_has_not_been_updated_still_reads_its_own_legacy_row():
    """Today's production path, unchanged: no sport passed, legacy key derived,
    legacy row found. This is the arm that proves the change is additive."""
    from app.services.anchor_channel import _FIND_BY_ANCHOR_SQL

    conn = _anchor_fixture_db()
    conn.execute(
        "INSERT INTO event_provider_anchors VALUES (10,'statpal','s6:354453','game')"
    )

    key = statpal_anchor_key(MLB_FIXTURE_ID)  # no sport — the pre-D55 caller
    assert statpal_legacy_source_id(key) is None
    row = conn.execute(
        _FIND_BY_ANCHOR_SQL, _params(key.source_id, key.source_id)
    ).fetchone()
    assert row == (10, 3)


def test_the_two_shape_predicate_cannot_widen_a_non_statpal_lookup():
    """For every other provider the caller passes the same value twice and the
    OR collapses to the original equality. Asserted with a row that WOULD match
    a widened predicate, so the test can fail."""
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
    assert statpal_legacy_source_id(key) is None
    row = conn.execute(
        _FIND_BY_ANCHOR_SQL,
        {
            "source": SOURCE_ESPN,
            "id_kind": ANCHOR_KIND_GAME,
            "source_id": key.source_id,
            "legacy_source_id": key.source_id,
        },
    ).fetchone()
    assert row == (10, 3)


# ---------------------------------------------------------------------------
# The countdown on the legacy branch
# ---------------------------------------------------------------------------


def test_an_unqualified_statpal_claim_is_logged_so_the_bridge_cannot_go_quiet(
    caplog,
):
    """The legacy branch is deleted when this log line stops appearing for a
    day. A bridge with no counter is just a permanent fixture nobody noticed."""
    with caplog.at_level(logging.WARNING, logger="app.services.anchor_channel"):
        key = anchor_key_for_claim("statpal", MLB_FIXTURE_ID)

    assert key.source_id == f"{STATPAL_NS_SHORT}:{MLB_FIXTURE_ID}"
    assert any(
        "D55" in r.message or "D55" in r.getMessage() for r in caplog.records
    ), "the unqualified fallback must be observable in production logs"


def test_a_qualified_claim_does_not_warn():
    """The control arm: a warning that fires on the good path is a warning
    everyone learns to ignore, and then the countdown never reaches zero."""
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
    """`anchor_is_current` re-derives a key from one already written. A pre-D55
    row's key is legacy by construction, so there is no sport for it to pass and
    telling it to pass one would make the log say the opposite of the truth."""
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
