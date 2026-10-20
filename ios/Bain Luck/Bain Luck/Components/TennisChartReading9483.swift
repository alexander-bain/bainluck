import SwiftUI
import Charts
import Combine

/// #9483 tennis — the recorded chance a reader inspects on a tennis chart, held
/// beside its separately dated earlier baseline, through the full-size chart and
/// back.
///
/// The selected design reference (`native-tennis-history-reader-v462`) called
/// every later point "Recorded in game" and its baseline "Last pre-match". The
/// app knows less than that, and the design finding of 2026-10-20 says so: a
/// stored start is at best a SCHEDULED one (`commence_time_is_kickoff` absent or
/// true), and an explicit `false` makes it Kalshi's expected resolution, which
/// for a tennis match is the far end of the contest
/// (`OddsChartView.sinceStartCut`). So the baseline exists only where that cut
/// does and reads "Before scheduled start"; every inspected point is a
/// "Recorded chance" at its own observation time; neither claims play began.
///
/// Reads the chart's own series (`OddsChartView.readoutSource`): the blend when
/// the payload carries one, never a fixture or a venue chosen here.
enum TennisChartReading9483 {
    static func applies(sportKey: String?) -> Bool {
        sportKey?.hasPrefix("tennis") == true
    }

    static let recordedLabel = "Recorded chance"
    static let baselineLabel = "Before scheduled start"
    static let unavailableText = "Selected recorded chance unavailable"
    static let showLatestText = "Show latest recorded chance"

    /// One recorded observation: what the panel prints AND the identity a held
    /// reading must find again, exactly, on every later payload.
    struct Reading: Equatable {
        let eventId: Int
        let source: String
        let date: Date
        let home: Double
        /// The away side the source supplies on its own — the sportsbook
        /// `consensus` row at exactly this time, aggregated apart from home —
        /// never `1 − home`. Nil everywhere else: the blend's away side is its
        /// exhaustive complement, printed and never looked up, and any other
        /// series supplies none.
        let away: Double?
    }

    /// What a lifted finger left held.
    enum Held: Equatable {
        case reading(Reading)
        /// Inside a break in the drawn line. Nothing was recorded there, and no
        /// neighbour across the break is borrowed.
        case gap(Date)
    }

    /// What the panel shows.
    enum Shown: Equatable {
        /// `held` is false only for the latest reading shown while nothing is held.
        case reading(Reading, held: Bool)
        case gap(Date)
        /// A held reading that is no longer exactly there — corrected, gone,
        /// duplicated or another event's. Never replaced by a neighbour.
        case unavailable
    }

    /// The chart's readout series, as the readings are taken from it.
    struct Series {
        let eventId: Int
        let source: String
        /// The series' own observations, oldest first (served order within one
        /// time): no live-edge re-serve and no result row on a finished match
        /// (`series(…)` says which row that is).
        let points: [ChartDataPoint]
        /// The chart's own breaks in that line (`OddsChartView.observationSegments`).
        let segments: [[ChartDataPoint]]
        /// The scheduled start the chart may cut at, or nil when the payload
        /// vetoes it or has none (`OddsChartView.sinceStartCut`).
        let scheduledStart: Date?
        /// Where a reading's supplied away side is looked up.
        let history: EventHistoryResponse?

        func reading(for point: ChartDataPoint) -> Reading {
            Reading(eventId: eventId, source: source, date: point.date, home: point.probability,
                    away: TennisChartReading9483.suppliedAway(at: point.date, source: source, in: history))
        }

        /// The last observation before the scheduled start, at its own time.
        var baseline: Reading? {
            guard let scheduledStart,
                  let point = points.last(where: { $0.date < scheduledStart }),
                  isUnique(point) else { return nil }
            return reading(for: point)
        }

        var latest: Reading? {
            guard let point = points.last, isUnique(point) else { return nil }
            return reading(for: point)
        }

        /// The observation a finger lifted at `date` holds: the nearest one in
        /// the drawn run under it. Past either end of the line it is that end,
        /// as the scrub reads it (`OddsChartView.scrubbedDate`); inside a
        /// break it is the break.
        func inspect(at date: Date) -> Held? {
            guard let first = points.first, let last = points.last else { return nil }
            if date <= first.date { return .reading(reading(for: first)) }
            if date >= last.date { return .reading(reading(for: last)) }
            for run in segments {
                guard let start = run.first?.date, let end = run.last?.date,
                      start <= date, date <= end,
                      let nearest = run.min(by: {
                          abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
                      }) else { continue }
                return .reading(reading(for: nearest))
            }
            return .gap(date)
        }

