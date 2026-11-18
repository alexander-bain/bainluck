import CryptoKit
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

private nonisolated struct MockOscarsFuturesDetailProvider12577: FuturesDetailProviding {
    let detail: FuturesMarketDetail
    let pairedSet: PairedMetricSet?

    func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
        detail
    }

    func fetchFuturesDetail(id: Int, representation: FuturesRepresentation) async throws -> FuturesMarketDetail {
        detail
    }

    func fetchPairedMetricByMarket(marketId: Int) async throws -> PairedMetricSet? {
        pairedSet
    }
}

private actor MockOscarsHubService12577: ContainerHubLoading {
    let response: ContainerHubResponse
    let ceremonySets: [PairedMetricSet]

    init(response: ContainerHubResponse, ceremonySets: [PairedMetricSet]) {
        self.response = response
        self.ceremonySets = ceremonySets
    }

    nonisolated func load(slug: String) async throws -> ContainerHubResponse {
        await readResponse()
    }

    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
        await readCeremonySets(slug: slug)
    }

    private func readResponse() -> ContainerHubResponse {
        response
    }

    private func readCeremonySets(slug: String) -> [PairedMetricSet] {
        guard slug == "oscars-2027" || slug == "oscars" || slug == "the-oscars" else {
            return []
        }
        return ceremonySets
    }
}

@MainActor
final class OscarsPairedSurfaces12577Tests: XCTestCase {

