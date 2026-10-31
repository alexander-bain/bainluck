import SwiftUI

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART TWO: THE NAMED-FIELD
/// WIN HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on `racing-live` the anchor chart draws
/// each displayed driver's own recorded price line — never normalized against
/// the others, never run on to now, never ended on a settled 0% or 100% — and
/// leaves every unrecorded stretch blank.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/futures/{id}/history`
/// body (`FuturesHistoryResponse`, `APIClient.fetchFuturesHistory`) of the race's
/// driver-winner market, that market's body (`FuturesMarketDetail`) and part one's
/// cohort. It decides nothing the app does not already decide:
///
///   - which line      the response's one line whose served `outcome_id` is the
///                     displayed outcome's id, and only when the response is for
///                     this market (`market_id`). Never a name: the source-mode
///                     `/probability-timeline` keys its lines by outcome NAME,
///                     which is not an identity, so this slot reads `/history`,
///                     the per-outcome series the verified chart already draws
///                     (`VerifiedTitleHistory.drawing`). A line with no id, or an
///                     id two lines share, draws nothing.
///   - not readings    a settlement point (`FuturesHistoryPoint.isSettlement`,
///                     #10955) is removed outright — no point, no gap — exactly as
///                     `VerifiedTitleHistory.drawing` sets it aside.
///   - where a line    an unreadable point (no value, outside 0…1, an unreadable,
///     breaks          non-advancing or future time) BREAKS the run where it sits;
///                     within the readable points, `EvolutionSeriesGaps.runs` — the
///                     futures chart's own per-series cadence rule — breaks every
///                     longer step. Two runs are never joined.
///   - no split        no race start time reaches the app (part one), so there is
///                     no pre-race/race split, no hollow "last pre-race" mark and
///                     no lap or report guide: H2's unconfirmed-start fallback, the
///                     recorded points drawn unsplit with the reason in the notes.
///   - the axis        `HockeyJourneyHistoryAdapter10868.xTicks` / `yTicks` / `frame`
///                     (`OddsChartView.xAxisPlan`, the same planner
///                     `EvolutionChartView.axisPlan` delegates to), so the candidate
///                     has one axis rule.
///   - every percent   `formatProbability`; clocks part one's; venue `SourceLabels`.
///   - key and tint    part one's display position, so each line matches its
///                     headline key.
///
/// The readout is each driver's LAST RECORDED point, bound to that exact point
/// and said with its own clock — a history reading, never offered as a current
/// chance (the headline owns currentness). Details and inspection are offered
/// unavailable until their owner contracts exist; only Full chart acts.
///
/// Nothing here fetches, subscribes, schedules or holds state. Host binding
/// still owed: the futures page does not hold this body — `EvolutionChartView`
/// fetches its own timeline inside `@State` — so Native must pass
/// `fetchFuturesHistory(marketId:hours:)`'s result in.
enum RacingHistoryAdapter10868 {
    typealias Page = RacingFieldPageAdapter10868

    enum Words {
        static let title = "Win probability"
        static let caption = "Recorded history · race start time unavailable"
        static let lastRecorded = "Last recorded"
        static let recorded = "Recorded"
        static let notRecorded = "Not recorded"
        static let noHistory = "No recorded history"
        /// No history response at all: says nothing about whether points exist or why.
        static let historyUnavailable = "History unavailable"
        static let independent = "Each line is that driver's own price, recorded at its own times. The lines are not adjusted to add up to 100%."
        static let startUnavailable = "The race start time is unavailable, so pre-race and race readings are not split."
        static let gapsNote = "Gaps remain blank."
        static let settledNote = "A settled result is not a chance, so no 0% or 100% point is shown."
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand race probability chart"
    }

    /// Offered unavailable until a history details destination exists.
    static let detailsActionID = "history.details"
    /// The one action the host routes: the full-size history reader.
    static let expandActionID = "history.expand"
    static let plotHeight: CGFloat = 260

    // MARK: - The history

