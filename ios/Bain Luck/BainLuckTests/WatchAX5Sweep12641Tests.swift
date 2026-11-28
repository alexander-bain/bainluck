import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Item 4 (#12641) — Watch `.accessibility5` largest-text sweep across the
/// Pins Home wrist tiles, Matchup Game Page heroes (Live / Upcoming / Final),
/// Unavailable complication view, and pinned action/sheet wrappers.
@MainActor
final class WatchAX5Sweep12641Tests: XCTestCase {
    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relative)
    }

    private func renderAndRecognize(_ view: some View, width: CGFloat) throws -> (UIImage, [String]) {
        let wrapped = view
            .frame(width: width)
            .padding(8)
            .background(Color.black)
            .environment(\.colorScheme, .dark)
            .environment(\.dynamicTypeSize, .accessibility5)

        let host = UIHostingController(rootView: wrapped)
        host.overrideUserInterfaceStyle = .dark
        let fitted = host.sizeThatFits(in: CGSize(width: width + 16, height: 1200))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: ceil(width + 16), height: ceil(max(fitted.height, 44))))

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .dark
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.2)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return (img, lines)
    }

    func testWristTilesAndMatchupHeroesRenderWithoutEllipsisAtAX5On41mmAnd45mm() throws {
        let now = Date(timeIntervalSince1970: 1_794_000_000)
        let liveTile = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "San Francisco Giants",
                awayTeam: "Los Angeles Dodgers",
                homeServedAbbreviation: "SF",
                awayServedAbbreviation: "LA",
                sportKey: "baseball_mlb",
                isLive: true,
                homeScore: 4,
                awayScore: 2,
                homeProbability: 0.64,
                awayProbability: 0.36,
                prematchHomeProbability: 0.51,
                prematchAwayProbability: 0.49,
                liveClockText: "Bot 7th",
                probabilityObservedAt: now.addingTimeInterval(-60),
                scoreObservedAt: now.addingTimeInterval(-45)
            ),
            now: now
        )
        let upcomingTile = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Kansas City Chiefs",
                awayTeam: "Buffalo Bills",
                homeServedAbbreviation: "KC",
                awayServedAbbreviation: "BUF",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 27,
                projectedAwayScore: 24,
                commenceTime: now.addingTimeInterval(3 * 3600),
                probabilityObservedAt: now.addingTimeInterval(-120)
            ),
            now: now
        )

        for watchCase in [(name: "41mm", width: CGFloat(176)), (name: "45mm", width: CGFloat(198))] {
            let contentWidth = watchCase.width - 12
            let (_, liveLines) = try renderAndRecognize(
                WatchWristTileView12616(model: liveTile, isAccessibilitySize: true) { EmptyView() },
                width: contentWidth
            )
            let liveJoined = liveLines.joined(separator: "\n")
            XCTAssertFalse(liveLines.contains(where: { $0.contains("…") || $0.contains("...") }), "\(watchCase.name) live tile ellipsis: \(liveJoined)")
            XCTAssertTrue(liveJoined.contains("64%"), "\(watchCase.name) live tile missing 64%: \(liveJoined)")

            let (_, upLines) = try renderAndRecognize(
                WatchWristTileView12616(model: upcomingTile, isAccessibilitySize: true) { EmptyView() },
                width: contentWidth
            )
            let upJoined = upLines.joined(separator: "\n")
            XCTAssertFalse(upLines.contains(where: { $0.contains("…") || $0.contains("...") }), "\(watchCase.name) upcoming tile ellipsis: \(upJoined)")
            XCTAssertTrue(upJoined.contains("58%"), "\(watchCase.name) upcoming tile missing 58%: \(upJoined)")

            let finalHero = WatchMatchupGameHeroModel297A(
                stage: .after,
                topBadgeText: "FINAL",
                isLive: false,
                isThreeWaySoccer: false,
                isTiedFinal: false,
                away: .init(abbreviation: "NYK", shortName: "Knicks", teamID: 22, crestPNG: nil, fillHex: "#F58426", inkHex: "#FFFFFF", barHex: "#F58426", currentPercentText: nil, currentShare: nil, score: 108, pregameText: "Pregame 47%", isWinner: false, isLoser: true),
                home: .init(abbreviation: "BOS", shortName: "Celtics", teamID: 21, crestPNG: nil, fillHex: "#007A33", inkHex: "#FFFFFF", barHex: "#007A33", currentPercentText: nil, currentShare: nil, score: 114, pregameText: "Pregame 53%", isWinner: true, isLoser: false),
                drawPercentText: nil,
                drawShare: nil,
                drawPregameText: nil,
                centerScoreText: "108–114",
                liveScoreExplanation: nil,
                finalScoreUnavailable: false,
                probabilityUnavailableText: nil,
                bottomSummaryText: nil,
                scoreAsOfText: "Score as of 30m",
                probabilityAsOfText: nil
            )
            let (_, heroLines) = try renderAndRecognize(
                WatchMatchupGamePageHeroView297A(model: finalHero, caseWidth: watchCase.width),
                width: contentWidth
            )
            let heroJoined = heroLines.joined(separator: "\n")
            XCTAssertFalse(heroLines.contains(where: { $0.contains("…") || $0.contains("...") }), "\(watchCase.name) final hero ellipsis: \(heroJoined)")
            XCTAssertTrue(heroJoined.contains("Won"), "\(watchCase.name) final hero missing Won: \(heroJoined)")
            XCTAssertTrue(heroJoined.contains("Lost"), "\(watchCase.name) final hero missing Lost: \(heroJoined)")
            XCTAssertTrue(heroJoined.contains("Pregame 53%"), "\(watchCase.name) final hero missing Pregame 53%: \(heroJoined)")
        }
    }

    func testPinnedHomeAndComplicationSourcesEnforceAX5WrappingAndSlotSafety() throws {
        let pinned = try String(contentsOf: Self.repoFile("BainLuckWatch Watch App/WatchPinnedHomeView12640.swift"), encoding: .utf8)
        XCTAssertTrue(pinned.contains(#"Text("Choose outcome (\(outcomeCount))")"#))
        XCTAssertTrue(pinned.contains(#".fixedSize(horizontal: false, vertical: true)"#))
        XCTAssertTrue(pinned.contains("NavigationLink {"))
        XCTAssertTrue(pinned.contains(".environment(\\.dynamicTypeSize, dynamicTypeSize)"))

        let tile = try String(contentsOf: Self.repoFile("Bain Luck/Utilities/WatchWristTile12616.swift"), encoding: .utf8)
        XCTAssertTrue(tile.contains("lineLimit(isAccessibilitySize ? nil : 2)"))
        XCTAssertTrue(tile.contains("if isAccessibilitySize {"))

        let comp = try String(contentsOf: Self.repoFile("BainLuckWatch Watch App/WatchSavedComplicationContent.swift"), encoding: .utf8)
        XCTAssertTrue(comp.contains(".font(.system(size: 13.5, weight: .semibold))"))
        XCTAssertFalse(comp.contains(".font(.subheadline.weight(.semibold))"))
    }
}
