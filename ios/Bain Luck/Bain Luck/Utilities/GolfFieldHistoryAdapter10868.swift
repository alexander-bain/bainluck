import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART TWO: EACH
/// GOLFER'S READINGS AND THE NAMED "CHANCE TO WIN" HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: the tournament screen's anchor draws each
/// golfer in the chart as their own recorded line, breaks it wherever the futures
/// chart would, and reads each golfer's last price before the listed start and
/// latest recorded price since — never a result, a stale quote called current,
/// or a line across a span nobody priced.
///
/// It builds `FieldHistoryInput10868` from the Winner market's decoded
/// `/api/futures/{id}/history` body (`FuturesHistoryResponse`) and its detail
/// (`FuturesMarketDetail`), for the golfers the HOST names in the chart. It also
/// owns `Field`, the one place a golfer's before and later readings are decided,
/// so the chart, chooser, contenders card and finish card can never read one
/// golfer two ways. Each part is the output of the authority that owns it:
///
///   - which line     the served line whose `outcome_id` is the golfer's exact
///                    outcome id — exactly one, never a name match.
///   - not prices     a settlement point (`FuturesHistoryPoint.isSettlement`,
///                    #10955) is removed outright, exactly as
///                    `VerifiedTitleHistory.drawing` sets it aside: a result, never
///                    a price.
///   - breaks         `EvolutionSeriesGaps.runs` (EvolutionChartView.swift:137),
///                    the futures chart's per-series rule (six median gaps, two
///                    hours minimum, none under four points), over the golfer's
///                    observations inside the frame. A served point with no price,
///                    an unreadable time or a time that does not advance BREAKS
///                    the line here, where the chart would skip it and join across
///                    — the one place this file is stricter than the chart.
///   - frame          `EvolutionChartView.timeCutoff` for the range the chart
///                    opens on (EvolutionChartView.swift:821, :556): `.week` before
///                    the listed start, `.tournament` (listed start less six hours)
///                    after it. Nothing after the reader's now is drawn.
///   - readings       before: the golfer's last observation strictly before the
///                    listed start; when the golfer has no served line, the
///                    detail's price at its own `last_updated` (the clock
///                    `FuturesPriceAge` dates a price by), only when that stamp is
///                    before the listed start. Later (recorded phase only): the
///                    last observation at or after the listed start, else the
///                    detail's price only when its stamp is at or after it — a
///                    pre-start quote is never the recorded estimate. An untimed
///                    `opening_probability` is never a reading, and neither is the
///                    price of a row `FuturesDetailRowValue.of` grades or calls
///                    unknown (its price may be its settlement).
///   - figures        `formatProbability` (FormattingUtilities.swift:12); a detail
///                    price with `futuresDetailRenderedPercents` (the Market
///                    Details integer, FuturesDetailView.swift:43).
///   - axis           `EvolutionChartView.axisPlan` (→ `OddsChartView.xAxisPlan`)
///                    and `OddsChartView.xAxisTicks`, said in the reader's
///                    calendar; y ticks through `OddsChartView.axisLabel`.
///   - tints          `EvolutionOutcomeColour.markHex` by chart position, the
///                    futures chart's own palette (EvolutionChartView.swift:337).
///   - source words   `SourceLabels.attribution(for:)` over the market's served
///                    contributors ("Probabilities from the DataGolf model").
///   - results        final only, a key context from `FuturesDetailRowValue.of`
///                    (the Market Details rule) when it grades the row Won / Lost.
///
/// Phase scopes:
///   before   — readable observations from a week before now; one readout, the
///              golfer's latest reading before the listed start.
///   recorded — from six hours before the listed start to now; the last reading
///              before the listed start (hollow when drawn, said beside the plot
///              when it is older than the frame) and the latest recorded reading.
///   final    — the same frame to the last served price; the before reading only.
///              The last served price is never read out after resolution: the
///              retained Baycurrent Classic history ends every golfer's line on a
///              22:08Z row that re-serves the Oct 6 pre-tournament price after
///              play (Brennan 1.0 at 06:41Z, then 0.026017), a served defect this
///              file draws as the chart does but never reads as a finish.
///
/// OWED, NOT MANUFACTURED:
///   - the chart cohort (which golfers are drawn): `EvolutionChartView` elects the
///     timeline's first three served outcomes inside its private state; no owner
///     exposes a cohort for this page, so the host passes it.
///   - round guides: `/history` serves `round_boundaries`, undecoded and stamped at
///     ~00:02 UTC data days, and the chart's own R1–R4 marks are UTC midnights
///     private to the View — neither is a round start, so no guide is drawn.
///   - Details, inspection, held windows: no owner contracts exist; Details is
///     offered unavailable and no inspection is built.
///   - post-play re-served prices (above): owner, the DataGolf futures ingest.
///
/// THE SCALE is Design's approved Auto / Full choice (prototype
/// `golfJourneyEvidence.ts` `chartCeiling`, `GolfRaceChart.tsx`; Design
/// 2026-10-31): Full is the whole 0–100%; Auto is the first rung of
/// `scaleLadder` at or above the highest PLOTTED point plus 4% headroom, so early
/// low chances stay readable and every plotted point stays inside the axis — none
/// is ever clipped or clamped. The host owns the reversible full flag.
///
/// Nothing here fetches, subscribes, schedules or holds state.
enum GolfFieldHistoryAdapter10868 {
    typealias Host = GolfFieldPageAdapter10868.Host

