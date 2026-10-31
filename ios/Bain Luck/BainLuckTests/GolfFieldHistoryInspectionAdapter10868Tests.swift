import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part seven (inspecting the "Chance to
/// win" history), and the host glue's inspection state and callbacks, on the
/// retained bodies in `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no Swift
/// parse, no XCTest).
///
/// RETAINED (decoded through the production models): the Baycurrent Classic
/// Winner market 64266833 (resolved, no grade) and its three-golfer history
/// (Clark, Schauffele, Morikawa), as `GolfFieldRetainedBodies10868` carries them.
///
/// CONSTRUCTED, and named again where used:
///   - an open copy of the Winner (`status` only), so the same served rows read
///     before or during play;
///   - every reader clock: `before` Oct 7 12:00Z, `late` Oct 11 12:00Z (during
///     play, before the 22:08Z rows), the final clock, and the one-moment clocks;
///   - the host's cohort and selection, every tap position, and single-key edits
///     of a retained body (a timestamp spelling or stamp, a probability, the
///     market id, the source, the listed start).
/// No constructed clock credits live delivery: the rows are retained captures.
///
/// Hand-derived from the retained stamps (not executed): at the late clock the
/// frame starts Oct 7 18:00Z; Schauffele's runs are 00:02:03…00:27:33 (6) and
/// Oct 11 06:02:25 / 06:06:55; Clark's are 00:02:03 / 00:06:33 / 00:11:13 /
/// 00:16:55 / 00:27:33 / 00:32:03 and Oct 10 02:01:32 / 02:27:02
/// (`EvolutionSeriesGaps`: medians 4.7 and 5.7 minutes, so only the 2-hour floor
/// breaks them). Eleven moments, m1…m11 below.
///
/// Mutation controls (each fails a named test): snapping without a covering
/// segment (gap); per-golfer nearest values or interpolation (snap); a zero for a
/// missing golfer (snap, gap); grouping by timestamp spelling (spellings); ids
/// without scope (scope); evidence without source key or listed start (scope);
/// withdrawal by evidence inequality alone (sticky); one presentation for every
/// phase (presentation); a hold on every step (hold); a readout left swapped
/// after Done (untouched); offering the final (final).
@MainActor
final class GolfFieldHistoryInspectionAdapter10868Tests: XCTestCase {
    private typealias I = GolfFieldHistoryInspectionAdapter10868
    private typealias H = GolfFieldHistoryAdapter10868
    private typealias A = GolfFieldPageAdapter10868
    private typealias G = FieldHistoryGeometry10868
    private typealias Host = GolfFieldEventPageHost10868
    private typealias R = GolfFieldRetainedBodies10868

    /// CONSTRUCTED reader clocks.
    private static let lateNow = "2026-10-11T12:00:00Z"
    private static let beforeNow = "2026-10-07T12:00:00Z"
    private static let finalNow = "2026-10-12T23:55:18Z"

    /// RETAINED served stamps.
    private static let m1 = "2026-10-08T00:02:03.231914+00:00"
    private static let m5 = "2026-10-08T00:23:03.133505+00:00"
    private static let m7 = "2026-10-08T00:32:03.148937+00:00"
    private static let m8 = "2026-10-10T02:01:32.388551+00:00"
    private static let m9 = "2026-10-10T02:27:02.431908+00:00"
    private static let m10 = "2026-10-11T06:02:25.916250+00:00"
    private static let m11 = "2026-10-11T06:06:55.965994+00:00"
    private static let lateMoments = [
        "2026-10-08T00:02:03.231914+00:00", "2026-10-08T00:06:33.172825+00:00", "2026-10-08T00:11:13.058928+00:00",
        "2026-10-08T00:16:55.542752+00:00", "2026-10-08T00:23:03.133505+00:00", "2026-10-08T00:27:33.145591+00:00",
        "2026-10-08T00:32:03.148937+00:00", "2026-10-10T02:01:32.388551+00:00", "2026-10-10T02:27:02.431908+00:00",
        "2026-10-11T06:02:25.916250+00:00", "2026-10-11T06:06:55.965994+00:00",
    ]
    private static let oct5 = "2026-10-05T17:39:14.507306+00:00"
    private static let oct6 = "2026-10-06T13:08:40.644152+00:00"

    // MARK: - Helpers

    /// CONSTRUCTED: the resolved Winner served as open (`status` only).
    private func openWinner() throws -> String {
        try R.edited(R.baycurrentWinner, ["status"], to: "open")
    }

    /// CONSTRUCTED: one Clark probability changed (his 00:11:13 row).
    private func changedHistory() throws -> String {
        try R.edited(R.baycurrentHistory, ["outcomes", 0, "history", 4, "probability"], to: 0.06)
    }

    private func snapshot(_ winnerJSON: String, _ historyJSON: String?, cohort: [Int], selected: Int?,
                          held: I.Held? = nil, now: String) throws -> I.Snapshot {
        let host = R.host(now)
        return Host.inspectionSnapshot(winner: try R.market(winnerJSON), history: try historyJSON.map { try R.history($0) },
                                       cohort: cohort, selected: selected, held: held,
                                       now: host.now, calendar: host.calendar, locale: host.locale)
    }

    private func input(_ winnerJSON: String, _ historyJSON: String?, cohort: [Int], selected: Int?,
                       held: I.Held?, fullScale: Bool = false, now: String) throws -> GolfEventPageInput10868 {
        let host = R.host(now)
        return Host.build(winner: try R.market(winnerJSON), history: try historyJSON.map { try R.history($0) },
                          cohort: cohort,
                          choice: Host.Choice(selected: selected, fullScale: fullScale, inspection: held),
                          now: host.now, calendar: host.calendar, locale: host.locale)
    }

    /// The late clock, cohort [Schauffele, Clark], Schauffele selected unless named.
    private func late(held: I.Held? = nil, cohort: [Int]? = nil, selected: Int? = nil) throws -> I.Snapshot {
        try snapshot(try openWinner(), R.baycurrentHistory, cohort: cohort ?? [R.schauffele, R.clark],
                     selected: selected ?? R.schauffele, held: held, now: Self.lateNow)
    }

    private func lateInput(held: I.Held?, cohort: [Int]? = nil, selected: Int? = nil,
                           fullScale: Bool = false) throws -> GolfEventPageInput10868 {
        try input(try openWinner(), R.baycurrentHistory, cohort: cohort ?? [R.schauffele, R.clark],
                  selected: selected ?? R.schauffele, held: held, fullScale: fullScale, now: Self.lateNow)
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    private func sid(_ outcome: Int) -> String { "datagolf:64266833:\(outcome)" }

    private func pid(_ outcome: Int, _ stamp: String) -> String { "\(sid(outcome))#\(stamp)" }

    private func recorded(_ stamp: String, _ now: String) -> String {
        "Recorded \(A.clockWords(stamp.asDate!, host: R.host(now))) · DataGolf"
    }

    /// The pass's moment at exactly this instant.
    private func id(_ pass: I.Pass, _ stamp: String) throws -> String {
        try XCTUnwrap(pass.moments.first(where: { $0.date == stamp.asDate! }), stamp).id
    }

    /// Every field the inspection must not touch, field by field.
    private func assertUntouched(_ a: FieldHistoryInput10868, _ b: FieldHistoryInput10868,
                                 file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(a.title, b.title, file: file, line: line)
        XCTAssertEqual(a.caption, b.caption, file: file, line: line)
        XCTAssertEqual(a.selection, b.selection, file: file, line: line)
        XCTAssertEqual(a.domain, b.domain, file: file, line: line)
        XCTAssertEqual(a.ceiling, b.ceiling, file: file, line: line)
        XCTAssertEqual(a.yTicks, b.yTicks, file: file, line: line)
        XCTAssertEqual(a.xTicks, b.xTicks, file: file, line: line)
        XCTAssertEqual(a.guides, b.guides, file: file, line: line)
        XCTAssertEqual(a.breaks, b.breaks, file: file, line: line)
        XCTAssertEqual(a.markKey, b.markKey, file: file, line: line)
        XCTAssertEqual(a.comparisonExplanation, b.comparisonExplanation, file: file, line: line)
        XCTAssertEqual(a.notes, b.notes, file: file, line: line)
        XCTAssertEqual(a.summary, b.summary, file: file, line: line)
        XCTAssertEqual(a.plotHeight, b.plotHeight, file: file, line: line)
        XCTAssertEqual(a.unboundReadingWords, b.unboundReadingWords, file: file, line: line)
        XCTAssertEqual(a.plotUnavailableWords, b.plotUnavailableWords, file: file, line: line)
        XCTAssertEqual(a.windows, b.windows, file: file, line: line)
        XCTAssertEqual(a.scale, b.scale, file: file, line: line)
        XCTAssertEqual(a.moreOriginals, b.moreOriginals, file: file, line: line)
        XCTAssertEqual(a.details, b.details, file: file, line: line)
        XCTAssertEqual(a.expand, b.expand, file: file, line: line)
        XCTAssertEqual(a.layout, b.layout, file: file, line: line)
        XCTAssertEqual(a.probabilityLowerBound, b.probabilityLowerBound, file: file, line: line)
        XCTAssertEqual(a.probabilityRangeExplanation, b.probabilityRangeExplanation, file: file, line: line)
        XCTAssertEqual(a.selectedReadout, b.selectedReadout, file: file, line: line)
        XCTAssertEqual(a.inspectionRingShape, b.inspectionRingShape, file: file, line: line)
        XCTAssertEqual(a.plotAbsence, b.plotAbsence, file: file, line: line)
        XCTAssertEqual(a.showsKey, b.showsKey, file: file, line: line)
        XCTAssertEqual(a.series.count, b.series.count, file: file, line: line)
        for (left, right) in zip(a.series, b.series) {
            XCTAssertEqual(left.id, right.id, file: file, line: line)
            XCTAssertEqual(left.name, right.name, file: file, line: line)
            XCTAssertEqual(left.shape, right.shape, file: file, line: line)
            XCTAssertEqual(left.tint, right.tint, file: file, line: line)
            XCTAssertEqual(left.runs, right.runs, file: file, line: line)
            XCTAssertEqual(left.links, right.links, file: file, line: line)
            XCTAssertEqual(left.labelPointID, right.labelPointID, file: file, line: line)
            XCTAssertEqual(left.before, right.before, file: file, line: line)
            XCTAssertEqual(left.absentWords, right.absentWords, file: file, line: line)
            XCTAssertEqual(left.choose, right.choose, file: file, line: line)
            XCTAssertEqual(left.keyContext, right.keyContext, file: file, line: line)
        }
    }

    // MARK: - Exact values and gaps

    func testATapOnADrawnLineSnapsToTheNearestExactMomentAndNeverInterpolates() throws {
        // RETAINED rows; CONSTRUCTED open copy, late clock, cohort and taps.
        let pass = try late().pass
        XCTAssertEqual(pass.moments.map(\.date), Self.lateMoments.map { $0.asDate! })
        XCTAssertEqual(pass.seriesIDs, [sid(R.schauffele), sid(R.clark)])

        // 00:20:00 lies on both lines; 00:23:03 (183.1 s) is nearer than 00:16:55 (184.5 s).
        let tap = try XCTUnwrap(I.position(x("2026-10-08T00:20:00Z"), in: pass))
        XCTAssertEqual(tap.at, .moment(try id(pass, Self.m5)))
        let history = try lateInput(held: tap).history
        let schauffele = history.series[0]
        let clark = history.series[1]
        XCTAssertEqual(G.inspectedDisplay(schauffele, in: history),
                       .figure(formatProbability(0.087687), provenance: recorded(Self.m5, Self.lateNow)))
        XCTAssertEqual(G.inspectedDisplay(clark, in: history), .words("Not recorded"),
                       "his line passes 00:23:03 but he has no observation there: no interpolation, no zero")
        XCTAssertEqual(history.inspection?.selections[sid(R.schauffele)],
                       .point(id: pid(R.schauffele, Self.m5), spoken: formatProbability(0.087687)))
        XCTAssertEqual(history.inspection?.selections[sid(R.clark)], .absent(words: "Not recorded"))
        XCTAssertNotNil(G.inspectedPoint(schauffele, in: history))
        XCTAssertNil(G.inspectedPoint(clark, in: history), "no ring where nothing was observed")
        XCTAssertEqual(G.cursor(history), x(Self.m5))
        XCTAssertEqual(history.inspection?.caption, "Recorded \(A.clockWords(Self.m5.asDate!, host: R.host(Self.lateNow)))")

        // 00:30:00 lies only on Clark's line: 00:32:03 (123.1 s) beats 00:27:33 (146.9 s).
        let second = try XCTUnwrap(I.position(x("2026-10-08T00:30:00Z"), in: pass))
        XCTAssertEqual(second.at, .moment(try id(pass, Self.m7)))
        let secondHistory = try lateInput(held: second).history
        XCTAssertEqual(G.inspectedDisplay(secondHistory.series[1], in: secondHistory),
                       .figure(formatProbability(0.054589), provenance: recorded(Self.m7, Self.lateNow)))
        XCTAssertEqual(G.inspectedDisplay(secondHistory.series[0], in: secondHistory), .words("Not recorded"))

        // Oct 10 02:10 lies on Clark's second run: 02:01:32 (507.6 s) beats 02:27:02 (1022.4 s).
        XCTAssertEqual(try XCTUnwrap(I.position(x("2026-10-10T02:10:00Z"), in: pass)).at,
                       .moment(try id(pass, Self.m8)))
    }

    func testATapAcrossARunBreakIsAGapWithNoCursorAndNoValue() throws {
        let pass = try late().pass
        // Oct 9 12:00: both lines break here, so the tap never snaps across.
        let gap = try XCTUnwrap(I.position(x("2026-10-09T12:00:00Z"), in: pass))
        XCTAssertEqual(gap.at, .gap(previous: try id(pass, Self.m7), next: try id(pass, Self.m8)))
        let history = try lateInput(held: gap).history
        let inspection = try XCTUnwrap(history.inspection)
        XCTAssertNil(inspection.x)
        XCTAssertNil(G.cursor(history))
        XCTAssertEqual(inspection.caption, "No observation here")
        XCTAssertEqual(inspection.selections, [sid(R.schauffele): .absent(words: "Not recorded"),
                                               sid(R.clark): .absent(words: "Not recorded")])
        XCTAssertEqual(history.series.map { G.inspectedDisplay($0, in: history) },
                       [.words("Not recorded"), .words("Not recorded")])
        XCTAssertFalse(inspection.choices.contains { $0.isSelected })
        XCTAssertNil(G.sliderIndex(inspection.choices), "no moment selected: no slider position is elected")
        XCTAssertEqual(history.previous?.isAvailable, true)
        XCTAssertEqual(history.next?.isAvailable, true)

        let open = try late(held: gap)
        XCTAssertEqual(I.intent(I.previousActionID, resolved: open.resolved, in: open.pass),
                       .select(I.Held(evidence: open.pass.evidence, at: .moment(try id(pass, Self.m7)))))
        XCTAssertEqual(I.intent(I.nextActionID, resolved: open.resolved, in: open.pass),
                       .select(I.Held(evidence: open.pass.evidence, at: .moment(try id(pass, Self.m8)))))

        // Oct 10 12:00: between Clark's last Oct 10 row and Schauffele's Oct 11 rows.
        XCTAssertEqual(try XCTUnwrap(I.position(x("2026-10-10T12:00:00Z"), in: pass)).at,
                       .gap(previous: try id(pass, Self.m9), next: try id(pass, Self.m10)))
    }

    func testStepsWalkEveryMomentInOrderAndStopAtTheEnds() throws {
        let pass = try late().pass
        var held = try XCTUnwrap(I.choice(try id(pass, Self.m1), in: pass))
        var visited: [I.Position] = [held.at]
        for _ in 1..<pass.moments.count {
            let open = I.Snapshot(pass: pass, held: held)
            guard case .select(let next)? = I.intent(I.nextActionID, resolved: open.resolved, in: pass) else {
                return XCTFail("next must move while a later moment exists")
            }
            held = next
            visited.append(held.at)
        }
        XCTAssertEqual(visited, pass.moments.map { I.Position.moment($0.id) })
        XCTAssertEqual(I.intent(I.nextActionID, resolved: I.Snapshot(pass: pass, held: held).resolved, in: pass),
                       .unavailable)
        let last = try lateInput(held: held).history
        XCTAssertEqual(last.next?.isAvailable, false)
        XCTAssertEqual(last.previous?.isAvailable, true)

        let firstHeld = try XCTUnwrap(I.choice(try id(pass, Self.m1), in: pass))
        let first = try lateInput(held: firstHeld).history
        XCTAssertEqual(first.previous?.isAvailable, false)
        XCTAssertEqual(I.intent(I.previousActionID, resolved: I.Snapshot(pass: pass, held: firstHeld).resolved, in: pass),
                       .unavailable)
        XCTAssertNil(G.adjustableID(first.previous, hasCallback: true, in: first), "unavailable: not adjustable")
        XCTAssertEqual(G.adjustableID(first.next, hasCallback: true, in: first), I.nextActionID,
                       "VoiceOver's swipe steps to the next moment")
    }

    func testInspectStartsAtTheLatestMomentAndARealZeroStaysAValue() throws {
        let pass = try late().pass
        let start = try XCTUnwrap(I.start(pass))
        XCTAssertEqual(start.at, .moment(try id(pass, Self.m11)))
        XCTAssertEqual(I.intent(I.startActionID, resolved: nil, in: pass), .start(start))
        let history = try lateInput(held: start).history
        XCTAssertEqual(G.inspectedDisplay(history.series[0], in: history),
                       .figure(formatProbability(0), provenance: recorded(Self.m11, Self.lateNow)),
                       "Schauffele's served 0 is a value, never the absence words")
        XCTAssertEqual(G.inspectedDisplay(history.series[1], in: history), .words("Not recorded"))
        XCTAssertEqual(history.inspect, H.action(I.doneActionID, "Done inspecting"))
        XCTAssertEqual(history.inspection?.note, "Only exact captured observations are shown.")
    }

    // MARK: - Correction 1: one instant, one moment

    func testEquivalentSpellingsOfOneInstantAreOneMomentAndEachGolferKeepsItsOwnPoint() throws {
        // CONSTRUCTED: Clark's 00:02:03 row re-spelled with "Z" (same instant); RETAINED otherwise.
        let spelled = "2026-10-08T00:02:03.231914Z"
        let history = try R.edited(R.baycurrentHistory, ["outcomes", 0, "history", 2, "timestamp"], to: spelled)
        XCTAssertEqual(spelled.asDate, Self.m1.asDate, "one parsed instant")
        let pass = try snapshot(try openWinner(), history, cohort: [R.schauffele, R.clark], selected: R.schauffele,
                                now: Self.lateNow).pass
        XCTAssertEqual(pass.moments.count, 11, "grouped by the parsed instant, not by its spelling")
        let first = try XCTUnwrap(pass.moments.first)
        XCTAssertEqual(first.marks[sid(R.clark)]?.pointID, pid(R.clark, spelled), "Clark keeps his own raw stamp")
        XCTAssertEqual(first.marks[sid(R.schauffele)]?.pointID, pid(R.schauffele, Self.m1))
        XCTAssertEqual(first.marks[sid(R.clark)]?.figure, formatProbability(0.052477))
        XCTAssertEqual(first.marks[sid(R.schauffele)]?.figure, formatProbability(0.084473))

        let inspected = try input(try openWinner(), history, cohort: [R.schauffele, R.clark], selected: R.schauffele,
                                  held: I.choice(first.id, in: pass), now: Self.lateNow).history
        XCTAssertEqual(G.inspectedDisplay(inspected.series[1], in: inspected),
                       .figure(formatProbability(0.052477), provenance: recorded(spelled, Self.lateNow)))
        XCTAssertEqual(G.inspectedDisplay(inspected.series[0], in: inspected),
                       .figure(formatProbability(0.084473), provenance: recorded(Self.m1, Self.lateNow)))
        XCTAssertNotNil(G.inspectedPoint(inspected.series[1], in: inspected), "bound to Clark's own drawn point")
    }

    // MARK: - Corrections 2 and 3: scope and evidence

    func testAnotherMarketsPhasesOrSourcesMomentIsRefusedAndContextChangesWithdraw() throws {
        let open = try openWinner()
        let pass = try late().pass
        let held = try XCTUnwrap(I.choice(try id(pass, Self.m5), in: pass))
        XCTAssertEqual(try id(pass, Self.m5),
                       "golf.history.moment|datagolf|golf:64266833:recorded|\(Self.m5.asDate!.timeIntervalSinceReferenceDate.bitPattern)")

        // Another market at the same instants (CONSTRUCTED `id` and `market_id`).
        let other = try snapshot(try R.edited(open, ["id"], to: 64266834),
                                 try R.edited(R.baycurrentHistory, ["market_id"], to: 64266834),
                                 cohort: [R.schauffele, R.clark], selected: R.schauffele, now: Self.lateNow).pass
        XCTAssertEqual(other.moments.map(\.date), pass.moments.map(\.date), "the same instants")
        XCTAssertNil(I.choice(try id(pass, Self.m5), in: other), "another market's moment never resolves")
        XCTAssertNil(I.choice(try id(other, Self.m5), in: pass))
        XCTAssertNil(I.resolve(held, in: other))

        // Another phase at the same instants: the RETAINED resolved Winner at the final clock.
        let closed = try snapshot(R.baycurrentWinner, R.baycurrentHistory, cohort: [R.schauffele, R.clark],
                                  selected: R.schauffele, now: Self.finalNow).pass
        XCTAssertNotEqual(try id(closed, Self.m5), try id(pass, Self.m5))
        XCTAssertNil(I.resolve(held, in: closed))

        // Another source (CONSTRUCTED `source`).
        let kalshi = try snapshot(try R.edited(open, ["source"], to: "kalshi"), R.baycurrentHistory,
                                  cohort: [R.schauffele, R.clark], selected: R.schauffele, now: Self.lateNow).pass
        XCTAssertNotEqual(try id(kalshi, Self.m5), try id(pass, Self.m5))
        XCTAssertNil(I.choice(try id(pass, Self.m5), in: kalshi))
        XCTAssertNotEqual(kalshi.evidence.sourceKey, pass.evidence.sourceKey)
        XCTAssertNil(I.resolve(held, in: kalshi), "a source-key change withdraws")

        // A listed-start correction (CONSTRUCTED `commence_time`, still during play): the
        // moment id is unchanged, so only the evidence can withdraw it.
        let moved = try snapshot(try R.edited(open, ["commence_time"], to: "2026-10-07T00:00:00+00:00"),
                                 R.baycurrentHistory, cohort: [R.schauffele, R.clark], selected: R.schauffele,
                                 now: Self.lateNow).pass
        XCTAssertEqual(try id(moved, Self.m5), try id(pass, Self.m5))
        XCTAssertNotEqual(moved.evidence.listedStart, pass.evidence.listedStart)
        XCTAssertNil(I.resolve(held, in: moved), "a listed-start change withdraws")
        XCTAssertNotNil(I.resolve(held, in: pass), "control: unchanged evidence resolves")
    }

    // MARK: - Correction 4: sticky withdrawal

    func testAWithdrawnInspectionIsNeverRevivedWhenTheEvidenceMatchesAgain() throws {
        let a = try late().pass
        let b = try snapshot(try openWinner(), try changedHistory(), cohort: [R.schauffele, R.clark],
                             selected: R.schauffele, now: Self.lateNow).pass
        let held = try XCTUnwrap(I.choice(try id(a, Self.m5), in: a))
        XCTAssertNil(I.resolve(held, in: b), "new served history withdraws")
        XCTAssertNotNil(I.resolve(held, in: a), "control: the pure resolver alone would revive it on A again")

        var session = Host.Session()
        session.choose(R.schauffele)
        session.selectFinish("datagolf|64266833|242242520")
        session.open(.reader(.history))
        session.inspect(held)
        session.expireInspection(in: a)
        XCTAssertEqual(session.inspection, held, "control: a valid inspection is kept")
        session.expireInspection(in: b)
        XCTAssertNil(session.inspection, "cleared on the first pass it does not resolve on")
        session.expireInspection(in: a)
        XCTAssertNil(I.resolve(session.inspection, in: a), "A again: nothing to revive")
        XCTAssertEqual(session.selected(initial: nil), R.schauffele)
        XCTAssertEqual(session.selectedFinish, "datagolf|64266833|242242520")
        XCTAssertEqual(session.mode, .reader(.history), "the reader stays open")

        // A phase out and back: the RETAINED resolved Winner, then the open copy again.
        let closed = try snapshot(R.baycurrentWinner, R.baycurrentHistory, cohort: [R.schauffele, R.clark],
                                  selected: R.schauffele, now: Self.finalNow).pass
        session.inspect(held)
        session.expireInspection(in: closed)
        XCTAssertNil(session.inspection)
        XCTAssertNil(try late(held: session.inspection).resolved)

        // Only a deliberate new inspection opens one again.
        session.inspect(try XCTUnwrap(I.start(a)))
        XCTAssertNotNil(I.resolve(session.inspection, in: a))
    }

    // MARK: - D-I2: buttons or slider

    func testBeforeTheStartOneToFourMomentsUseButtonsAndEverythingElseTheSlider() throws {
        let open = try openWinner()
        func presentation(_ history: String, cohort: [Int], now: String, count: Int,
                          line: UInt = #line) throws -> FieldHistoryChoicePresentation10868? {
            let snap = try snapshot(open, history, cohort: cohort, selected: cohort[0], now: now)
            XCTAssertEqual(snap.pass.moments.count, count, line: line)
            let inspected = try input(open, history, cohort: cohort, selected: cohort[0],
                                      held: I.start(snap.pass), now: now).history
            return inspected.inspection?.choicePresentation
        }
        let buttons = FieldHistoryChoicePresentation10868.buttons(groupLabel: "Recorded pre-tournament estimates")
        let slider = FieldHistoryChoicePresentation10868.slider(label: "Recorded history moment")

        // CONSTRUCTED Oct 6 00:00 clock: only Schauffele's Oct 5 row is drawn.
        XCTAssertEqual(try presentation(R.baycurrentHistory, cohort: [R.schauffele], now: "2026-10-06T00:00:00Z",
                                        count: 1), buttons)
        // RETAINED Oct 5 / Oct 6 rows at the CONSTRUCTED before clock.
        XCTAssertEqual(try presentation(R.baycurrentHistory, cohort: [R.schauffele, R.clark, R.morikawa],
                                        now: Self.beforeNow, count: 2), buttons)
        // CONSTRUCTED stamps: Clark's Oct 5 row at 09:00, Morikawa's Oct 6 row at 20:00 → four instants.
        var four = try R.edited(R.baycurrentHistory, ["outcomes", 0, "history", 0, "timestamp"], to: "2026-10-05T09:00:00+00:00")
        four = try R.edited(four, ["outcomes", 2, "history", 1, "timestamp"], to: "2026-10-06T20:00:00+00:00")
        XCTAssertEqual(try presentation(four, cohort: [R.schauffele, R.clark, R.morikawa], now: Self.beforeNow,
                                        count: 4), buttons)
        // CONSTRUCTED: also Schauffele's Oct 6 row at 22:00 → five instants.
        let five = try R.edited(four, ["outcomes", 1, "history", 1, "timestamp"], to: "2026-10-06T22:00:00+00:00")
        XCTAssertEqual(try presentation(five, cohort: [R.schauffele, R.clark, R.morikawa], now: Self.beforeNow,
                                        count: 5), slider)
        // During play: the slider whatever the count.
        XCTAssertEqual(try presentation(R.baycurrentHistory, cohort: [R.schauffele, R.clark], now: Self.lateNow,
                                        count: 11), slider)
        XCTAssertEqual(try presentation(R.baycurrentHistory, cohort: [R.schauffele], now: "2026-10-08T00:03:00Z",
                                        count: 1), slider)
    }

    func testAOneMomentInspectionStaysAccessible() throws {
        // CONSTRUCTED Oct 8 00:03 clock: only Schauffele's 00:02:03 row is drawn, during play.
        let now = "2026-10-08T00:03:00Z"
        let snap = try snapshot(try openWinner(), R.baycurrentHistory, cohort: [R.schauffele], selected: R.schauffele,
                                now: now)
        XCTAssertEqual(snap.pass.moments.count, 1)
        let history = try input(try openWinner(), R.baycurrentHistory, cohort: [R.schauffele], selected: R.schauffele,
                                held: I.start(snap.pass), now: now).history
        let inspection = try XCTUnwrap(history.inspection)
        XCTAssertNil(G.sliderIndex(inspection.choices), "one choice: the shared rule draws no slider")
        XCTAssertEqual(history.previous?.isAvailable, false)
        XCTAssertEqual(history.next?.isAvailable, false)
        XCTAssertEqual(G.inspectedDisplay(history.series[0], in: history),
                       .figure(formatProbability(0.084473), provenance: recorded(Self.m1, now)))
        let spoken = G.spokenValue(history)
        XCTAssertTrue(spoken.hasPrefix(inspection.caption), spoken)
        XCTAssertTrue(spoken.contains("Xander Schauffele: \(formatProbability(0.084473))"), spoken)

        // Before the start, one moment is one live button (CONSTRUCTED Oct 6 00:00 clock).
        let before = "2026-10-06T00:00:00Z"
        let beforeSnap = try snapshot(try openWinner(), R.baycurrentHistory, cohort: [R.schauffele],
                                      selected: R.schauffele, now: before)
        let beforeHistory = try input(try openWinner(), R.baycurrentHistory, cohort: [R.schauffele],
                                      selected: R.schauffele, held: I.start(beforeSnap.pass), now: before).history
        let choices = try XCTUnwrap(beforeHistory.inspection?.choices)
        XCTAssertEqual(choices.count, 1)
        XCTAssertEqual(G.liveChoiceID(choices[0], among: choices), choices[0].id)
        XCTAssertTrue(choices[0].isSelected)
    }

    // MARK: - Hold and callbacks

    func testTheHoldComesOnceBeforeAStartAndStaleOrForgedActionsChooseNothing() throws {
        let idle = try late()
        var log: [String] = []
        var chosen: [I.Held] = []
        let record: (I.Held) -> Void = { held in
            log.append("inspect")
            chosen.append(held)
        }
        let hold = { log.append("hold") }

        let action = Host.historyAction(idle, hold: hold, inspect: record, end: { log.append("end") },
                                        other: { log.append("other:\($0)") })
        XCTAssertEqual(log, [], "building the callback calls nothing")
        action(I.startActionID)
        XCTAssertEqual(log, ["hold", "inspect"])
        XCTAssertEqual(chosen.last?.at, .moment(try id(idle.pass, Self.m11)))
        action(H.expandActionID)
        XCTAssertEqual(log.last, "other:\(H.expandActionID)", "every other id reaches the existing route")
        action(I.previousActionID)
        XCTAssertEqual(log.count, 3, "nothing is open: a step names nothing")

        let open = try late(held: chosen.last)
        XCTAssertNotNil(open.resolved)
        log = []
        let stepping = Host.historyAction(open, hold: hold, inspect: record, end: { log.append("end") },
                                          other: { log.append("other:\($0)") })
        stepping(I.previousActionID)
        XCTAssertEqual(log, ["inspect"], "a step inside an inspection asks for no hold")
        XCTAssertEqual(chosen.last?.at, .moment(try id(open.pass, Self.m10)))
        stepping(I.nextActionID)
        XCTAssertEqual(log, ["inspect"], "at the latest moment next names nothing")
        stepping(I.doneActionID)
        XCTAssertEqual(log, ["inspect", "end"])

        // Plot taps: the hold only before a start.
        log = []
        let idleTap = try XCTUnwrap(Host.plotPosition(idle, hold: hold, inspect: record))
        idleTap(x("2026-10-08T00:20:00Z"))
        XCTAssertEqual(log, ["hold", "inspect"])
        log = []
        let openTap = try XCTUnwrap(Host.plotPosition(open, hold: hold, inspect: record))
        openTap(x("2026-10-08T00:20:00Z"))
        XCTAssertEqual(log, ["inspect"])

        // Moment choices: offered only while one resolves; a forged id chooses nothing.
        XCTAssertNil(Host.inspectionChoice(idle, inspect: record))
        log = []
        let choose = try XCTUnwrap(Host.inspectionChoice(open, inspect: record))
        choose(Self.m5)
        choose("golf.history.moment|datagolf|golf:64266834:recorded|\(Self.m5.asDate!.timeIntervalSinceReferenceDate.bitPattern)")
        XCTAssertEqual(log, [], "a raw stamp and another market's id name no moment here")
        choose(try id(open.pass, Self.m5))
        XCTAssertEqual(log, ["inspect"])

        // A stale held value (CONSTRUCTED: chosen on another history's evidence).
        let b = try snapshot(try openWinner(), try changedHistory(), cohort: [R.schauffele, R.clark],
                             selected: R.schauffele, now: Self.lateNow).pass
        let staleHeld = I.Held(evidence: b.evidence, at: .moment(try id(idle.pass, Self.m5)))
        let stale = try late(held: staleHeld)
        XCTAssertNil(stale.resolved)
        log = []
        let staleAction = Host.historyAction(stale, hold: hold, inspect: record, end: { log.append("end") },
                                             other: { log.append("other:\($0)") })
        staleAction(I.nextActionID)
        XCTAssertEqual(log, [], "never a neighbour")
        staleAction(I.startActionID)
        XCTAssertEqual(log, ["hold", "inspect"], "a deliberate new inspection")
        let staleHistory = try lateInput(held: staleHeld).history
        XCTAssertEqual(staleHistory.inspect?.id, I.startActionID, "drawn as a start, never as Done")
        XCTAssertNil(staleHistory.inspection)
    }

    // MARK: - D-I3: untouched fields

    func testOnlyTheInspectionFieldsChangeAndDoneRestoresTheBaseExactly() throws {
        let host = R.host(Self.lateNow)
        let field = GolfFieldPageInputAdapter10868.field(
            .init(winner: try R.market(try openWinner()), history: try R.history(R.baycurrentHistory)), now: host.now)
        let base = H.history(field, cohort: [R.schauffele, R.clark], selected: R.schauffele, chooserAvailable: true,
                             host: host)
        let pass = I.pass(field, cohort: [R.schauffele, R.clark], host: host)
        let held = try XCTUnwrap(I.choice(try id(pass, Self.m5), in: pass))

        let inspected = I.applied(base, snapshot: I.Snapshot(pass: pass, held: held))
        XCTAssertEqual(base.readout, .beforeAndRecorded(beforeLabel: "Before start", recordedLabel: "Latest recorded"))
        XCTAssertEqual(inspected.readout, .beforeAndInspected(beforeLabel: "Before start", inspectedLabel: "Selected time"))
        assertUntouched(inspected, base)
        XCTAssertEqual(inspected.series.map(\.before), base.series.map(\.before), "the original before readings stay")
        XCTAssertNotEqual(inspected.series.map(\.recorded), base.series.map(\.recorded))

        // Nothing held (Done): the base exactly, plus only the start action.
        let idle = I.applied(base, snapshot: I.Snapshot(pass: pass, held: nil))
        assertUntouched(idle, base)
        XCTAssertEqual(idle.readout, base.readout)
        XCTAssertEqual(idle.series, base.series)
        XCTAssertNil(idle.inspection)
        XCTAssertNil(idle.previous)
        XCTAssertNil(idle.next)
        XCTAssertEqual(idle.inspect, H.action(I.startActionID, "Inspect history"))

        // Withdrawn (CONSTRUCTED: another history's evidence): the same as nothing held.
        let b = try snapshot(try openWinner(), try changedHistory(), cohort: [R.schauffele, R.clark],
                             selected: R.schauffele, now: Self.lateNow).pass
        XCTAssertEqual(I.applied(base, snapshot: I.Snapshot(pass: pass, held: I.Held(evidence: b.evidence, at: held.at))),
                       idle)

        // CONSTRUCTED non-default optional fields survive: reader layout, crop, headline readout, ring, hidden key.
        let dressed = FieldHistoryInput10868(
            title: base.title, caption: base.caption, series: base.series, selection: base.selection,
            domain: base.domain, ceiling: base.ceiling, yTicks: base.yTicks, xTicks: base.xTicks,
            guides: base.guides, breaks: base.breaks, readout: base.readout, markKey: base.markKey,
            comparisonExplanation: base.comparisonExplanation, notes: base.notes, summary: base.summary,
            plotHeight: base.plotHeight, unboundReadingWords: base.unboundReadingWords,
            plotUnavailableWords: base.plotUnavailableWords, windows: base.windows, scale: base.scale,
            moreOriginals: base.moreOriginals, details: base.details, expand: nil,
            inspect: nil, previous: nil, next: nil, inspection: nil,
            layout: .expanded, probabilityLowerBound: 0.01, probabilityRangeExplanation: "Zoomed probability range",
            selectedReadout: FieldHistorySelectedReadout10868(beforeLabel: nil, inspectedLabel: "Inspected"),
            inspectionRingShape: .circle, plotAbsence: nil, showsKey: false)
        assertUntouched(I.applied(dressed, snapshot: I.Snapshot(pass: pass, held: held)), dressed)
        assertUntouched(I.applied(dressed, snapshot: I.Snapshot(pass: pass, held: nil)), dressed)
    }

    // MARK: - D-I4: the final stays withheld

    func testTheFinalStaysWithheldWhileTheMomentMachineryStillBuilds() throws {
        // RETAINED resolved Winner and history at the final clock.
        let snap = try snapshot(R.baycurrentWinner, R.baycurrentHistory, cohort: [R.clark, R.schauffele],
                                selected: nil, now: Self.finalNow)
        XCTAssertEqual(snap.pass.phase, .final)
        XCTAssertFalse(snap.pass.offered)
        XCTAssertEqual(snap.pass.moments.count, 12, "the exact-moment machinery still runs, for a qualified final later")
        XCTAssertNil(I.start(snap.pass))
        XCTAssertNil(I.position(x(Self.m5), in: snap.pass))
        XCTAssertEqual(I.intent(I.startActionID, resolved: nil, in: snap.pass), .unavailable)
        XCTAssertNil(Host.plotPosition(snap, hold: nil, inspect: { _ in }))
        XCTAssertNil(Host.inspectionChoice(snap, inspect: { _ in }))

        let host = R.host(Self.finalNow)
        let field = GolfFieldPageInputAdapter10868.field(
            .init(winner: try R.market(R.baycurrentWinner), history: try R.history(R.baycurrentHistory)), now: host.now)
        let base = H.history(field, cohort: [R.clark, R.schauffele], selected: nil, chooserAvailable: true, host: host)
        XCTAssertEqual(I.applied(base, snapshot: snap), base, "no inspect control at the final, nothing else changes")
    }

    // MARK: - Golfer, scale, reader return

    func testGolferChoiceScaleAndReaderReturnKeepAValidInspection() throws {
        let pass = try late().pass
        let held = try XCTUnwrap(I.choice(try id(pass, Self.m5), in: pass))

        // Choosing Morikawa adds his line; the moment still resolves and he reads his own value there.
        XCTAssertNotNil(try late(held: held, selected: R.morikawa).resolved)
        let withMorikawa = try lateInput(held: held, selected: R.morikawa).history
        XCTAssertEqual(withMorikawa.series.map(\.id), [sid(R.schauffele), sid(R.clark), sid(R.morikawa)])
        XCTAssertEqual(G.inspectedDisplay(withMorikawa.series[2], in: withMorikawa),
                       .figure(formatProbability(0.051017), provenance: recorded(Self.m5, Self.lateNow)))

        // A choice that leaves the moment undrawn withdraws it (cohort [Clark], Schauffele then Clark).
        let clarkOnly = try late(cohort: [R.clark], selected: R.schauffele).pass
        let schauffeleMoment = try XCTUnwrap(I.choice(try id(clarkOnly, Self.m5), in: clarkOnly))
        XCTAssertNil(try late(held: schauffeleMoment, cohort: [R.clark], selected: R.clark).resolved)

        // A gap that gains a moment between its bounds withdraws (Morikawa's 00:36:33 row).
        let gap = try XCTUnwrap(I.position(x("2026-10-09T12:00:00Z"), in: pass))
        XCTAssertNotNil(try late(held: gap).resolved)
        XCTAssertNil(try late(held: gap, selected: R.morikawa).resolved)

        // Auto and Full read the same inspection.
        let auto = try lateInput(held: held).history
        let full = try lateInput(held: held, fullScale: true).history
        XCTAssertNotEqual(auto.ceiling, full.ceiling)
        XCTAssertEqual(auto.inspection, full.inspection)
        XCTAssertEqual(auto.series.map(\.recorded), full.series.map(\.recorded))
        XCTAssertEqual(auto.readout, full.readout)

        // The full-size reader carries the same inspection.
        let page = try lateInput(held: held)
        let reader = GolfEventPageModel10868(page).readerHistory
        XCTAssertEqual(reader.inspection, page.history.inspection)
        XCTAssertEqual(reader.inspect, page.history.inspect)
        XCTAssertEqual(reader.previous, page.history.previous)
        XCTAssertEqual(reader.next, page.history.next)
        XCTAssertEqual(reader.readout, page.history.readout)
        XCTAssertEqual(reader.series, page.history.series)
        XCTAssertEqual(reader.layout, .expanded)

        // Page ↔ reader, Done, swipe-down, golfer and finish keep it; only Done inspecting ends it.
        var session = Host.Session()
        session.inspect(held)
        session.open(.reader(.history))
        XCTAssertEqual(session.inspection, held)
        session.close()
        XCTAssertEqual(session.inspection, held)
        session.open(.reader(.finish))
        session.dismiss()
        XCTAssertEqual(session.inspection, held)
        session.choose(R.morikawa)
        session.selectFinish("datagolf|64266833|242242527")
        XCTAssertEqual(session.inspection, held)
        session.endInspection()
        XCTAssertNil(session.inspection)
        XCTAssertEqual(session.selected(initial: nil), R.morikawa)
        XCTAssertEqual(session.selectedFinish, "datagolf|64266833|242242527")
    }

    func testAGapWithdrawnByAGolferChoiceUnderEqualEvidenceNeverRevives() throws {
        // RETAINED rows; CONSTRUCTED open copy, late clock, cohort and tap.
        let pass = try late().pass
        let gap = try XCTUnwrap(I.position(x("2026-10-09T12:00:00Z"), in: pass))
        XCTAssertEqual(gap.at, .gap(previous: try id(pass, Self.m7), next: try id(pass, Self.m8)))

        var session = Host.Session()
        session.choose(R.schauffele)
        session.inspect(gap)

        // Choosing Morikawa adds his line: the served evidence is EQUAL, yet the pass differs —
        // his 00:36:33 row now lies between the gap's bounds.
        session.choose(R.morikawa)
        let withMorikawa = try late(selected: R.morikawa).pass
        XCTAssertEqual(withMorikawa.evidence, pass.evidence, "a golfer choice never changes the evidence")
        XCTAssertNotEqual(withMorikawa, pass, "the pass the observer sees does change")
        XCTAssertNil(I.resolve(gap, in: withMorikawa))
        session.expireInspection(in: withMorikawa)
        XCTAssertNil(session.inspection, "cleared on the first pass it does not resolve on")

        // Back to the old cohort: the old gap does not revive.
        session.choose(R.schauffele)
        XCTAssertNotNil(I.resolve(gap, in: pass), "control: the pure resolver alone would revive it")
        XCTAssertNil(I.resolve(session.inspection, in: pass))
        XCTAssertNil(try late(held: session.inspection).resolved)
        let back = try lateInput(held: session.inspection).history
        XCTAssertNil(back.inspection)
        XCTAssertEqual(back.inspect?.id, I.startActionID, "only a deliberate new inspection opens one again")
        XCTAssertEqual(session.selected(initial: nil), R.schauffele)
    }

    // MARK: - Original Details and Session

    func testSessionAndOriginalDetailsBehaviourAreUnchanged() throws {
        let pass = try late().pass
        let held = try XCTUnwrap(I.choice(try id(pass, Self.m5), in: pass))
        let plain = try lateInput(held: nil)
        let inspected = try lateInput(held: held)

        // The inspection reaches the history only.
        XCTAssertNotEqual(inspected.history, plain.history)
        XCTAssertEqual(inspected.phase, plain.phase)
        XCTAssertEqual(inspected.copy, plain.copy)
        XCTAssertEqual(inspected.status, plain.status)
        XCTAssertEqual(inspected.finish, plain.finish)
        XCTAssertEqual(inspected.finishFrame, plain.finishFrame)
        XCTAssertEqual(inspected.contenders, plain.contenders)
        XCTAssertEqual(inspected.contendersFrame, plain.contendersFrame)
        XCTAssertEqual(inspected.movement, plain.movement)
        XCTAssertEqual(inspected.movementFrame, plain.movementFrame)
        XCTAssertEqual(inspected.chooser, plain.chooser)

        // The finish Details callback is offered the same way over the same finish.
        let host = R.host(Self.lateNow)
        let winner = try R.market(try openWinner())
        let originals = Host.originals(winner: winner, history: try R.history(R.baycurrentHistory), now: host.now,
                                       calendar: host.calendar, locale: host.locale)
        XCTAssertNotNil(Host.finishDetails(plain, originals: originals, hold: nil, open: { _ in }))
        XCTAssertNotNil(Host.finishDetails(inspected, originals: originals, hold: nil, open: { _ in }))
        XCTAssertEqual(GolfEventPageModel10868(inspected).finish, GolfEventPageModel10868(plain).finish)

        // The Details layer and its return context are untouched by an open inspection.
        var session = Host.Session()
        session.inspect(held)
        session.open(.reader(.finish))
        session.openDetails(.unavailable)
        XCTAssertEqual(session.presented?.id, "reader.finish")
        session.close()
        XCTAssertEqual(session.mode, .reader(.finish))
        XCTAssertNil(session.details)
        XCTAssertEqual(session.inspection, held)
        session.openDetails(.unavailable)
        session.dismiss()
        XCTAssertNil(session.presented)
        XCTAssertEqual(session.inspection, held)

        // The existing history routes are unchanged, and no inspection id is routed there.
        XCTAssertEqual(Host.route(H.expandActionID), .expand)
        XCTAssertEqual(Host.route(H.chooserActionID), .chooser)
        XCTAssertEqual(Host.route(H.scaleActionID), .scale)
        XCTAssertEqual(Host.route(I.startActionID), .none)
        XCTAssertEqual(Host.route(I.nextActionID), .none)
    }

    // MARK: - Before the start

    func testBeforeTheStartATapReadsEachGolfersOwnPreStartObservation() throws {
        // RETAINED rows; CONSTRUCTED open copy and the Oct 7 clock.
        let open = try openWinner()
        let cohort = [R.schauffele, R.clark, R.morikawa]
        let snap = try snapshot(open, R.baycurrentHistory, cohort: cohort, selected: R.schauffele, now: Self.beforeNow)
        XCTAssertEqual(snap.pass.phase, .before)
        XCTAssertEqual(snap.pass.moments.map(\.date), [Self.oct5, Self.oct6].map { $0.asDate! })

        // Oct 6 00:00 lies on every line: Oct 5 17:39 (6 h 21 min) beats Oct 6 13:08 (13 h 9 min).
        let tap = try XCTUnwrap(I.position(x("2026-10-06T00:00:00Z"), in: snap.pass))
        XCTAssertEqual(tap.at, .moment(try id(snap.pass, Self.oct5)))
        let history = try input(open, R.baycurrentHistory, cohort: cohort, selected: R.schauffele, held: tap,
                                now: Self.beforeNow).history
        XCTAssertEqual(history.series.map { G.inspectedDisplay($0, in: history) }, [
            .figure(formatProbability(0.089), provenance: recorded(Self.oct5, Self.beforeNow)),
            .figure(formatProbability(0.053783), provenance: recorded(Self.oct5, Self.beforeNow)),
            .figure(formatProbability(0.048933), provenance: recorded(Self.oct5, Self.beforeNow)),
        ])
        XCTAssertEqual(history.readout, .beforeAndInspected(beforeLabel: "Before start", inspectedLabel: "Selected time"))
        let base = try input(open, R.baycurrentHistory, cohort: cohort, selected: R.schauffele, held: nil,
                             now: Self.beforeNow).history
        XCTAssertEqual(base.readout, .singleBefore(label: "Before start"))
        XCTAssertEqual(history.series.map(\.before), base.series.map(\.before))
    }
}
