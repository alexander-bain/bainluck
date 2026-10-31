import SwiftUI

/// #10868 — THE FIELD SCREEN'S PRODUCTION ADAPTER, PART TWO: THE NAMED-FIELD
/// WIN HISTORY, ON DESIGN'S AUTO / FULL SCALE.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on a championship field page the anchor
/// chart draws each displayed contender's own recorded win line — never
/// normalized against the others, never run on to now, never ended on a
/// settled 0% or 100% — leaves every unrecorded stretch blank, and opens on a
/// scale that keeps a 3% contender readable.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/futures/{id}/history`
/// body (`FuturesHistoryResponse`, `APIClient.fetchFuturesHistory`) of the field's
/// winner market, that market's body and part one's cohort. It decides nothing
/// the app does not already decide:
///
///   - whose history   the response is used ONLY when `market_id` is this
///                     market's id. Any other response is not this field's
///                     history, whatever its outcome ids: the slot says "History
///                     unavailable" exactly as when no response arrived — it never
///                     claims this field has no recorded history (Design's
///                     history identity rule; golf's `history.marketId ==
///                     market.id`).
///   - which line      the one line whose served `outcome_id` is the displayed
///                     outcome's id (`GolfFieldHistoryAdapter10868.line`); none or
///                     several draw nothing. Never a name.
///   - not readings    a settlement point (`FuturesHistoryPoint.isSettlement`,
///                     #10955) is removed outright, as `VerifiedTitleHistory.drawing`
///                     sets it aside.
///   - where a line    `GolfFieldHistoryAdapter10868.entries` / `.runs`: a served
///     breaks          point with no value, a value outside 0…1, an unreadable,
///                     non-advancing or future time BREAKS the run where it sits;
///                     within, `EvolutionSeriesGaps.runs` — the futures chart's
///                     own per-series cadence rule — breaks every longer step. Two
///                     runs are never joined. No time window is applied: no start
///                     reaches the app to open one on, so every served point up
///                     to now is drawn.
///   - no split        no start, so no before/during split, no hollow "last
///                     before" mark and no guide; the reason is in the notes.
///   - the axis        `GolfFieldHistoryAdapter10868.frame` and `.xTicks`
///                     (`EvolutionChartView.axisPlan` → `OddsChartView.xAxisPlan`),
///                     said in the reader's calendar.
///   - the scale       Design's approved Auto / Full choice, REUSED from golf
///                     (`GolfFieldHistoryAdapter10868.ceiling(peak:full:)`,
///                     `.yTicks(ceiling:)`, `.scaleAction(ceiling:full:)`): Full is
///                     0–100%; Auto is the first ladder rung at or above the
///                     highest PLOTTED point plus 4% headroom, so no point is ever
///                     clipped or clamped. The host owns the reversible flag and
///                     routes `GolfFieldHistoryAdapter10868.scaleActionID`.
///   - every percent   `formatProbability`; clocks part one's; venue `SourceLabels`.
///   - key and tint    part one's display position: the headline key shapes
///                     (circle, diamond, square) and the chart palette. A held
///                     choice an update omits draws no line (this update names
///                     nothing to draw it as) but keeps its position, so every
///                     drawn line keeps its own shape and colour.
///   - results         final only: the key context `Result · Won / Lost` from
///                     `FuturesDetailRowValue.of`, never a chart point.
///
/// The readout is each contender's LAST RECORDED point, bound to that exact
/// point and said with its own clock — a history reading, never offered as a
/// current chance (the headline owns currentness). Details and inspection are
/// offered unavailable until their owner contracts exist; Full chart and the
/// scale act.
///
/// Nothing here fetches, subscribes, schedules or holds state. Host binding
/// still owed: the futures page does not hold this body — `EvolutionChartView`
/// fetches its own timeline inside `@State` — so Native must pass
/// `fetchFuturesHistory(marketId:hours:)`'s result in.
enum FieldEventHistoryAdapter10868 {
    typealias Page = FieldEventPageAdapter10868
    typealias Golf = GolfFieldHistoryAdapter10868

    enum Words {
        static let title = "Win probability"
        static let caption = "Recorded history · start time unavailable"
        static let lastRecorded = "Last recorded"
        static let recorded = "Recorded"
        /// An unbound readout and the unused recorded slot: never claims nothing was recorded.
        static let readingUnavailable = "Reading unavailable"
        /// The response holds no reading for this contender. Said of this
        /// history only — never that none was ever recorded.
        static let noReadings = "No readings in this history"
        /// No usable response at all: says nothing about whether readings exist or why.
        static let historyUnavailable = "History unavailable"
        static let startUnavailable = "Start times are unavailable here, so readings are not split into before and during play."
        static let gapsNote = "Gaps remain blank."
        static let settledNote = "A settled result is not a chance, so no 0% or 100% point is shown."
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand win probability chart"
        static let result = "Result"
        static let resultSpoken = "Final result"

