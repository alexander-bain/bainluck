import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// #13914 — Upright iPad Discover must keep two columns of cards (matching the
/// website's `sm:grid-cols-2` breakpoint) instead of collapsing into one oversized
/// column across upright split-view / sidebar / machinery-preview layouts on
/// iPad (`iPad16,6` `1032 x 1376 pt` and `834 pt` Display Zoom), while leaving
/// iPhone completely unchanged in one column.
@MainActor
final class DiscoverIPadPortraitTwoColumns13914Tests: XCTestCase {

    // MARK: - Breakpoint, Idiom & Dynamic Type Unit Tests

    func testIPhoneCompactWidthsRemainSingleColumnUnchanged() {
        for width in [320.0, 375.0, 390.0, 402.0, 430.0, 440.0] {
            let area = DiscoverMasonry.cardAreaWidth(
                containerWidth: CGFloat(width),
                maxContentWidth: .infinity
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    dynamicTypeSize: .large,
                    isPhone: true
                ),
                DiscoverMasonry.columnCount(availableWidth: area),
                "iPhone \(width) pt (.compact, area \(area)) must match legacy columnCount"
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    isPhone: true
                ),
                1,
                "iPhone \(width) pt portrait must stay 1 column"
            )
            XCTAssertFalse(
                DiscoverMasonry.usesNarrowMultiColumn(
                    availableWidth: area,
                    isPhone: true
                )
            )
        }
        // iPhone compact landscape (`540`, `600`, `700`) behaves identically to legacy `columnCount`.
        for landscapeWidth: CGFloat in [540, 600, 700] {
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: landscapeWidth,
                    dynamicTypeSize: .large,
                    isPhone: true
                ),
                DiscoverMasonry.columnCount(availableWidth: landscapeWidth),
                "iPhone compact width \(landscapeWidth) must match legacy columnCount"
            )
            XCTAssertFalse(
                DiscoverMasonry.usesNarrowMultiColumn(
                    availableWidth: landscapeWidth,
                    isPhone: true
                )
            )
        }
    }

    func testIPadPortraitFullScreenSplitAndSidebarWidthsResolveToTwoColumns() {
        // `iPad16,6` (`iPad Pro 13-inch`) upright full-screen (`1032`), sidebar open (`712`),
        // `2/3` Split View (`639`, `.compact`), `1/2` Split View (`507`, `.compact`), web `sm:`
        // `640` window, and Display Zoom / 11" iPad `834` with `320 pt` sidebar (`514` detail).
        let cases: [(width: CGFloat, sizeClass: UserInterfaceSizeClass, expected: Int, narrow: Bool, label: String)] = [
            (1032, .regular, 2, false, "iPad Pro 13 full screen upright (768 pt area)"),
            (712, .regular, 2, false, "iPad Pro 13 w/ 320 pt sidebar open (680 pt area)"),
            (639, .compact, 2, true, "iPad Pro 13 upright 2/3 Split View (.compact, 607 pt area)"),
            (507, .compact, 2, true, "iPad Pro 13 upright 1/2 Split View (.compact, 475 pt area)"),
            (640, .regular, 2, true, "640 pt window matching web sm:grid-cols-2 (608 pt area)"),
            (514, .regular, 2, true, "834 pt upright iPad w/ 320 pt sidebar (482 pt area)"),
            (744, .regular, 2, false, "iPad mini upright full screen"),
            (820, .regular, 2, false, "iPad Air 11 upright full screen"),
            (834, .regular, 2, false, "iPad Pro 11 upright full screen"),
            (1376, .regular, 2, false, "iPad Pro 13 landscape full screen (768 pt clamped area)"),
            (1056, .regular, 2, false, "iPad Pro 13 landscape w/ 320 pt sidebar (768 pt clamped area)"),
            (375, .compact, 1, false, "iPad Pro 13 upright 1/3 Split View (343 pt area -> 1 col)"),
            (320, .compact, 1, false, "iPad Slide Over (288 pt area -> 1 col)"),
        ]

        for entry in cases {
            let maxW: CGFloat = entry.sizeClass == .regular ? 800 : .infinity
            let area = DiscoverMasonry.cardAreaWidth(
                containerWidth: entry.width,
                maxContentWidth: maxW
            )
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: area,
                    dynamicTypeSize: .large,
                    isPhone: false
                ),
                entry.expected,
                "\(entry.label) (detail \(entry.width), area \(area))"
            )
            XCTAssertEqual(
                DiscoverMasonry.usesNarrowMultiColumn(
                    availableWidth: area,
                    dynamicTypeSize: .large,
                    isPhone: false
                ),
                entry.narrow,
                "\(entry.label) narrow-multi-column mismatch"
            )
        }
    }

    func testDiscoverColumnCountExactBoundariesAndAccessibilityGate() {
        // Exact boundary: 2 * 225 + 16 = 466 pt card area (498 pt detail width).
        XCTAssertEqual(DiscoverMasonry.regularTwoColumnMinimumCardWidth, 225)
        XCTAssertEqual(DiscoverMasonry.regularTwoColumnMinimumAreaWidth, 466)

        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 465, isPhone: false),
            1
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 466, isPhone: false),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 615, isPhone: false),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 616, isPhone: false),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 931, isPhone: false),
            2
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 932, isPhone: false),
            3
        )
        XCTAssertTrue(DiscoverMasonry.usesNarrowMultiColumn(availableWidth: 466, isPhone: false))
        XCTAssertTrue(DiscoverMasonry.usesNarrowMultiColumn(availableWidth: 615, isPhone: false))
        XCTAssertFalse(DiscoverMasonry.usesNarrowMultiColumn(availableWidth: 616, isPhone: false))

        // Unknown / non-positive width never returns < 1 column.
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: 0, isPhone: false),
            1
        )
        XCTAssertEqual(
            DiscoverMasonry.discoverColumnCount(availableWidth: -20, isPhone: false),
            1
        )

        // Ordinary sizes up through .xxLarge keep 2 columns in the narrow 466–615 pt band.
        for regularSize in [DynamicTypeSize.xSmall, .large, .xLarge, .xxLarge] {
            for width in [466.0, 482.0, 607.0] {
                XCTAssertEqual(
                    DiscoverMasonry.discoverColumnCount(
                        availableWidth: CGFloat(width),
                        dynamicTypeSize: regularSize,
                        isPhone: false
                    ),
                    2,
                    "Narrow \(width) pt card area keeps 2 columns at \(regularSize)"
                )
                XCTAssertTrue(
                    DiscoverMasonry.usesNarrowMultiColumn(
                        availableWidth: CGFloat(width),
                        dynamicTypeSize: regularSize,
                        isPhone: false
                    ),
                    "Narrow \(width) pt card area expects usesNarrowMultiColumn at \(regularSize)"
                )
            }
        }

        // Narrow iPad panes (< 616 pt) fall back to 1 column starting at .xxxLarge and
        // Accessibility Dynamic Type sizes so 225-299 pt cards never hyphenate mid-word;
        // wider panes (>= 616 pt) stay 2 columns.
        for fallbackSize in [DynamicTypeSize.xxxLarge, .accessibility1, .accessibility3, .accessibility5] {
            for width in [466.0, 482.0, 607.0] {
                XCTAssertEqual(
                    DiscoverMasonry.discoverColumnCount(
                        availableWidth: CGFloat(width),
                        dynamicTypeSize: fallbackSize,
                        isPhone: false
                    ),
                    1,
                    "Narrow \(width) pt card area must fall back to 1 column at \(fallbackSize)"
                )
                XCTAssertFalse(
                    DiscoverMasonry.usesNarrowMultiColumn(
                        availableWidth: CGFloat(width),
                        dynamicTypeSize: fallbackSize,
                        isPhone: false
                    ),
                    "Narrow \(width) pt card area at \(fallbackSize) must not report usesNarrowMultiColumn"
                )
            }
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: 768,
                    dynamicTypeSize: fallbackSize,
                    isPhone: false
                ),
                2,
                "Full 768 pt card area stays 2 columns at \(fallbackSize)"
            )
        }
    }

    #if os(iOS)

    // MARK: - Deterministic Feed & Machinery Stubs

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

    private nonisolated struct StubMachineryLoader13914: MachineryPreviewLoading12288 {
        let entries: [MachineryPreviewEntry]
        func loadPreview(user: AuthUser?) async throws -> [MachineryPreviewEntry] { entries }
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

    private func makeMachineryEntries() throws -> [MachineryPreviewEntry] {
        let json = """
        {
          "public_switch_enabled": false,
          "count": 2,
          "items": [
            {
              "slug": "machinery-fed-and-macro",
              "definition": {
                "slug": "machinery-fed-and-macro",
                "name": "Fed & U.S. Macro",
                "category": "economics",
                "kicker": "ECONOMICS · FEDERAL RESERVE",
                "footer": ""
              },
              "feed_item": {
                "data": {
                  "roundup": {
                    "machinery_card": {
                      "slug": "machinery-fed-and-macro",
                      "form_id": "contender_spotlight",
                      "kicker": "ECONOMICS · FEDERAL RESERVE",
                      "title": "January FOMC Rate Decision",
                      "subtitle": "Policy-move odds along the ladder.",
                      "footer": "",
                      "scale_ordered": true,
                      "section_count": 2,
                      "destination_href": "/collections/machinery-fed-and-macro",
                      "rows": [
                        {"outcome_id": 1, "name": "Cut 25 bps", "probability": 0.31, "rendered_percent": 31},
                        {"outcome_id": 2, "name": "No change", "probability": 0.58, "rendered_percent": 58}
                      ]
                    }
                  }
                }
              }
            },
            {
              "slug": "machinery-ai-race",
              "definition": {
                "slug": "machinery-ai-race",
                "name": "AI Models",
                "category": "tech",
                "kicker": "TECH · BENCHMARKS",
                "footer": ""
              },
              "feed_item": {
                "data": {
                  "roundup": {
                    "machinery_card": {
                      "slug": "machinery-ai-race",
                      "form_id": "contender_spotlight",
                      "kicker": "TECH · BENCHMARKS",
                      "title": "Best Frontier Model Q4",
                      "subtitle": "Head-to-head frontier leaderboard odds.",
                      "footer": "",
                      "scale_ordered": false,
                      "section_count": 2,
                      "destination_href": "/collections/machinery-ai-race",
                      "rows": [
                        {"outcome_id": 11, "name": "Gemini", "probability": 0.52, "rendered_percent": 52},
                        {"outcome_id": 12, "name": "Claude", "probability": 0.34, "rendered_percent": 34}
                      ]
                    }
                  }
                }
              }
            }
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(MachineryPreviewResponse.self, from: Data(json.utf8)).items
    }

    // MARK: - Sidebar & Legacy Pre-Fix Comparison Harnesses

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

    /// Pre-fix (`300 pt` minimum card width -> `DiscoverMasonry.columnCount(availableWidth:)`,
    /// plus 1-column `VStack` for owner machinery previews) harness used strictly for BEFORE panels.
    private struct LegacyBeforeDiscoverCanvas13914: View {
        let items: [FeedItem]
        var previewEntries: [MachineryPreviewEntry] = []
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
                        if !previewEntries.isEmpty {
                            VStack(spacing: DiscoverMasonry.spacing) {
                                ForEach(previewEntries) { entry in
                                    if let card = entry.machineryCard {
                                        MachineryDiscoverEntryCardView(
                                            card: card,
                                            pairedMetricSet: entry.pairedMetricSet
                                        )
                                    }
                                }
                            }
                            .padding(.horizontal)
                            .padding(.bottom, DiscoverMasonry.spacing)
                        }

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
        private let outerSize: CGSize
        private let traits: UITraitCollection

        init(
            sidebarChild: UIViewController?,
            sidebarWidth: CGFloat,
            detailChild: UIViewController,
            outerSize: CGSize,
            traits: UITraitCollection
        ) {
            self.sidebarChild = sidebarChild
            self.sidebarWidth = sidebarWidth
            self.detailChild = detailChild
            self.outerSize = outerSize
            self.traits = traits
            super.init(nibName: nil, bundle: nil)
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }

        override func viewDidLoad() {
            super.viewDidLoad()
            applyLayoutFrames()
            if let sidebarChild, sidebarWidth > 0 {
                addChild(sidebarChild)
                view.addSubview(sidebarChild.view)
                setOverrideTraitCollection(traits, forChild: sidebarChild)
                sidebarChild.didMove(toParent: self)

                let divider = UIView(frame: CGRect(x: sidebarWidth, y: 0, width: 1, height: outerSize.height))
                divider.backgroundColor = UIColor.separator
                view.addSubview(divider)
            }
            addChild(detailChild)
            view.addSubview(detailChild.view)
            setOverrideTraitCollection(traits, forChild: detailChild)
            detailChild.didMove(toParent: self)
            applyLayoutFrames()
        }

        override func viewDidLayoutSubviews() {
            super.viewDidLayoutSubviews()
            applyLayoutFrames()
        }

        private func applyLayoutFrames() {
            let totalH = outerSize.height
            let totalW = outerSize.width
            if let sidebarChild, sidebarWidth > 0 {
                sidebarChild.view.frame = CGRect(x: 0, y: 0, width: sidebarWidth, height: totalH)
                let detailX = sidebarWidth + 1
                detailChild.view.frame = CGRect(x: detailX, y: 0, width: max(1, totalW - detailX), height: totalH)
            } else {
                detailChild.view.frame = CGRect(x: 0, y: 0, width: totalW, height: totalH)
            }
        }
    }

    private func renderAndMeasure<V: View>(
        _ detailView: V,
        sidebarWidth: CGFloat = 0,
        outerSize: CGSize,
        detailSizeClass: UserInterfaceSizeClass,
        isPhone: Bool,
        colorScheme: ColorScheme,
        authManager: AuthManager? = nil,
        cardTitles: [String],
        extraTicks: Int = 0
    ) async -> (image: UIImage, titleFrames: [String: CGRect]) {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiSizeClass: UIUserInterfaceSizeClass = detailSizeClass == .compact ? .compact : .regular
        let detailW = sidebarWidth > 0 ? max(1, outerSize.width - sidebarWidth - 1) : outerSize.width

        let resolvedAuth: AuthManager = authManager ?? {
            let a = AuthManager(restoreOnInit: false)
            a.user = nil
            a.isLoading = false
            return a
        }()

        let styledDetail = detailView
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .large)
            .environment(\.horizontalSizeClass, detailSizeClass)
            .environment(\.discoverLayoutIsPhone13914, isPhone)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(allowLegacyGuestPins: false))
            .environmentObject(resolvedAuth)
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
            outerSize: outerSize,
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
        window.frame = bounds
        container.view.frame = bounds
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<(10 + extraTicks) {
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

        let onboardedKey = FirstRunStorageKeys212A.onboardedKey
        let hadOnboardedKey = UserDefaults.standard.object(forKey: onboardedKey) != nil
        let prevOnboardedValue = UserDefaults.standard.bool(forKey: onboardedKey)
        UserDefaults.standard.set(true, forKey: onboardedKey)

        defer {
            if hadSwipeHintKey {
                UserDefaults.standard.set(prevSwipeHintValue, forKey: swipeHintKey)
            } else {
                UserDefaults.standard.removeObject(forKey: swipeHintKey)
            }
            if hadOnboardedKey {
                UserDefaults.standard.set(prevOnboardedValue, forKey: onboardedKey)
            } else {
                UserDefaults.standard.removeObject(forKey: onboardedKey)
            }
        }

        let (feedResp, titles) = try makeTestFeed()
        let machineryEntries = try makeMachineryEntries()
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

        // 1. iPad16,6 (iPad Pro 13-inch) Upright 2/3 Split View (639 x 1376, .compact) — Light & Dark
        //    BEFORE: 1 oversized column (607 pt < 616 pt); AFTER: 2 equal columns (~295.5 pt ea).
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let size = CGSize(width: 639, height: 1376)
            let midX = size.width * 0.5

            let beforeView = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                detailWidth: size.width,
                totalHeight: size.height,
                colorScheme: scheme,
                horizontalSizeClass: .compact
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforeView,
                outerSize: size,
                detailSizeClass: .compact,
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_2_3_split_639_\(schemeName)")

            let b0 = try XCTUnwrap(beforeFrames[titles[0]])
            let b1 = try XCTUnwrap(beforeFrames[titles[1]])
            XCTAssertLessThan(b0.minX, midX)
            XCTAssertLessThan(b1.minX, midX)
            XCTAssertGreaterThan(b1.minY, b0.maxY, "BEFORE iPad 2/3 split stacks in 1 column")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: size,
                detailSizeClass: .compact,
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_2_3_split_639_\(schemeName)")

            let a0 = try XCTUnwrap(afterFrames[titles[0]])
            let a1 = try XCTUnwrap(afterFrames[titles[1]])
            let a2 = try XCTUnwrap(afterFrames[titles[2]])
            let a3 = try XCTUnwrap(afterFrames[titles[3]])
            XCTAssertLessThan(a0.minX, midX, "AFTER 2/3 split card 0 in left column")
            XCTAssertGreaterThan(a1.minX, midX, "AFTER 2/3 split card 1 in right column")
            XCTAssertGreaterThan(a1.minX - a0.minX, 240, "AFTER iPad 2/3 split \(schemeName) uses 2 columns")
            XCTAssertGreaterThan(a3.minX - a2.minX, 240, "AFTER iPad 2/3 split row 2 uses 2 columns")
            XCTAssertLessThanOrEqual(max(a1.maxX, a3.maxX), size.width - 14)
            try assertNoTruncatedOCR(
                in: afterImg,
                label: "after_ipad_2_3_split_639_\(schemeName)",
                requiredTokens: ["Discover", "year-end?", "Chiefs", "Riemann", "76%", "59%"]
            )
        }

        // 2. iPad16,6 Upright 1/2 Split View (507 x 1376, .compact) — Light BEFORE (1 col) vs AFTER (2 cols)
        do {
            let size = CGSize(width: 507, height: 1376)
            let midX = size.width * 0.5

            let beforeHalf = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                detailWidth: size.width,
                totalHeight: size.height,
                colorScheme: .light,
                horizontalSizeClass: .compact
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforeHalf,
                outerSize: size,
                detailSizeClass: .compact,
                isPhone: false,
                colorScheme: .light,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_1_2_split_507_light")
            let bh0 = try XCTUnwrap(beforeFrames[titles[0]])
            let bh1 = try XCTUnwrap(beforeFrames[titles[1]])
            XCTAssertLessThan(bh0.minX, midX)
            XCTAssertLessThan(bh1.minX, midX)
            XCTAssertGreaterThan(bh1.minY, bh0.maxY, "BEFORE iPad 1/2 split is 1 column")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: size,
                detailSizeClass: .compact,
                isPhone: false,
                colorScheme: .light,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_1_2_split_507_light")

            let h0 = try XCTUnwrap(afterFrames[titles[0]])
            let h1 = try XCTUnwrap(afterFrames[titles[1]])
            let h2 = try XCTUnwrap(afterFrames[titles[2]])
            let h3 = try XCTUnwrap(afterFrames[titles[3]])
            XCTAssertGreaterThan(h1.minX - h0.minX, 180, "507 pt 1/2 split must render 2 columns")
            XCTAssertGreaterThan(h3.minX - h2.minX, 180, "507 pt 1/2 split row 2 must render 2 columns")
            XCTAssertLessThanOrEqual(max(h1.maxX, h3.maxX), size.width - 14)
            try assertNoTruncatedOCR(
                in: afterImg,
                label: "after_ipad_1_2_split_507_light",
                requiredTokens: ["Discover", "year-end?", "Chiefs", "Riemann", "76%", "59%"]
            )
        }

        // 3. Upright iPad w/ 320 pt Sidebar (834 x 1194 -> 513 pt detail -> 481 pt card area, .regular) — Light & Dark
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let sidebarW: CGFloat = 320
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
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_sidebar_834_\(schemeName)")
            let b0 = try XCTUnwrap(beforeFrames[titles[0]])
            let b1 = try XCTUnwrap(beforeFrames[titles[1]])
            XCTAssertLessThan(b0.minX, detailMidX)
            XCTAssertLessThan(b1.minX, detailMidX)
            XCTAssertGreaterThan(b1.minY, b0.maxY, "BEFORE 834 w/ 320 sidebar stacks in 1 column")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_sidebar_834_\(schemeName)")

            let a0 = try XCTUnwrap(afterFrames[titles[0]])
            let a1 = try XCTUnwrap(afterFrames[titles[1]])
            let a2 = try XCTUnwrap(afterFrames[titles[2]])
            let a3 = try XCTUnwrap(afterFrames[titles[3]])
            XCTAssertLessThan(a0.minX, detailMidX)
            XCTAssertGreaterThan(a1.minX, detailMidX)
            XCTAssertGreaterThan(a1.minX - a0.minX, 180, "AFTER 834 w/ 320 sidebar \(schemeName) is 2 columns")
            XCTAssertGreaterThan(a3.minX - a2.minX, 180, "AFTER 834 w/ 320 sidebar row 2 is 2 columns")
            try assertNoTruncatedOCR(
                in: afterImg,
                label: "after_ipad_sidebar_834_\(schemeName)",
                requiredTokens: ["Discover", "year-end?", "Chiefs", "Riemann", "76%", "59%"]
            )
        }

        // 4. iPad16,6 Full-Screen Upright (1032 x 1376, .regular) w/ Owner Machinery Previews
        //    BEFORE: unservedPreviewItems stacked in 1 giant column (768 pt wide);
        //    AFTER: unservedPreviewItems + regular cards both render in 2 columns!
        do {
            let suiteName = "Discover13914Machinery.\(UUID().uuidString)"
            let isolatedDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
            GroupingMachineryGate12288.setOverrideDefaultsForTesting(isolatedDefaults)
            defer {
                GroupingMachineryGate12288.setOverrideDefaultsForTesting(nil)
                GroupingMachineryGate12288.setActiveUser(nil)
                isolatedDefaults.removePersistentDomain(forName: suiteName)
            }

            let ownerAlex = AuthUser(
                id: 364,
                email: "alex@example.com",
                displayName: "Alex",
                photoUrl: nil,
                onboardingCompleted: true,
                createdAt: nil
            )
            GroupingMachineryGate12288.setSwitchEnabled(true, for: ownerAlex, defaults: isolatedDefaults)
            let ownerAuth = AuthManager(restoreOnInit: false)
            ownerAuth.user = ownerAlex
            ownerAuth.isLoading = false

            let size = CGSize(width: 1032, height: 1376)
            let machineryTokens = ["January FOMC", "Best Frontier"] + Array(titles.prefix(2))

            let beforeMachinery = LegacyBeforeDiscoverCanvas13914(
                items: feedResp.items,
                previewEntries: machineryEntries,
                detailWidth: size.width,
                totalHeight: size.height,
                colorScheme: .light,
                horizontalSizeClass: .regular
            )
            let (beforeImg, beforeFrames) = await renderAndMeasure(
                beforeMachinery,
                outerSize: size,
                detailSizeClass: .regular,
                isPhone: false,
                colorScheme: .light,
                authManager: ownerAuth,
                cardTitles: machineryTokens
            )
            try savePNG(beforeImg, name: "before_ipad_1032_machinery_light")
            let bm0 = try XCTUnwrap(beforeFrames["January FOMC"])
            let bm1 = try XCTUnwrap(beforeFrames["Best Frontier"])
            XCTAssertLessThan(abs(bm1.minX - bm0.minX), 24, "BEFORE machinery preview stacks in 1 column")
            XCTAssertGreaterThan(bm1.minY, bm0.maxY)

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(
                    macPlace: place,
                    machineryPreviewLoader: StubMachineryLoader13914(entries: machineryEntries)
                ),
                outerSize: size,
                detailSizeClass: .regular,
                isPhone: false,
                colorScheme: .light,
                authManager: ownerAuth,
                cardTitles: machineryTokens,
                extraTicks: 8
            )
            try savePNG(afterImg, name: "after_ipad_1032_machinery_light")
            let am0 = try XCTUnwrap(afterFrames["January FOMC"])
            let am1 = try XCTUnwrap(afterFrames["Best Frontier"])
            let ar0 = try XCTUnwrap(afterFrames[titles[0]])
            let ar1 = try XCTUnwrap(afterFrames[titles[1]])
            XCTAssertLessThan(am0.minX, size.width * 0.5)
            XCTAssertGreaterThan(am1.minX, size.width * 0.5)
            XCTAssertGreaterThan(am1.minX - am0.minX, 320, "AFTER machinery preview renders 2 columns at 1032 pt")
            XCTAssertGreaterThan(ar1.minX - ar0.minX, 320, "AFTER regular feed keeps 2 columns below machinery preview")
            try assertNoTruncatedOCR(
                in: afterImg,
                label: "after_ipad_1032_machinery_light",
                requiredTokens: ["Discover", "January FOMC", "Best Frontier", "year-end?", "Chiefs"]
            )
        }

        // 5. iPad16,6 Landscape w/ 320 pt Sidebar (1376 x 1032, .regular) — Light & Dark (2 cols unchanged)
        for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let sidebarW: CGFloat = 320
            let detailW: CGFloat = 1376 - sidebarW - 1
            let size = CGSize(width: 1376, height: 1032)

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
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(beforeImg, name: "before_ipad_landscape_1376_\(schemeName)")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                sidebarWidth: sidebarW,
                outerSize: size,
                detailSizeClass: .regular,
                isPhone: false,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(4))
            )
            try savePNG(afterImg, name: "after_ipad_landscape_1376_\(schemeName)")

            let lb0 = try XCTUnwrap(beforeFrames[titles[0]])
            let lb1 = try XCTUnwrap(beforeFrames[titles[1]])
            let la0 = try XCTUnwrap(afterFrames[titles[0]])
            let la1 = try XCTUnwrap(afterFrames[titles[1]])
            XCTAssertGreaterThan(lb1.minX - lb0.minX, 320, "BEFORE iPad landscape is 2 columns")
            XCTAssertGreaterThan(la1.minX - la0.minX, 320, "AFTER iPad landscape remains 2 columns")
            XCTAssertEqual(la0.minX, lb0.minX, accuracy: 24, "iPad landscape left column unchanged")
            XCTAssertEqual(la1.minX, lb1.minX, accuracy: 24, "iPad landscape right column unchanged")
        }

        // 6. iPhone Portrait (390 x 844, .compact, isPhone = true) — BEFORE & AFTER stay 1 column identically.
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
                isPhone: true,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(2))
            )
            try savePNG(beforeImg, name: "before_iphone_390_\(schemeName)")

            let place = await makeDiscoverPlace()
            let (afterImg, afterFrames) = await renderAndMeasure(
                DiscoverView(macPlace: place, machineryPreviewLoader: EmptyMachineryLoader13914()),
                outerSize: size,
                detailSizeClass: .compact,
                isPhone: true,
                colorScheme: scheme,
                cardTitles: Array(titles.prefix(2))
            )
            try savePNG(afterImg, name: "after_iphone_390_\(schemeName)")

            let pb0 = try XCTUnwrap(beforeFrames[titles[0]])
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

    // MARK: - Fable CHANGES Guards: Longest Fixture Title & All Card Types at 225 pt Min Column Width

    private func decodeFixtureLongestFuturesItem() throws -> (longestItem: FeedItem, longestTitle: String) {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let prodResp = try decoder.decode(FeedResponse.self, from: Data(DiscoverFeedProdFixture.json.utf8))
        var candidates: [FeedItem] = []
        for item in prodResp.items {
            if item.futures != nil {
                candidates.append(item)
            }
            if let bundleItems = item.bundle?.items {
                for child in bundleItems where child.futures != nil {
                    candidates.append(child)
                }
            }
        }
        let picked = try XCTUnwrap(candidates.max(by: { ($0.futures?.name.count ?? 0) < ($1.futures?.name.count ?? 0) }))
        let title = try XCTUnwrap(picked.futures?.name)
        return (picked, title)
    }

    private func recognizeLines(in image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func renderMinimumColumnShowcasePage<V: View>(
        _ content: V,
        size: CGSize,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        isNarrowTwoColumn: Bool = true
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let auth = AuthManager(restoreOnInit: false)
        auth.user = nil
        auth.isLoading = false
        let view = content
            .padding(.horizontal, DiscoverMasonry.spacing)
            .padding(.vertical, 12)
            .frame(width: size.width, alignment: .topLeading)
            .background(colorScheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground))
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.horizontalSizeClass, .regular)
            .environment(\.discoverLayoutIsPhone13914, false)
            .environment(\.discoverNarrowTwoColumn13914, isNarrowTwoColumn)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(allowLegacyGuestPins: false))
            .environmentObject(auth)

        let host = hostForMeasurement(view, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.horizontalSizeClass = .regular
        let bounds = CGRect(origin: .zero, size: size)
        host.view.frame = bounds

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        window.rootViewController = host
        window.makeKeyAndVisible()
        window.frame = bounds
        host.view.frame = bounds
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<10 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    func testLongestFixtureTitleRendersWholeAtMinimumTwoColumnWidth() throws {
        let (feedResp, _) = try makeTestFeed()
        let (longestItem, longestTitle) = try decodeFixtureLongestFuturesItem()
        let riemannGroup = try XCTUnwrap(feedResp.items.first(where: { $0.bundle != nil })?.bundle)
        let riemannChild = try XCTUnwrap(riemannGroup.items.first)
        XCTAssertGreaterThan(longestTitle.count, 35, "Expected real long title from DiscoverFeedProdFixture")

        // Minimum 2-column canvas: 498 pt total - 32 pt padding = 466 pt card area -> two 225 pt columns.
        let canvasSize = CGSize(width: 498, height: 900)
        let items = [riemannChild, longestItem]
        let cardView = LazyMasonryColumns(
            range: 0..<2,
            columnCount: 2,
            spacing: DiscoverMasonry.spacing,
            horizontalAlignment: .center,
            cardAlignment: .center
        ) { idx in
            if idx == 0 {
                NativeGroupCard(
                    title: "AI",
                    items: items,
                    kind: "theme",
                    sharedQuestion: "Longest Fixture Title Guard",
                    navigationPath: .constant(NavigationPath())
                )
            } else {
                NativeGroupCard(
                    title: "TECH",
                    items: [longestItem],
                    kind: "theme",
                    sharedQuestion: longestTitle,
                    navigationPath: .constant(NavigationPath())
                )
            }
        }

        let img = renderMinimumColumnShowcasePage(
            cardView,
            size: canvasSize,
            colorScheme: .light,
            dynamicTypeSize: .large
        )
        if let dirPath = ProcessInfo.processInfo.environment["DISCOVER_IPAD_13914_RENDER_DIR"], !dirPath.isEmpty {
            let dirURL = URL(fileURLWithPath: dirPath, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try img.pngData()?.write(to: dirURL.appendingPathComponent("longest_title_min_2col_light.png"))
        }

        let lines = try recognizeLines(in: img)
        let full = lines.joined(separator: " | ")
        let fullSpace = lines.joined(separator: " ")
        XCTAssertFalse(full.contains("…"), "Minimum 225 pt column must not truncate longest fixture title with ellipsis: \(full)")
        XCTAssertFalse(full.contains("..."), "Minimum 225 pt column must not truncate longest fixture title: \(full)")
        XCTAssertTrue(
            fullSpace.localizedCaseInsensitiveContains("AI proves") || fullSpace.localizedCaseInsensitiveContains("Al proves"),
            "Missing 'AI proves' in: \(full)"
        )
        for required in ["Riemann", "Hypothesis", "2026?"] {
            XCTAssertTrue(fullSpace.localizedCaseInsensitiveContains(required), "Missing '\(required)' in: \(full)")
        }
        let longestWords = longestTitle
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init)
            .filter { $0.count >= 4 }
        for word in longestWords {
            XCTAssertTrue(
                fullSpace.localizedCaseInsensitiveContains(word),
                "Longest fixture title word '\(word)' (from '\(longestTitle)') truncated at 225 pt: \(full)"
            )
        }
    }

    func testAllFeedCardTypesAtMinimumTwoColumnWidthAcrossDynamicTypes() async throws {
        let (feedResp, _) = try makeTestFeed()
        let (longestItem, longestTitle) = try decodeFixtureLongestFuturesItem()
        let riemannGroup = try XCTUnwrap(feedResp.items.first(where: { $0.bundle != nil })?.bundle)
        let riemannChild = try XCTUnwrap(riemannGroup.items.first)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Live game with long team names and live score
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveCommence = iso.string(from: now.addingTimeInterval(-3600))
        let liveEventJSON = """
        {
          "id": 9139199,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Oklahoma City Thunder",
          "away_team": "Minnesota Timberwolves",
          "home_team_data": {"team_id": 25, "name": "Oklahoma City Thunder", "short_name": "Thunder", "abbreviation": "OKC", "primary_color": "#007AC1"},
          "away_team_data": {"team_id": 18, "name": "Minnesota Timberwolves", "short_name": "Timberwolves", "abbreviation": "MIN", "primary_color": "#0C2340"},
          "commence_time": "\(liveCommence)",
          "status": "live",
          "home_score": 108,
          "away_score": 104,
          "espn": {"period": "Q4", "game_clock": "2:14"},
          "current_odds": {"home_probability": 0.68, "away_probability": 0.32}
        }
        """
        let liveEvent = try decoder.decode(FeedEventData.self, from: Data(liveEventJSON.utf8))

        // 2. Division race card (`MachineryDiscoverCardView`) w/ `<1%` and `No recent probability`
        let divisionCardJSON = """
        {
          "slug": "machinery-nfc-north-race",
          "form_id": "contender_spotlight",
          "kicker": "NFL · NFC NORTH",
          "title": "NFC North Division Winner",
          "subtitle": "All 4 teams including sub-1% and unpriced.",
          "footer": "",
          "scale_ordered": false,
          "section_count": 1,
          "destination_href": "/collections/machinery-nfc-north-race",
          "rows": [
            {"outcome_id": 1, "name": "Detroit Lions", "probability": 0.61, "rendered_percent": 61, "settled_out": false},
            {"outcome_id": 2, "name": "Green Bay Packers", "probability": 0.38, "rendered_percent": 38, "settled_out": false},
            {"outcome_id": 3, "name": "Minnesota Vikings", "probability": 0.004, "rendered_percent": 1, "unfloored_percent": 0, "settled_out": false}
          ],
          "unpriced_outcomes": [
            {"outcome_id": 4, "name": "Chicago Bears", "settled_out": false}
          ]
        }
        """
        let divisionCard = try decoder.decode(MachineryCardContract.self, from: Data(divisionCardJSON.utf8))

        // 3. Round-up card (`DiscoverRoundupCardView`) w/ `<1%` and `No recent probability`
        let roundupContractJSON = """
        {
          "kicker": "NFL · DIVISION ROUND-UP",
          "tag": "4 teams",
          "subtitle": "Live prices beside sub-1% and paused team.",
          "complete_group": true,
          "footer": "See full division",
          "rows": [
            {"market_id": 7001, "outcome_id": 11, "label": "Buffalo Bills", "probability": 0.42, "rendered_percent": 42, "settled_out": false},
            {"market_id": 7001, "outcome_id": 12, "label": "Miami Dolphins", "probability": 0.29, "rendered_percent": 29, "settled_out": false},
            {"market_id": 7001, "outcome_id": 13, "label": "New England Patriots", "probability": 0.004, "rendered_percent": 1, "unfloored_percent": 0, "settled_out": false}
          ],
          "unpriced_outcomes": [
            {"outcome_id": 14, "name": "New York Jets", "settled_out": false}
          ]
        }
        """
        let roundupContract = try decoder.decode(FeedRoundupContract.self, from: Data(roundupContractJSON.utf8))
        let roundupModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: "AFC East contenders",
                contract: roundupContract,
                allowFlexibleRowCount: true
            )
        )

        // 4. Dated ladder (`HeatMapCardView`) w/ 4 date rungs including `<1%`
        let datedLadderJSON = """
        {
          "id": 9139204,
          "name": "Starship Mars landing date?",
          "llm_sport_category": "tech",
          "source": "kalshi",
          "source_count": 2,
          "sources": ["kalshi", "polymarket"],
          "market_tier": 2,
          "market_type": "quantity",
          "status": "open",
          "resolution_date": "2028-01-01T00:00:00Z",
          "discover_card": {
            "suggested_format": "threshold_heatmap",
            "threshold_points": [
              {"source": "date_bucket", "label": "Before Mar 31, 2027", "value": 1, "unit": "date", "direction": "before", "probability": 0.004},
              {"source": "date_bucket", "label": "Before Jun 30, 2027", "value": 2, "unit": "date", "direction": "before", "probability": 0.14},
              {"source": "date_bucket", "label": "Before Sep 30, 2027", "value": 3, "unit": "date", "direction": "before", "probability": 0.38},
              {"source": "date_bucket", "label": "Before Dec 31, 2027", "value": 4, "unit": "date", "direction": "before", "probability": 0.62}
            ]
          }
        }
        """
        let datedLadderData = try decoder.decode(FeedFuturesData.self, from: Data(datedLadderJSON.utf8))

        // 5. Tournament card (`NativeTournamentDiscoverCard`)
        let tournamentJSON = """
        {
          "key": "masters-2027",
          "name": "The Masters Tournament",
          "tour": "pga",
          "tour_label": "PGA Tour",
          "is_major": true,
          "venue": "Augusta National Golf Club",
          "marquee_whathit": false,
          "golfers": [
            {"name": "Scottie Scheffler", "probability": 0.31, "rendered_percent": 31, "rank": 1, "movement_24h": 0.024},
            {"name": "Rory McIlroy", "probability": 0.12, "rendered_percent": 12, "rank": 2},
            {"name": "Xander Schauffele", "probability": 0.09, "rendered_percent": 9, "rank": 3},
            {"name": "Jon Rahm", "probability": 0.07, "rendered_percent": 7, "rank": 4}
          ]
        }
        """
        let tournamentData = try decoder.decode(FeedTournamentData.self, from: Data(tournamentJSON.utf8))

        // 6. Futures card w/ `<1%`
        let subOneFuturesJSON = """
        {
          "id": 9139206,
          "name": "Next Federal Reserve Chair?",
          "llm_sport_category": "economics",
          "source": "kalshi",
          "source_count": 2,
          "sources": ["kalshi", "polymarket"],
          "market_tier": 1,
          "market_type": "field",
          "status": "open",
          "top_outcomes": [
            {"id": 91392061, "name": "Kevin Warsh", "probability": 0.54, "rank": 1, "movement": 0.03},
            {"id": 91392062, "name": "Christopher Waller", "probability": 0.28, "rank": 2},
            {"id": 91392063, "name": "Longshot Nominee", "probability": 0.004, "rank": 3}
          ],
          "outcome_count": 10
        }
        """
        let subOneFutures = try decoder.decode(FeedFuturesData.self, from: Data(subOneFuturesJSON.utf8))

        let page1View = LazyMasonryColumns(
            range: 0..<4,
            columnCount: 2,
            spacing: DiscoverMasonry.spacing,
            horizontalAlignment: .center,
            cardAlignment: .center
        ) { idx in
            switch idx {
            case 0:
                NativeGroupCard(
                    title: "TECH & WORLD",
                    items: [riemannChild, longestItem],
                    kind: "theme",
                    sharedQuestion: "Set · Long Titles",
                    navigationPath: .constant(NavigationPath())
                )
            case 1:
                NativeEventDiscoverCard(
                    event: liveEvent,
                    feedContext: nil,
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            case 2:
                MachineryDiscoverCardView(card: divisionCard)
            default:
                DiscoverRoundupCardView(model: roundupModel, collectionRef: nil)
            }
        }

        let page2View = LazyMasonryColumns(
            range: 0..<3,
            columnCount: 2,
            spacing: DiscoverMasonry.spacing,
            horizontalAlignment: .center,
            cardAlignment: .center
        ) { idx in
            switch idx {
            case 0:
                HeatMapCardView(data: datedLadderData, navigationPath: .constant(NavigationPath()))
            case 1:
                NativeTournamentDiscoverCard(
                    data: tournamentData,
                    feedContext: "PGA Tour: Scottie Scheffler leads at 31% (+2.4pp today)",
                    navigationPath: .constant(NavigationPath())
                )
            default:
                NativeFuturesDiscoverCard(
                    data: subOneFutures,
                    feedContext: "Warsh leads across 2 sources",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
        }

        let dirURL: URL? = {
            guard let p = ProcessInfo.processInfo.environment["DISCOVER_IPAD_13914_RENDER_DIR"], !p.isEmpty else { return nil }
            return URL(fileURLWithPath: p, isDirectory: true)
        }()
        if let dirURL {
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        }

        let configs: [(size: DynamicTypeSize, sizeLabel: String, scheme: ColorScheme, schemeName: String, heightP1: CGFloat, heightP2: CGFloat, enforceStrict: Bool)] = [
            (.large, "large", .light, "light", 1180, 980, true),
            (.large, "large", .dark, "dark", 1180, 980, true),
            (.xxLarge, "xxl", .light, "light", 1420, 1200, true),
            (.xxLarge, "xxl", .dark, "dark", 1420, 1200, true),
        ]

        let longestWords = longestTitle
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init)
            .filter { $0.count >= 4 }

        for cfg in configs {
            XCTAssertEqual(
                DiscoverMasonry.discoverColumnCount(
                    availableWidth: 466,
                    dynamicTypeSize: cfg.size,
                    isPhone: false
                ),
                2
            )
            let p1Img = renderMinimumColumnShowcasePage(
                page1View,
                size: CGSize(width: 498, height: cfg.heightP1),
                colorScheme: cfg.scheme,
                dynamicTypeSize: cfg.size
            )
            let p2Img = renderMinimumColumnShowcasePage(
                page2View,
                size: CGSize(width: 498, height: cfg.heightP2),
                colorScheme: cfg.scheme,
                dynamicTypeSize: cfg.size
            )

            if let dirURL {
                try p1Img.pngData()?.write(to: dirURL.appendingPathComponent("narrow225_\(cfg.sizeLabel)_\(cfg.schemeName)_p1.png"))
                try p2Img.pngData()?.write(to: dirURL.appendingPathComponent("narrow225_\(cfg.sizeLabel)_\(cfg.schemeName)_p2.png"))
            }

            let lines1 = try recognizeLines(in: p1Img)
            let lines2 = try recognizeLines(in: p2Img)
            let ocr1 = lines1.joined(separator: " | ")
            let ocr2 = lines2.joined(separator: " | ")
            let ocr1Space = lines1.joined(separator: " ")
            let ocr2Space = lines2.joined(separator: " ")
            let hasEllipsis1 = ocr1.contains("…") || ocr1.contains("...")
            let hasEllipsis2 = ocr2.contains("…") || ocr2.contains("...")
            print("NARROW_225_CHECK \(cfg.sizeLabel)_\(cfg.schemeName) ellipsis1=\(hasEllipsis1) ellipsis2=\(hasEllipsis2) p1=\(ocr1) ||| p2=\(ocr2)")

            if cfg.enforceStrict {
                XCTAssertFalse(hasEllipsis1, "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) page 1 has ellipsis: \(ocr1)")
                XCTAssertFalse(hasEllipsis2, "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) page 2 has ellipsis: \(ocr2)")
                for bad in ["Timber-", "ROUND- | ", "Christo-", "Nomi-", "Long-"] {
                    XCTAssertFalse(
                        ocr1.contains(bad) || ocr2.contains(bad),
                        "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) hyphenated '\(bad)' in p1=\(ocr1) ||| p2=\(ocr2)"
                    )
                }
                for tok in ["Riemann", "Hypothesis", "108", "104", "Lions", "Vikings", "<1%", "No recent probability", "Bears", "Jets"] {
                    XCTAssertTrue(ocr1Space.localizedCaseInsensitiveContains(tok), "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) p1 missing '\(tok)' in: \(ocr1)")
                }
                for word in longestWords {
                    XCTAssertTrue(ocr1Space.localizedCaseInsensitiveContains(word), "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) p1 missing '\(word)' in: \(ocr1)")
                }
                for tok in ["Starship Mars landing date?", "Before Dec 31", "Masters", "Scheffler", "Warsh", "Christopher Waller", "Longshot Nominee", "<1%"] {
                    XCTAssertTrue(ocr2Space.localizedCaseInsensitiveContains(tok), "225 pt .\(cfg.sizeLabel) \(cfg.schemeName) p2 missing '\(tok)' in: \(ocr2)")
                }
            }
        }

        // Verify .xxxLarge at 466 pt card area (498 pt pane) falls back to 1 column cleanly.
        let xxxlCols = DiscoverMasonry.discoverColumnCount(
            availableWidth: 466,
            dynamicTypeSize: .xxxLarge,
            isPhone: false
        )
        XCTAssertEqual(xxxlCols, 1)
        XCTAssertFalse(
            DiscoverMasonry.usesNarrowMultiColumn(
                availableWidth: 466,
                dynamicTypeSize: .xxxLarge,
                isPhone: false
            )
        )
        let xxxlFallbackView = LazyMasonryColumns(
            range: 0..<2,
            columnCount: xxxlCols,
            spacing: DiscoverMasonry.spacing,
            horizontalAlignment: .center,
            cardAlignment: .center
        ) { idx in
            if idx == 0 {
                NativeGroupCard(
                    title: "TECH & WORLD",
                    items: [riemannChild, longestItem],
                    kind: "theme",
                    sharedQuestion: "Set · Long Titles",
                    navigationPath: .constant(NavigationPath())
                )
            } else {
                NativeFuturesDiscoverCard(
                    data: subOneFutures,
                    feedContext: "Warsh leads across 2 sources",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
        }
        let xxxlImg = renderMinimumColumnShowcasePage(
            xxxlFallbackView,
            size: CGSize(width: 498, height: 1180),
            colorScheme: .light,
            dynamicTypeSize: .xxxLarge,
            isNarrowTwoColumn: false
        )
        if let dirURL {
            try xxxlImg.pngData()?.write(to: dirURL.appendingPathComponent("narrow225_xxxl_1col_fallback_light.png"))
        }
        let xxxlLines = try recognizeLines(in: xxxlImg)
        let xxxlOCR = xxxlLines.joined(separator: " | ")
        let xxxlOCRSpace = xxxlLines.joined(separator: " ")
        let xxxlEllipsis = xxxlOCR.contains("…") || xxxlOCR.contains("...")
        print("NARROW_225_CHECK xxxl_1col_fallback ellipsis=\(xxxlEllipsis) ocr=\(xxxlOCR)")
        XCTAssertFalse(xxxlEllipsis, ".xxxLarge 1-col fallback at 498 pt has ellipsis: \(xxxlOCR)")
        for tok in ["Riemann", "Hypothesis", "Christopher Waller", "Longshot Nominee", "<1%"] {
            XCTAssertTrue(
                xxxlOCRSpace.localizedCaseInsensitiveContains(tok),
                ".xxxLarge 1-col fallback missing '\(tok)' in: \(xxxlOCR)"
            )
        }
    }

    #endif
}
