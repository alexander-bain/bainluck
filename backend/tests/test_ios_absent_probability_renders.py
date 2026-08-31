"""UX-P218 — five more native surfaces must stop printing a price they do not have.

UX-P217 closed this class on `RelatedFuturesView`.  The same shape — a nil
probability coerced with `?? 0` and then rendered — was still live on five other
screens.  A row whose price never arrived showed a confident flat `0%` next to an
empty bar, which reads as "we know this is impossible" rather than "we do not
know".

The six converted render sites:

  1. `Components/DiscoverFuturesCard.swift`  — Discover futures card outcome row
  2. `Components/EvolutionChartView.swift`   — evolution legend row
  3. `Components/TournamentChartView.swift`  — tournament legend row
  4. `Views/DiscoverView.swift`              — IPO comparison summary
  5. `Views/DiscoverView.swift`              — compact futures row
  6. `Views/MyStuffView.swift`               — playoff journey stage row

Every one is inline in a SwiftUI view body, so no Swift unit test can reach them.
THIS file is the containment guard for the wiring.

TWO DESIGN CONSTRAINTS THIS GUARD ENFORCES, BOTH PAID FOR BY CERT-550:

*   🔴 **A COUNT IS A COMPENSATING GUARD.**  CERT-550 defeated a
    `count(helper) == 7` check by restoring one defect and adding the helper at an
    already-safe site: net count unchanged, suite green, defect back on screen.
    So every site below is anchored INDIVIDUALLY, by a snippet carrying something
    unique to it.  Restoring any one site fails regardless of what is added
    anywhere else.  There is no aggregate assertion in this file.

*   🔴 **A PRICED ROW MUST RENDER BYTE-IDENTICALLY TO BEFORE.**  CERT-550's second
    finding was that routing priced values through a shared formatter silently
    changed `0%`/`100%` edge rows into `<1%`/`>99%`.  This fix therefore does NOT
    reroute any priced value: each site keeps its own existing percent
    expression, and only the nil branch is new.  `TestPricedRowsAreUnchanged`
    pins those expressions verbatim.

Why the source is stripped of comments first: the fix's own comments quote the
banned `?? 0` spelling while explaining where it remains correct (geometry,
sorting, booleans).  A raw-byte guard would fail on the prose describing it and
— worse — could be silenced by deleting a comment.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
IOS = REPO / "ios/Bain Luck/Bain Luck"

CARD = IOS / "Components/DiscoverFuturesCard.swift"
EVOLUTION = IOS / "Components/EvolutionChartView.swift"
TOURNAMENT = IOS / "Components/TournamentChartView.swift"
DISCOVER = IOS / "Views/DiscoverView.swift"
MYSTUFF = IOS / "Views/MyStuffView.swift"
LADDER = IOS / "Components/LadderCardView.swift"

CONVERTED_FILES = [CARD, EVOLUTION, TOURNAMENT, DISCOVER, MYSTUFF]

# The absent marker, spelled the way shipped master already spells it in
# `ladderPercent`.  Deliberately a literal and NOT a new shared constant:
# `formatProbabilityOrDash` / `absentProbabilityMarker` are introduced by
# `program/ux-156`, which is under an ungraded cert, and adding the same symbol
# here would hand the integrator a conflict on a branch already staged.
# `TestTheMarkerMatchesShippedHouseStyle` is what stops the two drifting.
MARKER = "—"


def _strip_comments(src: str) -> str:
    """Drop `//` comments without touching `//` inside a string literal.

    These files contain URLs, so a naive split on `//` would truncate real code.
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


def _code(path: pathlib.Path) -> str:
    return _strip_comments(path.read_text())


def _struct_body(code: str, name: str) -> str:
    """Slice one `private struct X: View { ... }` out of a file.

    🔴 Mutant H earned this. `DiscoverView.swift` contains the SAME
    `.filter { $0.probability != nil }` line twice — once per comparison row — and
    a bare `in code` check is satisfied by EITHER of them. Deleting one left the
    guard green, which is the compensating-guard failure of CERT-550 wearing a
    different hat: an existence check over two identical occurrences cannot say
    WHICH one it found. Every claim about a specific struct is now made against
    that struct's own body.
    """
    marker = f"private struct {name}"
    start = code.index(marker)
    nxt = code.find("\nprivate struct ", start + len(marker))
    return code[start : nxt if nxt != -1 else len(code)]


