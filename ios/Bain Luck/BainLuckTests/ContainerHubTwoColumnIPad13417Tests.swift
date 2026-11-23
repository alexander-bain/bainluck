import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class TraitOverrideContainer13417: UIViewController {
    private let child: UIViewController
    private let overrideTraits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.overrideTraits = traits
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        child.view.backgroundColor = .clear
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}

private struct MockContainerHubService13417: ContainerHubLoading {
    let response: ContainerHubResponse
    let pairedSets: [PairedMetricSet]

    nonisolated func load(slug: String) async throws -> ContainerHubResponse {
        response
    }

    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
        pairedSets
    }
}

/// #13417 — Two-column layout for set pages (`ContainerHubView`) on iPad regular width,
/// single column on compact width (iPhone, Split View, Slide Over) and accessibility text sizes.
@MainActor
final class ContainerHubTwoColumnIPad13417Tests: XCTestCase {

    // MARK: - Layout arithmetic

    func testColumnCountBreakpointsAndCompactOrAccessibilityFallbacks() {
        // Phone / Split View / Slide Over (.compact): always 1 column regardless of width.
        for width in [CGFloat(320), 390, 440, 678, 834, 900] {
            for dt in [DynamicTypeSize.xSmall, .large, .xxxLarge, .accessibility5] {
                XCTAssertEqual(
                    ContainerHubGridLayout13417.columnCount(
                        horizontalSizeClass: .compact,
                        dynamicTypeSize: dt,
                        availableWidth: width
                    ),
                    1,
                    "Compact width \(width) at \(dt) must stay 1 column"
                )
            }
        }

        // iPad 11-inch portrait (798 pt inner), 11-inch landscape / 13-inch (864 pt inner):
        // 2 columns across standard text sizes, including .xxxLarge.
        for innerWidth in [CGFloat(798), 864] {
            for dt in [DynamicTypeSize.xSmall, .large, .xxLarge, .xxxLarge] {
                XCTAssertEqual(
                    ContainerHubGridLayout13417.columnCount(
                        horizontalSizeClass: .regular,
                        dynamicTypeSize: dt,
                        availableWidth: innerWidth
                    ),
                    2,
                    "Regular inner width \(innerWidth) at \(dt) must use 2 columns"
                )
            }
        }

        // Initial pass before GeometryReader resolves (`availableWidth == nil`): regular uses 2.
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: nil
            ),
            2
        )

        // Narrow regular window (< 2 * 340 + 16 = 696 pt): drops safely to 1 column.
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: 695
            ),
            1
        )
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: 696
            ),
            2
        )

        // Accessibility text sizes (AX1–AX5) on 11-inch portrait fall back cleanly to 1 column.
        for ax in [
            DynamicTypeSize.accessibility1,
            .accessibility2,
            .accessibility3,
            .accessibility4,
            .accessibility5
        ] {
            XCTAssertEqual(
                ContainerHubGridLayout13417.columnCount(
                    horizontalSizeClass: .regular,
                    dynamicTypeSize: ax,
                    availableWidth: 798
                ),
                1,
                "Regular 11-inch portrait at \(ax) must fall back to 1 column"
            )
        }
    }

    func testReadingOrderDealsLeftToRightThenDown() {
        let dealt = DiscoverMasonry.columns(cardCount: 6, columnCount: 2)
        XCTAssertEqual(dealt, [[0, 2, 4], [1, 3, 5]])
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 5, columnCount: 2), [[0, 2, 4], [1, 3]])
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 1, columnCount: 2), [[0], []])
    }

    func testInnerContentWidthAndZeroOrNegativeWidthNeverFlashesTwoColumns() {
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 0), 0)
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: -10), 0)
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: 0
            ),
            1
        )
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 700), 664)
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: 700)
            ),
            1
        )
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 731), 695)
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: 731)
            ),
            1
        )
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 732), 696)
        XCTAssertEqual(
            ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: .regular,
                dynamicTypeSize: .large,
                availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: 732)
            ),
            2
        )
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 834), 798)
        XCTAssertEqual(ContainerHubGridLayout13417.innerContentWidth(containerWidth: 1376), 864)
    }

    func testFirstLoadedFrameAt700PtRendersOneColumnWithoutTwoColumnFlash() async throws {
        let nflData = try fixtureData("live_nfl_week12_13417")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let nflResp = try decoder.decode(ContainerHubResponse.self, from: nflData)
        let firstTwoEvents: [(away: String, home: String)] = nflResp.sections.first?.members.prefix(2).compactMap {
            guard case .event(let e) = $0.card else { return nil }
            return (e.awayTeam, e.homeTeam)
        } ?? []
        XCTAssertEqual(firstTwoEvents.count, 2)
        let game0Token = firstTwoEvents[0].away.split(separator: " ").last.map(String.init) ?? firstTwoEvents[0].away
        let game1Token = firstTwoEvents[1].away.split(separator: " ").last.map(String.init) ?? firstTwoEvents[1].away
        let service = MockContainerHubService13417(response: nflResp, pairedSets: [])

        // Frame 1 at 700 pt .regular must already render 1 column (never flash 2 columns before measure).
        let frame1Narrow = await captureFirstLoadedFrame(
            ContainerHubView(slug: "nfl-2026-week-12", displayName: "NFL Week 12", service: service),
            width: 700,
            height: 1000
        )
        try maybeSave(frame1Narrow, "13417-frame1-700pt.png")
        let obsNarrow = try ocrObservations(frame1Narrow)
        let g0Narrow = obsNarrow.first { $0.text.localizedCaseInsensitiveContains(game0Token) }
        let g1Narrow = obsNarrow.first { $0.text.localizedCaseInsensitiveContains(game1Token) }
        XCTAssertNotNil(g0Narrow, "Frame 1 700pt missing \(game0Token)")
        XCTAssertNotNil(g1Narrow, "Frame 1 700pt missing \(game1Token)")
        if let g0Narrow, let g1Narrow {
            XCTAssertLessThan(g0Narrow.midX, 0.50, "700pt Frame 1 card 0 midX=\(g0Narrow.midX)")
            XCTAssertLessThan(g1Narrow.midX, 0.50, "700pt Frame 1 card 1 must already be 1 column, got midX=\(g1Narrow.midX)")
        }

        // Frame 1 at 834 pt .regular already renders 2 columns immediately.
        let frame1Regular = await captureFirstLoadedFrame(
            ContainerHubView(slug: "nfl-2026-week-12", displayName: "NFL Week 12", service: service),
            width: 834,
            height: 1210
        )
        try maybeSave(frame1Regular, "13417-frame1-834pt.png")
        let obsReg = try ocrObservations(frame1Regular)
        let g0Reg = obsReg.first { $0.text.localizedCaseInsensitiveContains(game0Token) }
        let g1Reg = obsReg.first { $0.text.localizedCaseInsensitiveContains(game1Token) }
        XCTAssertNotNil(g0Reg, "Frame 1 834pt missing \(game0Token)")
        XCTAssertNotNil(g1Reg, "Frame 1 834pt missing \(game1Token)")
        if let g0Reg, let g1Reg {
            XCTAssertLessThan(g0Reg.midX, 0.48, "834pt Frame 1 card 0 midX=\(g0Reg.midX)")
            XCTAssertGreaterThan(g1Reg.midX, 0.50, "834pt Frame 1 card 1 midX=\(g1Reg.midX)")
        }
    }

    // MARK: - Rendered Set Page Tests & Evidence Sheets

    func testNFLWeek12AndOscarsCultureSetLayoutsAndZeroTruncationAcrossIPadAndIPhone() async throws {
        let nflData = try fixtureData("live_nfl_week12_13417")
        let oscarsData = try fixtureData("live_oscars_2027_13417")
        let pairedData = try fixtureData("live_oscars_paired_13417")

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let nflResp = try decoder.decode(ContainerHubResponse.self, from: nflData)
        let oscarsResp = try decoder.decode(ContainerHubResponse.self, from: oscarsData)
        struct PairedEnvelope: Decodable { let sets: [PairedMetricSet] }
        let pairedSets = try decoder.decode(PairedEnvelope.self, from: pairedData).sets

        let firstTwoEvents: [(away: String, home: String)] = nflResp.sections.first?.members.prefix(2).compactMap {
            guard case .event(let e) = $0.card else { return nil }
            return (e.awayTeam, e.homeTeam)
        } ?? []
        XCTAssertEqual(firstTwoEvents.count, 2, "NFL Week 12 fixture must contain at least 2 game cards")
        let game0Token = firstTwoEvents[0].away.split(separator: " ").last.map(String.init) ?? firstTwoEvents[0].away
        let game1Token = firstTwoEvents[1].away.split(separator: " ").last.map(String.init) ?? firstTwoEvents[1].away

        let nflService = MockContainerHubService13417(response: nflResp, pairedSets: [])
        let oscarsService = MockContainerHubService13417(response: oscarsResp, pairedSets: pairedSets)

        struct Spec {
            let tag: String
            let label: String
            let width: CGFloat
            let height: CGFloat
            let sizeClass: UserInterfaceSizeClass
            let scheme: ColorScheme
            let dynamicType: DynamicTypeSize
            let expectTwoColumns: Bool
        }

        let specs: [Spec] = [
            .init(tag: "ipad13-portrait-light", label: "iPad 13\" Portrait · Light", width: 1032, height: 1376, sizeClass: .regular, scheme: .light, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad13-portrait-dark", label: "iPad 13\" Portrait · Dark", width: 1032, height: 1376, sizeClass: .regular, scheme: .dark, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad13-landscape-light", label: "iPad 13\" Landscape · Light", width: 1376, height: 1032, sizeClass: .regular, scheme: .light, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad13-landscape-dark", label: "iPad 13\" Landscape · Dark", width: 1376, height: 1032, sizeClass: .regular, scheme: .dark, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad11-portrait-light", label: "iPad 11\" Portrait · Light", width: 834, height: 1210, sizeClass: .regular, scheme: .light, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad11-portrait-dark", label: "iPad 11\" Portrait · Dark", width: 834, height: 1210, sizeClass: .regular, scheme: .dark, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad11-landscape-light", label: "iPad 11\" Landscape · Light", width: 1210, height: 834, sizeClass: .regular, scheme: .light, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad11-landscape-dark", label: "iPad 11\" Landscape · Dark", width: 1210, height: 834, sizeClass: .regular, scheme: .dark, dynamicType: .large, expectTwoColumns: true),
            .init(tag: "ipad11-portrait-ax5-light", label: "iPad 11\" Portrait · AX5 (1 col)", width: 834, height: 1210, sizeClass: .regular, scheme: .light, dynamicType: .accessibility5, expectTwoColumns: false),
            .init(tag: "ipad11-portrait-xxxLarge-light", label: "iPad 11\" Portrait · XXXLarge (2 col)", width: 834, height: 1210, sizeClass: .regular, scheme: .light, dynamicType: .xxxLarge, expectTwoColumns: true),
            .init(tag: "iphone-390-light", label: "iPhone 390 · Light (1 col)", width: 390, height: 844, sizeClass: .compact, scheme: .light, dynamicType: .large, expectTwoColumns: false),
            .init(tag: "iphone-390-dark", label: "iPhone 390 · Dark (1 col)", width: 390, height: 844, sizeClass: .compact, scheme: .dark, dynamicType: .large, expectTwoColumns: false),
        ]

        var nflImages: [(String, UIImage)] = []
        var oscarsImages: [(String, UIImage)] = []

        for spec in specs {
            let nflImage = await captureHub(
                ContainerHubView(slug: "nfl-2026-week-12", displayName: "NFL Week 12", service: nflService),
                width: spec.width,
                height: spec.height,
                sizeClass: spec.sizeClass,
                scheme: spec.scheme,
                dynamicType: spec.dynamicType
            )
            let nflObs = try ocrObservations(nflImage)
            let nflText = nflObs.map(\.text).joined(separator: "\n")
            XCTAssertFalse(nflText.contains("Loading"), "[\(spec.tag)] NFL hub did not finish loading")

            let g0 = nflObs.first { $0.text.localizedCaseInsensitiveContains(game0Token) }
            let g1 = nflObs.first { $0.text.localizedCaseInsensitiveContains(game1Token) }
            XCTAssertNotNil(g0, "[\(spec.tag)] missing game 0 token '\(game0Token)' in OCR:\n\(nflText)")
            XCTAssertNotNil(g1, "[\(spec.tag)] missing game 1 token '\(game1Token)' in OCR:\n\(nflText)")
            if let g0, let g1 {
                if spec.expectTwoColumns {
                    XCTAssertLessThan(g0.midX, 0.48, "[\(spec.tag)] card 0 should sit in left column, got midX=\(g0.midX)")
                    XCTAssertGreaterThan(g1.midX, 0.50, "[\(spec.tag)] card 1 should sit in right column, got midX=\(g1.midX)")
                    XCTAssertLessThan(abs(g0.midY - g1.midY), 0.12, "[\(spec.tag)] card 0 and card 1 must align top-left/top-right, midY diff=\(abs(g0.midY - g1.midY))")
                } else {
                    XCTAssertLessThan(g0.midX, 0.50, "[\(spec.tag)] single-column card 0 midX=\(g0.midX)")
                    XCTAssertLessThan(g1.midX, 0.50, "[\(spec.tag)] single-column card 1 must stay in left column, got midX=\(g1.midX)")
                }
            }
            if spec.dynamicType >= .xxxLarge {
                XCTAssertFalse(nflText.contains("..."), "[\(spec.tag)] found ellipsis truncation at large text size:\n\(nflText)")
            }
            nflImages.append((spec.label, nflImage))
            try maybeSave(nflImage, "13417-nfl-\(spec.tag).png")

            let oscarsImage = await captureHub(
                ContainerHubView(slug: "oscars-2027", displayName: "Oscars 2027", service: oscarsService),
                width: spec.width,
                height: spec.height,
                sizeClass: spec.sizeClass,
                scheme: spec.scheme,
                dynamicType: spec.dynamicType
            )
            let oscObs = try ocrObservations(oscarsImage)
            let oscText = oscObs.map(\.text).joined(separator: "\n")
            XCTAssertTrue(oscText.localizedCaseInsensitiveContains("Best Picture"), "[\(spec.tag)] Oscars Best Picture missing:\n\(oscText)")
            XCTAssertFalse(nflText.localizedCaseInsensitiveContains("aren't available right now"), "[\(spec.tag)] NFL fixture should not show partial warning")
            XCTAssertFalse(oscText.localizedCaseInsensitiveContains("Retry unavailable markets"), "[\(spec.tag)] Oscars fixture should not show partial retry")

            if pairedSets.count >= 2 {
                let firstSet = oscObs.first { $0.text.localizedCaseInsensitiveContains("Best Picture") }
                let secondSet = oscObs.first { $0.text.localizedCaseInsensitiveContains("Best Director") }
                if let firstSet, let secondSet, spec.expectTwoColumns {
                    XCTAssertLessThan(firstSet.midX, 0.48, "[\(spec.tag)] Best Picture card should be left column, got \(firstSet.midX)")
                    XCTAssertGreaterThan(secondSet.midX, 0.50, "[\(spec.tag)] Best Director card should be right column, got \(secondSet.midX)")
                } else if let firstSet, let secondSet {
                    XCTAssertLessThan(firstSet.midX, 0.45, "[\(spec.tag)] single column Best Picture midX=\(firstSet.midX)")
                    XCTAssertLessThan(secondSet.midX, 0.45, "[\(spec.tag)] single column Best Director must stay in single column, got \(secondSet.midX)")
                }
            }
            if spec.dynamicType >= .xxxLarge {
                XCTAssertFalse(oscText.contains("..."), "[\(spec.tag)] Oscars truncated at large text size:\n\(oscText)")
            }
            oscarsImages.append((spec.label, oscarsImage))
            try maybeSave(oscarsImage, "13417-oscars-\(spec.tag).png")
        }

        // Save composite contact sheets when BAINLUCK_13417_RENDER_DIR is specified.
        if let dir = ProcessInfo.processInfo.environment["BAINLUCK_13417_RENDER_DIR"], !dir.isEmpty {
            let nflGrid = Self.contactSheet(tiles: Array(nflImages.prefix(8)), columns: 2, scale: 0.48)
            try maybeSave(nflGrid, "sheet-13417-ipad-nfl-week12.png")

            let oscarsGrid = Self.contactSheet(tiles: Array(oscarsImages.prefix(8)), columns: 2, scale: 0.48)
            try maybeSave(oscarsGrid, "sheet-13417-ipad-oscars-2027.png")

            let axAndPhoneTiles = Array(nflImages.dropFirst(8)) + Array(oscarsImages.dropFirst(8))
            let axAndPhoneGrid = Self.contactSheet(tiles: axAndPhoneTiles, columns: 4, scale: 0.55)
            try maybeSave(axAndPhoneGrid, "sheet-13417-iphone-and-largest-text.png")
        }
    }

    func testStandaloneQuestionCardsDealLeftToRightIntoTwoColumnsOnIPadAndOneColumnOnCompact() async throws {
        let oscarsData = try fixtureData("live_oscars_2027_13417")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let oscarsResp = try decoder.decode(ContainerHubResponse.self, from: oscarsData)
        let service = MockContainerHubService13417(response: oscarsResp, pairedSets: [])

        // iPad 11-inch portrait (.regular): card 0 (Best Director) top-left, card 1 (Best Actress) top-right.
        let iPadImage = await captureHub(
            ContainerHubView(slug: "oscars-2027", displayName: "Oscars 2027", service: service),
            width: 834,
            height: 1210,
            sizeClass: .regular,
            scheme: .light,
            dynamicType: .large
        )
        let iPadObs = try ocrObservations(iPadImage)
        let iPadText = iPadObs.map(\.text).joined(separator: "\n")
        let directorIPad = try XCTUnwrap(iPadObs.first { $0.text.localizedCaseInsensitiveContains("Best Director") }, "Missing Best Director:\n\(iPadText)")
        let actressIPad = try XCTUnwrap(iPadObs.first { $0.text.localizedCaseInsensitiveContains("Best Actress") }, "Missing Best Actress:\n\(iPadText)")
        XCTAssertLessThan(directorIPad.midX, 0.48, "Card 0 standalone questionCard should sit in left column, got \(directorIPad.midX)")
        XCTAssertGreaterThan(actressIPad.midX, 0.50, "Card 1 standalone questionCard should sit in right column, got \(actressIPad.midX)")
        XCTAssertLessThan(abs(directorIPad.midY - actressIPad.midY), 0.12, "Standalone questionCards 0 and 1 must align top-left/top-right")

        // Compact width (.compact, iPad Split View / Slide Over): stays single-column.
        let compactImage = await captureHub(
            ContainerHubView(slug: "oscars-2027", displayName: "Oscars 2027", service: service),
            width: 390,
            height: 844,
            sizeClass: .compact,
            scheme: .light,
            dynamicType: .large
        )
        let compactObs = try ocrObservations(compactImage)
        let compactText = compactObs.map(\.text).joined(separator: "\n")
        let directorCompact = try XCTUnwrap(compactObs.first { $0.text.localizedCaseInsensitiveContains("Best Director") }, "Compact missing Best Director:\n\(compactText)")
        let actressCompact = try XCTUnwrap(compactObs.first { $0.text.localizedCaseInsensitiveContains("Best Actress") }, "Compact missing Best Actress:\n\(compactText)")
        XCTAssertLessThan(directorCompact.midX, 0.50, "Compact card 0 midX=\(directorCompact.midX)")
        XCTAssertLessThan(actressCompact.midX, 0.50, "Compact card 1 must stay in single column, got \(actressCompact.midX)")
        XCTAssertGreaterThan(actressCompact.midY, directorCompact.midY, "Compact card 1 must stack below card 0")
    }

    // MARK: - Helpers

    private func fixtureData(_ name: String) throws -> Data {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("ContainerHubFixtures/\(name).json")
        return try Data(contentsOf: url)
    }

    private func captureHub<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        sizeClass: UserInterfaceSizeClass,
        scheme: ColorScheme,
        dynamicType: DynamicTypeSize
    ) async -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let root = NavigationStack {
            view
                .navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: width, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.horizontalSizeClass, sizeClass)
        .environment(\.colorScheme, scheme)
        .environment(\.dynamicTypeSize, dynamicType)
        .environmentObject(NavigationCoordinator())
        .environmentObject(PinManager())
        .environmentObject(AuthManager())

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: sizeClass == .regular ? .regular : .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light)
        ])
        let host = hostForMeasurement(root, at: dynamicType)
        let container = TraitOverrideContainer13417(child: host, traits: traits)
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false

        for _ in 0..<12 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 50_000_000)
        }

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1.0
        let renderer = UIGraphicsImageRenderer(size: container.view.bounds.size, format: format)
        let img = renderer.image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }

    private func captureFirstLoadedFrame<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat
    ) async -> UIImage {
        let root = NavigationStack {
            view.navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: width, height: height, alignment: .topLeading)
        .background(Color(UIColor.systemGroupedBackground))
        .environment(\.horizontalSizeClass, .regular)
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, .large)
        .environmentObject(NavigationCoordinator())
        .environmentObject(PinManager())
        .environmentObject(AuthManager())

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .regular),
            UITraitCollection(userInterfaceStyle: .light)
        ])
        let host = hostForMeasurement(root, at: .large)
        let container = TraitOverrideContainer13417(child: host, traits: traits)
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = container
        window.isHidden = false

        // Allow async .task {} mock load to deliver .loaded state, then capture on the single layout pass.
        container.view.setNeedsLayout()
        container.view.layoutIfNeeded()
        await Task.yield()
        try? await Task.sleep(nanoseconds: 50_000_000)
        container.view.setNeedsLayout()
        container.view.layoutIfNeeded()

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1.0
        let renderer = UIGraphicsImageRenderer(size: container.view.bounds.size, format: format)
        let img = renderer.image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }

    private struct OCRObs {
        let text: String
        let midX: CGFloat
        let midY: CGFloat // normalized 0 = top, 1 = bottom
    }

    private func ocrObservations(_ image: UIImage) throws -> [OCRObs] {
        guard let cg = image.cgImage else { return [] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
        return (request.results ?? []).compactMap { obs in
            guard let top = obs.topCandidates(1).first else { return nil }
            let box = obs.boundingBox
            return OCRObs(text: top.string, midX: box.midX, midY: 1.0 - box.midY)
        }
    }

    private func maybeSave(_ image: UIImage, _ filename: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["BAINLUCK_13417_RENDER_DIR"], !dir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: dir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        if let png = image.pngData() {
            try png.write(to: dirURL.appendingPathComponent(filename))
        }
    }

    private static func contactSheet(tiles: [(String, UIImage)], columns: Int, scale: CGFloat) -> UIImage {
        guard !tiles.isEmpty else { return UIImage() }
        let headerH: CGFloat = 28
        let gap: CGFloat = 16
        let pad: CGFloat = 16
        let scaledSizes = tiles.map { CGSize(width: ($0.1.size.width * scale).rounded(), height: ($0.1.size.height * scale).rounded()) }
        let cellW = scaledSizes.map(\.width).max() ?? 400
        let cellH = (scaledSizes.map(\.height).max() ?? 500) + headerH
        let rows = (tiles.count + columns - 1) / columns
        let totalW = pad * 2 + CGFloat(columns) * cellW + CGFloat(max(0, columns - 1)) * gap
        let totalH = pad * 2 + CGFloat(rows) * cellH + CGFloat(max(0, rows - 1)) * gap

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1.0
        return UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: format).image { ctx in
            UIColor(white: 0.14, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: totalW, height: totalH))
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 15, weight: .semibold),
                .foregroundColor: UIColor.white
            ]
            for (idx, item) in tiles.enumerated() {
                let col = idx % columns
                let row = idx / columns
                let originX = pad + CGFloat(col) * (cellW + gap)
                let originY = pad + CGFloat(row) * (cellH + gap)
                (item.0 as NSString).draw(at: CGPoint(x: originX, y: originY + 4), withAttributes: attrs)
                let imgSize = scaledSizes[idx]
                item.1.draw(in: CGRect(x: originX, y: originY + headerH, width: imgSize.width, height: imgSize.height))
            }
        }
    }
}
#endif
