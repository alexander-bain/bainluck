import XCTest
@testable import Bain_Luck

/// #10875 R1 — on the Lock Screen a verdict longer than Won / Lost / Draw is
/// never one truncated line. Native walked the circular widget printing
/// "Under / Result unk…" and the rectangular one "Under   Result unk…" for
/// *Marchi vs. Lokoli: Match O/U 21.5* (#698's settled coin flip). Lane1 found
/// the same squeeze on a venue-settled game, whose verdict is the venue's own
/// words: a team name ("Seattle Se…") or "No final score has been recorded".
///
/// Every reading here comes through the real rules, one per branch that
/// produces a headline verdict or figure. The views only call
/// `SavedLockScreenFit10875`; the last test holds them to that.
@MainActor
final class SavedItemWidgetLockScreen10875Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000) // 2026-10-17T20:26:40Z

    private func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }

    private func game(status: String = "live", sport: String = "icehockey_nhl", homeScore: Int? = 2,
                      awayScore: Int? = 1, extra: String = "", side: SavedWidgetGameSide10875? = nil) throws -> SavedWidgetReading10875 {
        let json = """
        {"id": 15327330, "sport": "\(sport)", "home_team": "Colorado Avalanche", "away_team": "Toronto Maple Leafs",
         "status": "\(status)", "commence_time": "\(iso(t0.addingTimeInterval(-3600)))",
         "home_score": \(homeScore.map(String.init) ?? "null"), "away_score": \(awayScore.map(String.init) ?? "null"),
         "home_team_data": {"abbreviation": "COL"}, "away_team_data": {"abbreviation": "TOR"},
         "current_odds": {"home_probability": 0.62, "away_probability": 0.38},
         "hero_probability_source": "blend", "hero_probability_observed_at": "\(iso(t0.addingTimeInterval(-60)))"\(extra)}
        """
        let e = try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data(json.utf8))
        return SavedWidgetReadingRules10875.game(e, side: side, now: t0)
    }

    private func venueSettled(_ result: String) throws -> SavedWidgetReading10875 {
        try game(status: "suspended", extra: ", \"venue_settled\": true, \"venue_settled_result\": \"\(result)\"")
    }

    private func market(_ legs: String, status: String = "open") throws -> SavedWidgetMarketDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: Data("""
        {"id": 7, "name": "Winner", "status": "\(status)", "outcomes": [\(legs)]}
        """.utf8))
    }

    /// The banked `/futures/62134744` body Native walked (the frozen #698 fixture).
    private func marchiUnder() throws -> SavedWidgetReading10875 {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/settledDisplay698.0cd6a6c695.json")
        let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let spec = (fixture["specimens"] as! [String: Any])["62134744"] as! [String: Any]
        let body = try JSONSerialization.data(withJSONObject: spec["served"] as! [String: Any])
        let m = try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: body)
        return SavedWidgetReadingRules10875.market(m, outcomeID: 234738382, now: t0)
    }

    /// Every verdict- or figure-producing branch, through the real rules.
    private func everyBranch() throws -> [(String, SavedWidgetReading10875)] {
        let stamp = iso(t0.addingTimeInterval(-60))
        return [
            ("noResult market (Result unknown)", try marchiUnder()),
            ("venue-settled, served winner", try venueSettled("Toronto Maple Leafs wins")),
            ("venue-settled, team name", try venueSettled("Toronto Maple Leafs")),
            ("venue-settled, long words", try venueSettled("Maple Leafs win in overtime")),
            ("venue-settled, fallback", try venueSettled("")),
            ("venue-settled, short score", try venueSettled("1-2")),
            ("final, won", try game(status: "completed", extra: ", \"hero_settled_result\": \"away\"", side: .away)),
            ("final, lost", try game(status: "completed", extra: ", \"hero_settled_result\": \"away\"", side: .home)),
            ("final, draw", try game(status: "completed", sport: "soccer_epl", homeScore: 1, side: .home)),
            ("final, no result", try game(status: "completed", homeScore: nil, awayScore: nil)),
            ("game figure", try game()),
            ("market figure", SavedWidgetReadingRules10875.market(try market("""
                {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(stamp)"},
                {"id": 2, "name": "B", "probability": 0.4, "last_updated": "\(stamp)"}
                """), outcomeID: 2, now: t0)),
            ("market won", SavedWidgetReadingRules10875.market(try market("""
                {"id": 1, "name": "A", "probability": 1.0, "is_winner": true, "resolution_source": "api_settlement"},
                {"id": 2, "name": "B", "probability": 0.0, "is_winner": false, "resolution_source": "api_settlement"}
                """, status: "resolved"), outcomeID: 1, now: t0)),
            ("outcome no longer listed", SavedWidgetReadingRules10875.market(try market("""
                {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(stamp)"}
                """), outcomeID: 99, now: t0)),
        ]
    }

    // MARK: - The ring

    func testTheRingNeverHoldsMoreThanSevenLetters() throws {
        for (name, r) in try everyBranch() {
            let value = SavedLockScreenFit10875.ringValue(r)
            XCTAssertLessThanOrEqual(value.count, SavedLockScreenFit10875.ringLimit,
                                     "\(name): the ring was given \"\(value)\", which truncates")
        }
    }

    func testTheRingSaysUnknownForASettledCoinFlip() throws {
        let r = try marchiUnder()
        XCTAssertEqual(r.headline?.verdict, "Result unknown", "the specimen is no longer the #698 coin flip")
        XCTAssertEqual(r.headline?.shortLabel, "Under")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(r), "Unknown",
                       "the ring did not stand a word for \"Result unknown\" (mutant: headline.verdict)")
        XCTAssertNotEqual(SavedLockScreenFit10875.ringValue(r), "Lost")
    }

    func testTheRingNamesAVenueWinnerByItsShortName() throws {
        // The served shape: venue_settlement's WINNER_SENTENCE, "{participant} wins".
        let r = try venueSettled("Toronto Maple Leafs wins")
        XCTAssertEqual(r.headline?.shortLabel, "Settled")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(r), "TOR",
                       "the served winner sentence was not shortened to its team (mutant: drop the \" wins\" arm)")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try venueSettled("Toronto Maple Leafs")), "TOR",
                       "the bare team name was not shortened to its team")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try venueSettled("")), "—",
                       "the venue fallback sentence was squeezed into the ring")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try venueSettled("Maple Leafs win in overtime")), "—")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try venueSettled("1-2")), "1-2", "a score that fits was hidden")
    }

    func testTheRingKeepsWhatFitsToday() throws {
        let won = try game(status: "completed", extra: ", \"hero_settled_result\": \"away\"", side: .away)
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(won), "Won")
        let lost = try game(status: "completed", extra: ", \"hero_settled_result\": \"away\"", side: .home)
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(lost), "Lost")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try game(status: "completed", sport: "soccer_epl",
                                                                  homeScore: 1, side: .home)), "Draw")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try game()), "62%")
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(try game(status: "completed", homeScore: nil, awayScore: nil)),
                       "Final")
        let gone = try everyBranch().first { $0.0 == "outcome no longer listed" }!.1
        XCTAssertEqual(SavedLockScreenFit10875.ringValue(gone), "—")
    }

    // MARK: - The rectangle

    func testALongVerdictGetsItsOwnLineAndTheNameMovesBelow() throws {
        let r = try marchiUnder()
        XCTAssertEqual(SavedLockScreenFit10875.rectangleOwnLineVerdict(r), "Result unknown",
                       "\"Result unknown\" shared a line with the outcome name")
        XCTAssertEqual(SavedLockScreenFit10875.rectangleFooter(r, caption: "Last recorded 50% · Sep 24, 2:57 AM"),
                       "Under · Last recorded 50% · Sep 24, 2:57 AM", "the outcome the verdict belongs to was dropped")
        for words in ["Toronto Maple Leafs wins", "Toronto Maple Leafs", "Maple Leafs win in overtime", "", "1-2"] {
            let venue = try venueSettled(words)
            XCTAssertNotNil(SavedLockScreenFit10875.rectangleOwnLineVerdict(venue),
                            "the venue's \"\(words)\" shared a line with its label")
            XCTAssertEqual(SavedLockScreenFit10875.rectangleFooter(venue, caption: venue.status), "Settled",
                           "the footer said Settled twice")
        }
    }

    func testEveryVerdictOutsideTheShortSetIsOnItsOwnLine() throws {
        for (name, r) in try everyBranch() {
            guard r.phase != .unavailable, let verdict = r.headline?.verdict else { continue }
            let own = SavedLockScreenFit10875.rectangleOwnLineVerdict(r)
            if SavedLockScreenFit10875.shortVerdicts.contains(verdict) {
                XCTAssertNil(own, "\(name): \"\(verdict)\" left its line beside the name")
            } else {
                XCTAssertEqual(own, verdict, "\(name): \"\(verdict)\" shared one truncating line")
            }
        }
    }

    func testWonLostDrawAndFiguresKeepTheirLayout() throws {
        for (name, r) in try everyBranch() where r.headline?.verdict == nil
            || SavedLockScreenFit10875.shortVerdicts.contains(r.headline?.verdict ?? "") {
            XCTAssertNil(SavedLockScreenFit10875.rectangleOwnLineVerdict(r), "\(name) changed layout")
        }
        let gone = try everyBranch().first { $0.0 == "outcome no longer listed" }!.1
        XCTAssertNil(SavedLockScreenFit10875.rectangleOwnLineVerdict(gone),
                     "the vanished-outcome notice left its own branch")
    }

    // MARK: - The views use these rules

    func testTheLockScreenViewsDrawThroughTheseRules() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget/SavedItemWidget10875.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("Text(SavedLockScreenFit10875.ringValue(reading))"),
                      "the circular widget no longer draws its value through ringValue")
        XCTAssertTrue(source.contains("SavedLockScreenFit10875.rectangleOwnLineVerdict(reading)"),
                      "the rectangular widget no longer asks whether the verdict needs its own line")
    }

    /// R2 — Native re-walked ae42c81d36 at real size: the venue-settled
    /// rectangle drew "SBW vs ANH / Akita Northern Happinets… / Settled",
    /// the verdict one 12.7 pt line. Subject + a two-line verdict + footer is
    /// four lines in a three-line rectangle, so the verdict lost. The view now
    /// tries that layout and, when it does not fit, moves the footer onto the
    /// subject line so the verdict keeps both lines.
    func testATwoLineVerdictTakesTheFootersLineNotItsOwnSecondLine() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget/SavedItemWidget10875.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        guard let start = source.range(of: "struct SavedRectangular10875: View {"),
              let end = source.range(of: "struct SavedCircular10875: View {", range: start.upperBound..<source.endIndex) else {
            return XCTFail("the rectangular widget view moved")
        }
        let rectangle = String(source[start.upperBound..<end.lowerBound])
        guard let fits = rectangle.range(of: "ViewThatFits(in: .vertical) {") else {
            return XCTFail("the own-line verdict is drawn in one layout, which cuts a two-line verdict to one")
        }
        let afterFits = String(rectangle[fits.upperBound...])
        let three = afterFits.range(of: "subjectLine\n                    ownLine(verdict)\n                    footerLine")
        let folded = afterFits.range(of: "Text(\" · \\(footer)\")")
        XCTAssertNotNil(three, "the first choice is no longer subject / verdict / footer (\"Result unknown\" fits it)")
        XCTAssertNotNil(folded, "the fallback no longer carries the footer on the subject line")
        if let three, let folded {
            XCTAssertLessThan(three.lowerBound, folded.lowerBound,
                              "the folded layout is tried first, so a verdict that fits one line loses its footer line")
        }
        XCTAssertTrue(rectangle.contains(".lineLimit(2)"), "the own-line verdict can no longer wrap to a second line")

        // R2a — offline, the footer is "Offline · Oct 15, 3:42 PM", about the
        // rectangle's whole width. The subject must win the folded line, or a
        // settled game shows its clock and not which game it is.
        guard let hstack = afterFits.range(of: "HStack(spacing: 0) {"),
              let close = afterFits.range(of: "\n                    }", range: hstack.upperBound..<afterFits.endIndex) else {
            return XCTFail("the folded subject line is no longer an HStack")
        }
        let foldedLine = String(afterFits[hstack.upperBound..<close.lowerBound])
        XCTAssertTrue(foldedLine.contains("subjectLine\n                            .layoutPriority(1)"),
                      "the subject no longer outranks the footer, so an offline footer pushes the game off its line")
        guard let footerText = foldedLine.range(of: "Text(\" · \\(footer)\")") else {
            return XCTFail("the folded line no longer carries the footer")
        }
        XCTAssertFalse(foldedLine[footerText.upperBound...].contains("layoutPriority"),
                       "the footer carries a layout priority, so it takes its width before the subject")
    }

    /// R3 — Native's offline Lock Screen read on 9be33a5b6a: a settled game
    /// has no observed clock, so its footer read "Offline · last update" (cut
    /// to "Offline…"), a caption that names a time it does not have. With no
    /// clock the caption is just "Offline"; with one it keeps the clock.
    func testAnOfflineReadingWithNoClockSaysOnlyOffline() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget/SavedItemWidget10875.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        guard let start = source.range(of: "static func caption("),
              let end = source.range(of: "switch reading.phase", range: start.upperBound..<source.endIndex) else {
            return XCTFail("the caption function moved")
        }
        let offlineArm = String(source[start.upperBound..<end.lowerBound])
        XCTAssertFalse(offlineArm.contains("last update"),
                       "an offline reading with no clock names a 'last update' it cannot date")
        XCTAssertTrue(offlineArm.contains("?? \"Offline\""),
                      "an offline reading with no clock no longer says just \"Offline\"")
        XCTAssertTrue(offlineArm.contains("\"Offline · \\($0)\""),
                      "an offline reading with a clock no longer shows that clock")
    }
}
