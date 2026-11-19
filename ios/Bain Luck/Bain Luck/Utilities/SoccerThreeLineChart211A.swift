import Charts
import Foundation
import SwiftUI

/// Ruling 211-A (Alex / Fable, 2026-11-16):
/// Soccer charts draw all three lines — Home, Draw, and Away — on `0%` to `100%`,
/// with `Draw` drawn as the lighter grey line (`HeadlineStyleTable199.drawInk`).
///
/// Safety & Truth Guarantees:
/// 1. Only activates on draw-priced sports (`DrawPricedWinner.sportPricesADraw(sportKey)`)
///    when the payload carries genuine 3-way probabilities (explicit `drawProbability`,
///    or a 3-way de-vigged `history` board from `h2h_pair_on_the_full_board` where
///    `home + away < 1.0`).
/// 2. Never invents `1 - home` or a synthetic `0%` draw on two-way / complement-only
///    rows (#5271 / #5363): if no genuine 3-way series exists, `build` returns `nil`
///    and the caller keeps its single-line home chart.
/// 3. Excludes synthetic terminal settlement rows (`drawProbability == nil` on an
///    explicit 3-way venue series, or `bookmakerCount == 0` on `history`) so a 1–1
///    level result never spikes to the legacy 2-way `50% / 50%` tie convention.
enum SoccerThreeLineChart211A {

    nonisolated enum OutcomeRole: String, CaseIterable, Identifiable, Sendable {
        case home
        case draw
        case away

        var id: String { rawValue }
    }

    nonisolated struct Point: Identifiable, Equatable, Sendable {
        let id: Int
        let date: Date
        let home: Double
        let draw: Double
        let away: Double
        let isLiveEdge: Bool
        let isOpening: Bool
        let isSolidMark: Bool
        let isEndpoint: Bool

        func probability(for role: OutcomeRole) -> Double {
            switch role {
            case .home: return home
            case .draw: return draw
            case .away: return away
            }
        }
    }

