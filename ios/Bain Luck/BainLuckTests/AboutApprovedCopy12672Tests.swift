import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// `#12672` (Decision 189; Atlas `#12744` `AboutPage189.tsx` reference) — Native About screen
/// carries the verbatim approved text, retires `"The same knowledge as a betting app. None of the pull."`,
/// prints `64%` as the sole percentage on the page (Truth-pillar invariant), keeps the single bottom
/// fine-print `"Picture credits"` link (`Ruling 195-A`), and renders cleanly at `390 px`.
@MainActor
final class AboutApprovedCopy12672Tests: XCTestCase {

    func testApprovedCopyMatches12672VerbatimAndRetiresOldTagline() {
        XCTAssertEqual(AboutCopy12672.heroTitle, "The real score for everything.")
        XCTAssertEqual(
            AboutCopy12672.heroSubtitle,
            "What the world thinks will happen, as one clear percentage."
        )
        XCTAssertEqual(
            AboutCopy12672.heroLead,
            "A scoreboard tells you who's ahead. It doesn't tell you who's going to win. Bain Luck does: for tonight's game, next year's election, the Oscars, the weather, the Fed."
        )
        XCTAssertEqual(AboutCopy12672.oneNumberTitle, "One number.")
        XCTAssertEqual(
            AboutCopy12672.oneNumberBody,
            "Every day, thousands of people commit to what they expect will happen. We read the prediction markets and the sportsbooks and blend them into a single chance for each outcome."
        )
        XCTAssertEqual(AboutCopy12672.howToReadTitle, "How to read it.")
        XCTAssertEqual(
            AboutCopy12672.howToReadBody,
            "64% means it happens about two times in three. It's the world's best guess, not a promise. Watch it move; the movement is the story."
        )
        XCTAssertEqual(AboutCopy12672.notBettingTitle, "Not betting.")
        XCTAssertEqual(
            AboutCopy12672.notBettingBody,
            "No odds to decode, no bets to place, nothing to buy."
        )
        XCTAssertEqual(AboutCopy12672.keepScoreTitle, "We keep score on ourselves.")
        XCTAssertEqual(
            AboutCopy12672.keepScoreBody,
            "Every finished game and settled market is checked against what we showed."
        )
        XCTAssertEqual(AboutCopy12672.keepScoreLink, "See how we've done.")
        XCTAssertEqual(AboutCopy12672.primaryCTA, "Start exploring")

        let joined = AboutCopy12672.allCopyStrings.joined(separator: "\n")
        XCTAssertFalse(joined.localizedCaseInsensitiveContains("None of the pull"))
        XCTAssertFalse(joined.localizedCaseInsensitiveContains("same knowledge as a betting app"))

        // Truth-pillar invariant (#12744): 64% is the sole numeric percentage printed anywhere in About copy.
        let regex = try! NSRegularExpression(pattern: #"\d+(?:\.\d+)?%"#)
        let matches = regex.matches(in: joined, range: NSRange(joined.startIndex..., in: joined))
            .compactMap { Range($0.range, in: joined).map { String(joined[$0]) } }
        XCTAssertFalse(matches.isEmpty)
        XCTAssertEqual(Set(matches), ["64%"], "Only the approved 64% illustration may appear on About: \(matches)")
    }

    func testAboutViewExportsFull390pxRender() throws {
        // Render full unscrolled content height at 390 px so every approved card, CTA,
        // and the final bottom fine-print row are visible in one 390 px sheet.
        let fullHeight: CGFloat = 1520
        let screen = NavigationStack {
            AboutView()
        }
        .environmentObject(NavigationCoordinator())
        .environment(\.colorScheme, .light)
        .frame(width: 390, height: fullHeight)

        let host = hostForMeasurement(screen, at: .large)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: fullHeight)

        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.25)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        XCTAssertEqual(Int(image.size.width.rounded()), 390)

        if let exportDir = ProcessInfo.processInfo.environment["ABOUT_12672_EXPORT_DIR"],
           !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: dirURL.appendingPathComponent("about-12672-approved-390.png"))
        }
    }
}
