import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4907 — a live game's totals ladder stops pricing rungs the score has already
/// cleared.
///
/// THE PHOTOGRAPH: Slavia Praha **1 – 1** RC Lens, `live`, **81'**, iPhone 17,
/// 13:42 PDT 2026-09-10, `artifacts-native-020/n101-ucl-15296765-props-retry.png`.
/// Server-side at the time: `GET /api/events/15296765` → `home_score 1,
/// away_score 1, status live, espn.period "81'"`. The Goals map offered
///
/// ```
///   Over 0.5   96%     <- already hit, two goals scored
///   Over 1.5   82%     <- already hit
///   Over 2.5   60%     <- genuinely open
///   Over 3.5   38%
/// ```
///
/// — a price on a thing that had already happened, next to a scoreboard saying
/// so. #4885 had already added the honest `PRE-GAME` label and iOS already drew
/// it; the label is not the fix, which is the whole point of the issue.
///
/// The views are SwiftUI and are not rasterised here. What is asserted is the
/// pure rule they now defer to —
/// ``MarketMapRail/liveTotalLadderResult(threshold:scoreSoFar:marketName:)`` for
/// WHAT a rung says mid-game, and
/// ``MarketMapRail/spectrumRowCaption(finalTotal:isSettled:canStillBeGraded:rungResult:)``
/// for whether it also wears a tense — plus a source-scan holding the two call
/// sites onto them, because a rule nothing calls is not a fix.
final class ALiveRungTheScoreClearedReadsAsHit4907Tests: XCTestCase {

    /// The specimen's rungs, ascending, as the card drew them.
    private let specimenRungs: [Double] = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    /// 1 – 1 at 81'.
    private let specimenScore = 2

    private func live(
        _ threshold: Double, _ score: Int, _ name: String? = "Total Goals O/U"
    ) -> MarketMapRail.TotalLadderResult? {
        MarketMapRail.liveTotalLadderResult(
            threshold: threshold, scoreSoFar: score, marketName: name
        )
    }

    // MARK: - The photographed frame

    /// 🔴 THE ISSUE'S OWN TABLE, AS AN ASSERTION. If this goes green on the old
    /// code it is measuring nothing, so it is written against the exact numbers
    /// the screenshot carried rather than a synthetic ladder.
    func testTheTwoClearedRungsOnThePhotographedFrameReadAsHit() {
        let verdicts = specimenRungs.map { live($0, specimenScore) }

        XCTAssertEqual(
            verdicts[0], .over,
            "Over 0.5 with two goals scored is not a 96% chance — it happened"
        )
        XCTAssertEqual(verdicts[1], .over, "Over 1.5 with two goals scored has happened")
        XCTAssertNil(verdicts[2], "Over 2.5 at 1–1 is genuinely open and keeps its price")
        XCTAssertNil(verdicts[3])
        XCTAssertNil(verdicts[4])
        XCTAssertNil(verdicts[5])
    }

    /// The reader gets BOTH halves of the card, which is why the uncleared rungs
    /// keep a percentage rather than the whole ladder going quiet.
    func testTheLiveLadderShowsVerdictsAndPricesTogether() {
        let verdicts = specimenRungs.map { live($0, specimenScore) }
        XCTAssertEqual(verdicts.filter { $0 != nil }.count, 2)
        XCTAssertEqual(verdicts.filter { $0 == nil }.count, 4)
    }

    // MARK: - Only ONE verdict is available mid-game

