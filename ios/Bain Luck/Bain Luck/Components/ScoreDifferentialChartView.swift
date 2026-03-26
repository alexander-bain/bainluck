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

                chartView(dataPoints: dataPoints)
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

    private func buildDataPoints() -> [DiffPoint] {
        let startDate = isGameStarted ? gameStartDate : nil

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
        return merged
    }

    // MARK: - Chart

    private func chartView(dataPoints: [DiffPoint]) -> some View {
        let actualDiffs = dataPoints.compactMap(\.actualDiff)
        let projDiffs = dataPoints.compactMap(\.projectedDiff)
        let allDiffs = actualDiffs + projDiffs
        let absMax = max(allDiffs.map { abs($0) }.max() ?? 5, 5)
        let yRange = -(absMax + 2)...(absMax + 2)

        return Chart {
            // Zero line
            RuleMark(y: .value("Even", 0.0))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

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
}
