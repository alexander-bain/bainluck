import SwiftUI
import Charts

// MARK: - Time Range

enum EvolutionTimeRange: String, CaseIterable, Identifiable {
    case season = "Season"
    case week = "7d"
    case tournament = "Event"
    case day = "24h"
    case today = "Today"

    var id: String { rawValue }

    /// The word this chip PRINTS, which is not always the case's own name.
    ///
    /// 🔴 #7077 — `Season` WAS PRINTED OVER *The Game Awards: Game of the Year*
    /// and over *Meta announces a training pause by October 31?*. Neither question
    /// has a season; the chip is the widest window the chart offers, and calling
    /// it a season on a video-game award is the kind of borrowed sports vocabulary
    /// a reader has to translate before they can use the control.
    ///
    /// Only the `.season` case is affected — every other chip already names a real
    /// duration — so the substitution is one word and the case keys never move.
    func label(seasonWord: String) -> String {
        self == .season ? seasonWord : rawValue
    }
}

/// What to call the widest range this chart offers.
///
/// "Season" is kept for the questions that have one — a league's own competitions,
/// and any market carrying tournament dates, where `Season` sits beside `Event` and
/// means the tour around it. Everything else gets `6M`, which is what the chart
/// actually fetches (4,320 hours) and cannot be wrong about.
///
/// 🔴 `6M` RATHER THAN `All`: a 2028 election market has been trading since 2025,
/// so a chip reading "All" over a six-month fetch would trade one wrong word for
/// another. The default for an unknown or absent category is therefore the honest
/// generic, never the specific claim (this is an allowlist whose MISS is safe).
enum EvolutionRangeVocabulary {
    /// Categories whose markets belong to a season, from
    /// `futures_markets.llm_sport_category` as production actually writes it.
    static let seasonShapedCategories: Set<String> = [
        "football", "basketball", "baseball", "hockey", "soccer",
        "cricket", "rugby", "handball", "lacrosse", "softball", "motorsports",
    ]

    static let genericWidestWindow = "6M"

    static func seasonWord(sportCategory: String?, hasTournamentDates: Bool) -> String {
        if hasTournamentDates { return EvolutionTimeRange.season.rawValue }
        let key = (sportCategory ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return seasonShapedCategories.contains(key)
            ? EvolutionTimeRange.season.rawValue
            : genericWidestWindow
    }
}

// MARK: - Chart Point

private struct EvolutionPoint: Identifiable {
    let id = UUID()
    let date: Date
    let name: String
    let probability: Double
    let isCombined: Bool
}

// MARK: - Crosshair State

private struct CrosshairData: Equatable {
    let date: Date
    let entries: [(name: String, probability: Double, color: Color)]

    static func == (lhs: CrosshairData, rhs: CrosshairData) -> Bool {
        lhs.date == rhs.date && lhs.entries.count == rhs.entries.count
    }
}

// MARK: - Round Boundary

private struct EvolutionRoundBoundary: Identifiable {
    let id = UUID()
    let date: Date
    let label: String
}

// MARK: - Outcome Colour

/// What colour an Evolution outcome is drawn in — #7036's fifth arm.
///
/// **One function, four marks.** `EvolutionChartView.colorForOutcome` is a choke
/// point: everything the chart paints per outcome comes out of it. The plotted
/// LINE (`chartForegroundStyleScale`), the crosshair tooltip's 6pt dot, the
/// leaderboard row's 6pt dot, and the `color:` handed to `TeamLogoView`, whose
/// `initialsFallback` paints the outcome's letters in it. All four sit on
/// `Color.cardBackground`, which is white. So one floor under one function
/// covers the lot, and there is no second copy for the arms to drift apart on.
///
/// **This one is reachable from stored data, unlike arm 4.** Measured on
/// production 2026-09-20 (`futures_outcomes` ⋈ `teams`): of 16,739 chart-eligible
/// outcome rows carrying a stored colour, **1,054 (6.3%, 73 clubs) are under
/// 3:1**. They are not edge rows either — *NBA: Steph Curry Next Team* draws
/// Golden State at 97% in `#fdb927` (1.73:1), and *NFC South Division Winner*
/// serves four lines of which New Orleans `#d3bc8d` (1.85:1) and Carolina
/// `#7bafd4` (2.35:1) are both under it. A reader opening that chart sees two of
/// four lines missing and a legend whose dots are blank.
///
/// **The fallback is the palette slot the outcome would have had anyway.** An
/// outcome with no stored colour already takes `paletteHexes[index % count]`;
/// flooring hands a too-pale one the same thing. That is deliberately not a new
/// colour: it cannot introduce a collision class the palette does not already
/// have, because two outcomes at different display positions take different
/// slots exactly as before. Every entry clears the floor by a wide margin — the
/// palest is `#0e7490` at 5.36:1 — which is asserted rather than trusted, so a
/// future palette edit that drops a pastel in fails a test instead of a render.
enum EvolutionOutcomeColour {

    /// 10-colour indexed palette, optimised for light backgrounds.
    ///
    /// Hexes rather than `Color`s because a `Color` cannot be compared in a
    /// test, and the whole point of this arm is that the RESOLVED value is
    /// assertable.
    ///
    /// 🪤 **It no longer "matches the web EvolutionChart", whatever the line
    /// this replaced said.** `lib/seriesColors.ts` says in as many words that the
    /// web adopted the flagship `SERIES_COLORS` and dropped "its bespoke
    /// crimson-led duplicate" — which is this list. So the same market's chart is
    /// blue-led on the web and red-led here. That divergence is real and it is
    /// NOT this arm's to fix: repainting every Evolution chart in the app is a
    /// visible redesign, not a contrast floor. The stale claim is removed rather
    /// than left to be inherited as a reason not to look.
    ///
    /// Pinned by test, because this list is now load-bearing in a second way: it
    /// is what a FLOORED outcome falls onto, so editing it silently repaints
    /// clubs that do have a stored colour, not just the ones that do not.
    static let paletteHexes: [String] = [
        "#c41e3a", // red (leader)
        "#005eb8", // blue
        "#1d4ed8", // indigo
        "#0e7490", // teal
        "#b91c1c", // dark red
        "#0369a1", // sky
        "#92400e", // amber
        "#4338ca", // violet
        "#be185d", // pink
        "#065f46", // emerald
    ]

    /// The palette slot for a display position, wrapping past the tenth.
    static func fallbackHex(index: Int) -> String {
        paletteHexes[index % paletteHexes.count]
    }

    /// The hex to draw this outcome's line, dot and badge letters in.
    static func markHex(_ storedHex: String?, index: Int) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex(index: index))
    }

    /// The same answer, resolved the way the chart resolves it: find the named
    /// outcome in the payload the chart is holding, then floor its colour.
    ///
    /// The lookup lives here rather than in the view because the view's payload
    /// is `@State private` — a test can reach this with a real decoded
    /// `ProbabilityTimelineResponse` and cannot reach it there at all. An
    /// unnamed outcome (the Field row, `_combined`, a name the payload does not
    /// carry) has no stored colour to judge and takes its palette slot, which is
    /// what it took before this arm.
    static func markHex(name: String, outcomes: [TimelineOutcomeMeta]?, index: Int) -> String {
        markHex(outcomes?.first(where: { $0.name == name })?.primaryColor, index: index)
    }
}

