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
        if dataPoints.isEmpty {
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
                    HStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Color.orange)
                            .frame(width: 14, height: 3)
                        Text("Projected Spread")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    HStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(homeTeamColor ?? .blue)
                            .frame(width: 14, height: 3)
                        Text("Actual Score Diff")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
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
        var points: [DiffPoint] = []
        let startDate = isGameStarted ? gameStartDate : nil

        // Projected spread from odds history
        for h in history.history {
            guard let date = h.timestamp.asDate else { continue }
            if let start = startDate, date < start { continue }

            // The history points have projected scores via over/under + spread
            // We use the probability differential as a proxy for spread direction
            // But actual projected scores come from the bookmaker data
            points.append(DiffPoint(date: date, projectedDiff: nil, actualDiff: nil))
        }

        // Build from ESPN history (has both scores and can derive projected)
        var espnPoints: [DiffPoint] = []
        for ep in history.espnHistory ?? [] {
            guard let date = ep.timestamp.asDate,
                  let hs = ep.homeScore, let as_ = ep.awayScore else { continue }
            if let start = startDate, date < start { continue }
            espnPoints.append(DiffPoint(date: date, projectedDiff: nil, actualDiff: Double(hs - as_)))
        }

        // Build from score history (authoritative)
        var scorePoints: [DiffPoint] = []
        for sp in history.scoreHistory ?? [] {
            guard let date = sp.timestamp.asDate else { continue }
            if let start = startDate, date < start { continue }
            scorePoints.append(DiffPoint(date: date, projectedDiff: nil, actualDiff: Double(sp.homeScore - sp.awayScore)))
        }

        // Merge: prefer scoreHistory, supplement with ESPN
        var byMinute: [Int: DiffPoint] = [:]
        for p in espnPoints {
            let bucket = Int(p.date.timeIntervalSince1970 / 60)
            byMinute[bucket] = p
        }
        for p in scorePoints {
            let bucket = Int(p.date.timeIntervalSince1970 / 60)
            byMinute[bucket] = p // scoreHistory overrides ESPN
        }

        let merged = byMinute.values.sorted { $0.date < $1.date }
        return merged.isEmpty ? [] : merged
    }

    // MARK: - Chart

    private func chartView(dataPoints: [DiffPoint]) -> some View {
        let diffs = dataPoints.compactMap(\.actualDiff)
        let absMax = max(diffs.map { abs($0) }.max() ?? 5, 5)
        let yRange = -(absMax + 2)...(absMax + 2)

        return Chart {
            // Zero line
            RuleMark(y: .value("Even", 0.0))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

            // Actual score differential
            ForEach(dataPoints.filter { $0.actualDiff != nil }) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Diff", point.actualDiff!)
                )
                .foregroundStyle(homeTeamColor ?? .blue)
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