        static func independent(_ contender: Page.Contender) -> String {
            "Each line is that \(contender.singular)’s own chance, recorded at its own times. The lines are not adjusted to add up to 100%."
        }
    }

    /// Offered unavailable until a history details destination exists.
    static let detailsActionID = "field.history.details"
    /// The full-size history reader.
    static let expandActionID = "field.history.expand"
    /// Switches between Auto and Full: golf's own id, so one host rule routes both.
    static let scaleActionID = Golf.scaleActionID
    static let plotHeight: CGFloat = 240
    /// The headline key shapes, by display position.
    static let shapes: [FieldHistoryShape10868] = [.circle, .diamond, .square]

    // MARK: - The history

    /// The anchor for the host's snapshot. `full` is the host's scale choice.
    static func history(_ response: FuturesHistoryResponse, market: FuturesMarketDetail,
                        full: Bool = false, host: Page.Host) -> FieldHistoryInput10868 {
        // Another market's history is never this field's, however its outcome ids overlap.
        guard response.marketId == market.id else { return unavailable(market, host: host) }
        let phase = Page.phase(market)
        let shown = Page.cohort(market, host: host)
        let drawn: [[[Golf.Observation]]] = shown.served.map { runs($0, response: response, now: host.now) }
        let noteLines = notes(market, phase: phase)
        let dates: [Date] = drawn.flatMap { runs in runs.flatMap { run in run.map(\.date) } }
        guard let first = dates.min(), let last = dates.max() else {
            return placeholder(market, shown: shown, words: Words.noReadings, notes: noteLines)
        }
        let domain = Golf.frame(first, last)
        let peak: Double = drawn.flatMap { runs in runs.flatMap { run in run.map(\.probability) } }.max() ?? 0
        let top: Double = Golf.ceiling(peak: peak, full: full)
        var series: [FieldHistorySeries10868] = []
        for (index, outcome) in shown.served.enumerated() {
            series.append(Self.series(outcome, position: shown.position(index), runs: drawn[index],
                                      market: market, host: host))
        }
        // Each part on its own line, so the one large initializer stays cheap to type-check.
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let xTicks: [FieldHistoryTick10868] = Golf.xTicks(domain, host: host.golf)
        let yTicks: [FieldHistoryTick10868] = Golf.yTicks(ceiling: top)
        let spoken: String = summary(shown.served, drawn: drawn, market: market)
        let scale: FieldHistoryAction10868 = Golf.scaleAction(ceiling: top, full: full)
        let details: FieldHistoryAction10868 = action(detailsActionID, Words.details, available: false)
        let expand: FieldHistoryAction10868 = action(expandActionID, Words.expand, spoken: Words.expandSpoken)
        return FieldHistoryInput10868(
            title: Words.title,
            caption: Words.caption,
            series: series,
            selection: .none,
            domain: plotted,
            ceiling: top,
            yTicks: yTicks,
            xTicks: xTicks,
            guides: [],
            breaks: [],
            readout: .singleBefore(label: Words.lastRecorded),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: noteLines,
            summary: spoken,
            plotHeight: plotHeight,
            unboundReadingWords: Words.readingUnavailable,
            plotUnavailableWords: nil,
            windows: nil, scale: scale, moreOriginals: nil,
            details: details,
            expand: expand,
            inspect: nil,
            previous: nil, next: nil, inspection: nil)
    }

    // MARK: - One line

    /// The contender's runs: its one served line by outcome id, settlement
    /// points removed, broken at every served break and wherever the futures
    /// chart's cadence rule breaks it. No line, or several, draw nothing.
    static func runs(_ outcome: FuturesOutcome, response: FuturesHistoryResponse, now: Date) -> [[Golf.Observation]] {
        guard let points = Golf.line(response, outcomeID: outcome.id) else { return [] }
        return Golf.runs(Golf.entries(points, now: now), from: nil)
    }

    // MARK: - One series

    static func series(_ outcome: FuturesOutcome, position: Int, runs drawn: [[Golf.Observation]],
                       market: FuturesMarketDetail, host: Page.Host) -> FieldHistorySeries10868 {
        let id = seriesID(market, outcome)
        var runs: [FieldHistoryRun10868] = []
        for (number, run) in drawn.enumerated() {
            let points: [FieldHistoryPoint10868] = run.map { observation in
                FieldHistoryPoint10868(id: pointID(id, observation), x: observation.date.timeIntervalSince1970,
                                       probability: observation.probability, style: .filled)
            }
            runs.append(FieldHistoryRun10868(id: "\(id)#run-\(number + 1)", points: points))
        }
        let before: FieldHistoryReading10868
        if let latest = drawn.last?.last {
            before = .observation(pointID: pointID(id, latest), figure: formatProbability(latest.probability),
                                  provenance: provenance(latest, market: market, host: host))
        } else {
            before = .absent(words: Words.noReadings)
        }
        return FieldHistorySeries10868(id: id, name: outcome.name, shape: shape(position), tint: Page.tint(position),
                                       runs: runs, links: [], labelPointID: nil, before: before,
                                       recorded: .absent(words: Words.readingUnavailable),
                                       absentWords: Words.noReadings, choose: nil,
                                       keyContext: keyContext(outcome, market: market))
    }

