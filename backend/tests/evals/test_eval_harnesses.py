from pathlib import Path

from scripts.evals.calibrate_interestingness import auc, fit_weights, signal_rows, verdict_label
from scripts.evals.rater_reliability import agreement_report, inject_probes
from scripts.evals.search_gold_eval import parse_gold_markdown


def test_label_pass_decisions_map_to_target_interestingness():
    assert verdict_label({"decision": "accepted_promote"}) == 1
    assert verdict_label({"decision": "rejected_downrank"}) == 1
    assert verdict_label({"decision": "accepted_downrank"}) == 0
    assert verdict_label({"decision": "rejected_promote"}) == 0


def test_fit_and_auc_on_separable_fixture():
    rows = [
        {"label": "interesting", "movement_24h": .30, "volume_24h": 100000},
        {"label": "interesting", "movement_24h": .20, "volume_24h": 50000},
        {"label": "boring", "movement_24h": 0, "volume_24h": 0},
        {"label": "boring", "movement_24h": .01, "volume_24h": 10},
    ]
    samples = signal_rows(rows)
    fitted = fit_weights(samples)
    assert fitted.total > 0
    assert auc([1, 1, 0, 0], [1, .8, .2, 0]) == 1


def test_gold_parser_reads_coverage_and_real_halves():
    # The full gold set lives under the gitignored .claude/handoff/ dir, so CI
    # parses a small COMMITTED sample instead (Queue #250). The sample mirrors the
    # coverage + real-half format so the parser is exercised for real in CI rather
    # than skipped (skipping turned master red riding an unrelated push, Queue #249).
    path = Path(__file__).parent / "fixtures" / "gold_queries_sample.md"
    rows = parse_gold_markdown(path)
    queries = {row["query"] for row in rows}
    # coverage half (team pages) + both real-half recents lists
    assert "red sox" in queries
    assert "Golf" in queries
    assert "Where will Taylor Swift and Travis Kelce's Wedding occur?" in queries


def test_rater_agreement_and_probes():
    rows = [
        {"item_id": 1, "reviewer": "a", "label": 1, "known_answer": 1},
        {"item_id": 1, "reviewer": "b", "label": 1},
        {"item_id": 2, "reviewer": "a", "label": 0, "known_answer": 1},
        {"item_id": 2, "reviewer": "b", "label": 1},
    ]
    report = agreement_report(rows)
    assert report["pairwise"]["a vs b"]["agreement"] == .5
    assert report["raters"]["a"]["probe_accuracy"] == .5
    assert len(inject_probes([{"id": 1}, {"id": 2}], [{"probe_id": "p"}], 1)) == 4