        func resolve(_ held: Held?) -> Shown {
            switch held {
            case nil:
                return latest.map { .reading($0, held: false) } ?? .unavailable
            case .gap(let date):
                return .gap(date)
            case .reading(let wanted):
                guard wanted.eventId == eventId, wanted.source == source else { return .unavailable }
                let matches = points.filter { $0.date == wanted.date }
                guard matches.count == 1, reading(for: matches[0]) == wanted else { return .unavailable }
                return .reading(wanted, held: true)
            }
        }

        private func isUnique(_ point: ChartDataPoint) -> Bool {
            points.lazy.filter { $0.date == point.date }.prefix(2).count == 1
        }
    }

    /// The tennis series for a chart, or nil when there is no readout line.
    ///
    /// A finished match's series loses ONE row: the last one SERVED, when it is
    /// exactly 0 or 1. The backend appends exactly one result row to each series
    /// of a finished event with a resolved winner, and the card names that same
    /// single reading Final (`ChartReadoutPhase9483`). Earlier certainty is a
    /// genuine recording and stays. The row is chosen in served order, before
    /// the sort, because the result row's minute can equal the last genuine
    /// row's (1% then 0% at one stamp), and ties then keep served order.
    ///
    /// Limitation, carried as it stands: the blend and sportsbook rows carry no
    /// per-row result tag on this device, so a genuine last reading at exactly
    /// 0 or 1 on a finished event whose winner the backend never resolved (no
    /// result row appended) is dropped as the result too — the card names it
    /// Final by the same rule, so the two agree. No threshold, clock or
    /// inferred finish is added to tell them apart.
    static func series(eventId: Int, points: [ChartDataPoint], source: String?,
                       scheduledStart: Date?, gameStart: Date?, finished: Bool,
                       history: EventHistoryResponse?) -> Series? {
        guard let source else { return nil }
        var served = Array(points.filter { $0.source == source && !$0.isLiveEdge }.enumerated())
        if finished, let end = served.last, end.element.probability == 0 || end.element.probability == 1 {
            served.removeLast()
        }
        let own = served
            .sorted { ($0.element.date, $0.offset) < ($1.element.date, $1.offset) }
            .map(\.element)
        guard !own.isEmpty else { return nil }
        return Series(eventId: eventId, source: source, points: own,
                      segments: OddsChartView.observationSegments(own, gameStart: gameStart),
                      scheduledStart: scheduledStart, history: history)
    }

    /// The away probability a source supplies on its own at exactly `date`.
    /// Only the sportsbook `consensus` does (`history`, away aggregated apart
    /// from home): exactly one served row at that time, in any order, else nil.
    /// A duplicate, a missing row or a row with no away side is nil, never a
    /// neighbour and never `1 − home`. The blend's `aggregate_line` serves no
    /// away side and is never looked up; a venue series decodes none.
    static func suppliedAway(at date: Date, source: String, in history: EventHistoryResponse?) -> Double? {
        guard source == "consensus", let history else { return nil }
        let rows = history.history.filter { $0.timestamp.asDate == date }
        guard rows.count == 1 else { return nil }
        return rows[0].awayProbability
    }

    // MARK: - Both competitors' lines (Design C1, 2026-10-20)

    /// Every time at which the consensus supplies its own away side, by the
    /// rule `suppliedAway(at:source:in:)` applies to one time — exactly one
    /// served row there, carrying an away side — read once for a whole line
    /// rather than once per vertex.
    static func suppliedAways(in history: EventHistoryResponse?) -> [Date: Double] {
        guard let history else { return [:] }
        var rows: [Date: Int] = [:]
        var aways: [Date: Double] = [:]
        for row in history.history {
            guard let date = row.timestamp.asDate else { continue }
            rows[date, default: 0] += 1
            if let away = row.awayProbability { aways[date] = away }
        }
        return aways.filter { rows[$0.key] == 1 }
    }

    /// Whether the chart draws the second competitor's line beside the first.
    /// Only over one drawn series whose away side has a contract: the blend
    /// (its exhaustive complement) or the consensus where it supplied at least
    /// one away side of its own. Several venue lines, or one venue line, keep
    /// today's single line: no opponent series is invented for them.
    static func drawsBothCompetitors(drawnSources: [String], points: [ChartDataPoint],
                                     supplied: [Date: Double]) -> Bool {
        if drawnSources == ["aggregate"] { return true }
        if drawnSources == ["consensus"] {
            return points.contains { $0.source == "consensus" && supplied[$0.date] != nil }
        }
        return false
    }

