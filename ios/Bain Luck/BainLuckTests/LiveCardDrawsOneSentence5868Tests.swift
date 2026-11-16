import XCTest
import SwiftUI
@testable import Bain_Luck

/// #5868 — a live game card must print its sentence ONCE.
///
/// `EventCardView` renders two server strings: `headline` as a blue pill in the
/// top badge row, `reason` as the grey `reasonBadge` in `footerRow`. On a live
/// card the feed sends the same sentence in both, so the card said it twice
/// about 40pt apart. Photographed on production 2026-09-13 09:01Z,
/// `artifacts-native-142/sports.png`.
///
/// The specimens below are the literal strings from
/// `GET /api/feed?limit=100&include_futures=false` at 09:04Z, all three of that
/// payload's live cards plus the non-live shapes that must keep their pill.
///
/// EVERY TEST HERE ASSERTS IN BOTH DIRECTIONS, and the file deliberately does
/// not stop at the pill: a mutant that deleted the FOOTER badge instead would
/// also make the sentence appear once, and would be the wrong fix (it would
/// take the sentence off every non-live card too). So the footer's own gate is
/// pinned on the same live specimen, and the source scan at the bottom checks
/// the view is wired to both.
final class LiveCardDrawsOneSentence5868Tests: XCTestCase {

    private typealias Pill = EventCardView.EventCardHeadlinePill
    private typealias Footer = EventCardView.EventCardFooter

    // The three live cards on production at 09:04Z, verbatim.
    private let kLeagueSentence = "Sangju Sangmu FC leading after starting at 45%"
    private let npbSentence = "Hokkaido Nippon-Ham Fighters chance rose from 46% to 87%"
    private let kboHeadline = "Odds moved"
    private let kboReason = "Virtually even"

    // MARK: - The defect: the same sentence twice on a live card

    func testLiveCardWhoseHeadlineRepeatsItsReasonDrawsNoPill() {
        XCTAssertFalse(
            Pill.isDrawn(headline: kLeagueSentence, isLive: true),
            "the K League live card drew its reason sentence a second time as a pill")
    }

    func testTheOtherLiveSpecimenAlsoDrawsNoPill() {
        XCTAssertFalse(
            Pill.isDrawn(headline: npbSentence, isLive: true),
            "the NPB live card drew its reason sentence a second time as a pill")
    }

    /// The sentence must still be SAID once — this is the half a "delete the
    /// footer instead" mutant fails. `reason` is content on the live card, so
    /// `footerRow` still draws it.
    func testTheLiveSentenceSurvivesOnceInTheFooter() {
        XCTAssertTrue(
            Footer.hasContent(
                reason: kLeagueSentence, isLive: true,
                awayOpening: nil, homeOpening: 0.45, sport: "soccer_korea_kleague1"),
            "the live sentence was removed from the footer as well — the card now says nothing")
    }

    // MARK: - The rule removes a DIFFERENT live headline too, on purpose

    /// Named rather than left implicit: the third live card carries two
    /// different sentences and still loses its pill, because that is what the
    /// web twin (`FeedCard.tsx:661`) already does. A future reader who thinks
    /// this was an oversight should find it asserted.
    func testALiveHeadlineThatSaysSomethingNewIsAlsoDropped() {
        XCTAssertNotEqual(kboHeadline, kboReason, "the specimen stopped being the distinct-strings case")
        XCTAssertFalse(
            Pill.isDrawn(headline: kboHeadline, isLive: true),
            "iOS kept a live pill web does not draw — the two cards disagree again")
        XCTAssertTrue(
            Footer.hasContent(
                reason: kboReason, isLive: true,
                awayOpening: 0.49, homeOpening: 0.51, sport: "baseball_kbo"),
            "dropping the pill must not cost the card its reason line")
    }

    // MARK: - Ruling 182-A: no top-bar headline/records capsule in any state

    func testFinishedCardDrawsNoTopBarPill182A() {
        XCTAssertFalse(
            Pill.isDrawn(headline: "Recent upset", isLive: false),
            "Ruling 182-A: a capsule is only for live status; non-live top-bar pills are removed")
    }

    func testScheduledCardDrawsNoRecordsBubbleOrTopBarPill182A() {
        XCTAssertFalse(Pill.isDrawn(headline: "TOR 77-80 · BAL 76-81", isLive: false))
        XCTAssertFalse(Pill.isDrawn(headline: "Line moving", isLive: false))
        XCTAssertFalse(
            Footer.hasContent(reason: "TOR 77-80 · BAL 76-81", isLive: false, sport: "baseball_mlb"),
            "Ruling 182-A: team records captions never draw in the footer either")
    }

    func testRealReasonOnScheduledCardSurvivesInFooter182A() {
        XCTAssertFalse(Pill.isDrawn(headline: kLeagueSentence, isLive: false))
        XCTAssertTrue(
            Footer.hasContent(reason: "Starting soon — close matchup", isLive: false, sport: "basketball_nba"),
            "a real reason to care still draws once as a plain grey line in the footer")
    }

    // MARK: - Absence, unchanged by this ship

    func testNoHeadlineDrawsNothing() {
        XCTAssertFalse(Pill.isDrawn(headline: nil, isLive: false))
        XCTAssertFalse(Pill.isDrawn(headline: nil, isLive: true))
    }

    func testEmptyHeadlineDrawsNothing() {
        XCTAssertFalse(Pill.isDrawn(headline: "", isLive: false))
        XCTAssertFalse(Pill.isDrawn(headline: "", isLive: true))
    }

    // MARK: - The source scan: the helper above is wired to the real view

    private func cardSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("EventCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// 🔴 COMMENTS STRIPPED FIRST. Every claim below is about CODE. A scan that
    /// reads the whole file is satisfied by the prose this fix wrote next to the
    /// line it is checking, and then it passes forever for the wrong reason.
    private func cardCode() throws -> String {
        let stripped = try cardSource()
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
        return stripped.split(whereSeparator: { $0 == " " || $0 == "\n" || $0 == "\t" })
            .joined(separator: " ")
    }

    /// Anti-vacuity: if this fails, every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try cardCode()
        XCTAssertGreaterThan(code.count, 5_000, "the scan read something far too short to be EventCardView")
        XCTAssertTrue(code.contains("enum EventCardHeadlinePill"),
                      "the scan did not find the gate's own declaration")
        XCTAssertTrue(code.contains("private var topBar"),
                      "the scan did not find the row the gate is about")
    }

    /// Ruling 182-A: `topBar` draws no `EventCardHeadlinePill` and no
    /// `SignalBarsView` / `EIBadgeView` capsules; only live status keeps a capsule.
    func testTheTopBarDrawsNoHeadlinePill182A() throws {
        let code = try cardCode()
        XCTAssertFalse(
            code.contains("EventCardHeadlinePill.isDrawn("),
            "Ruling 182-A removed the top-bar headline/records capsule from EventCardView")
        XCTAssertFalse(
            code.contains("SignalBarsView("),
            "Ruling 182-A removed signal bars from game cards")
    }

    /// The footer still draws a real non-finished reason once as a plain grey line.
    func testTheFooterStillDrawsTheReasonBadge() throws {
        let code = try cardCode()
        XCTAssertTrue(
            code.contains("reasonBadge(cleaned)"),
            "the sentence lost its one remaining home — the live card now says nothing")
    }
}