    enum Words {
        static let title = "Chance to win"
        static let beforeCaption = "Before the start date · last 7 days"
        static let recordedCaption = "Since the start date"
        static let finalCaption = "Tournament history"
        static let beforeLabel = "Before start"
        static let latestLabel = "Latest recorded"
        static let noStartWords = "Start date unavailable"
        static let notRecorded = "Not recorded"
        static let notBeforeStart = "Before-start chance not recorded"
        static let notSinceStart = "Chance since the start not recorded"
        static let noHistory = "No recorded history"
        /// No history response at all: says nothing about whether rows exist or why.
        static let historyUnavailable = "History unavailable"
        static let hollowKey = "Hollow · last chance before the start date"
        static let gapsNote = "Gaps remain blank."
        static let splitNote = "“Before start” uses the tournament’s start date, not a tee time."
        static let recorded = "Recorded"
        static let updated = "Updated"
        static let result = "Result"
        static let resultSpoken = "Final result"
        static let selectedMissing = "No chance history for the selected golfer in this chart."
        static let selectedOutside = "The selected golfer isn’t in this chart."
        static let chooseGolfers = "Choose golfers"
        static let choose = "Choose"
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand chance to win history"
        static let autoScale = "Auto scale"
        static let fullScale = "Full scale"
        /// The reference's spoken words for the control (`GolfRaceChart.tsx`).
        static let useAutoScale = "Use automatic probability scale"
        static let showFullScale = "Show full zero to 100 percent scale"
    }

    /// Offered unavailable until a history details destination exists.
    static let detailsActionID = "golf.history.details"
    /// Opens the full-size history reader.
    static let expandActionID = "golf.history.expand"
    /// Opens the golfer chooser.
    static let chooserActionID = "golf.history.chooser"
    /// A series' choose action is this prefix and the golfer's outcome id.
    static let choosePrefix = "golf.history.choose."
    /// Switches between the Auto and Full scale.
    static let scaleActionID = "golf.history.scale"

    static let plotHeight: CGFloat = 230
    /// The approved Auto ceilings, lowest first (`chartCeiling`).
    static let scaleLadder: [Double] = [0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.4, 0.6, 0.8, 1]
    /// Auto leaves 4% headroom above the highest plotted point.
    static let scaleHeadroom = 1.04
    static let shapes: [FieldHistoryShape10868] = [.circle, .square, .diamond, .triangle]

    // MARK: - One golfer's served line

    /// One served price, admitted as an observation.
    struct Observation: Equatable {
        /// Position in the served line.
        let index: Int
        /// Verbatim.
        let timestamp: String
        let date: Date
        let probability: Double
    }

    /// One served point after the settlement is set aside: an observation, or a
    /// break the line may not be drawn across.
    enum Entry: Equatable {
        case observation(Observation)
        case gap
    }

    /// The served line for exactly this outcome id, or nil when there is none or several.
    static func line(_ response: FuturesHistoryResponse, outcomeID: Int) -> [FuturesHistoryPoint]? {
        let lines = response.outcomes.filter { $0.outcomeId == outcomeID }
        return lines.count == 1 ? lines[0].history : nil
    }

