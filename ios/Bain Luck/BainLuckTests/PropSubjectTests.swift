import XCTest
@testable import Bain_Luck

/// #9148 — the Player Props card named a defense "SEA Seahawks D/ST".
///
/// Measured on `/api/events/14781702/game-markets` (Seattle vs Washington) on
/// 2026-09-27: the four D/ST rows carry `outcome_name` "SEA Seahawks D/ST: Over
/// 9.2", "WAS Commanders D/ST: Over 5.7", "SEA Seahawks D/ST: 1+" and "WAS
/// Commanders D/ST: 1+". The card's name is the text before the colon.
/// `testTickerDefenseDropsTheTicker` fails on the old code; the rest pin that
/// only that exact shape moves.
final class PropSubjectTests: XCTestCase {

    func testTickerDefenseDropsTheTicker() {
        XCTAssertEqual(PropSubject.display("SEA Seahawks D/ST"), "Seahawks D/ST")
        XCTAssertEqual(PropSubject.display("WAS Commanders D/ST"), "Commanders D/ST")
        XCTAssertEqual(PropSubject.display("KC Chiefs D/ST"), "Chiefs D/ST")
    }

    func testSharedCityKeepsTheNickname() {
        XCTAssertEqual(PropSubject.display("NYJ New York Jets D/ST"), "New York Jets D/ST")
    }

    func testPlayersAndUntickeredSubjectsAreUnchanged() {
        for subject in [
            "Jaxon Smith-Njigba",
            "AJ Brown",
            "DK Metcalf",
            "Seahawks D/ST",
            "Team",
            "SEA",
            "SEA D/ST",
            "SEAT Seahawks D/ST",
            "SEA Seahawks D/ST Touchdown",
        ] {
            XCTAssertEqual(PropSubject.display(subject), subject, subject)
        }
    }
}
