import SwiftUI
import XCTest
@testable import Bain_Luck

/// A camera on #3977, because the defect only ever existed as a raster.
///
/// "`● MAR` becomes `M…`" is a claim about drawn ink at a text size, and no
/// assertion about constants can see it: the old rule and the new one are the same
/// number, `44`, and differ only in whether it is a ceiling or a floor. So this
/// renders the shipped `GameSegmentTeamBadge` through `ImageRenderer` — the camera
/// native/025 built and `LiveSparklineRenderSmokeTests` uses — at the reader's own
/// Dynamic Type sizes, and measures the width SwiftUI actually gave it.
///
/// **THE CONTROL IS THE FIRST TEST, AND IT IS NOT DECORATION.** The whole file is
/// worthless if `ImageRenderer` ignores `dynamicTypeSize`, because then every
/// measurement below is the same measurement three times and would pass against
/// the broken build too. `testTheCameraSeesTheReadersTextSize` fails in exactly
/// that case, so a green run means the sizes were really applied.
///
/// Sizes under test are the STANDARD Larger Text slider only (Large … XXXL), with
/// accessibility sizes switched off. That is deliberate: those are the sizes a
/// reader reaches without turning anything on, they are where #3977 was
/// photographed, and the accessibility sizes above them break other parts of the
/// event page too (filed separately) — promising them here would be a claim this
/// change does not earn.
@MainActor
final class GameSegmentTeamBadgeWidthTests: XCTestCase {

    /// The badge's own furniture, ahead of the text: a 7pt dot and the HStack's
    /// 6pt spacing. Written out because the assertions below are about how much
    /// room is left for the LABEL, which is the thing the reader loses.
    private static let furnitureWidth: CGFloat = 13

    /// Two real badges off the specimen in #3977 — Athletics 6 – Mariners 2
    /// (`15304933`), the page the defect was photographed on.
    private static let awayBadge = "ATH"
    private static let homeBadge = "MAR"

    /// Rendering is not exact to the point; nothing here turns on a half point.
    private static let epsilon: CGFloat = 0.5

    // MARK: - The camera

    private func renderedWidth<V: View>(
        _ view: V, at size: DynamicTypeSize, _ label: String
    ) throws -> CGFloat {
        let renderer = ImageRenderer(content: view.environment(\.dynamicTypeSize, size))
        // Points, not pixels — every number in this file is a layout width.
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.uiImage, "\(label) produced no raster")
        return image.size.width
    }

    /// The badge as the table draws it.
    private func badgeWidth(_ team: String, at size: DynamicTypeSize) throws -> CGFloat {
        try renderedWidth(
            GameSegmentTeamBadge(team: team, color: .blue),
            at: size, "badge \(team) @ \(size)")
    }

    /// The same string with NOTHING constraining it — the width the badge must
    /// leave room for if the label is to survive whole.
    private func unconstrainedLabelWidth(
        _ team: String, at size: DynamicTypeSize
    ) throws -> CGFloat {
        try renderedWidth(
            Text(team).font(.caption.weight(.semibold)).lineLimit(1),
            at: size, "bare label \(team) @ \(size)")
    }

    // MARK: - Control

    func testTheCameraSeesTheReadersTextSize() throws {
        let small = try unconstrainedLabelWidth(Self.homeBadge, at: .large)
        let large = try unconstrainedLabelWidth(Self.homeBadge, at: .xxxLarge)

        XCTAssertGreaterThan(
            large, small + Self.epsilon,
            """
            `\(Self.homeBadge)` measured \(small)pt at Large and \(large)pt at \
            XXXL — the same width, so ImageRenderer is NOT applying \
            `dynamicTypeSize` and every other assertion in this file is measuring \
            one size three times. Fix the harness before trusting a green run.
            """)
    }

    // MARK: - The default size must not move

    /// UX-P090 measured 44pt against a 375pt SE so the TOTAL column stayed on
    /// screen, and Alex accepted that layout. #3977 turns the ceiling into a floor
    /// and must change nothing at the size it was tuned for — which is only true
    /// while the badge's ink still fits inside 44.
    func testAtTheDefaultTextSizeTheFloorStillGovernsBothBadges() throws {
        for team in [Self.awayBadge, Self.homeBadge] {
            let ink = try unconstrainedLabelWidth(team, at: .large)
            XCTAssertLessThanOrEqual(
                Self.furnitureWidth + ink,
                GameSegmentTeamBadge.minimumWidthPoints,
                """
                `● \(team)` needs \(Self.furnitureWidth + ink)pt at the default \
                text size, which no longer fits UX-P090's 44pt column. The \
                default-size layout has moved; re-measure it against a 375pt SE \
                before changing this number.
                """)

            let width = try badgeWidth(team, at: .large)
            XCTAssertEqual(
                width, GameSegmentTeamBadge.minimumWidthPoints, accuracy: Self.epsilon,
                "`● \(team)` drew \(width)pt at the default text size, not the "
                + "44pt column UX-P090 tuned.")
        }
    }

    // MARK: - The defect

    /// The photographed failure: at XXL both badges cut to `A…` / `M…`, at XXXL
    /// the home row to a bare `…`. A truncating badge is one whose frame is
    /// NARROWER than its furniture plus its ink, so that is what is asserted —
    /// against the ink measured at the same size, never against a stored number.
    func testEveryStandardTextSizeLeavesRoomForTheWholeBadge() throws {
        for size in [DynamicTypeSize.large, .xLarge, .xxLarge, .xxxLarge] {
            for team in [Self.awayBadge, Self.homeBadge] {
                let ink = try unconstrainedLabelWidth(team, at: size)
                let width = try badgeWidth(team, at: size)

                XCTAssertGreaterThanOrEqual(
                    width, Self.furnitureWidth + ink - Self.epsilon,
                    """
                    At \(size) `● \(team)` was given \(width)pt for \
                    \(Self.furnitureWidth + ink)pt of dot, spacing and label, so \
                    SwiftUI cut the label — the reader sees `\(team.prefix(1))…` \
                    and the row stops naming its team (#3430, #3977). The team \
                    column is a FLOOR (`minWidth`); a ceiling (`width`) puts this \
                    back.
                    """)
            }
        }
    }

    /// Above the default the column must actually grow, or the assertion above
    /// could be satisfied by a font that never got bigger. Two claims, two tests:
    /// this one is the reason the fix exists at all.
    func testTheColumnGrowsPastUXP090sNumberWhenTheInkNeedsIt() throws {
        let width = try badgeWidth(Self.homeBadge, at: .xxxLarge)

        XCTAssertGreaterThan(
            width, GameSegmentTeamBadge.minimumWidthPoints + Self.epsilon,
            """
            `● \(Self.homeBadge)` still drew \(width)pt at XXXL — the column is \
            pinned to 44pt rather than floored at it, which is the whole of #3977.
            """)
    }
}
