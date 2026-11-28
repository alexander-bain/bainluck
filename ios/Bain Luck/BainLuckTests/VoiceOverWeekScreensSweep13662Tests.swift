import SwiftUI
#if os(iOS)
import UIKit
#endif
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class VoiceOverSweepTraitContainer13662: UIViewController {
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
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}
#endif

/// Item 6 (Refs #13662) — Live VoiceOver & spoken-number verification across this week's new screens
/// and probability surfaces, driven through UIKit's Accessibility Automation tree on the iOS Simulator
/// (`_AXSSetAutomationEnabled(1)`).
@MainActor
final class VoiceOverWeekScreensSweep13662Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-28T10:00:00Z")!

    #if os(iOS)
    private struct AXLeaf13662 {
        let label: String
        let value: String
        let hint: String
        let identifier: String
        let traits: UIAccessibilityTraits
        let frame: CGRect
    }

    override class func setUp() {
        super.setUp()
        setAutomation(true)
    }

    override class func tearDown() {
        setAutomation(false)
        super.tearDown()
    }

    private static func setAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
    }
    #endif

    // MARK: - 1. Spoken probability unit tests

    func testSpokenProbabilityTextAndSymbolExpansion() throws {
        XCTAssertEqual(spokenProbabilityText("<1%"), "less than 1 percent")
        XCTAssertEqual(spokenProbabilityText(">99%"), "more than 99 percent")
        XCTAssertEqual(spokenProbabilityText("0%"), "0 percent")
        XCTAssertEqual(spokenProbabilityText("53%"), "53 percent")
        XCTAssertEqual(spokenProbabilityText("100%"), "100 percent")
        XCTAssertEqual(spokenProbabilityText("—"), "No recent probability")
        XCTAssertEqual(spokenProbabilityText("No recent probability"), "No recent probability")
        XCTAssertEqual(spokenProbabilityText("No probability yet"), "No probability yet")
        XCTAssertEqual(spokenProbabilityText("Eliminated"), "Eliminated")
        XCTAssertEqual(spokenProbabilityText("   "), "")

        XCTAssertEqual(
            spokenTextExpandingProbabilitySymbols("Ravens <1% · Chiefs >99% · Bills 52%"),
            "Ravens less than 1 percent · Chiefs more than 99 percent · Bills 52 percent"
        )
        XCTAssertEqual(
            spokenTextExpandingProbabilitySymbols("Last recorded 0.996 → >99% and <1%"),
            "Last recorded 0.996 → more than 99 percent and less than 1 percent"
        )

        let contract = FeedRoundupContract(
            kicker: "TEST",
            footer: "Footer",
            rows: [
                FeedRoundupRow(marketId: 1, label: "Favorite", probability: 0.996, renderedPercent: 100),
                FeedRoundupRow(marketId: 2, label: "Contender", probability: 0.01, renderedPercent: 1),
                FeedRoundupRow(marketId: 3, label: "Underdog", probability: 0.004, renderedPercent: 0),
            ]
        )
        let built = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "Test", contract: contract, now: fixedNow))
        XCTAssertEqual(built.rows.map(\.spokenPercentText), ["more than 99 percent", "1 percent", "less than 1 percent"])
    }

    #if os(iOS)
    // MARK: - Live UIKit AX Tree Helpers

    private func collectAccessibilityLeaves<V: View>(
        view: V,
        width: CGFloat,
        height: CGFloat,
        dynamicType: DynamicTypeSize = .large,
        horizontalSizeClass: UserInterfaceSizeClass = .compact,
        pinManager: PinManager? = nil,
        authManager: AuthManager? = nil,
        navCoordinator: NavigationCoordinator? = nil
    ) async -> [AXLeaf13662] {
        let resolvedPinManager = pinManager ?? PinManager(
            defaults: UserDefaults(suiteName: "vo-13662-default")!,
            allowLegacyGuestPins: false
        )
        let resolvedAuthManager = authManager ?? AuthManager(restoreOnInit: false)
        let resolvedNavCoordinator = navCoordinator ?? NavigationCoordinator()
        let uiSizeClass: UIUserInterfaceSizeClass = horizontalSizeClass == .compact ? .compact : .regular
        let uiCategory: UIContentSizeCategory = dynamicType.isAccessibilitySize ? .accessibilityExtraExtraExtraLarge : .large
        let wrapped = NavigationStack {
            view
                .toolbar(.hidden, for: .navigationBar)
        }
        .frame(width: width, height: height, alignment: .topLeading)
        .environment(\.horizontalSizeClass, horizontalSizeClass)
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, dynamicType)
        .environmentObject(resolvedNavCoordinator)
        .environmentObject(resolvedPinManager)
        .environmentObject(resolvedAuthManager)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: uiSizeClass),
            UITraitCollection(userInterfaceStyle: .light),
            UITraitCollection(preferredContentSizeCategory: uiCategory),
        ])
        let host = hostForMeasurement(wrapped, at: dynamicType)
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        let container = VoiceOverSweepTraitContainer13662(child: host, traits: traits)
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<18 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 45_000_000)
        }

        var leaves: [AXLeaf13662] = []
        var visited = Set<ObjectIdentifier>()

        func resolvedIdentifier(for node: NSObject) -> String {
            if let ax = node as? UIAccessibilityIdentification, let aid = ax.accessibilityIdentifier, !aid.isEmpty {
                return aid
            }
            let sel = NSSelectorFromString("accessibilityIdentifier")
            if node.responds(to: sel), let raw = node.perform(sel)?.takeUnretainedValue() as? String {
                return raw
            }
            return ""
        }

        func leafInfo(for node: NSObject) -> AXLeaf13662? {
            let label = (node.accessibilityLabel ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let value = (node.accessibilityValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let hint = (node.accessibilityHint ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let identifier = resolvedIdentifier(for: node).trimmingCharacters(in: .whitespacesAndNewlines)
            let traits = node.accessibilityTraits
            let frame = node.accessibilityFrame
            guard node.isAccessibilityElement || !label.isEmpty || !value.isEmpty else { return nil }
            return AXLeaf13662(
                label: label,
                value: value,
                hint: hint,
                identifier: identifier,
                traits: traits,
                frame: frame
            )
        }

        func walk(_ node: NSObject) {
            let oid = ObjectIdentifier(node)
            guard !visited.contains(oid) else { return }
            visited.insert(oid)

            if node.accessibilityElementsHidden {
                return
            }

            if node.isAccessibilityElement {
                if let info = leafInfo(for: node) {
                    leaves.append(info)
                }
                return
            }

            if let elements = node.accessibilityElements as? [NSObject], !elements.isEmpty {
                for el in elements { walk(el) }
                return
            }
            let count = node.accessibilityElementCount()
            if count != NSNotFound, count > 0 {
                for i in 0..<count {
                    if let el = node.accessibilityElement(at: i) as? NSObject {
                        walk(el)
                    }
                }
                return
            }
            if let v = node as? UIView {
                for sub in v.subviews { walk(sub) }
            }
        }

        walk(container.view)
        return leaves
    }

    private func assertTopToBottomOrder(
        _ leaves: [AXLeaf13662],
        tolerance: CGFloat = 6.0,
        context: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let positioned = leaves.filter { !$0.frame.isNull && !$0.frame.isEmpty && $0.frame.height > 0 }
        XCTAssertFalse(positioned.isEmpty, "\(context): expected positioned accessibility elements", file: file, line: line)
        var currentBand: CGRect?
        for leaf in positioned {
            guard let band = currentBand else {
                currentBand = leaf.frame
                continue
            }
            let overlapsCurrentBand =
                leaf.frame.minY <= band.maxY - 1.0 && leaf.frame.maxY >= band.minY + 1.0
            if overlapsCurrentBand {
                currentBand = CGRect(
                    x: min(band.minX, leaf.frame.minX),
                    y: min(band.minY, leaf.frame.minY),
                    width: max(band.maxX, leaf.frame.maxX) - min(band.minX, leaf.frame.minX),
                    height: max(band.maxY, leaf.frame.maxY) - min(band.minY, leaf.frame.minY)
                )
            } else {
                if leaf.frame.minY + tolerance < band.maxY {
                    XCTFail(
                        "\(context): VoiceOver focus jumped backwards at '\(leaf.label)' (minY=\(leaf.frame.minY), prevBand=[\(band.minY), \(band.maxY)])",
                        file: file,
                        line: line
                    )
                }
                currentBand = leaf.frame
            }
        }
    }

    private func assertNoRawProbabilitySymbolsOrLeaks(
        _ leaves: [AXLeaf13662],
        forbiddenTokens: [String] = [],
        context: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for leaf in leaves {
            XCTAssertFalse(
                leaf.label.isEmpty && leaf.traits.contains(.button),
                "\(context): unnamed button id='\(leaf.identifier)' frame=\(leaf.frame)",
                file: file,
                line: line
            )
            XCTAssertFalse(
                leaf.label.contains("<1%") || leaf.label.contains(">99%"),
                "\(context): raw probability symbol leaked in AX label: '\(leaf.label)'",
                file: file,
                line: line
            )
            XCTAssertFalse(
                leaf.label.contains("\u{2192}"),
                "\(context): literal arrow leaked in AX label: '\(leaf.label)'",
                file: file,
                line: line
            )
            for forbidden in forbiddenTokens where leaf.label == forbidden {
                XCTFail("\(context): decorative token '\(forbidden)' leaked into VoiceOver tree", file: file, line: line)
            }
        }
    }

    // MARK: - 2. Division race cards (MachineryDiscoverCardView + ActionBar)

    func testDivisionRaceCardVoiceOverAtPhoneAndIPadAndAX5() async throws {
        let suiteName = "vo-div-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        let card = MachineryCardContract(
            slug: "machinery-afc-west-duel",
            formId: .siblingFieldsGrid,
            kicker: "AFC WEST",
            title: "AFC West Title Race",
            subtitle: "All four AFC West teams in the division title race.",
            footer: "See all 4 divisions",
            scaleOrdered: false,
            sectionCount: 2,
            outcomeRows: [
                MachineryOutcomeVisual(
                    outcomeId: 846594,
                    marketId: 53675,
                    name: "Denver Broncos",
                    probability: 0.62,
                    renderedPercent: 62,
                    unflooredPercent: 62,
                    art: MachinerySubjectArt(kind: "monogram", accentColor: "#FB4F14", initials: "DEN"),
                    settledOut: false
                ),
                MachineryOutcomeVisual(
                    outcomeId: 846593,
                    marketId: 53675,
                    name: "Kansas City Chiefs",
                    probability: 0.004,
                    renderedPercent: 0,
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

        let action = DiscoverCardLikeAction420D(
            itemKey: "bundle-afc-west",
            isLiked: false,
            pinType: "future",
            pinId: 53675,
            shareURL: URL(string: "https://bainluck.com/collections/afc-west"),
            shareTitle: "AFC West Title Race",
            shareMessage: "Denver Broncos lead at 62%",
            onToggle: {},
            onShare: {}
        )

        let configs: [(name: String, width: CGFloat, height: CGFloat, dt: DynamicTypeSize, hsc: UserInterfaceSizeClass)] = [
            ("phone_large_390", 390, 900, .large, .compact),
            ("phone_ax5_390", 390, 1500, .accessibility5, .compact),
            ("ipad_large_834", 834, 900, .large, .regular),
        ]

        for cfg in configs {
            let leaves = await collectAccessibilityLeaves(
                view: MachineryDiscoverCardView(card: card, onOpenContainer: { _, _ in })
                    .environment(\.discoverCardLikeAction420D, action)
                    .padding(16),
                width: cfg.width,
                height: cfg.height,
                dynamicType: cfg.dt,
                horizontalSizeClass: cfg.hsc,
                pinManager: pinManager
            )
            let labels = leaves.map(\.label)
            print("VO_DIV_\(cfg.name): \(labels)")

            assertNoRawProbabilitySymbolsOrLeaks(
                leaves,
                forbiddenTokens: ["DEN", "KC", "LAC", "LV"],
                context: "DivisionCard_\(cfg.name)"
            )
            assertTopToBottomOrder(leaves, context: "DivisionCard_\(cfg.name)")

            let joined = labels.joined(separator: " | ")
            XCTAssertTrue(joined.contains("AFC West Title Race"), "\(cfg.name): missing card title in \(joined)")
            XCTAssertTrue(joined.contains("62 percent"), "\(cfg.name): expected '62 percent' in \(joined)")
            XCTAssertTrue(joined.contains("less than 1 percent"), "\(cfg.name): expected 'less than 1 percent' in \(joined)")
            XCTAssertTrue(joined.contains("No recent probability"), "\(cfg.name): expected 'No recent probability' in \(joined)")
            XCTAssertTrue(joined.contains("Eliminated"), "\(cfg.name): expected 'Eliminated' in \(joined)")
            XCTAssertTrue(labels.contains("Like"), "\(cfg.name): missing Like button in \(labels)")
            XCTAssertTrue(labels.contains("Pin") || labels.contains("Unpin"), "\(cfg.name): missing Pin button in \(labels)")
            XCTAssertTrue(labels.contains("Share"), "\(cfg.name): missing Share button in \(labels)")

            let cardIdx = try XCTUnwrap(labels.firstIndex(where: { $0.contains("AFC West Title Race") }))
            let likeIdx = try XCTUnwrap(labels.firstIndex(of: "Like"))
            let shareIdx = try XCTUnwrap(labels.firstIndex(of: "Share"))
            XCTAssertLessThan(cardIdx, likeIdx, "\(cfg.name): card must precede action bar")
            XCTAssertLessThan(likeIdx, shareIdx, "\(cfg.name): Like must precede Share")
        }
    }

    // MARK: - 3. Usage-stats prompt, checklist, banner & Preferences toggle

    func testUsageStatsPromptChecklistAndPreferencesVoiceOver() async throws {
        let suiteName = "vo-usage-checklist-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        // 3a. TelemetryConsentPrompt (large + AX5)
        for dt: DynamicTypeSize in [.large, .accessibility5] {
            let leaves = await collectAccessibilityLeaves(
                view: TelemetryConsentPrompt { _ in },
                width: 390,
                height: dt.isAccessibilitySize ? 1900 : 844,
                dynamicType: dt,
                pinManager: pinManager
            )
            let labels = leaves.map(\.label)
            print("VO_CONSENT_\(dt): \(labels)")

            assertNoRawProbabilitySymbolsOrLeaks(leaves, context: "TelemetryConsent_\(dt)")
            assertTopToBottomOrder(leaves, context: "TelemetryConsent_\(dt)")

            let heading = try XCTUnwrap(leaves.first(where: { $0.label.contains("Help us find what") }))
            XCTAssertTrue(heading.traits.contains(.header), "Consent heading must carry .header trait at \(dt)")
            XCTAssertTrue(labels.contains("Allow"))
            XCTAssertTrue(labels.contains("No thanks"))
            let allowIdx = try XCTUnwrap(labels.firstIndex(of: "Allow"))
            let declineIdx = try XCTUnwrap(labels.firstIndex(of: "No thanks"))
            let headingIdx = try XCTUnwrap(leaves.firstIndex(where: { $0.label.contains("Help us find what") }))
            XCTAssertLessThan(headingIdx, allowIdx)
            XCTAssertLessThan(allowIdx, declineIdx)
        }

        // 3b. FirstRunChecklistView364A (partial & allDone, large + AX5)
        let content = makeMinimalChecklistContent()
        let partial = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: false
        )
        for dt: DynamicTypeSize in [.large, .accessibility5] {
            let partialLeaves = await collectAccessibilityLeaves(
                view: FirstRunChecklistView364A(content: content, state: .constant(partial)),
                width: 390,
                height: dt.isAccessibilitySize ? 2400 : 844,
                dynamicType: dt,
                pinManager: pinManager
            )
            print("VO_CHECKLIST_PARTIAL_\(dt): \(partialLeaves.map { "\($0.identifier):\($0.label)[\($0.value)]" })")
            assertNoRawProbabilitySymbolsOrLeaks(partialLeaves, context: "ChecklistPartial_\(dt)")
            assertTopToBottomOrder(partialLeaves, context: "ChecklistPartial_\(dt)")

            XCTAssertTrue(partialLeaves.contains(where: { $0.label == "Start anywhere" && $0.traits.contains(.header) }))
            let completedValues = partialLeaves.filter { $0.value == "Completed" }
            let pendingValues = partialLeaves.filter { $0.value == "Not started" }
            XCTAssertEqual(completedValues.count, 2, "Expected 2 Completed rows at \(dt)")
            XCTAssertEqual(pendingValues.count, 3, "Expected 3 Not started rows at \(dt)")
            XCTAssertTrue(partialLeaves.contains(where: { $0.identifier == "checklist364A.skipButton" }))

            let doneLeaves = await collectAccessibilityLeaves(
                view: FirstRunChecklistView364A(content: content, state: .constant(.allDone)),
                width: 390,
                height: dt.isAccessibilitySize ? 2400 : 844,
                dynamicType: dt,
                pinManager: pinManager
            )
            assertNoRawProbabilitySymbolsOrLeaks(doneLeaves, context: "ChecklistDone_\(dt)")
            let goButton = try XCTUnwrap(doneLeaves.first(where: { $0.identifier == "checklist364A.goToDiscoverButton" }))
            XCTAssertEqual(goButton.label, "Go to Discover")
        }

        // 3c. MyStuffChecklistBanner364A
        let bannerLeaves = await collectAccessibilityLeaves(
            view: ScrollView {
                MyStuffChecklistBanner364A(state: .constant(partial))
                    .padding(16)
            },
            width: 390,
            height: 1200,
            dynamicType: .accessibility5,
            pinManager: pinManager
        )
        assertNoRawProbabilitySymbolsOrLeaks(bannerLeaves, context: "MyStuffChecklistBanner")
        assertTopToBottomOrder(bannerLeaves, context: "MyStuffChecklistBanner")
        XCTAssertTrue(bannerLeaves.contains(where: { $0.label.contains("Getting started") && $0.traits.contains(.header) }))
        XCTAssertTrue(bannerLeaves.contains(where: { $0.label == "Dismiss checklist" }))
        XCTAssertEqual(bannerLeaves.filter { $0.value == "Completed" }.count, 2)
        XCTAssertEqual(bannerLeaves.filter { $0.value == "Not started" }.count, 3)

        // 3d. PreferencesView (usage-stats switch + App icon row)
        let prefs = PreferencesResponse(
            homeLocation: "Boston",
            sportAffinities: ["nfl": 1.0],
            onboardingCompleted: true,
            favorites: []
        )
        for dt: DynamicTypeSize in [.large, .accessibility5] {
            let prefsLeaves = await collectAccessibilityLeaves(
                view: PreferencesView(loadedPrefsForTest: prefs),
                width: 390,
                height: dt.isAccessibilitySize ? 2600 : 1800,
                dynamicType: dt,
                pinManager: pinManager
            )
            print("VO_PREFS_\(dt): \(prefsLeaves.map { "\($0.identifier):\($0.label)=\($0.value)" })")
            assertNoRawProbabilitySymbolsOrLeaks(prefsLeaves, context: "Preferences_\(dt)")
            assertTopToBottomOrder(prefsLeaves, context: "Preferences_\(dt)")

            let appIconRow = try XCTUnwrap(
                prefsLeaves.first(where: { $0.identifier == "preferences.appIconRow" }),
                "Missing preferences.appIconRow at \(dt)"
            )
            XCTAssertEqual(appIconRow.label, "App icon")
            XCTAssertFalse(appIconRow.value.isEmpty, "App icon row must expose current icon name in value at \(dt)")
            XCTAssertEqual(appIconRow.hint, "Choose an app icon")

            XCTAssertTrue(
                prefsLeaves.contains(where: { $0.label.contains("Share usage analytics") }),
                "Missing 'Share usage analytics' switch at \(dt)"
            )
        }
    }

    // MARK: - 4. App Icon Picker

    func testAppIconPickerVoiceOverAtLargeAndAX5() async throws {
        let switcher = AppIconSwitcher423A(
            supportsAlternateIcons: { true },
            currentIconName: { "AppIconWinter" },
            setIconName: { _ in }
        )

        for dt: DynamicTypeSize in [.large, .accessibility5] {
            let leaves = await collectAccessibilityLeaves(
                view: AppIconPickerView423A(switcher: switcher),
                width: 390,
                height: dt.isAccessibilitySize ? 1200 : 700,
                dynamicType: dt
            )
            print("VO_ICON_PICKER_\(dt): \(leaves.map { "\($0.label)[\($0.traits.contains(.selected) ? "SELECTED" : "")]" })")
            assertNoRawProbabilitySymbolsOrLeaks(leaves, context: "AppIconPicker_\(dt)")
            assertTopToBottomOrder(leaves, context: "AppIconPicker_\(dt)")

            let originalRow = try XCTUnwrap(leaves.first(where: { $0.identifier == "appIconPicker.option.original" }))
            let winterRow = try XCTUnwrap(leaves.first(where: { $0.identifier == "appIconPicker.option.winter" }))
            let nyeRow = try XCTUnwrap(leaves.first(where: { $0.identifier == "appIconPicker.option.newYearsEve" }))

            XCTAssertEqual(originalRow.label, AppIconChoice423A.original.displayName)
            XCTAssertEqual(winterRow.label, AppIconChoice423A.winter.displayName)
            XCTAssertEqual(nyeRow.label, AppIconChoice423A.newYearsEve.displayName)
            XCTAssertTrue(winterRow.traits.contains(.selected), "Active Winter row must carry .selected trait at \(dt)")
            XCTAssertFalse(originalRow.traits.contains(.selected))
            XCTAssertFalse(nyeRow.traits.contains(.selected))
        }
    }

    // MARK: - 5. Like Heart & Sibling Card Controls

    func testLikeHeartFuturesAndEventCardVoiceOver() async throws {
        let suiteName = "vo-like-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase

        // 5a. Standalone DiscoverLikeButton420D (unliked & liked)
        let unlikedLeaves = await collectAccessibilityLeaves(
            view: DiscoverLikeButton420D(isLiked: false, action: {}).padding(16),
            width: 320,
            height: 200,
            pinManager: pinManager
        )
        let unlikedBtn = try XCTUnwrap(unlikedLeaves.first(where: { $0.identifier == "discover.card.likeButton" }))
        XCTAssertEqual(unlikedBtn.label, "Like")
        XCTAssertEqual(unlikedBtn.hint, "Likes this card")
        XCTAssertFalse(unlikedBtn.traits.contains(.selected))

        let likedLeaves = await collectAccessibilityLeaves(
            view: DiscoverLikeButton420D(isLiked: true, action: {}).padding(16),
            width: 320,
            height: 200,
            pinManager: pinManager
        )
        let likedBtn = try XCTUnwrap(likedLeaves.first(where: { $0.identifier == "discover.card.likeButton" }))
        XCTAssertEqual(likedBtn.label, "Liked")
        XCTAssertEqual(likedBtn.hint, "Takes back your like")
        XCTAssertTrue(likedBtn.traits.contains(.selected))

        let futuresData = try dec.decode(FeedFuturesData.self, from: Data("""
        {
          "id": 9901,
          "name": "Who will win the championship?",
          "llm_sport_category": "basketball",
          "source": "kalshi",
          "status": "open",
          "top_outcomes": [
            {"id": 1, "name": "Leader High", "probability": 0.996, "rendered_percent": 100, "rank": 1},
            {"id": 2, "name": "Longshot", "probability": 0.004, "rendered_percent": 0, "rank": 2}
          ],
          "outcome_count": 2
        }
        """.utf8))

        let likeAction = DiscoverCardLikeAction420D(
            itemKey: "futures-9901",
            isLiked: true,
            pinType: "future",
            pinId: 9901,
            shareURL: URL(string: "https://bainluck.com/futures/9901"),
            shareTitle: "Championship",
            shareMessage: "Leader High at >99%",
            onToggle: {},
            onShare: {}
        )

        // 5b. NativeFuturesDiscoverCard (action bar + >99% / <1% speech)
        let futuresLeaves = await collectAccessibilityLeaves(
            view: NativeFuturesDiscoverCard(
                data: futuresData,
                feedContext: "Contenders separated early.",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
            .environment(\.discoverCardLikeAction420D, likeAction)
            .padding(16),
            width: 390,
            height: 900,
            pinManager: pinManager
        )
        let futuresLabels = futuresLeaves.map(\.label)
        print("VO_FUTURES_CARD: \(futuresLabels)")
        assertNoRawProbabilitySymbolsOrLeaks(futuresLeaves, context: "NativeFuturesDiscoverCard")
        assertTopToBottomOrder(futuresLeaves, context: "NativeFuturesDiscoverCard")
        let futuresJoined = futuresLabels.joined(separator: " | ")
        XCTAssertTrue(futuresJoined.contains("more than 99 percent"), "Expected spoken >99% in \(futuresJoined)")
        XCTAssertTrue(futuresJoined.contains("less than 1 percent"), "Expected spoken <1% in \(futuresJoined)")
        XCTAssertTrue(futuresLabels.contains("Liked"))
        XCTAssertTrue(futuresLabels.contains("Pin") || futuresLabels.contains("Unpin"))
        XCTAssertTrue(futuresLabels.contains("Share"))
        let futuresTitleIdx = try XCTUnwrap(futuresLabels.firstIndex(where: { $0.contains("Who will win the championship?") }))
        let futuresLikeIdx = try XCTUnwrap(futuresLabels.firstIndex(of: "Liked"))
        XCTAssertLessThan(futuresTitleIdx, futuresLikeIdx)

        // 5c. NativeEventDiscoverCard (action bar + <1% / >99% speech)
        let eventData = try dec.decode(FeedEventData.self, from: Data("""
        {
          "id": 9902,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Kansas City Chiefs",
          "away_team": "New York Jets",
          "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
          "away_team_data": {"team_id": 20, "name": "New York Jets", "short_name": "Jets", "abbreviation": "NYJ", "primary_color": "#125740"},
          "commence_time": "2026-11-28T09:30:00Z",
          "status": "live",
          "home_score": 28,
          "away_score": 0,
          "espn": {"period": "Q4", "clock": "2:00"},
          "current_odds": {"home_probability": 0.996, "away_probability": 0.004}
        }
        """.utf8))

        let eventLeaves = await collectAccessibilityLeaves(
            view: NativeEventDiscoverCard(
                event: eventData,
                feedContext: "One-sided fourth quarter.",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
            .environment(\.discoverCardLikeAction420D, likeAction)
            .padding(16),
            width: 390,
            height: 900,
            pinManager: pinManager
        )
        let eventLabels = eventLeaves.map(\.label)
        print("VO_EVENT_CARD: \(eventLabels)")
        assertNoRawProbabilitySymbolsOrLeaks(eventLeaves, context: "NativeEventDiscoverCard")
        assertTopToBottomOrder(eventLeaves, context: "NativeEventDiscoverCard")
        let eventJoined = eventLabels.joined(separator: " | ")
        XCTAssertTrue(eventJoined.contains("less than 1 percent"), "Expected spoken <1% on event card: \(eventJoined)")
        XCTAssertTrue(eventJoined.contains("more than 99 percent"), "Expected spoken >99% on event card: \(eventJoined)")
        XCTAssertTrue(eventLabels.contains("Liked"))
        XCTAssertTrue(eventLabels.contains("Pin") || eventLabels.contains("Unpin"))
        XCTAssertTrue(eventLabels.contains("Share"))
    }

    // MARK: - 6. Sub-1%, >99%, & No recent probability across remaining surfaces

    func testRoundupProbabilityNumberHeadlineAndDistributionVoiceOver() async throws {
        let suiteName = "vo-prob-surfaces-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        // 6a. DiscoverRoundupCardView (both hasAnySourceMark == false and true)
        for hasSourceMark in [false, true] {
            let mark: SourceMark? = hasSourceMark
                ? SourceMark(
                    state: .single,
                    sources: [.init(key: "kalshi", name: "Kalshi", probability: 0.996, observedAt: nil)],
                    method: "Single source"
                )
                : nil
            let contract = FeedRoundupContract(
                kicker: "EXTREMES",
                subtitle: "Boundaries",
                completeGroup: true,
                footer: "3 candidates",
                order: "probability",
                rows: [
                    FeedRoundupRow(marketId: 1, label: "Heavy Favorite", probability: 0.996, renderedPercent: 100, sourceMark: mark),
                    FeedRoundupRow(marketId: 2, label: "Mid Contender", probability: 0.25, renderedPercent: 25, sourceMark: mark),
                    FeedRoundupRow(marketId: 3, label: "Longshot", probability: 0.004, renderedPercent: 0, sourceMark: mark),
                ]
            )
            let model = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "Roundup Boundary VoiceOver", contract: contract, now: fixedNow))
            let ref = try XCTUnwrap(FeedThemeCollectionRef(slug: "roundup-vo", name: "Extremes", revision: 1, collectionCount: 2))

            let leaves = await collectAccessibilityLeaves(
                view: DiscoverRoundupCardView(model: model, collectionRef: ref, now: fixedNow, onOpenCollection: { _ in })
                    .padding(16),
                width: 390,
                height: 700,
                pinManager: pinManager
            )
            let labels = leaves.map(\.label)
            print("VO_ROUNDUP_mark=\(hasSourceMark): \(labels)")
            assertNoRawProbabilitySymbolsOrLeaks(leaves, context: "DiscoverRoundup_mark=\(hasSourceMark)")
            assertTopToBottomOrder(leaves, context: "DiscoverRoundup_mark=\(hasSourceMark)")

            let joined = labels.joined(separator: " | ")
            XCTAssertTrue(joined.contains("more than 99 percent"), "mark=\(hasSourceMark): expected spoken >99% in \(joined)")
            XCTAssertTrue(joined.contains("less than 1 percent"), "mark=\(hasSourceMark): expected spoken <1% in \(joined)")
        }

        // 6b. ProbabilityNumber
        let probLeaves = await collectAccessibilityLeaves(
            view: VStack(alignment: .leading, spacing: 12) {
                ProbabilityNumber(value: 0.4, renderedPercent: 0)
                ProbabilityNumber(value: 99.6, renderedPercent: 100)
            }
            .padding(16),
            width: 320,
            height: 300,
            pinManager: pinManager
        )
        print("VO_PROB_NUMBER: \(probLeaves.map(\.label))")
        assertNoRawProbabilitySymbolsOrLeaks(probLeaves, context: "ProbabilityNumber")
        XCTAssertEqual(probLeaves.map(\.label), ["less than 1 percent", "100 percent"])

        // 6c. EventSportHeadlineCard12472 (live soccer with <1%, >99%, and missing draw away cell)
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let soccerWithheldJSON = """
        {
          "id": 9903,
          "sport": "soccer_epl",
          "sport_name": "EPL",
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "commence_time": "2026-11-28T08:40:00Z",
          "start_is_tbd": false,
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "home_team_data": {"abbreviation": "ARS", "primary_color": "#EF0107"},
          "away_team_data": {"abbreviation": "CHE", "primary_color": "#144992"},
          "espn": {"period": "2nd Half", "game_clock": "67'"},
          "current_odds": {
            "captured_at": "2026-11-28T09:59:30Z",
            "home_probability": 0.996,
            "away_probability": 0.004,
            "draw_probability": null
          },
          "hero_probability": 0.996,
          "hero_probability_source": "kalshi",
          "hero_probability_observed_at": "2026-11-28T09:59:30Z"
        }
        """
        let soccerDetail = try dec.decode(EventDetail.self, from: Data(soccerWithheldJSON.utf8))
        let headlineModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: soccerDetail,
                awayFullName: soccerDetail.awayTeam,
                homeFullName: soccerDetail.homeTeam,
                liveStatusText: "67'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        let headlineLeaves = await collectAccessibilityLeaves(
            view: EventSportHeadlineCard12472(
                model: headlineModel,
                colors: (away: .blue, home: .red),
                ekgTracker: .empty,
                liveUpdateStatus: .hidden,
                displayAsOf: fixedNow,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: nil,
                confirmedAt: nil,
                revealForecast: nil
            )
            .padding(16),
            width: 390,
            height: 600,
            pinManager: pinManager
        )
        print("VO_HEADLINE_CARD: \(headlineLeaves.map(\.label))")
        assertNoRawProbabilitySymbolsOrLeaks(headlineLeaves, context: "EventSportHeadlineCard12472")
        let headlineJoined = headlineLeaves.map(\.label).joined(separator: " | ")
        XCTAssertTrue(headlineJoined.contains("No recent probability"), "Expected 'No recent probability' in \(headlineJoined)")
        XCTAssertTrue(headlineJoined.contains("more than 99 percent"), "Expected 'more than 99 percent' in \(headlineJoined)")

        // 6d. DistributionCardView (<1%, >99%)
        let distData = FeedFuturesData(
            id: 9904,
            name: "Best Picture Boundaries",
            sport: nil,
            sportName: nil,
            llmSportCategory: "entertainment",
            source: "polymarket",
            sourceCount: 1,
            sources: ["polymarket"],
            marketTier: 2,
            status: "open",
            resolutionDate: "2027-03-15T00:00:00Z",
            topOutcomes: [],
            outcomeCount: 2,
            canonicalMarketKey: nil,
            groupId: nil,
            groupType: nil,
            imageUrl: nil,
            hookDescription: nil,
            matchedOutcomes: nil,
            discoverCard: FeedDiscoverCard(
                suggestedFormat: "outcome_distribution",
                bundleCandidate: false,
                comparisonTheme: nil,
                thresholdPoints: nil,
                distributionOutcomes: [
                    FeedDiscoverDistributionOutcome(label: "Frontrunner", probability: 0.996, movement: nil),
                    FeedDiscoverDistributionOutcome(label: "Sleeper", probability: 0.004, movement: nil),
                ],
                remainingOutcomeCount: 0,
                qaSignals: nil,
                publicSourceDisagreement: nil,
                reasons: nil
            ),
            confidenceTier: nil,
            confidenceScore: nil,
            resolved: nil,
            winner: nil,
            winnerOpeningProbability: nil,
            storyKey: nil,
            priceObservedAt: nil,
            cardSumReason: nil
        )
        let distLeaves = await collectAccessibilityLeaves(
            view: DistributionCardView(data: distData, navigationPath: .constant(NavigationPath())).padding(16),
            width: 390,
            height: 600,
            pinManager: pinManager
        )
        print("VO_DIST_CARD: \(distLeaves.map(\.label))")
        assertNoRawProbabilitySymbolsOrLeaks(distLeaves, context: "DistributionCardView")
        assertTopToBottomOrder(distLeaves, context: "DistributionCardView")
        let distJoined = distLeaves.map(\.label).joined(separator: " | ")
        XCTAssertTrue(distJoined.contains("more than 99 percent"))
        XCTAssertTrue(distJoined.contains("less than 1 percent"))
    }

    private func makeMinimalChecklistContent() -> FirstRunChecklistContent364A {
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
    #endif
}
