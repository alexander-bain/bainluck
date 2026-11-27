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

from collections import Counter
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
APP_ROOT = REPO / "ios/Bain Luck/Bain Luck"
VIEW = APP_ROOT / "Components/RelatedFuturesView.swift"
FORMATTING = APP_ROOT / "Utilities/FormattingUtilities.swift"

# The seven text sites converted by UX-P217, each pinned INDIVIDUALLY.
#
# 🔴 CERT-550: A GLOBAL COUNT IS A COMPENSATING GUARD.  This started life as
# `count(formatProbabilityOrDash) == 7`, and the cert broke it in one move:
# restore the award-row `0%` defect AND add the helper at an already-safe
# `if let` site.  Net count still 7, all ten tests still green, defect back on
# screen.  A count cannot tell WHICH sites are wired — only how many calls
# exist somewhere in the file.
#
# Each site is now anchored by a snippet that includes a neighbouring line
# unique to it (its font, or its argument), so restoring any ONE site fails
# regardless of what is added anywhere else.  The count is kept as a
# SUPPLEMENTARY check for additions, not as the load-bearing one.
CONVERTED_SITES = [
    (
        "settledProbabilityText — the shared helper behind 3 render sites",
        "    return formatProbabilityOrDash(f.probability)",
    ),
    (
        "award-row percent (the site CERT-550 restored)",
        "Text(formatProbabilityOrDash(award.future.probability))",
    ),
    (
        "team-futures bar percent, 11pt monospaced",
        "Text(formatProbabilityOrDash(future.probability))\n"
        "                                    .font(.system(size: 11, weight: .black, design: .monospaced))",
    ),
    (
        "28pt team-colour hero",
        "Text(formatProbabilityOrDash(future.probability))\n"
        "                                .font(.system(size: 28, weight: .bold, design: .rounded))",
    ),
    (
        "title3 row",
        "Text(formatProbabilityOrDash(future.probability))\n"
        "                            .font(.title3)",
    ),
    (
        "GameCell 13pt percent",
        "Text(formatProbabilityOrDash(future.probability))\n"
        "                                .font(.system(size: 13, weight: .bold, design: .rounded))",
    ),
    (
        "StatGauge dial percent",
        "Text(formatProbabilityOrDash(probability))",
    ),
]

EXPECTED_ORDASH_SITES = 7

# The two percent renders that are correctly guarded by `if let` and must STAY
# inside `if let` (never converted to `formatProbabilityOrDash`, never given a
# `?? 0` default) because they render nothing when the price is absent. They
# were updated from hand-rolled `Int(prob * 100)` / `Int((prob * 100).rounded())`
# (which floored 0.6% to "0%" or rounded it to "1%") to `formatProbability(prob)`
# so sub-1% probabilities print "<1%" inside those same `if let` blocks.
GUARDED_PERCENT_RENDERS = [
    (
        "if let prob = future.probability {\n"
        "                                Text(formatProbability(prob))\n"
        "                                    .font(.system(size: 10, weight: .semibold))"
    ),
    (
        "if let prob = outcome.probability {\n"
        "                                Text(formatProbability(prob))\n"
        "                                    .font(.caption)\n"
        "                                    .fontWeight(.bold)"
    ),
]


def _strip_comments(src: str) -> str:
    """Drop `//` and `/* ... */` comments without touching string literals.

    Handles ESPN/asset `https://` URLs inside string literals and string
    interpolations containing nested quotes so comment stripping never truncates
    real Swift code or lets a prose comment hide/satisfy a scanner assertion.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    block_depth = 0
    in_line_comment = False
    # Track string mode alongside paren nesting so `"...\("inner")..."` exits
    # the outer string only at matching interpolation depth.
    string_paren_depths: list[int] = []
    triple_string = False
    paren_depth = 0

    while i < n:
        ch = src[i]
        nxt = src[i + 1 : i + 2]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if block_depth > 0:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
            elif ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
            else:
                if ch == "\n":
                    out.append(ch)
                i += 1
            continue

        if string_paren_depths and paren_depth == string_paren_depths[-1]:
            if ch == "\\" and nxt == "(":
                out.append("\\(")
                paren_depth += 1
                i += 2
                continue
            if ch == "\\" and i + 1 < n:
                out.append(src[i : i + 2])
                i += 2
                continue
            if triple_string and src[i : i + 3] == '"""':
                out.append('"""')
                string_paren_depths.pop()
                triple_string = False
                i += 3
                continue
            if not triple_string and ch == '"':
                out.append('"')
                string_paren_depths.pop()
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            i += 2
            continue
        if src[i : i + 3] == '"""':
            out.append('"""')
            string_paren_depths.append(paren_depth)
            triple_string = True
            i += 3
            continue
        if ch == '"':
            out.append('"')
            string_paren_depths.append(paren_depth)
            i += 1
            continue
        if ch == "(":
            paren_depth += 1
        elif ch == ")" and paren_depth > 0:
            paren_depth -= 1
        out.append(ch)
        i += 1

    return "".join(out)


