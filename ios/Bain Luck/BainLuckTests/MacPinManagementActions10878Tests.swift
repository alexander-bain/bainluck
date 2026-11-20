import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(AppKit)
import AppKit
#endif

/// #10878 / #4931 / #4942 — focused unit, source-wiring, and offscreen-render
/// tests for Mac `PinManagementView` desktop sheet sizing, keyboard dismissal,
/// and right-click row context actions (`MacPinManagementActions10878`).
@MainActor
final class MacPinManagementActions10878Tests: XCTestCase {

    // MARK: - 1. Action Ordering & Honest State Rules

    func testAvailableGamePinOffersCopyTitleCopyLinkOpenInNewWindowAndRemove() {
        let pin = SavedPin(type: "event", value: 40101)
        let actions = MacPinManagementAction10878.actions(
            for: pin,
            metadata: .available(title: "Celtics at Knicks"),
            isSaving: false
        )
        XCTAssertEqual(
            actions,
            [
                .copyTitle("Celtics at Knicks"),
                .copyLink("https://bainluck.com/events/40101"),
                .openInNewWindow(eventID: 40101),
                .removePin(pin),
            ]
        )
        XCTAssertEqual(
            actions.map(\.title),
            ["Copy Title", "Copy Link", "Open in New Window", "Remove Pin"]
        )
        XCTAssertEqual(
            actions.map(\.systemImage),
            ["doc.on.doc", "link", "macwindow.badge.plus", "bookmark.slash"]
        )
        XCTAssertEqual(actions.map(\.isDestructive), [false, false, false, true])
    }

    func testAvailableMarketPinOffersCopyTitleCopyLinkAndRemoveWithoutNewWindow() {
        let pin = SavedPin(type: "future", value: 50202)
        let actions = MacPinManagementAction10878.actions(
            for: pin,
            metadata: .available(title: "2026 NBA Champion"),
            isSaving: false
        )
        XCTAssertEqual(
            actions,
            [
                .copyTitle("2026 NBA Champion"),
                .copyLink("https://bainluck.com/futures/50202"),
                .removePin(pin),
            ]
        )
        XCTAssertEqual(
            actions.map(\.title),
            ["Copy Title", "Copy Link", "Remove Pin"]
        )
        XCTAssertFalse(
            actions.contains {
                if case .openInNewWindow = $0 { return true }
                return false
            },
            "market pins do not open the typed game detail window"
        )
    }

    func testBlankAvailableTitleOmitsCopyTitleAndNeverCopiesFallbackPlaceholder() {
        let pin = SavedPin(type: "event", value: 40102)
        let actions = MacPinManagementAction10878.actions(
            for: pin,
            metadata: .available(title: "   \n "),
            isSaving: false
        )
        XCTAssertEqual(
            actions,
            [
                .copyLink("https://bainluck.com/events/40102"),
                .openInNewWindow(eventID: 40102),
                .removePin(pin),
            ],
            "a blank hydrated title falls back to 'Saved game' on screen and must never be copied as a title"
        )
    }

    func testFailedMetadataOffersRetryDetailsCopyLinkAndRemoveWithoutCopyTitle() {
        let gamePin = SavedPin(type: "event", value: 40103)
        XCTAssertEqual(
            MacPinManagementAction10878.actions(
                for: gamePin,
                metadata: .failed,
                isSaving: false
            ),
            [
                .retryDetails,
                .copyLink("https://bainluck.com/events/40103"),
                .openInNewWindow(eventID: 40103),
                .removePin(gamePin),
            ]
        )

        let marketPin = SavedPin(type: "future", value: 50203)
        XCTAssertEqual(
            MacPinManagementAction10878.actions(
                for: marketPin,
                metadata: .failed,
                isSaving: false
            ),
            [
                .retryDetails,
                .copyLink("https://bainluck.com/futures/50203"),
                .removePin(marketPin),
            ]
        )
    }

    func testLoadingMetadataOffersCopyLinkAndRemoveWithoutCopyTitleOrRetry() {
        let gamePin = SavedPin(type: "event", value: 40104)
        XCTAssertEqual(
            MacPinManagementAction10878.actions(
                for: gamePin,
                metadata: nil,
                isSaving: false
            ),
            [
                .copyLink("https://bainluck.com/events/40104"),
                .openInNewWindow(eventID: 40104),
                .removePin(gamePin),
            ]
        )

        let marketPin = SavedPin(type: "future", value: 50204)
        XCTAssertEqual(
            MacPinManagementAction10878.actions(
                for: marketPin,
                metadata: nil,
                isSaving: false
            ),
            [
                .copyLink("https://bainluck.com/futures/50204"),
                .removePin(marketPin),
            ]
        )
    }

    func testUnavailable404PinOffersOnlyRemoveNeverDeadLinkOrNewWindow() {
        for type in ["event", "future"] {
            let pin = SavedPin(type: type, value: 99901)
            let actions = MacPinManagementAction10878.actions(
                for: pin,
                metadata: .unavailable,
                isSaving: false
            )
            XCTAssertEqual(
                actions,
                [.removePin(pin)],
                "\(type): a confirmed 404/410 pin must only offer Remove Pin, never a dead link or window"
            )
        }
    }

