import SwiftUI

#if canImport(UIKit)
import UIKit
public typealias PairedPlatformImage = UIImage
#elseif canImport(AppKit)
import AppKit
public typealias PairedPlatformImage = NSImage
#endif

// MARK: - Native Grouped Looks on iPhone (#12642 / #12577 / 168-A)
//
// Look 1: `paired_bars_top5_expandable` — Top 5 Dual Bars + 'Show all N' Expander
// Look 2: `podium_and_tiers` — 3-Spot Podium (#2 · #1 Elevated · #3) + Ballot Tiers

enum PairedArtSlotSize: Equatable {
    case xs
    case md
    case lg

    func dimensions(for kind: PairedArtKind) -> (width: CGFloat, height: CGFloat, cornerRadius: CGFloat, isCircle: Bool, initialsSize: CGFloat) {
        switch (kind, self) {
        case (.tmdbPoster, .lg):
            return (56, 80, 6, false, 14)
        case (.tmdbPoster, .md):
            return (40, 56, 6, false, 12)
        case (.tmdbPoster, .xs):
            return (24, 36, 4, false, 10)
        case (.tmdbHeadshot, .lg):
            return (48, 48, 24, true, 14)
        case (.tmdbHeadshot, .md):
            return (40, 40, 20, true, 12)
        case (.tmdbHeadshot, .xs):
            return (24, 24, 12, true, 10)
        case (.espnTeamLogo, .lg):
            return (40, 40, 20, true, 14)
        case (.espnTeamLogo, .md):
            return (32, 32, 16, true, 12)
        case (.espnTeamLogo, .xs):
            return (20, 20, 10, true, 10)
        }
    }
}

/// Renders a contender poster, headshot, or team logo after passing `#7461` (`resolveKidSafeVisualArt`),
/// with a deterministic 2-letter uppercase monogram tile in the exact same slot frame whenever art is
/// absent, blocked, or still loading.
struct PairedArtThumbnailView: View {
    let entry: PairedSubjectEntry
    let size: PairedArtSlotSize
    var preloadedImages: [String: PairedPlatformImage] = [:]

    private var kind: PairedArtKind {
        entry.art?.kind ?? .tmdbPoster
    }

    private var spec: (width: CGFloat, height: CGFloat, cornerRadius: CGFloat, isCircle: Bool, initialsSize: CGFloat) {
        size.dimensions(for: kind)
    }