def _extract_balanced_text_calls(code: str) -> list[tuple[int, str]]:
    """Extract balanced `(line_number, full_Text_call_text)` spans from comment-free Swift."""
    spans: list[tuple[int, str]] = []
    n = len(code)
    for m in re.finditer(r"(?<![A-Za-z0-9_])Text\s*\(", code):
        start = m.start()
        j = m.end() - 1
        paren_depth = 0
        string_paren_depths: list[int] = []
        triple_string = False

        while j < n:
            ch = code[j]
            if string_paren_depths and paren_depth == string_paren_depths[-1]:
                if ch == "\\" and code[j + 1 : j + 2] == "(":
                    paren_depth += 1
                    j += 2
                    continue
                if ch == "\\" and j + 1 < n:
                    j += 2
                    continue
                if triple_string and code[j : j + 3] == '"""':
                    string_paren_depths.pop()
                    triple_string = False
                    j += 3
                    continue
                if not triple_string and ch == '"':
                    string_paren_depths.pop()
                    j += 1
                    continue
                j += 1
                continue

            if code[j : j + 3] == '"""':
                string_paren_depths.append(paren_depth)
                triple_string = True
                j += 3
                continue
            if ch == '"':
                string_paren_depths.append(paren_depth)
                j += 1
                continue
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    j += 1
                    break
            j += 1

        line_no = code[:start].count("\n") + 1
        spans.append((line_no, code[start:j]))
    return spans


HAND_ROLLED_PERCENT_IN_TEXT_RE = re.compile(
    r"(?:\bInt\b|\bround)\s*\([^;]*?\*\s*100(?:\.0)?\b"
)


def _find_hand_rolled_text_percents(src: str) -> list[tuple[int, str]]:
    """Return `(line, normalized_Text_call)` for any `Text(...)` computing a percent via `* 100`."""
    code = _strip_comments(src)
    hits: list[tuple[int, str]] = []
    for line_no, span in _extract_balanced_text_calls(code):
        if "%" in span and HAND_ROLLED_PERCENT_IN_TEXT_RE.search(span):
            hits.append((line_no, " ".join(span.split())))
    return hits


