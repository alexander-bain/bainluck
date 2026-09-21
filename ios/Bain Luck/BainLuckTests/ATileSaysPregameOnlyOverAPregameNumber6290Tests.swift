import XCTest
@testable import Bain_Luck

/// #6290 — a tile captioned `PRE-GAME` printed the line RIGHT NOW.
///
/// THE PHOTOGRAPH THE ISSUE CARRIES: event 15312201 (Yankees v Twins, `live`),
/// the Runs map's `PRE-GAME` tile at **4.5** in the 7th and **11.4** 55 minutes
/// later — it moved 6.9 runs in step with the score, because it was
/// `current_odds.over_under`. A pre-game number cannot move during the game.
///
/// RE-MEASURED ON A LIVE SPECIMEN BEFORE ANY CODE WAS WRITTEN, 2026-09-20
/// 18:35 PT, event 14780544 (Colts 13 at Chiefs 10, `live`, 37:45 left):
///
/// ```
/// GET /api/events/14780544
///   opening_odds.over_under  45.5      <- the pre-game total
///   current_odds.over_under  53.6      <- what the tile drew
/// ```
///
/// and photographed on the phone at 18:27 PT (`artifacts-native-020/`):
///
/// ```
///   n278-before-2150.png   PRE-GAME 55.5 …  "Pace projects -2.5 vs pre-game expectation."
///                          1st half total map   PRE-GAME 31.5
///                          2nd half total map   PRE-GAME 20.5
///   n278-after-2150.png    PRE-GAME 45.5 …  "Pace projects +19.5 vs pre-game expectation."
///                          both half tiles withheld, rails and distributions kept
/// ```
///
/// 🟢 **WHAT CHANGED IS THAT THERE IS NOW SOMETHING HONEST TO DRAW.**
/// ``MarketMapRail/drawsPregameMarker(canStillBeGraded:)`` records the opposite
/// as measured on 2026-09-08 — *"`GET /api/events/{id}` does not serve them …
/// only `/debug` emits them"* — and #5414 (closed 2026-09-12) put
/// `opening_odds.over_under` on the detail payload for exactly this tile. The
/// column is a real pre-game value: `_update_opening_odds`
/// (`backend/app/tasks/odds_polling.py`) returns without writing once
/// `commence_time` has passed or the status leaves `scheduled`.
final class ATileSaysPregameOnlyOverAPregameNumber6290Tests: XCTestCase {

    // The live NFL specimen, in the units the payload serves them in.
    private let servedOpening = 45.5
    private let liveLine = 53.6

    // MARK: - The rule

    /// THE DEFECT, stated as the thing that must not happen again: while the
    /// game is on, the tile draws the served opening and NOT the live line.
    ///
    /// Both halves are asserted. "Equals 45.5" alone passes for a function that
    /// returns a constant; "is not 53.6" alone passes for one that returns nil.
    func testALiveTileDrawsTheServedOpeningAndNotTheLineRightNow() {
        let drawn = MarketMapRail.pregameLine(
            isLive: true, opening: servedOpening, current: liveLine
        )
        XCTAssertEqual(drawn, servedOpening,
                       "the PRE-GAME tile of a live game must name the pre-game total")
        XCTAssertNotEqual(drawn, liveLine,
                          "53.6 is current_odds.over_under — the line right now, which is what #6290 photographed")
    }

    /// A live card with no served opening draws NO tile.
    ///
    /// This is the arm every half card takes: the payload carries one opening
    /// total for the whole game, so `1st half total map` has nothing to name and
    /// #3823's rule applies unchanged — a number whose tense you cannot vouch for
    /// is worse than no number.
    func testALiveTileWithNoServedOpeningDrawsNothing() {
        XCTAssertNil(MarketMapRail.pregameLine(isLive: true, opening: nil, current: liveLine),
                     "with no opening to name, the live tile is withheld rather than filled with the live line")
    }