    func testInFlightSavingOmitsRemoveActionAndUnavailableSavingAttachesNoMenu() {
        let gamePin = SavedPin(type: "event", value: 40105)
        XCTAssertEqual(
            MacPinManagementAction10878.actions(
                for: gamePin,
                metadata: .available(title: "Lakers at Warriors"),
                isSaving: true
            ),
            [
                .copyTitle("Lakers at Warriors"),
                .copyLink("https://bainluck.com/events/40105"),
                .openInNewWindow(eventID: 40105),
            ],
            "an in-flight save/removal omits Remove Pin so it cannot be double-triggered"
        )

        let unavailablePin = SavedPin(type: "event", value: 40106)
        XCTAssertTrue(
            MacPinManagementAction10878.actions(
                for: unavailablePin,
                metadata: .unavailable,
                isSaving: true
            ).isEmpty,
            "an unavailable 404 pin whose removal is already in flight has no remaining actions and attaches no empty menu"
        )
    }

    func testUnknownPinTypeOrNonPositiveIDAttachesNoMenu() {
        XCTAssertTrue(
            MacPinManagementAction10878.actions(
                for: SavedPin(type: "team", value: 10),
                metadata: .available(title: "Knicks")
            ).isEmpty
        )
        XCTAssertTrue(
            MacPinManagementAction10878.actions(
                for: SavedPin(type: "event", value: 0),
                metadata: .available(title: "Knicks")
            ).isEmpty
        )
    }

    // MARK: - 2. Desktop Sheet Metrics & Source Wiring

    func testSheetMetricsProvideReadableDesktopDimensions() {
        XCTAssertGreaterThanOrEqual(MacPinManagementSheetMetrics10878.minWidth, 500)
        XCTAssertGreaterThanOrEqual(
            MacPinManagementSheetMetrics10878.idealWidth,
            MacPinManagementSheetMetrics10878.minWidth
        )
        XCTAssertGreaterThanOrEqual(MacPinManagementSheetMetrics10878.minHeight, 400)
        XCTAssertGreaterThanOrEqual(
            MacPinManagementSheetMetrics10878.idealHeight,
            MacPinManagementSheetMetrics10878.minHeight
        )
    }

    func testPinManagementViewWiresSheetFrameDoneShortcutAndRowMenu() throws {
        let source = try Self.appSource("Views/PinManagementView.swift")
        XCTAssertTrue(source.contains(".macPinManagementDoneShortcut()"))
        XCTAssertTrue(source.contains(".macPinManagementSheetFrame()"))
        XCTAssertTrue(source.contains(".macPinManagementRowMenu("))
        XCTAssertTrue(source.contains("metadata: vm.metadata[pin]"))
        XCTAssertTrue(source.contains("isSaving: pinManager.isSaving(type: pin.type, id: pin.value)"))
        XCTAssertTrue(source.contains("onRetryDetails: { Task { await vm.load(pinManager.savedPins, retryFailed: true) } }"))
        XCTAssertTrue(source.contains("onRemove: { pinManager.togglePin(type: pin.type, id: pin.value) }"))
    }

    func testModifierAndContextMenuAreMacOSGated() throws {
        let source = try Self.appSource("Utilities/MacPinManagementActions10878.swift")
        var platform: [String] = []
        var contextMenus = 0
        var windowOpeners = 0
        for line in source.components(separatedBy: "\n") {
            let text = line.trimmingCharacters(in: .whitespaces)
            if text.hasPrefix("//") { continue }
            if text.hasPrefix("#if ") { platform.append(text) }
            if text == "#else" { platform.append("#else of \(platform.popLast() ?? "")") }
            if text == "#endif" { _ = platform.popLast() }
            if text.contains(".contextMenu") {
                contextMenus += 1
                XCTAssertEqual(platform.last, "#if os(macOS)", "\(text) runs outside macOS")
            }
            if text.contains("openWindow") {
                windowOpeners += 1
                XCTAssertTrue(platform.contains("#if os(macOS)"), "\(text) runs outside macOS")
            }
        }
        XCTAssertEqual(contextMenus, 1)
        XCTAssertGreaterThan(windowOpeners, 0)
    }

    // MARK: - 3. Offscreen Rendered Snapshot Verification

