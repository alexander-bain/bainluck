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

    var body: some View {
        Group {
            if let ref = collectionRef, let onOpenCollection {
                Button {
                    onOpenCollection(ref)
                } label: {
                    cardSurface
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .combine)
                .accessibilityLabel(model.accessibilitySummary)
                .accessibilityAddTraits(.isButton)
            } else {
                cardSurface
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(model.accessibilitySummary)
            }
        }
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
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            footerSection
        }
        .padding(.horizontal, 18)
        .padding(.top, 18)
        .padding(.bottom, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    // MARK: - Header (Kicker + Tag + Headline + Optional Subtitle)

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if dynamicTypeSize.isAccessibilitySize {
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
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            if let subtitle = model.subtitle {
                Text(subtitle)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var kickerLabel: some View {
        Text(model.kicker.uppercased())
            .font(.caption2.weight(.semibold))
            .tracking(0.8)
            .foregroundStyle(DS.textSecondaryReadable)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func tagBadge(_ tag: String) -> some View {
        Text(tag)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DS.textSecondaryReadable)
            .padding(.horizontal, 9)
            .padding(.vertical, 3)
            .background(Capsule().fill(DS.trackBg))
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
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    percentView(marker: row.marker, digits: row.digits, font: .title3)
                    Spacer(minLength: 4)
                    if row.showsRowAgeMark,
                       let mark = PriceAgeMarkView(observedAt: row.observedAt, cadence: row.cadence, now: now) {
                        mark
                    }
                }
                rowRightColumn(row, includeAgeMarkInline: false)
            }
        } else {
            HStack(alignment: .top, spacing: 12) {
                percentView(marker: row.marker, digits: row.digits, font: .title3)
                    .frame(width: 56, alignment: .trailing)

                rowRightColumn(row, includeAgeMarkInline: true)
            }
        }
    }

    private func rowRightColumn(_ row: DiscoverRoundupRowModel, includeAgeMarkInline: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(row.label)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
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
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            proportionalBar(fill: row.fill, barHeight: 6, barColor: DS.blue)

            if let secondary = row.secondary {
                VStack(alignment: .leading, spacing: 4) {
                    proportionalBar(fill: secondary.fill, barHeight: 5, barColor: DS.textMuted)
                    Text("\(secondary.secondaryLabel) \(secondary.formattedPercentText) · \(secondary.primaryLabel) \(row.formattedPercentText)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
            }
        }
    }

    // MARK: - 3-Up Schedule Strip Presentation

    @ViewBuilder
    private var stripRowsSection: some View {
        if dynamicTypeSize.isAccessibilitySize {
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
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.opponentLabel ?? row.label)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                    .fixedSize(horizontal: false, vertical: true)

                if let dateLabel = row.dateLabel {
                    Text(dateLabel)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    percentView(marker: row.marker, digits: row.digits, font: .headline)
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
                .fill(DS.trackBg.opacity(0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    // MARK: - Footer

    private var footerSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Rectangle()
                .fill(DS.border)
                .frame(height: 1)

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.footer)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
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
                        .foregroundStyle(DS.textSecondaryReadable)
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

    private func percentView(marker: String?, digits: String, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text("\(marker ?? "")\(digits)")
                .font(font.monospacedDigit().weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize()
            Text("%")
                .font(.caption.weight(.medium))
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize()
        }
    }

    private func proportionalBar(fill: Double, barHeight: CGFloat, barColor: Color) -> some View {
        GeometryReader { geo in
            let clamped = CGFloat(min(1.0, max(0.0, fill)))
            let fillWidth = max(3, geo.size.width * clamped)
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(DS.trackBg)
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(barColor)
                    .frame(width: min(geo.size.width, fillWidth))
            }
        }
        .frame(height: barHeight)
        .accessibilityHidden(true)
    }
}
