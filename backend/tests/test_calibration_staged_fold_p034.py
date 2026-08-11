"""CAL-P034 — the cursor banks a running total, not a growing pile.

Measured on the live cursor at 91/128 units (``calibration:main:staged_futures``,
2026-08-11T03:36:23Z), which is why this change exists:

=============  =============  ====================  ===========
units banked   rows retained  distinct group keys   compaction
=============  =============  ====================  ===========
1              469            469                   1.0x
10             4,825          1,063                 4.5x
40             19,498         1,363                 14.3x
91             44,272         1,586                 27.9x
=============  =============  ====================  ===========

Rows grow linearly, groups saturate: a bucket is a price band, not a question,
so every unit re-states the same ~470 bands and the merge's only act is to sum
them. 10,622,807 bytes of banked ``repr`` at 91 units = 116.7 KB/unit, and the
whole cursor is re-serialised after EVERY unit, so a full 128-unit walk spent
~960 MB in ``json.dumps`` to retain ~62,300 rows that finalization turns into
~1,650. The worker peaked at 505 MB against a 512 MB dyno.

The rules pinned here are the ones whose inversion brings the pile back, plus
the ones that make folding early SAFE rather than merely smaller.
"""

from __future__ import annotations

import ast
import pathlib
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.calibration_staged_futures import (
    DECLARED_CENSUS_COLUMNS,
    DEFAULT_CENSUS_COLUMNS,
    GROUP_KEY_COLUMNS,
    REASON_UNFOLDED_UNITS,
    REPRESENTATIVE_TIE_COLUMN,
    MAIN_BUILD_TASK,
    STAGED_FUTURES_SCHEMA,
    UNIT_KEY_VM_ID,
    UndeclaredColumnError,
    advance,
    collect_unit_results,
    decode_staged_cursor_detailed,
    encode_unit_rows,
    fold_unit_rows,
    merge_futures_rows,
    new_staged_cursor,
    split_unit_rows,
)

VERSION = "q300d"
INPUT_FP = "fp-input"
GEN_FP = "fp-gen"
OWNER = "worker-a"

CENSUS = DECLARED_CENSUS_COLUMNS

_FROZEN = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks" / "precompute_calibration.py"


# =============================================================================
# The finalizer, mirrored
# =============================================================================


def _finalize(banked, *, census_columns=CENSUS, global_census=()):
    """What ``precompute_calibration``'s ``staged:finalize`` stage does.

    Mirrored rather than imported: ruling 009 bars this lane from editing that
    module and CAL-P032/P033 bar importing it at runtime. The mirror is pinned
    by :func:`test_the_mirrored_finalizer_still_matches_the_frozen_one`, because
    a mirror nobody checks is how two derivations of one fact drift apart.
    """
    census_only: list[dict] = []
    bucket_rows: list[list] = []
    for unit in banked:
        keep = []
        for row in unit:
            mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))
            if mapping.get("bucket_idx") is None:
                census_only.append(mapping)
            else:
                keep.append(row)
        bucket_rows.append(keep)
    return merge_futures_rows(
        bucket_rows,
        census_columns=census_columns,
        extra_censuses=census_only + list(global_census),
    )


def _cursor():
    return new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GEN_FP,
        owner=OWNER,
        generation=1,
    )


def _bank(units, *, census_columns=CENSUS):
    cursor = _cursor()
    for index, rows in enumerate(units):
        cursor = advance(
            cursor,
            f"u{index}",
            rows,
            owner=OWNER,
            lease_expires_at=1e12,
            census_columns=census_columns,
        )
    return cursor


def _row(**over):
    row = {
        "bucket_idx": 3,
        "source": "kalshi",
        "category": "baseball",
        "price_moved": False,
        "is_nonexclusive_bundle": False,
        "n": 14,
        "winners": 6,
        "sum_prob": Decimal("0.03071428571428571429"),
        "sum_sq_err": 0.0238,
        "avg_prob": 0.43,
    }
    row.update(over)
    return SimpleNamespace(**row)


def _unit(index: int, *, census: dict | None = None, buckets: int = 3):
    """One unit: several bucket rows sharing a chunk-constant census."""
    shared = {
        "published_outcomes": 100 + index,
        "published_questions": 10 + index,
        "kalshi_included": 7 + index,
        REPRESENTATIVE_TIE_COLUMN: index,
    }
    shared.update(census or {})
    return [
        _row(
            bucket_idx=b,
            source="kalshi" if b % 2 else "polymarket",
            category="baseball" if b % 3 else "soccer",
            n=index + b + 1,
            winners=b,
            sum_prob=Decimal("0.5") * (index + b + 1),
            sum_sq_err=0.01 * (index + b + 1),
            **shared,
        )
        for b in range(1, buckets + 1)
    ]