    nonisolated struct Series: Equatable, Sendable {
        let source: String
        let points: [Point]
        let segments: [[Point]]
        let homeLabel: String
        let awayLabel: String
        var homeCode: String = ""
        var awayCode: String = ""
        let isLive: Bool
        let isFinished: Bool

        static let drawLabel = "Draw"

        /// Resting reading (latest real observation, else last point) or scrubbed
        /// observation nearest `selectedDate` within the snap bound.
        func reading(at selectedDate: Date?) -> (point: Point, isScrubbed: Bool)? {
            let realPoints = points.filter { !$0.isLiveEdge }
            let candidates = realPoints.isEmpty ? points : realPoints
            guard let first = candidates.first, let last = candidates.last else {
                return nil
            }
            guard let selectedDate else {
                return (last, false)
            }
            guard let nearest = candidates.min(by: {
                abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate))
            }) else {
                return (last, false)
            }
            if candidates.count >= 2 {
                let snapBound = EventAtlasChartMarks11666.maxSelectionSnapSeconds(
                    first: first.date,
                    last: last.date
                )
                if abs(nearest.date.timeIntervalSince(selectedDate)) > snapBound {
                    return (last, false)
                }
            }
            return (nearest, true)
        }

        func formattedTriple(for point: Point) -> (home: String, draw: String, away: String) {
            EventSportHeadlines12472.soccerThreeWayChanceTexts(
                home: point.home,
                draw: point.draw,
                away: point.away,
                numberStreams: isLive && !isFinished
            )
        }
    }

    // MARK: - Raw Extraction

    private nonisolated struct RawTriple: Sendable {
        let date: Date
        let home: Double
        let draw: Double
        let away: Double
        let isLiveEdge: Bool
    }

    private nonisolated static let venuePriority: [String] = [
        "kalshi",
        "polymarket",
        "statpal",
        "bainluck_model",
        "espn",
    ]

    private nonisolated static func clampUnit(_ value: Double) -> Double {
        min(max(value, 0.0), 1.0)
    }

    private nonisolated static func isUsableUnit(_ value: Double?) -> Bool {
        guard let value, value.isFinite, value >= 0.0, value <= 1.0 else { return false }
        return true
    }

    /// Extracts canonical chronological 3-way triples from `EventHistoryResponse`
    /// without cross-source client-side averaging (C43).
    private nonisolated static func extractRawSeries(
        from history: EventHistoryResponse
    ) -> (source: String, rows: [RawTriple])? {
        // 1. Canonical backend `aggregate_line` when it carries all three outcomes.
        if let agg = history.aggregateLine {
            let aggTriples: [RawTriple] = agg.compactMap { row in
                guard let date = row.timestamp.asDate,
                      row.homeProbability.isFinite,
                      row.homeProbability >= 0, row.homeProbability <= 1,
                      isUsableUnit(row.awayProbability),
                      isUsableUnit(row.drawProbability),
                      let away = row.awayProbability,
                      let draw = row.drawProbability else {
                    return nil
                }
                return RawTriple(
                    date: date,
                    home: clampUnit(row.homeProbability),
                    draw: clampUnit(draw),
                    away: clampUnit(away),
                    isLiveEdge: false
                )
            }.sorted { $0.date < $1.date }
            if !aggTriples.isEmpty {
                return ("aggregate", aggTriples)
            }
        }

        // 2. Explicit 3-way `win_prob_history` source (`draw_probability` served on
        //    real snapshots; terminal `game_state.final` rows carry `draw_probability: null`
        //    and are excluded automatically).
        if let wpMap = history.winProbHistory, !wpMap.isEmpty {
            var candidates: [(source: String, realCount: Int, rows: [RawTriple])] = []
            for (sourceKey, wpRows) in wpMap {
                let triples: [RawTriple] = wpRows.compactMap { wp in
                    guard let date = wp.timestamp.asDate,
                          isUsableUnit(wp.homeProbability),
                          isUsableUnit(wp.awayProbability),
                          isUsableUnit(wp.drawProbability),
                          let home = wp.homeProbability,
                          let away = wp.awayProbability,
                          let draw = wp.drawProbability else {
                        return nil
                    }
                    let liveEdge = (wp.liveEdge == true) || (wp.evidence?.kind == "live_edge")
                    return RawTriple(
                        date: date,
                        home: clampUnit(home),
                        draw: clampUnit(draw),
                        away: clampUnit(away),
                        isLiveEdge: liveEdge
                    )
                }.sorted { $0.date < $1.date }

                let realCount = triples.filter { !$0.isLiveEdge }.count
                if realCount >= 1 {
                    candidates.append((sourceKey, realCount, triples))
                }
            }

            if let best = candidates.sorted(by: { lhs, rhs in
                if lhs.realCount != rhs.realCount {
                    return lhs.realCount > rhs.realCount
                }
                let lhsRank = venuePriority.firstIndex(of: lhs.source) ?? Int.max
                let rhsRank = venuePriority.firstIndex(of: rhs.source) ?? Int.max
                if lhsRank != rhsRank {
                    return lhsRank < rhsRank
                }
                return lhs.source < rhs.source
            }).first {
                return (best.source, best.rows)
            }
        }

        // 3. Sportsbook `history` consensus when de-vigged across all 3 outcomes
        //    (`h2h_pair_on_the_full_board`: `home + away < 1.0`, or explicit `drawProbability`).
        //    Pure 2-way complement rows (`home + away ≈ 1.0` everywhere with no explicit
        //    `drawProbability`) are refused (#5271 / #5363).
        let nonTerminalBooks = history.history.filter { ($0.bookmakerCount ?? 1) > 0 }
        let hasExplicitBookDraw = nonTerminalBooks.contains { isUsableUnit($0.drawProbability) }
        let hasFullBoardResidualMass = nonTerminalBooks.contains { row in
            guard let home = row.homeProbability, let away = row.awayProbability,
                  home.isFinite, away.isFinite, home >= 0, away >= 0 else {
                return false
            }
            let sum = home + away
            return sum > 0.01 && sum <= 0.98
        }

        if hasExplicitBookDraw || hasFullBoardResidualMass {
            let bookTriples: [RawTriple] = nonTerminalBooks.compactMap { row in
                guard let date = row.timestamp.asDate,
                      isUsableUnit(row.homeProbability),
                      isUsableUnit(row.awayProbability),
                      let home = row.homeProbability,
                      let away = row.awayProbability else {
                    return nil
                }
                let draw: Double
                if let explicit = row.drawProbability, explicit.isFinite {
                    draw = clampUnit(explicit)
                } else {
                    let sum = home + away
                    guard sum <= 1.005 else { return nil }
                    draw = clampUnit(1.0 - sum)
                }
                return RawTriple(
                    date: date,
                    home: clampUnit(home),
                    draw: draw,
                    away: clampUnit(away),
                    isLiveEdge: false
                )
            }.sorted { $0.date < $1.date }

            if !bookTriples.isEmpty {
                return ("consensus", bookTriples)
            }
        }

        return nil
    }

    // MARK: - Game-Page Builder (`OddsChartView`)

    nonisolated static func build(
        history: EventHistoryResponse?,
        sportKey: String?,
        status: String?,
        commenceTime: String?,
        selectedRange: OddsTimeRange,
        homeLabel: String,
        awayLabel: String,
        homeCode: String = "",
        awayCode: String = ""
    ) -> Series? {
        guard DrawPricedWinner.sportPricesADraw(sportKey),
              let history,
              let raw = extractRawSeries(from: history) else {
            return nil
        }

        let window = OddsChartView.drawnWindow(
            status: status,
            commenceTime: commenceTime,
            history: history,
            forcedDomain: nil,
            legacyDataDomain: nil,
            selectedRange: selectedRange,
            playStart: { scheduled in
                ObservedPlayStart.cut(scheduled: scheduled, history: history, sportKey: sportKey)
            }
        )

        let postGameClipped: [RawTriple] = {
            if let endDate = window.finishedEnd {
                let within = raw.rows.filter { $0.date <= endDate }
                return within.isEmpty ? raw.rows : within
            }
            return raw.rows
        }()

        var windowed: [RawTriple] = {
            guard let startCut = window.sinceStart else { return postGameClipped }
            let since = postGameClipped.filter { $0.date >= startCut }
            return since.isEmpty ? postGameClipped : since
        }()

        var hasPregameAnchor = false
        if let startCut = window.sinceStart,
           let firstInPlay = windowed.first,
           firstInPlay.date > startCut,
           let preRow = postGameClipped.last(where: { $0.date <= startCut }) {
            let anchorDate = min(startCut, firstInPlay.date.addingTimeInterval(-1))
            windowed.insert(
                RawTriple(
                    date: anchorDate,
                    home: preRow.home,
                    draw: preRow.draw,
                    away: preRow.away,
                    isLiveEdge: false
                ),
                at: 0
            )
            hasPregameAnchor = true
        } else if let startCut = window.sinceStart,
                  let first = windowed.first,
                  first.date <= startCut {
            hasPregameAnchor = true
        }

        let count = windowed.count
        guard count >= 2 else { return nil }

        let stride = max(1, EventAtlasChartMarks11666.solidMarkStride(pointCount: count))
        let drawsIntermediate = count <= 28
        let includesOpening = selectedRange == .all || hasPregameAnchor
        let startDate = commenceTime?.asDate

        let points: [Point] = windowed.enumerated().map { idx, row in
            let isFirst = idx == 0
            let isLast = idx == count - 1
            let isOpening = isFirst && includesOpening && (startDate == nil || row.date <= startDate!)
            let isSolid = !row.isLiveEdge && !isOpening && (isLast || (drawsIntermediate && idx % stride == 0))
            return Point(
                id: idx,
                date: row.date,
                home: row.home,
                draw: row.draw,
                away: row.away,
                isLiveEdge: row.isLiveEdge,
                isOpening: isOpening,
                isSolidMark: isSolid,
                isEndpoint: isLast
            )
        }

        // Split across capture gaps using OddsChartView's canonical observationSegments
        // so long capture holes stay honest gaps on all three lines.
        let homeProxy = points.map {
            var dp = ChartDataPoint(date: $0.date, probability: $0.home, source: raw.source)
            dp.isLiveEdge = $0.isLiveEdge
            return dp
        }
        let proxySegments = OddsChartView.observationSegments(homeProxy, gameStart: startDate)
        var cursor = 0
        var segments: [[Point]] = []
        for seg in proxySegments {
            let segCount = seg.count
            if cursor + segCount <= points.count {
                segments.append(Array(points[cursor..<(cursor + segCount)]))
                cursor += segCount
            }
        }
        if segments.isEmpty {
            segments = [points]
        }

        let isFinished = EventState.isFinished(status)
        let isLive = status == "live" && !isFinished

        return Series(
            source: raw.source,
            points: points,
            segments: segments,
            homeLabel: homeLabel,
            awayLabel: awayLabel,
            homeCode: homeCode.isEmpty ? homeLabel : homeCode,
            awayCode: awayCode.isEmpty ? awayLabel : awayCode,
            isLive: isLive,
            isFinished: isFinished
        )
    }

    // MARK: - Discover Card Builder (`DiscoverPictureChartPanel191A`)

    nonisolated static func extractCardPoints(
        event: FeedEventData,
        prematch: PrematchReading?,
        history: EventHistoryResponse?
    ) -> [Point] {
        guard DrawPricedWinner.sportPricesADraw(event.sport),
              let history,
              let raw = extractRawSeries(from: history) else {
            return []
        }

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

        let postGameClipped: [RawTriple] = {
            if let endDate = window.finishedEnd {
                let within = raw.rows.filter { $0.date <= endDate }
                return within.isEmpty ? raw.rows : within
            }
            return raw.rows
        }()

        var gameSeries: [RawTriple] = {
            guard let startCut = window.sinceStart else { return postGameClipped }
            let since = postGameClipped.filter { $0.date >= startCut }
            return since.isEmpty ? postGameClipped : since
        }()

        var hasPregameAnchor = false
        if let startCut = window.sinceStart, let firstInPlay = gameSeries.first {
            if firstInPlay.date > startCut {
                let preAnchor: (home: Double, draw: Double, away: Double)? = {
                    if CompactGameCard12616.hasExplicitThreeWayPrematch(event),
                       let pre = event.prematchOdds,
                       let h = CompactGameCard12616.usableProbability(pre.homeProbability),
                       let d = CompactGameCard12616.usableProbability(pre.drawProbability),
                       let a = CompactGameCard12616.usableProbability(pre.awayProbability) {
                        return (h, d, a)
                    }
                    if let preRow = postGameClipped.last(where: { $0.date <= startCut }) {
                        return (preRow.home, preRow.draw, preRow.away)
                    }
                    return nil
                }()
                if let preAnchor {
                    let anchorDate = min(startCut, firstInPlay.date.addingTimeInterval(-1))
                    gameSeries.insert(
                        RawTriple(
                            date: anchorDate,
                            home: preAnchor.home,
                            draw: preAnchor.draw,
                            away: preAnchor.away,
                            isLiveEdge: false
                        ),
                        at: 0
                    )
                    hasPregameAnchor = true
                }
            } else {
                hasPregameAnchor = true
            }
        }

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
        guard count >= 2 else { return [] }
        let stride = max(1, EventAtlasChartMarks11666.solidMarkStride(pointCount: count))
        let drawsIntermediate = count <= 28

        return gameSeries.enumerated().map { idx, row in
            let isFirst = idx == 0
            let isLast = idx == count - 1
            let isOpening = isFirst && hasPregameAnchor
            let isSolid = !isOpening && !row.isLiveEdge && (isLast || (drawsIntermediate && idx % stride == 0))
            return Point(
                id: idx,
                date: row.date,
                home: row.home,
                draw: row.draw,
                away: row.away,
                isLiveEdge: row.isLiveEdge,
                isOpening: isOpening,
                isSolidMark: isSolid,
                isEndpoint: isLast
            )
        }
    }

    // MARK: - SwiftUI Chart Marks

    @ChartContentBuilder
    static func chartMarks(
        segments: [[Point]],
        homeColor: Color,
        drawColor: Color = HeadlineStyleTable199.drawInk,
        awayColor: Color,
        lineWidth: CGFloat = 2.4
    ) -> some ChartContent {
        // Draw in lighter grey first so both named club lines cross cleanly over it.
        roleLineMarks(role: .draw, segments: segments, color: drawColor, lineWidth: max(1.9, lineWidth - 0.35))
        roleLineMarks(role: .away, segments: segments, color: awayColor, lineWidth: lineWidth)
        roleLineMarks(role: .home, segments: segments, color: homeColor, lineWidth: lineWidth)
    }

    @ChartContentBuilder
    private static func roleLineMarks(
        role: OutcomeRole,
        segments: [[Point]],
        color: Color,
        lineWidth: CGFloat
    ) -> some ChartContent {
        let stroke = StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round)
        ForEach(Array(segments.enumerated()), id: \.offset) { segIdx, segment in
            ForEach(segment) { pt in
                LineMark(
                    x: .value("Time", pt.date),
                    y: .value("Win probability", pt.probability(for: role)),
                    series: .value("Outcome", "soccer211a-\(role.rawValue)-\(segIdx)")
                )
                .foregroundStyle(color)
                .lineStyle(stroke)
                .interpolationMethod(.linear)
            }

            ForEach(segment.filter { $0.isOpening || $0.isEndpoint }) { pt in
                if pt.isOpening {
                    PointMark(
                        x: .value("Time", pt.date),
                        y: .value("Win probability", pt.probability(for: role))
                    )
                    .symbol(.circle)
                    .symbolSize(24)
                    .foregroundStyle(Color.cardBackground)

                    PointMark(
                        x: .value("Time", pt.date),
                        y: .value("Win probability", pt.probability(for: role))
                    )
                    .symbol(.circle.strokeBorder(lineWidth: 1.6))
                    .symbolSize(24)
                    .foregroundStyle(color)
                } else if pt.isEndpoint {
                    PointMark(
                        x: .value("Time", pt.date),
                        y: .value("Win probability", pt.probability(for: role))
                    )
                    .symbol(.circle)
                    .symbolSize(58)
                    .foregroundStyle(color.opacity(0.18))

                    PointMark(
                        x: .value("Time", pt.date),
                        y: .value("Win probability", pt.probability(for: role))
                    )
                    .symbol(.circle)
                    .symbolSize(26)
                    .foregroundStyle(color)
                }
            }
        }
    }
}