    /// 🔴 THE CENTRAL CLAIM, AND THE ONE MOST LIKELY TO BE "SIMPLIFIED" LATER
    /// INTO REUSING THE SETTLED GRADER. An uncleared rung is NOT a miss while the
    /// game is running — the total can still reach it. If someone routes the live
    /// path through `totalLadderResult`, every uncleared rung starts printing
    /// `MISS` on a live game and this goes red.
    func testAnUnclearedRungIsNeverAMissWhileTheGameIsStillOn() {
        for rung in specimenRungs where rung > Double(specimenScore) {
            XCTAssertNil(
                live(rung, specimenScore),
                "Over \(rung) at \(specimenScore) can still be cleared — it is open, not missed"
            )
            XCTAssertEqual(
                MarketMapRail.totalLadderResult(threshold: rung, finalTotal: specimenScore),
                .under,
                "the settled grader WOULD call it a miss, which is why the live path "
                + "must not be routed through it"
            )
        }
    }

    /// `.under` and `.push` are unreachable from the live rule, on any input.
    func testTheLiveRuleOnlyEverReturnsHitOrNothing() {
        for score in 0 ... 40 {
            for tenths in 0 ... 400 {
                let threshold = Double(tenths) / 10.0
                if let verdict = live(threshold, score) {
                    XCTAssertEqual(
                        verdict, .over,
                        "score \(score) vs \(threshold) produced \(verdict); the live rule "
                        + "may only ever say HIT"
                    )
                }
            }
        }
    }

    /// 🔴 `>` NOT `>=`, ON REACHABLE DATA. On the settled sibling the distinction
    /// is a documented-unreachable push (every served leg is a half-line). Here it
    /// is live: a game sitting exactly ON an integer line has not cleared it,
    /// because the next goal can still arrive.
    func testAScoreSittingExactlyOnAnIntegerLineHasNotClearedIt() {
        XCTAssertNil(live(7, 7), "Over 7 at 7 is still open — the eighth can arrive")
        XCTAssertEqual(live(7, 8), .over)
        XCTAssertNil(live(7, 6))
        // And the settled grader disagrees, correctly, because its total has stopped.
        XCTAssertEqual(MarketMapRail.totalLadderResult(threshold: 7, finalTotal: 7), .push)
    }

    /// Half-lines, which is what production actually serves.
    func testTheHalfLineBoundaryIsExact() {
        XCTAssertNil(live(2.5, 2), "two goals have not cleared 2.5")
        XCTAssertEqual(live(2.5, 3), .over)
    }

    /// A goalless live game grades nothing — the acceptance's vacuous case.
    func testALiveGameThatHasClearedNothingGradesNothing() {
        XCTAssertTrue(specimenRungs.allSatisfy { live($0, 0) == nil })
    }

    // MARK: - The sub-contest gate (measured reachable, not defensive)

    /// 🔴 THE GATE EXISTS BECAUSE `matchScopeLadderIndices` IS FAIL-OPEN. Where a
    /// ladder holds nothing but sub-contest rungs it keeps them all rather than
    /// empty the card, so a WHOLE-CONTEST score would grade a HALF's line.
    ///
    /// Measured on production 2026-09-11 — events whose linked `O/U`/`total`
    /// markets are entirely sub-contest-scoped: `soccer_other 57 ·
    /// soccer_italy_serie_a 7 · basketball_ncaab 7 · baseball_other 6 ·
    /// americanfootball_other 4 · baseball_mlb 2 · …` — **~99 of them outside
    /// tennis**, on sports whose scoreboard counts exactly the unit those rungs
    /// are quoted in. Tennis is stopped one gate earlier by
    /// `scoreboardCountsTheUnit`; these are not stopped by anything else.
    func testAHalfScopedRungIsNeverGradedByTheWholeGameScore() {
        // 31 points on the board, a first-half line of 24.5. The half may well
        // have scored 10.
        XCTAssertNil(
            live(24.5, 31, "Chiefs vs. Bills: 1st Half Total Points O/U 24.5"),
            "a whole-game score may not grade a first-half line"
        )
        XCTAssertEqual(
            live(24.5, 31, "Chiefs vs. Bills: Total Points O/U 24.5"), .over,
            "the same line without the sub-contest scope IS gradeable — otherwise "
            + "this test would pass with the rule deleted"
        )
    }

