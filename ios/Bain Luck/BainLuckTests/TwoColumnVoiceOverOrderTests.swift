import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class VoiceOverTraitContainer: UIViewController {
    private let child: UIViewController
    private let overrideTraits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.overrideTraits = traits
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
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}

private struct MockContainerHubServiceVO: ContainerHubLoading {
    let response: ContainerHubResponse
    let pairedSets: [PairedMetricSet]
    nonisolated func load(slug: String) async throws -> ContainerHubResponse { response }
    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] { pairedSets }
}

private nonisolated struct MockDiscoverFeedClientVO: DiscoverFeedProviding {
    let response: FeedResponse
    func fetchDiscoverFeed(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        response
    }
}

@MainActor
final class TwoColumnVoiceOverOrderTests: XCTestCase {

    override class func setUp() {
        super.setUp()
        setAutomation(true)
    }

    override class func tearDown() {
        setAutomation(false)
        super.tearDown()
    }

    private static func setAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    func testTwoColumnSetPageAndDiscoverReadLeftToRightThenDown() async throws {
        // 1. ContainerHubView (NFL Week 12)
        let nflURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("ContainerHubFixtures/live_nfl_week12_13417.json")
        let nflData = try Data(contentsOf: nflURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let nflResp = try decoder.decode(ContainerHubResponse.self, from: nflData)
        let nflTargetNames = ["Packers", "Bears", "Eagles", "Chiefs", "Broncos", "Giants", "Raiders", "Jets"]

        let hubView = ContainerHubView(
            slug: "nfl-2026-week-12",
            displayName: "NFL Week 12",
            service: MockContainerHubServiceVO(response: nflResp, pairedSets: [])
        )
        let hubOrder = try await collectTraversal(
            view: hubView,
            targetLabels: nflTargetNames,
            width: 834,
            height: 1210
        )
        print("MEASURED_CONTAINER_HUB_ORDER:", hubOrder)

        // 2. DiscoverView (6 markets)
        let feedItemsJSON = (1...6).map { i in
            """
            {"type":"futures","score":\(100 - i),"data":{"id":\(9000 + i),"name":"Question Card \(i) Alpha?","llm_sport_category":"politics","source":"kalshi","status":"open","top_outcomes":[{"id":\(90000 + i),"name":"Yes","probability":0.\(60 - i),"rank":1,"movement":0.01}],"outcome_count":1}}
            """
        }.joined(separator: ",")
        let feedJSON = """
        {"items":[\(feedItemsJSON)],"total":6,"limit":20,"offset":0,"has_more":false}
        """.data(using: .utf8)!
        let feedResp = try decoder.decode(FeedResponse.self, from: feedJSON)
        let client = MockDiscoverFeedClientVO(response: feedResp)
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        let place = MacReadingPlace<DiscoverViewModel>()
        _ = place.models(orMake: { vm })
        let discoverView = DiscoverView(macPlace: place)

        let discoverOrder = try await collectTraversal(
            view: discoverView,
            targetLabels: (1...6).map { "Question Card \($0) Alpha?" },
            width: 834,
            height: 1210
        )
        print("MEASURED_DISCOVER_ORDER:", discoverOrder)

        XCTAssertEqual(hubOrder, nflTargetNames, "ContainerHub VoiceOver order must go left-to-right then down")
        XCTAssertEqual(discoverOrder, (1...6).map { "Question Card \($0) Alpha?" }, "Discover VoiceOver order must go left-to-right then down")
    }

    func testUnequalHeightTwoColumnLayoutAndSingleColumnPreserveRankOrder() async throws {
        let items = (0..<12).map { idx in
            UnequalHeightCardVO(id: idx, label: "Unequal Card \(idx)", height: idx == 0 ? 280 : 64)
        }
        let twoColView = ScrollView {
            LazyMasonryColumns(
                range: 0..<items.count,
                columnCount: 2,
                spacing: 16
            ) { idx in
                let item = items[idx]
                Button(item.label) {}
                    .frame(maxWidth: .infinity, minHeight: item.height, maxHeight: item.height)
                    .accessibilityLabel(item.label)
            }
        }
        let unequalOrder = try await collectTraversal(
            view: twoColView,
            targetLabels: items.map(\.label),
            width: 834,
            height: 2400
        )
        XCTAssertEqual(unequalOrder, items.map(\.label), "Even across chunks and when right-column cards sit higher than row-2 left card, VoiceOver must visit left-to-right then down")

        // Single-column Discover at 390pt compact width preserves rank order
        let feedItemsJSON = (1...6).map { i in
            """
            {"type":"futures","score":\(100 - i),"data":{"id":\(9100 + i),"name":"Phone Card \(i) Beta?","llm_sport_category":"politics","source":"kalshi","status":"open","top_outcomes":[{"id":\(91000 + i),"name":"Yes","probability":0.\(60 - i),"rank":1,"movement":0.01}],"outcome_count":1}}
            """
        }.joined(separator: ",")
        let feedJSON = """
        {"items":[\(feedItemsJSON)],"total":6,"limit":20,"offset":0,"has_more":false}
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feedResp = try decoder.decode(FeedResponse.self, from: feedJSON)
        let vm = DiscoverViewModel(client: MockDiscoverFeedClientVO(response: feedResp), lastGood: nil, telemetry: nil)
        let place = MacReadingPlace<DiscoverViewModel>()
        _ = place.models(orMake: { vm })
        let phoneOrder = try await collectTraversal(
            view: DiscoverView(macPlace: place),
            targetLabels: (1...6).map { "Phone Card \($0) Beta?" },
            width: 390,
            height: 1600,
            horizontalSizeClass: .compact
        )
        XCTAssertEqual(phoneOrder, (1...6).map { "Phone Card \($0) Beta?" }, "Single-column Discover keeps rank order")
    }

    private func collectTraversal<V: View>(
        view: V,
        targetIds: [String] = [],
        targetLabels: [String] = [],
        width: CGFloat,
        height: CGFloat,
        horizontalSizeClass: UserInterfaceSizeClass = .regular
    ) async throws -> [String] {
        let uiSizeClass: UIUserInterfaceSizeClass = horizontalSizeClass == .compact ? .compact : .regular
        let root = NavigationStack { view }
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, horizontalSizeClass)
            .environment(\.colorScheme, .light)
            .environment(\.dynamicTypeSize, .large)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())
            .environmentObject(AuthManager())

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: uiSizeClass),
            UITraitCollection(userInterfaceStyle: .light),
        ])
        let host = hostForMeasurement(root, at: .large)
        let container = VoiceOverTraitContainer(child: host, traits: traits)
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<20 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 50_000_000)
        }

        var found: [String] = []
        var visited = Set<ObjectIdentifier>()

        func walk(_ node: NSObject) {
            let oid = ObjectIdentifier(node)
            guard !visited.contains(oid) else { return }
            visited.insert(oid)

            if let ax = node as? UIAccessibilityIdentification,
               let aid = ax.accessibilityIdentifier,
               targetIds.contains(aid),
               !found.contains(aid) {
                found.append(aid)
            }
            if let label = node.accessibilityLabel {
                for t in targetLabels where label.contains(t) && !found.contains(t) {
                    found.append(t)
                }
            }

            if let elements = node.accessibilityElements as? [NSObject], !elements.isEmpty {
                for el in elements { walk(el) }
                return
            }
            let count = node.accessibilityElementCount()
            if count != NSNotFound, count > 0 {
                for i in 0..<count {
                    if let el = node.accessibilityElement(at: i) as? NSObject {
                        walk(el)
                    }
                }
                return
            }
            if let v = node as? UIView {
                for sub in v.subviews { walk(sub) }
            }
        }

        walk(container.view)
        return found
    }
}

private struct UnequalHeightCardVO: Identifiable {
    let id: Int
    let label: String
    let height: CGFloat
}
#endif