# =============================================================================
# THE acceptance bar — folding early must change nothing downstream
# =============================================================================


class TestFoldingEarlyChangesNothing:
    def test_the_fold_finalizes_identically_to_banking_every_row(self):
        """THE test. Old shape and new shape, same finalized payload.

        The old shape retained every unit's rows and folded them all at the end;
        the new one folds as it banks. Everything the payload is read off —
        group keys, the four additive sums, ``avg_prob``, every census total,
        and the row ORDER — has to come out the same, or this queue has silently
        changed the published curve while making it cheaper.
        """
        units = [_unit(i) for i in range(6)]

        old = _finalize(units)
        new = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(6)]))

        assert old, "the old path produced nothing to compare against"
        assert [vars(r) for r in new] == [vars(r) for r in old]

    def test_the_census_is_counted_once_per_unit_not_once_per_row(self):
        """The arithmetic most at risk, isolated and asserted on a known total.

        ``merge_futures_rows`` takes ONE census observation per chunk, off its
        first row, because the values are CROSS JOINed off a 1-row summary and
        are constant down the chunk. The fold has to preserve that arity
        exactly: count per row and a 3-bucket unit inflates the census 3x;
        count per fold and 6 units collapse to 1.
        """
        units = [_unit(i, buckets=3) for i in range(6)]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(6)]))

        # published_outcomes is 100+index, summed once per unit.
        assert merged[0].published_outcomes == sum(100 + i for i in range(6))
        assert merged[0].published_questions == sum(10 + i for i in range(6))

    def test_a_census_nobody_reported_stays_unknown_and_never_becomes_zero(self):
        """Gotcha #53 through the fold. Unknown is None, not a confident 0."""
        units = [_unit(i) for i in range(3)]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(3)]))

        assert merged[0].poly_included is None, "never reported => unknown"
        assert merged[0].published_outcomes is not None, "reported => a number"

    def test_a_census_reported_as_none_by_every_unit_stays_none(self):
        units = [_unit(i, census={"poly_included": None}) for i in range(3)]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(3)]))
        assert merged[0].poly_included is None

    def test_a_census_some_units_report_sums_only_the_reporters(self):
        units = [
            _unit(0, census={"poly_included": 5}),
            _unit(1, census={"poly_included": None}),
            _unit(2, census={"poly_included": 7}),
        ]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(3)]))
        assert merged[0].poly_included == 12

    def test_refolding_a_folded_set_changes_nothing(self):
        """The property ``collect_unit_results`` depends on and cannot enforce.

        The finalizer re-merges whatever it is handed, so handing it an
        already-folded set must be a no-op: each group appears once so the sums
        pass through, ``avg_prob`` is recomputed from those same sums, and the
        folded rows carry no census of their own — all of it arrives through the
        carriers — so nothing is observed twice.
        """
        units = [_unit(i) for i in range(4)]
        once = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(4)]))
        twice = _finalize([list(once)])

        # The carriers are consumed by the first merge, so the second pass sees
        # the census already broadcast on every row: it re-observes ONE copy of
        # the same totals, which is what makes the operation idempotent.
        assert [vars(r) for r in twice] == [vars(r) for r in once]

    def test_avg_prob_is_recomputed_from_the_folded_sums(self):
        units = [_unit(i, buckets=1) for i in range(4)]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(4)]))
        for row in merged:
            assert row.avg_prob == pytest.approx(row.sum_prob / row.n)


# =============================================================================
# What the fold retains — the point of the exercise
# =============================================================================


class TestTheRetainedStructureIsBounded:
    def test_retained_rows_are_bounded_by_the_group_space_not_the_unit_count(self):
        """The measurement, as a property: 40 units of the same bands stay flat.

        Production's 91 units retained 44,272 rows carrying 1,586 groups. Here
        every unit re-states the same 3 bands, so the retained row count must
        stay at 3 no matter how many units bank — the pre-fold shape grows to
        120 and is what killed the beat.
        """
        cursor = _cursor()
        sizes = []
        for index in range(40):
            cursor = advance(
                cursor, f"u{index}", _unit(index, buckets=3), owner=OWNER, lease_expires_at=1e12
            )
            sizes.append(len(cursor.folded()[0]))

        assert sizes[-1] == 3, "the bands saturate; the retained rows must too"
        assert max(sizes) == 3
        assert len(cursor.committed_units) == 40

    def test_a_new_group_still_grows_the_fold(self):
        """The bound is the GROUP space, not a cap — a genuinely new band lands."""
        cursor = _cursor()
        cursor = advance(cursor, "u0", [_row(bucket_idx=1)], owner=OWNER, lease_expires_at=1e12)
        cursor = advance(cursor, "u1", [_row(bucket_idx=2)], owner=OWNER, lease_expires_at=1e12)
        assert len(cursor.folded()[0]) == 2

    def test_the_encoded_cursor_stops_growing_with_units(self):
        """The byte-level claim, since bytes are what the 512 MB dyno counts."""
        import json

        cursor = _cursor()
        sizes = []
        for index in range(30):
            cursor = advance(
                cursor, f"u{index}", _unit(index, buckets=3), owner=OWNER, lease_expires_at=1e12
            )
            sizes.append(len(json.dumps(cursor.accumulator, default=str)))

        # Carriers are one per unit and are bounded by 128, so the payload still
        # creeps; what must NOT happen is the ~470-rows-per-unit growth.
        growth_per_unit = (sizes[-1] - sizes[9]) / 20
        assert growth_per_unit < 200, f"cursor still grows {growth_per_unit:.0f} B/unit"


