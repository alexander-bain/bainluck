import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/236 (#7036, second arm) — the two game CARDS resolve their team pair
/// through the contrast floor, not straight off the palette.
///
/// **What a reader saw.** The first arm of #7036 put a WCAG 3:1 floor under the
/// event page's Championship Path. Two other surfaces resolve the same pair the
/// same way and got none of it, and they are the more-travelled ones:
///
///   * `EventCardView` — the Sports tab, My Stuff and the feed list. Photographed
///     on production 2026-09-18 22:58Z (`artifacts/native-236/BEFORE-soccer-s1800.png`,
///     `bainluck://category/soccer`): the **Rennes v Lyon** fixture card rendered
///     with **no win probability at all**, sitting directly between Strasbourg/Paris FC
///     (`48%`), Torino/Bologna (`49%`) and Alavés/Athletic Bilbao (`58%`). Lyon's
///     stored `primary_color` is `#ffffff` and Lyon is the home side, so the one
///     number that card prints was painted white on the white card. The bar told
///     the same lie more quietly: Lyon's segment is white on a `secondary.opacity(0.08)`
///     track, so the split reads as an empty capsule.
///   * `NativeEventDiscoverCard` — the Discover feed, which is the app's default
///     landing surface. It prints BOTH percentages in these colours, and in its
///     collapsed one-number branch the side's NAME as well.
///
/// **Why this file executes the card rather than scanning its source.**
/// `TeamTextContrastTests.testTheEventPageIsWiredThroughTheFloor` asserts on the
/// text of `EventDetailView` because the funnel there is a `private` view
/// property no test can call. These two cards expose `barColorHexes`, so the
/// wiring can be *driven* on the payload production actually serves — strictly
/// stronger than a substring, and it cannot be satisfied by a comment.
///
/// **The mutant this exists to kill** is not an exotic one. Reverting either card
/// to `ProbabilityBarPalette.colors(awayHex: event.awayTeamData?.primaryColor, …)`
/// compiles, renders, and leaves every test in `TeamTextContrastTests` and
/// `ProbabilityBarPaletteTests` green — the helper is correct in both worlds; only
/// the call site moved. So each assertion below is on the RESOLVED COLOUR. An
/// assertion that the percentage text exists in the hierarchy passes on the bug
/// (that is exactly how the web arm, #5165, survived into #5696), and so does a
/// screen reader.
final class CardsResolveTeamColourThroughTheFloor7036Tests: XCTestCase {

    private typealias C = TeamTextContrast

    /// Lyon `#ffffff` at home, Rennes `#ef2f24` away — the stored values behind
    /// the photographed card, read from production the same hour
    /// (`teams.primary_color`, event `15305933`, Ligue 1, 2026-09-19 18:45Z).
    ///
    /// Team names are parameters and never appended into `body`: Foundation keeps
    /// the FIRST of a duplicate JSON key, so a caller "overriding" a name by
    /// adding a second one silently asserts about the default team instead.
    /// (`TeamAvatarLadderTests` paid for that one; not paying it twice.)
    private func event(awayHex: String?, homeHex: String?,
                       away: String = "Rennes", home: String = "Lyon") throws -> FeedEventData {
        func teamData(_ hex: String?) -> String {
            hex.map { "{ \"primary_color\": \"\($0)\" }" } ?? "{ }"
        }
        let json = """
        {
          "id": 15305933,
          "sport": "soccer_france_ligue_one",
          "home_team": "\(home)",
          "away_team": "\(away)",
          "home_team_data": \(teamData(homeHex)),
          "away_team_data": \(teamData(awayHex))
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    @MainActor
    private func sportsRow(_ e: FeedEventData) -> EventCardView {
        EventCardView(event: e, reason: nil)
    }

    @MainActor
    private func discoverCard(_ e: FeedEventData) -> NativeEventDiscoverCard {
        NativeEventDiscoverCard(event: e, feedContext: nil, expandedContext: nil,
                                navigationPath: .constant(NavigationPath()))
    }

    // MARK: - The ship: the photographed card

    @MainActor
    func testTheSportsRowGivesLyonAVisibleColourOnTheExactPayloadItRendered() throws {
        let e = try event(awayHex: "#ef2f24", homeHex: "#ffffff")
        let pair = sportsRow(e).barColorHexes

        XCTAssertNotEqual(pair.home.uppercased(), "#FFFFFF",
                          "Lyon's percentage is still being printed white on the white card")
        XCTAssertTrue(C.readableOnCard(pair.home),
                      "home \(pair.home) is under the 3:1 floor — the number is there and cannot be read")
        XCTAssertEqual(pair.away.uppercased(), "#EF2F24",
                       "Rennes was never the problem; a floor that repaints a legible club is a redesign")
    }

    @MainActor
    func testTheDiscoverCardGivesLyonAVisibleColourOnTheSamePayload() throws {
        // Discover is the default landing surface and prints BOTH numbers, so the
        // same stored colour is worse here, not better.
        let e = try event(awayHex: "#ef2f24", homeHex: "#ffffff")
        let pair = discoverCard(e).barColorHexes

        XCTAssertNotEqual(pair.home.uppercased(), "#FFFFFF")
        XCTAssertTrue(C.readableOnCard(pair.home),
                      "home \(pair.home) is invisible on Discover's white card")
        XCTAssertEqual(pair.away.uppercased(), "#EF2F24")
    }

    // MARK: - Both cards, every stored colour, both slots

    @MainActor
    func testNeitherCardCanEverResolveAnInvisibleSide() throws {
        // The property, not the specimen. `#ffffff` is 26 clubs, but re-measured on
        // production 2026-09-18 23:10Z the same column has 1,464 parseable values
        // and **146 below the 3:1 floor** — Tottenham, Real Madrid, Leeds, Sevilla
        // and Valencia are all on this weekend's board. (#7036's body cites 44 for
        // this figure, attributing it to #5696; 44 does not reproduce today and
        // `TeamTextContrast`'s own docstring already said 146. Measured, not
        // inherited.) Sweeping
        // both slots also catches a fix applied to one side only, which is how the
        // Championship Path looked half-correct for a day.
        let stored: [String?] = [nil, "", "#ffffff", "#FFFFFF", "ffffff", "#fffffe",
                                 "#ffff00", "#fdb927", "#6cace4", "#ef2f24", "#000000",
                                 "not-a-color"]
        for away in stored {
            for home in stored {
                let e = try event(awayHex: away, homeHex: home)
                for (label, pair) in [("sports row", sportsRow(e).barColorHexes),
                                      ("discover card", discoverCard(e).barColorHexes)] {
                    let where_ = "\(label): away \(String(describing: away)) / home \(String(describing: home))"
                    XCTAssertTrue(C.readableOnCard(pair.away), "\(where_) -> away \(pair.away) is invisible")
                    XCTAssertTrue(C.readableOnCard(pair.home), "\(where_) -> home \(pair.home) is invisible")
                    XCTAssertTrue(ProbabilityBarPalette.distinguishable(pair.away, pair.home),
                                  "\(where_) -> \(pair.away)/\(pair.home) collapsed #2902's pair contract")
                }
            }
        }
    }

    // MARK: - What the fix must NOT do

    @MainActor
    func testACardOfTwoLegibleClubsIsUntouchedByTheFloor() throws {
        // The blast radius. 1,318 of the 1,464 clubs with a parseable stored colour
        // clear the floor, and every one must render exactly as it did yesterday —
        // otherwise this is a recolouring of the league shipped inside a bug fix.
        // Aston Villa `#660e36` is 12.49:1 and Rennes `#ef2f24` is 4.12:1.
        let e = try event(awayHex: "#660e36", homeHex: "#ef2f24", away: "Aston Villa", home: "Rennes")
        for pair in [sportsRow(e).barColorHexes, discoverCard(e).barColorHexes] {
            XCTAssertEqual(pair.away.uppercased(), "#660E36")
            XCTAssertEqual(pair.home.uppercased(), "#EF2F24")
        }
    }

    @MainActor
    func testAPaleClubIsRepaintedToo_AndThatIsTheDesignNotAnOverreach() throws {
        // ⭐ The honest half of the line above, written down because the first draft
        // of this file got it wrong and the suite caught it.
        //
        // The floor is not a special case for the 26 clubs storing `#ffffff` — it is
        // a floor, and 146 clubs sit under it. **Celta Vigo `#6cace4` is 2.43:1**, so
        // its `53%` on the Sports tab (visible in `BEFORE-soccer-s1200.png`, a card
        // that reads as perfectly fine at a glance) was pale blue on white and is now
        // slate. That is a real, deliberate, reader-visible change to a card nobody
        // filed a bug about, and pretending the fix only touches white clubs is how it
        // would arrive as a surprise later.
        //
        // What must stay true is the CONTRACT, not the old pixel: the replacement is
        // the palette's existing slot default (not a new colour chosen here), it is
        // legible, and the pair still reads apart.
        XCTAssertFalse(C.readableOnCard("#6cace4"), "if Celta Vigo ever clears the floor, retire this test")
        let e = try event(awayHex: "#6cace4", homeHex: "#ef2f24", away: "Celta Vigo", home: "Rennes")
        for pair in [sportsRow(e).barColorHexes, discoverCard(e).barColorHexes] {
            XCTAssertEqual(pair.away, ProbabilityBarPalette.awayDefault,
                           "a floored side takes the palette's own slot default, never a colour invented here")
            XCTAssertEqual(pair.home.uppercased(), "#EF2F24", "the legible side is left alone")
            XCTAssertTrue(ProbabilityBarPalette.distinguishable(pair.away, pair.home))
        }
    }

    @MainActor
    func testBothCardsAgreeWithTheEventPageOnEveryPair() throws {
        // Three surfaces, one answer. The reader moves Discover -> Sports row ->
        // event page in one journey, and a club that is slate on two of them and
        // blue on the third is its own defect. Pinning agreement to the SHARED
        // entry point is also what stops the next surface growing a fourth copy.
        let stored: [String?] = [nil, "#ffffff", "#ffff00", "#ef2f24", "#2563EB", "not-a-color"]
        for away in stored {
            for home in stored {
                let e = try event(awayHex: away, homeHex: home)
                let expected = C.cardColorHexes(awayHex: away, homeHex: home)
                XCTAssertEqual(sportsRow(e).barColorHexes.away, expected.away)
                XCTAssertEqual(sportsRow(e).barColorHexes.home, expected.home)
                XCTAssertEqual(discoverCard(e).barColorHexes.away, expected.away)
                XCTAssertEqual(discoverCard(e).barColorHexes.home, expected.home)
            }
        }
    }

    // MARK: - The one hop XCTest cannot execute

    /// `barColorHexes` is the decision and is driven directly by every test above.
    /// Turning that pair into two `Color`s is a `private` derivation inside a
    /// SwiftUI view, and no XCTest can call it — so a card whose hex pair is
    /// perfectly correct can still paint both segments the same side's colour.
    /// The mutation run found exactly that and nothing else
    /// (`tools/native-236-mutations-7036-cards.py`, mutant 10).
    ///
    /// Asserted on the source, which is the pattern arm 1 already set for this
    /// class of hop (`TeamTextContrastTests.testTheEventPageIsWiredThroughTheFloor`).
    /// A substring guard is weaker than an executed one and is used here only
    /// because the alternative is no guard at all.
    func testEachCardSpendsBothHalvesOfItsHexPair() throws {
        for (name, url) in [("EventCardView", Self.sportsRowURL),
                            ("DiscoverEventCard", Self.discoverCardURL)] {
            let source = try String(contentsOf: url, encoding: .utf8)
            let funnel = try XCTUnwrap(
                source.range(of: "private var barColors: (away: Color, home: Color) {"),
                "\(name).barColors has been renamed — re-aim this guard, do not delete it"
            )
            let body = source[funnel.lowerBound...].prefix(300)
            XCTAssertTrue(body.contains("Color(hex: hexes.away)"),
                          "\(name) no longer paints the away segment with the away hex")
            XCTAssertTrue(body.contains("Color(hex: hexes.home)"),
                          "\(name) no longer paints the home segment with the home hex")
        }
    }

    /// Resolved from `#filePath`, never by walking up from the working directory.
    ///
    /// 🪤 `#filePath` keeps the spelling the compiler was handed (`/tmp/…`) while
    /// `FileManager` returns the standardised one (`/private/tmp/…`), so prefix
    /// arithmetic between the two silently yields a path with its middle eaten
    /// out. Going straight up the URL avoids the subtraction. (Banked by arm 1.)
    private static var componentsDir: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck/Components")
    }
    private static var sportsRowURL: URL { componentsDir.appendingPathComponent("EventCardView.swift") }
    private static var discoverCardURL: URL { componentsDir.appendingPathComponent("DiscoverEventCard.swift") }

    // MARK: - The guard is aimed at something that can fail

    @MainActor
    func testAWhiteClubIsActuallyTheInvisibleCaseBeforeTheFloor() throws {
        // ⭐ Without this, every assertion above passes on a rig where the payload
        // never carried `#ffffff` in the first place — a decoder key typo
        // (`home_team_data` vs `homeTeamData`) hands both slots `nil`, the palette
        // returns its defaults, and the defaults are legible. So: prove the raw
        // payload reaches the card as white, and that the palette WITHOUT the
        // floor paints it white. This is the strawman guard for this file.
        let e = try event(awayHex: "#ef2f24", homeHex: "#ffffff")
        XCTAssertEqual(e.homeTeamData?.primaryColor, "#ffffff",
                       "the fixture is not carrying Lyon's stored colour — every other test here is vacuous")
        let unfloored = ProbabilityBarPalette.pair(awayHex: e.awayTeamData?.primaryColor,
                                                   homeHex: e.homeTeamData?.primaryColor)
        XCTAssertEqual(unfloored.home.uppercased(), "#FFFFFF",
                       "the palette alone must still return white here — otherwise the floor is guarding nothing")
        XCTAssertFalse(C.readableOnCard(unfloored.home),
                       "white on the white card must read as unreadable, or the floor is miscalibrated")
    }
}
