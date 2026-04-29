import SwiftUI

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
            return ("Run margin map", "Runs map", "runs")
        }
        if key.contains("hockey") || key.contains("nhl") {
            return ("Goal margin map", "Goals map", "goals")
        }
        if key.contains("soccer") || key.contains("mls") || key.contains("epl") {
            return ("Goal margin map", "Goals map", "goals")
        }
        return ("Margin map", "Total map", "points")
    }

    private var hasSpreads: Bool { !(gameMarkets.spreads ?? []).isEmpty }
    private var hasTotals: Bool { !(gameMarkets.totals ?? []).isEmpty }

    var body: some View {
        if !hasSpreads && !hasTotals { EmptyView() }
        else {
            VStack(spacing: 12) {
                if hasSpreads { marginMapCard }
                if hasTotals { totalMapCard }
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

        let awayParsed = parsed.filter { !$0.isHome }.sorted { abs($0.margin) < abs($1.margin) }
        let homeParsed = parsed.filter(\.isHome).sorted { $0.margin < $1.margin }
        let ladder: [(label: String, prob: Double, color: Color)] =
            awayParsed.prefix(4).map { ("\(awayAbbr ?? "Away") +\(Int(abs($0.margin)))", $0.probability, awayColor) } +
            homeParsed.prefix(4).map { ("\(homeAbbr ?? "Home") +\(Int($0.margin))", $0.probability, homeColor) }

        let zeroPos = posOnRail(0, min: rangeMin, max: rangeMax)
        let homeRgb = resolveRGB(homeColor)
        let awayRgb = resolveRGB(awayColor)

        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(vocab.marginTitle)
                        .font(.system(size: 15, weight: .black))
                        .tracking(-0.5)
                    Text("full game")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            // Density rail
            densityRail(
                density: density,
                zeroPosition: zeroPos,
                leftRgb: awayRgb,
                rightRgb: homeRgb
            )

            // Axis labels
            HStack {
                Text("\(awayAbbr ?? "Away") wins")
                    .foregroundStyle(awayColor)
                Spacer()
                Text("Even")
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(homeAbbr ?? "Home") wins")
                    .foregroundStyle(homeColor)
            }
            .font(.system(size: 11, weight: .heavy))

            // Probability ladder
            if !ladder.isEmpty {
                ladderView(entries: ladder)
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.barTrack.opacity(0.5), lineWidth: 1))
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
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: 14)

        let ladder: [(label: String, prob: Double, color: Color)] = thresholds.prefix(6).map { t in
            let label = "Over \(t.threshold.truncatingRemainder(dividingBy: 1) == 0 ? String(Int(t.threshold)) : String(format: "%.1f", t.threshold))"
            return (label, t.overProb, Color.blue)
        }

        let blueRgb = (r: 37.0, g: 99.0, b: 235.0)

        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(vocab.totalTitle)
                        .font(.system(size: 15, weight: .black))
                        .tracking(-0.5)
                    Text("projected total \(vocab.unit)")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            densityRail(
                density: density,
                zeroPosition: nil,
                leftRgb: blueRgb,
                rightRgb: blueRgb
            )

            HStack {
                if let lo = allThresh.min() { Text("\(Int(lo))").foregroundStyle(.secondary) }
                Spacer()
                if let hi = allThresh.max() { Text("\(Int(hi))").foregroundStyle(.secondary) }
            }
            .font(.system(size: 11, weight: .heavy))

            if !ladder.isEmpty {
                ladderView(entries: ladder)
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.barTrack.opacity(0.5), lineWidth: 1))
    }

    // MARK: - Density Rail (heat-map bar, matching web)

    private func densityRail(
        density: [Double],
        zeroPosition: Double?,
        leftRgb: (r: Double, g: Double, b: Double),
        rightRgb: (r: Double, g: Double, b: Double)
    ) -> some View {
        let segmentCount = density.count
        let zeroFrac = zeroPosition.map { $0 / 100.0 }

        return ZStack(alignment: .leading) {
            // Background segments
            GeometryReader { geo in
                HStack(spacing: 0) {
                    ForEach(0..<segmentCount, id: \.self) { i in
                        let frac = Double(i) / Double(segmentCount)
                        let isLeft = zeroFrac.map { frac < $0 } ?? true
                        let rgb = isLeft ? leftRgb : rightRgb
                        let alpha = 0.10 + (density[i] / 100.0) * 0.78
                        Rectangle()
                            .fill(Color(red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255).opacity(alpha))
                    }
                }
                .clipShape(Capsule())
                .overlay(
                    Capsule().stroke(Color.barTrack, lineWidth: 1)
                )
                .overlay(
                    // Subtle glass gradient
                    LinearGradient(
                        colors: [.white.opacity(0.25), .clear, .black.opacity(0.04)],
                        startPoint: .top, endPoint: .bottom
                    )
                    .clipShape(Capsule())
                )

                // Zero line
                if let zeroPct = zeroPosition {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.3))
                        .frame(width: 2)
                        .offset(x: geo.size.width * zeroPct / 100.0)
                        .frame(height: geo.size.height + 10)
                        .offset(y: -5)
                }
            }
        }
        .frame(height: 30)
    }

    // MARK: - Probability Ladder

    private func ladderView(entries: [(label: String, prob: Double, color: Color)]) -> some View {
        VStack(spacing: 5) {
            ForEach(entries.indices, id: \.self) { i in
                let entry = entries[i]
                HStack(spacing: 8) {
                    Text(entry.label)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(.secondary)
                        .frame(width: 72, alignment: .leading)
                    GeometryReader { geo in
                        Capsule()
                            .fill(Color.secondary.opacity(0.08))
                            .overlay(alignment: .leading) {
                                Capsule()
                                    .fill(entry.color.opacity(0.55))
                                    .frame(width: max(2, geo.size.width * min(entry.prob, 1.0)))
                            }
                    }
                    .frame(height: 16)
                    Text("\(Int((entry.prob * 100).rounded()))%")
                        .font(.system(size: 10, weight: .black, design: .monospaced))
                        .frame(width: 32, alignment: .trailing)
                }
            }
        }
    }

    // MARK: - Helpers

    private func posOnRail(_ value: Double, min: Double, max: Double) -> Double {
        Swift.max(0, Swift.min(100, ((value - min) / (max - min)) * 100))
    }

    private func resolveRGB(_ color: Color) -> (r: Double, g: Double, b: Double) {
        let resolved = color.resolve(in: EnvironmentValues())
        return (r: Double(resolved.red) * 255, g: Double(resolved.green) * 255, b: Double(resolved.blue) * 255)
    }

    // MARK: - Data Parsing

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

    // MARK: - Density Computation

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
        rangeMin: Double, rangeMax: Double, segments: Int = 14
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

        let smoothed = density.enumerated().map { (i, _) in
            let prev = i > 0 ? density[i - 1] : density[i]
            let next = i < density.count - 1 ? density[i + 1] : density[i]
            return (prev + density[i] * 2 + next) / 4
        }
        let peak = max(smoothed.max() ?? 0.001, 0.001)
        return smoothed.map { ($0 / peak) * 96 }
    }
}
