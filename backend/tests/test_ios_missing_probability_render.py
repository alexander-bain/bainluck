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


def _extract_string_literals(code: str) -> list[tuple[int, str]]:
    """Extract every Swift string literal `(line_number, raw_literal)` from comment-free code.

    Handles `\"\"\"...\"\"\"` multi-line strings, `\"...\"` single-line strings,
    and nested quotes inside `\\(...)` interpolations.
    """
    literals: list[tuple[int, str]] = []
    n = len(code)
    i = 0

    while i < n:
        ch = code[i]
        if code[i : i + 3] == '"""' or ch == '"':
            triple = code[i : i + 3] == '"""'
            start = i
            i += 3 if triple else 1
            paren_depth = 0
            string_paren_depths = [0]

            while i < n:
                c = code[i]
                if string_paren_depths and paren_depth == string_paren_depths[-1]:
                    if c == "\\" and code[i + 1 : i + 2] == "(":
                        paren_depth += 1
                        i += 2
                        continue
                    if c == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if triple and len(string_paren_depths) == 1 and code[i : i + 3] == '"""':
                        i += 3
                        string_paren_depths.pop()
                        break
                    if (not triple or len(string_paren_depths) > 1) and c == '"':
                        i += 1
                        string_paren_depths.pop()
                        if not string_paren_depths:
                            break
                        continue
                    i += 1
                    continue

                if code[i : i + 3] == '"""':
                    string_paren_depths.append(paren_depth)
                    i += 3
                    continue
                if ch == '"' and c == '"':
                    string_paren_depths.append(paren_depth)
                    i += 1
                    continue
                if c == '"':
                    string_paren_depths.append(paren_depth)
                    i += 1
                    continue
                if c == "(":
                    paren_depth += 1
                elif c == ")" and paren_depth > 0:
                    paren_depth -= 1
                i += 1

            line_no = code[:start].count("\n") + 1
            literals.append((line_no, code[start:i]))
            continue
        i += 1

    return literals


HAND_ROLLED_PERCENT_IN_STRING_RE = re.compile(
    r"(?:\bInt\b|\bround)\s*\([^;]*?\*\s*100(?:\.0)?\b"
)


def _find_hand_rolled_percent_strings(src: str) -> list[tuple[int, str]]:
    """Return `(line, normalized_literal)` for ANY Swift string computing a percent via `* 100`."""
    code = _strip_comments(src)
    hits: list[tuple[int, str]] = []
    for line_no, literal in _extract_string_literals(code):
        if "%" in literal and HAND_ROLLED_PERCENT_IN_STRING_RE.search(literal):
            hits.append((line_no, " ".join(literal.split())))
    return hits


