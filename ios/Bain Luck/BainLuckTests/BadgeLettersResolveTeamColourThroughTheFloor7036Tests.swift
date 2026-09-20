import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/267 (#7036, fourth arm) — the sites that draw a team's BADGE LETTERS
/// with, or under, its stored colour resolve it through the contrast floor.
///
/// **Why there was a fourth arm at all.** Arm 3 closed the text half of the list
/// and deferred `MyStuffView`'s `TeamLogoView(color:)` with a stated reason: a
/// logo tint is colour-as-BACKGROUND, "an invisible SHAPE, not an unreadable
/// number", and flooring it through `usableForText` would assert a guarantee
/// nobody had measured. That is true of exactly one of `TeamLogoView`'s three
/// states — the `Circle().fill(color.opacity(0.15))` drawn *while* a crest
/// loads. The other two fall through to `initialsFallback`, which paints
///
///     Text(Self.badge(...)).foregroundStyle(color)
///
/// over a 20%-opacity disc. Those are the states reached when the crest url is
/// absent, the fetch fails, or the ESPN fallback fails — for a crest-less club,
/// every render. So the "tint" is the badge's letters, and it is the same
/// unreadable-number question arms 1–3 answered.
///
/// **Two directions, one ratio, and that is the point of grouping these four.**
/// Two of the sites paint the club's colour AS text on a white card
/// (`TeamLogoView.initialsFallback`, reached from `LadderCardView` and both
/// `MyStuffView` rows). Two paint WHITE text ON the club's colour
/// (`LadderCardView`'s no-crest branch, `TeamDetailView`'s 64pt hero tile).
/// They read as different contrast questions and they are not: the pair being
/// weighed is (white, colour) either way, so `(1.05)/(L + 0.05)` is the same
/// number and `TeamTextContrast.readableOnCard` already answers both. No second
/// helper and no second constant for the two halves to drift apart on —
/// `testTheFloorAnswersBothDirectionsWithOneRatio` is that claim as an
/// assertion rather than as a paragraph.
///
/// **Why every assertion is on a resolved HEX.** Arm 2's rule, unchanged: every
/// character is in the view hierarchy, spelled correctly, and read perfectly by
/// VoiceOver. Only the pixels are wrong. A test that the badge renders passes on
/// the bug.
///
/// **Still deliberately out**, so the next reader does not think it was missed:
/// `DiscoverView.teamBadge` fills a 36pt tile and draws **no letters on it** —
/// its label sits below the tile in the default text colour — so it remains the
/// shape question arm 3 described, and it stays out.
/// `EvolutionChartView.colorForOutcome` is a chart LINE plus a
/// `TeamLogoView`, has its own indexed palette to fall into, and is named as
/// arm 5 on #7036.
final class BadgeLettersResolveTeamColourThroughTheFloor7036Tests: XCTestCase {

    private typealias C = TeamTextContrast

    /// Fulham, Tottenham, Real Madrid, Lyon and 22 more store exactly this.
    private let whiteShirt = "#ffffff"
    /// Liverpool. Never the problem, and must stay untouched.
    private let legible = "#d11317"

    // MARK: - The ship, site by site

    func testTheLadderCardGivesAWhiteShirtedClubAVisibleBadge() {
        let hex = LadderCardTeamColour.badgeHex(whiteShirt)

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the ladder badge is still white letters on a white card")
        XCTAssertTrue(C.readableOnCard(hex),
                      "ladder badge colour \(hex) is under the 3:1 floor")
        XCTAssertEqual(hex, LadderCardTeamColour.fallbackHex,
                       "a floored colour must land on the card's OWN default, not a new colour")
    }

    func testTheTeamPageGivesAWhiteShirtedClubAVisibleIdentityTile() {
        let hex = TeamDetailTeamColour.logoTileHex(whiteShirt)

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the team page's 64pt tile is still white-on-white")
        XCTAssertTrue(C.readableOnCard(hex), "tile fill \(hex) is under the 3:1 floor")
        XCTAssertEqual(hex, TeamDetailTeamColour.fallbackHex)
    }

    func testMyStuffGivesAWhiteShirtedClubAVisibleCrestCircle() {
        let hex = MyStuffTeamTextColour.logoTintHex(whiteShirt)

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the My Stuff crest circle is still drawing white initials on white")
        XCTAssertTrue(C.readableOnCard(hex), "crest tint \(hex) is under the 3:1 floor")
        XCTAssertEqual(hex, MyStuffTeamTextColour.fallbackHex)
    }

    /// The floor is not a redesign. A club that was always legible keeps its
    /// brand colour to the byte, on all three.
    func testALegibleClubKeepsItsOwnColourEverywhere() {
        XCTAssertEqual(LadderCardTeamColour.badgeHex(legible).uppercased(), "#D11317")
        XCTAssertEqual(TeamDetailTeamColour.logoTileHex(legible).uppercased(), "#D11317")
        XCTAssertEqual(MyStuffTeamTextColour.logoTintHex(legible).uppercased(), "#D11317")
    }

    // MARK: - The claim that lets one helper serve two-directional contrast

    /// Two of these sites draw the colour as text on white; two draw white text
    /// on the colour. If those were different questions, one floor could not
    /// serve both and this arm would be wrong.
    ///
    /// They are the same question because the ratio is symmetric in its pair:
    /// WCAG's formula is (lighter + 0.05) / (darker + 0.05), and white is the
    /// lighter member in both readings. So the single predicate must agree with
    /// an independently-computed white-vs-colour ratio across the range, not
    /// just at the two ends.
    func testTheFloorAnswersBothDirectionsWithOneRatio() {
        // Spread deliberately across the floor: pure white (1.00), the pale blue
        // that looks fine (2.43), one just over (3.77), one comfortably over.
        for hex in ["#ffffff", "#6cace4", "#059669", "#d11317", "#000000"] {
            guard let l = C.relativeLuminance(hex) else {
                return XCTFail("\(hex) did not parse — the sweep is measuring nothing")
            }
            let whiteOnColour = (1.0 + 0.05) / (l + 0.05)

            XCTAssertEqual(C.contrastVsCardSurface(hex) ?? 0, whiteOnColour, accuracy: 0.0001,
                           "\(hex): colour-on-white and white-on-colour disagreed, so one floor cannot serve both")
            XCTAssertEqual(C.readableOnCard(hex), whiteOnColour >= C.minimumRatio,
                           "\(hex): the predicate and the ratio it is meant to express disagree")
        }
    }

    // MARK: - The fallbacks, which are how this arm could silently do nothing

    /// If a default were itself under the floor, every assertion above would
    /// still pass while the badge stayed blank — the floored branch would hand
    /// back a second unreadable colour.
    func testEverySurfaceDefaultClearsTheFloorItself() {
        XCTAssertTrue(C.readableOnCard(LadderCardTeamColour.fallbackHex),
                      "the ladder card's default is under 3:1 — flooring to it changes nothing a reader can see")
        XCTAssertTrue(C.readableOnCard(TeamDetailTeamColour.fallbackHex),
                      "the team page's default is under 3:1")
        XCTAssertTrue(C.readableOnCard(MyStuffTeamTextColour.fallbackHex),
                      "My Stuff's default is under 3:1")

        // Pinned, not merely "over the floor": a default nudged pale enough to
        // matter reddens here before it reaches a screen.
        XCTAssertEqual(C.contrastVsCardSurface(LadderCardTeamColour.fallbackHex) ?? 0, 3.77, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(TeamDetailTeamColour.fallbackHex) ?? 0, 4.83, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(MyStuffTeamTextColour.fallbackHex) ?? 0, 4.83, accuracy: 0.01)
    }

    /// 🪤 The ladder's default sits at **3.77:1** — the closest of the three to
    /// the 3.0 floor. If #5165's AA question is ever revisited and the floor
    /// moves to 4.5:1 for small text, this default stops clearing it and the
    /// badge goes quietly back to being unreadable in the floored branch. That
    /// is a real trap, so it fails here rather than on a screen.
    func testTheLaddersDefaultWouldNotSurviveAnAAFloorAndSaysSo() {
        let ratio = C.contrastVsCardSurface(LadderCardTeamColour.fallbackHex) ?? 0
        XCTAssertGreaterThanOrEqual(ratio, C.minimumRatio)
        XCTAssertLessThan(ratio, 4.5,
                          "DS.emeraldDark now clears AA — raise the floor here deliberately rather than by accident")
    }

    /// A colour that *looks* fine tells you nothing about its ratio. Celta
    /// Vigo's `#6cace4` is a pleasant blue at 2.43:1, and the population under
    /// the floor is 146 clubs, not the 26 pure-white ones.
    func testAPleasantLookingPaleBlueIsFlooredOnAllThree() {
        XCTAssertEqual(C.contrastVsCardSurface("#6cace4") ?? 0, 2.43, accuracy: 0.01)
        XCTAssertEqual(LadderCardTeamColour.badgeHex("#6cace4"), LadderCardTeamColour.fallbackHex)
        XCTAssertEqual(TeamDetailTeamColour.logoTileHex("#6cace4"), TeamDetailTeamColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamTextColour.logoTintHex("#6cace4"), MyStuffTeamTextColour.fallbackHex)
    }

    /// Absent and unparseable both mean "no colour to judge", and both must land
    /// on the default rather than on a crash or a transparent colour. `nil` is
    /// the common case here: `PlayoffJourney.teamColor` and
    /// `TeamFutureItem.matchedTeam` are both optional.
    func testAnAbsentOrUnparseableColourLandsOnTheDefault() {
        for bad in [nil, "", "not a colour", "#12345"] as [String?] {
            XCTAssertEqual(LadderCardTeamColour.badgeHex(bad), LadderCardTeamColour.fallbackHex,
                           "ladder: \(bad ?? "nil")")
            XCTAssertEqual(TeamDetailTeamColour.logoTileHex(bad), TeamDetailTeamColour.fallbackHex,
                           "team page: \(bad ?? "nil")")
            XCTAssertEqual(MyStuffTeamTextColour.logoTintHex(bad), MyStuffTeamTextColour.fallbackHex,
                           "my stuff: \(bad ?? "nil")")
        }
    }

    // MARK: - The wiring, which is the half no assertion above can reach

    /// Every helper above can be perfect while the view goes on painting
    /// `Color(hex: team.primaryColor ?? …)` — it compiles, it renders, and this
    /// file stays green. These scans are the only thing that fails.
    ///
    /// Each anchor is the exact string a mutant in
    /// `tools/native-267-mutations-7036-badges.py` writes back, so none of them
    /// is an absence that could never occur.
    func testTheLadderCardsGridInitRoutesThroughTheFloor() throws {
        let body = try String(contentsOf: Self.ladderCardURL, encoding: .utf8)

        XCTAssertTrue(body.contains("teamColor: Color(hex: LadderCardTeamColour.badgeHex(team.primaryColor))"),
                      "the ladder's gridTeam init is not resolving through the #7036 floor")
        XCTAssertFalse(body.contains("teamColor: team.primaryColor.map { Color(hex: $0) } ?? DS.emeraldDark"),
                       "the ladder badge is being painted from the raw primary_color again")
    }

    func testTheTeamPagesHeroTileRoutesThroughTheFloor() throws {
        let body = try String(contentsOf: Self.teamDetailURL, encoding: .utf8)

        XCTAssertTrue(body.contains(".fill(Color(hex: TeamDetailTeamColour.logoTileHex(team.primaryColor)))"),
                      "the team page's identity tile is not resolving through the #7036 floor")
        XCTAssertFalse(body.contains(".fill(Color(hex: team.primaryColor ?? \"#6B7280\"))"),
                       "the team page tile is being filled from the raw primary_color again")
    }

    /// Both My Stuff crest circles — the playoff-journey header and the merged
    /// future row. A count, not a `contains`: wiring one and leaving the other
    /// is the likeliest half-fix, and `contains` cannot see it.
    func testBothMyStuffCrestCirclesRouteThroughTheFloor() throws {
        let body = try String(contentsOf: Self.myStuffURL, encoding: .utf8)

        // TWO, not three: the anchor carries the type prefix, and the
        // declaration inside `enum MyStuffTeamTextColour` does not repeat it. The
        // first draft of this line said three "for the declaration too" and the
        // suite reddened on the real tree — which is the guard working, and the
        // reason a count is written against a measured file rather than against
        // an expectation of one.
        XCTAssertEqual(body.components(separatedBy: "MyStuffTeamTextColour.logoTintHex(").count - 1, 2,
                       "expected BOTH crest circles — one of the two is still raw")
        XCTAssertFalse(body.contains("color: Color(hex: item.matchedTeam?.primaryColor ?? \"#6b7280\")"),
                       "the merged-future row's crest is raw again")
        XCTAssertFalse(body.contains("color: Color(hex: journey.teamColor ?? \"#6b7280\")"),
                       "the playoff-journey card's crest is raw again")
    }

    /// `TeamLogoView` cannot enforce the contract in its type — several callers
    /// legitimately pass a colour that never came from a team row. So the
    /// contract lives in its docstring, and this asserts the docstring is still
    /// there to be read: a silent deletion would leave the next caller with a
    /// `color:` parameter that looks like a tint and is not.
    func testTheLogoViewStillStatesThatItsColourIsDrawnAsText() throws {
        let body = try String(contentsOf: Self.teamLogoURL, encoding: .utf8)
        XCTAssertTrue(body.contains("This is drawn as TEXT, not only as a tint"),
                      "TeamLogoView's #7036 contract has been removed from the parameter it governs")
        XCTAssertTrue(body.contains("Text(Self.badge(teamName: teamName, opponentName: opponentName, sportKey: sportKey))"),
                      "initialsFallback no longer paints the badge — the contract above it may be stale")
        XCTAssertTrue(body.contains(".foregroundStyle(color)"),
                      "initialsFallback no longer draws the letters IN `color`, so re-read the contract")
    }

    /// Strawman: the scans read real files with real content, so the
    /// `XCTAssertFalse`s above cannot be passing because a read failed.
    func testTheSourceScansAreReadingTheFilesTheyThinkTheyAre() throws {
        for url in [Self.ladderCardURL, Self.teamDetailURL, Self.myStuffURL, Self.teamLogoURL] {
            let body = try String(contentsOf: url, encoding: .utf8)
            XCTAssertGreaterThan(body.count, 3_000, "\(url.lastPathComponent) read back far too small")
            XCTAssertTrue(body.contains("import SwiftUI"), "\(url.lastPathComponent) is not the Swift file")
        }
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given (`/tmp/…`) while
    /// `FileManager` hands back the standardised one (`/private/tmp/…`), so any
    /// prefix arithmetic between the two silently produces a path with its
    /// middle eaten out. Going straight up the URL avoids the subtraction.
    private static var appRoot: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
    }

    private static var ladderCardURL: URL { appRoot.appendingPathComponent("Components/LadderCardView.swift") }
    private static var teamLogoURL: URL { appRoot.appendingPathComponent("Components/TeamLogoView.swift") }
    private static var teamDetailURL: URL { appRoot.appendingPathComponent("Views/TeamDetailView.swift") }
    private static var myStuffURL: URL { appRoot.appendingPathComponent("Views/MyStuffView.swift") }
}