    /// The served points in served order. A settlement point is removed; a point
    /// with no price, a price outside 0…1, an unreadable or non-advancing time, or
    /// a time after now is a break.
    static func entries(_ points: [FuturesHistoryPoint], now: Date) -> [Entry] {
        var previous: Date?
        var out: [Entry] = []
        for (index, point) in points.enumerated() {
            if point.isSettlement { continue }
            guard let date = point.timestamp.asDate else {
                out.append(.gap)
                continue
            }
            if let before = previous, date <= before {
                out.append(.gap)
                continue
            }
            previous = date
            guard date <= now, let value = point.probability, value.isFinite, value >= 0, value <= 1 else {
                out.append(.gap)
                continue
            }
            out.append(.observation(Observation(index: index, timestamp: point.timestamp, date: date, probability: value)))
        }
        return out
    }

    static func observations(_ entries: [Entry]) -> [Observation] {
        entries.compactMap { entry in
            if case .observation(let observation) = entry { return observation }
            return nil
        }
    }

    // MARK: - Readings

    /// One admitted reading: its raw value, its own clock and where it came from.
    struct Reading: Equatable {
        enum Kind: Equatable {
            /// A `/history` observation at its served timestamp.
            case recorded(timestamp: String)
            /// The detail's price at its own `last_updated`, with the Market
            /// Details integer for that row.
            case price(renderedPercent: Int?)
        }

        let probability: Double
        let date: Date
        let kind: Kind
    }

    /// One market's golfers and readings, decided once for one snapshot.
    struct Field {
        let market: FuturesMarketDetail
        let history: FuturesHistoryResponse?
        let phase: GolfFinishPhase10868
        let listedStart: Date?
        let now: Date
        private let percents: [Int: Int]

        init(market: FuturesMarketDetail, history: FuturesHistoryResponse?, phase: GolfFinishPhase10868,
             listedStart: Date?, now: Date) {
            self.market = market
            self.history = history
            self.phase = phase
            self.listedStart = listedStart
            self.now = now
            percents = futuresDetailRenderedPercents(market.outcomes)
        }

        /// Exactly one detail outcome with this id, or nil.
        func outcome(_ id: Int) -> FuturesOutcome? {
            let matches = market.outcomes.filter { $0.id == id }
            return matches.count == 1 ? matches[0] : nil
        }

        /// The golfer's served points as entries, or nil when the golfer has no
        /// single served line.
        func entries(_ id: Int) -> [Entry]? {
            // Another market's history is never this field's, however its outcome ids overlap.
            guard let history, history.marketId == market.id,
                  let points = GolfFieldHistoryAdapter10868.line(history, outcomeID: id) else { return nil }
            return GolfFieldHistoryAdapter10868.entries(points, now: now)
        }

        /// The detail's price at its own stamp, or nil. Never the untimed opening,
        /// and never the price of a row the Market Details rule grades or calls
        /// unknown — that price may be its settlement (an open market can carry a
        /// graded leg, #6082), and a settlement is never a chance.
        func price(_ outcome: FuturesOutcome) -> Reading? {
            guard priceIsReadable(outcome),
                  let value = outcome.probability, value.isFinite, value >= 0, value <= 1,
                  let date = outcome.lastUpdated?.asDate, date <= now else { return nil }
            return Reading(probability: value, date: date, kind: .price(renderedPercent: percents[outcome.id]))
        }

        func priceIsReadable(_ outcome: FuturesOutcome) -> Bool {
            switch FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source) {
            case .verdict, .resultUnknown: return false
            case .price, .none: return true
            }
        }

        /// The last reading strictly before the listed start: the golfer's last
        /// observation before it, else the detail's price when its own stamp is
        /// before it. None without a listed start.
        func before(_ id: Int) -> Reading? {
            guard let start = listedStart else { return nil }
            if let entries = entries(id),
               let last = GolfFieldHistoryAdapter10868.observations(entries).last(where: { $0.date < start }) {
                return Self.reading(last)
            }
            guard let outcome = outcome(id), let price = price(outcome), price.date < start else { return nil }
            return price
        }

        /// The latest reading at or after the listed start — recorded phase only:
        /// the golfer's last observation since it, else the detail's price when
        /// its own stamp is at or after it. A pre-start quote is never this
        /// reading. Without a listed start, the latest reading at all.
        func later(_ id: Int) -> Reading? {
            guard phase == .recorded else { return nil }
            if let entries = entries(id) {
                let observed = GolfFieldHistoryAdapter10868.observations(entries)
                let since = listedStart.map { start in observed.filter { $0.date >= start } } ?? observed
                if let last = since.last { return Self.reading(last) }
            }
            guard let outcome = outcome(id), let price = price(outcome) else { return nil }
            if let start = listedStart, price.date < start { return nil }
            return price
        }