    /// The second competitor's line over one drawn run, by the same source
    /// contract the panel prints by (`labels(for:)`): the blend's complement
    /// vertex for vertex (tennis prices no draw); the consensus's own supplied
    /// side, broken wherever a vertex has none, so an unknown side is a gap and
    /// never a neighbour or `1 − home`; nothing for any other series.
    static func awayRuns(_ run: [ChartDataPoint], source: String,
                         supplied: [Date: Double]) -> [[PairedWinVertex9483]] {
        switch source {
        case "aggregate":
            return [PairedWinLines9483.awayRun(run)]
        case "consensus":
            var runs: [[PairedWinVertex9483]] = []
            var current: [PairedWinVertex9483] = []
            for point in run {
                if let away = supplied[point.date] {
                    current.append(PairedWinVertex9483(date: point.date, probability: away))
                } else if !current.isEmpty {
                    runs.append(current)
                    current = []
                }
            }
            if !current.isEmpty { runs.append(current) }
            return runs
        default:
            return []
        }
    }

    /// The live edge's away tail is the blend's alone: the hero's away number
    /// it ends on is the blend's complement, which no other series draws.
    static func drawsAwayTail(source: String) -> Bool {
        source == "aggregate"
    }

    /// Where a reading's second competitor sits on the plot: the value
    /// `labels(for:)` prints, unformatted. Nil where it prints nothing.
    static func awayValue(for reading: Reading) -> Double? {
        reading.source == "aggregate" ? 1.0 - reading.home : reading.away
    }

    /// "2:51 PM" today, "Sep 13, 2:51 PM" otherwise: a match's readings span
    /// days, and a weekday alone cannot date an archived one.
    static func time(_ date: Date, now: Date = Date(), timeZone: TimeZone = .autoupdatingCurrent,
                     locale: Locale = .autoupdatingCurrent) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let style = calendar.isDate(date, inSameDayAs: now)
            ? Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, timeZone: timeZone)
            : Date.FormatStyle(locale: locale, timeZone: timeZone).month(.abbreviated).day().hour().minute()
        return date.formatted(style)
    }

    /// The inspected reading's line. An observation before the scheduled start
    /// says so; nothing says "in game", because no actual first serve is known.
    static func heading(for reading: Reading, scheduledStart: Date?, now: Date = Date(),
                        timeZone: TimeZone = .autoupdatingCurrent,
                        locale: Locale = .autoupdatingCurrent) -> String {
        let before = scheduledStart.map { reading.date < $0 } ?? false
        let label = before ? "\(recordedLabel) \(baselineLabel.lowercased())" : recordedLabel
        return "\(label) · \(time(reading.date, now: now, timeZone: timeZone, locale: locale))"
    }

    static func baselineHeading(for reading: Reading, now: Date = Date(),
                                timeZone: TimeZone = .autoupdatingCurrent,
                                locale: Locale = .autoupdatingCurrent) -> String {
        "\(baselineLabel) · \(time(reading.date, now: now, timeZone: timeZone, locale: locale))"
    }

    /// The baseline prints as its own block only when it is not the reading
    /// already shown — the same pair never prints twice.
    static func separateBaseline(_ baseline: Reading?, shown: Shown) -> Reading? {
        guard let baseline else { return nil }
        if case .reading(let reading, _) = shown, reading == baseline { return nil }
        return baseline
    }

    /// One row of the panel, top to bottom.
    enum PanelPart: Equatable {
        /// The two competitors' names, once, heading the value columns.
        case names
        case shown(Shown)
        case baseline(Reading)
        case showLatest
    }

    /// The panel as one compact comparison (Design C2, 2026-10-20): the names
    /// once, the shown reading's row, its dated baseline's row directly under
    /// it, and "Show latest" after both, so the two pairs sit together and the
    /// 44pt utility never pushes the baseline down.
    static func panelParts(shown: Shown, baseline: Reading?, offersLatest: Bool) -> [PanelPart] {
        let separate = separateBaseline(baseline, shown: shown)
        var printsValues = separate != nil
        if case .reading = shown { printsValues = true }
        var parts: [PanelPart] = printsValues ? [.names] : []
        parts.append(.shown(shown))
        if let separate { parts.append(.baseline(separate)) }
        if offersLatest { parts.append(.showLatest) }
        return parts
    }

    /// Both sides as the card prints a chart moment (`GamePlayCardView.printedLabels`),
    /// chosen by the source's contract. The blend's away side is its exhaustive
    /// binary complement, as the chart's readout prints it
    /// (`OddsChartView.playPoint`; tennis prices no draw). Every other source
    /// prints the away side it supplied, or leaves the slot empty.
    static func labels(for reading: Reading) -> (home: String, away: String) {
        let away = reading.source == "aggregate"
            ? DrawPricedWinner.printablePair(away: 1.0 - reading.home, home: reading.home, sport: sportKey)?.away
            : reading.away
        let printed = GamePlayCardView.printedLabels(home: reading.home, away: away)
        return (printed.home, printed.away ?? "")
    }

    /// The sport this helper ever reads (`applies(sportKey:)`), as the draw rule
    /// looks it up.
    private static let sportKey = "tennis"
}

