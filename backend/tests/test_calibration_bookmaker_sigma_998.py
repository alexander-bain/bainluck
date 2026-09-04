"""CAL-P998 — guards for the bookmaker cells' measured SE.

THE GAP THIS CLOSES
-------------------
CAL-P128's sigma ledger banks a measured cluster-bootstrap SE per cell so the
board stops feeding a row-grain estimate into a standard-error gate. It is fed
by ``calibration_cluster_sigma.py``, which drives ``calibration_cell_exact`` and
therefore folds the ``futures_markets``-rooted producer chain. This source has
**zero rows in that table**, so the six ``odds_api_bookmaker`` cells could not
be banked even in principle — 6 of the 14 queued cells on the 2026-09-03 board,
82,345 excess-outcomes, permanently on the basis the ledger exists to correct.

CAL-P120 derived their game-grain SE by hand and wrote it in a report. The
board has carried them at the row basis ever since. That is exactly the
hand-derivation CAL-P128 was built to end, and it kept happening because there
was no instrument to run.

WHAT IS PINNED HERE
-------------------
1. **The cluster is the GAME, and regrouping into it aggregates nothing.**
2. **A game never lands in two clusters**, which is what makes the per-chunk
   sweep additive — the same property that makes the bucket fold exact.
3. **The emitted object is the LEDGER'S shape**, round-tripped through
   ``entry_from_sigma_json`` and ``validate``. A parallel entry shape for one
   source would be a second ledger wearing the first one's filename.
4. **rho = 1 is not assumed, it is reproduced.** ``won`` is a function of
   ``event_id`` alone here, so the bootstrap must land on the game-grain SE
   rather than between it and the row grain.
5. **CAL-P120's finding is executable now instead of quoted**: NBA at 573 games
   falls from ESTABLISHED to NOT ESTABLISHED, and the point estimate is not
   what moved.
6. **An empty cell is refused**, because an SE over nothing is not a small SE.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bmk = _load("calibration_bookmaker_cell_fold")
ledger_mod = _load("calibration_sigma_ledger")
cs = _load("calibration_scorecard")

META = {
    "generated_at": "2026-09-03T18:16:07.342457+00:00",
    "population_version": "q269",
}


def _row(event_id, bucket_idx, n, winners, sum_prob):
    return {
        "event_id": event_id,
        "bucket_idx": bucket_idx,
        "n": n,
        "winners": winners,
        "sum_prob": sum_prob,
    }


def _nba_like(games=573, books=18, p=0.72, win_rate=0.66, sd=0.10, seed=7):
    """A cell with NBA's shape: one game published `books` times, every row of a
    game carrying the SAME outcome — which is the whole point.

    `bucket_idx` follows the price, so the bins are real bins and not a label.
    """
    import random

    rng = random.Random(seed)
    rows, wins = [], 0
    for g in range(games):
        won = 1 if rng.random() < win_rate else 0
        wins += won
        prob = min(0.98, max(0.02, rng.gauss(p, sd)))
        b = min(9, int(prob * 10))
        rows.append(_row(f"e{g}", b, books, books * won, books * prob))
    return rows


# --------------------------------------------------------------------------
# Claims 1 and 2 — the cluster is the game
# --------------------------------------------------------------------------


class TestTheClusterIsTheGame:
    def test_one_cluster_per_game(self):
        rows = _nba_like(games=50)
        assert len(bmk.game_clusters(rows)) == 50

    def test_regrouping_aggregates_nothing(self):
        """Pooling the clusters back reproduces the bucket fold row for row.
        If it did not, the bootstrap would be resampling a cell this rail does
        not publish."""
        rows = _nba_like(games=120)
        pooled: dict[int, dict] = {}
        for g in bmk.game_clusters(rows):
            for b, v in g.items():
                p = pooled.setdefault(b, {"n": 0, "winners": 0, "sum_prob": 0.0})
                p["n"] += v["n"]
                p["winners"] += v["w"]
                p["sum_prob"] += v["sp"]
        direct = bmk.merge_buckets(rows)
        assert pooled == direct

    def test_a_game_split_across_two_chunks_lands_in_one_cluster(self):
        """Chunks partition events by `commence_time`, so this should not
        happen — but a rail that silently made two clusters out of one game
        would double its effective sample, which is the error the whole file
        exists to remove, in reverse."""
        rows = [_row("e1", 8, 10, 10, 8.4), _row("e1", 9, 8, 8, 7.4)]
        clusters = bmk.game_clusters(rows)
        assert len(clusters) == 1
        assert clusters[0][8]["n"] == 10 and clusters[0][9]["n"] == 8

    def test_two_rows_for_the_same_game_and_bucket_are_summed_not_overwritten(self):
        rows = [_row("e1", 8, 10, 10, 8.4), _row("e1", 8, 5, 5, 4.2)]
        c = bmk.game_clusters(rows)[0]
        assert c[8] == {"n": 15, "w": 15, "sp": pytest.approx(12.6)}


# --------------------------------------------------------------------------
# Claim 3 — the emitted object is the ledger's own shape
# --------------------------------------------------------------------------


class TestItEmitsTheLedgersShape:
    def _obj(self, **kw):
        rows = _nba_like(**kw)
        published = bmk.merge_buckets(rows)
        return bmk.sigma_object(
            "basketball_nba", bmk.game_clusters(rows), published, META, 200, 1
        )

    def test_the_ledger_folds_it_with_no_change(self):
        entry = ledger_mod.entry_from_sigma_json(self._obj(games=200), "test")
        assert entry["source"] == "odds_api_bookmaker"
        assert entry["category"] == "basketball_nba"
        assert entry["population_version"] == "q269"
        assert entry["se_bootstrap_pp"] > 0
        assert entry["as_measured"]["n"] > 0

    def test_the_built_ledger_validates(self, tmp_path):
        """`validate` recomputes the stored sigma from the stored SE and
        refuses on a mismatch. A hand-built entry shape that cannot survive
        that check is a transcription error with extra steps."""
        p = tmp_path / "sigma-nba.json"
        p.write_text(json.dumps(self._obj(games=200)))
        built = ledger_mod.build([p])
        assert ledger_mod.validate(built) == []
        assert "odds_api_bookmaker/basketball_nba" in built["entries"]

    def test_it_carries_the_population_so_the_entry_can_be_aged(self):
        """Without these two the entry cannot be FRESH, CARRIED or STALE — it
        is just a number, which is the state CAL-P128 was built to leave."""
        e = ledger_mod.entry_from_sigma_json(self._obj(games=200), "t")
        assert e["population_version"] == META["population_version"]
        assert e["generated_at"] == META["generated_at"]

    def test_a_fresh_entry_off_this_rail_reaches_the_board(self):
        obj = self._obj(games=200)
        entry = ledger_mod.entry_from_sigma_json(obj, "t")
        led = {
            "schema": ledger_mod.SCHEMA,
            "entries": {"odds_api_bookmaker/basketball_nba": entry},
        }
        _, status = ledger_mod.lookup(
            led, "odds_api_bookmaker", "basketball_nba", "q269",
            obj["payload"]["n"],
        )
        assert status == ledger_mod.STATUS_FRESH

    def test_the_bar_and_the_gate_are_the_boards_own_objects(self):
        """Identity, not equality: two dicts that both read 2.5 today are the
        state this program keeps having to undo."""
        obj = self._obj(games=200)
        assert obj["bar"] is cs.CLASS_BARS_PP[cs.CLASS_A]
        assert obj["sigma_gate"] is cs.SIGMA_GATE
        assert obj["klass"] == cs.CLASS_A


# --------------------------------------------------------------------------
# Claims 4 and 5 — the measurement itself
# --------------------------------------------------------------------------


class TestTheMeasurement:
    def _obj(self, boot=400, **kw):
        rows = _nba_like(**kw)
        published = bmk.merge_buckets(rows)
        return bmk.sigma_object(
            "basketball_nba", bmk.game_clusters(rows), published, META, boot, 11
        )

    def test_the_bootstrap_counts_games_and_not_book_rows(self):
        """rho = 1 BY CONSTRUCTION on this source: ``won`` is a function of
        ``event_id`` alone, so a book-row is a COPY of an observation rather
        than an observation.

        The claim is bounded on both sides rather than pinned to the game-grain
        figure, and the reason is the one CAL-P128's docstring already gives:
        ``50/sqrt(k)`` is a MAXIMUM-VARIANCE bound at ``p = 0.5``, and these
        bins sit at 0.75. A measured SE legitimately lands BELOW the game-grain
        bound (crypto 0.835, cricket 0.485 do the same on the exchange rail),
        so requiring equality would be requiring the instrument to be wrong.
        What must hold is that it is nowhere near the row basis and never above
        the bound: rho cannot exceed 1.
        """
        obj = self._obj(games=400)
        se = obj["se"]
        assert se["bootstrap"] > 2 * se["row"], "the row basis must be far too small"
        assert se["bootstrap"] <= se["market"] * 1.02, "rho cannot exceed 1"

    def test_the_effective_sample_is_of_the_order_of_the_game_count(self):
        """The same claim stated as the number a reader acts on. If effective n
        came back near the ROW count, the correction would not be happening."""
        obj = self._obj(games=400)
        ratio = ledger_mod.variance_ratio_vs_board(
            obj["se"]["bootstrap"], obj["se"]["row"]
        )
        eff = ledger_mod.effective_n(obj["exact"]["n"], ratio)
        assert eff < obj["exact"]["n"] / 4
        assert eff < 5 * obj["clusters"]

    def test_the_row_basis_is_the_one_that_is_wrong(self):
        obj = self._obj(games=400, books=18)
        # 18 copies of one observation: the row SE is understated by ~sqrt(18).
        assert obj["se"]["row"] == pytest.approx(
            obj["se"]["market"] / math.sqrt(18), rel=0.01
        )

    def test_nba_falls_from_established_to_not_established(self):
        """CAL-P120's finding, executable instead of quoted. 573 games behind
        10,186 book-rows: the board reads 5.4 sigma, the game grain 1.28.

        The fixture is NBA-shaped rather than NBA — 573 games, 18 books each,
        ECE 4.74 pp against the live cell's 5.18 — because a unit test cannot
        hold the production rows. What it reproduces is the STRUCTURE that
        produces the finding, and the finding follows from the structure.
        """
        obj = self._obj(games=573, books=18, p=0.75, win_rate=0.70, sd=0.05)
        assert obj["exact"]["ece"] == pytest.approx(4.74, abs=0.5)
        assert obj["sigma"]["row"] > cs.SIGMA_GATE
        assert obj["sigma"]["bootstrap"] < cs.SIGMA_GATE
        assert obj["established"] is False

    def test_the_point_estimate_is_not_what_moved(self):
        """The correction is about the SE. A reader who took this for 'the cell
        got better' would be reading the opposite of what happened."""
        obj = self._obj(games=573)
        assert obj["exact"]["ece"] == pytest.approx(obj["payload"]["ece"], abs=0.01)

    def test_the_bootstrap_is_reproducible(self):
        a = self._obj(games=150)["se"]["bootstrap"]
        b = self._obj(games=150)["se"]["bootstrap"]
        assert a == b, "a fixed seed is what makes the verdict re-checkable"

    def test_this_rail_reproduces_its_own_cell_so_coverage_is_one(self):
        """`exact_coverage` outside COVERAGE_BAND turns the entry into
        POPULATION_DIVERGENCE and it decides nothing. This rail chunks on
        `commence_time`, which partitions events, so it is exact — and if that
        ever stops being true the board says so instead of quietly halving a
        standard error."""
        obj = self._obj(games=200)
        e = ledger_mod.entry_from_sigma_json(obj, "t")
        assert e["exact_coverage"] == 1.0


# --------------------------------------------------------------------------
# Claim 6 — the refusals
# --------------------------------------------------------------------------


class TestItRefusesRatherThanGuesses:
    def test_an_empty_cell_yields_no_clusters(self):
        assert bmk.game_clusters([]) == []

    def test_sigma_forces_the_grain_that_can_answer_it(self):
        """`--sigma --grain game` asks for a bootstrap over units that have
        already been averaged into one price per game. It is overridden, not
        accepted, because producing a plausible number from the wrong units is
        the failure this file exists to remove."""
        src = (_SCRIPTS / "calibration_bookmaker_cell_fold.py").read_text()
        assert 'a.grain = "game_bucket"' in src

    def test_the_game_bucket_tail_groups_by_the_pair(self):
        tail = bmk.TAILS["game_bucket"]
        assert "GROUP BY event_id, bucket_idx" in tail
        # The same published-price filter as every other tail on this rail:
        # a grain that admitted rows the others exclude would measure the SE
        # of a population the board does not print.
        assert "prob > 0.01 AND prob < 0.99" in tail
        assert bmk.TAILS["bucket"].count("prob > 0.01 AND prob < 0.99") == 1