    func testOffscreenRenderedPinManagementMenuPreviewsProduceNonEmptyBitmaps() throws {
        let scenarios: [(slug: String, sectionTitle: String, pin: SavedPin, metadata: PinMetadata?, isSaving: Bool, statusNote: String)] = [
            (
                "01-available-game-pin-menu",
                "Games (2)",
                SavedPin(type: "event", value: 40101),
                .available(title: "Celtics at Knicks"),
                false,
                "Loaded game pin — opens detail or pops into a standalone Mac window"
            ),
            (
                "02-available-market-pin-menu",
                "Markets (2)",
                SavedPin(type: "future", value: 50202),
                .available(title: "2026 NBA Champion"),
                false,
                "Loaded market pin — copies title or canonical web link, or removes pin"
            ),
            (
                "03-failed-detail-pin-menu",
                "Games (2)",
                SavedPin(type: "event", value: 40103),
                .failed,
                false,
                "Transient lookup error — offers Retry Details, Copy Link, Open in New Window, and Remove Pin"
            ),
            (
                "04-unavailable-404-pin-menu",
                "Markets (2)",
                SavedPin(type: "future", value: 50209),
                .unavailable,
                false,
                "Confirmed 404/410 — offers only Remove Pin, never a dead link or window"
            ),
        ]

        let snapshotDir = ProcessInfo.processInfo.environment["MAC_PIN_MANAGEMENT_10878_SNAPSHOT_DIR"]
        if let dir = snapshotDir, !dir.isEmpty {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: dir),
                withIntermediateDirectories: true
            )
        }

        for scenario in scenarios {
            let actions = MacPinManagementAction10878.actions(
                for: scenario.pin,
                metadata: scenario.metadata,
                isSaving: scenario.isSaving
            )
            XCTAssertFalse(actions.isEmpty, "Expected menu actions for \(scenario.slug)")

            let preview = MacPinManagementPreviewCard10878(
                sectionTitle: scenario.sectionTitle,
                pin: scenario.pin,
                metadata: scenario.metadata,
                isSaving: scenario.isSaving,
                statusNote: scenario.statusNote,
                actions: actions
            )
            .macPinManagementSheetFrame()
            .frame(width: MacPinManagementSheetMetrics10878.idealWidth)
            .background(Color(red: 0.96, green: 0.97, blue: 0.98))

            let renderer = rendererForMeasurement(preview)
            renderer.scale = 2.0

            #if canImport(AppKit)
            let image = try XCTUnwrap(renderer.nsImage, "Expected rendered NSImage for \(scenario.slug)")
            XCTAssertGreaterThanOrEqual(image.size.width, MacPinManagementSheetMetrics10878.minWidth)
            XCTAssertGreaterThan(image.size.height, 220)

            if let dir = snapshotDir, !dir.isEmpty,
               let tiff = image.tiffRepresentation,
               let rep = NSBitmapImageRep(data: tiff),
               let png = rep.representation(using: .png, properties: [:]) {
                let url = URL(fileURLWithPath: dir).appendingPathComponent("\(scenario.slug).png")
                try png.write(to: url)
            }
            #endif
        }
    }

    // MARK: - Helpers

    private static func appSource(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        return try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }
}

private struct MacPinManagementPreviewCard10878: View {
    let sectionTitle: String
    let pin: SavedPin
    let metadata: PinMetadata?
    let isSaving: Bool
    let statusNote: String
    let actions: [MacPinManagementAction10878]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Manage pins", systemImage: "bookmark.fill")
                    .font(.headline)
                Spacer()
                Text("Done (Esc)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.blue.opacity(0.1), in: Capsule())
            }

            Divider()

            Text(sectionTitle.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(pin.displayTitle(for: metadata))
                        .font(.body.weight(.medium))
                        .foregroundStyle(
                            {
                                if case .available = metadata { return Color.blue }
                                return Color.primary
                            }()
                        )
                    switch metadata {
                    case .available:
                        Text(statusNote)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    case .unavailable:
                        Text("Details are no longer available. You can remove this pin.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    case .failed:
                        Text("Couldn't load details. You can still remove this pin.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Retry details")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.blue)
                    case .none:
                        Text("Loading details…")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 0)
                Text(isSaving ? "Removing…" : "Remove")
                    .font(.caption.weight(.medium))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.secondary.opacity(0.14), in: RoundedRectangle(cornerRadius: 6))
            }
            .padding(12)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.black.opacity(0.08), lineWidth: 1))
            .macPinManagementRowMenu(
                pin: pin,
                metadata: metadata,
                isSaving: isSaving,
                onRetryDetails: {},
                onRemove: {}
            )

            VStack(alignment: .leading, spacing: 6) {
                Text("MAC RIGHT-CLICK CONTEXT MENU (\(pin.id))")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 0) {
                    let primary = actions.filter { !$0.isDestructive }
                    let destructive = actions.filter { $0.isDestructive }
                    ForEach(Array(primary.enumerated()), id: \.offset) { idx, action in
                        menuRow(action)
                        if idx < primary.count - 1 {
                            Divider()
                        }
                    }
                    if !primary.isEmpty && !destructive.isEmpty {
                        Divider()
                    }
                    ForEach(Array(destructive.enumerated()), id: \.offset) { _, action in
                        menuRow(action)
                    }
                }
                .background(Color.white, in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.black.opacity(0.12), lineWidth: 1))
                .frame(width: 250)
            }
            Spacer(minLength: 0)
        }
        .padding(20)
    }

    private func menuRow(_ action: MacPinManagementAction10878) -> some View {
        HStack(spacing: 8) {
            Image(systemName: action.systemImage)
                .font(.caption)
                .foregroundStyle(action.isDestructive ? .red : .primary)
                .frame(width: 16)
            Text(action.title)
                .font(.caption.weight(.medium))
                .foregroundStyle(action.isDestructive ? .red : .primary)
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }
}