    var body: some View {
        let safeURL = PairedMetricPresentation.resolveKidSafeVisualArt(entry)
        Group {
            if let safeURL, let preloaded = preloadedImages[safeURL.absoluteString] {
                renderedImage(platformImage(preloaded))
            } else if let safeURL {
                AsyncImage(url: safeURL) { phase in
                    switch phase {
                    case .success(let image):
                        renderedImage(image)
                    default:
                        monogramTile
                    }
                }
            } else {
                monogramTile
            }
        }
        .frame(width: spec.width, height: spec.height)
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func renderedImage(_ image: Image) -> some View {
        if kind == .espnTeamLogo {
            image
                .resizable()
                .scaledToFit()
                .padding(2)
                .frame(width: spec.width, height: spec.height)
                .background(DS.trackBg)
                .clipShape(Circle())
                .overlay(Circle().stroke(DS.border, lineWidth: 1))
        } else if spec.isCircle {
            image
                .resizable()
                .scaledToFill()
                .frame(width: spec.width, height: spec.height)
                .background(DS.trackBg)
                .clipShape(Circle())
                .overlay(Circle().stroke(DS.border, lineWidth: 1))
        } else {
            image
                .resizable()
                .scaledToFill()
                .frame(width: spec.width, height: spec.height)
                .background(DS.trackBg)
                .clipShape(RoundedRectangle(cornerRadius: spec.cornerRadius))
                .overlay(RoundedRectangle(cornerRadius: spec.cornerRadius).stroke(DS.border, lineWidth: 1))
        }
    }

    private var monogramTile: some View {
        let text = Text(PairedMetricPresentation.initials(for: entry.subject))
            .font(.system(size: spec.initialsSize, weight: .bold))
            .foregroundStyle(DS.textSecondaryReadable)
            .lineLimit(1)
            .minimumScaleFactor(0.75)

        return Group {
            if spec.isCircle {
                ZStack {
                    Circle().fill(DS.trackBg)
                    text
                }
                .frame(width: spec.width, height: spec.height)
                .overlay(Circle().stroke(DS.border, lineWidth: 1))
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: spec.cornerRadius).fill(DS.trackBg)
                    text
                }
                .frame(width: spec.width, height: spec.height)
                .overlay(RoundedRectangle(cornerRadius: spec.cornerRadius).stroke(DS.border, lineWidth: 1))
            }
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

/// Official unmodified TMDB `blue_short` mark (`85 × 11 pt` in a bordered badge linking to `themoviedb.org`)
/// paired with the required attribution sentence whenever any contender uses TMDB art.
struct PairedTMDBAttributionFooter: View {
    let metricSet: PairedMetricSet

    init(set: PairedMetricSet) {
        self.metricSet = set
    }

    var body: some View {
        if metricSet.usesTMDBArt {
            HStack(alignment: .center, spacing: 6) {
                Link(destination: PairedMetricPresentation.tmdbAttributionURL) {
                    Image("TMDBLogoShort")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 85, height: 11)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(DS.trackBg)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(DS.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("The Movie Database (TMDB)")

                Text(PairedMetricPresentation.tmdbAttributionLine)
                    .font(.system(size: 11))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// Subtle proportional bar-chart fill behind a percentage number box (`94%` almost full,
/// `36%` about a third full) across both winning grouped-card looks (`#12675` / `#12642`).
struct PairedQuietNumberBox<Label: View>: View {
    let fraction: Double
    let isPrimaryStage: Bool
    var trackColor: Color = DS.trackBg
    var fixedWidth: CGFloat? = nil
    var expandToFillWidth: Bool = false
    var contentAlignment: Alignment = .center
    var cornerRadius: CGFloat = 5
    var horizontalPadding: CGFloat = 6
    var verticalPadding: CGFloat = 3
    @ViewBuilder let label: () -> Label

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var clampedFraction: CGFloat {
        CGFloat(min(1.0, max(0.0, fraction)))
    }

    private var fillTint: Color {
        isPrimaryStage
            ? DS.emerald.opacity(0.20)
            : DS.textSecondary.opacity(0.16)
    }

    var body: some View {
        let resolvedWidth: CGFloat? = dynamicTypeSize.isAccessibilitySize ? nil : fixedWidth
        label()
            .padding(.horizontal, horizontalPadding)
            .padding(.vertical, verticalPadding)
            .frame(
                width: resolvedWidth,
                alignment: contentAlignment
            )
            .frame(
                maxWidth: expandToFillWidth ? .infinity : nil,
                alignment: contentAlignment
            )
            .background {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        trackColor
                        if clampedFraction > 0 {
                            Rectangle()
                                .fill(fillTint)
                                .frame(width: max(2, geo.size.width * clampedFraction))
                        }
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(DS.border, lineWidth: 1)
            )
    }
}

/// Entry view rendering either Look 1 (`paired_bars_top5_expandable`) or Look 2 (`podium_and_tiers`).
struct DiscoverPairedMetricCardView: View {
    let metricSet: PairedMetricSet
    let form: PairedVisualFormId
    var initialExpanded: Bool = false
    var preloadedImages: [String: PairedPlatformImage] = [:]
    var onOpenMarket: ((Int) -> Void)? = nil

    @State private var expanded: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(
        set: PairedMetricSet,
        form: PairedVisualFormId? = nil,
        initialExpanded: Bool = false,
        preloadedImages: [String: PairedPlatformImage] = [:],
        onOpenMarket: ((Int) -> Void)? = nil
    ) {
        self.metricSet = set
        self.form = form ?? PairedMetricPresentation.resolvedForm(for: set)
        self.initialExpanded = initialExpanded
        self.preloadedImages = preloadedImages
        self.onOpenMarket = onOpenMarket
        self._expanded = State(initialValue: initialExpanded)
    }

    private var effectiveForm: PairedVisualFormId {
        if form == .podiumAndTiers && metricSet.entries.count < 3 {
            return .pairedBarsTop5Expandable
        }
        return form
    }

    private var sortedEntries: [PairedSubjectEntry] {
        PairedMetricPresentation.sortPairedEntries(metricSet.entries)
    }

    private var cleanSubtitle: String {
        PairedMetricPresentation.formatCardFaceSubtitle(metricSet.subtitle)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerBlock

            switch effectiveForm {
            case .pairedBarsTop5Expandable:
                pairedBarsBody
            case .podiumAndTiers:
                podiumAndTiersBody
            }

            footerBlock
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 1))
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("discover.pairedMetric.\(effectiveForm.rawValue).\(metricSet.setId)")
    }

    // MARK: - Shared Header & Footer

    private var headerBlock: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(metricSet.kicker.uppercased())
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text("\(metricSet.stage1Label) · \(metricSet.stage2Label)".uppercased())
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .multilineTextAlignment(.trailing)
            }

            Text(metricSet.title)
                .font(.system(size: 17, weight: .semibold))
                .lineSpacing(2)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)

            if !cleanSubtitle.isEmpty {
                Text(cleanSubtitle)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 2)
            }
        }
    }