    static func history(_ response: FuturesHistoryResponse, market: FuturesMarketDetail,
                        host: Page.Host) -> FieldHistoryInput10868 {
        let phase = Page.phase(market)
        let shown = Page.cohort(market, held: host.cohort)
        let drawn: [[[Vertex]]] = shown.map { outcome in
            guard let served = Self.line(for: outcome, in: response, market: market) else { return [] }
            return Self.runs(served, now: host.now)
        }
        let noteLines: [String] = Self.notes(market, phase: phase)
        let dates: [Date] = drawn.flatMap { runs in runs.flatMap { run in run.map(\.date) } }
        guard let first = dates.min(), let last = dates.max() else {
            return placeholder(market, shown: shown, words: Words.noHistory, notes: noteLines)
        }
        let domain = HockeyJourneyHistoryAdapter10868.frame(first, last)
        var series: [FieldHistorySeries10868] = []
        for (position, outcome) in shown.enumerated() {
            series.append(Self.series(outcome, position: position, runs: drawn[position], market: market, host: host))
        }
        // Each part on its own line, so the one large initializer stays cheap to type-check.
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let xTicks: [FieldHistoryTick10868] = HockeyJourneyHistoryAdapter10868.xTicks(domain, host: tickHost(host))
        let yTicks: [FieldHistoryTick10868] = HockeyJourneyHistoryAdapter10868.yTicks()
        let spoken: String = summary(shown, drawn: drawn)
        let details: FieldHistoryAction10868 = action(detailsActionID, Words.details, available: false)
        let expand: FieldHistoryAction10868 = action(expandActionID, Words.expand, spoken: Words.expandSpoken)
        return FieldHistoryInput10868(
            title: Words.title,
            caption: Words.caption,
            series: series,
            selection: .none,
            domain: plotted,
            ceiling: 1,
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
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: details,
            expand: expand,
            inspect: nil,
            previous: nil, next: nil, inspection: nil)
    }

    // MARK: - One line

    /// The response's one line for this outcome, by served outcome id, and only
    /// when the response is this market's.
    static func line(for outcome: FuturesOutcome, in response: FuturesHistoryResponse,
                     market: FuturesMarketDetail) -> FuturesHistoryOutcome? {
        guard response.marketId == market.id else { return nil }
        let matches = response.outcomes.filter { $0.outcomeId == outcome.id }
        return matches.count == 1 ? matches[0] : nil
    }

    /// One drawn point: its place in the served line, its served stamp and value.
    struct Vertex: Equatable {
        let index: Int
        /// Verbatim.
        let timestamp: String
        let date: Date
        let value: Double
    }

    /// The line's runs, in time order. Settlement points are removed outright;
    /// an unreadable point breaks the run where it sits; inside, the futures
    /// chart's own per-series cadence rule breaks every longer step.
    static func runs(_ line: FuturesHistoryOutcome, now: Date) -> [[Vertex]] {
        var readable: [(stretch: Int, vertex: Vertex)] = []
        var stretch = 0
        var previous: Date?
        for (index, point) in line.history.enumerated() {
            if point.isSettlement { continue }
            let advancing: Bool
            if let date = point.timestamp.asDate {
                advancing = previous.map { date > $0 } ?? true
            } else {
                advancing = false
            }
            guard advancing, let date = point.timestamp.asDate, date <= now,
                  let value = point.probability, value.isFinite, value >= 0, value <= 1
            else {
                stretch += 1
                continue
            }
            previous = date
            readable.append((stretch: stretch, vertex: Vertex(index: index, timestamp: point.timestamp,
                                                              date: date, value: value)))
        }
        let cadence: [Int] = EvolutionSeriesGaps.runs(readable.map { $0.vertex.date })
        var out: [[Vertex]] = []
        var held: (stretch: Int, run: Int)?
        for (offset, entry) in readable.enumerated() {
            let current = (stretch: entry.stretch, run: cadence[offset])
            if let held, held.stretch == current.stretch, held.run == current.run {
                out[out.count - 1].append(entry.vertex)
            } else {
                out.append([entry.vertex])
            }
            held = current
        }
        return out
    }

    // MARK: - One series

