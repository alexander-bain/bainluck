"""UX-1052 item 2 — an exact-score outcome is labelled with its scoreline, never "≥ N".

THE DEFECT, VERBATIM. Alex, shopping ``/sports`` at 1:00pm PT on 2026-09-03:

    "The exact-score ladders are broken. Player Props cards ('Villarreal vs
     Deportivo — Exact Score') show rungs '≥ 0, ≥ 1, ≥ 2, ≥ 2' and '≥ 0, ≥ 0,
     ≥ 0, ≥ 1' at 1–6% — rung labels are not the outcomes. Show the real
     scorelines or the real thresholds; a rung that cannot be labelled is not
     rendered."

THE MECHANISM, from the served payload (``GET /api/futures/grouped-feed
?sports_only=true&limit=20``, read 2026-09-03): 8 of 20 rows were Polymarket
"Exact Score" groups whose outcome names are ``"AC Milan 2 - 3 Sport Lisboa e
Benfica"``. ``_THRESHOLD_SIMPLE_RE`` accepts a **bare hyphen** as a threshold
suffix (it was written for "80-" style tails), so every one of those names
matched on its FIRST integer and came back as ``(2.0, "", "above")``. The
ladder then printed "≥ 2" — and because four scorelines share a home score, it
printed "≥ 3" four times in a row on the Sturm Graz card.

Two numbers and no direction is not a threshold in either direction. The parser
must REFUSE, which is what ``extract_scoreline`` is for, and the group must keep
its card with real labels, which is what ``detect_exact_score_groups`` is for.

RED-FIRST. Every assertion in ``TestScorelineIsNotAThreshold`` fails on the
parent commit: ``extract_threshold("AC Milan 2 - 3 Benfica")`` returned
``(2.0, "", "above")`` there.

THE CONTROL ARM MATTERS AS MUCH AS THE FIX. A refusal that is even slightly too
wide silently deletes real threshold rungs from CPI ladders, temperature buckets
and MLB hit props — a quieter regression than the one being fixed and harder to
see. ``TestRealThresholdsStillParse`` is that control, and it is not decorative:
the scoreline pattern deliberately requires a non-digit on both sides so
"2.5-3.5" and "1-0 or more" cannot be mistaken for scorelines.
"""

import pytest

from app.utils.market_grouping import (
    detect_exact_score_groups,
    detect_threshold_groups,
    extract_scoreline,
    extract_threshold,
)


# Real outcome names, copied from the served payload on 2026-09-03.
LIVE_EXACT_SCORE_NAMES = [
    "AC Milan 0 - 3 Sport Lisboa e Benfica",
    "AC Milan 1 - 3 Sport Lisboa e Benfica",
    "AC Milan 2 - 2 Sport Lisboa e Benfica",
    "AC Milan 2 - 3 Sport Lisboa e Benfica",
    "AC Milan 3 - 3 Sport Lisboa e Benfica",
]


class TestScorelineIsNotAThreshold:
    @pytest.mark.parametrize("name", LIVE_EXACT_SCORE_NAMES)
    def test_extract_threshold_refuses_a_scoreline(self, name):
        assert extract_threshold(name) is None, (
            f"{name!r} parsed as a threshold — this is the '≥ 2' rung Alex saw"
        )

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("AC Milan 0 - 3 Sport Lisboa e Benfica", (0, 3)),
            ("FC Emmen 1 - 1 FC Volendam", (1, 1)),
            ("SK Puntigamer Sturm Graz 3 - 2 Stade Rennais FC 1901", (3, 2)),
            # en dash and em dash, and the no-spaces spelling
            ("Team A 2–1 Team B", (2, 1)),
            ("Team A 2—1 Team B", (2, 1)),
            ("Team A 4-0 Team B", (4, 0)),
        ],
    )
    def test_extract_scoreline_reads_both_numbers(self, name, expected):
        assert extract_scoreline(name) == expected

    def test_the_whole_group_stops_becoming_a_threshold_ladder(self):
        outcomes = [
            {"id": i, "name": n, "market_id": 7, "group_id": "polymarket:960217",
             "market_name": "AC Milan vs. Sport Lisboa e Benfica - Exact Score",
             "probability": 0.07}
            for i, n in enumerate(LIVE_EXACT_SCORE_NAMES)
        ]
        assert detect_threshold_groups(outcomes) == {}


