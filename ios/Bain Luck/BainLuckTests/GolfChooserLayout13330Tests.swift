import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13330: `EventAtlasGolfContenderChooserView11666` keeps every probability (`16.2%`, `9.3%`, …)
/// on a single line while the golfer's name takes the horizontal squeeze, and spells `"points"`
/// instead of `"pts"` across chooser movement and finish delta labels.
@MainActor
final class GolfChooserLayout13330Tests: XCTestCase {

    private func decodeSourceMark(_ json: String) throws -> SourceMark {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SourceMark.self, from: Data(json.utf8))
    }

    private func renderChooser(
        rows: [GolfTournamentFieldRow],
        scheme: ColorScheme = .light,
        size: DynamicTypeSize = .large
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let card = EventAtlasGolfContenderChooserView11666(
            field: rows,
            phase: .recorded,
            selectedGolferName: rows.first?.name ?? "",
            mode: .constant(.chances),
            band: .constant(.all),
            onSelectGolfer: { _ in }
        )
        .padding(16)
        .frame(width: 390, alignment: .topLeading)
        .fixedSize(horizontal: false, vertical: true)
        .background(bg)
        .environment(\.colorScheme, scheme)

        let measureHost = hostForMeasurement(card, at: size)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = min(max(ceil(measureHost.sizeThatFits(in: CGSize(width: 390, height: 3_000)).height) + 24, 200), 3_000)

        let host = hostForMeasurement(NavigationStack { card.toolbar(.hidden, for: .navigationBar) }, at: size)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: 390, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let targetSize = CGSize(width: 390, height: fittingH)
        return UIGraphicsImageRenderer(size: targetSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: CGRect(origin: .zero, size: targetSize), afterScreenUpdates: true)
        }
    }

    private func recognizeBand(_ cgImage: CGImage) throws -> [String] {
        var lines: [String] = []
        let request = VNRecognizeTextRequest { req, _ in
            let obs = (req.results as? [VNRecognizedTextObservation]) ?? []
            lines = obs.compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return lines
    }

    private func ocrStrings(_ image: UIImage) throws -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        if cgImage.height <= 1500 {
            return try recognizeBand(cgImage)
        }
        var allLines: [String] = []
        let bandHeight = 1400
        let step = 1100
        var y = 0
        while y < cgImage.height {
            let h = min(bandHeight, cgImage.height - y)
            let rect = CGRect(x: 0, y: y, width: cgImage.width, height: h)
            if let cropped = cgImage.cropping(to: rect) {
                allLines.append(contentsOf: try recognizeBand(cropped))
            }
            if y + bandHeight >= cgImage.height { break }
            y += step
        }
        return allLines
    }

    private func joinWrappedProse(_ lines: [String]) -> String {
        var out = ""
        for raw in lines {
            let line = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }
            if out.isEmpty {
                out = line
            } else if out.hasSuffix("-") {
                out += line
            } else {
                out += " " + line
            }
        }
        return out
    }

    func testFormatMovementPointsUsesFullWordPointsAndNeverPts() {
        XCTAssertEqual(EventAtlasGolfTournament11666.formatMovementPoints(-0.0189), "-1.9 points")
        XCTAssertEqual(EventAtlasGolfTournament11666.formatMovementPoints(0.0317), "+3.2 points")
        XCTAssertEqual(EventAtlasGolfTournament11666.formatMovementPoints(0.01), "+1.0 points")
        XCTAssertNil(EventAtlasGolfTournament11666.formatMovementPoints(0.0004))
    }

    func testChooserPercentsStaySingleLineAt390DefaultAndLargestAccessibilitySize() throws {
        let blendMark = try decodeSourceMark("""
        {"state":"blend","sources":[{"key":"kalshi","name":"Kalshi","probability":0.175},{"key":"datagolf","name":"DataGolf","probability":0.1484}]}
        """)
        let rows: [GolfTournamentFieldRow] = [
            GolfTournamentFieldRow(name: "Michael Thorbjornsen", probability: 0.162, position: 1, movement24h: -0.0189, sourceMark: blendMark),
            GolfTournamentFieldRow(name: "Rasmus Neergaard-Petersen", probability: 0.093, position: 2, movement24h: 0.0317, sourceMark: blendMark),
            GolfTournamentFieldRow(name: "Marco Penge", probability: 0.079, position: 3, movement24h: 0.010, sourceMark: blendMark),
            GolfTournamentFieldRow(name: "Ricky Castillo", probability: 0.057, position: 4, movement24h: -0.022, sourceMark: blendMark),
            GolfTournamentFieldRow(name: "Adrien Dumont De Chassart", probability: 0.034, position: 5, movement24h: 0.0182, sourceMark: blendMark),
        ]

        for size in [DynamicTypeSize.large, DynamicTypeSize.accessibility5] {
            let img = renderChooser(rows: rows, scheme: .light, size: size)
            let lines = try ocrStrings(img)
            let joined = lines.joined(separator: " | ")
            let prose = joinWrappedProse(lines)

            for pct in ["16.2%", "9.3%", "7.9%", "5.7%", "3.4%"] {
                XCTAssertTrue(
                    lines.contains(where: { $0.contains(pct) }),
                    "Expected whole single-line percent '\(pct)' at \(size): \(joined)"
                )
            }
            XCTAssertFalse(
                lines.contains(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines) == "%" }),
                "Percent sign '%' must never wrap onto its own line at \(size): \(joined)"
            )
            XCTAssertTrue(joined.contains("points"), "Expected 'points' wording at \(size): \(joined)")
            XCTAssertFalse(
                lines.contains(where: { $0.localizedCaseInsensitiveContains("pts") }),
                "Must not abbreviate 'points' as 'pts' at \(size): \(joined)"
            )
            XCTAssertFalse(joined.contains("…") || joined.contains("..."), "No text truncation allowed at \(size): \(joined)")
            XCTAssertTrue(prose.contains("Neergaard-Petersen"), "Longest golfer name must remain readable at \(size): \(prose)")
            XCTAssertTrue(prose.contains("Dumont De Chassart"), "Dumont De Chassart must remain readable at \(size): \(prose)")
        }
    }
}