    private var footerBlock: some View {
        let showsOrderingFooter = !PairedMetricPresentation.subtitleStatesOrdering(cleanSubtitle)
        let showsTMDBFooter = metricSet.usesTMDBArt
        return Group {
            if showsOrderingFooter || showsTMDBFooter {
                VStack(alignment: .leading, spacing: 6) {
                    Rectangle()
                        .fill(DS.border)
                        .frame(height: 1)
                        .padding(.bottom, 2)

                    if showsOrderingFooter {
                        Text("Sorted by \(metricSet.stage2Label.lowercased()) %, ties broken by \(metricSet.stage1Label.lowercased()) %")
                            .font(.system(size: 11, weight: .regular))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    PairedTMDBAttributionFooter(set: metricSet)
                }
                .padding(.top, 12)
            }
        }
    }

    // MARK: - Look 1: `paired_bars_top5_expandable`

    private var anyStage1Settled: Bool {
        metricSet.entries.contains { $0.stage1SettledState != nil }
    }

    private var stageLabelWidth: CGFloat {
        let maxChars = max(metricSet.stage1Label.count, metricSet.stage2Label.count)
        return maxChars > 10 ? 86 : 76
    }

    private var pairedBarsBody: some View {
        let visible = expanded ? sortedEntries : Array(sortedEntries.prefix(5))
        return VStack(alignment: .leading, spacing: 0) {
            // Legend strip
            HStack(spacing: 16) {
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(DS.textSecondary)
                        .frame(width: 10, height: 10)
                    Text(anyStage1Settled ? "\(metricSet.stage1Label) (✓ / ✗ settled)" : "\(metricSet.stage1Label) %")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(DS.textPrimary)
                }
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(DS.emerald)
                        .frame(width: 10, height: 10)
                    Text("\(metricSet.stage2Label) %")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(DS.textPrimary)
                }
                Spacer(minLength: 0)
            }
            .padding(.top, 12)
            .padding(.bottom, 8)
            .overlay(alignment: .bottom) {
                Rectangle().fill(DS.border).frame(height: 1)
            }

            // Contender rows
            ForEach(Array(visible.enumerated()), id: \.element.id) { idx, entry in
                dualBarRow(entry: entry)
                    .padding(.vertical, 10)
                if idx < visible.count - 1 {
                    Rectangle().fill(DS.border).frame(height: 1)
                }
            }

            // Expander button
            if let copy = PairedMetricPresentation.expanderCopy(
                sortedEntries: sortedEntries,
                set: metricSet,
                expanded: expanded
            ) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        expanded.toggle()
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(copy.primary)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        if let notice = copy.unpricedNotice {
                            Text(notice)
                                .font(.system(size: 12, weight: .regular))
                                .foregroundStyle(DS.textSecondaryReadable)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(DS.trackBg)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(DS.border, lineWidth: 1))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.top, 10)
                .accessibilityIdentifier("discover.pairedMetric.expander")
            }
        }
    }

    @ViewBuilder
    private func dualBarRow(entry: PairedSubjectEntry) -> some View {
        let s1 = PairedMetricPresentation.formatStage1Display(entry: entry, set: metricSet)
        let s2 = PairedMetricPresentation.formatStage2Display(entry: entry, set: metricSet)
        let rowContent = HStack(alignment: .center, spacing: 12) {
            PairedArtThumbnailView(entry: entry, size: .md, preloadedImages: preloadedImages)

            VStack(alignment: .leading, spacing: 0) {
                Text(entry.subject)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                if !entry.detail.isEmpty {
                    Text(entry.detail)
                        .font(.system(size: 12, weight: .regular))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                }

                VStack(alignment: .leading, spacing: 6) {
                    stage1BarLine(s1: s1)
                    stage2BarLine(s2: s2)
                }
                .padding(.top, 6)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        if let onOpenMarket {
            let targetMarketId = entry.stage2Probability != nil ? entry.stage2MarketId : entry.stage1MarketId
            Button {
                if targetMarketId > 0 {
                    onOpenMarket(targetMarketId)
                }
            } label: {
                rowContent.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            rowContent
        }
    }

    @ViewBuilder
    private func stage1BarLine(s1: FormattedPairedStageDisplay) -> some View {
        HStack(alignment: .center, spacing: 8) {
            Text(metricSet.stage1Label)
                .font(.system(size: 12, weight: .regular))
                .foregroundStyle(DS.textSecondary)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : stageLabelWidth, alignment: .leading)
                .lineLimit(1)

            switch s1.kind {
            case .percent:
                let pct = CGFloat(s1.percent ?? 1)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(DS.trackBg)
                        Capsule()
                            .fill(DS.textSecondary)
                            .frame(width: max(geo.size.width * 0.04, geo.size.width * min(pct / 100.0, 1.0)))
                    }
                }
                .frame(height: 8)

                PairedQuietNumberBox(
                    fraction: PairedMetricPresentation.quietFillFraction(for: s1) ?? 0,
                    isPrimaryStage: false,
                    trackColor: DS.trackBg,
                    fixedWidth: 48,
                    contentAlignment: .trailing,
                    horizontalPadding: 6,
                    verticalPadding: 2.5
                ) {
                    Text(s1.label)
                        .font(.system(size: 12, weight: .semibold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(1)
                }

            case .tick:
                Text(s1.label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(DS.greenReadable)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(DS.trackBg)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                Spacer(minLength: 0)

            case .cross:
                Text(s1.label)
                    .font(.system(size: 12, weight: .medium))
                    .strikethrough()
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(DS.trackBg)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                Spacer(minLength: 4)
                if let sublabel = s1.sublabel {
                    Text(sublabel)
                        .font(.system(size: 12, weight: .regular).monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                }

            case .missing:
                Text(s1.label)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(DS.trackBg)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(DS.border, lineWidth: 1))
                Spacer(minLength: 0)
            }
        }
    }

    @ViewBuilder
    private func stage2BarLine(s2: FormattedPairedStageDisplay) -> some View {
        HStack(alignment: .center, spacing: 8) {
            Text(metricSet.stage2Label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(DS.textPrimary)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : stageLabelWidth, alignment: .leading)
                .lineLimit(1)

            switch s2.kind {
            case .percent:
                let pct = CGFloat(s2.percent ?? 1)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(DS.trackBg)
                        Capsule()
                            .fill(DS.emerald)
                            .frame(width: max(geo.size.width * 0.04, geo.size.width * min(pct / 100.0, 1.0)))
                    }
                }
                .frame(height: 10)

                PairedQuietNumberBox(
                    fraction: PairedMetricPresentation.quietFillFraction(for: s2) ?? 0,
                    isPrimaryStage: true,
                    trackColor: DS.trackBg,
                    fixedWidth: 48,
                    contentAlignment: .trailing,
                    horizontalPadding: 6,
                    verticalPadding: 2.5
                ) {
                    Text(s2.label)
                        .font(.system(size: 13, weight: .bold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(1)
                }

            case .cross:
                Text(s2.label)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                Spacer(minLength: 0)

            case .missing, .tick:
                Text(s2.label)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(DS.trackBg)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(DS.border, lineWidth: 1))
                Spacer(minLength: 0)
            }
        }
    }

    // MARK: - Look 2: `podium_and_tiers`

    @ViewBuilder
    private var podiumAndTiersBody: some View {
        if let partition = PairedMetricPresentation.podiumPartition(for: metricSet) {
            VStack(alignment: .leading, spacing: 0) {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(spacing: 8) {
                        ForEach(partition.podiumSpots.sorted(by: { $0.rank < $1.rank }), id: \.entry.id) { spot in
                            podiumCard(spot: spot)
                        }
                    }
                    .padding(.top, 12)
                } else {
                    HStack(alignment: .bottom, spacing: 8) {
                        ForEach(partition.podiumSpots, id: \.entry.id) { spot in
                            podiumCard(spot: spot)
                        }
                    }
                    .padding(.top, 12)
                }

                if !partition.lockTier.isEmpty || !partition.bubbleTier.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        if !partition.lockTier.isEmpty {
                            tierContainer(entries: partition.lockTier, isLockTier: true)
                        }
                        if !partition.bubbleTier.isEmpty {
                            tierContainer(entries: partition.bubbleTier, isLockTier: false)
                        }
                    }
                    .padding(.top, 12)
                }
            }
        }
    }

    @ViewBuilder
    private func podiumCard(spot: PairedPodiumSpot) -> some View {
        let s1 = PairedMetricPresentation.formatStage1Display(entry: spot.entry, set: metricSet)
        let s2 = PairedMetricPresentation.formatStage2Display(entry: spot.entry, set: metricSet)
        let s1Short = PairedMetricPresentation.shortStage1Tag(for: metricSet)
        let s2Short = PairedMetricPresentation.shortStage2Tag(for: metricSet)

        let cardBody = VStack(alignment: .center, spacing: 0) {
            Text(spot.badge)
                .font(.system(size: 10, weight: .bold))
                .tracking(0.2)
                .foregroundStyle(spot.elevated ? Color.white : DS.textSecondaryReadable)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(spot.elevated ? DS.emeraldDark : DS.cardBg)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            PairedArtThumbnailView(
                entry: spot.entry,
                size: spot.elevated ? .lg : .md,
                preloadedImages: preloadedImages
            )
            .padding(.top, 8)

            Text(spot.entry.subject)
                .font(.system(size: 12, weight: .bold))
                .multilineTextAlignment(.center)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 6)

            Group {
                if s2.kind == .percent, let frac2 = PairedMetricPresentation.quietFillFraction(for: s2) {
                    PairedQuietNumberBox(
                        fraction: frac2,
                        isPrimaryStage: true,
                        trackColor: DS.cardBg,
                        expandToFillWidth: true,
                        contentAlignment: .center,
                        cornerRadius: 6,
                        horizontalPadding: 6,
                        verticalPadding: 3.5
                    ) {
                        HStack(alignment: .firstTextBaseline, spacing: 2) {
                            Text(s2.label)
                                .font(.system(size: 15, weight: .bold).monospacedDigit())
                                .foregroundStyle(DS.textPrimary)
                            Text(s2Short)
                                .font(.system(size: 10.5, weight: .medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                        }
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                    }
                } else {
                    Text(s2.label)
                        .font(.system(size: 11, weight: .medium))
                        .multilineTextAlignment(.center)
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
            .padding(.top, 6)

            Group {
                switch s1.kind {
                case .percent:
                    PairedQuietNumberBox(
                        fraction: PairedMetricPresentation.quietFillFraction(for: s1) ?? 0,
                        isPrimaryStage: false,
                        trackColor: DS.cardBg,
                        expandToFillWidth: true,
                        contentAlignment: .center,
                        cornerRadius: 6,
                        horizontalPadding: 6,
                        verticalPadding: 3
                    ) {
                        Text("\(s1.label) \(s1Short)")
                            .font(.system(size: 11.5, weight: .medium).monospacedDigit())
                            .foregroundStyle(DS.textPrimary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.85)
                    }
                case .tick:
                    Text(s1.label)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(DS.greenReadable)
                case .cross:
                    Text(s1.label)
                        .font(.system(size: 11, weight: .medium))
                        .strikethrough()
                        .foregroundStyle(DS.textSecondaryReadable)
                case .missing:
                    Text(s1.label)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
            .multilineTextAlignment(.center)
            .padding(.top, 4)
        }
        .padding(.horizontal, 10)
        .padding(.top, spot.elevated ? 12 : 10)
        .padding(.bottom, spot.elevated ? 14 : 10)
        .frame(maxWidth: .infinity)
        .background(DS.trackBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(spot.elevated ? DS.emerald : DS.border, lineWidth: spot.elevated ? 1.5 : 1)
        )
        .shadow(color: spot.elevated ? .black.opacity(0.06) : .clear, radius: 4, x: 0, y: 2)

        if let onOpenMarket {
            let targetMarketId = spot.entry.stage2Probability != nil ? spot.entry.stage2MarketId : spot.entry.stage1MarketId
            Button {
                if targetMarketId > 0 {
                    onOpenMarket(targetMarketId)
                }
            } label: {
                cardBody.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            cardBody
        }
    }

    @ViewBuilder
    private func tierContainer(entries: [PairedSubjectEntry], isLockTier: Bool) -> some View {
        let header = PairedMetricPresentation.tierHeaderCopy(for: metricSet, isLockTier: isLockTier)
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(header.left)
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 6)
                Text(header.right)
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize()
            }

            VStack(spacing: 6) {
                ForEach(entries) { entry in
                    tierRow(entry: entry)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.trackBg)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(DS.border, lineWidth: 1))
    }

    @ViewBuilder
    private func tierRow(entry: PairedSubjectEntry) -> some View {
        let s1 = PairedMetricPresentation.formatStage1Display(entry: entry, set: metricSet)
        let s2 = PairedMetricPresentation.formatStage2Display(entry: entry, set: metricSet)
        let rowBody = HStack(alignment: .center, spacing: 8) {
            PairedArtThumbnailView(entry: entry, size: .xs, preloadedImages: preloadedImages)

            Text(entry.subject)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)

            if s2.kind == .percent {
                HStack(spacing: 5) {
                    if s1.kind == .percent, let frac1 = PairedMetricPresentation.quietFillFraction(for: s1) {
                        PairedQuietNumberBox(
                            fraction: frac1,
                            isPrimaryStage: false,
                            trackColor: DS.trackBg,
                            fixedWidth: 46,
                            contentAlignment: .trailing,
                            horizontalPadding: 6,
                            verticalPadding: 2.5
                        ) {
                            Text(s1.label)
                                .font(.system(size: 12, weight: .medium).monospacedDigit())
                                .foregroundStyle(DS.textPrimary)
                                .lineLimit(1)
                        }
                    } else {
                        Text(s1.label)
                            .font(.system(size: 11, weight: .medium).monospacedDigit())
                            .foregroundStyle(DS.textSecondaryReadable)
                    }

                    PairedQuietNumberBox(
                        fraction: PairedMetricPresentation.quietFillFraction(for: s2) ?? 0,
                        isPrimaryStage: true,
                        trackColor: DS.trackBg,
                        fixedWidth: 46,
                        contentAlignment: .trailing,
                        horizontalPadding: 6,
                        verticalPadding: 2.5
                    ) {
                        Text(s2.label)
                            .font(.system(size: 12, weight: .bold).monospacedDigit())
                            .foregroundStyle(DS.textPrimary)
                            .lineLimit(1)
                    }
                }
                .fixedSize()
            } else if s1.kind == .percent, let frac1 = PairedMetricPresentation.quietFillFraction(for: s1) {
                HStack(spacing: 6) {
                    PairedQuietNumberBox(
                        fraction: frac1,
                        isPrimaryStage: false,
                        trackColor: DS.trackBg,
                        fixedWidth: 46,
                        contentAlignment: .trailing,
                        horizontalPadding: 6,
                        verticalPadding: 2.5
                    ) {
                        Text(s1.label)
                            .font(.system(size: 12, weight: .medium).monospacedDigit())
                            .foregroundStyle(DS.textPrimary)
                            .lineLimit(1)
                    }
                    Text(s2.label)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .multilineTextAlignment(.trailing)
                }
            } else {
                Text("\(s1.label) · \(s2.label)")
                    .font(.system(size: 12, weight: .medium).monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
                    .multilineTextAlignment(.trailing)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(DS.border, lineWidth: 1))

        if let onOpenMarket {
            let targetMarketId = entry.stage2Probability != nil ? entry.stage2MarketId : entry.stage1MarketId
            Button {
                if targetMarketId > 0 {
                    onOpenMarket(targetMarketId)
                }
            } label: {
                rowBody.contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            rowBody
        }
    }
}
