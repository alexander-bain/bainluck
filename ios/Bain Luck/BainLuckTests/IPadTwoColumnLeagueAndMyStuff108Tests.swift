import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class TraitContainer108: UIViewController {
    private let child: UIViewController
    private let traits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.traits = traits
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        child.view.backgroundColor = .clear
        view.addSubview(child.view)
        setOverrideTraitCollection(traits, forChild: child)
        child.didMove(toParent: self)
    }
}
#endif

/// 1.0.8 Item 1 — Regular-width two-column layout for `LeagueGridView` and `MyStuffView`,
/// single column on compact/Split View/Slide Over/AX, and left-to-right-then-down VO order.
@MainActor
final class IPadTwoColumnLeagueAndMyStuff108Tests: XCTestCase {

    func testRegularWidthGateMatchesPhoneSplitViewSlideOverAndAccessibilityRules() {
        // Compact widths stay 1 column regardless of point width.
        for width: CGFloat in [320, 390, 440, 678, 834] {
            for dt: DynamicTypeSize in [.large, .xxxLarge, .accessibility3] {
                XCTAssertEqual(
                    RegularWidthTwoColumnGrid108.columnCount(
                        horizontalSizeClass: .compact,
                        dynamicTypeSize: dt,
                        availableWidth: width
                    ),
                    1
                )
            }
        }

        // Narrow regular widths (<700 pt inner, e.g. Split View) stay 1 column.
        for width: CGFloat in [0, 390, 620, 699] {
            XCTAssertEqual(
                RegularWidthTwoColumnGrid108.columnCount(
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: .large,
                    availableWidth: width
                ),
                1
            )
        }

        // Accessibility Dynamic Type sizes stay 1 column even on 13-inch iPad landscape.
        for ax: DynamicTypeSize in [.accessibility1, .accessibility3, .accessibility5] {
            XCTAssertEqual(
                RegularWidthTwoColumnGrid108.columnCount(
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: ax,
                    availableWidth: 1200
                ),
                1
            )
        }

        // Regular width >= 700 pt inner uses 2 columns across standard text sizes.
        for width: CGFloat in [700, 798, 960, 1280] {
            for dt: DynamicTypeSize in [.xSmall, .large, .xxxLarge] {
                XCTAssertEqual(
                    RegularWidthTwoColumnGrid108.columnCount(
                        horizontalSizeClass: .regular,
                        dynamicTypeSize: dt,
                        availableWidth: width
                    ),
                    2
                )
            }
        }
    }