    /// BEFORE THE OFF NOTHING MOVES. A scheduled card keeps drawing the line it
    /// has always drawn, even where an opening is also served — pre-game the
    /// current line IS the pre-game line, and re-pointing every scheduled card at
    /// a column that stops updating at kickoff would be a second change wearing
    /// this one's justification.
    func testAScheduledTileIsUnchangedByTheServedOpening() {
        let currentBeforeTheOff = 46.5
        XCTAssertEqual(
            MarketMapRail.pregameLine(isLive: false, opening: servedOpening, current: currentBeforeTheOff),
            currentBeforeTheOff,
            "a scheduled card draws the line it drew before #6290"
        )
        XCTAssertEqual(
            MarketMapRail.pregameLine(isLive: false, opening: nil, current: currentBeforeTheOff),
            currentBeforeTheOff
        )
        XCTAssertNil(MarketMapRail.pregameLine(isLive: false, opening: servedOpening, current: nil),
                     "and it draws nothing where it drew nothing — the opening is not a new source for it")
    }

    /// The two inputs are only distinguishable where they DISAGREE, so every
    /// case above is fed a pair that differs. This states it as its own
    /// assertion so a future edit that makes the fixtures equal fails here
    /// rather than quietly making three tests vacuous.
    func testTheFixturesDisagree() {
        XCTAssertNotEqual(servedOpening, liveLine,
                          "a specimen whose opening equals its live line cannot tell the two rules apart")
    }

    // MARK: - The mirror

    /// #3503's empty-chrome guard has to move with the marker block, and this is
    /// the case that proves it does: a live card with no rungs, no served opening
    /// and no scoreboard now draws NOTHING, where before the fix it was judged
    /// non-empty on a line tile it would go on to render.
    ///
    /// The predicate is fed through ``MarketMapRail/pregameLine(isLive:opening:current:)``
    /// exactly as `MarketMapView` feeds it, so the mirror is asserted on the
    /// composition and not on a re-statement of it.
    func testTheEmptyChromeGuardFollowsTheTileItGuards() {
        let liveWithNoOpening = MarketMapRail.pregameLine(isLive: true, opening: nil, current: liveLine)

        XCTAssertTrue(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false,
            lineMarker: liveWithNoOpening,
            isLive: true, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false
        ), "a rail, an axis and nothing on it — the card must not draw")