    /// Every scope pattern the rail knows, so the gate cannot be narrowed to the
    /// one case this test was written against.
    func testEverySubContestScopeIsGated() {
        let scoped = [
            "Zverev vs. Darderi: Set 1 Games O/U 8.5",
            "T1 vs. GEN: Map 2 Total Kills O/U 8.5",
            "Chiefs vs. Bills: 1st Half Total Points O/U 8.5",
            "Lakers vs. Suns: 2nd Half Total Points O/U 8.5",
            "Lakers vs. Suns: 3rd Quarter Total Points O/U 8.5",
            "Bruins vs. Habs: 1st Period Total Goals O/U 8.5",
            "Yankees vs. Sox: First 5 Innings Total Runs O/U 8.5",
        ]
        for name in scoped {
            XCTAssertNil(
                live(8.5, 40, name),
                "\(name) names a sub-contest and must not be graded by the match score"
            )
        }
    }

    /// The fail-open direction, matching `namesASubContestScope`'s own: a rung
    /// whose name we do not have is treated as whole-contest, exactly as the
    /// settled grader treats it today.
    func testAnUnnamedRungIsTreatedAsWholeContest() {
        XCTAssertEqual(live(1.5, 2, nil), .over)
        XCTAssertEqual(live(1.5, 2, ""), .over)
    }

    /// `Total Sets` must not be caught by the `set N` pattern — the boundary
    /// `MarketMapRail` documents, re-asserted through THIS entry point because
    /// that is the one the live grade uses.
    func testTheSetsUnitFamilyIsStillGradeableThroughTheLiveRule() {
        XCTAssertEqual(
            live(3.5, 4, "Zverev vs. Darderi: Total Sets O/U 3.5"), .over,
            "`Total Sets` is a whole-match market; only `Set 1` is a sub-contest"
        )
    }

    // MARK: - The caption

    /// 🔴 A ROW THAT SAYS `HIT` MUST NOT ALSO SAY `PRE-GAME`. Without this the
    /// 81st-minute card reads `PRE-GAME … HIT` — #3850's contradiction, a tense
    /// and a verdict in one row, arriving from the other side.
    func testAGradedRowWearsNoTense() {
        XCTAssertNil(
            MarketMapRail.spectrumRowCaption(
                finalTotal: nil, isSettled: false, canStillBeGraded: true, rungResult: .over
            ),
            "the verdict badge owns the row"
        )
    }

    /// …and the rows beside it keep theirs. This is the asymmetry the per-card
    /// caption function could not express, which is why the row-level one exists.
    func testTheUnclearedRowsOnTheSameLiveCardKeepTheirTense() {
        XCTAssertEqual(
            MarketMapRail.spectrumRowCaption(
                finalTotal: nil, isSettled: false, canStillBeGraded: true, rungResult: nil
            ),
            "PRE-GAME"
        )
    }

    /// The three clauses are independent — a gated row stays gated whatever its
    /// verdict, so #4907 cannot have re-opened #4018's abandoned-game chip.
    func testAnAbandonedGameStillWearsNoChipEitherWay() {
        for verdict: MarketMapRail.TotalLadderResult? in [nil, .over] {
            XCTAssertNil(
                MarketMapRail.spectrumRowCaption(
                    finalTotal: nil, isSettled: false,
                    canStillBeGraded: false, rungResult: verdict
                ),
                "#4018: a game that can never be graded wears no chip"
            )
        }
    }

