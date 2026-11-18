import SwiftUI

// MARK: - Grouping Machinery Native Views (#12288 · Ruling 227: A · Direction 228)
//
// Topic-free SwiftUI renderer for all 8 section visual forms and the Discover card.
// Rules enforced:
// - Zero topic-specific code: dispatches strictly on `formId` and served atom shapes.
// - Three rows then "Show all" (`effectiveVisibleLimit <= 3`).
// - Ladder, range, rate, and count markets in ascending numerical order (Direction 228).
// - Real verified art or nothing — never placeholder letters / monogram initials.
// - Full text wrapping at largest Dynamic Type sizes (zero `"…"` truncation).

private struct MachineryPreloadedImagesKey12288: EnvironmentKey {
    static let defaultValue: [String: PairedPlatformImage] = [:]
}

extension EnvironmentValues {
    var machineryPreloadedImages12288: [String: PairedPlatformImage] {
        get { self[MachineryPreloadedImagesKey12288.self] }
        set { self[MachineryPreloadedImagesKey12288.self] = newValue }
    }
}

struct MachineryRenderedPictureFramesKey12288: PreferenceKey {
    static var defaultValue: [CGRect] = []
    static func reduce(value: inout [CGRect], nextValue: () -> [CGRect]) {
        value.append(contentsOf: nextValue())
    }
}

enum MachineryDateFormatting12288 {
    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let kickoffFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "EEE, h:mm a"
        return f
    }()

    private static let spanFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d"
        return f
    }()

    static func parseISO(_ raw: String) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let d = isoFractional.date(from: trimmed) ?? isoPlain.date(from: trimmed) {
            return d
        }
        let normalized = trimmed.hasSuffix("Z") || trimmed.contains("+") ? trimmed : trimmed + "Z"
        return isoFractional.date(from: normalized) ?? isoPlain.date(from: normalized)
    }

    static func shortKickoff(_ iso: String) -> String {
        guard let d = parseISO(iso) else { return "" }
        return kickoffFormatter.string(from: d)
    }

    static func shortSpan(_ startIso: String, _ endIso: String) -> String {
        let s = parseISO(startIso).map { spanFormatter.string(from: $0) } ?? ""
        let e = parseISO(endIso).map { spanFormatter.string(from: $0) } ?? ""
        if !s.isEmpty && !e.isEmpty {
            return s == e ? s : "\(s)–\(e)"
        }
        return s.isEmpty ? e : s
    }
}

/// Renders verified art (`team_logo`, `tmdb_poster`, `tmdb_headshot`, `person`) when `art.verifiedURL`
/// is present; renders `EmptyView()` otherwise — NEVER placeholder letters or monogram circles.
struct MachinerySubjectArtView: View {
    let art: MachinerySubjectArt?
    var width: CGFloat = 34
    var height: CGFloat = 34
    var reservesWidthWhenEmpty: Bool = false
    var emptySlotIsPoster: Bool = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages

    private var trackBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.14) : DS.border
    }

    @ViewBuilder
    var body: some View {
        if let art, let url = art.verifiedURL {
            let w = art.isPoster ? width : max(width, height)
            let h = art.isPoster ? height : max(width, height)
            Group {
                if let preloaded = preloadedImages[url.absoluteString] {
                    styledImage(platformImage(preloaded), art: art, width: w, height: h)
                } else {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            styledImage(image, art: art, width: w, height: h)
                        default:
                            blankSlot(art: art, width: w, height: h)
                        }
                    }
                }
            }
            .frame(width: w, height: h)
            .background(
                GeometryReader { geo in
                    Color.clear.preference(
                        key: MachineryRenderedPictureFramesKey12288.self,
                        value: [geo.frame(in: .named("machineryPageRoot12288"))]
                    )
                }
            )
            .accessibilityHidden(true)
        } else if reservesWidthWhenEmpty {
            let w = emptySlotIsPoster ? width : max(width, height)
            Color.clear
                .frame(width: w, height: 1)
                .accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private func styledImage(_ image: Image, art: MachinerySubjectArt, width: CGFloat, height: CGFloat) -> some View {
        if art.isPoster {
            image
                .resizable()
                .scaledToFill()
                .frame(width: width, height: height, alignment: .top)
                .background(trackBgColor)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(borderColor, lineWidth: 1))
        } else if art.isTeamLogo {
            image
                .resizable()
                .scaledToFit()
                .padding(3)
                .frame(width: width, height: height)
                .background(trackBgColor)
                .clipShape(Circle())
                .overlay(Circle().stroke(borderColor, lineWidth: 1))
        } else {
            image
                .resizable()
                .scaledToFill()
                .frame(width: width, height: height, alignment: .top)
                .background(trackBgColor)
                .clipShape(Circle())
                .overlay(Circle().stroke(borderColor, lineWidth: 1))
        }
    }

    @ViewBuilder
    private func blankSlot(art: MachinerySubjectArt, width: CGFloat, height: CGFloat) -> some View {
        if art.isPoster {
            RoundedRectangle(cornerRadius: 6)
                .fill(trackBgColor)
                .frame(width: width, height: height)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(borderColor, lineWidth: 1))
        } else {
            Circle()
                .fill(trackBgColor)
                .frame(width: width, height: height)
                .overlay(Circle().stroke(borderColor, lineWidth: 1))
        }
    }

    private func platformImage(_ img: PairedPlatformImage) -> Image {
        #if canImport(UIKit)
        return Image(uiImage: img)
        #elseif canImport(AppKit)
        return Image(nsImage: img)
        #endif
    }
}

/// Reusable `"Show all N <noun> (+K more)"` / `"Show top 3"` expander button.
struct MachineryShowAllButton: View {
    let expanded: Bool
    let totalCount: Int
    let visibleLimit: Int
    let noun: String
    let onToggle: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @ScaledMetric(relativeTo: .caption) private var fontSize: CGFloat = 13

