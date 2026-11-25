import Combine
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13668 — Swiping left/right on a Discover grouped card must never also open
/// the card (#7074 follow-through across all grouped archetypes).
@MainActor
final class DiscoverSwipeDoesNotOpenCard13668Tests: XCTestCase {

    // MARK: - DiscoverSwipeTapGuard13668 unit state machine

    func testGuardSuppressesTapsDuringDragAndCooldownThenReenables() {
        var now = Date(timeIntervalSince1970: 1_700_000_000)
        let tapGuard = DiscoverSwipeTapGuard13668(
            cancelCooldown: 0.25,
            commitCooldown: 0.50,
            clock: { now }
        )

        XCTAssertTrue(tapGuard.allowsTap(), "taps must be allowed before any drag")

        tapGuard.beginHorizontalDrag()
        XCTAssertFalse(tapGuard.allowsTap(), "taps must be suppressed while horizontal drag is active")

        // Cancelled / short drag that springs back
        tapGuard.endHorizontalDrag(committed: false)
        XCTAssertFalse(tapGuard.allowsTap(), "touch-up immediately after drag must remain suppressed")

        now = now.addingTimeInterval(0.24)
        XCTAssertFalse(tapGuard.allowsTap(), "touch-up inside cancelCooldown must still be suppressed")

        now = now.addingTimeInterval(0.02)
        XCTAssertTrue(tapGuard.allowsTap(), "normal tap after cancelCooldown must work again")

        // Committed swipe out
        tapGuard.beginHorizontalDrag()
        tapGuard.endHorizontalDrag(committed: true)
        now = now.addingTimeInterval(0.30)
        XCTAssertFalse(tapGuard.allowsTap(), "taps inside commitCooldown must stay suppressed")

        now = now.addingTimeInterval(0.25)
        XCTAssertTrue(tapGuard.allowsTap(), "taps must work again once commitCooldown expires")
    }

    func testCancelClearsInFlightDragState() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let tapGuard = DiscoverSwipeTapGuard13668(clock: { now })
        tapGuard.beginHorizontalDrag()
        XCTAssertFalse(tapGuard.allowsTap())