    /// Part one's identity key: venue, market id, outcome id.
    static func seriesID(_ market: FuturesMarketDetail, _ outcome: FuturesOutcome) -> String {
        "\(Page.venueKey(market)):\(market.id):\(outcome.id)"
    }

    /// The served stamp is unique inside a line: drawn times strictly advance.
    static func pointID(_ seriesID: String, _ observation: Golf.Observation) -> String {
        "\(seriesID)#\(observation.timestamp)"
    }

    /// The same shape part one gives this display position's headline key.
    static func shape(_ position: Int) -> FieldHistoryShape10868 {
        shapes[position % shapes.count]
    }

    /// "Recorded Oct 12, 10:40 AM · Kalshi".
    static func provenance(_ observation: Golf.Observation, market: FuturesMarketDetail, host: Page.Host) -> String {
        let clock = "\(Words.recorded) \(Page.clockWords(observation.date, host: host))"
        guard let venue = SourceLabels.label(for: market.source) else { return clock }
        return "\(clock) · \(venue)"
    }

    /// The Market Details result rule, final only: Won / Lost in the key, else none.
    static func keyContext(_ outcome: FuturesOutcome, market: FuturesMarketDetail) -> FieldHistoryKeyContext10868? {
        guard Page.phase(market) == .final,
              case .verdict(let verdict) = FuturesDetailRowValue.of(outcome, marketStatus: market.status,
                                                                     marketSource: market.source)
        else { return nil }
        return FieldHistoryKeyContext10868(label: Words.result, words: verdict.label,
                                           spoken: "\(Words.resultSpoken): \(verdict.label)")
    }

    // MARK: - Words

    static func notes(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> [String] {
        var notes: [String] = []
        if let venue = SourceLabels.label(for: market.source) { notes.append("Source: \(venue)") }
        notes.append(Words.independent(Page.contender(market)))
        notes.append(Words.startUnavailable)
        notes.append(Words.gapsNote)
        if phase == .final { notes.append(Words.settledNote) }
        return notes
    }

    /// Each contender's name and whether any of its history is drawn.
    static func summary(_ shown: [FuturesOutcome], drawn: [[[Golf.Observation]]], market: FuturesMarketDetail) -> String {
        var named: [String] = []
        var missing: [String] = []
        for (outcome, runs) in zip(shown, drawn) {
            if runs.isEmpty { missing.append(outcome.name) } else { named.append(outcome.name) }
        }
        guard !named.isEmpty else { return Words.noReadings }
        let contender = Page.contender(market)
        let lead = "Recorded win probability for \(named.joined(separator: ", ")), each line that \(contender.singular)’s own chance."
        return missing.isEmpty ? lead : "\(lead) No readings in this history for \(missing.joined(separator: ", "))."
    }

    static func action(_ id: String, _ label: String, spoken: String? = nil,
                       available: Bool = true) -> FieldHistoryAction10868 {
        Golf.action(id, label, spoken: spoken, available: available)
    }

    // MARK: - Absence

    /// No usable history response — not arrived, failed, or another market's;
    /// the host does not say which, so none is claimed. The chart slot says
    /// "History unavailable", names no source and offers no working control;
    /// the rest of the page composes from its own inputs.
    static func unavailable(_ market: FuturesMarketDetail, host: Page.Host) -> FieldHistoryInput10868 {
        placeholder(market, shown: Page.cohort(market, host: host), words: Words.historyUnavailable, notes: [])
    }

    /// Nothing to draw, in the owner's words: no point, axis or guide under it,
    /// and a placeholder domain the leaf never draws under an absence.
    static func placeholder(_ market: FuturesMarketDetail, shown: Page.Cohort, words: String,
                            notes: [String]) -> FieldHistoryInput10868 {
        var series: [FieldHistorySeries10868] = []
        for (index, outcome) in shown.served.enumerated() {
            let position = shown.position(index)
            series.append(FieldHistorySeries10868(
                id: seriesID(market, outcome), name: outcome.name, shape: shape(position), tint: Page.tint(position),
                runs: [], links: [], labelPointID: nil, before: .absent(words: words),
                recorded: .absent(words: words), absentWords: words, choose: nil))
        }
        let details: FieldHistoryAction10868 = action(detailsActionID, Words.details, available: false)
        return FieldHistoryInput10868(
            title: Words.title,
            caption: Words.caption,
            series: series,
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: Words.lastRecorded),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: notes,
            summary: words,
            plotHeight: plotHeight,
            unboundReadingWords: words,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: details,
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: FieldHistoryPlotAbsence10868(title: words, words: nil))
    }
}
