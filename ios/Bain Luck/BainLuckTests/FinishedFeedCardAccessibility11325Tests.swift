import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #11325 — at accessibility text sizes a finished Sports card broke "FINAL"
/// mid-word and cut both team names to "Washingt…" / "San Fran…", and the
/// finished Discover card's two-line title stopped at "Washing-/ton Com…".
///
/// These tests READ THE RENDERED CARD. Each card is hosted at a pinned width
/// and Dynamic Type size and its pixels are read by Vision, so a test passes
/// only if a reader could read the words — not because a modifier is present.
/// The deciding arms are the AX5 ones: on the base layout each of them fails,
/// because the name, status or title text they look for is not on screen.
///
/// Controls, each able to fail in the other direction:
///   - Large keeps the single rows: the score sits on its team's name row.
///   - A LIVE card at AX5 keeps the single rows too: only finished cards move.
///   - The forecast line still prints, labelled, below both actual scores, and
///     the soccer final (whose forecast is withheld) prints no forecast at all.
///
/// Fixture: the two served finals from `FinalForecastComparison11296Tests`
/// (production `/api/feed?mode=sports`, 2026-10-20 07:10Z), trimmed to the
/// keys these cards read. The live copy edits ONE value — `status` — and is
/// CONSTRUCTED, not served. The odds copy inserts ONE key — `opening_odds` —
/// and is CONSTRUCTED, not served: the served capture carries no pre-game
/// probability, so no served frame draws one, and its frames say so by name.
@MainActor
final class FinishedFeedCardAccessibility11325Tests: XCTestCase {

    // MARK: - Branch selection

    func testOnlyAFinishedCardAtAnAccessibilitySizeTakesTheNewLayout() {
        XCTAssertTrue(EventState.isFinished("completed"), "precondition: the served final is finished")
        let statuses: [String?] = ["completed", "scheduled", "live", "suspended", nil]
        let sizes: [DynamicTypeSize] = [.large, .xxxLarge, .accessibility1, .accessibility5]
        for status in statuses {
            for size in sizes {
                let expected = status == "completed" && size.isAccessibilitySize
                let finished = EventState.isFinished(status)
                XCTAssertEqual(FinishedCardAccessibility11325.applies(isFinished: finished, typeSize: size),
                               expected, "\(status ?? "nil") at \(size)")
                XCTAssertEqual(NativeEventDiscoverCard.matchTitleLineLimit(isDone: finished, typeSize: size),
                               expected ? nil : 2, "Discover title cap, \(status ?? "nil") at \(size)")
            }
        }
    }

    // MARK: - Sports card, finished, AX5

    func testTheFinishedSportsCardAtAX5ReadsWholeLeagueStatusAndBothNames() throws {
        for width: CGFloat in [320, 393] {
            let name = "sports-nfl-\(Int(width))-ax5"
            let read = try sportsLines(try served(14780563), width: width, size: .accessibility5, name: name)
            let all = describe(read)

            assertWholeToken("NFL", in: read, name)
            assertWholeToken("FINAL", in: read, name)
            assertNoFragmentOfFinal(in: read, name)

            let away = try XCTUnwrap(scoreLine("17", in: read), "\(name): no actual 17 — \(all)")
            let home = try XCTUnwrap(scoreLine("23", in: read), "\(name): no actual 23 — \(all)")
            XCTAssertLessThan(away.box.minY, home.box.minY, "\(name): team order moved — \(all)")
            XCTAssertTrue(nameSitsAbove(away, reading: "WashingtonCommanders", in: read),
                          "\(name): the complete away name does not sit directly above its 17 — \(all)")
            XCTAssertTrue(nameSitsAbove(home, reading: "SanFrancisco49ers", in: read),
                          "\(name): the complete home name does not sit directly above its 23 — \(all)")

            // The served final carries no pre-game probability: no label, no block.
            XCTAssertFalse(read.contains { normalized($0.text).contains("Pregame") },
                           "\(name): a pre-game chance label printed with no pre-game probability — \(all)")

            let label = try XCTUnwrap(read.first { $0.text.contains("Projection") },
                                      "\(name): the forecast line is gone — \(all)")
            XCTAssertGreaterThan(label.box.minY, home.box.maxY, "\(name): the forecast left its place under the result")
            let below = read.filter { $0.box.minY >= label.box.minY - 2 }.map(\.text).joined(separator: " ")
            XCTAssertTrue(below.contains("22") && below.contains("29"), "\(name): forecast pair 22/29 missing — \(all)")
            for line in read where line.box.maxY < label.box.minY {
                XCTAssertFalse(isElided(line.text), "\(name): '\(line.text)' is cut short — \(all)")
            }
        }
    }

