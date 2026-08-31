"""UX-P217 — the native related-futures rows must not invent a price they lack.

`RelatedFuture.probability` is optional because the backend sends `null` for a
market with no current price.  `RelatedFuturesView` used to spell every text
render `future.probability ?? 0` and hand the result to `formatProbability`,
which returns "<1%" for zero.  A row whose price never arrived therefore made a
confident claim that the outcome was nearly impossible — at 28pt bold in team
colour on two of the seven sites.  The hand-rolled `Int(p * 100)%` sites printed
a flat "0%", the same lie with worse rounding.

The behaviour lives in `formatProbabilityOrDash` and is pinned by
`BainLuckTests/MissingProbabilityRenderTests.swift`.  Those Swift tests cannot
reach the five sites that are inline in SwiftUI view bodies, so THIS file is the
containment guard for the wiring: it reads the shipped Swift source and asserts
that no probability text render coerces a nil away.

Why the source is stripped of comments first: the fix's own explanatory comments
legitimately quote the banned `?? 0` spelling while explaining where it is still
correct (geometry and booleans).  A guard that scanned raw bytes would fail on
the prose describing it — and, worse, could be silenced by deleting a comment.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
VIEW = REPO / "ios/Bain Luck/Bain Luck/Components/RelatedFuturesView.swift"
FORMATTING = REPO / "ios/Bain Luck/Bain Luck/Utilities/FormattingUtilities.swift"

# The seven text sites converted by UX-P217.  An EXACT count, not a floor: a new
# probability render that skips the helper should fail here, and so should the
# silent deletion of one that has it.
EXPECTED_ORDASH_SITES = 7


def _strip_comments(src: str) -> str:
    """Drop `//` comments without touching `//` inside a string literal.

    The file contains an ESPN headshot URL, so a naive split on `//` would
    truncate a real line of code.
    """
    out = []
    for line in src.splitlines():
        in_string = False
        escaped = False
        cut = len(line)
        for i, ch in enumerate(line):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string and ch == "/" and line[i + 1 : i + 2] == "/":
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def _view_code() -> str:
    return _strip_comments(VIEW.read_text())


class TestNoTextRenderInventsAProbability:
    """The class: a nil price may never reach a formatter as a number."""

    def test_no_text_render_coerces_a_nil_probability(self):
        offenders = [
            line.strip()
            for line in _view_code().splitlines()
            if "Text(" in line and re.search(r"probability\s*\?\?", line)
        ]
        assert offenders == [], (
            "a probability text render is coercing nil away; use "
            "formatProbabilityOrDash so the row prints the absent marker: "
            f"{offenders}"
        )

    def test_format_probability_is_never_given_a_nil_default(self):
        """`formatProbability(x ?? 0)` IS the defect — zero formats as '<1%'."""
        offenders = [
            line.strip()
            for line in _view_code().splitlines()
            if re.search(r"\bformatProbability\([^)]*\?\?", line)
        ]
        assert offenders == [], (
            "formatProbability was handed a nil default, which renders '<1%' "
            f"for a row with no price: {offenders}"
        )

    def test_the_gauge_is_handed_the_optional_not_a_substitute(self):
        """StatGauge prints its own percent, so it must receive the optional."""
        code = _view_code()
        assert re.search(r"StatGauge\(probability:\s*future\.probability\s*,", code), (
            "StatGauge must be passed the raw optional so it can draw no arc "
            "and print the absent marker"
        )
        assert not re.search(r"StatGauge\(probability:[^,]*\?\?", code)

    def test_every_converted_site_is_still_wired_to_the_helper(self):
        count = len(re.findall(r"\bformatProbabilityOrDash\(", _view_code()))
        assert count == EXPECTED_ORDASH_SITES, (
            f"expected {EXPECTED_ORDASH_SITES} nil-aware probability renders in "
            f"RelatedFuturesView, found {count}. If a render was added or "
            "removed on purpose, update EXPECTED_ORDASH_SITES deliberately."
        )


class TestTheGuardCanActuallyFail:
    """A containment guard that cannot fail is decoration.

    Each check is re-run against a planted violation to prove the pattern
    matches the shape it claims to match, rather than passing vacuously.
    """

    def test_planted_coercion_is_detected(self):
        planted = 'Text(formatProbability(future.probability ?? 0))'
        assert "Text(" in planted and re.search(r"probability\s*\?\?", planted)
        assert re.search(r"\bformatProbability\([^)]*\?\?", planted)

    def test_planted_gauge_coercion_is_detected(self):
        planted = "StatGauge(probability: future.probability ?? 0, teamColor: c)"
        assert re.search(r"StatGauge\(probability:[^,]*\?\?", planted)

    def test_comment_stripper_keeps_code_and_drops_prose(self):
        src = '// probability ?? 0 in prose\nlet u = "https://x/y" // tail\n'
        stripped = _strip_comments(src)
        assert "prose" not in stripped, "a comment must not satisfy the guard"
        assert '"https://x/y"' in stripped, "a URL is not a comment"
        assert "tail" not in stripped


class TestTheFormatterItself:
    """The Swift unit tests own the behaviour; this pins that it exists at all,
    so the containment checks above cannot be satisfied by a stub."""

    def test_helper_returns_the_absent_marker_for_nil(self):
        src = FORMATTING.read_text()
        assert "func formatProbabilityOrDash(_ value: Double?" in src
        body = src.split("func formatProbabilityOrDash(", 1)[1]
        assert "guard let value else { return absentProbabilityMarker }" in body
        assert "return formatProbability(value" in body, (
            "the helper must DELEGATE to formatProbability for real values "
            "rather than reimplementing the <1%/>99% rules"
        )

    def test_absent_marker_is_an_em_dash(self):
        src = FORMATTING.read_text()
        assert 'let absentProbabilityMarker = "\\u{2014}"' in src


class TestGuardedSitesWereNotDisturbed:
    """Five sites already used `if let prob = future.probability` — the file's own
    convention, and the reason the defect was survivable elsewhere.  The fix must
    not have quietly rewritten them into the helper (which would change their
    layout, since they render nothing at all when the price is absent)."""

    def test_if_let_sites_are_intact(self):
        code = _view_code()
        assert code.count("if let prob = future.probability") == 5
        assert code.count("if let prob = outcome.probability") == 1
