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
        /// The away side as the served row supplied it, never `1 − home`. Nil
        /// when the row carries none; the card's own complement prints then.
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
        /// The series' own observations, oldest first: no live-edge re-serve and
        /// no settled 0/1 end on a finished match (that end is the result, which
        /// the chart's card prints as Final, not a recorded chance).
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
    static func series(eventId: Int, points: [ChartDataPoint], source: String?,
                       scheduledStart: Date?, gameStart: Date?, finished: Bool,
                       history: EventHistoryResponse?) -> Series? {
        guard let source else { return nil }
        var own = points.filter { $0.source == source && !$0.isLiveEdge }.sorted { $0.date < $1.date }
        if finished {
            while let end = own.last, end.probability == 0 || end.probability == 1 { own.removeLast() }
        }
        guard !own.isEmpty else { return nil }
        return Series(eventId: eventId, source: source, points: own,
                      segments: OddsChartView.observationSegments(own, gameStart: gameStart),
                      scheduledStart: scheduledStart, history: history)
    }

    /// The away probability the served row at exactly `date` carries: the blend's
    /// `aggregate_line` or the sportsbook `history`. Rows are oldest first; a
    /// miss (a pushed live frame, a venue series) is nil, never a neighbour.
    static func suppliedAway(at date: Date, source: String, in history: EventHistoryResponse?) -> Double? {
        guard let history else { return nil }
        switch source {
        case "aggregate":
            guard let rows = history.aggregateLine else { return nil }
            return search(rows.count, date) { (timestamp: rows[$0].timestamp, away: rows[$0].awayProbability) }
        case "consensus":
            let rows = history.history
            return search(rows.count, date) { (timestamp: rows[$0].timestamp, away: rows[$0].awayProbability) }
        default:
            return nil
        }
    }

    private static func search(_ count: Int, _ date: Date,
                               _ row: (Int) -> (timestamp: String, away: Double?)) -> Double? {
        var low = 0, high = count - 1
        while low <= high {
            let mid = (low + high) / 2
            let candidate = row(mid)
            guard let stamp = candidate.timestamp.asDate else { return nil }
            if stamp == date { return candidate.away }
            if stamp < date { low = mid + 1 } else { high = mid - 1 }
        }
        return nil
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

    /// Both sides as the card prints a chart moment (`GamePlayCardView.printedLabels`):
    /// the supplied away side when the row has one, else the card's complement.
    static func labels(for reading: Reading) -> (home: String, away: String) {
        let printed = GamePlayCardView.printedLabels(home: reading.home, away: reading.away ?? (1.0 - reading.home))
        return (printed.home, printed.away ?? "")
    }
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
        VStack(alignment: .leading, spacing: expanded ? 8 : 6) {
            switch shown {
            case .reading(let reading, _):
                Text(TennisChartReading9483.heading(for: reading, scheduledStart: series.scheduledStart))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                chances(reading, prominent: expanded)
            case .gap(let date):
                Text("No recorded chance at \(TennisChartReading9483.time(date))")
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            case .unavailable:
                Text(TennisChartReading9483.unavailableText)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if scrubDate == nil, offersLatest(shown) {
                Button(TennisChartReading9483.showLatestText) { pin.holdLatest(in: series) }
                    .font(.caption)
                    .frame(minHeight: 44, alignment: .leading)
            }
            if let baseline = TennisChartReading9483.separateBaseline(series.baseline, shown: shown) {
                Divider()
                Text(TennisChartReading9483.baselineHeading(for: baseline))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                chances(baseline, prominent: false)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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

    private func chances(_ reading: TennisChartReading9483.Reading, prominent: Bool) -> some View {
        let printed = TennisChartReading9483.labels(for: reading)
        let layout = textSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        return layout {
            chance(homeName, printed.home, colors?.home ?? .blue, prominent)
            chance(awayName, printed.away, colors?.away ?? .red, prominent)
        }
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
/// reading then) and whenever the held reading is not exactly there.
struct TennisHeldReadingMarker9483: View {
    @ObservedObject var pin: TennisReadingPin9483
    @ObservedObject var selection: OddsChartSelection
    let series: TennisChartReading9483.Series
    let proxy: ChartProxy
    let plotFrame: CGRect
    let color: Color

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
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }
}
