import SwiftUI

/// The hero supplies away, probability, home. When text needs more room the
/// probability takes the full FIRST row and both teams share the row beneath.
///
/// #9483 — probabilities lead. The first build of this layout put the teams on
/// top, so at enlarged text the page opened on two crests, two names and two
/// scores and the win chances sat under them (the design review of
/// `5f542c7b96`, Native's `nfl-live-xxxl-top.png`). The pair is the headline;
/// the teams it belongs to and their score follow directly, in the same
/// away-left / home-right order and colours as the two numbers.
struct EventHeroTeamLayout: Layout {
    var spacing: CGFloat = 12

    /// Where each row starts, from the top: the probability row, then the teams.
    static func rowOffsets(probabilityHeight: CGFloat, spacing: CGFloat) -> (probability: CGFloat, teams: CGFloat) {
        (0, probabilityHeight + spacing)
    }

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
        let probabilityProposal = ProposedViewSize(width: bounds.width, height: nil)
        let offsets = Self.rowOffsets(probabilityHeight: subviews[1].sizeThatFits(probabilityProposal).height,
                                      spacing: spacing)
        subviews[1].place(at: CGPoint(x: bounds.midX, y: bounds.minY + offsets.probability),
                          anchor: .top, proposal: probabilityProposal)
        subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.minY + offsets.teams),
                          anchor: .topLeading, proposal: teamProposal)
        subviews[2].place(at: CGPoint(x: bounds.maxX - teamWidth, y: bounds.minY + offsets.teams),
                          anchor: .topLeading, proposal: teamProposal)
    }
}
