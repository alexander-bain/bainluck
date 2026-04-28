import SwiftUI
import Charts

struct MarketMapView: View {
    let gameMarkets: GameMarketsResponse
    let eventStatus: String?
    let homeTeam: String
    let awayTeam: String
    let homeAbbr: String?
    let awayAbbr: String?
    let homeColor: Color
    let awayColor: Color
    let sportKey: String?

    private var vocab: (marginTitle: String, totalTitle: String, unit: String) {
        let key = (sportKey ?? "").lowercased()
        if key.contains("baseball") || key.contains("mlb") {
            return ("Run Margin Map", "Runs Map", "runs")
        }
        if key.contains("hockey") || key.contains("nhl") {
            return ("Goal Margin Map", "Goals Map", "goals")
        }
        if key.contains("soccer") || key.contains("mls") || key.contains("epl") {
            return ("Goal Margin Map", "Goals Map", "goals")
        }
        return ("Margin Map", "Total Map", "points")
    }

    private var hasSpreads: Bool { !(gameMarkets.spreads ?? []).isEmpty }
    private var hasTotals: Bool { !(gameMarkets.totals ?? []).isEmpty }

    var body: some View {
        if !hasSpreads && !hasTotals { EmptyView() }
        else {
            VStack(spacing: 12) {
                if hasSpreads {
                    marginMapCard
                }
                if hasTotals {
                    totalMapCard
                }
            }
        }
    }

    // MARK: - Margin Map

