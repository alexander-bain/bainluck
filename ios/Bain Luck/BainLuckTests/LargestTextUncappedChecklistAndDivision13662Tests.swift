import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Item 2 (#13662 remainder) — Checklist titles must keep growing past 28 pt so
/// titles stay larger than grey subtitles at AX5, and the iPad/iPhone division
/// card, hub grid, and checklist must grow with the reader's Dynamic Type
/// setting rather than capping well short of AX5.
@MainActor
final class LargestTextUncappedChecklistAndDivision13662Tests: XCTestCase {

    #if os(iOS)

    // MARK: - Deterministic Fixtures (reader-facing wording only)

    private func makeChecklistContent() -> FirstRunChecklistContent364A {
        FirstRunChecklistContent364A(
            lookupExamples: [],
            startWithTonight: [],
            discoverSets: [],
            rowPreviews: [
                .lookUp: FirstRunChecklistRowPreview364A(
                    subtitle: "Search any game, team, award, or election",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "magnifyingglass",
                    accentHex: "#005CC2"
                ),
                .follow: FirstRunChecklistRowPreview364A(
                    subtitle: "Teams, cities, schools, or topics",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "star.fill",
                    accentHex: "#047857"
                ),
                .exploreSets: FirstRunChecklistRowPreview364A(
                    subtitle: "Pick topics to shape your Discover feed",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "square.grid.2x2.fill",
                    accentHex: "#7C3AED"
                ),
                .syncDevices: FirstRunChecklistRowPreview364A(
                    subtitle: "Sign in to sync across devices",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "laptopcomputer.and.iphone",
                    accentHex: "#005CC2"
                ),
                .alerts: FirstRunChecklistRowPreview364A(
                    subtitle: "Game starts & 15+ point swings",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "bell.badge.fill",
                    accentHex: "#D97706"
                ),
            ],
            subjectArtByCategory: [:]
        )
    }

    private func makeDivisionRaceFixtures() -> (discoverCard: MachineryCardContract, hubBlock: MachineryVisualBlock) {
        let discoverCard = MachineryCardContract(
            slug: "machinery-afc-west-duel",
            formId: .siblingFieldsGrid,
            kicker: "AFC WEST",
            title: "AFC West Title Race",
            subtitle: "All four AFC West contenders in one division race.",
            footer: "See all 4 divisions",
            scaleOrdered: false,
            sectionCount: 2,
            outcomeRows: [
                MachineryOutcomeVisual(
                    outcomeId: 846594,
                    marketId: 53675,
                    name: "Denver Broncos",
                    probability: 0.525,
                    renderedPercent: 53,
                    unflooredPercent: 53,
                    art: MachinerySubjectArt(kind: "monogram", accentColor: "#FB4F14", initials: "DEN"),
                    settledOut: false
                ),
                MachineryOutcomeVisual(
                    outcomeId: 846593,
                    marketId: 53675,
                    name: "Kansas City Chiefs",
                    probability: 0.004,
                    renderedPercent: 1,
                    unflooredPercent: 0,
                    art: MachinerySubjectArt(kind: "monogram", accentColor: "#E31837", initials: "KC"),
                    settledOut: false
                ),
            ],
            unpricedOutcomes: [
                MachineryOutcomeVisual(
                    outcomeId: 846592,
                    marketId: 53675,
                    name: "Los Angeles Chargers",
                    probability: 0,
                    renderedPercent: 0,
                    art: MachinerySubjectArt(kind: "monogram", accentColor: "#0080C6", initials: "LAC"),
                    settledOut: false
                ),
                MachineryOutcomeVisual(
                    outcomeId: 846591,
                    marketId: 53675,
                    name: "Las Vegas Raiders",
                    probability: 0,
                    renderedPercent: 0,
                    art: MachinerySubjectArt(kind: "monogram", accentColor: "#000000", initials: "LV"),
                    settledOut: true
                ),
            ]
        )

        let hubBlock = MachineryVisualBlock(
            formId: .siblingFieldsGrid,
            initialVisibleLimit: 3,
            itemNoun: "divisions",
            marketItems: [
                MachineryMarketVisualItem(
                    marketId: 53680,
                    title: "NFC West Championship",
                    outcomes: [
                        MachineryOutcomeVisual(
                            outcomeId: 11,
                            name: "San Francisco 49ers",
                            probability: 0.61,
                            renderedPercent: 61,
                            unflooredPercent: 61,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#AA0000", initials: "SF"),
                            settledOut: false
                        ),
                        MachineryOutcomeVisual(
                            outcomeId: 12,
                            name: "Los Angeles Rams",
                            probability: 0.38,
                            renderedPercent: 38,
                            unflooredPercent: 38,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#003594", initials: "LAR"),
                            settledOut: false
                        ),
                        MachineryOutcomeVisual(
                            outcomeId: 13,
                            name: "Seattle Seahawks",
                            probability: 0.004,
                            renderedPercent: 1,
                            unflooredPercent: 0,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#002244", initials: "SEA"),
                            settledOut: false
                        ),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(
                            outcomeId: 14,
                            name: "Arizona Cardinals",
                            probability: 0,
                            renderedPercent: 0,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#97233F", initials: "ARI"),
                            settledOut: false
                        ),
                    ]
                ),
                MachineryMarketVisualItem(
                    marketId: 53681,
                    title: "AFC South",
                    outcomes: [
                        MachineryOutcomeVisual(
                            outcomeId: 21,
                            name: "Houston Texans",
                            probability: 0.57,
                            renderedPercent: 57,
                            unflooredPercent: 57,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#03202F", initials: "HOU"),
                            settledOut: false
                        ),
                        MachineryOutcomeVisual(
                            outcomeId: 22,
                            name: "Indianapolis Colts",
                            probability: 0.42,
                            renderedPercent: 42,
                            unflooredPercent: 42,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#002C5F", initials: "IND"),
                            settledOut: false
                        ),
                        MachineryOutcomeVisual(
                            outcomeId: 23,
                            name: "Jacksonville Jaguars",
                            probability: 0.005,
                            renderedPercent: 1,
                            unflooredPercent: 0,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#006778", initials: "JAX"),
                            settledOut: false
                        ),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(
                            outcomeId: 24,
                            name: "Tennessee Titans",
                            probability: 0,
                            renderedPercent: 0,
                            art: MachinerySubjectArt(kind: "monogram", accentColor: "#4B92DB", initials: "TEN"),
                            settledOut: true
                        ),
                    ]
                ),
            ]
        )

        return (discoverCard, hubBlock)
    }

    // MARK: - Renderers & Vision OCR Helpers

    private func renderIntrinsic<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        enforceWidthLimit: Bool = true
    ) -> UIImage {
        let bg = colorScheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
        let styled = view
            .frame(width: max(1, width - 32))
            .padding(16)
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: width)
            .background(bg)
            .ignoresSafeArea()
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)

        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let host = hostForMeasurement(styled, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)

        let initialSize = host.sizeThatFits(in: CGSize(width: width, height: 8000))
        let initialBounds = CGRect(origin: .zero, size: CGSize(width: width, height: max(120, ceil(initialSize.height) + 16)))

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: initialBounds)
        window.frame = initialBounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.frame = initialBounds
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 8000))
        if enforceWidthLimit {
            XCTAssertLessThanOrEqual(
                measured.width,
                width + 1.0,
                "Rendered content exceeded \(width) pt viewport width (\(measured.width) pt)"
            )
        }
        let finalBounds = CGRect(origin: .zero, size: CGSize(width: width, height: max(120, ceil(measured.height))))
        window.frame = finalBounds
        host.view.frame = finalBounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: finalBounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: finalBounds, afterScreenUpdates: true)
        }
    }

    private func renderIntrinsicInNavStack<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        enforceWidthLimit: Bool = true
    ) -> UIImage {
        let bg = colorScheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground)
        let styled = view
            .frame(width: max(1, width - 32))
            .padding(16)
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: width)
            .background(bg)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)

        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let measureHost = hostForMeasurement(styled, at: dynamicTypeSize)
        measureHost.overrideUserInterfaceStyle = uiStyle
        measureHost.additionalSafeAreaInsets = .zero
        measureHost.view.insetsLayoutMarginsFromSafeArea = false
        measureHost.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        measureHost.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)

        let measured = measureHost.sizeThatFits(in: CGSize(width: width, height: 8000))
        if enforceWidthLimit {
            XCTAssertLessThanOrEqual(
                measured.width,
                width + 1.0,
                "Rendered content exceeded \(width) pt viewport width (\(measured.width) pt)"
            )
        }
        let targetHeight = max(120, ceil(measured.height))
        let navWrapped = NavigationStack {
            styled
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(bg)
                .toolbar(.hidden, for: .navigationBar)
        }
        return renderFixedViewport(
            navWrapped,
            width: width,
            height: targetHeight,
            colorScheme: colorScheme,
            dynamicTypeSize: dynamicTypeSize
        )
    }

    private func renderFixedViewport<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLinesInPoints(in image: UIImage) throws -> [(text: String, heightPt: CGFloat)] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let s = obs.topCandidates(1).first?.string else { return nil }
            return (s, obs.boundingBox.height * image.size.height)
        }
    }

    private func lineHeightPt(_ lines: [(text: String, heightPt: CGFloat)], containing needle: String) -> CGFloat? {
        let matches = lines
            .filter { $0.text.localizedCaseInsensitiveContains(needle) }
            .map(\.heightPt)
        return matches.max()
    }

    private func maybeSave(_ image: UIImage, name: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["AX5_13662_RENDER_DIR"], !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    private func assertCleanText(
        _ lines: [(text: String, heightPt: CGFloat)],
        label: String,
        requiredTokens: [String],
        forbiddenSubstrings: [String],
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let joined = lines.map(\.text).joined(separator: " ")
        let normalizedJoined = joined.replacingOccurrences(of: "- ", with: "-")
        XCTAssertFalse(lines.isEmpty, "\(label): blank OCR", file: file, line: line)
        for bad in forbiddenSubstrings {
            XCTAssertFalse(
                joined.contains(bad),
                "\(label): found clipped/hyphenated '\(bad)' in OCR: \(joined)",
                file: file,
                line: line
            )
        }
        for tok in requiredTokens {
            XCTAssertTrue(
                joined.localizedCaseInsensitiveContains(tok) || normalizedJoined.localizedCaseInsensitiveContains(tok),
                "\(label): missing '\(tok)' in OCR: \(joined)",
                file: file,
                line: line
            )
        }
    }

    // MARK: - Deterministic UIFontMetrics Scaling Hierarchy + Ordinary Size Parity

    func testAX5FontScalingHierarchyIsUncapped() {
        let largeTraits = UITraitCollection(preferredContentSizeCategory: .large)
        let ax5Traits = UITraitCollection(preferredContentSizeCategory: .accessibilityExtraExtraExtraLarge)

        func scaled(_ value: CGFloat, style: UIFont.TextStyle, traits: UITraitCollection) -> CGFloat {
            UIFontMetrics(forTextStyle: style).scaledValue(for: value, compatibleWith: traits)
        }

        // 1. Checklist row title (.headline) must remain strictly larger than grey subtitle (.caption1) and exceed old 28 pt cap.
        let checklistTitleLarge = UIFont.preferredFont(forTextStyle: .headline, compatibleWith: largeTraits).pointSize
        let checklistTitleAX5 = UIFont.preferredFont(forTextStyle: .headline, compatibleWith: ax5Traits).pointSize
        let checklistSubAX5 = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: ax5Traits).pointSize
        XCTAssertGreaterThan(checklistTitleAX5, 28.0)
        XCTAssertGreaterThan(checklistTitleAX5, checklistSubAX5)
        XCTAssertGreaterThanOrEqual(checklistTitleAX5, checklistTitleLarge * 3.0)

        // 2. Discover division race card keeps master's base curves below AX and uses unified .headline + .title3 from AX1 up.
        let discoverDuelAX5 = scaled(21, style: .title3, traits: ax5Traits)
        let discoverTitleAX5 = scaled(17, style: .headline, traits: ax5Traits)
        let discoverRowAX5 = scaled(14, style: .headline, traits: ax5Traits)
        let discoverSubAX5 = scaled(12, style: .headline, traits: ax5Traits)
        let discoverKickerAX5 = max(scaled(11, style: .headline, traits: ax5Traits), 17.5)
        XCTAssertGreaterThan(discoverDuelAX5, discoverTitleAX5)
        XCTAssertGreaterThan(discoverTitleAX5, discoverRowAX5)
        XCTAssertGreaterThan(discoverRowAX5, discoverSubAX5)
        XCTAssertGreaterThan(discoverSubAX5, discoverKickerAX5)
        XCTAssertGreaterThan(discoverDuelAX5, 26.0)
        XCTAssertGreaterThan(discoverTitleAX5, 26.0)
        XCTAssertGreaterThan(discoverRowAX5, 22.0)
        XCTAssertGreaterThan(discoverSubAX5, 19.0)
        XCTAssertGreaterThan(discoverKickerAX5, 17.0)
        XCTAssertGreaterThanOrEqual(discoverTitleAX5, 17.0 * 2.75)
        XCTAssertGreaterThanOrEqual(discoverRowAX5, 14.0 * 2.75)

        // 3. Hub grid division race cards: compact phones keep 12-char words whole at 320 pt; regular iPad scales cleanly higher.
        let hubCompactTitleAX5 = MachineryDynamicTypeCurve13662.compactHubAXTitleSize(step: 5)
        let hubCompactRowAX5 = MachineryDynamicTypeCurve13662.compactHubAXRowSize(step: 5)
        XCTAssertGreaterThan(hubCompactTitleAX5, hubCompactRowAX5)
        XCTAssertGreaterThan(hubCompactTitleAX5, 22.0)
        XCTAssertGreaterThan(hubCompactRowAX5, 20.0)
        XCTAssertGreaterThanOrEqual(hubCompactTitleAX5, 14.0 * 2.25)
        XCTAssertGreaterThanOrEqual(hubCompactRowAX5, 13.0 * 2.25)

        let hubRegularTitleAX5 = max(scaled(14, style: .subheadline, traits: ax5Traits), hubCompactTitleAX5)
        let hubRegularRowAX5 = max(scaled(13, style: .subheadline, traits: ax5Traits), hubCompactRowAX5)
        XCTAssertGreaterThan(hubRegularTitleAX5, hubRegularRowAX5)
        XCTAssertGreaterThan(hubRegularTitleAX5, 22.0)
        XCTAssertGreaterThan(hubRegularRowAX5, 20.0)
        XCTAssertGreaterThanOrEqual(hubRegularTitleAX5, 14.0 * 2.5)
        XCTAssertGreaterThanOrEqual(hubRegularRowAX5, 13.0 * 2.5)
        XCTAssertGreaterThan(hubRegularTitleAX5, hubCompactTitleAX5)
        XCTAssertGreaterThan(hubRegularRowAX5, hubCompactRowAX5)
    }

    func testOrdinaryLargerSizesNeverShrinkBelowMasterAndGrowAcrossAXBoundary() throws {
        let levels: [(dt: DynamicTypeSize, ui: UIContentSizeCategory, label: String)] = [
            (.large, .large, "large"),
            (.xLarge, .extraLarge, "xLarge"),
            (.xxLarge, .extraExtraLarge, "xxLarge"),
            (.xxxLarge, .extraExtraExtraLarge, "xxxLarge"),
            (.accessibility1, .accessibilityMedium, "AX1"),
            (.accessibility2, .accessibilityLarge, "AX2"),
            (.accessibility3, .accessibilityExtraLarge, "AX3"),
            (.accessibility4, .accessibilityExtraExtraLarge, "AX4"),
            (.accessibility5, .accessibilityExtraExtraExtraLarge, "AX5"),
        ]

        func scaled(_ value: CGFloat, style: UIFont.TextStyle, cat: UIContentSizeCategory) -> CGFloat {
            let t = UITraitCollection(preferredContentSizeCategory: cat)
            return UIFontMetrics(forTextStyle: style).scaledValue(for: value, compatibleWith: t)
        }

        struct Sample {
            let showAll: CGFloat
            let kicker: CGFloat
            let title: CGFloat
            let row: CGFloat
            let sub: CGFloat
            let duelPct: CGFloat
            let hubCompactTitle: CGFloat
            let hubCompactRow: CGFloat
            let hubRegularTitle: CGFloat
            let hubRegularRow: CGFloat
        }

        var samples: [Sample] = []
        for entry in levels {
            let isAX = entry.dt.isAccessibilitySize
            let step = MachineryDynamicTypeCurve13662.accessibilityStepIndex(entry.dt) ?? 0

            let cap13 = scaled(13, style: .caption1, cat: entry.ui)
            let cap2_11 = scaled(11, style: .caption2, cat: entry.ui)
            let head17 = scaled(17, style: .headline, cat: entry.ui)
            let head14 = scaled(14, style: .headline, cat: entry.ui)
            let head12 = scaled(12, style: .headline, cat: entry.ui)
            let head11 = scaled(11, style: .headline, cat: entry.ui)
            let sub14 = scaled(14, style: .subheadline, cat: entry.ui)
            let sub13 = scaled(13, style: .subheadline, cat: entry.ui)
            let cap12 = scaled(12, style: .caption1, cat: entry.ui)
            let title3_21 = scaled(21, style: .title3, cat: entry.ui)

            let showAll = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: cap13, ordinaryCap: 20, axScaled: cap13, isAccessibilitySize: isAX)
            let kicker = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: cap2_11, ordinaryCap: 17, axScaled: max(head11, 17.5), isAccessibilitySize: isAX)
            let title = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: head17, ordinaryCap: 26, axScaled: head17, isAccessibilitySize: isAX)
            let row = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: sub14, ordinaryCap: 22, axScaled: head14, isAccessibilitySize: isAX)
            let sub = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: cap12, ordinaryCap: 19, axScaled: head12, isAccessibilitySize: isAX)
            let duelPct = MachineryDynamicTypeCurve13662.resolved(ordinaryScaled: title3_21, ordinaryCap: 26, axScaled: title3_21, isAccessibilitySize: isAX)

            let hubCompactTitle = isAX ? MachineryDynamicTypeCurve13662.compactHubAXTitleSize(step: step) : min(sub14, 22)
            let hubCompactRow = isAX ? MachineryDynamicTypeCurve13662.compactHubAXRowSize(step: step) : min(cap13, 20)
            let hubRegularTitle = isAX ? max(sub14, hubCompactTitle) : min(sub14, 22)
            let hubRegularRow = isAX ? max(sub13, hubCompactRow) : min(cap13, 20)

            print(String(format: "CURVE_13662 %@ show=%.1f kicker=%.1f sub=%.1f row=%.1f title=%.1f duel=%.1f hubC=(%.1f,%.1f) hubR=(%.1f,%.1f)", entry.label, showAll, kicker, sub, row, title, duelPct, hubCompactTitle, hubCompactRow, hubRegularTitle, hubRegularRow))

            // Master exact parity across ordinary sizes (.large .. .xxxLarge).
            if !isAX {
                XCTAssertEqual(showAll, min(cap13, 20), accuracy: 0.001, "\(entry.label) showAll")
                XCTAssertEqual(kicker, min(cap2_11, 17), accuracy: 0.001, "\(entry.label) kicker")
                XCTAssertEqual(title, min(head17, 26), accuracy: 0.001, "\(entry.label) title")
                XCTAssertEqual(row, min(sub14, 22), accuracy: 0.001, "\(entry.label) row")
                XCTAssertEqual(sub, min(cap12, 19), accuracy: 0.001, "\(entry.label) sub")
                XCTAssertEqual(duelPct, min(title3_21, 26), accuracy: 0.001, "\(entry.label) duelPct")
                XCTAssertEqual(hubCompactTitle, min(sub14, 22), accuracy: 0.001, "\(entry.label) hubCompactTitle")
                XCTAssertEqual(hubCompactRow, min(cap13, 20), accuracy: 0.001, "\(entry.label) hubCompactRow")
                XCTAssertEqual(hubRegularTitle, min(sub14, 22), accuracy: 0.001, "\(entry.label) hubRegularTitle")
                XCTAssertEqual(hubRegularRow, min(cap13, 20), accuracy: 0.001, "\(entry.label) hubRegularRow")
            } else {
                // Visual hierarchy preserved across all accessibility sizes.
                XCTAssertGreaterThan(duelPct, title, "\(entry.label): duelPct > title")
                XCTAssertGreaterThan(title, row, "\(entry.label): title > row")
                XCTAssertGreaterThan(row, sub, "\(entry.label): row > sub")
                XCTAssertGreaterThan(sub, kicker, "\(entry.label): sub > kicker")
                XCTAssertGreaterThan(hubCompactTitle, hubCompactRow, "\(entry.label): hubCompactTitle > row")
                XCTAssertGreaterThan(hubRegularTitle, hubRegularRow, "\(entry.label): hubRegularTitle > row")
            }

            samples.append(Sample(
                showAll: showAll, kicker: kicker, title: title, row: row, sub: sub, duelPct: duelPct,
                hubCompactTitle: hubCompactTitle, hubCompactRow: hubCompactRow,
                hubRegularTitle: hubRegularTitle, hubRegularRow: hubRegularRow
            ))
        }

        // Verify strictly non-decreasing across every step, and strictly growing at xxxLarge -> AX1 -> AX5.
        for i in 1..<samples.count {
            let prev = samples[i - 1], cur = samples[i]
            XCTAssertGreaterThanOrEqual(cur.showAll, prev.showAll)
            XCTAssertGreaterThanOrEqual(cur.kicker, prev.kicker)
            XCTAssertGreaterThanOrEqual(cur.title, prev.title)
            XCTAssertGreaterThanOrEqual(cur.row, prev.row)
            XCTAssertGreaterThanOrEqual(cur.sub, prev.sub)
            XCTAssertGreaterThanOrEqual(cur.duelPct, prev.duelPct)
            XCTAssertGreaterThanOrEqual(cur.hubCompactTitle, prev.hubCompactTitle)
            XCTAssertGreaterThanOrEqual(cur.hubCompactRow, prev.hubCompactRow)
            XCTAssertGreaterThanOrEqual(cur.hubRegularTitle, prev.hubRegularTitle)
            XCTAssertGreaterThanOrEqual(cur.hubRegularRow, prev.hubRegularRow)
        }

        let xxxl = samples[3]
        let ax1 = samples[4]
        let ax5 = samples[8]
        XCTAssertGreaterThan(ax1.showAll, xxxl.showAll)
        XCTAssertGreaterThan(ax1.kicker, xxxl.kicker)
        XCTAssertGreaterThan(ax1.title, xxxl.title)
        XCTAssertGreaterThan(ax1.row, xxxl.row)
        XCTAssertGreaterThan(ax1.sub, xxxl.sub)
        XCTAssertGreaterThan(ax1.duelPct, xxxl.duelPct)
        XCTAssertGreaterThan(ax1.hubCompactTitle, xxxl.hubCompactTitle)
        XCTAssertGreaterThan(ax1.hubCompactRow, xxxl.hubCompactRow)
        XCTAssertGreaterThan(ax1.hubRegularTitle, xxxl.hubRegularTitle)
        XCTAssertGreaterThan(ax1.hubRegularRow, xxxl.hubRegularRow)

        XCTAssertGreaterThan(ax5.showAll, ax1.showAll)
        XCTAssertGreaterThan(ax5.kicker, ax1.kicker)
        XCTAssertGreaterThan(ax5.title, ax1.title)
        XCTAssertGreaterThan(ax5.row, ax1.row)
        XCTAssertGreaterThan(ax5.sub, ax1.sub)
        XCTAssertGreaterThan(ax5.duelPct, ax1.duelPct)
        XCTAssertGreaterThan(ax5.hubCompactTitle, ax1.hubCompactTitle)
        XCTAssertGreaterThan(ax5.hubCompactRow, ax1.hubCompactRow)
        XCTAssertGreaterThan(ax5.hubRegularTitle, ax1.hubRegularTitle)
        XCTAssertGreaterThan(ax5.hubRegularRow, ax1.hubRegularRow)

        // Render-verify .xxxLarge at 390 pt Light on Discover division card & Hub grid.
        let suiteName = "xxxl-13662-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = nil
        let (discoverCard, hubBlock) = makeDivisionRaceFixtures()
        let bad = ["\u{2026}", "...", "Champion-", "Fran-"]

        let dImg = renderIntrinsic(
            MachineryDiscoverCardView(card: discoverCard, onOpenContainer: { _, _ in })
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager),
            width: 390,
            colorScheme: .light,
            dynamicTypeSize: .xxxLarge
        )
        let dOCR = try ocrLinesInPoints(in: dImg)
        assertCleanText(
            dOCR,
            label: "xxxl_discover_390",
            requiredTokens: ["Denver Broncos", "53%", "Kansas City Chiefs", "<1%", "Los Angeles Chargers", "No recent probability", "Las Vegas Raiders", "Eliminated"],
            forbiddenSubstrings: bad
        )

        let hImg = renderIntrinsicInNavStack(
            MachinerySectionBlockView(visualBlock: hubBlock, members: [], columnCount: 1)
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager),
            width: 390,
            colorScheme: .light,
            dynamicTypeSize: .xxxLarge
        )
        let hOCR = try ocrLinesInPoints(in: hImg)
        assertCleanText(
            hOCR,
            label: "xxxl_hub_390",
            requiredTokens: ["NFC West Championship", "San Francisco 49ers", "61%", "Seattle Seahawks", "<1%", "Arizona Cardinals", "No recent probability", "Tennessee Titans", "Eliminated"],
            forbiddenSubstrings: bad
        )
    }

    // MARK: - Capture + Uncapped Scaling Verification

    func testCaptureAndVerifyAX5UncappedScaling13662() throws {
        let env = ProcessInfo.processInfo.environment
        let prefix = (env["AX5_13662_CAPTURE_PREFIX"] ?? "after").trimmingCharacters(in: .whitespacesAndNewlines)
        let isBeforeCapture = prefix == "before"

        let suiteName = "ax5-13662-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = nil

        let checklistContent = makeChecklistContent()
        let partialChecklist = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: false
        )
        let (discoverRaceCard, hubRaceBlock) = makeDivisionRaceFixtures()

        // Measure .large baselines at 834 pt for growth assertions.
        let checklistLarge834 = renderFixedViewport(
            NavigationStack {
                FirstRunChecklistView364A(content: checklistContent, state: .constant(partialChecklist))
            }.environmentObject(authManager),
            width: 834,
            height: 760,
            colorScheme: .light,
            dynamicTypeSize: .large
        )
        try maybeSave(checklistLarge834, name: "\(prefix)_checklist_834_large")
        let checklistLargeOCR = try ocrLinesInPoints(in: checklistLarge834)
        let largeChecklistTitleH = try XCTUnwrap(
            lineHeightPt(checklistLargeOCR, containing: "anything"),
            "Missing 'anything' in checklistLargeOCR: \(checklistLargeOCR.map(\.text).joined(separator: " | "))"
        )

        let discoverLarge834 = renderIntrinsic(
            MachineryDiscoverCardView(
                card: discoverRaceCard,
                onOpenContainer: { _, _ in }
            )
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environmentObject(authManager),
            width: 834,
            colorScheme: .light,
            dynamicTypeSize: .large
        )
        try maybeSave(discoverLarge834, name: "\(prefix)_division_discover_834_large")
        let discoverLargeOCR = try ocrLinesInPoints(in: discoverLarge834)
        let largeDiscoverTitleH = try XCTUnwrap(
            lineHeightPt(discoverLargeOCR, containing: "Race"),
            "Missing 'Race' in discoverLargeOCR: \(discoverLargeOCR.map(\.text).joined(separator: " | "))"
        )
        let largeDiscoverRowH = try XCTUnwrap(
            lineHeightPt(discoverLargeOCR, containing: "Broncos"),
            "Missing 'Broncos' in discoverLargeOCR: \(discoverLargeOCR.map(\.text).joined(separator: " | "))"
        )

        let hubLargeCols = ContainerHubGridLayout13417.columnCount(
            horizontalSizeClass: .regular,
            dynamicTypeSize: .large,
            availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: 834)
        )
        let hubLarge834 = renderIntrinsicInNavStack(
            MachinerySectionBlockView(
                visualBlock: hubRaceBlock,
                members: [],
                columnCount: hubLargeCols
            )
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environmentObject(authManager),
            width: 834,
            colorScheme: .light,
            dynamicTypeSize: .large
        )
        try maybeSave(hubLarge834, name: "\(prefix)_division_hub_834_large")
        let hubLargeOCR = try ocrLinesInPoints(in: hubLarge834)
        let largeHubTitleH = try XCTUnwrap(
            lineHeightPt(hubLargeOCR, containing: "Championship"),
            "Missing 'Championship' in hubLargeOCR: \(hubLargeOCR.map(\.text).joined(separator: " | "))"
        )
        let largeHubRowH = try XCTUnwrap(
            lineHeightPt(hubLargeOCR, containing: "Francisco"),
            "Missing 'Francisco' in hubLargeOCR: \(hubLargeOCR.map(\.text).joined(separator: " | "))"
        )

        let variants: [(width: CGFloat, scheme: ColorScheme, schemeName: String, checklistH: CGFloat)] = [
            (320, .light, "light", 2680),
            (390, .light, "light", 2550),
            (834, .light, "light", 2050),
            (834, .dark, "dark", 2050),
        ]

        let commonBad = ["\u{2026}", "...", "any-", "ex-", "de-", "Champion-", "Fran-", "Char-", "Jack-", "Indi-", "Bron-", "Sea-", "Ten-"]

        for v in variants {
            // 1. Checklist
            let checklistImg = renderFixedViewport(
                NavigationStack {
                    FirstRunChecklistView364A(content: checklistContent, state: .constant(partialChecklist))
                }.environmentObject(authManager),
                width: v.width,
                height: v.checklistH,
                colorScheme: v.scheme,
                dynamicTypeSize: .accessibility5
            )
            try maybeSave(checklistImg, name: "\(prefix)_checklist_\(Int(v.width))_\(v.schemeName)")
            let checklistOCR = try ocrLinesInPoints(in: checklistImg)
            let cDump = checklistOCR.map(\.text).joined(separator: " | ")
            let titleHeights = ["anything", "Follow", "expects", "Keep", "heads"].compactMap {
                lineHeightPt(checklistOCR, containing: $0)
            }
            let subHeights = ["Search", "cities", "Pick", "Sign in", "swings"].compactMap {
                lineHeightPt(checklistOCR, containing: $0)
            }
            XCTAssertGreaterThanOrEqual(titleHeights.count, 4, "Missing checklist title tokens in \(cDump)")
            XCTAssertGreaterThanOrEqual(subHeights.count, 4, "Missing checklist subtitle tokens in \(cDump)")
            let cTitleMeanH = titleHeights.reduce(0, +) / CGFloat(max(1, titleHeights.count))
            let cSubMeanH = subHeights.reduce(0, +) / CGFloat(max(1, subHeights.count))
            print(String(format: "AX5_13662_METRICS %@ checklist_%d_%@ titleMean=%.1f subMean=%.1f titles=%@ subs=%@ largeTitle=%.1f", prefix, Int(v.width), v.schemeName, cTitleMeanH, cSubMeanH, titleHeights.map { String(format: "%.1f", $0) }.joined(separator: ","), subHeights.map { String(format: "%.1f", $0) }.joined(separator: ","), largeChecklistTitleH))

            if !isBeforeCapture {
                assertCleanText(
                    checklistOCR,
                    label: "checklist_\(Int(v.width))_\(v.schemeName)",
                    requiredTokens: ["Start anywhere", "Look anything up", "Search any game", "Follow what you care about", "Get a heads-up"],
                    forbiddenSubstrings: commonBad
                )
                XCTAssertGreaterThan(
                    cTitleMeanH,
                    cSubMeanH,
                    "Checklist title mean (\(cTitleMeanH) pt) must remain strictly larger than grey subtitle mean (\(cSubMeanH) pt) at \(Int(v.width)) \(v.schemeName)"
                )
                XCTAssertGreaterThanOrEqual(
                    cTitleMeanH,
                    largeChecklistTitleH * 2.0,
                    "AX5 checklist title mean (\(cTitleMeanH) pt) must scale >= 2.0x .large (\(largeChecklistTitleH) pt) at \(Int(v.width)) \(v.schemeName)"
                )
            }

            // 2. Discover division race card (onOpenContainer wired so card renders at full contrast)
            let discoverImg = renderIntrinsic(
                MachineryDiscoverCardView(
                    card: discoverRaceCard,
                    onOpenContainer: { _, _ in }
                )
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager),
                width: v.width,
                colorScheme: v.scheme,
                dynamicTypeSize: .accessibility5,
                enforceWidthLimit: !isBeforeCapture
            )
            try maybeSave(discoverImg, name: "\(prefix)_division_discover_\(Int(v.width))_\(v.schemeName)")
            let discoverOCR = try ocrLinesInPoints(in: discoverImg)
            let dDump = discoverOCR.map(\.text).joined(separator: " | ")
            let dTitleH = try XCTUnwrap(lineHeightPt(discoverOCR, containing: "Race"), "Missing 'Race' in \(dDump)")
            let dRowH = try XCTUnwrap(lineHeightPt(discoverOCR, containing: "Broncos"), "Missing 'Broncos' in \(dDump)")
            print(String(format: "AX5_13662_METRICS %@ discover_%d_%@ title=%.1f row=%.1f largeTitle=%.1f largeRow=%.1f", prefix, Int(v.width), v.schemeName, dTitleH, dRowH, largeDiscoverTitleH, largeDiscoverRowH))

            if !isBeforeCapture {
                assertCleanText(
                    discoverOCR,
                    label: "division_discover_\(Int(v.width))_\(v.schemeName)",
                    requiredTokens: ["Denver Broncos", "53%", "Kansas City Chiefs", "<1%", "Los Angeles Chargers", "No recent probability", "Las Vegas Raiders", "Eliminated"],
                    forbiddenSubstrings: commonBad
                )
                if v.width >= 390 {
                    XCTAssertGreaterThanOrEqual(dTitleH, dRowH, "Discover division title must be >= row size at \(Int(v.width)) \(v.schemeName)")
                    XCTAssertGreaterThanOrEqual(
                        dTitleH,
                        largeDiscoverTitleH * 2.0,
                        "Discover division title at AX5 (\(dTitleH) pt) must scale >= 2.0x .large (\(largeDiscoverTitleH) pt)"
                    )
                    XCTAssertGreaterThanOrEqual(
                        dRowH,
                        largeDiscoverRowH * 2.0,
                        "Discover division row at AX5 (\(dRowH) pt) must scale >= 2.0x .large (\(largeDiscoverRowH) pt)"
                    )
                }
            }

            // 3. Hub grid division race card inside NavigationStack so links render active
            let hubCols = ContainerHubGridLayout13417.columnCount(
                horizontalSizeClass: v.width >= 700 ? .regular : .compact,
                dynamicTypeSize: .accessibility5,
                availableWidth: ContainerHubGridLayout13417.innerContentWidth(containerWidth: v.width)
            )
            let hubImg = renderIntrinsicInNavStack(
                MachinerySectionBlockView(
                    visualBlock: hubRaceBlock,
                    members: [],
                    columnCount: hubCols
                )
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager),
                width: v.width,
                colorScheme: v.scheme,
                dynamicTypeSize: .accessibility5,
                enforceWidthLimit: !isBeforeCapture
            )
            try maybeSave(hubImg, name: "\(prefix)_division_hub_\(Int(v.width))_\(v.schemeName)")
            let hubOCR = try ocrLinesInPoints(in: hubImg)
            let hDump = hubOCR.map(\.text).joined(separator: " | ")
            let hTitleH = try XCTUnwrap(lineHeightPt(hubOCR, containing: "Championship"), "Missing 'Championship' in \(hDump)")
            let hRowH = try XCTUnwrap(lineHeightPt(hubOCR, containing: "Francisco"), "Missing 'Francisco' in \(hDump)")
            print(String(format: "AX5_13662_METRICS %@ hub_%d_%@ title=%.1f row=%.1f largeTitle=%.1f largeRow=%.1f", prefix, Int(v.width), v.schemeName, hTitleH, hRowH, largeHubTitleH, largeHubRowH))

            if !isBeforeCapture {
                assertCleanText(
                    hubOCR,
                    label: "division_hub_\(Int(v.width))_\(v.schemeName)",
                    requiredTokens: ["San Francisco", "49ers", "61%", "Seattle", "Seahawks", "<1%", "Arizona", "Cardinals", "No recent probability", "Tennessee", "Titans", "Eliminated"],
                    forbiddenSubstrings: commonBad
                )
                if v.width >= 390 {
                    XCTAssertGreaterThanOrEqual(hTitleH, hRowH, "Hub grid title must be >= row size at \(Int(v.width)) \(v.schemeName)")
                    let expectedMinScale: CGFloat = v.width >= 700 ? 2.0 : 1.6
                    XCTAssertGreaterThanOrEqual(
                        hTitleH,
                        largeHubTitleH * expectedMinScale,
                        "Hub grid title at AX5 (\(hTitleH) pt) must scale >= \(expectedMinScale)x .large (\(largeHubTitleH) pt)"
                    )
                    XCTAssertGreaterThanOrEqual(
                        hRowH,
                        largeHubRowH * expectedMinScale,
                        "Hub grid row at AX5 (\(hRowH) pt) must scale >= \(expectedMinScale)x .large (\(largeHubRowH) pt)"
                    )
                }
            }
        }
    }

    #endif
}
