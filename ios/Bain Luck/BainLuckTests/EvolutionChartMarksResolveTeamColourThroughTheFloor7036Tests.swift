import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/268 (#7036, fifth arm) — the Evolution chart's per-outcome marks
/// resolve a stored team colour through the contrast floor.
///
/// **What this arm is, in one sentence.** `EvolutionChartView.colorForOutcome`
/// is a choke point: the plotted LINE, the crosshair tooltip's dot, the
/// leaderboard row's dot and the `color:` handed to `TeamLogoView` — whose
/// `initialsFallback` paints the outcome's letters in it — all come out of that
/// one function, all sit on `Color.cardBackground`, and none of them had a
/// floor. One floor under one function covers four marks.
///
/// **Why it was arm 5 and not arm 3.** Arm 3 deferred it with a reason that
/// still holds: it is a mark on a chart rather than a number in a card, it
/// already carries an indexed palette to fall into, and that palette was a
/// `[Color]`, which cannot be compared in a test. Turning it into `[String]` is
/// what makes the resolution assertable, and that was its own change.
///
/// **⭐ Unlike arm 4, this one is reachable from stored data, and it was
/// measured before it was claimed.** Arm 4's population turned out to be the
/// crest-FETCH-FAILURE path — zero rows reach it from stored data. Arm 5 was
/// therefore measured first rather than inferred from the `if`. On production,
/// 2026-09-20, `futures_outcomes` ⋈ `teams`: of **16,739** chart-eligible
/// outcome rows carrying a stored colour, **1,054 — 6.3%, across 73 clubs — are
/// under 3:1**. Two served payloads confirm it end to end:
///
/// * `/api/futures/57777176/probability-timeline` — *NBA: Steph Curry Next
///   Team* serves Golden State at **97.4%** in `#fdb927`, **1.73:1**. The
///   leader's line, the one line the chart exists to show.
/// * `/api/futures/53672/probability-timeline` — *NFC South Division Winner*
///   serves four outcomes of which **two** are under the floor: New Orleans
///   `#d3bc8d` (1.85:1) and Carolina `#7bafd4` (2.35:1).
///
/// That second payload is this file's main fixture, colour for colour, because
/// it is a board a reader can open today where half the lines are missing.
///
/// **Every assertion is on a resolved HEX.** #7036's standing rule, unchanged
/// since arm 2: every outcome is in the view hierarchy, named correctly, read
/// correctly by VoiceOver, and its probability is right. Only the pixels are
/// wrong. A test that the chart renders four series passes on the bug.
final class EvolutionChartMarksResolveTeamColourThroughTheFloor7036Tests: XCTestCase {

    private typealias C = TeamTextContrast
    private typealias E = EvolutionOutcomeColour

    // Colours as production serves them, not as anyone remembers them.
    private let tampaBay = "#bd1c36"       // 6.21:1 — legible, must not move
    private let newOrleans = "#d3bc8d"     // 1.85:1
    private let carolina = "#7bafd4"       // 2.35:1
    private let goldenState = "#fdb927"    // 1.73:1
    private let whiteShirt = "#ffffff"     // 1.00:1 — 13 clubs on this join

    // MARK: - The specimen board

    /// `/api/futures/53672/probability-timeline`, served 2026-09-20: four
    /// outcomes, two under the floor, one over it, one with no stored colour at
    /// all. The last is load-bearing — it is the case that already worked, and
    /// the floor must leave it exactly where it was.
    private func nfcSouth() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "Tampa Bay", colour: tampaBay),
            outcome(name: "New Orleans", colour: newOrleans),
            outcome(name: "Carolina", colour: carolina),
            outcome(name: "Atlanta", colour: nil),
        ]
    }

    func testEveryLineOnTheNFCSouthBoardIsVisible() {
        let board = nfcSouth()

        for (index, o) in board.enumerated() {
            let hex = E.markHex(name: o.name, outcomes: board, index: index)
            XCTAssertTrue(C.readableOnCard(hex),
                          "\(o.name) is drawn in \(hex), which is under the 3:1 floor")
        }
    }

    /// The two under-floor sides land on the slot their POSITION would have had,
    /// not on some new colour chosen here.
    func testAFlooredOutcomeTakesItsOwnPaletteSlot() {
        let board = nfcSouth()

        XCTAssertEqual(E.markHex(name: "New Orleans", outcomes: board, index: 1),
                       E.paletteHexes[1],
                       "New Orleans should fall into the slot an uncoloured second line takes")
        XCTAssertEqual(E.markHex(name: "Carolina", outcomes: board, index: 2),
                       E.paletteHexes[2])
    }

    /// The floor is not a redesign. A club that was always legible keeps its
    /// brand colour to the byte, and an outcome with no colour keeps the palette
    /// slot it already had.
    func testTheBoardsOtherTwoOutcomesAreUntouched() {
        let board = nfcSouth()

        XCTAssertEqual(E.markHex(name: "Tampa Bay", outcomes: board, index: 0), tampaBay)
        XCTAssertEqual(E.markHex(name: "Atlanta", outcomes: board, index: 3),
                       E.paletteHexes[3])
    }

    /// 🔴 The case that makes this a p-anything rather than a tidy-up: the
    /// LEADER of a chart, at 97%, drawn in a gold that is 1.73:1 on white.
    func testTheLeaderOfAChartCannotBeTheInvisibleLine() {
        let board = [outcome(name: "Golden State Warriors", colour: goldenState)]
        let hex = E.markHex(name: "Golden State Warriors", outcomes: board, index: 0)

        XCTAssertNotEqual(hex.lowercased(), goldenState,
                          "the 97% leader is still painted in 1.73:1 gold")
        XCTAssertEqual(hex, E.paletteHexes[0],
                       "and it should take the leader slot, which is what an uncoloured leader takes")
        XCTAssertTrue(C.readableOnCard(hex))
    }

    // MARK: - The fallback cannot itself be the invisible case

    /// Asserted rather than trusted, so a future palette edit that drops a
    /// pastel in fails here instead of in a render nobody photographs.
    func testEveryPaletteSlotClearsTheFloorItself() {
        XCTAssertEqual(E.paletteHexes.count, 10)

        for hex in E.paletteHexes {
            guard let ratio = C.contrastVsCardSurface(hex) else {
                return XCTFail("palette entry \(hex) does not parse")
            }
            XCTAssertGreaterThanOrEqual(
                ratio, C.minimumRatio,
                "palette entry \(hex) is \(String(format: "%.2f", ratio)):1 — flooring onto it "
                + "would swap one invisible colour for another")
        }
    }

    /// Two floored outcomes at different display positions must not collapse
    /// onto one colour — the reason the fallback is indexed rather than a single
    /// default. The chart's whole job is telling lines apart.
    func testFlooringTwoOutcomesDoesNotCollapseThemOntoOneColour() {
        let board = [
            outcome(name: "Fulham", colour: whiteShirt),
            outcome(name: "Tottenham", colour: whiteShirt),
            outcome(name: "Leeds", colour: whiteShirt),
        ]
        let hexes = board.enumerated().map {
            E.markHex(name: $1.name, outcomes: board, index: $0)
        }

        XCTAssertEqual(Set(hexes).count, 3,
                       "three white-shirted clubs resolved to \(hexes) — the chart cannot be read")
    }

    // MARK: - The lookup, and the rows that have no colour to look up

    /// The colour is found by NAME. A lookup that ignored the name and took the
    /// first outcome would paint the whole board in one colour and pass every
    /// assertion above that only checks legibility.
    func testTheColourIsFoundByNameNotByPosition() {
        let board = nfcSouth()

        XCTAssertEqual(E.markHex(name: "Tampa Bay", outcomes: board, index: 2), tampaBay,
                       "asked for Tampa Bay at a different index, still Tampa Bay's colour")
        XCTAssertNotEqual(E.markHex(name: "Atlanta", outcomes: board, index: 0), tampaBay,
                          "Atlanta took the first outcome's colour")
    }

    /// `Field`, `_combined` and any name the payload does not carry have no
    /// stored colour to judge, so they take their palette slot — which is what
    /// they took before this arm. Stated as a test because "absent" and
    /// "unparseable" reaching the same branch is a property worth pinning.
    func testARowThePayloadDoesNotNameTakesItsPaletteSlot() {
        let board = nfcSouth()

        XCTAssertEqual(E.markHex(name: "Field", outcomes: board, index: 4), E.paletteHexes[4])
        XCTAssertEqual(E.markHex(name: "Tampa Bay", outcomes: nil, index: 0), E.paletteHexes[0])
    }

    func testAnUnparseableStoredColourTakesItsPaletteSlot() {
        XCTAssertEqual(E.markHex("not-a-colour", index: 6), E.paletteHexes[6])
        XCTAssertEqual(E.markHex("", index: 7), E.paletteHexes[7])
    }

    /// A board longer than the palette wraps, exactly as it did before — the
    /// chart serves up to 50 outcomes and the palette is 10.
    func testThePaletteWrapsPastItsTenthSlot() {
        XCTAssertEqual(E.fallbackHex(index: 10), E.paletteHexes[0])
        XCTAssertEqual(E.fallbackHex(index: 13), E.paletteHexes[3])
        XCTAssertEqual(E.markHex(whiteShirt, index: 11), E.paletteHexes[1])
    }

    // MARK: - One floor, not a fifth spelling of one

    /// Arms 1–5 answer the same question with the same number. If this drifted,
    /// a colour could be legible on a card and invisible on the chart beside it.
    func testTheChartUsesTheSameFloorAsEveryOtherArm() {
        for hex in [tampaBay, newOrleans, carolina, goldenState, whiteShirt] {
            let kept = E.markHex(hex, index: 0) == hex
            XCTAssertEqual(kept, C.usableForText(hex) != nil,
                           "\(hex): the chart and the card disagree about the floor")
        }
    }

    // MARK: - The wiring, which is the half no assertion above can reach

    /// Every assertion above can be perfect while the chart goes on painting
    /// `Color(hex: meta.primaryColor)` — it compiles, it renders, and this file
    /// stays green. These scans are the only thing that fails.
    ///
    /// Each anchor is the exact string a mutant in
    /// `tools/native-268-mutations-7036-chart-marks.py` writes back, so none of
    /// them is an absence that could never occur.
    func testTheChartsOwnResolverRoutesThroughTheFloor() throws {
        let body = try String(contentsOf: Self.chartURL, encoding: .utf8)

        XCTAssertTrue(body.contains("EvolutionOutcomeColour.markHex(\n            name: name, outcomes: data?.outcomes, index: index)"),
                      "colorForOutcome is not resolving through the #7036 floor")
        XCTAssertFalse(body.contains("if let meta = data?.outcomes.first(where: { $0.name == name }),"),
                       "the chart is reading meta.primaryColor straight again")
    }

    /// 🪤 THE HALF-FIX. The chart draws its outcome colour in three places — the
    /// series scale, the crosshair, the leaderboard — and every one of them goes
    /// through `colorForOutcome`. Wiring the floor and then letting ONE site
    /// bypass it compiles, renders, and leaves every helper assertion green.
    /// A count, not a `contains`, is the only thing that sees it.
    func testAllThreeMarkSitesGoThroughTheOneResolver() throws {
        let body = try String(contentsOf: Self.chartURL, encoding: .utf8)

        // Three call sites plus the declaration.
        XCTAssertEqual(body.components(separatedBy: "colorForOutcome(name:").count - 1, 4,
                       "a mark site has stopped going through the chart's one resolver")
        XCTAssertFalse(body.contains("Color(hex: outcome.primaryColor"),
                       "the leaderboard row is painting a raw primary_color again")
    }

    /// Strawman: the scan reads a real file with real content, so the
    /// `XCTAssertFalse`s above cannot be passing because a read failed.
    func testTheSourceScanIsReadingTheFileItThinksItIs() throws {
        let body = try String(contentsOf: Self.chartURL, encoding: .utf8)
        XCTAssertGreaterThan(body.count, 20_000, "EvolutionChartView.swift read back far too small")
        XCTAssertTrue(body.contains("import Charts"), "that is not the chart file")
    }

    // MARK: - The palette as a pinned contract

    /// The palette was always the colour of an UNCOLOURED outcome. Since this
    /// arm it is also what a floored one falls onto, so an edit here repaints
    /// clubs that do have a stored colour. Pinned so that is a decision.
    ///
    /// ⭐ Deliberately NOT justified as "web parity". `lib/seriesColors.ts`
    /// records that the web dropped this crimson-led list for the flagship
    /// blue-led `SERIES_COLORS`, so the two platforms already differ. That is a
    /// real divergence and a separate question from this floor; pinning it here
    /// stops the native list drifting further while it is open.
    func testThePaletteIsPinned() {
        XCTAssertEqual(E.paletteHexes, [
            "#c41e3a", "#005eb8", "#1d4ed8", "#0e7490", "#b91c1c",
            "#0369a1", "#92400e", "#4338ca", "#be185d", "#065f46",
        ])
    }

    /// 🪤 Arm 4 found the ladder's default at **3.77:1** — one AA revision away
    /// from being unreadable again. This palette is not in that position and it
    /// is worth knowing which of the two you are looking at: the palest slot is
    /// `#0e7490` at 5.36:1, so every slot would survive #5165's AA question
    /// (4.5:1) unchanged. If an edit ever brings one under that, this says so
    /// before a render does.
    func testThePalestSlotWouldSurviveAnAAFloorToo() {
        let ratios = E.paletteHexes.compactMap { C.contrastVsCardSurface($0) }
        XCTAssertEqual(ratios.count, E.paletteHexes.count)
        XCTAssertEqual(ratios.min() ?? 0, 5.36, accuracy: 0.01)
        XCTAssertGreaterThan(ratios.min() ?? 0, 4.5)
    }

    /// A colour that *looks* fine tells you nothing about its ratio. Carolina's
    /// `#7bafd4` is a pleasant sky blue at 2.35:1, and New Orleans' `#d3bc8d` a
    /// perfectly ordinary gold at 1.85:1. Both are on one four-line board.
    func testThePaleColoursOnTheSpecimenBoardAreMeasuredNotEyeballed() {
        XCTAssertEqual(C.contrastVsCardSurface(carolina) ?? 0, 2.35, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(newOrleans) ?? 0, 1.85, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(goldenState) ?? 0, 1.73, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(tampaBay) ?? 0, 6.21, accuracy: 0.01)
    }

    // MARK: - Fixtures

    /// Decoded rather than constructed, so the fixture is the shape the route
    /// actually serves — `primary_color`, through `.convertFromSnakeCase`.
    private func outcome(name: String, colour: String?) -> TimelineOutcomeMeta {
        var json: [String: Any] = ["name": name, "current_probability": 0.25]
        if let colour { json["primary_color"] = colour }
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` hands back the standardised one, so prefix arithmetic
    /// between the two eats the middle out of the path. Going up the URL avoids
    /// the subtraction. (Banked by arm 4.)
    private static var chartURL: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components/EvolutionChartView.swift")
    }
}