    private var marginMapCard: some View {
        let spreads = gameMarkets.spreads ?? []
        let fullGame = spreads.filter { isFullGameSpread($0.marketName) }
        let parsed = fullGame.compactMap { parseSprOutcome($0) }
        let homeMargins = parsed.filter(\.isHome).map(\.margin)
        let awayMargins = parsed.filter { !$0.isHome }.map(\.margin)
        let allMargins = homeMargins + awayMargins
        let rangeMin = (allMargins.min() ?? -15) - 3
        let rangeMax = (allMargins.max() ?? 15) + 3
        let density = buildDensityFromSpreads(parsed, rangeMin: rangeMin, rangeMax: rangeMax)
        let segments = 14
        let step = (rangeMax - rangeMin) / Double(segments)

        return VStack(alignment: .leading, spacing: 8) {
            Text(vocab.marginTitle)
                .font(.subheadline)
                .fontWeight(.semibold)

            Chart {
                ForEach(0..<segments, id: \.self) { i in
                    let x = rangeMin + (Double(i) + 0.5) * step
                    let h = density[i]
                    AreaMark(
                        x: .value("Margin", x),
                        y: .value("Density", h)
                    )
                    .foregroundStyle(
                        x < 0 ? awayColor.opacity(0.3) : homeColor.opacity(0.3)
                    )
                    .interpolationMethod(.catmullRom)
                    LineMark(
                        x: .value("Margin", x),
                        y: .value("Density", h)
                    )
                    .foregroundStyle(x < 0 ? awayColor : homeColor)
                    .interpolationMethod(.catmullRom)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
                }
                RuleMark(x: .value("Even", 0))
                    .foregroundStyle(.secondary.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 7)) { value in
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text(v > 0 ? "+\(Int(v))" : "\(Int(v))")
                                .font(.system(size: 9))
                        }
                    }
                    AxisGridLine()
                }
            }
            .chartYAxis(.hidden)
            .frame(height: 120)

            HStack(spacing: 16) {
                HStack(spacing: 4) {
                    Circle().fill(awayColor).frame(width: 6, height: 6)
                    Text(awayAbbr ?? String(awayTeam.split(separator: " ").last ?? ""))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 4) {
                    Circle().fill(homeColor).frame(width: 6, height: 6)
                    Text(homeAbbr ?? String(homeTeam.split(separator: " ").last ?? ""))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Total Map

    private var totalMapCard: some View {
        let totals = gameMarkets.totals ?? []
        let fullGame = totals.filter { !$0.outcomeName.contains(":") }
        let thresholds: [(threshold: Double, overProb: Double)] = fullGame.compactMap { t in
            let name = t.outcomeName.lowercased()
            guard name.contains("over") else { return nil }
            guard let threshold = Self.extractNumber(from: t.outcomeName) else { return nil }
            return (threshold, t.probability ?? 0.5)
        }
        .sorted(by: { $0.threshold < $1.threshold })

        let allThresh = thresholds.map(\.threshold)
        let rangeMin = (allThresh.min() ?? 180) - 10
        let rangeMax = (allThresh.max() ?? 230) + 10
        let segments = 12
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: segments)
        let step = (rangeMax - rangeMin) / Double(segments)

        return VStack(alignment: .leading, spacing: 8) {
            Text(vocab.totalTitle)
                .font(.subheadline)
                .fontWeight(.semibold)

            Chart {
                ForEach(0..<segments, id: \.self) { i in
                    let x = rangeMin + (Double(i) + 0.5) * step
                    let h = density[i]
                    AreaMark(
                        x: .value("Total", x),
                        y: .value("Density", h)
                    )
                    .foregroundStyle(Color.blue.opacity(0.2))
                    .interpolationMethod(.catmullRom)
                    LineMark(
                        x: .value("Total", x),
                        y: .value("Density", h)
                    )
                    .foregroundStyle(.blue)
                    .interpolationMethod(.catmullRom)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 6)) { value in
                    AxisValueLabel {
                        if let v = value.as(Double.self) {
                            Text("\(Int(v))")
                                .font(.system(size: 9))
                        }
                    }
                    AxisGridLine()
                }
            }
            .chartYAxis(.hidden)
            .frame(height: 120)

            Text("Distribution of projected total \(vocab.unit)")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Density Computation

    private struct ParsedSpread {
        let margin: Double
        let probability: Double
        let isHome: Bool
    }

    private func isFullGameSpread(_ name: String) -> Bool {
        let lower = name.lowercased()
        return !lower.contains("1h") && !lower.contains("1st half") && !lower.contains("first half") &&
               !lower.contains("2h") && !lower.contains("2nd half") && !lower.contains("second half") &&
               !lower.contains("first 5")
    }

    private func parseSprOutcome(_ o: GameMarketOutcome) -> ParsedSpread? {
        let lower = o.outcomeName.lowercased()
        let homeWords = homeTeam.lowercased().split(separator: " ")
        let awayWords = awayTeam.lowercased().split(separator: " ")
        let isHome = homeWords.contains(where: { $0.count >= 3 && lower.contains($0) })
        let isAway = awayWords.contains(where: { $0.count >= 3 && lower.contains($0) })
        guard isHome || isAway else { return nil }

        guard let threshold = Self.extractNumber(from: o.outcomeName) else { return nil }
        let margin = isHome ? threshold : -threshold
        return ParsedSpread(margin: margin, probability: o.probability ?? 0.5, isHome: isHome)
    }

    private static func extractNumber(from text: String) -> Double? {
        let pattern = try! NSRegularExpression(pattern: #"(\d+\.?\d*)"#)
        let range = NSRange(text.startIndex..., in: text)
        let matches = pattern.matches(in: text, range: range)
        guard let last = matches.last else { return nil }
        let matchRange = Range(last.range(at: 1), in: text)!
        return Double(text[matchRange])
    }

    private func buildDensityFromSpreads(_ spreads: [ParsedSpread], rangeMin: Double, rangeMax: Double, segments: Int = 14) -> [Double] {
        if spreads.isEmpty { return Array(repeating: 5, count: segments) }
        var density = Array(repeating: 0.0, count: segments)
        let step = (rangeMax - rangeMin) / Double(segments)
        for s in spreads {
            let idx = Int((s.margin - rangeMin) / step)
            let clamped = max(0, min(segments - 1, idx))
            density[clamped] += s.probability
        }
        let peak = max(density.max() ?? 0.01, 0.01)
        return density.map { ($0 / peak) * 96 }
    }

    private func buildDensityFromThresholds(
        _ thresholds: [(threshold: Double, overProb: Double)],
        rangeMin: Double, rangeMax: Double, segments: Int = 12
    ) -> [Double] {
        if thresholds.count < 2 { return Array(repeating: 8, count: segments) }
        let sorted = thresholds.sorted(by: { $0.threshold < $1.threshold })

        var rawPdf: [(mid: Double, density: Double)] = []
        for i in 0..<(sorted.count - 1) {
            let dt = sorted[i + 1].threshold - sorted[i].threshold
            guard dt > 0 else { continue }
            let dp = sorted[i].overProb - sorted[i + 1].overProb
            rawPdf.append((mid: (sorted[i].threshold + sorted[i + 1].threshold) / 2, density: max(0, dp / dt)))
        }
        if rawPdf.isEmpty { return Array(repeating: 8, count: segments) }

        let step = (rangeMax - rangeMin) / Double(segments)
        var density = Array(repeating: 0.0, count: segments)

        for i in 0..<segments {
            let x = rangeMin + (Double(i) + 0.5) * step
            if rawPdf.count == 1 {
                density[i] = rawPdf[0].density
            } else if x <= rawPdf[0].mid {
                density[i] = rawPdf[0].density * max(0, 1 - (rawPdf[0].mid - x) / (step * 3))
            } else if x >= rawPdf.last!.mid {
                density[i] = rawPdf.last!.density * max(0, 1 - (x - rawPdf.last!.mid) / (step * 3))
            } else {
                for j in 0..<(rawPdf.count - 1) {
                    if x >= rawPdf[j].mid && x <= rawPdf[j + 1].mid {
                        let t = (x - rawPdf[j].mid) / (rawPdf[j + 1].mid - rawPdf[j].mid)
                        density[i] = rawPdf[j].density * (1 - t) + rawPdf[j + 1].density * t
                        break
                    }
                }
            }
        }

        // Smooth
        let smoothed = density.enumerated().map { (i, _) in
            let prev = i > 0 ? density[i - 1] : density[i]
            let next = i < density.count - 1 ? density[i + 1] : density[i]
            return (prev + density[i] * 2 + next) / 4
        }
        let peak = max(smoothed.max() ?? 0.001, 0.001)
        return smoothed.map { ($0 / peak) * 96 }
    }
}
