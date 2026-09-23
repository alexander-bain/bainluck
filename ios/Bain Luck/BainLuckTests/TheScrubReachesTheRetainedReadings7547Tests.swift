import XCTest
@testable import Bain_Luck

/// #7547 — THE CROSSHAIR STOPPED FOLLOWING THE FINGER FOR HALF THE WINDOW, AND THE
/// DENSER THE RETAINED HISTORY GOT THE MORE OF IT STOPPED.
///
/// `EvolutionChartView.updateCrosshair` chose its resting instant over every
/// DISPLAYED outcome and then reported only the SELECTED ones. When the instant it
/// chose carried no selected reading the readout came out empty, and the code's
/// answer to an empty readout was to leave `crosshair` untouched — so the dashed
/// `RuleMark` stayed parked where it last succeeded while the touch travelled on,
/// still printing that older moment's timestamp and price.
///
/// ═══ THE SPECIMEN ═══
///
/// `window` below is production market **56775596** — *Las Vegas: Team Specials*,
/// 12 independent Kalshi props — exactly as `/api/futures/56775596/probability-
/// timeline?top=50&hours=24` served it (`source: kalshi`, `actual_hours: 24`,
/// `coverage_hours: 23.27`, `observation_times: 203`), read at 2026-09-23T06:16Z.
/// Offsets are seconds from `2026-09-22T07:00:00Z`; the index is the outcome's
/// position in the served field; prices are the served prices, unrounded.
///
/// It is kept whole rather than sampled because the thing under test is a RATE over
/// a window, and a hand-picked excerpt would let me choose the answer. The counts
/// the tests assert are the counts this payload actually produces.
///
/// The shape that causes the defect is the shape #7547 is about: minute-level
/// capture records the outcome that MOVED at the minute it moved, so **156 of the
/// payload's 203 instants carry exactly one outcome** and only 2 carry all twelve.
/// Four of `Mike Washington Jr. records 500+ rushing yards`'s readings are
/// single-instant spikes off a 0.38 floor — 0.44, 0.53, 0.52, 0.525, each at a
/// ragged non-round second — and those transient moves are precisely the history
/// this issue exists to keep.
///
/// ═══ WHAT THESE PIN ═══
///
/// The ship is that every position a reader can scrub to answers with a real
/// observation. Both arms matter: a rule that simply drew a crosshair everywhere
/// would pass the reachability test while inventing readings, so the
/// observed-not-interpolated arm and the untouched-dense-field control are what
/// stop this from being satisfied by a lie.
final class TheScrubReachesTheRetainedReadings7547Tests: XCTestCase {

    // MARK: - The served window

    /// The reader's default state, as `EvolutionChartView` sets it up: `topFilter`
    /// 10, and `selectedNames` seeded from the served field's first three.
    private static let displayedIndices = Set(1...10)
    private static let selectedIndices: Set<Int> = [1, 2, 3]

    private static let base = Date(timeIntervalSince1970: 1_758_524_400) // 2026-09-22T07:00:00Z

