import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// `#12288` — Grouping machinery on iPhone (Ruling 227: A · Direction 228):
/// 1. Double gate: server admin-only read + owner-only Preferences switch (owner account `id == 364` only,
///    default `off`). Public, signed-out, non-owner, and switched-off accounts see nothing and issue zero machinery requests.
/// 2. Topic-free native rendering of the Discover card and all 8 section visual forms.
/// 3. Three rows then `"Show all"`; Direction 228 ascending numerical order on ladder/range/rate/count markets;
///    real verified art or nothing (never placeholder letters); zero text cut off (`"…"`) through `.xxxLarge`.
/// 4. Exports `390 px` Light & Dark renders of all 4 groupings' cards and container pages + prints iPhone `227: A` counts.
@MainActor
final class GroupingMachinery12288Tests: XCTestCase {

    private final class SpyMachineryPreviewLoader: MachineryPreviewLoading12288, @unchecked Sendable {
        var callCount = 0
        var entries: [MachineryPreviewEntry] = []

        nonisolated func loadPreview(user: AuthUser?) async throws -> [MachineryPreviewEntry] {
            await MainActor.run { self.callCount += 1 }
            return await MainActor.run { self.entries }
        }
    }

    private final class SpyContainerHubService: ContainerHubLoading, @unchecked Sendable {
        var loadCallCount = 0
        var pairedCallCount = 0
        var response: ContainerHubResponse?

        nonisolated func load(slug: String) async throws -> ContainerHubResponse {
            await MainActor.run { self.loadCallCount += 1 }
            if let resp = await MainActor.run(body: { self.response }) {
                return resp
            }
            throw APIError.httpError(statusCode: 404, body: nil)
        }

        nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
            await MainActor.run { self.pairedCallCount += 1 }
            return []
        }
    }

    override func tearDown() {
        GroupingMachineryGate12288.setOverrideDefaultsForTesting(nil)
        GroupingMachineryGate12288.setActiveUser(nil)
        super.tearDown()
    }

    // MARK: - 1. Double Gate & Zero-Request Proof

    func testDoubleGatePreventsPublicAndSwitchedOffAccountsFromSeeingSwitchOrIssuingRequests() async throws {
        let suiteName = "GroupingMachinery12288Tests.\(UUID().uuidString)"
        let isolatedDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { isolatedDefaults.removePersistentDomain(forName: suiteName) }
        GroupingMachineryGate12288.setOverrideDefaultsForTesting(isolatedDefaults)

        let publicUser = AuthUser(
            id: 9001,
            email: "reader@example.com",
            displayName: "Public Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        let nonOwnerFamilyUser = AuthUser(
            id: 500,
            email: "member@example.com",
            displayName: "Family Member",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        let ownerAlex = AuthUser(
            id: 364,
            email: "owner@example.com",
            displayName: "Owner Account",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )

        // Identity checks: ONLY the owner account (`id == 364`) is owner.
        XCTAssertFalse(GroupingMachineryGate12288.isOwnerUser(nil))
        XCTAssertFalse(GroupingMachineryGate12288.isOwnerUser(publicUser))
        XCTAssertFalse(GroupingMachineryGate12288.isOwnerUser(nonOwnerFamilyUser))
        XCTAssertTrue(GroupingMachineryGate12288.isOwnerUser(ownerAlex))

        // Default is strictly OFF even for Alex.
        XCTAssertFalse(GroupingMachineryGate12288.isSwitchEnabled(for: ownerAlex))
        XCTAssertFalse(GroupingMachineryGate12288.canAccessMachinery(user: ownerAlex))

        // Non-owner attempts to flip the switch are ignored.
        GroupingMachineryGate12288.setSwitchEnabled(true, for: nil)
        GroupingMachineryGate12288.setSwitchEnabled(true, for: publicUser)
        GroupingMachineryGate12288.setSwitchEnabled(true, for: nonOwnerFamilyUser)
        XCTAssertFalse(GroupingMachineryGate12288.canAccessMachinery(user: nil))
        XCTAssertFalse(GroupingMachineryGate12288.canAccessMachinery(user: publicUser))
        XCTAssertFalse(GroupingMachineryGate12288.canAccessMachinery(user: nonOwnerFamilyUser))

        // PreferencesView visibility: non-owners NEVER see the switch; Alex sees it (default OFF).
        let samplePrefs = PreferencesResponse(
            homeLocation: nil,
            sportAffinities: [:],
            onboardingCompleted: true,
            favorites: [],
            pushPreferences: nil
        )
        for nonOwner in [nil, publicUser, nonOwnerFamilyUser] {
            let auth = AuthManager()
            auth.user = nonOwner
            let prefsImg = renderView(
                NavigationStack {
                    PreferencesView(loadedPrefsForTest: samplePrefs)
                        .environmentObject(auth)
                }
                .frame(width: 390),
                width: 390,
                maxHeight: 1_800
            )
            let ocr = try recognizeStrings(in: XCTUnwrap(prefsImg.cgImage)).joined(separator: " | ")
            XCTAssertFalse(
                ocr.localizedCaseInsensitiveContains("Grouping machinery preview"),
                "Non-owner \(String(describing: nonOwner?.email)) must never see owner switch: \(ocr)"
            )
        }

        let ownerAuth = AuthManager()
        ownerAuth.user = ownerAlex
        let ownerPrefsImg = renderView(
            NavigationStack {
                PreferencesView(loadedPrefsForTest: samplePrefs)
                    .environmentObject(ownerAuth)
            }
            .frame(width: 390),
            width: 390,
            maxHeight: 2_000
        )
        let ownerPrefsOCR = try recognizeStrings(in: XCTUnwrap(ownerPrefsImg.cgImage)).joined(separator: " | ")
        XCTAssertTrue(
            ownerPrefsOCR.localizedCaseInsensitiveContains("Grouping machinery preview"),
            "Alex must see 'Grouping machinery preview' in Preferences: \(ownerPrefsOCR)"
        )

        // Network request prevention across ALL 4 non-authorized states (anonymous, public user,
        // non-owner family admin, and Alex with switch OFF):
        for candidateUser in [nil, publicUser, nonOwnerFamilyUser, ownerAlex] {
            GroupingMachineryGate12288.setActiveUser(candidateUser)

            let apiItems = try await APIClient.shared.fetchMachineryPreview(user: candidateUser)
            XCTAssertTrue(apiItems.isEmpty, "APIClient.fetchMachineryPreview must short-circuit with []")

            let loader = APIMachineryPreviewLoader12288()
            let loaderItems = try await loader.loadPreview(user: candidateUser)
            XCTAssertTrue(loaderItems.isEmpty)

            do {
                _ = try await APIClient.shared.fetchContainerHub(slug: "machinery-nfl-week")
                XCTFail("Expected 404 before network on machinery-nfl-week for unauthorized/off user")
            } catch let APIError.httpError(statusCode, _) {
                XCTAssertEqual(statusCode, 404)
            }

            let spyHub = SpyContainerHubService()
            let hubVM = ContainerHubViewModel(slug: "machinery-oscars-best-picture", service: spyHub)
            await hubVM.load()
            XCTAssertEqual(spyHub.loadCallCount, 0, "Zero network requests allowed for machinery-* when gated off")
            XCTAssertEqual(spyHub.pairedCallCount, 0)
            if case .unavailable = hubVM.state {
                // expected
            } else {
                XCTFail("Expected .unavailable for gated machinery-* slug, got \(hubVM.state)")
            }

            let spyDiscoverLoader = SpyMachineryPreviewLoader()
            let discoverAuth = AuthManager()
            discoverAuth.user = candidateUser
            _ = renderView(
                DiscoverView(machineryPreviewLoader: spyDiscoverLoader)
                    .environmentObject(discoverAuth)
                    .environmentObject(NavigationCoordinator())
                    .environmentObject(PinManager())
                    .frame(width: 390, height: 600),
                width: 390,
                maxHeight: 600
            )
            XCTAssertEqual(
                spyDiscoverLoader.callCount,
                0,
                "DiscoverView must make ZERO machinery requests for \(String(describing: candidateUser?.email)) while switch is off"
            )
        }

        // Flip switch ON for Alex -> access granted; sign out -> immediately revoked.
        GroupingMachineryGate12288.setActiveUser(ownerAlex)
        GroupingMachineryGate12288.setSwitchEnabled(true, for: ownerAlex)
        XCTAssertTrue(GroupingMachineryGate12288.canAccessMachinery(user: ownerAlex))
        XCTAssertTrue(GroupingMachineryGate12288.canAccessMachineryCurrentUser())

        GroupingMachineryGate12288.setActiveUser(nil)
        XCTAssertFalse(GroupingMachineryGate12288.canAccessMachineryCurrentUser())
    }

    // MARK: - 2. Direction 228 Scale Order, 3-Row Cap, Real Art Only & All 8 Forms

    func testDirection228ScaleOrderThreeRowCapAndRealArtOnly() throws {
        // Out-of-order Fed rate move scale -> automatically sorted ascending from largest cut to hike.
        let rawOutcomes = [
            MachineryOutcomeVisual(outcomeId: 1, name: "No change", probability: 0.58, renderedPercent: 58),
            MachineryOutcomeVisual(outcomeId: 2, name: "Hike 25 bps", probability: 0.04, renderedPercent: 4),
            MachineryOutcomeVisual(outcomeId: 3, name: "Cut 25 bps", probability: 0.31, renderedPercent: 31),
            MachineryOutcomeVisual(outcomeId: 4, name: "Cut 50+ bps", probability: 0.07, renderedPercent: 7)
        ]
        let market = MachineryMarketVisualItem(
            marketId: 77001,
            title: "January 2027 FOMC Rate Decision",
            scaleOrdered: false,
            leaderOutcomeId: 1,
            outcomes: rawOutcomes
        )
        let normalized = MachineryMarketVisualItem.normalizedOutcomes(rawOutcomes, scaleOrdered: false)
        XCTAssertEqual(normalized.map(\.name), ["Cut 50+ bps", "Cut 25 bps", "No change", "Hike 25 bps"])
        XCTAssertTrue(market.effectiveScaleOrdered)

        // Flat history chart is rejected (`hasMovingSeries == false`).
        let flatChart = MachineryHistoryChartItem(
            marketId: 88001,
            title: "Flat Market",
            series: [
                MachineryHistorySeries(
                    outcomeId: 1,
                    name: "Option A",
                    currentPct: 50,
                    color: "#2563EB",
                    points: [.init(t: "2026-11-10T00:00:00Z", pct: 50), .init(t: "2026-11-17T00:00:00Z", pct: 50)]
                )
            ]
        )
        XCTAssertFalse(flatChart.hasMovingSeries)

        // Missing art (`url == nil`) draws NOTHING — zero monogram initials.
        let missingArtContender = MachineryMarketVisualItem(
            marketId: 99001,
            title: "Contender Field",
            outcomes: [
                MachineryOutcomeVisual(outcomeId: 11, name: "Zeta Candidate", probability: 0.44, renderedPercent: 44, art: .init(url: nil, kind: "monogram")),
                MachineryOutcomeVisual(outcomeId: 12, name: "Beta Candidate", probability: 0.33, renderedPercent: 33, art: .init(url: nil, kind: "monogram")),
                MachineryOutcomeVisual(outcomeId: 13, name: "Gamma Candidate", probability: 0.15, renderedPercent: 15, art: .init(url: nil, kind: "monogram")),
                MachineryOutcomeVisual(outcomeId: 14, name: "Delta Candidate", probability: 0.08, renderedPercent: 8, art: .init(url: nil, kind: "monogram"))
            ]
        )
        let block = MachineryVisualBlock(
            formId: .contenderSpotlight,
            initialVisibleLimit: 3,
            marketItems: [missingArtContender]
        )
        let img = renderView(
            NavigationStack {
                MachinerySectionBlockView(visualBlock: block, members: [])
                    .padding(16)
            }
            .frame(width: 390),
            width: 390,
            maxHeight: 900
        )
        let strings = try recognizeStrings(in: XCTUnwrap(img.cgImage))
        let joined = strings.joined(separator: " | ")
        XCTAssertTrue(joined.contains("Show all 4 contenders (+1 more)"), "Expected 3-row Show all expander: \(joined)")
        XCTAssertFalse(strings.contains("ZC"), "Must never render placeholder monogram letters 'ZC': \(joined)")
        XCTAssertFalse(strings.contains("BC"), "Must never render placeholder monogram letters 'BC': \(joined)")
        XCTAssertFalse(strings.contains("GC"), "Must never render placeholder monogram letters 'GC': \(joined)")
    }

    // MARK: - 2b. Follow-Up Polish (#12924): Shared Left Edge, Distinct Chart Series Colours & No Duplicate Page Headline

    func testFollowUpPolishSharedNameLeftEdgeDistinctChartSeriesColorsAndNoDuplicatePageHeadline() throws {
        // (1) Distinct chart series colours even when the server sends 3 identical purple or blue hexes.
        let threePurple: [MachineryHistorySeries] = [
            .init(outcomeId: 1, name: "Kevin Warsh", currentPct: 42, color: "#7C3AED", points: [.init(t: "2026-11-10T00:00:00Z", pct: 35), .init(t: "2026-11-17T00:00:00Z", pct: 42)]),
            .init(outcomeId: 2, name: "Scott Bessent", currentPct: 31, color: "#7C3AED", points: [.init(t: "2026-11-10T00:00:00Z", pct: 34), .init(t: "2026-11-17T00:00:00Z", pct: 31)]),
            .init(outcomeId: 3, name: "Christopher Waller", currentPct: 19, color: "#7C3AED", points: [.init(t: "2026-11-10T00:00:00Z", pct: 22), .init(t: "2026-11-17T00:00:00Z", pct: 19)])
        ]
        let threeBlue: [MachineryHistorySeries] = [
            .init(outcomeId: 1, name: "No change", currentPct: 54, color: "#2563EB", points: [.init(t: "2026-11-10T00:00:00Z", pct: 48), .init(t: "2026-11-17T00:00:00Z", pct: 54)]),
            .init(outcomeId: 2, name: "25 bps cut", currentPct: 36, color: "#2563EB", points: [.init(t: "2026-11-10T00:00:00Z", pct: 41), .init(t: "2026-11-17T00:00:00Z", pct: 36)]),
            .init(outcomeId: 3, name: "50+ bps cut", currentPct: 10, color: "#2563EB", points: [.init(t: "2026-11-10T00:00:00Z", pct: 11), .init(t: "2026-11-17T00:00:00Z", pct: 10)])
        ]
        for isDark in [false, true] {
            let resolvedPurple = MachineryChartSeriesPalette12288.resolvedHexes(for: threePurple, isDark: isDark)
            let resolvedBlue = MachineryChartSeriesPalette12288.resolvedHexes(for: threeBlue, isDark: isDark)
            XCTAssertEqual(Set(resolvedPurple).count, 3, "Expected 3 distinct colours for 3 purple series (isDark=\(isDark)): \(resolvedPurple)")
            XCTAssertEqual(Set(resolvedBlue).count, 3, "Expected 3 distinct colours for 3 blue series (isDark=\(isDark)): \(resolvedBlue)")
            for group in [resolvedPurple, resolvedBlue] {
                let metrics = try group.map { try XCTUnwrap(MachineryChartSeriesPalette12288.parseMetrics($0)) }
                XCTAssertTrue(MachineryChartSeriesPalette12288.areDistinct(metrics[0], metrics[1]))
                XCTAssertTrue(MachineryChartSeriesPalette12288.areDistinct(metrics[0], metrics[2]))
                XCTAssertTrue(MachineryChartSeriesPalette12288.areDistinct(metrics[1], metrics[2]))
            }
        }
        // Served distinct colours (Blue vs Red) stay intact in light mode.
        let twoDistinct: [MachineryHistorySeries] = [
            .init(outcomeId: 1, name: "Democratic", currentPct: 52, color: "#2563EB", points: []),
            .init(outcomeId: 2, name: "Republican", currentPct: 48, color: "#DC2626", points: [])
        ]
        XCTAssertEqual(
            MachineryChartSeriesPalette12288.resolvedHexes(for: twoDistinct, isDark: false),
            ["#2563EB", "#DC2626"]
        )

        // (2) Shared left edge: an outcome without art aligns with its illustrated neighbour's name left edge.
        let samplePosterURL = "https://image.tmdb.org/t/p/w342/sample_poster_12288.jpg"
        let solidPoster = UIGraphicsImageRenderer(size: CGSize(width: 56, height: 80)).image { ctx in
            UIColor(red: 0.14, green: 0.42, blue: 0.34, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 56, height: 80))
        }
        let siblingMarket = MachineryMarketVisualItem(
            marketId: 99101,
            title: "Animated Feature",
            outcomes: [
                MachineryOutcomeVisual(
                    outcomeId: 1,
                    name: "Wildwood",
                    probability: 0.46,
                    renderedPercent: 46,
                    art: .init(url: samplePosterURL, kind: "tmdb_poster")
                ),
                MachineryOutcomeVisual(
                    outcomeId: 2,
                    name: "Hoppers",
                    probability: 0.34,
                    renderedPercent: 34,
                    art: nil
                )
            ]
        )
        let siblingBlock = MachineryVisualBlock(
            formId: .siblingFieldsGrid,
            initialVisibleLimit: 3,
            marketItems: [siblingMarket]
        )
        let siblingImg = renderSurface(
            MachinerySectionBlockView(visualBlock: siblingBlock, members: []).padding(16),
            preloadedImages: [samplePosterURL: solidPoster],
            style: .light,
            dynamicType: .large,
            maxHeight: 600
        )
        let siblingBoxes = try recognizeObservationBoxes(in: XCTUnwrap(siblingImg.cgImage))
        let wildwoodX = try XCTUnwrap(siblingBoxes.first(where: { $0.text.contains("Wildwood") })?.minXPx)
        let hoppersX = try XCTUnwrap(siblingBoxes.first(where: { $0.text.contains("Hoppers") })?.minXPx)
        XCTAssertLessThanOrEqual(
            abs(wildwoodX - hoppersX),
            12.0,
            "Artless sibling 'Hoppers' (\(hoppersX) px) must share 'Wildwood' left edge (\(wildwoodX) px)"
        )

        // (3) Embedded paired card inside a page section drops its own eyebrow and duplicate headline,
        // while the Discover card keeps both.
        let oscarsSetJSON = """
        {
          "set_id": "oscars-best-picture",
          "category": "entertainment",
          "kicker": "Awards · Oscars",
          "title": "Oscars Best Picture",
          "subtitle": "99th Academy Awards",
          "stage1_label": "Nominated",
          "stage2_label": "Winner",
          "stage1_settled": false,
          "primary_stage1_market_id": 501,
          "primary_stage2_market_id": 502,
          "entries": [
            {
              "subject_key": "odyssey",
              "subject": "The Odyssey",
              "detail": "",
              "stage1_market_id": 501,
              "stage2_market_id": 502,
              "stage1_probability": 0.88,
              "stage2_probability": 0.29,
              "art": {
                "kind": "tmdb_poster",
                "url": "\(samplePosterURL)",
                "verified_subject_match": true
              }
            },
            {
              "subject_key": "hoppers",
              "subject": "Hoppers",
              "detail": "",
              "stage1_market_id": 501,
              "stage2_market_id": 502,
              "stage1_probability": 0.54,
              "stage2_probability": 0.11
            }
          ]
        }
        """
        let oscarsSet = try JSONDecoder().decode(PairedMetricSet.self, from: Data(oscarsSetJSON.utf8))
        let pagePairedBlock = MachineryVisualBlock(
            formId: .pairedStageBars,
            initialVisibleLimit: 3,
            pairedMetricSet: oscarsSet
        )
        let pageSectionImg = renderSurface(
            MachinerySectionBlockView(visualBlock: pagePairedBlock, members: []).padding(16),
            preloadedImages: [samplePosterURL: solidPoster],
            style: .light,
            dynamicType: .large,
            maxHeight: 800
        )
        let pageSectionBoxes = try recognizeObservationBoxes(in: XCTUnwrap(pageSectionImg.cgImage))
        let pageSectionJoined = pageSectionBoxes.map { $0.text }.joined(separator: " | ")
        XCTAssertFalse(
            pageSectionJoined.localizedCaseInsensitiveContains("Oscars Best Picture"),
            "Embedded page section card must drop its own duplicate headline: \(pageSectionJoined)"
        )
        XCTAssertFalse(
            pageSectionJoined.localizedCaseInsensitiveContains("AWARDS"),
            "Embedded page section card must drop its own eyebrow: \(pageSectionJoined)"
        )
        let odysseyX = try XCTUnwrap(pageSectionBoxes.first(where: { $0.text.contains("The Odyssey") })?.minXPx)
        let pairedHoppersX = try XCTUnwrap(pageSectionBoxes.first(where: { $0.text.contains("Hoppers") })?.minXPx)
        XCTAssertLessThanOrEqual(
            abs(odysseyX - pairedHoppersX),
            12.0,
            "Artless paired row 'Hoppers' (\(pairedHoppersX) px) must share 'The Odyssey' left edge (\(odysseyX) px)"
        )

        // Meanwhile, the Discover card still renders its eyebrow and headline.
        let oscarsCardJSON = """
        {
          "slug": "machinery-oscars-best-picture",
          "form_id": "paired_stage_bars",
          "kicker": "Awards · Oscars",
          "title": "Oscars Best Picture",
          "subtitle": "99th Academy Awards",
          "section_count": 4,
          "footer": ""
        }
        """
        let oscarsCard = try JSONDecoder().decode(MachineryCardContract.self, from: Data(oscarsCardJSON.utf8))
        let discoverCardImg = renderSurface(
            MachineryDiscoverEntryCardView(card: oscarsCard, pairedMetricSet: oscarsSet).padding(16),
            preloadedImages: [samplePosterURL: solidPoster],
            style: .light,
            dynamicType: .large,
            maxHeight: 900
        )
        let discoverJoined = try recognizeStrings(in: XCTUnwrap(discoverCardImg.cgImage)).joined(separator: " | ")
        XCTAssertTrue(discoverJoined.localizedCaseInsensitiveContains("Oscars Best Picture"))
    }

    // MARK: - 3. Live 4 Groupings: Decode, 227: A Screen Counts, Largest Dynamic Type & 390 px Renders

    func testLiveFourGroupingsCardsPagesDiversityCountsAnd390PxRenders() throws {
        let inputDir = URL(fileURLWithPath: "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/renders-12288")
        let renderDir = URL(fileURLWithPath: "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/renders-12288-polish")
        let liveJSONPath = inputDir.appendingPathComponent("live_machinery_preview_12288.json")
        let manifestPath = inputDir.appendingPathComponent("art_manifest.json")

        let payloadData: Data
        if let diskData = try? Data(contentsOf: liveJSONPath) {
            payloadData = diskData
        } else {
            payloadData = Data(Self.embeddedFallbackPreviewJSON.utf8)
        }

        // Prove decoding works under BOTH APIClient's `.convertFromSnakeCase` decoder AND raw `JSONDecoder()`.
        let snakeDecoder = JSONDecoder()
        snakeDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let previewSnake = try snakeDecoder.decode(MachineryPreviewResponse.self, from: payloadData)
        let previewRaw = try JSONDecoder().decode(MachineryPreviewResponse.self, from: payloadData)
        XCTAssertEqual(previewSnake.items.map(\.slug), previewRaw.items.map(\.slug))
        XCTAssertGreaterThanOrEqual(previewSnake.items.count, 1)

        var preloadedImages: [String: UIImage] = [:]
        if let manifestData = try? Data(contentsOf: manifestPath),
           let manifest = try? JSONSerialization.jsonObject(with: manifestData) as? [String: String] {
            for (urlStr, localPath) in manifest {
                if let data = try? Data(contentsOf: URL(fileURLWithPath: localPath)),
                   let uiImg = UIImage(data: data) {
                    preloadedImages[urlStr] = uiImg
                    if let url = URL(string: urlStr),
                       let httpResp = HTTPURLResponse(
                           url: url,
                           statusCode: 200,
                           httpVersion: "HTTP/1.1",
                           headerFields: ["Content-Type": localPath.hasSuffix(".png") ? "image/png" : "image/jpeg"]
                       ) {
                        URLCache.shared.storeCachedResponse(
                            CachedURLResponse(response: httpResp, data: data),
                            for: URLRequest(url: url)
                        )
                    }
                }
            }
        }

        let suiteName = "GroupingMachinery12288Tests.Live.\(UUID().uuidString)"
        let isolatedDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { isolatedDefaults.removePersistentDomain(forName: suiteName) }
        GroupingMachineryGate12288.setOverrideDefaultsForTesting(isolatedDefaults)
        let ownerAlex = AuthUser(
            id: 364,
            email: "owner@example.com",
            displayName: "Owner Account",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        GroupingMachineryGate12288.setActiveUser(ownerAlex)
        GroupingMachineryGate12288.setSwitchEnabled(true, for: ownerAlex)

        var iphoneDiversitySummary: [[String: Any]] = []
        let canExportDisk = FileManager.default.fileExists(atPath: renderDir.path)

        for entry in previewSnake.items {
            let card = try XCTUnwrap(entry.machineryCard, "Missing machineryCard for \(entry.slug)")
            let hubResponse = try XCTUnwrap(entry.container, "Missing container for \(entry.slug)")

            // Enforce <= 3 rows on every Discover card
            XCTAssertLessThanOrEqual(card.eventRows.count, 3)
            XCTAssertLessThanOrEqual(card.outcomeRows.count, 3)
            if let pset = entry.pairedMetricSet {
                XCTAssertLessThanOrEqual(pset.entries.count, 3)
            }

            // Render Discover Card (390 px Light & Dark)
            let cardLightImg = renderSurface(
                MachineryDiscoverEntryCardView(card: card, pairedMetricSet: entry.pairedMetricSet)
                    .padding(16),
                preloadedImages: preloadedImages,
                style: .light,
                dynamicType: .large,
                maxHeight: 1_200
            )
            let cardDarkImg = renderSurface(
                MachineryDiscoverEntryCardView(card: card, pairedMetricSet: entry.pairedMetricSet)
                    .padding(16),
                preloadedImages: preloadedImages,
                style: .dark,
                dynamicType: .large,
                maxHeight: 1_200
            )

            // Verify zero truncation ("…") & zero forbidden copy on card at `.large` AND `.xxxLarge`
            let cardLargeOCR = try recognizeStrings(in: XCTUnwrap(cardLightImg.cgImage))
            assertCleanCopyAndNoEllipsis(cardLargeOCR, context: "card(\(entry.slug), .large)")

            let cardXXXLargeImg = renderSurface(
                MachineryDiscoverEntryCardView(card: card, pairedMetricSet: entry.pairedMetricSet)
                    .padding(16),
                preloadedImages: preloadedImages,
                style: .light,
                dynamicType: .xxxLarge,
                maxHeight: 2_000
            )
            let cardXXXLargeOCR = try recognizeStrings(in: XCTUnwrap(cardXXXLargeImg.cgImage))
            assertCleanCopyAndNoEllipsis(cardXXXLargeOCR, context: "card(\(entry.slug), .xxxLarge)")

            // Render Container Page (`ContainerHubView` with seeded `SpyContainerHubService`, 390 px Light & Dark)
            let presentation = ContainerHubPresentation(response: hubResponse)
            XCTAssertFalse(presentation.isPartial, "\(entry.slug) container must not mark healthy machinery sections partial")

            let pageLightResult = renderAndMeasureContainerPage(
                presentation: presentation,
                displayName: entry.displayName,
                preloadedImages: preloadedImages,
                style: .light,
                dynamicType: .large
            )
            let pageDarkResult = renderAndMeasureContainerPage(
                presentation: presentation,
                displayName: entry.displayName,
                preloadedImages: preloadedImages,
                style: .dark,
                dynamicType: .large
            )
            let pageXXXLargeResult = renderAndMeasureContainerPage(
                presentation: presentation,
                displayName: entry.displayName,
                preloadedImages: preloadedImages,
                style: .light,
                dynamicType: .xxxLarge
            )

            let pageLargeOCR = try recognizeStrings(in: XCTUnwrap(pageLightResult.image.cgImage))
            assertCleanCopyAndNoEllipsis(pageLargeOCR, context: "page(\(entry.slug), .large)")

            let pageXXXLargeOCR = try recognizeStrings(in: XCTUnwrap(pageXXXLargeResult.image.cgImage))
            assertCleanCopyAndNoEllipsis(pageXXXLargeOCR, context: "page(\(entry.slug), .xxxLarge)")

            // Compute iPhone 227: A counts across 390x844 phone screens
            let counts = computeIPhone227ACounts(
                entry: entry,
                presentation: presentation,
                pageHeightPt: pageLightResult.heightPt,
                pictureBoxesPt: pageLightResult.pictureBoxesPt
            )
            iphoneDiversitySummary.append(counts)

            if canExportDisk {
                try? cardLightImg.pngData()?.write(to: renderDir.appendingPathComponent("12288-card-\(entry.slug)-light-390.png"))
                try? cardDarkImg.pngData()?.write(to: renderDir.appendingPathComponent("12288-card-\(entry.slug)-dark-390.png"))
                try? pageLightResult.image.pngData()?.write(to: renderDir.appendingPathComponent("12288-page-\(entry.slug)-light-390.png"))
                try? pageDarkResult.image.pngData()?.write(to: renderDir.appendingPathComponent("12288-page-\(entry.slug)-dark-390.png"))
            }
        }

        if canExportDisk {
            // Also export Preferences owner-switch render (390 px Light & Dark)
            let samplePrefs = PreferencesResponse(
                homeLocation: nil,
                sportAffinities: [:],
                onboardingCompleted: true,
                favorites: [],
                pushPreferences: nil
            )
            let ownerAuth = AuthManager()
            ownerAuth.user = ownerAlex
            let prefsLight = renderSurface(
                PreferencesView(loadedPrefsForTest: samplePrefs)
                    .environmentObject(ownerAuth)
                    .navigationBarTitleDisplayMode(.inline),
                preloadedImages: preloadedImages,
                style: .light,
                dynamicType: .large,
                maxHeight: 900
            )
            let prefsDark = renderSurface(
                PreferencesView(loadedPrefsForTest: samplePrefs)
                    .environmentObject(ownerAuth)
                    .navigationBarTitleDisplayMode(.inline),
                preloadedImages: preloadedImages,
                style: .dark,
                dynamicType: .large,
                maxHeight: 900
            )
            try? prefsLight.pngData()?.write(to: renderDir.appendingPathComponent("12288-preferences-owner-switch-light-390.png"))
            try? prefsDark.pngData()?.write(to: renderDir.appendingPathComponent("12288-preferences-owner-switch-dark-390.png"))

            let summaryData = try JSONSerialization.data(withJSONObject: iphoneDiversitySummary, options: [.prettyPrinted, .sortedKeys])
            try summaryData.write(to: renderDir.appendingPathComponent("iphone_227a_counts_12288.json"))
        }
    }

    // MARK: - Measurement & Rendering Helpers

    private func assertCleanCopyAndNoEllipsis(_ lines: [String], context: String) {
        let joined = lines.joined(separator: " | ")
        for line in lines {
            XCTAssertFalse(
                line.contains("…") || line.contains("..."),
                "Truncated text '\(line)' in \(context): \(joined)"
            )
            let lower = line.lowercased()
            XCTAssertFalse(lower.contains("kalshi"), "Forbidden venue name 'Kalshi' in \(context): \(line)")
            XCTAssertFalse(lower.contains("polymarket"), "Forbidden venue name 'Polymarket' in \(context): \(line)")
            XCTAssertFalse(
                lower.range(of: "\\bquestions?\\b", options: .regularExpression) != nil,
                "Forbidden word 'question(s)' in \(context): \(line)"
            )
        }
    }

    private func computeIPhone227ACounts(
        entry: MachineryPreviewEntry,
        presentation: ContainerHubPresentation,
        pageHeightPt: CGFloat,
        pictureBoxesPt: [CGRect]
    ) -> [String: Any] {
        let screenHeight: CGFloat = 844.0
        let screenCount = max(1, Int(ceil(pageHeightPt / screenHeight)))
        var picsPerScreen: [Int] = []
        for idx in 0..<screenCount {
            let top = CGFloat(idx) * screenHeight
            let bot = CGFloat(idx + 1) * screenHeight
            let count = pictureBoxesPt.filter { box in
                box.maxY > top + 8 && box.minY < bot - 8
            }.count
            picsPerScreen.append(count)
        }

        var distinctForms: [String] = []
        var longestRun = 0
        var currentRun = 0
        var prevForm: String? = nil

        for sec in presentation.displaySections {
            guard let vb = sec.visualBlock else { continue }
            let f = vb.formId.rawValue
            if !distinctForms.contains(f) {
                distinctForms.append(f)
            }
            let visibleUnits: Int = {
                let lim = vb.effectiveVisibleLimit
                switch vb.formId {
                case .pairedStageBars:
                    return min(lim, vb.pairedMetricSet?.entries.count ?? 0)
                case .probabilityHistoryChart:
                    return min(lim, vb.historyItems.count)
                case .coinFlipMatchups:
                    return min(lim, vb.eventItems.count)
                case .matchupSlate:
                    return min(lim, max(sec.members.count, vb.eventItems.count))
                case .duelBar:
                    return vb.marketItems.isEmpty ? 0 : 1
                case .contenderSpotlight:
                    guard let lead = vb.marketItems.first else { return 0 }
                    return lead.effectiveScaleOrdered ? min(lim, lead.outcomes.count) : 1
                case .siblingFieldsGrid, .benchmarkStrip:
                    return min(lim, vb.marketItems.count)
                }
            }()
            if f == prevForm {
                currentRun += visibleUnits
            } else {
                currentRun = visibleUnits
                prevForm = f
            }
            longestRun = max(longestRun, currentRun)
        }

        // Content kinds from section layout + members
        var kindCounts: [String: Int] = [:]
        for sec in presentation.sections {
            let layout = sec.layout ?? sec.visualBlock?.formId.rawValue ?? ""
            if layout == "probability_history_chart" {
                let c = max(sec.visualBlock?.historyItems.count ?? 0, sec.slots.count)
                kindCounts["history", default: 0] += c
            } else if layout == "coin_flip_matchups" || layout == "matchup_slate" {
                let c = max(sec.visualBlock?.eventItems.count ?? 0, sec.slots.count)
                kindCounts["games", default: 0] += c
            } else if sec.sectionClass.contains("prop") {
                let c = max(sec.visualBlock?.marketItems.count ?? 0, sec.slots.count)
                kindCounts["props", default: 0] += c
            } else {
                let c = max(
                    sec.visualBlock?.marketItems.count ?? (sec.visualBlock?.pairedMetricSet != nil ? sec.slots.count : 0),
                    sec.slots.count
                )
                kindCounts["futures", default: 0] += c
            }
        }
        let totalTyped = max(1, kindCounts.values.reduce(0, +))
        let largestPair = kindCounts.sorted { a, b in
            if a.value != b.value { return a.value > b.value }
            return a.key < b.key
        }.first
        let largestKind = largestPair?.key ?? "futures"
        let largestShare = Double(largestPair?.value ?? 0) / Double(totalTyped)

        let cardPics: Int = {
            guard let card = entry.machineryCard else { return 0 }
            if card.formId == .pairedStageBars, let pset = entry.pairedMetricSet {
                return pset.entries.prefix(3).filter { PairedMetricPresentation.resolveKidSafeVisualArt($0) != nil }.count
            }
            if card.isEventCard {
                return card.eventRows.prefix(3).reduce(0) { acc, r in
                    acc + (r.awayArt?.verifiedURL != nil ? 1 : 0) + (r.homeArt?.verifiedURL != nil ? 1 : 0)
                }
            }
            let rowArt = card.outcomeRows.prefix(3).filter { $0.art?.verifiedURL != nil }.count
            return rowArt + (card.miniChart != nil ? 1 : 0)
        }()

        let cardRowsCount: Int = {
            guard let card = entry.machineryCard else { return 0 }
            if card.formId == .pairedStageBars, let pset = entry.pairedMetricSet {
                return min(3, pset.entries.count)
            }
            return card.isEventCard ? min(3, card.eventRows.count) : min(3, card.outcomeRows.count)
        }()

        return [
            "slug": entry.slug,
            "name": entry.displayName,
            "card_form": entry.machineryCard?.formId.rawValue ?? "",
            "card_pictures": cardPics,
            "card_rows": cardRowsCount,
            "page_height_pt_at_390": Int(round(pageHeightPt)),
            "screen_count_390x844": screenCount,
            "pictures_per_screen_390x844": picsPerScreen,
            "min_pictures_per_screen": picsPerScreen.min() ?? 0,
            "longest_form_run": longestRun,
            "distinct_forms": distinctForms,
            "form_count": distinctForms.count,
            "content_kinds": kindCounts,
            "largest_kind": largestKind,
            "largest_kind_share": round(largestShare * 1000.0) / 10.0
        ]
    }

    private final class PictureFrameCollector {
        var rects: [CGRect] = []
    }

    private func renderAndMeasureContainerPage(
        presentation: ContainerHubPresentation,
        displayName: String,
        preloadedImages: [String: UIImage],
        style: UIUserInterfaceStyle,
        dynamicType: DynamicTypeSize
    ) -> (image: UIImage, heightPt: CGFloat, pictureBoxesPt: [CGRect]) {
        let collector = PictureFrameCollector()
        let pageContent = VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "chevron.left")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(style == .dark ? DS.emerald : DS.greenReadable)
                Spacer()
                if dynamicType < .xxxLarge, !displayName.isEmpty, displayName.count <= 28 {
                    Text(displayName)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(style == .dark ? Color.white : DS.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                }
                Spacer()
                Color.clear.frame(width: 14, height: 14)
            }
            .padding(.horizontal, 16)
            .frame(height: 44)
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(style == .dark ? Color.white.opacity(0.12) : DS.border)
                    .frame(height: 0.5)
            }

            VStack(alignment: .leading, spacing: 16) {
                if let title = presentation.title {
                    Text(title)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(style == .dark ? Color.white : DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let subtitle = presentation.subtitle {
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(style == .dark ? Color(white: 0.72) : DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(presentation.displaySections) { section in
                    if let visualBlock = section.visualBlock {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(presentation.resolvedSectionTitle(section))
                                    .font(.headline)
                                    .foregroundStyle(style == .dark ? Color.white : DS.textPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let sectionNote = section.note?.trimmingCharacters(in: .whitespacesAndNewlines),
                                   !sectionNote.isEmpty {
                                    Text(sectionNote)
                                        .font(.subheadline)
                                        .foregroundStyle(style == .dark ? Color(white: 0.72) : DS.textSecondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .padding(.top, 4)

                            MachinerySectionBlockView(
                                visualBlock: visualBlock,
                                members: section.members
                            )
                        }
                    }
                }
            }
            .padding(18)
        }
        .frame(width: 390, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .coordinateSpace(name: "machineryPageRoot12288")
        .onPreferenceChange(MachineryRenderedPictureFramesKey12288.self) { frames in
            collector.rects = frames
        }
        .background(style == .dark ? Color.black : DS.surface)
        .environment(\.machineryPreloadedImages12288, preloadedImages)
        .environment(\.colorScheme, style == .dark ? .dark : .light)
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())

        // Step 1: measure intrinsic content height outside NavigationStack so NavigationStack's
        // greedy container does not inflate height to 6,000 pt.
        let sizingHost = hostForMeasurement(pageContent, at: dynamicType)
        sizingHost.safeAreaRegions = []
        sizingHost.overrideUserInterfaceStyle = style
        let intrinsicHeight = max(240, ceil(sizingHost.sizeThatFits(in: CGSize(width: 390, height: 10_000)).height))

        // Step 2: host inside NavigationStack at the exact measured height so every NavigationLink
        // renders enabled at full 100% contrast (zero disabled-link dimming).
        let hostedStack = NavigationStack {
            pageContent
        }
        let host = hostForMeasurement(hostedStack, at: dynamicType)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = style
        let finalSize = CGSize(width: 390, height: intrinsicHeight)
        host.view.frame = CGRect(origin: .zero, size: finalSize)

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let deadline = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < deadline

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = finalSize.height > 3_600 ? 1.5 : (finalSize.height > 2_400 ? 2.0 : 3.0)
        let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        return (img, finalSize.height, collector.rects)
    }

    private func renderSurface<V: View>(
        _ content: V,
        preloadedImages: [String: UIImage],
        style: UIUserInterfaceStyle,
        dynamicType: DynamicTypeSize,
        maxHeight: CGFloat
    ) -> UIImage {
        let base = content
            .frame(width: 390, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
            .background(style == .dark ? Color.black : DS.surface)
            .environment(\.machineryPreloadedImages12288, preloadedImages)
            .environment(\.colorScheme, style == .dark ? .dark : .light)
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())

        let sizingHost = hostForMeasurement(base, at: dynamicType)
        sizingHost.safeAreaRegions = []
        sizingHost.overrideUserInterfaceStyle = style
        let intrinsicHeight = max(180, min(maxHeight, ceil(sizingHost.sizeThatFits(in: CGSize(width: 390, height: maxHeight)).height)))

        let wrapped = NavigationStack { base }
        return renderView(wrapped, width: 390, exactHeight: intrinsicHeight, maxHeight: maxHeight, style: style, dynamicType: dynamicType)
    }

    private func renderView<V: View>(
        _ view: V,
        width: CGFloat,
        exactHeight: CGFloat? = nil,
        maxHeight: CGFloat,
        style: UIUserInterfaceStyle = .light,
        dynamicType: DynamicTypeSize = .large
    ) -> UIImage {
        let host = hostForMeasurement(view, at: dynamicType)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = style
        let fittingHeight = exactHeight ?? max(200, min(maxHeight, ceil(host.sizeThatFits(in: CGSize(width: width, height: maxHeight)).height)))
        let targetSize = CGSize(width: width, height: fittingHeight)
        host.view.frame = CGRect(origin: .zero, size: targetSize)

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let deadline = Date().addingTimeInterval(0.25)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < deadline

        let finalHeight = exactHeight ?? max(200, min(maxHeight, ceil(host.sizeThatFits(in: CGSize(width: width, height: maxHeight)).height)))
        let finalSize = CGSize(width: width, height: finalHeight)
        host.view.frame = CGRect(origin: .zero, size: finalSize)
        window.frame = host.view.frame
        host.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = finalSize.height > 2_400 ? 2.0 : 3.0
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func recognizeStrings(in cgImage: CGImage) throws -> [String] {
        var output: [String] = []
        let request = VNRecognizeTextRequest { req, _ in
            let observations = (req.results as? [VNRecognizedTextObservation]) ?? []
            output = observations.compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return output
    }

    private func recognizeObservationBoxes(in cgImage: CGImage) throws -> [(text: String, minXPx: CGFloat)] {
        var output: [(String, CGFloat)] = []
        let w = CGFloat(cgImage.width)
        let request = VNRecognizeTextRequest { req, _ in
            let observations = (req.results as? [VNRecognizedTextObservation]) ?? []
            for obs in observations {
                if let s = obs.topCandidates(1).first?.string {
                    output.append((s, obs.boundingBox.minX * w))
                }
            }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return output
    }

    // Minimal offline CI fallback when `/renders-12288/live_machinery_preview_12288.json` is not on disk.
    private static let embeddedFallbackPreviewJSON = """
    {
      "public_switch_enabled": false,
      "count": 1,
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
                  "title": "January 2027 FOMC Rate Decision prices No change at 58%",
                  "subtitle": "Priced probabilities along the policy-move scale from cut to hike.",
                  "footer": "",
                  "scale_ordered": true,
                  "section_count": 2,
                  "destination_href": "/collections/machinery-fed-and-macro",
                  "rows": [
                    {"outcome_id": 1, "name": "Cut 25 bps", "probability": 0.31, "rendered_percent": 31},
                    {"outcome_id": 2, "name": "No change", "probability": 0.58, "rendered_percent": 58},
                    {"outcome_id": 3, "name": "Hike 25 bps", "probability": 0.11, "rendered_percent": 11}
                  ],
                  "mini_chart": {
                    "market_id": 501,
                    "title": "January 2027 FOMC Rate Decision",
                    "href": "/futures/501",
                    "scale_ordered": true,
                    "start_iso": "2026-11-10T00:00:00Z",
                    "end_iso": "2026-11-17T00:00:00Z",
                    "y_min": 0,
                    "y_max": 70,
                    "moved": true,
                    "series": [
                      {
                        "outcome_id": 2,
                        "name": "No change",
                        "current_pct": 58,
                        "color": "#2563EB",
                        "points": [
                          {"t": "2026-11-10T00:00:00Z", "pct": 49},
                          {"t": "2026-11-17T00:00:00Z", "pct": 58}
                        ]
                      }
                    ]
                  }
                }
              }
            }
          },
          "container": {
            "state": "published",
            "slug": "machinery-fed-and-macro",
            "revision": 1001,
            "subtitle": "",
            "container": {
              "id": 1001,
              "kind": "roundup",
              "name": "January 2027 FOMC Rate Decision prices No change at 58%",
              "slug": "machinery-fed-and-macro",
              "category": "economics",
              "status": "published"
            },
            "children": [],
            "sections": [
              {
                "class": "jan_fomc",
                "title": "January 2027 FOMC Rate Decision",
                "note": "Priced probabilities along the policy-move scale from cut to hike.",
                "layout": "contender_spotlight",
                "count": 1,
                "members": [],
                "visual_block": {
                  "form_id": "contender_spotlight",
                  "initial_visible_limit": 3,
                  "items": [
                    {
                      "market_id": 501,
                      "title": "January 2027 FOMC Rate Decision",
                      "href": "/futures/501",
                      "scale_ordered": true,
                      "leader_outcome_id": 2,
                      "outcomes": [
                        {"outcome_id": 1, "name": "Cut 25 bps", "probability": 0.31, "rendered_percent": 31},
                        {"outcome_id": 2, "name": "No change", "probability": 0.58, "rendered_percent": 58},
                        {"outcome_id": 3, "name": "Hike 25 bps", "probability": 0.11, "rendered_percent": 11}
                      ]
                    }
                  ]
                }
              },
              {
                "class": "recession_benchmarks",
                "title": "Recession Benchmark",
                "note": "Yes-or-no market on official U.S. recession calls.",
                "layout": "benchmark_strip",
                "count": 1,
                "members": [],
                "visual_block": {
                  "form_id": "benchmark_strip",
                  "initial_visible_limit": 3,
                  "items": [
                    {
                      "market_id": 502,
                      "title": "U.S. Recession in 2027",
                      "href": "/futures/502",
                      "outcomes": [
                        {"outcome_id": 10, "name": "Yes", "probability": 0.24, "rendered_percent": 24}
                      ]
                    }
                  ]
                }
              }
            ],
            "member_count": 2,
            "withheld": [],
            "withheld_count": 0,
            "assembled": true,
            "known_classes": ["jan_fomc", "recession_benchmarks"],
            "revision_moved": false
          }
        }
      ]
    }
    """
}
