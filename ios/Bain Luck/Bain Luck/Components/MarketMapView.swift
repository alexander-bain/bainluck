import SwiftUI

// MARK: - Marker Types

private enum MarkerType: String {
    case actual, pre, proj, final_

    var dotColor: Color {
        switch self {
        case .actual: return Color(hex: "#16a34a")
        case .final_: return Color(hex: "#0f172a")
        case .pre: return Color(hex: "#94a3b8")
        case .proj: return Color(hex: "#0f172a")
        }
    }
}

private struct MapMarker: Identifiable {
    let id: String
    let value: Double
    let type: MarkerType
    let label: String
    let displayValue: String
}

// MARK: - Main View

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
    var homeWinProb: Double?
    var awayWinProb: Double?
    var homeSpread: Double?
    var overUnder: Double?
    var homeScore: Int?
    var awayScore: Int?

    @Environment(\.horizontalSizeClass) private var sizeClass

    private var hAbbr: String { homeAbbr ?? String(homeTeam.split(separator: " ").last ?? "") }
    private var aAbbr: String { awayAbbr ?? String(awayTeam.split(separator: " ").last ?? "") }
    private var isDone: Bool { eventStatus == "completed" || eventStatus == "closed" }
    private var isLive: Bool { eventStatus == "live" }
    private var isPre: Bool { !isDone && !isLive }
    private var maxMargin: Int {
        let key = (sportKey ?? "").lowercased()
        if key.contains("baseball") || key.contains("mlb") { return 8 }
        if key.contains("hockey") || key.contains("nhl") { return 5 }
        if key.contains("soccer") || key.contains("mls") || key.contains("epl") { return 5 }
        return 18
    }

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
    private var useColumns: Bool {
        #if os(macOS)
        return true
        #else
        return sizeClass == .regular
        #endif
    }

    var body: some View {
        if !hasSpreads && !hasTotals { EmptyView() }
        else if useColumns {
            HStack(alignment: .top, spacing: 12) {
                if hasSpreads {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("MARGIN MAPS")
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .tracking(1)
                        fullMarginMap
                        halfMarginMaps
                    }
                    .frame(maxWidth: .infinity)
                }
                if hasTotals {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("TOTAL MAPS")
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .tracking(1)
                        fullTotalMap
                        halfTotalMaps
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        } else {
            VStack(spacing: 12) {
                if hasSpreads { fullMarginMap; halfMarginMaps }
                if hasTotals { fullTotalMap; halfTotalMaps }
            }
        }
    }

    // MARK: - Full Game Margin Map

    private var fullMarginMap: some View {
        let spreads = gameMarkets.spreads ?? []
        let fullGame = spreads.filter { isFullGameSpread($0.marketName) }
        let parsed = fullGame.compactMap { parseSprOutcome($0) }
        let allMargins = parsed.map(\.margin)
        let rangeMin = min((allMargins.min() ?? Double(-maxMargin)) - 3, Double(-maxMargin))
        let rangeMax = max((allMargins.max() ?? Double(maxMargin)) + 3, Double(maxMargin))
        let density = buildDensityFromSpreads(parsed, rangeMin: rangeMin, rangeMax: rangeMax)

        let ladder: [(label: String, prob: Double, color: Color)] =
            parsed.filter { !$0.isHome }.sorted { abs($0.margin) < abs($1.margin) }.prefix(3).map {
                ("\(aAbbr) +\(Int(abs($0.margin)))", $0.probability, awayColor)
            } +
            parsed.filter(\.isHome).sorted { $0.margin < $1.margin }.prefix(3).map {
                ("\(hAbbr) +\(Int($0.margin))", $0.probability, homeColor)
            }

        // Headline: favored team + win %
        let headline: String = {
            guard let homeProbability = homeWinProb, let awayProbability = awayWinProb else { return "" }
            let favored = homeProbability > 0.5
            return "\(favored ? hAbbr : aAbbr) \(Int(((favored ? homeProbability : awayProbability) * 100).rounded()))%"
        }()

        // Markers
        var markers: [MapMarker] = []
        let projValue = homeSpread != nil ? -(homeSpread!) : closestToEvenMargin(parsed)
        if isDone {
            if let homeScoreValue = gameMarkets.homeScore ?? homeScore,
               let awayScoreValue = gameMarkets.awayScore ?? awayScore {
                let margin = homeScoreValue - awayScoreValue
                markers.append(MapMarker(id: "final", value: Double(margin), type: .final_, label: "FINAL", displayValue: "\(margin > 0 ? hAbbr : aAbbr) +\(abs(margin))"))
            }
            if let pv = projValue {
                markers.append(MapMarker(id: "pre", value: pv, type: .pre, label: "PRE-GAME", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        } else if isLive {
            if let homeScoreValue = gameMarkets.homeScore ?? homeScore,
               let awayScoreValue = gameMarkets.awayScore ?? awayScore {
                let margin = homeScoreValue - awayScoreValue
                markers.append(MapMarker(id: "actual", value: Double(margin), type: .actual, label: "ACTUAL", displayValue: "\(margin > 0 ? hAbbr : aAbbr) +\(abs(margin))"))
            }
            if let pv = projValue {
                markers.append(MapMarker(id: "proj", value: pv, type: .proj, label: "PROJECTION", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        } else {
            if let pv = projValue {
                markers.append(MapMarker(id: "proj", value: pv, type: .proj, label: "PROJECTION", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
            }
        }

        let zeroPos = posOnRail(0, min: rangeMin, max: rangeMax)
        let homeRgb = resolveRGB(homeColor)
        let awayRgb = resolveRGB(awayColor)

        return mapCard(
            title: useColumns ? "Full game margin map" : vocab.marginTitle,
            subtitle: isDone ? "Final margin distribution" : "Projected margin distribution",
            headline: headline,
            density: density,
            rangeMin: rangeMin,
            rangeMax: rangeMax,
            zeroPosition: zeroPos,
            leftRgb: awayRgb,
            rightRgb: homeRgb,
            axisLeft: "\(aAbbr) by \(maxMargin)+",
            axisMid: "Tie",
            axisRight: "\(hAbbr) by \(maxMargin)+",
            markers: markers,
            ladder: ladder
        )
    }

    // MARK: - Full Game Total Map

    private var fullTotalMap: some View {
        let totals = gameMarkets.totals ?? []
        let fullGame = totals.filter { !$0.outcomeName.contains(":") }
        let thresholds = extractTotalThresholds(fullGame)
        let allThresh = thresholds.map(\.threshold)
        let rangeMin = (allThresh.min() ?? 180) - 10
        let rangeMax = (allThresh.max() ?? 230) + 10
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: 14)

        let ladder: [(label: String, prob: Double, color: Color)] = thresholds.prefix(6).map {
            ("Over \(formatThreshold($0.threshold))", $0.overProb, Color(hex: "#7c3aed"))
        }

        var markers: [MapMarker] = []
        let ouLine = overUnder ?? thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold
        if isDone {
            if let homeScoreValue = gameMarkets.homeScore ?? homeScore,
               let awayScoreValue = gameMarkets.awayScore ?? awayScore {
                let totalScore = homeScoreValue + awayScoreValue
                markers.append(MapMarker(id: "final", value: Double(totalScore), type: .final_, label: "FINAL", displayValue: "\(totalScore) \(vocab.unit)"))
            }
            if let ou = ouLine {
                markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
            }
        } else if isLive {
            if let homeScoreValue = gameMarkets.homeScore ?? homeScore,
               let awayScoreValue = gameMarkets.awayScore ?? awayScore,
               let pace = gameMarkets.pace, let proj = pace.projectedTotal {
                let totalScore = homeScoreValue + awayScoreValue
                markers.append(MapMarker(id: "actual", value: Double(totalScore), type: .actual, label: "ACTUAL", displayValue: "\(totalScore)"))
                markers.append(MapMarker(id: "proj", value: proj, type: .proj, label: "PROJECTED", displayValue: "\(Int(proj.rounded()))"))
            }
            if let ou = ouLine {
                markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
            }
        } else {
            if let ou = ouLine {
                markers.append(MapMarker(id: "proj", value: ou, type: .proj, label: "PROJECTION", displayValue: formatThreshold(ou)))
            }
        }

        let purpleRgb = (r: 124.0, g: 58.0, b: 237.0)

        return mapCard(
            title: useColumns ? "Full game total map" : vocab.totalTitle,
            subtitle: isDone ? "Final \(vocab.unit) distribution" : "Projected total \(vocab.unit)",
            headline: "",
            density: density,
            rangeMin: rangeMin,
            rangeMax: rangeMax,
            zeroPosition: nil,
            leftRgb: purpleRgb,
            rightRgb: purpleRgb,
            axisLeft: "\(Int(rangeMin))",
            axisMid: "\(Int((rangeMin + rangeMax) / 2))",
            axisRight: "\(Int(rangeMax))+",
            markers: markers,
            ladder: ladder
        )
    }

    // MARK: - Half Maps

    @ViewBuilder
    private var halfMarginMaps: some View {
        // Try period_markets first, fall back to filtering spreads by name
        let periodMarkets = gameMarkets.periodMarkets ?? []
        let spreads = gameMarkets.spreads ?? []
        let halfSpreads = periodMarkets.filter { isSpreadMarket($0) } +
            spreads.filter { !isFullGameSpread($0.marketName) }

        let h1 = halfSpreads.filter { derivePeriod($0) == "1H" }
        let h2 = halfSpreads.filter { derivePeriod($0) == "2H" }
        if !h1.isEmpty { halfMarginCard(outcomes: h1, label: "1st half margin") }
        if !h2.isEmpty { halfMarginCard(outcomes: h2, label: "2nd half margin") }
    }

    @ViewBuilder
    private var halfTotalMaps: some View {
        let periodMarkets = gameMarkets.periodMarkets ?? []
        let totals = gameMarkets.totals ?? []
        let halfTotals = periodMarkets.filter { isTotalMarket($0) } +
            totals.filter { $0.outcomeName.contains(":") }

        let h1 = halfTotals.filter { derivePeriod($0) == "1H" }
        let h2 = halfTotals.filter { derivePeriod($0) == "2H" }
        if !h1.isEmpty { halfTotalCard(outcomes: h1, label: "1st half total map") }
        if !h2.isEmpty { halfTotalCard(outcomes: h2, label: "2nd half total map") }
    }

    private func halfMarginCard(outcomes: [GameMarketOutcome], label: String) -> some View {
        let parsed = outcomes.compactMap { parseSprOutcome($0) }
        let allMargins = parsed.map(\.margin)
        let rangeMin = min((allMargins.min() ?? Double(-maxMargin)) - 3, Double(-maxMargin))
        let rangeMax = max((allMargins.max() ?? Double(maxMargin)) + 3, Double(maxMargin))
        let density = buildDensityFromSpreads(parsed, rangeMin: rangeMin, rangeMax: rangeMax)
        let zeroPos = posOnRail(0, min: rangeMin, max: rangeMax)
        let projValue = closestToEvenMargin(parsed)

        var markers: [MapMarker] = []
        if let pv = projValue {
            markers.append(MapMarker(id: "pre", value: pv, type: .pre, label: "PRE-GAME", displayValue: "\(pv > 0 ? hAbbr : aAbbr) +\(String(format: "%.1f", abs(pv)))"))
        }

        return mapCard(
            title: label, subtitle: "Half margin distribution", headline: "",
            density: density, rangeMin: rangeMin, rangeMax: rangeMax,
            zeroPosition: zeroPos,
            leftRgb: resolveRGB(awayColor), rightRgb: resolveRGB(homeColor),
            axisLeft: "\(aAbbr) by \(maxMargin)+", axisMid: "Tie", axisRight: "\(hAbbr) by \(maxMargin)+",
            markers: markers, ladder: []
        )
    }

    private func halfTotalCard(outcomes: [GameMarketOutcome], label: String) -> some View {
        let thresholds = extractTotalThresholds(outcomes)
        let allThresh = thresholds.map(\.threshold)
        let rangeMin = (allThresh.min() ?? 90) - 5
        let rangeMax = (allThresh.max() ?? 120) + 5
        let density = buildDensityFromThresholds(thresholds, rangeMin: rangeMin, rangeMax: rangeMax, segments: 14)
        let purpleRgb = (r: 124.0, g: 58.0, b: 237.0)

        var markers: [MapMarker] = []
        if let ou = thresholds.first(where: { abs($0.overProb - 0.5) < 0.1 })?.threshold {
            markers.append(MapMarker(id: "pre", value: ou, type: .pre, label: "PRE-GAME", displayValue: formatThreshold(ou)))
        }

        return mapCard(
            title: label, subtitle: "Half \(vocab.unit) distribution", headline: "",
            density: density, rangeMin: rangeMin, rangeMax: rangeMax,
            zeroPosition: nil,
            leftRgb: purpleRgb, rightRgb: purpleRgb,
            axisLeft: "\(Int(rangeMin))", axisMid: "\(Int((rangeMin + rangeMax) / 2))", axisRight: "\(Int(rangeMax))+",
            markers: markers, ladder: []
        )
    }

    // MARK: - Reusable Map Card

    private func mapCard(
        title: String, subtitle: String, headline: String,
        density: [Double], rangeMin: Double, rangeMax: Double,
        zeroPosition: Double?,
        leftRgb: (r: Double, g: Double, b: Double),
        rightRgb: (r: Double, g: Double, b: Double),
        axisLeft: String, axisMid: String, axisRight: String,
        markers: [MapMarker],
        ladder: [(label: String, prob: Double, color: Color)]
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(title)
                        .font(.system(size: 15, weight: .black))
                        .tracking(-0.5)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if !headline.isEmpty {
                    Text(headline)
                        .font(.system(size: 14, weight: .black))
                        .foregroundStyle(.primary)
                }
            }

            // Summary tiles
            if !markers.isEmpty {
                HStack(spacing: 8) {
                    ForEach(markers) { m in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(m.label)
                                .font(.system(size: 10, weight: .heavy))
                                .foregroundStyle(.secondary)
                                .tracking(0.5)
                            Text(m.displayValue)
                                .font(.system(size: 14, weight: .black))
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.04))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .overlay(alignment: .bottom) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(m.type.dotColor)
                                .frame(height: 3)
                                .padding(.horizontal, 4)
                        }
                    }
                }
            }

            // Density rail with marker dots
            densityRail(
                density: density, rangeMin: rangeMin, rangeMax: rangeMax,
                zeroPosition: zeroPosition,
                leftRgb: leftRgb, rightRgb: rightRgb,
                markers: markers
            )

            // Axis labels
            HStack {
                Text(axisLeft).foregroundStyle(.secondary)
                Spacer()
                Text(axisMid).foregroundStyle(.secondary)
                Spacer()
                Text(axisRight).foregroundStyle(.secondary)
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

    // MARK: - Density Rail with Marker Dots

    private func densityRail(
        density: [Double], rangeMin: Double, rangeMax: Double,
        zeroPosition: Double?,
        leftRgb: (r: Double, g: Double, b: Double),
        rightRgb: (r: Double, g: Double, b: Double),
        markers: [MapMarker]
    ) -> some View {
        let segmentCount = density.count
        let zeroFrac = zeroPosition.map { $0 / 100.0 }

        return ZStack(alignment: .leading) {
            GeometryReader { geo in
                // Background segments
                HStack(spacing: 0) {
                    ForEach(0..<segmentCount, id: \.self) { i in
                        let frac = Double(i) / Double(segmentCount)
                        let isLeft = zeroFrac.map { frac < $0 } ?? true
                        let rgb = isLeft ? leftRgb : rightRgb
                        let alpha = 0.15 + (density[i] / 100.0) * 0.75
                        Rectangle()
                            .fill(Color(red: rgb.r / 255, green: rgb.g / 255, blue: rgb.b / 255).opacity(alpha))
                    }
                }
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Color.barTrack, lineWidth: 1))
                .overlay(
                    LinearGradient(
                        colors: [.white.opacity(0.30), .clear, .black.opacity(0.08)],
                        startPoint: .top, endPoint: .bottom
                    )
                    .clipShape(Capsule())
                )
                .shadow(color: .black.opacity(0.06), radius: 2, y: 1)

                // Zero line + label
                if let zeroPct = zeroPosition {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.3))
                        .frame(width: 2)
                        .offset(x: geo.size.width * zeroPct / 100.0 - 1)
                        .frame(height: 40)
                        .offset(y: -5)

                    Text("0")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(.secondary)
                        .position(x: geo.size.width * zeroPct / 100.0, y: 48)
                }

                // Marker dots — scale radius relative to rail width
                ForEach(markers) { m in
                    let pct = posOnRail(m.value, min: rangeMin, max: rangeMax)
                    let xPos = geo.size.width * pct / 100.0
                    let isProj = m.type == .proj
                    let markerRadius: CGFloat = geo.size.width > 300 ? 13 : 11
                    let dotSize: CGFloat = isProj ? markerRadius * 2 : markerRadius * 2 - 4
                    Circle()
                        .fill(isProj ? Color.cardBackground : m.type.dotColor)
                        .frame(width: dotSize, height: dotSize)
                        .overlay(
                            Circle().stroke(isProj ? Color.primary : .white, lineWidth: 2)
                        )
                        .shadow(color: .black.opacity(0.2), radius: 3, y: 1)
                        .position(x: xPos, y: 15)
                }
            }
        }
        .frame(height: 36)
    }

    // MARK: - Probability Ladder

    private func ladderView(entries: [(label: String, prob: Double, color: Color)]) -> some View {
        VStack(spacing: 5) {
            ForEach(entries.indices, id: \.self) { i in
                let entry = entries[i]
                HStack(spacing: 8) {
                    // Label with team color dot for visual association
                    HStack(spacing: 4) {
                        Circle()
                            .fill(entry.color)
                            .frame(width: 5, height: 5)
                        Text(entry.label)
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .frame(width: 82, alignment: .leading)
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

    private func formatThreshold(_ t: Double) -> String {
        t.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(t))" : String(format: "%.1f", t)
    }

    private func closestToEvenMargin(_ parsed: [ParsedSpread]) -> Double? {
        guard !parsed.isEmpty else { return nil }
        let closest = parsed.min(by: { abs($0.probability - 0.5) < abs($1.probability - 0.5) })!
        return closest.isHome ? closest.margin : closest.margin
    }

    /// Derive the period label for a market outcome.
    /// Uses backend-supplied ``period`` field (derived from ticker prefix);
    /// falls back to text-based detection in outcome/market names.
    private func derivePeriod(_ o: GameMarketOutcome) -> String? {
        if let p = o.period, !p.isEmpty { return p }
        if isFirstHalf(o.outcomeName) || isFirstHalf(o.marketName) { return "1H" }
        if isSecondHalf(o.outcomeName) || isSecondHalf(o.marketName) { return "2H" }
        return nil
    }

    private func isFirstHalf(_ s: String) -> Bool {
        let lower = s.lowercased()
        return lower.contains("1h") || lower.contains("1st half") || lower.contains("first half") || lower.contains("first 5")
    }

    private func isSecondHalf(_ s: String) -> Bool {
        let lower = s.lowercased()
        return lower.contains("2h") || lower.contains("2nd half") || lower.contains("second half")
    }

    private func isSpreadMarket(_ o: GameMarketOutcome) -> Bool {
        let mt = (o.marketType ?? "").lowercased()
        let mn = o.marketName.lowercased()
        return mt.contains("spread") || mn.contains("spread") || mn.contains("handicap")
    }

    private func isTotalMarket(_ o: GameMarketOutcome) -> Bool {
        let mt = (o.marketType ?? "").lowercased()
        let mn = o.marketName.lowercased()
        return mt.contains("total") || mn.contains("total")
    }

    private func isFullGameSpread(_ name: String) -> Bool {
        let lower = name.lowercased()
        return !lower.contains("1h") && !lower.contains("1st half") && !lower.contains("first half") &&
               !lower.contains("2h") && !lower.contains("2nd half") && !lower.contains("second half") &&
               !lower.contains("first 5")
    }

    // MARK: - Data Parsing

    private struct ParsedSpread {
        let margin: Double
        let probability: Double
        let isHome: Bool
    }

    private func parseSprOutcome(_ o: GameMarketOutcome) -> ParsedSpread? {
        let lower = o.outcomeName.lowercased()
        let homeWords = homeTeam.lowercased().split(separator: " ")
        let awayWords = awayTeam.lowercased().split(separator: " ")
        let isHome = homeWords.contains(where: { $0.count >= 3 && lower.contains($0) })
        let isAway = awayWords.contains(where: { $0.count >= 3 && lower.contains($0) })
        guard isHome || isAway else { return nil }
        let threshold = o.threshold ?? Self.extractNumber(from: o.outcomeName)
        guard let t = threshold else { return nil }
        let margin = isHome ? t : -t
        return ParsedSpread(margin: margin, probability: o.probability ?? 0.5, isHome: isHome)
    }

    private func extractTotalThresholds(_ outcomes: [GameMarketOutcome]) -> [(threshold: Double, overProb: Double)] {
        outcomes.compactMap { t in
            let name = t.outcomeName.lowercased()
            guard name.contains("over") else { return nil }
            let threshold = t.threshold ?? Self.extractNumber(from: t.outcomeName)
            guard let th = threshold else { return nil }
            return (th, t.overProbability ?? t.probability ?? 0.5)
        }
        .sorted(by: { $0.threshold < $1.threshold })
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
            if rawPdf.count == 1 { density[i] = rawPdf[0].density }
            else if x <= rawPdf[0].mid { density[i] = rawPdf[0].density * max(0, 1 - (rawPdf[0].mid - x) / (step * 3)) }
            else if x >= rawPdf.last!.mid { density[i] = rawPdf.last!.density * max(0, 1 - (x - rawPdf.last!.mid) / (step * 3)) }
            else {
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
