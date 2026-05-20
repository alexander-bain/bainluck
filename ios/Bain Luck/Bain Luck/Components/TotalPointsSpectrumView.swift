import SwiftUI

/// Projected scoring spectrum: O/U line, pace/actual bars, and threshold ladder.
/// Mirrors the web TotalPointsSpectrum component.
struct TotalPointsSpectrumView: View {
    let gameMarkets: GameMarketsResponse
    let eventStatus: String?
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    var overUnder: Double?
    var homeScore: Int?
    var awayScore: Int?

    private var isLive: Bool { eventStatus == "live" }
    private var isDone: Bool { eventStatus == "completed" || eventStatus == "closed" }
    private var isPre: Bool { !isLive && !isDone }

    /// Game-total thresholds sorted ascending with monotonicity enforced.
    private var thresholds: [GameMarketOutcome] {
        let sorted = (gameMarkets.totals ?? [])
            .filter { $0.marketType == "game_total" && ($0.overProbability ?? 0) > 0 }
            .sorted { ($0.threshold ?? 0) < ($1.threshold ?? 0) }

        var result: [GameMarketOutcome] = []
        for item in sorted {
            if let prev = result.last, let prevProb = prev.overProbability, let curProb = item.overProbability {
                if curProb > prevProb {
                    // Clamp to previous to enforce monotonicity
                    result.append(item)
                } else {
                    result.append(item)
                }
            } else {
                result.append(item)
            }
        }
        return result
    }

    /// Pick up to 5 representative thresholds for the ladder.
    private var ladderThresholds: [GameMarketOutcome] {
        if thresholds.count <= 5 { return thresholds }
        let step = max(1, thresholds.count / 5)
        var picks: [GameMarketOutcome] = []
        var i = 0
        while i < thresholds.count, picks.count < 5 {
            picks.append(thresholds[i])
            i += step
        }
        if picks.count < 5, let last = thresholds.last {
            picks.append(last)
        }
        return picks
    }

    /// The threshold closest to 50% over probability — the implied O/U line.
    private var centerLine: Double? {
        guard !thresholds.isEmpty else { return nil }
        let center = thresholds.min(by: {
            abs(($0.overProbability ?? 0) - 0.5) < abs(($1.overProbability ?? 0) - 0.5)
        })
        return center?.threshold ?? overUnder
    }

    private var sourceCount: Int {
        Set(thresholds.compactMap(\.source)).count
    }

    private var actualTotal: Int? {
        guard isDone, let h = homeScore, let a = awayScore else { return nil }
        return h + a
    }

    var body: some View {
        if thresholds.isEmpty { EmptyView() }
        else if thresholds.count < 5 && isPre {
            minimalView
        } else {
            fullView
        }
    }

    // MARK: - Minimal View (few thresholds, pre-game)

