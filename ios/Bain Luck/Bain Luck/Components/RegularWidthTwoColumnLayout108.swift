import SwiftUI

/// 1.0.8 Item 1 — Shared regular-width two-column gate & rank-preserving layout
/// for `LeagueGridView` and `MyStuffView`. Keeps iPhone, Split View, Slide Over
/// (<700 pt inner width), and Accessibility Dynamic Type sizes single-column,
/// while preserving left-to-right-then-down VoiceOver order in two columns.
enum RegularWidthTwoColumnGrid108 {
    static let minTwoColumnInnerWidth: CGFloat = 700
    static let spacing: CGFloat = 12
    static let listHorizontalMarginAllowance: CGFloat = 40

    nonisolated static func innerWidth(containerWidth: CGFloat) -> CGFloat {
        max(0, containerWidth - listHorizontalMarginAllowance)
    }

    nonisolated static func columnCount(
        horizontalSizeClass: UserInterfaceSizeClass?,
        dynamicTypeSize: DynamicTypeSize,
        availableWidth: CGFloat
    ) -> Int {
        guard horizontalSizeClass == .regular,
              !dynamicTypeSize.isAccessibilitySize,
              availableWidth >= minTwoColumnInnerWidth else {
            return 1
        }
        return 2
    }

    nonisolated static func sortPriority(index: Int) -> Double {
        Double(max(1, 10_000 - index))
    }
}

/// Deals child views round-robin (`index % 2`) into two top-aligned columns with
/// zero row-height stretching while keeping SwiftUI subviews in source rank order
/// (`0, 1, 2, ...`) so VoiceOver naturally traverses left-to-right, then down.
struct TwoColumnMasonryLayout108: Layout {
    var spacing: CGFloat = RegularWidthTwoColumnGrid108.spacing

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let width = proposal.width ?? 760
        let colWidth = max(1, (width - spacing) / 2)
        let childProposal = ProposedViewSize(width: colWidth, height: nil)
        var columnHeights: [CGFloat] = [0, 0]
        for (index, subview) in subviews.enumerated() {
            let col = index % 2
            let fitted = subview.sizeThatFits(childProposal)
            if columnHeights[col] > 0 {
                columnHeights[col] += spacing
            }
            columnHeights[col] += fitted.height
        }
        return CGSize(width: width, height: max(columnHeights[0], columnHeights[1]))
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        guard !subviews.isEmpty else { return }
        let colWidth = max(1, (bounds.width - spacing) / 2)
        let childProposal = ProposedViewSize(width: colWidth, height: nil)
        var columnY: [CGFloat] = [bounds.minY, bounds.minY]
        for (index, subview) in subviews.enumerated() {
            let col = index % 2
            let fitted = subview.sizeThatFits(childProposal)
            let x = bounds.minX + CGFloat(col) * (colWidth + spacing)
            subview.place(
                at: CGPoint(x: x, y: columnY[col]),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: colWidth, height: fitted.height)
            )
            columnY[col] += fitted.height + spacing
        }
    }
}