        // …and the same card keeps drawing as soon as it has real numbers.
        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false,
            lineMarker: liveWithNoOpening,
            isLive: true, isDone: false,
            hasScoreboardTotal: true, hasProjectedTotal: true
        ), "ACTUAL and PROJECTED are still two real numbers")

        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false,
            lineMarker: MarketMapRail.pregameLine(isLive: true, opening: servedOpening, current: liveLine),
            isLive: true, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false
        ), "a served opening is itself a number worth a card")
    }

    // MARK: - Every site, not just the photographed one

    /// THE BLANKET RULE. `MarketMapView` prints `PRE-GAME` on three tiles — the
    /// full totals map, the half totals map and the half margin map — and #6290
    /// was photographed on two of them in one frame. A fourth tile added later
    /// without the helper is the way this comes back, so the two counts are held
    /// equal rather than the photographed site being pinned alone.
    ///
    /// 🪤 **THE SCAN READS CODE, NOT THE FILE.** Both needles appear in the
    /// comments that explain them — a raw-file scan here would be a guard
    /// grading its own explanation.
    func testEveryPregameTileInTheMapsRoutesThroughTheRule() throws {
        let code = try Self.code(at: "Bain Luck/Components/MarketMapView.swift")
        let labels = Self.occurrences(of: "\"PRE-GAME\"", in: code)
        let routed = Self.occurrences(of: "MarketMapRail.pregameLine(", in: code)

        XCTAssertEqual(labels, 3, "MarketMapView draws three PRE-GAME tiles: full totals, half totals, half margin")
        XCTAssertEqual(routed, labels + 1,
                       """
                       every PRE-GAME tile takes its value from pregameLine — a tile that does not is #6290 again. \
                       The one extra call is the empty-chrome mirror in totalMapIsEmptyChrome, which has to ask the \
                       same question the full card's tile asks.
                       """)
    }

    /// The Projected-scoring card's live strip is the second site, and it is not
    /// a tile: it is a BAR labelled "Pre-game" plus a sentence comparing the pace
    /// against it ("Pace projects +19.5 vs pre-game expectation"). Both read one
    /// value, and before this fix that value was ``centerLine`` — the live
    /// ladder's coin-flip rung. The strip cannot be asserted without rasterising
    /// it, so what is pinned is that `liveStrip` no longer sees the old value at
    /// all: its parameter is the optional pre-game total, and `ouLine` is gone
    /// from its body.
    func testTheLiveStripComparesAgainstThePregameTotal() throws {
        let code = try Self.code(at: "Bain Luck/Components/TotalPointsSpectrumView.swift")

        // BOTH functions, because the value is chosen in one and spent in the
        // other: pinning only `liveStrip` leaves `projectionStrip` free to hand
        // it the live line again under the new parameter's name.
        for name in ["projectionStrip", "liveStrip"] {
            let body = try XCTUnwrap(Self.function(named: name, in: code),
                                     "\(name) must still exist — it is the strip this issue photographed")
            XCTAssertTrue(body.contains("pregameTotal"),
                          "\(name) reads the served opening, not a line of its own")
            XCTAssertFalse(body.contains("centerLine"),
                           "`centerLine` is the live ladder's coin-flip rung — the number #6290 photographed under the word Pre-game")
            XCTAssertFalse(body.contains("ouLine ="),
                           "and the local that held it is gone, not renamed around")
        }

        XCTAssertTrue(code.contains("MarketMapRail.pregameLine("),
                      "and the value itself comes from the shared rule, not a second copy of it")
    }

    // MARK: - The wire

    /// THE HALF THAT MAKES THE REST REACHABLE. Every rule above is inert unless
    /// the number actually arrives, and it arrives through one snake-cased key on
    /// a struct that had no field for it until this fix — the exact shape that
    /// decodes to `nil` forever without anything failing.
    ///
    /// The fixture is `GET /api/events/14780544`'s own `opening_odds` object,
    /// read from production 2026-09-20 18:35 PT and quoted verbatim.
    func testTheServedOpeningTotalDecodes() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let opening = try decoder.decode(OpeningOdds.self, from: Data("""
        {"home_probability": 0.7095, "away_probability": 0.2905,
         "spread": -6.0, "over_under": 45.5, "favorite": "home"}
        """.utf8))

        XCTAssertEqual(opening.overUnder, 45.5,
                       "`over_under` reaches `overUnder` through .convertFromSnakeCase")
        XCTAssertEqual(opening.homeProbability, 0.7095, "and nothing already decoded moves")

        // A payload from a deploy older than #5414 still decodes, to nil — which
        // is the `opening: nil` arm above, not a crash.
        let older = try decoder.decode(OpeningOdds.self, from: Data("""
        {"home_probability": 0.7095, "away_probability": 0.2905, "favorite": "home"}
        """.utf8))
        XCTAssertNil(older.overUnder)
    }

    /// And that it is handed to both cards. Neither view can be rendered in a
    /// unit test, so what is pinned is the wiring the page does: the totals map
    /// and the Projected-scoring card each take the OPENING total, and neither is
    /// quietly passed the current one.
    func testThePageHandsBothCardsTheOpeningTotal() throws {
        let code = try Self.code(at: "Bain Luck/Views/EventDetailView.swift")
        XCTAssertEqual(
            Self.occurrences(of: "openingOverUnder: event.openingOdds?.overUnder", in: code), 2,
            "MarketMapView and TotalPointsSpectrumView both read opening_odds — a site wired to nil is a fix that does nothing"
        )
        XCTAssertEqual(
            Self.occurrences(of: "openingOverUnder: event.currentOdds?.overUnder", in: code), 0,
            "and neither is handed the live line under the opening's name"
        )
    }

    // MARK: - Reading the source

    private static func code(at path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)      // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()               // …/BainLuckTests
            .deletingLastPathComponent()               // …/ios/Bain Luck
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    private static func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    /// The body of one declaration — a `func` or a computed `var`, since the
    /// strip is one of each — from its signature to the line that closes it at
    /// the same indentation. Enough to tell what a declaration reads;
    /// deliberately not a parser.
    private static func function(named name: String, in code: String) -> String? {
        let lines = code.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        guard let start = lines.firstIndex(where: {
            $0.contains("func \(name)(") || $0.contains("var \(name):")
        }) else { return nil }
        let indent = lines[start].prefix(while: { $0 == " " }).count
        let close = String(repeating: " ", count: indent) + "}"
        guard let end = lines[(start + 1)...].firstIndex(where: { $0 == close }) else { return nil }
        return lines[start...end].joined(separator: "\n")
    }
}