    private var minimalView: some View {
        let ouLine = centerLine ?? 0
        let centerProb = thresholds.min(by: {
            abs(($0.overProbability ?? 0) - 0.5) < abs(($1.overProbability ?? 0) - 0.5)
        })?.overProbability ?? 0.5

        return VStack(alignment: .leading, spacing: 12) {
            header
            HStack(alignment: .top, spacing: 20) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("PRE-GAME LINE")
                        .font(.system(size: 9, weight: .semibold))
                        .tracking(0.5)
                        .foregroundStyle(.secondary)
                    Text(formatThreshold(ouLine))
                        .font(.system(size: 28, weight: .bold, design: .monospaced))
                    Text("combined points")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Probability the total clears \(formatThreshold(ouLine))")
                        .font(.system(size: 9, weight: .semibold))
                        .tracking(0.5)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.secondary.opacity(0.15))
                                    .frame(height: 8)
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.blue)
                                    .frame(width: geo.size.width * min(1, centerProb), height: 8)
                            }
                        }
                        .frame(height: 8)
                        Text("\(Int((centerProb * 100).rounded()))%")
                            .font(.caption.monospacedDigit().weight(.bold))
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Full View

    private var fullView: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            projectionStrip
            ladderView
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text("Projected scoring")
                .font(.subheadline)
                .fontWeight(.semibold)
            Spacer()
            if sourceCount > 1 {
                Text("\(sourceCount) sources")
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(0.5)
                    .textCase(.uppercase)
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 4))
            }
        }
    }

    // MARK: - Projection Strip

    @ViewBuilder
    private var projectionStrip: some View {
        let ouLine = centerLine ?? 0

        if isPre {
            preGameStrip(ouLine: ouLine)
        } else if isLive, let pace = gameMarkets.pace,
                  let paceTotal = pace.projectedTotal,
                  let scored = pace.totalScored {
            liveStrip(ouLine: ouLine, paceTotal: paceTotal, scored: scored)
        } else if isDone, let actual = actualTotal {
            finalStrip(ouLine: ouLine, actual: actual)
        }
    }

    private func preGameStrip(ouLine: Double) -> some View {
        let expected = Int(ouLine.rounded())
        let scaleMax = Double(expected) * 1.12

        return VStack(alignment: .leading, spacing: 8) {
            Text("Expected total points")
                .font(.caption)
                .fontWeight(.semibold)
            projectionBar(label: "Pre-game", value: Double(expected), scaleMax: scaleMax,
                          barColor: Color.secondary.opacity(0.55), labelColor: .primary, bold: true)
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func liveStrip(ouLine: Double, paceTotal: Double, scored: Int) -> some View {
        let scaleMax = max(ouLine, paceTotal) * 1.12
        let projRemaining = paceTotal - Double(scored)
        let paceColor = Color(hex: "#8B5CF6")

        return VStack(alignment: .leading, spacing: 8) {
            Text("Projected total points")
                .font(.caption)
                .fontWeight(.semibold)
            projectionBar(label: "Pre-game", value: ouLine, scaleMax: scaleMax,
                          barColor: Color.secondary.opacity(0.55), labelColor: .secondary, bold: false)
            // Pace bar with scored portion solid
            paceBar(scored: scored, paceTotal: paceTotal, scaleMax: scaleMax, color: paceColor)
            HStack(spacing: 0) {
                Text("\(scored)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(paceColor)
                Text(" scored")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                if projRemaining > 0 {
                    Text(" · +\(Int(projRemaining.rounded())) projected")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.leading, 68)

            if abs(paceTotal - ouLine) > 0.5 {
                let diff = paceTotal - ouLine
                HStack(spacing: 4) {
                    Text("Pace projects")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("\(diff > 0 ? "+" : "")\(String(format: "%.1f", diff))")
                        .font(.caption2.monospacedDigit().weight(.semibold))
                        .foregroundStyle(paceColor)
                    Text("vs pre-game expectation.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func finalStrip(ouLine: Double, actual: Int) -> some View {
        let scaleMax = max(ouLine, Double(actual)) * 1.12
        let diff = Double(actual) - ouLine
        let covered = diff > 0
        let actualColor = Color(hex: "#8B5CF6")

        return VStack(alignment: .leading, spacing: 8) {
            Text("Final total points")
                .font(.caption)
                .fontWeight(.semibold)
            projectionBar(label: "Pre-game", value: ouLine, scaleMax: scaleMax,
                          barColor: Color.secondary.opacity(0.55), labelColor: .secondary, bold: false)
            projectionBar(label: "Actual", value: Double(actual), scaleMax: scaleMax,
                          barColor: actualColor, labelColor: actualColor, bold: true)
            HStack(spacing: 4) {
                Text("Actual came in")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("\(covered ? "+" : "")\(String(format: "%.1f", diff))")
                    .font(.caption2.monospacedDigit().weight(.semibold))
                    .foregroundStyle(covered ? Color(hex: "#10B981") : .red)
                Text("vs pre-game expectation.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Ladder

    private var ladderView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Projected combined scoring")
                .font(.caption)
                .fontWeight(.semibold)
                .padding(.bottom, 4)

            ForEach(Array(ladderThresholds.enumerated()), id: \.offset) { _, item in
                ladderRow(item)
            }
        }
    }

    private func ladderRow(_ item: GameMarketOutcome) -> some View {
        let prob = item.overProbability ?? 0
        let threshold = item.threshold ?? 0

        return VStack(spacing: 0) {
            Divider()
            HStack(spacing: 10) {
                Text("\(formatThreshold(threshold))+")
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .frame(width: 50, alignment: .leading)

                Text("PRE-GAME")
                    .font(.system(size: 8, weight: .semibold))
                    .tracking(0.5)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .leading)

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.secondary.opacity(0.12))
                            .frame(height: 5)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.secondary.opacity(0.5))
                            .frame(width: geo.size.width * min(1, prob), height: 5)
                    }
                }
                .frame(height: 5)

                Text("\(Int((prob * 100).rounded()))%")
                    .font(.system(size: 11).monospacedDigit().weight(.semibold))
                    .frame(width: 32, alignment: .trailing)

                if isDone, let actual = actualTotal {
                    let hit = Double(actual) >= threshold
                    Text(hit ? "HIT" : "MISS")
                        .font(.system(size: 9, weight: .bold))
                        .tracking(0.3)
                        .foregroundStyle(hit ? Color(hex: "#10B981") : .red)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background((hit ? Color(hex: "#10B981") : Color.red).opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .frame(width: 50)
                } else {
                    Spacer().frame(width: isDone ? 50 : 0)
                }
            }
            .padding(.vertical, 8)
        }
    }

    // MARK: - Reusable Bar Components

    private func projectionBar(label: String, value: Double, scaleMax: Double,
                               barColor: Color, labelColor: Color, bold: Bool) -> some View {
        HStack(spacing: 8) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(labelColor)
                .frame(width: 60, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.secondary.opacity(0.12))
                        .frame(height: 7)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(barColor)
                        .frame(width: geo.size.width * min(1, value / scaleMax), height: 7)
                }
            }
            .frame(height: 7)

            Text(formatValue(value))
                .font(.caption.monospacedDigit())
                .fontWeight(bold ? .semibold : .regular)
                .foregroundStyle(labelColor)
                .frame(width: 36, alignment: .trailing)
        }
    }

    private func paceBar(scored: Int, paceTotal: Double, scaleMax: Double, color: Color) -> some View {
        HStack(spacing: 8) {
            Text("PACE")
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(color)
                .frame(width: 60, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.secondary.opacity(0.12))
                        .frame(height: 7)
                    // Ghost bar for projected total
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color.opacity(0.25))
                        .frame(width: geo.size.width * min(1, paceTotal / scaleMax), height: 7)
                    // Solid bar for scored portion
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color)
                        .frame(width: geo.size.width * min(1, Double(scored) / scaleMax), height: 7)
                }
            }
            .frame(height: 7)

            Text(formatValue(paceTotal))
                .font(.caption.monospacedDigit().weight(.semibold))
                .foregroundStyle(color)
                .frame(width: 36, alignment: .trailing)
        }
    }

    // MARK: - Formatting Helpers

    private func formatThreshold(_ value: Double) -> String {
        value.truncatingRemainder(dividingBy: 1) == 0
            ? "\(Int(value))"
            : String(format: "%.1f", value)
    }

    private func formatValue(_ value: Double) -> String {
        value.truncatingRemainder(dividingBy: 1) == 0
            ? "\(Int(value))"
            : String(format: "%.1f", value)
    }
}
