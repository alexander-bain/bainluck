import XCTest
@testable import Bain_Luck

/// #7285 — the chart's participant table stops SPEAKING a null 24-hour change as
/// "unchanged over 24 hours".
///
/// THE SPECIMEN, found by the native N3 consumer check for #4079 and photographed
/// in `artifacts/native-255/danube-s1100.png`: market 58776433, whose participant
/// table serves a null `probability_change_24h` on three of its five rows
/// (`/futures/58321581` serves one on twenty-two of twenty-four). Every one of them
/// drew a dash — honest — while `EvolutionLeaderboardRow`'s `accessibilityLabel`
/// said the market had not moved.
///
/// The cause was one coalesce per field:
///
///     private var changePct: Double { (outcome.probabilityChange24h ?? 0) * 100 }
///
/// `changeLabel(0)` is `"-"`, so the screen was fine and nothing looked wrong for
/// as long as anyone looked. `spokenChange(0)` is `"unchanged over 24 hours"`, and
/// that is a claim about the market rather than about our knowledge of it. The
/// sighted reader is told nothing; the VoiceOver reader is told something false.
///
/// The rule was not new — `formatProbabilityOrDash` already carries it in prose
/// ("a probability we do not have is not a probability of zero", and the backend
/// serialises "no price" and "priced at exactly zero" identically as `null`). This
/// table was the reader that never got it, on both of its numbers.
///
/// These tests pin the fix AND the three things that must NOT move with it: the
/// drawn delta column, a MEASURED zero on either field (#5899), and the widths.
final class ANullChangeIsNotSpokenAsUnchanged7285Tests: XCTestCase {

    // MARK: - The specimen, decoded the way the app decodes it

    /// Three null changes and one null price, through `JSONDecoder` and
    /// `TolerantNumeric` — not hand-built values. A test that assigns `nil`
    /// directly would still pass if the wire's `null` stopped surviving decode,
    /// which is half of what is being claimed here.
    private func danubeShapedOutcomes() -> [TimelineOutcomeMeta] {
        [
            outcome(name: "October 1 – 31, 2026", prob: 0.59, change: 0.125),
            outcome(name: "November 1 – 30, 2026", prob: 0.22, change: nil),
            outcome(name: "December 1 – 31, 2026", prob: 0.11, change: nil),
            outcome(name: "Any Other Score", prob: nil, change: nil),
        ]
    }

