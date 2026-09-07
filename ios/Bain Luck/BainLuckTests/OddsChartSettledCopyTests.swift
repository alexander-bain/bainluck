import XCTest
@testable import Bain_Luck

/// #3859 — the win-probability card told a finished match to keep waiting.
///
/// Photographed 2026-09-07 against production
/// (`artifacts-native-053/LOOK-settled-noreadings-15304990-s150.png`, iPhone 17).
/// Event 15304990, LAFC 2 — Real Salt Lake 2. The page's own navigation bar reads
/// `LAFC 2 - RSL 2 · FT 90'+4'`, and directly beneath it:
///
///     📈  No win probability readings for this game yet.
///
/// `GET /api/events/15304990` returns `status: completed` with an empty
/// `win_probability_sources`, and `/history` returns `history: 0`,
/// `espn_history: 0`. Nothing will ever write a snapshot for a match that is over,
/// so "yet" promises a reading that cannot arrive. The population is wholesale, not
/// a curiosity: all ten of the most recently settled events sampled for #3859 held
/// ZERO win-prob snapshots.
///
/// This is the THIRD instance of one class on one page — #3465 tensed the score
/// chart's unit-mismatch note, #3821 tensed the empty-markets line, and these four
/// sentences were missed by both. At three instances the class earns a guard rather
/// than a third one-off, which is what `testNoSentenceInTheCardPromisesALaterOnA
/// FinishedGame` is: it sweeps every sentence the card can print instead of naming
/// the four that were broken today.
///
/// The mechanism was the same each time: the sentence took NO state at all. The
/// tests below are therefore mostly about the OTHER direction — an unfinished game
/// must KEEP "yet", and upcoming games are far the larger population.
final class OddsChartSettledCopyTests: XCTestCase {

    /// Everything `EventDetail.status` is known to carry, plus the absent case.
    private static let unfinished: [String?] = [nil, "scheduled", "live", "suspended"]
    private static let finished: [String?] = ["completed", "closed"]

    // MARK: - The photographed sentence

    func testTheSettledGameDropsThePromise() {
        // The 15304990 frame, corrected.
        XCTAssertEqual(
            OddsChartView.noReadingsLine(status: "completed"),
            "No win probability readings for this game."
        )
    }

    func testAnUnfinishedGameKeepsIt() {
        // The regression that would be worse than the bug: deleting the word
        // everywhere. "Yet" is CORRECT before and during a game, and a scheduled
        // match with no readings yet is the common case, not the settled one.
        for status in Self.unfinished {
            XCTAssertEqual(
                OddsChartView.noReadingsLine(status: status),
                "No win probability readings for this game yet.",
                "status \(status ?? "nil") lost a promise it should keep"
            )
        }
    }

    func testSuspendedKeepsItsPromiseBecauseItIsNotOver() {
        // Called out on its own because it is the one status that LOOKS terminal
        // and is not: a suspended match can go back to `live` and can be settled
        // later by something that actually watched it, so a reading really may
        // still arrive. `EventState.isSuspended`'s own note is the authority.
        XCTAssertFalse(EventState.isFinished("suspended"))
        XCTAssertTrue(OddsChartView.noReadingsLine(status: "suspended").hasSuffix("yet."))
    }

    func testTheTenseFollowsIsFinishedRatherThanAHardCodedList() {
        // The copy must not grow its own idea of what "over" means. When a fifth
        // status lands the way `suspended` did (live/048), it gets its tense from
        // the one enum every other native surface already reads.
        for status in Self.unfinished + Self.finished + ["postponed", "in_progress", "🙂"] {
            let saysYet = OddsChartView.noReadingsLine(status: status).contains("yet")
            XCTAssertEqual(
                saysYet, !EventState.isFinished(status),
                "status \(status ?? "nil") disagrees with EventState.isFinished"
            )
        }
    }

    func testTheSettledLineInventsNoCause() {
        // #3821's wording decision, inherited verbatim. This branch covers a match
        // no source ever modelled AND a match whose readings we simply never
        // captured, and the view cannot tell them apart. Naming either cause is
        // false for the other half, so it names neither — a quiet true sentence
        // beats a friendly false one.
        for status in Self.finished {
            let line = OddsChartView.noReadingsLine(status: status).lowercased()
            for invented in ["never", "no venue", "no source", "expired", "unavailable", "because"] {
                XCTAssertFalse(line.contains(invented), "invented a cause we did not measure: \(invented)")
            }
        }
    }

    // MARK: - The other three sentences, which #3859 found by audit rather than by eye