class TestExactScoreGroupsAreLabelled:
    def _outcomes(self):
        # Probabilities differ so ordering is observable; 2-2 is the favourite.
        probs = [0.07, 0.07, 0.085, 0.07, 0.06]
        return [
            {"id": 100 + i, "name": n, "market_id": 7,
             "group_id": "polymarket:960217",
             "market_name": "AC Milan vs. Sport Lisboa e Benfica - Exact Score",
             "probability": p}
            for i, (n, p) in enumerate(zip(LIVE_EXACT_SCORE_NAMES, probs))
        ]

    def test_every_rung_label_is_the_actual_scoreline(self):
        groups = detect_exact_score_groups(self._outcomes())
        assert list(groups) == ["group:polymarket:960217"]
        labels = [o["score_label"] for o in groups["group:polymarket:960217"]]
        assert set(labels) == {"0–3", "1–3", "2–2", "2–3", "3–3"}
        # And no label is a threshold claim.
        assert not any("≥" in x or "≤" in x for x in labels)

    def test_labels_are_distinct_which_is_the_visible_symptom(self):
        # "≥ 3, ≥ 3, ≥ 3, ≥ 3" was the Sturm Graz card. Distinctness is the
        # property a reader actually checks.
        groups = detect_exact_score_groups(self._outcomes())
        labels = [o["score_label"] for o in groups["group:polymarket:960217"]]
        assert len(set(labels)) == len(labels)

    def test_most_likely_scoreline_leads(self):
        groups = detect_exact_score_groups(self._outcomes())
        assert groups["group:polymarket:960217"][0]["score_label"] == "2–2"

    def test_a_lone_scoreline_is_not_a_group(self):
        one = self._outcomes()[:1]
        assert detect_exact_score_groups(one) == {}

    def test_scorelines_with_no_parent_context_are_refused_not_pooled(self):
        # #1102: pooling context-free outcomes across unrelated games is the
        # defect that scoping was introduced to kill. A bare scoreline carries
        # no game, so it is dropped rather than grouped with a stranger's.
        naked = [
            {"id": 1, "name": "2 - 1", "market_id": 1, "probability": 0.1},
            {"id": 2, "name": "3 - 1", "market_id": 2, "probability": 0.1},
        ]
        assert detect_exact_score_groups(naked) == {}

    def test_two_different_games_get_two_cards(self):
        a = self._outcomes()
        b = [
            {"id": 200 + i, "name": n, "market_id": 8,
             "group_id": "polymarket:960245",
             "market_name": "OFI vs. TSG Hoffenheim - Exact Score",
             "probability": 0.05}
            for i, n in enumerate(["OFI 2 - 2 TSG 1899 Hoffenheim",
                                   "OFI 3 - 0 TSG 1899 Hoffenheim"])
        ]
        groups = detect_exact_score_groups(a + b)
        assert set(groups) == {"group:polymarket:960217", "group:polymarket:960245"}


