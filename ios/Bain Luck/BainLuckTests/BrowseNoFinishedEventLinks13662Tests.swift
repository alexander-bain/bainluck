import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class BrowseNoFinishedEventLinks13662Tests: XCTestCase {

    private func decodeDiscovery(_ collections: [[String: Any]]) throws -> ContainerDiscoveryResponse {
        let data = try JSONSerialization.data(withJSONObject: ["collections": collections])
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(ContainerDiscoveryResponse.self, from: data)
    }

    private func nflCard(week: Int, status: String, name: String) -> [String: Any] {
        [
            "type": "collection",
            "id": 100 + week,
            "slug": "nfl-2026-week-\(week)",
            "name": name,
            "text": name,
            "state": "published",
            "revision": 10,
            "edition": [
                "kind": "nfl_week",
                "league": "nfl",
                "season": 2026,
                "stage": "Regular Season",
                "week": week,
            ],
            "status": status,
            "game_count": 13,
            "question_count": 2100,
            "matched_event_ids": [],
            "destination": [
                "kind": "container",
                "slug": "nfl-2026-week-\(week)",
                "api": "/api/containers/nfl-2026-week-\(week)",
            ],
        ]
    }

    private func captureWindow<V: View>(
        _ view: V,
        width: CGFloat = 390,
        height: CGFloat = 760,
        scheme: ColorScheme = .light
    ) -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let root = view
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
            .environmentObject(NavigationCoordinator())
            .environmentObject(AuthManager(restoreOnInit: false))
            .environmentObject(PinManager(defaults: UserDefaults(suiteName: "Browse13671.\(UUID().uuidString)")!, allowLegacyGuestPins: true))

        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = style
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: rect)
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: rect.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        if cg.height <= 1800 {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: cg).perform([req])
            return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        }
        var lines: [String] = []
        var yStart = 0
        while yStart < cg.height {
            let h = min(1400, cg.height - yStart)
            guard let slice = cg.cropping(to: CGRect(x: 0, y: yStart, width: cg.width, height: h)) else { break }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: slice).perform([req])
            lines.append(contentsOf: (req.results ?? []).compactMap { $0.topCandidates(1).first?.string })
            if yStart + h >= cg.height { break }
            yStart += 1000
        }
        return lines
    }

    func testContainerDiscoveryDropsFinishedNFLWeeksAndKeepsActiveWeeks() throws {
        let response = try decodeDiscovery([
            nflCard(week: 12, status: "scheduled", name: "NFL 2026 · Week 12 · Nov 25–30"),
            nflCard(week: 11, status: "final", name: "NFL 2026 · Week 11 · Nov 19–23"),
            nflCard(week: 10, status: "completed", name: "NFL 2026 · Week 10 · Nov 12–16"),
            nflCard(week: 9, status: "closed", name: "NFL 2026 · Week 9 · Nov 5–9"),
        ])
        let request = ContainerDiscoveryRequest(league: .nfl, season: 2026)
        let entries = request.entries(in: response)
        XCTAssertEqual(entries.map(\.id), ["nfl-2026-week-12"])
    }

    func testBrowseTabOmitsUSOpenAndFinishedCollectionsAt390pt() throws {
        let sampleCollections = try decodeDiscovery([
            nflCard(week: 12, status: "scheduled", name: "NFL 2026 · Week 12 · Nov 25–30"),
            nflCard(week: 11, status: "final", name: "NFL 2026 · Week 11 · Nov 19–23"),
            nflCard(week: 10, status: "final", name: "NFL 2026 · Week 10 · Nov 12–16"),
        ])

        struct StaticDiscoveryService: ContainerDiscoveryLoading {
            let nflResponse: ContainerDiscoveryResponse
            func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse {
                if request.league == .nfl { return nflResponse }
                let data = try JSONSerialization.data(withJSONObject: ["collections": []])
                let d = JSONDecoder()
                d.keyDecodingStrategy = .convertFromSnakeCase
                return try d.decode(ContainerDiscoveryResponse.self, from: data)
            }
        }

        // Also test actual LeaguesView directly (verifying US Open is absent and Explore reaches bottom)
        let pureBrowseLight = captureWindow(LeaguesView(), height: 1750, scheme: .light)
        let pureBrowseDark = captureWindow(LeaguesView(), height: 1750, scheme: .dark)
        let collectionsOnly = captureWindow(
            NavigationStack {
                BrowseCollectionsView(service: StaticDiscoveryService(nflResponse: sampleCollections))
                    .padding(22)
                    .background(Color.groupedBackground.opacity(0.35))
            },
            height: 220,
            scheme: .light
        )

        let browseLines = try ocrLines(pureBrowseLight)
        XCTAssertFalse(browseLines.joined(separator: " ").contains("US Open"), "Browse must omit finished US Open card: \(browseLines)")
        XCTAssertTrue(browseLines.joined(separator: " ").contains("Futures Markets"))
        XCTAssertTrue(browseLines.joined(separator: " ").contains("About Bain Luck"))

        let colLines = try ocrLines(collectionsOnly).joined(separator: " ")
        XCTAssertTrue(colLines.contains("Week 12"), "Scheduled NFL Week 12 must stay on Browse: \(colLines)")
        XCTAssertFalse(colLines.contains("Week 11"), "Finished NFL Week 11 must be filtered off Browse: \(colLines)")
        XCTAssertFalse(colLines.contains("Week 10"), "Finished NFL Week 10 must be filtered off Browse: \(colLines)")

        // Check SearchView empty-state omits finished US Open pill
        let searchEmpty = captureWindow(SearchView(), height: 640, scheme: .light)
        let searchLines = try ocrLines(searchEmpty).joined(separator: " ")
        XCTAssertFalse(searchLines.contains("US Open"), "Empty Search must omit finished US Open tournament pill: \(searchLines)")

        if let outDir = ProcessInfo.processInfo.environment["SHEET_13662_ITEM8_DIR"], !outDir.isEmpty {
            let dir = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

            // Composite after view (LeaguesView top + filtered Collections strip)
            let combinedAfterLight = VStack(alignment: .leading, spacing: 12) {
                Image(uiImage: pureBrowseLight).resizable().aspectRatio(contentMode: .fit)
                Text("Filtered Collections (after #13671)").font(.caption.bold()).padding(.horizontal, 16)
                Image(uiImage: collectionsOnly).resizable().aspectRatio(contentMode: .fit)
            }
            .frame(width: 390)
            let afterLightSheet = captureWindow(combinedAfterLight, height: 1040, scheme: .light)

            let panels: [(String, UIImage)] = [
                ("After Light (390pt · no US Open / only scheduled Week 12) · simulator results, not phone results", afterLightSheet),
                ("After Dark (390pt · Browse featuredGrid) · simulator results, not phone results", pureBrowseDark),
            ]
            let padding: CGFloat = 16
            let gap: CGFloat = 16
            let headerH: CGFloat = 28
            let totalW = panels.map { $0.1.size.width }.reduce(0, +) + gap * CGFloat(panels.count - 1) + padding * 2
            let totalH = (panels.map { $0.1.size.height }.max() ?? 820) + headerH + padding * 2
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let sheet = UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
                UIColor.systemGray6.setFill()
                ctx.fill(CGRect(origin: .zero, size: CGSize(width: totalW, height: totalH)))
                var x = padding
                for (title, img) in panels {
                    let para = NSMutableParagraphStyle()
                    para.lineBreakMode = .byTruncatingTail
                    NSString(string: title).draw(
                        in: CGRect(x: x, y: padding, width: img.size.width, height: 22),
                        withAttributes: [.font: UIFont.systemFont(ofSize: 11, weight: .bold), .foregroundColor: UIColor.label, .paragraphStyle: para]
                    )
                    img.draw(at: CGPoint(x: x, y: padding + headerH))
                    x += img.size.width + gap
                }
            }
            let data = try XCTUnwrap(sheet.pngData())
            try data.write(to: dir.appendingPathComponent("sheet-13662-item8-browse-finished-390.png"))
        }
    }
}