// MARK: - EvolutionChartView

/// Multi-outcome probability evolution chart with interactive crosshair,
/// combined probability line, and leaderboard grid. Feature parity with the web
/// EvolutionChart.
///
/// It replaced `TournamentChartView`, which was deleted along with the RACE
/// chart's arrival (#2911) after sitting with zero call sites: a dead chart in
/// a tree whose next job is "every chart becomes a primitive" is a thing
/// somebody eventually ports.
struct EvolutionChartView: View {
    let marketId: Int
    var hours: Int = 168
    var height: CGFloat = 280
    var tournamentStart: String?
    var tournamentEnd: String?

    @State private var data: ProbabilityTimelineResponse?
    @State private var loading = true
    @State private var error: String?
    @State private var errorIsRetryable = false
    @State private var topFilter: Int = 10
    @State private var selectedNames: Set<String> = []
    @State private var highlightedName: String?
    /// Off for every reader; the LOOK rig can ask for it (`-launch_chart_sum`).
    @State private var showCombinedProbability = LaunchRig.startsChartSumOn()
    @State private var selectedRange: EvolutionTimeRange = .week
    @State private var crosshair: CrosshairData?

    /// The window the loaded payload was ASKED for, kept so the coverage note can
    /// compare it against the coverage that came back. Written by `loadData` on
    /// every fetch, because `selectedRange` alone does not say it (`.tournament`
    /// computes its hours from the tournament's own start).
    @State private var requestedHours: Int = 0

    /// The plot's measured width, for the axis planner's geometric fit. 0 until the
    /// first layout, which the planner reads as "no geometry" and answers from its
    /// fallback tick budget.
    @State private var plotWidth: CGFloat = 0

    /// Which drags on the chart are a crosshair scrub and which belong to the
    /// page's scroll (#6705). Pure and unit-tested — see `ChartScrubState`.
    ///
    /// Load-bearing BECAUSE the fix made the pan recognize simultaneously with
    /// the scroll view's: both now fire, so something has to say which of them
    /// this particular drag was for.
    @State private var scrub = ChartScrubState()

    /// #4373 — the leaderboard's numeric columns are measured in the face they are
    /// drawn in, so they need the size the reader is actually at.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    // MARK: - Colors

    private static let combinedColor = Color(hex: "#111827")

    /// Every per-outcome mark the chart draws comes out of here — the plotted
    /// line, the crosshair dot, the leaderboard dot, and the colour handed to
    /// `TeamLogoView`, which paints the outcome's initials in it. #7036's floor
    /// sits under all four at once because they all sit on the white card.
    private func colorForOutcome(name: String, index: Int) -> Color {
        Color(hex: EvolutionOutcomeColour.markHex(
            name: name, outcomes: data?.outcomes, index: index))
    }

    // MARK: - Tournament Dates

    private var parsedTournamentStart: Date? { tournamentStart?.asDate }

    private var parsedTournamentEnd: Date? {
        if let end = tournamentEnd?.asDate { return end }
        guard let start = parsedTournamentStart else { return nil }
        return Calendar.current.date(byAdding: .day, value: 4, to: start)
    }

    private var hasTournamentDates: Bool { parsedTournamentStart != nil }

    private var roundBoundaries: [EvolutionRoundBoundary] {
        guard let start = parsedTournamentStart else { return [] }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let startOfDay = cal.startOfDay(for: start)
        let endBound = parsedTournamentEnd.map { min($0.addingTimeInterval(86400), Date()) } ?? Date()
        var boundaries: [EvolutionRoundBoundary] = []
        var dayOffset = 0
        while dayOffset < 5 {
            guard let roundDate = cal.date(byAdding: .day, value: dayOffset, to: startOfDay) else { break }
            if roundDate > endBound { break }
            let label = dayOffset < 4 ? "R\(dayOffset + 1)" : "PO"
            boundaries.append(EvolutionRoundBoundary(date: roundDate, label: label))
            dayOffset += 1
        }
        return boundaries
    }

    // MARK: - Available Time Ranges

    private var availableRanges: [EvolutionTimeRange] {
        if hasTournamentDates, let start = parsedTournamentStart, start <= Date() {
            let tournamentEnded: Bool
            if let end = parsedTournamentEnd {
                tournamentEnded = end.addingTimeInterval(86400) < Date()
            } else {
                tournamentEnded = false
            }
            return tournamentEnded
                ? [.season, .tournament]
                : [.season, .tournament, .day, .today]
        }
        return [.season, .week, .day, .today]
    }

    // MARK: - Body

