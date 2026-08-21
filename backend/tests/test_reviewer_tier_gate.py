"""Queue 311 Item B1 (#1170, #1542) — the reviewer-tier quarantine.

`/play` is about to let an 8-year-old and a 13-year-old write `ranking_judgments`
rows. Those rows feed the daily eval metrics, the labelling queue, and the
holdout export. The labelled corpus is ~24 rows with one positive, so a handful
of kid taps would not skew those numbers — they would dominate them.

Tested in BOTH directions throughout (gotcha #43): the kid row is excluded AND
the gold row survives. A one-directional test cannot tell a working gate from a
filter that drops everything, and a gate proven only to block is how a gate
rots into decoration.
"""

import pytest
from sqlalchemy.dialects import postgresql

from app.models.models import RankingJudgment
from app.utils.reviewer_tier import (
    DEFAULT_TIER,
    GOLD_TIERS,
    TIER_ALEX,
    TIER_KEY,
    TIER_KID,
    TIER_LLM,
    gold_filter,
    is_gold,
    resolve_tiers,
    tier_filter,
    tier_of,
    with_tier,
)


class _Row:
    def __init__(self, metadata):
        self.label_metadata = metadata


# ---------------------------------------------------------------------------
# tier_of — absence resolves to alex, in one place
# ---------------------------------------------------------------------------


def test_untagged_row_reads_as_alex():
    """Every pre-B1 row is the curator's; absence has one correct reading."""
    assert tier_of(_Row(None)) == TIER_ALEX
    assert tier_of(_Row({})) == TIER_ALEX
    assert tier_of(_Row({"other": "value"})) == TIER_ALEX


def test_explicit_tiers_round_trip():
    assert tier_of(_Row({"reviewer_tier": TIER_KID})) == TIER_KID
    assert tier_of(_Row({"reviewer_tier": TIER_LLM})) == TIER_LLM
    assert tier_of(_Row({"reviewer_tier": TIER_ALEX})) == TIER_ALEX


def test_unrecognized_tier_reads_as_alex_not_as_quarantined():
    """A typo must not silently DROP a real curator label from a 24-row corpus.

    Safe here means "treated as real", not "treated as suspect" — the corpus is
    too small for a swallowed label to be a rounding error.
    """
    assert tier_of(_Row({"reviewer_tier": "aelx"})) == DEFAULT_TIER
    assert tier_of(_Row({"reviewer_tier": None})) == DEFAULT_TIER


def test_is_gold_both_directions():
    assert is_gold(_Row({"reviewer_tier": TIER_ALEX})) is True
    assert is_gold(_Row(None)) is True
    assert is_gold(_Row({"reviewer_tier": TIER_KID})) is False
    assert is_gold(_Row({"reviewer_tier": TIER_LLM})) is False


# ---------------------------------------------------------------------------
# with_tier — a write knows its own tier
# ---------------------------------------------------------------------------


def test_with_tier_stamps_without_losing_existing_metadata():
    out = with_tier({"fixable_interest": {"a": 1}}, TIER_KID)
    assert out["reviewer_tier"] == TIER_KID
    assert out["fixable_interest"] == {"a": 1}


def test_with_tier_handles_absent_metadata():
    assert with_tier(None, TIER_ALEX) == {"reviewer_tier": TIER_ALEX}


def test_with_tier_does_not_mutate_the_caller_dict():
    original = {"k": "v"}
    with_tier(original, TIER_KID)
    assert "reviewer_tier" not in original


def test_with_tier_raises_on_an_unknown_tier():
    """A write site knows its tier; a typo should stop the write.

    Defaulting here would do the one unacceptable thing: quietly produce a GOLD
    row from a mistyped kid write.
    """
    with pytest.raises(ValueError):
        with_tier({}, "kids")


# ---------------------------------------------------------------------------
# The SQL predicate
# ---------------------------------------------------------------------------


def _sql(clause):
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_gold_filter_matches_untagged_rows_too():
    """Every pre-B1 row has NULL metadata. A filter that missed them would
    empty the corpus rather than gate it — silently reporting zero labels."""
    sql = _sql(gold_filter())
    assert "'alex'" in sql
    assert "IS NULL" in sql, "untagged and NULL-metadata rows must still count as gold"


def test_gold_filter_does_not_match_kid_or_llm():
    sql = _sql(gold_filter())
    assert "'kid'" not in sql
    assert "'llm'" not in sql


