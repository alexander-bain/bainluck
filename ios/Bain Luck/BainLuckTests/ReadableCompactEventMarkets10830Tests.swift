import XCTest
@testable import Bain_Luck

/// #10830, Alex's October 10 report (LV–NE screenshots): the game odds read as
/// a compact ladder, sports words replace "questions", a period is said once,
/// and the protected-touchdown contract keeps its own identity while its
/// verified rule is explained in plain words.
///
/// What the scan rule may NOT do is the other half of every test here: rename
/// an option into another one's words, add a side no venue quoted, or merge a
/// protected contract with an unprotected one.
final class ReadableCompactEventMarkets10830Tests: XCTestCase {

    private func option(_ key: String, _ label: String, _ value: EventQuestionMatrixAdapter.Value = .quoted(0.5))
        -> EventQuestionMatrixAdapter.Option {
        EventQuestionMatrixAdapter.Option(
            selection: QuestionMatrixSelection(scope: .game, questionKey: "q", optionKey: key),
            label: label, side: nil, value: value, observedAt: nil, basis: nil, result: nil)
    }

    private func row(_ label: String, kind: QuestionMatrixKind, options: [EventQuestionMatrixAdapter.Option])
        -> EventQuestionMatrixAdapter.Row {
        EventQuestionMatrixAdapter.Row(
            id: .init(scope: .game, questionKey: label), kind: kind, label: label, quantity: nil, period: nil,
            subject: nil, predicate: nil, lifecycle: nil, options: options, missingOptions: [],
            offersMoreOptions: false, complete: nil, optionCounts: nil, sourceTotals: [])
    }

    // MARK: - Words

    func testTheSectionsUseSportsWords() {
        XCTAssertEqual(EventQuestionMatrixSection10238.title(.game), "Game odds")
        XCTAssertEqual(EventQuestionMatrixSection10238.title(.series), "Series odds")
    }

    // MARK: - The scan line

    /// The screenshot's card: "24+ points" over "Over 23.5 points". One line,
    /// named once, opening that exact served option.
    func testAOneOptionThresholdIsOneLineNamedOnce() {
        let over = option("over", "Over 23.5 points", .quoted(0.96))
        let scan = EventQuestionMatrixSection10238.scan(row("24+ points", kind: .countThreshold, options: [over]))
        XCTAssertNil(scan.heading)
        XCTAssertEqual(scan.lines.map(\.label), ["24+ points"])
        XCTAssertEqual(scan.lines.map(\.option), [over], "the line opens the served option, unchanged")
    }

    /// A one-option NAMED question is not collapsed: "Overtime?" alone over a
    /// served "No" would read as the chance of overtime.
    func testAOneOptionNamedQuestionKeepsItsOptionsWords() {
        let no = option("no", "No", .quoted(0.93))
        let scan = EventQuestionMatrixSection10238.scan(row("Overtime?", kind: .namedOptions, options: [no]))
        XCTAssertEqual(scan.heading, "Overtime?")
        XCTAssertEqual(scan.lines.map(\.label), ["No"])
    }

    /// Two served sides stay two lines with their own names and values; a
    /// one-sided spread is not given its other side.
    func testEveryServedOptionIsALineAndNoneIsAdded() {
        let sides = [option("ne", "New England -3.5", .quoted(0.55)), option("lv", "Las Vegas +3.5", .quoted(0.44))]
        let two = EventQuestionMatrixSection10238.scan(row("Spread 3.5", kind: .signedHandicap, options: sides))
        XCTAssertEqual(two.heading, "Spread 3.5")
        XCTAssertEqual(two.lines.map(\.label), ["New England -3.5", "Las Vegas +3.5"])
        XCTAssertEqual(two.lines.map(\.option.value), [.quoted(0.55), .quoted(0.44)], "70/29-style sums stay as served")

        let one = EventQuestionMatrixSection10238.scan(row("Spread 3.5", kind: .signedHandicap, options: [sides[0]]))
        XCTAssertEqual(one.lines.count, 1)

        // Over and Under of one threshold are two served options: both kept.
        let ou = EventQuestionMatrixSection10238.scan(row("24+ points", kind: .countThreshold, options: [
            option("over", "Over 23.5 points"), option("under", "Under 23.5 points"),
        ]))
        XCTAssertEqual(ou.heading, "24+ points")
        XCTAssertEqual(ou.lines.map(\.label), ["Over 23.5 points", "Under 23.5 points"])
    }

    /// Unpriced and decided options keep their own value on the line.
    func testUnpricedAndSettledValuesTravelUnchanged() {
        for value in [EventQuestionMatrixAdapter.Value.unavailable, .won, .lost] {
            let scan = EventQuestionMatrixSection10238.scan(
                row("27+ points", kind: .countThreshold, options: [option("over", "Over 26.5 points", value)]))
            XCTAssertEqual(scan.lines.map(\.option.value), [value])
        }
    }