    private func outcome(name: String, prob: Double?, change: Double?) -> TimelineOutcomeMeta {
        // `NSNull` so the key is PRESENT and null, which is what the endpoint
        // serves. An absent key takes a different path through the decoder.
        let json: [String: Any] = [
            "name": name,
            "current_probability": prob.map { $0 as Any } ?? NSNull(),
            "probability_change_24h": change.map { $0 as Any } ?? NSNull(),
        ]
        let data = try! JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TimelineOutcomeMeta.self, from: data)
    }

    func testTheWiresNullSurvivesDecodeOnBothFields() {
        let rows = danubeShapedOutcomes()
        XCTAssertNil(rows[1].probabilityChange24h, "a null change decoded to a value")
        XCTAssertNil(rows[3].currentProbability, "a null price decoded to a value")
        XCTAssertEqual(rows[0].probabilityChange24h, 0.125)
        XCTAssertEqual(rows[0].currentProbability, 0.59)
    }

    // MARK: - The defect

    func testAnAbsentChangeIsNotSpokenAsUnchanged() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenChange(nil),
                       "24-hour change not available")
        XCTAssertNotEqual(EvolutionLeaderboardGeometry.spokenChange(nil),
                          "unchanged over 24 hours",
                          "VoiceOver was told a market did not move when we had no reading")
    }

    /// The other half of the same distinction, and the reason this is not just a
    /// string swap: a market we DID read and that did not move still says so.
    func testAMeasuredZeroIsStillSpokenAsUnchanged() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenChange(0),
                       "unchanged over 24 hours")
        XCTAssertNotEqual(EvolutionLeaderboardGeometry.spokenChange(0),
                          EvolutionLeaderboardGeometry.spokenChange(nil),
                          "absence and no-movement are different facts")
    }

    func testEveryOtherSpokenDeltaIsUntouched() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenChange(1.5), "+1.5% over 24 hours")
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenChange(-12.34), "-12.3% over 24 hours")
    }

    /// The price had the same coalesce one line up, and it was visible: a null
    /// `current_probability` printed a flat `0%`. Three rows of market 60268421
    /// carry one, and the All Outcomes ladder on the same screen prints no
    /// percentage for exactly those rows.
    func testAnAbsentPriceIsTheMarkerAndNotZeroPercent() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(nil), absentProbabilityMarker)
        XCTAssertNotEqual(EvolutionLeaderboardGeometry.probLabel(nil), "0%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenProb(nil), "probability not available",
                       "an em dash is silent, so the spoken row would state no number at all")
    }

    /// #5899 pinned a measured zero as `0%` on this very function. It stays.
    func testAMeasuredZeroIsStillZeroPercent() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0), "0%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.spokenProb(0), "0%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(0.05), "0.1%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.probLabel(57), "57%")
    }

    // MARK: - What must NOT move: the drawn delta column

    /// The issue asked for the visible column to stay exactly as it is — the dash
    /// is honest for both an absent delta and a zero one, and a second spelling on
    /// screen would be a redesign riding a correctness fix.
    func testTheDrawnDeltaTreatsAbsenceAndZeroAlike() {
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(nil), "-")
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(0), "-")
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(1.5), "+1.5%")
        XCTAssertEqual(EvolutionLeaderboardGeometry.changeLabel(-12.34), "-12.3%")
    }

    // MARK: - What must NOT move: the measured widths

    /// `EvolutionLeaderboardGeometry`'s whole doctrine is that the measured string
    /// and the drawn string are one call. The drawn string for a null price just
    /// changed, so the measurement has to have changed with it — this is the
    /// assertion that says it did.
    func testTheColumnIsMeasuredOnTheStringTheRowNowDraws() throws {
        let rows = danubeShapedOutcomes()
        let columns = EvolutionLeaderboardGeometry.columns(for: rows, at: .large, renderedPercents: [])

        // What `EvolutionLeaderboardRow` will actually put on screen, built the way
        // the row builds it.
        let drawnProbs = rows.map {
            EvolutionLeaderboardGeometry.probLabel($0.currentProbability.map { $0 * 100 })
        }
        let drawnChanges = rows.map {
            EvolutionLeaderboardGeometry.changeLabel($0.probabilityChange24h.map { $0 * 100 })
        }
        XCTAssertEqual(drawnProbs.last, absentProbabilityMarker,
                       "the fixture stopped carrying a null price — re-aim this test")

        // Equality, not "it fits": a column sized on `0%` while the row draws a
        // dash is over-wide rather than clipped, so an inequality would let the
        // coalesce back into the measurement unnoticed.
        XCTAssertEqual(
            columns,
            EvolutionLeaderboardGeometry.columns(
                probs: drawnProbs, changes: drawnChanges, typeSize: .large),
            "the columns were measured on strings this row does not draw")

        let change = try XCTUnwrap(columns.change)
        for drawn in drawnProbs {
            let ink = EvolutionLeaderboardGeometry.textWidth(
                drawn, font: .probValue, typeSize: .large)
            XCTAssertLessThanOrEqual(
                ink, columns.prob,
                "\(drawn) needs \(ink)pt and the Prob column is \(columns.prob)pt")
        }
        for drawn in drawnChanges {
            let ink = EvolutionLeaderboardGeometry.textWidth(
                drawn, font: .changeValue, typeSize: .large)
            XCTAssertLessThanOrEqual(ink, change)
        }
    }

    /// A board of nothing but nulls used to be measured on `0%` and `-`; it is now
    /// measured on two dashes, so both columns fall back to their HEADERS. The
    /// header floor is the thing that stops that board drawing a heading outside
    /// its own column — the case `untradedOutcomes` was written for.
    func testAnAllNullBoardStillClearsItsHeadings() throws {
        let allNull = (1...3).map { outcome(name: "Row \($0)", prob: nil, change: nil) }
        let columns = EvolutionLeaderboardGeometry.columns(for: allNull, at: .large, renderedPercents: [])

        XCTAssertGreaterThanOrEqual(
            columns.prob,
            EvolutionLeaderboardGeometry.textWidth("Prob", font: .header, typeSize: .large))
        XCTAssertGreaterThanOrEqual(
            try XCTUnwrap(columns.change),
            EvolutionLeaderboardGeometry.textWidth("24h", font: .header, typeSize: .large))
        XCTAssertLessThanOrEqual(columns.total,
                                 EvolutionLeaderboardGeometry.legacyPairWidth)
    }

    /// 🪤 WHY MUTANT 9 OF `tools/native-256-mutations-7285.py` SURVIVES, measured
    /// rather than shrugged at.
    ///
    /// That mutant leaves the `?? 0` in `columns(for:)`, so the column is sized on
    /// `0%` while the row draws an em dash — a real divergence between the measured
    /// string and the drawn one, which is the thing this file's doctrine exists to
    /// forbid. It survives because it is currently UNOBSERVABLE: the `Prob` header
    /// is drawn in a different face and its ink floors the column above BOTH
    /// spellings, so no board can tell them apart. It is an equivalent mutant, not
    /// a hole in the suite.
    ///
    /// Pinned because that is only true while the absent spelling stays short. The
    /// day someone writes it `no price`, this fails, and the equality assertion in
    /// `testTheColumnIsMeasuredOnTheStringTheRowNowDraws` starts doing real work.
    func testTheProbHeaderFloorsBothAbsentSpellings() {
        let header = EvolutionLeaderboardGeometry.textWidth(
            "Prob", font: .header, typeSize: .large)
        let zero = EvolutionLeaderboardGeometry.textWidth(
            "0%", font: .probValue, typeSize: .large)
        let marker = EvolutionLeaderboardGeometry.textWidth(
            absentProbabilityMarker, font: .probValue, typeSize: .large)

        XCTAssertLessThan(zero, header,
                          "`0%` now decides the column; the measurement divergence is live")
        XCTAssertLessThan(marker, header,
                          "the absent marker now decides the column; same")
    }

    // MARK: - The call site

    /// The functions above are only worth their assertions if the row still reaches
    /// them holding the optional. Positive AND negative, because "the coalesce is
    /// gone" goes stale the moment someone writes it a second way, and a scan that
    /// finds nothing must fail.
    func testTheRowCarriesTheOptionalToBothLabels() throws {
        let file = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift")
        let source = try String(contentsOf: file, encoding: .utf8)

        XCTAssertTrue(source.contains("struct EvolutionLeaderboardRow"),
                      "this scan no longer holds the thing it aims at — re-aim it")
        XCTAssertTrue(source.contains("private var changePct: Double?"),
                      "the row stopped carrying the change as an optional (#7285)")
        XCTAssertTrue(source.contains("private var probPct: Double?"),
                      "the row stopped carrying the price as an optional (#7285)")
        // #8109 widened this call: the spoken row now also carries the card-level
        // decision, so a VoiceOver reader cannot hear a different number than the
        // screen draws. Re-aimed at the WHOLE call rather than loosened to a
        // prefix — this scan's job is to notice the row's arguments changing, and
        // `spokenProb(probPct` would stop noticing exactly that.
        XCTAssertTrue(
            source.contains(
                "EvolutionLeaderboardGeometry.spokenProb(probPct, renderedPercent: renderedPercent)"),
            "the spoken price stopped going through the optional-aware call (#7285) "
            + "or stopped carrying the card-level decision (#8109)")

        XCTAssertFalse(source.contains("(outcome.probabilityChange24h ?? 0)"),
                       "the 24h coalesce is back (#7285)")
        XCTAssertFalse(source.contains("(outcome.currentProbability ?? 0)"),
                       "the price coalesce is back (#7285)")
    }
}
