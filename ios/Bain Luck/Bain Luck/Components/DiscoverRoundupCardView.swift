import SwiftUI

// MARK: - Native Discover Round-Up Card View (Item 3 / #10357 / #12288)
//
// Renders `kind: "roundup"` Discover grouped cards on iPhone, iPad, and Mac to
// Fable's R4 round-up specification (`frontend/components/discover/roundup/`),
// covering all 11 candidate producers under `backend/data/discover/candidates/`:
// - Live & upcoming game-event rows (`roundup-upsets-brewing`, `roundup-team-active-streaks`)
// - Mixed cross-domain game + market yardstick bands (`roundup-as-likely-as`)
// - 24h movers & waking long-shot point shifts (`roundup-big-movers-today`, `roundup-long-shot-movers`)
// - Benchmark, division, trophy, ceremony, box-office & halftime stage leaderboards
//   (`roundup-ai-race`, `roundup-nba-division-races`, `roundup-nba-award-ladders`,
//    `roundup-ceremony-award-categories`, `roundup-opening-weekend-slate`,
//    `roundup-headliners-and-hosts`)
// - Dual-bar ceremony rows (`secondary_probability`) and 3-up schedule `strip` tiles.

struct DiscoverRoundupCardView: View {
    let model: DiscoverRoundupCardModel
    let collectionRef: FeedThemeCollectionRef?
    var now: Date = Date()
    var onOpenCollection: ((FeedThemeCollectionRef) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.discoverNarrowTwoColumn13914) private var isNarrowTwoColumn
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.discoverCardLikeAction420D) private var likeAction

    private var isDark: Bool {
        colorScheme == .dark
    }

    private var cardSurfaceColor: Color {
        isDark ? Color.cardBackground : DS.cardBg
    }

    private var primaryInk: Color {
        isDark ? Color.primary : DS.textPrimary
    }

    private var secondaryReadableInk: Color {
        isDark ? Color(hex: "#94A3B8") : DS.textSecondaryReadable
    }

    private var borderInk: Color {
        isDark ? Color.white.opacity(0.12) : DS.border
    }

    private var trackInk: Color {
        isDark ? Color.white.opacity(0.10) : DS.trackBg
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let ref = collectionRef, let onOpenCollection {
                Button {
                    onOpenCollection(ref)
                } label: {
                    cardSurface
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: model.hasAnySourceMark ? .contain : .combine)
                .accessibilityLabel(model.accessibilitySummary)
                .accessibilityAddTraits(.isButton)
            } else {
                cardSurface
                    .accessibilityElement(children: model.hasAnySourceMark ? .contain : .combine)
                    .accessibilityLabel(model.accessibilitySummary)
            }

            if let likeAction {
                DiscoverCardActionBar420D(actions: likeAction, topDivider: true, horizontalPadding: 18, verticalPadding: 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardSurfaceColor)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(borderInk, lineWidth: 1)
        )
    }

    private var cardSurface: some View {
        VStack(alignment: .leading, spacing: 14) {
            headerSection

            if model.presentation == .strip {
                stripRowsSection
            } else {
                standardRowsSection
            }

            if let countLine = model.countLine {
                Text(countLine)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(secondaryReadableInk)
                    .fixedSize(horizontal: false, vertical: true)
            }

            footerSection
        }
        .padding(.horizontal, 18)
        .padding(.top, 18)
        .padding(.bottom, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Header (Kicker + Tag + Headline + Optional Subtitle)

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if dynamicTypeSize.isAccessibilitySize || isNarrowTwoColumn {
                VStack(alignment: .leading, spacing: 6) {
                    kickerLabel
                    if let tag = model.tag {
                        tagBadge(tag)
                    }
                }
            } else {
                HStack(alignment: .center, spacing: 10) {
                    kickerLabel
                    Spacer(minLength: 4)
                    if let tag = model.tag {
                        tagBadge(tag)
                    }
                }
            }

            Text(model.title)
                .font((model.longHeadline ? Font.headline : Font.title3).weight(.bold))
                .foregroundStyle(primaryInk)
                .fixedSize(horizontal: false, vertical: true)

            if let subtitle = model.subtitle {
                Text(subtitle)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(secondaryReadableInk)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var kickerLabel: some View {
        Text(model.kicker.uppercased())
            .font(.caption2.weight(.semibold))
            .tracking(0.8)
            .foregroundStyle(secondaryReadableInk)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func tagBadge(_ tag: String) -> some View {
        Text(tag)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(secondaryReadableInk)
            .padding(.horizontal, 9)
            .padding(.vertical, 3)
            .background(Capsule().fill(trackInk))
            .fixedSize()
    }

    // MARK: - Standard Rows

    private var standardRowsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(model.rows) { row in
                standardRowView(row)
            }
        }
    }

    @ViewBuilder
    private func standardRowView(_ row: DiscoverRoundupRowModel) -> some View {
        let divDisplay = row.divisionDisplay
        let isUnpricedOrOut = divDisplay?.state == .eliminated || divDisplay?.state == .noRecentProbability
        let isSubOne = divDisplay?.state == .subOnePercent
        let isSettled = row.sourceMark?.state == .settled
        let numberForSheet: Double? = isSettled ? nil : row.rawProbability
        let renderedPercentForSheet: Int? = isSettled ? nil : row.renderedPercent
        let showsRowTenths = row.digits.contains(".")
        let pctInk = isSubOne ? secondaryReadableInk : primaryInk
        let barColor: Color = isSubOne
            ? (isDark ? Color.white.opacity(0.32) : DS.textMuted.opacity(0.65))
            : DS.blue

        if let divDisplay, isUnpricedOrOut {
            VStack(alignment: .leading, spacing: 6) {
                if dynamicTypeSize.isAccessibilitySize || isNarrowTwoColumn {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.label)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(secondaryReadableInk)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(divDisplay.label)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(secondaryReadableInk)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(row.label)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(secondaryReadableInk)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        Text(divDisplay.label)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(secondaryReadableInk)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
                proportionalBar(fill: 0, barHeight: 6, barColor: DS.blue)
            }
        } else if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    percentView(marker: row.marker, digits: row.digits, font: .title3, ink: pctInk)
                    if let srcMark = SourceMarkButton(row.sourceMark, number: numberForSheet, renderedPercent: renderedPercentForSheet, subject: row.label, numberSize: 16, compactRow: true, showsTenths: showsRowTenths) {
                        srcMark.buttonStyle(.borderless)
                    }
                    Spacer(minLength: 4)
                    if row.showsRowAgeMark,
                       let mark = PriceAgeMarkView(observedAt: row.observedAt, cadence: row.cadence, now: now) {
                        mark
                    }
                }
                rowRightColumn(row, includeAgeMarkInline: false, barColor: barColor, mutedLabel: isSubOne)
            }
        } else {
            HStack(alignment: .top, spacing: 12) {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    percentView(marker: row.marker, digits: row.digits, font: .title3, ink: pctInk)
                    if let srcMark = SourceMarkButton(row.sourceMark, number: numberForSheet, renderedPercent: renderedPercentForSheet, subject: row.label, numberSize: 16, compactRow: true, showsTenths: showsRowTenths) {
                        srcMark.buttonStyle(.borderless)
                    }
                }
                .frame(width: model.hasAnySourceMark ? 78 : 56, alignment: .trailing)

                rowRightColumn(row, includeAgeMarkInline: true, barColor: barColor, mutedLabel: isSubOne)
            }
        }
    }

    private func rowRightColumn(
        _ row: DiscoverRoundupRowModel,
        includeAgeMarkInline: Bool,
        barColor: Color = DS.blue,
        mutedLabel: Bool = false
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(row.label)
                    .font(.subheadline)
                    .foregroundStyle(mutedLabel ? secondaryReadableInk : primaryInk)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if includeAgeMarkInline,
                   row.showsRowAgeMark,
                   let mark = PriceAgeMarkView(observedAt: row.observedAt, cadence: row.cadence, now: now) {
                    mark
                }
            }

            if let callout = row.detailCallout {
                Text(callout)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(secondaryReadableInk)
                    .fixedSize(horizontal: false, vertical: true)
            }

            proportionalBar(fill: row.fill, barHeight: 6, barColor: barColor)

            if let secondary = row.secondary {
                VStack(alignment: .leading, spacing: 4) {
                    proportionalBar(fill: secondary.fill, barHeight: 5, barColor: DS.textMuted)
                    Text("\(secondary.secondaryLabel) \(secondary.formattedPercentText) · \(secondary.primaryLabel) \(row.formattedPercentText)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(secondaryReadableInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
            }
        }
    }

    // MARK: - 3-Up Schedule Strip Presentation

    @ViewBuilder
    private var stripRowsSection: some View {
        if dynamicTypeSize.isAccessibilitySize || isNarrowTwoColumn {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(model.rows) { row in
                    stripTile(row)
                }
            }
        } else {
            HStack(alignment: .top, spacing: 8) {
                ForEach(model.rows) { row in
                    stripTile(row)
                }
            }
        }
    }

    private func stripTile(_ row: DiscoverRoundupRowModel) -> some View {
        let relaxed = dynamicTypeSize.isAccessibilitySize || isNarrowTwoColumn
        return VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.opponentLabel ?? row.label)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(primaryInk)
                    .lineLimit(relaxed ? nil : 2)
                    .fixedSize(horizontal: false, vertical: true)

                if let dateLabel = row.dateLabel {
                    Text(dateLabel)
                        .font(.caption2)
                        .foregroundStyle(secondaryReadableInk)
                        .lineLimit(relaxed ? nil : 1)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    percentView(marker: row.marker, digits: row.digits, font: .headline)
                    if let srcMark = SourceMarkButton(
                        row.sourceMark,
                        number: row.sourceMark?.state == .settled ? nil : row.rawProbability,
                        renderedPercent: row.sourceMark?.state == .settled ? nil : row.renderedPercent,
                        subject: row.opponentLabel ?? row.label,
                        numberSize: 15,
                        compactRow: true,
                        showsTenths: row.digits.contains(".")
                    ) {
                        srcMark.buttonStyle(.borderless)
                    }
                    Spacer(minLength: 0)
                    if row.showsRowAgeMark,
                       let mark = PriceAgeMarkView(observedAt: row.observedAt, cadence: row.cadence, now: now) {
                        mark
                    }
                }
                proportionalBar(fill: row.fill, barHeight: 5, barColor: DS.blue)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(trackInk.opacity(0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(borderInk, lineWidth: 1)
        )
    }

    // MARK: - Footer

    private var footerSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Rectangle()
                .fill(borderInk)
                .frame(height: 1)

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.footer)
                        .font(.caption)
                        .foregroundStyle(secondaryReadableInk)
                        .fixedSize(horizontal: false, vertical: true)
                    if let cardStamp = model.cardMarkObservedAt,
                       let mark = PriceAgeMarkView(observedAt: cardStamp, cadence: model.cadence, now: now) {
                        mark
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(model.footer)
                        .font(.caption)
                        .foregroundStyle(secondaryReadableInk)
                        .fixedSize(horizontal: false, vertical: true)

                    Spacer(minLength: 4)

                    if let cardStamp = model.cardMarkObservedAt,
                       let mark = PriceAgeMarkView(observedAt: cardStamp, cadence: model.cadence, now: now) {
                        mark
                    }
                }
            }
        }
    }

    // MARK: - Shared Primitives

    private func percentView(marker: String?, digits: String, font: Font, ink: Color? = nil) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text("\(marker ?? "")\(digits)")
                .font(font.monospacedDigit().weight(.bold))
                .foregroundStyle(ink ?? primaryInk)
                .fixedSize()
            Text("%")
                .font(.caption.weight(.medium))
                .foregroundStyle(secondaryReadableInk)
                .fixedSize()
        }
    }

    private func proportionalBar(fill: Double, barHeight: CGFloat, barColor: Color) -> some View {
        GeometryReader { geo in
            let clamped = CGFloat(min(1.0, max(0.0, fill)))
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(trackInk)
                if clamped > 0 {
                    let fillWidth = max(3, geo.size.width * clamped)
                    RoundedRectangle(cornerRadius: 3, style: .continuous)
                        .fill(barColor)
                        .frame(width: min(geo.size.width, fillWidth))
                }
            }
        }
        .frame(height: barHeight)
        .accessibilityHidden(true)
    }
}