# Exact non-probability exceptions under `ios/Bain Luck/Bain Luck/`.
# Keyed by `(rel_path, normalized_Text_call) -> expected_count` so no whole
# file is exempted and zero market-probability renders are allow-listed.
NON_PROBABILITY_HAND_ROLLED_TEXT_ALLOWLIST: dict[tuple[str, str], int] = {
    # Swift Charts Y-axis tick labels must show exact scale origins ("0%", "50%", "100%").
    (
        "Components/EventAtlasGolfTournament11666.swift",
        'Text("\\(Int((d * 100).rounded()))%")',
    ): 2,
    (
        "Components/MLBFinalCards11284.swift",
        'Text("\\(Int((v * 100).rounded()))%")',
    ): 1,
    (
        "Components/MLBFinalCards11284.swift",
        'Text("\\(Int((chance * 100).rounded()))%")',
    ): 1,
    (
        "Components/NBAEventCards9483.swift",
        'Text("\\(Int((chance * 100).rounded()))%")',
    ): 1,
    (
        "Components/NFLEventCards9483.swift",
        'Text("\\(Int((chance * 100).rounded()))%")',
    ): 1,
    (
        "Components/PlayerMilestoneProfileView.swift",
        'Text("\\(Int((chance * 100).rounded()))%")',
    ): 1,
    (
        "Components/RaceChartView.swift",
        'Text("\\(Int((value * 100).rounded()))%")',
    ): 1,
    # Signed 24h delta badge (`MovementBadge`, gated by `abs(m) >= 0.01`, point move not chance).
    (
        "Views/DiscoverView.swift",
        'Text("\\(abs(Int((m * 100).rounded())))%")',
    ): 1,
    # User prediction hit-rate accuracy ratios (`correct / total` legitimately spans 0%..100%).
    (
        "Views/MyStuffView.swift",
        'Text("\\(Int(stats.accuracy * 100))%")',
    ): 1,
    (
        "Views/PredictionStatsView.swift",
        'Text("\\(Int(stats.accuracy * 100))%")',
    ): 1,
    (
        "Views/PredictionStatsView.swift",
        'Text("\\(Int(data.accuracy * 100))%")',
    ): 1,
}


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

    def test_each_converted_site_is_individually_still_wired(self):
        """The load-bearing check. One assertion per site, anchored so that
        restoring any single one fails no matter what is added elsewhere."""
        code = _view_code()
        missing = [name for name, snippet in CONVERTED_SITES if snippet not in code]
        assert missing == [], (
            "these render sites are no longer wired to formatProbabilityOrDash, "
            f"so they print an invented number for a priceless row: {missing}"
        )

    def test_the_two_guarded_renders_stay_hand_rolled(self):
        """The other half of CERT-550's compensating move: it satisfied the
        count by converting an `if let` site. Those must stay inside `if let`
        with `formatProbability(prob)` (no `formatProbabilityOrDash`, no `?? 0`
        default) — they render nothing when absent while printing `<1%` under 1%."""
        code = _view_code()
        for snippet in GUARDED_PERCENT_RENDERS:
            assert snippet in code, (
                f"a correctly `if let`-guarded percent render was rewritten: {snippet}"
            )

    def test_helper_call_count_has_not_drifted(self):
        """Supplementary, NOT load-bearing (see CERT-550). Catches a NEW render
        that skips the helper; it cannot catch a swap, which is what the
        per-site anchors above are for."""
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

    def test_planted_hand_rolled_percent_in_text_is_detected(self):
        """Scanning `ios/Bain Luck/Bain Luck/` must catch every floor and rounded mutant."""
        mutants = [
            'if let prob = future.probability {\n    Text("\\(Int(prob * 100))%")\n}',
            'Text("\\(Int((prob * 100).rounded()))%")',
            'Text(\n    "\\(Int((prob * 100.0).rounded()))%"\n)',
            'Text("Based on \\(Int(round(prob * 100)))% chance")',
            'Text("\\(label ?? "fallback"): \\(Int(prob * 100))%")',
        ]
        for mutant in mutants:
            assert _find_hand_rolled_text_percents(mutant), f"missed mutant: {mutant!r}"

        safe = [
            '// Text("\\(Int(prob * 100))%")\nText(formatProbability(prob))',
            '/* Text("\\(Int((prob * 100).rounded()))%") */\nText(formatProbabilityOrDash(prob))',
        ]
        for snippet in safe:
            assert _find_hand_rolled_text_percents(snippet) == [], (
                f"false positive on {snippet!r}"
            )


class TestNoViewHandRollsProbabilityPercent:
    """Class-level guard (#13892): no view in the app may build a probability
    percent inside `Text(...)` with `Int(... * 100)` or `.rounded()` by hand."""

    def test_no_view_hand_rolls_a_probability_percent(self):
        found_counts: Counter[tuple[str, str]] = Counter()
        unexpected: list[str] = []

        for path in sorted(APP_ROOT.rglob("*.swift")):
            rel = path.relative_to(APP_ROOT).as_posix()
            for line_no, norm_text in _find_hand_rolled_text_percents(path.read_text()):
                key = (rel, norm_text)
                found_counts[key] += 1
                expected = NON_PROBABILITY_HAND_ROLLED_TEXT_ALLOWLIST.get(key, 0)
                if found_counts[key] > expected:
                    unexpected.append(f"{rel}:{line_no}: {norm_text}")

        assert unexpected == [], (
            "SwiftUI view hand-rolls a percent inside Text(...) using `* 100`; "
            "route probability displays through `formatProbability(...)` or "
            "`formatProbabilityOrDash(...)` so 0.1%..0.99% reads `<1%`: "
            f"{unexpected}"
        )

        drift = {
            key: (expected, found_counts[key])
            for key, expected in NON_PROBABILITY_HAND_ROLLED_TEXT_ALLOWLIST.items()
            if found_counts[key] != expected
        }
        assert drift == {}, (
            "Non-probability allow-list entries drifted from source counts: "
            f"{drift}"
        )


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