// MARK: - Game-Page Header, Scrub Overlay & Legend (`OddsChartView`)

struct SoccerThreeLineHeaderView211A: View {
    @ObservedObject var selection: OddsChartSelection
    let series: SoccerThreeLineChart211A.Series
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        // #9517: quiet at rest (the headline above already prints current chances, and
        // the legend below names all three lines); appears on scrub with non-truncating
        // percentages and exact PT timestamp.
        if let active = series.reading(at: selection.date), active.isScrubbed {
            let formatted = series.formattedTriple(for: active.point)
            HStack(spacing: 8) {
                outcomePill(label: series.homeCode, pct: formatted.home, color: homeColor)
                outcomePill(label: SoccerThreeLineChart211A.Series.drawLabel, pct: formatted.draw, color: HeadlineStyleTable199.drawInk)
                outcomePill(label: series.awayCode, pct: formatted.away, color: awayColor)
                Spacer(minLength: 2)
                Text(EventAtlasChartMarks11666.formatMinuteTimestampPT(active.point.date))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(.leading, 36)
            .padding(.trailing, 4)
            .allowsHitTesting(false)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("soccer-211a-three-line-header")
        }
    }

    private func outcomePill(label: String, pct: String, color: Color) -> some View {
        HStack(spacing: 3) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
            Text(pct)
                .font(.caption2.weight(.bold).monospacedDigit())
                .foregroundStyle(color)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
    }
}

