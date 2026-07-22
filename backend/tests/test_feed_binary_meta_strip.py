"""#235 Item 2: a Yes/No parent binary must never be merged into a candidate field.

A non-neg-risk Polymarket event ("Who will Taylor Swift's bridesmaids be?") folds
its base "will it happen at all" Yes/No sub-market onto the same parent market as the
nominee sub-markets, so the card mixes "No 64.5% / Yes 35.5%" with a nominee list.
`_strip_mixed_binary_meta` removes the generic Yes/No from the candidate distribution
when — and only when — there is a real candidate list to segregate it from.
"""

from types import SimpleNamespace

from app.routes.feed import _strip_mixed_binary_meta


def _o(name, prob):
    return SimpleNamespace(name=name, current_probability=prob)


class TestStripMixedBinaryMeta:
    def test_strips_yes_no_from_mixed_nominee_field(self):
        outcomes = [
            _o("No", 0.645),
            _o("Yes", 0.355),
            _o("Gigi Hadid", 0.0035),
            _o("Selena Gomez", 0.0005),
            _o("Blake Lively", 0.0005),
        ]
        kept = _strip_mixed_binary_meta(outcomes)
        names = {getattr(o, "name") for o in kept}
        assert "Yes" not in names and "No" not in names
        assert {"Gigi Hadid", "Selena Gomez", "Blake Lively"} <= names
        assert len(kept) == 3

    def test_pure_binary_market_is_untouched(self):
        # A real Yes/No market (no named candidates) keeps both sides.
        outcomes = [_o("Yes", 0.62), _o("No", 0.38)]
        kept = _strip_mixed_binary_meta(outcomes)
        assert len(kept) == 2
        assert {getattr(o, "name") for o in kept} == {"Yes", "No"}

    def test_single_candidate_plus_binary_is_untouched(self):
        # Only one named candidate → not a candidate *field*; leave as-is so we
        # never accidentally empty a two-outcome card down to one.
        outcomes = [_o("Yes", 0.5), _o("No", 0.5), _o("Some Entity", 0.1)]
        kept = _strip_mixed_binary_meta(outcomes)
        assert len(kept) == 3

    def test_candidate_only_field_is_untouched(self):
        outcomes = [_o("Alice", 0.4), _o("Bob", 0.35), _o("Carol", 0.25)]
        kept = _strip_mixed_binary_meta(outcomes)
        assert len(kept) == 3

    def test_case_and_whitespace_insensitive(self):
        outcomes = [_o(" yes ", 0.3), _o("NO", 0.7), _o("Cand A", 0.01), _o("Cand B", 0.01)]
        kept = _strip_mixed_binary_meta(outcomes)
        assert {getattr(o, "name") for o in kept} == {"Cand A", "Cand B"}
