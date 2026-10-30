import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket-live "Changing expectations" card as a stateless
/// presentation leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: each original's own before and comparison readings,
/// their independence (no complement, normalization or shared clock), the
/// explicit missing and withheld words, zero versus absent versus malformed,
/// the marks and connector, the owner's movement words, the exact-id
/// selection and the action each row carries, the pair geometry and the
/// spoken text. Nothing here claims a rendered fit, a native runtime or a
/// production binding.
///
/// ARCHIVED raw values come from South Africa–Australia, first Test,
/// October 9–13, 2026 (route cricket-live, original event
/// KXTESTMATCH-26OCT090330AUSSA), as retained in
/// `shipping-adoption-20261027/CRICKET-OUTLOOK-RETAINED-CASES.json`
/// (sha256 0b468101…18e9). Three original Kalshi Yes contracts:
///   SA  KXTESTMATCH-26OCT090330AUSSA-SA   pregame 0.48
///   AUS KXTESTMATCH-26OCT090330AUSSA-AUS  pregame 0.47
///   TIE KXTESTMATCH-26OCT090330AUSSA-TIE  pregame 0.09   (sum 1.04)
///   Pregame: each contract's own eligible hourly bar ending 2026-10-09T00:00Z.
///   Four Day-5 report frames, each original with its own minute bar end:
///     09:11:34Z report  SA 0.03 @09:11  AUS 0.64 @09:11  TIE 0.35 @09:11
///     09:49:56Z lunch   SA 0.01 @09:46  AUS 0.87 @09:48  TIE 0.17 @09:45
///     11:03:34Z report  SA 0.02 @11:03  AUS 0.79 @11:03  TIE 0.20 @11:02
///     11:11:58Z report  SA 0.01 @11:09  AUS 0.95 @11:11  TIE 0.03 @11:11
///   Bar ends are not exact trade or app-arrival clocks (both null). No
///   internal app event/market/outcome id is retained. Final contract results
///   were captured later and are not inputs.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// row ids (the retained source + ticker + side, carried as opaque strings),
/// every display string, the local-calendar provenance words, the movement
/// words, the phase labels, heading and notes, every action reference
/// (none is retained, so the retained rows carry none), missing, withheld,
/// zero, malformed, duplicate, held, long-label and extra-row cases, and every
/// measured width.
final class CricketOutlookPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let sa = "kalshi:KXTESTMATCH-26OCT090330AUSSA-SA:yes"
    private static let aus = "kalshi:KXTESTMATCH-26OCT090330AUSSA-AUS:yes"
    private static let tie = "kalshi:KXTESTMATCH-26OCT090330AUSSA-TIE:yes"
    private static let order = [sa, aus, tie]

    private static let subjects: [String: String] = [sa: "South Africa", aus: "Australia", tie: "Draw / tie"]
    private static let shapes: [String: CricketOutlookShape10868] = [sa: .circle, aus: .diamond, tie: .square]
    private static let tints: [String: Color] = [sa: .blue, aus: .orange, tie: .gray]

    /// ARCHIVED.
    private static let pregameBarEnd = "2026-10-09T00:00:00+00:00"
    private static let pregameProbability: [String: Double] = [sa: 0.48, aus: 0.47, tie: 0.09]
    /// CONSTRUCTED owner text.
    private static let pregameText: [String: String] = [sa: "48%", aus: "47%", tie: "9%"]
    /// CONSTRUCTED local-calendar words for the ARCHIVED hourly bar.
    private static let pregameDetail = "Kalshi trade close · hour 4–5 PM PDT, Oct 8"

    private struct Recorded {
        /// ARCHIVED.
        let probability: Double
        /// ARCHIVED bar end (UTC).
        let barEnd: String
        /// CONSTRUCTED owner text.
        let text: String
        /// CONSTRUCTED local-calendar words for that minute bar.
        let detail: String
        /// CONSTRUCTED owner movement.
        let movement: String
        let spokenMovement: String
    }

    private struct Frame {
        /// ARCHIVED report key and publication time.
        let key: String
        let reportedAt: String
        let recorded: [String: Recorded]
    }

    private static func recorded(_ probability: Double, _ barEnd: String, _ text: String, _ minute: String, up: Bool, _ points: String) -> Recorded {
        Recorded(
            probability: probability,
            barEnd: barEnd,
            text: text,
            detail: "Kalshi trade close · minute \(minute) PDT, Oct 13",
            movement: "\(up ? "↑" : "↓") \(points) points",
            spokenMovement: "\(up ? "Up" : "Down") \(points) percentage points from pregame"
        )
    }

    private static let frames: [Frame] = [
        Frame(key: "block-6acdf5298f084a13d13ca4ea", reportedAt: "2026-10-13T09:11:34Z", recorded: [
            sa: recorded(0.03, "2026-10-13T09:11:00Z", "3%", "2:10–2:11 AM", up: false, "45"),
            aus: recorded(0.64, "2026-10-13T09:11:00Z", "64%", "2:10–2:11 AM", up: true, "17"),
            tie: recorded(0.35, "2026-10-13T09:11:00Z", "35%", "2:10–2:11 AM", up: true, "26"),
        ]),
        Frame(key: "block-6acdfe288f08741d63f9bedf", reportedAt: "2026-10-13T09:49:56Z", recorded: [
            sa: recorded(0.01, "2026-10-13T09:46:00Z", "1%", "2:45–2:46 AM", up: false, "47"),
            aus: recorded(0.87, "2026-10-13T09:48:00Z", "87%", "2:47–2:48 AM", up: true, "40"),
            tie: recorded(0.17, "2026-10-13T09:45:00Z", "17%", "2:44–2:45 AM", up: true, "8"),
        ]),
        Frame(key: "block-6ace0f308f0874762783cf04", reportedAt: "2026-10-13T11:03:34Z", recorded: [
            sa: recorded(0.02, "2026-10-13T11:03:00Z", "2%", "4:02–4:03 AM", up: false, "46"),
            aus: recorded(0.79, "2026-10-13T11:03:00Z", "79%", "4:02–4:03 AM", up: true, "32"),
            tie: recorded(0.2, "2026-10-13T11:02:00Z", "20%", "4:01–4:02 AM", up: true, "11"),
        ]),
        Frame(key: "block-6ace11b98f0811efce0fe34a", reportedAt: "2026-10-13T11:11:58Z", recorded: [
            sa: recorded(0.01, "2026-10-13T11:09:00Z", "1%", "4:08–4:09 AM", up: false, "47"),
            aus: recorded(0.95, "2026-10-13T11:11:00Z", "95%", "4:10–4:11 AM", up: true, "48"),
            tie: recorded(0.03, "2026-10-13T11:11:00Z", "3%", "4:10–4:11 AM", up: false, "6"),
        ]),
    ]

    private static let unavailable = "Unavailable"
    private static let withheld = "Held — not current"
    private static let notes = [
        "Changes are percentage points, not runs or wickets.",
        "Reconstructed from published score reports and separately recorded trades — not a live feed.",
    ]

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> CricketOutlookObservation10868 {
        CricketOutlookObservation10868(probability: probability, text: text, detail: detail)
    }

    /// Retained ids only. A CONSTRUCTED row passes its own explicit `before`.
    private static func pregame(_ id: String) -> CricketOutlookReading10868 {
        .observed(obs(pregameProbability[id]!, pregameText[id]!, pregameDetail))
    }

    private static func row(
        _ id: String,
        subject: String? = nil,
        shape: CricketOutlookShape10868? = nil,
        ref: CricketOutlookRef10868? = nil,
        before: CricketOutlookReading10868? = nil,
        comparison: CricketOutlookReading10868,
        movement: CricketOutlookMovement10868? = nil
    ) -> CricketOutlookRow10868 {
        CricketOutlookRow10868(
            id: id,
            subject: subject ?? subjects[id] ?? id,
            shape: shape ?? shapes[id] ?? .circle,
            tint: tints[id] ?? .gray,
            ref: ref,
            before: before ?? pregame(id),
            comparison: comparison,
            movement: movement
        )
    }

    /// One retained frame's row for one original, with no action reference.
    private static func retainedRow(_ id: String, frame: Int, ref: CricketOutlookRef10868? = nil) -> CricketOutlookRow10868 {
        let reading = frames[frame].recorded[id]!
        return row(
            id,
            ref: ref,
            comparison: .observed(obs(reading.probability, reading.text, reading.detail)),
            movement: CricketOutlookMovement10868(text: reading.movement, spoken: reading.spokenMovement)
        )
    }

    private static func input(
        _ rows: [CricketOutlookRow10868],
        comparisonLabel: String = "Recorded",
        selected: String? = nil,
        title: String? = "How the outlook changed",
        notes: [String] = notes
    ) -> CricketOutlookInput10868 {
        CricketOutlookInput10868(
            eyebrow: "Pregame → recorded chance",
            title: title,
            beforeLabel: "Pregame",
            comparisonLabel: comparisonLabel,
            rows: rows,
            selectedRowID: selected,
            notes: notes
        )
    }

    private static func retained(frame: Int, selected: String? = nil) -> CricketOutlookInput10868 {
        input(order.map { retainedRow($0, frame: frame) }, selected: selected)
    }

    /// CONSTRUCTED owner references — none is retained.
    private static func ref(_ id: String) -> CricketOutlookRef10868 {
        CricketOutlookRef10868(event: "owner-event", market: "owner-market-\(id.suffix(7))", outcome: "owner-outcome-\(id.suffix(7))")
    }

    private static func withRefs(frame: Int, selected: String? = nil) -> CricketOutlookInput10868 {
        input(order.map { retainedRow($0, frame: frame, ref: ref($0)) }, selected: selected)
    }

    private static func iso(_ text: String) -> Date {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: text)!
    }

    // MARK: The retained packet

    func testThreeOriginalsKeepOwnerOrderSubjectsShapesAndCarryNoInventedReference() {
        for frame in Self.frames.indices {
            let model = Self.retained(frame: frame)
            XCTAssertEqual(model.rows.map(\.id), Self.order)
            XCTAssertEqual(model.rows.map(\.subject), ["South Africa", "Australia", "Draw / tie"])
            XCTAssertEqual(model.rows.map(\.shape), [.circle, .diamond, .square])
            for row in model.rows {
                XCTAssertNil(row.ref, "no internal app id is retained, so none is invented")
                XCTAssertNil(model.actionableRef(row))
                XCTAssertNil(model.rowAction(row, canSelect: true))
            }
        }
    }

    func testPregameReadingsKeepTheirOwnHourlyBarAndSumTo104WithoutNormalization() {
        let model = Self.retained(frame: 0)
        let before = model.rows.compactMap { $0.before.observation }
        XCTAssertEqual(before.map(\.text), ["48%", "47%", "9%"])
        XCTAssertEqual(before.map(\.probability), [0.48, 0.47, 0.09])
        XCTAssertEqual(before.map(\.probability).reduce(0, +), 1.04, accuracy: 1e-9)
        XCTAssertEqual(model.rows.map { model.marks($0).before }, [0.48, 0.47, 0.09])
        XCTAssertEqual(Set(before.map(\.detail)), [Self.pregameDetail])
        XCTAssertEqual(Self.iso(Self.pregameBarEnd), Self.iso("2026-10-09T00:00:00Z"))
    }

    func testEveryRetainedFrameKeepsEachOriginalsOwnRecordedFigureMarkAndBar() {
        for (index, frame) in Self.frames.enumerated() {
            let model = Self.retained(frame: index)
            for row in model.rows {
                let expected = frame.recorded[row.id]!
                XCTAssertEqual(row.comparison, .observed(Self.obs(expected.probability, expected.text, expected.detail)), "\(frame.key) \(row.id)")
                XCTAssertEqual(model.marks(row).comparison, expected.probability)
                XCTAssertEqual(model.marks(row).before, Self.pregameProbability[row.id])
                XCTAssertTrue(model.showsMark(row.comparison))
                XCTAssertFalse(model.isNotDrawn(row.comparison))
            }
        }
    }

    func testRetainedReadingsPrecedeTheirReportAndNoLaterResultIsAnInput() {
        for frame in Self.frames {
            for (_, reading) in frame.recorded {
                XCTAssertLessThanOrEqual(Self.iso(reading.barEnd), Self.iso(frame.reportedAt), frame.key)
                XCTAssertGreaterThan(Self.iso(reading.barEnd), Self.iso(Self.pregameBarEnd))
            }
        }
        let labels = Set(Mirror(reflecting: Self.retained(frame: 3).rows[0]).children.compactMap { $0.label })
            .union(Mirror(reflecting: Self.retained(frame: 3)).children.compactMap { $0.label })
        for forbidden in ["result", "settlement", "score", "runs", "wickets", "overs", "winner"] {
            XCTAssertFalse(labels.contains { $0.lowercased().contains(forbidden) }, forbidden)
        }
    }

    func testLunchFrameKeepsThreeDifferentBarClocksNeverOneSharedTime() {
        let model = Self.retained(frame: 1)
        let details = model.rows.compactMap { $0.comparison.observation?.detail }
        XCTAssertEqual(details.count, 3)
        XCTAssertEqual(Set(details).count, 3)
        XCTAssertEqual(Set(Self.frames[1].recorded.values.map(\.barEnd)).count, 3)
        for row in model.rows {
            let value = model.accessibilityRowValue(row)
            XCTAssertTrue(value.contains(Self.frames[1].recorded[row.id]!.detail))
            for other in model.rows where other.id != row.id {
                XCTAssertFalse(value.contains(Self.frames[1].recorded[other.id]!.detail))
            }
        }
    }

    func testSeparatelyTimedFrameSumsStayUnnormalized() {
        let expected: [Double] = [1.02, 1.05, 1.01, 0.99]
        for frame in Self.frames.indices {
            let model = Self.retained(frame: frame)
            let marks = model.rows.compactMap { model.marks($0).comparison }
            XCTAssertEqual(marks.reduce(0, +), expected[frame], accuracy: 1e-9)
            XCTAssertEqual(marks, Self.order.map { Self.frames[frame].recorded[$0]!.probability })
        }
    }

    func testRemovingAnOriginalLeavesEveryOtherMarkAndFigureUnchanged() {
        let whole = Self.retained(frame: 2)
        let partial = Self.input(whole.rows.filter { $0.id != Self.aus })
        for row in partial.rows {
            let original = whole.rows.first { $0.id == row.id }!
            XCTAssertEqual(partial.marks(row), whole.marks(original))
            XCTAssertEqual(partial.accessibilityRowValue(row), whole.accessibilityRowValue(original))
        }
        XCTAssertEqual(partial.rows.map(\.id), [Self.sa, Self.tie])
    }

    // MARK: Movement

    func testMovementIsTheOwnersDirectionAndPointWordsVerbatim() {
        for (index, frame) in Self.frames.enumerated() {
            let model = Self.retained(frame: index)
            for row in model.rows {
                let expected = frame.recorded[row.id]!
                XCTAssertEqual(model.visibleMovement(row)?.text, expected.movement)
                XCTAssertTrue(model.accessibilityRowValue(row).contains(expected.spokenMovement))
                XCTAssertTrue(expected.spokenMovement.contains("percentage points"))
            }
        }
        let tieLast = Self.retained(frame: 3).rows[2]
        XCTAssertEqual(tieLast.movement?.text, "↓ 6 points")
    }

    func testZeroAndTinyMovementUseTheOwnersWordsWithNoPrivateRounding() {
        let none = CricketOutlookMovement10868(text: "No change", spoken: "No change from pregame")
        let tiny = CricketOutlookMovement10868(text: "↑ <0.1 points", spoken: "Up less than 0.1 percentage points from pregame")
        let flat = Self.row(Self.sa, comparison: .observed(Self.obs(0.48, "48%", "minute")), movement: none)
        let small = Self.row(Self.aus, comparison: .observed(Self.obs(0.4704, "47%", "minute")), movement: tiny)
        let model = Self.input([flat, small])
        XCTAssertEqual(model.visibleMovement(flat), none)
        XCTAssertEqual(model.visibleMovement(small), tiny)
        XCTAssertTrue(model.accessibilityRowValue(small).hasSuffix("Up less than 0.1 percentage points from pregame"))
        XCTAssertEqual(model.marks(flat).segment, 0.48...0.48)
    }

    func testRowWithoutOwnerMovementShowsNoneAndNothingIsComputed() {
        let row = Self.row(Self.sa, comparison: .observed(Self.obs(0.03, "3%", "minute")), movement: nil)
        let model = Self.input([row])
        XCTAssertNil(model.visibleMovement(row))
        XCTAssertEqual(model.accessibilityRowValue(row), "Pregame: 48%, \(Self.pregameDetail). Recorded: 3%, minute")
    }

    // MARK: Missing, withheld, zero, malformed

    func testUnavailableComparisonKeepsItsSlotWordsAndBaselineMarkButNoComparisonMarkConnectorOrMovement() {
        let movement = CricketOutlookMovement10868(text: "↓ 45 points", spoken: "Down 45 percentage points from pregame")
        let row = Self.row(Self.sa, comparison: .unavailable(Self.unavailable), movement: movement)
        let model = Self.input([row])
        XCTAssertEqual(row.comparison.words, Self.unavailable)
        XCTAssertEqual(model.marks(row), CricketOutlookMarks10868(before: 0.48, comparison: nil))
        XCTAssertNil(model.marks(row).segment)
        XCTAssertNil(model.visibleMovement(row))
        XCTAssertFalse(model.showsMark(row.comparison))
        XCTAssertTrue(model.showsMark(row.before))
        XCTAssertEqual(model.accessibilityRowValue(row), "Pregame: 48%, \(Self.pregameDetail). Recorded: Unavailable")
    }

    func testWithheldComparisonCarriesNoValueAndNeverFallsBackToPregame() {
        let row = Self.row(Self.aus, comparison: .withheld(Self.withheld))
        let model = Self.input([row])
        XCTAssertNil(row.comparison.observation)
        XCTAssertEqual(row.comparison.words, Self.withheld)
        XCTAssertNil(model.marks(row).comparison)
        XCTAssertNotEqual(row.comparison, row.before)
        XCTAssertEqual(model.accessibilityRowValue(row), "Pregame: 47%, \(Self.pregameDetail). Recorded: Held — not current")
    }

    func testMissingBaselineKeepsWordsAndAnAdmittedComparisonWithoutConnectorOrMovement() {
        let movement = CricketOutlookMovement10868(text: "↑ 26 points", spoken: "Up 26 percentage points from pregame")
        let row = Self.row(
            Self.tie,
            before: .unavailable("Not recorded before the match"),
            comparison: .observed(Self.obs(0.35, "35%", Self.frames[0].recorded[Self.tie]!.detail)),
            movement: movement
        )
        let model = Self.input([row])
        XCTAssertEqual(model.marks(row), CricketOutlookMarks10868(before: nil, comparison: 0.35))
        XCTAssertNil(model.marks(row).segment)
        XCTAssertNil(model.visibleMovement(row))
        XCTAssertFalse(model.showsPair(row))
        XCTAssertEqual(
            model.accessibilityRowValue(row),
            "Pregame: Not recorded before the match. Recorded: 35%, \(Self.frames[0].recorded[Self.tie]!.detail)"
        )
    }

    func testBothReadingsMissingDrawNoMarksAndKeepBothLabelledSlots() {
        let row = Self.row(Self.sa, before: .withheld("Pregame held"), comparison: .unavailable(Self.unavailable))
        let model = Self.input([row])
        XCTAssertEqual(model.marks(row), CricketOutlookMarks10868(before: nil, comparison: nil))
        XCTAssertEqual(model.accessibilityRowValue(row), "Pregame: Pregame held. Recorded: Unavailable")
    }

    func testZeroIsARealPlaceAndARealFigureNotAbsence() {
        let row = Self.row(Self.sa, comparison: .observed(Self.obs(0, "0%", "minute")))
        let model = Self.input([row])
        XCTAssertEqual(model.marks(row).comparison, 0)
        XCTAssertEqual(model.marks(row).segment, 0...0.48)
        XCTAssertTrue(model.showsMark(row.comparison))
        XCTAssertEqual(CricketOutlookGeometry10868.position(0), 0)
        XCTAssertEqual(CricketOutlookGeometry10868.position(1), 1)
        XCTAssertTrue(model.accessibilityRowValue(row).contains("Recorded: 0%, minute"))
    }

    func testMalformedGeometryDrawsNoMarkKeepsTheFigureAndSaysSoWithoutClamping() {
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.0000001, 1.2] {
            let row = Self.row(Self.aus, comparison: .observed(Self.obs(bad, "95%", "minute")))
            let model = Self.input([row])
            XCTAssertNil(CricketOutlookGeometry10868.position(bad), "\(bad)")
            XCTAssertNil(model.marks(row).comparison)
            XCTAssertNil(model.marks(row).segment)
            XCTAssertEqual(model.marks(row).before, 0.47)
            XCTAssertFalse(model.showsMark(row.comparison))
            XCTAssertTrue(model.isNotDrawn(row.comparison))
            XCTAssertEqual(row.comparison.observation?.text, "95%")
            XCTAssertTrue(model.accessibilityRowValue(row).contains("Recorded: 95%, minute, Not drawn on the scale"))
        }
        let badBefore = Self.row(Self.sa, before: .observed(Self.obs(-1, "48%", "hour")), comparison: .observed(Self.obs(0.03, "3%", "minute")))
        let model = Self.input([badBefore])
        XCTAssertEqual(model.marks(badBefore), CricketOutlookMarks10868(before: nil, comparison: 0.03))
        XCTAssertTrue(model.isNotDrawn(badBefore.before))
    }

    func testMarkPositionKeepsZeroAndHundredWholeOnTheTrack() {
        XCTAssertEqual(CricketOutlookGeometry10868.markX(0, width: 200, inset: 6), 6)
        XCTAssertEqual(CricketOutlookGeometry10868.markX(1, width: 200, inset: 6), 194)
        XCTAssertEqual(CricketOutlookGeometry10868.markX(0.5, width: 200, inset: 6), 100)
        XCTAssertEqual(CricketOutlookGeometry10868.markX(0.48, width: 12, inset: 6), 6)
        XCTAssertEqual(CricketOutlookGeometry10868.markX(0.48, width: 4, inset: 6), 6, "no negative usable width")
    }

    func testConnectorSpansExactlyTheTwoOwnMarksInEitherDirection() {
        let down = Self.retainedRow(Self.sa, frame: 0)
        let up = Self.retainedRow(Self.aus, frame: 3)
        let model = Self.input([down, up])
        XCTAssertEqual(model.marks(down).segment, 0.03...0.48)
        XCTAssertEqual(model.marks(up).segment, 0.47...0.95)
    }

    // MARK: Identity, selection and actions

    func testExactReferencesOnSelectAndDetails() {
        let model = Self.withRefs(frame: 1, selected: Self.aus)
        let rows = model.rows
        XCTAssertEqual(rows.map { model.rowAction($0, canSelect: true) }, Self.order.map { Optional(CricketOutlookAction10868.select(Self.ref($0))) })
        XCTAssertEqual(model.detailsAction(canOpenDetails: true), .details(Self.ref(Self.aus)))
        var selected: [CricketOutlookRef10868] = []
        var details: [CricketOutlookRef10868] = []
        model.rowAction(rows[2], canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        model.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.ref(Self.tie)])
        XCTAssertEqual(details, [Self.ref(Self.aus)])
    }

    func testNoCallbackMeansStaticRowsAndNoDetails() {
        let model = Self.withRefs(frame: 0, selected: Self.sa)
        for row in model.rows { XCTAssertNil(model.rowAction(row, canSelect: false)) }
        XCTAssertNil(model.detailsAction(canOpenDetails: false))
        XCTAssertTrue(model.isSelected(model.rows[0]))
    }

    func testSelectedRowWithoutAReferenceIsMarkedSelectedButOffersNoDetails() {
        let model = Self.retained(frame: 0, selected: Self.tie)
        XCTAssertTrue(model.isSelected(model.rows[2]))
        XCTAssertNil(model.selectionNotice)
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertTrue(model.accessibilityRowValue(model.rows[2]).hasSuffix("Selected"))
    }

    func testDuplicateRowIdsCarryNoActionAndCannotBeSelectedButStayListed() {
        let first = Self.retainedRow(Self.sa, frame: 0, ref: Self.ref(Self.sa))
        let twin = Self.row(Self.sa, subject: "South Africa (other row)", ref: Self.ref("other-row"), comparison: .unavailable(Self.unavailable))
        let model = Self.input([first, twin, Self.retainedRow(Self.aus, frame: 0, ref: Self.ref(Self.aus))], selected: Self.sa)
        XCTAssertEqual(model.duplicateRowIDs, [Self.sa])
        XCTAssertNil(model.rowAction(first, canSelect: true))
        XCTAssertNil(model.rowAction(twin, canSelect: true))
        XCTAssertNotNil(model.rowAction(model.rows[2], canSelect: true))
        XCTAssertEqual(model.selection, .unavailable(Self.sa))
        XCTAssertEqual(model.selectionNotice, CricketOutlookInput10868.selectionUnavailable)
        XCTAssertFalse(model.isSelected(first))
        XCTAssertFalse(model.isSelected(twin))
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertEqual(model.rows.count, 3)
    }

    func testDuplicateReferencesCarryNoActionSoNoTapReachesAnAmbiguousSubject() {
        let shared = Self.ref(Self.sa)
        let model = Self.input([
            Self.retainedRow(Self.sa, frame: 0, ref: shared),
            Self.retainedRow(Self.aus, frame: 0, ref: shared),
            Self.retainedRow(Self.tie, frame: 0, ref: Self.ref(Self.tie)),
        ], selected: Self.aus)
        XCTAssertEqual(model.duplicateRefs, [shared])
        XCTAssertNil(model.rowAction(model.rows[0], canSelect: true))
        XCTAssertNil(model.rowAction(model.rows[1], canSelect: true))
        XCTAssertEqual(model.rowAction(model.rows[2], canSelect: true), .select(Self.ref(Self.tie)))
        XCTAssertTrue(model.isSelected(model.rows[1]), "the row id is unique, so it may show as selected")
        XCTAssertNil(model.detailsAction(canOpenDetails: true), "but it hands back no ambiguous reference")
    }

    func testMissingSelectedRowShowsNoticeAndSelectsNoNeighbour() {
        let model = Self.withRefs(frame: 2, selected: "kalshi:KXTESTMATCH-26OCT090330AUSSA-NZ:yes")
        XCTAssertEqual(model.selection, .unavailable("kalshi:KXTESTMATCH-26OCT090330AUSSA-NZ:yes"))
        XCTAssertEqual(model.selectionNotice, CricketOutlookInput10868.selectionUnavailable)
        for row in model.rows {
            XCTAssertFalse(model.isSelected(row))
            XCTAssertNotNil(model.rowAction(row, canSelect: true))
        }
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertNil(Self.withRefs(frame: 2).selectionNotice)
        XCTAssertEqual(Self.withRefs(frame: 2).selection, .none)
    }

    func testHeldSelectionFollowsIdentityAcrossReorderAndNewFigures() {
        let before = Self.withRefs(frame: 0, selected: Self.tie)
        let rows = [Self.tie, Self.sa, Self.aus].map { Self.retainedRow($0, frame: 1, ref: Self.ref($0)) }
        let after = Self.input(rows, selected: Self.tie)
        XCTAssertEqual(before.selection.row?.comparison.observation?.text, "35%")
        XCTAssertEqual(after.selection.row?.id, Self.tie)
        XCTAssertEqual(after.selection.row?.comparison.observation?.text, "17%")
        XCTAssertEqual(after.rows.map(\.id), [Self.tie, Self.sa, Self.aus], "the owner's order, never re-sorted")
        XCTAssertEqual(after.detailsAction(canOpenDetails: true), .details(Self.ref(Self.tie)))
        XCTAssertEqual(after.rows.filter { after.isSelected($0) }.map(\.id), [Self.tie])
    }

    func testRowsKeepOwnerOrderAndHaveNoThreeItemCeilingOrHomeAwayDrawInference() {
        // CONSTRUCTED extra originals: none is retained, so each supplies its
        // own explicit missing pregame slot rather than a retained baseline.
        let noPregame = "No pregame reading for this outcome"
        let heldPregame = "Pregame held — not admitted"
        let extra = [
            Self.row("owner-row-4", subject: "No result", shape: .circle, before: .unavailable(noPregame), comparison: .unavailable(Self.unavailable)),
            Self.row("owner-row-5", subject: "Abandoned", shape: .diamond, before: .withheld(heldPregame), comparison: .withheld(Self.withheld)),
        ]
        let rows = [Self.retainedRow(Self.tie, frame: 0)] + extra + [Self.aus, Self.sa].map { Self.retainedRow($0, frame: 0) }
        let model = Self.input(rows)
        XCTAssertEqual(model.rows.map(\.id), [Self.tie, "owner-row-4", "owner-row-5", Self.aus, Self.sa])
        XCTAssertEqual(model.rows.map(\.shape), [.square, .circle, .diamond, .diamond, .circle], "shapes are the owner's, never inferred from a subject")
        XCTAssertEqual(model.rows.map { model.accessibilityRowValue($0) }.count, 5)

        // The extra rows keep their own constructed missing words and borrow no
        // other original's baseline, mark or movement.
        let fourth = model.rows[1]
        let fifth = model.rows[2]
        XCTAssertEqual(fourth.before, .unavailable(noPregame))
        XCTAssertEqual(fifth.before, .withheld(heldPregame))
        for extraRow in [fourth, fifth] {
            XCTAssertNil(extraRow.before.observation)
            XCTAssertEqual(model.marks(extraRow), CricketOutlookMarks10868(before: nil, comparison: nil))
            XCTAssertNil(model.visibleMovement(extraRow))
            XCTAssertFalse(model.showsMark(extraRow.before))
        }
        XCTAssertEqual(model.accessibilityRowValue(fourth), "Pregame: \(noPregame). Recorded: Unavailable")
        XCTAssertEqual(model.accessibilityRowValue(fifth), "Pregame: \(heldPregame). Recorded: Held — not current")
        XCTAssertEqual(model.rows.compactMap { model.marks($0).before }, [0.09, 0.47, 0.48], "retained baselines unchanged")
    }

    func testComparisonLabelIsTheOwnersWordRecordedOrCurrent() {
        let recorded = Self.retained(frame: 0)
        let current = Self.input(recorded.rows, comparisonLabel: "Current")
        XCTAssertTrue(recorded.accessibilityRowValue(recorded.rows[1]).contains("Recorded: 64%"))
        XCTAssertTrue(current.accessibilityRowValue(current.rows[1]).contains("Current: 64%"))
        XCTAssertFalse(current.accessibilityRowValue(current.rows[1]).contains("Recorded"))
        XCTAssertTrue(current.accessibilityKey!.contains("Filled mark: Current"))
    }

    // MARK: Words and VoiceOver

    func testSpokenRowNamesEachPhaseReadingWithItsOwnProvenanceAndTheOwnersMovement() {
        let model = Self.retained(frame: 1)
        XCTAssertEqual(
            model.accessibilityRowValue(model.rows[1]),
            "Pregame: 47%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. "
                + "Recorded: 87%, Kalshi trade close · minute 2:47–2:48 AM PDT, Oct 13. "
                + "Up 40 percentage points from pregame"
        )
        XCTAssertEqual(
            model.accessibilityRowValue(model.rows[0]),
            "Pregame: 48%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. "
                + "Recorded: 1%, Kalshi trade close · minute 2:45–2:46 AM PDT, Oct 13. "
                + "Down 47 percentage points from pregame"
        )
    }

    func testSpokenKeyNamesTheScaleBothPhaseMarksAndShapes() {
        let model = Self.retained(frame: 0)
        XCTAssertEqual(
            model.accessibilityKey,
            "Scale runs from 0% to 100% chance. Hollow mark: Pregame. Filled mark: Recorded. Each outcome keeps its own shape"
        )
        XCTAssertNil(Self.input([]).accessibilityKey, "no rows, no scale or key")
    }

    func testHeaderAndNotesAreVerbatimAndNoLiveFeedIsClaimed() {
        let model = Self.retained(frame: 0)
        XCTAssertEqual(model.accessibilityHeader, "Pregame → recorded chance. How the outlook changed")
        XCTAssertEqual(model.accessibilityNotes, Self.notes.joined(separator: " "))
        XCTAssertEqual(Self.input(model.rows, title: nil, notes: []).accessibilityHeader, "Pregame → recorded chance")
        XCTAssertNil(Self.input(model.rows, notes: []).accessibilityNotes)
        let spoken = ([model.accessibilityHeader, model.accessibilityKey ?? ""] + model.rows.map { model.accessibilityRowValue($0) })
            .joined(separator: " ")
        XCTAssertFalse(spoken.localizedCaseInsensitiveContains("live"))
    }

    func testFullSubjectQualifierDateAndProvenanceAreShownVerbatim() {
        let long = Self.row(
            Self.tie,
            subject: "Match drawn or tied after five full days in Durban",
            before: .observed(Self.obs(0.004, "<1%", "Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026")),
            comparison: .observed(Self.obs(0.996, "≥99.5%", "Kalshi trade close · minute 4:10–4:11 AM PDT, Tuesday, October 13, 2026")),
            movement: CricketOutlookMovement10868(text: "↑ 99.2 points", spoken: "Up 99.2 percentage points from pregame")
        )
        let model = Self.input([long])
        XCTAssertEqual(long.subject, "Match drawn or tied after five full days in Durban")
        XCTAssertEqual(
            model.accessibilityRowValue(long),
            "Pregame: <1%, Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026. "
                + "Recorded: ≥99.5%, Kalshi trade close · minute 4:10–4:11 AM PDT, Tuesday, October 13, 2026. "
                + "Up 99.2 percentage points from pregame"
        )
        XCTAssertEqual(model.marks(long), CricketOutlookMarks10868(before: 0.004, comparison: 0.996))
    }

    func testShapesAndPhaseFillsAreDistinctNonColourKeys() {
        let shapes = CricketOutlookShape10868.allCases
        XCTAssertEqual(Set(shapes.map(\.symbolName)).count, 3)
        XCTAssertEqual(Set(shapes.map(\.filledSymbolName)).count, 3)
        for shape in shapes { XCTAssertNotEqual(shape.symbolName, shape.filledSymbolName) }
        XCTAssertEqual(shapes.map(\.symbolName), ["circle", "diamond", "square"])
    }

    func testIdentifiersAreDistinctPerRowAndControl() {
        let ids = Self.order.map { CricketOutlookAccessibilityID10868.row($0) }
            + Self.order.map { CricketOutlookAccessibilityID10868.details($0) }
            + [CricketOutlookAccessibilityID10868.header, CricketOutlookAccessibilityID10868.key, CricketOutlookAccessibilityID10868.notes]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    // MARK: Layout

    /// CONSTRUCTED measurement: a whole figure keeps `figure` points; wrapping
    /// text never measures under `widestWord` and otherwise fits what it is
    /// offered.
    private static func measure(figure: CGFloat, widestWord: CGFloat, ideal: CGFloat) -> (CGFloat?) -> CGFloat {
        { proposal in
            guard let proposal else { return max(ideal, figure, widestWord) }
            return max(figure, widestWord, min(proposal, ideal))
        }
    }

    func testFigurePairSitsSideBySideAtPhoneAndWideWidthsWithStandardText() {
        // Card content width at 320/375/393 and a wide reader (CONSTRUCTED).
        for available: CGFloat in [256, 311, 329, 640] {
            let arrangement = CricketOutlookGeometry10868.pairArrangement(
                available: available,
                spacing: 16,
                equalColumns: true,
                forceStack: false,
                first: Self.measure(figure: 58, widestWord: 52, ideal: 230),
                second: Self.measure(figure: 58, widestWord: 52, ideal: 250)
            )
            XCTAssertEqual(arrangement, .sideBySide, "\(available)")
        }
    }

    func testPairStacksWhenAWholeFigureOrWordWouldNotFitOrAtAccessibilitySizes() {
        let tooWide = CricketOutlookGeometry10868.pairArrangement(
            available: 256, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(figure: 58, widestWord: 52, ideal: 230),
            second: Self.measure(figure: 132, widestWord: 52, ideal: 250)
        )
        XCTAssertEqual(tooWide, .stacked)
        let longWord = CricketOutlookGeometry10868.pairArrangement(
            available: 256, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(figure: 58, widestWord: 52, ideal: 230),
            second: Self.measure(figure: 0, widestWord: 141, ideal: 141)
        )
        XCTAssertEqual(longWord, .stacked)
        let accessibility = CricketOutlookGeometry10868.pairArrangement(
            available: 640, spacing: 16, equalColumns: true, forceStack: true,
            first: Self.measure(figure: 58, widestWord: 52, ideal: 60),
            second: Self.measure(figure: 58, widestWord: 52, ideal: 60)
        )
        XCTAssertEqual(accessibility, .stacked)
        XCTAssertEqual(
            CricketOutlookGeometry10868.pairArrangement(
                available: nil, spacing: 16, equalColumns: true, forceStack: false,
                first: { _ in 999 }, second: { _ in 999 }
            ),
            .sideBySide,
            "an unbounded proposal keeps one row"
        )
    }

    func testSubjectAndMovementShareALineOnlyWhenBothFitWhole() {
        let fits = CricketOutlookGeometry10868.pairArrangement(
            available: 256, spacing: 12, equalColumns: false, forceStack: false,
            first: { _ in 104 }, second: { _ in 92 }
        )
        XCTAssertEqual(fits, .sideBySide)
        let long = CricketOutlookGeometry10868.pairArrangement(
            available: 256, spacing: 12, equalColumns: false, forceStack: false,
            first: { _ in 330 }, second: { _ in 92 }
        )
        XCTAssertEqual(long, .stacked)
        let malformed = CricketOutlookGeometry10868.pairArrangement(
            available: 256, spacing: 12, equalColumns: false, forceStack: false,
            first: { _ in .infinity }, second: { _ in 92 }
        )
        XCTAssertEqual(malformed, .stacked)
    }

    func testColumnsSplitEquallyForFiguresAndKeepTheMovementWholeAtTheTrailingEdge() {
        XCTAssertEqual(
            CricketOutlookGeometry10868.columns(total: 256, secondIdeal: 999, spacing: 16, equalColumns: true),
            CricketOutlookColumns10868(first: 120, second: 120)
        )
        XCTAssertEqual(
            CricketOutlookGeometry10868.columns(total: 256, secondIdeal: 92, spacing: 12, equalColumns: false),
            CricketOutlookColumns10868(first: 152, second: 92)
        )
        XCTAssertEqual(
            CricketOutlookGeometry10868.columns(total: 50, secondIdeal: 92, spacing: 12, equalColumns: false),
            CricketOutlookColumns10868(first: 0, second: 38)
        )
        XCTAssertEqual(CricketOutlookGeometry10868.equalColumn(available: 10, spacing: 16), 0)
    }

    func testWordsSplitOnlyAtWhitespaceAndKeepQualifiersWhole() {
        XCTAssertEqual(CricketOutlookGeometry10868.words("Draw / tie"), ["Draw", "/", "tie"])
        XCTAssertEqual(CricketOutlookGeometry10868.words("≥99.5% · 4:10–4:11 AM"), ["≥99.5%", "·", "4:10–4:11", "AM"])
        XCTAssertEqual(CricketOutlookGeometry10868.words("  "), [])
    }

    // MARK: Completed match — final expectations extension

    // ARCHIVED from `shipping-adoption-20261027/CRICKET-FINAL-EXPECTATIONS-RETAINED-CASES.json`
    // (sha256 e09bebd0…9091). The final score report was published at
    // 2026-10-13T11:24:20.000Z and confirmed at 11:26:55.000Z: South Africa
    // 206 all out (10 wickets, overs null); Australia won by 214 runs; the
    // target was 421. Each original Yes contract finalized separately at
    // 2026-10-13T12:35:49.612166Z: SA "no", AUS "yes", TIE "no". None of
    // these is an exact last-ball or app-arrival clock, and no internal app
    // id is retained.
    //
    // CONSTRUCTED owner words: the outcome descriptions (the packet's
    // reference-only Lost / Winner / No draw / tie), the Won/Lost grade copy
    // and glyphs, the local-calendar provenance, the labels, the context
    // lines, the notes, and every invalid, held, identity and width case. No
    // grade is derived from an outcome here, or the reverse.

    private static let finalReportedAt = "2026-10-13T11:24:20.000Z"
    private static let finalConfirmedAt = "2026-10-13T11:26:55.000Z"
    private static let contractsFinalizedAt = "2026-10-13T12:35:49.612166Z"
    /// CONSTRUCTED local-calendar words for the ARCHIVED report clocks.
    private static let reportDetail = "Score report 4:24 AM PDT, Oct 13 · margin confirmed 4:26 AM PDT"
    /// CONSTRUCTED local-calendar words for the ARCHIVED settlement clock.
    private static let gradeDetail = "Kalshi Yes contract · finalized 5:35 AM PDT, Oct 13"

    private struct RetainedFinal {
        let id: String
        /// ARCHIVED raw contract result. It is source evidence and never
        /// a renderer input.
        let sourceResult: String
        /// CONSTRUCTED owner words.
        let outcome: String
        let grade: String
        let gradeSymbol: String
    }

    private static let retainedFinals: [RetainedFinal] = [
        RetainedFinal(id: sa, sourceResult: "no", outcome: "Lost", grade: "Lost", gradeSymbol: "xmark.circle"),
        RetainedFinal(id: aus, sourceResult: "yes", outcome: "Winner", grade: "Won", gradeSymbol: "checkmark.circle"),
        RetainedFinal(id: tie, sourceResult: "no", outcome: "No draw / tie", grade: "Lost", gradeSymbol: "xmark.circle"),
    ]

    private static let finalContext = [
        "South Africa 206 all out · Australia won by 214 runs",
        "Final overs not reported",
        "Target 421 was the runs needed to win, not a projected score",
    ]

    private static let finalFrame = CricketOutlookFinalFrame10868(
        outcomeLabel: "Match",
        outcomeMissing: "Not reported",
        gradeLabel: "Original contract",
        context: finalContext
    )

    private static let finalNotes = ["Hollow marks are pregame chances. Result labels describe the match, not later probabilities."]

    private static func word(_ text: String, symbol: String? = nil, _ detail: String) -> CricketOutlookFinalWord10868 {
        CricketOutlookFinalWord10868(text: text, symbolName: symbol, detail: detail)
    }

    private static func finish(_ retained: RetainedFinal) -> CricketOutlookFinish10868 {
        CricketOutlookFinish10868(
            outcome: .admitted(word(retained.outcome, reportDetail)),
            grade: .admitted(word(retained.grade, symbol: retained.gradeSymbol, gradeDetail))
        )
    }

    /// Every field explicit. No retained dictionary is consulted, so a
    /// CONSTRUCTED id cannot trap.
    private static func finalRow(
        _ id: String,
        subject: String,
        shape: CricketOutlookShape10868,
        ref: CricketOutlookRef10868?,
        before: CricketOutlookReading10868,
        comparison: CricketOutlookReading10868,
        movement: CricketOutlookMovement10868?,
        finish: CricketOutlookFinish10868?
    ) -> CricketOutlookRow10868 {
        CricketOutlookRow10868(
            id: id,
            subject: subject,
            shape: shape,
            tint: .gray,
            ref: ref,
            before: before,
            comparison: comparison,
            movement: movement,
            finish: finish
        )
    }

    /// The three retained originals carrying a retained frame's old
    /// comparison reading and movement, plus their owner finish.
    private static func completedRows(comparisonFrame: Int = 3, refs: Bool = false) -> [CricketOutlookRow10868] {
        retainedFinals.map { retained in
            var row = retainedRow(retained.id, frame: comparisonFrame, ref: refs ? ref(retained.id) : nil)
            row.finish = finish(retained)
            return row
        }
    }

    private static func completed(
        _ rows: [CricketOutlookRow10868],
        selected: String? = nil,
        frame: CricketOutlookFinalFrame10868 = finalFrame
    ) -> CricketOutlookInput10868 {
        CricketOutlookInput10868(
            eyebrow: "Pregame expectations → result",
            title: "Australia was 47% pregame",
            beforeLabel: "Pregame",
            comparisonLabel: "Recorded",
            rows: rows,
            selectedRowID: selected,
            notes: finalNotes,
            mode: .completed(frame)
        )
    }

    /// Second resolution is enough to order clocks that are minutes apart.
    private static func isoSeconds(_ text: String) -> Date {
        iso(String(text.prefix(19)) + "Z")
    }

    private static func position(of part: String, in text: String) -> String.Index? {
        text.range(of: part)?.lowerBound
    }

    func testCompletedModeShowsEachOriginalsOwnPregameBesideItsReportedOutcomeAndSeparateGrade() {
        let model = Self.completed(Self.completedRows())
        XCTAssertTrue(model.isCompleted)
        XCTAssertEqual(model.rows.map(\.id), Self.order)
        XCTAssertEqual(model.rows.map(\.subject), ["South Africa", "Australia", "Draw / tie"])
        XCTAssertEqual(model.rows.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(model.rows.map { model.marks($0).before }, [0.48, 0.47, 0.09])
        XCTAssertEqual(model.rows.compactMap { model.marks($0).before }.reduce(0, +), 1.04, accuracy: 1e-9, "never normalized")
        XCTAssertEqual(model.rows.compactMap { $0.before.observation?.text }, ["48%", "47%", "9%"])
        XCTAssertEqual(model.rows.map { model.finalOutcome($0)?.word?.text }, ["Lost", "Winner", "No draw / tie"])
        XCTAssertEqual(model.rows.map { model.finalGrade($0)?.word?.text }, ["Lost", "Won", "Lost"])
        XCTAssertEqual(model.rows.map { model.finalGrade($0)?.word?.symbolName }, ["xmark.circle", "checkmark.circle", "xmark.circle"])
        XCTAssertEqual(model.rows.map { model.finalOutcome($0)?.word?.symbolName }, [nil, nil, nil])
        XCTAssertEqual(Self.retainedFinals.map(\.sourceResult), ["no", "yes", "no"], "ARCHIVED evidence, not an input")
        XCTAssertEqual(
            model.accessibilityRowValue(model.rows[1]),
            "Pregame: 47%, \(Self.pregameDetail). Match: Winner, \(Self.reportDetail). Original contract: Won, \(Self.gradeDetail)"
        )
        XCTAssertEqual(
            model.accessibilityRowValue(model.rows[2]),
            "Pregame: 9%, \(Self.pregameDetail). Match: No draw / tie, \(Self.reportDetail). Original contract: Lost, \(Self.gradeDetail)"
        )
    }

    func testCompletedModeKeepsPregameReportAndSettlementClocksSeparate() {
        XCTAssertLessThan(Self.iso(Self.pregameBarEnd), Self.isoSeconds(Self.finalReportedAt))
        XCTAssertLessThan(Self.isoSeconds(Self.finalReportedAt), Self.isoSeconds(Self.finalConfirmedAt))
        XCTAssertLessThan(Self.isoSeconds(Self.finalConfirmedAt), Self.isoSeconds(Self.contractsFinalizedAt))
        let model = Self.completed(Self.completedRows())
        for row in model.rows {
            let outcome = model.finalOutcome(row)?.word
            let grade = model.finalGrade(row)?.word
            XCTAssertEqual(outcome?.detail, Self.reportDetail)
            XCTAssertEqual(grade?.detail, Self.gradeDetail)
            XCTAssertNotEqual(outcome?.detail, grade?.detail)
            let value = model.accessibilityRowValue(row)
            let pregame = Self.position(of: Self.pregameDetail, in: value)
            let report = Self.position(of: Self.reportDetail, in: value)
            let settled = Self.position(of: Self.gradeDetail, in: value)
            XCTAssertNotNil(pregame)
            XCTAssertNotNil(report)
            XCTAssertNotNil(settled)
            if let pregame, let report, let settled {
                XCTAssertLessThan(pregame, report, "each clock is spoken in its own slot")
                XCTAssertLessThan(report, settled)
            }
        }
    }

    func testCompletedModeSuppressesEverySuppliedComparisonSettlementExtremeAndMovement() {
        for frame in Self.frames.indices {
            let model = Self.completed(Self.completedRows(comparisonFrame: frame))
            for row in model.rows {
                XCTAssertNotNil(row.comparison.observation, "an old reading is supplied")
                XCTAssertNotNil(row.movement, "an old movement is supplied")
                XCTAssertNil(model.marks(row).comparison, "no filled mark")
                XCTAssertNil(model.marks(row).segment, "no connector")
                XCTAssertNil(model.visibleMovement(row))
                XCTAssertFalse(model.showsPair(row))
                let value = model.accessibilityRowValue(row)
                XCTAssertFalse(value.contains(Self.frames[frame].recorded[row.id]!.detail))
                XCTAssertFalse(value.contains(Self.frames[frame].recorded[row.id]!.spokenMovement))
                XCTAssertFalse(value.contains("Recorded"))
            }
        }
        // CONSTRUCTED settlement-time prices supplied as comparison readings.
        let settlementPrice = "Last price at settlement"
        let extremes = [
            Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                          before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                          comparison: .observed(Self.obs(0, "0%", settlementPrice)),
                          movement: CricketOutlookMovement10868(text: "↓ 48 points", spoken: "Down 48 percentage points from pregame"),
                          finish: Self.finish(Self.retainedFinals[0])),
            Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                          before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                          comparison: .observed(Self.obs(1, "100%", settlementPrice)),
                          movement: CricketOutlookMovement10868(text: "↑ 53 points", spoken: "Up 53 percentage points from pregame"),
                          finish: Self.finish(Self.retainedFinals[1])),
        ]
        let withExtremes = Self.completed(extremes)
        let withoutComparison = Self.completed(extremes.map {
            Self.finalRow($0.id, subject: $0.subject, shape: $0.shape, ref: nil, before: $0.before,
                          comparison: .unavailable(Self.unavailable), movement: nil, finish: $0.finish)
        })
        for (row, bare) in zip(withExtremes.rows, withoutComparison.rows) {
            XCTAssertEqual(withExtremes.marks(row), CricketOutlookMarks10868(before: row.before.observation?.probability, comparison: nil))
            XCTAssertEqual(withExtremes.accessibilityRowValue(row), withoutComparison.accessibilityRowValue(bare), "a supplied comparison changes nothing")
            XCTAssertFalse(withExtremes.accessibilityRowValue(row).contains(settlementPrice))
            XCTAssertFalse(withExtremes.accessibilityRowValue(row).contains("100%"))
        }
        XCTAssertFalse(withExtremes.accessibilityKey!.contains("Filled mark"))
    }

    func testDefaultComparisonModeIgnoresEverySuppliedFinish() {
        let plain = Self.retained(frame: 3)
        let model = Self.input(Self.completedRows())
        XCTAssertEqual(model.mode, .comparison, "comparison unless the owner selects completed")
        XCTAssertFalse(model.isCompleted)
        XCTAssertNil(model.completion)
        XCTAssertEqual(model.finalContext, [])
        XCTAssertNil(model.accessibilityFinalContext)
        XCTAssertEqual(model.accessibilityKey, plain.accessibilityKey)
        for (row, original) in zip(model.rows, plain.rows) {
            XCTAssertNotNil(row.finish, "a later finish is supplied")
            XCTAssertNil(original.finish)
            XCTAssertNil(model.finalOutcome(row))
            XCTAssertNil(model.finalGrade(row))
            XCTAssertEqual(model.marks(row), plain.marks(original))
            XCTAssertEqual(model.visibleMovement(row), plain.visibleMovement(original))
            XCTAssertEqual(model.accessibilityRowValue(row), plain.accessibilityRowValue(original))
        }
        let spoken = model.rows.map { model.accessibilityRowValue($0) }.joined(separator: " ")
        for later in ["Winner", "Won", "Match:", "Original contract", Self.reportDetail, Self.gradeDetail] + Self.finalContext {
            XCTAssertFalse(spoken.contains(later), later)
        }
    }

    func testCompletedModeIsExplicitAndNeverInferredFromSuppliedWords() {
        let unfinished = Self.order.map { Self.retainedRow($0, frame: 3) }
        let model = Self.completed(unfinished)
        XCTAssertTrue(model.isCompleted, "selected by the owner, with no finish supplied")
        for row in model.rows {
            XCTAssertNil(row.finish)
            XCTAssertEqual(model.finalOutcome(row), .unavailable("Not reported"))
            XCTAssertNil(model.finalOutcome(row)?.word, "missing words are not an outcome")
            XCTAssertNil(model.finalGrade(row), "no grade slot without a supplied grade")
            XCTAssertNil(model.marks(row).comparison)
        }
        XCTAssertEqual(model.accessibilityRowValue(model.rows[0]), "Pregame: 48%, \(Self.pregameDetail). Match: Not reported")
        XCTAssertEqual(
            CricketOutlookInput10868(eyebrow: "e", title: nil, beforeLabel: "Pregame", comparisonLabel: "Recorded", rows: [], selectedRowID: nil, notes: []).mode,
            .comparison
        )
    }

    func testContractGradeStaysSeparateWhenUnconfirmedVoidContradictoryOrAbsent() {
        let winner = CricketOutlookFinalEntry10868.admitted(Self.word("Winner", Self.reportDetail))
        let grades: [CricketOutlookFinalEntry10868?] = [
            .unavailable("Contract result pending"),
            .admitted(Self.word("Void", "Kalshi Yes contract · voided, no payout either way")),
            .unavailable("Sources disagree — contract result not shown"),
            nil,
        ]
        for grade in grades {
            let row = Self.finalRow(
                Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                comparison: .unavailable(Self.unavailable), movement: nil,
                finish: CricketOutlookFinish10868(outcome: winner, grade: grade)
            )
            let model = Self.completed([row])
            XCTAssertEqual(model.finalOutcome(row), winner, "the match outcome stands on its own")
            XCTAssertEqual(model.finalGrade(row), grade, "the grade is the owner's, never derived from the outcome")
            XCTAssertEqual(model.rows.map(\.subject), ["Australia"])
            XCTAssertEqual(model.rows.map(\.shape), [.diamond])
            XCTAssertEqual(model.marks(row), CricketOutlookMarks10868(before: 0.47, comparison: nil))
            let value = model.accessibilityRowValue(row)
            XCTAssertTrue(value.contains("Match: Winner, \(Self.reportDetail)"))
            XCTAssertFalse(value.contains("Lost"), "nothing unknown becomes a loss")
            XCTAssertFalse(value.contains("Won"))
            switch grade {
            case .some(.admitted(let word)): XCTAssertTrue(value.hasSuffix("Original contract: \(word.text), \(word.detail)"))
            case .some(.unavailable(let words)): XCTAssertTrue(value.hasSuffix("Original contract: \(words)"))
            case .none: XCTAssertFalse(value.contains("Original contract"))
            }
        }
        // A reported loss with a pending grade manufactures no grade.
        let pendingLoss = Self.finalRow(
            Self.sa, subject: "South Africa", shape: .circle, ref: nil,
            before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
            comparison: .unavailable(Self.unavailable), movement: nil,
            finish: CricketOutlookFinish10868(outcome: .admitted(Self.word("Lost", Self.reportDetail)), grade: .unavailable("Contract result pending"))
        )
        let model = Self.completed([pendingLoss])
        XCTAssertNil(model.finalGrade(pendingLoss)?.word)
        XCTAssertEqual(model.accessibilityRowValue(pendingLoss).components(separatedBy: "Lost").count - 1, 1)
    }

    func testMissingPregameAndMissingFinishStayExplicitAndAreNeverReconstructed() {
        let tieFinal = Self.retainedFinals[2]
        let noPregame = Self.finalRow(
            Self.tie, subject: "Draw / tie", shape: .square, ref: nil,
            before: .unavailable("No pregame reading for this outcome"),
            comparison: .observed(Self.obs(0.03, "3%", Self.frames[3].recorded[Self.tie]!.detail)),
            movement: nil, finish: Self.finish(tieFinal)
        )
        // CONSTRUCTED extra original: no retained value, no supplied finish.
        let extra = Self.finalRow(
            "owner-row-4", subject: "No result", shape: .circle, ref: nil,
            before: .withheld("Pregame held — not admitted"),
            comparison: .withheld(Self.withheld), movement: nil, finish: nil
        )
        let rows = Self.completedRows().filter { $0.id != Self.tie } + [noPregame, extra]
        let model = Self.completed(rows)
        XCTAssertEqual(model.rows.map(\.id), [Self.sa, Self.aus, Self.tie, "owner-row-4"], "no three-row ceiling")
        XCTAssertEqual(model.marks(noPregame), CricketOutlookMarks10868(before: nil, comparison: nil), "never rebuilt from a final price")
        XCTAssertEqual(
            model.accessibilityRowValue(noPregame),
            "Pregame: No pregame reading for this outcome. Match: No draw / tie, \(Self.reportDetail). Original contract: Lost, \(Self.gradeDetail)"
        )
        XCTAssertEqual(model.marks(extra), CricketOutlookMarks10868(before: nil, comparison: nil))
        XCTAssertEqual(model.accessibilityRowValue(extra), "Pregame: Pregame held — not admitted. Match: Not reported")
        XCTAssertEqual(model.rows.compactMap { model.marks($0).before }, [0.48, 0.47], "other baselines unchanged")

        // A missing comparison reading changes nothing in completed mode.
        let withheldComparison = Self.finalRow(
            Self.tie, subject: "Draw / tie", shape: .square, ref: nil,
            before: noPregame.before, comparison: .withheld(Self.withheld), movement: nil, finish: noPregame.finish
        )
        XCTAssertEqual(model.accessibilityRowValue(noPregame), Self.completed([withheldComparison]).accessibilityRowValue(withheldComparison))
    }

    func testCompletedModeKeepsExactStaticDuplicateAndWithdrawnReferences() {
        let comparison = Self.withRefs(frame: 3, selected: Self.aus)
        let model = Self.completed(Self.completedRows(refs: true), selected: Self.aus)
        XCTAssertEqual(
            model.rows.map { model.rowAction($0, canSelect: true) },
            comparison.rows.map { comparison.rowAction($0, canSelect: true) },
            "an outcome neither grants nor changes a reference"
        )
        XCTAssertEqual(model.detailsAction(canOpenDetails: true), .details(Self.ref(Self.aus)))
        var selected: [CricketOutlookRef10868] = []
        var details: [CricketOutlookRef10868] = []
        model.rowAction(model.rows[0], canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        model.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.ref(Self.sa)])
        XCTAssertEqual(details, [Self.ref(Self.aus)])
        XCTAssertTrue(model.accessibilityRowValue(model.rows[1]).hasSuffix("Selected"))

        let staticModel = Self.completed(Self.completedRows(), selected: Self.aus)
        for row in staticModel.rows { XCTAssertNil(staticModel.rowAction(row, canSelect: true), "the winner's row has no reference either") }
        XCTAssertNil(staticModel.detailsAction(canOpenDetails: true))
        XCTAssertTrue(staticModel.isSelected(staticModel.rows[1]))

        var shared = Self.completedRows(refs: true)
        shared[1] = Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: Self.ref(Self.sa),
                                  before: shared[1].before, comparison: shared[1].comparison,
                                  movement: shared[1].movement, finish: shared[1].finish)
        let duplicate = Self.completed(shared, selected: Self.aus)
        XCTAssertNil(duplicate.rowAction(duplicate.rows[0], canSelect: true))
        XCTAssertNil(duplicate.rowAction(duplicate.rows[1], canSelect: true))
        XCTAssertEqual(duplicate.rowAction(duplicate.rows[2], canSelect: true), .select(Self.ref(Self.tie)))
        XCTAssertNil(duplicate.detailsAction(canOpenDetails: true))

        let withdrawn = Self.completed(Array(Self.completedRows(refs: true).prefix(2)), selected: Self.tie)
        XCTAssertEqual(withdrawn.selection, .unavailable(Self.tie))
        XCTAssertEqual(withdrawn.selectionNotice, CricketOutlookInput10868.selectionUnavailable)
        XCTAssertTrue(withdrawn.rows.allSatisfy { !withdrawn.isSelected($0) }, "no neighbour is selected")
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
    }

    func testCompletedLongOutcomeGradeQualifierContextAndProvenanceAreVerbatim() {
        let longReport = "Score report 4:24 AM PDT, Tuesday, October 13, 2026 · margin confirmed 4:26 AM PDT, Tuesday, October 13, 2026"
        let longGrade = "Kalshi Yes contract “Draw/Tie wins” · finalized 5:35 AM PDT, Tuesday, October 13, 2026 · settled after the reported finish"
        let row = Self.finalRow(
            Self.tie, subject: "Match drawn or tied after five full days in Durban", shape: .square, ref: nil,
            before: .observed(Self.obs(0.09, "9%", "Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026")),
            comparison: .unavailable(Self.unavailable), movement: nil,
            finish: CricketOutlookFinish10868(
                outcome: .admitted(Self.word("No draw or tie — the match reached a result on day five", longReport)),
                grade: .admitted(Self.word("Lost — this Yes contract did not pay", symbol: "xmark.circle", longGrade))
            )
        )
        let model = Self.completed([row])
        XCTAssertEqual(
            model.accessibilityRowValue(row),
            "Pregame: 9%, Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026. "
                + "Match: No draw or tie — the match reached a result on day five, \(longReport). "
                + "Original contract: Lost — this Yes contract did not pay, \(longGrade)"
        )
        XCTAssertEqual(model.finalContext, Self.finalContext)
        XCTAssertEqual(model.accessibilityFinalContext, Self.finalContext.joined(separator: " "))
        XCTAssertEqual(model.accessibilityHeader, "Pregame expectations → result. Australia was 47% pregame")
        XCTAssertEqual(model.accessibilityNotes, Self.finalNotes.joined(separator: " "))
        XCTAssertNil(Self.completed([row], frame: CricketOutlookFinalFrame10868(
            outcomeLabel: "Match", outcomeMissing: "Not reported", gradeLabel: "Original contract", context: []
        )).accessibilityFinalContext)
    }

    func testCompletedSpokenKeyNamesOnlyTheHollowPregameMarkAndIdentifiersStayDistinct() {
        let model = Self.completed(Self.completedRows())
        XCTAssertEqual(
            model.accessibilityKey,
            "Scale runs from 0% to 100% chance. Hollow mark: Pregame. Each outcome keeps its own shape"
        )
        XCTAssertNil(Self.completed([]).accessibilityKey)
        let ids = Self.order.map { CricketOutlookAccessibilityID10868.row($0) }
            + Self.order.map { CricketOutlookAccessibilityID10868.details($0) }
            + [
                CricketOutlookAccessibilityID10868.header,
                CricketOutlookAccessibilityID10868.key,
                CricketOutlookAccessibilityID10868.notes,
                CricketOutlookAccessibilityID10868.context,
            ]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    func testOutcomePairSitsSideBySideAtPhoneAndWideWidthsAndStacksForLongWordsOrAccessibility() {
        // CONSTRUCTED: a whole 26-point pregame figure beside a 20-point outcome
        // word, at card content widths for 320/375/393 and a wide reader.
        let pregame = Self.measure(figure: 58, widestWord: 52, ideal: 230)
        let outcome = Self.measure(figure: 0, widestWord: 72, ideal: 190)
        for available: CGFloat in [256, 311, 329, 640] {
            XCTAssertEqual(
                CricketOutlookGeometry10868.pairArrangement(
                    available: available, spacing: 16, equalColumns: true, forceStack: false, first: pregame, second: outcome
                ),
                .sideBySide,
                "\(available)"
            )
        }
        let longWord = Self.measure(figure: 0, widestWord: 141, ideal: 260)
        XCTAssertEqual(
            CricketOutlookGeometry10868.pairArrangement(
                available: 256, spacing: 16, equalColumns: true, forceStack: false, first: pregame, second: longWord
            ),
            .stacked,
            "an unbreakable outcome word stacks the pair instead of splitting"
        )
        XCTAssertEqual(
            CricketOutlookGeometry10868.pairArrangement(
                available: 640, spacing: 16, equalColumns: true, forceStack: false, first: pregame, second: longWord
            ),
            .sideBySide
        )
        XCTAssertEqual(
            CricketOutlookGeometry10868.pairArrangement(
                available: 640, spacing: 16, equalColumns: true, forceStack: true, first: pregame, second: outcome
            ),
            .stacked
        )
    }

    func testCompletedInputsAddOnlyTheModeAndFinishAndStillTakeNoScoreRunsWicketsOrOvers() {
        let model = Self.completed(Self.completedRows())
        let inputLabels = Mirror(reflecting: model).children.compactMap { $0.label }
        let rowLabels = Mirror(reflecting: model.rows[0]).children.compactMap { $0.label }
        let frameLabels = Mirror(reflecting: Self.finalFrame).children.compactMap { $0.label }
        let finishLabels = Mirror(reflecting: model.rows[0].finish!).children.compactMap { $0.label }
        XCTAssertEqual(inputLabels, ["eyebrow", "title", "beforeLabel", "comparisonLabel", "rows", "selectedRowID", "notes", "mode"])
        XCTAssertEqual(rowLabels, ["id", "subject", "shape", "tint", "ref", "before", "comparison", "movement", "finish"])
        XCTAssertEqual(frameLabels, ["outcomeLabel", "outcomeMissing", "gradeLabel", "context"])
        XCTAssertEqual(finishLabels, ["outcome", "grade"])
        for label in inputLabels + rowLabels + frameLabels + finishLabels {
            for forbidden in ["score", "runs", "wickets", "overs", "target", "probability", "price"] {
                XCTAssertFalse(label.lowercased().contains(forbidden), "\(label) / \(forbidden)")
            }
        }
    }

    // MARK: Match headline — before, during and completed play

    // The same ARCHIVED originals, pregame bars, Day-5 frames and final report
    // as above, re-retained in
    // `shipping-adoption-20261027/CRICKET-HEADLINE-RETAINED-CASES.json`
    // (sha256 0aa7236a…5a43). ARCHIVED score-report context for the four
    // frames (publication times, not ball times):
    //   09:11:34Z  64 overs  154/4
    //   09:49:56Z  lunch     166/6  (73.0 overs)
    //   11:03:34Z  84 overs  201/6
    //   11:11:58Z  85 overs  201/8
    // Target 421 is the runs South Africa needed to win, not a projection.
    // Final: 206 all out, overs null, Australia won by 214 runs.
    //
    // CONSTRUCTED: every caption, label, state word, spoken form and state
    // provenance line; every missing, withheld, zero, equal-value, extreme,
    // long-label and five-row case; every measured width. Constructed rows
    // pass every field explicitly through `finalRow`, so no retained
    // dictionary is consulted for them.

    private struct HeadlineReport {
        /// ARCHIVED.
        let runs: Int
        let wickets: Int
        /// CONSTRUCTED owner words.
        let oversText: String
        let detail: String
    }

    private static let headlineReports: [HeadlineReport] = [
        HeadlineReport(runs: 154, wickets: 4, oversText: "64 overs", detail: "Score report 2:11 AM PDT, Oct 13 · published time, not ball time"),
        HeadlineReport(runs: 166, wickets: 6, oversText: "Lunch · 73 overs", detail: "Score report 2:49 AM PDT, Oct 13 · published time, not ball time"),
        HeadlineReport(runs: 201, wickets: 6, oversText: "84 overs", detail: "Score report 4:03 AM PDT, Oct 13 · published time, not ball time"),
        HeadlineReport(runs: 201, wickets: 8, oversText: "85 overs", detail: "Score report 4:11 AM PDT, Oct 13 · published time, not ball time"),
    ]

    /// CONSTRUCTED owner state words for an ARCHIVED report.
    private static func duringState(_ frame: Int) -> CricketHeadlineState10868 {
        let report = headlineReports[frame]
        return .reported(CricketHeadlineStateFrame10868(
            entries: [
                CricketHeadlineStateEntry10868(
                    label: "South Africa · batting",
                    text: "\(report.runs)/\(report.wickets)",
                    spoken: "\(report.runs) for \(report.wickets)"
                ),
                CricketHeadlineStateEntry10868(
                    label: report.oversText,
                    text: "Target 421",
                    spoken: "Target 421 runs to win, not a projected score"
                ),
            ],
            detail: report.detail
        ))
    }

    private static let completedStateDetail = "Final score report 4:24 AM PDT, Oct 13 · final overs not reported"

    /// CONSTRUCTED owner state words for the ARCHIVED final report.
    private static let completedState = CricketHeadlineState10868.reported(CricketHeadlineStateFrame10868(
        entries: [
            CricketHeadlineStateEntry10868(label: "South Africa", text: "206 all out", spoken: "206 all out"),
            CricketHeadlineStateEntry10868(label: nil, text: "Australia won by 214 runs", spoken: "Australia won by 214 runs"),
        ],
        detail: completedStateDetail
    ))

    private static func headline(
        _ phase: CricketHeadlinePhase10868,
        _ rows: [CricketOutlookRow10868],
        caption: String? = nil,
        comparisonLabel: String = "Recorded",
        state: CricketHeadlineState10868? = nil
    ) -> CricketHeadlineInput10868 {
        CricketHeadlineInput10868(
            phase: phase,
            caption: caption,
            beforeLabel: "Pregame",
            comparisonLabel: comparisonLabel,
            outcomeLabel: "Match",
            outcomeMissing: "Not reported",
            rows: rows,
            state: state
        )
    }

    private static func headlineValues(_ model: CricketHeadlineInput10868) -> [String] {
        model.rows.map { model.accessibilityRowValue($0) }
    }

    func testHeadlineBeforeShowsOnlyEachOriginalsOwnPregameFigureUnnormalized() {
        let model = Self.headline(
            .before,
            Self.order.map { Self.row($0, comparison: .unavailable(Self.unavailable)) },
            caption: "Pregame · hourly trade closes ending 5 PM PDT, Oct 8"
        )
        XCTAssertEqual(model.slots, [.pregame])
        XCTAssertEqual(model.cellsPerRow, 2)
        XCTAssertEqual(model.cells.count, 6)
        XCTAssertEqual(model.rows.map(\.id), Self.order)
        XCTAssertEqual(model.rows.map(\.subject), ["South Africa", "Australia", "Draw / tie"])
        XCTAssertEqual(model.rows.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(model.rows.map(\.tint), [.blue, .orange, .gray])
        let pregame = model.rows.compactMap { $0.before.observation }
        XCTAssertEqual(pregame.map(\.text), ["48%", "47%", "9%"])
        XCTAssertEqual(pregame.map(\.probability).reduce(0, +), 1.04, accuracy: 1e-9, "never normalized")
        XCTAssertTrue(model.rows.allSatisfy { model.showsKey($0.before) }, "each pregame figure keeps its hollow key")
        XCTAssertEqual(Self.headlineValues(model), [
            "Pregame: 48%, \(Self.pregameDetail)",
            "Pregame: 47%, \(Self.pregameDetail)",
            "Pregame: 9%, \(Self.pregameDetail)",
        ])
        XCTAssertNil(model.visibleState)
        XCTAssertNil(model.accessibilityState)
    }

    func testHeadlineBeforeSuppressesEverySuppliedLaterReadingMovementOutcomeGradeAndState() {
        for frame in Self.frames.indices {
            for state in [Self.duringState(frame), Self.completedState] {
                let model = Self.headline(.before, Self.completedRows(comparisonFrame: frame), state: state)
                XCTAssertNil(model.visibleState, "a supplied state stays hidden before play")
                XCTAssertNil(model.accessibilityState)
                XCTAssertEqual(
                    model.cells.map(\.kind),
                    Array(repeating: [CricketHeadlineCellKind10868.subject, .reading(.pregame)], count: 3).flatMap { $0 }
                )
                for row in model.rows {
                    XCTAssertNotNil(row.comparison.observation, "a later reading is supplied")
                    XCTAssertNotNil(row.movement)
                    XCTAssertNotNil(row.finish?.grade)
                    XCTAssertNil(model.comparison(row))
                    XCTAssertNil(model.outcome(row))
                    let value = model.accessibilityRowValue(row)
                    XCTAssertEqual(value, "Pregame: \(Self.pregameText[row.id]!), \(Self.pregameDetail)")
                    let recorded = Self.frames[frame].recorded[row.id]!
                    for later in [recorded.detail, recorded.spokenMovement, "Recorded", "Match", "Winner", "Won", "Lost",
                                  Self.reportDetail, Self.gradeDetail, "154", "206", "Target"] {
                        XCTAssertFalse(value.contains(later), later)
                    }
                }
            }
        }
    }

    func testHeadlineDuringShowsEveryRetainedFramesPregameAndRecordedFigureWithItsOwnClock() {
        let sums: [Double] = [1.02, 1.05, 1.01, 0.99]
        for (index, frame) in Self.frames.enumerated() {
            let model = Self.headline(.during, Self.order.map { Self.retainedRow($0, frame: index) }, state: Self.duringState(index))
            XCTAssertEqual(model.slots, [.pregame, .comparison])
            XCTAssertEqual(model.cells.count, 9)
            for row in model.rows {
                let expected = frame.recorded[row.id]!
                XCTAssertEqual(model.comparison(row), .observed(Self.obs(expected.probability, expected.text, expected.detail)), frame.key)
                XCTAssertNil(model.outcome(row))
                XCTAssertTrue(model.showsKey(row.before))
                XCTAssertTrue(model.showsKey(row.comparison))
                let value = model.accessibilityRowValue(row)
                XCTAssertEqual(value, "Pregame: \(Self.pregameText[row.id]!), \(Self.pregameDetail). Recorded: \(expected.text), \(expected.detail)")
                XCTAssertFalse(value.contains(expected.spokenMovement), "the headline repeats no movement")
                for other in model.rows where frame.recorded[other.id]!.detail != expected.detail {
                    XCTAssertFalse(value.contains(frame.recorded[other.id]!.detail), "no shared clock")
                }
            }
            let recorded = model.rows.compactMap { model.comparison($0)?.observation?.probability }
            XCTAssertEqual(recorded.reduce(0, +), sums[index], accuracy: 1e-9, "never normalized")
        }
        let lunch = Self.headline(.during, Self.order.map { Self.retainedRow($0, frame: 1) })
        XCTAssertEqual(Set(lunch.rows.compactMap { lunch.comparison($0)?.observation?.detail }).count, 3, "three separate bar clocks")
    }

    func testHeadlineDuringStateIsTheOwnersWordsAndStaysIndependentOfTheReadings() {
        let rows = Self.order.map { Self.retainedRow($0, frame: 0) }
        let model = Self.headline(.during, rows, state: Self.duringState(0))
        XCTAssertEqual(model.visibleState, Self.duringState(0))
        XCTAssertEqual(
            model.accessibilityState,
            "South Africa · batting: 154 for 4. 64 overs: Target 421 runs to win, not a projected score. "
                + "Score report 2:11 AM PDT, Oct 13 · published time, not ball time"
        )
        XCTAssertEqual(
            Self.headline(.during, rows, state: Self.duringState(1)).accessibilityState,
            "South Africa · batting: 166 for 6. Lunch · 73 overs: Target 421 runs to win, not a projected score. "
                + "Score report 2:49 AM PDT, Oct 13 · published time, not ball time"
        )

        let noState = Self.headline(.during, rows)
        XCTAssertNil(noState.visibleState)
        XCTAssertNil(noState.accessibilityState)
        XCTAssertEqual(Self.headlineValues(noState), Self.headlineValues(model), "a missing state erases no reading")

        let unavailable = Self.headline(.during, rows, state: .unavailable("Score unavailable"))
        XCTAssertEqual(unavailable.accessibilityState, "Score unavailable")
        XCTAssertEqual(Self.headlineValues(unavailable), Self.headlineValues(model))

        let empty = Self.headline(.during, rows, state: .reported(CricketHeadlineStateFrame10868(entries: [], detail: nil)))
        XCTAssertNil(empty.accessibilityState)

        // CONSTRUCTED: no admitted reading anywhere, state still reported.
        let originals: [(String, String, CricketOutlookShape10868)] = [
            (Self.sa, "South Africa", CricketOutlookShape10868.circle),
            (Self.aus, "Australia", CricketOutlookShape10868.diamond),
            (Self.tie, "Draw / tie", CricketOutlookShape10868.square),
        ]
        let blank = originals.map { original in
            Self.finalRow(original.0, subject: original.1, shape: original.2, ref: nil,
                          before: .unavailable("Not recorded"), comparison: .withheld(Self.withheld), movement: nil, finish: nil)
        }
        let noReadings = Self.headline(.during, blank, state: Self.duringState(0))
        XCTAssertEqual(noReadings.accessibilityState, model.accessibilityState, "missing chances erase no state")
        XCTAssertEqual(Set(Self.headlineValues(noReadings)), ["Pregame: Not recorded. Recorded: Held — not current"])
    }

    func testHeadlineDuringEachMissingOrWithheldReadingKeepsItsOwnWordsAndBorrowsNothing() {
        let ausDetail = Self.frames[0].recorded[Self.aus]!.detail
        let rows = [
            Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                          before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                          comparison: .unavailable(Self.unavailable),
                          movement: CricketOutlookMovement10868(text: "↓ 45 points", spoken: "Down 45 percentage points from pregame"),
                          finish: nil),
            Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                          before: .withheld("Pregame held — not admitted"),
                          comparison: .observed(Self.obs(0.64, "64%", ausDetail)),
                          movement: nil, finish: nil),
            Self.finalRow(Self.tie, subject: "Draw / tie", shape: .square, ref: nil,
                          before: .unavailable("No pregame reading for this outcome"),
                          comparison: .withheld(Self.withheld),
                          movement: nil, finish: nil),
        ]
        let model = Self.headline(.during, rows, state: Self.duringState(0))
        XCTAssertEqual(Self.headlineValues(model), [
            "Pregame: 48%, \(Self.pregameDetail). Recorded: Unavailable",
            "Pregame: Pregame held — not admitted. Recorded: 64%, \(ausDetail)",
            "Pregame: No pregame reading for this outcome. Recorded: Held — not current",
        ])
        XCTAssertEqual(model.rows.map { model.showsKey($0.before) }, [true, false, false])
        XCTAssertEqual(model.rows.map { model.showsKey($0.comparison) }, [false, true, false])
        XCTAssertNotNil(model.visibleState)
    }

    func testHeadlineRealZeroIsAFigureAndAbsenceIsWords() {
        // CONSTRUCTED 0% reading; the retained closes never reach zero.
        let zeroDetail = "Kalshi trade close · minute 4:08–4:09 AM PDT, Oct 13"
        let zero = Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                                 before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                                 comparison: .observed(Self.obs(0, "0%", zeroDetail)), movement: nil, finish: nil)
        let absent = Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                                   before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                                   comparison: .unavailable(Self.unavailable), movement: nil, finish: nil)
        let model = Self.headline(.during, [zero, absent])
        XCTAssertEqual(model.comparison(zero)?.observation?.probability, 0)
        XCTAssertTrue(model.showsKey(zero.comparison))
        XCTAssertFalse(model.showsKey(absent.comparison))
        XCTAssertEqual(Self.headlineValues(model), [
            "Pregame: 48%, \(Self.pregameDetail). Recorded: 0%, \(zeroDetail)",
            "Pregame: 47%, \(Self.pregameDetail). Recorded: Unavailable",
        ])
    }

    func testHeadlineEqualFiguresFromDifferentObservationsStaySeparate() {
        // CONSTRUCTED: a later reading that happens to equal the pregame figure.
        let laterDetail = "Kalshi trade close · minute 2:30–2:31 AM PDT, Oct 13"
        let row = Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                                before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                                comparison: .observed(Self.obs(0.47, "47%", laterDetail)),
                                movement: CricketOutlookMovement10868(text: "No change", spoken: "No change from pregame"),
                                finish: nil)
        let model = Self.headline(.during, [row], comparisonLabel: "Current")
        let value = model.accessibilityRowValue(row)
        XCTAssertEqual(value, "Pregame: 47%, \(Self.pregameDetail). Current: 47%, \(laterDetail)")
        XCTAssertEqual(value.components(separatedBy: "47%").count - 1, 2, "two figures, never merged")
        XCTAssertNotEqual(model.comparison(row), row.before)
        XCTAssertFalse(value.contains("No change"))
        XCTAssertFalse(value.contains("Recorded"), "the owner's word only")
    }

    func testHeadlineCompletedShowsEachPregameBesideItsReportedOutcomeAndSuppressesComparisonMovementAndGrade() {
        for frame in Self.frames.indices {
            let model = Self.headline(.completed, Self.completedRows(comparisonFrame: frame), state: Self.completedState)
            XCTAssertEqual(model.slots, [.pregame, .outcome])
            XCTAssertEqual(model.cells.count, 9)
            XCTAssertEqual(model.rows.map { model.outcome($0)?.word?.text }, ["Lost", "Winner", "No draw / tie"])
            XCTAssertEqual(model.rows.compactMap { $0.before.observation?.probability }.reduce(0, +), 1.04, accuracy: 1e-9)
            for row in model.rows {
                XCTAssertNil(model.comparison(row))
                XCTAssertNotNil(row.finish?.grade, "a grade is supplied")
                let value = model.accessibilityRowValue(row)
                let recorded = Self.frames[frame].recorded[row.id]!
                for hidden in [Self.gradeDetail, "Original contract", "Won", "Recorded", recorded.detail, recorded.spokenMovement] {
                    XCTAssertFalse(value.contains(hidden), hidden)
                }
            }
            XCTAssertEqual(Self.headlineValues(model), [
                "Pregame: 48%, \(Self.pregameDetail). Match: Lost, \(Self.reportDetail)",
                "Pregame: 47%, \(Self.pregameDetail). Match: Winner, \(Self.reportDetail)",
                "Pregame: 9%, \(Self.pregameDetail). Match: No draw / tie, \(Self.reportDetail)",
            ])
        }
        let model = Self.headline(.completed, Self.completedRows(), state: Self.completedState)
        XCTAssertEqual(model.accessibilityState, "South Africa: 206 all out. Australia won by 214 runs. \(Self.completedStateDetail)")
    }

    func testHeadlineCompletedNeverShowsASettlementExtremeAsAChance() {
        // CONSTRUCTED settlement-time prices supplied as comparison readings.
        let settlement = "Last price at settlement"
        let rows = [
            Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                          before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                          comparison: .observed(Self.obs(0, "0%", settlement)),
                          movement: nil, finish: Self.finish(Self.retainedFinals[0])),
            Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                          before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                          comparison: .observed(Self.obs(1, "100%", settlement)),
                          movement: nil, finish: Self.finish(Self.retainedFinals[1])),
        ]
        let bare = rows.map {
            Self.finalRow($0.id, subject: $0.subject, shape: $0.shape, ref: nil, before: $0.before,
                          comparison: .unavailable(Self.unavailable), movement: nil, finish: $0.finish)
        }
        let model = Self.headline(.completed, rows)
        let control = Self.headline(.completed, bare)
        XCTAssertEqual(Self.headlineValues(model), Self.headlineValues(control), "a supplied comparison changes nothing")
        for value in Self.headlineValues(model) {
            XCTAssertFalse(value.contains(settlement))
            XCTAssertFalse(value.contains("0%"))
        }
    }

    func testHeadlineCompletedMissingOutcomeIsNeverInferredFromTheGradeOrAPrice() {
        let won = CricketOutlookFinalEntry10868.admitted(Self.word("Won", symbol: "checkmark.circle", Self.gradeDetail))
        let lost = CricketOutlookFinalEntry10868.admitted(Self.word("Lost", symbol: "xmark.circle", Self.gradeDetail))
        let unreported = Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                                       before: .observed(Self.obs(0.47, "47%", Self.pregameDetail)),
                                       comparison: .observed(Self.obs(0.95, "95%", Self.frames[3].recorded[Self.aus]!.detail)),
                                       movement: nil,
                                       finish: CricketOutlookFinish10868(outcome: .unavailable("Result not yet reported"), grade: won))
        let noFinish = Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                                     before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                                     comparison: .observed(Self.obs(0.01, "1%", Self.frames[3].recorded[Self.sa]!.detail)),
                                     movement: nil, finish: nil)
        let pendingTie = Self.finalRow(Self.tie, subject: "Draw / tie", shape: .square, ref: nil,
                                       before: .observed(Self.obs(0.09, "9%", Self.pregameDetail)),
                                       comparison: .unavailable(Self.unavailable), movement: nil,
                                       finish: CricketOutlookFinish10868(outcome: .unavailable("Not reported"), grade: lost))
        let model = Self.headline(.completed, [unreported, noFinish, pendingTie])
        XCTAssertEqual(Self.headlineValues(model), [
            "Pregame: 47%, \(Self.pregameDetail). Match: Result not yet reported",
            "Pregame: 48%, \(Self.pregameDetail). Match: Not reported",
            "Pregame: 9%, \(Self.pregameDetail). Match: Not reported",
        ])
        for row in model.rows {
            XCTAssertNil(model.outcome(row)?.word, "missing words are not an outcome")
            let value = model.accessibilityRowValue(row)
            for inferred in ["Won", "Lost", "Winner", "95%", "1%"] { XCTAssertFalse(value.contains(inferred), inferred) }
        }
    }

    func testHeadlinePhaseIsExplicitAndNeverInferredFromSuppliedInputs() {
        let rows = Self.completedRows(comparisonFrame: 2)
        let before = Self.headline(.before, rows, state: Self.completedState)
        let during = Self.headline(.during, rows, state: Self.completedState)
        let completed = Self.headline(.completed, rows, state: Self.completedState)
        XCTAssertEqual([before.slots, during.slots, completed.slots], [[.pregame], [.pregame, .comparison], [.pregame, .outcome]])
        XCTAssertEqual(
            during.accessibilityRowValue(during.rows[1]),
            "Pregame: 47%, \(Self.pregameDetail). Recorded: 79%, \(Self.frames[2].recorded[Self.aus]!.detail)",
            "a supplied finish does not end the match"
        )
        XCTAssertEqual(completed.accessibilityRowValue(completed.rows[1]), "Pregame: 47%, \(Self.pregameDetail). Match: Winner, \(Self.reportDetail)")
        XCTAssertNil(before.visibleState)
        XCTAssertEqual(during.visibleState, Self.completedState, "the owner chose this state for this phase")
        XCTAssertEqual(completed.visibleState, Self.completedState)

        // Completed with nothing later supplied is still completed.
        let unfinished = Self.headline(.completed, Self.order.map { Self.row($0, comparison: .unavailable(Self.unavailable)) })
        XCTAssertEqual(
            unfinished.rows.compactMap { unfinished.outcome($0) },
            [CricketOutlookFinalEntry10868](repeating: .unavailable("Not reported"), count: 3)
        )
    }

    func testHeadlineKeepsEveryConstructedRowInOwnerOrderWithItsOwnShapeAndNoCap() {
        // CONSTRUCTED five explicit rows — robustness only, not an approved route.
        let five = [
            Self.finalRow("owner-row-a", subject: "Draw / tie", shape: .square, ref: nil,
                          before: .observed(Self.obs(0.09, "9%", "owner hour A")), comparison: .observed(Self.obs(0.03, "3%", "owner minute A")),
                          movement: nil, finish: nil),
            Self.finalRow("owner-row-b", subject: "No result", shape: .circle, ref: nil,
                          before: .unavailable("No pregame reading"), comparison: .unavailable(Self.unavailable),
                          movement: nil, finish: nil),
            Self.finalRow("owner-row-c", subject: "Abandoned", shape: .diamond, ref: nil,
                          before: .withheld("Pregame held"), comparison: .withheld(Self.withheld),
                          movement: nil, finish: nil),
            Self.finalRow("owner-row-d", subject: "Australia", shape: .diamond, ref: nil,
                          before: .observed(Self.obs(0.47, "47%", "owner hour D")), comparison: .observed(Self.obs(0.95, "95%", "owner minute D")),
                          movement: nil, finish: nil),
            Self.finalRow("owner-row-e", subject: "South Africa", shape: .circle, ref: nil,
                          before: .observed(Self.obs(0.48, "48%", "owner hour E")), comparison: .observed(Self.obs(0.01, "1%", "owner minute E")),
                          movement: nil, finish: nil),
        ]
        let model = Self.headline(.during, five)
        XCTAssertEqual(model.rows.map(\.id), ["owner-row-a", "owner-row-b", "owner-row-c", "owner-row-d", "owner-row-e"])
        XCTAssertEqual(model.rows.map(\.shape), [.square, .circle, .diamond, .diamond, .circle])
        XCTAssertEqual(model.cells.count, 15)
        XCTAssertEqual(model.cells.filter { $0.kind == .subject }.map(\.row), [0, 1, 2, 3, 4])
        XCTAssertEqual(model.cells[3], CricketHeadlineCell10868(row: 1, kind: .subject))
        XCTAssertEqual(model.cells[5], CricketHeadlineCell10868(row: 1, kind: .reading(.comparison)))
        XCTAssertEqual(Self.headlineValues(model), [
            "Pregame: 9%, owner hour A. Recorded: 3%, owner minute A",
            "Pregame: No pregame reading. Recorded: Unavailable",
            "Pregame: Pregame held. Recorded: Held — not current",
            "Pregame: 47%, owner hour D. Recorded: 95%, owner minute D",
            "Pregame: 48%, owner hour E. Recorded: 1%, owner minute E",
        ])
        XCTAssertEqual(Self.headline(.completed, five).rows.compactMap { Self.headline(.completed, five).outcome($0) }.count, 5)
        XCTAssertTrue(Self.headline(.during, []).cells.isEmpty)
    }

    func testHeadlineLongSubjectQualifierProvenanceAndStateAreVerbatim() {
        let pregameLong = "Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026"
        let currentLong = "Kalshi trade close · minute 4:10–4:11 AM PDT, Tuesday, October 13, 2026 · owner-admitted as current"
        let row = Self.finalRow(Self.tie, subject: "Match drawn or tied after five full days in Durban", shape: .square, ref: nil,
                                before: .observed(Self.obs(0.004, "<1%", pregameLong)),
                                comparison: .observed(Self.obs(0.996, "≥99.5%", currentLong)),
                                movement: nil, finish: nil)
        let state = CricketHeadlineState10868.reported(CricketHeadlineStateFrame10868(
            entries: [CricketHeadlineStateEntry10868(
                label: "South Africa · second innings · batting",
                text: "201/8",
                spoken: "201 for 8 wickets"
            )],
            detail: "Score report 4:11 AM PDT, Tuesday, October 13, 2026 · publication time, not the time of the ball"
        ))
        let caption = "Each chance keeps its own trade minute · Day 5 · 85-over report"
        let model = Self.headline(.during, [row], caption: caption, comparisonLabel: "Current", state: state)
        XCTAssertEqual(model.caption, caption)
        XCTAssertEqual(model.rows[0].subject, "Match drawn or tied after five full days in Durban")
        XCTAssertEqual(model.accessibilityRowValue(row), "Pregame: <1%, \(pregameLong). Current: ≥99.5%, \(currentLong)")
        XCTAssertEqual(
            model.accessibilityState,
            "South Africa · second innings · batting: 201 for 8 wickets. "
                + "Score report 4:11 AM PDT, Tuesday, October 13, 2026 · publication time, not the time of the ball"
        )
    }

    // MARK: Match headline layout

    /// CONSTRUCTED cell widths, in cell order: (figure, widest word, ideal).
    private static func cellWidths(_ specs: [(CGFloat, CGFloat, CGFloat)]) -> (Int, CGFloat?) -> CGFloat {
        { index, proposal in Self.measure(figure: specs[index].0, widestWord: specs[index].1, ideal: specs[index].2)(proposal) }
    }

    private static let subjectCell: (CGFloat, CGFloat, CGFloat) = (0, 46, 90)
    private static let figureCell: (CGFloat, CGFloat, CGFloat) = (58, 46, 230)
    private static let outcomeCell: (CGFloat, CGFloat, CGFloat) = (0, 52, 190)

    private static func blocks(_ count: Int, _ cells: [(CGFloat, CGFloat, CGFloat)]) -> [(CGFloat, CGFloat, CGFloat)] {
        Array(repeating: cells, count: count).flatMap { $0 }
    }

    func testHeadlineThreeColumnsAtPhoneAndWideWidthsWithStandardText() {
        // Card content widths at 320/375/393 and a wide reader (CONSTRUCTED).
        let phases: [(Int, [(CGFloat, CGFloat, CGFloat)])] = [
            (2, Self.blocks(3, [Self.subjectCell, Self.figureCell])),
            (3, Self.blocks(3, [Self.subjectCell, Self.figureCell, Self.figureCell])),
            (3, Self.blocks(3, [Self.subjectCell, Self.figureCell, Self.outcomeCell])),
        ]
        for (perBlock, specs) in phases {
            for available: CGFloat in [256, 311, 329, 640] {
                XCTAssertEqual(
                    CricketHeadlineGeometry10868.arrangement(
                        available: available, spacing: 12, blocks: 3, cellsPerBlock: perBlock, forceStack: false,
                        measure: Self.cellWidths(specs)
                    ),
                    .columns,
                    "\(perBlock) \(available)"
                )
            }
        }
    }

    func testHeadlineStacksIntoNamedBlocksWhenAWholeFigureOrWordWouldNotFitOrAtAccessibilitySizes() {
        let wideFigure: (CGFloat, CGFloat, CGFloat) = (95, 46, 230)
        let wide = Self.blocks(3, [Self.subjectCell, Self.figureCell, wideFigure])
        func arrange(_ available: CGFloat?, _ specs: [(CGFloat, CGFloat, CGFloat)], blocks: Int = 3, per: Int = 3, force: Bool = false) -> CricketHeadlineArrangement10868 {
            CricketHeadlineGeometry10868.arrangement(
                available: available, spacing: 12, blocks: blocks, cellsPerBlock: per, forceStack: force, measure: Self.cellWidths(specs)
            )
        }
        XCTAssertEqual(arrange(256, wide), .blocks(readingsSideBySide: true), "a whole ≥99.5% figure stacks the columns but fits a half")
        XCTAssertEqual(arrange(640, wide), .columns)
        let longWord = Self.blocks(3, [Self.subjectCell, Self.figureCell, (0, 141, 260)])
        XCTAssertEqual(arrange(256, longWord), .blocks(readingsSideBySide: false), "an unbreakable word never splits")
        XCTAssertEqual(arrange(640, Self.blocks(3, [Self.subjectCell, Self.figureCell, Self.figureCell]), force: true), .blocks(readingsSideBySide: false))
        XCTAssertEqual(arrange(nil, wide), .columns, "an unbounded proposal keeps one line")
        XCTAssertEqual(arrange(nil, [Self.subjectCell, Self.figureCell, Self.figureCell], blocks: 1), .blocks(readingsSideBySide: true))
        XCTAssertEqual(arrange(256, [Self.subjectCell, Self.figureCell], blocks: 1, per: 2), .blocks(readingsSideBySide: false))
        let malformed = Self.blocks(3, [Self.subjectCell, (.infinity, 46, 230), Self.figureCell])
        XCTAssertEqual(arrange(640, malformed), .blocks(readingsSideBySide: false))
        XCTAssertEqual(arrange(640, [], blocks: 0), .blocks(readingsSideBySide: false))
    }

    func testHeadlineFiveConstructedRowsUseColumnsOnlyWhenEveryCellFits() {
        let five = Self.blocks(5, [Self.subjectCell, Self.figureCell, Self.figureCell])
        func arrange(_ available: CGFloat) -> CricketHeadlineArrangement10868 {
            CricketHeadlineGeometry10868.arrangement(
                available: available, spacing: 12, blocks: 5, cellsPerBlock: 3, forceStack: false, measure: Self.cellWidths(five)
            )
        }
        XCTAssertEqual(arrange(640), .columns)
        XCTAssertEqual(arrange(329), .blocks(readingsSideBySide: true))
        XCTAssertEqual(arrange(256), .blocks(readingsSideBySide: true))
        XCTAssertEqual(arrange(120), .blocks(readingsSideBySide: false))
    }

    func testHeadlineColumnWidthsAndStateEntryArrangement() {
        XCTAssertEqual(CricketHeadlineGeometry10868.column(available: 256, spacing: 12, count: 3), 232.0 / 3, accuracy: 1e-9)
        XCTAssertEqual(CricketHeadlineGeometry10868.column(available: 640, spacing: 12, count: 5), 118.4, accuracy: 1e-9)
        XCTAssertEqual(CricketHeadlineGeometry10868.column(available: 20, spacing: 12, count: 3), 0)
        XCTAssertEqual(CricketHeadlineGeometry10868.column(available: 256, spacing: 12, count: 0), 0)
        // CONSTRUCTED state entries ("South Africa · batting / 154/4", "64 overs / Target 421").
        let entries: [(CGFloat, CGFloat, CGFloat)] = [(0, 62, 150), (0, 70, 110)]
        func arrange(_ specs: [(CGFloat, CGFloat, CGFloat)], force: Bool = false) -> CricketHeadlineArrangement10868 {
            CricketHeadlineGeometry10868.arrangement(
                available: 256, spacing: 20, blocks: specs.count, cellsPerBlock: 1, forceStack: force, measure: Self.cellWidths(specs)
            )
        }
        XCTAssertEqual(arrange(entries), .columns)
        XCTAssertEqual(arrange([(0, 62, 150), (0, 130, 130)]), .blocks(readingsSideBySide: false))
        XCTAssertEqual(arrange([entries[0]]), .blocks(readingsSideBySide: false))
        XCTAssertEqual(arrange(entries, force: true), .blocks(readingsSideBySide: false))
    }

    // MARK: Match headline inputs and identifiers

    func testHeadlineInputsTakeOnlyOwnerWordsAndNoScoreParserForecastOrGrade() {
        let model = Self.headline(.completed, Self.completedRows(), state: Self.completedState)
        let inputLabels = Mirror(reflecting: model).children.compactMap { $0.label }
        let frameLabels = Mirror(reflecting: CricketHeadlineStateFrame10868(entries: [], detail: nil)).children.compactMap { $0.label }
        let entryLabels = Mirror(reflecting: CricketHeadlineStateEntry10868(label: nil, text: "", spoken: "")).children.compactMap { $0.label }
        XCTAssertEqual(inputLabels, ["phase", "caption", "beforeLabel", "comparisonLabel", "outcomeLabel", "outcomeMissing", "rows", "state"])
        XCTAssertEqual(frameLabels, ["entries", "detail"])
        XCTAssertEqual(entryLabels, ["label", "text", "spoken"])
        for label in inputLabels + frameLabels + entryLabels {
            for forbidden in ["score", "runs", "wickets", "overs", "target", "margin", "projection", "forecast",
                              "probability", "price", "grade", "ticker", "winner", "date", "time"] {
                XCTAssertFalse(label.lowercased().contains(forbidden), "\(label) / \(forbidden)")
            }
        }
        XCTAssertNil(Self.headline(.during, []).state, "the state is optional and defaults to none")
    }

    func testHeadlineIdentifiersAreDistinctAndSeparateFromTheOutlookCard() {
        let ids = Self.order.map { CricketHeadlineAccessibilityID10868.row($0) }
            + [CricketHeadlineAccessibilityID10868.caption, CricketHeadlineAccessibilityID10868.state]
            + Self.order.map { CricketOutlookAccessibilityID10868.row($0) }
            + [
                CricketOutlookAccessibilityID10868.header,
                CricketOutlookAccessibilityID10868.key,
                CricketOutlookAccessibilityID10868.notes,
                CricketOutlookAccessibilityID10868.context,
            ]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    // MARK: Pregame story card — T20 before the first ball

    // ARCHIVED from `shipping-adoption-20261027/T20-BEFORE-STORY-RETAINED-CASES.json`
    // (sha256 c5c10bc1…6d52): India v West Indies, second T20I, Ranchi,
    // October 9, 2026 (route cricket-t20). Two original Kalshi winner
    // contracts, independently traded:
    //   IND  KXT20MATCH-26OCT090930WIIND-IND  close 0.7800  minute bar end 12:57:00Z
    //   WI   KXT20MATCH-26OCT090930WIIND-WI   close 0.2300  minute bar end 12:57:00Z
    // The pre-match report describing the match as upcoming was published at
    // 2026-10-09T12:57:17Z, 17 s after both bars end. 78 + 23 = 101 is not
    // adjusted and no draw is added: the contracts' tie/no-result rule pays
    // $0.50, a settlement amount and not a third prediction. Market close
    // (17:40:24Z) and settlement (17:45:23.67777Z) are later facts and never
    // inputs. No internal app id, arrival time or first-ball time is retained.
    //
    // CONSTRUCTED owner inputs (the packet's constructed_owner_words): the row
    // ids, eyebrow, title, "Pregame chance to win" label, figures, provenance
    // words and note. CONSTRUCTED later facts, supplied only to prove they stay
    // hidden: the 67% / 34% readings and their words, the movement, 249/5,
    // 187/4, target 250, "West Indies won" and the original grade "Won". Also
    // constructed: every missing, held, zero, one, malformed, long-label,
    // one-row, five-row and empty case, and every measured width.

    private static let t20India = "constructed:pregame:india"
    private static let t20WestIndies = "constructed:pregame:west-indies"
    /// ARCHIVED clocks (settlement truncated to the second).
    private static let t20BarEnd = "2026-10-09T12:57:00Z"
    private static let t20ReportedAt = "2026-10-09T12:57:17Z"
    private static let t20MarketClose = "2026-10-09T17:40:24Z"
    private static let t20Settled = "2026-10-09T17:45:23Z"
    /// CONSTRUCTED local-calendar words for the ARCHIVED minute bar.
    private static let t20Detail = "Kalshi trade close · minute 5:56–5:57 AM PDT, October 9, 2026"
    private static let t20Label = "Pregame chance to win"
    private static let t20Note = "Two independently traded winner markets. No chase target or projected final is known in this retained pre-match frame."

    /// Every field explicit; no retained dictionary is consulted.
    private static func t20Row(
        _ id: String,
        subject: String,
        shape: CricketOutlookShape10868,
        tint: Color,
        before: CricketOutlookReading10868,
        comparison: CricketOutlookReading10868 = .unavailable("Unavailable"),
        movement: CricketOutlookMovement10868? = nil,
        finish: CricketOutlookFinish10868? = nil
    ) -> CricketOutlookRow10868 {
        CricketOutlookRow10868(
            id: id,
            subject: subject,
            shape: shape,
            tint: tint,
            ref: nil,
            before: before,
            comparison: comparison,
            movement: movement,
            finish: finish
        )
    }

    /// The two ARCHIVED pregame readings in CONSTRUCTED owner words; either
    /// side may be replaced on its own.
    private static func t20Retained(
        india: CricketOutlookReading10868? = nil,
        westIndies: CricketOutlookReading10868? = nil
    ) -> [CricketOutlookRow10868] {
        [
            t20Row(t20India, subject: "India", shape: .circle, tint: .blue,
                   before: india ?? .observed(obs(0.78, "78%", t20Detail))),
            t20Row(t20WestIndies, subject: "West Indies", shape: .diamond, tint: .orange,
                   before: westIndies ?? .observed(obs(0.23, "23%", t20Detail))),
        ]
    }

    /// The same two pregame readings, each row also carrying every
    /// CONSTRUCTED later fact.
    private static func t20WithLaterFacts() -> [CricketOutlookRow10868] {
        [
            t20Row(
                t20India, subject: "India", shape: .circle, tint: .blue,
                before: .observed(obs(0.78, "78%", t20Detail)),
                comparison: .observed(obs(0.67, "67%", "Kalshi trade close · after India 249/5")),
                movement: CricketOutlookMovement10868(text: "↓ 11 points", spoken: "Down 11 percentage points from pregame"),
                finish: CricketOutlookFinish10868(
                    outcome: .admitted(word("Lost", "Score report · West Indies won chasing target 250")),
                    grade: .admitted(word("Lost", symbol: "xmark.circle", "Kalshi Yes contract · finalized"))
                )
            ),
            t20Row(
                t20WestIndies, subject: "West Indies", shape: .diamond, tint: .orange,
                before: .observed(obs(0.23, "23%", t20Detail)),
                comparison: .observed(obs(0.34, "34%", "Kalshi trade close · West Indies 187/4 chasing target 250")),
                movement: CricketOutlookMovement10868(text: "↑ 11 points", spoken: "Up 11 percentage points from pregame"),
                finish: CricketOutlookFinish10868(
                    outcome: .admitted(word("West Indies won", "Score report · 187/4 after India 249/5")),
                    grade: .admitted(word("Won", symbol: "checkmark.circle", "Kalshi Yes contract · finalized"))
                )
            ),
        ]
    }

    private static func pregameStory(
        _ phase: CricketHeadlinePhase10868,
        _ rows: [CricketOutlookRow10868],
        title: String? = "India starts as favorite",
        notes: [String] = [t20Note]
    ) -> CricketPregameStoryInput10868 {
        CricketPregameStoryInput10868(
            phase: phase,
            eyebrow: "Before the first ball",
            title: title,
            beforeLabel: t20Label,
            rows: rows,
            notes: notes
        )
    }

    private static func storyValues(_ model: CricketPregameStoryInput10868) -> [String?] {
        model.rows.map { model.accessibilityRowValue($0) }
    }

    private static var t20RetainedValues: [String?] {
        ["\(t20Label): 78%, \(t20Detail)", "\(t20Label): 23%, \(t20Detail)"]
    }

    func testPregameStoryShowsEachRetainedOriginalsOwnFigureAndRailUnnormalized() {
        let model = Self.pregameStory(.before, Self.t20Retained())
        XCTAssertTrue(model.isVisible)
        XCTAssertEqual(model.visibleRows.map(\.id), [Self.t20India, Self.t20WestIndies])
        XCTAssertEqual(model.visibleRows.map(\.subject), ["India", "West Indies"])
        XCTAssertEqual(model.visibleRows.map(\.shape), [.circle, .diamond])
        XCTAssertEqual(model.visibleRows.map(\.tint), [.blue, .orange])
        XCTAssertEqual(model.rows.compactMap { model.reading($0)?.observation?.text }, ["78%", "23%"])
        let fills = model.rows.compactMap { model.fill($0) }
        XCTAssertEqual(fills, [0.78, 0.23], "each rail is that original's own reading")
        XCTAssertEqual(fills.reduce(0, +), 1.01, accuracy: 1e-9, "never normalized or complemented")
        XCTAssertFalse(model.rows.contains { model.isNotDrawn($0) })
        XCTAssertEqual(Self.storyValues(model), Self.t20RetainedValues)
        XCTAssertEqual(model.accessibilityHeader, "Before the first ball. India starts as favorite")
        XCTAssertEqual(model.visibleNotes, [Self.t20Note])
        XCTAssertEqual(model.accessibilityNotes, Self.t20Note)
    }

    func testRetainedPregameBarsEndBeforeTheUpcomingReportAndLaterClocksAreNotInputs() {
        let bar = Self.iso(Self.t20BarEnd)
        let report = Self.iso(Self.t20ReportedAt)
        XCTAssertEqual(report.timeIntervalSince(bar), 17, accuracy: 0.001)
        XCTAssertLessThan(report, Self.iso(Self.t20MarketClose))
        XCTAssertLessThan(Self.iso(Self.t20MarketClose), Self.iso(Self.t20Settled))
        let model = Self.pregameStory(.before, Self.t20Retained())
        let spoken = Self.storyValues(model).compactMap { $0 }.joined(separator: " ")
        for later in ["10:40", "10:45", "17:40", "17:45", "settle", "finalized", "Won", "won"] {
            XCTAssertFalse(spoken.contains(later), later)
        }
    }

    func testPregameStorySuppressesEverySuppliedLaterReadingMovementScoreTargetResultAndGrade() {
        let model = Self.pregameStory(.before, Self.t20WithLaterFacts())
        XCTAssertTrue(model.isVisible)
        XCTAssertEqual(model.rows.compactMap { model.fill($0) }, [0.78, 0.23], "only the before reading draws")
        XCTAssertEqual(Self.storyValues(model), Self.t20RetainedValues)
        for row in model.rows {
            XCTAssertNotNil(row.comparison.observation, "a later reading is supplied")
            XCTAssertNotNil(row.movement)
            XCTAssertNotNil(row.finish?.grade)
            XCTAssertEqual(model.reading(row), row.before)
            XCTAssertFalse(model.isNotDrawn(row))
        }
        let spoken = (Self.storyValues(model).compactMap { $0 } + [model.accessibilityHeader, model.accessibilityNotes].compactMap { $0 })
            .joined(separator: " ")
        for later in ["67%", "34%", "249/5", "187/4", "250", "11 points", "West Indies won", "Won", "Lost",
                      "Recorded", "Current", "finalized", "Score report"] {
            XCTAssertFalse(spoken.contains(later), later)
        }
    }

    func testPregameStoryDuringAndCompletedHideTheWholeCardAndItsSpeech() {
        for phase in [CricketHeadlinePhase10868.during, .completed] {
            for rows in [Self.t20Retained(), Self.t20WithLaterFacts()] {
                let model = Self.pregameStory(phase, rows)
                XCTAssertFalse(model.isVisible, "\(phase)")
                XCTAssertTrue(model.visibleRows.isEmpty)
                XCTAssertTrue(model.visibleNotes.isEmpty)
                XCTAssertNil(model.accessibilityHeader)
                XCTAssertNil(model.accessibilityNotes)
                XCTAssertEqual(model.rows.count, 2, "the owner's rows are kept, only hidden")
                for row in model.rows {
                    XCTAssertNil(model.reading(row))
                    XCTAssertNil(model.fill(row))
                    XCTAssertFalse(model.isNotDrawn(row))
                    XCTAssertNil(model.accessibilityRowValue(row))
                }
            }
        }
    }

    func testPregameStoryPhaseIsExplicitAndNeverInferredFromSuppliedInputs() {
        XCTAssertTrue(Self.pregameStory(.before, Self.t20WithLaterFacts()).isVisible, "later facts never hide a before card")
        XCTAssertFalse(Self.pregameStory(.during, Self.t20Retained()).isVisible, "pregame-only rows never show a during card")
        XCTAssertFalse(Self.pregameStory(.completed, Self.t20Retained()).isVisible)
        XCTAssertTrue(Self.pregameStory(.before, []).isVisible)
        XCTAssertFalse(Self.pregameStory(.during, []).isVisible)
    }

    func testPregameStoryEachMissingOrHeldSideKeepsItsOwnWordsAndLeavesTheOtherUntouched() {
        let indiaMissing = Self.pregameStory(.before, Self.t20Retained(india: .unavailable("No pregame trade admitted")))
        XCTAssertNil(indiaMissing.fill(indiaMissing.rows[0]), "no rail, never a 0% guess")
        XCTAssertFalse(indiaMissing.isNotDrawn(indiaMissing.rows[0]))
        XCTAssertEqual(indiaMissing.fill(indiaMissing.rows[1]), 0.23)
        XCTAssertEqual(Self.storyValues(indiaMissing), [
            "\(Self.t20Label): No pregame trade admitted",
            "\(Self.t20Label): 23%, \(Self.t20Detail)",
        ])
        let westIndiesHeld = Self.pregameStory(.before, Self.t20Retained(westIndies: .withheld("Pregame held — not admitted")))
        XCTAssertEqual(westIndiesHeld.fill(westIndiesHeld.rows[0]), 0.78)
        XCTAssertNil(westIndiesHeld.fill(westIndiesHeld.rows[1]))
        XCTAssertEqual(Self.storyValues(westIndiesHeld), [
            "\(Self.t20Label): 78%, \(Self.t20Detail)",
            "\(Self.t20Label): Pregame held — not admitted",
        ])
        // A missing pregame never borrows the row's later reading.
        let borrowed = Self.pregameStory(.before, [Self.t20Row(
            Self.t20India, subject: "India", shape: .circle, tint: .blue,
            before: .unavailable("Unavailable"),
            comparison: .observed(Self.obs(0.67, "67%", "Kalshi trade close · after India 249/5"))
        )])
        XCTAssertNil(borrowed.fill(borrowed.rows[0]))
        XCTAssertEqual(Self.storyValues(borrowed), ["\(Self.t20Label): Unavailable"])
        // No qualified reading at all: the card stays, every original named.
        let none = Self.pregameStory(.before, Self.t20Retained(india: .unavailable("Unavailable"), westIndies: .withheld("Held")))
        XCTAssertTrue(none.isVisible)
        XCTAssertEqual(none.visibleRows.map(\.subject), ["India", "West Indies"])
        XCTAssertTrue(none.rows.allSatisfy { none.fill($0) == nil })
        XCTAssertEqual(Self.storyValues(none), ["\(Self.t20Label): Unavailable", "\(Self.t20Label): Held"])
    }

    func testPregameStoryRealZeroIsAnEmptyRailAndOneFillsIt() {
        let model = Self.pregameStory(.before, Self.t20Retained(
            india: .observed(Self.obs(1, "100%", Self.t20Detail)),
            westIndies: .observed(Self.obs(0, "0%", Self.t20Detail))
        ))
        XCTAssertEqual(model.fill(model.rows[0]), 1)
        XCTAssertEqual(model.fill(model.rows[1]), 0, "zero is a real place: an empty rail, not absence")
        XCTAssertFalse(model.rows.contains { model.isNotDrawn($0) })
        XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0, width: 256), 0)
        XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(1, width: 256), 256)
        XCTAssertEqual(Self.storyValues(model), [
            "\(Self.t20Label): 100%, \(Self.t20Detail)",
            "\(Self.t20Label): 0%, \(Self.t20Detail)",
        ])
    }

    func testPregameStoryMalformedGeometryKeepsTheWordsSaysNotDrawnAndIsNeverClamped() {
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01, 78] {
            let model = Self.pregameStory(.before, Self.t20Retained(india: .observed(Self.obs(bad, "78%", Self.t20Detail))))
            let india = model.rows[0]
            XCTAssertNil(model.fill(india), "\(bad)")
            XCTAssertTrue(model.isNotDrawn(india), "\(bad)")
            XCTAssertEqual(model.reading(india)?.observation?.text, "78%")
            XCTAssertEqual(
                model.accessibilityRowValue(india),
                "\(Self.t20Label): 78%, \(Self.t20Detail), \(CricketOutlookInput10868.notDrawn)"
            )
            XCTAssertNil(CricketPregameStoryGeometry10868.fillWidth(bad, width: 256), "\(bad)")
            XCTAssertEqual(model.fill(model.rows[1]), 0.23, "the other original is unaffected")
        }
    }

    func testPregameStoryRailFillIsTheReadingsOwnFractionOfTheOfferedWidthWithNoMinimum() {
        // Rail widths at 320/375/393 and a wide reader (CONSTRUCTED).
        for width: CGFloat in [256, 311, 329, 640] {
            XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0.78, width: width)!, width * 0.78, accuracy: 1e-9)
            XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0.23, width: width)!, width * 0.23, accuracy: 1e-9)
        }
        XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0.001, width: 256)!, 0.256, accuracy: 1e-9, "no 2-point floor")
        XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0.5, width: 0), 0)
        XCTAssertEqual(CricketPregameStoryGeometry10868.fillWidth(0.5, width: -10), 0)
    }

    func testPregameStoryKeepsOneOrManyOriginalsInOwnerOrderWithNoCapComplementOrDraw() {
        let one = Self.pregameStory(.before, [Self.t20Retained()[1]])
        XCTAssertEqual(one.visibleRows.map(\.subject), ["West Indies"])
        XCTAssertEqual(Self.storyValues(one), ["\(Self.t20Label): 23%, \(Self.t20Detail)"], "no complementary 77% appears")
        let reversed = Self.pregameStory(.before, Array(Self.t20Retained().reversed()))
        XCTAssertEqual(reversed.visibleRows.map(\.subject), ["West Indies", "India"], "owner order, never sorted by chance")
        XCTAssertEqual(Self.pregameStory(.before, Self.t20Retained()).visibleRows.count, 2, "no draw row is added")
        // CONSTRUCTED five rows — robustness only, not an approved route.
        let probabilities = [0.0, 0.2, 0.4, 0.6, 0.8]
        let five = probabilities.indices.map { index in
            Self.t20Row(
                "owner-row-\(index)", subject: "Original \(index)",
                shape: CricketOutlookShape10868.allCases[index % 3], tint: .gray,
                before: .observed(Self.obs(probabilities[index], "\(index * 20)%", "owner bar \(index)"))
            )
        }
        let many = Self.pregameStory(.before, five)
        XCTAssertEqual(many.visibleRows.map(\.id), five.map(\.id))
        XCTAssertEqual(many.rows.compactMap { many.fill($0) }, probabilities)
        XCTAssertEqual(Self.storyValues(many).last, "\(Self.t20Label): 80%, owner bar 4")
        // No originals: the card still says what it is.
        let empty = Self.pregameStory(.before, [])
        XCTAssertTrue(empty.isVisible)
        XCTAssertTrue(empty.visibleRows.isEmpty)
        XCTAssertEqual(empty.accessibilityHeader, "Before the first ball. India starts as favorite")
        XCTAssertEqual(empty.accessibilityNotes, Self.t20Note)
        let bare = Self.pregameStory(.before, [], title: nil, notes: [])
        XCTAssertEqual(bare.accessibilityHeader, "Before the first ball")
        XCTAssertNil(bare.accessibilityNotes)
    }

    func testPregameStoryLongSubjectLabelAndLocalCalendarProvenanceAreVerbatim() {
        let longDetail = "Kalshi trade close · minute 5:56–5:57 AM PDT, Friday, October 9, 2026 · last positive-volume trade before the pre-match report"
        let longLabel = "Pregame chance to win the second T20 international"
        let subject = "West Indies (touring side, second T20 international, Ranchi)"
        let row = Self.t20Row(Self.t20WestIndies, subject: subject, shape: .diamond, tint: .orange,
                              before: .observed(Self.obs(0.23, "23%", longDetail)))
        let model = CricketPregameStoryInput10868(
            phase: .before,
            eyebrow: "Before the first ball · Friday, October 9, 2026",
            title: "India starts as favorite in Ranchi",
            beforeLabel: longLabel,
            rows: [row],
            notes: [Self.t20Note]
        )
        XCTAssertEqual(model.visibleRows.map(\.subject), [subject])
        XCTAssertEqual(model.accessibilityRowValue(row), "\(longLabel): 23%, \(longDetail)")
        XCTAssertEqual(model.accessibilityHeader, "Before the first ball · Friday, October 9, 2026. India starts as favorite in Ranchi")
    }

    func testPregameStoryNameAndFigureShareALineOnlyWhenBothFitWholeElseStack() {
        // CONSTRUCTED ideal widths: a subject at subheadline bold and a whole
        // 26-point figure; the card's row widths at 320/375/393 and wide.
        func line(_ available: CGFloat, subject: CGFloat, figure: CGFloat, force: Bool = false) -> CricketOutlookArrangement10868 {
            CricketOutlookGeometry10868.pairArrangement(
                available: available, spacing: 12, equalColumns: false, forceStack: force,
                first: { _ in subject }, second: { _ in figure }
            )
        }
        for available: CGFloat in [256, 311, 329, 640] {
            for subject: CGFloat in [44, 88] {
                XCTAssertEqual(line(available, subject: subject, figure: 52), .sideBySide, "\(available) \(subject)")
            }
        }
        XCTAssertEqual(line(256, subject: 300, figure: 52), .stacked, "a long name stacks above its whole figure")
        XCTAssertEqual(line(640, subject: 300, figure: 52), .sideBySide)
        XCTAssertEqual(line(256, subject: 88, figure: 190), .stacked, "long absence words stack")
        XCTAssertEqual(line(640, subject: 44, figure: 52, force: true), .stacked, "accessibility sizes stack")
        XCTAssertEqual(line(256, subject: .infinity, figure: 52), .stacked)
        // Side by side, the figure keeps its whole width at the trailing edge.
        XCTAssertEqual(
            CricketOutlookGeometry10868.columns(total: 256, secondIdeal: 52, spacing: 12, equalColumns: false),
            CricketOutlookColumns10868(first: 192, second: 52)
        )
    }

    @MainActor
    func testPregameStoryInputsTakeOnlyOwnerWordsAndTheViewHasNoSelectorActionOrState() {
        let model = Self.pregameStory(.before, Self.t20Retained())
        let labels = Mirror(reflecting: model).children.compactMap { $0.label }
        XCTAssertEqual(labels, ["phase", "eyebrow", "title", "beforeLabel", "rows", "notes"])
        for label in labels {
            for forbidden in ["comparison", "movement", "finish", "grade", "outcome", "score", "runs", "wickets", "overs",
                              "target", "projection", "forecast", "probability", "price", "selected", "ticker", "date", "time", "action"] {
                XCTAssertFalse(label.lowercased().contains(forbidden), "\(label) / \(forbidden)")
            }
        }
        let viewLabels = Mirror(reflecting: CricketPregameStoryPresentation10868(input: model)).children.compactMap { $0.label }
        XCTAssertEqual(viewLabels.first, "input")
        for label in viewLabels {
            for forbidden in ["select", "details", "action", "callback", "timer", "subscription", "state", "focus"] {
                XCTAssertFalse(label.lowercased().contains(forbidden), "\(label) / \(forbidden)")
            }
        }
    }

    func testPregameStoryIdentifiersAreDistinctFromTheHeadlineAndOutlookCard() {
        let ids = [Self.t20India, Self.t20WestIndies].flatMap { id in
            [
                CricketPregameStoryAccessibilityID10868.row(id),
                CricketHeadlineAccessibilityID10868.row(id),
                CricketOutlookAccessibilityID10868.row(id),
            ]
        } + [
            CricketPregameStoryAccessibilityID10868.header,
            CricketPregameStoryAccessibilityID10868.notes,
            CricketHeadlineAccessibilityID10868.caption,
            CricketHeadlineAccessibilityID10868.state,
            CricketOutlookAccessibilityID10868.header,
            CricketOutlookAccessibilityID10868.notes,
        ]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    // MARK: Match headline — sources and timing (compact provenance)

    // The approved `T20Match.tsx` main headline renders `T20ChanceComparison`
    // without `showDates` and keeps timing one tap away in `HeadlineInfo`.
    // These cases use the same ARCHIVED packets as above (three-original
    // Test, CRICKET-HEADLINE-RETAINED-CASES.json; two-original T20,
    // T20-BEFORE-STORY-RETAINED-CASES.json) in the same CONSTRUCTED owner
    // words. CONSTRUCTED here: the flag/callback combinations, the captured
    // handback, every blank, held, long and empty case. Nothing here claims a
    // rendered fit, a tap, focus return or VoiceOver output.

    private static let provenanceCombinations: [(secondary: Bool, connected: Bool)] = [
        (false, false), (false, true), (true, false), (true, true),
    ]

    private static func presentation(offers: Bool, inline: Bool) -> CricketHeadlineProvenancePresentation10868 {
        CricketHeadlineProvenancePresentation10868(offersInfo: offers, inline: inline)
    }

    private static func sourceEntry(
        _ slot: CricketHeadlineSlot10868,
        _ label: String,
        _ text: String,
        _ detail: String?
    ) -> CricketHeadlineSourceEntry10868 {
        CricketHeadlineSourceEntry10868(slot: slot, label: label, text: text, detail: detail)
    }

    /// Every string the payload carries, for leak checks.
    private static func sourceTexts(_ info: CricketHeadlineSourceInfo10868) -> [String] {
        var texts: [String] = info.caption.map { [$0] } ?? []
        for subject in info.subjects {
            texts.append(subject.subject)
            for entry in subject.entries {
                texts += [entry.label, entry.text] + (entry.detail.map { [$0] } ?? [])
            }
        }
        switch info.state {
        case .reported(let frame)?:
            for entry in frame.entries {
                texts += (entry.label.map { [$0] } ?? []) + [entry.text, entry.spoken]
            }
            texts += frame.detail.map { [$0] } ?? []
        case .unavailable(let words)?:
            texts.append(words)
        case nil:
            break
        }
        return texts
    }

    private static func assertNoLeak(_ info: CricketHeadlineSourceInfo10868, _ hidden: [String], file: StaticString = #filePath, line: UInt = #line) {
        let texts = sourceTexts(info)
        for word in hidden {
            XCTAssertFalse(texts.contains { $0.contains(word) }, word, file: file, line: line)
        }
    }

    /// CONSTRUCTED: three originals with no admitted reading at all.
    private static func blankRows() -> [CricketOutlookRow10868] {
        [
            finalRow(sa, subject: "South Africa", shape: .circle, ref: nil,
                     before: .unavailable("Not recorded"), comparison: .withheld(withheld), movement: nil, finish: nil),
            finalRow(aus, subject: "Australia", shape: .diamond, ref: nil,
                     before: .withheld("Pregame held — not admitted"), comparison: .unavailable(unavailable), movement: nil, finish: nil),
            finalRow(tie, subject: "Draw / tie", shape: .square, ref: nil,
                     before: .unavailable("No pregame reading for this outcome"), comparison: .withheld(withheld), movement: nil, finish: nil),
        ]
    }

    func testHeadlineSourcesCompactOnlyForTheExplicitSecondaryFlagWithAConnectedHost() {
        let models = [
            Self.headline(.before, Self.completedRows(comparisonFrame: 0), state: Self.duringState(0)),
            Self.headline(.during, Self.order.map { Self.retainedRow($0, frame: 0) }, state: Self.duringState(0)),
            Self.headline(.completed, Self.completedRows(), state: Self.completedState),
            Self.headline(.before, Self.t20WithLaterFacts()),
            Self.headline(.during, Self.t20WithLaterFacts()),
            Self.headline(.completed, Self.t20WithLaterFacts()),
        ]
        for model in models {
            XCTAssertTrue(model.sourceInfo.hasProvenance)
            XCTAssertEqual(model.provenancePresentation(secondary: false, connected: false), Self.presentation(offers: false, inline: true))
            XCTAssertEqual(model.provenancePresentation(secondary: false, connected: true), Self.presentation(offers: true, inline: true),
                           "a callback alone offers the control and moves nothing")
            XCTAssertEqual(model.provenancePresentation(secondary: true, connected: false), Self.presentation(offers: false, inline: true),
                           "a flag alone moves nothing and offers no control")
            XCTAssertEqual(model.provenancePresentation(secondary: true, connected: true), Self.presentation(offers: true, inline: false))
            for combination in Self.provenanceCombinations {
                let presentation = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                XCTAssertEqual(presentation.inline, !(combination.secondary && combination.connected), "\(combination)")
            }
        }
    }

    func testHeadlineSourceInfoBeforeCarriesOnlyEachPregameReadingAndNoLaterFact() {
        for frame in Self.frames.indices {
            for state in [Self.duringState(frame), Self.completedState] {
                let model = Self.headline(.before, Self.completedRows(comparisonFrame: frame), caption: "Pregame chances", state: state)
                let info = model.sourceInfo
                XCTAssertEqual(info.phase, .before)
                XCTAssertEqual(info.caption, "Pregame chances")
                XCTAssertNil(info.state, "a supplied state stays out before play")
                XCTAssertEqual(info.subjects.map(\.id), Self.order)
                XCTAssertEqual(info.subjects.map(\.subject), ["South Africa", "Australia", "Draw / tie"])
                for subject in info.subjects {
                    XCTAssertEqual(subject.entries, [Self.sourceEntry(.pregame, "Pregame", Self.pregameText[subject.id]!, Self.pregameDetail)])
                }
                let later = Self.frames[frame].recorded.values.flatMap { [$0.text, $0.detail, $0.movement, $0.spokenMovement] }
                Self.assertNoLeak(info, later + ["Recorded", "Match", "Winner", "Won", "Lost", "No draw",
                                                 Self.reportDetail, Self.gradeDetail, Self.completedStateDetail, "154", "206", "Target"])
            }
        }
        let t20 = Self.headline(.before, Self.t20WithLaterFacts()).sourceInfo
        XCTAssertEqual(t20.subjects.map(\.subject), ["India", "West Indies"])
        XCTAssertEqual(t20.subjects.map(\.entries), [
            [Self.sourceEntry(.pregame, "Pregame", "78%", Self.t20Detail)],
            [Self.sourceEntry(.pregame, "Pregame", "23%", Self.t20Detail)],
        ])
        Self.assertNoLeak(t20, ["67%", "34%", "249/5", "187/4", "250", "11 points", "West Indies won", "Won", "Lost", "finalized"])
    }

    func testHeadlineSourceInfoDuringCarriesBothReadingsAndStateButNoOutcomeGradeOrMovement() {
        for (index, frame) in Self.frames.enumerated() {
            let model = Self.headline(.during, Self.completedRows(comparisonFrame: index), state: Self.duringState(index))
            let info = model.sourceInfo
            XCTAssertEqual(info.phase, .during)
            XCTAssertEqual(info.state, Self.duringState(index))
            XCTAssertEqual(info.subjects.map(\.id), Self.order)
            for subject in info.subjects {
                let recorded = frame.recorded[subject.id]!
                XCTAssertEqual(subject.entries, [
                    Self.sourceEntry(.pregame, "Pregame", Self.pregameText[subject.id]!, Self.pregameDetail),
                    Self.sourceEntry(.comparison, "Recorded", recorded.text, recorded.detail),
                ], frame.key)
            }
            let movements = frame.recorded.values.flatMap { [$0.movement, $0.spokenMovement] }
            Self.assertNoLeak(info, movements + ["Match", "Winner", "Won", "Lost", "No draw", "Original contract",
                                                 Self.reportDetail, Self.gradeDetail])
        }
        let lunch = Self.headline(.during, Self.order.map { Self.retainedRow($0, frame: 1) }).sourceInfo
        XCTAssertEqual(Set(lunch.subjects.compactMap { $0.entries.last?.detail }).count, 3, "three separate bar clocks, never one")

        let t20 = Self.headline(.during, Self.t20WithLaterFacts(), comparisonLabel: "Current").sourceInfo
        XCTAssertEqual(t20.subjects.map { $0.entries.map(\.text) }, [["78%", "67%"], ["23%", "34%"]])
        XCTAssertEqual(t20.subjects.map { $0.entries.map(\.label) }, [["Pregame", "Current"], ["Pregame", "Current"]])
        Self.assertNoLeak(t20, ["11 points", "West Indies won", "Won", "Lost", "finalized", "Recorded"])
    }

    func testHeadlineSourceInfoCompletedCarriesPregameAndOutcomeButNoLaterChanceOrGrade() {
        for (index, frame) in Self.frames.enumerated() {
            let model = Self.headline(.completed, Self.completedRows(comparisonFrame: index), state: Self.completedState)
            let info = model.sourceInfo
            XCTAssertEqual(info.phase, .completed)
            XCTAssertEqual(info.state, Self.completedState)
            XCTAssertEqual(info.subjects.map { $0.entries.map(\.slot) }, Array(repeating: [CricketHeadlineSlot10868.pregame, .outcome], count: 3))
            for (subject, retained) in zip(info.subjects, Self.retainedFinals) {
                XCTAssertEqual(subject.id, retained.id)
                XCTAssertEqual(subject.entries, [
                    Self.sourceEntry(.pregame, "Pregame", Self.pregameText[retained.id]!, Self.pregameDetail),
                    Self.sourceEntry(.outcome, "Match", retained.outcome, Self.reportDetail),
                ])
            }
            let later = frame.recorded.values.flatMap { [$0.text, $0.detail, $0.movement, $0.spokenMovement] }
            Self.assertNoLeak(info, later + [Self.gradeDetail, "Original contract", "Won", "Recorded", "checkmark", "xmark"])
        }
        let t20 = Self.headline(.completed, Self.t20WithLaterFacts()).sourceInfo
        XCTAssertEqual(t20.subjects.map { $0.entries.map(\.text) }, [["78%", "Lost"], ["23%", "West Indies won"]])
        Self.assertNoLeak(t20, ["67%", "34%", "11 points", "Won", "finalized", "Kalshi Yes contract"])
    }

    func testHeadlineSourceInfoKeepsAbsenceWordsVisibleAndOffersNoEmptyControl() {
        for phase in [CricketHeadlinePhase10868.before, .during, .completed] {
            let blank = Self.headline(phase, Self.blankRows())
            XCTAssertFalse(blank.sourceInfo.hasProvenance, "absence words alone leave nothing to open")
            for combination in Self.provenanceCombinations {
                XCTAssertEqual(
                    blank.provenancePresentation(secondary: combination.secondary, connected: combination.connected),
                    Self.presentation(offers: false, inline: true),
                    "no inert or empty info control: \(phase) \(combination)"
                )
            }
            XCTAssertTrue(blank.sourceInfo.subjects.allSatisfy { $0.entries.allSatisfy { $0.detail == nil } })
        }
        let during = Self.headline(.during, Self.blankRows()).sourceInfo
        XCTAssertEqual(during.subjects.map { $0.entries.map(\.text) }, [
            ["Not recorded", Self.withheld],
            ["Pregame held — not admitted", Self.unavailable],
            ["No pregame reading for this outcome", Self.withheld],
        ])
        XCTAssertEqual(
            Self.headline(.completed, Self.blankRows()).sourceInfo.subjects.compactMap { $0.entries.last },
            Array(repeating: Self.sourceEntry(.outcome, "Match", "Not reported", nil), count: 3)
        )
        // A state without provenance adds nothing to open; one with it does.
        XCTAssertFalse(Self.headline(.during, Self.blankRows(), state: .unavailable("Score unavailable")).sourceInfo.hasProvenance)
        let undated = CricketHeadlineState10868.reported(CricketHeadlineStateFrame10868(
            entries: [CricketHeadlineStateEntry10868(label: "South Africa · batting", text: "154/4", spoken: "154 for 4")],
            detail: nil
        ))
        XCTAssertFalse(Self.headline(.during, Self.blankRows(), state: undated).sourceInfo.hasProvenance)
        let reported = Self.headline(.during, Self.blankRows(), state: Self.duringState(0))
        XCTAssertTrue(reported.sourceInfo.hasProvenance)
        XCTAssertEqual(reported.provenancePresentation(secondary: true, connected: true), Self.presentation(offers: true, inline: false))
        XCTAssertNil(Self.headline(.before, Self.blankRows(), state: Self.duringState(0)).sourceInfo.state)
        XCTAssertFalse(Self.headline(.before, Self.blankRows(), state: Self.duringState(0)).sourceInfo.hasProvenance,
                       "a state hidden before play cannot offer the control")

        // Mixed: a held reading keeps its own words beside an observed one.
        let ausDetail = Self.frames[0].recorded[Self.aus]!.detail
        let mixed = Self.headline(.during, [
            Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                          before: .observed(Self.obs(0.48, "48%", Self.pregameDetail)),
                          comparison: .withheld(Self.withheld), movement: nil, finish: nil),
            Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                          before: .unavailable(Self.unavailable),
                          comparison: .observed(Self.obs(0.64, "64%", ausDetail)), movement: nil, finish: nil),
        ])
        XCTAssertEqual(mixed.sourceInfo.subjects.map(\.entries), [
            [Self.sourceEntry(.pregame, "Pregame", "48%", Self.pregameDetail), Self.sourceEntry(.comparison, "Recorded", Self.withheld, nil)],
            [Self.sourceEntry(.pregame, "Pregame", Self.unavailable, nil), Self.sourceEntry(.comparison, "Recorded", "64%", ausDetail)],
        ])
        XCTAssertEqual(mixed.provenancePresentation(secondary: true, connected: true), Self.presentation(offers: true, inline: false))
        XCTAssertEqual(Self.headlineValues(mixed), [
            "Pregame: 48%, \(Self.pregameDetail). Recorded: \(Self.withheld)",
            "Pregame: \(Self.unavailable). Recorded: 64%, \(ausDetail)",
        ], "the held and unavailable reasons are still said in full")
    }

    func testHeadlineSpokenRowsAndStateKeepEveryProvenanceInEveryCombination() {
        let models = [
            Self.headline(.before, Self.completedRows(comparisonFrame: 2), state: Self.completedState),
            Self.headline(.during, Self.completedRows(comparisonFrame: 2), state: Self.duringState(2)),
            Self.headline(.completed, Self.completedRows(comparisonFrame: 2), state: Self.completedState),
            Self.headline(.during, Self.t20WithLaterFacts()),
        ]
        for model in models {
            let spoken = Self.headlineValues(model)
            let state = model.accessibilityState
            for combination in Self.provenanceCombinations {
                _ = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                XCTAssertEqual(Self.headlineValues(model), spoken, "speech takes no presentation input")
                XCTAssertEqual(model.accessibilityState, state)
            }
            for (subject, value) in zip(model.sourceInfo.subjects, spoken) {
                for entry in subject.entries {
                    XCTAssertTrue(value.contains("\(entry.label): \(entry.text)"), entry.label)
                    if let detail = entry.detail { XCTAssertTrue(value.contains(detail), detail) }
                }
            }
            if case .reported(let frame)? = model.visibleState, let detail = frame.detail {
                let compact = model.provenancePresentation(secondary: true, connected: true)
                XCTAssertNil(model.inlineStateDetail(compact), "moved off screen")
                XCTAssertTrue(state?.contains(detail) ?? false, "still spoken")
            }
        }
        XCTAssertEqual(
            Self.headlineValues(models[1])[1],
            "Pregame: 47%, \(Self.pregameDetail). Recorded: 79%, \(Self.frames[2].recorded[Self.aus]!.detail)"
        )
    }

    func testHeadlineStateProvenanceMovesOnlyBeneathReportedEntries() {
        let rows = Self.order.map { Self.retainedRow($0, frame: 0) }
        let model = Self.headline(.during, rows, state: Self.duringState(0))
        let reportDetail = Self.headlineReports[0].detail
        for combination in Self.provenanceCombinations {
            let presentation = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
            XCTAssertEqual(model.inlineStateDetail(presentation), combination.secondary && combination.connected ? nil : reportDetail,
                           "\(combination)")
        }
        let compact = Self.presentation(offers: true, inline: false)
        let inline = Self.presentation(offers: true, inline: true)
        // Entries stay; with no entry the line qualifies nothing and stays.
        let detailOnly = CricketHeadlineState10868.reported(CricketHeadlineStateFrame10868(entries: [], detail: "Score report delayed"))
        XCTAssertEqual(Self.headline(.during, rows, state: detailOnly).inlineStateDetail(compact), "Score report delayed")
        XCTAssertNil(Self.headline(.during, rows, state: .unavailable("Score unavailable")).inlineStateDetail(inline))
        XCTAssertNil(Self.headline(.during, rows).inlineStateDetail(inline))
        XCTAssertNil(Self.headline(.before, rows, state: Self.duringState(0)).inlineStateDetail(inline), "no state before play")
        XCTAssertEqual(Self.headline(.completed, Self.completedRows(), state: Self.completedState).inlineStateDetail(inline),
                       Self.completedStateDetail)
        XCTAssertNil(Self.headline(.completed, Self.completedRows(), state: Self.completedState).inlineStateDetail(compact))
    }

    func testHeadlineTopRowPlacesTheOneControlBesideTheCaptionOrAloneAndNeverTouchesTheCells() {
        let rows = Self.order.map { Self.retainedRow($0, frame: 3) }
        let caption = "Recorded win chances · Day 5"
        let captioned = Self.headline(.during, rows, caption: caption, state: Self.duringState(3))
        let bare = Self.headline(.during, rows, state: Self.duringState(3))
        for combination in Self.provenanceCombinations {
            let withCaption = captioned.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
            let withoutCaption = bare.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
            XCTAssertEqual(captioned.topRow(withCaption), combination.connected ? .captionAndInfo : .caption)
            XCTAssertEqual(bare.topRow(withoutCaption), combination.connected ? .info : CricketHeadlineTopRow10868.none)
        }
        XCTAssertEqual(captioned.sourceInfo.caption, caption, "verbatim")
        XCTAssertNil(bare.sourceInfo.caption)
        // The flags never change a cell, a slot or the measured arrangement inputs.
        for model in [captioned, bare] {
            XCTAssertEqual(model.cells.count, 9)
            XCTAssertEqual(model.cellsPerRow, 3)
        }
        // Accessibility sizes keep stacking named blocks; the top row takes no type-size input.
        XCTAssertEqual(
            CricketHeadlineGeometry10868.arrangement(
                available: 640, spacing: 12, blocks: 3, cellsPerBlock: 3, forceStack: true,
                measure: Self.cellWidths(Self.blocks(3, [Self.subjectCell, Self.figureCell, Self.figureCell]))
            ),
            .blocks(readingsSideBySide: false)
        )
        // Empty: no rows and no state leave nothing to open; a state alone may.
        let empty = Self.headline(.during, [])
        XCTAssertTrue(empty.sourceInfo.subjects.isEmpty)
        XCTAssertEqual(empty.topRow(empty.provenancePresentation(secondary: true, connected: true)), CricketHeadlineTopRow10868.none)
        let stateOnly = Self.headline(.during, [], caption: caption, state: Self.duringState(0))
        XCTAssertEqual(stateOnly.topRow(stateOnly.provenancePresentation(secondary: true, connected: true)), .captionAndInfo)
        XCTAssertEqual(CricketHeadlineInput10868.sourceInfoLabel, "Sources and timing")
        XCTAssertEqual(CricketHeadlineInput10868.sourceInfoSymbol, "info.circle")
        XCTAssertGreaterThanOrEqual(CricketHeadlineInput10868.sourceInfoTarget, 44)
    }

    func testHeadlineSourceInfoKeepsLongSubjectsCaptionsAndProvenanceVerbatim() {
        let pregameLong = "Kalshi trade close · hour 4–5 PM PDT, Thursday, October 8, 2026"
        let currentLong = "Kalshi trade close · minute 4:10–4:11 AM PDT, Tuesday, October 13, 2026 · owner-admitted as current"
        let row = Self.finalRow(Self.tie, subject: "Match drawn or tied after five full days in Durban", shape: .square, ref: nil,
                                before: .observed(Self.obs(0.004, "<1%", pregameLong)),
                                comparison: .observed(Self.obs(0.996, "≥99.5%", currentLong)),
                                movement: nil, finish: nil)
        let caption = "Each chance keeps its own trade minute · Day 5 · 85-over report"
        let model = Self.headline(.during, [row], caption: caption, comparisonLabel: "Current")
        XCTAssertEqual(model.sourceInfo, CricketHeadlineSourceInfo10868(
            phase: .during,
            caption: caption,
            subjects: [CricketHeadlineSourceSubject10868(
                id: Self.tie,
                subject: "Match drawn or tied after five full days in Durban",
                entries: [
                    Self.sourceEntry(.pregame, "Pregame", "<1%", pregameLong),
                    Self.sourceEntry(.comparison, "Current", "≥99.5%", currentLong),
                ]
            )],
            state: nil
        ))
    }

    @MainActor
    func testHeadlineViewHandsTheHostTheExactPhaseSafeSourceInfoOnlyWhenTheControlIsOffered() {
        var received: [CricketHeadlineSourceInfo10868] = []
        for phase in [CricketHeadlinePhase10868.before, .during, .completed] {
            let model = Self.headline(phase, Self.completedRows(comparisonFrame: 1), state: Self.duringState(1))
            for secondary in [false, true] {
                received = []
                let view = CricketHeadlinePresentation10868(input: model, secondaryProvenance: secondary, onSourceInfo: { received.append($0) })
                view.openSourceInfo()
                XCTAssertEqual(received, [model.sourceInfo], "\(phase) \(secondary)")
                XCTAssertNotEqual(received.first?.subjects.map(\.entries), model.rows.map { _ in [CricketHeadlineSourceEntry10868]() })
            }
        }
        // No callback: nothing to hand back, whatever the flag says.
        let model = Self.headline(.during, Self.completedRows(), state: Self.duringState(3))
        CricketHeadlinePresentation10868(input: model, secondaryProvenance: true).openSourceInfo()
        // A connected host with nothing to disclose gets no handback.
        received = []
        CricketHeadlinePresentation10868(input: Self.headline(.during, Self.blankRows()), secondaryProvenance: true,
                                         onSourceInfo: { received.append($0) }).openSourceInfo()
        XCTAssertTrue(received.isEmpty, "no inert or empty info action")

        let plain = CricketHeadlinePresentation10868(input: model)
        XCTAssertFalse(plain.secondaryProvenance, "secondary provenance defaults off")
        XCTAssertNil(plain.onSourceInfo, "the disclosure defaults to none")
        let labels = Mirror(reflecting: plain).children.compactMap { $0.label }
        XCTAssertEqual(Array(labels.prefix(3)), ["input", "secondaryProvenance", "onSourceInfo"])
        for label in labels {
            for forbidden in ["sheet", "router", "timer", "subscription", "isPresented", "selected", "focus", "snapshot"] {
                XCTAssertFalse(label.lowercased().contains(forbidden.lowercased()), "\(label) / \(forbidden)")
            }
        }
    }

    @MainActor
    func testOutlookAndStoryViewsGainNoSourcesControlOrSecondaryFlag() {
        let outlook = Mirror(reflecting: CricketOutlookPresentation10868(input: Self.retained(frame: 0))).children.compactMap { $0.label }
        let story = Mirror(reflecting: CricketPregameStoryPresentation10868(input: Self.pregameStory(.before, Self.t20Retained())))
            .children.compactMap { $0.label }
        XCTAssertEqual(Array(outlook.prefix(3)), ["input", "onSelect", "onDetails"])
        XCTAssertEqual(story.first, "input")
        for label in outlook + story {
            XCTAssertFalse(label.lowercased().contains("source"), label)
            XCTAssertFalse(label.lowercased().contains("secondary"), label)
        }
    }

    func testHeadlineSourcesIdentifierIsDistinct() {
        let ids = Self.order.map { CricketHeadlineAccessibilityID10868.row($0) }
            + [
                CricketHeadlineAccessibilityID10868.caption,
                CricketHeadlineAccessibilityID10868.state,
                CricketHeadlineAccessibilityID10868.sourceInfo,
                CricketOutlookAccessibilityID10868.header,
                CricketPregameStoryAccessibilityID10868.header,
            ]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    // MARK: Match headline — blank provenance offers nothing to open

    // The same ARCHIVED figures in the same CONSTRUCTED owner words as above —
    // 78/23 with its 67/34 current pair and outcome words for the two-original
    // T20, the pregame and lunch-frame figures and outcome words for the
    // three-original Test. CONSTRUCTED here: provenance strings that are
    // empty, spaces, a newline or mixed whitespace, beside or instead of the
    // real ones. Every string passes through unchanged; only whether the info
    // control is offered depends on them. Nothing here claims a rendered fit,
    // a tap or VoiceOver output.

    private static let blankDetails = ["", " ", "\n", " \n\t "]
    private static let blankStateDetails: [String?] = [nil, "", " ", "\n", " \n\t "]
    private static let headlinePhases: [CricketHeadlinePhase10868] = [.before, .during, .completed]

    private static func everyOriginal(_ detail: String, _ count: Int) -> [String] {
        Array(repeating: detail, count: count)
    }

    /// CONSTRUCTED: the two T20 originals, each slot carrying the given
    /// provenance verbatim (owner order). The grade keeps real words: the
    /// headline never shows it.
    private static func t20Provenance(_ pregame: [String], _ current: [String], _ outcome: [String]) -> [CricketOutlookRow10868] {
        [
            t20Row(t20India, subject: "India", shape: .circle, tint: .blue,
                   before: .observed(obs(0.78, "78%", pregame[0])),
                   comparison: .observed(obs(0.67, "67%", current[0])),
                   finish: CricketOutlookFinish10868(
                       outcome: .admitted(word("Lost", outcome[0])),
                       grade: .admitted(word("Lost", symbol: "xmark.circle", "Kalshi Yes contract · finalized"))
                   )),
            t20Row(t20WestIndies, subject: "West Indies", shape: .diamond, tint: .orange,
                   before: .observed(obs(0.23, "23%", pregame[1])),
                   comparison: .observed(obs(0.34, "34%", current[1])),
                   finish: CricketOutlookFinish10868(
                       outcome: .admitted(word("West Indies won", outcome[1])),
                       grade: .admitted(word("Won", symbol: "checkmark.circle", "Kalshi Yes contract · finalized"))
                   )),
        ]
    }

    /// CONSTRUCTED: the three Test originals' pregame and lunch-frame figures
    /// and outcome words, each slot carrying the given provenance verbatim.
    private static func testProvenance(_ pregame: [String], _ recorded: [String], _ outcome: [String]) -> [CricketOutlookRow10868] {
        retainedFinals.enumerated().map { index, retained in
            let lunch = frames[1].recorded[retained.id]!
            return finalRow(retained.id, subject: subjects[retained.id]!, shape: shapes[retained.id]!, ref: nil,
                            before: .observed(obs(pregameProbability[retained.id]!, pregameText[retained.id]!, pregame[index])),
                            comparison: .observed(obs(lunch.probability, lunch.text, recorded[index])),
                            movement: nil,
                            finish: CricketOutlookFinish10868(
                                outcome: .admitted(word(retained.outcome, outcome[index])),
                                grade: .admitted(word(retained.grade, symbol: retained.gradeSymbol, gradeDetail))
                            ))
        }
    }

    private static func provenanceRows(_ count: Int, _ pregame: [String], _ comparison: [String], _ outcome: [String]) -> [CricketOutlookRow10868] {
        count == 2 ? t20Provenance(pregame, comparison, outcome) : testProvenance(pregame, comparison, outcome)
    }

    /// The real provenance the same fixtures carry above.
    private static func realProvenance(_ count: Int) -> (pregame: [String], comparison: [String], outcome: [String]) {
        if count == 2 {
            return ([t20Detail, t20Detail],
                    ["Kalshi trade close · after India 249/5", "Kalshi trade close · West Indies 187/4 chasing target 250"],
                    ["Score report · West Indies won chasing target 250", "Score report · 187/4 after India 249/5"])
        }
        return (everyOriginal(pregameDetail, 3), order.map { frames[1].recorded[$0]!.detail }, everyOriginal(reportDetail, 3))
    }

    /// Each original's visible figures or outcome words in the phase.
    private static func visibleTexts(_ count: Int, _ phase: CricketHeadlinePhase10868) -> [[String]] {
        let pregame = count == 2 ? ["78%", "23%"] : order.map { pregameText[$0]! }
        let later: [String]
        switch phase {
        case .before: return pregame.map { [$0] }
        case .during: later = count == 2 ? ["67%", "34%"] : order.map { frames[1].recorded[$0]!.text }
        case .completed: later = count == 2 ? ["Lost", "West Indies won"] : retainedFinals.map(\.outcome)
        }
        return zip(pregame, later).map { [$0, $1] }
    }

    private static func expectedSubjects(
        _ count: Int,
        _ phase: CricketHeadlinePhase10868,
        _ pregame: [String],
        _ comparison: [String],
        _ outcome: [String]
    ) -> [CricketHeadlineSourceSubject10868] {
        let ids = count == 2 ? [t20India, t20WestIndies] : order
        let names = count == 2 ? ["India", "West Indies"] : order.map { subjects[$0]! }
        let texts = visibleTexts(count, phase)
        return ids.indices.map { index in
            var entries = [sourceEntry(.pregame, "Pregame", texts[index][0], pregame[index])]
            switch phase {
            case .before: break
            case .during: entries.append(sourceEntry(.comparison, "Recorded", texts[index][1], comparison[index]))
            case .completed: entries.append(sourceEntry(.outcome, "Match", texts[index][1], outcome[index]))
            }
            return CricketHeadlineSourceSubject10868(id: ids[index], subject: names[index], entries: entries)
        }
    }

    /// The phase's CONSTRUCTED state entries with the given provenance.
    private static func phaseState(_ phase: CricketHeadlinePhase10868, detail: String?) -> CricketHeadlineState10868 {
        guard case .reported(let frame) = phase == .completed ? completedState : duringState(1) else {
            preconditionFailure("constructed states are reported")
        }
        return .reported(CricketHeadlineStateFrame10868(entries: frame.entries, detail: detail))
    }

    func testHeadlineBlankVisibleProvenanceOffersNoControlForTwoOrThreeOriginalsInAnyPhaseOrCombination() {
        for count in [2, 3] {
            for blank in Self.blankDetails {
                let none = Self.everyOriginal(blank, count)
                let rows = Self.provenanceRows(count, none, none, none)
                for phase in Self.headlinePhases {
                    for stateDetail in Self.blankStateDetails {
                        let state = Self.phaseState(phase, detail: stateDetail)
                        for caption in [nil, "Win chances"] as [String?] {
                            let model = Self.headline(phase, rows, caption: caption, state: state)
                            let info = model.sourceInfo
                            let context = "\(count) \(phase) \(blank.debugDescription) \(String(describing: stateDetail)) \(String(describing: caption))"
                            XCTAssertFalse(info.hasProvenance, context)
                            for combination in Self.provenanceCombinations {
                                let presentation = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                                XCTAssertEqual(presentation, Self.presentation(offers: false, inline: true), "\(context) \(combination)")
                                XCTAssertEqual(model.topRow(presentation), caption == nil ? CricketHeadlineTopRow10868.none : .caption, context)
                                XCTAssertEqual(model.inlineStateDetail(presentation), phase == .before ? nil : stateDetail,
                                               "the state line stays where it was, unchanged: \(context)")
                            }
                            // Every figure, outcome word and blank string is carried exactly as supplied.
                            XCTAssertEqual(info.subjects.map { $0.entries.map(\.text) }, Self.visibleTexts(count, phase), context)
                            XCTAssertEqual(info.subjects, Self.expectedSubjects(count, phase, none, none, none), context)
                            XCTAssertEqual(info.state, phase == .before ? nil : state, context)
                            XCTAssertEqual(info.caption, caption, "a caption alone is not provenance")
                        }
                    }
                }
            }
        }
    }

    func testHeadlineBlankProvenanceKeepsEveryFigureOutcomeAbsenceWordAndSpokenLineVerbatim() {
        for blank in Self.blankDetails {
            let t20 = Self.provenanceRows(2, Self.everyOriginal(blank, 2), Self.everyOriginal(blank, 2), Self.everyOriginal(blank, 2))
            let test = Self.provenanceRows(3, Self.everyOriginal(blank, 3), Self.everyOriginal(blank, 3), Self.everyOriginal(blank, 3))
            let liveState = Self.phaseState(.during, detail: blank)
            let finalState = Self.phaseState(.completed, detail: blank)
            let cases: [(CricketHeadlineInput10868, [String])] = [
                (Self.headline(.before, t20), ["Pregame: 78%, \(blank)", "Pregame: 23%, \(blank)"]),
                (Self.headline(.during, t20, comparisonLabel: "Current"), [
                    "Pregame: 78%, \(blank). Current: 67%, \(blank)",
                    "Pregame: 23%, \(blank). Current: 34%, \(blank)",
                ]),
                (Self.headline(.completed, t20), [
                    "Pregame: 78%, \(blank). Match: Lost, \(blank)",
                    "Pregame: 23%, \(blank). Match: West Indies won, \(blank)",
                ]),
                (Self.headline(.before, test, state: liveState), [
                    "Pregame: 48%, \(blank)", "Pregame: 47%, \(blank)", "Pregame: 9%, \(blank)",
                ]),
                (Self.headline(.during, test, state: liveState), [
                    "Pregame: 48%, \(blank). Recorded: 1%, \(blank)",
                    "Pregame: 47%, \(blank). Recorded: 87%, \(blank)",
                    "Pregame: 9%, \(blank). Recorded: 17%, \(blank)",
                ]),
                (Self.headline(.completed, test, state: finalState), [
                    "Pregame: 48%, \(blank). Match: Lost, \(blank)",
                    "Pregame: 47%, \(blank). Match: Winner, \(blank)",
                    "Pregame: 9%, \(blank). Match: No draw / tie, \(blank)",
                ]),
            ]
            for (model, expected) in cases {
                let state = model.accessibilityState
                for combination in Self.provenanceCombinations {
                    _ = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                    XCTAssertEqual(Self.headlineValues(model), expected, "\(model.phase) \(blank.debugDescription)")
                    XCTAssertEqual(model.accessibilityState, state)
                }
            }
            XCTAssertEqual(Self.headline(.during, test, state: liveState).accessibilityState,
                           "South Africa · batting: 166 for 6. Lunch · 73 overs: Target 421 runs to win, not a projected score. \(blank)")
            XCTAssertEqual(Self.headline(.completed, test, state: finalState).accessibilityState,
                           "South Africa: 206 all out. Australia won by 214 runs. \(blank)")

            // Absence words beside blank provenance: still shown and said, still nothing to open.
            let held = Self.headline(.during, [
                Self.finalRow(Self.sa, subject: "South Africa", shape: .circle, ref: nil,
                              before: .observed(Self.obs(0.48, "48%", blank)),
                              comparison: .withheld(Self.withheld), movement: nil, finish: nil),
                Self.finalRow(Self.aus, subject: "Australia", shape: .diamond, ref: nil,
                              before: .unavailable(Self.unavailable),
                              comparison: .observed(Self.obs(0.87, "87%", blank)), movement: nil, finish: nil),
            ], state: liveState)
            XCTAssertFalse(held.sourceInfo.hasProvenance)
            XCTAssertEqual(held.sourceInfo.subjects.map(\.entries), [
                [Self.sourceEntry(.pregame, "Pregame", "48%", blank), Self.sourceEntry(.comparison, "Recorded", Self.withheld, nil)],
                [Self.sourceEntry(.pregame, "Pregame", Self.unavailable, nil), Self.sourceEntry(.comparison, "Recorded", "87%", blank)],
            ])
            XCTAssertEqual(Self.headlineValues(held), [
                "Pregame: 48%, \(blank). Recorded: \(Self.withheld)",
                "Pregame: \(Self.unavailable). Recorded: 87%, \(blank)",
            ])
            for combination in Self.provenanceCombinations {
                XCTAssertEqual(held.provenancePresentation(secondary: combination.secondary, connected: combination.connected),
                               Self.presentation(offers: false, inline: true))
            }
        }
    }

    func testHeadlineProvenanceHiddenByThePhaseNeverOffersTheCurrentPhasesControl() {
        for count in [2, 3] {
            let real = Self.realProvenance(count)
            for blank in Self.blankDetails {
                let none = Self.everyOriginal(blank, count)
                // Before play: every later slot and the supplied state carry real provenance.
                let before = Self.headline(.before, Self.provenanceRows(count, none, real.comparison, real.outcome), state: Self.duringState(1))
                // During play: the outcome and grade carry real provenance.
                let during = Self.headline(.during, Self.provenanceRows(count, none, none, real.outcome),
                                           state: Self.phaseState(.during, detail: blank))
                // Completed: the superseded current readings carry real provenance.
                let completed = Self.headline(.completed, Self.provenanceRows(count, none, real.comparison, none),
                                              state: Self.phaseState(.completed, detail: blank))
                let hidden: [(CricketHeadlineInput10868, [String])] = [
                    (before, real.comparison + real.outcome + [Self.headlineReports[1].detail, "Kalshi Yes contract"]),
                    (during, real.outcome + ["Kalshi Yes contract"]),
                    (completed, real.comparison + ["Kalshi Yes contract"]),
                ]
                for (model, words) in hidden {
                    let context = "\(count) \(model.phase) \(blank.debugDescription)"
                    XCTAssertFalse(model.sourceInfo.hasProvenance, context)
                    for combination in Self.provenanceCombinations {
                        XCTAssertEqual(model.provenancePresentation(secondary: combination.secondary, connected: combination.connected),
                                       Self.presentation(offers: false, inline: true), "\(context) \(combination)")
                    }
                    Self.assertNoLeak(model.sourceInfo, words)
                    XCTAssertEqual(model.sourceInfo.subjects, Self.expectedSubjects(count, model.phase, none, none, none), context)
                }
                // The same rows offer the control in the phase that shows that provenance.
                XCTAssertTrue(Self.headline(.during, before.rows).sourceInfo.hasProvenance)
                XCTAssertTrue(Self.headline(.during, Self.provenanceRows(count, none, none, none), state: Self.duringState(1)).sourceInfo.hasProvenance)
                XCTAssertTrue(Self.headline(.completed, during.rows).sourceInfo.hasProvenance)
                XCTAssertTrue(Self.headline(.during, completed.rows).sourceInfo.hasProvenance)
            }
        }
    }

    func testHeadlineOneRealVisibleDetailAmongBlankNeighboursOffersTheSameCompletePayload() {
        let caption = "Win chances"
        for count in [2, 3] {
            let real = Self.realProvenance(count)
            for blank in Self.blankDetails {
                let none = Self.everyOriginal(blank, count)
                var firstPregame = none
                firstPregame[0] = real.pregame[0]
                var lastComparison = none
                lastComparison[count - 1] = real.comparison[count - 1]
                var lastOutcome = none
                lastOutcome[count - 1] = real.outcome[count - 1]
                let cases: [(CricketHeadlinePhase10868, [String], [String], [String], CricketHeadlineState10868?)] = [
                    (.before, firstPregame, none, none, nil),
                    (.during, none, lastComparison, none, Self.phaseState(.during, detail: blank)),
                    (.completed, none, none, lastOutcome, Self.phaseState(.completed, detail: nil)),
                    // Only the state's own provenance is real.
                    (.completed, none, none, none, Self.completedState),
                ]
                for (phase, pregame, comparison, outcome, state) in cases {
                    for withCaption in [false, true] {
                        let model = Self.headline(phase, Self.provenanceRows(count, pregame, comparison, outcome),
                                                  caption: withCaption ? caption : nil, state: state)
                        let info = model.sourceInfo
                        let context = "\(count) \(phase) \(blank.debugDescription) \(withCaption)"
                        XCTAssertTrue(info.hasProvenance, context)
                        XCTAssertEqual(info, CricketHeadlineSourceInfo10868(
                            phase: phase,
                            caption: withCaption ? caption : nil,
                            subjects: Self.expectedSubjects(count, phase, pregame, comparison, outcome),
                            state: state
                        ), "the complete payload, blank neighbours unchanged: \(context)")
                        XCTAssertEqual(model.provenancePresentation(secondary: false, connected: false), Self.presentation(offers: false, inline: true))
                        XCTAssertEqual(model.provenancePresentation(secondary: false, connected: true), Self.presentation(offers: true, inline: true))
                        XCTAssertEqual(model.provenancePresentation(secondary: true, connected: false), Self.presentation(offers: false, inline: true))
                        XCTAssertEqual(model.provenancePresentation(secondary: true, connected: true), Self.presentation(offers: true, inline: false))
                        for combination in Self.provenanceCombinations {
                            let presentation = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                            let expectedTop: CricketHeadlineTopRow10868 = switch (withCaption, combination.connected) {
                            case (true, true): .captionAndInfo
                            case (true, false): .caption
                            case (false, true): .info
                            case (false, false): CricketHeadlineTopRow10868.none
                            }
                            XCTAssertEqual(model.topRow(presentation), expectedTop, context)
                        }
                    }
                }
                // A real state detail beside blank rows leaves the headline only beneath its entries.
                let stateOnlyReal = Self.headline(.completed, Self.provenanceRows(count, none, none, none), state: Self.completedState)
                XCTAssertNil(stateOnlyReal.inlineStateDetail(stateOnlyReal.provenancePresentation(secondary: true, connected: true)))
                XCTAssertEqual(stateOnlyReal.inlineStateDetail(stateOnlyReal.provenancePresentation(secondary: false, connected: true)),
                               Self.completedStateDetail)
            }
        }
        // One non-whitespace character is provenance; the string is kept as supplied.
        let dot = Self.headline(.during, [], state: .reported(CricketHeadlineStateFrame10868(entries: [], detail: "\n·\n")))
        XCTAssertTrue(dot.sourceInfo.hasProvenance)
        XCTAssertEqual(dot.sourceInfo.state, .reported(CricketHeadlineStateFrame10868(entries: [], detail: "\n·\n")))
    }

    func testHeadlineStateOnlyWithBlankProvenanceOffersNothingWithOrWithoutACaption() {
        for blank in Self.blankDetails {
            for phase in [CricketHeadlinePhase10868.during, .completed] {
                let withEntries = Self.phaseState(phase, detail: blank)
                let detailOnly = CricketHeadlineState10868.reported(CricketHeadlineStateFrame10868(entries: [], detail: blank))
                for state in [withEntries, detailOnly] {
                    for caption in [nil, "Win chances"] as [String?] {
                        let model = Self.headline(phase, [], caption: caption, state: state)
                        let context = "\(phase) \(blank.debugDescription) \(String(describing: caption))"
                        XCTAssertFalse(model.sourceInfo.hasProvenance, context)
                        XCTAssertEqual(model.sourceInfo.state, state, context)
                        for combination in Self.provenanceCombinations {
                            let presentation = model.provenancePresentation(secondary: combination.secondary, connected: combination.connected)
                            XCTAssertEqual(presentation, Self.presentation(offers: false, inline: true), "\(context) \(combination)")
                            XCTAssertEqual(model.topRow(presentation), caption == nil ? CricketHeadlineTopRow10868.none : .caption, context)
                            XCTAssertEqual(model.inlineStateDetail(presentation), blank, "kept on screen, unchanged: \(context)")
                        }
                    }
                }
            }
            // Before play the state is hidden, so even its real provenance offers nothing.
            let before = Self.headline(.before, [], caption: "Win chances", state: Self.duringState(1))
            XCTAssertFalse(before.sourceInfo.hasProvenance)
            XCTAssertEqual(before.topRow(before.provenancePresentation(secondary: true, connected: true)), .caption)
        }
    }

    @MainActor
    func testHeadlineViewHandsBackNothingForBlankOrHiddenProvenanceAndTheExactPayloadForOneRealDetail() {
        var received: [CricketHeadlineSourceInfo10868] = []
        for count in [2, 3] {
            let real = Self.realProvenance(count)
            for blank in Self.blankDetails {
                let none = Self.everyOriginal(blank, count)
                let nothingToOpen = [
                    Self.headline(.before, Self.provenanceRows(count, none, none, none), caption: "Win chances"),
                    Self.headline(.during, Self.provenanceRows(count, none, none, none), state: Self.phaseState(.during, detail: blank)),
                    Self.headline(.completed, Self.provenanceRows(count, none, none, none), state: Self.phaseState(.completed, detail: blank)),
                    Self.headline(.before, Self.provenanceRows(count, none, real.comparison, real.outcome), state: Self.duringState(1)),
                    Self.headline(.during, Self.provenanceRows(count, none, none, real.outcome), state: Self.phaseState(.during, detail: blank)),
                    Self.headline(.completed, Self.provenanceRows(count, none, real.comparison, none)),
                    Self.headline(.during, [], caption: "Win chances", state: Self.phaseState(.during, detail: blank)),
                ]
                for model in nothingToOpen {
                    for secondary in [false, true] {
                        received = []
                        CricketHeadlinePresentation10868(input: model, secondaryProvenance: secondary,
                                                         onSourceInfo: { received.append($0) }).openSourceInfo()
                        XCTAssertTrue(received.isEmpty, "no empty info action: \(count) \(model.phase) \(blank.debugDescription) \(secondary)")
                    }
                }
                var lastComparison = none
                lastComparison[count - 1] = real.comparison[count - 1]
                let mixed = Self.headline(.during, Self.provenanceRows(count, none, lastComparison, real.outcome),
                                          state: Self.phaseState(.during, detail: blank))
                for secondary in [false, true] {
                    received = []
                    CricketHeadlinePresentation10868(input: mixed, secondaryProvenance: secondary,
                                                     onSourceInfo: { received.append($0) }).openSourceInfo()
                    XCTAssertEqual(received, [mixed.sourceInfo], "\(count) \(blank.debugDescription) \(secondary)")
                    XCTAssertEqual(received.first?.subjects, Self.expectedSubjects(count, .during, none, lastComparison, real.outcome))
                    XCTAssertEqual(received.first?.subjects.first?.entries.first?.detail, blank, "blank neighbours stay in the payload unchanged")
                }
            }
        }
    }
}
