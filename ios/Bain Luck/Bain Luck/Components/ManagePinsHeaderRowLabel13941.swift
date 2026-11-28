import SwiftUI

/// #13941 (`PILLAR: FORMATTING`):
/// Shared `"Manage pins"` header-row label in `MyStuffView`.
///
/// At ordinary text sizes (`dynamicTypeSize.isAccessibilitySize == false`), this renders the
/// exact inline `HStack` with `Label("Manage pins", systemImage: "bookmark.fill")`, count, and
/// chevron unchanged from `master`. At accessibility text sizes (`.accessibility1`–`.accessibility5`),
/// `Label` inside an `HStack` broke `"Manage"` mid-word across lines (`M / anage / pins` at 320 pt,
/// `Man- / age pins` at 390 pt). Using a capped icon + count/chevron beside a `ViewThatFits` title
/// sized with `CardTeamNameSizing.sharedUnboundedWordSafeFontSize` keeps every word whole and at a
/// uniform font size while preserving the count and chevron on the row.
struct ManagePinsHeaderRowLabel13941: View {
    let savedPinCount: Int

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .subheadline) private var scaledTitleSize: CGFloat = 15
    @State private var titleSlotWidth: CGFloat = 0

    nonisolated static let titleWords = ["Manage", "pins"]

    nonisolated static func sharedAccessibilityFontSize(
        baseSize: CGFloat,
        availableWidth: CGFloat
    ) -> CGFloat {
        guard availableWidth > 0 else { return baseSize }
        return CardTeamNameSizing.sharedUnboundedWordSafeFontSize(
            names: titleWords,
            baseSize: baseSize,
            weight: .medium,
            availableWidth: max(availableWidth - 4, 40),
            minimumScale: 0.45
        )
    }

    var body: some View {
        if dynamicTypeSize.isAccessibilitySize {
            accessibilityRow
        } else {
            ordinaryRow
        }
    }

    private var ordinaryRow: some View {
        HStack {
            Label("Manage pins", systemImage: "bookmark.fill")
                .font(.subheadline.weight(.medium))
            Spacer()
            Text("\(savedPinCount)")
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(.secondary)
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
    }

    private var accessibilityRow: some View {
        let effectiveWidth = titleSlotWidth > 0 ? titleSlotWidth : 120
        let uniformSize = Self.sharedAccessibilityFontSize(
            baseSize: scaledTitleSize,
            availableWidth: effectiveWidth
        )

        return HStack(spacing: 8) {
            Image(systemName: "bookmark.fill")
                .font(.subheadline.weight(.medium))
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
                .accessibilityHidden(true)

            ViewThatFits(in: .horizontal) {
                Text("Manage pins")
                    .font(.system(size: uniformSize, weight: .medium))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)

                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(Self.titleWords.enumerated()), id: \.offset) { _, word in
                        Text(word)
                            .font(.system(size: uniformSize, weight: .medium))
                            .lineLimit(1)
                            .allowsTightening(true)
                            .minimumScaleFactor(0.90)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { newWidth in
                if abs(newWidth - titleSlotWidth) > 0.5 {
                    titleSlotWidth = newWidth
                }
            }
            .layoutPriority(1)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Manage pins")

            Text("\(savedPinCount)")
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(.secondary)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
                .fixedSize()

            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
                .fixedSize()
                .accessibilityHidden(true)
        }
    }
}
