import SwiftUI
import Charts

// MARK: - Score Differential Chart

/// Shows projected score differential (spread) and actual score difference over time.
/// Y-axis centered at 0. Positive = home team leading, negative = away team leading.
struct ScoreDifferentialChartView: View {
    let history: EventHistoryResponse
    let homeTeam: String
    let awayTeam: String
    var sportKey: String?
    var commenceTime: String?
    var eventStatus: String?
    var homeTeamColor: Color?
    var awayTeamColor: Color?
    var homeTeamAbbrev: String?
    var awayTeamAbbrev: String?
    /// #4117 — the served crest, the first rung of the avatar ladder. Optional
    /// with a nil default because the ladder derives one from the team name for
    /// most teams anyway; passing it is what lets a served crest outrank a
    /// derived one, exactly as it does in the gutter above this chart.
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    var forcedDomain: ClosedRange<Date>?

    /// The chart's height and its gutter's width, named because the gutter's
    /// label run is derived from the height (#2903) — two literals that have to
    /// agree cannot be two literals.
    static let chartHeight: CGFloat = 160
    static let gutterWidth: CGFloat = 22

    @State private var selectedDate: Date?
    /// #3269 — the plot area's width, needed for the same two reasons the MATCH
    /// chart above needs it: to size the time axis, and to place the period chips
    /// in chart space rather than plot space.
    @State private var plotWidth: CGFloat = 0

