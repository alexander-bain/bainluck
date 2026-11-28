import SwiftUI

// MARK: - Grouping Machinery Native Views (#12288 · Ruling 227: A · Direction 228)
//
// Topic-free SwiftUI renderer for all 8 section visual forms and the Discover card.
// Rules enforced:
// - Zero topic-specific code: dispatches strictly on `formId` and served atom shapes.
// - Three rows then "Show all" (`effectiveVisibleLimit <= 3`).
// - Ladder, range, rate, and count markets in ascending numerical order (Direction 228).
// - When at least one sibling row has verified art, an artless sibling draws its
//   initials in the same circle (Ruling 387: A); all-text cards draw no icons.
// - Full text wrapping at largest Dynamic Type sizes (zero `"…"` truncation).

private struct MachineryPreloadedImagesKey12288: EnvironmentKey {
    static let defaultValue: [String: PairedPlatformImage] = [:]
}

/// #13304 — Enforces an exact width:height ratio filling the proposed width so parent VStacks
/// cannot compress a flexible background/image placeholder narrower than card width.
private struct HeroAspectRatioLayout13304: Layout {
    let ratio: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.replacingUnspecifiedDimensions().width
        return CGSize(width: width, height: width / ratio)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for subview in subviews {
            subview.place(
                at: CGPoint(x: bounds.midX, y: bounds.midY),
                anchor: .center,
                proposal: ProposedViewSize(bounds.size)
            )
        }
    }
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

enum MachineryColorContrast12288 {
    static func pairHexes(awayHex: String?, homeHex: String?, scheme: ColorScheme) -> (away: String, home: String) {
        if scheme == .dark {
            return TeamTextContrast.darkSurfaceColorHexes(
                awayHex: awayHex,
                homeHex: homeHex,
                checkHueFamily: true
            )
        }
        return TeamTextContrast.cardColorHexes(
            awayHex: awayHex,
            homeHex: homeHex,
            checkHueFamily: true
        )
    }

    static func singleAccent(_ hex: String?, scheme: ColorScheme) -> Color {
        guard let hex, !hex.isEmpty else { return DS.emerald }
        if scheme == .dark {
            return Color(hex: TeamTextContrast.usableOnDarkSurface(primaryHex: hex) ?? hex)
        }
        return Color(hex: TeamTextContrast.usableForText(hex) ?? hex)
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
/// is present. When a sibling row has a picture (`reservesWidthWhenEmpty == true`) and this row lacks
/// one, draws its initials in the same circle (Ruling 387: A); otherwise renders `EmptyView()`.
struct MachinerySubjectArtView: View {
    let art: MachinerySubjectArt?
    var width: CGFloat = 34
    var height: CGFloat = 34
    var reservesWidthWhenEmpty: Bool = false
    var emptySlotIsPoster: Bool = false
    var subjectName: String? = nil
    var defaultSubjectKind: String? = nil
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages

    private var trackBgColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : DS.trackBg
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.14) : DS.border
    }