    var body: some View {
        if totalCount > visibleLimit {
            Button(action: onToggle) {
                Text(
                    expanded
                        ? "Show top \(visibleLimit)"
                        : "Show all \(totalCount) \(noun) (+\(totalCount - visibleLimit) more)"
                )
                .font(.system(size: min(fontSize, 20), weight: .semibold))
                .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 44)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(colorScheme == .dark ? Color.white.opacity(0.07) : DS.trackBg)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(colorScheme == .dark ? Color.white.opacity(0.14) : DS.border, lineWidth: 1)
                )
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("machinery.showAll.\(noun)")
        }
    }
}

/// Assigns mutually distinct, readable line colours across up to 3 chart series even when
/// the server sends identical or same-family hexes (`#12924` follow-up).
enum MachineryChartSeriesPalette12288 {
    private static let lightFallback: [String] = [
        "#059669", // Emerald (160°)
        "#2563EB", // Royal blue (221°)
        "#D97706", // Warm amber (32°)
        "#DC2626", // Crimson red (0°)
        "#7C3AED"  // Deep violet (263°)
    ]

    private static let darkFallback: [String] = [
        "#34D399", // Bright emerald (158°)
        "#60A5FA", // Sky blue (217°)
        "#FBBF24", // Amber gold (43°)
        "#F87171", // Coral red (0°)
        "#A78BFA"  // Soft violet (255°)
    ]

    struct RGBMetrics {
        let r: Double
        let g: Double
        let b: Double
        let hueDeg: Double
        let chroma: Double
        let luma: Double
    }

    static func parseMetrics(_ rawHex: String) -> RGBMetrics? {
        let cleaned = rawHex.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard cleaned.count == 6, let val = UInt32(cleaned, radix: 16) else { return nil }
        let r = Double((val >> 16) & 0xFF)
        let g = Double((val >> 8) & 0xFF)
        let b = Double(val & 0xFF)
        let maxC = max(r, g, b)
        let minC = min(r, g, b)
        let delta = maxC - minC
        var hue: Double = 0
        if delta > 0.001 {
            if maxC == r {
                hue = 60.0 * (((g - b) / delta).truncatingRemainder(dividingBy: 6.0))
            } else if maxC == g {
                hue = 60.0 * (((b - r) / delta) + 2.0)
            } else {
                hue = 60.0 * (((r - g) / delta) + 4.0)
            }
            if hue < 0 { hue += 360.0 }
        }
        let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return RGBMetrics(r: r, g: g, b: b, hueDeg: hue, chroma: delta, luma: luma)
    }

    static func areDistinct(_ a: RGBMetrics, _ b: RGBMetrics) -> Bool {
        let dr = a.r - b.r
        let dg = a.g - b.g
        let db = a.b - b.b
        let rgbDist = (dr * dr + dg * dg + db * db).squareRoot()
        if rgbDist < 85.0 { return false }
        if a.chroma >= 24.0 && b.chroma >= 24.0 {
            let diff = abs(a.hueDeg - b.hueDeg)
            let hueDist = min(diff, 360.0 - diff)
            if hueDist < 45.0 { return false }
        }
        return true
    }

    static func resolvedHexes(for series: [MachineryHistorySeries], isDark: Bool) -> [String] {
        let palette = isDark ? darkFallback : lightFallback
        var chosenHexes: [String] = []
        var chosenMetrics: [RGBMetrics] = []

        for (idx, s) in series.enumerated() {
            let candidate = s.color.trimmingCharacters(in: .whitespacesAndNewlines)
            if let m = parseMetrics(candidate),
               (series.count == 1 || m.chroma >= 24.0),
               (isDark ? m.luma >= 80.0 : m.luma <= 195.0),
               chosenMetrics.allSatisfy({ areDistinct($0, m) }) {
                let normalized = candidate.hasPrefix("#") ? candidate.uppercased() : "#\(candidate.uppercased())"
                chosenHexes.append(normalized)
                chosenMetrics.append(m)
                continue
            }

            // Pick the first fallback colour distinct from every already-chosen series colour.
            var picked: (String, RGBMetrics)? = nil
            for fallbackHex in palette {
                if let fm = parseMetrics(fallbackHex),
                   chosenMetrics.allSatisfy({ areDistinct($0, fm) }) {
                    picked = (fallbackHex, fm)
                    break
                }
            }
            if let (hex, fm) = picked {
                chosenHexes.append(hex)
                chosenMetrics.append(fm)
            } else {
                let fallbackHex = palette[idx % palette.count]
                chosenHexes.append(fallbackHex)
                if let fm = parseMetrics(fallbackHex) {
                    chosenMetrics.append(fm)
                }
            }
        }
        return chosenHexes
    }
}