/// #9483 tennis — the held reading. Stored by `OddsChartView` the way it stores
/// `OddsChartSelection` (a reference in `@State`), so the inline chart and its
/// full-size cover share one, and only the panel and the marker observe it.
final class TennisReadingPin9483: ObservableObject {
    @Published private(set) var held: TennisChartReading9483.Held?

    func hold(_ held: TennisChartReading9483.Held?) {
        if self.held != held { self.held = held }
    }

    /// Opening the full-size chart holds what it shows, so neither a later
    /// arrival nor the return moves the reading the reader opened on.
    func holdShown(_ shown: TennisChartReading9483.Shown) {
        guard held == nil, case .reading(let reading, held: false) = shown else { return }
        held = .reading(reading)
    }

    /// The reader's explicit choice of the newest observation, held like any other.
    func holdLatest(in series: TennisChartReading9483.Series) {
        hold(series.latest.map { .reading($0) })
    }
}

/// #9483 tennis — the dated reading and its baseline. Full size it always shows
/// (the latest observation until one is held); on the page it appears only once
/// a reading is held, because the hero above already prints the current chance
/// (#9517).
struct TennisReadingPanel9483: View {
    @ObservedObject var pin: TennisReadingPin9483
    let series: TennisChartReading9483.Series
    let homeName: String
    let awayName: String
    let colors: (away: Color, home: Color)?
    let expanded: Bool
    /// A finger on the full-size chart: the panel previews what lifting holds.
    var scrubDate: Date? = nil

    @Environment(\.dynamicTypeSize) private var textSize
    /// The value columns, wide enough for "100%" at each row's type and
    /// scaled with it, so the dated caption beside them takes the rest.
    /// (Not private: a defaulted private `var` would make the memberwise
    /// init private, and `OddsChartView` builds this panel.)
    @ScaledMetric(relativeTo: .title3) var prominentColumn: CGFloat = 64
    @ScaledMetric(relativeTo: .subheadline) var column: CGFloat = 52

    private var shown: TennisChartReading9483.Shown {
        if let scrubDate { return series.resolve(series.inspect(at: scrubDate)) }
        return series.resolve(pin.held)
    }

    var body: some View {
        if expanded || pin.held != nil {
            content(shown)
                .onAppear { if expanded { pin.holdShown(series.resolve(pin.held)) } }
        }
    }