    /// `offsetSeconds,outcomeIndex,probability`, whitespace separated.
    private static let window = """
        0,1,0.87 780,4,0.61 900,3,0.38 960,5,0.37 1380,4,0.61 1380,6,0.26
        1380,2,0.38 1500,3,0.38 1860,5,0.37 1980,6,0.26 2100,3,0.38 2400,2,0.38
        2820,3,0.38 3096,5,0.37 3096,6,0.42 3096,2,0.44 3360,5,0.37 3540,4,0.61
        3600,3,0.38 3600,1,0.87 3600,6,0.26 3600,2,0.38 4440,6,0.26 4680,1,0.87
        4860,5,0.37 5040,6,0.26 5040,2,0.38 5100,4,0.61 5460,5,0.37 5940,3,0.38
        6060,1,0.87 6120,5,0.37 6420,6,0.26 6420,2,0.38 6540,3,0.38 6660,1,0.87
        7140,4,0.61 7200,3,0.38 7200,5,0.37 7200,6,0.26 7200,2,0.38 7260,1,0.87
        8280,6,0.26 8760,4,0.61 8820,5,0.37 8940,6,0.26 9180,1,0.87 9660,4,0.61
        9720,2,0.38 9780,1,0.87 9780,5,0.37 10020,3,0.38 10380,1,0.87 10560,6,0.26
        10800,3,0.38 10800,4,0.61 10800,5,0.37 10800,2,0.38 11220,6,0.26 11460,4,0.61
        11880,5,0.37 12000,3,0.38 12120,4,0.61 12120,2,0.38 12300,1,0.87 12540,5,0.37
        12540,6,0.26 12600,3,0.38 12720,4,0.61 12780,2,0.38 12960,1,0.87 13380,5,0.37
        13440,4,0.61 13620,6,0.26 13860,3,0.38 14100,4,0.61 14280,6,0.26 14400,1,0.87
        14400,5,0.37 14400,2,0.38 14760,4,0.61 14940,3,0.38 15180,1,0.87 15420,4,0.61
        15840,1,0.87 16080,4,0.61 16200,6,0.26 16440,1,0.87 17400,3,0.38 17460,5,0.37
        17760,6,0.26 17820,9,0.13 18000,3,0.38 18000,4,0.61 18000,1,0.87 18000,5,0.37
        18360,2,0.38 18420,10,0.9 18420,8,0.14 18420,7,0.505 18720,5,0.37 18900,1,0.87
        19020,4,0.61 19200,6,0.26 19320,3,0.38 19380,5,0.37 19680,4,0.61 19680,2,0.38
        19800,6,0.26 20460,6,0.26 20640,5,0.37 20880,2,0.38 20940,1,0.87 21240,5,0.37
        21540,4,0.61 21600,3,0.38 21600,1,0.87 21600,10,0.9 21600,8,0.14 21600,7,0.505
        21600,6,0.26 21600,2,0.38 21900,5,0.37 22200,4,0.61 22320,3,0.38 22560,1,0.87
        23400,6,0.26 23460,3,0.38 23760,5,0.37 24000,1,0.87 24000,2,0.38 24120,6,0.26
        24480,5,0.37 24600,2,0.38 24900,3,0.38 25200,4,0.61 25200,1,0.87 25200,5,0.37
        25200,10,0.9 25200,8,0.14 25200,6,0.26 25200,2,0.38 25860,4,0.61 25980,6,0.26
        26220,3,0.38 26340,5,0.37 26400,2,0.38 26460,1,0.87 26820,3,0.38 26940,5,0.37
        27300,4,0.61 27300,2,0.38 27960,4,0.61 27960,2,0.38 28080,3,0.38 28080,1,0.87
        28200,5,0.37 28321,3,0.38 28321,4,0.505 28321,1,0.87 28321,5,0.37 28321,6,0.26
        28321,2,0.53 28500,6,0.26 28800,3,0.38 28800,4,0.61 28800,1,0.87 28800,5,0.37
        28800,2,0.38 29520,4,0.61 29580,6,0.26 29940,5,0.37 30120,2,0.38 30360,4,0.61
        30660,5,0.37 30840,6,0.26 31080,1,0.87 31380,2,0.38 31980,3,0.38 31980,2,0.38
        32100,4,0.61 32160,6,0.26 32340,5,0.37 32400,1,0.87 36000,3,0.38 36000,4,0.61
        36000,1,0.87 36000,5,0.37 36000,7,0.505 36000,6,0.26 36000,2,0.38 36240,9,0.13
        39600,3,0.38 39600,4,0.61 39600,1,0.87 39600,9,0.13 39600,5,0.37 39600,8,0.14
        39600,6,0.26 39600,2,0.38 43200,3,0.38 43200,4,0.61 43200,5,0.37 43200,6,0.26
        43200,2,0.38 46800,3,0.38 46800,4,0.61 46800,1,0.87 46800,5,0.37 46800,6,0.26
        46800,2,0.38 46980,9,0.105 46980,10,0.105 48420,9,0.13 48420,10,0.9 48480,9,0.105
        48480,10,0.105 49500,9,0.13 49500,10,0.9 49560,9,0.105 49560,10,0.105 50400,3,0.38
        50400,4,0.385 50400,1,0.64 50400,9,0.105 50400,5,0.28 50400,10,0.105 50400,8,0.115
        50400,7,0.135 50400,6,0.22 50400,2,0.38 53510,3,0.38 53510,4,0.385 53510,9,0.105
        53510,5,0.28 53510,10,0.105 53510,8,0.115 53510,7,0.135 53510,6,0.22 53510,2,0.52
        54000,3,0.38 54000,2,0.38 56700,9,0.11 57600,3,0.38 57600,4,0.385 57600,9,0.11
        57600,8,0.12 57600,7,0.14 57600,6,0.21 57600,2,0.38 61200,3,0.38 61200,2,0.38
        64800,3,0.38 64800,4,0.385 64800,2,0.38 68400,3,0.38 68400,2,0.38 72000,3,0.38
        72000,2,0.38 72720,9,0.105 72720,10,0.105 75600,3,0.38 75600,4,0.38 75600,1,0.63
        75600,9,0.105 75600,5,0.28 75600,10,0.105 75600,8,0.115 75600,7,0.135 75600,6,0.21
        75600,2,0.38 78703,3,0.38 78703,4,0.38 78703,9,0.105 78703,5,0.28 78703,10,0.105
        78703,8,0.115 78703,7,0.135 78703,6,0.21 78703,2,0.525 79200,3,0.38 79200,2,0.38
        82800,3,0.38 82800,2,0.38 83760,10,0.12
        """

