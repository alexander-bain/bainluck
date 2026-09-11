"""#4758 — a page-one bundle row stops being wordless.

WHAT A READER SAW. `GET /api/feed?limit=20&event_pct=0.15`, production
2026-09-11 13:45Z, the reader's own page-one request: **4 of the 14 bundle rows
on page one carried `headline=None`, `context_summary=""` AND `reason=""`.** Two
of the three "Fed & Rates" rows and both "Russia-Ukraine" rows. With no sentence
to print, `FuturesCompactRow` fell through to `rowAnswerLabel` and the row read

    How many Fed rate cuts in 2026?                    93%
    0 (0 bps)

— a raw outcome label under a question, on the first screen.

WHY THEY WERE SILENT, MEASURED RATHER THAN GUESSED. Every one of the four has
exactly one caption-eligible signal, `major_surprise`: a huge move against its
opening price (`0 (0 bps)` opened at 10.25% and trades at 92.95%; `Yes` on
`Fed Rate Hike by September 2026 Meeting?` opened at 20.5% and trades at 78%).
The copy for that signal exists, is tested, and is DATED by design — D1 clause
a (#4066) refused to publish "moved 82.7 points from opening" without saying
from WHEN, because an undated lifetime move reads as this morning's news. The
date came from `outcome["opening_captured_at"]`, a key the wire never carried,
so `format_baseline_date` returned `None`, every branch behind it was
unreachable, and the composer fell through to its empty terminal. The four rows
were not missing copy; their copy was gated on a value with no carrier.

WHAT THIS FILE HOLDS. Three properties, each of which is a way the fix could be
wrong rather than absent:

1. **The fold is exact or it is silent.** `opening_baseline_at` is published
   only when the market's outcomes agree on one opening instant. The two ways
   of pretending otherwise were measured and refused (`created_at` dates one
   market in seven wrongly; one outcome's stamp dates the others by a day they
   were not captured on), so a disagreeing market must stay as silent as it is
   today.
2. **Both carriers answer the same.** The value reaches a reader down two
   routes — folded onto a rebuilt snapshot row, or re-derived from hydrated ORM
   outcomes — and a market must not be dated on one path and undated on the
   other. That is the "a DIFFERENT feed, not a cheaper one" failure the
   snapshot module exists to make impossible.
3. **A yes/no card states the AFFIRMATIVE's move.** `compose_binary_card_copy`
   composes against the affirmative's probability and is handed a magnitude
   with no side attached. `Putin out as President of Russia by December 31,
   2026?` trades at `Yes` 6.5% / `No` 93.5%, and `No` is both the biggest mover
   and the row sorted first — so the pre-fix pick would have published "Up 84.0
   points since Jul 6 - now 7% chance", which is exactly backwards. This was
   never served only because the branch was unreachable; making it reachable is
   what puts the sentence one step from a reader.

The specimens below are the production rows, by id and by number.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.routes.feed import _biggest_move_from_opening
from app.utils import futures_market_snapshot as fms
from app.utils.feed_reasons import (
    compose_binary_card_copy,
    generate_futures_context_summary,
    generate_futures_headline,
)

#: The two distinct opening instants carried by the production specimens.
FEB_19 = datetime(2026, 2, 19, 1, 41, 4, 341363, tzinfo=timezone.utc)
APR_29 = datetime(2026, 4, 29, 21, 17, 12, 997392, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 11, 13, 45, tzinfo=timezone.utc)


class _Outcome:
    """An outcome carrying only what the fold reads, positionally faithful.

    Not a `FuturesOutcomeSnapshot`: the fold reads `__dict__` precisely so that
    a projection which stops loading the column degrades to `None` instead of
    lazy-loading, and a double that answers every attribute would hide that.
    """

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


class _Market:
    def __init__(self, outcomes: list[_Outcome], **values: object) -> None:
        self.__dict__.update(values)
        self.__dict__["outcomes"] = outcomes


# --------------------------------------------------------------------------
# 1. the fold is exact or it is silent
# --------------------------------------------------------------------------


def test_a_market_whose_outcomes_share_one_opening_instant_is_dated():
    """The 85% case (26,310 of 30,944 open markets, production 2026-09-11)."""
    market = _Market(
        [
            _Outcome(name="0 (0 bps)", opening_captured_at=FEB_19),
            _Outcome(name="1 (25 bps)", opening_captured_at=FEB_19),
            _Outcome(name="2 (50 bps)", opening_captured_at=FEB_19),
        ]
    )
    assert fms.opening_baseline_stamp(market) == FEB_19


def test_a_market_whose_outcomes_disagree_publishes_no_date_at_all():
    """The 15% case, and the whole reason the rule is unanimity.

    Not "pick the earliest", not "pick the leader's": either would date the
    other outcomes by a day they were not captured on, which is the same defect
    as borrowing `created_at` (one market in seven wrong, up to 214.9 days)
    wearing a different carrier. A market with two answers to "since when?"
    has none.
    """
    market = _Market(
        [
            _Outcome(name="The Odyssey", opening_captured_at=FEB_19),
            _Outcome(name="Dune: Part Three", opening_captured_at=APR_29),
        ]
    )
    assert fms.opening_baseline_stamp(market) is None


def test_an_unstamped_outcome_is_not_a_disagreement():
    """A leg nobody stamped is not evidence that the stamps disagree.

    Production carries 151,664 stamps against 154,434 openings, so the mixed
    market is the ordinary one, not the exception; treating a `NULL` as a
    dissenting vote would silence a market whose stamps are unanimous.
    """
    market = _Market(
        [
            _Outcome(name="Yes", opening_captured_at=APR_29),
            _Outcome(name="No", opening_captured_at=None),
        ]
    )
    assert fms.opening_baseline_stamp(market) == APR_29


def test_a_market_with_no_stamp_anywhere_is_undated_not_defaulted():
    market = _Market([_Outcome(name="Yes"), _Outcome(name="No")])
    assert fms.opening_baseline_stamp(market) is None
    assert fms.opening_baseline_stamp(_Market([])) is None


# --------------------------------------------------------------------------
# 2. both carriers answer the same
# --------------------------------------------------------------------------


def _wire_market(stamp: datetime | None) -> object:
    """One market through the real `to_plain` -> `from_plain` round trip."""
    outcomes = [
        _Outcome(
            id=1,
            name="Yes",
            current_probability=0.78,
            opening_probability=0.205,
            opening_captured_at=stamp,
        ),
        _Outcome(
            id=2,
            name="No",
            current_probability=0.22,
            opening_probability=0.795,
            opening_captured_at=stamp,
        ),
    ]
    market = _Market(outcomes, id=13797610, name="Fed Rate Hike?", sport=None)
    payload = fms.to_plain([market])
    assert fms.is_snapshot_payload(
        payload
    ), "the artifact this fold wrote is unreadable"
    (rebuilt,) = fms.from_plain(payload)
    return rebuilt


@pytest.mark.parametrize("stamp", [APR_29, None])
def test_the_hydrated_market_and_the_rebuilt_one_are_dated_alike(stamp):
    """The failure the snapshot module exists to prevent, for this column.

    A rebuilt market's outcomes do NOT carry `opening_captured_at` — it is
    `OUTCOME_LOAD_ONLY_EXTRA`, loaded and deliberately not on the wire — so if
    the fold were missing, the cached path would report "no market has an
    opening date" while the build path knew it. Both arms, because a fix that
    only ever returns the stamp would pass the `APR_29` arm alone.
    """
    hydrated = _Market(
        [
            _Outcome(name="Yes", opening_captured_at=stamp),
            _Outcome(name="No", opening_captured_at=stamp),
        ]
    )
    assert fms.opening_baseline_stamp(_wire_market(stamp)) == stamp
    assert fms.opening_baseline_stamp(hydrated) == stamp


def test_the_rebuilt_outcomes_do_not_carry_the_stamp_they_were_folded_from():
    """The economics, asserted rather than described.

    The whole reason the fold exists is that one timestamp per OUTCOME costs
    +12% of a size-capped shared artifact (2,928,973 B -> 3,289,739 B over
    6,904 outcomes). If this ever starts passing a stamp per outcome, the fold
    has been quietly replaced by the thing it was the alternative to.
    """
    rebuilt = _wire_market(APR_29)
    assert "opening_baseline_at" in rebuilt.__dict__
    for outcome in rebuilt.__dict__["outcomes"]:
        assert "opening_captured_at" not in outcome.__dict__


def test_the_wire_shape_and_its_version_move_together():
    """A shape change without a version bump is the failure, so pin the PAIR.

    🔴 WRITTEN THIS WAY BECAUSE THE OBVIOUS TEST IS A TAUTOLOGY. The first draft
    built its "predecessor" as `{"v": SNAPSHOT_SCHEMA_VERSION - 1, ...}` and
    asserted it was refused — which stays green when the bump is reverted,
    because the arithmetic follows the constant. Mutation-checked: reverting
    `SNAPSHOT_SCHEMA_VERSION = 4` to `3` left all sixteen tests in this file
    passing.

    A LITERAL on both sides is what closes that. Adding a column without a bump
    fails on the width; bumping without a shape change fails on the version;
    and either failure names the other half, which is the pairing the module's
    own note describes ("the version guards the shape a row CLAIMS, per-row
    arity guards the shape it HAS, and neither is the other's backstop").

    v4 = 29 loaded market columns + 2 derived (`price_polled_at`,
    `opening_baseline_at`), 12 outcome columns, 2 sport columns.
    """
    assert (
        fms.SNAPSHOT_SCHEMA_VERSION,
        len(fms.MARKET_ROW_COLUMNS),
        len(fms.OUTCOME_COLUMNS),
        len(fms.SPORT_COLUMNS),
    ) == (4, 31, 12, 2), (
        "the shared wire changed shape or version. Both must move: an in-flight "
        "entry of the old shape read under the old version tag is a market row "
        "of the wrong width, and `zip` truncates rather than raising."
    )
    assert fms.DERIVED_MARKET_COLUMNS[-1] == "opening_baseline_at", (
        "derived columns are POSITIONAL; inserting one before this changes the "
        "meaning of every value after it while keeping the arity"
    )


def test_every_outcome_column_a_build_time_fold_reads_is_actually_loaded():
    """The fold's silent-death mode, closed by deriving the names, not listing them.

    `_opening_baseline_at` reads `o.__dict__.get("opening_captured_at")` — the
    deliberate idiom, because `getattr` on an unprojected column lazy-loads and
    raises `MissingGreenlet` inside the per-item serializer (gotcha #42). The
    cost of that safety is that dropping the column from the load surface does
    not raise: every outcome reads `None`, the fold publishes no date, and the
    four rows this ship un-silenced go quiet again with every test green.

    CERT-622's projection guard cannot see this one. It derives the READ set
    from the two route bodies by AST, and this read lives in the snapshot
    module behind a string literal rather than an attribute. So the names are
    derived HERE, from the folds' own source, and checked against the load
    surface — a fold that starts reading a third column is covered without
    anyone remembering to add a line.
    """
    import ast
    import inspect

    load_surface = set(fms.OUTCOME_COLUMNS) | set(fms.OUTCOME_LOAD_ONLY_EXTRA)
    for fold in (fms._opening_baseline_at, fms._price_polled_at):
        tree = ast.parse(inspect.getsource(fold))
        read = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        assert read, (
            f"read no column names out of `{fold.__name__}` — this scan is "
            "broken, and a scan that reports nothing for what it cannot parse "
            "is indistinguishable from a clean one"
        )
        missing = read - load_surface
        assert not missing, (
            f"`{fold.__name__}` folds outcome column(s) {sorted(missing)} that "
            "`market_load_options()` does not project. It will not raise — it "
            "will read `None` off every outcome and publish nothing. Add them "
            "to `OUTCOME_LOAD_ONLY_EXTRA`."
        )


def test_a_row_of_the_previous_width_is_refused_rather_than_read_short():
    """An in-flight v3 market row is one value short of a v4 reader.

    Read anyway, `zip` would truncate it and every market would silently carry
    no opening date for the life of that entry — an answer, not a rebuild
    (gotcha #53). Tagged with the CURRENT version, so this is the arity half on
    its own: the row that survives the version check must still be rejected.
    """
    current = fms.to_plain(
        [_Market([_Outcome(name="Yes", opening_captured_at=APR_29)])]
    )
    short = {
        "v": fms.SNAPSHOT_SCHEMA_VERSION,
        "rows": [[row[0][:-1], row[1], row[2]] for row in current["rows"]],
    }
    assert fms.is_snapshot_payload(current)
    assert not fms.is_snapshot_payload(short)
    assert fms.from_plain(short) == []


# --------------------------------------------------------------------------
# 3. the serving read, and the side a yes/no card speaks for
# --------------------------------------------------------------------------

#: `How many Fed rate cuts in 2026?` (market 113032) as page one served it.
FED_CUTS = [
    {"name": "0 (0 bps)", "probability": 0.9295, "opening_probability": 0.1025},
    {"name": "1 (25 bps)", "probability": 0.0495, "opening_probability": 0.165},
    {"name": "2 (50 bps)", "probability": 0.0115, "opening_probability": 0.265},
]

#: `Putin out as President of Russia by December 31, 2026?` (market 51672221),
#: sorted as the serializer sorts it — by probability, so `No` comes first and
#: IS the biggest-mover pick.
PUTIN_OUT = [
    {"name": "No", "probability": 0.935, "opening_probability": 0.095},
    {"name": "Yes", "probability": 0.065, "opening_probability": 0.905},
]


def test_the_serving_read_takes_the_date_off_the_market_not_the_outcome():
    """The regression: the outcome dicts have never carried this key.

    Serve-time outcome dicts are built by hand in `routes/feed.py` from the
    projection, and `opening_captured_at` is not among the keys they build.
    Reading it there again would be an unprojected lazy load inside the
    per-item serializer — `MissingGreenlet`, and a futures pool of zero
    (CERT-622, gotcha #42) — so the date must come off the market row.
    """
    assert all("opening_captured_at" not in o for o in FED_CUTS)

    name, change, opened_at = _biggest_move_from_opening(
        FED_CUTS,
        _Market(
            [_Outcome(name=o["name"], opening_captured_at=FEB_19) for o in FED_CUTS]
        ),
    )
    assert (name, opened_at) == ("0 (0 bps)", FEB_19)
    assert change == pytest.approx(0.827)


def test_a_market_with_no_agreed_opening_still_reports_its_move_undated():
    """The move is a fact; the date is what may be missing.

    `change` must survive so the SCORING signals that read it are untouched —
    only the sentence is gated, and it is gated on `opened_at`.
    """
    _, change, opened_at = _biggest_move_from_opening(
        FED_CUTS,
        _Market(
            [
                _Outcome(name="0 (0 bps)", opening_captured_at=FEB_19),
                _Outcome(name="1 (25 bps)", opening_captured_at=APR_29),
            ]
        ),
    )
    assert change == pytest.approx(0.827)
    assert opened_at is None


def test_a_yes_no_market_reports_the_affirmatives_move_not_the_biggest():
    """The sign, on the specimen that inverts.

    Both sides of `Putin out...` moved 84 points; `No` moved UP and is sorted
    first, so the biggest-mover pick returns +0.84 while the affirmative — the
    side every binary sentence is composed against — moved DOWN 84.
    """
    name, change, _ = _biggest_move_from_opening(
        PUTIN_OUT, _Market([_Outcome(name="Yes", opening_captured_at=FEB_19)])
    )
    assert name == "Yes"
    assert change == pytest.approx(-0.84)


def test_the_binary_card_says_down_for_a_collapsed_affirmative():
    """The reader-facing half of the same fact, through the real composer.

    Fed the biggest mover this reads "Up 84 points since Feb 19 - now 7%
    chance", a sentence whose two halves contradict each other.
    """
    copy = compose_binary_card_copy(
        market_name="Putin out as President of Russia by December 31, 2026?",
        highlight_reasons=["major_surprise"],
        affirmative_probability=0.065,
        rendered_affirmative_percent=7,
        top_surprise_change=-0.84,
        top_surprise_opened_at=FEB_19,
        now=NOW,
    )
    assert copy.headline == "Down 84 points since Feb 19"
    assert copy.context_summary == "Down 84 points since Feb 19 — now 7% chance"


# --------------------------------------------------------------------------
# the ship itself: the four rows get a sentence
# --------------------------------------------------------------------------

#: Each production specimen as `(market name, highlight reasons, leader, kwargs)`
#: — the inputs `routes/feed.py` hands the composers, taken from
#: `/api/admin/discover-quality/trace/{id}` on 2026-09-11.
SILENT_ROWS = [
    pytest.param(
        "How many Fed rate cuts in 2026?",
        ["category_base_economics", "tier_2", "high_volume", "major_surprise"],
        dict(
            leader_name="0 (0 bps)",
            leader_probability=0.9295,
            rendered_leader_percent=93,
            top_surprise_name="0 (0 bps)",
            top_surprise_change=0.827,
        ),
        id="113032-fed-cuts",
    ),
    pytest.param(
        "Fed Rate Hike by September 2026 Meeting?",
        ["category_base_economics", "tier_2", "high_volume", "major_surprise"],
        dict(
            leader_name="Yes",
            leader_probability=0.78,
            rendered_leader_percent=78,
            affirmative_probability=0.78,
            rendered_affirmative_percent=78,
            top_surprise_name="Yes",
            top_surprise_change=0.575,
        ),
        id="13797610-fed-hike",
    ),
    pytest.param(
        "Russia x Ukraine ceasefire agreement by...?",
        ["category_base_geopolitics", "tier_2", "high_volume", "major_surprise"],
        dict(
            leader_name="December 31",
            leader_probability=0.225,
            rendered_leader_percent=23,
            top_surprise_name="October 31",
            top_surprise_change=-0.28,
        ),
        id="20569379-ceasefire",
    ),
    pytest.param(
        "Putin out as President of Russia by December 31, 2026?",
        ["category_base_geopolitics", "tier_2", "fresh", "major_surprise"],
        dict(
            leader_name="No",
            leader_probability=0.935,
            rendered_leader_percent=94,
            affirmative_probability=0.065,
            rendered_affirmative_percent=7,
            top_surprise_name="Yes",
            top_surprise_change=-0.84,
        ),
        id="51672221-putin",
    ),
]


@pytest.mark.parametrize("market_name,reasons,inputs", SILENT_ROWS)
def test_a_row_whose_only_signal_is_a_lifetime_move_gets_a_caption(
    market_name, reasons, inputs
):
    """Undated it says nothing; dated it says something. Both arms.

    The `None` arm is not decoration — it is the production reading, and
    without it a composer that had simply become unconditionally chatty would
    pass the dated arm on its own.
    """
    undated = generate_futures_context_summary(
        headline=generate_futures_headline(
            highlight_reasons=reasons,
            market_name=market_name,
            top_surprise_opened_at=None,
            now=NOW,
            **inputs,
        ),
        highlight_reasons=reasons,
        market_name=market_name,
        top_surprise_opened_at=None,
        now=NOW,
        **{k: v for k, v in inputs.items() if k != "top_surprise_name"},
    )
    assert undated == "", (
        f"{market_name!r} is expected to be silent WITHOUT a baseline — this is "
        "the production reading of 2026-09-11 and the reason this ship exists"
    )

    headline = generate_futures_headline(
        highlight_reasons=reasons,
        market_name=market_name,
        top_surprise_opened_at=FEB_19,
        now=NOW,
        **inputs,
    )
    dated = generate_futures_context_summary(
        headline=headline,
        highlight_reasons=reasons,
        market_name=market_name,
        top_surprise_opened_at=FEB_19,
        now=NOW,
        **{k: v for k, v in inputs.items() if k != "top_surprise_name"},
    )
    assert dated.strip(), f"{market_name!r} still renders no caption"
    assert "Feb 19" in dated, (
        "the caption must name the day the move is measured from — an undated "
        "lifetime move is what D1 clause a (#4066) refused to publish"
    )