    /// The settled card is untouched: same answers as the per-card function it
    /// wraps, for every state that function has.
    func testTheSettledAndPreGameCardsAreUnchanged() {
        // Finished, gradeable: the badge owns every row, as since #3850.
        XCTAssertNil(
            MarketMapRail.spectrumRowCaption(
                finalTotal: 11, isSettled: true, canStillBeGraded: false, rungResult: .over
            )
        )
        // Finished, NOT gradeable (tennis: the scoreboard counts sets) — #3925's
        // `LAST QUOTE` still prints.
        XCTAssertEqual(
            MarketMapRail.spectrumRowCaption(
                finalTotal: nil, isSettled: true, canStillBeGraded: false, rungResult: nil
            ),
            MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: true)
        )
        // Pre-game.
        XCTAssertEqual(
            MarketMapRail.spectrumRowCaption(
                finalTotal: nil, isSettled: false, canStillBeGraded: true, rungResult: nil
            ),
            MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: false)
        )
    }

    // MARK: - WHICH cards may grade live at all

    private func gradable(
        isLive: Bool = true, countsTheUnit: Bool = true,
        home: Int? = 1, away: Int? = 1
    ) -> Int? {
        MarketMapRail.liveGradableTotal(
            isLive: isLive, scoreboardCountsTheUnit: countsTheUnit,
            homeScore: home, awayScore: away
        )
    }

    func testALiveGameWithAScoreIsGradable() {
        XCTAssertEqual(gradable(), 2, "1–1 at 81' is the specimen")
    }

    /// 🔴 THE SCOPE PIN. An ABANDONED game has a score too, and grading it is
    /// #4018/#4829's class, not this one — verdicts on a result nobody will
    /// certify. #4907 is deliberately live-only, and without this nothing says so:
    /// dropping `isLive` for a bare "has a score" passes every other test here.
    func testASuspendedOrFinishedGameIsNotGradedByTheLiveRule() {
        XCTAssertNil(gradable(isLive: false), "a game that is not live has no live grade")
    }

    /// 🔴 The tennis gate. That scoreboard counts SETS; a ladder quoted in GAMES
    /// must never be compared to it. This is the gate that keeps the 173+20+9
    /// sub-contest tennis ladders out before the name gate is even reached.
    func testACardWhoseScoreboardCountsAnotherUnitIsNotGradable() {
        XCTAssertNil(gradable(countsTheUnit: false))
    }

    func testAMissingScoreIsNotGradable() {
        XCTAssertNil(gradable(home: nil))
        XCTAssertNil(gradable(away: nil))
    }

    /// A live 0–0 IS gradable — it just grades nothing, because no rung is
    /// cleared. The two questions are separate and both cards ask them in order.
    func testAGoallessLiveGameIsGradableAndGradesNothing() {
        XCTAssertEqual(gradable(home: 0, away: 0), 0)
        XCTAssertTrue(specimenRungs.allSatisfy { live($0, 0) == nil })
    }

    // MARK: - The rule is actually WIRED (a rule nothing calls is not a fix)

    /// 🔴 THE GUARD THAT WOULD HAVE CAUGHT SHIPPING THE RULE UNCALLED. Both cards
    /// in the issue draw this ladder — the Goals/Runs map and the Projected
    /// scoring card — and the screenshot showed the same wrong rungs on both. A
    /// fix wired into one of them is half a fix, and no unit test over a pure
    /// function can tell the difference.
    /// 🟠 AND IT SCANS CODE, NOT PROSE. The first version of this guard searched
    /// for the bare symbol and SURVIVED the mutant that unwired the Goals/Runs
    /// map — because a doc comment three hundred lines away in the same file
    /// mentions ``MarketMapRail/liveTotalLadderResult(threshold:scoreSoFar:marketName:)``
    /// by name, and a substring search cannot tell a call from a sentence about
    /// one. Comments are stripped first, and the needle is the qualified call
    /// form.
    func testBothLadderCardsCallTheLiveRule() throws {
        for file in ["MarketMapView.swift", "TotalPointsSpectrumView.swift"] {
            let code = Self.strippingComments(try Self.componentSource(file))
            XCTAssertTrue(
                code.contains("MarketMapRail.liveTotalLadderResult("),
                "\(file) draws a totals ladder and must grade its cleared rungs"
            )
            XCTAssertTrue(
                code.contains("MarketMapRail.liveGradableTotal("),
                "\(file) must ask the shared gate whether it may grade live at all"
            )
        }
    }

    /// 🔴 AND IT MUST PASS THE CARD'S OWN LIFECYCLE, NOT A LITERAL. Calling the
    /// shared gate is not the same as obeying it: `isLive: true` compiles, reads
    /// almost identically, and hands an ABANDONED game — which is neither live nor
    /// done, so `settledTotal` is nil and the `??` falls through to the live
    /// branch — a verdict on every cleared rung. That is #4018 arriving back
    /// through the door #4907 opened, and the unit tests above cannot see it
    /// because the mistake is at the call site, not in the rule.
    ///
    /// This survived the first battery. It is the reason the guard checks the
    /// ARGUMENT and not just the symbol.
    func testNeitherCardHardCodesTheLiveGatesLifecycleArgument() throws {
        for file in ["MarketMapView.swift", "TotalPointsSpectrumView.swift"] {
            let code = Self.strippingComments(try Self.componentSource(file))
            XCTAssertTrue(
                code.contains("isLive: isLive"),
                "\(file) must pass its own `isLive` to the live gate"
            )
            for literal in ["isLive: true", "isLive: false"] {
                XCTAssertFalse(
                    code.contains(literal),
                    "\(file) hard-codes `\(literal)`; an abandoned game would be graded"
                )
            }
        }
    }

    /// The stripper is itself asserted, because a scan that silently strips
    /// everything passes nothing and reads exactly like a clean sweep.
    func testTheCommentStripperKeepsCodeAndDropsProse() {
        let sample = """
        // MarketMapRail.liveTotalLadderResult( in a line comment
        /// MarketMapRail.liveTotalLadderResult( in a doc comment
        let x = MarketMapRail.liveTotalLadderResult(threshold: 1)
        """
        let stripped = Self.strippingComments(sample)
        XCTAssertEqual(
            stripped.components(separatedBy: "MarketMapRail.liveTotalLadderResult(").count - 1,
            1,
            "exactly the one real call survives"
        )
        XCTAssertTrue(stripped.contains("let x ="))
    }

    /// Line and doc comments only — enough for this scan, and honest about it.
    /// A `/* */` block would need a real lexer; there are none in either file
    /// (`testNeitherLadderFileUsesBlockComments` holds that true).
    private static func strippingComments(_ source: String) -> String {
        source
            .components(separatedBy: .newlines)
            .map { line -> String in
                guard let marker = line.range(of: "//") else { return line }
                return String(line[..<marker.lowerBound])
            }
            .joined(separator: "\n")
    }

    func testNeitherLadderFileUsesBlockComments() throws {
        for file in ["MarketMapView.swift", "TotalPointsSpectrumView.swift"] {
            XCTAssertFalse(
                try Self.componentSource(file).contains("/*"),
                "\(file) grew a block comment; the scan's stripper cannot see it"
            )
        }
    }

    /// The margin ladder must NOT — a margin is not monotone, so a side leading by
    /// 10 has not cleared `+7.5`. The reduction that lets the margin card share
    /// `totalLadderResult` (#3852) stops at the live rule, and this pins it.
    func testTheMarginLadderDoesNotGradeLive() throws {
        let code = Self.strippingComments(try Self.componentSource("MarketMapView.swift"))
        let marginLadder = try XCTUnwrap(
            code.range(of: "func marginLadder").map { String(code[$0.lowerBound...].prefix(1400)) },
            "marginLadder has been renamed — re-aim this guard"
        )
        XCTAssertTrue(
            marginLadder.contains("settledMargin"),
            "the window this guard reads no longer contains the margin ladder's body"
        )
        XCTAssertFalse(
            marginLadder.contains("liveTotalLadderResult"),
            "a margin can shrink; only a total is monotone"
        )
    }

    private static func componentSource(_ name: String) throws -> String {
        // …/ios/Bain Luck/BainLuckTests/<this file> → …/ios/Bain Luck/Bain Luck/Components/<name>
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let url = root
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent(name)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