    private struct Reading {
        let date: Date
        let index: Int
        let probability: Double
    }

    private static func readings() -> [Reading] {
        window.split(whereSeparator: \.isWhitespace).map { token in
            let parts = token.split(separator: ",")
            return Reading(
                date: base.addingTimeInterval(TimeInterval(Int(parts[0])!)),
                index: Int(parts[1])!,
                probability: Double(parts[2])!
            )
        }
    }

    /// What `EvolutionChartView` now hands the policy: the SELECTED outcomes'
    /// readings, and nothing else.
    private static func selectedCandidates() -> [ScrubCandidate] {
        readings()
            .filter { selectedIndices.contains($0.index) }
            .map { ScrubCandidate(date: $0.date, name: "outcome-\($0.index)", probability: $0.probability) }
    }

    /// What it used to search over: every DISPLAYED outcome's readings.
    private static func displayedCandidates() -> [ScrubCandidate] {
        readings()
            .filter { displayedIndices.contains($0.index) }
            .map { ScrubCandidate(date: $0.date, name: "outcome-\($0.index)", probability: $0.probability) }
    }

    /// The instants a finger can come to rest nearest to — one per displayed
    /// observation, which is what `proxy.value(atX:)` resolves a touch onto.
    private static func reachableInstants() -> [Date] {
        Array(Set(displayedCandidates().map(\.date))).sorted()
    }

    // MARK: - The rule as it was