# Exact non-probability exceptions under `ios/Bain Luck/Bain Luck/`.
# Keyed by `(rel_path, normalized_string_literal) -> expected_count` so no whole
# file is exempted and zero market-probability formatters/strings are allow-listed.
NON_PROBABILITY_HAND_ROLLED_STRING_ALLOWLIST: dict[tuple[str, str], int] = {
    # 10 chart Y-axis scale ticks (`0%`..`100%` scale marks, never outcome probabilities;
    # verified `OddsChartView.axisLabel(for:)` only renders Y-axis ticks via `RacingWinPodiumAdapter10868`).
    (
        "Components/EventAtlasGolfTournament11666.swift",
        '"\\(Int((d * 100).rounded()))%"',
    ): 2,
    (
        "Components/MLBFinalCards11284.swift",
        '"\\(Int((v * 100).rounded()))%"',
    ): 1,
    (
        "Components/MLBFinalCards11284.swift",
        '"\\(Int((chance * 100).rounded()))%"',
    ): 1,
    (
        "Components/NBAEventCards9483.swift",
        '"\\(Int((chance * 100).rounded()))%"',
    ): 1,
    (
        "Components/NFLEventCards9483.swift",
        '"\\(Int((chance * 100).rounded()))%"',
    ): 1,
    (
        "Components/OddsChartView.swift",
        '"\\(Int((value * 100).rounded()))%"',
    ): 1,
    (
        "Components/PlayerMilestoneProfileView.swift",
        '"\\(Int((chance * 100).rounded()))%"',
    ): 1,
    (
        "Components/RaceChartView.swift",
        '"\\(Int((value * 100).rounded()))%"',
    ): 1,
    (
        "Utilities/RaceChart.swift",
        '"\\(Int(($0 * 100).rounded()))%"',
    ): 1,
    # Signed 24h delta badge (`MovementBadge`, gated by `abs(m) >= 0.01`, point move not chance).
    (
        "Views/DiscoverView.swift",
        '"\\(abs(Int((m * 100).rounded())))%"',
    ): 1,
    # User prediction hit-rate accuracy ratios (`correct / total` legitimately spans 0%..100%).
    (
        "Views/MyStuffView.swift",
        '"\\(Int(stats.accuracy * 100))%"',
    ): 1,
    (
        "Views/PredictionStatsView.swift",
        '"\\(Int(stats.accuracy * 100))%"',
    ): 1,
    (
        "Views/PredictionStatsView.swift",
        '"\\(Int(data.accuracy * 100))%"',
    ): 1,
    # Dev-only source blend weight diagnostic string (`mark.dev?.weights`, gated by dev overlay).
    (
        "Components/SourceMarkView12581.swift",
        '"\\(src.name) \\(Int((w * 100).rounded()))%"',
    ): 1,
    # Raw 3-way bookmaker overround sum diagnostic (sum of 3 legs, e.g. 104%, not a single chance).
    (
        "Components/EventAtlasSoccerCards11666.swift",
        '"Raw 3-way sum \\(Int(($0 * 100.0).rounded()))%"',
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
        """Scanning `ios/Bain Luck/Bain Luck/` must catch floor, rounded, helper, and string mutants."""
        mutants = [
            'if let prob = future.probability {\n    Text("\\(Int(prob * 100))%")\n}',
            'Text("\\(Int((prob * 100).rounded()))%")',
            'Text(\n    "\\(Int((prob * 100.0).rounded()))%"\n)',
            'Text("Based on \\(Int(round(prob * 100)))% chance")',
            'Text("\\(label ?? "fallback"): \\(Int(prob * 100))%")',
            'private func formatPct(_ p: Double) -> String {\n    "\\(Int(round(p * 100)))%"\n}',
            'let text = "\\(leader.name): \\(Int(prob * 100))%"',
            'return "\\(Int((p * 100.0).rounded()))%"',
        ]
        for mutant in mutants:
            assert _find_hand_rolled_percent_strings(mutant), f"missed mutant: {mutant!r}"

        safe = [
            '// "\\(Int(prob * 100))%"\nText(formatProbability(prob))',
            '/* Text("\\(Int((prob * 100).rounded()))%") */\nlet s = formatProbabilityOrDash(prob)',
        ]
        for snippet in safe:
            assert _find_hand_rolled_percent_strings(snippet) == [], (
                f"false positive on {snippet!r}"
            )


class TestNoViewHandRollsProbabilityPercent:
    """Class-level guard (#13892 follow-up): no string anywhere in `ios/Bain Luck/Bain Luck/`
    (inside or outside `Text(...)`) may build a probability percent via `* 100` with `Int(` or `round(`."""

    def test_no_view_hand_rolls_a_probability_percent(self):
        found_counts: Counter[tuple[str, str]] = Counter()
        unexpected: list[str] = []

        for path in sorted(APP_ROOT.rglob("*.swift")):
            rel = path.relative_to(APP_ROOT).as_posix()
            for line_no, norm_literal in _find_hand_rolled_percent_strings(path.read_text()):
                key = (rel, norm_literal)
                found_counts[key] += 1
                expected = NON_PROBABILITY_HAND_ROLLED_STRING_ALLOWLIST.get(key, 0)
                if found_counts[key] > expected:
                    unexpected.append(f"{rel}:{line_no}: {norm_literal}")

        assert unexpected == [], (
            "App string hand-rolls a percent using `* 100`; route probability "
            "formatting through `formatProbability(...)`, `formatProbabilityOrDash(...)`, "
            "or `DiscoverRoundupCardModel.probabilityText(...)` so 0.1%..0.99% reads `<1%`: "
            f"{unexpected}"
        )

        drift = {
            key: (expected, found_counts[key])
            for key, expected in NON_PROBABILITY_HAND_ROLLED_STRING_ALLOWLIST.items()
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
