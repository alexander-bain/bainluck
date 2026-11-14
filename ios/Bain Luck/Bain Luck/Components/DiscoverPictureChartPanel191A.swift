import Charts
import Foundation
import SwiftUI

// MARK: - Pure Presentation & Trajectory Model (#12616, Ruling 191-A)

/// #12616 (Ruling 191-A, Decision 164, #5271/#5363, #11984) — Pure model and
/// presentation builder for the Discover single-game picture card's chart panel
/// under the competitor rows, shown for games in progress and finished games.
enum DiscoverPictureChart191A {

    nonisolated enum Perspective: String, Equatable, Sendable {
        case away
        case home
    }

    nonisolated struct Point: Identifiable, Equatable, Sendable {
        let id: Int
        let date: Date
        /// Win probability (`0.0 ... 1.0`) for `perspective`.
        let probability: Double
        let isOpening: Bool
        let isSolidMark: Bool
        let isEndpoint: Bool
    }

    nonisolated struct Model: Equatable, Sendable {
        let perspective: Perspective
        let plottedTeamShortName: String
        let plottedTeamCode: String
        let points: [Point]
        let leftEndLabel: String
        let rightEndLabel: String
        let isFinished: Bool
        let rightEndUsesTeamAccent: Bool
    }

    /// Resolves which side the single win-chance trajectory line represents:
    /// - Draw-priced sports (soccer, #5271/#5363): ALWAYS `.home`, because
    ///   `EventHistoryResponse` stores `home_probability` and `1 - home`
    ///   includes the draw outcome rather than away win alone.
    /// - Two-way finished games: the winning side (`.away` on road win, else `.home`).
    /// - Two-way live games: the currently leading win-chance side.
    nonisolated static func resolvePerspective(event: FeedEventData) -> Perspective {
        if DrawPricedWinner.sportPricesADraw(event.sport) {
            return .home
        }
        if EventState.isFinished(event.status) {
            let outcome = EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore
            )
            if outcome == .away {
                return .away
            }
            return .home
        }
        if let awayP = CompactGameCard12616.usableProbability(event.currentOdds?.awayProbability),
           let homeP = CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability),
           awayP > homeP {
            return .away
        }
        return .home
    }

    nonisolated static func build(
        event: FeedEventData,
        prematch: PrematchReading?,
        history: EventHistoryResponse?
    ) -> Model {
        let isFinished = EventState.isFinished(event.status)
        let isLive = event.status == "live"
        let pricesADraw = DrawPricedWinner.sportPricesADraw(event.sport)
        let perspective = resolvePerspective(event: event)
        let shortPair = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )
        let rawCodes = TeamShortName.abbreviationPair(
            away: event.awayTeam,
            home: event.homeTeam,
            awayServed: event.awayTeamData?.abbreviation,
            homeServed: event.homeTeamData?.abbreviation,
            sportKey: event.sport
        )
        let awayCode = TeamShortName.refusingResultWord(
            rawCodes.away, name: event.awayTeam, sportKey: event.sport
        )
        let homeCode = TeamShortName.refusingResultWord(
            rawCodes.home, name: event.homeTeam, sportKey: event.sport
        )
        let plottedShortName = perspective == .away ? shortPair.away : shortPair.home
        let plottedTeamCode = perspective == .away ? awayCode : homeCode

        let pregameSideProb: Double? = {
            guard let prematch else { return nil }
            if pricesADraw {
                return CompactGameCard12616.usableProbability(prematch.homeProbability)
            }
            let raw = perspective == .home ? prematch.homeProbability : prematch.awayProbability
            return CompactGameCard12616.usableProbability(raw)
        }()

        let currentSideProb: Double? = {
            guard isLive else { return nil }
            if pricesADraw {
                return CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability)
            }
            let raw = perspective == .home
                ? event.currentOdds?.homeProbability
                : event.currentOdds?.awayProbability
            return CompactGameCard12616.usableProbability(raw)
        }()

        let extractedPoints = extractPoints(
            event: event,
            prematch: prematch,
            history: history,
            perspective: perspective
        )

        let leftEndLabel: String = {
            if let preP = pregameSideProb {
                return "Pregame \(formatProbability(preP)) \(plottedTeamCode)"
            }
            if let first = extractedPoints.first {
                return "Start \(formatProbability(first.probability)) \(plottedTeamCode)"
            }
            return "Pregame \(absentProbabilityMarker)"
        }()

        let outcome = EventOutcome.resolve(
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore
        )

        let (rightEndLabel, rightEndUsesTeamAccent): (String, Bool) = {
            if isFinished {
                if outcome == .away {
                    let scorePart = scorePairText(winner: event.awayScore, loser: event.homeScore)
                    let label = scorePart.map { "Final \u{00B7} \(awayCode) won \($0)" }
                        ?? "Final \u{00B7} \(awayCode) won"
                    return (label, perspective == .away)
                }
                if outcome == .home {
                    let scorePart = scorePairText(winner: event.homeScore, loser: event.awayScore)
                    let label = scorePart.map { "Final \u{00B7} \(homeCode) won \($0)" }
                        ?? "Final \u{00B7} \(homeCode) won"
                    return (label, perspective == .home)
                }
                if outcome == .draw {
                    if let a = event.awayScore, let h = event.homeScore {
                        return ("Final \u{00B7} Draw \(a)\u{2013}\(h)", false)
                    }
                    return ("Final \u{00B7} Draw", false)
                }
                return ("Final", false)
            }

            let effectiveCurrent = currentSideProb ?? extractedPoints.last?.probability
            guard let curP = effectiveCurrent,
                  let tenthsText = CompactGameCard12616.formatSingleLiveTenths(curP) else {
                return ("Now \(plottedTeamCode)", true)
            }

            if let preP = pregameSideProb {
                let deltaPts = (curP - preP) * 100.0
                if abs(deltaPts) >= 0.05 {
                    let sign = deltaPts >= 0 ? "+" : "-"
                    let formattedDelta = String(format: "%@%.1f pts", sign, abs(deltaPts))
                    return ("Now \(tenthsText) \(plottedTeamCode) (\(formattedDelta))", true)
                }
            }
            return ("Now \(tenthsText) \(plottedTeamCode)", true)
        }()

        return Model(
            perspective: perspective,
            plottedTeamShortName: plottedShortName,
            plottedTeamCode: plottedTeamCode,
            points: extractedPoints,
            leftEndLabel: leftEndLabel,
            rightEndLabel: rightEndLabel,
            isFinished: isFinished,
            rightEndUsesTeamAccent: rightEndUsesTeamAccent
        )
    }

    private nonisolated static func scorePairText(winner: Int?, loser: Int?) -> String? {
        guard let winner, let loser else { return nil }
        return "\(winner)\u{2013}\(loser)"
    }

    /// Extracts canonical chronological points (`0...1` for `perspective`) from
    /// `EventHistoryResponse`, respecting C43 (canonical `aggregate_line` first,
    /// sportsbook `consensus` fallback, zero client-side source averaging) and
    /// `OddsChartView.drawnWindow` (post-game drift clip + `Since Start` window
    /// with true pregame anchor carried onto the kickoff edge).
    nonisolated static func extractPoints(
        event: FeedEventData,
        prematch: PrematchReading?,
        history: EventHistoryResponse?,
        perspective: Perspective
    ) -> [Point] {
        guard let history else { return [] }

        let blendPoints = OddsChartView.servedBlendPoints(from: history)
        let consensusPoints: [ChartDataPoint] = history.history.compactMap { row in
            guard let date = row.timestamp.asDate,
                  let homeP = row.homeProbability,
                  homeP.isFinite else {
                return nil
            }
            return ChartDataPoint(date: date, probability: min(max(homeP, 0), 1), source: "consensus")
        }

        let baseHomeSeries: [ChartDataPoint]
        if blendPoints.count >= 2 {
            baseHomeSeries = blendPoints
        } else if consensusPoints.count >= 2 {
            baseHomeSeries = consensusPoints
        } else if !blendPoints.isEmpty {
            baseHomeSeries = blendPoints
        } else {
            baseHomeSeries = consensusPoints
        }

        let sortedHome = baseHomeSeries.sorted { $0.date < $1.date }
        guard !sortedHome.isEmpty else { return [] }

        let window = OddsChartView.drawnWindow(
            status: event.status,
            commenceTime: event.commenceTime,
            history: history,
            forcedDomain: nil,
            legacyDataDomain: nil,
            selectedRange: .sinceStart,
            playStart: { scheduled in
                ObservedPlayStart.cut(scheduled: scheduled, history: history, sportKey: event.sport)
            }
        )

        let postGameClipped: [ChartDataPoint] = {
            if let endDate = window.finishedEnd {
                let withinEnd = sortedHome.filter { $0.date <= endDate }
                return withinEnd.isEmpty ? sortedHome : withinEnd
            }
            return sortedHome
        }()

        var gameSeries = OddsChartView.drawnPoints(postGameClipped, window: window)
        var hasPregameAnchor = false

        if let startCut = window.sinceStart {
            let pregameHomeProb: Double? = {
                if let pre = prematch,
                   let usable = CompactGameCard12616.usableProbability(pre.homeProbability) {
                    return usable
                }
                return postGameClipped.last(where: { $0.date <= startCut })?.probability
            }()

            if let firstInPlay = gameSeries.first {
                if firstInPlay.date > startCut, let preHome = pregameHomeProb {
                    let anchorDate = min(startCut, firstInPlay.date.addingTimeInterval(-1))
                    let anchor = ChartDataPoint(
                        date: anchorDate,
                        probability: preHome,
                        source: firstInPlay.source
                    )
                    gameSeries.insert(anchor, at: 0)
                    hasPregameAnchor = true
                } else if firstInPlay.date <= startCut {
                    hasPregameAnchor = true
                }
            }
        }

        // If the game just tipped off and `Since Start` has < 2 points while
        // recent pregame history exists within the 2-hour warm-up margin, retain
        // that recent run-up so the card already draws a connected trajectory.
        if gameSeries.count < 2, postGameClipped.count >= 2 {
            if let scheduled = event.commenceTime?.asDate {
                let floor = scheduled.addingTimeInterval(-SharedChartWindow.preStartMargin)
                let recent = postGameClipped.filter { $0.date >= floor }
                gameSeries = recent.count >= 2 ? recent : Array(postGameClipped.suffix(12))
            } else {
                gameSeries = postGameClipped
            }
            hasPregameAnchor = true
        }

        let count = gameSeries.count
        guard count > 0 else { return [] }
        let stride = max(1, EventAtlasChartMarks11666.solidMarkStride(pointCount: count))
        let drawsIntermediateMarks = count <= 28

        return gameSeries.enumerated().map { index, item in
            let sideP = perspective == .home ? item.probability : (1.0 - item.probability)
            let clamped = min(max(sideP, 0.0), 1.0)
            let isFirst = index == 0
            let isLast = index == count - 1
            let isOpening = isFirst && hasPregameAnchor && count >= 2
            let isSolid = !isOpening && (isLast || (drawsIntermediateMarks && index % stride == 0))
            return Point(
                id: index,
                date: item.date,
                probability: clamped,
                isOpening: isOpening,
                isSolidMark: isSolid,
                isEndpoint: isLast
            )
        }
    }
}