# =============================================================================
# The guards that make folding early safe
# =============================================================================


class TestTheGuards:
    def test_an_undeclared_column_is_refused_at_bank_time(self):
        """Without this, the fold BROADCASTS an unknown column instead of raising.

        ``merge_futures_rows`` refuses an undeclared column because there is no
        safe default. The fold routes every non-group, non-additive column into
        the carrier — i.e. down the broadcast path — so the refusal has to move
        to where a unit's rows are last seen whole.
        """
        with pytest.raises(UndeclaredColumnError):
            split_unit_rows([_row(surprise=1)])

    def test_an_additive_column_is_never_mistaken_for_a_census(self):
        """The specific inversion the guard prevents, stated as mass."""
        units = [_unit(i, buckets=1) for i in range(5)]
        merged = _finalize(collect_unit_results(_bank(units), [f"u{i}" for i in range(5)]))
        assert merged[0].n == sum(i + 2 for i in range(5)), "n must SUM, not broadcast"

    def test_a_row_with_no_bucket_is_kept_whole_as_a_carrier(self):
        """An empty chunk's census carrier must survive the fold intact."""
        carrier = SimpleNamespace(bucket_idx=None, published_outcomes=42)
        _mass, carriers = split_unit_rows([carrier])
        assert [c["published_outcomes"] for c in carriers] == [42]

    def test_a_unit_with_both_a_carrier_and_buckets_yields_both(self):
        """Replicated from today's behaviour rather than tidied.

        The finalizer strips null-keyed rows into ``extra_censuses`` AND
        ``merge_futures_rows`` still takes a census off the first surviving
        bucket row, so such a unit contributes two observations. Tidier here
        would mean a different census total.
        """
        rows = [SimpleNamespace(bucket_idx=None, published_outcomes=1), _row(published_outcomes=2)]
        _mass, carriers = split_unit_rows(rows)
        assert sorted(c.get("published_outcomes") for c in carriers) == [1, 2]

    def test_the_declared_census_set_matches_the_frozen_builds_own_expression(self):
        """The mirror, pinned in BOTH directions (gotcha #10's lesson).

        ``DECLARED_CENSUS_COLUMNS`` exists because the fold needs the declared
        set at bank time and ruling 009 bars importing the module that owns it.
        A mirror that nothing checks is how two derivations of one fact drift —
        CAL-P032 deleted a hand-copied census for exactly this reason. Read as
        TEXT via ``ast``: a read, not a commit.
        """
        tree = ast.parse(_FROZEN.read_text())

        flag = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "COVERAGE_CENSUS_ENABLED"
                for t in node.targets
            )
        ]
        assert len(flag) == 1, "the coverage switch moved or multiplied"
        assert ast.literal_eval(flag[0].value) is False, (
            "COVERAGE_CENSUS_ENABLED is ON — the cb_* columns are now part of the "
            "declared set, so advance() must be passed census_columns explicitly"
        )

        assigns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "census_columns" for t in node.targets)
        ]
        assert len(assigns) == 1, "the build's census_columns assignment moved"
        assert (
            ast.unparse(assigns[0].value)
            == "tuple(DEFAULT_CENSUS_COLUMNS) + ('representative_tie_broken',)"
        )
        assert DECLARED_CENSUS_COLUMNS == tuple(DEFAULT_CENSUS_COLUMNS) + (
            REPRESENTATIVE_TIE_COLUMN,
        )

    def test_the_mirrored_finalizer_still_matches_the_frozen_one(self):
        """``_finalize`` above is a copy of a barred file's logic. Pin it.

        Not a character-for-character diff — that would fail on a comment. The
        three decisions the mirror depends on: the null-keyed split, the census
        routing into ``extra_censuses``, and the per-unit iteration.
        """
        text = _FROZEN.read_text()
        assert 'if mapping.get("bucket_idx") is None:' in text
        assert "extra_censuses=census_only + global_census," in text
        assert "banked = collect_unit_results(cursor, chunks)" in text