# Each entry: (human name, file, snippet unique to THAT site).
#
# Sites 4 and 5 share a font, so they are separated by their subject expression
# (`probability.map` vs `leader.probability.map`) rather than by their chrome.
CONVERTED_SITES = [
    (
        "1. Discover futures card outcome row — percent",
        CARD,
        'Text(outcome.probability.map { "\\(Int(($0 * 100).rounded()))%" } ?? "—")\n'
        "                .font(.caption.weight(.bold).monospacedDigit())",
    ),
    (
        "1b. Discover futures card outcome row — bar draws nothing without a price",
        CARD,
        "if let probability = outcome.probability {\n"
        "                        Capsule()\n"
        "                            .fill(isLeader ? Color.blue : Color.secondary.opacity(0.35))\n"
        "                            .frame(width: max(3, geo.size.width * probability))",
    ),
    (
        "2. Evolution legend row — percent",
        EVOLUTION,
        'Text(probability == nil\n'
        '                                 ? "—"\n'
        "                                 : probPct < 1 && probPct > 0",
    ),
    (
        "2b. Evolution legend row — bar draws nothing without a price",
        EVOLUTION,
        "if probability != nil {\n"
        "                                        RoundedRectangle(cornerRadius: 2)\n"
        "                                            .fill(color.opacity(0.6))",
    ),
    (
        "3. Tournament legend row — percent",
        TOURNAMENT,
        'Text(probability == nil\n'
        '                                 ? "—"\n'
        "                                 : probPct < 1 && probPct > 0",
    ),
    (
        "3b. Tournament legend row — bar draws nothing without a price",
        TOURNAMENT,
        "if probability != nil {\n"
        "                                        RoundedRectangle(cornerRadius: 2)\n"
        "                                            .fill(color.opacity(0.6))",
    ),
    (
        "4. Discover IPO comparison summary — percent agrees with its own label",
        DISCOVER,
        'Text(probability.map { "\\(Int(($0 * 100).rounded()))%" } ?? "—")\n'
        "                .font(.subheadline.weight(.black).monospacedDigit())",
    ),
    (
        "5. Discover compact futures row — percent",
        DISCOVER,
        'Text(leader.probability.map { "\\(Int(($0 * 100).rounded()))%" } ?? "—")\n'
        "                        .font(.subheadline.weight(.black).monospacedDigit())",
    ),
    (
        "6. My Stuff playoff journey stage row — percent",
        MYSTUFF,
        'Text(achieved ? "done" : probability.map { formatProbability($0) } ?? "—")',
    ),
    (
        "6b. My Stuff playoff journey stage row — bar draws nothing without a price",
        MYSTUFF,
        "if probability != nil {\n"
        "                                    Capsule()\n"
        "                                        .fill(achieved",
    ),
    (
        "7. Discover threshold comparison row — defensive only, see the note below",
        DISCOVER,
        'Text(point.probability.map { "\\(Int(($0 * 100).rounded()))%" } ?? "—")\n'
        "                            .font(.caption.weight(.black).monospacedDigit())",
    ),
]

# 🔴 SITE 7 IS NOT A USER-VISIBLE FIX AND IS NOT CLAIMED AS ONE.
# `NativeThresholdComparisonRow` iterates a list already filtered to
# `probability != nil`, so its coercion is unreachable today.  It was converted
# anyway for one reason: it is the only remaining instance of the banned shape in
# these five files, and leaving it would have forced
# `test_no_text_render_coerces_a_nil_probability` to carry an allowlist.  An
# exemption is a hole a future regression can be parked in; a behaviour-preserving
# conversion is not.  The conversion changes nothing for a non-nil value — `.map`
# yields the identical string — and `TestKnownNonSitesStayHandRolled` pins that
# the filter which makes it unreachable is still there.


