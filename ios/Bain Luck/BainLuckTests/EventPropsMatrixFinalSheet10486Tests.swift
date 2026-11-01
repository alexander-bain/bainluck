import Combine
import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #10486 — a During question sheet that is OPEN when the game ends keeps the
/// player's name and says what happened: it follows the same question's After
/// version when the server grades one, else says the game is over. Before the
/// game ends, a question the server drops still reads as withdrawn (#10236
/// step 10).
///
/// FIXTURES: the #10236 and #10237 route-harness bodies — the real
/// serializers' spelling, NOT production prices. As in the reported game
/// (strikeouts at SD@MIL 15323985), the After body grades only Home Runs, so
/// the open Hits question has no After version. The one "follows After" case
/// re-keys one After question to that Hits question, labelled below.
@MainActor
final class EventPropsMatrixFinalSheet10486Tests: XCTestCase {
    private static func fixture(_ name: String) throws -> [String: Any] {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private static func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private static let judgeTwoHits = "s:aaron judge|hits|full_game|ge:2|over"
    private static let noRows = DuringPlayerProps(contract: nil, stats: [], rows: [], coverage: nil)

    private func during() throws -> DuringPlayerProps {
        try XCTUnwrap(Self.decode(Self.fixture("game-markets-10236-during-matrix.route.json")).duringPlayerProps)
    }

    /// The #10237 After body exactly: Home Runs only.
    private func after() throws -> AfterPlayerProps {
        try XCTUnwrap(Self.decode(Self.fixture("game-markets-10237-after.route.json")).afterPlayerProps)
    }

    /// DERIVED, not served: the #10237 body plus a Hits stat and Judge's 1+
    /// home-run question re-keyed to his 2+ hits — the After version of the
    /// open question, built with the server's own key shape.
    private func afterWithJudgeTwoHits(count: Int = 2) throws -> AfterPlayerProps {
        var body = try Self.fixture("game-markets-10237-after.route.json")
        var props = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        var stats = try XCTUnwrap(props["stats"] as? [[String: Any]])
        var hits = stats[0]
        hits["stat_key"] = "hits"; hits["label"] = "Hits"
        hits["unit_singular"] = "hit"; hits["unit_plural"] = "hits"
        stats.append(hits)
        var questions = try XCTUnwrap(props["questions"] as? [[String: Any]])
        var question = try XCTUnwrap(questions.first { ($0["question_key"] as? String)?.hasPrefix("s:aaron judge|") == true })
        question["question_key"] = "s:aaron judge|hits|full_game|ge:\(count)|over"
        question["stat_key"] = "hits"
        question["actual_key"] = "s:aaron judge|hits|full_game"
        question["predicate"] = ["count": count, "kind": "count_at_least", "label": "\(count)+", "side": "over"]
        questions.append(question)
        var actuals = try XCTUnwrap(props["actuals"] as? [[String: Any]])
        var actual = try XCTUnwrap(actuals.first { ($0["actual_key"] as? String)?.hasPrefix("s:aaron judge|") == true })
        actual["actual_key"] = "s:aaron judge|hits|full_game"; actual["stat_key"] = "hits"
        actuals.append(actual)
        props["stats"] = stats; props["questions"] = questions; props["actuals"] = actuals
        body["after_player_props"] = props
        return try XCTUnwrap(Self.decode(body).afterPlayerProps)
    }

    private func openJudge() throws -> (EventPropsMatrixSelection.OpenQuestion, DuringPropRow) {
        let row = try XCTUnwrap(during().rows.first { $0.questionKey == Self.judgeTwoHits })
        return (EventPropsMatrixSelection.OpenQuestion(row), row)
    }

    // MARK: - The rule

    func testAServedQuestionStaysLiveEvenAtTheFinal() throws {
        let (open, row) = try openJudge()
        for ended in [false, true] {
            XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: try during(), after: try after(), gameEnded: ended),
                           .live(row))
        }
    }

    func testAQuestionDroppedMidGameIsStillWithdrawn() throws {
        let (open, _) = try openJudge()
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: Self.noRows, after: nil, gameEnded: false), .withdrawn)
        // Even with an After body around: the page's phase, not the payload
        // shape, says the game is still on.
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(
            open, during: Self.noRows, after: try afterWithJudgeTwoHits(), gameEnded: false), .withdrawn)
    }

    func testAtTheFinalWithNoAfterVersionTheGameIsOver() throws {
        let (open, _) = try openJudge()
        let after = try after()
        XCTAssertNil(AfterPropsMatrixLayout.resolve(open, in: after), "control: the After body grades no Hits question")
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: Self.noRows, after: after, gameEnded: true), .gameEnded)
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: Self.noRows, after: nil, gameEnded: true), .gameEnded)
    }

    func testAtTheFinalTheSameAfterQuestionIsFollowed() throws {
        let (open, _) = try openJudge()
        let after = try afterWithJudgeTwoHits()
        let question = try XCTUnwrap(after.questions.first { $0.questionKey == Self.judgeTwoHits })
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: Self.noRows, after: after, gameEnded: true),
                       .after(question))
    }

    func testAnAfterSiblingIsNeverFollowed() throws {
        let (open, _) = try openJudge()
        // Judge's 3+ hits graded, his 2+ not: a different question.
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(
            open, during: Self.noRows, after: try afterWithJudgeTwoHits(count: 3), gameEnded: true), .gameEnded)
    }

    func testAnUnsupportedAfterContractIsNotFollowed() throws {
        let (open, _) = try openJudge()
        let after = try afterWithJudgeTwoHits()
        let unsupported = AfterPlayerProps(contract: "10237.v0", stats: after.stats, actuals: after.actuals,
                                           questions: after.questions, coverage: after.coverage)
        XCTAssertEqual(EventPropsMatrixDetailContent.resolve(open, during: Self.noRows, after: unsupported, gameEnded: true),
                       .gameEnded)
    }

    func testOpeningKeepsThePlayersNameTheReaderTapped() throws {
        let (_, row) = try openJudge()
        var selection = EventPropsMatrixSelection()
        _ = selection.open(row)
        XCTAssertEqual(selection.openedSubjectLabel, "Aaron Judge")
    }

    // MARK: - Wiring: the one During mount hands the sheet all three

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck").appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheMatrixSheetAndTheDuringMountCarryTheNameTheAfterBodyAndThePhase() throws {
        let matrix = try source("Components/EventPropsMatrixView.swift")
        let sheet = try XCTUnwrap(matrix.range(of: ".sheet(item: $selection.openQuestion"))
        let call = String(matrix[sheet.upperBound...].prefix(400))
        for argument in ["subjectLabel: selection.openedSubjectLabel", "afterProps: afterProps", "gameEnded: gameEnded",
                         "displayAsOf: displayAsOf"] {
            XCTAssertTrue(call.contains(argument), "the matrix's sheet drops \(argument): \(call)")
        }
        let page = try source("Views/EventDetailView.swift")
        let mount = try XCTUnwrap(page.range(of: "EventPropsMatrixView("))
        let close = try XCTUnwrap(page.range(of: "onDetailPresentationChanged:", range: mount.upperBound..<page.endIndex))
        let args = String(page[mount.upperBound..<close.lowerBound])
        XCTAssertTrue(args.contains("afterProps: AfterPropsMatrixLayout.drawable(vm.gameMarkets?.afterPlayerProps)"), args)
        XCTAssertTrue(args.contains("gameEnded: isFinished"), args)
        XCTAssertTrue(args.contains("|| AfterPropsMatrixLayout.drawable(vm.gameMarkets?.afterPlayerProps) != nil"), args)
    }

    // MARK: - Mounted: the reader's open sheet across the final

    private final class Feed: ObservableObject {
        @Published var during: DuringPlayerProps
        @Published var after: AfterPlayerProps?
        @Published var ended = false
        @Published var open: EventPropsMatrixSelection.OpenQuestion?
        var label: String?
        init(during: DuringPlayerProps) { self.during = during }
    }

    /// The matrix's own presentation, verbatim in shape (pinned by the wiring
    /// test above): the real `EventPropsMatrixDetailView`, kept up while the
    /// payload underneath changes.
    private struct Presenter: View {
        @ObservedObject var feed: Feed
        var body: some View {
            Color.clear.sheet(item: $feed.open) { open in
                EventPropsMatrixDetailView(
                    open: open, subjectLabel: feed.label,
                    props: feed.during, afterProps: feed.after, gameEnded: feed.ended,
                    // #10236 — the route body's capture minute (quotes
                    // observed 07:08Z), so the live 48% is current here.
                    displayAsOf: "2026-10-03T07:09:00Z".asDate
                )
            }
        }
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    /// The sheet as its reader sees it: the window's own composited, opaque
    /// pixels over the presentation's container, so the sheet's navigation
    /// bar (Close and the player's title) is read with its body. The sheet
    /// view's own hierarchy drawn into a transparent image carried only the
    /// glyph ink on iOS 26.5 — no grouped background, no bar, no title.
    private func sheetLines(_ host: UIViewController, _ name: String) throws -> [String] {
        let sheet = try XCTUnwrap(host.presentedViewController, "\(name): the question sheet is open")
        let window = try XCTUnwrap(sheet.view.window, "\(name): the sheet is in a window")
        let container = try XCTUnwrap(sheet.presentationController?.presentedView, "\(name): the sheet's container")
        let box = container.convert(container.bounds, to: window).intersection(window.bounds).integral
        let crop = try XCTUnwrap(box.isEmpty ? nil : box, "\(name): the sheet's container is on screen")
        let format = UIGraphicsImageRendererFormat(for: window.traitCollection)
        format.opaque = true
        let image = UIGraphicsImageRenderer(bounds: crop, format: format).image { _ in
            window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("props-final-sheet-10486-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Final sheet rendered evidence (#10486, route-harness data): \(url.path)")
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    /// The reader's verdict on a sheet that was open at the final: the
    /// player's name is still there and it never says the question was
    /// withdrawn or falls back to the generic title.
    private func keepsFinalContext(_ lines: [String]) -> Bool {
        let text = lines.joined(separator: " | ")
        return text.contains("Aaron Judge") && !text.contains("being offered")
            && !lines.contains { $0.trimmingCharacters(in: .whitespaces) == "Player prop" }
    }

    /// Opens Judge's 2+ hits from the live payload as the matrix does, then
    /// moves the payload to `final` and returns the open sheet's lines before
    /// and after — the same presentation, never re-opened.
    /// The presented sheet lives in a window of the app's foreground-active
    /// scene, as a reader's does (the MatrixPageReadingAnchor10236Tests host).
    private func sceneWindow(_ name: String) throws -> UIWindow {
        func activeScene() -> UIWindowScene? {
            UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
        }
        let deadline = CACurrentMediaTime() + 10
        while activeScene() == nil && CACurrentMediaTime() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        let scene = try XCTUnwrap(activeScene(), "\(name): the final sheet needs a foreground-active window scene")
        return UIWindow(windowScene: scene)
    }

    private func journey(_ name: String, to final: (Feed) throws -> Void) throws -> (before: [String], after: [String]) {
        let feed = Feed(during: try during())
        let host = hostForMeasurement(Presenter(feed: feed))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = try sceneWindow(name)
        let previousKeyWindow = window.windowScene?.windows.first { $0.isKeyWindow }
        window.frame = host.view.frame
        window.rootViewController = host; window.makeKeyAndVisible()
        defer { host.dismiss(animated: false); window.isHidden = true; previousKeyWindow?.makeKey() }
        settle(host, 0.3)
        let (_, row) = try openJudge()
        var selection = EventPropsMatrixSelection()
        let open = selection.open(row)
        feed.label = selection.openedSubjectLabel
        feed.open = open
        settle(host, 1.0)
        let sheet = try XCTUnwrap(host.presentedViewController, "\(name): the question sheet is open")
        let before = try sheetLines(host, "\(name)-open")
        try final(feed)
        settle(host, 1.0)
        XCTAssertTrue(host.presentedViewController === sheet, "\(name): the same sheet stays up across the final")
        return (before, try sheetLines(host, "\(name)-final"))
    }

    func testAnOpenSheetAtTheFinalKeepsThePlayerAndSaysTheGameIsOver() throws {
        let after = try after()
        let (before, final) = try journey("game-over") { feed in
            feed.during = Self.noRows; feed.after = after; feed.ended = true
        }
        XCTAssertTrue(before.joined(separator: " ").contains("Aaron Judge") && before.contains { $0.contains("48%") },
                      "control: the live question was open: \(before)")
        XCTAssertTrue(keepsFinalContext(final), "the final sheet lost its context: \(final)")
        XCTAssertTrue(final.contains { $0.contains("This game is over") }, "no game-over line: \(final)")
        XCTAssertFalse(final.contains { $0.contains("48%") }, "a live price survived the final: \(final)")
    }

    /// Negative control on the same mounted journey: the game is still on, so
    /// the dropped question reads as withdrawn (#10236 step 10) — and the
    /// final-state verdict above refuses exactly that sheet.
    func testAQuestionDroppedMidGameStillReadsWithdrawnAndTheVerdictRefusesIt() throws {
        let (_, final) = try journey("withdrawn") { feed in feed.during = Self.noRows }
        XCTAssertTrue(final.contains { $0.contains("being offered right now") }, "mid-game withdrawal lost: \(final)")
        XCTAssertTrue(final.joined(separator: " ").contains("Aaron Judge"), "the player's name is kept here too: \(final)")
        XCTAssertFalse(keepsFinalContext(final), "the final-state verdict must refuse the withdrawal sentence: \(final)")
    }

    func testAnOpenSheetAtTheFinalFollowsTheSameAfterQuestion() throws {
        let after = try afterWithJudgeTwoHits()
        let (_, final) = try journey("follows-after") { feed in
            feed.during = Self.noRows; feed.after = after; feed.ended = true
        }
        XCTAssertTrue(keepsFinalContext(final), "the followed sheet lost its context: \(final)")
        XCTAssertTrue(final.contains { $0.uppercased().contains("RESULT") }, "the After detail is not shown: \(final)")
        XCTAssertFalse(final.contains { $0.contains("This game is over") }, "followed After yet said game over: \(final)")
    }
}
