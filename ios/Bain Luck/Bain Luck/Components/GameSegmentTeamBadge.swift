import SwiftUI

/// The label that names one row of the Game Segments table.
///
/// #3977 — LIFTED OUT OF `GameSegmentsView` BECAUSE ITS WIDTH WAS THE ONLY FIXED
/// COLUMN IN A TABLE OF FLOORS, and the fix is only checkable if a test can point
/// a camera at it.
///
/// The two rows of that table are the two competitors, stacked, and #3430 is the
/// ruling that the reader tells them apart by these labels alone. On the standard
/// Larger Text slider — accessibility sizes switched OFF — that guarantee failed:
/// `● ATH` and `● MAR` became `A…` and `M…` at XXL, and at XXXL the home row
/// degraded to a bare `…`. What was left naming the row was a 7pt coloured dot,
/// and a dot is not a label.
///
/// The cause was one word. Every other column in the Grid is written as a FLOOR
/// (`minWidth: 22` for an inning, `minWidth: 26` for the total) so it grows with
/// its ink; the team column alone was `frame(width: 44)`, a CEILING. 44 is
/// UX-P090's number and it is right — it is what keeps the TOTAL column on screen
/// at the default text size, measured against a 375pt SE — but it was only ever
/// measured at ONE text size, and a number measured at one size is a floor, not a
/// width.
///
/// So the floor stays and the ceiling goes. At Large the badge draws ~35pt and the
/// floor governs, which is what makes this change a no-op on the layout Alex
/// already accepted; above Large the column takes the width its own ink needs, and
/// the `ScrollView(.horizontal, showsIndicators: true)` that UX-P090 wrapped this
/// Grid in is exactly the affordance a wider row is supposed to fall back on.
///
/// Nothing here models how wide the text is. SwiftUI measures it, in the font it
/// is about to draw it in, at the reader's own type size — the arithmetic version
/// of that question is what #3954 had to delete.
struct GameSegmentTeamBadge: View {
    let team: String
    let color: Color

    /// UX-P090's team-column width, kept as the FLOOR it always should have been.
    ///
    /// The header row's empty spacer cell carries the same number, because the two
    /// must move together or the columns shear (that warning is UX-P090's and it
    /// still holds — it is why this is a `static` on the type both cells use
    /// rather than a literal typed twice).
    static let minimumWidthPoints: CGFloat = 44

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 7, height: 7)
            Text(team)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
                // Kept from the original: a badge is one line. The column now
                // grows to hold that line instead of cutting it.
                .lineLimit(1)
        }
        .frame(minWidth: Self.minimumWidthPoints, alignment: .leading)
    }
}
