import SwiftUI
import Charts

// MARK: - Score Differential Chart

/// Shows projected score differential (spread) and actual score difference over time.
/// Y-axis centered at 0. Positive = home team leading, negative = away team leading.
struct ScoreDifferentialChartView: View {
    let history: EventHistoryResponse
    let homeTeam: String
    let awayTeam: String
    var commenceTime: String?
    var eventStatus: String?
    var homeTeamColor: Color?
    var awayTeamColor: Color?
    var homeTeamAbbrev: String?
    var awayTeamAbbrev: String?

    private var homeShort: String {
        homeTeamAbbrev ?? homeTeam.split(separator: " ").last.map(String.init) ?? "Home"
    }
    private var awayShort: String {
        awayTeamAbbrev ?? awayTeam.split(separator: " ").last.map(String.init) ?? "Away"
    }

    private var isGameStarted: Bool {
        eventStatus == "live" || eventStatus == "completed" || eventStatus == "closed"
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

                HStack(spacing: 0) {
                    // Vertical team labels: home on top (positive), away on bottom (negative)
                    VStack {
                        Text(homeShort.uppercased())
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(homeTeamColor ?? .blue)
                            .lineLimit(1)
                            .fixedSize()
                            .rotationEffect(.degrees(-90))
                        Spacer()
                        Text(awayShort.uppercased())
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(awayTeamColor ?? .red)
                            .lineLimit(1)
                            .fixedSize()
                            .rotationEffect(.degrees(-90))
                    }
                    .frame(width: 22)
                    .padding(.vertical, 8)

                    chartView(dataPoints: dataPoints)
                }
                .frame(height: 160)

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
        guard eventStatus == "completed" || eventStatus == "closed" else { return nil }
        // Fallback: last ESPN point
        if let espn = history.espnHistory, let last = espn.last, let d = last.timestamp.asDate {
            return d.addingTimeInterval(120)
        }
        return nil
    }

    private func buildDataPoints() -> [DiffPoint] {
        let startDate = isGameStarted ? gameStartDate : nil
        let endDate = gameEndDate

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

        // Actual scores from ESPN history
        var actualByMinute: [Int: (date: Date, diff: Double)] = [:]
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

        // Merge projected and actual into unified points
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

        // Clip at game end
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

            // Period markers
            ForEach(periodMarkers) { marker in
                RuleMark(x: .value("Period", marker.date))
                    .lineStyle(StrokeStyle(lineWidth: 1.0, dash: [5, 5]))
                    .foregroundStyle(.secondary.opacity(0.4))
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
            AxisMarks { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(format: .dateTime.hour().minute(), anchor: .top)
                    .font(.caption2)
            }
        }
    }

    // MARK: - Period Markers

    private struct ScoreDiffPeriodMarker: Identifiable {
        let id = UUID()
        let date: Date
        let label: String
    }

    private func extractScoreDiffPeriodMarkers(dataPoints: [DiffPoint]) -> [ScoreDiffPeriodMarker] {
        guard let minDate = dataPoints.first?.date,
              let maxDate = dataPoints.last?.date else { return [] }

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

        return markers.sorted { $0.date < $1.date }
    }

    private func normalizePeriodLabel(_ raw: String) -> String {
        let s = raw.trimmingCharacters(in: .whitespaces)
        let lower = s.lowercased()
        // Baseball: "Top 3rd" / "Middle 1st" / "Bottom 5th" → "3" / "1" / "5"
        if lower.hasPrefix("top ") || lower.hasPrefix("middle ") || lower.hasPrefix("bottom ") || lower.hasPrefix("end ") || lower.hasPrefix("mid ") {
            let digits = s.filter(\.isNumber)
            if !digits.isEmpty { return digits }
        }
        // Quarters
        if s.hasPrefix("Q") || s.hasPrefix("P") || s.hasPrefix("OT") { return s }
        if lower == "1st" { return "Q1" }
        if lower == "2nd" { return "Q2" }
        if lower == "3rd" { return "Q3" }
        if lower == "4th" { return "Q4" }
        if s == "1st Half" || s == "1H" { return "1H" }
        if s == "2nd Half" || s == "2H" { return "2H" }
        if s == "Halftime" { return "HT" }
        return s
    }
}