    /// #3430 — the two ends of one differential axis. If both read the same, a
    /// curve above the midline says nothing about who is ahead.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(
            away: awayTeam, home: homeTeam,
            awayServed: awayTeamAbbrev, homeServed: homeTeamAbbrev
        )
    }
    private var homeShort: String { sides.home }
    private var awayShort: String { sides.away }

    private var isGameStarted: Bool {
        eventStatus == "live" || isFinished
    }

    /// Read through `EventState` rather than open-coded, so this view cannot
    /// drift from the one place native decides what "over" means (#3465).
    private var isFinished: Bool { EventState.isFinished(eventStatus) }

    /// ux/1034 B5, ported from `ScoreDifferentialChart.tsx`: the actual line is
    /// only drawn where the scoreboard counts the unit the projection is in.
    ///
    /// On a tennis match `score_history` is SETS — `1-0`, `1-1` — while
    /// `projectedHomeScore`/`projectedAwayScore` are the books' GAME spread.
    /// The teal "Actual Score Diff" line was a three-step staircase under a ±6
    /// game axis: a category error drawn as a fact. The widget keeps its
    /// projection and stops drawing a line in the wrong unit; the note below it
    /// says which two units it is refusing to mix, because a widget that just
    /// goes quiet reads as broken.
    private var vocab: SportVocab { SportVocab.forSport(sportKey) }
    private var scoreboardCountsTheUnit: Bool { vocab.scoreboardCountsTheUnit }

    /// The sentence the chart owes a reader whose actual line is missing.
    ///
    /// #3465 — IT IS TENSED, AND IT USED TO BE WRITTEN ONLY FOR A MATCH STILL
    /// BEING PLAYED. Photographed on a settled US Open match (Tabilo 0-3
    /// Zverev, event 15304537), under a hero reading `FINAL · Zverev Win` and a
    /// win-probability chart that had correctly flipped to `● Final`, this
    /// section still read:
    ///
    ///     Played games are not captured YET — the scoreboard reports sets.
    ///     The line below IS the books' PROJECTED game margin.
    ///
    /// Two false tenses on a match that is over: "yet" promises a capture that
    /// will never come, and a finished match's projection is history, not a
    /// forecast. Alex's standing ruling — settled means settled — covers the
    /// prose under a chart as much as the chart itself.
    private var unitMismatchNote: String? {
        vocab.projectedMarginNote(settled: isFinished)
    }

    private var gameStartDate: Date? {
        commenceTime?.asDate
    }

    var body: some View {
        let dataPoints = buildDataPoints()
        let hasActual = dataPoints.contains { $0.actualDiff != nil }
        let hasProjected = dataPoints.contains { $0.projectedDiff != nil }
        if !hasActual && !hasProjected {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Score Differential")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)

                if let note = unitMismatchNote {
                    Text(note)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                HStack(spacing: 0) {
                    // Vertical team labels: home on top (positive), away on bottom
                    // (negative). #2903 — the run is stated so a long name truncates
                    // rather than clipping, and the gutter reserves the rotated
                    // footprint rather than overdrawing the heading beside it.
                    VStack {
                        let run = ChartGutter.run(chartHeight: Self.chartHeight, verticalPadding: 8)
                        // #4117 — the crest, from the same shared rung the Win
                        // Probability gutter above this one climbs. Without it this
                        // page drew crests in one gutter and bare abbreviations in
                        // its immediate neighbour, for the same two teams.
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            HStack(spacing: 3) {
                                if let url = ChartGutterCrest.resolvedURL(
                                    servedURL: homeTeamLogo, teamName: homeTeam, sportKey: sportKey) {
                                    ChartGutterCrest(url: url)
                                }
                                Text(homeShort.uppercased())
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(homeTeamColor ?? .blue)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            HStack(spacing: 3) {
                                if let url = ChartGutterCrest.resolvedURL(
                                    servedURL: awayTeamLogo, teamName: awayTeam, sportKey: sportKey) {
                                    ChartGutterCrest(url: url)
                                }
                                Text(awayShort.uppercased())
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(awayTeamColor ?? .red)
                                    .lineLimit(1)
                            }
                        }
                    }
                    .frame(width: Self.gutterWidth)
                    .padding(.vertical, 8)

                    chartView(dataPoints: dataPoints)
                }
                .frame(height: Self.chartHeight)

                // Legend
                HStack(spacing: 12) {
                    if hasProjected {
                        HStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(Color.orange)
                                .frame(width: 14, height: 3)
                            Text("Projected Spread")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if hasActual {
                        HStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(Color(hex: "#0d9488"))
                                .frame(width: 14, height: 3)
                            Text("Actual Score Diff")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Data

    private struct DiffPoint: Identifiable {
        let id = UUID()
        let date: Date
        let projectedDiff: Double?
        let actualDiff: Double?
    }

    private var gameEndDate: Date? {
        if let ca = history.completedAt, let d = ca.asDate {
            return d.addingTimeInterval(120)
        }
        guard isFinished else { return nil }
        // Fallback: last ESPN point
        if let espn = history.espnHistory, let last = espn.last, let d = last.timestamp.asDate {
            return d.addingTimeInterval(120)
        }
        return nil
    }

    /// The projected-margin series, bucketed to the minute.
    ///
    /// #4982 — extracted from ``buildDataPoints()`` rather than copied, because
    /// ``statesPlayedCountAbsence(history:sportKey:eventStatus:commenceTime:)``
    /// has to answer "will this chart draw?" and a second transcription of these
    /// two loops would be a rule with two spellings that drift. Both callers run
    /// THIS function, so the predicate cannot disagree with the view it predicts.
    ///
    /// `history.history` wins a minute outright; the bookmaker series only fills
    /// buckets it left empty. That precedence is the shipped behaviour and is
    /// preserved exactly.
    private static func projectedDiffPoints(
        history: EventHistoryResponse,
        since startDate: Date?
    ) -> [Int: DiffPoint] {
        // Projected spread from odds history (projected home score - projected away score)
        var projectedByMinute: [Int: DiffPoint] = [:]
        for h in history.history {
            guard let date = h.timestamp.asDate,
                  let projHome = h.projectedHomeScore,
                  let projAway = h.projectedAwayScore else { continue }
            if let start = startDate, date < start { continue }
            let bucket = Int(date.timeIntervalSince1970 / 60)
            projectedByMinute[bucket] = DiffPoint(date: date, projectedDiff: projHome - projAway, actualDiff: nil)
        }

        // Also check bookmaker history for projected scores
        for (_, bmPoints) in history.bookmakerHistory ?? [:] {
            for bm in bmPoints {
                guard let date = bm.timestamp.asDate,
                      let projHome = bm.projectedHomeScore,
                      let projAway = bm.projectedAwayScore else { continue }
                if let start = startDate, date < start { continue }
                let bucket = Int(date.timeIntervalSince1970 / 60)
                if projectedByMinute[bucket] == nil {
                    projectedByMinute[bucket] = DiffPoint(date: date, projectedDiff: projHome - projAway, actualDiff: nil)
                }
            }
        }
        return projectedByMinute
    }

    /// Does this chart put the played-count absence sentence on the screen?
    ///
    /// #4982 / #4969. Two adjacent cards told a live US Open reader the same
    /// thing twice — this chart's *"Played games are not captured yet — the
    /// scoreboard reports sets"* and, a card below, `MarketMapView`'s *"The
    /// scoreboard reports sets, this market quotes games — we do not hold the
    /// games played yet"*. Each already dedups WITHIN itself (#3503 is why the
    /// map prints one footnote under all its maps), and neither can see the
    /// other, so two correct single prints landed as one repeated admission.
    /// D102 / notice 34: the second copy adds nothing the first did not say.
    ///
    /// The page arbitrates by ORDER — this chart is rendered above the maps, and
    /// its sentence is the better one to keep because it also carries what only
    /// it knows (*"the line below is the sportsbooks' projected game margin"*).
    /// So the chart speaks and the map defers to it; where the chart is absent
    /// or silent, the map is the one that speaks and nothing is lost.
    ///
    /// THREE CONDITIONS, AND EVERY ONE IS NECESSARY. The sentence exists (the
    /// vocab guard: a sport whose scoreboard does not count the unit its markets
    /// quote), the page puts this chart on screen at all (`EventDetailView`
    /// draws it only once the match is live or over), AND this view actually
    /// draws rather than returning `EmptyView` — a chart with no series prints
    /// no note, and suppressing the map on a chart that never spoke would
    /// re-orphan the suppressed tile that #3503 exists to explain.
    ///
    /// The status gate lives HERE rather than beside the call, so that the page
    /// cannot drift from the chart it is predicting: the caller supplies the
    /// payload and this function answers for the whole rendering.
    ///
    /// `hasActual` is deliberately not consulted: whenever the note is owed,
    /// `scoreboardCountsTheUnit` is false and ``buildDataPoints()`` takes its
    /// early return with `actualByMinute` empty, so the projected series alone
    /// decides whether anything is drawn. `testTheAbsenceIsNotClaimedWithoutASeries`
    /// pins that, so the shortcut cannot quietly stop being true.
    static func statesPlayedCountAbsence(
        history: EventHistoryResponse,
        sportKey: String?,
        eventStatus: String?,
        commenceTime: String?
    ) -> Bool {
        let vocab = SportVocab.forSport(sportKey)
        // #3465 — tensed, so the tense has to be passed here too: a settled
        // match's sentence is a different string, but it is equally the one the
        // reader would otherwise meet twice.
        guard vocab.projectedMarginNote(settled: EventState.isFinished(eventStatus)) != nil else {
            return false
        }
        // The page's own render condition, restated once: a chart that is not in
        // the tree cannot have told the reader anything.
        let started = eventStatus == "live" || EventState.isFinished(eventStatus)
        guard started else { return false }
        // `isGameStarted` is true past that guard, so this is exactly the
        // `startDate` `buildDataPoints()` computes.
        return !projectedDiffPoints(history: history, since: commenceTime?.asDate).isEmpty
    }

    private func buildDataPoints() -> [DiffPoint] {
        let startDate = isGameStarted ? gameStartDate : nil
        let endDate = gameEndDate

        var projectedByMinute = Self.projectedDiffPoints(history: history, since: startDate)

        // Actual scores — only where the scoreboard counts the unit the
        // projection is quoted in. For tennis this stays empty on purpose: the
        // scoreboard's sets are not the rail's games (see `vocab`).
        var actualByMinute: [Int: (date: Date, diff: Double)] = [:]
        guard scoreboardCountsTheUnit else {
            return mergeDiffPoints(projectedByMinute: projectedByMinute,
                                   actualByMinute: actualByMinute,
                                   endDate: endDate)
        }
        for ep in history.espnHistory ?? [] {
            guard let date = ep.timestamp.asDate,
                  let hs = ep.homeScore, let as_ = ep.awayScore else { continue }
            if let start = startDate, date < start { continue }
            let bucket = Int(date.timeIntervalSince1970 / 60)
            actualByMinute[bucket] = (date, Double(hs - as_))
        }

        // Score history overrides ESPN
        for sp in history.scoreHistory ?? [] {
            guard let date = sp.timestamp.asDate else { continue }
            if let start = startDate, date < start { continue }
            let bucket = Int(date.timeIntervalSince1970 / 60)
            actualByMinute[bucket] = (date, Double(sp.homeScore - sp.awayScore))
        }

        // Fallback: win_prob_history game states (when ESPN scores are null)
        if actualByMinute.isEmpty {
            for (_, points) in history.winProbHistory ?? [:] {
                for pt in points {
                    guard let gs = pt.gameState,
                          let hs = gs.homeScore, let as_ = gs.awayScore,
                          let date = pt.timestamp.asDate else { continue }
                    if let start = startDate, date < start { continue }
                    let bucket = Int(date.timeIntervalSince1970 / 60)
                    if actualByMinute[bucket] == nil {
                        actualByMinute[bucket] = (date, Double(hs - as_))
                    }
                }
            }
        }

        return mergeDiffPoints(projectedByMinute: projectedByMinute,
                               actualByMinute: actualByMinute,
                               endDate: endDate)
    }

    /// Merge projected and actual into unified points. Extracted so the
    /// unit-gated early return above shares one exit with the normal path.
    private func mergeDiffPoints(
        projectedByMinute: [Int: DiffPoint],
        actualByMinute: [Int: (date: Date, diff: Double)],
        endDate: Date?
    ) -> [DiffPoint] {
        let allBuckets = Set(projectedByMinute.keys).union(actualByMinute.keys)
        var merged: [DiffPoint] = []
        for bucket in allBuckets {
            let proj = projectedByMinute[bucket]
            let actual = actualByMinute[bucket]
            let date = actual?.date ?? proj?.date ?? Date()
            merged.append(DiffPoint(
                date: date,
                projectedDiff: proj?.projectedDiff,
                actualDiff: actual?.diff
            ))
        }

        merged.sort { $0.date < $1.date }

        if let endDate {
            return merged.filter { $0.date <= endDate }
        }
        return merged
    }

    // MARK: - Chart

    private func chartView(dataPoints: [DiffPoint]) -> some View {
        let actualDiffs = dataPoints.compactMap(\.actualDiff)
        let projDiffs = dataPoints.compactMap(\.projectedDiff)
        let allDiffs = actualDiffs + projDiffs
        let absMax = max(allDiffs.map { abs($0) }.max() ?? 5, 5)
        let yRange = -(absMax + 2)...(absMax + 2)

        let periodMarkers = extractScoreDiffPeriodMarkers(dataPoints: dataPoints)

        return Chart {
            // Zero line
            RuleMark(y: .value("Even", 0.0))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

            // Selection indicator
            if let selectedDate {
                RuleMark(x: .value("Selected", selectedDate))
                    .lineStyle(StrokeStyle(lineWidth: 1.0))
                    .foregroundStyle(.primary.opacity(0.4))
            }

            // Period markers — light vertical gridlines at period boundaries
            ForEach(periodMarkers) { marker in
                RuleMark(x: .value("Period", marker.date))
                    .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
                    .foregroundStyle(.secondary.opacity(0.25))
            }

            // Projected spread (orange dashed — contrasts with teal actual)
            ForEach(dataPoints.filter { $0.projectedDiff != nil }) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Diff", point.projectedDiff!),
                    series: .value("Series", "projected")
                )
                .foregroundStyle(Color.orange)
                .lineStyle(StrokeStyle(lineWidth: 2.0, dash: [6, 3]))
                .interpolationMethod(.monotone)
            }

            // Actual score differential (teal — high contrast against orange)
            ForEach(dataPoints.filter { $0.actualDiff != nil }) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Diff", point.actualDiff!),
                    series: .value("Series", "actual")
                )
                .foregroundStyle(Color(hex: "#0d9488"))
                .lineStyle(StrokeStyle(lineWidth: 2.5))
                .interpolationMethod(.stepCenter)
            }
        }
        .chartYScale(domain: yRange)
        .chartXScale(domain: chartXDomain(dataPoints: dataPoints))
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 5)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        let intVal = Int(v)
                        Text(intVal > 0 ? "+\(intVal)" : "\(intVal)")
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .chartXAxis {
            // ONE axis, owned by the MATCH chart. This used to carry its own copy
            // of a 15/30/60-minute stride rule under a comment claiming it
            // matched `OddsChartView` — and it had not matched since the stride
            // ladder landed (#3238). On the same 47-minute domain the two stacked
            // charts, which are handed the SAME `forcedDomain` precisely so their
            // times line up, drew 12:30 · 12:40 · 12:50 · 1:00 · 1:10 above and
            // 12:30 · 12:45 · 1:00 below. Two clocks, one page. The font matches
            // for the same reason: the plan's fit is measured at 9pt (#3269).
            let plan = OddsChartView.xAxisPlan(
                for: chartXDomain(dataPoints: dataPoints), plotWidth: plotWidth)
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
        .chartXSelection(value: $selectedDate)
        // Period marker labels as small floating chips inside the chart.
        //
        // #3237's two corrections, which landed on the MATCH chart above and were
        // left here: `proxy.position(forX:)` is measured from the PLOT AREA's
        // origin while this GeometryReader spans the WHOLE chart, so every chip
        // was drawn a gutter's width LEFT of the period it marks, and the first
        // one sat on the y-axis label. `PeriodChipGeometry.place` also keeps a
        // chip's own width inside the plot at both ends.
        .chartOverlay { proxy in
            GeometryReader { geo in
                let plotFrame = geo[proxy.plotAreaFrame]
                let placements = PeriodChipGeometry.place(
                    periodMarkers.enumerated().compactMap { index, marker in
                        proxy.position(forX: marker.date).map {
                            PeriodChipGeometry.ChipRequest(
                                key: index, label: marker.label, rawX: Double($0))
                        }
                    },
                    plotWidth: plotFrame.width,
                    metrics: .score
                )
                Color.clear.preference(
                    key: PlotWidthPreferenceKey.self, value: plotFrame.width)
                ForEach(placements, id: \.key) { placement in
                    Text(periodMarkers[placement.key].label)
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(.secondary.opacity(0.7))
                        .padding(.horizontal, 3)
                        .padding(.vertical, 1)
                        .background(.ultraThinMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                        .position(x: plotFrame.minX + placement.centerX, y: 8)
                }
            }
        }
        .onPreferenceChange(PlotWidthPreferenceKey.self) { width in
            plotWidth = width
        }
    }

    private func chartXDomain(dataPoints: [DiffPoint]) -> ClosedRange<Date> {
        // Use the forced domain from EventDetailView (shared with OddsChart)
        if let forced = forcedDomain { return forced }
        let start = gameStartDate ?? dataPoints.first?.date ?? Date()
        let end = gameEndDate ?? dataPoints.last?.date ?? Date()
        guard start < end else { return start...start.addingTimeInterval(3600) }
        return start...end
    }

    // MARK: - Period Markers

    private struct ScoreDiffPeriodMarker: Identifiable {
        let id = UUID()
        let date: Date
        let label: String
    }

    private func extractScoreDiffPeriodMarkers(dataPoints: [DiffPoint]) -> [ScoreDiffPeriodMarker] {
        // Use game start as floor (period markers may precede first score data)
        let minDate = gameStartDate ?? dataPoints.first?.date ?? Date.distantPast
        let maxDate = gameEndDate ?? dataPoints.last?.date ?? Date.distantFuture

        var seenLabels: Set<String> = []
        var markers: [ScoreDiffPeriodMarker] = []

        // Extract from ESPN history
        for pt in (history.espnHistory ?? []) {
            guard let period = pt.period, !period.isEmpty,
                  let date = pt.timestamp.asDate,
                  date >= minDate, date <= maxDate else { continue }
            let label = normalizePeriodLabel(period)
            guard !label.isEmpty, !seenLabels.contains(label) else { continue }
            seenLabels.insert(label)
            markers.append(ScoreDiffPeriodMarker(date: date, label: label))
        }

        // Supplement from win_prob_history game_state
        for (_, points) in (history.winProbHistory ?? [:]) {
            for pt in points {
                guard let gs = pt.gameState, let date = pt.timestamp.asDate,
                      date >= minDate, date <= maxDate else { continue }
                let periodStr: String
                if let p = gs.period, !p.isEmpty { periodStr = p }
                else if let inning = gs.inning, inning > 0 { periodStr = "Top \(inning)" }
                else { continue }
                let label = normalizePeriodLabel(periodStr)
                guard !label.isEmpty, !seenLabels.contains(label) else { continue }
                seenLabels.insert(label)
                markers.append(ScoreDiffPeriodMarker(date: date, label: label))
            }
        }

        let sorted = markers.sorted { $0.date < $1.date }
        var filtered: [ScoreDiffPeriodMarker] = []
        for marker in sorted {
            if let last = filtered.last, marker.date.timeIntervalSince(last.date) < 120 {
                continue
            }
            filtered.append(marker)
        }
        return filtered
    }

    /// Delegates to `PeriodLabel.normalize` — the single implementation (#1831).
    /// This file used to carry its own copy; the two had drifted.
    ///
    /// `sportKey` is passed for #4888, for a BARE period number only — see the
    /// twin note in `OddsChartView`. Both charts stack on one event page, so a
    /// sport threaded into one and not the other is exactly the drift #1831
    /// deleted the copies to prevent.
    private func normalizePeriodLabel(_ raw: String) -> String {
        PeriodLabel.normalize(raw, sport: sportKey)
    }
}