// MARK: - Bounded In-Memory History Cache (#11984 Zero-Flicker Discover Scrolling)

@MainActor
final class DiscoverEventChartHistoryCache191A {
    static let shared = DiscoverEventChartHistoryCache191A()

    private struct Entry {
        let response: EventHistoryResponse
        let fetchedAt: Date
    }

    private var entries: [Int: Entry] = [:]
    private var order: [Int] = []
    private var inflight: [Int: Task<EventHistoryResponse?, Never>] = [:]
    private let maxEntries = 64

    func cached(eventId: Int, isLive: Bool, now: Date = Date()) -> EventHistoryResponse? {
        guard let entry = entries[eventId] else { return nil }
        let ttl: TimeInterval = isLive ? 45 : 600
        guard now.timeIntervalSince(entry.fetchedAt) <= ttl else { return nil }
        return entry.response
    }

    func latestAnyAge(eventId: Int) -> EventHistoryResponse? {
        entries[eventId]?.response
    }

    func fetch(eventId: Int, isLive: Bool) async -> EventHistoryResponse? {
        if let hit = cached(eventId: eventId, isLive: isLive) {
            return hit
        }
        if let existing = inflight[eventId] {
            return await existing.value
        }
        let task = Task<EventHistoryResponse?, Never> {
            try? await APIClient.shared.fetchEventHistory(id: eventId, hours: 168)
        }
        inflight[eventId] = task
        let result = await task.value
        inflight[eventId] = nil
        if let result {
            store(result, for: eventId)
            return result
        }
        return entries[eventId]?.response
    }