    /// A question with no options keeps its heading so its "no quoted options"
    /// note has something to sit under.
    func testAQuestionWithNoOptionsKeepsItsHeading() {
        let scan = EventQuestionMatrixSection10238.scan(row("30+ points", kind: .countThreshold, options: []))
        XCTAssertEqual(scan.heading, "30+ points")
        XCTAssertTrue(scan.lines.isEmpty)
    }

    // MARK: - A heading said once

    func testAPeriodHeadingIsDrawnOncePerRun() {
        let headings = ["Game", "Game", "1st half", "1st half", "", "Game"]
        let drawn = headings.indices.map { MarketBrowserLogic.headingText(headings, at: $0) }
        XCTAssertEqual(drawn, ["Game", nil, "1st half", nil, nil, "Game"])
        XCTAssertNil(MarketBrowserLogic.headingText([], at: 0))
        XCTAssertNil(MarketBrowserLogic.headingText(["Game"], at: 3))
    }

    // MARK: - Protected touchdowns

    func testOnlyTheVerifiedProtectedContractGetsTheRule() {
        let verified = PlayerPropsFamily.isVerifiedProtectedTouchdowns
        XCTAssertTrue(verified("Touchdowns (Protected)", "americanfootball_nfl", ["kalshi"]))
        XCTAssertTrue(verified("2+ Touchdowns (Protected)", "americanfootball_nfl", ["kalshi"]))
        // Not verified: another sport, another venue, a mix, another stat, plain TDs.
        XCTAssertFalse(verified("Touchdowns (Protected)", "americanfootball_ncaaf", ["kalshi"]))
        XCTAssertFalse(verified("Touchdowns (Protected)", nil, ["kalshi"]))
        XCTAssertFalse(verified("Touchdowns (Protected)", "americanfootball_nfl", ["polymarket"]))
        XCTAssertFalse(verified("Touchdowns (Protected)", "americanfootball_nfl", ["kalshi", "polymarket"]))
        XCTAssertFalse(verified("Touchdowns (Protected)", "americanfootball_nfl", []))
        XCTAssertFalse(verified("Receiving Yards (Protected)", "americanfootball_nfl", ["kalshi"]))
        XCTAssertFalse(verified("Touchdowns", "americanfootball_nfl", ["kalshi"]))
    }

    /// The venue's rule exempts team defense/special-teams picks from the
    /// player exception, so a team subject never gets the player rule.
    func testATeamSubjectNeverGetsThePlayerRule() {
        let teams = ["Las Vegas Raiders", "New England Patriots"]
        XCTAssertFalse(PlayerPropsFamily.isTeamSubject("Drake Maye", teams: teams))
        XCTAssertFalse(PlayerPropsFamily.isTeamSubject("Rhamondre Stevenson", teams: teams))
        XCTAssertFalse(PlayerPropsFamily.isTeamSubject("", teams: teams))
        XCTAssertTrue(PlayerPropsFamily.isTeamSubject("New England Patriots", teams: teams))
        XCTAssertTrue(PlayerPropsFamily.isTeamSubject("Patriots", teams: teams))
        XCTAssertTrue(PlayerPropsFamily.isTeamSubject("las vegas", teams: teams))
        XCTAssertTrue(PlayerPropsFamily.isTeamSubject("New England D/ST", teams: teams))
        XCTAssertTrue(PlayerPropsFamily.isTeamSubject("Raiders Defense/Special Teams", teams: teams))
        // A fragment of a word is not the team.
        XCTAssertFalse(PlayerPropsFamily.isTeamSubject("Pat", teams: teams))
    }

    /// The protected contract stays its own family: renaming it must not land
    /// it on the plain touchdowns pill, where the two would read as one stat.
    func testTheProtectedFamilyNeverSharesAPillWithPlainTouchdowns() {
        let plain = PlayerPropsFamily.family(statLabel: "Touchdowns", isPriced: true)
        XCTAssertNotEqual(PlayerPropsFamily.protectedTouchdownFamily, plain)
        XCTAssertNotEqual(PlayerPropsFamily.protectedTouchdownFamily, PlayerPropsFamily.unpricedFamily)
        XCTAssertEqual(
            Set(PlayerPropsFamily.orderedFamilies([PlayerPropsFamily.protectedTouchdownFamily, plain])).count, 2)
    }

    /// The explanation states what the venue's rule says and nothing it does
    /// not: no refund, no injury requirement.
    func testTheRuleCopySaysWhatTheVenueSaid() {
        let copy = PlayerPropsFamily.participationRuleLines.joined(separator: " ").lowercased()
        XCTAssertTrue(copy.contains("first half"))
        XCTAssertTrue(copy.contains("before kickoff"))
        XCTAssertTrue(copy.contains("already reached the target"))
        XCTAssertTrue(copy.contains("after halftime"))
        XCTAssertTrue(copy.contains("no injury"))
        XCTAssertTrue(copy.contains("passing touchdowns"))
        XCTAssertTrue(copy.contains("team defense and special-teams picks settle on actual touchdowns"))
        XCTAssertFalse(copy.contains("refund"))
        XCTAssertFalse(copy.contains("void"))
        XCTAssertEqual(PlayerPropsFamily.participationRuleTermsURL.host, "assets.kalshi.com")
    }
}