    private let servedBestPictureJSON = #"""
    {
      "set_id": "oscars-2027-best-picture",
      "category": "entertainment",
      "kicker": "OSCARS 2027 · BEST PICTURE",
      "title": "The Odyssey leads Best Picture, with 7 films at 75%+ to be nominated",
      "subtitle": "99th Academy Awards · Top 10 most likely to be nominated",
      "stage_1_label": "Nominated",
      "stage_2_label": "Wins",
      "stage_1_settled_yes_label": "Nominated",
      "stage_1_settled_no_label": "Not nominated",
      "stage_1_settled": false,
      "stage_1_market": {
        "id": 5165726,
        "companion_polymarket_id": 27988771
      },
      "stage_2_market": {
        "id": 6173044
      },
      "entries": [
        {
          "subject_key": "film:the-odyssey-2026",
          "subject": "The Odyssey",
          "detail": "Christopher Nolan · Universal Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.978,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.525,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1368337,
            "poster_path": "/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
            "url": "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
            "genre_ids": [12, 28, 14],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:you-can-see-everything-2026",
          "subject": "You Can See Everything",
          "detail": "Nathan Fielder & Lance Oppenheim · Blow Out Productions",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.865,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.205,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1765072,
            "poster_path": "/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
            "url": "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
            "genre_ids": [99],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:the-black-ball-2026",
          "subject": "The Black Ball",
          "detail": "Javier Ambrossi & Javier Calvo · Movistar Plus",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.945,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.115,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1422041,
            "poster_path": "/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
            "url": "https://image.tmdb.org/t/p/w342/7HwFQTMghL6HOvzEnXYUvyuZXeh.jpg",
            "genre_ids": [18, 10752],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:dune-part-three-2026",
          "subject": "Dune: Part Three",
          "detail": "Denis Villeneuve · Legendary Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.8225,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.085,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 1170608,
            "poster_path": "/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
            "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
            "genre_ids": [878, 12],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:wild-horse-nine-2026",
          "subject": "Wild Horse Nine",
          "detail": "Martin McDonagh · Searchlight Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.9375,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.015,
          "art": {
            "kind": "tmdb_poster",
            "tmdb_id": 891621,
            "poster_path": "/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
            "url": "https://image.tmdb.org/t/p/w342/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg",
            "genre_ids": [35, 80, 53],
            "adult": false,
            "kid_safe_vetted": true
          }
        },
        {
          "subject_key": "film:artificial-2026",
          "subject": "Artificial",
          "detail": "Luca Guadagnino · Heyday Films",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.575,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.015
        },
        {
          "subject_key": "film:project-hail-mary-2026",
          "subject": "Project Hail Mary",
          "detail": "Phil Lord & Christopher Miller · Amazon MGM Studios",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.76,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01
        },
        {
          "subject_key": "film:the-debut-2026",
          "subject": "The Debut",
          "detail": "A24",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.78,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01
        },
        {
          "subject_key": "film:the-invite-2026",
          "subject": "The Invite",
          "detail": "Olivia Wilde · Annapurna Pictures",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.75,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": 0.01
        },
        {
          "subject_key": "film:i-play-rocky-2026",
          "subject": "I Play Rocky",
          "detail": "Peter Farrelly · Amazon MGM Studios",
          "stage_1_market_id": 5165726,
          "stage_1_probability": 0.49,
          "stage_1_settled_state": null,
          "stage_2_market_id": 6173044,
          "stage_2_probability": null
        }
      ]
    }
    """#

    private func decodeSet(_ json: String) throws -> PairedMetricSet {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(PairedMetricSet.self, from: Data(json.utf8))
    }

    func testOscarsDiscoverFormStaysPairedBarsAtBothEvenAndOddIndicesAndDecodesStageMarkets() throws {
        let set = try decodeSet(servedBestPictureJSON)
        XCTAssertEqual(set.primaryStage1MarketId, 5165726)
        XCTAssertEqual(set.primaryStage2MarketId, 6173044)
        XCTAssertEqual(set.coveredMarketIds, Set([5165726, 27988771, 6173044]))
        XCTAssertFalse(set.stage1Settled)

        // Build 5768 bug: when `preferred` was nil on `/api/feed`, odd `cardIndex` values flipped
        // `roundup:oscars-best-picture` to `.podiumAndTiers` instead of `#12849`'s dual-bar card.
        XCTAssertEqual(
            PairedMetricPresentation.resolvedForm(for: set, preferred: nil, cardIndex: 0),
            .pairedBarsTop5Expandable
        )
        XCTAssertEqual(
            PairedMetricPresentation.resolvedForm(for: set, preferred: nil, cardIndex: 1),
            .pairedBarsTop5Expandable
        )
        XCTAssertEqual(
            PairedMetricPresentation.resolvedForm(for: set, preferred: "podium_and_tiers", cardIndex: 0),
            .podiumAndTiers
        )

        // Discover `groupRelatedItems` admits a `roundup` bundle carrying `paired_metric_set` even if
        // legacy `roundup.rows` is omitted.
        let feedJSON = """
        {
          "items": [
            {
              "type": "bundle",
              "score": 94,
              "headline": "Best Picture",
              "data": {
                "id": "roundup:oscars-best-picture",
                "title": "The Odyssey leads Best Picture, with 7 films at 75%+ to be nominated",
                "kind": "roundup",
                "collection_ref": {
                  "slug": "roundup-oscars-best-picture",
                  "name": "The Odyssey leads Best Picture, with 7 films at 75%+ to be nominated",
                  "revision": 1743654066,
                  "collection_count": 3
                },
                "roundup": {
                  "paired_metric_set": \(servedBestPictureJSON)
                },
                "items": []
              }
            }
          ],
          "total": 1,
          "limit": 40,
          "offset": 0,
          "has_more": false
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(FeedResponse.self, from: Data(feedJSON.utf8))
        let grouped = DiscoverView.groupRelatedItems(feed.items)
        XCTAssertEqual(grouped.count, 1)
    }