    private func store(_ response: EventHistoryResponse, for eventId: Int) {
        entries[eventId] = Entry(response: response, fetchedAt: Date())
        order.removeAll { $0 == eventId }
        order.append(eventId)
        while order.count > maxEntries {
            let evicted = order.removeFirst()
            entries.removeValue(forKey: evicted)
        }
    }
}

// MARK: - 191-A Chart Panel View Under the Competitor Rows

/// #12616 (Ruling 191-A) — Tall, unsmoothed win-chance chart panel under the
/// competitor rows on Discover single-game cards during and after a game.
///
/// Draws:
/// 1. Full `0%–100%` y-axis with `100%`, `50%`, `0%` guides and real vertical
///    height (`104 pt` default plot canvas, never smushed).
/// 2. Dashed `50%` reference line across the plot.
/// 3. Connected linear win-chance line (`Decision 164`) with soft gradient fill,
///    pregame ring anchor, and endpoint dot.
/// 4. Labelled ends (`Pregame X%` · `50% even` · `<Team> Y% (+Z pts)` or `Final · <Winner> A–B`).
struct DiscoverPictureChartPanel191AView: View {
    let event: FeedEventData
    let prematch: PrematchReading?
    let awayColor: Color
    let homeColor: Color
    var preloadedHistory: EventHistoryResponse? = nil

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .body) private var rawPlotHeight: CGFloat = 126
    @ScaledMetric(relativeTo: .caption2) private var yAxisFontSize: CGFloat = 9.5
    @ScaledMetric(relativeTo: .caption) private var endLabelFontSize: CGFloat = 11.5

    @State private var loadedHistory: EventHistoryResponse?
    @State private var didFinishLoad = false

    private var effectiveHistory: EventHistoryResponse? {
        preloadedHistory
            ?? loadedHistory
            ?? DiscoverEventChartHistoryCache191A.shared.latestAnyAge(eventId: event.id)
    }

    private var model: DiscoverPictureChart191A.Model {
        DiscoverPictureChart191A.build(
            event: event,
            prematch: prematch,
            history: effectiveHistory
        )
    }

    private var lineColor: Color {
        model.perspective == .away ? awayColor : homeColor
    }

    private var plotHeight: CGFloat {
        min(max(rawPlotHeight, 122), 144)
    }

    var body: some View {
        Group {
            if !didFinishLoad || !model.points.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    plotCanvas
                        .frame(height: plotHeight)

                    labelledEndsRow
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 9)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Color.primary.opacity(0.032))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.primary.opacity(0.07), lineWidth: 0.5)
                )
                .accessibilityElement(children: .combine)
                .accessibilityLabel(
                    "Win chance chart for \(model.plottedTeamShortName): \(model.leftEndLabel), \(model.rightEndLabel)"
                )
                .accessibilityIdentifier("discover-card-191a-chart-panel")
            }
        }
        .task(id: "\(event.id)-\(event.status ?? "")-\(event.currentOdds?.homeProbability ?? -1)") {
            guard preloadedHistory == nil else {
                didFinishLoad = true
                return
            }
            let isLive = event.status == "live"
            if let hit = DiscoverEventChartHistoryCache191A.shared.cached(eventId: event.id, isLive: isLive) {
                loadedHistory = hit
                didFinishLoad = true
                return
            }
            let fetched = await DiscoverEventChartHistoryCache191A.shared.fetch(
                eventId: event.id,
                isLive: isLive
            )
            if let fetched {
                loadedHistory = fetched
            }
            didFinishLoad = true
        }
    }

    // MARK: - Plot Canvas (0%–25%–50%–75%–100% Scale + 50% Reference Line + Connected Line)

    private var plotCanvas: some View {
        HStack(spacing: 6) {
            if !dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .trailing, spacing: 0) {
                    yTickLabel("100%")
                    Spacer(minLength: 0)
                    yTickLabel("75%")
                    Spacer(minLength: 0)
                    yTickLabel("50%", emphasized: true)
                    Spacer(minLength: 0)
                    yTickLabel("25%")
                    Spacer(minLength: 0)
                    yTickLabel("0%")
                }
                .fixedSize(horizontal: true, vertical: false)
                .frame(minWidth: 32, maxHeight: plotHeight, alignment: .trailing)
                .accessibilityHidden(true)
            }

            ZStack {
                Chart {
                    // Subtle quarter & bound gridlines (100%, 75%, 25%, 0%)
                    ForEach([1.0, 0.75, 0.25, 0.0], id: \.self) { level in
                        RuleMark(y: .value("Grid", level))
                            .lineStyle(StrokeStyle(lineWidth: 0.5))
                            .foregroundStyle(Color.primary.opacity(0.055))
                    }

                    // 191-A 50% dashed reference line
                    RuleMark(y: .value("Even", 0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1.1, dash: [4, 4]))
                        .foregroundStyle(Color.secondary.opacity(0.50))

                    if model.points.count >= 2 {
                        ForEach(model.points) { point in
                            AreaMark(
                                x: .value("Time", point.date),
                                yStart: .value("Floor", 0.0),
                                yEnd: .value("Win chance", point.probability)
                            )
                            .interpolationMethod(.linear)
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [
                                        lineColor.opacity(0.16),
                                        lineColor.opacity(0.015)
                                    ],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )

                            LineMark(
                                x: .value("Time", point.date),
                                y: .value("Win chance", point.probability)
                            )
                            .interpolationMethod(.linear)
                            .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                            .foregroundStyle(lineColor)
                        }

                        ForEach(model.points.filter { $0.isOpening || $0.isSolidMark || $0.isEndpoint }) { point in
                            if point.isOpening {
                                PointMark(
                                    x: .value("Time", point.date),
                                    y: .value("Win chance", point.probability)
                                )
                                .symbol(.circle)
                                .symbolSize(28)
                                .foregroundStyle(Color.cardBackground)

                                PointMark(
                                    x: .value("Time", point.date),
                                    y: .value("Win chance", point.probability)
                                )
                                .symbol(.circle.strokeBorder(lineWidth: 1.6))
                                .symbolSize(28)
                                .foregroundStyle(lineColor)
                            } else if point.isEndpoint {
                                PointMark(
                                    x: .value("Time", point.date),
                                    y: .value("Win chance", point.probability)
                                )
                                .symbol(.circle)
                                .symbolSize(72)
                                .foregroundStyle(lineColor.opacity(0.20))

                                PointMark(
                                    x: .value("Time", point.date),
                                    y: .value("Win chance", point.probability)
                                )
                                .symbol(.circle)
                                .symbolSize(30)
                                .foregroundStyle(lineColor)
                            } else {
                                PointMark(
                                    x: .value("Time", point.date),
                                    y: .value("Win chance", point.probability)
                                )
                                .symbol(.circle)
                                .symbolSize(14)
                                .foregroundStyle(lineColor.opacity(0.85))
                            }
                        }
                    } else if let lone = model.points.first {
                        PointMark(
                            x: .value("Time", lone.date),
                            y: .value("Win chance", lone.probability)
                        )
                        .symbol(.circle)
                        .symbolSize(34)
                        .foregroundStyle(lineColor)
                    }
                }
                .chartYScale(domain: 0.0 ... 1.0)
                .chartXAxis(.hidden)
                .chartYAxis(.hidden)
                .chartLegend(.hidden)
                .allowsHitTesting(false)
            }
        }
    }

    private func yTickLabel(_ text: String, emphasized: Bool = false) -> some View {
        Text(text)
            .font(.system(size: min(yAxisFontSize, 10.5), weight: emphasized ? .bold : .medium).monospacedDigit())
            .foregroundStyle(emphasized ? Color.primary.opacity(0.68) : DS.textSecondaryReadable.opacity(0.75))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
    }

    // MARK: - Labelled Ends Row (Pregame X% TEAM · Now Y% TEAM (+Z pts) / Final · TEAM won A–B)

    @ViewBuilder
    private var labelledEndsRow: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 3) {
                leftEndText
                rightEndText(font: .footnote.weight(.bold).monospacedDigit())
                    .fixedSize(horizontal: false, vertical: true)
            }
        } else {
            let labelSize = min(endLabelFontSize, 13.0)
            let leftFont = Font.system(size: labelSize, weight: .medium).monospacedDigit()
            let rightFont = Font.system(size: labelSize, weight: .bold).monospacedDigit()

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(model.leftEndLabel)
                        .font(leftFont)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Spacer(minLength: 8)

                    rightEndText(font: rightFont)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }

                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(model.leftEndLabel)
                        .font(leftFont)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Spacer(minLength: 6)

                    rightEndText(font: rightFont)
                        .lineLimit(1)
                        .minimumScaleFactor(0.86)
                }
            }
        }
    }

    private var leftEndText: some View {
        Text(model.leftEndLabel)
            .font(.footnote.weight(.medium).monospacedDigit())
            .foregroundStyle(DS.textSecondaryReadable)
    }

    private func rightEndText(font: Font) -> some View {
        Text(model.rightEndLabel)
            .font(font)
            .foregroundStyle(model.rightEndUsesTeamAccent ? lineColor : DS.textSecondaryReadable)
    }
}