    var body: some View {
        Group {
            if loading {
                ProgressView()
                    .frame(height: height)
            } else if let error {
                emptyState(error, retryable: errorIsRetryable)
            } else if data != nil {
                switch Self.cardBody(
                    windowPoints: chartEntries.count,
                    windowInstants: windowInstants,
                    totalInstants: totalInstants,
                    windowWord: windowWord
                ) {
                case .sparse(let copy):
                    VStack(spacing: 0) {
                        controlBar
                        emptyState(copy.note, hint: copy.hint)
                    }
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                case .plot:
                    VStack(spacing: 0) {
                        controlBar
                        chartSection
                        if let note = Self.coverageNote(
                            coverageHours: data?.coverageHours,
                            observationTimes: data?.observationTimes,
                            requestedHours: requestedHours
                        ) {
                            Text(note)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal)
                                .padding(.bottom, 6)
                        }
                        if crosshair != nil {
                            crosshairTooltip
                        }
                        leaderboardGrid
                    }
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
        }
        .task {
            if hasTournamentDates, let start = parsedTournamentStart, start <= Date() {
                selectedRange = .tournament
            }
            await loadData()
        }
    }

    // MARK: - Empty State

    /// 🔴 #7350 — THE SECOND LINE USED TO READ *"Prices update every 1-2 hours for
    /// this market"*, unconditionally, under every non-retryable empty state. It is
    /// the poll schedule recited as a promise to the reader, and on the market that
    /// reported this ship it was printed over nine observations spread across a
    /// MONTH — three of the gaps longer than a week. Nothing in the payload supports
    /// a cadence, so nothing here says one: the `hint` is passed in by the caller
    /// that has evidence, and is absent otherwise.
    private func emptyState(
        _ message: String, hint: String? = nil, retryable: Bool = false
    ) -> some View {
        VStack(spacing: 6) {
            Image(systemName: retryable ? "exclamationmark.triangle" : "doc.text")
                .font(.system(size: 16))
                .foregroundStyle(.tertiary)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if let hint {
                Text(hint)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .multilineTextAlignment(.center)
            }
            if retryable {
                Button {
                    Task { await loadData() }
                } label: {
                    Label("Retry", systemImage: "arrow.clockwise")
                        .font(.caption)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, 4)
            }
        }
        .frame(height: height * 0.5)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Load Data

    private func loadData() async {
        loading = data == nil
        errorIsRetryable = false
        do {
            let fetchHours: Int
            switch selectedRange {
            case .season:
                fetchHours = 4320 // ~6 months
            case .week:
                fetchHours = hours
            case .tournament:
                if let start = parsedTournamentStart {
                    fetchHours = max(Int(Date().timeIntervalSince(start) / 3600) + 12, 48)
                } else {
                    fetchHours = hours
                }
            case .day:
                fetchHours = 24
            case .today:
                fetchHours = 24
            }
            let result = try await APIClient.shared.fetchProbabilityTimeline(
                marketId: marketId, top: 50, hours: fetchHours
            )
            data = result
            requestedHours = fetchHours
            if selectedNames.isEmpty {
                selectedNames = Set(result.outcomes.prefix(3).map(\.name))
            }
            error = nil
            loading = false
        } catch let apiError as APIError {
            if apiError.isCancellation {
                // Task cancelled (e.g. view disappeared) — don't show error
                return
            }
            switch apiError {
            case .networkError:
                self.error = "Connection failed. Check your network."
                errorIsRetryable = true
            case .httpError(let code, _) where code == 404:
                self.error = "Market history not available"
                errorIsRetryable = false
            case .httpError(let code, _) where code >= 500:
                self.error = "Server error. Try again in a moment."
                errorIsRetryable = true
            case .httpError:
                self.error = "Failed to load timeline"
                errorIsRetryable = true
            case .decodingError:
                self.error = "Failed to load timeline"
                errorIsRetryable = true
            case .invalidURL:
                self.error = "Failed to load timeline"
                errorIsRetryable = false
            }
            loading = false
        } catch {
            self.error = "Failed to load timeline"
            errorIsRetryable = true
            loading = false
        }
    }

    // MARK: - Computed

    /// The rows this render draws, each carrying WHERE IN THE SERVED FIELD it came
    /// from.
    ///
    /// #8109: the percent a row prints is decided once over the whole served field
    /// and looked up positionally, so the index has to survive the two things this
    /// property does to the list — dropping `Field` and truncating to the reader's
    /// `Top N` chip. Carrying it is what stops the lookup being keyed on `name`,
    /// which is this table's identity everywhere else (`selectedNames`, the
    /// `ForEach`, `colorForOutcome`) and is one served duplicate away from handing
    /// two rows one number.
    private var displayedRows: [(servedIndex: Int, outcome: TimelineOutcomeMeta)] {
        guard let data else { return [] }
        let filtered = data.outcomes.enumerated()
            .filter { $0.element.name != "Field" }
            .map { (servedIndex: $0.offset, outcome: $0.element) }
        if topFilter >= filtered.count { return filtered }
        return Array(filtered.prefix(topFilter))
    }

    private var displayedOutcomes: [TimelineOutcomeMeta] { displayedRows.map(\.outcome) }

    /// The card-level decision, taken ONCE over `data.outcomes` — the whole served
    /// field, not the rows on screen. See `EvolutionLeaderboardGeometry
    /// .renderedPercents(forServedField:)` for why the distinction is the fix.
    private var servedRenderedPercents: [Int?] {
        EvolutionLeaderboardGeometry.renderedPercents(forServedField: data?.outcomes ?? [])
    }

    /// Whether adding this market's outcomes up produces a probability — decided
    /// ONCE over the whole served field, like `servedRenderedPercents` above and for
    /// the same reason. See `EvolutionCombinedLinePolicy` for the measurement.
    ///
    /// Gates the `Sum` control AND the line independently. Two gates rather than one
    /// because they can disagree: `showCombinedProbability` survives in `@State`
    /// across a reload, and the rig can seed it true at launch, so hiding only the
    /// checkbox would leave a market able to draw a line its reader can no longer
    /// turn off.
    private var fieldSupportsCombinedLine: Bool {
        EvolutionCombinedLinePolicy.fieldIsOneQuestion(servedOutcomes: displayedOutcomes)
    }

    private var displayedNames: [String] { displayedOutcomes.map(\.name) }

    private var effectiveSelected: Set<String> {
        selectedNames.isEmpty ? Set(displayedNames.prefix(3)) : selectedNames
    }

    /// Time-filtered cutoff date for chart entries.
    private var timeCutoff: Date? {
        switch selectedRange {
        case .season:
            return nil
        case .week:
            return Calendar.current.date(byAdding: .day, value: -7, to: Date())
        case .tournament:
            guard let start = parsedTournamentStart else { return nil }
            return start.addingTimeInterval(-3600 * 6)
        case .day:
            return Calendar.current.date(byAdding: .hour, value: -24, to: Date())
        case .today:
            return Calendar.current.startOfDay(for: Date())
        }
    }

    private var chartEntries: [EvolutionPoint] {
        guard let data else { return [] }
        let names = Set(displayedNames)
        let cutoff = timeCutoff
        // Hoisted: a card-level fact, not a per-entry one, and the loop runs once
        // per served instant (584 on 56775596).
        let supportsCombined = fieldSupportsCombinedLine
        var points: [EvolutionPoint] = []
        // Track latest known probabilities for the combined line
        var latestProbs: [String: Double] = [:]

        for entry in data.timeline {
            guard let date = entry.timestamp.asDate else { continue }
            if let cutoff, date < cutoff { continue }

            for (name, prob) in entry.outcomes where names.contains(name) {
                points.append(EvolutionPoint(
                    date: date,
                    name: name,
                    probability: prob * 100,
                    isCombined: false
                ))
                if effectiveSelected.contains(name) {
                    latestProbs[name] = prob * 100
                }
            }

            // Combined probability line
            if let combined = EvolutionCombinedLinePolicy.combinedProbability(
                showRequested: showCombinedProbability,
                fieldIsOneQuestion: supportsCombined,
                selectedCount: effectiveSelected.count,
                latestProbs: latestProbs
            ) {
                points.append(EvolutionPoint(
                    date: date,
                    name: "_combined",
                    probability: combined,
                    isCombined: true
                ))
            }
        }
        return points
    }

    /// Distinct instants the CHOSEN window holds, counted off the same timeline and
    /// the same cutoff the plot is built from — not off `chartEntries`, whose count
    /// multiplies by however many outcomes are selected.
    private var windowInstants: Int {
        guard let data else { return 0 }
        let cutoff = timeCutoff
        return data.timeline.reduce(into: 0) { total, entry in
            guard let date = entry.timestamp.asDate else { return }
            if let cutoff, date < cutoff { return }
            total += 1
        }
    }

    /// Distinct instants the RESPONSE holds, whatever window was asked for. The
    /// route routinely answers with more than it was asked for — 59165099 returned
    /// 2,160 hours against a 168-hour request — and that surplus is exactly the
    /// history #7350 is about.
    private var totalInstants: Int {
        data?.timeline.reduce(into: 0) { total, entry in
            if entry.timestamp.asDate != nil { total += 1 }
        } ?? 0
    }

    private var windowWord: String { Self.windowWord(for: selectedRange) }

    // MARK: - Axis, Coverage and Observation Marks (#7077)

    /// How to tick and label this chart's time axis.
    ///
    /// 🔴 #7077 — THE AXIS WAS LABELLED FROM THE CHIP THE READER PRESSED, NOT FROM
    /// THE DATA IT DREW. `7d` took `month().day()` whatever came back, so *The Game
    /// Awards: Game of the Year* — 20 hours of prices inside a 168-hour request —
    /// printed **Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep…** across the
    /// bottom of Alex's phone, six labels touching each other, the last one cut off.
    /// *Meta announces a training pause* printed **Sep 15 · Sep 16 · Sep 16 · Sep 17
    /// · Sep 17 · …** for the same reason. A duplicated label is the same lie as a
    /// wrong one (#3269).
    ///
    /// ✅ THERE IS NO NEW RULE HERE. `OddsChartView.xAxisPlan` already chooses a
    /// stride from the domain and adds a weekday or an hour exactly when the domain
    /// needs one, its label widths are re-measured by the suite at the axis's own
    /// 9pt across a locale set, and `ScoreDifferentialChartView` adopted it for
    /// precisely this reason — the copy it used to carry had silently stopped
    /// matching, and two stacked charts drew two clocks (#3238). This chart was the
    /// third one, still on `.automatic(desiredCount: 5)`.
    static func axisPlan(
        for dates: [Date], plotWidth: CGFloat = 0, calendar: Calendar = .current
    ) -> OddsChartView.XAxisPlan {
        guard let lo = dates.min(), let hi = dates.max() else {
            let now = Date()
            return OddsChartView.xAxisPlan(for: now...now, plotWidth: plotWidth, calendar: calendar)
        }
        return OddsChartView.xAxisPlan(for: lo...hi, plotWidth: plotWidth, calendar: calendar)
    }

    /// A series this sparse is drawn with its observations ON it.
    ///
    /// 🔴 THE META CHART WAS TWO STRAIGHT LINES CROSSING, drawn from **two** prices
    /// per outcome 75 hours apart, and it reads as a market sliding steadily from
    /// 85% to 5% over three days. Nothing between those two instants was observed
    /// and nothing may be invented — so the honest change is not to the line, it is
    /// to say where the line has evidence. Above this count the dots stop being
    /// information and become texture, and the line alone is fair.
    static let sparseObservationLimit = 12

    static func showsObservationMarks(distinctInstants: Int) -> Bool {
        distinctInstants >= 1 && distinctInstants <= sparseObservationLimit
    }

    /// One plain line about how much of the chosen window this market has actually
    /// been priced for — or nil when the window is substantially covered and the
    /// chart needs no caption at all.
    ///
    /// The reader presses `7d` and gets a chart; nothing on it could say that the
    /// market has only existed for a day of that week. This is the smallest true
    /// sentence that closes the gap, and it is silent in the ordinary case — an
    /// absent explanation beats an unhelpful one (#871).
    ///
    /// Count first, span second: at one or two prices the count IS the story, and
    /// "prices only go back 3d" would imply a line where there are two dots.
    static func coverageNote(
        coverageHours: Double?, observationTimes: Int?, requestedHours: Int
    ) -> String? {
        if let seen = observationTimes, seen > 0, seen <= 3 {
            return seen == 1 ? "Only one price seen so far" : "Only \(seen) prices seen so far"
        }
        guard let covered = coverageHours, covered >= 0, requestedHours > 0 else { return nil }
        guard covered < Double(requestedHours) * 0.5 else { return nil }
        return "Prices only go back \(coverageSpanWord(covered))"
    }

    // MARK: - A Window With Almost Nothing In It (#7350)

    /// What the card draws once a response is in hand.
    ///
    /// 🔴 #7350 — THE CONTROLS LIVED INSIDE THE "THERE IS A CHART" BRANCH, so the
    /// one state in which a reader most needs them was the one state that hid them.
    /// *Will federal capital gains taxes be cut in 2026?* (59165099) on Alex's
    /// TestFlight 1.0 (16): the route served **nine** observations reaching back to
    /// August 18 — the client asked for 168 hours and the route answered with 2,160
    /// — the default `7d` window filtered eight of them away, and the card fell to
    /// *"Limited price history available"* with no chips under it. The history was
    /// already on the phone, in the response the view was holding, and there was no
    /// way to ask for it.
    ///
    /// ✅ The controls are now OUTSIDE the branch and the sparse state is a first
    /// class card: chips, then one true line about what the chosen window holds.
    /// **The plot still needs two points** — one observation is a dot in time, and
    /// joining it to nothing is the invented interval #7077 was about — so the fix
    /// is reachability and honesty, not a line drawn through a single price.
    enum CardBody: Equatable {
        /// The chart, its caption and its leaderboard.
        case plot
        /// Controls and one true sentence, no plot.
        case sparse(SparseCopy)
    }

    /// What the sparse card says, and — only when there is something to reach — how
    /// to reach it.
    struct SparseCopy: Equatable {
        let note: String
        let hint: String?
    }

    static func cardBody(
        windowPoints: Int, windowInstants: Int, totalInstants: Int, windowWord: String
    ) -> CardBody {
        guard windowPoints < 2 else { return .plot }
        return .sparse(sparseCopy(
            windowInstants: windowInstants,
            totalInstants: totalInstants,
            windowWord: windowWord
        ))
    }

    /// The sentence, counted off the response rather than asserted.
    ///
    /// "Earlier" is the whole point: it distinguishes *we have never seen a price*
    /// from *we have eight prices and you are looking at the wrong week*, which the
    /// one sentence it replaces could not (gotcha #53 — an empty window and an empty
    /// history had the same words). The hint appears only in the second case, so it
    /// is never an instruction to go looking for something that is not there.
    static func sparseCopy(
        windowInstants: Int, totalInstants: Int, windowWord: String
    ) -> SparseCopy {
        // ONE clamp, not two: `guard seen > 0` below already sends every
        // non-positive total to the honest sentence, so wrapping this in
        // `max(0,)` as well was a second copy of the same rule — measured
        // equivalent over every input pair in -50...50 by native/260's
        // mutation run, which is exactly how a redundant guard shows up.
        // The clamp on `inWindow` is NOT redundant and stays: it is what
        // stops a negative window count inflating `earlier`.
        let seen = totalInstants
        let inWindow = max(0, min(windowInstants, seen))
        let earlier = seen - inWindow

        guard seen > 0 else { return SparseCopy(note: "No price history yet", hint: nil) }

        // 🔴 The window count is NOT capped at one. `cardBody` gates on POINTS and
        // this sentence counts INSTANTS, and the two diverge: `chartEntries` only
        // emits a point for an outcome the card is displaying, so a timeline entry
        // carrying just `Field` (filtered out) or only outcomes past `topFilter`
        // is an instant with no point. Two such entries plus older history reached
        // `inWindow == 2` while the card was still sparse, and the old ternary read
        // every one of them as "One price". Count what is there.
        let windowPhrase: String
        switch inWindow {
        case 0: windowPhrase = "No prices \(windowWord)"
        case 1: windowPhrase = "One price \(windowWord)"
        default: windowPhrase = "\(inWindow) prices \(windowWord)"
        }

        // Nothing older means the window already holds everything the response has,
        // so the window's own name would be noise — and on the widest chip (no
        // cutoff) it is always this branch. "so far" is true of every range.
        guard earlier > 0 else {
            return SparseCopy(
                note: inWindow == 1
                    ? "Only one price seen so far"
                    : "\(inWindow) prices seen so far",
                hint: nil)
        }

        let earlierPhrase = earlier == 1 ? "one earlier price" : "\(earlier) earlier prices"
        let note = "\(windowPhrase) — \(earlierPhrase)"
        return SparseCopy(note: note, hint: "Try a longer range")
    }

    /// The window a chip actually selects, as it reads INSIDE the sentence — the
    /// preposition belongs to the phrase, because `Today` does not take one and
    /// every other window does ("No prices today", "No prices in the last 7 days").
    ///
    /// Named from the RANGE, never from the chip's own label: `6M` reads fine on a
    /// chip and not in a sentence, and the widest range's cutoff is nil — so when it
    /// is sparse, the window IS everything and the count sentence carries it without
    /// this word at all.
    static func windowWord(for range: EvolutionTimeRange) -> String {
        switch range {
        case .week: return "in the last 7 days"
        case .day: return "in the last 24 hours"
        case .today: return "today"
        case .tournament: return "during this event"
        case .season: return "in this range"
        }
    }

    static func coverageSpanWord(_ hours: Double) -> String {
        if hours < 1 { return "under an hour" }
        if hours < 48 { return "\(Int(hours.rounded()))h" }
        return "\(Int((hours / 24).rounded()))d"
    }

    // MARK: - Control Bar

    /// 🔴 #4199 — THREE GROUPS COMPETED FOR ONE ROW AND `Text` WAS THE ONLY THING
    /// IN IT THAT COULD GIVE, so SwiftUI took the width out of the words. At 402pt
    /// the bar read `Sea/son  7d  24/h  To-/day`; at 375pt it degraded to about one
    /// character per line (`Se/aso/n`). This is the control that decides what the
    /// chart underneath is showing, and it was unreadable at every phone width —
    /// not a narrow-phone edge case, the default state.
    ///
    /// ✅ TWO MODIFIERS AND A LAST RESORT. `lineLimit(1)` alone would only convert
    /// wrapping into truncation — the same information loss, which is #3966's
    /// finding — so each chip also claims its intrinsic width with `fixedSize`.
    /// That guarantees whole words and makes the row's real ink visible to the
    /// layout, and `ViewThatFits` then picks the widest arm that actually fits:
    /// roomy padding, else compact, else a horizontal scroller.
    ///
    /// **NO SECOND COPY OF THE ARITHMETIC.** There is deliberately no width model
    /// here to compare against — `ViewThatFits` measures the real chips at the real
    /// Dynamic Type size, so it cannot drift from a literal the way #3817's
    /// per-character bound did. `EvolutionControlBarLayoutTests` hosts these very
    /// views and asserts the row is ONE line tall at 375 and 402 across the
    /// vocabulary, including the mid-tournament `Event` variant.
    ///
    /// **`minimumScaleFactor` was measured and rejected** before this — see
    /// `CalibrationSourceTableGeometry`: SwiftUI scales sibling `Text` together, so
    /// it shrinks every chip in the row to half-rescue one, and still truncates.
    private var controlBar: some View {
        EvolutionControlBar(
            availableRanges: availableRanges,
            selectedRange: $selectedRange,
            showCombinedProbability: $showCombinedProbability,
            sumAvailable: fieldSupportsCombinedLine,
            topFilter: $topFilter,
            seasonWord: EvolutionRangeVocabulary.seasonWord(
                sportCategory: data?.sportCategory,
                hasTournamentDates: hasTournamentDates
            ),
            onRangeChange: {
                crosshair = nil
                Task { await loadData() }
            }
        )
    }

    // MARK: - Chart

    private var chartSection: some View {
        let entries = chartEntries
        // #7077 — how many instants this chart has evidence for, counted off the
        // points it is about to draw rather than off `observation_times`, which
        // describes the payload before the range cutoff filtered it.
        let showsObservationMarks = Self.showsObservationMarks(
            distinctInstants: Set(entries.map(\.date)).count)
        let visibleBoundaries: [EvolutionRoundBoundary]
        if let minDate = entries.map(\.date).min(),
           let maxDate = entries.map(\.date).max() {
            visibleBoundaries = roundBoundaries.filter { $0.date >= minDate && $0.date <= maxDate }
        } else {
            visibleBoundaries = roundBoundaries
        }

        return Chart {
            // Round boundary vertical lines
            ForEach(visibleBoundaries) { boundary in
                RuleMark(x: .value("Round", boundary.date))
                    .lineStyle(StrokeStyle(lineWidth: 0.7, dash: [4, 3]))
                    .foregroundStyle(.secondary.opacity(0.3))
            }

            // Crosshair vertical line
            if let crosshair {
                RuleMark(x: .value("Crosshair", crosshair.date))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 2]))
                    .foregroundStyle(.primary.opacity(0.3))
            }

            // Data lines
            ForEach(entries) { point in
                let isSelected = point.isCombined || effectiveSelected.contains(point.name)
                let isHighlighted = highlightedName == nil || highlightedName == point.name

                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Probability", point.probability)
                )
                .foregroundStyle(by: .value("Participant", point.name))
                // #7077 — the dots ARE the observations. `symbolSize(0)` rather
                // than a branch: a conditional mark inside a ChartContentBuilder
                // is a second code path for the same series, and this is one
                // property of one mark.
                .symbol(.circle)
                .symbolSize(showsObservationMarks ? 14 : 0)
                .lineStyle(StrokeStyle(
                    lineWidth: point.isCombined ? 2.2 :
                        (highlightedName == point.name ? 2.5 :
                            (isSelected ? 1.8 : 0.8)),
                    lineCap: .round,
                    dash: point.isCombined ? [7, 4] : []
                ))
                .opacity(point.isCombined
                    ? (highlightedName != nil ? 0.45 : 0.9)
                    : (isSelected && isHighlighted ? 1 : (isSelected ? 0.2 : 0.1)))
            }
        }
        .chartForegroundStyleScale(mapping: { (name: String) -> Color in
            if name == "_combined" { return Self.combinedColor }
            let idx = displayedNames.firstIndex(of: name) ?? 0
            return colorForOutcome(name: name, index: idx)
        })
        // Round boundary labels
        .chartOverlay { proxy in
            GeometryReader { geo in
                // The PLOT's width, not the chart's — the axis planner fits labels
                // into the drawing area, and the y-axis gutter is not part of it.
                Color.clear.preference(
                    key: PlotWidthPreferenceKey.self,
                    value: geo[proxy.plotAreaFrame].width)

                ForEach(visibleBoundaries) { boundary in
                    if let xPos = proxy.position(forX: boundary.date) {
                        Text(boundary.label)
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(.ultraThinMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                            .position(x: xPos, y: 12)
                    }
                }

                // Touch overlay for crosshair. #6705.
                //
                // A SwiftUI `DragGesture` here starved FuturesDetailView's
                // ScrollView: this overlay is 280pt tall at full width, and an
                // identical 160pt swipe measured ~330pt of travel started off
                // the chart against 0.0pt started on it. FOUR compositions were
                // measured and all four read 0.0 — plain `.gesture`,
                // `.simultaneousGesture`, and each of those sequenced behind a
                // LongPressGesture. Removing the gesture entirely was the only
                // thing that scrolled, and that deletes the interaction.
                //
                // `shouldRecognizeSimultaneouslyWith` is the only layer that can
                // actually say "both of you may recognize this", so the scrub
                // runs on a UIKit pan. See `ChartScrubSurface` for the table.
                #if os(iOS)
                ChartScrubSurface(
                    onChange: { location, translation in
                        guard scrub.change(
                            width: translation.width,
                            height: translation.height
                        ) else {
                            // Latched vertical: the reader is scrolling, and
                            // because the pan now recognizes SIMULTANEOUSLY we
                            // are still being called throughout. Drop any
                            // crosshair placed by the undecided opening frames
                            // rather than letting it ride down the page.
                            crosshair = nil
                            return
                        }
                        updateCrosshair(at: location, proxy: proxy, geometry: geo)
                    },
                    onEnd: {
                        scrub.end()
                        crosshair = nil
                    }
                )
                #else
                // macOS: a trackpad scroll never contended for the touch, so
                // the ordinary gesture is correct and the UIKit bridge does not
                // exist to port.
                Color.clear
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { drag in
                                updateCrosshair(at: drag.location, proxy: proxy, geometry: geo)
                            }
                            .onEnded { _ in crosshair = nil }
                    )
                #endif
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text("\(Int(v))%")
                            .font(.caption2)
                    }
                }
            }
        }
        .chartXAxis {
            // #7077 — planned from the domain that is DRAWN, at the 9pt the
            // planner's label widths were measured in. See `axisPlan`.
            let plan = Self.axisPlan(for: entries.map(\.date), plotWidth: plotWidth)
            AxisMarks(values: .stride(by: plan.component, count: plan.count)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(
                    format: plan.format,
                    anchor: OddsChartView.xAxisLabelAnchor(
                        index: value.index, count: value.count)
                )
                .font(.system(size: 9))
            }
        }
        .onPreferenceChange(PlotWidthPreferenceKey.self) { width in
            plotWidth = width
        }
        .chartLegend(.hidden)
        .frame(height: height)
        .padding(.horizontal)
        .padding(.vertical, 8)
        // How a finger-driven test finds the region that used to swallow the
        // scroll. `.contain` is load-bearing for the same reason it is on
        // `DiscoverEventCard`: an identifier alone inherits down to every leaf
        // in the subtree, and a drag test that resolves to an axis label drags
        // the wrong 30pt frame. `.contain` lands it once, on an element with
        // the chart's own 280pt frame, without merging or hiding any child.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(Self.scrubSurfaceIdentifier)
    }

    /// How a tap-driven test finds the chart's touch surface.
    static let scrubSurfaceIdentifier = "evolution-chart-surface"

    // MARK: - Crosshair Update

    private func updateCrosshair(at location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard let date: Date = proxy.value(atX: location.x) else { return }
        let entries = chartEntries.filter { !$0.isCombined }
        // Find closest timestamp
        guard let closest = entries.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        }) else { return }

        let matchDate = closest.date
        let matchEntries = entries
            .filter { $0.date == matchDate && effectiveSelected.contains($0.name) }
            .sorted { $0.probability > $1.probability }

        let coloredEntries: [(name: String, probability: Double, color: Color)] = matchEntries.map { point in
            let idx = displayedNames.firstIndex(of: point.name) ?? 0
            let color = colorForOutcome(name: point.name, index: idx)
            return (name: point.name, probability: point.probability, color: color)
        }

        if !coloredEntries.isEmpty {
            crosshair = CrosshairData(date: matchDate, entries: coloredEntries)
        }
    }

    // MARK: - Crosshair Tooltip

    private var crosshairTooltip: some View {
        guard let crosshair else { return AnyView(EmptyView()) }
        let dateStr: String
        if selectedRange == .day || selectedRange == .today {
            dateStr = crosshair.date.formatted(.dateTime.hour().minute())
        } else {
            dateStr = crosshair.date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 4) {
                Text(dateStr)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                ForEach(Array(crosshair.entries.prefix(8).enumerated()), id: \.offset) { _, entry in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(entry.color)
                            .frame(width: 6, height: 6)
                        Text(entry.name)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text(String(format: "%.1f%%", entry.probability))
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color.cardBackground.opacity(0.95))
        )
    }

    // MARK: - Leaderboard Grid

    private var leaderboardGrid: some View {
        // #4373 — sized ONCE, here, off the outcomes this render is about to draw,
        // and handed to the header and every row. Two callers measuring separately
        // is how a header stops sitting over its own column.
        // #8109 — the strings the rows will draw, resolved BEFORE the measurement,
        // because the measured string and the drawn string have to be one call
        // (#4373). A column sized on `99%` under a row drawing a decided `100%`
        // clips a digit, which is this file's original defect wearing the new fix.
        let rows = displayedRows
        let percents = rows.map { row -> Int? in
            servedRenderedPercents.indices.contains(row.servedIndex)
                ? servedRenderedPercents[row.servedIndex] : nil
        }
        let columns = EvolutionLeaderboardGeometry.columns(
            for: rows.map(\.outcome), at: dynamicTypeSize, renderedPercents: percents)

        return VStack(spacing: 0) {
            EvolutionLeaderboardHeader(columns: columns)

            Divider()

            ForEach(Array(rows.enumerated()), id: \.element.outcome.name) { index, row in
                let outcome = row.outcome
                let isSelected = effectiveSelected.contains(outcome.name)
                let isHighlighted = highlightedName == nil || highlightedName == outcome.name
                let color = colorForOutcome(name: outcome.name, index: index)

                Button {
                    toggleSelection(outcome.name)
                } label: {
                    EvolutionLeaderboardRow(
                        position: index + 1,
                        outcome: outcome,
                        color: color,
                        isSelected: isSelected,
                        isHighlighted: isHighlighted,
                        columns: columns,
                        renderedPercent: percents[index])
                }
                .buttonStyle(.plain)
                .simultaneousGesture(
                    LongPressGesture(minimumDuration: 0.3)
                        .onEnded { _ in
                            withAnimation(.easeInOut(duration: 0.15)) {
                                highlightedName = highlightedName == outcome.name ? nil : outcome.name
                            }
                        }
                )

                if index < rows.count - 1 {
                    Divider().padding(.leading, 40)
                }
            }

            // Footer: selected count + reset
            HStack {
                Text("\(effectiveSelected.count) of \(displayedOutcomes.count) selected")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Spacer()
                if !selectedNames.isEmpty {
                    Button("Reset") {
                        selectedNames = []
                        highlightedName = nil
                    }
                    .font(.caption2)
                    .foregroundStyle(.blue)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
        }
    }

    // MARK: - Actions

    private func toggleSelection(_ name: String) {
        if selectedNames.contains(name) {
            selectedNames.remove(name)
        } else {
            selectedNames.insert(name)
        }
    }
}

// MARK: - Control Bar

/// The Evolution chart's control bar, as its own view so the suite can host and
/// measure the real thing rather than a model of it (#4199).
/// The leaderboard's column headings.
///
/// Extracted with `EvolutionLeaderboardRow` (#4373) so the header and the rows are
/// the same two widths by construction rather than by two people remembering to
/// change both — the previous pair of `50`s had already stopped matching what was
/// under them.
struct EvolutionLeaderboardHeader: View {
    let columns: EvolutionLeaderboardGeometry.Columns

    var body: some View {
        HStack {
            Text("#")
                .frame(width: 24, alignment: .leading)
            Text("Participant")
            Spacer()
            Text("Prob")
                .frame(width: columns.prob, alignment: .trailing)
            if let change = columns.change {
                Text("24h")
                    .frame(width: change, alignment: .trailing)
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .padding(.horizontal)
        .padding(.vertical, 6)
        .background(Color.cardBackground.opacity(0.5))
    }
}

/// One leaderboard row: position, participant, probability, 24-hour change.
///
/// 🔴 #4373 — THE MINI BAR IS GONE FROM THE `Prob` CELL, and that is the fix.
/// `EvolutionLeaderboardGeometry` carries the measurements; the short version is
/// that a 50pt cell spent 28 of its points on a 24pt bar and left 22 for a number
/// that needs 43.5, so the number wrapped its percent sign onto a second line on
/// every row of every leaderboard at every width.
///
/// The number is `lineLimit(1)` as well as measured. The measurement is what makes
/// it fit; the line limit is what makes a future miss show up as a clipped digit
/// rather than as this defect coming quietly back.
struct EvolutionLeaderboardRow: View {
    let position: Int
    let outcome: TimelineOutcomeMeta
    let color: Color
    let isSelected: Bool
    let isHighlighted: Bool
    let columns: EvolutionLeaderboardGeometry.Columns

    /// The whole percent this row's card decided for this outcome (#8109), or
    /// `nil` where there is no card-level decision to make. No default: a row that
    /// forgets to ask for the decision is the defect, and a defaulted `nil` is how
    /// that comes back silently — #8097's battery caught exactly that survivor,
    /// every renderer correctly wired while the thing feeding them handed out
    /// nothing.
    let renderedPercent: Int?

    /// 🔴 #7285 — BOTH OF THESE COALESCED TO ZERO, and the row then had no way to
    /// tell "we have no number" from "the number is zero". The dash it drew was
    /// right by luck; the sentence it SPOKE — "unchanged over 24 hours" — was a
    /// claim about a market we had no 24-hour reading for. The optional is kept
    /// alive as far as the labels, so each of the three readers below decides for
    /// itself: the drawn delta treats them alike, the drawn price and the spoken
    /// row do not.
    private var probPct: Double? { outcome.currentProbability.map { $0 * 100 } }
    private var changePct: Double? { outcome.probabilityChange24h.map { $0 * 100 } }

    /// Absence is not a direction, so it takes the same neutral tint a zero does.
    private var changeTint: Color {
        guard let changePct, changePct != 0 else { return .secondary }
        return changePct > 0 ? .green : .red
    }

    var body: some View {
        HStack(spacing: 6) {
            // Position + color dot
            HStack(spacing: 4) {
                Circle()
                    .fill(color)
                    .frame(width: 6, height: 6)
                    .opacity(isSelected ? 1 : 0.3)
                Text("\(position)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 24, alignment: .leading)

            // Logo + Name
            if let logo = outcome.logoSmall {
                TeamLogoView(
                    url: logo,
                    teamName: outcome.name,
                    color: color,
                    size: 18
                )
            }
            Text(outcome.name)
                .font(.subheadline)
                .fontWeight(isSelected ? .semibold : .regular)
                .foregroundStyle(isSelected ? .primary : .secondary)
                .lineLimit(1)
                .opacity(isHighlighted ? 1 : 0.4)

            if let record = outcome.record {
                Text(record)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Spacer()

            Text(EvolutionLeaderboardGeometry.probLabel(
                probPct, renderedPercent: renderedPercent))
                .font(.subheadline)
                .fontWeight(.semibold)
                .monospacedDigit()
                .lineLimit(1)
                .foregroundStyle(.primary)
                .frame(width: columns.prob, alignment: .trailing)

            if let change = columns.change {
                Text(EvolutionLeaderboardGeometry.changeLabel(changePct))
                    .font(.caption)
                    .fontWeight(.medium)
                    .monospacedDigit()
                    .lineLimit(1)
                    .foregroundStyle(changeTint)
                    .frame(width: change, alignment: .trailing)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(isSelected ? Color.accentColor.opacity(0.05) : Color.clear)
        // The delta leaves the SCREEN at accessibility sizes, never the row. Said
        // as one sentence because four separate elements is four swipes to learn
        // one line of a table.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            "\(position). \(outcome.name), "
            + "\(EvolutionLeaderboardGeometry.spokenProb(probPct, renderedPercent: renderedPercent)), "
            + EvolutionLeaderboardGeometry.spokenChange(changePct))
    }
}

/// One group of chips, abutting like a segmented control — on one line, or wrapped
/// onto as many lines as the width needs.
///
/// 🔴 #4445 — A GROUP THAT CANNOT WRAP IS A GROUP THAT CANNOT FIT. At
/// `.accessibility5` on a 375pt phone the four range chips want 414.5pt against the
/// bar's 343, and the three `Top N` chips want 383.5 — so no arrangement of WHOLE
/// groups fits, however they are stacked. `spacing: 0` in both arms is what keeps
/// the wrapped form reading as the same control rather than as loose buttons.
private struct ChipStrip<Content: View>: View {
    let wraps: Bool
    @ViewBuilder let content: Content

    var body: some View {
        if wraps {
            FlowLayout(spacing: 0) { content }
        } else {
            HStack(spacing: 0) { content }
        }
    }
}

struct EvolutionControlBar: View {
    /// Chip padding for the two single-row arms, roomiest first.
    ///
    /// 🔴 THERE IS NO PADDING THAT FITS EIGHT CHIPS ON ONE ROW AT 375pt, and finding
    /// that out is what the third arm below exists for. Measured by
    /// `EvolutionControlBarLayoutTests`: the four-range bar wants ~399pt at 8pt
    /// padding and ~351pt at 5pt, while the card on an iPhone SE gives the bar about
    /// **310pt**. Even zero padding leaves ~271pt of pure ink plus the checkbox and
    /// the group gaps. A third rung at 4pt was tried and photographed: it still
    /// overflowed, and `ViewThatFits` fell through to a horizontal scroller that put
    /// `Top 20` off the right edge — the same defect, quieter.
    static let chipPaddings: [CGFloat] = [8, 5]

    let availableRanges: [EvolutionTimeRange]
    @Binding var selectedRange: EvolutionTimeRange
    @Binding var showCombinedProbability: Bool
    /// Whether this market's outcomes can be added up at all
    /// (`EvolutionCombinedLinePolicy`). Defaulted `true` so the bar still composes
    /// on its own and so every existing caller — including the layout tests that
    /// measure the widest vocabulary — keeps measuring the bar WITH the `Sum` chip,
    /// which is the wide case and therefore the one worth pinning.
    var sumAvailable: Bool = true
    @Binding var topFilter: Int
    /// What the widest chip is called for THIS market (#7077). Defaulted so the
    /// bar still composes on its own — every caller that shows a real market
    /// passes `EvolutionRangeVocabulary.seasonWord`.
    var seasonWord: String = EvolutionTimeRange.season.rawValue
    var onRangeChange: () -> Void = {}

    var body: some View {
        VStack(spacing: 8) {
            ViewThatFits(in: .horizontal) {
                row(chipPadding: Self.chipPaddings[0])
                row(chipPadding: Self.chipPaddings[1])
                stackedRows(chipPadding: Self.chipPaddings[0])
                wrappedRows(chipPadding: Self.chipPaddings[0])
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.cardBackground.opacity(0.5))
    }

    /// The three groups, defined once. Every arm composes THESE, so no arm can
    /// disagree with another about what the bar contains or how a chip is drawn —
    /// the one-row and two-row layouts differ only in where the groups are put.
    ///
    /// Each chip carries `lineLimit(1)` AND `fixedSize`. The pair is the whole fix:
    /// `lineLimit` alone turns wrapping into truncation, which loses the same
    /// information (#3966), and `fixedSize` alone would still let a chip wrap.
    ///
    /// Exposed to the suite so a test can measure a chosen arm directly — asking
    /// `ViewThatFits` which one it picked is not something a test can do.
    @ViewBuilder
    func rangeGroup(chipPadding: CGFloat, wraps: Bool = false) -> some View {
        ChipStrip(wraps: wraps) {
            ForEach(availableRanges) { range in
                Button {
                    selectedRange = range
                    onRangeChange()
                } label: {
                    Text(range.label(seasonWord: seasonWord))
                        .font(.caption2)
                        .fontWeight(selectedRange == range ? .semibold : .regular)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .padding(.horizontal, chipPadding)
                        .padding(.vertical, 5)
                        .background(selectedRange == range ? Color.blue.opacity(0.15) : Color.clear)
                        .foregroundStyle(selectedRange == range ? .blue : .secondary)
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.secondary.opacity(0.2), lineWidth: 0.5)
        )
    }

    /// The `Sum` checkbox, drawn only where a sum is a probability.
    ///
    /// Absent rather than disabled, and with nothing put in its place. A greyed
    /// checkbox invites the question "why can't I?", and answering it on the page
    /// would be exactly the diagnostic prose notice 34 forbids — the reader gets the
    /// controls that mean something, and no paragraph about the one that doesn't.
    @ViewBuilder
    func sumToggle(chipPadding: CGFloat) -> some View {
        if sumAvailable {
            sumToggleButton(chipPadding: chipPadding)
        }
    }

    @ViewBuilder
    private func sumToggleButton(chipPadding: CGFloat) -> some View {
        Button {
            showCombinedProbability.toggle()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: showCombinedProbability ? "checkmark.square.fill" : "square")
                    .font(.system(size: 11))
                Text("Sum")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.horizontal, chipPadding)
            .padding(.vertical, 5)
            .foregroundStyle(showCombinedProbability ? .blue : .secondary)
        }
    }

    @ViewBuilder
    func topGroup(chipPadding: CGFloat, wraps: Bool = false) -> some View {
        ChipStrip(wraps: wraps) {
            ForEach([5, 10, 20], id: \.self) { n in
                Button {
                    topFilter = n
                } label: {
                    Text("Top \(n)")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .padding(.horizontal, chipPadding)
                        .padding(.vertical, 5)
                        .background(topFilter == n ? Color.primary : Color.clear)
                        .foregroundStyle(topFilter == n ? Color.systemBackground : .secondary)
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.barTrack, lineWidth: 0.5)
        )
    }

    /// All three groups on one row — the layout the bar has always had, now with
    /// chips that keep their words.
    @ViewBuilder
    func row(chipPadding: CGFloat) -> some View {
        HStack(spacing: 8) {
            rangeGroup(chipPadding: chipPadding)
            Spacer(minLength: 0)
            sumToggle(chipPadding: chipPadding)
            topGroup(chipPadding: chipPadding)
        }
    }

    /// 🔴 THE ARM THAT MAKES THE NARROW PHONE HONEST. Ranges above, `Sum` and the
    /// `Top N` group below. Its width is the wider of the two rows rather than the
    /// sum of all three groups, so it fits any phone **at the type sizes it was
    /// measured at**.
    ///
    /// ⚠️ IT IS NO LONGER THE TERMINAL ARM, and #4445 is why. "Fits any phone" was
    /// measured at `.large`, where it is true; the sentence did not carry its own
    /// scope, so nobody re-read it when Dynamic Type grew. At `.accessibility3` this
    /// arm's second row (`Sum` + `Top N`) wants 393pt against 343, and at
    /// `.accessibility5` 505 — so `ViewThatFits` fell through to it as a LAST resort
    /// and drew it overflowing. See `wrappedRows`.
    ///
    /// A second ROW is not the defect this ship fixes. #4199 is about words broken
    /// mid-syllable — `Se/aso/n` — not about a control that takes two lines. Every
    /// chip here is whole, on one line, and on screen; nothing is truncated and
    /// nothing has to be scrolled to.
    @ViewBuilder
    func stackedRows(chipPadding: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                rangeGroup(chipPadding: chipPadding)
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                sumToggle(chipPadding: chipPadding)
                topGroup(chipPadding: chipPadding)
                Spacer(minLength: 0)
            }
        }
    }

    /// 🔴 THE ARM THAT CANNOT OVERFLOW, AND #4445 IS THE FRAME THAT NEEDED IT.
    ///
    /// Photographed on master at `.accessibility5`, 375pt: the control bar demanded
    /// **545pt**, and because a card is as wide as its widest child, the bar dragged
    /// the WHOLE Evolution card to 545 and SwiftUI centred it. Everything else in
    /// the card fit 375 on its own and was clipped anyway — the leaderboard lost its
    /// rank, its colour dot and its logo off the left edge and its probability off
    /// the right, the header read `articipant … P`, and the y-axis read `0` where it
    /// meant `0%`. **One over-wide control cost the reader every number on the
    /// board.**
    ///
    /// So the last arm gives each group its own row AND lets the chips inside a
    /// group wrap. That makes fitting depend on the widest single CHIP rather than
    /// on the widest group, and the chip vocabulary is closed and short —
    /// `Season`/`6M`, `7d`, `Event`, `24h`, `Today`, `Sum`, `Top 5/10/20` — so there
    /// is no market and no type size at which this arm can overflow. That is what
    /// makes it a terminal arm; `stackedRows` was called one without the property.
    ///
    /// It is deliberately NOT a horizontal scroller. #4199 measured that one and
    /// photographed `Top 20` sitting off the right edge: a control you cannot see is
    /// not improved by being reachable.
    @ViewBuilder
    func wrappedRows(chipPadding: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            rangeGroup(chipPadding: chipPadding, wraps: true)
            sumToggle(chipPadding: chipPadding)
            topGroup(chipPadding: chipPadding, wraps: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