    func testTheAllRangeNotEnoughReadingsLineIsTensed() {
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .all, hasAnyPointInRange: true, allIsDrawable: true, status: "completed"),
            "Not enough readings to draw a line."
        )
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .all, hasAnyPointInRange: true, allIsDrawable: true, status: "live"),
            "Not enough readings yet to draw a line."
        )
    }

    func testTheSinceStartNotEnoughReadingsLineIsTensed() {
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .sinceStart, hasAnyPointInRange: true, allIsDrawable: false, status: "closed"),
            "Not enough readings since the start to draw a line."
        )
    }

    func testTheSinceStartNoReadingsLineIsTensed() {
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .sinceStart, hasAnyPointInRange: false, allIsDrawable: false, status: "completed"),
            "No readings since the start."
        )
    }

    func testTheOfferOfTheAllRangeSurvivesSettlement() {
        // Deliberately unchanged by this fix: on a finished game "All" still holds
        // the pre-match market, so the suggestion is as true after the whistle as
        // before it. Dropping it with the tense would have cost a settled reader
        // the only route to the one line the page can actually draw.
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(
                range: .sinceStart, hasAnyPointInRange: false, allIsDrawable: true, status: "completed"),
            "No readings since the start. Switch to All for the pre-match market."
        )
    }

    func testTheUntensedSentenceIsLeftAlone() {
        // "No probability data available" never promised anything, so it does not
        // move. A fix that rewrites the sentences it did not need to is a fix
        // nobody can review.
        for status in Self.finished + Self.unfinished {
            XCTAssertEqual(
                OddsChartView.emptyChartMessage(
                    range: .all, hasAnyPointInRange: false, allIsDrawable: false, status: status),
                "No probability data available"
            )
        }
    }

    // MARK: - The whole card, read as a block

    /// THE SWEEP, which is the actual guard: every sentence this card can print,
    /// in every state it can print it in.
    ///
    /// Written this way rather than as four equality assertions because #3859 was
    /// FOUND by an audit of exactly this shape — #3821 fixed one string and its
    /// craft note asked for the sweep, and the sweep turned up four more in one
    /// file. A fifth sentence added later is covered the day it is written.
    func testNoSentenceInTheCardPromisesALaterOnAFinishedGame() {
        for status in Self.finished {
            XCTAssertFalse(
                OddsChartView.noReadingsLine(status: status).contains("yet"),
                "noReadingsLine promised a later on \(status ?? "nil")")
            for range in OddsTimeRange.allCases {
                for hasAnyPointInRange in [true, false] {
                    for allIsDrawable in [true, false] {
                        let message = OddsChartView.emptyChartMessage(
                            range: range,
                            hasAnyPointInRange: hasAnyPointInRange,
                            allIsDrawable: allIsDrawable,
                            status: status)
                        XCTAssertFalse(
                            message.contains("yet"),
                            "\(range)/\(hasAnyPointInRange)/\(allIsDrawable) on \(status ?? "nil") "
                            + "promised a later: \(message)")
                        XCTAssertFalse(message.isEmpty)
                    }
                }
            }
        }
    }

    /// #3823'S LESSON, APPLIED: a per-row rule can be correct on every row and
    /// still leave the card saying one thing several times.
    ///
    /// That is exactly what happened to the settled totals ladder — grading each
    /// line was right, and turned six lines into six identical `HIT`s. So the
    /// settled block is not merely checked for tense, it is counted: it must hold
    /// as many DISTINCT sentences as the unsettled block. A tempting "simplify"
    /// that collapses two settled states onto one string fails here rather than on
    /// Alex's phone.
    func testTheSettledSetSaysAsMuchAsTheUnsettledOne() {
        func sentences(_ status: String?) -> Set<String> {
            var out = Set([OddsChartView.noReadingsLine(status: status)])
            for range in OddsTimeRange.allCases {
                for hasAnyPointInRange in [true, false] {
                    for allIsDrawable in [true, false] {
                        out.insert(OddsChartView.emptyChartMessage(
                            range: range,
                            hasAnyPointInRange: hasAnyPointInRange,
                            allIsDrawable: allIsDrawable,
                            status: status))
                    }
                }
            }
            return out
        }

        let settled = sentences("completed")
        let unsettled = sentences("live")
        XCTAssertEqual(
            settled.count, unsettled.count,
            "the settled card draws \(settled.count) distinct sentences against "
            + "\(unsettled.count) unsettled — settlement lost the card a distinction:\n"
            + "settled: \(settled.sorted())\nunsettled: \(unsettled.sorted())")
        XCTAssertEqual(settled.count, 7, "the sentence inventory changed; read the new block as a whole")
        XCTAssertTrue(settled.isDisjoint(with: unsettled.filter { $0.contains("yet") }))
    }
}
