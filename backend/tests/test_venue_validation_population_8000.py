"""#8000 — the helpers behind the display-selection repair, at the unit level.

The route-level proof is `tests/integration/test_supported_history_survives_
display_selection_8000_real_pg_redis.py`. This file pins the two helper facts
the repair leans on, in the exact shape Codex constructed on cdba3e9f
(`8000-INDEPENDENT-REVIEW-EVIDENCE.json`): a complete 12-leg exclusive field,
one simultaneous 0.05 observation per leg, ten of them drawn.

  * `_venue_points_countable_as_density` handed ALL twelve rows and ten drawn
    ids counts the ten drawn rows (it counted zero — it re-filtered to the
    drawn ids before asking the hole question);
  * `_venue_field_columns` is asked with the whole field's rows and answers
    whole; a subset is a hole and a superset is a wrong identity, neither whole.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes import futures as futures_route

T0 = datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)
FIELD = list(range(3001, 3013))          # twelve legs
DRAWN = set(FIELD[:10])


def _market():
    return SimpleNamespace(id=1, name="Twelve", source="kalshi", mutually_exclusive=True)


def _outcomes(ids=FIELD):
    return [SimpleNamespace(id=oid, name=f"Leg {oid}") for oid in ids]


def _row(oid, at, p=0.05):
    return SimpleNamespace(outcome_id=oid, bookmaker="kalshi", probability=p, captured_at=at,
                           tier="kalshi_candle_60m")


def _rows(ids, instants):
    return [_row(oid, at) for at in instants for oid in ids]


class TestCodexCounterexample:
    INSTANTS = [T0 - timedelta(hours=h) for h in (3, 2, 1)]

    def test_the_full_field_is_whole_and_the_scale_contract_accepts_it(self):
        by_outcome = {oid: [_row(oid, at) for at in self.INSTANTS] for oid in FIELD}
        hole, columns = futures_route._venue_field_columns(_market(), _outcomes(), by_outcome)
        assert hole is None and len(columns) == 3
        assert futures_route._venue_scale_refusal(_market(), _outcomes(), by_outcome, {}, {}) is None

    def test_density_handed_the_field_and_ten_drawn_ids_counts_the_drawn_rows(self):
        """Codex measured 0 here on cdba3e9f. Thirty is the density a reader sees."""
        density = futures_route._venue_points_countable_as_density(
            _market(), _outcomes(), _rows(FIELD, self.INSTANTS), DRAWN)
        assert density == 10 * len(self.INSTANTS)

    def test_density_still_refuses_a_hole_in_an_undrawn_leg(self):
        rows = _rows(FIELD, self.INSTANTS)
        rows = [r for r in rows if not (r.outcome_id == FIELD[-1] and r.captured_at == self.INSTANTS[0])]
        assert futures_route._venue_points_countable_as_density(
            _market(), _outcomes(), rows, DRAWN) == 0

    def test_density_over_only_the_drawn_rows_is_the_defect_and_still_reads_zero(self):
        """The narrowing itself, at the helper: ten legs' rows on a twelve-leg
        field have no denominator. The repair moves WHAT is handed in, not the
        rule — a caller that still narrows first still gets zero."""
        assert futures_route._venue_points_countable_as_density(
            _market(), _outcomes(), _rows(sorted(DRAWN), self.INSTANTS), DRAWN) == 0


class TestWholeMeansExactlyTheField:
    def test_a_subset_column_is_a_hole(self):
        by_outcome = {oid: [_row(oid, T0)] for oid in FIELD[:11]}
        hole, _ = futures_route._venue_field_columns(_market(), _outcomes(), by_outcome)
        assert hole == "exclusive_field_incomplete_at_venue_instant"

    def test_a_superset_column_is_not_whole_either(self):
        """🧟 wrong identity: a thirteenth leg that is not this field's cannot
        complete it (`validate_payload` refuses such a row upstream — 7351's
        C1 — and the column rule refuses it again here, so neither can drift)."""
        by_outcome = {oid: [_row(oid, T0)] for oid in FIELD + [9999]}
        hole, _ = futures_route._venue_field_columns(_market(), _outcomes(), by_outcome)
        assert hole == "exclusive_field_incomplete_at_venue_instant"