struct SoccerThreeLineScrubOverlay211A: View {
    @ObservedObject var selection: OddsChartSelection
    let series: SoccerThreeLineChart211A.Series
    let proxy: ChartProxy
    let plotFrame: CGRect
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        if selection.date != nil,
           let active = series.reading(at: selection.date),
           active.isScrubbed,
           let x = proxy.position(forX: active.point.date),
           x >= 0, x <= plotFrame.width {
            let chartX = plotFrame.minX + x
            ZStack {
                Path { path in
                    path.move(to: CGPoint(x: chartX, y: plotFrame.minY))
                    path.addLine(to: CGPoint(x: chartX, y: plotFrame.maxY))
                }
                .stroke(Color.primary.opacity(0.22), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))

                scrubDot(yProb: active.point.draw, x: chartX, color: HeadlineStyleTable199.drawInk)
                scrubDot(yProb: active.point.away, x: chartX, color: awayColor)
                scrubDot(yProb: active.point.home, x: chartX, color: homeColor)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private func scrubDot(yProb: Double, x: CGFloat, color: Color) -> some View {
        if let y = proxy.position(forY: yProb), y >= 0, y <= plotFrame.height {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
                .overlay(Circle().stroke(Color.cardBackground, lineWidth: 1.5))
                .position(x: x, y: plotFrame.minY + y)
        }
    }
}

struct SoccerThreeLineLegendView211A: View {
    let homeLabel: String
    let awayLabel: String
    let homeColor: Color
    let awayColor: Color
    let rail: Bool

    var body: some View {
        HStack(spacing: 14) {
            swatchItem(label: homeLabel, color: homeColor)
            swatchItem(label: SoccerThreeLineChart211A.Series.drawLabel, color: HeadlineStyleTable199.drawInk)
            swatchItem(label: awayLabel, color: awayColor)
            Spacer(minLength: 0)
        }
        .padding(.leading, rail ? 0 : chartTeamGutterWidth)
        .padding(.top, rail ? 0 : 2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("soccer-211a-three-line-legend")
    }

    private func swatchItem(label: String, color: Color) -> some View {
        HStack(spacing: 5) {
            Capsule()
                .fill(color)
                .frame(width: 14, height: 3)
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(1)
        }
    }
}
