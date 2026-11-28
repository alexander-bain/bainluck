import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// #13914 — Upright iPad Discover must keep two columns of cards (matching the
/// website's `sm:grid-cols-2` breakpoint) instead of collapsing into one oversized
/// column when split-view/sidebar panes narrow the detail area below 616 pt, while
/// keeping iPhone unchanged in one column.
@MainActor
final class DiscoverIPadPortraitTwoColumns13914Tests: XCTestCase {

    // MARK: - Breakpoint & Size-Class Unit Tests

    func testIPhoneCompactWidthsRemainSingleColumnUnchanged() {
        for width in [320.0, 375.0, 390.0, 402.0, 430.0, 440.0] {
            let area = DiscoverMasonry.cardAreaWidth(
                containerWidth: CGFloat(width),
                maxContentWidth: .infinity
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    horizontalSizeClass: .compact,
                    dynamicTypeSize: .large
                ),
                DiscoverMasonry.columnCount(availableWidth: area),
                "iPhone \(width) pt (.compact, area \(area)) must match legacy columnCount"
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    horizontalSizeClass: .compact
                ),
                1,
                "iPhone \(width) pt portrait must stay 1 column"
            )
        }
        // Compact landscape behaves identically to legacy `columnCount`.
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(
                availableWidth: 700,
                horizontalSizeClass: .compact
            ),
            DiscoverMasonry.columnCount(availableWidth: 700)
        )
    }

    func testIPadPortraitRegularWidthsResolveToTwoColumns() {
        // Upright iPad portrait with sidebar open (220-320 pt) or windowed/split panes,
        // plus web `sm:` 640 px equivalent (`608 pt` card area), must all resolve to 2 columns.
        let portraitDetailWidths: [CGFloat] = [500, 514, 560, 574, 600, 614, 640]
        for detailWidth in portraitDetailWidths {
            let area = DiscoverMasonry.cardAreaWidth(
                containerWidth: detailWidth,
                maxContentWidth: 800
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: .large
                ),
                2,
                "Regular iPad detail \(detailWidth) pt (card area \(area) pt) should show 2 columns"
            )
        }

        // Full-width upright iPad portrait (iPad mini 744, Air 820, Pro 11 834, Pro 13 1032)
        // clamped at Discover's 800 pt `contentMaxWidth` stays 2 columns.
        for fullWidth: CGFloat in [744, 820, 834, 1032, 1194] {
            let area = DiscoverMasonry.cardAreaWidth(
                containerWidth: fullWidth,
                maxContentWidth: 800
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    horizontalSizeClass: .regular
                ),
                2,
                "Full-width regular canvas \(fullWidth) pt (card area \(area) pt) should show 2 columns"
            )
        }
    }

    func testDiscoverColumnCountExactBoundariesAndAccessibilityGate() {
        // Exact boundary: 2 * 225 + 16 = 466 pt card area (498 pt detail width).
        XCTAssertEqual(DiscoverMasonry.regularTwoColumnMinimumCardWidth, 225)
        XCTAssertEqual(DiscoverMasonry.regularTwoColumnMinimumAreaWidth, 466)

        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 465, horizontalSizeClass: .regular),
            1
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 466, horizontalSizeClass: .regular),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 615, horizontalSizeClass: .regular),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 616, horizontalSizeClass: .regular),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 931, horizontalSizeClass: .regular),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 932, horizontalSizeClass: .regular),
            3
        )

        // Unknown / non-positive width never returns < 1 column.
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 0, horizontalSizeClass: .regular),
            1
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: -20, horizontalSizeClass: .regular),
            1
        )

        // Narrow regular panes (< 616 pt) fall back to 1 column at Accessibility Dynamic Type sizes
        // so oversized text never squeezes into 233-283 pt columns; wider panes (>= 616 pt) stay 2.
        for ax in [DynamicTypeSize.accessibility1, .accessibility3, .accessibility5] {
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: 542,
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: ax
                ),
                1,
                "Narrow regular 542 pt card area must stay 1 column at \(ax)"
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: 768,
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: ax
                ),
                2,
                "Full 768 pt card area stays 2 columns at \(ax)"
            )
        }
    }

    #if os(iOS)

    // MARK: - Deterministic Feed Stubs & Window Helpers

    private nonisolated struct StubDiscoverProvider13914: DiscoverFeedProviding {
        let response: FeedResponse
        func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            response
        }
    }

    private nonisolated struct EmptyMachineryLoader13914: MachineryPreviewLoading12288 {
        func loadPreview(user: AuthUser?) async throws -> [MachineryPreviewEntry] { [] }
    }

    private func makeTestFeed() throws -> (response: FeedResponse, cardTitles: [String]) {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let gameStart = iso.string(from: now.addingTimeInterval(7200))

        let json = """
        {
          "items": [
            {
              "type": "futures",
              "score": 96,
              "reason": "Claude leads Best AI at year-end at 65%",
              "headline": "Claude leads at 65%",
              "context_summary": "Claude leads Best AI at year-end at 65% across 2 sources",
              "data": {
                "id": 9139141,
                "name": "Best AI at year-end?",
                "llm_sport_category": "tech",
                "source": "kalshi",
                "source_count": 2,
                "sources": ["kalshi", "polymarket"],
                "market_tier": 1,
                "market_type": "field",
                "status": "open",
                "top_outcomes": [
                  {"id": 91391411, "name": "Gemini", "probability": 0.76, "rank": 1, "movement": 0.04},
                  {"id": 91391412, "name": "Anthropic", "probability": 0.53, "rank": 2, "movement": 0.02},
                  {"id": 91391413, "name": "OpenAI", "probability": 0.31, "rank": 3, "movement": -0.02}
                ],
                "outcome_count": 6
              }
            },
            {
              "type": "event",
              "score": 94,
              "data": {
                "id": 9139144,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "home_team": "Kansas City Chiefs",
                "away_team": "Buffalo Bills",
                "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
                "away_team_data": {"team_id": 2, "name": "Buffalo Bills", "short_name": "Bills", "abbreviation": "BUF", "primary_color": "#00338D"},
                "commence_time": "\(gameStart)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.59, "away_probability": 0.41}
              }
            },
            {
              "type": "bundle",
              "score": 92,
              "reason": "What happens next in AI?",
              "headline": "AI",
              "data": {
                "id": "theme:story:ai:9139143",
                "title": "AI",
                "kind": "theme",
                "story_key": "story:ai",
                "shared_question": "AI: Riemann Hypothesis & Prize",
                "item_count": 2,
                "member_ids": [91391431, 91391432],
                "items": [
                  {
                    "type": "futures",
                    "score": 92,
                    "reason": "73% yes",
                    "headline": "AI proves Riemann Hypothesis",
                    "data": {
                      "id": 91391431,
                      "name": "AI proves Riemann Hypothesis in 2026?",
                      "llm_sport_category": "tech",
                      "source": "polymarket",
                      "source_count": 1,
                      "sources": ["polymarket"],
                      "market_tier": 2,
                      "market_type": "yes_no",
                      "status": "open",
                      "top_outcomes": [
                        {"id": 913914311, "name": "Yes", "probability": 0.73, "rank": 1, "movement": 0.01}
                      ],
                      "outcome_count": 2
                    }
                  },
                  {
                    "type": "futures",
                    "score": 90,
                    "reason": "71% yes",
                    "headline": "Next Millennium Prize",
                    "data": {
                      "id": 91391432,
                      "name": "Next Millennium Prize solved by AI?",
                      "llm_sport_category": "tech",
                      "source": "kalshi",
                      "source_count": 1,
                      "sources": ["kalshi"],
                      "market_tier": 2,
                      "market_type": "yes_no",
                      "status": "open",
                      "top_outcomes": [
                        {"id": 913914321, "name": "Yes", "probability": 0.71, "rank": 1, "movement": 0.02}
                      ],
                      "outcome_count": 2
                    }
                  }
                ]
              }
            },
            {
              "type": "futures",
              "score": 89,
              "reason": "San Francisco 49ers leads NFL Super Bowl Winner at 16%",
              "headline": "49ers lead at 16%",
              "data": {
                "id": 9139145,
                "name": "NFL Super Bowl Winner",
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "llm_sport_category": "football",
                "source": "odds_api",
                "source_count": 2,
                "sources": ["odds_api", "polymarket"],
                "market_tier": 1,
                "market_type": "field",
                "status": "open",
                "top_outcomes": [
                  {"id": 91391451, "name": "San Francisco 49ers", "probability": 0.16, "rank": 1},
                  {"id": 91391452, "name": "Buffalo Bills", "probability": 0.14, "rank": 2},
                  {"id": 91391453, "name": "Baltimore Ravens", "probability": 0.11, "rank": 3}
                ],
                "outcome_count": 32
              }
            },
            {
              "type": "futures",
              "score": 86,
              "reason": "No change leads Fed Rate Cut in December at 56%",
              "headline": "No change leads at 56%",
              "data": {
                "id": 9139146,
                "name": "Fed Decision in December?",
                "llm_sport_category": "economics",
                "source": "kalshi",
                "source_count": 2,
                "sources": ["kalshi", "polymarket"],
                "market_tier": 2,
                "market_type": "field",
                "status": "open",
                "top_outcomes": [
                  {"id": 91391461, "name": "No change", "probability": 0.56, "rank": 1},
                  {"id": 91391462, "name": "25 bps cut", "probability": 0.38, "rank": 2}
                ],
                "outcome_count": 4
              }
            },
            {
              "type": "futures",
              "score": 84,
              "reason": "Next Claude Opus released before year-end at 96%",
              "headline": "96% chance before Dec 31",
              "context_summary": "Next Claude Opus released before year-end leads at 96%",
              "data": {
                "id": 9139142,
                "name": "Next Claude Opus (5.6+) released?",
                "llm_sport_category": "tech",
                "source": "polymarket",
                "source_count": 1,
                "sources": ["polymarket"],
                "market_tier": 1,
                "market_type": "yes_no",
                "status": "open",
                "top_outcomes": [
                  {"id": 91391421, "name": "Yes", "probability": 0.96, "rank": 1, "movement": 0.03}
                ],
                "outcome_count": 2
              }
            }
          ],
          "total": 6,
          "limit": 20,
          "offset": 0,
          "has_more": false,
          "edition": "ed-13914"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let resp = try decoder.decode(FeedResponse.self, from: json)
        let titles = [
            "year-end?",
            "Chiefs",
            "Riemann",
            "Super Bowl",
            "December",
            "Claude Opus",
        ]
        return (resp, titles)
    }

    /// Renders a realistic iPad sidebar rail beside the detail canvas in its own
    /// child UIViewController so `NavigationStack` keeps native iPad bar margins.
    private struct IPadSidebarRail13914: View {
        let colorScheme: ColorScheme

        private var sidebarBg: Color {
            colorScheme == .dark ? Color(red: 0.08, green: 0.09, blue: 0.11) : Color(uiColor: .secondarySystemGroupedBackground)
        }

        private var activeRowBg: Color {
            colorScheme == .dark ? Color.white.opacity(0.10) : Color.blue.opacity(0.12)
        }

        var body: some View {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    BainLuckMarkView(size: 18)
                    Text("Bain Luck")
                        .font(.headline.weight(.semibold))
                }
                .padding(.horizontal, 14)
                .padding(.top, 18)
                .padding(.bottom, 10)

                ForEach([
                    ("My Stuff", "person.fill", false),
                    ("Discover", "safari", true),
                    ("Sports", "rectangle.stack.fill", false),
                    ("Browse", "square.grid.2x2", false),
                    ("Search", "magnifyingglass", false),
                ], id: \.0) { title, icon, active in
                    HStack(spacing: 10) {
                        Image(systemName: icon)
                            .frame(width: 20)
                            .foregroundStyle(active ? .blue : .secondary)
                        Text(title)
                            .font(.subheadline.weight(active ? .semibold : .regular))
                            .foregroundStyle(active ? Color.primary : Color.secondary)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(active ? activeRowBg : .clear, in: RoundedRectangle(cornerRadius: 10))
                    .padding(.horizontal, 8)
                }
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(sidebarBg)
            .environment(\.colorScheme, colorScheme)
        }
    }

    /// Pre-fix (`300 pt` minimum card width -> `DiscoverMasonry.columnCount(availableWidth:)`)
    /// masonry harness used strictly for BEFORE comparison panels beside real `DiscoverView`.
    private struct LegacyBeforeDiscoverCanvas13914: View {
        let items: [FeedItem]
        let detailWidth: CGFloat
        let totalHeight: CGFloat
        let colorScheme: ColorScheme
        let horizontalSizeClass: UserInterfaceSizeClass

        var body: some View {
            let maxContentWidth: CGFloat = horizontalSizeClass == .regular ? 800 : .infinity
            let areaWidth = DiscoverMasonry.cardAreaWidth(
                containerWidth: detailWidth,
                maxContentWidth: maxContentWidth
            )
            let legacyCols = DiscoverMasonry.columnCount(availableWidth: areaWidth)
            NavigationStack {
                ScrollView {
                    VStack(spacing: 0) {
                        Group {
                            if legacyCols <= 1 {
                                LazyVStack(spacing: DiscoverMasonry.spacing) {
                                    ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                                        legacyCard(for: item)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                            } else {
                                LazyMasonryColumns(
                                    range: 0..<items.count,
                                    columnCount: legacyCols,
                                    spacing: DiscoverMasonry.spacing,
                                    horizontalAlignment: .center,
                                    cardAlignment: .center
                                ) { idx in
                                    legacyCard(for: items[idx])
                                }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom)
                    }
                    .frame(maxWidth: maxContentWidth)
                    .frame(maxWidth: .infinity)
                }
                .navigationTitle("Discover")
                .navigationBarTitleDisplayMode(.large)
            }
            .frame(width: detailWidth, height: totalHeight)
            .environment(\.colorScheme, colorScheme)
            .environment(\.horizontalSizeClass, horizontalSizeClass)
            .environment(\.dynamicTypeSize, .large)
        }

        @ViewBuilder
        private func legacyCard(for item: FeedItem) -> some View {
            let previewLike = DiscoverCardLikeAction420D(
                itemKey: "preview-\(item.id)",
                isLiked: false,
                onToggle: {}
            )
            if item.type == "bundle", let b = item.bundle {
                NativeGroupCard(
                    title: b.title,
                    items: b.items,
                    kind: b.kind,
                    theme: b.comparisonTheme,
                    sharedQuestion: b.sharedQuestion,
                    collectionRef: b.collectionRef,
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, previewLike)
                .environment(
                    \.discoverGroupBundleArt12840,
                    DiscoverBundleArtContext12840(
                        imageUrl: b.imageUrl,
                        imagePresentation: b.imagePresentation,
                        imageMonogram: b.imageMonogram
                    )
                )
            } else if item.type == "futures", let f = item.futures {
                NativeFuturesDiscoverCard(
                    data: f,
                    feedContext: DiscoverCaption.feedCaption(
                        contextSummary: item.contextSummary,
                        headline: item.headline,
                        reason: item.reason,
                        hookDescription: f.hookDescription
                    ),
                    expandedContext: DiscoverCaption.firstMeaningful([
                        f.hookDescription,
                        item.reason,
                        item.headline,
                    ]),
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, previewLike)
            } else if item.type == "event", let e = item.event {
                NativeEventDiscoverCard(
                    event: e,
                    feedContext: item.contextSummary ?? item.reason ?? item.headline,
                    expandedContext: item.reason ?? item.headline,
                    navigationPath: .constant(NavigationPath())
                )
                .environment(\.discoverCardLikeAction420D, previewLike)
            }
        }
    }

    private final class SplitLayoutContainer13914: UIViewController {
        private let sidebarChild: UIViewController?
        private let sidebarWidth: CGFloat
        private let detailChild: UIViewController
        private let traits: UITraitCollection

        init(
            sidebarChild: UIViewController?,
            sidebarWidth: CGFloat,
            detailChild: UIViewController,
            traits: UITraitCollection
        ) {
            self.sidebarChild = sidebarChild
            self.sidebarWidth = sidebarWidth
            self.detailChild = detailChild
            self.traits = traits
            super.init(nibName: nil, bundle: nil)
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }

        override func viewDidLoad() {
            super.viewDidLoad()
            let totalH = view.bounds.height
            let totalW = view.bounds.width
            if let sidebarChild, sidebarWidth > 0 {
                addChild(sidebarChild)
                sidebarChild.view.frame = CGRect(x: 0, y: 0, width: sidebarWidth, height: totalH)
                sidebarChild.view.autoresizingMask = [.flexibleHeight]
                view.addSubview(sidebarChild.view)
                setOverrideTraitCollection(traits, forChild: sidebarChild)
                sidebarChild.didMove(toParent: self)

                let divider = UIView(frame: CGRect(x: sidebarWidth, y: 0, width: 1, height: totalH))
                divider.backgroundColor = UIColor.separator
                divider.autoresizingMask = [.flexibleHeight]
                view.addSubview(divider)

                let detailX = sidebarWidth + 1
                addChild(detailChild)
                detailChild.view.frame = CGRect(x: detailX, y: 0, width: max(1, totalW - detailX), height: totalH)
                detailChild.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
                view.addSubview(detailChild.view)
                setOverrideTraitCollection(traits, forChild: detailChild)
                detailChild.didMove(toParent: self)
            } else {
                addChild(detailChild)
                detailChild.view.frame = view.bounds
                detailChild.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
                view.addSubview(detailChild.view)
                setOverrideTraitCollection(traits, forChild: detailChild)
                detailChild.didMove(toParent: self)
            }
        }
    }

    private func renderAndMeasure<V: View>(
        _ detailView: V,
        sidebarWidth: CGFloat = 0,
        outerSize: CGSize,
        detailSizeClass: UserInterfaceSizeClass,
        colorScheme: ColorScheme,
        cardTitles: [String]
    ) async -> (image: UIImage, titleFrames: [String: CGRect]) {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiSizeClass: UIUserInterfaceSizeClass = detailSizeClass == .compact ? .compact : .regular
        let detailW = sidebarWidth > 0 ? max(1, outerSize.width - sidebarWidth - 1) : outerSize.width

        let styledDetail = detailView
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .large)
            .environment(\.horizontalSizeClass, detailSizeClass)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(allowLegacyGuestPins: false))
            .environmentObject(AuthManager(restoreOnInit: false))
            .frame(width: detailW, height: outerSize.height, alignment: .topLeading)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: uiSizeClass),
            UITraitCollection(userInterfaceStyle: uiStyle),
        ])
        let detailHost = hostForMeasurement(styledDetail, at: .large)
        detailHost.overrideUserInterfaceStyle = uiStyle
        detailHost.traitOverrides.horizontalSizeClass = uiSizeClass

        let sidebarHost: UIViewController? = sidebarWidth > 0
            ? {
                let sHost = hostForMeasurement(IPadSidebarRail13914(colorScheme: colorScheme), at: .large)
                sHost.overrideUserInterfaceStyle = uiStyle
                sHost.traitOverrides.horizontalSizeClass = uiSizeClass
                return sHost
            }()
            : nil

        let container = SplitLayoutContainer13914(
            sidebarChild: sidebarHost,
            sidebarWidth: sidebarWidth,
            detailChild: detailHost,
            traits: traits
        )
        let bounds = CGRect(origin: .zero, size: outerSize)
        container.view.frame = bounds

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<10 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }

        var titleFrames: [String: CGRect] = [:]
        if let cg = image.cgImage {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            let handler = VNImageRequestHandler(cgImage: cg, options: [:])
            try? handler.perform([req])
            for obs in (req.results ?? []) {
                guard let text = obs.topCandidates(1).first?.string else { continue }
                let bb = obs.boundingBox
                let rect = CGRect(
                    x: bb.minX * outerSize.width,
                    y: (1.0 - bb.maxY) * outerSize.height,
                    width: bb.width * outerSize.width,
                    height: bb.height * outerSize.height
                )
                for token in cardTitles where text.localizedCaseInsensitiveContains(token) && titleFrames[token] == nil {
                    titleFrames[token] = rect
                }
            }
        }
        return (image, titleFrames)
    }

    private func assertNoTruncatedOCR(in image: UIImage, label: String, requiredTokens: [String]) throws {
        guard let cg = image.cgImage else {
            XCTFail("Missing CGImage for \(label)")
            return
        }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let full = lines.joined(separator: " | ")
        for token in requiredTokens {
            XCTAssertTrue(
                full.localizedCaseInsensitiveContains(token),
                "\(label) missing '\(token)'. OCR: \(full)"
            )
        }
    }

    // MARK: - Live Geometry + Before/After Capture Test

    func testDiscoverIPadPortraitTwoColumnsAndIPhoneUnchangedBeforeAfter() async throws {
        let swipeHintKey = "discover_swipe_hinted"
        let hadSwipeHintKey = UserDefaults.standard.object(forKey: swipeHintKey) != nil
        let prevSwipeHintValue = UserDefaults.standard.bool(forKey: swipeHintKey)
        UserDefaults.standard.set(true, forKey: swipeHintKey)
        defer {
            if hadSwipeHintKey {
                UserDefaults.standard.set(prevSwipeHintValue, forKey: swipeHintKey)
            } else {
                UserDefaults.standard.removeObject(forKey: swipeHintKey)
            }
        }

        let (feedResp, titles) = try makeTestFeed()
        let renderDir = ProcessInfo.processInfo.environment["DISCOVER_IPAD_13914_RENDER_DIR"]
        let dirURL = renderDir.flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        if let dirURL {
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        }

        func makeDiscoverPlace() async -> MacReadingPlace<DiscoverViewModel> {
            let vm = DiscoverViewModel(
                client: StubDiscoverProvider13914(response: feedResp),
                lastGood: nil,
                telemetry: nil
            )
            let place = MacReadingPlace<DiscoverViewModel>()
            _ = place.models { vm }
            _ = await vm.load()
            return place
        }

        func savePNG(_ image: UIImage, name: String) throws {
            guard let dirURL else { return }
            try image.pngData()?.write(to: dirURL.appendingPathComponent("\(name).png"))
        }

        // 1. iPad Portrait with Sidebar (834 x 1194 -> 260 pt sidebar + 573 pt detail -> 541 pt card area)
        //    BEFORE: 1 wide column; AFTER: 2 equal columns (Light & Dark).
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let sidebarW: CGFloat = 260
            let detailW: CGFloat = 834 - sidebarW - 1
            let detailMidX = sidebarW + 1 + detailW * 0.5
            let size = CGSize(width: 834, height: 1194)

            let beforeDetail = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                detailWidth: detailW,
                totalHeight: size.height,
                colorScheme: scheme,
                horizontalSizeClass: .regular
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforeDetail,
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_portrait_sidebar_\(schemeName)")

            let card0Before = try XCTUnwrap(beforeFrames[titles[0]], "before portrait missing card 0")
            let card1Before = try XCTUnwrap(beforeFrames[titles[1]], "before portrait missing card 1")
            // BEFORE places every card stacked vertically inside column 0 (left side of detail).
            XCTAssertLessThan(card0Before.minX, detailMidX, "BEFORE card 0 left-aligned in 1 column")
            XCTAssertLessThan(card1Before.minX, detailMidX, "BEFORE card 1 left-aligned in same 1 column")
            XCTAssertLessThan(
                abs(card1Before.minX - card0Before.minX),
                60,
                "BEFORE iPad portrait \(schemeName) expected 1 column, got X=\(card0Before.minX) vs \(card1Before.minX)"
            )
            XCTAssertGreaterThan(card1Before.minY, card0Before.maxY, "BEFORE iPad portrait stacks vertically")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(
                    macPlace: place,
                    machineryPreviewLoader: EmptyMachineryLoader13914()
                ),
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_portrait_sidebar_\(schemeName)")

            let card0After = try XCTUnwrap(afterFrames[titles[0]], "after portrait missing card 0")
            let card1After = try XCTUnwrap(afterFrames[titles[1]], "after portrait missing card 1")
            let card2After = try XCTUnwrap(afterFrames[titles[2]], "after portrait missing card 2")
            let card3After = try XCTUnwrap(afterFrames[titles[3]], "after portrait missing card 3")

            // AFTER places card 0 & 2 in column 0 (left) and card 1 & 3 in column 1 (right), side by side!
            XCTAssertLessThan(card0After.minX, detailMidX, "AFTER card 0 stays in left column")
            XCTAssertGreaterThan(card1After.minX, detailMidX, "AFTER card 1 moves into right column")
            XCTAssertGreaterThan(
                card1After.minX - card0After.minX,
                200,
                "AFTER iPad portrait \(schemeName) must put card 1 in right column (0: \(card0After.minX), 1: \(card1After.minX))"
            )
            XCTAssertGreaterThan(
                card3After.minX - card2After.minX,
                200,
                "AFTER iPad portrait \(schemeName) row 2 must also use two columns"
            )
            XCTAssertLessThanOrEqual(
                max(card1After.maxX, card3After.maxX),
                size.width - 14,
                "Right column cards must fit cleanly inside detail area without clipping"
            )
            try assertNoTruncatedOCR(
                in: afterImg,
                label: "after_ipad_portrait_\(schemeName)",
                requiredTokens: ["Discover", "year-end?", "Chiefs", "Riemann", "76%", "59%"]
            )
        }

        // 2. Narrowest upright iPad split (514 pt detail -> 482 pt card area -> ~233 pt per card)
        //    + Full-width upright iPad portrait (834 x 1194 -> 768 pt card area -> 2 columns)
        do {
            let narrowSize = CGSize(width: 514, height: 1080)
            let narrowPlace = await makeDiscoverPlace()
            let (narrowImg, narrowFrames) = await renderAndMeasure(
                DiscoverView(macPlace: narrowPlace, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: narrowSize,
                detailSizeClass: .regular,
                colorScheme: .light,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(narrowImg, name: "after_ipad_portrait_narrow_514_light")
            let n0 = try XCTUnwrap(narrowFrames[titles[0]])
            let n1 = try XCTUnwrap(narrowFrames[titles[1]])
            let n2 = try XCTUnwrap(narrowFrames[titles[2]])
            let n3 = try XCTUnwrap(narrowFrames[titles[3]])
            XCTAssertGreaterThan(n1.minX - n0.minX, 180, "514 pt upright detail must render 2 columns")
            XCTAssertGreaterThan(n3.minX - n2.minX, 180, "514 pt upright detail row 2 must render 2 columns")
            XCTAssertLessThanOrEqual(max(n1.maxX, n3.maxX), narrowSize.width - 14)
            try assertNoTruncatedOCR(
                in: narrowImg,
                label: "after_ipad_portrait_narrow_514_light",
                requiredTokens: ["Discover", "year-end?", "Chiefs", "Riemann", "76%", "59%"]
            )

            let fullSize = CGSize(width: 834, height: 1194)
            let fullPlace = await makeDiscoverPlace()
            let (fullImg, fullFrames) = await renderAndMeasure(
                DiscoverView(macPlace: fullPlace, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: fullSize,
                detailSizeClass: .regular,
                colorScheme: .light,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(fullImg, name: "after_ipad_portrait_full_834_light")
            let f0 = try XCTUnwrap(fullFrames[titles[0]])
            let f1 = try XCTUnwrap(fullFrames[titles[1]])
            XCTAssertGreaterThan(f1.minX - f0.minX, 320, "834 pt full-width upright iPad shows 2 columns")
        }

        // 3. iPad Landscape with Sidebar (1194 x 834 -> 220 pt sidebar + 973 pt detail -> 2 columns BEFORE & AFTER)
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let sidebarW: CGFloat = 220
            let detailW: CGFloat = 1194 - sidebarW - 1
            let size = CGSize(width: 1194, height: 834)

            let beforeLandscape = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                detailWidth: detailW,
                totalHeight: size.height,
                colorScheme: scheme,
                horizontalSizeClass: .regular
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforeLandscape,
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_landscape_\(schemeName)")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_landscape_\(schemeName)")

            let lb0 = try XCTUnwrap(beforeFrames[titles[0]])
            let lb1 = try XCTUnwrap(beforeFrames[titles[1]])
            let la0 = try XCTUnwrap(afterFrames[titles[0]])
            let la1 = try XCTUnwrap(afterFrames[titles[1]])
            XCTAssertGreaterThan(lb1.minX - lb0.minX, 320, "BEFORE iPad landscape is 2 columns")
            XCTAssertGreaterThan(la1.minX - la0.minX, 320, "AFTER iPad landscape remains 2 columns")
            XCTAssertEqual(la0.minX, lb0.minX, accuracy: 24, "iPad landscape left column unchanged")
            XCTAssertEqual(la1.minX, lb1.minX, accuracy: 24, "iPad landscape right column unchanged")
        }

        // 4. iPhone Portrait (390 x 844, .compact) — BEFORE & AFTER stay 1 column identically.
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let size = CGSize(width: 390, height: 844)
            let beforePhone = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                detailWidth: size.width,
                totalHeight: size.height,
                colorScheme: scheme,
                horizontalSizeClass: .compact
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforePhone,
                outerSize: size,
                detailSizeClass: .compact,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(2))
            )
            try savePNG(beforeImg, name: "before_iphone_390_\(schemeName)")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: size,
                detailSizeClass: .compact,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(2))
            )
            try savePNG(afterImg, name: "after_iphone_390_\(schemeName)")

            let pb0 = try XCTUnwrap(beforeFrames[titles[0]])
            let pb1 = try XCTUnwrap(beforeFrames[titles[1]])
            let pa0 = try XCTUnwrap(afterFrames[titles[0]])
            let pa1 = try XCTUnwrap(afterFrames[titles[1]])
            XCTAssertLessThan(pa0.minX, size.width * 0.35, "AFTER iPhone 390 \(schemeName) card 0 stays in column 0")
            XCTAssertLessThan(pa1.minX, size.width * 0.35, "AFTER iPhone 390 \(schemeName) card 1 stays in column 0")
            XCTAssertLessThan(abs(pa1.minX - pa0.minX), 60, "AFTER iPhone 390 \(schemeName) stays 1 column")
            XCTAssertLessThan(abs(pa0.minX - pb0.minX), 8, "AFTER iPhone 390 left inset matches BEFORE")
            XCTAssertLessThan(abs(pa0.width - pb0.width), 8, "AFTER iPhone 390 card width matches BEFORE")
            XCTAssertGreaterThan(pa1.minY, pa0.maxY, "iPhone cards stack vertically")
        }
    }

    #endif
}
