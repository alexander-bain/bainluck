import XCTest
@testable import Bain_Luck

/// Direction 199 / ruling 200-B: on every surface that draws the game headline,
/// "Now" is the largest number. Includes the Live Activity's Lock Screen and
/// expanded Dynamic Island, which the Apple lane draws from this one table.
final class HeadlineStyleTable199Tests: XCTestCase {
    func testNowIsTheLargestNumberOnEverySurface() {
        for surface in HeadlineStyleTable199.Surface.allCases {
            let now = HeadlineStyleTable199.nowBaseSize(surface)
            XCTAssertGreaterThan(
                now, HeadlineStyleTable199.secondNumberBaseSize(surface, prominent: false),
                "\(surface.rawValue): Now must be larger than every plain second number")
            // #12796 sized the card, widget and wrist tile so a prominent number (a
            // final score) may equal Now; Now is never smaller. The Live Activity's
            // own two surfaces keep Now strictly largest.
            let prominent = HeadlineStyleTable199.secondNumberBaseSize(surface, prominent: true)
            if surface == .lockScreen || surface == .island {
                XCTAssertGreaterThan(now, prominent, surface.rawValue)
            } else {
                XCTAssertGreaterThanOrEqual(now, prominent, surface.rawValue)
            }
            XCTAssertGreaterThan(now, HeadlineStyleTable199.nameBaseSize(surface), surface.rawValue)
            XCTAssertGreaterThan(now, HeadlineStyleTable199.quietTextBaseSize(surface), surface.rawValue)
            XCTAssertGreaterThan(now, HeadlineStyleTable199.headerBaseSize(surface), surface.rawValue)
        }
    }

    func testTheLiveActivityHasItsOwnTwoSurfaces() {
        let names = HeadlineStyleTable199.Surface.allCases.map(\.rawValue)
        XCTAssertTrue(names.contains("lockScreen"))
        XCTAssertTrue(names.contains("island"))
    }

    /// The Live Activity labels its columns with the page's words in each phase
    /// (`EventSportHeadlines12472`): before `Chance`, during `Score` and `Now`,
    /// after `Final`. No score column before kickoff.
    func testTheLiveActivityUsesThePagesColumnWordsInEachPhase() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget/GameLiveActivity.swift")
        let view = try String(contentsOf: url, encoding: .utf8).filter { !$0.isWhitespace }
        XCTAssertTrue(view.contains("case.before:Text(\"Chance\")"), "before: one Chance column")
        XCTAssertTrue(view.contains("case.during:Text(\"Score\")"), "during: Score")
        XCTAssertTrue(view.contains("Text(\"Now\").frame(width:Self.nowWidth"), "during: Now")
        XCTAssertTrue(view.contains("case.after:ifreading.hasPregame{Text(\"Pregame\")"), "after: Pregame (direction 209)")
        XCTAssertTrue(view.contains("Text(\"Final\").frame(width:Self.scoreWidth"), "after: Final")
        XCTAssertTrue(view.contains("Text(reading.shortName(side))"), "the Lock Screen prints the short name once")
        XCTAssertTrue(view.contains("ifreading.phase!=.before{Text(reading.scoreText(side))"), "no score before kickoff")
        XCTAssertTrue(view.contains("varchanceHeader:String{phase==.before?\"Chance\":\"Now\"}"))
    }
}
