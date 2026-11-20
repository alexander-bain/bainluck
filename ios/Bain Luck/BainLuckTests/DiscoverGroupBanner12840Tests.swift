import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12840 / #12825 — iPhone Discover grouped cards (`NativeGroupCard`) decode and render
/// served `bundle.image_url`, `bundle.image_presentation`, and `bundle.image_monogram`,
/// wear `🎵` on Grammys/music bundles, fall back to team crest or deterministic monogram
/// matching the website, and render cleanly in both Light and Dark mode at 390 px.
@MainActor
final class DiscoverGroupBanner12840Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func grammysBundleJSON() -> String {
        """
        {
          "type": "bundle",
          "score": 88,
          "reason": "",
          "headline": "",
          "data": {
            "id": "theme:story:grammys:1-2",
            "title": "Grammys",
            "kind": "theme",
            "shared_question": "Where do the Grammys races stand?",
            "image_url": "https://image.tmdb.org/t/p/w780/11QwqK3hUCWkLJclPUPzd6tgtxL.jpg",
            "image_presentation": "photo",
            "collection_ref": {
              "slug": "grammys-2027",
              "name": "Grammys 2027",
              "revision": 1,
              "collection_count": 6
            },
            "items": [
              {
                "type": "futures",
                "score": 80,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 70208636,
                  "name": "Grammys 2027: Best Musica Urbana Album Winner",
                  "llm_sport_category": "entertainment",
                  "top_outcomes": [{"id": 1, "name": "Do Not Disturb — Young Miko", "probability": 0.44}]
                }
              },
              {
                "type": "futures",
                "score": 78,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 70208635,
                  "name": "Grammys 2027: Best Latin Pop Album Winner",
                  "llm_sport_category": "entertainment",
                  "top_outcomes": [{"id": 2, "name": "KAROL G", "probability": 0.51}]
                }
              }
            ]
          }
        }
        """
    }

    private func iposBundleJSON() -> String {
        """
        {
          "type": "bundle",
          "score": 84,
          "reason": "",
          "headline": "",
          "data": {
            "id": "theme:story:ipo_markets:30691373-16623139",
            "title": "IPOs",
            "kind": "comparison",
            "shared_question": "Who goes public, and at what price?",
            "image_url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/92/New_York_Stock_Exchange_August_2017_02.jpg/500px-New_York_Stock_Exchange_August_2017_02.jpg",
            "image_presentation": "photo",
            "items": [
              {
                "type": "futures",
                "score": 82,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 30691373,
                  "name": "SpaceX IPO before 2027?",
                  "llm_sport_category": "economics",
                  "top_outcomes": [{"id": 11, "name": "Yes", "probability": 0.31}]
                }
              },
              {
                "type": "futures",
                "score": 79,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 16623139,
                  "name": "Stripe IPO before 2027?",
                  "llm_sport_category": "economics",
                  "top_outcomes": [{"id": 12, "name": "Yes", "probability": 0.42}]
                }
              }
            ]
          }
        }
        """
    }

    private func crestFallbackBundleJSON() -> String {
        """
        {
          "type": "bundle",
          "score": 80,
          "reason": "",
          "headline": "",
          "data": {
            "id": "theme:story:patriots_outlook",
            "title": "New England Patriots",
            "kind": "theme",
            "shared_question": "Where does New England's season stand?",
            "items": [
              {
                "type": "futures",
                "score": 76,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 16630438,
                  "name": "Team to Make Postseason",
                  "llm_sport_category": "football",
                  "top_outcomes": [{"id": 21, "name": "New England Patriots", "probability": 0.23}]
                }
              },
              {
                "type": "futures",
                "score": 74,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 59165023,
                  "name": "AFC #7 Seed",
                  "llm_sport_category": "football",
                  "top_outcomes": [{"id": 22, "name": "New England Patriots", "probability": 0.12}]
                }
              }
            ]
          }
        }
        """
    }

    private func monogramFallbackBundleJSON() -> String {
        """
        {
          "type": "bundle",
          "score": 77,
          "reason": "",
          "headline": "",
          "data": {
            "id": "comparison:kimi-ipo",
            "title": "Kimi Moonshot AI",
            "kind": "comparison",
            "shared_question": "When does Kimi (Moonshot AI) list?",
            "image_url": "https://images.pexels.com/photos/6289047/pexels-photo-6289047.jpeg",
            "items": [
              {
                "type": "futures",
                "score": 75,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 9001,
                  "name": "Kimi IPO before July 2027?",
                  "llm_sport_category": "tech",
                  "top_outcomes": [{"id": 31, "name": "Yes", "probability": 0.28}]
                }
              },
              {
                "type": "futures",
                "score": 73,
                "reason": "",
                "headline": "",
                "data": {
                  "id": 9002,
                  "name": "Kimi IPO before 2028?",
                  "llm_sport_category": "tech",
                  "top_outcomes": [{"id": 32, "name": "Yes", "probability": 0.54}]
                }
              }
            ]
          }
        }
        """
    }

    func testFeedBundleDecodesImageFieldsPreservesAcrossWithItemsAndResolvesFallbacks() throws {
        let grammysItem = try decoder().decode(FeedItem.self, from: Data(grammysBundleJSON().utf8))
        let grammys = try XCTUnwrap(grammysItem.bundle)
        XCTAssertEqual(grammys.imageUrl, "https://image.tmdb.org/t/p/w780/11QwqK3hUCWkLJclPUPzd6tgtxL.jpg")
        XCTAssertEqual(grammys.imagePresentation, "photo")

        let rebuilt = grammys.withItems(Array(grammys.items.prefix(1)))
        XCTAssertEqual(rebuilt.imageUrl, grammys.imageUrl)
        XCTAssertEqual(rebuilt.imagePresentation, "photo")
        XCTAssertEqual(DiscoverBundleVisual12840.eyebrowEmoji(title: "Grammys", category: "entertainment"), "🎵")
        XCTAssertEqual(DiscoverBundleVisual12840.eyebrowEmoji(title: "Oscars", category: "entertainment"), "🎬")

        // Crest fallback when bundle has no image_url and sports title names a known club
        let crestItem = try decoder().decode(FeedItem.self, from: Data(crestFallbackBundleJSON().utf8))
        let crestBundle = try XCTUnwrap(crestItem.bundle)
        let resolvedCrest = DiscoverBundleVisual12840.resolve(
            title: crestBundle.title,
            sharedQuestion: crestBundle.sharedQuestion,
            category: "football",
            bundleImageUrl: crestBundle.imageUrl,
            bundlePresentation: crestBundle.imagePresentation,
            bundleMonogram: crestBundle.imageMonogram,
            items: crestBundle.items
        )
        XCTAssertNil(resolvedCrest.primaryURL)
        XCTAssertNotNil(resolvedCrest.fallbackCrestURL, "Sports grouped card without served image must resolve team crest fallback")

        // Blocked Pexels photo ID ("6289047") is rejected -> falls back to deterministic monogram ("KM")
        let monoItem = try decoder().decode(FeedItem.self, from: Data(monogramFallbackBundleJSON().utf8))
        let monoBundle = try XCTUnwrap(monoItem.bundle)
        let resolvedMono = DiscoverBundleVisual12840.resolve(
            title: monoBundle.title,
            sharedQuestion: monoBundle.sharedQuestion,
            category: "tech",
            bundleImageUrl: monoBundle.imageUrl,
            bundlePresentation: monoBundle.imagePresentation,
            bundleMonogram: monoBundle.imageMonogram,
            items: monoBundle.items
        )
        XCTAssertNil(resolvedMono.primaryURL, "Blocked Pexels photo 6289047 must be rejected")
        XCTAssertNil(resolvedMono.fallbackCrestURL)
        XCTAssertEqual(resolvedMono.monogram.initials, "KM")
    }

    func testGroupedCardsRenderAt390LightAndDarkAndExportContactSheet() async throws {
        let grammys = try XCTUnwrap(decoder().decode(FeedItem.self, from: Data(grammysBundleJSON().utf8)).bundle)
        let ipos = try XCTUnwrap(decoder().decode(FeedItem.self, from: Data(iposBundleJSON().utf8)).bundle)
        let patriots = try XCTUnwrap(decoder().decode(FeedItem.self, from: Data(crestFallbackBundleJSON().utf8)).bundle)
        let kimi = try XCTUnwrap(decoder().decode(FeedItem.self, from: Data(monogramFallbackBundleJSON().utf8)).bundle)

        let resolvedPatriots = DiscoverBundleVisual12840.resolve(
            title: patriots.title,
            sharedQuestion: patriots.sharedQuestion,
            category: "football",
            bundleImageUrl: patriots.imageUrl,
            bundlePresentation: patriots.imagePresentation,
            bundleMonogram: patriots.imageMonogram,
            items: patriots.items
        )
        let patriotsCrestURL = try XCTUnwrap(resolvedPatriots.fallbackCrestURL)

        var preloaded: [URL: Image] = [:]
        let urls: [URL] = [
            URL(string: grammys.imageUrl!)!,
            URL(string: ipos.imageUrl!)!,
            patriotsCrestURL,
        ]
        for u in urls {
            var req = URLRequest(url: u, timeoutInterval: 8)
            req.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
            if let (data, resp) = try? await URLSession.shared.data(for: req),
               (resp as? HTTPURLResponse)?.statusCode == 200,
               let uiImg = UIImage(data: data) {
                preloaded[u] = Image(uiImage: uiImg)
            }
        }

        func renderSlice<V: View>(_ content: V, style: UIUserInterfaceStyle) -> UIImage {
            let wrapped = content.frame(width: 390)
            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = style
            let measured = host.sizeThatFits(in: CGSize(width: 390, height: 2400))
            let targetFrame = CGRect(x: 0, y: 0, width: 390, height: ceil(max(measured.height + 28, 420)))
            let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
            let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: targetFrame)
            window.frame = targetFrame
            host.view.frame = targetFrame
            window.overrideUserInterfaceStyle = style
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
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            return UIGraphicsImageRenderer(size: targetFrame.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: targetFrame, afterScreenUpdates: true)
            }
        }

        @ViewBuilder
        func pairSection(scheme: ColorScheme, label: String?, pair: [FeedBundle]) -> some View {
            VStack(alignment: .leading, spacing: 14) {
                if let label {
                    Text(label)
                        .font(.caption.weight(.heavy))
                        .tracking(0.8)
                        .foregroundStyle(scheme == .dark ? Color.white.opacity(0.82) : Color.secondary)
                        .padding(.horizontal, 4)
                }
                ForEach(Array(pair.enumerated()), id: \.offset) { _, bundle in
                    NativeGroupCard(
                        title: bundle.title,
                        items: bundle.items,
                        kind: bundle.kind,
                        theme: bundle.comparisonTheme,
                        sharedQuestion: bundle.sharedQuestion,
                        collectionRef: bundle.themeCollectionRef,
                        imageUrl: bundle.imageUrl,
                        imagePresentation: bundle.imagePresentation,
                        imageMonogram: bundle.imageMonogram,
                        preloadedBannerImages: preloaded,
                        navigationPath: .constant(NavigationPath())
                    )
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(width: 390)
            .background(scheme == .dark ? Color(red: 0.05, green: 0.06, blue: 0.09) : Color(red: 0.96, green: 0.96, blue: 0.97))
            .environment(\.colorScheme, scheme)
        }

        let slices: [UIImage] = [
            renderSlice(pairSection(scheme: .light, label: "390 PX · LIGHT", pair: [grammys, ipos]), style: .light),
            renderSlice(pairSection(scheme: .light, label: nil, pair: [patriots, kimi]), style: .light),
            renderSlice(pairSection(scheme: .dark, label: "390 PX · DARK", pair: [grammys, ipos]), style: .dark),
            renderSlice(pairSection(scheme: .dark, label: nil, pair: [patriots, kimi]), style: .dark),
        ]

        let totalHeight = slices.reduce(CGFloat(0)) { $0 + $1.size.height }
        let outFmt = UIGraphicsImageRendererFormat()
        outFmt.scale = 2.0
        outFmt.opaque = true
        let image = UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalHeight), format: outFmt).image { _ in
            var y: CGFloat = 0
            for slice in slices {
                slice.draw(in: CGRect(x: 0, y: y, width: 390, height: slice.size.height))
                y += slice.size.height
            }
        }

        var allLines: [String] = []
        for slice in slices {
            let ocr = VNRecognizeTextRequest()
            ocr.recognitionLevel = .accurate
            ocr.usesLanguageCorrection = false
            ocr.minimumTextHeight = 0.0
            try VNImageRequestHandler(cgImage: XCTUnwrap(slice.cgImage)).perform([ocr])
            allLines.append(contentsOf: (ocr.results ?? []).compactMap { $0.topCandidates(1).first?.string })
        }
        let joined = allLines.joined(separator: " ")

        for required in [
            "GRAMMYS",
            "Where do the Grammys races stand?",
            "Who goes public, and at what price?",
            "Where does New England's season stand?",
            "KM"
        ] {
            XCTAssertTrue(joined.contains(required), "Expected '\(required)' in 390px light+dark sheet OCR, got: \(joined)")
        }
        XCTAssertFalse(joined.contains("…"), "Expected zero truncation in 390px light+dark grouped cards sheet")

        if let dir = ProcessInfo.processInfo.environment["EXPORT_GROUP_12840_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(image.pngData()).write(to: outURL.appendingPathComponent("12840-discover-grouped-cards-light-dark-390.png"))
        }
    }
}