    static func series(_ outcome: FuturesOutcome, position: Int, runs drawn: [[Vertex]],
                       market: FuturesMarketDetail, host: Page.Host) -> FieldHistorySeries10868 {
        let id = seriesID(market, outcome)
        var runs: [FieldHistoryRun10868] = []
        for (number, run) in drawn.enumerated() {
            let points: [FieldHistoryPoint10868] = run.map { vertex in
                FieldHistoryPoint10868(id: pointID(id, vertex), x: vertex.date.timeIntervalSince1970,
                                       probability: vertex.value, style: .filled)
            }
            runs.append(FieldHistoryRun10868(id: "\(id)#run-\(number + 1)", points: points))
        }
        let before: FieldHistoryReading10868
        if let latest = drawn.last?.last {
            before = .observation(pointID: pointID(id, latest), figure: formatProbability(latest.value),
                                  provenance: provenance(latest, market: market, host: host))
        } else {
            before = .absent(words: Words.noHistory)
        }
        return FieldHistorySeries10868(id: id, name: outcome.name, shape: shape(position), tint: Page.tint(position),
                                       runs: runs, links: [], labelPointID: nil, before: before,
                                       recorded: .absent(words: Words.notRecorded),
                                       absentWords: Words.noHistory, choose: nil)
    }

    /// Part one's identity key: venue, market id, outcome id.
    static func seriesID(_ market: FuturesMarketDetail, _ outcome: FuturesOutcome) -> String {
        "\(Page.venueKey(market)):\(market.id):\(outcome.id)"
    }

    /// The served stamp is unique inside a line: drawn times strictly advance.
    static func pointID(_ seriesID: String, _ vertex: Vertex) -> String {
        "\(seriesID)#\(vertex.timestamp)"
    }

    /// The same shape part one gives this display position's headline key.
    static func shape(_ position: Int) -> FieldHistoryShape10868 {
        let shapes: [FieldHistoryShape10868] = [.circle, .diamond, .square]
        return shapes[position % shapes.count]
    }

    /// "Recorded Oct 3, 7:46 PM · Kalshi".
    static func provenance(_ vertex: Vertex, market: FuturesMarketDetail, host: Page.Host) -> String {
        let clock = "\(Words.recorded) \(Page.clockWords(vertex.date, host: host))"
        guard let venue = SourceLabels.label(for: market.source) else { return clock }
        return "\(clock) · \(venue)"
    }

    // MARK: - Words

    static func notes(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> [String] {
        var notes: [String] = []
        if let venue = SourceLabels.label(for: market.source) { notes.append("Source: \(venue)") }
        notes.append(Words.independent)
        notes.append(Words.startUnavailable)
        notes.append(Words.gapsNote)
        if phase == .final { notes.append(Words.settledNote) }
        return notes
    }

    /// Each driver's name and whether any of its history is drawn.
    static func summary(_ shown: [FuturesOutcome], drawn: [[[Vertex]]]) -> String {
        var named: [String] = []
        var missing: [String] = []
        for (outcome, runs) in zip(shown, drawn) {
            if runs.isEmpty { missing.append(outcome.name) } else { named.append(outcome.name) }
        }
        guard !named.isEmpty else { return Words.noHistory }
        let lead = "Recorded win probability for \(named.joined(separator: ", ")), each line that driver's own price."
        return missing.isEmpty ? lead : "\(lead) No recorded history for \(missing.joined(separator: ", "))."
    }

    static func action(_ id: String, _ label: String, spoken: String? = nil,
                       available: Bool = true) -> FieldHistoryAction10868 {
        HockeyJourneyHistoryAdapter10868.action(id, label, spoken: spoken, available: available)
    }

    static func tickHost(_ host: Page.Host) -> HockeyJourneyHistoryAdapter10868.Host {
        HockeyJourneyHistoryAdapter10868.Host(now: host.now, calendar: host.calendar, locale: host.locale)
    }

    // MARK: - Absence

    /// No history response at all — not arrived yet, or failed; the host does
    /// not say which, so neither is claimed. The chart slot says "History
    /// unavailable", names no source and offers no working control; the rest of
    /// the page composes from its own inputs.
    static func unavailable(_ market: FuturesMarketDetail, host: Page.Host) -> FieldHistoryInput10868 {
        placeholder(market, shown: Page.cohort(market, held: host.cohort), words: Words.historyUnavailable, notes: [])
    }

    /// Nothing to draw, in the owner's words: no point, axis or guide under it,
    /// and a placeholder domain the leaf never draws under an absence.
    static func placeholder(_ market: FuturesMarketDetail, shown: [FuturesOutcome], words: String,
                            notes: [String]) -> FieldHistoryInput10868 {
        var series: [FieldHistorySeries10868] = []
        for (position, outcome) in shown.enumerated() {
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
