import Foundation
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13770 part 2: My Stuff rows must stay readable on iPad (2-column masonry on
/// wide canvases, single-column capped at 560 pt) without changing iPhone.
@MainActor
final class MyStuffIPadRowWidth13770Tests: XCTestCase {

    func testLayoutBreakpointsAcrossIPhoneSplitViewAndIPadWidths() {
        // iPhone & Split View remain single-column
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 320, itemCount: 5, isAccessibilitySize: false), 1)
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 390, itemCount: 5, isAccessibilitySize: false), 1)
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 500, itemCount: 5, isAccessibilitySize: false), 1)
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 680, itemCount: 5, isAccessibilitySize: false), 1)

        // iPad regular widths use 2 columns when section has >= 2 items
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 834, itemCount: 5, isAccessibilitySize: false), 2)
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 1194, itemCount: 2, isAccessibilitySize: false), 2)

        // Single-item section stays 1 column capped at 560 pt
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 834, itemCount: 1, isAccessibilitySize: false), 1)
        XCTAssertEqual(
            MyStuffLandingLayout13770.containerMaxWidth(availableWidth: 834, hasMultiItemSection: false, isAccessibilitySize: false),
            560
        )
        XCTAssertEqual(
            MyStuffLandingLayout13770.containerMaxWidth(availableWidth: 834, hasMultiItemSection: true, isAccessibilitySize: false),
            880
        )

        // Accessibility sizes collapse to 1 readable column (<= 560 pt)
        XCTAssertEqual(MyStuffLandingLayout13770.columnCount(availableWidth: 1194, itemCount: 5, isAccessibilitySize: true), 1)
        XCTAssertEqual(
            MyStuffLandingLayout13770.containerMaxWidth(availableWidth: 1194, hasMultiItemSection: true, isAccessibilitySize: true),
            560
        )
    }

    func testIPadMyStuffCardRowsStayUnderSingleColumnCapAndRenderCleanly() throws {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveTime = iso.string(from: now.addingTimeInterval(-1800))
        let soonTime = iso.string(from: now.addingTimeInterval(7200))

        let eventsJSON = """
        [
          {"id": 9137701, "sport": "icehockey_nhl", "sport_name": "NHL", "home_team": "Boston Bruins", "away_team": "Winnipeg Jets", "commence_time": "\(liveTime)", "status": "live", "home_score": 2, "away_score": 1, "espn": {"period": "P2", "clock": "08:12"}, "current_odds": {"home_probability": 0.61, "away_probability": 0.39}},
          {"id": 9137702, "sport": "basketball_nba", "sport_name": "NBA", "home_team": "Boston Celtics", "away_team": "Atlanta Hawks", "commence_time": "\(soonTime)", "status": "scheduled", "current_odds": {"home_probability": 0.75, "away_probability": 0.25}},
          {"id": 9137703, "sport": "icehockey_nhl", "sport_name": "NHL", "home_team": "Boston Bruins", "away_team": "Toronto Maple Leafs", "commence_time": "\(soonTime)", "status": "scheduled", "current_odds": {"home_probability": 0.61, "away_probability": 0.39}},
          {"id": 9137704, "sport": "americanfootball_ncaaf", "sport_name": "NCAAF", "home_team": "Notre Dame", "away_team": "Syracuse", "commence_time": "\(soonTime)", "status": "scheduled", "current_odds": {"home_probability": 0.93, "away_probability": 0.07}}
        ]
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let events = try dec.decode([FeedEventData].self, from: Data(eventsJSON.utf8))

        let snapshot = MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [(events[0], false)],
            nextEvents: Array(events.dropFirst()).map { ($0, false) }
        )
        let suite = "MyStuffIPadRowWidth13770Tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        let followManager = FollowManager295A(defaults: defaults)
        _ = followManager.toggle(.team(slug: "boston-celtics", teamId: 2, name: "Boston Celtics", sportKey: "basketball_nba"))
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        let authManager = AuthManager()

        for width in [390.0, 834.0, 1194.0] {
            let landing = NavigationStack {
                MyStuffLandingView295A(
                    landingVM: MyStuffLandingViewModel295A(preloaded: snapshot),
                    path: .constant(NavigationPath()),
                    onOpenDiscover: {},
                    onManagePins: {},
                    onRefresh: {}
                )
                .navigationTitle("My Stuff")
            }
            .environment(\.followManager295A, followManager)
            .environmentObject(pinManager)
            .environmentObject(authManager)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .frame(width: width)

            let host = hostForMeasurement(landing, at: .large)
            let fitted = host.sizeThatFits(in: CGSize(width: width, height: 1400))
            XCTAssertLessThanOrEqual(fitted.width, width + 1.0)
        }

        // Verify per-column math: 2 columns in 880 maxWidth -> card width 418 pt (vs old 728 pt)
        let effective834 = min(CGFloat(834), MyStuffLandingLayout13770.multiColumnMaxWidth)
        let cardWidth834 = (effective834 - 32 - MyStuffLandingLayout13770.cardSpacing) / 2
        XCTAssertLessThanOrEqual(cardWidth834, 420)

        let effective1194 = min(CGFloat(1194), MyStuffLandingLayout13770.multiColumnMaxWidth)
        let cardWidth1194 = (effective1194 - 32 - MyStuffLandingLayout13770.cardSpacing) / 2
        XCTAssertLessThanOrEqual(cardWidth1194, 430)

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13770_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

            let viewBuilder: (ColorScheme, DynamicTypeSize, Bool) -> AnyView = { scheme, dt, wide in
                AnyView(
                    MyStuffLandingView295A(
                        landingVM: MyStuffLandingViewModel295A(preloaded: snapshot),
                        path: .constant(NavigationPath()),
                        onOpenDiscover: {},
                        onManagePins: {},
                        onRefresh: {}
                    )
                    .environment(\.followManager295A, followManager)
                    .environmentObject(pinManager)
                    .environmentObject(authManager)
                    .environment(\.horizontalSizeClass, wide ? .regular : .compact)
                    .environment(\.colorScheme, scheme)
                )
            }

            // "Before" comparison card stack matching old master (.frame(maxWidth: 760) single column)
            let before834 = VStack(alignment: .leading, spacing: 10) {
                ForEach(events, id: \.id) { ev in
                    EventCardView(event: ev, reason: nil, personalizationReasons: nil, headline: nil)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(DS.cardBg))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
                }
            }
            .padding(16)
            .frame(width: 760)
            .frame(width: 834)
            .background(DS.surface)
            .environment(\.followManager295A, followManager)
            .environmentObject(pinManager)
            .environmentObject(authManager)
            .environment(\.colorScheme, .light)

            let beforeRenderer = rendererForMeasurement(before834, at: .large)
            beforeRenderer.scale = 2.0
            let beforeImg = try XCTUnwrap(beforeRenderer.uiImage)
            try XCTUnwrap(beforeImg.pngData()).write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-ipad-834-light.png"))

            let window: UIWindow = {
                if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                    return UIWindow(windowScene: scene)
                }
                return UIWindow(frame: CGRect(x: 0, y: 0, width: 1194, height: 960))
            }()
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }

            let renders: [(String, CGFloat, CGFloat, ColorScheme, DynamicTypeSize, Bool)] = [
                ("ipad-834-light.png", 834, 960, .light, .large, true),
                ("ipad-834-dark.png", 834, 960, .dark, .large, true),
                ("ipad-1194-light.png", 1194, 920, .light, .large, true),
                ("iphone-390-light.png", 390, 960, .light, .large, false),
            ]
            for (name, w, h, scheme, dt, wide) in renders {
                let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
                let rendered = viewBuilder(scheme, dt, wide)
                    .frame(width: w, height: h)
                    .clipped()
                let host = hostForMeasurement(rendered, at: dt)
                host.overrideUserInterfaceStyle = uiStyle
                host.traitOverrides.horizontalSizeClass = wide ? .regular : .compact
                window.overrideUserInterfaceStyle = uiStyle
                window.frame = CGRect(x: 0, y: 0, width: w, height: h)
                window.rootViewController = host
                host.view.frame = window.bounds
                for _ in 0..<4 {
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                }
                let fmt = UIGraphicsImageRendererFormat()
                fmt.scale = 2.0
                fmt.opaque = true
                let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                    let bg = scheme == .dark ? UIColor(white: 0.07, alpha: 1.0) : UIColor(white: 0.96, alpha: 1.0)
                    bg.setFill()
                    ctx.fill(host.view.bounds)
                    if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                        host.view.layer.render(in: ctx.cgContext)
                    }
                }
                try XCTUnwrap(img.pngData()).write(to: URL(fileURLWithPath: outDir).appendingPathComponent(name))
            }
        }
    }
}
