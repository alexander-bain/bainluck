import XCTest
@testable import Bain_Luck

/// #12308 — a Bain Luck card in Messages: what it says now and as sent, which
/// item its link names, and what it shows after each read. The extension's own
/// views are photographed on the issue; these are the rules under them, which
/// live in the app's sources so this target can reach them.
final class MessageCard12308Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000) // 2026-10-14T17:46:40Z
    private let utc = TimeZone(identifier: "UTC")!

    private func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }

    private func game(_ id: Int) -> SavedWidgetSubject10875 { .init(kind: .game, id: id) }
    private func market(_ id: Int) -> SavedWidgetSubject10875 { .init(kind: .market, id: id) }

    /// Bills (away) at Vikings (home), the public `/api/events/{id}` shape.
    private func gameJSON(id: Int = 15327330, status: String = "live", sport: String = "americanfootball_nfl",
                          away: String = "Buffalo Bills", home: String = "Minnesota Vikings",
                          awayChance: Double? = 0.62, homeChance: Double = 0.38,
                          scores: (away: Int, home: Int)? = (24, 21), extra: String = "") -> Data {
        let awayField = awayChance.map { String($0) } ?? "null"
        let scoreFields = scores.map { "\"home_score\": \($0.home), \"away_score\": \($0.away)," } ?? ""
        return Data("""
        {"id": \(id), "sport": "\(sport)", "home_team": "\(home)", "away_team": "\(away)",
         "status": "\(status)", "commence_time": "\(iso(t0.addingTimeInterval(-3600)))", \(scoreFields)
         "current_odds": {"home_probability": \(homeChance), "away_probability": \(awayField)},
         "hero_probability_source": "blend", "hero_probability_observed_at": "\(iso(t0.addingTimeInterval(-60)))"\(extra)}
        """.utf8)
    }

    private func marketJSON(id: Int = 7, status: String = "open", legs: String? = nil) -> Data {
        let outcomes = legs ?? """
        {"id": 1, "name": "Yes", "probability": 0.61, "last_updated": "\(iso(t0.addingTimeInterval(-60)))"},
        {"id": 2, "name": "No", "probability": 0.39, "last_updated": "\(iso(t0.addingTimeInterval(-60)))"}
        """
        return Data("""
        {"id": \(id), "name": "Fed cuts rates in December", "status": "\(status)", "outcomes": [\(outcomes)]}
        """.utf8)
    }

    /// The text as read: the platform's date format puts a no-break space
    /// before "PM" (as the widget's own start time does).
    private func visible(_ text: String) -> String {
        text.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    private func card(_ data: Data, as kind: SavedWidgetSubject10875.Kind) throws -> MessageCard12308 {
        let payload = try SavedWidgetDetailPayload10875.decode(data, as: kind)
        return try XCTUnwrap(MessageCardRules12308.card(payload, now: t0, timeZone: utc), "no card for a decodable detail")
    }

    // MARK: - Games

    func testALiveGameNamesBothSidesEachBesideItsOwnNumber() throws {
        let c = try card(gameJSON(), as: .game)
        XCTAssertEqual(c.line, "Bills 62% · Vikings 38%", "a number sat beside the other side's name (#4306)")
        XCTAssertEqual(c.title, "Buffalo Bills vs Minnesota Vikings")
        XCTAssertEqual(c.status, "Live · 24–21 · Current win chance")
        XCTAssertEqual(c.summary, "Buffalo Bills vs Minnesota Vikings: Bills 62% · Vikings 38%",
                       "the thread list and notifications must carry the same sentence as the card")
        XCTAssertEqual(c.phase, .current)
        XCTAssertTrue(c.spoken.contains("Buffalo Bills 62%") && c.spoken.contains("Minnesota Vikings 38%"),
                      "VoiceOver did not read both sides with their own numbers: \(c.spoken)")

        let flipped = try card(gameJSON(awayChance: 0.38, homeChance: 0.62), as: .game)
        XCTAssertEqual(flipped.line, "Bills 38% · Vikings 62%", "the names do not follow their own rows")
    }

    func testADrawPricedMatchLeavesTheWithheldSideOutRatherThanFillingItIn() throws {
        let c = try card(gameJSON(sport: "soccer_epl", away: "Chelsea", home: "Arsenal",
                                  awayChance: 0.55, homeChance: 0.45), as: .game)
        XCTAssertEqual(c.line, "Arsenal 45%", "the away side of a draw-priced match was printed (1 − home, #5271)")
        XCTAssertFalse(c.line.contains("Chelsea"), "the withheld side was named beside a number")
    }

    func testAFinishedGameNamesItsWinnerAndNoPrice() throws {
        let c = try card(gameJSON(status: "completed", extra: ", \"hero_settled_result\": \"away\""), as: .game)
        XCTAssertEqual(c.line, "Bills won")
        XCTAssertEqual(c.status, "Final · 24–21", "the final score is away–home, as every card prints it")
        XCTAssertFalse(c.line.contains("%") || c.status.contains("%"), "a finished game printed a price")
        XCTAssertEqual(c.phase, .result)
    }

    func testALevelFinalIsADrawAndAScorelessFinalNamesNoWinner() throws {
        let level = try card(gameJSON(status: "completed", sport: "soccer_epl", away: "Chelsea", home: "Arsenal",
                                      scores: (1, 1)), as: .game)
        XCTAssertEqual(level.line, "Draw")
        let scoreless = try card(gameJSON(status: "completed", scores: nil), as: .game)
        XCTAssertEqual(scoreless.line, "No result recorded", "a final with no score invented a winner or a draw")
    }

    func testNoPriceSaysSoInsteadOfANumber() throws {
        let body = String(decoding: gameJSON(), as: UTF8.self)
            .replacingOccurrences(of: "\"current_odds\": {\"home_probability\": 0.38, \"away_probability\": 0.62},", with: "")
        let c = try card(Data(body.utf8), as: .game)
        XCTAssertEqual(c.line, MessageCardRules12308.noNumber)
        XCTAssertFalse(c.line.contains("%"), "a missing price was printed")
    }

    // MARK: - Markets

    func testAMarketCardNamesItsHeroOutcomeAndItsResult() throws {
        let open = try card(marketJSON(), as: .market)
        XCTAssertEqual(open.line, "Yes 61%")
        XCTAssertEqual(open.title, "Fed cuts rates in December")
        XCTAssertEqual(open.status, "Open")
        XCTAssertEqual(open.url.absoluteString, "https://bainluck.com/futures/7")

        let settled = try card(marketJSON(status: "resolved", legs: """
        {"id": 1, "name": "Yes", "probability": 0.99, "is_winner": true, "resolution_source": "api_settlement"},
        {"id": 2, "name": "No", "probability": 0.01, "is_winner": false, "resolution_source": "api_settlement"}
        """), as: .market)
        XCTAssertEqual(settled.line, "Yes won")
        XCTAssertFalse(settled.line.contains("%"), "a settled market kept printing its last price")
    }

    // MARK: - The link

    func testTheLinkIsTheOneShareSendsAndReadsBack() throws {
        let c = try card(gameJSON(), as: .game)
        XCTAssertEqual(c.url.absoluteString, eventShareURL(15327330), "the card's link is not the one Share sends")
        XCTAssertEqual(MessageCardRules12308.subject(from: c.url), game(15327330))
        XCTAssertEqual(MessageCardRules12308.url(for: market(7))?.absoluteString, futuresShareURL(7))

        let names: [(String, SavedWidgetSubject10875?)] = [
            ("https://www.bainluck.com/events/42", game(42)),
            ("https://bainluck.com/futures/7", market(7)),
            ("bainluck://events/42", game(42)),
            ("bainluck://futures/7", market(7)),
            (eventShareURL(42, style: .nativeCard), game(42)),
            ("https://bainluck.com.example.com/events/42", nil),
            ("https://example.com/events/42", nil),
            ("https://bainluck.com/events/abc", nil),
            ("https://bainluck.com/events/0", nil),
            ("https://bainluck.com/events/-3", nil),
            ("https://bainluck.com/events/42/props", nil),
            ("https://bainluck.com/teams/42", nil),
            ("mailto:someone@bainluck.com", nil),
        ]
        for (text, expected) in names {
            let url = try XCTUnwrap(URL(string: text))
            XCTAssertEqual(MessageCardRules12308.subject(from: url), expected, "\(text) was read as the wrong item")
        }
    }

    // MARK: - Which screen

    func testATappedCardOpensItsItemAndAnythingElseOpensThePicker() throws {
        let link = URL(string: eventShareURL(42))
        XCTAssertEqual(MessageScreen12308.screen(expanded: true, selected: link), .card(game(42)))
        XCTAssertEqual(MessageScreen12308.screen(expanded: false, selected: link), .picker,
                       "the app drawer must offer the saved items, not the last card tapped")
        XCTAssertEqual(MessageScreen12308.screen(expanded: true, selected: nil), .picker)
        XCTAssertEqual(MessageScreen12308.screen(expanded: true, selected: URL(string: "https://example.com/events/42")),
                       .picker, "a link that is not Bain Luck's opened a card")
    }

    // MARK: - The card as sent

    func testASentCardDatesItsPriceAndNeverCallsItCurrent() throws {
        let c = try card(gameJSON(), as: .game)
        XCTAssertEqual(c.status, "Live · 24–21 · Current win chance", "the picker and the opened card read the price now")
        XCTAssertEqual(visible(c.sentStatus), "Live · 24–21 · Win chance as of Oct 14 at 5:45 PM GMT",
                       "a picture in a thread is never redrawn, so it must date its price by the price's own clock")
        XCTAssertFalse(c.sentStatus.contains("Current"), "a sent picture called its price current")
        XCTAssertEqual(visible(c.sentSpoken),
                       "Buffalo Bills vs Minnesota Vikings: Bills 62%, Vikings 38%. Live. 24–21. Win chance as of Oct 14 at 5:45 PM GMT.")
        XCTAssertFalse(c.sentSpoken.contains("Current"), "VoiceOver read a sent price as current")

        let market = try card(marketJSON(), as: .market)
        XCTAssertEqual(visible(market.sentStatus), "Open · Chance as of Oct 14 at 5:45 PM GMT")
    }

    func testASentCardNamesTheZoneOfEveryTimeOnIt() throws {
        let start = t0.addingTimeInterval(3 * 3600)
        let body = String(decoding: gameJSON(status: "scheduled", scores: nil), as: UTF8.self)
            .replacingOccurrences(of: iso(t0.addingTimeInterval(-3600)), with: iso(start))
        let payload = try SavedWidgetDetailPayload10875.decode(Data(body.utf8), as: .game)
        let eastern = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
        let c = try XCTUnwrap(MessageCardRules12308.card(payload, now: t0, timeZone: eastern))
        XCTAssertEqual(visible(c.sentStatus), "Starts Oct 14 at 4:46 PM EDT · Win chance as of Oct 14 at 1:45 PM EDT",
                       "a friend in another zone would read the sender's clock as their own")
        XCTAssertTrue(c.status.hasPrefix("Starts "), "the picker keeps the reader's own start time")
        XCTAssertFalse(c.status.contains("EDT"), "the reader's own card does not need a zone")
    }

    func testASentResultNeedsNoDateAndAnOpeningLineOrAStalePriceSaysWhatItIs() throws {
        let final = try card(gameJSON(status: "completed", extra: ", \"hero_settled_result\": \"away\""), as: .game)
        XCTAssertEqual(final.sentStatus, "Final · 24–21", "a final is permanent; dating it adds nothing")

        let opening = try card(gameJSON(status: "scheduled",
                                        extra: ", \"hero_probability\": 0.5996, \"hero_probability_away\": 0.4004")
            .replacingBlendWithOpening(), as: .game)
        XCTAssertTrue(opening.sentStatus.hasSuffix(" · Opening line"), "an opening line lost its name: \(opening.sentStatus)")
        XCTAssertFalse(opening.sentStatus.contains(" as of "), "an opening line was dated as an observation")

        let stale = String(decoding: gameJSON(), as: UTF8.self)
            .replacingOccurrences(of: iso(t0.addingTimeInterval(-60)), with: iso(t0.addingTimeInterval(-31 * 60)))
        let old = try card(Data(stale.utf8), as: .game)
        XCTAssertEqual(old.phase, .lastRecorded)
        XCTAssertEqual(visible(old.sentStatus), "Live · 24–21 · Last recorded win chance, Oct 14 at 5:15 PM GMT")
    }

    // MARK: - After a read

    func testAReadKeepsADrawnCardRefusesAnotherMarketsAnswerAndSaysGone() throws {
        let drawn = MessageCardReading12308.after(.success(gameJSON()), for: game(15327330), previous: nil, now: t0)
        guard case .card(let c) = drawn else { return XCTFail("a good answer drew no card: \(drawn)") }
        XCTAssertEqual(c.line, "Bills 62% · Vikings 38%")

        XCTAssertEqual(MessageCardReading12308.after(.failure(.failed), for: game(15327330), previous: drawn, now: t0),
                       drawn, "a failed read blanked a card already drawn")
        XCTAssertEqual(MessageCardReading12308.after(.failure(.failed), for: game(15327330), previous: .loading, now: t0),
                       .unreachable, "with nothing drawn, a failed read must say so rather than spin forever")
        XCTAssertEqual(MessageCardReading12308.after(.success(Data("{}".utf8)), for: game(15327330), previous: drawn, now: t0),
                       drawn, "an unreadable answer replaced a card already drawn")
        XCTAssertEqual(MessageCardReading12308.after(.failure(.notFound), for: game(15327330), previous: drawn, now: t0),
                       .gone, "an item that no longer exists kept showing its old number")

        XCTAssertEqual(MessageCardReading12308.after(.success(marketJSON(id: 999)), for: market(7), previous: nil, now: t0),
                       .unreachable, "another market's answer was drawn under this card; the market page refuses it too")

        // A proven duplicate game is served as its canonical row, which the
        // event page adopts; the card does too, and links the canonical row.
        let adopted = MessageCardReading12308.after(.success(gameJSON(id: 15312656)), for: game(15308290),
                                                     previous: nil, now: t0)
        guard case .card(let canonical) = adopted else { return XCTFail("a canonical row was refused: \(adopted)") }
        XCTAssertEqual(canonical.url.absoluteString, eventShareURL(15312656))
    }

    // MARK: - Wiring (read from source; the extension is built and photographed on the issue)

    private func source(_ path: String) throws -> String {
        try String(contentsOf: ProjectTree.root().appendingPathComponent(path), encoding: .utf8)
    }

    func testTheExtensionIsEmbeddedForIOSOnlyAndReadsTheSavedItemsAppGroup() throws {
        let pbxproj = try source("Bain Luck.xcodeproj/project.pbxproj")
        XCTAssertTrue(pbxproj.contains("productType = \"com.apple.product-type.app-extension.messages\";"),
                      "there is no Messages extension target")
        let embed = try XCTUnwrap(pbxproj.components(separatedBy: "\n")
            .first { $0.contains("BainLuckMessages.appex in Embed Foundation Extensions */ = {") },
                                  "the app does not embed the Messages extension")
        XCTAssertTrue(embed.contains("platformFilter = ios;"), "the Messages extension would be embedded in the Mac app")

        let start = try XCTUnwrap(pbxproj.range(of: "Exceptions for \"Bain Luck\" folder in \"BainLuckMessages\" target"))
        let end = try XCTUnwrap(pbxproj.range(of: ");", range: start.upperBound..<pbxproj.endIndex))
        let members = String(pbxproj[start.upperBound..<end.lowerBound])
        for file in ["Messages12308/MessageCard12308.swift", "Utilities/ShareURLs.swift", "Utilities/TeamShortName.swift",
                     "Widgets10875/SavedWidgetReading10875.swift", "Widgets10875/SavedWidgetTimeline10875.swift"] {
            XCTAssertTrue(members.contains(file + ","), "\(file) is not a member of BainLuckMessages")
        }
        XCTAssertFalse(members.contains("SavedWidgetPublisher10875"), "the app-only publisher leaked into the extension")

        let info = try XCTUnwrap(PropertyListSerialization.propertyList(
            from: Data(try source("BainLuckMessages/Info.plist").utf8), format: nil) as? [String: Any])
        let ext = try XCTUnwrap(info["NSExtension"] as? [String: Any])
        XCTAssertEqual(ext["NSExtensionPointIdentifier"] as? String, "com.apple.message-payload-provider")
        XCTAssertEqual(ext["NSExtensionPrincipalClass"] as? String, "$(PRODUCT_MODULE_NAME).MessagesViewController")

        let entitlements = try XCTUnwrap(PropertyListSerialization.propertyList(
            from: Data(try source("BainLuckMessages/BainLuckMessages.entitlements").utf8), format: nil) as? [String: Any])
        XCTAssertEqual(entitlements["com.apple.security.application-groups"] as? [String], [SavedWidgetBridge10875.appGroup],
                       "the extension cannot read the saved items the widget reads")
    }

    func testTheExtensionStagesAMessageAndNeverSendsOne() throws {
        let controller = try source("BainLuckMessages/MessagesViewController.swift")
        XCTAssertTrue(controller.contains("conversation.insert("), "the card no longer goes into the message field")
        XCTAssertFalse(controller.contains(".send("), "the extension sends a message the reader did not send")
    }
}

private extension Data {
    func replacingBlendWithOpening() -> Data {
        Data(String(decoding: self, as: UTF8.self)
            .replacingOccurrences(of: "\"hero_probability_source\": \"blend\"", with: "\"hero_probability_source\": \"opening\"").utf8)
    }
}
