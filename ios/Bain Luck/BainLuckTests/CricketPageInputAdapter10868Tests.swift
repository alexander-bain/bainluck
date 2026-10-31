import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match adapter, parts four and five (the stories
/// production data can feed and the whole page input), on the retained REAL
/// bodies of `CricketEventPageAdapter10868Tests` (decoded the app's way; their
/// paths, sha256 values and the "nearest real body" note are there).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED, one key each and named where used: `status` set to `live`,
/// `completed` or `scheduled`; the reader's calendar, `now` and the host's
/// displayed probability clock are host values.
@MainActor
final class CricketPageInputAdapter10868Tests: XCTestCase {
    private typealias Fixtures = CricketEventPageAdapter10868Tests
    private typealias Input = CricketPageInputAdapter10868
    private typealias Stories = CricketStoriesAdapter10868

    private func input(_ event: EventDetail, host: CricketEventPageAdapter10868.Host,
                       originals: Int? = nil) -> CricketEventPageInput10868 {
        Input.input(event, history: CricketHistoryAdapter10868.unavailable(event), originalsCount: originals,
                    stream: .init(), host: host)
    }

    /// CONSTRUCTED: `status` set to `scheduled`, read before the listed start.
    func testBeforePlayThePageIsTitleHeadlineHistoryAndOriginalsWithNoStory() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "status", to: "scheduled")
        let page = input(event, host: Fixtures.host("2026-10-11T12:00:00+00:00"))
        XCTAssertEqual(page.phase, .before)
        XCTAssertNil(page.stream, "the reference's before page offers no story")
        XCTAssertEqual(page.stories, [])
        XCTAssertNil(page.shifts)
        XCTAssertNil(page.chase)
        XCTAssertNil(page.survival)
        XCTAssertNil(page.expectations)
        XCTAssertNil(page.historyMarkers, "no cricket score report reaches the app")
        let model = CricketEventPageModel10868(page)
        XCTAssertTrue(model.isMounted(.history))
        XCTAssertFalse(model.isMounted(.shifts))
        XCTAssertFalse(model.isMounted(.chase))
        XCTAssertFalse(model.isMounted(.survival))
        XCTAssertFalse(model.isMounted(.expectations))
        XCTAssertNotNil(model.headline, "the headline is at the page's own phase")
        XCTAssertEqual(page.copy.aboutLabel, "About this match")
        XCTAssertNil(page.copy.allPropsLabel, "no originals, no entry")
    }

    /// The retained body as served: during a stoppage no original shows both a
    /// pregame and an in-play figure, so there is no change to show.
    func testDuringAStoppageNoStoryIsOffered() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka)
        let page = input(event, host: Fixtures.host(Fixtures.capturedAt))
        XCTAssertEqual(page.phase, .during)
        XCTAssertNil(page.shifts)
        XCTAssertNil(page.stream)
        XCTAssertEqual(page.stories, [])
        XCTAssertNil(page.chase, "no runs, wickets, overs or target reach the app")
        XCTAssertNil(page.survival)
    }

    /// CONSTRUCTED: `status` set to `live`, with the served `current_odds` clock
    /// as the host's displayed clock, read 2½ minutes later.
    func testDuringLivePlayChangingExpectationsIsTheOneStory() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "status", to: "live")
        let host = Fixtures.host("2026-10-11T15:55:00+00:00", observedAt: "2026-10-11T15:52:33.190244+00:00")
        let page = input(event, host: host)
        let shifts = try XCTUnwrap(page.shifts)
        XCTAssertEqual(shifts.eyebrow, "Pregame → current chance")
        XCTAssertEqual(shifts.title, "How the outlook changed")
        XCTAssertEqual(shifts.rows, page.headline.rows, "the headline's own readings, unchanged")
        XCTAssertEqual(shifts.mode, .comparison)
        XCTAssertFalse(shifts.isCompleted)
        XCTAssertTrue(shifts.rows.allSatisfy { $0.movement == nil }, "no point change is written")
        XCTAssertTrue(shifts.showsPair(shifts.rows[0]), "the home side's pregame and in-play figures")
        XCTAssertFalse(shifts.showsPair(shifts.rows[1]))
        XCTAssertNil(page.expectations)

        let stream = try XCTUnwrap(page.stream)
        XCTAssertEqual(stream.scope, "cricket:15327397:during")
        XCTAssertEqual(stream.cards, [StoryStreamPresentation10868.Card(id: "shifts", name: "Changing expectations")])
        XCTAssertEqual(stream.primary, StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "shifts"))
        XCTAssertNil(stream.companion)
        XCTAssertNil(stream.playback, "a manual stream: no playback")
        XCTAssertNil(stream.dwellFraction)
        XCTAssertEqual(stream.position, "1 of 1")
        XCTAssertEqual(page.stories, [CricketEventPageStory10868(cardID: "shifts", card: .shifts)])

        let model = CricketEventPageModel10868(page)
        XCTAssertEqual(model.storyCard("shifts"), .shifts)
        XCTAssertNil(model.storyCard("chase"), "a card this phase does not mount is never a neighbour")
    }

    /// CONSTRUCTED: `status` set to `completed`. No verdict is served, so every
    /// original's result reads unavailable — never a loss.
    func testAtTheFinalExpectationsAndResultIsTheOneStory() throws {
        let event = try Fixtures.detail(Fixtures.pakistanSriLanka, setting: "status", to: "completed")
        let page = input(event, host: Fixtures.host(Fixtures.capturedAt))
        XCTAssertEqual(page.phase, .completed)
        XCTAssertNil(page.shifts)
        let expectations = try XCTUnwrap(page.expectations)
        XCTAssertTrue(expectations.isCompleted)
        XCTAssertEqual(expectations.eyebrow, "Pregame expectations → result")
        XCTAssertEqual(expectations.completion, CricketOutlookFinalFrame10868(
            outcomeLabel: "Match", outcomeMissing: "Result unavailable", gradeLabel: "Original contract", context: []))
        for row in expectations.rows {
            XCTAssertEqual(expectations.finalOutcome(row), CricketOutlookFinalEntry10868.unavailable("Result unavailable"))
            XCTAssertNil(expectations.finalGrade(row), "the blend is not an original contract")
            XCTAssertNil(expectations.marks(row).comparison, "a settled 0% or 100% is never a mark")
        }
        let stream = try XCTUnwrap(page.stream)
        XCTAssertEqual(stream.cards.map(\.id), ["expectations"])
        XCTAssertEqual(page.stories, [CricketEventPageStory10868(cardID: "expectations", card: .expectations)])
        XCTAssertNil(page.chase, "the resolved chase needs a reported innings and target")
    }

    func testTheAllMarketsEntryNamesTheCount() {
        XCTAssertEqual(Input.copy(originalsCount: 3).allPropsLabel, "All 3 original markets")
        XCTAssertEqual(Input.copy(originalsCount: 1).allPropsLabel, "1 original market")
        XCTAssertNil(Input.copy(originalsCount: 0).allPropsLabel)
        XCTAssertNil(Input.copy(originalsCount: nil).allPropsLabel)
        let copy = Input.copy(originalsCount: nil)
        XCTAssertEqual(copy.storiesLabel, "Match stories")
        XCTAssertEqual(copy.headlineUnavailable, "Match chances unavailable for this moment")
    }

    /// Previous and Next name the other offered card; nothing advances alone.
    func testTheStreamIsManualAndHoldsTheHostsCard() {
        let scope = "cricket:1:during"
        let both = Input.stream(scope: scope, offered: [.shifts, .expectations],
                                state: .init(displayed: .expectations))
        XCTAssertEqual(both.primary?.id, "expectations")
        XCTAssertEqual(both.next?.id, "shifts")
        XCTAssertEqual(both.previous?.id, "shifts")
        XCTAssertEqual(both.position, "2 of 2")
        XCTAssertEqual(both.status, "Use Previous or Next to see each story")
        XCTAssertNil(both.playback)
        let withdrawn = Input.stream(scope: scope, offered: [.shifts], state: .init(displayed: .expectations))
        XCTAssertEqual(withdrawn.primary?.id, "shifts", "a card no longer offered shows the first offered card")
    }
}