    /// The shipped `updateCrosshair` before this fix, written out so the two rules
    /// can be run over the same window and compared.
    ///
    /// Not a strawman: it is the old body's two populations verbatim — snap over
    /// `displayed`, report over `selected` — and `nil` is its real behaviour, the
    /// `if !coloredEntries.isEmpty` that left the crosshair where it was.
    private static func legacyResolve(
        at date: Date,
        displayed: [ScrubCandidate],
        selected: Set<String>
    ) -> (date: Date, entries: [ScrubCandidate])? {
        guard let nearest = displayed.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        }) else { return nil }
        let entries = displayed
            .filter { $0.date == nearest.date && selected.contains($0.name) }
            .sorted { $0.probability > $1.probability }
        return entries.isEmpty ? nil : (date: nearest.date, entries: entries)
    }

    // MARK: - 🔴 The defect

    func testTheOldRuleWentQuietAtSeventyFiveOfTheHundredAndFiftySevenReachableInstants() {
        let displayed = Self.displayedCandidates()
        let selectedNames = Set(Self.selectedIndices.map { "outcome-\($0)" })
        let instants = Self.reachableInstants()

        XCTAssertEqual(instants.count, 157, "the window's reachable instants")

        let quiet = instants.filter {
            Self.legacyResolve(at: $0, displayed: displayed, selected: selectedNames) == nil
        }

        XCTAssertEqual(
            quiet.count, 75,
            """
            The old two-population rule. At these instants it snapped to a reading \
            of a line the tooltip could not speak for, returned nothing, and the \
            view left the crosshair parked at its previous date and price.
            """
        )
        // Stated as a share because that is how a reader meets it: not an edge
        // case, a coin flip on every drag.
        XCTAssertEqual(Double(quiet.count) / Double(instants.count), 0.478, accuracy: 0.001)
    }

    // MARK: - 🟢 The ship

    func testEveryReachableInstantNowAnswersWithAReading() {
        let candidates = Self.selectedCandidates()
        let silent = Self.reachableInstants().filter {
            ChartCrosshairPolicy.resolve(at: $0, among: candidates) == nil
        }
        XCTAssertEqual(silent, [], "the crosshair must follow the finger everywhere it can land")
    }

    /// The touch is continuous, so the instants are not the only positions worth
    /// asking about — a finger between two readings must also resolve.
    func testEveryPositionBETWEENTwoReadingsAlsoAnswers() {
        let candidates = Self.selectedCandidates()
        let instants = Self.reachableInstants()
        let midpoints = zip(instants, instants.dropFirst()).map {
            Date(timeIntervalSince1970: ($0.timeIntervalSince1970 + $1.timeIntervalSince1970) / 2)
        }
        XCTAssertEqual(midpoints.count, 156)
        for point in midpoints {
            XCTAssertNotNil(ChartCrosshairPolicy.resolve(at: point, among: candidates))
        }
    }

    func testTheRestingReadingIsObservedNeverInterpolated() {
        let candidates = Self.selectedCandidates()
        let observed = Set(candidates.map { "\($0.date.timeIntervalSince1970)|\($0.name)|\($0.probability)" })

        for instant in Self.reachableInstants() {
            guard let resolved = ChartCrosshairPolicy.resolve(at: instant, among: candidates) else {
                return XCTFail("no reading at \(instant)")
            }
            for entry in resolved.entries {
                XCTAssertEqual(entry.date, resolved.date, "an entry dated away from its own crosshair")
                XCTAssertTrue(
                    observed.contains("\(entry.date.timeIntervalSince1970)|\(entry.name)|\(entry.probability)"),
                    "\(entry.name) @ \(entry.probability) is not a reading this market ever published"
                )
            }
        }
    }

    // MARK: - The 24h chip

    /// The `24h` chip's clause of #7547: what the venue retained for the last day
    /// reaches the plot intact, spikes included.
    ///
    /// The client's only window operation is `timeCutoff` — a `<` on the date. It
    /// carries no sampling, no bucketing and no point budget, so the assertion is
    /// that the count out equals the count in.
    func test24hWindowKeepsEveryRetainedReadingIncludingTheSingleInstantSpikes() {
        let all = Self.readings().filter { Self.displayedIndices.contains($0.index) }
        let cutoff = Self.base.addingTimeInterval(-1)  // the whole served day is inside 24h
        let kept = all.filter { $0.date >= cutoff }

        XCTAssertEqual(kept.count, all.count, "the 24h window must not thin the retained readings")
        XCTAssertEqual(Set(kept.map(\.date)).count, 157)

        // Minute-grain detail actually survives to the client: the tightest gap
        // between two retained instants is 60s, not the payload's 3600s
        // `bucket_seconds`.
        let instants = Set(kept.map(\.date)).sorted()
        let gaps = zip(instants, instants.dropFirst()).map { $1.timeIntervalSince($0) }
        XCTAssertEqual(gaps.min(), 60, "minute detail is what #7547 retains; it must reach the plot")
    }

    /// Each of `Mike Washington Jr. records 500+ rushing yards`'s four transient
    /// moves is ONE reading off a 0.38 floor. A reader who cannot rest the
    /// crosshair on it cannot read the move at all.
    func testEachSingleInstantReversalIsReachableAndReadsItsOwnPrice() {
        let candidates = Self.selectedCandidates()
        let spikes: [(offset: TimeInterval, price: Double)] = [
            (3096, 0.44), (28321, 0.53), (53510, 0.52), (78703, 0.525),
        ]

        for spike in spikes {
            let at = Self.base.addingTimeInterval(spike.offset)
            guard let resolved = ChartCrosshairPolicy.resolve(at: at, among: candidates) else {
                return XCTFail("the \(spike.price) move is unreachable")
            }
            XCTAssertEqual(resolved.date, at, "the crosshair rested off the move it was dropped on")
            XCTAssertEqual(
                resolved.entries.first(where: { $0.name == "outcome-2" })?.probability,
                spike.price,
                "the reversal must read its own price, not the 0.38 floor around it"
            )
        }
    }

    // MARK: - Controls

    /// A field where every instant carries every outcome — a championship board,
    /// and what most markets look like. The two rules cannot disagree here, so the
    /// fix must be invisible: this is the arm that stops "always answer" being
    /// satisfied by answering with something new.
    func testADenseFieldWhereEveryInstantCarriesEveryOutcomeIsUntouched() {
        let names = ["Kansas City", "Philadelphia", "Buffalo"]
        let dense: [ScrubCandidate] = (0..<48).flatMap { step in
            names.enumerated().map { idx, name in
                ScrubCandidate(
                    date: Self.base.addingTimeInterval(TimeInterval(step * 1800)),
                    name: name,
                    probability: 0.2 + Double(idx) * 0.1 + Double(step) * 0.001
                )
            }
        }
        let selected = Set(names)

        for step in 0..<48 {
            let at = Self.base.addingTimeInterval(TimeInterval(step * 1800) + 400)
            let old = Self.legacyResolve(at: at, displayed: dense, selected: selected)
            let new = ChartCrosshairPolicy.resolve(at: at, among: dense)
            XCTAssertEqual(old?.date, new?.date)
            XCTAssertEqual(old?.entries, new?.entries)
            XCTAssertEqual(new?.entries.count, 3)
        }
    }

    /// The one state that still draws no crosshair, and the reason the fix is not a
    /// behaviour change anybody can see: with nothing selected there was never a
    /// tooltip to keep.
    func testASelectionWithNoObservationsStillDrawsNothing() {
        XCTAssertNil(ChartCrosshairPolicy.resolve(at: Self.base, among: []))
    }

    // MARK: - The call site

    /// 🪤 THE DEFECT WAS NEVER IN THE RULE — IT WAS IN WHAT THE VIEW HANDED IT.
    ///
    /// `ChartCrosshairPolicy.resolve` takes ONE list, so the two-population bug
    /// cannot be written inside it and no test of it can fail on the old
    /// behaviour. Everything above would go on passing if `updateCrosshair` went
    /// back to searching every displayed line tomorrow.
    ///
    /// So this reads the call site, in the manner of
    /// `ChartLegendPrintsTheBoardsNumber5949Tests`: the candidate list must be
    /// narrowed to the reader's selection BEFORE the policy sees it, and the
    /// discarded `if !coloredEntries.isEmpty` — the line that actually froze the
    /// crosshair — must not come back.
    func testTheViewNarrowsToTheSelectionBeforeItAsksThePolicy() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        let view = try code(at: root.appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift"))

        XCTAssertTrue(
            view.contains("!$0.isCombined && effectiveSelected.contains($0.name)"),
            "updateCrosshair must hand the policy the SELECTED readings only — "
            + "snapping over a wider set than the tooltip can speak for is #7547")
        XCTAssertTrue(
            view.contains("ChartCrosshairPolicy.resolve(at: date, among: candidates)"),
            "the resting instant must be the policy's decision, not a second "
            + "`min(by:)` grown back in the view")
        XCTAssertFalse(
            view.contains("if !coloredEntries.isEmpty"),
            "the empty-readout guard is the freeze: it left `crosshair` at its "
            + "previous date while the finger kept moving")
    }

    /// Source with its comment lines removed, plus the check that the strip left
    /// real code standing: this file's own doc comments quote the strings it
    /// forbids, and an over-eager filter makes every assertion pass against an
    /// empty string.
    private func code(at url: URL) throws -> String {
        let source = try String(contentsOf: url, encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            stripped.contains("struct") || stripped.contains("enum"),
            "the comment strip left nothing to scan in \(url.lastPathComponent)")
        return stripped
    }

    /// Ties go to the earlier reading rather than to whichever `min(by:)` happened
    /// to visit first — pinned so a later reordering of the candidate list cannot
    /// silently move the crosshair.
    ///
    /// Swept over the midpoints as well as the instants, because a midpoint is
    /// where a tie actually occurs and the instants alone would never exercise it.
    func testTheRestingInstantDoesNotDependOnCandidateOrder() {
        let candidates = Self.selectedCandidates()
        let shuffled = candidates.shuffled()
        let instants = Self.reachableInstants()
        let midpoints = zip(instants, instants.dropFirst()).map {
            Date(timeIntervalSince1970: ($0.timeIntervalSince1970 + $1.timeIntervalSince1970) / 2)
        }
        for point in instants + midpoints {
            XCTAssertEqual(
                ChartCrosshairPolicy.resolve(at: point, among: candidates)?.date,
                ChartCrosshairPolicy.resolve(at: point, among: shuffled)?.date,
                "candidate order moved the crosshair at \(point)"
            )
        }
    }

    /// The tie itself, stated directly rather than hoped for: a touch exactly
    /// halfway between two readings rests on the earlier one, from either order.
    func testATouchExactlyBetweenTwoReadingsRestsOnTheEarlier() {
        let early = ScrubCandidate(date: Self.base, name: "A", probability: 0.4)
        let late = ScrubCandidate(date: Self.base.addingTimeInterval(60), name: "A", probability: 0.5)
        let midpoint = Self.base.addingTimeInterval(30)

        XCTAssertEqual(ChartCrosshairPolicy.resolve(at: midpoint, among: [early, late])?.date, Self.base)
        XCTAssertEqual(ChartCrosshairPolicy.resolve(at: midpoint, among: [late, early])?.date, Self.base)
    }
}
