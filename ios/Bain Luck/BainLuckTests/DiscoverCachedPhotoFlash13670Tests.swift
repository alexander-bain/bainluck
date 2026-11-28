import Combine
import Darwin
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13670 — Discover cached first page must never paint a previously cached
/// remote photo before live `/api/feed` confirms `image_url` (`387: A`).
@MainActor
final class DiscoverCachedPhotoFlash13670Tests: XCTestCase {

    private func makeKanyeMarket(imageUrl: String?) throws -> FeedFuturesData {
        let imgField = imageUrl.map { "\"\($0)\"" } ?? "null"
        let json = """
        {
          "id": 69907692,
          "name": "Will Kanye West attend Super Bowl LXI?",
          "llm_sport_category": "entertainment",
          "source": "polymarket",
          "status": "open",
          "image_url": \(imgField),
          "top_outcomes": [
            {"id": 699076921, "name": "Yes", "probability": 0.14, "rank": 1, "movement": -0.01}
          ],
          "outcome_count": 2
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedFuturesData.self, from: Data(json.utf8))
    }

    func testResolvedBackgroundPolicyWithholdsUnconfirmedCachedPhotos() {
        let url = "https://images.pexels.com/photos/123456/example.jpeg"
        XCTAssertEqual(
            FuturesHeroBackground.resolvedBackground(imageURL: url, withholdUnconfirmedPhotos: true),
            .category,
            "Cached seed must fall back to category gradient until live feed confirms image_url"
        )
        XCTAssertEqual(
            FuturesHeroBackground.resolvedBackground(imageURL: url, withholdUnconfirmedPhotos: false),
            .photo(URL(string: url)!)
        )
        XCTAssertEqual(
            FuturesHeroBackground.resolvedBackground(imageURL: nil, withholdUnconfirmedPhotos: false),
            .category
        )
    }

    func testDiscoverViewWiresWithholdUnconfirmedPhotosToIsShowingCachedContent() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(
            source.contains(".environment(\\.discoverWithholdUnconfirmedPhotos13670, vm.isShowingCachedContent)"),
            "DiscoverView must suppress unconfirmed photos while vm.isShowingCachedContent is true"
        )
    }

    func testCachedHeroWithholdsStalePhotoAndMatchesServerWithheldLiveCard() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13670_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let pngData = try makeSamplePNGData()
        let server = try LoopbackPNGServer13670(pngData: pngData)
        defer { server.stop() }

        let staleURL = "http://127.0.0.1:\(server.port)/kanye-stale.png"
        let cachedWithStalePhoto = try makeKanyeMarket(imageUrl: staleURL)
        let liveWithheld = try makeKanyeMarket(imageUrl: nil)

        // 1. AFTER (cached seed with stale URL + withhold flag ON): must make 0 image requests
        //    and match the live server-withheld card pixel-for-pixel.
        let afterCached = cardHostView(data: cachedWithStalePhoto, withholdPhotos: true, label: "AFTER · Cached seed (photo withheld)")
        let afterCachedImg = snapshot(afterCached, settleLoops: 12)
        XCTAssertEqual(server.hitCount, 0, "Withheld cached card must not even request stale image URL")

        let afterLive = cardHostView(data: liveWithheld, withholdPhotos: false, label: "AFTER · Live refresh (image_url: null)")
        let afterLiveImg = snapshot(afterLive, settleLoops: 10)

        let cachedText = try ocrText(afterCachedImg)
        let liveText = try ocrText(afterLiveImg)
        XCTAssertTrue(cachedText.contains("Kanye West") && cachedText.contains("14%"), "saw: \(cachedText)")
        XCTAssertTrue(liveText.contains("Kanye West") && liveText.contains("14%"), "saw: \(liveText)")

        let afterCachedHeroLuma = averageTopHeroBrightness(afterCachedImg)
        let afterLiveHeroLuma = averageTopHeroBrightness(afterLiveImg)
        XCTAssertLessThan(
            abs(afterCachedHeroLuma - afterLiveHeroLuma),
            0.02,
            "Fixed cached card hero must match live image_url:nil gradient with zero photo flash"
        )

        // 2. BEFORE (unguarded cached seed paints the stale photo over the hero gradient before
        //    live `image_url: null` replaces it).
        let beforeCached = cardHostView(data: cachedWithStalePhoto, withholdPhotos: false, label: "BEFORE · Cached seed flashed photo")
        let beforeCachedImg = snapshot(beforeCached, settleLoops: 25)
        let beforeHeroLuma = averageTopHeroBrightness(beforeCachedImg)
        XCTAssertGreaterThan(server.hitCount, 0, "Unguarded BEFORE must have loaded the stale photo URL")
        XCTAssertGreaterThan(
            abs(beforeHeroLuma - afterLiveHeroLuma),
            0.08,
            "Precondition: unguarded cached photo measurably altered hero appearance"
        )

        if let outDir, !outDir.isEmpty {
            if let d = beforeCachedImg.pngData() {
                try d.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-13670-cached-flash-390.png"))
            }
            if let d = afterCachedImg.pngData() {
                try d.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13670-cached-withheld-390.png"))
            }
            if let d = afterLiveImg.pngData() {
                try d.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13670-live-withheld-390.png"))
            }
        }
    }

    func testGroupBannerSuppressesPrimaryPhotoWhileCached() throws {
        let monogram = DiscoverImageMonogram(
            initials: "KW",
            label: "Kanye West",
            kind: "person",
            bgHex: "#1E293B",
            accentHex: "#7C3AED"
        )
        let resolved = DiscoverBundleVisual12840.ResolvedBanner(
            primaryURL: URL(string: "https://example.com/withheld-photo.jpg"),
            presentation: "photo",
            fallbackCrestURL: nil,
            monogram: monogram
        )
        let cachedBanner = DiscoverGroupBannerView12840(resolved: resolved, category: "entertainment")
            .environment(\.discoverWithholdUnconfirmedPhotos13670, true)
            .frame(width: 358, height: 144)
        let img = snapshot(cachedBanner, height: 144, settleLoops: 8)
        let ocr = try ocrText(img)
        XCTAssertTrue(ocr.contains("KW"), "Expected monogram fallback while cached photo withheld, saw: \(ocr)")
    }

    private func makeSamplePNGData() throws -> Data {
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        let img = UIGraphicsImageRenderer(size: CGSize(width: 400, height: 220), format: fmt).image { ctx in
            UIColor(red: 0.98, green: 0.90, blue: 0.28, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 400, height: 220))
        }
        return try XCTUnwrap(img.pngData())
    }

    private func cardHostView(data: FeedFuturesData, withholdPhotos: Bool, label: String) -> some View {
        let suite = "test-13670-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        return HarnessCard13670(data: data, label: label)
            .environment(\.discoverWithholdUnconfirmedPhotos13670, withholdPhotos)
            .environment(\.colorScheme, .light)
            .environmentObject(pinManager)
            .environmentObject(NavigationCoordinator())
            .environmentObject(AuthManager(restoreOnInit: false))
    }

    private func averageTopHeroBrightness(_ image: UIImage) -> Double {
        guard let cg = image.cgImage else { return 0 }
        let width = cg.width
        let height = cg.height
        let yStart = Int(Double(height) * 0.16)
        let yEnd = Int(Double(height) * 0.34)
        let xStart = Int(Double(width) * 0.15)
        let xEnd = Int(Double(width) * 0.85)
        var data = [UInt8](repeating: 0, count: width * height * 4)
        let cs = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(
            data: &data,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: cs,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return 0 }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
        var total = 0.0
        var count = 0
        for y in stride(from: yStart, to: yEnd, by: 4) {
            for x in stride(from: xStart, to: xEnd, by: 4) {
                let idx = (y * width + x) * 4
                let r = Double(data[idx]) / 255.0
                let g = Double(data[idx + 1]) / 255.0
                let b = Double(data[idx + 2]) / 255.0
                total += 0.299 * r + 0.587 * g + 0.114 * b
                count += 1
            }
        }
        return count > 0 ? total / Double(count) : 0
    }

    private func snapshot<V: View>(_ view: V, height: CGFloat = 460, settleLoops: Int = 10) -> UIImage {
        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: height)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.frame = bounds
        for _ in 0..<settleLoops {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrText(_ image: UIImage) throws -> String {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }
}

private final class LoopbackPNGServer13670: @unchecked Sendable {
    private let listenFD: Int32
    let port: UInt16
    private let lock = NSLock()
    private var _hitCount = 0
    private var stopped = false
    private let pngData: Data

    var hitCount: Int {
        lock.lock()
        defer { lock.unlock() }
        return _hitCount
    }

    init(pngData: Data) throws {
        self.pngData = pngData
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else {
            throw NSError(domain: "LoopbackPNGServer13670", code: Int(errno))
        }
        var yes: Int32 = 1
        Darwin.setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let bindRes = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindRes == 0, Darwin.listen(fd, 8) == 0 else {
            Darwin.close(fd)
            throw NSError(domain: "LoopbackPNGServer13670", code: Int(errno))
        }
        var boundAddr = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &boundAddr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(fd, $0, &len)
            }
        }
        self.listenFD = fd
        self.port = UInt16(bigEndian: boundAddr.sin_port)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.acceptLoop()
        }
    }

    private func acceptLoop() {
        while true {
            lock.lock()
            let done = stopped
            lock.unlock()
            if done { break }
            let clientFD = Darwin.accept(listenFD, nil, nil)
            if clientFD < 0 { break }
            var buf = [UInt8](repeating: 0, count: 2048)
            _ = Darwin.recv(clientFD, &buf, buf.count, 0)
            lock.lock()
            _hitCount += 1
            lock.unlock()
            let header = "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: \(pngData.count)\r\nConnection: close\r\n\r\n"
            var payload = Data(header.utf8)
            payload.append(pngData)
            payload.withUnsafeBytes { raw in
                guard let base = raw.baseAddress else { return }
                var sent = 0
                while sent < payload.count {
                    let n = Darwin.send(clientFD, base.advanced(by: sent), payload.count - sent, 0)
                    if n <= 0 { break }
                    sent += n
                }
            }
            Darwin.close(clientFD)
        }
    }

    func stop() {
        lock.lock()
        let wasStopped = stopped
        stopped = true
        lock.unlock()
        if !wasStopped {
            Darwin.close(listenFD)
        }
    }
}

private struct HarnessCard13670: View {
    let data: FeedFuturesData
    let label: String
    @State private var path = NavigationPath()

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            NativeFuturesDiscoverCard(
                data: data,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: $path
            )
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(DS.surface)
    }
}