    func testSortPriorityAndLayoutPreserveLeftToRightThenDownOrder() throws {
        var recordedFrames: [Int: CGRect] = [:]
        let heights: [CGFloat] = [90, 130, 110, 80, 100, 95]

        let view = TwoColumnMasonryLayout108(spacing: 12) {
            ForEach(0..<heights.count, id: \.self) { index in
                Color.blue
                    .frame(height: heights[index])
                    .background(
                        GeometryReader { geo in
                            Color.clear.preference(
                                key: CardFramePreferenceKey108.self,
                                value: [index: geo.frame(in: .named("grid"))]
                            )
                        }
                    )
                    .accessibilitySortPriority(RegularWidthTwoColumnGrid108.sortPriority(index: index))
            }
        }
        .coordinateSpace(name: "grid")
        .onPreferenceChange(CardFramePreferenceKey108.self) { recordedFrames = $0 }
        .frame(width: 800)

        let host = hostForMeasurement(view, at: .large)
        let size = host.sizeThatFits(in: CGSize(width: 800, height: 1000))
        host.view.frame = CGRect(origin: .zero, size: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        XCTAssertEqual(recordedFrames.count, heights.count)
        let f0 = try XCTUnwrap(recordedFrames[0])
        let f1 = try XCTUnwrap(recordedFrames[1])
        let f2 = try XCTUnwrap(recordedFrames[2])
        let f3 = try XCTUnwrap(recordedFrames[3])

        // Even indices in left column, odd indices in right column; equal top within each pair.
        XCTAssertLessThan(f0.minX, f1.minX)
        XCTAssertLessThan(f2.minX, f3.minX)
        XCTAssertEqual(f0.minY, f1.minY, accuracy: 0.5)
        XCTAssertEqual(f2.minY, f0.maxY + 12, accuracy: 0.5, "short left card packs at spacing instead of row stretching")
        XCTAssertEqual(f3.minY, f1.maxY + 12, accuracy: 0.5)

        // Sort priority descends monotonically from index 0 -> n-1 (left-to-right, then down).
        for idx in 0..<(heights.count - 1) {
            XCTAssertGreaterThan(
                RegularWidthTwoColumnGrid108.sortPriority(index: idx),
                RegularWidthTwoColumnGrid108.sortPriority(index: idx + 1)
            )
        }
    }

    func testLeagueGridRendersTwoColumnsAtIPad13LandscapeAndOneColumnAt390Phone() throws {
        let json = """
        {
          "sport_key": "basketball_nba",
          "total_markets": 6,
          "sections": {
            "series": [
              { "id": 103, "name": "Eastern Conference Champion", "source": "kalshi", "outcome_count": 15, "top_outcomes": [{ "name": "Boston Celtics", "probability": 0.41 }, { "name": "Cleveland Cavaliers", "probability": 0.25 }] },
              { "id": 104, "name": "Western Conference Champion", "source": "polymarket", "outcome_count": 15, "top_outcomes": [{ "name": "Oklahoma City Thunder", "probability": 0.44 }, { "name": "Denver Nuggets", "probability": 0.18 }] }
            ],
            "awards": [
              { "id": 101, "name": "NBA MVP", "source": "kalshi", "outcome_count": 18, "top_outcomes": [{ "name": "Nikola Jokic", "probability": 0.34 }, { "name": "Shai Gilgeous-Alexander", "probability": 0.29 }] },
              { "id": 102, "name": "Rookie of the Year", "source": "polymarket", "outcome_count": 12, "top_outcomes": [{ "name": "Cooper Flagg", "probability": 0.52 }, { "name": "Dylan Harper", "probability": 0.19 }] },
              { "id": 105, "name": "Defensive Player of the Year", "source": "kalshi", "outcome_count": 10, "top_outcomes": [{ "name": "Victor Wembanyama", "probability": 0.61 }, { "name": "Chet Holmgren", "probability": 0.14 }] },
              { "id": 106, "name": "Coach of the Year", "source": "polymarket", "outcome_count": 20, "top_outcomes": [{ "name": "Mark Daigneault", "probability": 0.28 }, { "name": "Kenny Atkinson", "probability": 0.22 }] }
            ]
          },
          "upcoming_games": [
            { "id": 201, "external_id": "g1", "sport": "basketball_nba", "sport_name": "NBA", "away_team": "Boston Celtics", "home_team": "New York Knicks", "commence_time": "2026-11-24T00:00:00Z", "status": "scheduled", "current_odds": { "away_probability": 0.56, "home_probability": 0.44 } },
            { "id": 202, "external_id": "g2", "sport": "basketball_nba", "sport_name": "NBA", "away_team": "Denver Nuggets", "home_team": "Los Angeles Lakers", "commence_time": "2026-11-24T03:00:00Z", "status": "scheduled", "current_odds": { "away_probability": 0.52, "home_probability": 0.48 } }
          ],
          "recent_results": []
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let markets = try decoder.decode(LeagueMarketsResponse.self, from: Data(json.utf8))
        let vm = LeagueGridViewModel(slug: "nba", preloadedGrid: nil, preloadedMarkets: markets)
        let suiteName = "IPadTwoColumnLeagueAndMyStuff108.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pins = PinManager(defaults: defaults)

        let specs: [(name: String, width: CGFloat, height: CGFloat, sizeClass: UIUserInterfaceSizeClass)] = [
            ("108-league-grid-ipad13-1366.png", 1366, 900, .regular),
            ("108-league-grid-iphone-390.png", 390, 760, .compact),
        ]

        for spec in specs {
            let hosted = NavigationStack {
                LeagueGridView(slug: "nba", preloadedViewModel: vm)
            }
            .environmentObject(pins)
            .environment(\.horizontalSizeClass, spec.sizeClass == .regular ? .regular : .compact)
            .environment(\.colorScheme, .light)

            let child = hostForMeasurement(hosted, at: .large)
            let traits = UITraitCollection(traitsFrom: [
                UITraitCollection(horizontalSizeClass: spec.sizeClass),
                UITraitCollection(userInterfaceStyle: .light),
            ])
            let container = TraitContainer108(child: child, traits: traits)
            container.view.frame = CGRect(x: 0, y: 0, width: spec.width, height: spec.height)
            let window = UIWindow(frame: container.view.frame)
            window.rootViewController = container
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let img = UIGraphicsImageRenderer(bounds: container.view.bounds, format: fmt).image { _ in
                _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
            }
            XCTAssertGreaterThan(img.size.height, 400)
            let att = XCTAttachment(image: img)
            att.name = spec.name
            att.lifetime = .keepAlways
            add(att)
        }
    }
}

private struct CardFramePreferenceKey108: PreferenceKey {
    static var defaultValue: [Int: CGRect] = [:]
    static func reduce(value: inout [Int: CGRect], nextValue: () -> [Int: CGRect]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}