class TestWhatIsRefusedOnRead:
    def _raw(self, **over):
        base = {
            "schema": STAGED_FUTURES_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "unit_key": UNIT_KEY_VM_ID,
            "population_version": VERSION,
            "input_fingerprint": INPUT_FP,
            "committed_units": ["u0"],
            "lease_expires_at": 0.0,
        }
        base.update(over)
        return base

    def _decode(self, raw):
        return decode_staged_cursor_detailed(
            raw,
            expected_population_version=VERSION,
            expected_input_fingerprint=INPUT_FP,
            expected_generation_fingerprint=GEN_FP,
            owner=OWNER,
            generation=9,
            now=0.0,
        )

    def test_a_cal_p033_era_cursor_is_refused_under_its_own_reason(self):
        """The ONE expected reset, and it must be namable.

        A CAL-P033 cursor's units are perfectly readable — they are just not
        folded. Reporting that as ``malformed_units`` would make the single
        expected reset indistinguishable from a real one, which is the mistake
        CAL-P033 itself refused to make with ``unencoded_units``.
        """
        raw = self._raw(unit_results={"u0": encode_unit_rows([{"bucket_idx": 1}])})
        cursor, action, reason = self._decode(raw)
        assert reason == REASON_UNFOLDED_UNITS
        assert cursor.committed_units == ()

    def test_a_folded_cursor_round_trips(self):
        banked = _bank([_unit(0)])
        cursor, action, _reason = self._decode(banked.as_payload())
        assert cursor.committed_units == ("u0",)
        assert len(cursor.folded()[0]) == 3

    def test_the_walk_survives_a_json_round_trip_between_every_unit(self):
        """The edge CAL-P033 found the hard way: production only ever resumes.

        ~8,000 tests missed the last cursor bug because they handed rows from
        ``advance`` straight to the merge in one process. Every unit here goes
        through real JSON before the next one banks.
        """
        import json

        raw = None
        for index in range(5):
            if raw is None:
                cursor = _cursor()
            else:
                cursor, action, reason = self._decode(raw)
                assert action != "invalidate", reason
            cursor = advance(
                cursor, f"u{index}", _unit(index), owner=OWNER, lease_expires_at=1e12
            )
            raw = json.loads(json.dumps(cursor.as_payload(), default=str))

        resumed, _action, _reason = self._decode(raw)
        merged = _finalize(collect_unit_results(resumed, [f"u{i}" for i in range(5)]))
        direct = _finalize([_unit(i) for i in range(5)])
        assert [vars(r) for r in merged] == [vars(r) for r in direct]


class TestFoldUnitRowsDirectly:
    def test_folding_nothing_onto_nothing_is_empty(self):
        buckets, carriers = fold_unit_rows([], [], [])
        assert buckets == []
        assert carriers == []

    def test_group_keys_that_differ_only_by_none_stay_distinct(self):
        """``None`` is a real group-key value, not a wildcard."""
        buckets, _c = fold_unit_rows(
            [], [], [_row(category="baseball"), _row(category=None)]
        )
        assert len(buckets) == 2

    def test_integer_columns_stay_integers_through_the_fold(self):
        buckets, _c = fold_unit_rows([], [], [_row(n=1, winners=2)])
        buckets, _c = fold_unit_rows(buckets, [], [_row(n=3, winners=4)])
        assert buckets[0].n == 4 and isinstance(buckets[0].n, int)
        assert buckets[0].winners == 6 and isinstance(buckets[0].winners, int)

    def test_integer_mass_is_summed_as_integers_not_through_float(self):
        """The ACCUMULATOR must be integral, not just the value it hands out.

        Written because a mutation survived: routing the running total through
        ``_as_float`` still produced ints, since the output coerces with
        ``_as_int`` on the way out. It is only distinguishable past 2**53, where
        a float can no longer represent consecutive integers — so the count
        silently stops rising while every type check still passes. Contrived
        magnitude, real invariant: counts are summed as counts.
        """
        big = 2**53
        buckets, _c = fold_unit_rows([], [], [_row(n=big)])
        for _ in range(2):
            buckets, _c = fold_unit_rows(buckets, [], [_row(n=1)])
        assert buckets[0].n == big + 2

    def test_every_group_key_column_participates_in_the_key(self):
        """Drop one from the key and rows that must stay apart would merge."""
        for column in GROUP_KEY_COLUMNS:
            base = _row()
            other = _row(**{column: "different" if column != "bucket_idx" else 99})
            buckets, _c = fold_unit_rows([], [], [base, other])
            assert len(buckets) == 2, f"{column} is not part of the group key"