    /// Resolves server-provided initials (`art.initials`) or extracts the trailing entity
    /// after `"Role · Entity"` / full `subjectName` via canonical `KitInitials366B`.
    private var resolvedInitialsTarget: (raw: String, kind: String?)? {
        if let provided = art?.initials?.trimmingCharacters(in: .whitespacesAndNewlines), !provided.isEmpty {
            return (provided, art?.kind ?? defaultSubjectKind)
        }
        guard let rawName = subjectName?.trimmingCharacters(in: .whitespacesAndNewlines), !rawName.isEmpty else {
            return nil
        }
        let subject: String = {
            if let dotRange = rawName.range(of: " · ", options: .backwards) {
                let tail = String(rawName[dotRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !tail.isEmpty { return tail }
            }
            return rawName
        }()
        return (subject, art?.kind ?? defaultSubjectKind)
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
                            if let target = resolvedInitialsTarget {
                                KitInitialsCircle366B(
                                    name: target.raw,
                                    subjectKind: target.kind,
                                    box: CGSize(width: w, height: h)
                                )
                            } else {
                                blankSlot(art: art, width: w, height: h)
                            }
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
            let h = emptySlotIsPoster ? height : max(width, height)
            if let target = resolvedInitialsTarget {
                KitInitialsCircle366B(
                    name: target.raw,
                    subjectKind: target.kind,
                    box: CGSize(width: w, height: h)
                )
            } else {
                Color.clear
                    .frame(width: w, height: 1)
                    .accessibilityHidden(true)
            }
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
    @ScaledMetric(relativeTo: .headline) private var fontSize: CGFloat = 13

    var body: some View {
        if totalCount > visibleLimit {
            Button(action: onToggle) {
                Text(
                    expanded
                        ? "Show top \(visibleLimit)"
                        : "Show all \(totalCount) \(noun) (+\(totalCount - visibleLimit) more)"
                )
                .font(.system(size: fontSize, weight: .semibold))
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

/// Resolves server-owned `SourceMark` attribution for grouping machinery rows (`#11920` / `#12581`),
/// preferring an explicit `sourceMark` on the visual atom and falling back to the section's
/// hydrated `ContainerHubMember` payload (`FeedEventData` / `FeedFuturesData`). Never infers a source.
enum MachinerySourceMarkResolver11920 {
    static func outcomeMark(
        for outcome: MachineryOutcomeVisual,
        marketId: Int?,
        members: [ContainerHubMember] = []
    ) -> SourceMark? {
        if let direct = outcome.sourceMark, direct.draws {
            return direct
        }
        let targetMarketId = outcome.marketId ?? marketId
        guard let targetMarketId else { return nil }
        for member in members where member.memberId == targetMarketId {
            if case .question(let feed, _) = member.card {
                let matched = feed.topOutcomes?.first(where: {
                    ($0.id > 0 && $0.id == outcome.outcomeId)
                        || $0.name.caseInsensitiveCompare(outcome.name) == .orderedSame
                })
                if let resolved = feed.resolvedSourceMark(for: matched), resolved.draws {
                    return resolved
                }
            }
        }
        return nil
    }

    static func seriesMark(
        for series: MachineryHistorySeries,
        marketId: Int,
        members: [ContainerHubMember] = []
    ) -> SourceMark? {
        if let direct = series.sourceMark, direct.draws {
            return direct
        }
        for member in members where member.memberId == marketId {
            if case .question(let feed, _) = member.card {
                let matched = feed.topOutcomes?.first(where: {
                    ($0.id > 0 && $0.id == series.outcomeId)
                        || $0.name.caseInsensitiveCompare(series.name) == .orderedSame
                })
                if let resolved = feed.resolvedSourceMark(for: matched), resolved.draws {
                    return resolved
                }
            }
        }
        return nil
    }

    static func eventMarks(
        for item: MachineryEventVisualItem,
        members: [ContainerHubMember] = []
    ) -> (away: SourceMark?, home: SourceMark?) {
        let directHome = (item.sourceMark?.draws == true) ? item.sourceMark : nil
        let directAway = (item.awaySourceMark?.draws == true) ? item.awaySourceMark : nil
        if directHome != nil || directAway != nil {
            return (away: directAway, home: directHome)
        }
        for member in members where member.memberId == item.eventId {
            if case .event(let event) = member.card {
                let home = (event.sourceMark?.draws == true) ? event.sourceMark : nil
                let away = (event.awaySourceMark?.draws == true) ? event.awaySourceMark : nil
                if home != nil || away != nil {
                    return (away: away, home: home)
                }
            }
        }
        return (nil, nil)
    }
}

/// Connected straight-line probability trend card (`probability_history_chart` + `mini_chart`).
struct MachineryHistoryChartCardView: View {
    let chart: MachineryHistoryChartItem
    var compact: Bool = false
    var members: [ContainerHubMember] = []

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.timeZone) private var timeZone
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
        if chart.hasMovingSeries {
            chartCardBody
        }
    }

    @ViewBuilder
    private var chartCardBody: some View {
        let spanText = MachineryDateFormatting12288.shortSpan(chart.startIso, chart.endIso)
        let shownSeries = Array(chart.series.prefix(3))
        let seriesHexes = MachineryChartSeriesPalette12288.resolvedHexes(
            for: shownSeries,
            isDark: colorScheme == .dark
        )
        let resolvedStartIso = chart.startIso.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? (shownSeries.compactMap(\.points.first?.t).first ?? "")
            : chart.startIso
        let resolvedEndIso = chart.endIso.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? (shownSeries.compactMap(\.points.last?.t).last ?? "")
            : chart.endIso
        let xAxisLabels = DiscoverCardChartRules13773.axisEndLabels(
            startIso: resolvedStartIso,
            endIso: resolvedEndIso,
            timeZone: timeZone
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
                    let sMark = MachinerySourceMarkResolver11920.seriesMark(
                        for: s,
                        marketId: chart.marketId,
                        members: members
                    )
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Circle()
                            .fill(seriesColor)
                            .frame(width: 8, height: 8)
                        Text(s.name)
                            .font(.system(size: min(metaSize, 18), weight: .medium))
                            .foregroundStyle(secondaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        HStack(alignment: .firstTextBaseline, spacing: 2) {
                            Text("\(s.currentPct)%")
                                .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: true, vertical: false)
                            if let markBtn = SourceMarkButton(
                                sMark,
                                number: Double(s.currentPct) / 100.0,
                                subject: s.name,
                                subtitle: chart.title,
                                numberSize: min(metaSize, 18),
                                compactRow: true
                            ) {
                                markBtn
                            }
                        }
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

            if let xAxisLabels {
                HStack(spacing: 8) {
                    Text(xAxisLabels.start)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                    Spacer(minLength: 6)
                    Text(xAxisLabels.end)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
                .font(.system(size: 10, weight: .medium).monospacedDigit())
                .foregroundStyle(secondaryInk)
                .padding(.leading, 40)
                .accessibilityIdentifier("machinery.historyChart.xAxis")
            }
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

@ViewBuilder
private func machineryCardColumns13417<Item: Identifiable, Card: View>(
    _ items: [Item],
    columnCount: Int,
    spacing: CGFloat = ContainerHubGridLayout13417.spacing,
    @ViewBuilder card: @escaping (Item) -> Card
) -> some View {
    if columnCount <= 1 || items.isEmpty {
        ForEach(items) { item in
            card(item)
        }
    } else {
        LazyMasonryColumns(
            range: 0..<items.count,
            columnCount: columnCount,
            spacing: spacing,
            horizontalAlignment: .leading,
            cardAlignment: .leading
        ) { idx in
            card(items[idx])
        }
    }
}

struct MachinerySectionBlockView: View {
    let visualBlock: MachineryVisualBlock
    let members: [ContainerHubMember]
    var columnCount: Int = 1
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
            MachineryHistoryChartSectionView(items: visualBlock.historyItems, members: members, limit: limit, columnCount: columnCount)
        case .coinFlipMatchups:
            MachineryCoinFlipSectionView(items: visualBlock.eventItems, members: members, limit: limit, columnCount: columnCount)
        case .matchupSlate:
            MachineryMatchupSlateSectionView(
                members: members,
                fallbackItems: visualBlock.eventItems,
                limit: limit,
                columnCount: columnCount
            )
        case .duelBar:
            MachineryDuelBarSectionView(items: visualBlock.marketItems, members: members)
        case .contenderSpotlight:
            MachineryContenderSpotlightSectionView(items: visualBlock.marketItems, members: members, limit: limit)
        case .siblingFieldsGrid:
            MachinerySiblingFieldsSectionView(items: visualBlock.marketItems, members: members, limit: limit, columnCount: columnCount)
        case .benchmarkStrip:
            MachineryBenchmarkStripSectionView(
                items: visualBlock.marketItems,
                members: members,
                limit: limit,
                itemNoun: visualBlock.effectiveItemNoun
            )
        }
    }
}

private struct MachineryHistoryChartSectionView: View {
    let items: [MachineryHistoryChartItem]
    var members: [ContainerHubMember] = []
    let limit: Int
    var columnCount: Int = 1
    @State private var expanded = false

    var body: some View {
        let shown = expanded ? items : Array(items.prefix(limit))
        VStack(alignment: .leading, spacing: 10) {
            machineryCardColumns13417(shown, columnCount: columnCount) { chart in
                MachineryHistoryChartCardView(chart: chart, compact: false, members: members)
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
    var members: [ContainerHubMember] = []
    let limit: Int
    var columnCount: Int = 1
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
            machineryCardColumns13417(shown, columnCount: columnCount) { item in
                let colors = MachineryColorContrast12288.pairHexes(
                    awayHex: item.awayArt?.accentColor,
                    homeHex: item.homeArt?.accentColor,
                    scheme: colorScheme
                )
                let marks = MachinerySourceMarkResolver11920.eventMarks(for: item, members: members)
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
                            let rowHasArt = (item.awayArt?.verifiedURL != nil) || (item.homeArt?.verifiedURL != nil)
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(spacing: 10) {
                                    MachinerySubjectArtView(art: item.awayArt, width: 32, height: 32, reservesWidthWhenEmpty: rowHasArt, subjectName: item.awayShort, defaultSubjectKind: "team")
                                    Text(item.awayShort)
                                        .font(.system(size: min(teamSize, 24), weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Spacer(minLength: 6)
                                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                                        Text("\(item.awayPct)%")
                                            .font(.system(size: min(teamSize, 24), weight: .bold).monospacedDigit())
                                            .foregroundStyle(primaryInk)
                                        if let m = SourceMarkButton(marks.away, number: Double(item.awayPct) / 100.0, subject: item.awayTeam, numberSize: min(teamSize, 24), compactRow: true) {
                                            m
                                        }
                                    }
                                }
                                HStack(spacing: 10) {
                                    MachinerySubjectArtView(art: item.homeArt, width: 32, height: 32, reservesWidthWhenEmpty: rowHasArt, subjectName: item.homeShort, defaultSubjectKind: "team")
                                    Text(item.homeShort)
                                        .font(.system(size: min(teamSize, 24), weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                    Spacer(minLength: 6)
                                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                                        Text("\(item.homePct)%")
                                            .font(.system(size: min(teamSize, 24), weight: .bold).monospacedDigit())
                                            .foregroundStyle(primaryInk)
                                        if let m = SourceMarkButton(marks.home, number: Double(item.homePct) / 100.0, subject: item.homeTeam, numberSize: min(teamSize, 24), compactRow: true) {
                                            m
                                        }
                                    }
                                }
                            }
                        } else {
                            let rowHasArt = (item.awayArt?.verifiedURL != nil) || (item.homeArt?.verifiedURL != nil)
                            HStack(alignment: .center, spacing: 8) {
                                HStack(spacing: 8) {
                                    MachinerySubjectArtView(art: item.awayArt, width: 32, height: 32, reservesWidthWhenEmpty: rowHasArt, subjectName: item.awayShort, defaultSubjectKind: "team")
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.awayShort)
                                            .font(.system(size: min(teamSize, 22), weight: .semibold))
                                            .foregroundStyle(primaryInk)
                                            .fixedSize(horizontal: false, vertical: true)
                                        HStack(alignment: .firstTextBaseline, spacing: 2) {
                                            Text("\(item.awayPct)%")
                                                .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                                                .foregroundStyle(secondaryInk)
                                            if let m = SourceMarkButton(marks.away, number: Double(item.awayPct) / 100.0, subject: item.awayTeam, numberSize: min(metaSize, 18), compactRow: true) {
                                                m
                                            }
                                        }
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
                                        HStack(alignment: .firstTextBaseline, spacing: 2) {
                                            Text("\(item.homePct)%")
                                                .font(.system(size: min(metaSize, 18), weight: .bold).monospacedDigit())
                                                .foregroundStyle(secondaryInk)
                                            if let m = SourceMarkButton(marks.home, number: Double(item.homePct) / 100.0, subject: item.homeTeam, numberSize: min(metaSize, 18), compactRow: true) {
                                                m
                                            }
                                        }
                                    }
                                    MachinerySubjectArtView(art: item.homeArt, width: 32, height: 32, reservesWidthWhenEmpty: rowHasArt, subjectName: item.homeShort, defaultSubjectKind: "team")
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
    var columnCount: Int = 1
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
                machineryCardColumns13417(shown, columnCount: columnCount) { member in
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
            MachineryCoinFlipSectionView(items: fallbackItems, members: members, limit: limit, columnCount: columnCount)
        }
    }
}

private struct MachineryDuelBarSectionView: View {
    let items: [MachineryMarketVisualItem]
    var members: [ContainerHubMember] = []
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
            let colors = MachineryColorContrast12288.pairHexes(
                awayHex: left.art?.accentColor,
                homeHex: right.art?.accentColor,
                scheme: colorScheme
            )
            let leftColor = Color(hex: colors.away)
            let rightColor = Color(hex: colors.home)
            let leftMark = MachinerySourceMarkResolver11920.outcomeMark(for: left, marketId: lead.marketId, members: members)
            let rightMark = MachinerySourceMarkResolver11920.outcomeMark(for: right, marketId: lead.marketId, members: members)

            NavigationLink(value: Route.futuresDetail(id: lead.marketId)) {
                VStack(alignment: .leading, spacing: 12) {
                    if dynamicTypeSize >= .xxxLarge {
                        VStack(alignment: .leading, spacing: 10) {
                            duelSideRow(outcome: left, dotColor: leftColor, mark: leftMark, marketTitle: lead.title)
                            duelSideRow(outcome: right, dotColor: rightColor, mark: rightMark, marketTitle: lead.title)
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
                                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                                        Text(left.probabilityLabel)
                                            .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                                            .foregroundStyle(primaryInk)
                                        if let m = SourceMarkButton(leftMark, number: left.probability, subject: left.name, subtitle: lead.title, numberSize: min(nameSize, 20), compactRow: true) {
                                            m
                                        }
                                    }
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
                                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                                        Text(right.probabilityLabel)
                                            .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                                            .foregroundStyle(primaryInk)
                                        if let m = SourceMarkButton(rightMark, number: right.probability, subject: right.name, subtitle: lead.title, numberSize: min(nameSize, 20), compactRow: true) {
                                            m
                                        }
                                    }
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
    private func duelSideRow(outcome: MachineryOutcomeVisual, dotColor: Color, mark: SourceMark?, marketTitle: String) -> some View {
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
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(outcome.probabilityLabel)
                    .font(.system(size: min(pctSize, 28), weight: .heavy).monospacedDigit())
                    .foregroundStyle(primaryInk)
                if let m = SourceMarkButton(mark, number: outcome.probability, subject: outcome.name, subtitle: marketTitle, numberSize: min(nameSize, 20), compactRow: true) {
                    m
                }
            }
        }
    }
}

private struct MachineryContenderSpotlightSectionView: View {
    let items: [MachineryMarketVisualItem]
    var members: [ContainerHubMember] = []
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
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(o.probabilityLabel)
                                        .font(.system(size: min(labelSize, 22), weight: isFav ? .heavy : .semibold).monospacedDigit())
                                        .foregroundStyle(isFav ? primaryInk : secondaryInk)
                                    if let m = SourceMarkButton(
                                        MachinerySourceMarkResolver11920.outcomeMark(for: o, marketId: lead.marketId, members: members),
                                        number: o.probability,
                                        subject: o.name,
                                        subtitle: lead.title,
                                        numberSize: min(labelSize, 20),
                                        compactRow: true
                                    ) {
                                        m
                                    }
                                }
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
                                marketId: lead.marketId,
                                marketTitle: lead.title,
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
                            columnSpotlightTile(
                                rank: idx + 1,
                                outcome: o,
                                marketId: lead.marketId,
                                marketTitle: lead.title,
                                reservesArtSlot: topHasArt,
                                listUsesPoster: topUsesPoster
                            )
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
                                    emptySlotIsPoster: chasersUsePoster,
                                    subjectName: o.name
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
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(o.probabilityLabel)
                                        .font(.system(size: min(labelSize, 22), weight: .bold).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                    if let m = SourceMarkButton(
                                        MachinerySourceMarkResolver11920.outcomeMark(for: o, marketId: lead.marketId, members: members),
                                        number: o.probability,
                                        subject: o.name,
                                        subtitle: lead.title,
                                        numberSize: min(labelSize, 20),
                                        compactRow: true
                                    ) {
                                        m
                                    }
                                }
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

    private func columnSpotlightTile(
        rank: Int,
        outcome: MachineryOutcomeVisual,
        marketId: Int,
        marketTitle: String,
        reservesArtSlot: Bool = false,
        listUsesPoster: Bool = false
    ) -> some View {
        let barColor = MachineryColorContrast12288.singleAccent(outcome.art?.accentColor, scheme: colorScheme)
        let resolvedMark = MachinerySourceMarkResolver11920.outcomeMark(for: outcome, marketId: marketId, members: members)
        let rowIsPoster = outcome.art?.isPoster ?? listUsesPoster
        return VStack(spacing: 6) {
            HStack(spacing: 2) {
                Text("#\(rank)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(secondaryInk)
                Spacer(minLength: 2)
                Text(outcome.probabilityLabel)
                    .font(.system(size: min(labelSize, 20), weight: .heavy).monospacedDigit())
                    .foregroundStyle(primaryInk)
                if let m = SourceMarkButton(resolvedMark, number: outcome.probability, subject: outcome.name, subtitle: marketTitle, numberSize: 13, compactRow: true) {
                    m
                }
            }

            MachinerySubjectArtView(
                art: outcome.art,
                width: listUsesPoster ? 44 : 48,
                height: rowIsPoster ? 64 : 48,
                reservesWidthWhenEmpty: reservesArtSlot,
                emptySlotIsPoster: listUsesPoster,
                subjectName: outcome.name
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
        marketId: Int,
        marketTitle: String,
        reservesArtSlot: Bool,
        listUsesPoster: Bool
    ) -> some View {
        let rowIsPoster = outcome.art?.isPoster ?? listUsesPoster
        let resolvedMark = MachinerySourceMarkResolver11920.outcomeMark(for: outcome, marketId: marketId, members: members)
        return HStack(spacing: 12) {
            MachinerySubjectArtView(
                art: outcome.art,
                width: listUsesPoster ? 44 : 48,
                height: rowIsPoster ? 64 : 48,
                reservesWidthWhenEmpty: reservesArtSlot,
                emptySlotIsPoster: listUsesPoster,
                subjectName: outcome.name
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
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(outcome.probabilityLabel)
                    .font(.system(size: min(labelSize, 24), weight: .heavy).monospacedDigit())
                    .foregroundStyle(primaryInk)
                if let m = SourceMarkButton(resolvedMark, number: outcome.probability, subject: outcome.name, subtitle: marketTitle, numberSize: min(labelSize, 20), compactRow: true) {
                    m
                }
            }
        }
        .padding(12)
        .background(cardBgColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
    }
}

/// Shared row layout used by both `MachinerySiblingFieldsSectionView` and
/// `MachineryDiscoverCardView.outcomeRowsBody` so division-race (`441: A` / `#13777`)
/// live, `<1%`, `No recent probability`, and `Eliminated` states render identically.
private struct MachineryOutcomeBarRow441A: View {
    let outcome: MachineryOutcomeVisual
    let scaleOrdered: Bool
    let isFav: Bool
    let artWidth: CGFloat
    let artHeight: CGFloat
    let listHasArt: Bool
    let listUsesPoster: Bool
    let rowFontSize: CGFloat
    let rowSpacing: CGFloat
    let barColor: Color
    let trackBgColor: Color
    let primaryInk: Color
    let secondaryInk: Color
    let colorScheme: ColorScheme
    let sourceMark: SourceMark?
    let marketTitle: String

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.discoverNarrowTwoColumn13914) private var isNarrowTwoColumn

    private var progressBar: some View {
        let display = outcome.display441A
        let fillColor: Color = display.state == .subOnePercent
            ? (colorScheme == .dark ? Color.white.opacity(0.32) : DS.textMuted.opacity(0.65))
            : barColor
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(trackBgColor)
                if display.barWidthPercent > 0 {
                    let frac = CGFloat(min(100, display.barWidthPercent)) / 100.0
                    let width = display.state == .subOnePercent
                        ? max(4, geo.size.width * 0.02)
                        : max(4, geo.size.width * frac)
                    Capsule()
                        .fill(fillColor)
                        .frame(width: min(geo.size.width, width))
                }
            }
        }
        .frame(height: 6)
    }

    var body: some View {
        let display = outcome.display441A
        let isMuted = display.muted
        let isUnpricedOrOut = display.state == .eliminated || display.state == .noRecentProbability
        let artOpacity: Double = isUnpricedOrOut ? 0.45 : (display.state == .subOnePercent ? 0.75 : 1.0)
        let labelColor = isMuted ? secondaryInk : (isFav ? primaryInk : secondaryInk)
        let titleWeight: Font.Weight = isMuted ? .medium : (isFav ? .semibold : .medium)
        let valueWeight: Font.Weight = isMuted ? .medium : (isFav ? .bold : .semibold)

        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: max(rowSpacing, 6)) {
                Text(outcome.name)
                    .font(.system(size: rowFontSize, weight: titleWeight))
                    .foregroundStyle(labelColor)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .center, spacing: 8) {
                    if !scaleOrdered {
                        MachinerySubjectArtView(
                            art: outcome.art,
                            width: artWidth,
                            height: artHeight,
                            reservesWidthWhenEmpty: listHasArt,
                            emptySlotIsPoster: listUsesPoster,
                            subjectName: outcome.name
                        )
                        .saturation(isUnpricedOrOut ? 0 : 1)
                        .opacity(artOpacity)
                    }
                    Text(display.label)
                        .font(.system(size: rowFontSize, weight: valueWeight).monospacedDigit())
                        .foregroundStyle(labelColor)
                        .fixedSize(horizontal: false, vertical: true)
                    if !isUnpricedOrOut,
                       outcome.servedProbability != nil,
                       let m = SourceMarkButton(
                           sourceMark,
                           number: outcome.servedProbability,
                           subject: outcome.name,
                           subtitle: marketTitle,
                           numberSize: min(rowFontSize, 22),
                           compactRow: true
                       ) {
                        m
                    }
                }
                progressBar
            }
        } else {
            HStack(alignment: .center, spacing: 10) {
                if !scaleOrdered {
                    MachinerySubjectArtView(
                        art: outcome.art,
                        width: artWidth,
                        height: artHeight,
                        reservesWidthWhenEmpty: listHasArt,
                        emptySlotIsPoster: listUsesPoster,
                        subjectName: outcome.name
                    )
                    .saturation(isUnpricedOrOut ? 0 : 1)
                    .opacity(artOpacity)
                }
                VStack(alignment: .leading, spacing: rowSpacing) {
                    if isNarrowTwoColumn && isUnpricedOrOut {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(outcome.name)
                                .font(.system(size: rowFontSize, weight: titleWeight))
                                .foregroundStyle(labelColor)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(display.label)
                                .font(.system(size: rowFontSize, weight: valueWeight))
                                .foregroundStyle(labelColor)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    } else {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(outcome.name)
                                .font(.system(size: rowFontSize, weight: titleWeight))
                                .foregroundStyle(labelColor)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 6)
                            HStack(alignment: .firstTextBaseline, spacing: 3) {
                                Text(display.label)
                                    .font(.system(size: rowFontSize, weight: valueWeight).monospacedDigit())
                                    .foregroundStyle(labelColor)
                                    .lineLimit(1)
                                    .fixedSize(horizontal: true, vertical: false)
                                if !isUnpricedOrOut,
                                   outcome.servedProbability != nil,
                                   let m = SourceMarkButton(
                                       sourceMark,
                                       number: outcome.servedProbability,
                                       subject: outcome.name,
                                       subtitle: marketTitle,
                                       numberSize: min(rowFontSize, 18),
                                       compactRow: true
                                   ) {
                                    m
                                }
                            }
                        }
                    }
                    progressBar
                }
            }
        }
    }
}

private struct MachinerySiblingFieldsSectionView: View {
    let items: [MachineryMarketVisualItem]
    var members: [ContainerHubMember] = []
    let limit: Int
    var columnCount: Int = 1
    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @ScaledMetric(relativeTo: .title) private var compactTitleSize: CGFloat = 14
    @ScaledMetric(relativeTo: .title) private var compactRowSize: CGFloat = 13
    @ScaledMetric(relativeTo: .headline) private var regularTitleSize: CGFloat = 14
    @ScaledMetric(relativeTo: .headline) private var regularRowSize: CGFloat = 13

    private var titleSize: CGFloat {
        horizontalSizeClass == .regular ? regularTitleSize : compactTitleSize
    }

    private var rowSize: CGFloat {
        horizontalSizeClass == .regular ? regularRowSize : compactRowSize
    }

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
            machineryCardColumns13417(shown, columnCount: columnCount) { market in
                let scaleOrd = market.effectiveScaleOrdered
                let shownOutcomes = Array(market.displayOutcomes.prefix(4))
                let maxPct = shownOutcomes.map(\.renderedPercent).max() ?? 0
                let listHasArt = !scaleOrd && shownOutcomes.contains { $0.art?.verifiedURL != nil }
                let listUsesPoster = shownOutcomes.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }

                NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .top : .firstTextBaseline, spacing: 4) {
                            Text(market.title)
                                .font(.system(size: titleSize, weight: .bold))
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 4)
                            Image(systemName: "chevron.right")
                                .font(.system(size: min(titleSize * 0.45, 16), weight: .semibold))
                                .foregroundStyle(secondaryInk)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(shownOutcomes) { o in
                                let display = o.display441A
                                let isFav = !scaleOrd
                                    ? display.state == .live
                                    : ((market.leaderOutcomeId != nil && o.outcomeId == market.leaderOutcomeId)
                                        || (market.leaderOutcomeId == nil && o.renderedPercent == maxPct))
                                let barColor: Color = {
                                    if scaleOrd {
                                        return isFav ? DS.emerald : Color.gray.opacity(0.6)
                                    }
                                    return MachineryColorContrast12288.singleAccent(o.art?.accentColor, scheme: colorScheme)
                                }()
                                let rowIsPoster = o.art?.isPoster ?? listUsesPoster

                                MachineryOutcomeBarRow441A(
                                    outcome: o,
                                    scaleOrdered: scaleOrd,
                                    isFav: isFav,
                                    artWidth: 28,
                                    artHeight: rowIsPoster ? 38 : 28,
                                    listHasArt: listHasArt,
                                    listUsesPoster: true,
                                    rowFontSize: rowSize,
                                    rowSpacing: 4,
                                    barColor: barColor,
                                    trackBgColor: trackBgColor,
                                    primaryInk: primaryInk,
                                    secondaryInk: secondaryInk,
                                    colorScheme: colorScheme,
                                    sourceMark: MachinerySourceMarkResolver11920.outcomeMark(for: o, marketId: market.marketId, members: members),
                                    marketTitle: market.title
                                )
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
    var members: [ContainerHubMember] = []
    let limit: Int
    var itemNoun: String = "markets"
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
                        let yesMark = MachinerySourceMarkResolver11920.outcomeMark(for: yes, marketId: market.marketId, members: members)
                        NavigationLink(value: Route.futuresDetail(id: market.marketId)) {
                            HStack(alignment: .center, spacing: 10) {
                                let benchSubjectName = ["yes", "no"].contains(yes.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
                                    ? market.title
                                    : yes.name
                                MachinerySubjectArtView(
                                    art: yes.art,
                                    width: 28,
                                    height: 28,
                                    reservesWidthWhenEmpty: listHasArt,
                                    subjectName: benchSubjectName
                                )
                                Text(market.title)
                                    .font(.system(size: min(rowSize, 21), weight: .medium))
                                    .foregroundStyle(primaryInk)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                HStack(alignment: .center, spacing: 3) {
                                    Text(yes.probabilityLabel)
                                        .font(.system(size: min(rowSize, 21), weight: .bold).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(badgeBgColor, in: RoundedRectangle(cornerRadius: 6))
                                    if let m = SourceMarkButton(yesMark, number: yes.probability, subject: market.title, numberSize: min(rowSize, 18), compactRow: true) {
                                        m
                                    }
                                }
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
                noun: itemNoun,
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
                    containerDestination: (card.slug, card.title),
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
            Text(card.openContainerCallToAction)
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
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages
    @Environment(\.discoverCardLikeAction420D) private var likeAction
    @ScaledMetric(relativeTo: .headline) private var kickerSize: CGFloat = 11
    @ScaledMetric(relativeTo: .headline) private var titleSize: CGFloat = 17
    @ScaledMetric(relativeTo: .headline) private var rowSize: CGFloat = 14
    @ScaledMetric(relativeTo: .headline) private var subSize: CGFloat = 12
    @ScaledMetric(relativeTo: .title2) private var duelPctSize: CGFloat = 21

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
                    .font(.system(size: kickerSize, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
                    .fixedSize(horizontal: false, vertical: true)

                Text(card.title)
                    .font(.system(size: titleSize, weight: .bold))
                    .foregroundStyle(primaryInk)
                    .fixedSize(horizontal: false, vertical: true)

                if !card.subtitle.isEmpty {
                    Text(card.subtitle)
                        .font(.system(size: subSize))
                        .foregroundStyle(secondaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let imageURL = card.verifiedImageURL {
                cardHeroImage(url: imageURL)
            } else if let miniChart = card.miniChart {
                MachineryHistoryChartCardView(chart: miniChart, compact: true)
            }

            if card.isEventCard {
                eventRowsBody
            } else if !card.isDivisionRaceCard441A, card.formId == .duelBar, card.outcomeRows.count >= 2 {
                duelBarBody
            } else {
                outcomeRowsBody
            }

            VStack(alignment: .leading, spacing: 4) {
                Rectangle().fill(borderColor).frame(height: 1).padding(.bottom, 4)
                if !card.footer.isEmpty {
                    Text(card.footer)
                        .font(.system(size: subSize))
                        .foregroundStyle(secondaryInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .firstTextBaseline : .center, spacing: 4) {
                    Text(card.openContainerCallToAction)
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "chevron.right")
                        .font(.system(size: min(subSize * 0.65, 22), weight: .bold))
                }
                .font(.system(size: subSize, weight: .semibold))
                .foregroundStyle(colorScheme == .dark ? DS.emerald : DS.greenReadable)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)

        VStack(spacing: 0) {
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

            if let likeAction {
                DiscoverCardActionBar420D(actions: likeAction, topDivider: true, horizontalPadding: 16, verticalPadding: 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardBgColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(borderColor, lineWidth: 1))
        .shadow(color: .black.opacity(colorScheme == .dark ? 0.22 : 0.04), radius: 6, x: 0, y: 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("discover.machineryCard.\(card.slug)")
    }

    @ViewBuilder
    private func cardHeroImage(url: URL) -> some View {
        if let preloaded = preloadedImages[url.absoluteString] {
            fittedCardHeroFrame(platformImage(preloaded))
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(card.imageAlt ?? card.title)
                .accessibilityIdentifier("machinery.card.heroImage.\(card.slug)")
        } else {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    fittedCardHeroFrame(image)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(card.imageAlt ?? card.title)
                        .accessibilityIdentifier("machinery.card.heroImage.\(card.slug)")
                case .empty:
                    fittedCardHeroFrame(nil)
                        .accessibilityHidden(true)
                case .failure:
                    EmptyView()
                @unknown default:
                    EmptyView()
                }
            }
        }
    }

    private func fittedCardHeroFrame(_ image: Image?) -> some View {
        HeroAspectRatioLayout13304(ratio: 2) {
            ZStack {
                trackBgColor
                if let image {
                    image
                        .resizable()
                        .scaledToFill()
                }
            }
            .clipped()
        }
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(borderColor, lineWidth: 1)
        )
    }

    private func platformImage(_ img: PairedPlatformImage) -> Image {
        #if canImport(UIKit)
        return Image(uiImage: img)
        #elseif canImport(AppKit)
        return Image(nsImage: img)
        #endif
    }

    private var eventRowsBody: some View {
        let rows = Array(card.eventRows.prefix(3))
        return Group {
            if dynamicTypeSize >= .xxxLarge {
                stackedEventRowsList(rows)
            } else {
                // #13501 — keep short pro matchups on one compact line when every
                // row fits unwrapped; fall back uniformly to stacked team rows when
                // longer names (e.g. "St. Bonaventure" at "Appalachian St") would squeeze.
                ViewThatFits(in: .horizontal) {
                    singleLineEventRowsList(rows)
                    stackedEventRowsList(rows)
                }
            }
        }
    }

    private func singleLineEventRowsList(_ rows: [MachineryEventVisualItem]) -> some View {
        let listHasArt = rows.contains { ($0.awayArt?.verifiedURL != nil) || ($0.homeArt?.verifiedURL != nil) }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { idx, r in
                HStack(alignment: .center, spacing: 8) {
                    HStack(spacing: 6) {
                        MachinerySubjectArtView(art: r.awayArt, width: 26, height: 26, reservesWidthWhenEmpty: listHasArt, subjectName: r.awayShort, defaultSubjectKind: "team")
                        Text(r.awayShort)
                            .font(.system(size: min(rowSize, 20), weight: .semibold))
                            .foregroundStyle(primaryInk)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        Text("at")
                            .font(.system(size: min(subSize, 17)))
                            .foregroundStyle(secondaryInk)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        MachinerySubjectArtView(art: r.homeArt, width: 26, height: 26, reservesWidthWhenEmpty: listHasArt, subjectName: r.homeShort, defaultSubjectKind: "team")
                        Text(r.homeShort)
                            .font(.system(size: min(rowSize, 20), weight: .semibold))
                            .foregroundStyle(primaryInk)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .fixedSize(horizontal: true, vertical: false)

                    Spacer(minLength: 8)

                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text("\(r.awayPct)%–\(r.homePct)%")
                            .font(.system(size: min(rowSize, 20), weight: .bold).monospacedDigit())
                            .foregroundStyle(primaryInk)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                        if let m = SourceMarkButton(r.sourceMark ?? r.awaySourceMark, number: Double(r.homePct) / 100.0, subject: "\(r.awayShort) at \(r.homeShort)", numberSize: min(rowSize, 18), compactRow: true) {
                            m
                        }
                    }
                    .fixedSize(horizontal: true, vertical: false)
                }
                .padding(.vertical, 8)
                if idx < rows.count - 1 {
                    Rectangle().fill(borderColor).frame(height: 1)
                }
            }
        }
    }

    private func stackedEventRowsList(_ rows: [MachineryEventVisualItem]) -> some View {
        let listHasArt = rows.contains { ($0.awayArt?.verifiedURL != nil) || ($0.homeArt?.verifiedURL != nil) }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { idx, r in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(alignment: .center, spacing: 8) {
                        MachinerySubjectArtView(art: r.awayArt, width: 24, height: 24, reservesWidthWhenEmpty: listHasArt, subjectName: r.awayShort, defaultSubjectKind: "team")
                        Text(r.awayShort)
                            .font(.system(size: rowSize, weight: .semibold))
                            .foregroundStyle(primaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        HStack(alignment: .firstTextBaseline, spacing: 3) {
                            Text("\(r.awayPct)%")
                                .font(.system(size: rowSize, weight: .bold).monospacedDigit())
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: true, vertical: false)
                            if let m = SourceMarkButton(r.awaySourceMark, number: Double(r.awayPct) / 100.0, subject: r.awayShort, numberSize: min(rowSize, 22), compactRow: true) {
                                m
                            }
                        }
                    }
                    HStack(alignment: .center, spacing: 8) {
                        MachinerySubjectArtView(art: r.homeArt, width: 24, height: 24, reservesWidthWhenEmpty: listHasArt, subjectName: r.homeShort, defaultSubjectKind: "team")
                        (Text("at ").foregroundStyle(secondaryInk) + Text(r.homeShort).foregroundStyle(primaryInk))
                            .font(.system(size: rowSize, weight: .semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        HStack(alignment: .firstTextBaseline, spacing: 3) {
                            Text("\(r.homePct)%")
                                .font(.system(size: rowSize, weight: .bold).monospacedDigit())
                                .foregroundStyle(primaryInk)
                                .fixedSize(horizontal: true, vertical: false)
                            if let m = SourceMarkButton(r.sourceMark, number: Double(r.homePct) / 100.0, subject: r.homeShort, numberSize: min(rowSize, 22), compactRow: true) {
                                m
                            }
                        }
                    }
                }
                .padding(.vertical, 8)
                if idx < rows.count - 1 {
                    Rectangle().fill(borderColor).frame(height: 1)
                }
            }
        }
    }

    private var outcomeRowsBody: some View {
        let rows = card.displayOutcomeRows
        let maxPct = rows.map(\.renderedPercent).max() ?? 0
        let listHasArt = !card.scaleOrdered && rows.contains { $0.art?.verifiedURL != nil }
        let listUsesPoster = rows.contains { $0.art?.verifiedURL != nil && $0.art?.isPoster == true }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(rows.enumerated()), id: \.element.id) { idx, o in
                let display = o.display441A
                let isFav = !card.scaleOrdered ? display.state == .live : (o.renderedPercent == maxPct)
                let barColor: Color = {
                    if card.scaleOrdered {
                        return isFav ? DS.emerald : Color.gray.opacity(0.6)
                    }
                    return MachineryColorContrast12288.singleAccent(o.art?.accentColor, scheme: colorScheme)
                }()
                let rowIsPoster = o.art?.isPoster ?? listUsesPoster

                MachineryOutcomeBarRow441A(
                    outcome: o,
                    scaleOrdered: card.scaleOrdered,
                    isFav: isFav,
                    artWidth: listUsesPoster ? 28 : 32,
                    artHeight: rowIsPoster ? 40 : 32,
                    listHasArt: listHasArt,
                    listUsesPoster: listUsesPoster,
                    rowFontSize: rowSize,
                    rowSpacing: 5,
                    barColor: barColor,
                    trackBgColor: trackBgColor,
                    primaryInk: primaryInk,
                    secondaryInk: secondaryInk,
                    colorScheme: colorScheme,
                    sourceMark: o.sourceMark,
                    marketTitle: card.title
                )
                .padding(.vertical, 8)
                if idx < rows.count - 1 {
                    Rectangle().fill(borderColor).frame(height: 1)
                }
            }
        }
    }

    // MARK: - Pile 7 (`duel_bar` split bar on Discover cards)

    /// Resolves the two primary sides (plus an optional Draw/Tie/Neither middle leg).
    /// When >= 3 rows arrive without an explicit draw/tie/neither row, the top two rows
    /// (`rows[0]` and `rows[1]`) are the two sides and nothing grey is drawn in between.
    static func resolveDuelBarSides(
        _ rawRows: [MachineryOutcomeVisual]
    ) -> (left: MachineryOutcomeVisual, right: MachineryOutcomeVisual, middle: MachineryOutcomeVisual?)? {
        let rows = Array(rawRows.prefix(3))
        guard rows.count >= 2 else { return nil }
        let drawNames: Set<String> = ["tie", "draw", "neither"]
        let midIdx: Int? = rows.count >= 3
            ? rows.firstIndex {
                drawNames.contains($0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
            }
            : nil
        if let midIdx {
            let sides = rows.enumerated().filter { $0.offset != midIdx }.map(\.element)
            guard sides.count >= 2 else { return nil }
            return (left: sides[0], right: sides[1], middle: rows[midIdx])
        }
        return (left: rows[0], right: rows[1], middle: nil)
    }

    @ViewBuilder
    private var duelBarBody: some View {
        if let resolved = Self.resolveDuelBarSides(card.outcomeRows) {
            let left = resolved.left
            let right = resolved.right
            let middle = resolved.middle
            let colors = MachineryColorContrast12288.pairHexes(
                awayHex: left.art?.accentColor,
                homeHex: right.art?.accentColor,
                scheme: colorScheme
            )
            let leftColor = Color(hex: colors.away)
            let rightColor = Color(hex: colors.home)
            let leftPct = max(0, left.renderedPercent)
            let rightPct = max(0, right.renderedPercent)
            let midPct = max(0, middle?.renderedPercent ?? 0)
            let totalPct = max(1, leftPct + rightPct + midPct)

            VStack(alignment: .leading, spacing: 10) {
                if dynamicTypeSize >= .xxxLarge {
                    VStack(alignment: .leading, spacing: 10) {
                        duelSideRow(outcome: left, dotColor: leftColor)
                        if let middle {
                            duelSideRow(outcome: middle, dotColor: secondaryInk.opacity(0.45))
                        }
                        duelSideRow(outcome: right, dotColor: rightColor)
                    }
                } else {
                    HStack(alignment: .bottom, spacing: 12) {
                        HStack(alignment: .bottom, spacing: 10) {
                            MachinerySubjectArtView(art: left.art, width: 36, height: 36)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    if left.art?.verifiedURL == nil {
                                        Circle().fill(leftColor).frame(width: 9, height: 9)
                                    }
                                    Text(left.name)
                                        .font(.system(size: rowSize, weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(left.probabilityLabel)
                                        .font(.system(size: duelPctSize, weight: .heavy).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                    if let m = SourceMarkButton(left.sourceMark, number: left.probability, subject: left.name, subtitle: card.title, numberSize: min(rowSize, 22), compactRow: true) {
                                        m
                                    }
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .bottomLeading)

                        HStack(alignment: .bottom, spacing: 10) {
                            VStack(alignment: .trailing, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(right.name)
                                        .font(.system(size: rowSize, weight: .semibold))
                                        .foregroundStyle(primaryInk)
                                        .multilineTextAlignment(.trailing)
                                        .fixedSize(horizontal: false, vertical: true)
                                    if right.art?.verifiedURL == nil {
                                        Circle().fill(rightColor).frame(width: 9, height: 9)
                                    }
                                }
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(right.probabilityLabel)
                                        .font(.system(size: duelPctSize, weight: .heavy).monospacedDigit())
                                        .foregroundStyle(primaryInk)
                                    if let m = SourceMarkButton(right.sourceMark, number: right.probability, subject: right.name, subtitle: card.title, numberSize: min(rowSize, 22), compactRow: true) {
                                        m
                                    }
                                }
                            }
                            MachinerySubjectArtView(art: right.art, width: 36, height: 36)
                        }
                        .frame(maxWidth: .infinity, alignment: .bottomTrailing)
                    }
                }

                GeometryReader { geo in
                    let leftFrac = CGFloat(min(94, max(6, Int(round(Double(leftPct) * 100.0 / Double(totalPct)))))) / 100.0
                    let midFrac = middle == nil ? 0 : CGFloat(max(4, Int(round(Double(midPct) * 100.0 / Double(totalPct))))) / 100.0
                    HStack(spacing: 2) {
                        Rectangle()
                            .fill(leftColor)
                            .frame(width: max(8, geo.size.width * leftFrac - 1))
                        if middle != nil {
                            Rectangle()
                                .fill(secondaryInk.opacity(colorScheme == .dark ? 0.42 : 0.28))
                                .frame(width: max(6, geo.size.width * midFrac - 1))
                        }
                        Rectangle()
                            .fill(rightColor)
                            .frame(maxWidth: .infinity)
                    }
                }
                .frame(height: 11)
                .clipShape(Capsule())

                if let middle, !dynamicTypeSize.isAccessibilitySize {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(secondaryInk.opacity(colorScheme == .dark ? 0.42 : 0.28))
                            .frame(width: 7, height: 7)
                        Text("\(middle.name) \(middle.probabilityLabel)")
                            .font(.system(size: subSize, weight: .medium).monospacedDigit())
                            .foregroundStyle(secondaryInk)
                        if let m = SourceMarkButton(middle.sourceMark, number: middle.probability, subject: middle.name, subtitle: card.title, numberSize: min(subSize, 20), compactRow: true) {
                            m
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                }
            }
            .padding(.vertical, 6)
        }
    }

    @ViewBuilder
    private func duelSideRow(outcome: MachineryOutcomeVisual, dotColor: Color) -> some View {
        HStack(spacing: 10) {
            if outcome.art?.verifiedURL != nil {
                MachinerySubjectArtView(art: outcome.art, width: 36, height: 36)
            } else {
                Circle().fill(dotColor).frame(width: 10, height: 10)
            }
            Text(outcome.name)
                .font(.system(size: rowSize, weight: .semibold))
                .foregroundStyle(primaryInk)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 6)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(outcome.probabilityLabel)
                    .font(.system(size: duelPctSize, weight: .heavy).monospacedDigit())
                    .foregroundStyle(primaryInk)
                if let m = SourceMarkButton(outcome.sourceMark, number: outcome.probability, subject: outcome.name, subtitle: card.title, numberSize: min(rowSize, 22), compactRow: true) {
                    m
                }
            }
        }
    }
}