        static func reading(_ observation: Observation) -> Reading {
            Reading(probability: observation.probability, date: observation.date,
                    kind: .recorded(timestamp: observation.timestamp))
        }

        /// The Market Details result rule, final only: Won / Lost, else nil.
        func verdict(_ id: Int) -> OutcomeVerdict? {
            guard phase == .final, let outcome = outcome(id) else { return nil }
            if case .verdict(let verdict) = FuturesDetailRowValue.of(outcome, marketStatus: market.status,
                                                                     marketSource: market.source) {
                return verdict
            }
            return nil
        }
    }

    static func figure(_ reading: Reading) -> String {
        switch reading.kind {
        case .recorded: formatProbability(reading.probability)
        case .price(let rendered): formatProbability(reading.probability, renderedPercent: rendered)
        }
    }

    /// "Recorded Oct 6, 6:08 AM · DataGolf" / "Updated Oct 12, 4:11 PM · DataGolf".
    static func provenance(_ reading: Reading, market: FuturesMarketDetail, host: Host) -> String {
        let verb: String
        switch reading.kind {
        case .recorded: verb = Words.recorded
        case .price: verb = Words.updated
        }
        let clock = "\(verb) \(GolfFieldPageAdapter10868.clockWords(reading.date, host: host))"
        return GolfFieldPageAdapter10868.joined([clock, GolfFieldPageAdapter10868.sourceName(market)]) ?? clock
    }

    // MARK: - The history

    static func history(_ field: Field, cohort: [Int], selected: Int?,
                        chooserAvailable: Bool, full: Bool = false, host: Host) -> FieldHistoryInput10868 {
        let golfers = drawnGolfers(field, cohort: cohort)
        let cutoff = frameCutoff(field)
        let drawn: [[[Observation]]] = golfers.map { runs(field.entries($0.id) ?? [], from: cutoff) }
        let dates = drawn.flatMap { $0.flatMap { $0.map(\.date) } }
        guard let first = dates.min(), let last = dates.max() else {
            return absence(field, golfers: golfers, selected: selected, chooserAvailable: chooserAvailable,
                           plot: FieldHistoryPlotAbsence10868(title: Words.noHistory, words: nil))
        }
        let domain = frame(first, last)
        let peak = drawn.flatMap { $0.flatMap { $0.map(\.probability) } }.max() ?? 0
        let top = ceiling(peak: peak, full: full)
        var series: [FieldHistorySeries10868] = []
        for (position, golfer) in golfers.enumerated() {
            series.append(self.series(field, golfer: golfer, position: position, runs: drawn[position], host: host))
        }
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let names: [(String, Bool)] = golfers.enumerated().map { ($0.element.name, !drawn[$0.offset].isEmpty) }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: caption(field.phase),
            series: series,
            selection: selection(field, golfers: golfers, selected: selected),
            domain: plotted,
            ceiling: top,
            yTicks: yTicks(ceiling: top),
            xTicks: xTicks(domain, host: host),
            guides: [],
            breaks: [],
            readout: readout(field),
            markKey: FieldHistoryMarkKey10868(hollow: field.listedStart == nil ? nil : Words.hollowKey, filled: nil),
            comparisonExplanation: nil,
            notes: notes(field),
            summary: summary(names),
            plotHeight: plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: scaleAction(ceiling: top, full: full),
            moreOriginals: chooserAction(available: chooserAvailable),
            details: action(detailsActionID, Words.details, available: false),
            expand: action(expandActionID, Words.expand, spoken: Words.expandSpoken),
            inspect: nil, previous: nil, next: nil, inspection: nil)
    }

    /// The host's chart golfers that resolve to exactly one detail outcome, in
    /// the host's order; a repeated id is drawn once, where it first appears.
    static func drawnGolfers(_ field: Field, cohort: [Int]) -> [FuturesOutcome] {
        var seen: Set<Int> = []
        var golfers: [FuturesOutcome] = []
        for id in cohort where !seen.contains(id) {
            seen.insert(id)
            if let outcome = field.outcome(id) { golfers.append(outcome) }
        }
        return golfers
    }

    /// The futures chart's own cutoff for the range it opens on.
    static func frameCutoff(_ field: Field) -> Date? {
        let range: EvolutionTimeRange = field.phase == .before ? .week : .tournament
        return EvolutionChartView.timeCutoff(for: range, tournamentStart: field.listedStart, now: field.now)
    }

    /// The golfer's runs inside the frame: broken at every served break and
    /// wherever the futures chart's per-series rule breaks the observations.
    static func runs(_ entries: [Entry], from cutoff: Date?) -> [[Observation]] {
        let windowed: [Entry] = entries.filter { entry in
            guard case .observation(let observation) = entry, let cutoff else { return true }
            return observation.date >= cutoff
        }
        let kept = observations(windowed)
        let numbers = EvolutionSeriesGaps.runs(kept.map(\.date))
        var runs: [[Observation]] = []
        var current: [Observation] = []
        var position = 0
        var lastNumber: Int?
        for entry in windowed {
            switch entry {
            case .gap:
                if !current.isEmpty { runs.append(current) }
                current = []
            case .observation(let observation):
                let number = numbers[position]
                position += 1
                if let lastNumber, lastNumber != number, !current.isEmpty {
                    runs.append(current)
                    current = []
                }
                lastNumber = number
                current.append(observation)
            }
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }

    static func series(_ field: Field, golfer: FuturesOutcome, position: Int, runs: [[Observation]],
                       host: Host) -> FieldHistorySeries10868 {
        let id = seriesID(field.market, outcomeID: golfer.id)
        let before = field.before(golfer.id)
        let hollowStamp: String? = {
            guard let before, case .recorded(let stamp) = before.kind,
                  runs.contains(where: { $0.contains { $0.timestamp == stamp } }) else { return nil }
            return stamp
        }()
        let fieldRuns: [FieldHistoryRun10868] = runs.enumerated().map { number, run in
            FieldHistoryRun10868(id: "\(id)#run-\(number + 1)", points: run.map { observation in
                FieldHistoryPoint10868(id: pointID(id, observation.timestamp), x: observation.date.timeIntervalSince1970,
                                       probability: observation.probability,
                                       style: observation.timestamp == hollowStamp ? .hollow : .filled)
            })
        }
        let beforeSlot = reading(before, field: field, seriesID: id, runs: runs,
                                 missing: field.listedStart == nil ? Words.noStartWords : Words.notBeforeStart, host: host)
        let recordedSlot = field.phase == .recorded
            ? reading(field.later(golfer.id), field: field, seriesID: id, runs: runs,
                      missing: field.listedStart == nil ? Words.notRecorded : Words.notSinceStart, host: host)
            : FieldHistoryReading10868.absent(words: Words.notRecorded)
        return FieldHistorySeries10868(
            id: id, name: golfer.name, shape: shapes[position % shapes.count], tint: tint(position),
            runs: fieldRuns, links: [], labelPointID: nil,
            before: beforeSlot, recorded: recordedSlot, absentWords: Words.noHistory,
            choose: action("\(choosePrefix)\(golfer.id)", golfer.name, spoken: "\(Words.choose) \(golfer.name)"),
            keyContext: keyContext(field, outcomeID: golfer.id))
    }

    /// A reading slot: bound to its drawn point, else said beside the plot,
    /// else the slot's own absence words.
    static func reading(_ reading: Reading?, field: Field, seriesID: String,
                        runs: [[Observation]], missing: String, host: Host) -> FieldHistoryReading10868 {
        guard let reading else { return .absent(words: missing) }
        let figure = self.figure(reading)
        let provenance = self.provenance(reading, market: field.market, host: host)
        if case .recorded(let stamp) = reading.kind,
           runs.contains(where: { $0.contains { $0.timestamp == stamp } }) {
            return .observation(pointID: pointID(seriesID, stamp), figure: figure, provenance: provenance)
        }
        return .independent(figure: figure, provenance: provenance)
    }

    static func keyContext(_ field: Field, outcomeID: Int) -> FieldHistoryKeyContext10868? {
        guard let verdict = field.verdict(outcomeID) else { return nil }
        return FieldHistoryKeyContext10868(label: Words.result, words: verdict.label,
                                           spoken: "\(Words.resultSpoken): \(verdict.label)")
    }

    /// The same labels with or without a start date; without one, each golfer's
    /// before slot says the start date is unavailable.
    static func readout(_ field: Field) -> FieldHistoryReadoutIntent10868 {
        switch field.phase {
        case .recorded: return .beforeAndRecorded(beforeLabel: Words.beforeLabel, recordedLabel: Words.latestLabel)
        case .before, .final: return .singleBefore(label: Words.beforeLabel)
        }
    }

    static func selection(_ field: Field, golfers: [FuturesOutcome], selected: Int?) -> FieldHistoryOriginalSelection10868 {
        guard let selected else { return .none }
        guard golfers.contains(where: { $0.id == selected }) else { return .unavailable(words: Words.selectedOutside) }
        return .series(id: seriesID(field.market, outcomeID: selected), missingWords: Words.selectedMissing)
    }

    static func caption(_ phase: GolfFinishPhase10868) -> String {
        switch phase {
        case .before: Words.beforeCaption
        case .recorded: Words.recordedCaption
        case .final: Words.finalCaption
        }
    }

    static func notes(_ field: Field) -> [String] {
        var notes: [String] = []
        if let attribution = SourceLabels.attribution(for: field.market.bookmakers ?? []) {
            notes.append(attribution)
        } else if let name = GolfFieldPageAdapter10868.sourceName(field.market) {
            notes.append(name)
        }
        if field.phase != .before, field.listedStart != nil { notes.append(Words.splitNote) }
        notes.append(Words.gapsNote)
        return notes
    }

    // MARK: - Frame and axes

    /// First to last drawn observation. A single instant opens by the chart's
    /// own minimum padding (`OddsChartView.naturalDomain`), so the domain is valid.
    static func frame(_ first: Date, _ last: Date) -> ClosedRange<Date> {
        guard last > first else {
            return OddsChartView.naturalDomain(of: [first]) ?? (first...first.addingTimeInterval(60))
        }
        return first...last
    }

    // MARK: - The Auto / Full scale

    /// Full: 1. Auto: the first ladder rung at or above `peak` plus 4% headroom, else 1.
    static func ceiling(peak: Double, full: Bool) -> Double {
        if full { return 1 }
        let needed = max(0, peak) * scaleHeadroom
        return scaleLadder.first { $0 >= needed } ?? 1
    }

    /// Ticks only at whole percents, so each label is exactly its value
    /// (`OddsChartView.axisLabel` prints whole percents): zero, the middle and the
    /// top when they are whole; otherwise every whole percent up to the top.
    static func tickValues(ceiling: Double) -> [Double] {
        let kept = [0, ceiling / 2, ceiling].filter(isWholePercent)
        if kept.count >= 2 { return kept }
        let top = Int((ceiling * 100 + 1e-9).rounded(.down))
        return (0...max(top, 0)).map { Double($0) / 100 }
    }

    static func isWholePercent(_ value: Double) -> Bool {
        abs(value * 100 - (value * 100).rounded()) < 1e-9
    }

    static func yTicks(ceiling: Double = 1) -> [FieldHistoryTick10868] {
        tickValues(ceiling: ceiling).map { FieldHistoryTick10868(value: $0, lines: [OddsChartView.axisLabel(for: $0)]) }
    }

    /// The axis top in words through the app's own printers: whole percents as the
    /// axis prints them, the 2.5% rung at the detail precision
    /// (`EventPropsMatrixLayout.exactPercent`) so it is never rounded to 3%.
    static func ceilingWords(_ ceiling: Double) -> String {
        isWholePercent(ceiling) ? OddsChartView.axisLabel(for: ceiling) : EventPropsMatrixLayout.exactPercent(ceiling)
    }

    /// "Auto scale · 0–10%" / "Full scale · 0–100%".
    static func scaleAction(ceiling: Double, full: Bool) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: scaleActionID,
                                label: "\(full ? Words.fullScale : Words.autoScale) · 0–\(ceilingWords(ceiling))",
                                spokenLabel: full ? Words.useAutoScale : Words.showFullScale,
                                isAvailable: true)
    }

    static func xTicks(_ domain: ClosedRange<Date>, host: Host) -> [FieldHistoryTick10868] {
        let plan = EvolutionChartView.axisPlan(for: [domain.lowerBound, domain.upperBound], calendar: host.calendar)
        return OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: host.calendar).map {
            FieldHistoryTick10868(value: $0.timeIntervalSince1970, lines: [tickWords($0, plan: plan, host: host)])
        }
    }

    /// The plan's own label format, said in the reader's calendar, zone and locale.
    static func tickWords(_ date: Date, plan: OddsChartView.XAxisPlan, host: Host) -> String {
        var style = plan.format
        style.locale = host.locale
        style.calendar = host.calendar
        style.timeZone = host.calendar.timeZone
        return date.formatted(style)
    }

    // MARK: - Identity and words

    static func seriesID(_ market: FuturesMarketDetail, outcomeID: Int) -> String {
        "\(GolfFieldPageAdapter10868.sourceKey(market)):\(market.id):\(outcomeID)"
    }

    /// The served timestamp is unique inside a line: drawn times strictly advance.
    static func pointID(_ seriesID: String, _ timestamp: String) -> String {
        "\(seriesID)#\(timestamp)"
    }

    /// The futures chart's palette slot for a chart position.
    static func tint(_ position: Int) -> Color {
        Color(hex: EvolutionOutcomeColour.markHex(nil, index: position))
    }

    /// Each golfer's name and whether any of their history is drawn.
    static func summary(_ golfers: [(String, Bool)]) -> String {
        let shown = golfers.filter { $0.1 }.map { $0.0 }
        let missing = golfers.filter { !$0.1 }.map { $0.0 }
        guard !shown.isEmpty else { return Words.noHistory }
        let lead = "\(shown.joined(separator: ", ")) chance to win, recorded observations only."
        return missing.isEmpty ? lead : "\(lead) No recorded history for \(missing.joined(separator: ", "))."
    }

    static func action(_ id: String, _ label: String, spoken: String? = nil,
                       available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: available)
    }

    static func chooserAction(available: Bool) -> FieldHistoryAction10868? {
        available ? action(chooserActionID, Words.chooseGolfers) : nil
    }

    // MARK: - Absence

    /// Nothing to draw, in the owner's words: no point, axis or guide is offered
    /// under it, and the domain is a placeholder the leaf never draws under an absence.
    static func absence(_ field: Field, golfers: [FuturesOutcome], selected: Int?, chooserAvailable: Bool,
                        plot: FieldHistoryPlotAbsence10868) -> FieldHistoryInput10868 {
        absentInput(field.market, golfers: golfers, phase: field.phase,
                    selection: selection(field, golfers: golfers, selected: selected),
                    notes: notes(field), words: Words.notRecorded, summary: Words.noHistory,
                    chooserAvailable: chooserAvailable, plot: plot)
    }

    /// No history response at all — not arrived yet, or failed; the host does not
    /// say which, so neither is claimed. The chart slot says "History unavailable"
    /// through the plot-absence channel, draws nothing and offers no working chart
    /// control. The rest of the page composes from its own inputs.
    static func unavailable(_ winner: FuturesMarketDetail, cohort: [Int], selected: Int?,
                            phase: GolfFinishPhase10868, chooserAvailable: Bool) -> FieldHistoryInput10868 {
        let field = Field(market: winner, history: nil, phase: phase,
                          listedStart: GolfFieldPageAdapter10868.listedStart(winner), now: Date.distantPast)
        let golfers = drawnGolfers(field, cohort: cohort)
        return absentInput(winner, golfers: golfers, phase: phase,
                           selection: selection(field, golfers: golfers, selected: selected),
                           notes: [], words: Words.historyUnavailable, summary: Words.historyUnavailable,
                           chooserAvailable: chooserAvailable,
                           plot: FieldHistoryPlotAbsence10868(title: Words.historyUnavailable, words: nil))
    }

    private static func absentInput(_ market: FuturesMarketDetail, golfers: [FuturesOutcome],
                                    phase: GolfFinishPhase10868, selection: FieldHistoryOriginalSelection10868,
                                    notes: [String], words: String, summary: String, chooserAvailable: Bool,
                                    plot: FieldHistoryPlotAbsence10868) -> FieldHistoryInput10868 {
        let series: [FieldHistorySeries10868] = golfers.enumerated().map { position, golfer in
            FieldHistorySeries10868(
                id: seriesID(market, outcomeID: golfer.id), name: golfer.name,
                shape: shapes[position % shapes.count], tint: tint(position),
                runs: [], links: [], labelPointID: nil,
                before: .absent(words: words), recorded: .absent(words: words),
                absentWords: words, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: caption(phase),
            series: series,
            selection: selection,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: Words.beforeLabel),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: notes,
            summary: summary,
            plotHeight: plotHeight,
            unboundReadingWords: words,
            plotUnavailableWords: nil,
            windows: nil, scale: nil,
            moreOriginals: chooserAction(available: chooserAvailable),
            details: action(detailsActionID, Words.details, available: false),
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: plot)
    }
}
