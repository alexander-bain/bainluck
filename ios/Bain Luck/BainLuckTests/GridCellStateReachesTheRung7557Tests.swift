import XCTest
@testable import Bain_Luck

/// #7557 — a graded grid cell draws its result, not the no-market glyph.
///
/// THE DEFECT. `/api/playoffs/{league}` carries a typed `state` on every cell
/// (queue 295 / L2-227; live since #7387 at v4821). `GridCell` did not decode
/// it, so `LadderCardView(gridTeam:columns:)` built every rung with
/// `LadderRungState`'s default `.open` and `trailingValue` printed
/// `ladderPercent(nil)` — **"—", the app's own no-market glyph** — on every
/// cell the venue had already graded. Measured on the 2026-09-20 17:04Z MLB
/// payload: 120 cells, 7 `won` + 46 `eliminated`, and **all 53 of those carry
/// `merged_probability: null`**, so all 53 read "—". Milwaukee had clinched its
/// division and the MIL DIVISION rung said nothing. Web drew ✓.
///
/// WHY THE SUITE IS SHAPED LIKE THIS. The whole class is a field crossing three
/// links — decode, adapt, render — and a test at any one link passes while the
/// reader still sees "—". So the load-bearing cases run the REAL adapter
/// (`LadderCardView(gridTeam:columns:)` → `LadderRung`) over cells built by the
/// REAL decoder from the verbatim payload bytes, and assert on the rung a
/// reader is shown. The unit cases beneath them say WHY a rung came out that
/// way; they do not stand in for it.
///
/// The fail-closed half is not decoration. `renderState` is the only thing
/// standing between an unrecognised state string and a rung that publishes a
/// number for a cell this build cannot read, so every such input is pinned with
/// a number in the payload that must NOT reach the reader.
final class GridCellStateReachesTheRung7557Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func cell(_ json: String) throws -> GridCell {
        try decoder().decode(GridCell.self, from: Data(json.utf8))
    }

    /// The four MLB columns, in served order.
    private static let columns: [GridColumn] = [
        GridColumn(key: "make_playoffs", label: "Make Playoffs", order: 1, sequential: true, marketId: nil),
        GridColumn(key: "division", label: "Division", order: 2, sequential: true, marketId: nil),
        GridColumn(key: "pennant", label: "AL / NL Champ", order: 3, sequential: true, marketId: nil),
        GridColumn(key: "championship", label: "World Series", order: 4, sequential: true, marketId: nil),
    ]

    private func team(_ name: String, cells: [String: GridCell]) -> GridTeam {
        GridTeam(
            name: name, shortName: nil, teamId: nil, logoUrl: nil,
            primaryColor: nil, secondaryColor: nil, record: nil,
            conference: nil, division: nil, region: nil, seed: nil,
            cells: cells
        )
    }

    /// Run the real adapter and return its rungs by column key.
    private func rungs(for team: GridTeam) -> [String: LadderRung] {
        let card = LadderCardView(gridTeam: team, columns: Self.columns)
        return Dictionary(uniqueKeysWithValues: card.rungs.map { ($0.id, $0) })
    }

    // MARK: - The reader's rung (the specimen from the issue, end to end)

    /// THE NAMED SPECIMEN. Milwaukee's `division` cell, verbatim from the
    /// 17:04Z payload, through the decoder and the real adapter.
    ///
    /// Both halves are asserted because either alone passes on the defect: the
    /// rung must be `.clinched` (so `trailingValue` draws ✓ and `bar` fills the
    /// track), AND it must not be the `.open`/nil pair that produced "—".
    func testTheClinchedDivisionRungIsClinchedAndNotTheNoMarketGlyph() throws {
        let mil = team("Brewers", cells: [
            "division": try cell(#"{"merged_probability": null, "sources": [], "trend_24h": null, "state": "won"}"#),
        ])

        let rung = try XCTUnwrap(rungs(for: mil)["division"])

        XCTAssertEqual(rung.state, .clinched, "a cell the venue graded WON is a clinched rung")
        XCTAssertNotEqual(rung.state, .open, "the .open branch is the one that prints the no-market glyph")

        // The glyph the defect produced, named so this test fails if "—" ever
        // becomes what a clinched rung draws.
        XCTAssertEqual(ladderPercent(nil), "—", "control: the .open branch's output for a null probability")
    }

    /// The other terminal half, same path: `eliminated` draws ✕, not "—".
    func testAnEliminatedRungIsEliminatedAndNotTheNoMarketGlyph() throws {
        let row = team("Rockies", cells: [
            "division": try cell(#"{"merged_probability": null, "sources": [], "trend_24h": null, "state": "eliminated"}"#),
        ])

        let rung = try XCTUnwrap(rungs(for: row)["division"])

        XCTAssertEqual(rung.state, .eliminated)
        XCTAssertNotEqual(rung.state, .open)
    }

    /// The control that keeps this suite honest: a LIVE cell is unchanged by
    /// the fix — still open, still carrying its number. 67 of the payload's 120
    /// cells are this, and a fix that settled them would be worse than the bug.
    func testALiveRungStillCarriesItsNumber() throws {
        let row = team("Dodgers", cells: [
            "pennant": try cell(#"{"merged_probability": 0.4, "sources": [], "trend_24h": 0.005, "state": "live"}"#),
        ])

        let rung = try XCTUnwrap(rungs(for: row)["pennant"])

        XCTAssertEqual(rung.state, .open)
        XCTAssertEqual(rung.probability, 0.4)
        XCTAssertEqual(ladderPercent(rung.probability), "40%")
    }

    /// A whole team row, mixed the way the payload actually mixes them: two
    /// graded cells and two live ones on the same card. A mapping that keys on
    /// the row rather than the cell passes every single-cell test above.
    func testOneTeamCarriesGradedAndLiveRungsAtTheSameTime() throws {
        let lad = team("Dodgers", cells: [
            "make_playoffs": try cell(#"{"merged_probability": null, "sources": [], "trend_24h": null, "state": "won"}"#),
            "division": try cell(#"{"merged_probability": null, "sources": [], "trend_24h": null, "state": "won"}"#),
            "pennant": try cell(#"{"merged_probability": 0.4, "sources": [], "trend_24h": 0.005, "state": "live"}"#),
            "championship": try cell(#"{"merged_probability": 0.2855, "sources": [], "trend_24h": -0.002, "state": "live"}"#),
        ])

        let byKey = rungs(for: lad)

        XCTAssertEqual(byKey["make_playoffs"]?.state, .clinched)
        XCTAssertEqual(byKey["division"]?.state, .clinched)
        XCTAssertEqual(byKey["pennant"]?.state, .open)
        XCTAssertEqual(byKey["championship"]?.state, .open)
        XCTAssertEqual(byKey["championship"]?.probability, 0.2855)
    }

    /// A column the team has no cell for is unchanged: an open rung with no
    /// number. `missing` must not become a verdict just because it is typed.
    func testAColumnWithNoCellStaysAnEmptyOpenRung() throws {
        let row = team("Marlins", cells: [:])

        let byKey = rungs(for: row)

        XCTAssertEqual(byKey.count, 4, "every column still produces a rung")
        for key in ["make_playoffs", "division", "pennant", "championship"] {
            XCTAssertEqual(byKey[key]?.state, .open, "\(key)")
            XCTAssertNil(byKey[key]?.probability, "\(key)")
        }
    }

    // MARK: - Settled means settled: no terminal rung publishes a number

    /// A graded cell that still carries a price hands the adapter NO number.
    ///
    /// The render already ignores a clinched rung's probability, so this is
    /// about the model: nothing downstream — a future tooltip, a sort, a share
    /// card — may find a live-looking percentage on a settled rung.
    func testATerminalCellNeverPublishesItsProbabilityOrTrend() throws {
        for state in ["won", "eliminated"] {
            let raw = try cell(#"{"merged_probability": 0.97, "sources": [], "trend_24h": 0.04, "state": "\#(state)"}"#)

            XCTAssertNil(raw.publishedProbability, "\(state) published a probability")
            XCTAssertNil(raw.publishedTrend24H, "\(state) published a trend")

            let rung = try XCTUnwrap(rungs(for: team("X", cells: ["division": raw]))["division"])
            XCTAssertNil(rung.probability, "\(state) reached the rung with a number")
        }
    }

    /// The card's headline delta ("WIN 24H") comes off the LAST column, so a
    /// settled championship must not leave a 24-hour move beside it.
    func testTheHeadlineDeltaIsDroppedWhenTheLastColumnIsSettled() throws {
        let settled = team("Dodgers", cells: [
            "championship": try cell(#"{"merged_probability": 1.0, "sources": [], "trend_24h": 0.08, "state": "won"}"#),
        ])
        XCTAssertNil(LadderCardView(gridTeam: settled, columns: Self.columns).headlineDelta)

        // Control: the same shape while still trading keeps its delta, so the
        // assertion above is about SETTLEMENT and not about the field itself.
        let live = team("Dodgers", cells: [
            "championship": try cell(#"{"merged_probability": 0.2855, "sources": [], "trend_24h": 0.08, "state": "live"}"#),
        ])
        XCTAssertEqual(LadderCardView(gridTeam: live, columns: Self.columns).headlineDelta ?? 0, 8.0, accuracy: 0.0001)
    }

    // MARK: - Fail closed (every case carries a number that must not be shown)

    /// A state this build has never heard of is `unavailable` — and its number
    /// does not reach the reader. Web's `readDeclaredState` has the same rule;
    /// a `default: .live` here would publish a price for a cell we cannot read.
    func testAnUnrecognisedStateIsUnavailableAndPublishesNothing() throws {
        let raw = try cell(#"{"merged_probability": 0.9, "sources": [], "trend_24h": 0.01, "state": "vacated"}"#)

        XCTAssertEqual(raw.renderState, .unavailable)
        XCTAssertNil(raw.publishedProbability, "0.9 reached the reader through a state we cannot read")

        let rung = try XCTUnwrap(rungs(for: team("X", cells: ["division": raw]))["division"])
        XCTAssertEqual(rung.state, .open, "unavailable is an empty OPEN rung, never a verdict")
        XCTAssertNil(rung.probability)
    }

    /// `missing` is the register saying the market is not there. Same
    /// treatment, and specifically NOT `.eliminated` — "no market" is not
    /// "cannot happen".
    func testAMissingCellIsAnEmptyOpenRungAndNotAVerdict() throws {
        let raw = try cell(#"{"merged_probability": 0.9, "sources": [], "trend_24h": null, "state": "missing"}"#)

        XCTAssertEqual(raw.renderState, .missing)
        XCTAssertNil(raw.publishedProbability)

        let rung = try XCTUnwrap(rungs(for: team("X", cells: ["division": raw]))["division"])
        XCTAssertEqual(rung.state, .open)
        XCTAssertNotEqual(rung.state, .eliminated, "a missing market is not an impossible outcome")
    }

    /// A cell declared live with no usable number cannot be drawn as live.
    func testALiveCellWithNoNumberIsUnavailable() throws {
        XCTAssertEqual(try cell(#"{"merged_probability": null, "state": "live"}"#).renderState, .unavailable)
    }

    /// Out-of-contract numbers are not numbers this app draws. Each is paired
    /// with the in-range control so the bound is asserted, not the field.
    func testAnOutOfRangeProbabilityIsNotPublished() throws {
        for bad in ["1.4", "-0.2"] {
            let raw = try cell(#"{"merged_probability": \#(bad), "state": "live"}"#)
            XCTAssertEqual(raw.renderState, .unavailable, "\(bad)")
            XCTAssertNil(raw.publishedProbability, "\(bad)")
        }
        for good in ["0.0", "1.0"] {
            let raw = try cell(#"{"merged_probability": \#(good), "state": "live"}"#)
            XCTAssertEqual(raw.renderState, .live, "\(good)")
            XCTAssertNotNil(raw.publishedProbability, "\(good)")
        }
    }

    // MARK: - Decode and vocabulary

    /// The field is decoded at all. `.convertFromSnakeCase` leaves `state`
    /// alone, but a CodingKeys slip here is silent — the cell would decode
    /// fine, with `state == nil`, and every rung would go back to "—".
    func testStateIsDecodedFromThePayloadKey() throws {
        XCTAssertEqual(try cell(#"{"merged_probability": null, "state": "won"}"#).state, "won")
        XCTAssertEqual(try cell(#"{"merged_probability": null, "state": "won"}"#).declaredRenderState, .won)
    }

    /// A payload that declares no state at all — a pre-register cached
    /// response — still decodes, and still infers from the number alone.
    /// This is the control for the whole fix: it is what every build before
    /// today did, and it must keep working.
    func testAPayloadWithNoDeclaredStateFallsBackToTheNumber() throws {
        let withNumber = try cell(#"{"merged_probability": 0.42, "trend_24h": 0.031}"#)
        XCTAssertNil(withNumber.state)
        XCTAssertNil(withNumber.declaredRenderState)
        XCTAssertEqual(withNumber.renderState, .live)
        XCTAssertEqual(withNumber.publishedProbability, 0.42)
        XCTAssertEqual(withNumber.publishedTrend24H, 0.031)

        let without = try cell(#"{"merged_probability": null}"#)
        XCTAssertEqual(without.renderState, .missing)
        XCTAssertNil(without.publishedProbability)
    }

    /// `clinched` is the display word for `won`. The register does not send it
    /// today; accepting it is what stops a future producer from silently
    /// degrading a clinched cell to `unavailable`.
    func testTheClinchedAliasIsReadAsWon() throws {
        let raw = try cell(#"{"merged_probability": null, "state": "clinched"}"#)
        XCTAssertEqual(raw.declaredRenderState, .won)
        XCTAssertEqual(try XCTUnwrap(rungs(for: team("X", cells: ["division": raw]))["division"]).state, .clinched)
    }

    /// The vocabulary itself, pinned. If the register grows a sixth state, this
    /// fails here and the parity test fails in CI — so the fail-closed default
    /// gets re-read by a person instead of quietly swallowing the new state.
    func testTheStateVocabularyIsTheFiveContractStates() {
        XCTAssertEqual(
            Set(GridCellRenderState.allCases.map(\.rawValue)),
            ["live", "won", "eliminated", "missing", "unavailable"]
        )
        XCTAssertEqual(
            Set(GridCellRenderState.allCases.filter(\.isTerminal).map(\.rawValue)),
            ["won", "eliminated"],
            "only a graded outcome is terminal"
        )
    }

    /// The general rule over the whole vocabulary, so a sixth state cannot be
    /// added with a number-publishing default: exactly one state publishes a
    /// probability, and it is `live`.
    func testOnlyALiveCellEverPublishesANumber() throws {
        var publishing: [String] = []
        for state in GridCellRenderState.allCases {
            let raw = try cell(#"{"merged_probability": 0.5, "trend_24h": 0.01, "state": "\#(state.rawValue)"}"#)
            if raw.publishedProbability != nil || raw.publishedTrend24H != nil {
                publishing.append(state.rawValue)
            }
        }
        XCTAssertEqual(publishing, ["live"])
    }
}