    /// Each pre-game probability stays in its own team's group and says what it
    /// is: the actual score alone on its line, and directly under it a complete
    /// "Pregame win chance" label, then the whole percent — away's under 17 and
    /// above the home name, home's under 23. A copy that swaps the sides, drops
    /// the label, or puts the percent back beside the score has no such block.
    func testTheFinishedSportsCardAtAX5KeepsEachPreGameProbabilityWithItsOwnTeam() throws {
        XCTAssertNil(try served(14780563).openingOdds, "precondition: the served final carries no pre-game probability")
        let odds = try served(14780563, editing: #""ended_at": "#,
                              to: Self.constructedOpeningOdds + #", "ended_at": "#)
        XCTAssertEqual(odds.openingOdds?.awayProbability, 0.2381)
        XCTAssertEqual(odds.openingOdds?.homeProbability, 0.7619)
        XCTAssertNil(odds.prematchOdds, "precondition: the card falls back to the constructed opening_odds")
        for width: CGFloat in [320, 393] {
            let name = "sports-nfl-\(Int(width))-ax5-constructed-odds"
            let read = try sportsLines(odds, width: width, size: .accessibility5, name: name)
            let all = describe(read)

            for percent in ["24%", "76%"] {
                XCTAssertEqual(read.filter { valueTokens($0.text).contains(percent) }.count, 1,
                               "\(name): \(percent) is not printed exactly once — \(all)")
            }
            let away = try XCTUnwrap(scoreLine("17", in: read), "\(name): no actual 17 on a line of its own — \(all)")
            let home = try XCTUnwrap(scoreLine("23", in: read), "\(name): no actual 23 on a line of its own — \(all)")
            for score in [away, home] {
                XCTAssertFalse(read.contains { $0.box.minX > score.box.maxX && sameRow($0, score) },
                               "\(name): something is printed beside the actual \(score.text) — \(all)")
            }
            let awayChance = try XCTUnwrap(chanceBlock(under: away, percent: "24%", in: read),
                                           "\(name): 24% is not directly under 17, after a complete 'Pregame win chance' — \(all)")
            let homeChance = try XCTUnwrap(chanceBlock(under: home, percent: "76%", in: read),
                                           "\(name): 76% is not directly under 23, after a complete 'Pregame win chance' — \(all)")
            let awayName = try XCTUnwrap(nameLines(above: away, reading: "WashingtonCommanders", in: read),
                                         "\(name): the complete away name does not sit directly above its 17 — \(all)")
            let homeName = try XCTUnwrap(nameLines(above: home, reading: "SanFrancisco49ers", in: read),
                                         "\(name): the complete home name does not sit directly above its 23 — \(all)")
            XCTAssertGreaterThan(awayChance.percent.box.midY, awayName.bottom.box.maxY,
                                 "\(name): 24% is not below Washington Commanders — \(all)")
            XCTAssertLessThan(awayChance.percent.box.maxY, homeName.top.box.minY,
                              "\(name): 24% is not above San Francisco 49ers — \(all)")
            XCTAssertGreaterThan(homeChance.label.box.minY, homeName.bottom.box.maxY,
                                 "\(name): 76% and its label are not below San Francisco 49ers — \(all)")
        }
    }

    func testTheFinishedSoccerCardAtAX5ReadsWholeLeagueWordsAndNamesWithNoForecast() throws {
        let name = "sports-soccer-320-ax5"
        let read = try sportsLines(try served(15326903), width: 320, size: .accessibility5, name: name)
        let all = describe(read)

        // "Primera División - Argentina" may take several lines; each word whole.
        for word in ["Primera", "Division", "Argentina"] {
            assertWholeToken(word, in: read, name)
        }
        assertWholeToken("FINAL", in: read, name)
        assertNoFragmentOfFinal(in: read, name)

        // Both names, complete, in the name column (single-digit scores are too
        // small a target for Vision to pin, so the 1–1 is left to the frames).
        let column = read.map { clearOfCrest($0, columnEdge: 40) }.filter { $0.box.minX >= 40 }.sorted { $0.box.minY < $1.box.minY }
        let joined = column.map { normalized($0.text) }.joined()
        XCTAssertTrue(joined.contains("UnionSantaFe"), "\(name): away name incomplete — \(all)")
        XCTAssertTrue(joined.contains("DeportivoRiestra"), "\(name): home name incomplete — \(all)")
        for line in read {
            XCTAssertFalse(isElided(line.text), "\(name): '\(line.text)' is cut short — \(all)")
        }
        XCTAssertFalse(read.contains { $0.text.contains("Projection") },
                       "\(name): the withheld soccer forecast printed — \(all)")
    }

    // MARK: - Sports card controls: the single rows stay where they were

    func testTheFinishedSportsCardAtLargeKeepsItsSingleRows() throws {
        let name = "sports-nfl-393-large"
        let read = try sportsLines(try served(14780563), width: 393, size: .large, name: name)
        let all = describe(read)
        let away = try XCTUnwrap(scoreLine("17", in: read), "\(name): no 17 — \(all)")
        let home = try XCTUnwrap(scoreLine("23", in: read), "\(name): no 23 — \(all)")
        let awayName = try XCTUnwrap(read.first { $0.text.contains("Washington Commanders") }, "\(name): \(all)")
        let homeName = try XCTUnwrap(read.first { $0.text.contains("San Francisco 49ers") && !$0.text.contains("Washington") },
                                     "\(name): \(all)")
        XCTAssertTrue(sameRow(away, awayName), "\(name): 17 left its name's row — \(all)")
        XCTAssertTrue(sameRow(home, homeName), "\(name): 23 left its name's row — \(all)")
        let league = try XCTUnwrap(read.first { tokens($0.text).contains("NFL") }, "\(name): \(all)")
        let status = try XCTUnwrap(read.first { tokens($0.text).contains("FINAL") }, "\(name): \(all)")
        XCTAssertTrue(sameRow(league, status), "\(name): league and FINAL no longer share the top row — \(all)")
        XCTAssertTrue(read.contains { $0.text.contains("Projection") }, "\(name): forecast line gone — \(all)")
    }

    func testALiveSportsCardAtAX5KeepsItsSingleRows() throws {
        let name = "sports-nfl-320-ax5-live"
        let live = try served(14780563, editing: #""status": "completed""#, to: #""status": "live""#)
        XCTAssertEqual(live.status, "live")
        let read = try sportsLines(live, width: 320, size: .accessibility5, name: name)
        let all = describe(read)
        let away = try XCTUnwrap(scoreLine("17", in: read), "\(name): no 17 — \(all)")
        // The single row puts the (truncated) name to the score's LEFT on the
        // same row; the finished layout puts the score under the name, with
        // nothing beside it. How far the name is cut is not this test's claim.
        XCTAssertTrue(read.map { clearOfCrest($0, columnEdge: 40) }.contains { $0.box.minX >= 40 && $0.box.maxX < away.box.minX && sameRow(away, $0) },
                      "\(name): a live card took the finished layout — \(all)")
    }

    // MARK: - #9483 — the finished single row names its pre-game number

    /// At default size the finished row printed a bare "32%" beside
    /// Stuttgart's actual "1", and nothing on the card said the percent was
    /// from before the game. Now the word "Pregame" prints immediately before
    /// each pre-game number, on its own team's row, after that team's score —
    /// and whole, at both widths. At 320pt the word must not cost a name: the
    /// name wraps rather than truncating. A copy that drops the word, puts it
    /// on the other row, or cuts the word or a name has no such row.
    func testTheFinishedSportsCardAtLargeNamesEachPreGameProbability() throws {
        let odds = try served(14780563, editing: #""ended_at": "#,
                              to: Self.constructedOpeningOdds + #", "ended_at": "#)
        for width: CGFloat in [320, 393] {
            let name = "sports-nfl-\(Int(width))-large-constructed-odds"
            let read = try sportsLines(odds, width: width, size: .large, name: name)
            let all = describe(read)
            for (team, score, percent) in [("WashingtonCommanders", "17", "24%"), ("SanFrancisco49ers", "23", "76%")] {
                let row = try XCTUnwrap(qualifiedRow(percent, in: read),
                                        "\(name): \(percent) is not printed exactly once — \(all)")
                XCTAssertEqual(row.firstIndex(of: percent).map { row[row.index(before: $0)] }, "Pregame",
                               "\(name): \(percent) is not directly after a whole 'Pregame' — \(row)")
                let at = try XCTUnwrap(row.firstIndex(of: score), "\(name): \(score) left \(percent)'s row — \(row)")
                XCTAssertLessThan(at, row.index(before: row.firstIndex(of: percent)!),
                                  "\(name): 'Pregame \(percent)' is not after the actual \(score) — \(row)")
                // The complete name, before the score (a crest Vision fuses on
                // — "®San" — only adds a leading mark), whole at both widths.
                XCTAssertTrue(normalized(row[..<at].joined()).hasSuffix(team),
                              "\(name): \(team) is not complete before \(score) on \(percent)'s row — \(row)")
            }
            XCTAssertEqual(read.filter { tokens($0.text).contains("Pregame") }.count, 2,
                           "\(name): not one 'Pregame' per number — \(all)")
            for line in read where tokens(line.text).contains("Pregame") || line.text.contains("%") {
                XCTAssertFalse(isElided(line.text), "\(name): '\(line.text)' is cut short — \(all)")
            }
        }
    }

    /// The case Design read: Stuttgart 1, Atlético Madrid 1, a board that prices
    /// a draw, so only the home number prints (#5363). Its row reads
    /// "VfB Stuttgart 1 Pregame 32%"; Atlético's row carries no word and no
    /// percent, and the card prints the word exactly once.
    func testTheStuttgartFinalAtLargeReadsPregameBeforeItsOnlyNumber() throws {
        let card = try leagueFeedEvent(Self.stuttgartLeagueRow)
        for width: CGFloat in [320, 393] {
            let name = "sports-soccer-15330334-\(Int(width))-large"
            let read = try sportsLines(card, width: width, size: .large, name: name)
            let all = describe(read)
            let row = try XCTUnwrap(qualifiedRow("32%", in: read), "\(name): 32% is not printed exactly once — \(all)")
            XCTAssertEqual(Array(row.suffix(4)), ["Stuttgart", "1", "Pregame", "32%"],
                           "\(name): Stuttgart's row does not end '1 Pregame 32%' — \(row)")
            let atletico = try XCTUnwrap(read.first { normalized($0.text).contains("AtleticoMadrid") },
                                         "\(name): no Atlético Madrid row — \(all)")
            let other = rowTokens(atletico, in: read)
            XCTAssertFalse(other.contains("Pregame") || other.contains { $0.hasSuffix("%") },
                           "\(name): Atlético's row carries a pre-game word or number — \(other)")
            XCTAssertEqual(read.filter { tokens($0.text).contains("Pregame") }.count, 1,
                           "\(name): 'Pregame' is not printed exactly once — \(all)")
        }
    }

    /// Controls: the word belongs to a FINISHED row's pre-game number only.
    /// No number — no word. A live or scheduled card holding the same pair
    /// prints no word. A suspended row still prints its bare pre-match number
    /// under "No result reported", with no word: nothing on it is final.
    func testOnlyAFinishedRowWithAPreGameNumberPrintsTheWord() throws {
        let bare = try served(14780563)
        XCTAssertNil(bare.openingOdds, "precondition: the served final carries no pre-game probability")
        let read = try sportsLines(bare, width: 393, size: .large, name: "sports-nfl-393-large-no-baseline")
        XCTAssertFalse(read.contains { tokens($0.text).contains("Pregame") || $0.text.contains("%") },
                       "no-baseline: a pre-game word or number printed with no pre-game probability — \(describe(read))")
        for status in ["live", "scheduled", "suspended"] {
            let e = try served(14780563, edits: [
                (#""ended_at": "#, Self.constructedOpeningOdds + #", "ended_at": "#),
                (#""status": "completed""#, #""status": "\#(status)""#),
            ])
            XCTAssertEqual(e.status, status)
            XCTAssertEqual(e.openingOdds?.homeProbability, 0.7619)
            let name = "sports-nfl-393-large-\(status)-constructed-odds"
            let lines = try sportsLines(e, width: 393, size: .large, name: name)
            let all = describe(lines)
            XCTAssertFalse(lines.contains { tokens($0.text).contains("Pregame") },
                           "\(name): a \(status) card printed 'Pregame' — \(all)")
            if status == "suspended" {
                for percent in ["24%", "76%"] {
                    XCTAssertTrue(lines.contains { valueTokens($0.text).contains(percent) },
                                  "\(name): the suspended row lost its bare pre-match \(percent) — \(all)")
                }
            }
        }
    }

    // MARK: - Discover card, finished, AX5

    func testTheFinishedDiscoverTitlePrintsBothCompleteNamesBeforeTheForecast() throws {
        for width: CGFloat in [320, 393] {
            let name = "discover-nfl-\(Int(width))-ax5"
            let read = try discoverLines(try served(14780563), width: width, size: .accessibility5, name: name)
            let all = describe(read)
            let label = try XCTUnwrap(read.first { $0.text.contains("Projection") },
                                      "\(name): the forecast line is gone — \(all)")
            // Walk up from the forecast label: the lines directly above it must
            // read the whole title, with nothing elided, and nothing else.
            let above = read.filter { $0.box.maxY <= label.box.minY + 2 }.sorted { $0.box.minY > $1.box.minY }
            let target = "WashingtonCommandersSanFrancisco49ers"
            var acc = "", title: [Line] = []
            for line in above {
                let next = normalized(titleText(line, above: acc, home: "SanFrancisco49ers")) + acc
                guard target.hasSuffix(next) else { break }
                acc = next
                title.append(line)
                if acc == target { break }
            }
            XCTAssertEqual(acc, target, "\(name): the title above the forecast is not both complete names — \(all)")
            for line in title {
                XCTAssertFalse(isElided(line.text), "\(name): title line '\(line.text)' is cut short — \(all)")
            }
        }
    }

    // MARK: - Hosting and reading

    /// A line Vision read, and the rendered frame it was read from (so a line
    /// Vision fused with a neighbouring glyph can be settled from its pixels).
    private struct Line { let text: String; let box: CGRect; let frame: RenderedFrame11325 }

    private let pins = PinManager(
        defaults: UserDefaults(suiteName: "FinishedFeedCardAccessibility11325Tests")!,
        serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in })

    private func sportsLines(_ e: FeedEventData, width: CGFloat, size: DynamicTypeSize, name: String) throws -> [Line] {
        try read(EventCardView(event: e, reason: nil), width: width, size: size, name: name)
    }

    private func discoverLines(_ e: FeedEventData, width: CGFloat, size: DynamicTypeSize, name: String) throws -> [Line] {
        try read(NativeEventDiscoverCard(event: e, feedContext: nil, expandedContext: nil,
                                         navigationPath: .constant(NavigationPath())),
                 width: width, size: size, name: name)
    }

    /// The card as the feed lays it out (16pt side margins, in a vertical
    /// scroller), at a pinned size, read top to bottom.
    private func read<V: View>(_ card: V, width: CGFloat, size: DynamicTypeSize, name: String) throws -> [Line] {
        let host = hostForMeasurement(
            ScrollView { card.padding(.horizontal, 16) }
                .environmentObject(pins)
                .environment(\.colorScheme, .light),
            at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 1400)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        settle(host, 0.8)
        defer { window.isHidden = true }
        return try tiledLines(host, name: name).sorted { $0.box.minY < $1.box.minY }
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    /// The window in two overlapping halves, each read by Vision at full scale
    /// (a whole tall frame is downscaled and loses small text); each line kept
    /// from exactly one half. The rendered frame is saved as evidence.
    private func tiledLines(_ host: UIViewController, name: String) throws -> [Line] {
        let bounds = host.view.bounds
        let image = UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("finished-card-11325-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Finished card 11325 rendered evidence: \(url.path)")
        let frame = RenderedFrame11325(image: try XCTUnwrap(image.cgImage), bounds: bounds)
        let mid = bounds.height / 2, overlap: CGFloat = 200
        let upper = try bandLines(frame, band: CGRect(x: 0, y: 0, width: bounds.width, height: mid + overlap / 2))
        let lower = try bandLines(frame, band: CGRect(x: 0, y: mid - overlap / 2, width: bounds.width,
                                                      height: bounds.height - mid + overlap / 2))
        return upper.filter { $0.box.midY < mid } + lower.filter { $0.box.midY >= mid }
    }

    private func bandLines(_ frame: RenderedFrame11325, band: CGRect) throws -> [Line] {
        try frame.recognize(in: band).map { Line(text: $0.text, box: $0.box, frame: frame) }
    }

    // MARK: - Reading rules

    /// Letters and digits only, accents folded: a name broken across lines
    /// ("Washing-" / "ton") reads back whole, and "@" vs "©" cannot matter.
    private func normalized(_ text: String) -> String {
        String(String.UnicodeScalarView(
            text.folding(options: .diacriticInsensitive, locale: nil).unicodeScalars
                .filter { CharacterSet.alphanumerics.contains($0) }))
    }

    private func tokens(_ text: String) -> [String] {
        text.folding(options: .diacriticInsensitive, locale: nil)
            .components(separatedBy: CharacterSet.whitespaces.union(CharacterSet(charactersIn: "·•")))
            .filter { !$0.isEmpty }
    }

    private func isElided(_ text: String) -> Bool {
        text.contains("…") || text.contains("...")
    }

    private func assertWholeToken(_ word: String, in read: [Line], _ name: String,
                                  file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(read.contains { tokens($0.text).contains(word) },
                      "\(name): '\(word)' is not on screen as one whole word — \(describe(read))",
                      file: file, line: line)
    }

    /// "FI-" / "NAL" and the like: the badge broken across lines.
    private func assertNoFragmentOfFinal(in read: [Line], _ name: String,
                                         file: StaticString = #filePath, line: UInt = #line) {
        let fragments: Set<String> = ["FI", "FIN", "FINA", "FI-", "FIN-", "FINA-", "NAL", "INAL", "AL"]
        for l in read where tokens(l.text).contains(where: fragments.contains) {
            XCTFail("\(name): FINAL broke across lines ('\(l.text)') — \(describe(read))", file: file, line: line)
        }
    }

    /// The topmost line reading exactly `digits`, clear of the forecast line.
    private func scoreLine(_ digits: String, in read: [Line]) -> Line? {
        let label = read.first { $0.text.contains("Projection") }?.box.minY ?? .infinity
        return read.first { $0.text.trimmingCharacters(in: .whitespaces) == digits && $0.box.minY < label }
    }

    /// Whether the lines directly above `score`, in its column, read exactly
    /// `target` — the complete name and nothing between it and its score.
    private func nameSitsAbove(_ score: Line, reading target: String, in read: [Line]) -> Bool {
        let column = read.map { clearOfCrest($0, columnEdge: score.box.minX - 8) }.filter {
            $0.box.maxY <= score.box.minY + 2
                && $0.box.minX >= score.box.minX - 8 && $0.box.minX <= score.box.minX + 40
        }.sorted { $0.box.minY > $1.box.minY }
        var acc = ""
        for line in column {
            acc = normalized(line.text) + acc
            if acc == target { return true }
            if !target.hasSuffix(acc) { return false }
        }
        return false
    }

    /// `nameSitsAbove`, returning the name's top and bottom lines.
    private func nameLines(above score: Line, reading target: String, in read: [Line]) -> (top: Line, bottom: Line)? {
        let column = read.map { clearOfCrest($0, columnEdge: score.box.minX - 8) }.filter {
            $0.box.maxY <= score.box.minY + 2
                && $0.box.minX >= score.box.minX - 8 && $0.box.minX <= score.box.minX + 40
        }.sorted { $0.box.minY > $1.box.minY }
        var acc = ""
        for line in column {
            acc = normalized(line.text) + acc
            if acc == target { return (line, column[0]) }
            if !target.hasSuffix(acc) { return nil }
        }
        return nil
    }

    /// Tokens with a percent read as "24 %" closed up to "24%".
    private func valueTokens(_ text: String) -> [String] {
        tokens(text.replacingOccurrences(of: " %", with: "%"))
    }

    /// The lines directly under `score`, in its column, clear of the forecast
    /// line: the label reading exactly "Pregame win chance" top to bottom
    /// (wrapped wherever the width puts it), then one line reading exactly
    /// `percent` — the whole value on its own. Nothing may sit between the
    /// score, the label and the value; anything else is no block. Returns the
    /// label's top line and the percent's line.
    private func chanceBlock(under score: Line, percent: String, in read: [Line]) -> (label: Line, percent: Line)? {
        let forecast = read.first { $0.text.contains("Projection") }?.box.minY ?? .infinity
        let column = read.filter {
            $0.box.minY >= score.box.maxY - 2 && $0.box.minY < forecast
                && $0.box.minX >= score.box.minX - 8 && $0.box.minX <= score.box.minX + 40
        }.sorted { $0.box.minY < $1.box.minY }
        let target = "Pregamewinchance"
        var acc = ""
        for line in column {
            if acc == target { return valueTokens(line.text) == [percent] ? (column[0], line) : nil }
            acc += normalized(line.text)
            if !target.hasPrefix(acc) { return nil }
        }
        return nil
    }

    /// #9483 — every token on `line`'s row, left to right, across however many
    /// lines Vision split the row into: each line whose box overlaps `line`'s
    /// vertically, so a name wrapped onto two lines beside a centred score
    /// still counts as that row's.
    private func rowTokens(_ line: Line, in read: [Line]) -> [String] {
        read.filter { $0.box.minY < line.box.maxY && line.box.minY < $0.box.maxY }
            // Left to right; lines starting in one column (a wrapped name), top down.
            .sorted { abs($0.box.minX - $1.box.minX) < 8 ? $0.box.minY < $1.box.minY : $0.box.minX < $1.box.minX }
            .flatMap { valueTokens($0.text) }
    }

    /// #9483 — the row of the ONE line printing `percent`; nil if it prints on
    /// none, or on more than one.
    private func qualifiedRow(_ percent: String, in read: [Line]) -> [String]? {
        let holding = read.filter { valueTokens($0.text).contains(percent) }
        guard holding.count == 1 else { return nil }
        return rowTokens(holding[0], in: read)
    }

    private func sameRow(_ a: Line, _ b: Line) -> Bool {
        a.box.midY >= b.box.minY - 2 && a.box.midY <= b.box.maxY + 2
    }

    private func describe(_ read: [Line]) -> String {
        read.map { "'\($0.text)'@\(Int($0.box.minX)),\(Int($0.box.minY))" }.joined(separator: " ")
    }

    // MARK: - Lines Vision fused with a neighbour (settled from the frame)

    /// A crest's ink is at most this wide; the blank gap between a crest and
    /// its name is at least `crestGap`. Measured on the 837e3c152c frames:
    /// crests 14.6–24.7pt wide, crest→name gaps 9.3–15.7pt, while the widest
    /// letter gap in any line crossing a name column's edge is 6.3pt
    /// (N→F of "NFL").
    private static let crestWidth: CGFloat = 30
    private static let crestGap: CGFloat = 8

    /// Vision can read a team crest and the first line of the name beside it
    /// as ONE line that starts at the crest ("wWashing-"@7, "®San Francisco"@11,
    /// "(' Union"@8). Such a line, crossing the name column's `columnEdge`, is
    /// read again from the pixels right of the blank gap that separates crest
    /// and name — and only when the frame shows that gap: the first blank run
    /// at least `crestGap` wide has no more than a crest's width of ink before
    /// it, and the ink after it starts in the column. The re-read must be one
    /// line. Otherwise the line is returned as read, and stays out of the column.
    private func clearOfCrest(_ line: Line, columnEdge edge: CGFloat) -> Line {
        guard line.box.minX < edge, line.box.maxX > edge else { return line }
        let ink = line.frame.inkClusters(in: line.box)
        guard let first = ink.first,
              let gap = ink.indices.dropFirst().first(where: { ink[$0].minX - ink[$0 - 1].maxX >= Self.crestGap }),
              ink[gap - 1].maxX - first.minX <= Self.crestWidth, ink[gap].minX >= edge else { return line }
        let cut = (ink[gap - 1].maxX + ink[gap].minX) / 2, pad = line.box.height * 0.15
        let name = CGRect(x: cut, y: line.box.minY - pad, width: line.box.maxX + 4 - cut,
                          height: line.box.height + 2 * pad)
        guard let reread = try? line.frame.recognize(in: name), reread.count == 1 else { return line }
        return Line(text: reread[0].text, box: reread[0].box, frame: line.frame)
    }

    /// The Discover title prints "Away @ Home". `normalized` drops the "@"
    /// (or "©"/"®"), but Vision can also read it as the letter "a" ("a San").
    /// A lone leading "a" is dropped only where the separator belongs — the
    /// rest of its line plus the title lines below spell exactly `home`, the
    /// complete home name — and only when its ink is at least as tall as the
    /// next glyph's: the "@" spans the capital height and drops below the
    /// baseline (44.0pt vs 38.7pt for the "S" after it), a lowercase "a" does
    /// not (29.0pt in the same line).
    private func titleText(_ line: Line, above acc: String, home: String) -> String {
        let parts = line.text.split(separator: " ", maxSplits: 1)
        guard parts.count == 2, parts[0] == "a", normalized(String(parts[1])) + acc == home else { return line.text }
        let b = line.box
        let ink = line.frame.inkClusters(in: CGRect(x: b.minX - b.height / 2, y: b.minY - b.height * 0.15,
                                                    width: b.width + b.height / 2, height: b.height * 1.3))
        guard ink.count >= 2, ink[0].height >= ink[1].height else { return line.text }
        return String(parts[1])
    }

    // MARK: - Fixture

    private func served(_ id: Int, editing old: String? = nil, to new: String? = nil) throws -> FeedEventData {
        if let old, let new { return try served(id, edits: [(old, new)]) }
        return try served(id, edits: [])
    }

    /// `served`, applying each edit in turn to the requested item only.
    private func served(_ id: Int, edits: [(String, String)]) throws -> FeedEventData {
        var json = Self.servedItems
        for (old, new) in edits {
            // Edit the requested item only: the first match after its id.
            let marker = #""id": \#(id),"#
            let head = try XCTUnwrap(json.range(of: marker))
            let tail = json[head.upperBound...]
            let at = try XCTUnwrap(tail.range(of: old))
            json.replaceSubrange(at, with: new)
        }
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let items = try d.decode([FeedItem].self, from: Data(json.utf8))
        return try XCTUnwrap(items.compactMap(\.event).first { $0.id == id }, "served event \(id) did not decode")
    }

    /// CONSTRUCTED, not served: the served NFL final carries no pre-game
    /// probability. The shape `AFinishedCardPrintsTheNumberItsLineQuotes8622Tests`
    /// decodes; the pair rounds to 24/76, digits no score or forecast uses.
    private static let constructedOpeningOdds =
        #""opening_odds": {"home_probability": 0.7619, "away_probability": 0.2381, "favorite": "home"}"#

    /// #9483 — a `/api/leagues` row in a CONSTRUCTED one-item feed envelope.
    private func leagueFeedEvent(_ data: String) throws -> FeedEventData {
        let json = #"[{"type":"event","score":40,"data":"# + data + "}]"
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let items = try d.decode([FeedItem].self, from: Data(json.utf8))
        return try XCTUnwrap(items.first?.event, "the league row did not decode")
    }

    /// #9483 — event 15330334 (VfB Stuttgart 1–1 Atlético Madrid, Champions
    /// League), its row in `/api/leagues/soccer_uefa_champs_league`
    /// `recent_results`, every key verbatim: the `leagueRow` of
    /// `FinalComparisonSoccerPeriod11296Tests` (PR #11390), which authority
    /// checked dict-equal to Design's retained `league.json`. Its
    /// `opening_odds` home 0.3169 is the "32%" Design read at 393pt/default.
    private static let stuttgartLeagueRow = ##"""
    {"id":15330334,"external_id":"56989e10c299aba1a0fce210bb214775","sport":"soccer_uefa_champs_league","home_team":"VfB Stuttgart","away_team":"Atlético Madrid","commence_time":"2026-10-20T19:00:00+00:00","completed_at":"2026-10-20T20:52:00.499184+00:00","status":"completed","home_score":1,"away_score":1,"home_win_probability":0.0558,"current_odds":{"home_probability":0.0558,"away_probability":0.9442},"opening_odds":{"home_probability":0.3169,"away_probability":0.4339},"home_team_data":{"team_id":18819,"slug":"vfb-stuttgart-ucl","primary_color":"#ffffff","secondary_color":"#DA0308","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/134.png","record":"2-1-0","abbreviation":"VFB"},"away_team_data":{"team_id":2293,"slug":"atltico-madrid-league","primary_color":"#ca3624","secondary_color":"#000000","logo_small":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","logo_large":"https://a.espncdn.com/i/teamlogos/soccer/500/1068.png","record":"1-1-1","abbreviation":"ATM"},"espn":{"period":"FT","game_clock":"90'+4'","broadcast":"Paramount+"},"pregame_projection":{"projected_home_score":1.5,"projected_away_score":1.9,"kind":"last_before_scheduled_start","earliest_captured_at":"2026-10-20T18:37:57.209904+00:00","latest_captured_at":"2026-10-20T18:56:23.853083+00:00","boundary":"scheduled_start","boundary_at":"2026-10-20T19:00:00+00:00","source":"sportsbooks","basis":"consensus_spread_total","bookmaker_count":4,"unit":"goals","period":"regulation"},"final_score_period":"regulation"}
    """##

    /// Trimmed from `FinalForecastComparison11296Tests.servedItems` (same
    /// served capture), keeping its two finals verbatim.
    private static let servedItems = #"""
    [
      {
        "type": "event",
        "score": 35,
        "reason": "",
        "headline": null,
        "data": {
          "id": 14780563,
          "external_id": "f122527f003276d3bca19efa48c902c1",
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "San Francisco 49ers",
          "away_team": "Washington Commanders",
          "commence_time": "2026-10-20T00:15:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 23,
          "away_score": 17,
          "ended_at": "2026-10-20T03:22:26.523221+00:00",
          "pregame_projection": {
            "projected_home_score": 29.4,
            "projected_away_score": 22.2,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-10-19T22:15:21.773164+00:00",
            "latest_captured_at": "2026-10-20T00:12:13.153004+00:00",
            "boundary": "scheduled_start",
            "boundary_at": "2026-10-20T00:15:00+00:00",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 21,
            "unit": "points",
            "period": "full_game"
          }
        }
      },
      {
        "type": "event",
        "score": 28,
        "reason": "",
        "headline": null,
        "data": {
          "id": 15326903,
          "external_id": "475ceeb0bfb323ff19700f0b90ed6980",
          "sport": "soccer_argentina_primera_division",
          "sport_name": "Primera División - Argentina",
          "home_team": "Deportivo Riestra",
          "away_team": "Union Santa Fe",
          "commence_time": "2026-10-20T00:15:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "status": "completed",
          "home_score": 1,
          "away_score": 1,
          "ended_at": "2026-10-20T02:10:36.340211+00:00",
          "pregame_projection": {
            "projected_home_score": 1.2,
            "projected_away_score": 0.8,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-10-20T00:05:34.521964+00:00",
            "latest_captured_at": "2026-10-20T00:14:51.898122+00:00",
            "boundary": "scheduled_start",
            "boundary_at": "2026-10-20T00:15:00+00:00",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 3,
            "unit": "goals",
            "period": "regulation"
          }
        }
      }
    ]
    """#
}

/// A rendered card frame (`bounds` in points, `image` at device scale), read
/// two ways: by Vision, and by where its ink is. A column holds ink when any
/// pixel in it is darker than luma 200 — the cards' grey text (≈142) and team
/// colours are ink; white and the status pill's fill (≈240) are not.
/// CoreGraphics and Vision only.
private final class RenderedFrame11325 {
    let bounds: CGRect
    private let image: CGImage
    private let width: Int, height: Int

    init(image: CGImage, bounds: CGRect) {
        self.image = image; self.bounds = bounds; width = image.width; height = image.height
    }

    /// Row-major luma, top row first, over white; decoded only when a line
    /// needs its ink read. Empty if it cannot be drawn, and then no ink is found.
    private lazy var luma: [UInt8] = {
        let w = width, h = height
        var rgba = [UInt8](repeating: 0, count: w * h * 4)
        let drawn = rgba.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                          bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: w, height: h))
            context.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard drawn else { return [] }
        return (0..<(w * h)).map { i in
            UInt8((299 * Int(rgba[4 * i]) + 587 * Int(rgba[4 * i + 1]) + 114 * Int(rgba[4 * i + 2])) / 1000)
        }
    }()

    private var scale: CGFloat { CGFloat(width) / bounds.width }

    /// Vision's lines inside `rect` (points), read on their own; boxes in points.
    /// Throws if `rect` cannot be cut from the frame.
    func recognize(in rect: CGRect) throws -> [(text: String, box: CGRect)] {
        let s = scale
        guard let crop = image.cropping(to: CGRect(x: rect.minX * s, y: rect.minY * s,
                                                   width: rect.width * s, height: rect.height * s))
        else { throw CocoaError(.coderInvalidValue) }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.minimumTextHeight = 0
        try VNImageRequestHandler(cgImage: crop).perform([request])
        return (request.results ?? []).compactMap { o in
            o.topCandidates(1).first.map { c in
                let b = o.boundingBox
                return (c.string, CGRect(x: rect.minX + b.minX * rect.width, y: rect.minY + (1 - b.maxY) * rect.height,
                                         width: b.width * rect.width, height: b.height * rect.height))
            }
        }
    }

    /// The ink inside `rect` (points), left to right: each maximal run of
    /// inked columns, boxed to the rows its ink spans.
    func inkClusters(in rect: CGRect) -> [CGRect] {
        let s = scale
        let x0 = max(0, Int((rect.minX * s).rounded(.down))), x1 = min(width, Int((rect.maxX * s).rounded(.up)))
        let y0 = max(0, Int((rect.minY * s).rounded(.down))), y1 = min(height, Int((rect.maxY * s).rounded(.up)))
        guard x0 < x1, y0 < y1, luma.count == width * height else { return [] }
        var clusters: [CGRect] = [], start: Int?, top = Int.max, bottom = Int.min
        for x in x0...x1 {
            var inked = false
            if x < x1 {
                for y in y0..<y1 where luma[y * width + x] < 200 {
                    inked = true; top = min(top, y); bottom = max(bottom, y)
                }
            }
            if inked, start == nil { start = x }
            if !inked, let from = start {
                clusters.append(CGRect(x: CGFloat(from) / s, y: CGFloat(top) / s,
                                       width: CGFloat(x - from) / s, height: CGFloat(bottom - top + 1) / s))
                start = nil; top = .max; bottom = .min
            }
        }
        return clusters
    }
}
