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
/// CONSTRUCTED, not served.
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
        let column = read.filter { $0.box.minX >= 40 }.sorted { $0.box.minY < $1.box.minY }
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
        XCTAssertTrue(read.contains { $0.box.minX >= 40 && $0.box.maxX < away.box.minX && sameRow(away, $0) },
                      "\(name): a live card took the finished layout — \(all)")
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
                let next = normalized(line.text) + acc
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

    private struct Line { let text: String; let box: CGRect }

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
        let mid = bounds.height / 2, overlap: CGFloat = 200
        let upper = try bandLines(image, bounds: bounds,
                                  band: CGRect(x: 0, y: 0, width: bounds.width, height: mid + overlap / 2))
        let lower = try bandLines(image, bounds: bounds,
                                  band: CGRect(x: 0, y: mid - overlap / 2, width: bounds.width,
                                               height: bounds.height - mid + overlap / 2))
        return upper.filter { $0.box.midY < mid } + lower.filter { $0.box.midY >= mid }
    }

    private func bandLines(_ image: UIImage, bounds: CGRect, band: CGRect) throws -> [Line] {
        let cg = try XCTUnwrap(image.cgImage)
        let scale = CGFloat(cg.width) / bounds.width
        let crop = try XCTUnwrap(cg.cropping(to: CGRect(x: band.minX * scale, y: band.minY * scale,
                                                        width: band.width * scale, height: band.height * scale)))
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.minimumTextHeight = 0
        try VNImageRequestHandler(cgImage: crop).perform([request])
        return (request.results ?? []).compactMap { o in
            o.topCandidates(1).first.map { c in
                let b = o.boundingBox
                return Line(text: c.string, box: CGRect(x: band.minX + b.minX * band.width,
                                                        y: band.minY + (1 - b.maxY) * band.height,
                                                        width: b.width * band.width, height: b.height * band.height))
            }
        }
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
        let column = read.filter {
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

    private func sameRow(_ a: Line, _ b: Line) -> Bool {
        a.box.midY >= b.box.minY - 2 && a.box.midY <= b.box.maxY + 2
    }

    private func describe(_ read: [Line]) -> String {
        read.map { "'\($0.text)'@\(Int($0.box.minX)),\(Int($0.box.minY))" }.joined(separator: " ")
    }

    // MARK: - Fixture

    private func served(_ id: Int, editing old: String? = nil, to new: String? = nil) throws -> FeedEventData {
        var json = Self.servedItems
        if let old, let new {
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
