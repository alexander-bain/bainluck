import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the Olympic 500m page's required "Before the race" card: each named
/// skater's own gold chance at its first captured trade beside its latest
/// captured trade before race day, as a stateless leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: exact scoped identity through the chooser's resolver,
/// the one-admitted-reading / one-tied-observation rule per endpoint, marks on
/// one common scale, the small/large hollow glyph plan, the connector, the
/// measured axis inset, the arrangement choices, the actions each endpoint
/// hands back, the phase gate and the spoken summaries. Nothing here claims a
/// rendered fit, a native runtime, VoiceOver behaviour or a held-update
/// qualification.
///
/// ARCHIVED raw values come from Winter Games 2026 Speed Skating Women's 500m
/// (event 200646), as retained in
/// `shipping-adoption-20261027/PRE-EVENT-SHIFT-RETAINED-CASES.json`
/// (sha256 cbeea51d…2b662), generated from the unchanged `skatingMovement`,
/// `skatingTrades` and `skatingBaseline`: the three featured Yes originals in
/// source order — Polymarket market id, market name, Yes token id, and the
/// first and last retained trades before the Feb 15 Milan midnight cutoff
/// (1771110000), each with its own probability, unix clock and transaction
/// hash — plus Kok's No side with its own observations (0.29 → 0.23). All
/// eight clocks precede the cutoff.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// scope and source strings, every label and absence word, the percent figure
/// text and Milan clock line of each reading, the glyph and order assignment,
/// the observation keys (the trade's transaction hash, chosen as an opaque
/// owner key), the scale and its tick labels, the phases, and every missing,
/// duplicate, mismatched, foreign, blank, off-scale and invalid case. Provider
/// token ids stand in for the production outcome identity the owner still has
/// to map.
final class PreEventProbabilityShiftPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    /// CONSTRUCTED opaque scope and source.
    private static let scope = "polymarket|200646|gold|before-race-day"
    private static let source = "polymarket"
    /// ARCHIVED: race day begins at midnight in Milan. Not an actual race start.
    private static let cutoff = 1_771_110_000

    private struct Trade {
        let p: Double
        let t: Int
        let tx: String
        /// CONSTRUCTED owner text for this trade.
        let text: String
        let clock: String
    }

    private struct Side {
        let marketID: String
        let name: String
        let token: String
        let glyph: PreEventShiftGlyph10868
        let first: Trade
        let last: Trade

        var ref: FieldChooserOriginalRef10868 {
            FieldChooserOriginalRef10868(scope: PreEventProbabilityShiftPresentation10868Tests.scope,
                                         source: PreEventProbabilityShiftPresentation10868Tests.source,
                                         marketID: marketID, outcomeID: token)
        }
    }

    /// ARCHIVED featured Yes originals in source order, with CONSTRUCTED glyphs and text.
    private static let kok = Side(
        marketID: "1347941", name: "Femke Kok (NED)",
        token: "8015203451758424254624644018470563478761525048434806320115142348030067468557", glyph: .circle,
        first: Trade(p: 0.6799999728, t: 1_770_423_645, tx: "0x4d7e4656e88569b3e0de0867f268f2703487f17b69a28f07d16378ac73255414",
                     text: "68%", clock: "Feb 7, 1:20 AM Milan · Polymarket"),
        last: Trade(p: 0.7799999991, t: 1_771_109_125, tx: "0x700b0fded4ba3abd72c57b870264303a2eb528c2d53806f46295c0c08ea8c25b",
                    text: "78%", clock: "Feb 14, 11:45 PM Milan · Polymarket"))
    private static let leerdam = Side(
        marketID: "1347948", name: "Jutta Leerdam (NED)",
        token: "79914460156377571131066368245251308998571925540235970541258802787200179848437", glyph: .triangle,
        first: Trade(p: 0.04, t: 1_770_446_333, tx: "0xac0c36f893d540e3e8b6d2d3caa5a705e79bb072a43cd86339dc18a47c508819",
                     text: "4%", clock: "Feb 7, 7:38 AM Milan · Polymarket"),
        last: Trade(p: 0.2257564719, t: 1_771_107_553, tx: "0xe75608aa6a2f2118a67f0dde82e9edca3bf4392696aa5858b270a1a41743ad11",
                    text: "23%", clock: "Feb 14, 11:19 PM Milan · Polymarket"))
    private static let jackson = Side(
        marketID: "1347949", name: "Erin Jackson (USA)",
        token: "53304661739730347120669901078624402642379665537751793251399570729507588207289", glyph: .diamond,
        first: Trade(p: 0.021, t: 1_770_477_175, tx: "0xc6a7418cae812931f6732e6cc55afc1db6587934f6c0a142901c927b7ed3eca5",
                     text: "2.1%", clock: "Feb 7, 4:12 PM Milan · Polymarket"),
        last: Trade(p: 0.014, t: 1_771_107_825, tx: "0x2e472627f92a8dab0ede779734fe53c5be2fac36a8b80c3d106105bb1e2281d5",
                    text: "1.4%", clock: "Feb 14, 11:23 PM Milan · Polymarket"))
    /// ARCHIVED: Kok's No side, its own token and its own trades — not a complement.
    private static let kokNo = Side(
        marketID: "1347941", name: "Femke Kok (NED) · No",
        token: "6871475823121509807575753550545899827766388996691185372123240045395047814247", glyph: .circle,
        first: Trade(p: 0.29, t: 1_770_462_375, tx: "0x08d33b1d73f0b0a664aee7650364ef90a3b892ebd2f3cfc7396672ed0c9d8562",
                     text: "29%", clock: "Feb 7, 12:06 PM Milan · Polymarket"),
        last: Trade(p: 0.23, t: 1_771_108_967, tx: "0x1bd56e47ed9afc674f6452aecf0f062a65ad100038ce7f45ff24cadfbd0c0ca3",
                    text: "23%", clock: "Feb 14, 11:42 PM Milan · Polymarket"))

    private static let featured = [kok, leerdam, jackson]

    private static let copy = PreEventShiftCopy10868(
        eyebrow: "GOLD EXPECTATIONS",
        title: "Before the race",
        phaseKey: "Both marks: before race day",
        firstKey: "Small: first captured",
        latestKey: "Large: latest before race day",
        graphicLabel: "Gold chances before race day",
        firstLabel: "First captured",
        latestLabel: "Latest before race day",
        endpointUnavailable: "Not recorded for this comparison",
        offScale: "Above this scale",
        note: "Each chance keeps its own trade time",
        openHint: "Opens this trade in the gold history"
    )

    private static let scale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [
            FieldOutlookTick10868(probability: 0, label: "0%"),
            FieldOutlookTick10868(probability: 0.5, label: "50%"),
            FieldOutlookTick10868(probability: 1, label: "100%"),
        ],
        words: "Gold chance · 0–100% · not normalized"
    )

    private static func reading(_ kind: PreEventShiftEndpointKind10868, _ trade: Trade) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: kind == .first ? copy.firstLabel : copy.latestLabel,
                                 value: .recorded(text: trade.text, detail: trade.clock))
    }

    private static func original(_ side: Side) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: side.ref, name: side.name,
            plan: .single(FieldChooserReading10868(label: "Gold chance before race day", value: .recorded(text: side.last.text, detail: side.last.clock))),
            preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
            movement: nil, clock: nil, result: nil, browseStatus: "Recorded history available"
        )
    }

    private static func admitted(_ sides: [Side]) -> [PreEventShiftReading10868] {
        sides.flatMap { side in
            [PreEventShiftReading10868(ref: side.ref, endpoint: .first, reading: reading(.first, side.first)),
             PreEventShiftReading10868(ref: side.ref, endpoint: .latest, reading: reading(.latest, side.last))]
        }
    }

    private static func observation(_ side: Side, _ kind: PreEventShiftEndpointKind10868) -> PreEventShiftObservation10868 {
        let trade = kind == .first ? side.first : side.last
        return PreEventShiftObservation10868(
            ref: side.ref, endpoint: kind,
            observation: FieldMovementObservation10868(probability: trade.p, reading: reading(kind, trade)),
            key: trade.tx
        )
    }

    private static func observed(_ sides: [Side]) -> [PreEventShiftObservation10868] {
        sides.flatMap { [observation($0, .first), observation($0, .latest)] }
    }

    private static func slot(_ side: Side) -> PreEventShiftSlot10868 {
        PreEventShiftSlot10868(ref: side.ref, name: side.name, glyph: side.glyph)
    }

    private static func input(
        sides: [Side] = PreEventProbabilityShiftPresentation10868Tests.featured,
        displayed: [PreEventShiftSlot10868]? = nil,
        catalogue: [FieldChooserOriginal10868]? = nil,
        readings: [PreEventShiftReading10868]? = nil,
        observations: [PreEventShiftObservation10868]? = nil,
        scale: FieldOutlookScale10868 = PreEventProbabilityShiftPresentation10868Tests.scale,
        phase: FieldOutlookPhase10868 = .before
    ) -> PreEventShiftInput10868 {
        PreEventShiftInput10868(
            scope: scope,
            catalogue: catalogue ?? (featured + [kokNo]).map(original),
            displayed: displayed ?? sides.map(slot),
            readings: readings ?? admitted(sides),
            observations: observations ?? observed(sides),
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: "Skater unavailable in this update"
        )
    }

    private static func model(_ input: PreEventShiftInput10868 = PreEventProbabilityShiftPresentation10868Tests.input()) -> PreEventShiftModel10868 {
        PreEventShiftModel10868(input)
    }

    private static let unavailableFirst = FieldMovementEndpoint10868.unavailable(label: "First captured", words: "Not recorded for this comparison")
    private static let unavailableLatest = FieldMovementEndpoint10868.unavailable(label: "Latest before race day", words: "Not recorded for this comparison")

    // MARK: Real featured pairs

    func testThreeFeaturedSkatersKeepTheirOwnFirstAndLatestPairsAndExactIdentities() {
        for side in Self.featured + [Self.kokNo] {
            XCTAssertLessThan(side.first.t, side.last.t, side.name)
            XCTAssertLessThan(side.last.t, Self.cutoff, "\(side.name): both endpoints precede race day")
        }
        let rows = Self.model().rows
        XCTAssertEqual(rows.map(\.slot.name), ["Femke Kok (NED)", "Jutta Leerdam (NED)", "Erin Jackson (USA)"])
        XCTAssertEqual(rows.map(\.slot.glyph), [.circle, .triangle, .diamond])
        for (row, side) in zip(rows, Self.featured) {
            XCTAssertEqual(row.resolution.original?.ref, side.ref)
            XCTAssertEqual(row.resolution.original?.ref.marketID, side.marketID)
            XCTAssertEqual(row.first?.endpoint, .reading(Self.reading(.first, side.first)))
            XCTAssertEqual(row.latest?.endpoint, .reading(Self.reading(.latest, side.last)))
            // Ceiling 1: each mark sits at its own raw value, exactly.
            XCTAssertEqual(row.first?.chance, .value(probability: side.first.p, fraction: side.first.p))
            XCTAssertEqual(row.latest?.chance, .value(probability: side.last.p, fraction: side.last.p))
            XCTAssertEqual(row.first?.key, side.first.tx)
            XCTAssertEqual(row.latest?.key, side.last.tx)
            XCTAssertNil(Self.model().stateWords(row))
        }
        // Leerdam rose and Jackson fell; the card computes no change words for either.
        XCTAssertLessThan(Self.leerdam.first.p, Self.leerdam.last.p)
        XCTAssertGreaterThan(Self.jackson.first.p, Self.jackson.last.p)
        XCTAssertFalse(Self.model().rowSummary(rows[2]).contains("pts"))
    }

    func testKokNoKeepsItsOwnIndependentObservationsNotAComplement() {
        let model = Self.model(Self.input(sides: [Self.kok, Self.kokNo]))
        let rows = model.rows
        XCTAssertEqual(rows.count, 2)
        let no = rows[1]
        XCTAssertEqual(no.resolution.original?.ref.outcomeID, Self.kokNo.token)
        XCTAssertEqual(no.first?.chance, .value(probability: 0.29, fraction: 0.29))
        XCTAssertEqual(no.latest?.chance, .value(probability: 0.23, fraction: 0.23))
        // Never 1 − Yes: 0.32 and 0.22 would be complements of Kok Yes.
        XCTAssertNotEqual(no.first?.chance.fraction ?? .nan, 1 - Self.kok.first.p, accuracy: 0.001)
        XCTAssertNotEqual(no.latest?.chance.fraction ?? .nan, 1 - Self.kok.last.p, accuracy: 0.001)
        XCTAssertEqual(FieldChaseModel10868.detail(no.first!.endpoint), "Feb 7, 12:06 PM Milan · Polymarket")
        XCTAssertEqual(FieldChaseModel10868.detail(no.latest!.endpoint), "Feb 14, 11:42 PM Milan · Polymarket")
        XCTAssertEqual([no.first?.key, no.latest?.key], [Self.kokNo.first.tx, Self.kokNo.last.tx])
        // Kok Yes keeps its own figures beside its own No.
        XCTAssertEqual(rows[0].latest?.chance, .value(probability: Self.kok.last.p, fraction: Self.kok.last.p))
    }

    // MARK: Endpoint association

    func testMissingOrUntiedReadingsAndMismatchedOrDuplicateObservationsBorrowNothing() {
        var readings = Self.admitted(Self.featured)
        var observations = Self.observed(Self.featured)
        // Kok: no admitted latest reading.
        readings.removeAll { $0.ref == Self.kok.ref && $0.endpoint == .latest }
        // Leerdam: the owner's own absence words for the first endpoint.
        readings.removeAll { $0.ref == Self.leerdam.ref && $0.endpoint == .first }
        let absence = FieldChooserReading10868(label: "First captured", value: .missing("No captured trade"))
        readings.append(PreEventShiftReading10868(ref: Self.leerdam.ref, endpoint: .first, reading: absence))
        // Jackson: the latest observation's reading carries another clock line.
        observations.removeAll { $0.ref == Self.jackson.ref && $0.endpoint == .latest }
        observations.append(PreEventShiftObservation10868(
            ref: Self.jackson.ref, endpoint: .latest,
            observation: FieldMovementObservation10868(probability: Self.jackson.last.p, reading: FieldChooserReading10868(
                label: "Latest before race day", value: .recorded(text: "1.4%", detail: "Feb 15, 9:00 PM Milan · Polymarket"))),
            key: Self.jackson.last.tx))
        // Jackson: two identical first observations are none.
        observations.append(Self.observation(Self.jackson, .first))

        let model = Self.model(Self.input(readings: readings, observations: observations))
        let rows = model.rows
        XCTAssertEqual(rows[0].first?.chance, .value(probability: Self.kok.first.p, fraction: Self.kok.first.p))
        XCTAssertEqual(rows[0].first?.key, Self.kok.first.tx)
        XCTAssertEqual(rows[0].latest, PreEventShiftSide10868(kind: .latest, endpoint: Self.unavailableLatest, chance: .unavailable, key: nil))

        XCTAssertEqual(rows[1].first, PreEventShiftSide10868(kind: .first, endpoint: .reading(absence), chance: .unavailable, key: nil))
        XCTAssertEqual(rows[1].latest?.key, Self.leerdam.last.tx)

        XCTAssertEqual(rows[2].first, PreEventShiftSide10868(kind: .first, endpoint: Self.unavailableFirst, chance: .unavailable, key: nil))
        XCTAssertEqual(rows[2].latest, PreEventShiftSide10868(kind: .latest, endpoint: Self.unavailableLatest, chance: .unavailable, key: nil))
        XCTAssertFalse(model.showsTrack(rows[2]), "two untied endpoints draw no track")

        // An observation filed under the other endpoint is not this endpoint's tie.
        var swapped = Self.observed([Self.kok])
        swapped[1] = PreEventShiftObservation10868(ref: Self.kok.ref, endpoint: .latest,
                                                    observation: Self.observation(Self.kok, .first).observation, key: Self.kok.last.tx)
        let kokSwapped = Self.model(Self.input(sides: [Self.kok], observations: swapped)).rows[0]
        XCTAssertEqual(kokSwapped.latest?.endpoint, Self.unavailableLatest)
        XCTAssertEqual(kokSwapped.first?.key, Self.kok.first.tx, "the first endpoint keeps its own key")
    }

    func testScopedIdentityFailuresBorrowNothingAndNeighboursKeepTheirOwn() {
        let unknown = FieldChooserOriginalRef10868(scope: Self.scope, source: Self.source, marketID: "1347999", outcomeID: "999")
        let foreign = FieldChooserOriginalRef10868(scope: "polymarket|200646|gold|live", source: Self.source,
                                                   marketID: Self.leerdam.marketID, outcomeID: Self.leerdam.token)
        let blank = FieldChooserOriginalRef10868(scope: Self.scope, source: " ", marketID: Self.kok.marketID, outcomeID: Self.kok.token)
        // Jackson is carried twice in the catalogue; Kok No is withdrawn from it; Leerdam is displayed twice.
        let catalogue = [Self.kok, Self.leerdam, Self.jackson, Self.jackson].map(Self.original)
        let displayed = [
            PreEventShiftSlot10868(ref: unknown, name: "Unknown skater", glyph: .circle),
            Self.slot(Self.kok),
            PreEventShiftSlot10868(ref: foreign, name: "Jutta Leerdam (NED)", glyph: .triangle),
            Self.slot(Self.jackson),
            PreEventShiftSlot10868(ref: blank, name: "Blank reference", glyph: .circle),
            Self.slot(Self.kokNo),
            Self.slot(Self.leerdam),
            Self.slot(Self.leerdam),
        ]
        let sides = [Self.kok, Self.leerdam, Self.jackson, Self.kokNo]
        let model = Self.model(Self.input(sides: sides, displayed: displayed, catalogue: catalogue))
        let rows = model.rows
        XCTAssertEqual(rows.count, 8)
        for index in [0, 2, 3, 4, 5, 6, 7] {
            let row = rows[index]
            XCTAssertEqual(row.resolution, .unavailable, row.slot.name)
            XCTAssertNil(row.first)
            XCTAssertNil(row.latest)
            XCTAssertFalse(model.showsTrack(row))
            XCTAssertEqual(model.stateWords(row), "Skater unavailable in this update")
            XCTAssertEqual(model.rowSummary(row), "\(row.slot.name). Skater unavailable in this update")
        }
        let neighbour = rows[1]
        XCTAssertEqual(neighbour.resolution.original?.ref, Self.kok.ref)
        XCTAssertEqual(neighbour.first?.key, Self.kok.first.tx)
        XCTAssertEqual(neighbour.latest?.key, Self.kok.last.tx)
        XCTAssertTrue(model.showsTrack(neighbour))
    }

    // MARK: Geometry

    func testRealZeroAndHundredAreEdgeMarksAndInvalidOrOffScaleValuesAreNeverClamped() {
        func single(first p0: Double, latest p1: Double, scale: FieldOutlookScale10868 = Self.scale) -> (PreEventShiftModel10868, PreEventShiftRow10868) {
            let side = Side(marketID: Self.kok.marketID, name: Self.kok.name, token: Self.kok.token, glyph: .diamond,
                            first: Trade(p: p0, t: Self.kok.first.t, tx: "first", text: "first figure", clock: Self.kok.first.clock),
                            last: Trade(p: p1, t: Self.kok.last.t, tx: "latest", text: "latest figure", clock: Self.kok.last.clock))
            let model = Self.model(Self.input(sides: [side], scale: scale))
            return (model, model.rows[0])
        }
        let size = CGSize(width: 300, height: 24)
        let (_, edges) = single(first: 0, latest: 1)
        XCTAssertEqual(edges.first?.chance, .value(probability: 0, fraction: 0))
        XCTAssertEqual(edges.latest?.chance, .value(probability: 1, fraction: 1))
        let plan = PreEventShiftGeometry10868.trackPlan(glyph: .diamond, first: 0, latest: 1, ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
        XCTAssertEqual(plan.first?.center.x, plan.zeroX)
        XCTAssertEqual(plan.latest?.center.x, plan.ceilingX)
        let latestBounds = PreEventShiftGeometry10868.bounds(.diamond, center: plan.latest!.center, radius: 7).insetBy(dx: -1, dy: -1)
        XCTAssertGreaterThanOrEqual(latestBounds.minX, 0)
        XCTAssertLessThanOrEqual(latestBounds.maxX, size.width, "a real 100% is a whole mark at the edge")

        for invalid in [Double.nan, .infinity, 1.2, -0.01] {
            let (model, row) = single(first: invalid, latest: 0.5)
            XCTAssertEqual(row.first?.endpoint, Self.unavailableFirst, "\(invalid)")
            XCTAssertEqual(row.first?.chance, .unavailable)
            XCTAssertNil(FieldChaseModel10868.figure(row.first!.endpoint))
            XCTAssertEqual(row.latest?.chance, .value(probability: 0.5, fraction: 0.5))
            XCTAssertNil(model.stateWords(row))
        }

        // A 0–50% scale: Kok's 78% keeps its figure, draws no mark and says so.
        let half = FieldOutlookScale10868(ceiling: 0.5, ticks: [], words: "Gold chance · 0–50%")
        let (offModel, off) = single(first: Self.leerdam.last.p, latest: Self.kok.last.p, scale: half)
        XCTAssertEqual(off.latest?.chance, .offScale)
        XCTAssertEqual(FieldChaseModel10868.figure(off.latest!.endpoint), "latest figure")
        XCTAssertEqual(offModel.stateWords(off), "Above this scale")
        XCTAssertTrue(offModel.showsTrack(off))
        let offPlan = PreEventShiftGeometry10868.trackPlan(glyph: .diamond, first: off.first?.chance.fraction, latest: off.latest?.chance.fraction,
                                                           ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
        XCTAssertNotNil(offPlan.first)
        XCTAssertNil(offPlan.latest)
        XCTAssertNil(offPlan.connector)

        // No valid scale or no scale words: no tracks, figures stay.
        for broken in [FieldOutlookScale10868(ceiling: 0, ticks: [], words: "x"), FieldOutlookScale10868(ceiling: 1, ticks: [], words: " ")] {
            let model = Self.model(Self.input(scale: broken))
            XCTAssertFalse(model.showsTracks)
            XCTAssertTrue(model.ticks.isEmpty)
            XCTAssertTrue(model.rows.allSatisfy { !model.showsTrack($0) && FieldChaseModel10868.figure($0.first!.endpoint) != nil })
        }
    }

    func testEqualValuesAtDifferentClocksStayTwoConcentricHollowMarksAndAMissingEndpointDrawsNoConnector() {
        let side = Side(marketID: Self.kok.marketID, name: Self.kok.name, token: Self.kok.token, glyph: .circle,
                        first: Trade(p: 0.5, t: Self.kok.first.t, tx: "a", text: "50%", clock: Self.kok.first.clock),
                        last: Trade(p: 0.5, t: Self.kok.last.t, tx: "b", text: "50%", clock: Self.kok.last.clock))
        let row = Self.model(Self.input(sides: [side])).rows[0]
        XCTAssertEqual(row.first?.chance, row.latest?.chance)
        XCTAssertNotEqual(FieldChaseModel10868.detail(row.first!.endpoint), FieldChaseModel10868.detail(row.latest!.endpoint))
        let size = CGSize(width: 300, height: 24)
        for glyph in PreEventShiftGlyph10868.allCases {
            let plan = PreEventShiftGeometry10868.trackPlan(glyph: glyph, first: 0.5, latest: 0.5, ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
            XCTAssertEqual(plan.first?.center, plan.latest?.center)
            XCTAssertNil(plan.connector, "\(glyph): equal values are two marks, not a segment")
            let large = plan.latest!.radius
            let small = plan.first!.radius
            XCTAssertEqual(small, large * PreEventShiftGeometry10868.firstScale)
            XCTAssertGreaterThan(large - small, 2, "\(glyph): the small outline stays clear of the large one")
        }
        let missing = PreEventShiftGeometry10868.trackPlan(glyph: .triangle, first: nil, latest: 0.2257564719, ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
        XCTAssertNil(missing.first)
        XCTAssertNotNil(missing.latest)
        XCTAssertNil(missing.connector)
        let kok = PreEventShiftGeometry10868.trackPlan(glyph: .circle, first: Self.kok.first.p, latest: Self.kok.last.p, ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
        XCTAssertEqual(kok.connector?.minX, kok.first?.center.x)
        XCTAssertEqual(kok.connector?.maxX ?? 0, kok.latest?.center.x ?? -1, accuracy: 0.0001)
        XCTAssertEqual(kok.connector?.height, 3)
    }

    func testGlyphPlanKeepsEachSkatersShapeFirstSmallLatestLargeWholeInEveryMarkerBoxOnOneInset() {
        let center = CGPoint(x: 50, y: 50)
        XCTAssertEqual(PreEventShiftGeometry10868.bounds(.circle, center: center, radius: 10), CGRect(x: 40, y: 40, width: 20, height: 20))
        let triangle = PreEventShiftGeometry10868.bounds(.triangle, center: center, radius: 10)
        XCTAssertEqual(triangle.minX, 39, accuracy: 0.0001)
        XCTAssertEqual(triangle.width, 22, accuracy: 0.0001)
        XCTAssertEqual(triangle.minY, 37.5, accuracy: 0.0001)
        XCTAssertEqual(triangle.maxY, 60, accuracy: 0.0001)
        let diamond = PreEventShiftGeometry10868.bounds(.diamond, center: center, radius: 10)
        XCTAssertEqual(diamond.minX, 38, accuracy: 0.0001)
        XCTAssertEqual(diamond.minY, 38, accuracy: 0.0001)
        XCTAssertEqual(diamond.width, 24, accuracy: 0.0001)
        XCTAssertEqual(diamond.height, 24, accuracy: 0.0001)
        for glyph in PreEventShiftGlyph10868.allCases {
            let path = PreEventShiftGeometry10868.path(glyph, center: center, radius: 10).boundingRect
            let box = PreEventShiftGeometry10868.bounds(glyph, center: center, radius: 10)
            XCTAssertEqual(path.minX, box.minX, accuracy: 0.0001, "\(glyph)")
            XCTAssertEqual(path.maxY, box.maxY, accuracy: 0.0001, "\(glyph)")
        }
        // The one inset is the expectations rule on the widest glyph, outline included.
        XCTAssertEqual(PreEventShiftGeometry10868.inset(radius: 7, lineWidth: 2),
                       FieldExpectationsGeometry10868.inset(markDiameter: 2 * 1.2 * 7 + 2), accuracy: 0.0001)
        // Each glyph's whole reach is centred in its track.
        let size = CGSize(width: 300, height: 24)
        for glyph in PreEventShiftGlyph10868.allCases {
            let plan = PreEventShiftGeometry10868.trackPlan(glyph: glyph, first: 0.04, latest: 0.2257564719, ticks: [], in: size, radius: 7, lineWidth: 2, connectorWidth: 3)!
            XCTAssertEqual(PreEventShiftGeometry10868.bounds(glyph, center: plan.latest!.center, radius: 7).midY, 12, accuracy: 0.0001, "\(glyph)")
            XCTAssertLessThan(plan.first!.radius, plan.latest!.radius)
        }
        // Too short for the tallest reach: nothing is drawn rather than clipped.
        XCTAssertNil(PreEventShiftGeometry10868.trackPlan(glyph: .diamond, first: 0.5, latest: 0.6, ticks: [], in: CGSize(width: 300, height: 10), radius: 7, lineWidth: 2, connectorWidth: 3))

        // Design C2 (initial review 12:21Z): every marker box holds every glyph
        // whole — the triangle's 1.25 r apex included — at both sizes and any radius.
        XCTAssertEqual(PreEventShiftGeometry10868.stroke(lineWidth: 2).lineJoin, .round, "no mitred corner reaches past half the line")
        let lineWidth: CGFloat = 2
        // Ordinary, enlarged, and the 0.6× identity key.
        for radius: CGFloat in [7, 14, 4.2] {
            let side = PreEventShiftGeometry10868.markExtent(radius: radius, lineWidth: lineWidth)
            let box = CGRect(x: 0, y: 0, width: side, height: side).insetBy(dx: -0.0001, dy: -0.0001)
            for glyph in PreEventShiftGlyph10868.allCases {
                for drawn in [radius, radius * PreEventShiftGeometry10868.firstScale] {
                    let center = PreEventShiftGeometry10868.center(glyph, in: CGSize(width: side, height: side), radius: drawn)
                    let ink = PreEventShiftGeometry10868.strokedBounds(glyph, center: center, radius: drawn, lineWidth: lineWidth)
                    XCTAssertTrue(box.contains(ink), "\(glyph) r\(drawn) in \(side): \(ink)")
                }
            }
            // On a track exactly that tall, real 0% and 100% marks stay whole and
            // share the axis labels' inset.
            let size = CGSize(width: 320, height: side)
            let inset = PreEventShiftGeometry10868.inset(radius: radius, lineWidth: lineWidth)
            for glyph in PreEventShiftGlyph10868.allCases {
                let plan = PreEventShiftGeometry10868.trackPlan(glyph: glyph, first: 0, latest: 1, ticks: [0.5], in: size,
                                                                radius: radius, lineWidth: lineWidth, connectorWidth: 3)!
                XCTAssertEqual(plan.first?.center.x, FieldFinishGeometry10868.x(of: 0, width: 320, inset: inset))
                XCTAssertEqual(plan.latest?.center.x, FieldFinishGeometry10868.x(of: 1, width: 320, inset: inset))
                XCTAssertEqual(plan.tickXs.last, FieldFinishGeometry10868.x(of: 0.5, width: 320, inset: inset))
                let track = CGRect(origin: .zero, size: size).insetBy(dx: -0.0001, dy: -0.0001)
                for mark in [plan.first!, plan.latest!] {
                    XCTAssertTrue(track.contains(PreEventShiftGeometry10868.strokedBounds(glyph, center: mark.center, radius: mark.radius, lineWidth: lineWidth)), "\(glyph) r\(radius)")
                }
                XCTAssertEqual(plan.first?.center, CGPoint(x: plan.zeroX, y: plan.centerY))
            }
        }
    }

    func testScaleTicksShareTheMeasuredAxisInsetAndCompactOrAccessibilityArrangements() {
        let scale = FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks + [
            FieldOutlookTick10868(probability: 1.2, label: "120%"),
            FieldOutlookTick10868(probability: .nan, label: "?"),
        ], words: Self.scale.words)
        let model = Self.model(Self.input(scale: scale))
        XCTAssertEqual(model.ticks, [
            FieldOutlookPlacedTick10868(label: "0%", fraction: 0),
            FieldOutlookPlacedTick10868(label: "50%", fraction: 0.5),
            FieldOutlookPlacedTick10868(label: "100%", fraction: 1),
        ])
        let inset = PreEventShiftGeometry10868.inset(radius: 7, lineWidth: 2)
        let units = model.ticks.map(\.fraction)
        let standard = FieldExpectationsGeometry10868.axisLabels(units.map { FieldChaseMeasuredTick10868(unit: $0, size: CGSize(width: 30, height: 13)) },
                                                                 width: 343, inset: inset, spacing: 6)
        let plan = PreEventShiftGeometry10868.trackPlan(glyph: .circle, first: nil, latest: nil, ticks: units, in: CGSize(width: 343, height: 24),
                                                        radius: 7, lineWidth: 2, connectorWidth: 3)!
        XCTAssertEqual(standard.compactMap { $0 }.count, 3)
        XCTAssertEqual(standard[1]?.midX ?? 0, plan.tickXs[2], accuracy: 0.0001, "the 50% label is centred on the track's own 50% tick")
        let dense = FieldExpectationsGeometry10868.axisLabels(units.map { FieldChaseMeasuredTick10868(unit: $0, size: CGSize(width: 50, height: 22)) },
                                                              width: 120, inset: inset, spacing: 6)
        XCTAssertNotNil(dense[0])
        XCTAssertNil(dense[1], "a crowded label is left out, not overlapped")
        XCTAssertEqual(PreEventShiftGeometry10868.readoutArrangements(accessibilitySize: true), [.stacked])
        XCTAssertEqual(PreEventShiftGeometry10868.readoutArrangements(accessibilitySize: false), [.sideBySide, .stacked])
    }

    // MARK: Actions

    func testEndpointCallbacksHandBackTheExactOriginalAndItsOwnKeyAndNoCallbackIsStatic() {
        let model = Self.model()
        for (row, side) in zip(model.rows, Self.featured) {
            let first = model.openAction(row, row.first!, canOpen: true)
            let latest = model.openAction(row, row.latest!, canOpen: true)
            XCTAssertEqual(first, FieldMovementOpen10868(ref: side.ref, observation: side.first.tx))
            XCTAssertEqual(latest, FieldMovementOpen10868(ref: side.ref, observation: side.last.tx))
            XCTAssertEqual(model.hint(first), "Opens this trade in the gold history")
            XCTAssertNil(model.openAction(row, row.first!, canOpen: false))
            XCTAssertNil(model.openAction(row, row.latest!, canOpen: false))
            XCTAssertEqual(model.hint(nil), "")
        }
        // A blank latest key: that endpoint does not act, and never borrows the first key.
        var observations = Self.observed([Self.kok])
        observations[1] = PreEventShiftObservation10868(ref: Self.kok.ref, endpoint: .latest,
                                                         observation: Self.observation(Self.kok, .latest).observation, key: "  ")
        let blank = Self.model(Self.input(sides: [Self.kok], observations: observations))
        let row = blank.rows[0]
        XCTAssertEqual(FieldChaseModel10868.figure(row.latest!.endpoint), "78%")
        XCTAssertNil(blank.openAction(row, row.latest!, canOpen: true))
        XCTAssertEqual(blank.openAction(row, row.first!, canOpen: true), FieldMovementOpen10868(ref: Self.kok.ref, observation: Self.kok.first.tx))
        // Words never act.
        var readings = Self.admitted([Self.kok])
        readings[0] = PreEventShiftReading10868(ref: Self.kok.ref, endpoint: .first,
                                                reading: FieldChooserReading10868(label: "First captured", value: .missing("No captured trade")))
        let words = Self.model(Self.input(sides: [Self.kok], readings: readings))
        XCTAssertNil(words.openAction(words.rows[0], words.rows[0].first!, canOpen: true))
    }

    /// Design C1 (initial review 12:21Z): keys are opaque per original, and an
    /// action binds to the row's own current original and endpoint.
    func testSharedOpaqueKeysStayExactAndForeignStaleOrHiddenSidesOpenNothing() {
        var observations = Self.observed(Self.featured)
        for index in observations.indices where observations[index].endpoint == .first && observations[index].ref != Self.jackson.ref {
            let tied = observations[index]
            observations[index] = PreEventShiftObservation10868(ref: tied.ref, endpoint: .first, observation: tied.observation, key: "trade")
        }
        let base = Self.input(observations: observations)
        let model = Self.model(base)
        let kok = model.rows[0]
        let leerdam = model.rows[1]
        XCTAssertEqual(model.openAction(kok, kok.first!, canOpen: true), FieldMovementOpen10868(ref: Self.kok.ref, observation: "trade"))
        XCTAssertEqual(model.openAction(leerdam, leerdam.first!, canOpen: true), FieldMovementOpen10868(ref: Self.leerdam.ref, observation: "trade"))
        XCTAssertEqual(model.openAction(kok, kok.latest!, canOpen: true), FieldMovementOpen10868(ref: Self.kok.ref, observation: Self.kok.last.tx))

        // Another row's side opens nothing on this row.
        XCTAssertNil(model.openAction(kok, leerdam.first!, canOpen: true))
        XCTAssertNil(model.openAction(kok, leerdam.latest!, canOpen: true))

        // After an input change: Kok's first reading is re-admitted at another figure.
        var readings = Self.admitted(Self.featured)
        let revised = FieldChooserReading10868(label: "First captured", value: .recorded(text: "70%", detail: Self.kok.first.clock))
        readings[0] = PreEventShiftReading10868(ref: Self.kok.ref, endpoint: .first, reading: revised)
        observations[0] = PreEventShiftObservation10868(ref: Self.kok.ref, endpoint: .first,
                                                         observation: FieldMovementObservation10868(probability: 0.7, reading: revised), key: "trade")
        let changed = Self.model(Self.input(readings: readings, observations: observations))
        XCTAssertNil(changed.openAction(kok, kok.first!, canOpen: true), "a stale side opens nothing")
        XCTAssertEqual(changed.openAction(changed.rows[0], changed.rows[0].first!, canOpen: true),
                       FieldMovementOpen10868(ref: Self.kok.ref, observation: "trade"))

        // Kok withdrawn from the catalogue, or no longer displayed.
        let withdrawn = Self.model(Self.input(catalogue: [Self.leerdam, Self.jackson].map(Self.original), observations: observations))
        XCTAssertNil(withdrawn.openAction(kok, kok.latest!, canOpen: true))
        let hidden = Self.model(Self.input(sides: [Self.leerdam, Self.jackson]))
        XCTAssertNil(hidden.openAction(kok, kok.latest!, canOpen: true))

        // No action while the card is not shown.
        let during = Self.model(Self.input(observations: observations, phase: .during))
        XCTAssertNil(during.openAction(kok, kok.latest!, canOpen: true))
        XCTAssertNil(during.openAction(leerdam, leerdam.latest!, canOpen: true))
    }

    // MARK: Phase and subjects

    func testShownBeforeRaceDayAndAtTheFinalButNeverDuring() {
        let before = Self.model(Self.input(phase: .before))
        let final = Self.model(Self.input(phase: .final))
        for model in [before, final] {
            XCTAssertTrue(model.isShown)
            XCTAssertEqual(model.rows.count, 3)
            XCTAssertEqual(model.eyebrow, "GOLD EXPECTATIONS")
            XCTAssertEqual(model.note, "Each chance keeps its own trade time")
            XCTAssertTrue(model.showsTracks)
        }
        // The same two pre-race-day observations at the final: nothing is relabelled current.
        XCTAssertEqual(before.rows, final.rows)
        let during = Self.model(Self.input(phase: .during))
        XCTAssertFalse(during.isShown)
        XCTAssertTrue(during.rows.isEmpty)
        XCTAssertNil(during.eyebrow)
        XCTAssertNil(during.note)
        XCTAssertFalse(during.showsTracks)
        XCTAssertTrue(during.ticks.isEmpty)
    }

    func testSpokenSummariesSayTheFullSubjectBothLabelledChancesAndClocksAndNeverAResult() {
        // The canonical record carries a settled later reading, movement, clock
        // and result for other cards; this card reads none of them.
        let settled = FieldChooserOriginal10868(
            ref: Self.kok.ref, name: Self.kok.name,
            plan: .comparison(
                before: FieldChooserReading10868(label: "Gold chance before race day", value: .recorded(text: "78%", detail: Self.kok.last.clock)),
                later: FieldChooserReading10868(label: "Settled", value: .recorded(text: "100%", detail: "Feb 15 · Final"))),
            preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
            movement: "Up 22 pts", clock: "Final",
            result: FieldChooserResult10868(title: "Final result", words: "Won gold · 36.49s"),
            browseStatus: "Recorded history available")
        let model = Self.model(Self.input(sides: [Self.kok], catalogue: [settled], phase: .final))
        let row = model.rows[0]
        let summary = model.rowSummary(row)
        XCTAssertEqual(summary, "Femke Kok (NED). First captured: 68%, Feb 7, 1:20 AM Milan · Polymarket. Latest before race day: 78%, Feb 14, 11:45 PM Milan · Polymarket")
        for leaked in ["Won", "36.49", "100%", "Settled", "Up 22", "Final", "current", "opening", "closing"] {
            XCTAssertFalse(summary.contains(leaked), leaked)
        }
        XCTAssertEqual(model.endpointSummary(row, row.first!), "Femke Kok (NED). First captured: 68%, Feb 7, 1:20 AM Milan · Polymarket")
        XCTAssertEqual(model.endpointSummary(row, row.latest!), "Femke Kok (NED). Latest before race day: 78%, Feb 14, 11:45 PM Milan · Polymarket")
        // An off-scale mark adds the owner's words; the figure is still spoken.
        let half = Self.model(Self.input(sides: [Self.kok], scale: FieldOutlookScale10868(ceiling: 0.5, ticks: [], words: "0–50%")))
        XCTAssertTrue(half.rowSummary(half.rows[0]).hasSuffix("78%, Feb 14, 11:45 PM Milan · Polymarket. Above this scale"))
    }
}
