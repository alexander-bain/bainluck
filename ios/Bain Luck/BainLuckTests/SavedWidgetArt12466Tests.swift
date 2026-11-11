import ImageIO
import XCTest
@testable import Bain_Luck

/// #12466 — the saved widget's new looks draw colours, crests and a chance bar.
/// What these pin:
///  - The bar draws exactly what the figures print: the reading's integers, a
///    draw-priced game's home side alone, a market's printed integer, and no
///    bar at all where no figure is printed (a result, a choice with no price).
///  - The bar's widths fill it and keep a side with any chance visible.
///  - Colours: on a light surface the app's own card rule, unchanged; on a dark
///    one the same floor, trying the team's secondary colour before the slot
///    default; text on a fill takes whichever ink reads better.
///  - Live scores only while live and only with both sides; https crests only.
///  - Crests are shrunk, kept on disk for 30 days, and a stale crest beats none.
/// Unit tests of the source. The looks themselves are photographed on #12466.
@MainActor
final class SavedWidgetArt12466Tests: XCTestCase {

    // A fixed clock (gotcha #44): every stamp below is relative to this.
    private let now = ISO8601DateFormatter().date(from: "2026-11-09T21:00:00Z")!
    private let fresh = "2026-11-09T20:55:00Z"

    private func event(_ fields: String, sport: String = "americanfootball_nfl") throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data("""
        {"id":14780576,"home_team":"Minnesota Vikings","away_team":"Buffalo Bills","sport":"\(sport)",
         "home_team_data":{"abbreviation":"MIN","primary_color":"#4f2683","secondary_color":"#ffc62f",
                           "logo_small":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/min.png"},
         "away_team_data":{"abbreviation":"BUF","primary_color":"#00338d","secondary_color":"#c60c30",
                           "logo_small":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png"},
         \(fields)}
        """.utf8))
    }

    private func market(_ fields: String) throws -> SavedWidgetMarketDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: Data("""
        {"id":86832,"name":"NFL Super Bowl Winner",\(fields)}
        """.utf8))
    }

    // MARK: - The bar draws what the figures print

    func testTheBarDrawsTheIntegersTheFiguresPrint() throws {
        let e = try event("""
        "status":"live","commence_time":"2026-11-09T20:15:00Z","away_score":3,"home_score":0,
        "current_odds":{"away_probability":0.634,"home_probability":0.366,
                        "away_rendered_percent":63,"home_rendered_percent":37},
        "hero_probability_observed_at":"\(fresh)"
        """)
        let reading = SavedWidgetReadingRules10875.game(e, side: nil, now: now)
        XCTAssertEqual(reading.rows.map(\.figure), ["63%", "37%"])
        XCTAssertEqual(reading.shares, .game(away: 0.63, home: 0.37))
    }

    func testWithoutServedIntegersTheBarDrawsThePairTheFiguresCameFrom() throws {
        let e = try event("""
        "status":"scheduled","commence_time":"2026-11-10T01:15:00Z",
        "current_odds":{"away_probability":0.64,"home_probability":0.36},
        "hero_probability_observed_at":"\(fresh)"
        """)
        let reading = SavedWidgetReadingRules10875.game(e, side: nil, now: now)
        XCTAssertEqual(reading.rows.map(\.figure), ["64%", "36%"])
        XCTAssertEqual(reading.shares, .game(away: 0.64, home: 0.36))
    }

    func testADrawPricedGameLeavesTheRestOfTheBarToNoTeam() throws {
        let e = try event("""
        "status":"scheduled","commence_time":"2026-11-10T01:15:00Z",
        "current_odds":{"away_probability":0.30,"home_probability":0.52},
        "hero_probability_observed_at":"\(fresh)"
        """, sport: "soccer_epl")
        let reading = SavedWidgetReadingRules10875.game(e, side: nil, now: now)
        XCTAssertNil(reading.rows[0].figure, "a draw-priced away side has no figure")
        XCTAssertEqual(reading.shares, .game(away: nil, home: 0.52))
    }

    func testNoBarWhereNoFigureIsPrinted() throws {
        let final = try event("""
        "status":"completed","commence_time":"2026-11-08T18:00:00Z","away_score":12,"home_score":35,
        "hero_settled_result":"home",
        "current_odds":{"away_probability":0.0,"home_probability":1.0}
        """)
        XCTAssertNil(SavedWidgetReadingRules10875.game(final, side: nil, now: now).shares, "a result got a bar")

        let unpriced = try event(#""status":"scheduled","commence_time":"2026-11-10T01:15:00Z""#)
        XCTAssertNil(SavedWidgetReadingRules10875.game(unpriced, side: nil, now: now).shares,
                     "a game with no chance to show got a bar")

        let settled = try market("""
        "status":"resolved","outcomes":[{"id":1,"name":"Seattle","probability":1.0,"is_winner":true,
                                         "resolution_source":"venue"}]
        """)
        XCTAssertNil(SavedWidgetReadingRules10875.market(settled, outcomeID: 1, now: now).shares,
                     "a settled market got a bar")
    }

    func testAMarketBarDrawsTheOutcomesPrintedInteger() throws {
        let m = try market("""
        "status":"open","outcomes":[
          {"id":1,"name":"San Francisco 49ers","probability":0.131,"last_updated":"\(fresh)"},
          {"id":2,"name":"Kansas City Chiefs","probability":0.112,"last_updated":"\(fresh)"}]
        """)
        let reading = SavedWidgetReadingRules10875.market(m, outcomeID: nil, now: now)
        XCTAssertEqual(reading.headline?.figure, "13%")
        XCTAssertEqual(reading.shares, .outcome(0.13))
    }

    // MARK: - Widths

    func testTheBarsSegmentsFillItInTheirShares() {
        let w = SavedWidgetArt12466.barWidths(.game(away: 0.63, home: 0.37), total: 102, gap: 2)
        XCTAssertEqual(w.first, 63, accuracy: 0.001)
        XCTAssertEqual(w.second, 37, accuracy: 0.001)
        let draw = SavedWidgetArt12466.barWidths(.game(away: nil, home: 0.52), total: 102, gap: 2)
        XCTAssertEqual(draw.second, 52, accuracy: 0.001, "a draw-priced bar draws the home chance alone")
        XCTAssertEqual(draw.first + draw.second, 100, accuracy: 0.001)
        let outcome = SavedWidgetArt12466.barWidths(.outcome(0.13), total: 102, gap: 2)
        XCTAssertEqual(outcome.second, 13, accuracy: 0.001)
    }

    func testASideWithAnyChanceStaysVisible() {
        let w = SavedWidgetArt12466.barWidths(.game(away: 0.996, home: 0.004), total: 102, gap: 2)
        XCTAssertGreaterThanOrEqual(w.second, 3)
        XCTAssertEqual(w.first + w.second, 100, accuracy: 0.001)
        let none = SavedWidgetArt12466.barWidths(.game(away: 1, home: 0), total: 102, gap: 2)
        XCTAssertEqual(none.second, 0, "a side with no chance gets no sliver")
        let broken = SavedWidgetArt12466.barWidths(.outcome(.nan), total: 102, gap: 2)
        XCTAssertEqual(broken.second, 0)
    }

    // MARK: - Colours

    private func art(awayPrimary: String?, awaySecondary: String? = nil,
                     homePrimary: String?, homeSecondary: String? = nil) -> SavedWidgetArt12466 {
        SavedWidgetArt12466(
            away: .init(short: "AWY", primaryHex: awayPrimary, secondaryHex: awaySecondary, logoURL: nil),
            home: .init(short: "HOM", primaryHex: homePrimary, secondaryHex: homeSecondary, logoURL: nil))
    }

    func testOnALightSurfaceTheBarIsTheAppsOwnCardColours() {
        let cases: [(String?, String?)] = [("#00338d", "#4f2683"), ("#ffffff", "#d11317"), (nil, nil), ("#d11317", "#d11317")]
        for (away, home) in cases {
            let resolved = art(awayPrimary: away, homePrimary: home)
                .barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
            let app = TeamTextContrast.cardColorHexes(awayHex: away, homeHex: home)
            XCTAssertEqual(resolved.away, app.away, "\(String(describing: away))")
            XCTAssertEqual(resolved.home, app.home, "\(String(describing: home))")
        }
    }

    func testOnADarkSurfaceATeamTriesItsOwnSecondaryBeforeTheDefault() {
        let dark = SavedWidgetArt12466.darkSurfaceLuminance
        // Navy fails 3:1 on the dark fill; the team's own gold passes.
        let navyGold = art(awayPrimary: "#002A5C", awaySecondary: "#FFB612", homePrimary: "#E31837")
            .barHexes(surfaceLuminance: dark)
        XCTAssertEqual(navyGold.away, "#FFB612")
        XCTAssertEqual(navyGold.home, "#E31837")
        // Both of the team's colours fail: the slot default, as the app's floor does.
        let bothDark = art(awayPrimary: "#002A5C", awaySecondary: "#0B162A", homePrimary: "#E31837")
            .barHexes(surfaceLuminance: dark)
        XCTAssertEqual(bothDark.away, ProbabilityBarPalette.awayDefault)
        // Whatever each side resolves to, the two read apart and clear the floor.
        for pair in [navyGold, bothDark] {
            XCTAssertTrue(ProbabilityBarPalette.distinguishable(pair.away, pair.home))
            for hex in [pair.away, pair.home] {
                XCTAssertGreaterThanOrEqual(SavedWidgetArt12466.contrast(hex, againstLuminance: dark) ?? 0,
                                            TeamTextContrast.minimumRatio, hex)
            }
        }
    }

    func testTextOnAFillTakesTheInkThatReadsBetter() {
        XCTAssertEqual(SavedWidgetArt12466.ink(on: "#00338D"), "#FFFFFF")
        XCTAssertEqual(SavedWidgetArt12466.ink(on: "#FFFFFF"), SavedWidgetArt12466.inkHex)
        XCTAssertEqual(SavedWidgetArt12466.ink(on: "#10B981"), SavedWidgetArt12466.inkHex)
        XCTAssertEqual(SavedWidgetArt12466.ink(on: "not-a-colour"), "#FFFFFF")
    }

    func testTwoFillsThatDoNotReadApartAreKeptApart() {
        let fills = art(awayPrimary: "#D11317", homePrimary: "#D11317").fillHexes()
        XCTAssertEqual(fills.home, "#D11317", "home keeps its own colour")
        XCTAssertTrue(ProbabilityBarPalette.distinguishable(fills.away, fills.home))
    }

    func testShadedMixesTowardBlack() {
        XCTAssertEqual(SavedWidgetArt12466.shaded("#FFFFFF", by: 0.5), "#808080")
        XCTAssertEqual(SavedWidgetArt12466.shaded("#10B981", by: 0), "#10B981")
        XCTAssertEqual(SavedWidgetArt12466.shaded("#10B981", by: 1), "#000000")
    }

    // MARK: - Scores and crests

    func testScoresOnlyWhileLiveWithBothSides() throws {
        let live = try event(#""status":"live","away_score":3,"home_score":0"#)
        XCTAssertEqual(SavedWidgetArt12466.game(live).scores, .init(away: 3, home: 0))
        let half = try event(#""status":"live","away_score":3"#)
        XCTAssertNil(SavedWidgetArt12466.game(half).scores, "half a score is not a score")
        let final = try event(#""status":"completed","away_score":12,"home_score":35"#)
        XCTAssertNil(SavedWidgetArt12466.game(final).scores, "a final score is the rows' own figure")
        let scheduled = try event(#""status":"scheduled""#)
        XCTAssertNil(SavedWidgetArt12466.game(scheduled).scores)
    }

    func testOnlyAnHttpsCrestIsFetched() throws {
        let e = try event(#""status":"scheduled""#)
        let art = SavedWidgetArt12466.game(e)
        XCTAssertEqual(art.away.logoURL?.absoluteString, "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png")
        XCTAssertEqual(art.away.short, "BUF")
        XCTAssertEqual(art.home.primaryHex, "#4f2683")
        let plain = try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data("""
        {"id":1,"home_team":"A","away_team":"B","home_team_data":{"abbreviation":"A","logo_small":"http://x.test/a.png"}}
        """.utf8))
        XCTAssertNil(SavedWidgetArt12466.game(plain).home.logoURL)
    }

    /// A 500×500 PNG, the size the server's crests are.
    private func bigPNG() -> Data {
        let context = CGContext(data: nil, width: 500, height: 500, bitsPerComponent: 8, bytesPerRow: 0,
                                space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.setFillColor(red: 0, green: 0.2, blue: 0.55, alpha: 1)
        context.fill(CGRect(x: 100, y: 100, width: 300, height: 300))
        let out = NSMutableData()
        let destination = CGImageDestinationCreateWithData(out, "public.png" as CFString, 1, nil)!
        CGImageDestinationAddImage(destination, context.makeImage()!, nil)
        CGImageDestinationFinalize(destination)
        return out as Data
    }

    func testACrestIsShrunkAndKeptOnDiskForThirtyDays() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("logos-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = URL(string: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png")!
        let png = bigPNG()
        final class Counter: @unchecked Sendable { var calls = 0; var answer: Data? }
        let counter = Counter()
        counter.answer = png
        let fetch: @Sendable (URL) async -> Data? = { _ in counter.calls += 1; return counter.answer }

        let first = await SavedWidgetLogos12466.crest(url, now: now, directory: directory, fetch: fetch)
        let image = try XCTUnwrap(SavedWidgetLogos12466.image(first))
        XCTAssertLessThanOrEqual(max(image.width, image.height), SavedWidgetLogos12466.maxPixelSize)
        XCTAssertEqual(counter.calls, 1)
        // The file's stamp is the machine's clock; put it on this test's clock.
        let file = SavedWidgetLogos12466.cacheFile(for: url, in: directory)
        try FileManager.default.setAttributes([.modificationDate: now], ofItemAtPath: file.path)

        let kept = await SavedWidgetLogos12466.crest(url, now: now.addingTimeInterval(60), directory: directory, fetch: fetch)
        XCTAssertEqual(kept, first)
        XCTAssertEqual(counter.calls, 1, "a crest on disk was fetched again")

        // A stamp from the future is no known age: fetched again.
        try FileManager.default.setAttributes([.modificationDate: now.addingTimeInterval(3600)], ofItemAtPath: file.path)
        _ = await SavedWidgetLogos12466.crest(url, now: now, directory: directory, fetch: fetch)
        XCTAssertEqual(counter.calls, 2, "a crest stamped in the future was trusted")

        // Older than 30 days: fetched again, and a failed fetch keeps the old crest.
        try FileManager.default.setAttributes([.modificationDate: now.addingTimeInterval(-31 * 24 * 3600)],
                                              ofItemAtPath: file.path)
        counter.answer = nil
        let stale = await SavedWidgetLogos12466.crest(url, now: now, directory: directory, fetch: fetch)
        XCTAssertEqual(counter.calls, 3, "an old crest was not fetched again")
        XCTAssertEqual(stale, first, "a stale crest beats none")
    }

    func testWhatIsNotAnImageIsNoCrest() async {
        XCTAssertNil(SavedWidgetLogos12466.thumbnail(Data("<html>nope</html>".utf8)))
        let url = URL(string: "https://a.espncdn.com/x.png")!
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("logos-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let none = await SavedWidgetLogos12466.crest(url, now: now, directory: directory) { _ in Data("nope".utf8) }
        XCTAssertNil(none)
        let refused = await SavedWidgetLogos12466.crest(URL(string: "http://a.espncdn.com/x.png")!, now: now,
                                                        directory: directory) { _ in XCTFail("fetched http"); return nil }
        XCTAssertNil(refused)
    }

    // MARK: - The views use these rules

    /// The looks draw the bar only from `reading.shares`, and today's look
    /// fetches nothing new.
    func testTheWidgetDrawsTheseRulesAndTodaysLookFetchesNoCrest() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let looks = try String(contentsOf: root.appendingPathComponent("BainLuckWidget/SavedWidgetLooks12466.swift"),
                               encoding: .utf8)
        // Every bar is drawn from a `shares` bound to the reading's own.
        let bars = looks.components(separatedBy: "SavedChanceBar12466(").count - 1
        XCTAssertGreaterThan(bars, 0)
        XCTAssertEqual(looks.components(separatedBy: "SavedChanceBar12466(shares: shares,").count - 1, bars,
                       "a bar draws something other than the reading's shares")
        let bindings = looks.components(separatedBy: "let shares = ").dropFirst()
        XCTAssertFalse(bindings.isEmpty)
        for binding in bindings {
            XCTAssertTrue(binding.hasPrefix("model.reading.shares"), "a bar's shares come from elsewhere")
        }
        XCTAssertFalse(looks.contains("Shares.game(") || looks.contains("Shares.outcome("),
                       "a look builds its own bar shares")
        let widget = try String(contentsOf: root.appendingPathComponent("BainLuckWidget/SavedItemWidget10875.swift"),
                                encoding: .utf8)
        XCTAssertTrue(widget.contains("if look != .today, case .detail(.game(let event), _) = content {"),
                      "today's look no longer skips the crest fetch")
    }

    /// #12466 — Alex picked A, Matchup (Tue Nov 10). It is the one look kept:
    /// every build draws it over a reading, and no look choice reaches the widget's settings.
    func testMatchupIsTheOneLookAndEveryBuildDrawsIt() throws {
        // The look type lives in the widget extension, which this target cannot
        // import, so the rule is read from the source.
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let intent = try String(contentsOf: root.appendingPathComponent("BainLuckWidget/SavedItemWidgetIntent10875.swift"),
                                encoding: .utf8)
        XCTAssertFalse(intent.contains("Look (preview)"), "the four-look preview parameter is gone")
        XCTAssertTrue(intent.contains("var look12466: SavedWidgetLook12466 { .shipping }"))
        let looks = try String(contentsOf: root.appendingPathComponent("BainLuckWidget/SavedWidgetLooks12466.swift"),
                               encoding: .utf8)
        XCTAssertTrue(looks.contains("case today, matchup\n"), "today (messages) and Matchup only")
        XCTAssertTrue(looks.contains("static let shipping: SavedWidgetLook12466 = .matchup"))
        for gone in ["SavedCleanLook12466", "SavedScoreboardLook12466", "SavedSpotlightLook12466"] {
            XCTAssertFalse(looks.contains(gone), gone)
        }
    }
}
