import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class LiveUpdatePopover12938Tests: XCTestCase {

    private func makeNow() -> Date {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: "2026-11-18T05:13:51.000Z")!
    }

    private func makeStanfordEvent() throws -> EventDetail {
        let json = """
        {
          "id": 15350027,
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "away_team": "UC Irvine Anteaters",
          "home_team": "Stanford Cardinal",
          "away_team_data": {"primary_color": "#0C2340", "abbreviation": "UCI"},
          "home_team_data": {"primary_color": "#8C1515", "abbreviation": "STAN"},
          "commence_time": "2026-11-18T03:00:00Z",
          "status": "live",
          "away_score": 61,
          "home_score": 65,
          "espn": {"period": "2nd", "game_clock": "0:42"},
          "hero_probability": 0.932,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-18T05:13:50Z",
          "current_odds": {
            "away_probability": 0.068,
            "home_probability": 0.932,
            "away_rendered_percent": 7,
            "home_rendered_percent": 93
          },
          "prematch_odds": {
            "away_probability": 0.29,
            "home_probability": 0.71,
            "away_rendered_percent": 29,
            "home_rendered_percent": 71,
            "source": "books"
          }
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func makeStanfordStream() -> LiveUpdateStream {
        // 2026-11-18T05:13:50.880Z = 9:13:50 PM PST (Tue Nov 17)
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var stream = LiveUpdateStream()
        let updates: [LiveUpdateStream.Update] = [
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:07:12.100Z")!, p: 0.740),
            .init(source: "odds_api", at: f.date(from: "2026-11-18T05:07:55.340Z")!, p: 0.791),
            .init(source: "kalshi", at: f.date(from: "2026-11-18T05:08:28.900Z")!, p: 0.815),
            .init(source: "odds_api", at: f.date(from: "2026-11-18T05:09:04.120Z")!, p: 0.795),
            .init(source: "kalshi", at: f.date(from: "2026-11-18T05:09:42.510Z")!, p: 0.880),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:10:18.300Z")!, p: 0.920),
            .init(source: "odds_api", at: f.date(from: "2026-11-18T05:11:02.420Z")!, p: 0.805),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:11:44.770Z")!, p: 0.955),
            .init(source: "kalshi", at: f.date(from: "2026-11-18T05:12:22.190Z")!, p: 0.988),
            .init(source: "odds_api", at: f.date(from: "2026-11-18T05:12:58.050Z")!, p: 0.810),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:19.640Z")!, p: 0.989),
            .init(source: "kalshi", at: f.date(from: "2026-11-18T05:13:31.050Z")!, p: 0.994),
            // Six identical Polymarket 99.5% rows from multi-leg / rapid book ticks around 9:13:50.88 PM
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:48.110Z")!, p: 0.995),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:49.330Z")!, p: 0.995),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:50.880Z")!, p: 0.995),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:50.880Z")!, p: 0.995),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:50.880Z")!, p: 0.995),
            .init(source: "polymarket", at: f.date(from: "2026-11-18T05:13:50.880Z")!, p: 0.995)
        ]
        stream.add(updates)
        return stream
    }

    func testTimeTextPrintsSecondsWithNoHundredths() {
        let pst = TimeZone(identifier: "America/Los_Angeles")!
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = f.date(from: "2026-11-18T05:13:50.880Z")!
        let formatted = LiveUpdateStream.timeText(date, timeZone: pst)
        XCTAssertEqual(formatted, "9:13:50 PM")
        XCTAssertFalse(formatted.contains("."), "Must never include fractional seconds / hundredths")
    }

    func testDisplayRowsCollapsesConsecutiveIdenticalVenueAndProbabilityRuns() {
        let stream = makeStanfordStream()
        let screen = LiveUpdateScreen(opening: stream.updates)
        XCTAssertEqual(screen.rows.count, 18)

        let displayed = LiveUpdateStream.displayRows(screen.rows, maxCount: 8)
        XCTAssertEqual(displayed.count, 8)
        XCTAssertEqual(
            displayed.map { "\(LiveUpdateStream.venueName($0.source)) \(LiveUpdateStream.probabilityText($0.p))" },
            [
                "Polymarket 99.5%",
                "Kalshi 99.4%",
                "Polymarket 98.9%",
                "Sportsbooks 81.0%",
                "Kalshi 98.8%",
                "Polymarket 95.5%",
                "Sportsbooks 80.5%",
                "Polymarket 92.0%"
            ],
            "Six consecutive Polymarket 99.5% rows collapse to the newest one while preserving distinct rows below"
        )
        // Keeps the newest timestamp of the collapsed run (05:13:50.880Z, not 05:13:48.110Z).
        let pst = TimeZone(identifier: "America/Los_Angeles")!
        XCTAssertEqual(LiveUpdateStream.timeText(displayed[0].at, timeZone: pst), "9:13:50 PM")
    }

    private func renderPopoverToPNG<V: View>(_ view: V, width: CGFloat, at typeSize: DynamicTypeSize, to url: URL) throws -> CGSize {
        let content = view
            .frame(width: width)
            .environment(\.dynamicTypeSize, typeSize)
            .environment(\.colorScheme, .light)
        let renderer = ImageRenderer(content: content)
        renderer.scale = 3.0
        let uiImage = try XCTUnwrap(renderer.uiImage)
        try XCTUnwrap(uiImage.pngData()).write(to: url)
        return uiImage.size
    }

    func testPopoverContentKeepsVenueAndTimeSingleLineAndUncutAcrossTextSizes() throws {
        let stream = makeStanfordStream()
        for typeSize in [DynamicTypeSize.large, .xxLarge, .xxxLarge, .accessibility3] {
            let popoverView = LiveUpdateStreamView(
                stream: stream,
                homeTeam: "Stanford",
                onDetails: {}
            )
            .frame(width: 340)
            .background(Color(uiColor: .systemBackground))
            .environment(\.colorScheme, .light)

            let outURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("popover-check-\(typeSize)-\(UUID().uuidString).png")
            defer { try? FileManager.default.removeItem(at: outURL) }

            let size = try renderPopoverToPNG(popoverView, width: 340, at: typeSize, to: outURL)
            XCTAssertGreaterThan(size.height, 140)

            let data = try Data(contentsOf: outURL)
            let image = try XCTUnwrap(UIImage(data: data)?.cgImage)
            let observations = try recognizeObservations(in: image)
            let strings = observations.map(\.text)
            let joined = strings.joined(separator: "\n")

            XCTAssertTrue(joined.contains("Updates feeding"), "Missing popover title at \(typeSize): \(joined)")
            XCTAssertTrue(joined.contains("Polymarket"), "Polymarket must stay on one line without breaking mid-word at \(typeSize): \(joined)")
            XCTAssertFalse(joined.contains("Polymar-"), "Polymarket broke mid-word at \(typeSize): \(joined)")
            XCTAssertFalse(joined.contains(".88"), "Fractional hundredths leaked into rendered popover at \(typeSize): \(joined)")
            XCTAssertTrue(joined.contains("Details"), "Bottom Details action was cut off at \(typeSize): \(joined)")

            // Bottom-most text ("Details") must sit cleanly inside the bottom margin (normalized Vision y > 0.02).
            if let detailsObs = observations.first(where: { $0.text.contains("Details") }) {
                XCTAssertGreaterThan(detailsObs.boundingBox.minY, 0.02, "Bottom row / Details clipped against bottom edge at \(typeSize)")
            }
        }
    }

    private struct RecognizedLine {
        let text: String
        let boundingBox: CGRect
    }

    private func recognizeObservations(in cgImage: CGImage) throws -> [RecognizedLine] {
        var out: [RecognizedLine] = []
        let request = VNRecognizeTextRequest { req, _ in
            guard let results = req.results as? [VNRecognizedTextObservation] else { return }
            for obs in results {
                if let top = obs.topCandidates(1).first {
                    out.append(RecognizedLine(text: top.string, boundingBox: obs.boundingBox))
                }
            }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return out
    }

    private struct PopoverHostScreen: View {
        let model: EventSportHeadlines12472.Model
        let tracker: EkgTracker
        let now: Date
        let stream: LiveUpdateStream
        @State var showPopover = false
        @State var showDetails = false

        var body: some View {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    EventSportHeadlineCard12472(
                        model: model,
                        colors: (Color(hex: "#0C2340"), Color(hex: "#8C1515")),
                        ekgTracker: tracker,
                        liveUpdateStatus: .live,
                        displayAsOf: now,
                        updateStream: stream,
                        showUpdateStream: $showPopover,
                        showProbabilityDetails: $showDetails,
                        priceStreamingEligible: true,
                        lastReceivedAt: now,
                        confirmedAt: now,
                        revealForecast: nil
                    )
                    .padding(16)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(DS.surface)
            .onAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    showPopover = true
                }
            }
        }
    }

    func testExport390PtPopoverRendersWhenRequested() async throws {
        guard ProcessInfo.processInfo.environment["EXPORT_12938_POPOVER_RENDERS"] == "1" else {
            return
        }
        let now = makeNow()
        let event = try makeStanfordEvent()
        let model = EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: "2nd · 0:42",
            hasScore: true,
            numberStreams: true,
            now: now
        )
        let tracker = EkgTracker.empty
            .stepped(.init(eventId: 15350027, transportOpen: true, confirmedAt: now.addingTimeInterval(-6), priceObservedAt: now.addingTimeInterval(-6)), now: now.addingTimeInterval(-5))
            .stepped(.init(eventId: 15350027, transportOpen: true, confirmedAt: now, priceObservedAt: now), now: now)
        let stream = makeStanfordStream()

        let deadline = Date().addingTimeInterval(10)
        func activeScene() -> UIWindowScene? {
            let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            return scenes.first { $0.activationState == .foregroundActive } ?? scenes.first
        }
        while activeScene() == nil && Date() < deadline {
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        let scene = try XCTUnwrap(activeScene())
        let outDir = URL(fileURLWithPath: "/tmp/renders-12938-after", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let existingWindows = scene.windows
        for w in existingWindows { w.isHidden = true }
        defer { for w in existingWindows { w.isHidden = false } }

        let mode = ProcessInfo.processInfo.environment["EXPORT_12938_SIZE_TAG"] ?? "default"
        let typeSize: DynamicTypeSize = mode == "xxlarge" ? .xxLarge : .large

        for (styleName, uiStyle) in [("light", UIUserInterfaceStyle.light), ("dark", UIUserInterfaceStyle.dark)] {
            let rootView = NavigationStack {
                PopoverHostScreen(model: model, tracker: tracker, now: now, stream: stream)
                    .navigationTitle("UC Irvine at Stanford")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .environment(\.colorScheme, uiStyle == .dark ? .dark : .light)
            .environment(\.dynamicTypeSize, typeSize)

            let host = hostForMeasurement(rootView, at: typeSize)
            host.overrideUserInterfaceStyle = uiStyle
            host.traitOverrides.preferredContentSizeCategory = UIContentSizeCategory(typeSize)
            let bounds = CGRect(x: 0, y: 0, width: 390, height: 740)
            host.view.frame = bounds
            let window = UIWindow(windowScene: scene)
            window.overrideUserInterfaceStyle = uiStyle
            window.traitOverrides.preferredContentSizeCategory = UIContentSizeCategory(typeSize)
            window.backgroundColor = uiStyle == .dark ? .black : .systemGroupedBackground
            window.frame = bounds
            window.rootViewController = host
            window.makeKeyAndVisible()

            var didConfigurePresented = false
            let waitEnd = Date().addingTimeInterval(1.2)
            while Date() < waitEnd {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                if let presented = host.presentedViewController {
                    if !didConfigurePresented {
                        didConfigurePresented = true
                        presented.overrideUserInterfaceStyle = uiStyle
                        presented.traitOverrides.preferredContentSizeCategory = UIContentSizeCategory(typeSize)
                    }
                    presented.view.setNeedsLayout()
                    presented.view.layoutIfNeeded()
                }
                try await Task.sleep(nanoseconds: 50_000_000)
            }

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let image = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { _ in
                _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
            }
            host.dismiss(animated: false)
            try await Task.sleep(nanoseconds: 200_000_000)
            window.isHidden = true
            window.rootViewController = nil

            try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent("after-popover-\(mode)-\(styleName)-390.png"))
        }
    }
}