    func testFuturesDetailViewModelAndContainerHubLoadServedOscarsPairedPayload() async throws {
        let pairedSet = try decodeSet(servedBestPictureJSON)
        let detailJSON = """
        {
          "id": 6173044,
          "name": "Oscar Winner: Best Picture",
          "category": "entertainment",
          "llm_sport_category": "entertainment",
          "source": "kalshi",
          "status": "open",
          "outcomes": [
            {"id": 31537937, "name": "The Odyssey", "probability": 0.525, "rendered_percent": 53},
            {"id": 226650037, "name": "You Can See Everything", "probability": 0.205, "rendered_percent": 21}
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let marketDetail = try decoder.decode(FuturesMarketDetail.self, from: Data(detailJSON.utf8))

        let provider = MockOscarsFuturesDetailProvider12577(detail: marketDetail, pairedSet: pairedSet)
        let detailVM = FuturesDetailViewModel(marketId: 6173044, client: provider)
        await detailVM.load()
        XCTAssertEqual(detailVM.pairedMetricSet?.setId, "oscars-2027-best-picture")
        XCTAssertEqual(detailVM.pairedMetricSet?.entries.count, 10)

        // Oscars theme hub loads all ceremony paired sets and records covered market IDs for dedup.
        let oscarsHubResponse = try ContainerHubFixture.decode("representative_ai_page_1") { obj in
            obj["slug"] = "oscars-2027"
            obj["edition"] = ["kind": "theme_edition", "subject": "oscars", "edition": 2027]
            if var container = obj["container"] as? [String: Any] {
                container["slug"] = "oscars-2027"
                container["name"] = "Oscars 2027"
                obj["container"] = container
            }
        }
        let hubService = MockOscarsHubService12577(response: oscarsHubResponse, ceremonySets: [pairedSet])
        let hubVM = ContainerHubViewModel(slug: "oscars-2027", service: hubService)
        await hubVM.load()
        XCTAssertTrue(hubVM.isOscarsHub)
        XCTAssertEqual(hubVM.pairedMetricSets.map(\.setId), ["oscars-2027-best-picture"])
        XCTAssertEqual(hubVM.pairedCoveredMarketIds, Set([5165726, 27988771, 6173044]))

        // Member-level `roundup-oscars-best-picture` container (`edition == nil`, `container.kind == "roundup"`)
        // decodes cleanly and surfaces its embedded `paired_metric_set`.
        let roundupContainerJSON = """
        {
          "state": "published",
          "slug": "roundup-oscars-best-picture",
          "revision": 1743654066,
          "edition": null,
          "container": {
            "id": 901,
            "kind": "roundup",
            "name": "The Odyssey leads Best Picture, with 7 films at 75%+ to be nominated",
            "slug": "roundup-oscars-best-picture",
            "category": "entertainment",
            "status": "active"
          },
          "children": [],
          "sections": [],
          "member_count": 0,
          "withheld": [],
          "withheld_count": 0,
          "assembled": true,
          "paired_metric_set": \(servedBestPictureJSON)
        }
        """
        let roundupResponse = try decoder.decode(ContainerHubResponse.self, from: Data(roundupContainerJSON.utf8))
        let roundupService = MockOscarsHubService12577(response: roundupResponse, ceremonySets: [])
        let roundupVM = ContainerHubViewModel(slug: "roundup-oscars-best-picture", service: roundupService)
        await roundupVM.load()
        XCTAssertEqual(roundupVM.pairedMetricSets.map(\.setId), ["oscars-2027-best-picture"])
    }

    func testOscarsPairedSurfacesRenderAt390LightAndDarkWithZeroTruncationOrVenueLeak() throws {
        var setsToRender: [PairedMetricSet] = [try decodeSet(servedBestPictureJSON)]
        var preloaded: [String: UIImage] = [:]

        let cacheDir = URL(fileURLWithPath: "/tmp/builderc-oscars-12577-art", isDirectory: true)
        let ceremonyFile = cacheDir.appendingPathComponent("ceremony_oscars.json")
        if let rawData = try? Data(contentsOf: ceremonyFile) {
            struct CeremonyEnv: Decodable { let sets: [PairedMetricSet] }
            let dec = JSONDecoder()
            dec.keyDecodingStrategy = .convertFromSnakeCase
            if let env = try? dec.decode(CeremonyEnv.self, from: rawData), !env.sets.isEmpty {
                setsToRender = Array(env.sets.prefix(2))
            }
        }
        for pSet in setsToRender {
            for entry in pSet.entries {
                guard let urlStr = entry.art?.url else { continue }
                let digest = SHA256.hash(data: Data(urlStr.utf8))
                    .map { String(format: "%02x", $0) }
                    .joined()
                let prefix = String(digest.prefix(16))
                let ext = urlStr.hasSuffix(".png") ? ".png" : ".jpg"
                let fileURL = cacheDir.appendingPathComponent(prefix + ext)
                if let data = try? Data(contentsOf: fileURL), let img = UIImage(data: data) {
                    preloaded[urlStr] = img
                }
            }
        }

        let bestPicture = setsToRender[0]
        let bestDirector = setsToRender.count > 1 ? setsToRender[1] : nil

        func renderSlice<V: View>(_ content: V, scheme: ColorScheme, dynamicType: DynamicTypeSize = .large) -> UIImage {
            let bg = scheme == .dark
                ? Color(red: 0.05, green: 0.06, blue: 0.09)
                : Color(red: 0.965, green: 0.969, blue: 0.976)
            let wrapped = content
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(width: 390, alignment: .topLeading)
                .background(bg)
                .environment(\.colorScheme, scheme)
                .environment(\.dynamicTypeSize, dynamicType)
            let host = hostForMeasurement(wrapped, at: dynamicType)
            host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 2400))
            let size = CGSize(width: 390, height: min(2400, ceil(fitting.height) + 20))
            host.view.frame = CGRect(origin: .zero, size: size)

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            let until = Date().addingTimeInterval(0.20)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                UIColor.white.setFill()
                ctx.fill(host.view.bounds)
                if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }
        }

        let discoverLight = renderSlice(
            VStack(alignment: .leading, spacing: 10) {
                Text("390 PX · DISCOVER CARD (LIGHT)")
                    .font(.system(size: 11, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(.secondary)
                DiscoverPairedMetricCardView(
                    set: bestPicture,
                    form: .pairedBarsTop5Expandable,
                    initialExpanded: false,
                    preloadedImages: preloaded,
                    onOpenMarket: { _ in },
                    onOpenCollection: { _, _ in }
                )
            },
            scheme: .light
        )

        let discoverDark = renderSlice(
            VStack(alignment: .leading, spacing: 10) {
                Text("390 PX · DISCOVER CARD (DARK)")
                    .font(.system(size: 11, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(.secondary)
                DiscoverPairedMetricCardView(
                    set: bestPicture,
                    form: .pairedBarsTop5Expandable,
                    initialExpanded: false,
                    preloadedImages: preloaded,
                    onOpenMarket: { _ in },
                    onOpenCollection: { _, _ in }
                )
            },
            scheme: .dark
        )

        let categoryExpanded = renderSlice(
            VStack(alignment: .leading, spacing: 10) {
                Text("390 PX · CATEGORY PAGE (/futures/6173044 · EXPANDED)")
                    .font(.system(size: 11, weight: .bold))
                    .tracking(0.6)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                DiscoverPairedMetricCardView(
                    set: bestPicture,
                    form: .pairedBarsTop5Expandable,
                    initialExpanded: true,
                    currentMarketId: 6173044,
                    preloadedImages: preloaded,
                    onOpenMarket: { _ in },
                    onOpenCollection: { _, _ in }
                )
            },
            scheme: .light
        )

        var slices: [UIImage] = [discoverLight, discoverDark, categoryExpanded]
        if let bestDirector {
            let oscarsHubDirector = renderSlice(
                VStack(alignment: .leading, spacing: 10) {
                    Text("390 PX · OSCARS HUB (BEST DIRECTOR HEADSHOTS)")
                        .font(.system(size: 11, weight: .bold))
                        .tracking(0.6)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    DiscoverPairedMetricCardView(
                        set: bestDirector,
                        form: .pairedBarsTop5Expandable,
                        initialExpanded: false,
                        isOscarsCollectionSurface: true,
                        preloadedImages: preloaded,
                        onOpenMarket: { _ in },
                        onOpenCollection: { _, _ in }
                    )
                },
                scheme: .light
            )
            slices.append(oscarsHubDirector)
        }

        // Vision OCR check across rendered slices: zero ellipsis truncation, zero venue names,
        // and both "Nominated" and "Wins" appear.
        var allText: [String] = []
        for slice in slices {
            guard let cg = slice.cgImage else { continue }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
            let recognized = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            allText.append(contentsOf: recognized)
        }
        let joined = allText.joined(separator: "\n")
        XCTAssertTrue(joined.contains("The Odyssey"), "Expected contender title in OCR: \(joined)")
        XCTAssertTrue(joined.contains("Nominated"), "Expected Nominated label in OCR: \(joined)")
        XCTAssertTrue(joined.contains("Wins"), "Expected Wins label in OCR: \(joined)")
        XCTAssertTrue(joined.contains("nominated"), "Expected full word 'nominated' (never 'nom') in OCR: \(joined)")
        XCTAssertFalse(joined.contains("% nom "), "Must never abbreviate 'nominated' to 'nom': \(joined)")
        XCTAssertFalse(joined.contains("…"), "Found ellipsis truncation in OCR: \(joined)")
        XCTAssertFalse(joined.lowercased().contains("kalshi"), "Leaked Kalshi on card face: \(joined)")
        XCTAssertFalse(joined.lowercased().contains("polymarket"), "Leaked Polymarket on card face: \(joined)")

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_12577"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let totalHeight = slices.reduce(CGFloat(0)) { $0 + $1.size.height }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            let combined = UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalHeight), format: fmt).image { _ in
                var y: CGFloat = 0
                for s in slices {
                    s.draw(in: CGRect(x: 0, y: y, width: 390, height: s.size.height))
                    y += s.size.height
                }
            }
            if let png = combined.pngData() {
                try png.write(to: dirURL.appendingPathComponent("12577-oscars-paired-discover-and-category-390.png"))
            }

            // Export largest-text (.xxxLarge & AX5) render of "46% nominated" (Fable look on #12863)
            let xxxLargeSlice = renderSlice(
                VStack(alignment: .leading, spacing: 10) {
                    Text("390 PX · .xxxLarge ('46% nominated' in full)")
                        .font(.system(size: 11, weight: .bold)).foregroundStyle(.secondary)
                    DiscoverPairedMetricCardView(
                        set: bestPicture, form: .pairedBarsTop5Expandable,
                        initialExpanded: false, preloadedImages: preloaded
                    )
                },
                scheme: .light, dynamicType: .xxxLarge
            )
            let ax5Slice = renderSlice(
                VStack(alignment: .leading, spacing: 10) {
                    Text("390 PX · AX5 Largest Accessibility Size ('46% nominated' in full)")
                        .font(.system(size: 11, weight: .bold)).foregroundStyle(.secondary)
                    DiscoverPairedMetricCardView(
                        set: bestPicture, form: .pairedBarsTop5Expandable,
                        initialExpanded: false, preloadedImages: preloaded
                    )
                },
                scheme: .light, dynamicType: .accessibility5
            )
            let largestH = xxxLargeSlice.size.height + ax5Slice.size.height
            let largestCombined = UIGraphicsImageRenderer(size: CGSize(width: 390, height: largestH), format: fmt).image { _ in
                xxxLargeSlice.draw(in: CGRect(x: 0, y: 0, width: 390, height: xxxLargeSlice.size.height))
                ax5Slice.draw(in: CGRect(x: 0, y: xxxLargeSlice.size.height, width: 390, height: ax5Slice.size.height))
            }
            if let png = largestCombined.pngData() {
                try png.write(to: dirURL.appendingPathComponent("12577-oscars-nominated-largest-text-390.png"))
            }
        }
    }
}