    private func content(_ shown: TennisChartReading9483.Shown) -> some View {
        let parts = TennisChartReading9483.panelParts(
            shown: shown, baseline: series.baseline, offersLatest: scrubDate == nil && offersLatest(shown))
        return VStack(alignment: .leading, spacing: expanded ? 8 : 6) {
            ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                switch part {
                case .names:
                    if !textSize.isAccessibilitySize { names }
                case .shown(.reading(let reading, _)):
                    row(TennisChartReading9483.heading(for: reading, scheduledStart: series.scheduledStart),
                        reading, prominent: expanded)
                case .shown(.gap(let date)):
                    Text("No recorded chance at \(TennisChartReading9483.time(date))")
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                case .shown(.unavailable):
                    Text(TennisChartReading9483.unavailableText)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                case .baseline(let baseline):
                    row(TennisChartReading9483.baselineHeading(for: baseline), baseline, prominent: false)
                case .showLatest:
                    Button(TennisChartReading9483.showLatestText) { pin.holdLatest(in: series) }
                        .font(.caption)
                        .frame(minHeight: 44, alignment: .leading)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var valueColumn: CGFloat { expanded ? prominentColumn : column }

    /// The two names once, over the value columns of every row below.
    private var names: some View {
        HStack(alignment: .lastTextBaseline, spacing: 8) {
            Spacer(minLength: 0)
            name(homeName)
            name(awayName)
        }
        .accessibilityHidden(true)
    }

    private func name(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.primary)
            .lineLimit(2)
            .frame(width: valueColumn, alignment: .leading)
    }

    /// One dated pair: its caption, then each competitor's value under that
    /// competitor's name. At accessibility sizes the caption takes its own
    /// line and each value carries its name, as the panel did before.
    @ViewBuilder
    private func row(_ heading: String, _ reading: TennisChartReading9483.Reading, prominent: Bool) -> some View {
        let printed = TennisChartReading9483.labels(for: reading)
        if textSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) {
                caption(heading)
                chance(homeName, printed.home, colors?.home ?? .blue, prominent)
                chance(awayName, printed.away, colors?.away ?? .red, prominent)
            }
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                caption(heading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                value(printed.home, colors?.home ?? .blue, prominent)
                value(printed.away, colors?.away ?? .red, prominent)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel([heading, "\(homeName) \(printed.home)", "\(awayName) \(printed.away)"]
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .joined(separator: ", "))
        }
    }

    private func caption(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func value(_ text: String, _ color: Color, _ prominent: Bool) -> some View {
        Text(text)
            .font(prominent ? .title3.bold() : .subheadline.bold())
            .monospacedDigit()
            .foregroundStyle(color)
            .frame(width: valueColumn, alignment: .leading)
    }

    /// This panel previewing the observation under a finger at `date`.
    func scrubbing(_ date: Date?) -> TennisReadingPanel9483 {
        var copy = self
        copy.scrubDate = date
        return copy
    }

    /// Held on anything but the newest observation, or on nothing at all.
    private func offersLatest(_ shown: TennisChartReading9483.Shown) -> Bool {
        guard pin.held != nil else { return false }
        if case .reading(let reading, _) = shown { return reading != series.latest }
        return series.latest != nil
    }

    private func chance(_ name: String, _ value: String, _ color: Color, _ prominent: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(name)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(1)
            Text(value)
                .font(prominent ? .title3.bold() : .subheadline.bold())
                .monospacedDigit()
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// #9483 tennis — `TennisReadingPanel9483` following the finger on the
/// full-size chart. Only this leaf observes the selection, as only the
/// crosshair and readout do (#8651).
struct TennisScrubbedReadingPanel9483: View {
    @ObservedObject var selection: OddsChartSelection
    let panel: TennisReadingPanel9483

    var body: some View {
        panel.scrubbing(selection.date)
    }
}

/// #9483 tennis — where the held reading sits on the plot: a dotted rule and a
/// dot at its own time and value. Hidden under a finger (the crosshair is the
/// reading then) and whenever the held reading is not exactly there. Where the
/// chart draws the second competitor's line (`awayColor`), a second dot sits
/// on it at the value the panel prints for that side, and only where it
/// prints one.
struct TennisHeldReadingMarker9483: View {
    @ObservedObject var pin: TennisReadingPin9483
    @ObservedObject var selection: OddsChartSelection
    let series: TennisChartReading9483.Series
    let proxy: ChartProxy
    let plotFrame: CGRect
    let color: Color
    var awayColor: Color? = nil

    var body: some View {
        if !selection.isScrubbing, case .reading(let reading, held: true) = series.resolve(pin.held),
           let x = proxy.position(forX: reading.date), let y = proxy.position(forY: reading.home),
           x >= 0, x <= plotFrame.width, y >= 0, y <= plotFrame.height {
            ZStack {
                Path { path in
                    path.move(to: CGPoint(x: plotFrame.minX + x, y: plotFrame.minY))
                    path.addLine(to: CGPoint(x: plotFrame.minX + x, y: plotFrame.maxY))
                }
                .stroke(.secondary, style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
                Circle()
                    .fill(color)
                    .frame(width: 8, height: 8)
                    .position(x: plotFrame.minX + x, y: plotFrame.minY + y)
                if let awayColor, let away = TennisChartReading9483.awayValue(for: reading),
                   let awayY = proxy.position(forY: away), awayY >= 0, awayY <= plotFrame.height {
                    Circle()
                        .fill(awayColor)
                        .frame(width: 8, height: 8)
                        .position(x: plotFrame.minX + x, y: plotFrame.minY + awayY)
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}
