import SwiftUI

/// A layout that arranges views horizontally, wrapping to the next line when needed.
///
/// #9483 R4 — an item wider than the whole row is offered the row's width
/// (so a long label wraps inside it) instead of being placed at its natural
/// width and cut off at the edge. Items that fit are laid out exactly as before.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var height: CGFloat = 0
        for (i, row) in rows.enumerated() {
            let maxH = row.map { Self.fitted($0, maxWidth: maxWidth).size.height }.max() ?? 0
            height += maxH
            if i > 0 { height += spacing }
        }
        return CGSize(width: proposal.width ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let maxWidth = proposal.width ?? .infinity
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var y = bounds.minY
        for (i, row) in rows.enumerated() {
            if i > 0 { y += spacing }
            var x = bounds.minX
            let maxH = row.map { Self.fitted($0, maxWidth: maxWidth).size.height }.max() ?? 0
            for subview in row {
                let (size, offer) = Self.fitted(subview, maxWidth: maxWidth)
                subview.place(at: CGPoint(x: x, y: y + (maxH - size.height) / 2), proposal: offer)
                x += size.width + spacing
            }
            y += maxH
        }
    }

    /// A subview's natural size, or — when that is wider than the row — its
    /// size at the row's width, with the proposal that produced it.
    private static func fitted(_ subview: LayoutSubviews.Element,
                               maxWidth: CGFloat) -> (size: CGSize, offer: ProposedViewSize) {
        let natural = subview.sizeThatFits(.unspecified)
        guard natural.width > maxWidth, maxWidth.isFinite else { return (natural, .unspecified) }
        let offer = ProposedViewSize(width: maxWidth, height: nil)
        return (subview.sizeThatFits(offer), offer)
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [[LayoutSubviews.Element]] {
        let maxWidth = proposal.width ?? .infinity
        var rows: [[LayoutSubviews.Element]] = [[]]
        var currentWidth: CGFloat = 0
        for subview in subviews {
            let size = Self.fitted(subview, maxWidth: maxWidth).size
            if currentWidth + size.width > maxWidth, !rows[rows.count - 1].isEmpty {
                rows.append([])
                currentWidth = 0
            }
            rows[rows.count - 1].append(subview)
            currentWidth += size.width + spacing
        }
        return rows
    }
}