class TestEachSiteIsIndividuallyWired:
    """The load-bearing check. One assertion per site, anchored so that restoring
    any single one fails no matter what is added elsewhere."""

    def test_every_converted_site_is_still_wired(self):
        missing = [
            name
            for name, path, snippet in CONVERTED_SITES
            if snippet not in _code(path)
        ]
        assert missing == [], (
            "these render sites no longer handle an absent price, so they print "
            f"an invented number for a priceless row: {missing}"
        )


class TestTheClassIsClosedInTheseFiles:
    """Not just the six known sites — the shape itself must be gone."""

    def test_no_text_render_coerces_a_nil_probability(self):
        offenders = []
        for path in CONVERTED_FILES:
            for n, line in enumerate(_code(path).splitlines(), 1):
                if "Text(" in line and re.search(
                    r"[Pp]robability\w*\s*\?\?", line
                ):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
        assert offenders == [], (
            "a probability text render is coercing nil away; render the absent "
            f"marker instead: {offenders}"
        )

    def test_format_probability_is_never_handed_a_nil_default(self):
        """`formatProbability(x ?? 0)` IS the defect — zero formats as '<1%'."""
        offenders = []
        for path in CONVERTED_FILES:
            for n, line in enumerate(_code(path).splitlines(), 1):
                if re.search(r"\bformatProbability\([^)]*\?\?", line):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
        assert offenders == [], (
            "formatProbability was handed a nil default, which renders '<1%' "
            f"for a row with no price: {offenders}"
        )


class TestPricedRowsAreUnchanged:
    """CERT-550's second finding: a fix for the absent case must not restyle the
    priced case. Each site keeps its OWN percent expression — no shared formatter
    was introduced, so no `0%` became `<1%` and no `100%` became `>99%`."""

    def test_the_two_legend_rows_keep_their_own_edge_style(self):
        for path in (EVOLUTION, TOURNAMENT):
            code = _code(path)
            assert 'String(format: "%.1f%%", probPct)' in code, (
                f"{path.name} lost its sub-1% one-decimal style"
            )
            assert '"\\(Int(probPct.rounded()))%"' in code, (
                f"{path.name} lost its whole-percent style"
            )

    def test_the_card_and_discover_rows_keep_integer_rounding(self):
        for path in (CARD, DISCOVER):
            assert '"\\(Int(($0 * 100).rounded()))%"' in _code(path), (
                f"{path.name} no longer rounds a priced value the way it used to"
            )

    def test_my_stuff_still_uses_the_app_wide_formatter_for_priced_stages(self):
        code = _code(MYSTUFF)
        assert "formatProbability($0)" in code
        assert "formatProbabilityOrDash" not in code, (
            "MyStuffView must keep calling formatProbability for priced stages; "
            "swapping formatter changes the priced rendering, which is out of "
            "scope for this fix (see CERT-550)"
        )

    def test_the_achieved_shortcut_still_wins_over_a_percent(self):
        assert 'Text(achieved ? "done" :' in _code(MYSTUFF)


class TestTheMarkerMatchesShippedHouseStyle:
    """No new shared constant was introduced (ux-156 owns that symbol and is under
    an ungraded cert). This is what stops the literal drifting from the marker
    shipped master already renders for a nil ladder rung."""

    def test_ladder_percent_still_returns_the_same_marker(self):
        body = _code(LADDER).split("func ladderPercent(", 1)[1]
        nil_return = re.search(r"guard let value else \{ return \"(.+?)\" \}", body)
        assert nil_return is not None, "ladderPercent no longer has a nil branch"
        assert nil_return.group(1) == MARKER, (
            "the shipped absent marker moved; the six sites in this fix spell it "
            "literally and would now disagree with the ladder"
        )

    def test_every_converted_site_spells_the_marker_the_same_way(self):
        for name, path, snippet in CONVERTED_SITES:
            if "bar draws nothing" in name:
                continue
            assert MARKER in snippet, f"{name} does not render the absent marker"


