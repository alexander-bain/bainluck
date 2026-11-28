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

    private func renderAndRecognize(
        _ view: some View,
        width: CGFloat,
        size: DynamicTypeSize = .accessibility5
    ) throws -> (UIImage, [String]) {
        let wrapped = view
            .frame(width: width)
            .padding(8)
            .background(Color.black)
            .environment(\.colorScheme, .dark)

        let host = hostForMeasurement(wrapped, at: size)
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
        XCTAssertTrue(comp.contains("isA11y ? .system(size: 13.5, weight: .semibold) : .headline"))
        XCTAssertTrue(comp.contains(".lineLimit(isA11y ? 2 : 1)"))
        XCTAssertFalse(comp.contains(".font(.subheadline.weight(.semibold))"))
    }

    func testExportDefaultAndAX5ParityRendersIfRequested() throws {
        guard let outDirPath = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_AX5_SHEET_DIR"],
              !outDirPath.isEmpty else { return }
        let outDir = URL(fileURLWithPath: outDirPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        func save(_ name: String, _ image: UIImage) throws {
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: outDir.appendingPathComponent(name))
        }

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
        let liveHero = WatchMatchupGameHeroModel297A(
            stage: .during,
            topBadgeText: "Bot 7th",
            isLive: true,
            isThreeWaySoccer: false,
            isTiedFinal: false,
            away: .init(abbreviation: "LA", shortName: "Dodgers", teamID: 2, crestPNG: nil, fillHex: "#005A9C", inkHex: "#FFFFFF", barHex: "#005A9C", currentPercentText: "36%", currentShare: 0.36, score: 2, pregameText: nil, isWinner: false, isLoser: false),
            home: .init(abbreviation: "SF", shortName: "Giants", teamID: 1, crestPNG: nil, fillHex: "#FD5A1E", inkHex: "#FFFFFF", barHex: "#FD5A1E", currentPercentText: "64%", currentShare: 0.64, score: 4, pregameText: nil, isWinner: false, isLoser: false),
            drawPercentText: nil, drawShare: nil, drawPregameText: nil,
            centerScoreText: "2–4", liveScoreExplanation: nil,
            finalScoreUnavailable: false, probabilityUnavailableText: nil,
            bottomSummaryText: nil, scoreAsOfText: "Score 45s ago", probabilityAsOfText: "1m ago"
        )
        let upcomingHero = WatchMatchupGameHeroModel297A(
            stage: .before,
            topBadgeText: "Sun 1:25 PM",
            isLive: false,
            isThreeWaySoccer: false,
            isTiedFinal: false,
            away: .init(abbreviation: "BUF", shortName: "Bills", teamID: 12, crestPNG: nil, fillHex: "#00338D", inkHex: "#FFFFFF", barHex: "#00338D", currentPercentText: "42%", currentShare: 0.42, score: nil, pregameText: nil, isWinner: false, isLoser: false),
            home: .init(abbreviation: "KC", shortName: "Chiefs", teamID: 11, crestPNG: nil, fillHex: "#E31837", inkHex: "#FFFFFF", barHex: "#E31837", currentPercentText: "58%", currentShare: 0.58, score: nil, pregameText: nil, isWinner: false, isLoser: false),
            drawPercentText: nil, drawShare: nil, drawPregameText: nil,
            centerScoreText: nil, liveScoreExplanation: nil,
            finalScoreUnavailable: false, probabilityUnavailableText: nil,
            bottomSummaryText: nil, scoreAsOfText: nil, probabilityAsOfText: "As of 8:55 AM"
        )
        let finalHero = WatchMatchupGameHeroModel297A(
            stage: .after,
            topBadgeText: "FINAL",
            isLive: false,
            isThreeWaySoccer: false,
            isTiedFinal: false,
            away: .init(abbreviation: "NYK", shortName: "Knicks", teamID: 22, crestPNG: nil, fillHex: "#F58426", inkHex: "#FFFFFF", barHex: "#F58426", currentPercentText: nil, currentShare: nil, score: 108, pregameText: "Pregame 47%", isWinner: false, isLoser: true),
            home: .init(abbreviation: "BOS", shortName: "Celtics", teamID: 21, crestPNG: nil, fillHex: "#007A33", inkHex: "#FFFFFF", barHex: "#007A33", currentPercentText: nil, currentShare: nil, score: 114, pregameText: "Pregame 53%", isWinner: true, isLoser: false),
            drawPercentText: nil, drawShare: nil, drawPregameText: nil,
            centerScoreText: "108–114", liveScoreExplanation: nil,
            finalScoreUnavailable: false, probabilityUnavailableText: nil,
            bottomSummaryText: nil, scoreAsOfText: "Score as of 30m", probabilityAsOfText: nil
        )

        for spec in [
            (tag: "41mm-default", width: CGFloat(176), dt: DynamicTypeSize.large),
            (tag: "45mm-default", width: CGFloat(198), dt: DynamicTypeSize.large),
            (tag: "41mm-ax5", width: CGFloat(176), dt: DynamicTypeSize.accessibility5),
        ] {
            let contentW = spec.width - 12
            let isA11y = spec.dt.isAccessibilitySize

            let (tileImg, _) = try renderAndRecognize(
                WatchWristTileView12616(model: liveTile, isAccessibilitySize: isA11y) { EmptyView() },
                width: contentW,
                size: spec.dt
            )
            try save("\(spec.tag)-tile.png", tileImg)

            let (liveImg, _) = try renderAndRecognize(
                WatchMatchupGamePageHeroView297A(model: liveHero, caseWidth: spec.width),
                width: contentW,
                size: spec.dt
            )
            try save("\(spec.tag)-live.png", liveImg)

            let (upImg, _) = try renderAndRecognize(
                WatchMatchupGamePageHeroView297A(model: upcomingHero, caseWidth: spec.width),
                width: contentW,
                size: spec.dt
            )
            try save("\(spec.tag)-upcoming.png", upImg)

            let (finImg, _) = try renderAndRecognize(
                WatchMatchupGamePageHeroView297A(model: finalHero, caseWidth: spec.width),
                width: contentW,
                size: spec.dt
            )
            try save("\(spec.tag)-final.png", finImg)

            let (actImg, actLines) = try renderAndRecognize(
                VStack(alignment: .leading, spacing: 8) {
                    Label {
                        Text("Choose outcome (4)")
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    } icon: { Image(systemName: "list.bullet") }
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, isA11y ? 10 : 8)
                    .padding(.vertical, isA11y ? 8 : 0)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))

                    Label {
                        Text("Refresh pins")
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    } icon: { Image(systemName: "arrow.clockwise") }
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, isA11y ? 10 : 8)
                    .padding(.vertical, isA11y ? 8 : 0)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))

                    Text("Clear selection")
                        .font(.footnote).foregroundStyle(.primary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, isA11y ? 10 : 8)
                        .padding(.vertical, isA11y ? 8 : 0)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .contentShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary, lineWidth: 1))
                },
                width: contentW,
                size: spec.dt
            )
            XCTAssertFalse(actLines.contains(where: { $0.contains("…") || $0.contains("...") }), "\(spec.tag) actions ellipsis: \(actLines)")
            try save("\(spec.tag)-actions.png", actImg)
        }
    }
}