class TestTennisExactMatchScoreNamesItsWinner:
    """The SECOND shape on the same strip, and the reason a bare score is not
    always enough. Polymarket tennis serves "Iva Jovic wins 2-1" — labelling
    that "2–1" collides with "Magdalena Frech wins 2-1", which is the very
    defect being fixed, one layer down. Payload read 2026-09-03."""

    def _outcomes(self):
        rows = [
            ("Iva Jovic wins 2-0", 0.99),
            ("Iva Jovic wins 2-1", 0.01),
            ("Magdalena Frech wins 2-0", 0.01),
            ("Magdalena Frech wins 2-1", 0.01),
        ]
        return [
            {"id": 300 + i, "name": n, "market_id": 9, "group_id": "polymarket:tennis-1",
             "market_name": "Iva Jovic vs Magdalena Frech: Exact Match Score",
             "probability": p}
            for i, (n, p) in enumerate(rows)
        ]

    def test_the_winner_is_in_the_label(self):
        groups = detect_exact_score_groups(self._outcomes())
        labels = {o["score_label"] for o in groups["group:polymarket:tennis-1"]}
        assert labels == {
            "Iva Jovic 2–0", "Iva Jovic 2–1",
            "Magdalena Frech 2–0", "Magdalena Frech 2–1",
        }

    def test_no_two_rungs_share_a_label(self):
        groups = detect_exact_score_groups(self._outcomes())
        labels = [o["score_label"] for o in groups["group:polymarket:tennis-1"]]
        assert len(set(labels)) == 4

    def test_the_99_percent_outcome_leads(self):
        groups = detect_exact_score_groups(self._outcomes())
        assert groups["group:polymarket:tennis-1"][0]["score_label"] == "Iva Jovic 2–0"

    @pytest.mark.parametrize("name", [
        "Iva Jovic wins 2-1",
        "Zizou Bergs wins 3-1",
        "Jesper De Jong wins 3-2",
    ])
    def test_these_are_refused_as_thresholds_too(self, name):
        assert extract_threshold(name) is None


class TestRealThresholdsStillParse:
    """The control. A refusal that is too wide is the same bug pointed the
    other way — it deletes rungs from every genuine ladder on the site."""

    @pytest.mark.parametrize(
        "name,value",
        [
            ("Will Bitcoin exceed $80,000?", 80000.0),
            ("33°F or below", 33.0),
            ("Over 100.5 points", 100.5),
            ("At least 250", 250.0),
            ("2.5 or more goals", 2.5),
            # A decimal range must NOT read as a scoreline (digits on both
            # sides of the dash are guarded by the surrounding non-digit rule).
            ("Over 2.5 goals", 2.5),
        ],
    )
    def test_threshold_names_still_yield_a_threshold_control(self, name, value):
        parsed = extract_threshold(name)
        assert parsed is not None, f"{name!r} lost its threshold"
        assert parsed[0] == value

    @pytest.mark.parametrize("name", [
        # An ISO date is three integers joined by dashes. The scoreline pattern
        # must not read "09-03" out of it and refuse the whole name.
        "Resolves 2026-09-03",
        "Between 2026-01-01 and 2026-12-31",
    ])
    def test_an_iso_date_is_not_a_scoreline(self, name):
        assert extract_scoreline(name) is None

    @pytest.mark.parametrize(
        "name,value",
        [
            ("Will Bitcoin exceed $80,000?", 80000.0),
            ("Over 100.5 points", 100.5),
        ],
    )
    def test_threshold_names_still_yield_a_threshold(self, name, value):
        parsed = extract_threshold(name)
        assert parsed is not None, f"{name!r} lost its threshold"
        assert parsed[0] == value

    def test_a_real_threshold_group_still_forms(self):
        outcomes = [
            {"id": 1, "name": "Over 2.5 goals", "market_id": 3,
             "market_name": "Total Goals", "probability": 0.5},
            {"id": 2, "name": "Over 3.5 goals", "market_id": 3,
             "market_name": "Total Goals", "probability": 0.3},
        ]
        groups = detect_threshold_groups(outcomes)
        assert groups, "the control ladder disappeared"
        values = [o["threshold_value"] for g in groups.values() for o in g]
        assert values == [2.5, 3.5]

    def test_a_real_threshold_is_not_an_exact_score(self):
        outcomes = [
            {"id": 1, "name": "Over 2.5 goals", "market_id": 3,
             "market_name": "Total Goals", "group_id": "g", "probability": 0.5},
            {"id": 2, "name": "Over 3.5 goals", "market_id": 3,
             "market_name": "Total Goals", "group_id": "g", "probability": 0.3},
        ]
        assert detect_exact_score_groups(outcomes) == {}