/// Connected straight-line probability trend card (`probability_history_chart` + `mini_chart`).
struct MachineryHistoryChartCardView: View {
    let chart: MachineryHistoryChartItem
    var compact: Bool = false

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .caption) private var titleSize: CGFloat = 13
    @ScaledMetric(relativeTo: .caption2) private var metaSize: CGFloat = 11

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var compactBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.05) : DS.trackBg.opacity(0.55)
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    private var secondaryInk: Color {
        colorScheme == .dark ? Color(white: 0.72) : DS.textSecondaryReadable
    }

    private var yMin: Int { chart.yMin }
    private var yMax: Int { chart.yMax > chart.yMin ? chart.yMax : 100 }
    private var yMid: Int { Int((Double(yMin + yMax) / 2.0).rounded()) }

    var body: some View {
        let spanText = MachineryDateFormatting12288.shortSpan(chart.startIso, chart.endIso)
        let shownSeries = Array(chart.series.prefix(3))
        let seriesHexes = MachineryChartSeriesPalette12288.resolvedHexes(
            for: shownSeries,
            isDark: colorScheme == .dark
        )
        let content = VStack(alignment: .leading, spacing: 8) {
            if dynamicTypeSize >= .xxxLarge {
                VStack(alignment: .leading, spacing: 2) {
                    Text(chart.title)
                        .font(.system(size: min(titleSize, 22), weight: .bold))
                        .foregroundStyle(primaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                    if !spanText.isEmpty {
                        Text(spanText)
                            .font(.system(size: min(metaSize, 18), weight: .medium))
                            .foregroundStyle(secondaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(chart.title)
                        .font(.system(size: min(titleSize, 22), weight: .bold))
                        .foregroundStyle(primaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if !spanText.isEmpty {
                        Text(spanText)
                            .font(.system(size: min(metaSize, 18), weight: .medium))
                            .foregroundStyle(secondaryInk)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
            }

            // Legend items (up to 3 series, each guaranteed a distinct colour)
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(shownSeries.enumerated()), id: \.element.id) { idx, s in
                    let seriesColor = Color(hex: seriesHexes[idx])
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Circle()
                            .fill(seriesColor)
                            .frame(width: 8, height: 8)
                        Text(s.name)
                            .font(.system(size: min(metaSize, 18), weight: .medium))
                            .foregroundStyle(secondaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        Text("\(s.currentPct)%")
                            .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                            .foregroundStyle(primaryInk)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
            }

            // Connected polyline plot
            HStack(spacing: 6) {
                VStack(alignment: .trailing, spacing: 0) {
                    Text("\(yMax)%")
                    Spacer(minLength: 0)
                    Text("\(yMid)%")
                    Spacer(minLength: 0)
                    Text("\(yMin)%")
                }
                .font(.system(size: 10, weight: .medium).monospacedDigit())
                .foregroundStyle(secondaryInk)
                .frame(width: 34, height: compact ? 74 : 104)

                GeometryReader { geo in
                    let w = max(1, geo.size.width)
                    let h = max(1, geo.size.height)
                    let topPad: CGFloat = 6
                    let botPad: CGFloat = 6
                    let plotH = max(1, h - topPad - botPad)
                    let ySpan = CGFloat(max(1, yMax - yMin))
                    let yOf: (Int) -> CGFloat = { pct in
                        let clamped = CGFloat(min(yMax, max(yMin, pct)) - yMin)
                        return (h - botPad) - (clamped / ySpan) * plotH
                    }

                    ZStack {
                        ForEach([yMin, yMid, yMax], id: \.self) { tick in
                            Path { p in
                                let y = yOf(tick)
                                p.move(to: CGPoint(x: 0, y: y))
                                p.addLine(to: CGPoint(x: w, y: y))
                            }
                            .stroke(borderColor, lineWidth: 1)
                        }

                        ForEach(Array(shownSeries.enumerated()), id: \.element.id) { idx, s in
                            let pts = s.points
                            if !pts.isEmpty {
                                let strokeColor = Color(hex: seriesHexes[idx])
                                Path { p in
                                    for (ptIdx, pt) in pts.enumerated() {
                                        let x = pts.count == 1
                                            ? w * 0.5
                                            : (CGFloat(ptIdx) / CGFloat(pts.count - 1)) * (w - 4)
                                        let y = yOf(pt.pct)
                                        if ptIdx == 0 {
                                            p.move(to: CGPoint(x: x, y: y))
                                        } else {
                                            p.addLine(to: CGPoint(x: x, y: y))
                                        }
                                    }
                                }
                                .stroke(
                                    strokeColor,
                                    style: StrokeStyle(lineWidth: 2.25, lineCap: .round, lineJoin: .round)
                                )

                                if let last = pts.last {
                                    let endX = pts.count == 1 ? w * 0.5 : (w - 4)
                                    Circle()
                                        .fill(strokeColor)
                                        .frame(width: 6, height: 6)
                                        .position(x: endX, y: yOf(last.pct))
                                }
                            }
                        }
                    }
                }
                .frame(height: compact ? 74 : 104)
            }
            .background {
                if chart.hasMovingSeries {
                    GeometryReader { geo in
                        Color.clear.preference(
                            key: MachineryRenderedPictureFramesKey12288.self,
                            value: [geo.frame(in: .named("machineryPageRoot12288"))]
                        )
                    }
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Probability trend chart for \(chart.title)")
        }

        if compact {
            content
                .padding(10)
                .background(compactBgColor)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(borderColor, lineWidth: 1))
                .accessibilityIdentifier("machinery.card.miniChart.\(chart.marketId)")
        } else {
            NavigationLink(value: Route.futuresDetail(id: chart.marketId)) {
                content
                    .padding(14)
                    .background(cardBgColor)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("machinery.historyChart.\(chart.marketId)")
        }
    }
}

// MARK: - Section Renderer (All 8 Forms)

struct MachinerySectionBlockView: View {
    let visualBlock: MachineryVisualBlock
    let members: [ContainerHubMember]
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages

    var body: some View {
        let limit = visualBlock.effectiveVisibleLimit
        switch visualBlock.formId {
        case .pairedStageBars:
            if let set = visualBlock.pairedMetricSet, !set.entries.isEmpty {
                DiscoverPairedMetricCardView(
                    set: set,
                    form: .pairedBarsTop5Expandable,
                    collapsedCount: limit,
                    showsPlaceholderMonogram: false,
                    showsCardHeader: false,
                    allowsRouteLinks: true,
                    isOscarsCollectionSurface: true,
                    preloadedImages: preloadedImages
                )
            }
        case .probabilityHistoryChart:
            MachineryHistoryChartSectionView(items: visualBlock.historyItems, limit: limit)
        case .coinFlipMatchups:
            MachineryCoinFlipSectionView(items: visualBlock.eventItems, limit: limit)
        case .matchupSlate:
            MachineryMatchupSlateSectionView(
                members: members,
                fallbackItems: visualBlock.eventItems,
                limit: limit
            )
        case .duelBar:
            MachineryDuelBarSectionView(items: visualBlock.marketItems)
        case .contenderSpotlight:
            MachineryContenderSpotlightSectionView(items: visualBlock.marketItems, limit: limit)
        case .siblingFieldsGrid:
            MachinerySiblingFieldsSectionView(items: visualBlock.marketItems, limit: limit)
        case .benchmarkStrip:
            MachineryBenchmarkStripSectionView(items: visualBlock.marketItems, limit: limit)
        }
    }
}

private struct MachineryHistoryChartSectionView: View {
    let items: [MachineryHistoryChartItem]
    let limit: Int
    @State private var expanded = false

    var body: some View {
        let shown = expanded ? items : Array(items.prefix(limit))
        VStack(alignment: .leading, spacing: 10) {
            ForEach(shown) { chart in
                MachineryHistoryChartCardView(chart: chart, compact: false)
            }
            MachineryShowAllButton(
                expanded: expanded,
                totalCount: items.count,
                visibleLimit: limit,
                noun: "charts",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }
}

private struct MachineryCoinFlipSectionView: View {
    let items: [MachineryEventVisualItem]
    let limit: Int
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .subheadline) private var teamSize: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var metaSize: CGFloat = 12

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    private var secondaryInk: Color {
        colorScheme == .dark ? Color(white: 0.72) : DS.textSecondaryReadable
    }

    var body: some View {
        let shown = expanded ? items : Array(items.prefix(limit))
        VStack(alignment: .leading, spacing: 10) {
            ForEach(shown) { item in
                let colors = ProbabilityBarPalette.pair(
                    awayHex: item.awayArt?.accentColor,
                    homeHex: item.homeArt?.accentColor
                )
                let when = MachineryDateFormatting12288.shortKickoff(item.commenceTime)
                NavigationLink(value: Route.eventDetail(id: item.eventId)) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("TOSS-UP")
                                .font(.system(size: min(metaSize, 18), weight: .bold))
                                .tracking(0.4)
                                .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 6)
                            if !when.isEmpty {
                                Text(when)
                                    .font(.system(size: min(metaSize, 18), weight: .medium))
                                    .foregroundStyle(secondaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }

                        if dynamicTypeSize >= .xxxLarge {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(spacing: 10) {
                                    MachinerySubjectArtView(art: item.awayArt, width: 32, height: 32)
                                    Text(item.awayShort)
                                        .font(.system(size: min(teamSize, 24), weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Spacer(minLength: 6)
                                    Text("\(item.awayPct)%")
                                        .font(.system(size: min(teamSize, 24), weight: .bold).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                }
                                HStack(spacing: 10) {
                                    MachinerySubjectArtView(art: item.homeArt, width: 32, height: 32)
                                    Text(item.homeShort)
                                        .font(.system(size: min(teamSize, 24), weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Spacer(minLength: 6)
                                    Text("\(item.homePct)%")
                                        .font(.system(size: min(teamSize, 24), weight: .bold).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                }
                            }
                        } else {
                            HStack(alignment: .center, spacing: 8) {
                                HStack(spacing: 8) {
                                    MachinerySubjectArtView(art: item.awayArt, width: 32, height: 32)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.awayShort)
                                            .font(.system(size: min(teamSize, 22), weight: .semibold))
                                            .foregroundStyle(primaryInk)
                                            .fixedSize(horizontal: false, vertical: true)
                                        Text("\(item.awayPct)%")
                                            .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                                            .foregroundStyle(secondaryInk)
                                    }
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)

                                Text("at")
                                    .font(.system(size: min(metaSize, 18), weight: .medium))
                                    .foregroundStyle(secondaryInk)

                                HStack(spacing: 8) {
                                    VStack(alignment: .trailing, spacing: 2) {
                                        Text(item.homeShort)
                                            .font(.system(size: min(teamSize, 22), weight: .semibold))
                                            .foregroundStyle(primaryInk)
                                            .multilineTextAlignment(.trailing)
                                            .fixedSize(horizontal: false, vertical: true)
                                        Text("\(item.homePct)%")
                                            .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                                            .foregroundStyle(secondaryInk)
                                    }
                                    MachinerySubjectArtView(art: item.homeArt, width: 32, height: 32)
                                }
                                .frame(maxWidth: .infinity, alignment: .trailing)
                            }
                        }

                        GeometryReader { geo in
                            let awayFrac = CGFloat(min(92, max(8, item.awayPct))) / 100.0
                            HStack(spacing: 2) {
                                Rectangle()
                                    .fill(Color(hex: colors.away))
                                    .frame(width: max(6, geo.size.width * awayFrac - 1))
                                Rectangle()
                                    .fill(Color(hex: colors.home))
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .frame(height: 8)
                        .clipShape(Capsule())
                    }
                    .padding(14)
                    .background(cardBgColor)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }

            MachineryShowAllButton(
                expanded: expanded,
                totalCount: items.count,
                visibleLimit: limit,
                noun: "games",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }
}

private struct MachineryMatchupSlateSectionView: View {
    let members: [ContainerHubMember]
    let fallbackItems: [MachineryEventVisualItem]
    let limit: Int
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme

    private var eventMembers: [ContainerHubMember] {
        members.filter { member in
            if case .event = member.card { return true }
            return false
        }
    }

    var body: some View {
        if !eventMembers.isEmpty {
            let shown = expanded ? eventMembers : Array(eventMembers.prefix(limit))
            VStack(alignment: .leading, spacing: 10) {
                ForEach(shown) { member in
                    if case .event(let event) = member.card {
                        NavigationLink(value: Route.eventDetail(id: member.memberId)) {
                            EventCardView(event: event, reason: nil)
                                .padding(14)
                                .background(
                                    colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg,
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(colorScheme == .dark ? Color.white.opacity(0.12) : DS.border, lineWidth: 1)
                                )
                                .background(
                                    GeometryReader { geo in
                                        let f = geo.frame(in: .named("machineryPageRoot12288"))
                                        let awayHasArt = (event.awayTeamData?.logoSmall?.isEmpty == false) || (event.awayTeamData?.logoLarge?.isEmpty == false) || (event.awayImageUrl?.isEmpty == false)
                                        let homeHasArt = (event.homeTeamData?.logoSmall?.isEmpty == false) || (event.homeTeamData?.logoLarge?.isEmpty == false) || (event.homeImageUrl?.isEmpty == false)
                                        let rects = (awayHasArt ? [f] : []) + (homeHasArt ? [f] : [])
                                        Color.clear.preference(
                                            key: MachineryRenderedPictureFramesKey12288.self,
                                            value: rects
                                        )
                                    }
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                MachineryShowAllButton(
                    expanded: expanded,
                    totalCount: eventMembers.count,
                    visibleLimit: limit,
                    noun: "games",
                    onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
                )
            }
        } else if !fallbackItems.isEmpty {
            MachineryCoinFlipSectionView(items: fallbackItems, limit: limit)
        }
    }
}

private struct MachineryDuelBarSectionView: View {
    let items: [MachineryMarketVisualItem]
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .subheadline) private var nameSize: CGFloat = 15
    @ScaledMetric(relativeTo: .title3) private var pctSize: CGFloat = 21

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    var body: some View {
        if let lead = items.first, lead.outcomes.count >= 2 {
            let left = lead.outcomes[0]
            let right = lead.outcomes[1]
            let colors = ProbabilityBarPalette.pair(
                awayHex: left.art?.accentColor,
                homeHex: right.art?.accentColor
            )
            let leftColor = Color(hex: colors.away)
            let rightColor = Color(hex: colors.home)

            NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                VStack(alignment: .leading, spacing: 12) {
                    if dynamicTypeSize >= .xxxLarge {
                        VStack(alignment: .leading, spacing: 10) {
                            duelSideRow(outcome: left, dotColor: leftColor)
                            duelSideRow(outcome: right, dotColor: rightColor)
                        }
                    } else {
                        HStack(alignment: .top, spacing: 12) {
                            HStack(spacing: 10) {
                                MachinerySubjectArtView(art: left.art, width: 40, height: 40)
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: 6) {
                                        if left.art?.verifiedURL == nil {
                                            Circle().fill(leftColor).frame(width: 9, height: 9)
                                        }
                                        Text(left.name)
                                            .font(.system(size: min(nameSize, 22), weight: .semibold))
                                            .foregroundStyle(primaryInk)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    Text("\(left.renderedPercent)%")
                                        .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            HStack(spacing: 10) {
                                VStack(alignment: .trailing, spacing: 2) {
                                    HStack(spacing: 6) {
                                        Text(right.name)
                                            .font(.system(size: min(nameSize, 22), weight: .semibold))
                                            .foregroundStyle(primaryInk)
                                            .multilineTextAlignment(.trailing)
                                            .fixedSize(horizontal: false, vertical: true)
                                        if right.art?.verifiedURL == nil {
                                            Circle().fill(rightColor).frame(width: 9, height: 9)
                                        }
                                    }
                                    Text("\(right.renderedPercent)%")
                                        .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                }
                                MachinerySubjectArtView(art: right.art, width: 40, height: 40)
                            }
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        }
                    }

                    GeometryReader { geo in
                        let leftFrac = CGFloat(min(94, max(6, left.renderedPercent))) / 100.0
                        HStack(spacing: 2) {
                            Rectangle()
                                .fill(leftColor)
                                .frame(width: max(8, geo.size.width * leftFrac - 1))
                            Rectangle()
                                .fill(rightColor)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(height: 11)
                    .clipShape(Capsule())
                }
                .padding(16)
                .background(cardBgColor)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func duelSideRow(outcome: MachineryOutcomeVisual, dotColor: Color) -> some View {
        HStack(spacing: 10) {
            if outcome.art?.verifiedURL != nil {
                MachinerySubjectArtView(art: outcome.art, width: 40, height: 40)
            } else {
                Circle().fill(dotColor).frame(width: 10, height: 10)
            }
            Text(outcome.name)
                .font(.system(size: min(nameSize, 24), weight: .semibold))
                .foregroundStyle(primaryInk)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 6)
            Text("\(outcome.renderedPercent)%")
                .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                .foregroundStyle(primaryInk)
        }
    }
}

private struct MachineryContenderSpotlightSectionView: View {
    let items: [MachineryMarketVisualItem]
    let limit: Int
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .subheadline) private var labelSize: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var detailSize: CGFloat = 12

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var trackBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    private var secondaryInk: Color {
        colorScheme == .dark ? Color(white: 0.72) : DS.textSecondaryReadable
    }

    var body: some View {
        if let lead = items.first, !lead.outcomes.isEmpty {
            if lead.effectiveScaleOrdered {
                scaleOrderedBody(lead: lead)
            } else {
                podiumBody(lead: lead)
            }
        }
    }

    @ViewBuilder
    private func scaleOrderedBody(lead: MachineryMarketVisualItem) -> some View {
        let shown = expanded ? lead.outcomes : Array(lead.outcomes.prefix(limit))
        let maxPct = lead.outcomes.map(\.renderedPercent).max() ?? 0
        VStack(alignment: .leading, spacing: 10) {
            NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(shown.enumerated()), id: \.element.id) { idx, o in
                        let isFav = (lead.leaderOutcomeId != nil && o.outcomeId == lead.leaderOutcomeId)
                            || (lead.leaderOutcomeId == nil && o.renderedPercent == maxPct)
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(o.name)
                                    .font(.system(size: min(labelSize, 22), weight: isFav ? .bold : .medium))
                                    .foregroundStyle(isFav ? primaryInk : secondaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 6)
                                Text("\(o.renderedPercent)%")
                                    .font(.system(size: min(labelSize, 22), weight: isFav ? .heavy : .semibold).monospacedDigit())
                                    .foregroundStyle(isFav ? primaryInk : secondaryInk)
                            }
                            GeometryReader { geo in
                                let frac = CGFloat(min(100, max(3, o.renderedPercent))) / 100.0
                                ZStack(alignment: .leading) {
                                    Capsule().fill(trackBgColor)
                                    Capsule()
                                        .fill(isFav ? DS.emerald : Color.gray.opacity(0.6))
                                        .frame(width: max(4, geo.size.width * frac))
                                }
                            }
                            .frame(height: 7)
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        if idx < shown.count - 1 {
                            Rectangle().fill(borderColor).frame(height: 1)
                        }
                    }
                }
                .background(cardBgColor)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            MachineryShowAllButton(
                expanded: expanded,
                totalCount: lead.outcomes.count,
                visibleLimit: limit,
                noun: "outcomes",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }

    @ViewBuilder
    private func podiumBody(lead: MachineryMarketVisualItem) -> some View {
        let topThree = Array(lead.outcomes.prefix(3))
        let chasers = Array(lead.outcomes.dropFirst(3))
        let topHasArt = topThree.contains { $0.art?.verifiedURL != nil }
        let topUsesPoster = topThree.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }
        let chasersHaveArt = chasers.contains { $0.art?.verifiedURL != nil }
        let chasersUsePoster = chasers.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }
        VStack(alignment: .leading, spacing: 10) {
            if dynamicTypeSize >= .xxxLarge {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(topThree.enumerated()), id: \.element.id) { idx, o in
                        NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                            stackedSpotlightTile(
                                rank: idx + 1,
                                outcome: o,
                                reservesArtSlot: topHasArt,
                                listUsesPoster: topUsesPoster
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 8) {
                    ForEach(Array(topThree.enumerated()), id: \.element.id) { idx, o in
                        NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                            columnSpotlightTile(rank: idx + 1, outcome: o)
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity)
                    }
                }
            }

            if expanded && !chasers.isEmpty {
                NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(chasers.enumerated()), id: \.element.id) { idx, o in
                            let rowIsPoster = o.art?.isPoster ?? chasersUsePoster
                            HStack(spacing: 10) {
                                MachinerySubjectArtView(
                                    art: o.art,
                                    width: chasersUsePoster ? 28 : 32,
                                    height: rowIsPoster ? 40 : 32,
                                    reservesWidthWhenEmpty: chasersHaveArt,
                                    emptySlotIsPoster: chasersUsePoster
                                )
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(o.name)
                                        .font(.system(size: min(labelSize, 22), weight: .medium))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                    if let detail = o.art?.detail, !detail.isEmpty {
                                        Text(detail)
                                            .font(.system(size: min(detailSize, 18)))
                                            .foregroundStyle(secondaryInk)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                }
                                Spacer(minLength: 6)
                                Text("\(o.renderedPercent)%")
                                    .font(.system(size: min(labelSize, 22), weight: .bold).monospacedDigit())
                                    .foregroundStyle(primaryInk)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            if idx < chasers.count - 1 {
                                Rectangle().fill(borderColor).frame(height: 1)
                            }
                        }
                    }
                    .background(cardBgColor)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }

            MachineryShowAllButton(
                expanded: expanded,
                totalCount: lead.outcomes.count,
                visibleLimit: 3,
                noun: "contenders",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }

    private func columnSpotlightTile(rank: Int, outcome: MachineryOutcomeVisual) -> some View {
        let barColor = (outcome.art?.accentColor.isEmpty == false)
            ? Color(hex: outcome.art!.accentColor)
            : DS.emerald
        return VStack(spacing: 6) {
            HStack {
                Text("#\(rank)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(secondaryInk)
                Spacer(minLength: 2)
                Text("\(outcome.renderedPercent)%")
                    .font(.system(size: min(labelSize, 20), weight: .heavy).monospacedDigit())
                    .foregroundStyle(primaryInk)
            }

            MachinerySubjectArtView(
                art: outcome.art,
                width: outcome.art?.isPoster == true ? 44 : 48,
                height: outcome.art?.isPoster == true ? 64 : 48
            )

            Text(outcome.name)
                .font(.system(size: min(detailSize, 17), weight: .semibold))
                .foregroundStyle(primaryInk)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)

            if let detail = outcome.art?.detail, !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 11))
                    .foregroundStyle(secondaryInk)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            GeometryReader { geo in
                let frac = CGFloat(min(100, max(6, outcome.renderedPercent))) / 100.0
                ZStack(alignment: .leading) {
                    Capsule().fill(trackBgColor)
                    Capsule()
                        .fill(barColor)
                        .frame(width: max(4, geo.size.width * frac))
                }
            }
            .frame(height: 6)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .top)
        .background(cardBgColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
    }

    private func stackedSpotlightTile(
        rank: Int,
        outcome: MachineryOutcomeVisual,
        reservesArtSlot: Bool,
        listUsesPoster: Bool
    ) -> some View {
        let rowIsPoster = outcome.art?.isPoster ?? listUsesPoster
        return HStack(spacing: 12) {
            MachinerySubjectArtView(
                art: outcome.art,
                width: listUsesPoster ? 44 : 48,
                height: rowIsPoster ? 64 : 48,
                reservesWidthWhenEmpty: reservesArtSlot,
                emptySlotIsPoster: listUsesPoster
            )
            VStack(alignment: .leading, spacing: 3) {
                Text("#\(rank) · \(outcome.name)")
                    .font(.system(size: min(labelSize, 24), weight: .semibold))
                    .foregroundStyle(primaryInk)
                    .fixedSize(horizontal: false, vertical: true)
                if let detail = outcome.art?.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: min(detailSize, 19)))
                        .foregroundStyle(secondaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 6)
            Text("\(outcome.renderedPercent)%")
                .font(.system(size: min(labelSize, 24), weight: .heavy).monospacedDigit())
                .foregroundStyle(primaryInk)
        }
        .padding(12)
        .background(cardBgColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
    }
}

private struct MachinerySiblingFieldsSectionView: View {
    let items: [MachineryMarketVisualItem]
    let limit: Int
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @ScaledMetric(relativeTo: .subheadline) private var titleSize: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var rowSize: CGFloat = 13

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var trackBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    private var secondaryInk: Color {
        colorScheme == .dark ? Color(white: 0.72) : DS.textSecondaryReadable
    }

    var body: some View {
        let shown = expanded ? items : Array(items.prefix(limit))
        VStack(alignment: .leading, spacing: 10) {
            ForEach(shown) { market in
                let scaleOrd = market.effectiveScaleOrdered
                let shownOutcomes = Array(market.outcomes.prefix(4))
                let maxPct = shownOutcomes.map(\.renderedPercent).max() ?? 0
                let listHasArt = !scaleOrd && shownOutcomes.contains { $0.art?.verifiedURL != nil }
                let listUsesPoster = shownOutcomes.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }

                NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(market.title)
                                .font(.system(size: min(titleSize, 22), weight: .bold))
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 6)
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(secondaryInk)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(shownOutcomes) { o in
                                let isFav = !scaleOrd
                                    || (market.leaderOutcomeId != nil && o.outcomeId == market.leaderOutcomeId)
                                    || (market.leaderOutcomeId == nil && o.renderedPercent == maxPct)
                                let barColor: Color = {
                                    if scaleOrd {
                                        return isFav ? DS.emerald : Color.gray.opacity(0.6)
                                    }
                                    if let hex = o.art?.accentColor, !hex.isEmpty {
                                        return Color(hex: hex)
                                    }
                                    return DS.emerald
                                }()

                                HStack(alignment: .center, spacing: 10) {
                                    if !scaleOrd {
                                        let rowIsPoster = o.art?.isPoster ?? listUsesPoster
                                        MachinerySubjectArtView(
                                            art: o.art,
                                            width: 28,
                                            height: rowIsPoster ? 38 : 28,
                                            reservesWidthWhenEmpty: listHasArt,
                                            emptySlotIsPoster: true
                                        )
                                    }
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                                            Text(o.name)
                                                .font(.system(size: min(rowSize, 20), weight: isFav ? .semibold : .medium))
                                                .foregroundStyle(isFav ? primaryInk : secondaryInk)
                                                .fixedSize(horizontal: false, vertical: true)
                                            Spacer(minLength: 6)
                                            Text("\(o.renderedPercent)%")
                                                .font(.system(size: min(rowSize, 20), weight: isFav ? .bold : .semibold).monospacedDigit())
                                                .foregroundStyle(isFav ? primaryInk : secondaryInk)
                                        }
                                        GeometryReader { geo in
                                            let frac = CGFloat(min(100, max(4, o.renderedPercent))) / 100.0
                                            ZStack(alignment: .leading) {
                                                Capsule().fill(trackBgColor)
                                                Capsule()
                                                    .fill(barColor)
                                                    .frame(width: max(4, geo.size.width * frac))
                                            }
                                        }
                                        .frame(height: 6)
                                    }
                                }
                            }
                        }
                    }
                    .padding(14)
                    .background(cardBgColor)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }

            MachineryShowAllButton(
                expanded: expanded,
                totalCount: items.count,
                visibleLimit: limit,
                noun: "markets",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }
}

private struct MachineryBenchmarkStripSectionView: View {
    let items: [MachineryMarketVisualItem]
    let limit: Int
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @ScaledMetric(relativeTo: .caption) private var rowSize: CGFloat = 13

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var badgeBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.09) : DS.trackBg
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    var body: some View {
        let shown = expanded ? items : Array(items.prefix(limit))
        let listHasArt = shown.contains { $0.outcomes.first?.art?.verifiedURL != nil }
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(shown.enumerated()), id: \.element.id) { idx, market in
                    if let yes = market.outcomes.first {
                        NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                            HStack(alignment: .center, spacing: 10) {
                                MachinerySubjectArtView(
                                    art: yes.art,
                                    width: 28,
                                    height: 28,
                                    reservesWidthWhenEmpty: listHasArt
                                )
                                Text(market.title)
                                    .font(.system(size: min(rowSize, 21), weight: .medium))
                                    .foregroundStyle(primaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                Text("\(yes.renderedPercent)%")
                                    .font(.system(size: min(rowSize, 21), weight: .bold).monospacedDigit())
                                    .foregroundStyle(primaryInk)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(badgeBgColor, in: RoundedRectangle(cornerRadius: 6))
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 11)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        if idx < shown.count - 1 {
                            Rectangle().fill(borderColor).frame(height: 1)
                        }
                    }
                }
            }
            .background(cardBgColor)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))

            MachineryShowAllButton(
                expanded: expanded,
                totalCount: items.count,
                visibleLimit: limit,
                noun: "benchmarks",
                onToggle: { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } }
            )
        }
    }
}

// MARK: - Discover Card Renderer

struct MachineryDiscoverEntryCardView: View {
    let card: MachineryCardContract
    let pairedMetricSet: PairedMetricSet?
    var onOpenContainer: ((String, String) -> Void)? = nil
    var onOpenMarket: ((Int) -> Void)? = nil
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages

    var body: some View {
        if card.formId == .pairedStageBars, let pset = pairedMetricSet, !pset.entries.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                DiscoverPairedMetricCardView(
                    set: pset,
                    form: .pairedBarsTop5Expandable,
                    collapsedCount: 3,
                    showsPlaceholderMonogram: false,
                    allowsRouteLinks: onOpenMarket == nil,
                    isOscarsCollectionSurface: true,
                    preloadedImages: preloadedImages,
                    onOpenMarket: onOpenMarket,
                    onOpenCollection: onOpenContainer
                )
                openSectionsPill
            }
        } else {
            MachineryDiscoverCardView(
                card: card,
                onOpenContainer: onOpenContainer
            )
        }
    }

    @ViewBuilder
    private var openSectionsPill: some View {
        let label = HStack {
            Text("Open all \(card.sectionCount) sections")
                .font(.footnote.weight(.semibold))
            Spacer(minLength: 6)
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
        }
        .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg,
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(colorScheme == .dark ? Color.white.opacity(0.12) : DS.border, lineWidth: 1)
        )

        if let onOpenContainer {
            Button {
                onOpenContainer(card.slug, card.title)
            } label: {
                label.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("machinery.card.openContainer.\(card.slug)")
        } else {
            NavigationLink(value: Route.containerHub(slug: card.slug, name: card.title)) {
                label.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("machinery.card.openContainer.\(card.slug)")
        }
    }
}

struct MachineryDiscoverCardView: View {
    let card: MachineryCardContract
    var onOpenContainer: ((String, String) -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .caption2) private var kickerSize: CGFloat = 11
    @ScaledMetric(relativeTo: .headline) private var titleSize: CGFloat = 17
    @ScaledMetric(relativeTo: .subheadline) private var rowSize: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var subSize: CGFloat = 12

    private var cardBgColor: Color {
        colorScheme == .dark ? Color(red: 0.11, green: 0.11, blue: 0.12) : DS.cardBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    private var trackBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
    }

    private var primaryInk: Color {
        colorScheme == .dark ? Color.white : DS.textPrimary
    }

    private var secondaryInk: Color {
        colorScheme == .dark ? Color(white: 0.72) : DS.textSecondaryReadable
    }

    var body: some View {
        let content = VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(card.kicker.uppercased())
                    .font(.system(size: min(kickerSize, 17), weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                    .fixedSize(horizontal: false, vertical: true)

                Text(card.title)
                    .font(.system(size: min(titleSize, 26), weight: .bold))
                    .foregroundStyle(primaryInk)
                    .fixedSize(horizontal: false, vertical: true)

                if !card.subtitle.isEmpty {
                    Text(card.subtitle)
                        .font(.system(size: min(subSize, 19)))
                        .foregroundStyle(secondaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let miniChart = card.miniChart {
                MachineryHistoryChartCardView(chart: miniChart, compact: true)
            }

            if card.isEventCard {
                eventRowsBody
            } else {
                outcomeRowsBody
            }

            VStack(alignment: .leading, spacing: 4) {
                Rectangle().fill(borderColor).frame(height: 1).padding(.bottom, 4)
                if !card.footer.isEmpty {
                    Text(card.footer)
                        .font(.system(size: min(subSize, 18)))
                        .foregroundStyle(secondaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(spacing: 4) {
                    Text("Open all \(card.sectionCount) sections")
                    Image(systemName: "chevron.right").font(.caption2.weight(.bold))
                }
                .font(.system(size: min(subSize, 18), weight: .semibold))
                .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardBgColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
        .shadow(color: .black.opacity(colorScheme == .dark ? 0.22 : 0.04), radius: 6, x: 0, y: 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("discover.machineryCard.\(card.slug)")

        if let onOpenContainer {
            Button {
                onOpenContainer(card.slug, card.title)
            } label: {
                content.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            NavigationLink(value: Route.containerHub(slug: card.slug, name: card.title)) {
                content.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }

    private var eventRowsBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(card.eventRows.prefix(3).enumerated()), id: \.element.id) { idx, r in
                Group {
                    if dynamicTypeSize >= .xxxLarge {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                MachinerySubjectArtView(art: r.awayArt, width: 26, height: 26)
                                Text("\(r.awayShort) at \(r.homeShort)")
                                    .font(.system(size: min(rowSize, 22), weight: .semibold))
                                    .foregroundStyle(primaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                                MachinerySubjectArtView(art: r.homeArt, width: 26, height: 26)
                            }
                            Text("\(r.awayPct)%–\(r.homePct)%")
                                .font(.system(size: min(rowSize, 22), weight: .bold).monospacedDigit())
                                .foregroundStyle(primaryInk)
                        }
                    } else {
                        HStack(alignment: .center, spacing: 8) {
                            HStack(spacing: 6) {
                                MachinerySubjectArtView(art: r.awayArt, width: 26, height: 26)
                                Text(r.awayShort)
                                    .font(.system(size: min(rowSize, 20), weight: .semibold))
                                    .foregroundStyle(primaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text("at")
                                    .font(.system(size: min(subSize, 17)))
                                    .foregroundStyle(secondaryInk)
                                MachinerySubjectArtView(art: r.homeArt, width: 26, height: 26)
                                Text(r.homeShort)
                                    .font(.system(size: min(rowSize, 20), weight: .semibold))
                                    .foregroundStyle(primaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            Text("\(r.awayPct)%–\(r.homePct)%")
                                .font(.system(size: min(rowSize, 20), weight: .bold).monospacedDigit())
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                }
                .padding(.vertical, 8)
                if idx < min(3, card.eventRows.count) - 1 {
                    Rectangle().fill(borderColor).frame(height: 1)
                }
            }
        }
    }

    private var outcomeRowsBody: some View {
        let rows = Array(card.outcomeRows.prefix(3))
        let maxPct = rows.map(\.renderedPercent).max() ?? 0
        let listHasArt = !card.scaleOrdered && rows.contains { $0.art?.verifiedURL != nil }
        let listUsesPoster = rows.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { idx, o in
                let isFav = !card.scaleOrdered || o.renderedPercent == maxPct
                let barColor: Color = {
                    if card.scaleOrdered {
                        return isFav ? DS.emerald : Color.gray.opacity(0.6)
                    }
                    if let hex = o.art?.accentColor, !hex.isEmpty {
                        return Color(hex: hex)
                    }
                    return DS.emerald
                }()

                HStack(alignment: .center, spacing: 10) {
                    if !card.scaleOrdered {
                        let rowIsPoster = o.art?.isPoster ?? listUsesPoster
                        MachinerySubjectArtView(
                            art: o.art,
                            width: listUsesPoster ? 28 : 32,
                            height: rowIsPoster ? 40 : 32,
                            reservesWidthWhenEmpty: listHasArt,
                            emptySlotIsPoster: listUsesPoster
                        )
                    }
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(o.name)
                                .font(.system(size: min(rowSize, 22), weight: isFav ? .semibold : .medium))
                                .foregroundStyle(isFav ? primaryInk : secondaryInk)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 6)
                            Text("\(o.renderedPercent)%")
                                .font(.system(size: min(rowSize, 22), weight: isFav ? .bold : .semibold).monospacedDigit())
                                .foregroundStyle(isFav ? primaryInk : secondaryInk)
                        }
                        GeometryReader { geo in
                            let frac = CGFloat(min(100, max(4, o.renderedPercent))) / 100.0
                            ZStack(alignment: .leading) {
                                Capsule().fill(trackBgColor)
                                Capsule()
                                    .fill(barColor)
                                    .frame(width: max(4, geo.size.width * frac))
                            }
                        }
                        .frame(height: 6)
                    }
                }
                .padding(.vertical, 8)
                if idx < rows.count - 1 {
                    Rectangle().fill(borderColor).frame(height: 1)
                }
            }
        }
    }
}
