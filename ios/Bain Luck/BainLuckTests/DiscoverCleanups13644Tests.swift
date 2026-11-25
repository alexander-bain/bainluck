import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class DiscoverCleanups13644Tests: XCTestCase {
    private static let outputDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/sheets"

    private static var oscarsSet: PairedMetricSet {
        PairedMetricSet(
            setId: "oscars-best-picture-2026",
            category: "Entertainment",
            kicker: "OSCARS · 2026",
            title: "Best Picture: Nominee vs Winner",
            subtitle: "Ranked by winning · nomination chance shown beside",
            stage1Label: "Nominated",
            stage2Label: "Winner",
            stage1SettledYesLabel: "Nominated",
            stage1SettledNoLabel: "Missed",
            entries: [
                PairedSubjectEntry(
                    subjectKey: "sinners",
                    subject: "Sinners",
                    detail: "Ryan Coogler",
                    stage1MarketId: 900101,
                    stage1Probability: 0.92,
                    stage2MarketId: 900201,
                    stage2Probability: 0.34,
                    art: PairedArtAsset(
                        kind: .tmdbPoster,
                        url: "https://image.tmdb.org/t/p/w500/example1.jpg",
                        tmdbId: 1233413,
                        posterPath: "/example1.jpg",
                        adult: false,
                        kidSafeVetted: true
                    )
                ),
                PairedSubjectEntry(
                    subjectKey: "one-battle-after-another",
                    subject: "One Battle After Another",
                    detail: "Paul Thomas Anderson",
                    stage1MarketId: 900102,
                    stage1Probability: 0.88,
                    stage2MarketId: 900202,
                    stage2Probability: 0.29,
                    art: PairedArtAsset(
                        kind: .tmdbPoster,
                        url: "https://image.tmdb.org/t/p/w500/example2.jpg",
                        tmdbId: 1054867,
                        posterPath: "/example2.jpg",
                        adult: false,
                        kidSafeVetted: true
                    )
                ),
                PairedSubjectEntry(
                    subjectKey: "hamnet",
                    subject: "Hamnet",
                    detail: "Chloé Zhao",
                    stage1MarketId: 900103,
                    stage1Probability: 0.76,
                    stage2MarketId: 900203,
                    stage2Probability: 0.14
                ),
            ],
            preferredVisualForm: PairedVisualFormId.pairedBarsTop5Expandable.rawValue
        )
    }

    func testOscarsCardOmitsTMDBFooterAndAboutViewCarriesTMDBAttribution() throws {
        // 1. After: Oscars paired card on Light and Dark (390 pt) has zero TMDB logo or attribution text.
        let afterLight = renderSlice(width: 390, height: 470, scheme: .light) {
            DiscoverPairedMetricCardView(set: Self.oscarsSet, form: .pairedBarsTop5Expandable)
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(Color(.systemGroupedBackground))
        }
        let afterDark = renderSlice(width: 390, height: 470, scheme: .dark) {
            DiscoverPairedMetricCardView(set: Self.oscarsSet, form: .pairedBarsTop5Expandable)
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(Color(.systemGroupedBackground))
        }

        let ocrAfterLight = recognizeText(in: afterLight)
        let ocrAfterDark = recognizeText(in: afterDark)
        XCTAssertTrue(ocrAfterLight.contains("Best Picture"), "Missing Oscars card title (light): \(ocrAfterLight)")
        XCTAssertTrue(ocrAfterLight.contains("Sinners"), "Missing Oscars contender (light): \(ocrAfterLight)")
        XCTAssertTrue(ocrAfterDark.contains("Best Picture"), "Missing Oscars card title (dark): \(ocrAfterDark)")
        XCTAssertFalse(
            ocrAfterLight.localizedCaseInsensitiveContains("TMDB")
                || ocrAfterLight.localizedCaseInsensitiveContains("endorsed or certified"),
            "TMDB attribution leaked onto Oscars card (light): \(ocrAfterLight)"
        )
        XCTAssertFalse(
            ocrAfterDark.localizedCaseInsensitiveContains("TMDB")
                || ocrAfterDark.localizedCaseInsensitiveContains("endorsed or certified"),
            "TMDB attribution leaked onto Oscars card (dark): \(ocrAfterDark)"
        )

        // 2. Discover feed / grouped cards on iPhone also never render "Your sport" or "Following" feed cues.
        XCTAssertFalse(ocrAfterLight.localizedCaseInsensitiveContains("Your sport"))

        // 3. AboutView carries subtle TMDB mark + required attribution sentence at bottom in both themes.
        let fullAboutHeight: CGFloat = 1580
        let aboutLightFull = renderSlice(width: 390, height: fullAboutHeight, scheme: .light) {
            NavigationStack {
                AboutView()
            }
            .environmentObject(NavigationCoordinator())
        }
        let aboutDarkFull = renderSlice(width: 390, height: fullAboutHeight, scheme: .dark) {
            NavigationStack {
                AboutView()
            }
            .environmentObject(NavigationCoordinator())
        }

        let ocrAboutLight = recognizeText(in: aboutLightFull)
        let ocrAboutDark = recognizeText(in: aboutDarkFull)
        XCTAssertTrue(
            ocrAboutLight.localizedCaseInsensitiveContains("endorsed or certified by TMDB"),
            "AboutView light mode must carry TMDB attribution notice: \(ocrAboutLight)"
        )
        XCTAssertTrue(
            ocrAboutDark.localizedCaseInsensitiveContains("endorsed or certified by TMDB"),
            "AboutView dark mode must carry TMDB attribution notice: \(ocrAboutDark)"
        )

        // 4. Local-only before-and-after 390 pt sheet generation (skipped cleanly on CI where scratch files do not exist).
        let beforeLightPath = "\(Self.outputDir)/13644-before-light.png"
        let beforeDarkPath = "\(Self.outputDir)/13644-before-dark.png"
        if FileManager.default.fileExists(atPath: beforeLightPath),
           FileManager.default.fileExists(atPath: beforeDarkPath),
           let beforeLight = UIImage(contentsOfFile: beforeLightPath),
           let beforeDark = UIImage(contentsOfFile: beforeDarkPath) {
            let aboutBottomLight = cropBottom(aboutLightFull, heightPoints: 115)
            let aboutBottomDark = cropBottom(aboutDarkFull, heightPoints: 115)
            let sheet = buildComparisonSheet(
                beforeLight: beforeLight,
                beforeDark: beforeDark,
                afterLight: afterLight,
                afterDark: afterDark,
                aboutLight: aboutBottomLight,
                aboutDark: aboutBottomDark
            )
            let sheetPath = "\(Self.outputDir)/sheet-13644-iphone-cleanups-390.png"
            try savePNG(sheet, to: sheetPath)
        }
    }

    private func cropBottom(_ image: UIImage, heightPoints: CGFloat) -> UIImage {
        let size = CGSize(width: image.size.width, height: min(heightPoints, image.size.height))
        let yOffset = max(0, image.size.height - size.height)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = image.scale
        return UIGraphicsImageRenderer(size: size, format: fmt).image { _ in
            image.draw(at: CGPoint(x: 0, y: -yOffset))
        }
    }

    private func buildComparisonSheet(
        beforeLight: UIImage,
        beforeDark: UIImage,
        afterLight: UIImage,
        afterDark: UIImage,
        aboutLight: UIImage,
        aboutDark: UIImage
    ) -> UIImage {
        let colWidth: CGFloat = 390
        let gap: CGFloat = 16
        let margin: CGFloat = 16
        let headerH: CGFloat = 28

        let row1H = max(beforeLight.size.height, beforeDark.size.height)
        let row2H = max(afterLight.size.height, afterDark.size.height)
        let row3H = max(aboutLight.size.height, aboutDark.size.height)
        let totalW = margin * 2 + colWidth * 2 + gap
        let totalH = margin * 2 + (headerH + row1H) + gap + (headerH + row2H) + gap + (headerH + row3H)

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        return UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
            UIColor(white: 0.94, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: totalW, height: totalH))

            func drawPanel(_ img: UIImage, title: String, x: CGFloat, y: CGFloat) {
                let titleAttr: [NSAttributedString.Key: Any] = [
                    .font: UIFont.systemFont(ofSize: 12, weight: .semibold),
                    .foregroundColor: UIColor.black,
                ]
                NSString(string: title).draw(
                    in: CGRect(x: x, y: y + 5, width: colWidth, height: headerH - 5),
                    withAttributes: titleAttr
                )
                img.draw(in: CGRect(x: x, y: y + headerH, width: colWidth, height: img.size.height))
            }

            let y1 = margin
            drawPanel(beforeLight, title: "BEFORE Light (390pt) · simulator results, not phone results", x: margin, y: y1)
            drawPanel(beforeDark, title: "BEFORE Dark (390pt) · simulator results, not phone results", x: margin + colWidth + gap, y: y1)

            let y2 = y1 + headerH + row1H + gap
            drawPanel(afterLight, title: "AFTER Light (390pt) · TMDB removed from card · sim", x: margin, y: y2)
            drawPanel(afterDark, title: "AFTER Dark (390pt) · TMDB removed from card · sim", x: margin + colWidth + gap, y: y2)

            let y3 = y2 + headerH + row2H + gap
            drawPanel(aboutLight, title: "AFTER About Light (390pt) · subtle TMDB + notice · sim", x: margin, y: y3)
            drawPanel(aboutDark, title: "AFTER About Dark (390pt) · subtle TMDB + notice · sim", x: margin + colWidth + gap, y: y3)
        }
    }

    private func renderSlice<Content: View>(
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        @ViewBuilder content: () -> Content
    ) -> UIImage {
        let host = UIHostingController(
            rootView: content()
                .environment(\.colorScheme, scheme)
                .environment(\.dynamicTypeSize, .large)
        )
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.view.backgroundColor = scheme == .dark ? .black : .white
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<5 {
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.04))
        }
        let format = UIGraphicsImageRendererFormat()
        format.scale = 2.0
        let renderer = UIGraphicsImageRenderer(size: bounds.size, format: format)
        let image = renderer.image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return image
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    private func savePNG(_ image: UIImage, to path: String) throws {
        guard let data = image.pngData() else {
            XCTFail("Failed to encode PNG at \(path)")
            return
        }
        try data.write(to: URL(fileURLWithPath: path), options: .atomic)
    }
}
