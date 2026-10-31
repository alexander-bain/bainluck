import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part four (the golfer chooser and the
/// before-the-start contenders card), on the retained Baycurrent Classic Winner
/// market and its top-ten history in `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The chooser and contenders models (`FieldChooserModel10868`,
/// `FieldOutlookModel10868`) are the accepted leaves' own; these tests read what
/// they resolve from the adapter's input, never re-implement them.
///
/// CONSTRUCTED here, and named where used: the reader's calendar and `now`, the
/// host's cohort and chooser disclosures, an open copy of the resolved Winner
/// body (`status` only) read before or after the listed start, and a grade on
/// one row (`is_winner` + `resolution_source`).
@MainActor
final class GolfFieldChooserAdapter10868Tests: XCTestCase {
    private typealias C = GolfFieldChooserAdapter10868
    private typealias H = GolfFieldHistoryAdapter10868
    private typealias A = GolfFieldPageAdapter10868
    private typealias R = GolfFieldRetainedBodies10868

    private static let finalNow = "2026-10-12T23:55:18Z"
    private static let order = [R.schauffele, R.clark, R.morikawa, R.brennan, R.thorbjornsen, R.mitchell, R.fishburn]

    private func field(_ winnerJSON: String, _ historyJSON: String?, now: String) throws -> H.Field {
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        return GolfFieldPageInputAdapter10868.field(.init(winner: winner, history: history), now: now.asDate!)
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    private func recorded(_ stamp: String, _ host: A.Host) -> String {
        "Recorded \(A.clockWords(stamp.asDate!, host: host)) · DataGolf"
    }

    // MARK: - Catalogue

    func testTheCatalogueIsEveryServedGolferByExactIdentityInServedOrder() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        let input = C.chooser(field, cohort: [R.schauffele, R.brennan], selected: R.schauffele, state: C.Disclosures(), host: host)

        XCTAssertEqual(input.scope, "golf:64266833:final")
        XCTAssertEqual(input.catalogue.map(\.ref.outcomeID), Self.order.map(String.init))
        XCTAssertTrue(input.catalogue.allSatisfy {
            $0.ref.isComplete && $0.ref.scope == input.scope && $0.ref.source == "datagolf" && $0.ref.marketID == "64266833"
        })
        XCTAssertEqual(input.catalogue.map(\.name), [
            "Xander Schauffele", "Wyndham Clark", "Collin Morikawa", "Michael Brennan",
            "Michael Thorbjornsen", "Keith Mitchell", "Patrick Fishburn",
        ])

        let schauffele = input.catalogue[0]
        XCTAssertEqual(schauffele.plan, .single(FieldChooserReading10868(
            label: "Before start",
            value: .recorded(text: "9%", detail: recorded("2026-10-06T13:08:40.644152+00:00", host)))))
        // No served line in this history, and his price is stamped after the start.
        XCTAssertEqual(input.catalogue[3].plan,
                       .single(FieldChooserReading10868(label: "Before start", value: .missing("Before-start chance not recorded"))))
        XCTAssertEqual(input.catalogue[6].plan,
                       .single(FieldChooserReading10868(label: "Before start", value: .missing("Before-start chance not recorded"))),
                       "served with no price: still a choosable golfer")

        let preview = try XCTUnwrap(schauffele.preview.history)
        XCTAssertEqual(preview.segments.map(\.count), [6, 2, 1])
        XCTAssertEqual(preview.gaps, [
            FieldChooserGap10868(start: x("2026-10-08T00:27:33.145591+00:00"), end: x("2026-10-11T06:02:25.916250+00:00")),
            FieldChooserGap10868(start: x("2026-10-11T06:06:55.965994+00:00"), end: x("2026-10-11T22:08:55.891004+00:00")),
        ])
        XCTAssertEqual(preview.beforeReference, 0.086583)
        XCTAssertNil(preview.emphasis, "the before reading is older than the frame, so nothing is emphasized")
        XCTAssertNil(input.catalogue[4].preview.history)
        XCTAssertEqual(input.catalogue[4].preview.absence, "No recorded history")

        XCTAssertEqual(schauffele.accent, H.tint(0))
        XCTAssertEqual(input.catalogue[3].accent, H.tint(1))
        XCTAssertNil(input.catalogue[1].accent, "not in the chart")
        XCTAssertTrue(input.catalogue.allSatisfy { $0.result == nil && $0.movement == nil }, "no grade, no tied pair")
        XCTAssertEqual(input.catalogue.map(\.browseStatus), [
            "Recorded history available", "Recorded history available", "Recorded history available",
            "No recorded history in this view", "No recorded history in this view",
            "No recorded history in this view", "No recorded history in this view",
        ])
    }

    func testSectionsReferToTheCatalogueAndEveryGolferResolves() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        let input = C.chooser(field, cohort: [R.schauffele, R.brennan, R.schauffele], selected: R.schauffele,
                              state: C.Disclosures(moreExpanded: true, browseExpanded: true, browseGroup: C.allGroupID),
                              host: host)
        XCTAssertEqual(input.featured.refs.map(\.outcomeID), [R.schauffele, R.brennan].map(String.init), "each once")
        XCTAssertEqual(input.more?.refs.map(\.outcomeID), [R.clark, R.morikawa].map(String.init))
        XCTAssertEqual(input.more?.title, "More with recorded history · 2")
        XCTAssertEqual(input.context, "3 of 7 golfers have recorded history in this view")
        XCTAssertEqual(input.browse?.title, "Browse all 7 golfers")
        XCTAssertEqual(input.browse?.groups.map(\.id), [C.allGroupID])
        XCTAssertEqual(input.browse?.groups.first?.refs.map(\.outcomeID), Self.order.map(String.init))
        XCTAssertNil(input.intro, "no election words")
        XCTAssertEqual(input.selected?.words, "In focus")

        let frame = try XCTUnwrap(input.frame)
        XCTAssertEqual(frame.start, x("2026-10-08T00:02:03.231914+00:00"))
        XCTAssertEqual(frame.end, x("2026-10-11T22:08:55.891004+00:00"))
        XCTAssertEqual(frame.ceiling, 1)
        XCTAssertEqual(frame.provenance, "DataGolf recorded history")
        XCTAssertNotNil(frame.explainedReferenceKey)

        let model = FieldChooserModel10868(input)
        XCTAssertTrue(input.catalogue.allSatisfy { model.resolve($0.ref).original != nil })
        XCTAssertEqual(model.moreRows.count, 2)
        XCTAssertEqual(model.groupRows.count, 7)
        XCTAssertEqual(model.selectedRef?.outcomeID, String(R.schauffele))
        XCTAssertEqual(C.outcomeID(input.catalogue[0].ref, market: field.market), R.schauffele)
        XCTAssertNil(C.outcomeID(FieldChooserOriginalRef10868(scope: input.scope, source: "datagolf", marketID: "1",
                                                              outcomeID: "242242520"), market: field.market))
    }

    func testRecordedCardsSetTheLatestRecordedReadingBesideTheBeforeOne() throws {
        // CONSTRUCTED: the Winner body opened (`status` only), read at 00:30Z.
        let host = R.host("2026-10-08T00:30:00Z")
        let field = try field(R.edited(R.baycurrentWinner, ["status"], to: "open"), R.baycurrentHistory,
                              now: "2026-10-08T00:30:00Z")
        let input = C.chooser(field, cohort: [R.schauffele], selected: nil, state: C.Disclosures(), host: host)
        let schauffele = input.catalogue[0]
        XCTAssertEqual(schauffele.plan, .comparison(
            before: FieldChooserReading10868(label: "Before start",
                                             value: .recorded(text: "9%", detail: recorded("2026-10-06T13:08:40.644152+00:00", host))),
            later: FieldChooserReading10868(label: "Latest recorded",
                                            value: .recorded(text: "9%", detail: recorded("2026-10-08T00:27:33.145591+00:00", host)))))
        XCTAssertEqual(schauffele.preview.history?.emphasis,
                       FieldChooserPoint10868(time: x("2026-10-08T00:27:33.145591+00:00"), probability: 0.090256))
        XCTAssertEqual(input.scope, "golf:64266833:recorded")
    }

    func testWithoutAHistoryResponseNothingClaimsThereIsNoHistory() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, nil, now: Self.finalNow)
        let input = C.chooser(field, cohort: [R.schauffele], selected: nil, state: C.Disclosures(), host: host)
        XCTAssertNil(input.context)
        XCTAssertNil(input.more)
        XCTAssertNil(input.frame)
        XCTAssertTrue(input.catalogue.allSatisfy { $0.preview.history == nil && $0.preview.absence == "History unavailable" })
        XCTAssertTrue(input.catalogue.allSatisfy { $0.browseStatus == "History unavailable" })
        XCTAssertNotNil(input.browse, "the whole field stays choosable")
    }

    func testFinalResultWordsComeOnlyFromAGrade() throws {
        let host = R.host(Self.finalNow)
        // CONSTRUCTED: Brennan's row graded won (`is_winner` + `resolution_source`).
        var graded = try R.edited(R.baycurrentWinner, ["outcomes", 3, "is_winner"], to: true)
        graded = try R.edited(graded, ["outcomes", 3, "resolution_source"], to: "datagolf_settlement")
        let field = try field(graded, R.baycurrentHistory, now: Self.finalNow)
        let input = C.chooser(field, cohort: [], selected: nil, state: C.Disclosures(), host: host)
        XCTAssertEqual(input.catalogue[3].result, FieldChooserResult10868(title: "Final result", words: "Won"))
        XCTAssertNil(input.catalogue[0].result)
        XCTAssertEqual(input.featured.emptyWords, "No golfers in the chart yet.")
    }

    // MARK: - Who starts strongest?

    func testContendersAreTheChartGolfersBeforeTheStartTiedToTheirOwnReadings() throws {
        // CONSTRUCTED: the Winner body opened, read at 2026-10-07T12:00Z.
        let host = R.host("2026-10-07T12:00:00Z")
        let field = try field(R.edited(R.baycurrentWinner, ["status"], to: "open"), R.baycurrentHistory,
                              now: "2026-10-07T12:00:00Z")
        XCTAssertEqual(field.phase, .before)
        let cohort = [R.schauffele, R.clark, R.morikawa, R.brennan]
        let chooser = C.chooser(field, cohort: cohort, selected: R.clark, state: C.Disclosures(), host: host)
        let input = try XCTUnwrap(C.contenders(field, chooser: chooser, cohort: cohort, host: host))
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.displayed.map(\.label), ["Xander Schauffele", "Wyndham Clark", "Collin Morikawa", "Michael Brennan"])
        XCTAssertEqual(input.traversal, chooser.catalogue.map(\.ref))
        XCTAssertEqual(input.scale.ticks.map(\.label), [0, 0.25, 0.5, 0.75, 1].map { OddsChartView.axisLabel(for: $0) })

        let model = FieldOutlookModel10868(input)
        XCTAssertEqual(model.bars.map(\.chance), [
            .value(probability: 0.086583, fraction: 0.086583),
            .value(probability: 0.053967, fraction: 0.053967),
            .value(probability: 0.04975, fraction: 0.04975),
            .unavailable,
        ], "Brennan has no line in this history and his price is stamped after now")
        XCTAssertEqual(model.selectedOriginal?.name, "Wyndham Clark")
        XCTAssertEqual(model.neighbour(.next)?.name, "Collin Morikawa", "the served order")

        // Any other phase draws no contenders card.
        let final = try self.field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        let finalChooser = C.chooser(final, cohort: cohort, selected: nil, state: C.Disclosures(), host: R.host(Self.finalNow))
        XCTAssertNil(C.contenders(final, chooser: finalChooser, cohort: cohort, host: R.host(Self.finalNow)))
        XCTAssertNil(C.contenders(field, chooser: chooser, cohort: [], host: host), "no golfers in the chart, no card")
    }
}
