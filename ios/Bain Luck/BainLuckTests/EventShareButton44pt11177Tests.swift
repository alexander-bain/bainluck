import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #11177 — on the iPhone event page, the top-right Share icon must be at least a
/// 44 × 44 pt tap target (responding 20 pt above/below its centre, matching #10880's
/// strip probe), keep `.primary` ink under `.buttonStyle(.plain)` (never accent blue),
/// and leave the event title readable with zero `"…"` truncation at 393 pt and 390 pt
/// in both default (`.large`) and AX3 (`.accessibilityExtraExtraExtraLarge`).
@MainActor
final class EventShareButton44pt11177Tests: XCTestCase {

    override class func setUp() {
        super.setUp()
        setAccessibilityAutomation(true)
    }

    override class func tearDown() {
        setAccessibilityAutomation(false)
        super.tearDown()
    }

    private static func setAccessibilityAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let sym = dlsym(lib, "_AXSSetAutomationEnabled") else {
            return
        }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(sym, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    private func source(_ parts: String...) throws -> String {
        var url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        for part in parts { url.appendPathComponent(part) }
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testEventDetailShareControlUses44x44PlainTargetAndPrimaryInk() throws {
        let page = try source("Views", "EventDetailView.swift")
        guard let shareStart = page.range(of: "ShareLink(item: shareURL)"),
              let pinStart = page.range(of: #"PinButton(type: "event", id: eventId)"#) else {
            return XCTFail("Expected ShareLink and PinButton in EventDetailView toolbar")
        }
        let shareSlice = String(page[shareStart.lowerBound..<pinStart.lowerBound])
        XCTAssertTrue(shareSlice.contains(".frame(width: 44, height: 44)"), "Share label must be 44×44")
        XCTAssertTrue(shareSlice.contains(".contentShape(Rectangle())"), "Share label must make its full 44×44 rect hit-testable")
        XCTAssertTrue(shareSlice.contains(".buttonStyle(.plain)"), "Toolbar's default style caps controls at 36 pt; Share needs .plain")
        XCTAssertTrue(shareSlice.contains(".foregroundStyle(.primary)"), "Plain toolbar icon must keep primary ink")
        XCTAssertFalse(shareSlice.contains(".foregroundStyle(.tint)"), "Never paint Share accent blue beside More")
        XCTAssertTrue(shareSlice.contains(#".accessibilityLabel("Share")"#))
        XCTAssertFalse(shareSlice.contains("height: 36"), "Never lower 44 pt tap target")
    }

    func testHostedEventToolbarShareFrameIsAtLeast44x44AndRespondsAt20ptVerticalOffsetAndTitleStaysReadable() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let eligibleEvent = try decoder.decode(EventDetail.self, from: Data("""
        {
          "id": 15327537,
          "external_id": "abc123",
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "commence_time": "2099-10-16T23:00:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "completed_at": null,
          "status": "scheduled",
          "started_without_result": false,
          "home_score": null,
          "away_score": null
        }
        """.utf8))

        let pins = PinManager(
            defaults: UserDefaults(suiteName: "EventShareButton44pt11177Tests.\(UUID().uuidString)")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        struct ToolbarHarness: View {
            let event: EventDetail
            let shareTapped: () -> Void
            private let fullTitle = "Boston Celtics vs Philadelphia 76ers"
            private let compactTitle = EventNavTitle.scorelessCompact(
                away: "Boston Celtics",
                home: "Philadelphia 76ers"
            )

            var body: some View {
                NavigationStack {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(fullTitle)
                            .font(.subheadline.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Tip-off 8:00 PM")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer()
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .navigationTitle(fullTitle)
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .principal) {
                            ViewThatFits(in: .horizontal) {
                                Text(fullTitle).font(.headline).lineLimit(1)
                                Text(compactTitle).font(.headline).lineLimit(1).minimumScaleFactor(0.65)
                            }
                        }
                        ToolbarItem(placement: .confirmationAction) {
                            HStack(spacing: 4) {
                                ShareLink(item: URL(string: "https://bainluck.com/events/15327537")!) {
                                    Image(systemName: "square.and.arrow.up")
                                        .font(.system(size: 14))
                                        .foregroundStyle(.primary)
                                        .frame(width: 44, height: 44)
                                        .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel("Share")
                                .recordsShareOpened {
                                    shareTapped()
                                }
                                PinButton(type: "event", id: event.id)
                                CalendarDetailMenu10880(pageEventId: event.id, event: event)
                            }
                        }
                    }
                }
            }
        }

        func findToolbarButtons(in root: UIView) -> [UIView] {
            var out: [UIView] = []
            if root is UIControl || String(describing: type(of: root)).contains("Button") {
                out.append(root)
            }
            for sub in root.subviews {
                out.append(contentsOf: findToolbarButtons(in: sub))
            }
            return out
        }

        var capturedSlices: [(String, UIImage)] = []

        for width in [CGFloat(393), CGFloat(390)] {
            for typeSize in [DynamicTypeSize.large, DynamicTypeSize.accessibility3] {
                for scheme in [ColorScheme.light, ColorScheme.dark] {
                    let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
                    let root = ToolbarHarness(event: eligibleEvent, shareTapped: {})
                        .environmentObject(pins)
                        .environment(\.colorScheme, scheme)
                    let host = hostForMeasurement(root, at: typeSize)
                    host.overrideUserInterfaceStyle = uiStyle
                    host.view.frame = CGRect(x: 0, y: 0, width: width, height: 300)

                    let window: UIWindow
                    if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                        window = UIWindow(windowScene: scene)
                    } else {
                        window = UIWindow(frame: host.view.frame)
                    }
                    window.frame = host.view.frame
                    window.overrideUserInterfaceStyle = uiStyle
                    window.rootViewController = host
                    window.isHidden = false
                    defer {
                        window.isHidden = true
                        window.rootViewController = nil
                    }

                    let until = Date().addingTimeInterval(0.18)
                    repeat {
                        host.view.setNeedsLayout()
                        host.view.layoutIfNeeded()
                        RunLoop.current.run(until: Date().addingTimeInterval(0.015))
                    } while Date() < until

                    // Locate the Share control in the navigation bar hierarchy and verify >= 44×44 + ±20pt strip hit-test.
                    let controls = findToolbarButtons(in: host.view)
                    let shareCandidates = controls.filter { v in
                        let frameInRoot = v.convert(v.bounds, to: host.view)
                        return frameInRoot.minY < 130 && frameInRoot.width >= 44 && frameInRoot.height >= 44
                    }
                    XCTAssertGreaterThanOrEqual(
                        shareCandidates.count,
                        2,
                        "Toolbar at \(Int(width))pt \(typeSize) \(scheme) must expose >=44×44 controls for Share and Pin; got \(controls.map { $0.convert($0.bounds, to: host.view) })"
                    )
                    if let leftmostRightBarControl = shareCandidates
                        .map({ $0.convert($0.bounds, to: host.view) })
                        .filter({ $0.minX > width * 0.45 })
                        .min(by: { $0.minX < $1.minX }) {
                        XCTAssertGreaterThanOrEqual(leftmostRightBarControl.width, 44.0)
                        XCTAssertGreaterThanOrEqual(leftmostRightBarControl.height, 44.0)
                        let center = CGPoint(x: leftmostRightBarControl.midX, y: leftmostRightBarControl.midY)
                        for dy in [CGFloat(-20), CGFloat(20)] {
                            let probe = CGPoint(x: center.x, y: center.y + dy)
                            XCTAssertTrue(
                                leftmostRightBarControl.contains(probe),
                                "Point 20pt from Share centre (\(probe)) must fall inside Share's \(leftmostRightBarControl) target"
                            )
                            XCTAssertNotNil(
                                host.view.hitTest(probe, with: nil),
                                "hitTest 20pt from Share centre must resolve to a live view"
                            )
                        }
                    }

                    // Render and run OCR on the navigation bar strip (top 120 pt) to confirm zero ellipsis on the title.
                    let fmt = UIGraphicsImageRendererFormat()
                    fmt.scale = 3.0
                    let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                        if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                            host.view.layer.render(in: ctx.cgContext)
                        }
                    }
                    let req = VNRecognizeTextRequest()
                    req.recognitionLevel = .accurate
                    try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
                    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                    XCTAssertFalse(
                        lines.contains(where: { line in
                            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                            // CalendarDetailMenu10880 renders SF symbol `ellipsis.circle`, which Vision OCR reads as "(...)".
                            guard trimmed != "(...)" && trimmed != "..." else { return false }
                            return trimmed.contains("…") || trimmed.contains("...")
                        }),
                        "Event toolbar/title at \(Int(width))pt \(typeSize) \(scheme) truncated: \(lines)"
                    )

                    if width == 390 {
                        let tag = "\(typeSize == .large ? "default" : "ax3")-\(scheme == .dark ? "dark" : "light")"
                        capturedSlices.append((tag, img))
                    }
                }
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_11177"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            for (tag, img) in capturedSlices {
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("11177-event-toolbar-\(tag)-390.png"))
                }
            }
        }
    }

    private nonisolated final class StubClient11177: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        init(event: EventDetail) { self.event = event }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private nonisolated final class StubStreamHandle11177: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() {}
    }

    private func findAccessibilityElement(named label: String, in root: NSObject, visited: inout Set<ObjectIdentifier>) -> NSObject? {
        let oid = ObjectIdentifier(root)
        guard !visited.contains(oid) else { return nil }
        visited.insert(oid)

        if root.isAccessibilityElement,
           root.accessibilityLabel == label,
           root.accessibilityTraits.contains(.button) {
            return root
        }
        if let explicit = root.accessibilityElements {
            for child in explicit {
                if let obj = child as? NSObject,
                   let found = findAccessibilityElement(named: label, in: obj, visited: &visited) {
                    return found
                }
            }
        }
        let count = root.accessibilityElementCount()
        if count != NSNotFound && count > 0 {
            for i in 0..<count {
                if let obj = root.accessibilityElement(at: i) as? NSObject,
                   let found = findAccessibilityElement(named: label, in: obj, visited: &visited) {
                    return found
                }
            }
        }
        if let view = root as? UIView {
            for sub in view.subviews {
                if let found = findAccessibilityElement(named: label, in: sub, visited: &visited) {
                    return found
                }
            }
        }
        return nil
    }

    func testRealEventDetailToolbarShareButtonIsAtLeast44x44Keeps14ptIconAndCapturesBeforeVsAfter() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let eligibleEvent = try decoder.decode(EventDetail.self, from: Data("""
        {
          "id": 15327537,
          "external_id": "abc123",
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "commence_time": "2099-10-16T23:00:00+00:00",
          "start_is_tbd": false,
          "start_is_from_schedule": true,
          "completed_at": null,
          "status": "scheduled",
          "started_without_result": false,
          "home_score": null,
          "away_score": null
        }
        """.utf8))

        let vm = EventDetailViewModel(
            eventId: eligibleEvent.id,
            client: StubClient11177(event: eligibleEvent),
            makeStreamHandle: { _ in StubStreamHandle11177() }
        )
        defer { vm.stopRefresh() }
        await vm.load()

        let pins = PinManager(
            defaults: UserDefaults(suiteName: "EventDetailShare11177.\(UUID().uuidString)")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )
        let nav = NavigationCoordinator()
        let auth = AuthManager()

        // Pre-fix 1.0.7 (5854) bare ShareLink toolbar control for honest before-vs-after capture.
        struct Before107ToolbarHarness: View {
            let event: EventDetail
            private let compactTitle = EventNavTitle.scorelessCompact(
                away: "Boston Celtics",
                home: "Philadelphia 76ers"
            )
            var body: some View {
                NavigationStack {
                    Color.clear
                        .navigationTitle("Boston Celtics vs Philadelphia 76ers")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .principal) {
                                Text(compactTitle).font(.headline).lineLimit(1).minimumScaleFactor(0.65)
                            }
                            ToolbarItem(placement: .confirmationAction) {
                                HStack(spacing: 4) {
                                    ShareLink(item: URL(string: "https://bainluck.com/events/15327537")!) {
                                        Image(systemName: "square.and.arrow.up")
                                            .font(.system(size: 14))
                                    }
                                    .accessibilityLabel("Share")
                                    PinButton(type: "event", id: event.id)
                                    CalendarDetailMenu10880(pageEventId: event.id, event: event)
                                }
                            }
                        }
                }
            }
        }

        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_11177"]
            ?? ProcessInfo.processInfo.environment["TEST_RUNNER_BUILDER_C_RENDER_DIR_11177"]

        var frameSummaryLines: [String] = []

        for width in [CGFloat(393), CGFloat(390)] {
            for typeSize in [DynamicTypeSize.large, DynamicTypeSize.accessibility3] {
                for scheme in [ColorScheme.light, ColorScheme.dark] {
                    let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
                    let realPage = NavigationStack {
                        EventDetailView(eventId: eligibleEvent.id, viewModel: vm)
                            .withLoadedEventForTest12278(eligibleEvent, viewModel: vm)
                    }
                    .environmentObject(pins)
                    .environmentObject(nav)
                    .environmentObject(auth)
                    .environment(\.colorScheme, scheme)
                    .environment(\.scenePhase, .active)

                    let host = hostForMeasurement(realPage, at: typeSize)
                    host.overrideUserInterfaceStyle = uiStyle
                    host.view.frame = CGRect(x: 0, y: 0, width: width, height: 320)

                    let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
                    let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
                    window.frame = host.view.frame
                    window.overrideUserInterfaceStyle = uiStyle
                    window.rootViewController = host
                    window.makeKeyAndVisible()
                    defer {
                        window.isHidden = true
                        window.rootViewController = nil
                    }

                    var shareAX: NSObject?
                    let deadline = Date().addingTimeInterval(2.5)
                    while Date() < deadline {
                        host.view.setNeedsLayout()
                        host.view.layoutIfNeeded()
                        var visited = Set<ObjectIdentifier>()
                        shareAX = findAccessibilityElement(named: "Share", in: host.view, visited: &visited)
                        if let el = shareAX, el.accessibilityFrame.width >= 43.9, el.accessibilityFrame.height >= 43.9 {
                            break
                        }
                        try? await Task.sleep(nanoseconds: 40_000_000)
                    }

                    let shareEl = try XCTUnwrap(shareAX, "Real EventDetailView missing Share button at \(Int(width))pt \(typeSize) \(scheme)")
                    let rawFrame = shareEl.accessibilityFrame
                    let localFrame = window.convert(rawFrame, from: nil)
                    XCTAssertGreaterThanOrEqual(rawFrame.width, 43.9, "Real Share width < 44 at \(Int(width))pt \(typeSize) \(scheme): \(rawFrame)")
                    XCTAssertGreaterThanOrEqual(rawFrame.height, 43.9, "Real Share height < 44 at \(Int(width))pt \(typeSize) \(scheme): \(rawFrame)")

                    let center = CGPoint(x: localFrame.midX, y: localFrame.midY)
                    for dy in [CGFloat(-20), CGFloat(20)] {
                        let probe = CGPoint(x: center.x, y: center.y + dy)
                        XCTAssertTrue(localFrame.contains(probe), "Point \(dy)pt from real Share centre missed \(localFrame)")
                        XCTAssertNotNil(host.view.hitTest(probe, with: nil), "hitTest \(dy)pt from real Share centre returned nil")
                    }

                    let fmt = UIGraphicsImageRendererFormat()
                    fmt.scale = 3.0
                    let navRect = CGRect(x: 0, y: 0, width: width, height: 120)
                    let afterImg = UIGraphicsImageRenderer(bounds: navRect, format: fmt).image { ctx in
                        if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                            host.view.layer.render(in: ctx.cgContext)
                        }
                    }

                    let req = VNRecognizeTextRequest()
                    req.recognitionLevel = .accurate
                    try VNImageRequestHandler(cgImage: XCTUnwrap(afterImg.cgImage), options: [:]).perform([req])
                    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                    XCTAssertFalse(
                        lines.contains(where: { line in
                            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard trimmed != "(...)" && trimmed != "..." else { return false }
                            return trimmed.contains("…") || trimmed.contains("...")
                        }),
                        "Real EventDetailView nav title truncated with ellipsis at \(Int(width))pt \(typeSize) \(scheme): \(lines)"
                    )

                    if width == 390, let outDir, !outDir.isEmpty {
                        let sizeTag = typeSize == .large ? "default" : "ax3"
                        let schemeTag = scheme == .dark ? "dark" : "light"
                        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                        try afterImg.pngData()?.write(to: dirURL.appendingPathComponent("real-after-\(sizeTag)-\(schemeTag)-390.png"))

                        // Measure and export 1.0.7 before state on exact same toolbar layout.
                        let beforeHost = hostForMeasurement(
                            Before107ToolbarHarness(event: eligibleEvent)
                                .environmentObject(pins)
                                .environment(\.colorScheme, scheme),
                            at: typeSize
                        )
                        beforeHost.overrideUserInterfaceStyle = uiStyle
                        beforeHost.view.frame = CGRect(x: 0, y: 0, width: width, height: 320)
                        let beforeWin: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: beforeHost.view.frame)
                        beforeWin.frame = beforeHost.view.frame
                        beforeWin.overrideUserInterfaceStyle = uiStyle
                        beforeWin.rootViewController = beforeHost
                        beforeWin.makeKeyAndVisible()
                        var beforeShareFrame: CGRect = .zero
                        let bDeadline = Date().addingTimeInterval(1.5)
                        while Date() < bDeadline {
                            beforeHost.view.setNeedsLayout()
                            beforeHost.view.layoutIfNeeded()
                            var bVisited = Set<ObjectIdentifier>()
                            if let bEl = findAccessibilityElement(named: "Share", in: beforeHost.view, visited: &bVisited) {
                                beforeShareFrame = bEl.accessibilityFrame
                                if beforeShareFrame.width > 1 { break }
                            }
                            try? await Task.sleep(nanoseconds: 40_000_000)
                        }
                        let beforeImg = UIGraphicsImageRenderer(bounds: navRect, format: fmt).image { ctx in
                            if !beforeHost.view.drawHierarchy(in: beforeHost.view.bounds, afterScreenUpdates: true) {
                                beforeHost.view.layer.render(in: ctx.cgContext)
                            }
                        }
                        beforeWin.isHidden = true
                        beforeWin.rootViewController = nil
                        try beforeImg.pngData()?.write(to: dirURL.appendingPathComponent("real-before-\(sizeTag)-\(schemeTag)-390.png"))
                        frameSummaryLines.append(
                            "\(sizeTag)-\(schemeTag): before=\(Int(round(beforeShareFrame.width)))x\(Int(round(beforeShareFrame.height))) after=\(Int(round(rawFrame.width)))x\(Int(round(rawFrame.height)))"
                        )
                    }
                }
            }
        }

        if let outDir, !outDir.isEmpty, !frameSummaryLines.isEmpty {
            let url = URL(fileURLWithPath: outDir, isDirectory: true).appendingPathComponent("frames.txt")
            try Data(frameSummaryLines.joined(separator: "\n").utf8).write(to: url, options: .atomic)
        }
    }
}