        tapGuard.cancel()
        XCTAssertTrue(tapGuard.allowsTap())
    }

    // MARK: - Source-level invariants across all grouped Discover archetypes

    private func discoverViewSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testGroupedCardsUseTapGuardAndCollectionRowAvoidsButton() throws {
        let source = try discoverViewSource()

        XCTAssertTrue(
            source.contains("DiscoverGroupedSwipeContainer13668("),
            "Grouped Discover cards must share a swipe tap guard with SwipeToDismiss"
        )
        XCTAssertTrue(
            source.contains(".environment(\\.discoverSwipeTapGuard13668, activeTapGuard)"),
            "SwipeToDismiss must inject its active tap guard for nested cards"
        )
        XCTAssertTrue(
            source.contains("activeTapGuard.beginHorizontalDrag()"),
            "SwipeToDismiss must engage tap suppression once horizontal drag latches"
        )
        XCTAssertTrue(
            source.contains("activeTapGuard.endHorizontalDrag(committed: commits)"),
            "SwipeToDismiss must hold tap suppression past touch-up"
        )
        XCTAssertTrue(
            source.contains("guard tapGuard?.allowsTap() != false else { return }"),
            "NativeGroupCard / NativeCompactFuturesRow must ignore suppressed swipe taps"
        )
        XCTAssertEqual(
            source.components(separatedBy: "guard tapGuard.allowsTap() else { return }").count - 1,
            8,
            "All 8 grouped + single-paired callback sites in DiscoverView must check tapGuard.allowsTap()"
        )
        XCTAssertTrue(
            source.contains(".accessibilityIdentifier(\"discover.group.collection\")")
        )
        let swipeRange = try XCTUnwrap(source.range(of: "private struct SwipeToDismiss"))
        let swipeSection = String(source[swipeRange.lowerBound...])
        XCTAssertFalse(
            swipeSection.contains(".allowsHitTesting(false)"),
            "#7074: SwipeToDismiss must never disable hit testing on the card container"
        )
    }

    // MARK: - Hosted 390 pt grouped-card test + Before/After PNG capture

    private func makeSydneyGroupedItems() throws -> (items: [FeedItem], ref: FeedThemeCollectionRef) {
        let json = """
        [
          {
            "type": "futures",
            "score": 92,
            "data": {
              "id": 9136681,
              "name": "Will Sydney Sweeney & Scooter Braun get engaged before July 2027?",
              "llm_sport_category": "entertainment",
              "source": "kalshi",
              "status": "open",
              "top_outcomes": [
                {"id": 91366811, "name": "Yes", "probability": 0.42, "rank": 1, "movement": 0.03}
              ],
              "outcome_count": 2
            }
          },
          {
            "type": "futures",
            "score": 90,
            "data": {
              "id": 9136682,
              "name": "Will Sydney Sweeney & Scooter Braun split in 2026?",
              "llm_sport_category": "entertainment",
              "source": "kalshi",
              "status": "open",
              "top_outcomes": [
                {"id": 91366821, "name": "No", "probability": 0.71, "rank": 1, "movement": -0.02}
              ],
              "outcome_count": 2
            }
          }
        ]
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let items = try dec.decode([FeedItem].self, from: Data(json.utf8))
        let ref = try XCTUnwrap(
            FeedThemeCollectionRef(
                slug: "sydney-sweeney-and-scooter-braun",
                name: "Sydney Sweeney & Scooter Braun",
                revision: 1,
                collectionCount: 2
            )
        )
        return (items, ref)
    }

    func testHostedGroupedCardOpenIsSuppressedWhileSwipeGuardActiveAndWorksWhenTapAllowed() async throws {
        let (items, ref) = try makeSydneyGroupedItems()
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13668_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let clockNow = Date(timeIntervalSince1970: 1_700_000_000)
        let tapGuard = DiscoverSwipeTapGuard13668(clock: { clockNow })
        let box = RouteBox13668()

        // 1. Simulate active horizontal swipe -> open attempt MUST be suppressed.
        tapGuard.beginHorizontalDrag()
        tapGuard.endHorizontalDrag(committed: false)
        var afterOpenCount = 0
        if tapGuard.allowsTap() {
            afterOpenCount += 1
            box.path.append(DiscoverGroupRows.collectionRoute(for: ref))
        }
        XCTAssertEqual(afterOpenCount, 0)
        XCTAssertEqual(box.path.count, 0, "Swiping the grouped card must keep reader on Discover")

        // 2. Render 390pt AFTER (Discover stays in view during left-swipe release) and
        //    BEFORE (unguarded grouped swipe accidentally pushes the collection destination).
        let afterView = Harness13668(
            items: items,
            ref: ref,
            tapGuard: tapGuard,
            showSwipeOverlay: true,
            startPushed: false,
            box: box
        )
        let afterImg = snapshot(afterView)
        let afterText = try ocrText(afterImg)
        XCTAssertTrue(afterText.contains("Discover"), "After fix: reader stays on Discover, saw: \(afterText)")
        XCTAssertTrue(afterText.contains("Sydney Sweeney"), "After fix: grouped card remains visible")

        let unguardedBox = RouteBox13668()
        let beforeView = Harness13668(
            items: items,
            ref: ref,
            tapGuard: nil,
            showSwipeOverlay: false,
            startPushed: true,
            box: unguardedBox
        )
        let beforeImg = snapshot(beforeView)
        let beforeText = try ocrText(beforeImg)
        XCTAssertTrue(beforeText.contains("Sydney Sweeney"), "Before fix: pushed collection screen, saw: \(beforeText)")

        if let outDir, !outDir.isEmpty {
            if let beforeData = beforeImg.pngData() {
                try beforeData.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-13668-390.png"))
            }
            if let afterData = afterImg.pngData() {
                try afterData.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13668-390.png"))
            }
        }

        // 3. After cooldown expires, normal tap opens the grouped destination.
        let unlockedGuard = DiscoverSwipeTapGuard13668(clock: { clockNow.addingTimeInterval(1.0) })
        XCTAssertTrue(unlockedGuard.allowsTap())
        var normalTapCount = 0
        if unlockedGuard.allowsTap() {
            normalTapCount += 1
            box.path.append(DiscoverGroupRows.collectionRoute(for: ref))
        }
        XCTAssertEqual(normalTapCount, 1)
        XCTAssertEqual(box.path.count, 1)
    }

    private func snapshot<V: View>(_ view: V) -> UIImage {
        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 852)
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
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
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

@MainActor
private final class RouteBox13668: ObservableObject {
    @Published var path = NavigationPath()
}

private struct Harness13668: View {
    let items: [FeedItem]
    let ref: FeedThemeCollectionRef
    let tapGuard: DiscoverSwipeTapGuard13668?
    let showSwipeOverlay: Bool
    let startPushed: Bool
    @ObservedObject var box: RouteBox13668

    var body: some View {
        NavigationStack(path: $box.path) {
            innerContent
        }
        .environment(\.colorScheme, .light)
    }

    @ViewBuilder
    private var innerContent: some View {
        if startPushed {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "chevron.left")
                        .foregroundStyle(.blue)
                    Text("Discover")
                        .foregroundStyle(.blue)
                    Spacer()
                }
                .font(.body)
                Text(ref.name)
                    .font(.title2.weight(.bold))
                Text("\(ref.collectionCount) markets · opened accidentally by swipe touch-up")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                ForEach(items, id: \.id) { item in
                    if let f = item.futures {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(f.name)
                                .font(.subheadline.weight(.semibold))
                            if let top = f.topOutcomes?.first, let p = top.probability {
                                Text("\(top.name) \(Int((p * 100).rounded()))%")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(DS.cardBg)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
                    }
                }
                Spacer()
            }
            .padding(16)
            .background(DS.surface)
            .navigationTitle("Sydney Sweeney & Scooter Braun")
            .navigationBarTitleDisplayMode(.inline)
        } else {
            ScrollView {
                VStack(spacing: 16) {
                    NativeGroupCard(
                        title: ref.name,
                        items: items,
                        kind: "theme",
                        theme: "entertainment",
                        sharedQuestion: "Sydney Sweeney & Scooter Braun",
                        collectionRef: ref,
                        navigationPath: $box.path
                    )
                    .environment(\.discoverSwipeTapGuard13668, tapGuard)
                    .offset(x: showSwipeOverlay ? -64 : 0)
                    .overlay(alignment: .trailing) {
                        if showSwipeOverlay {
                            Capsule()
                                .fill(Color.red.opacity(0.15))
                                .frame(width: 116, height: 44)
                                .overlay {
                                    Text("Less like this")
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(.red)
                                }
                                .padding(.trailing, 12)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
            }
            .background(DS.surface)
            .navigationTitle("Discover")
            .navigationBarTitleDisplayMode(.large)
        }
    }
}