def test_tier_filter_can_be_widened_explicitly():
    sql = _sql(tier_filter({TIER_KID}))
    assert "'kid'" in sql
    # Widening to kid must NOT drag untagged rows along: those are Alex's.
    assert "IS NULL" not in sql


def test_tier_filter_rejects_unknown_tiers():
    with pytest.raises(ValueError):
        tier_filter({"grownup"})


# ---------------------------------------------------------------------------
# Deny by default — the actual B1 requirement
# ---------------------------------------------------------------------------


def test_resolve_tiers_defaults_to_gold_not_to_everything():
    """The whole point of B1.

    The filters this replaced were all `reviewer: str | None = None` → no filter
    when None. Same fail-open shape as the analytics consent gate one queue
    earlier: correct when used, off unless someone remembers.
    """
    assert resolve_tiers(None) == GOLD_TIERS
    assert resolve_tiers({TIER_KID}) == frozenset({TIER_KID})
    assert resolve_tiers({TIER_ALEX, TIER_KID}) == frozenset({TIER_ALEX, TIER_KID})


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param("eval_rows", id="daily-eval-beat"),
        pytest.param("labeling_queue", id="labeling-queue"),
        pytest.param("export", id="holdout-export"),
    ],
)
def test_every_consumer_denies_by_default(builder):
    """Called with no tier argument, each consumer must emit the gold predicate.

    This is the regression that matters: the risk is not that someone writes a
    wrong filter, it is that a NEW consumer is added with no filter at all and
    nothing notices.
    """
    import inspect

    if builder == "eval_rows":
        from app.utils.discover_label_eval_runs import load_label_eval_rows as fn
    elif builder == "labeling_queue":
        from app.utils.labeling_queue import load_reviewed_ranking_keys as fn
    else:
        from scripts.export_discover_labeled_dataset import (
            build_labeled_dataset_statement as fn,
        )

    source = inspect.getsource(fn)
    assert "tier_filter(resolve_tiers(" in source, (
        f"{builder} must apply the tier filter; without it kid rows enter gold metrics"
    )
    signature = inspect.signature(fn)
    assert signature.parameters["tiers"].default is None, (
        f"{builder}'s `tiers` must default to None so resolve_tiers() picks gold"
    )


def test_export_statement_carries_the_gold_predicate_when_unasked():
    from datetime import datetime, timezone

    from scripts.export_discover_labeled_dataset import build_labeled_dataset_statement

    stmt = build_labeled_dataset_statement(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "'alex'" in sql
    assert "'kid'" not in sql


def test_admin_write_path_stamps_the_alex_tier():
    """Authority in the route, not in a caller-supplied flag.

    The admin surface is Alex's, so it writes `alex` unconditionally. The kid
    surface gets its own route with no path to any other tier — rather than one
    shared route with an `is_kid` boolean someone must remember to pass.

    ** RE-ANCHORED BY UX-P112 (#1933 bullet 2), NOT RELAXED. ** The stamping
    itself moved into `gold_label_store.gold_label_row`, the one place a gold
    label is now constructed, so asserting `with_tier(` inside
    `create_judgment` would only prove where a line of code sits. The property
    worth pinning is unchanged and is now checked in both halves: the route
    names `TIER_ALEX` and names nothing else, and the shared constructor is
    what applies it. Behaviour is asserted underneath, so this cannot pass on
    the strings alone.
    """
    import inspect

    from app.routes import admin_judgments
    from app.utils import gold_label_store

    source = inspect.getsource(admin_judgments.create_judgment)
    assert "TIER_ALEX" in source
    # Unconditional: exactly one tier is named on this write path, and a second
    # one appearing is the `is_kid`-boolean shape this rule exists to forbid.
    assert "TIER_KID" not in source and "TIER_LLM" not in source
    assert source.count("tier=") == 1, "the admin route must name one tier, once"

    # ...and the tier is really applied, by the shared constructor.
    assert "with_tier(" in inspect.getsource(gold_label_store.gold_label_row)
    row = gold_label_store.gold_label_row(
        label="love", surface="discover", reviewer="alex", metadata=None
    )
    assert row.label_metadata[TIER_KEY] == TIER_ALEX


def test_reviewer_tier_is_metadata_not_a_new_column():
    """No migration (premise P9): the tier rides in existing JSONB.

    Pinned because "add a column" is the reflex, and Batch B's ability to follow
    Batch A in one lane depends on it not claiming a second migration slot.
    """
    assert not hasattr(RankingJudgment, "reviewer_tier")
    assert hasattr(RankingJudgment, "label_metadata")