class TestTheGuardCanActuallyFail:
    """A containment guard that cannot fail is decoration. Each pattern is re-run
    against a planted violation to prove it matches the shape it claims to."""

    def test_planted_text_coercion_is_detected(self):
        planted = 'Text("\\(Int(((outcome.probability ?? 0) * 100).rounded()))%")'
        assert "Text(" in planted and re.search(r"[Pp]robability\w*\s*\?\?", planted)

    def test_planted_formatter_coercion_is_detected(self):
        planted = "Text(formatProbability(stage.merged.avgProbability ?? 0))"
        assert re.search(r"\bformatProbability\([^)]*\?\?", planted)

    def test_the_camel_case_variants_are_covered(self):
        """The five files spell the value four different ways."""
        for spelling in (
            "outcome.probability ?? 0",
            "outcome.currentProbability ?? 0",
            "stage.merged.avgProbability ?? 0",
            "point?.probability ?? 0",
        ):
            assert re.search(r"[Pp]robability\w*\s*\?\?", spelling), spelling

    def test_comment_stripper_keeps_code_and_drops_prose(self):
        src = '// probability ?? 0 in prose\nlet u = "https://x/y" // tail\n'
        stripped = _strip_comments(src)
        assert "prose" not in stripped, "a comment must not satisfy the guard"
        assert '"https://x/y"' in stripped, "a URL is not a comment"
        assert "tail" not in stripped

    def test_a_site_anchor_is_not_satisfied_by_another_sites_text(self):
        """The anchors must be mutually distinguishing — that is the whole point
        of abandoning the count. Sites 4 and 5 share a font and are the hard
        case."""
        site4 = next(s for n, _, s in CONVERTED_SITES if n.startswith("4."))
        site5 = next(s for n, _, s in CONVERTED_SITES if n.startswith("5."))
        assert site4 != site5
        assert site4 not in site5 and site5 not in site4


class TestKnownNonSitesStayHandRolled:
    """The grep for `?? 0` over these files returns far more than the six sites.
    These are the ones that are NOT defects, recorded so a later sweep does not
    'fix' them and change behaviour."""

    def test_futures_detail_percent_renders_stay_if_let_guarded(self):
        """`FuturesDetailView` computes `probPct` eagerly but renders it only
        inside `if let prob` / `if outcome.probability != nil`. It renders NOTHING
        when the price is absent, which is a different and equally honest answer.
        Converting it would change its layout."""
        code = _code(IOS / "Views/FuturesDetailView.swift")
        assert "if let prob = outcome.probability {" in code
        assert "if outcome.probability != nil {" in code

    def test_threshold_comparison_row_is_pre_filtered(self):
        """`NativeThresholdComparisonRow` iterates a list already filtered to
        `probability != nil`. That filter is the entire basis for calling site 7
        'defensive only', so it is pinned against THAT struct's own body — see
        `_struct_body` and mutant H."""
        body = _struct_body(_code(DISCOVER), "NativeThresholdComparisonRow")
        assert "filter { $0.probability != nil }" in body, (
            "the filter that made site 7 unreachable is gone; site 7 is now a "
            "live render path and this fix's scope note is stale"
        )

    def test_ipo_comparison_row_is_pre_filtered(self):
        """The same filter guards the IPO row's `points`. Site 4 is a real fix
        regardless — `point` is nil when the list is EMPTY, which the filter can
        cause rather than prevent — but the two must not be conflated."""
        body = _struct_body(_code(DISCOVER), "NativeIPOComparisonRow")
        assert "filter { $0.probability != nil }" in body

    def test_the_struct_slicer_actually_separates_the_two(self):
        """If the slicer returned the whole file, both checks above would be the
        vacuous substring check they replaced."""
        code = _code(DISCOVER)
        threshold = _struct_body(code, "NativeThresholdComparisonRow")
        ipo = _struct_body(code, "NativeIPOComparisonRow")
        assert "NativeIPOComparisonRow" not in threshold
        assert "NativeThresholdComparisonRow" not in ipo
        assert len(threshold) < len(code) and len(ipo) < len(code)

    def test_the_24h_change_column_keeps_its_own_dash(self):
        """The change column already renders a dash for no movement, spelled with
        a hyphen. It is a PRICED zero, not an absent value, so this fix leaves it
        alone rather than restyling a correct render."""
        for path in (EVOLUTION, TOURNAMENT):
            assert 'changePct < 0 ? "\\(String(format: "%.1f", changePct))%"' in _code(
                path
            )
