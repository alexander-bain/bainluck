import SwiftUI

/// The hero supplies away, probability, home. Keep both teams on the same row
/// and give the probability the full next row when text needs more room.
struct EventHeroTeamLayout: Layout {
    var spacing: CGFloat = 12

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 3 else { return .zero }
        let width = proposal.width ?? 358
        let teamWidth = max(0, (width - spacing) / 2)
        let teamProposal = ProposedViewSize(width: teamWidth, height: nil)
        let teamHeight = max(subviews[0].sizeThatFits(teamProposal).height,
                             subviews[2].sizeThatFits(teamProposal).height)
        let probabilityHeight = subviews[1].sizeThatFits(.init(width: width, height: nil)).height
        return CGSize(width: width, height: teamHeight + spacing + probabilityHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 3 else { return }
        let teamWidth = max(0, (bounds.width - spacing) / 2)
        let teamProposal = ProposedViewSize(width: teamWidth, height: nil)
        let teamHeight = max(subviews[0].sizeThatFits(teamProposal).height,
                             subviews[2].sizeThatFits(teamProposal).height)
        subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.minY), anchor: .topLeading, proposal: teamProposal)
        subviews[2].place(at: CGPoint(x: bounds.maxX - teamWidth, y: bounds.minY), anchor: .topLeading, proposal: teamProposal)
        subviews[1].place(at: CGPoint(x: bounds.midX, y: bounds.minY + teamHeight + spacing),
                          anchor: .top, proposal: .init(width: bounds.width, height: nil))
    }
}
