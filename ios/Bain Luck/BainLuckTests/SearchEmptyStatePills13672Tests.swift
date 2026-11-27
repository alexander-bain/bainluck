import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13672 — Search empty-state pills adopt Bain Luck's light/dark adaptive DS
/// bordered pill grammar (Browse / 402: A), drop unbordered dark blobs, omit
/// finished tournaments (`US Open`), and stay unclipped at Light, Dark, and AX5.
@MainActor
final class SearchEmptyStatePills13672Tests: XCTestCase {

    private func searchViewSource() throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/SearchView.swift"), encoding: .utf8)
    }

    func testQuickSearchChipUsesBorderedAdaptiveDesignTokensInsteadOfDarkBlob() throws {
        let source = try searchViewSource()
        let quickStart = try XCTUnwrap(source.range(of: "private func quickSearchChip("))
        let quickEnd = try XCTUnwrap(source.range(of: "// MARK: - Suggestions", range: quickStart.upperBound..<source.endIndex))
        let chipSection = String(source[quickStart.lowerBound..<quickEnd.lowerBound])

        XCTAssertFalse(
            chipSection.contains("Color.cardBackgroundDark"),
            "quickSearchChip must not fall back to unbordered Color.cardBackgroundDark"
        )
        XCTAssertTrue(
            chipSection.contains("colorScheme == .dark ? Color.cardBackground : DS.cardBg"),
            "quickSearchChip must adapt fill to light/dark surface tokens"
        )
        XCTAssertTrue(
            chipSection.contains("colorScheme == .dark ? Color.white.opacity(0.14) : DS.border"),
            "quickSearchChip must carry a 1 pt adaptive border"
        )

        let filterStart = try XCTUnwrap(source.range(of: "private func sportFilterChips("))
        let filterSection = String(source[filterStart.lowerBound..<quickStart.lowerBound])
        XCTAssertFalse(
            filterSection.contains("Color.cardBackgroundDark"),
            "Empty-state & filter pills must all avoid Color.cardBackgroundDark"
        )
    }

    func testHostedSearchEmptyStateAt390LightDarkAndAX5IsReadableWithoutUSOpenOrTruncation() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13672_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        for (scheme, size, tag, height) in [
            (ColorScheme.light, DynamicTypeSize.large, "light-large", CGFloat(852)),
            (ColorScheme.dark, DynamicTypeSize.large, "dark-large", CGFloat(852)),
            (ColorScheme.light, DynamicTypeSize.accessibility5, "light-ax5", CGFloat(1150)),
        ] {
            let navCoordinator = NavigationCoordinator()
            let view = SearchView()
                .environmentObject(navCoordinator)
                .environment(\.colorScheme, scheme)

            let img = snapshot(view, scheme: scheme, size: size, height: height)
            let ocr = try ocrText(img)
            XCTAssertTrue(ocr.contains("NBA") && ocr.contains("NFL"), "\(tag): missing sport pills in \(ocr)")
            XCTAssertFalse(ocr.localizedCaseInsensitiveContains("US Open"),
                           "\(tag): finished US Open must never show in Search empty-state pills — \(ocr)")
            XCTAssertFalse(ocr.contains("…"), "\(tag): pill label clipped with ellipsis in \(ocr)")

            if let outDir, !outDir.isEmpty, let data = img.pngData() {
                try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13672-\(tag)-390.png"))
            }
        }

        if let outDir, !outDir.isEmpty {
            let legacy = legacyBeforePreview()
            let beforeImg = snapshot(legacy, scheme: .light, size: .large, height: 852)
            if let data = beforeImg.pngData() {
                try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-13672-light-390.png"))
            }
        }
    }

    private func legacyBeforePreview() -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Search")
                    .font(.largeTitle.weight(.bold))
                Text("Tournaments")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    legacyChip(icon: "tennisball.fill", label: "US Open")
                    legacyChip(icon: "trophy.fill", label: "NBA Cup")
                }
                Text("Browse by Sport")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                FlowLayout(spacing: 8) {
                    ForEach(["NBA", "NFL", "MLB", "NHL", "Soccer", "Golf", "UFC"], id: \.self) { name in
                        self.legacyChip(icon: "sportscourt", label: name)
                    }
                }
            }
            .padding(16)
        }
    }

    private func legacyChip(icon: String, label: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 11))
            Text(label)
                .font(.subheadline)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.cardBackgroundDark)
        .clipShape(Capsule())
    }

    private func snapshot<V: View>(_ view: V, scheme: ColorScheme, size: DynamicTypeSize, height: CGFloat) -> UIImage {
        let host = hostForMeasurement(view, at: size)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
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
