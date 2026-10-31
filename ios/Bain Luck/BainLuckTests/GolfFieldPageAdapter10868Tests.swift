import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part one (phase, header, frames), on
/// the retained futures bodies in `GolfFieldRetainedBodies10868`, decoded as the
/// app decodes them.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here, and named where used: the reader's calendar (Pacific,
/// en_US), `now`, an open copy of the resolved Baycurrent Winner body (`status`
/// only), a start equal to its resolution (`commence_time` only) and two source
/// variants (`source` only). Clock and date words are compared with the
/// production formatters' own output, never with hard-coded strings.
@MainActor
final class GolfFieldPageAdapter10868Tests: XCTestCase {
    private typealias A = GolfFieldPageAdapter10868
    private typealias R = GolfFieldRetainedBodies10868

    func testAResolvedMarketIsFinalWhateverTheReaderClock() throws {
        let winner = try R.market(R.baycurrentWinner)
        XCTAssertEqual(A.listedStart(winner), "2026-10-08T00:00:00+00:00".asDate)
        XCTAssertEqual(A.phase(winner, now: "2026-10-12T23:55:17Z".asDate!), .final)
        // The market-level fact decides, not a clock: final even before the listed start.
        XCTAssertEqual(A.phase(winner, now: "2026-10-07T12:00:00Z".asDate!), .final)
        XCTAssertEqual(A.outlookPhase(.final), .final)
    }

    func testAnOpenMarketIsBeforeUntilItsListedStartThenRecorded() throws {
        // CONSTRUCTED: the Baycurrent Winner body with `status` "open" (one key).
        let open = try R.market(R.edited(R.baycurrentWinner, ["status"], to: "open"))
        XCTAssertEqual(A.phase(open, now: "2026-10-07T23:59:59Z".asDate!), .before)
        XCTAssertEqual(A.phase(open, now: "2026-10-08T00:00:00Z".asDate!), .recorded)
        XCTAssertEqual(A.phase(open, now: "2026-10-09T12:00:00Z".asDate!), .recorded)
        XCTAssertEqual(A.outlookPhase(.before), .before)
        XCTAssertEqual(A.outlookPhase(.recorded), .during)

        // India as served, three days before its listed start.
        let india = try R.market(R.indiaWin)
        XCTAssertEqual(A.listedStart(india), "2026-10-15T00:00:00+00:00".asDate)
        XCTAssertEqual(A.phase(india, now: "2026-10-12T23:28:52Z".asDate!), .before)
    }

    func testAStartThatIsNotBeforeItsResolutionIsNoStart() throws {
        // CONSTRUCTED: `commence_time` set equal to `resolution_date` (one key);
        // `FuturesStartDate.shown` refuses a start that is not before resolution.
        let noStart = try R.market(R.edited(R.indiaWin, ["commence_time"], to: "2026-10-18T00:00:00+00:00"))
        let host = R.host("2026-10-12T23:28:52Z")
        XCTAssertNil(A.listedStart(noStart))
        XCTAssertEqual(A.phase(noStart, now: host.now), .recorded, "no start is never called before the start")
        XCTAssertEqual(A.eyebrow(noStart, phase: .recorded), A.Words.recordedNoStartEyebrow)
        XCTAssertNil(A.context(noStart, tournament: nil, host: host), "no dates are printed for a refused start")
    }

    func testTheHeaderSaysTheStartDateAndNeverATeeTimeOrALiveFeed() throws {
        let winner = try R.market(R.baycurrentWinner)
        let host = R.host("2026-10-12T23:55:17Z")
        let copy = A.copy(winner, tournament: nil, phase: .final, finishUnavailable: A.Words.chooseGolfer, host: host)
        XCTAssertEqual(copy.eyebrow, "Final")
        XCTAssertEqual(copy.title, "Baycurrent Classic - Winner", "without the tournament body, the market's own name")
        XCTAssertEqual(copy.context, formatDateRange(start: winner.commenceTime, end: winner.resolutionDate,
                                                     localZone: R.pacific.timeZone))
        XCTAssertNotNil(copy.context)
        XCTAssertNil(copy.aboutLabel, "no About destination exists, so no about control")
        XCTAssertEqual(copy.storiesLabel, "Tournament stories")
        XCTAssertEqual(copy.finishUnavailable, A.Words.chooseGolfer)

        let open = try R.market(R.edited(R.baycurrentWinner, ["status"], to: "open"))
        let eyebrows = [A.eyebrow(open, phase: .before), A.eyebrow(open, phase: .recorded), A.eyebrow(open, phase: .final)]
        XCTAssertEqual(eyebrows, ["Before the start date", "Since the start date", "Final"])
        for words in eyebrows {
            XCTAssertFalse(words.localizedCaseInsensitiveContains("tee"))
            XCTAssertFalse(words.localizedCaseInsensitiveContains("live"))
        }
    }

    func testCardFramesOfferOnlyControlsTheyCanOpen() throws {
        let winner = try R.market(R.baycurrentWinner)
        XCTAssertEqual(A.finishFrame(winner, phase: .final),
                       GolfEventPageCardFrame10868(eyebrow: "Final", openLabel: "Expand finish expectations"))
        XCTAssertEqual(A.contendersFrame(),
                       GolfEventPageCardFrame10868(eyebrow: "Before the start date", openLabel: "Expand who starts strongest"))
        XCTAssertNil(A.movementFrame().openLabel, "the movement card has no owner input, so nothing opens")
    }

    func testClockWordsAndSourceNamesComeFromTheProductionStyleAndResolver() throws {
        let winner = try R.market(R.baycurrentWinner)
        let host = R.host("2026-10-12T23:55:17Z")
        let date = try XCTUnwrap("2026-10-06T13:08:40.644152+00:00".asDate)
        let style = Date.FormatStyle(locale: Locale(identifier: "en_US"), calendar: R.pacific, timeZone: R.pacific.timeZone)
        XCTAssertEqual(A.clockWords(date, host: host), date.formatted(style.month(.abbreviated).day().hour().minute()))
        XCTAssertTrue(A.clockWords(date, host: host).hasPrefix("Oct 6, 6:08"), "06:08 Pacific daylight time")

        XCTAssertEqual(A.sourceName(winner), "DataGolf")
        XCTAssertEqual(A.sourceKey(winner), "datagolf")
        // CONSTRUCTED: `source` null (one key) — no name, an empty key.
        let unnamed = try R.market(R.edited(R.baycurrentWinner, ["source"], to: NSNull()))
        XCTAssertNil(A.sourceName(unnamed))
        XCTAssertEqual(A.sourceKey(unnamed), "")
        // CONSTRUCTED: a source key the app cannot name (one key) — never printed raw.
        let unknown = try R.market(R.edited(R.baycurrentWinner, ["source"], to: "newvenue"))
        XCTAssertNil(A.sourceName(unknown))
        XCTAssertEqual(A.sourceKey(unknown), "newvenue", "kept as an identity key only")
    }

    func testJoinedDropsBlankParts() {
        XCTAssertEqual(A.joined(["Venue", nil, " ", "Oct 8–11"]), "Venue · Oct 8–11")
        XCTAssertNil(A.joined([nil, ""]))
    }
}
