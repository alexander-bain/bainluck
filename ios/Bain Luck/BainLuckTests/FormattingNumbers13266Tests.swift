import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13266 — two formatting fixes for 1.0.7:
/// (a) Every row on `"Where this number comes from"` (`SourceMarkSheet`) aligns its
///     percentage in one right-aligned column whether or not the row carries an age;
///     the age sits under the source name on a second line.
/// (b) Every football or basketball projected score in `ProjectedFinalPointsChartView`
///     prints as a whole integer, live or finished (never `"27.5 projected"`).
@MainActor
final class FormattingNumbers13266Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-20T23:56:00Z")!

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat? = nil,
        scheme: ColorScheme = .light,
        at size: DynamicTypeSize = .large
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let sizedContent: AnyView = {
            if let fixedHeight {
                return AnyView(
                    view
                        .frame(width: width, height: fixedHeight, alignment: .topLeading)
                        .background(bg)
                        .environment(\.colorScheme, scheme)
                )
            }
            return AnyView(
                view
                    .frame(width: width, alignment: .topLeading)
                    .fixedSize(horizontal: false, vertical: true)
                    .background(bg)
                    .environment(\.colorScheme, scheme)
            )
        }()

        let measureHost = hostForMeasurement(sizedContent, at: size)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = fixedHeight ?? min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_600)).height + 16, 180), 2_600)

        let hostedRoot: AnyView = {
            if fixedHeight != nil {
                return sizedContent
            }
            return AnyView(
                NavigationStack {
                    sizedContent
                        .toolbar(.hidden, for: .navigationBar)
                }
            )
        }()

        let host = hostForMeasurement(hostedRoot, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<3 {
            if fixedHeight == nil {
                let nextH = min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_600)).height + 16, fittingH), 2_600)
                if abs(nextH - window.frame.height) > 0.5 {
                    window.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                    host.view.frame = window.bounds
                }
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let topInset = fixedHeight == nil ? host.view.safeAreaInsets.top : 0
        let cropSize = CGSize(width: width, height: max(host.view.bounds.height - topInset, 140))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: cropSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -topInset, width: width, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }
    }

    private func ocrObservations(_ image: UIImage) throws -> [(text: String, box: CGRect)] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let top = obs.topCandidates(1).first else { return nil }
            return (top.string, obs.boundingBox)
        }
    }

    // MARK: - 3(b): Whole-number projected scores (live & finished football / basketball)

    func testFinishedFootballAndBasketballProjectionsEndingInHalfPrintWholeNumbers() {
        XCTAssertEqual(ProjectedFinalPointsChartView.wholePoints(27.5), 28)
        XCTAssertEqual(ProjectedFinalPointsChartView.wholePoints(27.4), 27)
        XCTAssertEqual(ProjectedFinalPointsChartView.wholePoints(30.0), 30)

        // Finished college football game (Rice 31, Temple 27) with stored projection 27.5 / 30.0
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: nil, forecast: 27.5, phase: .after),
            "28 projected"
        )
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: 29, forecast: 27.5, phase: .after),
            "28 projected",
            "finished games use the rounded final sportsbook forecast"
        )
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: nil, forecast: 30.0, phase: .after),
            "30 projected"
        )

        // Finished NBA game with .5 forecast
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: 114, forecast: 115.5, phase: .after),
            "116 projected"
        )
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: 109, forecast: 109.5, phase: .after),
            "110 projected"
        )

        // Live & pregame fallback when pagePoints is absent
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: nil, forecast: 27.5, phase: .during),
            "28 projected"
        )
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(pagePoints: 26, forecast: 27.5, phase: .during),
            "26 projected"
        )
    }

    // MARK: - 3(a): SourceMarkSheet right-aligned percentage column & 390 pt renders

    func testSourceMarkSheetAlignsEveryPercentageColumnDefaultAndAX5() throws {
        // Five sources where only Sportsbooks (6) carries an age ("just now"),
        // matching the Iowa State at UCF live college football sheet reported in #13266.
        let mark = SourceMark(
            state: .blend,
            sources: [
                .init(key: "venue_a", name: "Venue A", probability: 0.675, observedAt: nil),
                .init(key: "venue_b", name: "Venue B", probability: 0.675, observedAt: nil),
                .init(key: "betting", name: "Sportsbooks", probability: 0.696, observedAt: fixedNow.ISO8601Format(), count: 6),
                .init(key: "network", name: "Sports network", probability: 0.712, observedAt: nil),
                .init(key: "stat_model", name: "Our model", probability: 0.700, observedAt: nil),
            ],
            method: "Bain Luck blend · the weighted middle of these sources"
        )
        let sheet = SourceMarkSheet(
            mark: mark,
            number: 0.688,
            subject: "UCF Knights",
            isPregame: false,
            showsTenths: true,
            now: fixedNow
        )

        let defaultLight = captureView(sheet, width: 390, fixedHeight: 540, scheme: .light, at: .large)
        let defaultObs = try ocrObservations(defaultLight)
        let defaultTexts = defaultObs.map(\.text)
        let joinedDefault = defaultTexts.joined(separator: " ")

        XCTAssertFalse(joinedDefault.contains("…"), "No ellipsis in SourceMarkSheet default view: \(defaultTexts)")
        XCTAssertTrue(joinedDefault.contains("just now"), "Sportsbooks age must remain visible: \(defaultTexts)")

        let rowPcts = ["67.5%", "69.6%", "71.2%", "70.0%"]
        var maxXValues: [CGFloat] = []
        for token in rowPcts {
            let matches = defaultObs.filter { $0.text == token }
            XCTAssertFalse(matches.isEmpty, "Missing percentage \(token) in \(defaultTexts)")
            maxXValues.append(contentsOf: matches.map { $0.box.maxX })
        }
        XCTAssertGreaterThanOrEqual(maxXValues.count, 5, "All five row percentages should be recognized individually: \(defaultObs)")
        let spreadDefault = (maxXValues.max() ?? 0) - (maxXValues.min() ?? 0)
        XCTAssertLessThanOrEqual(
            spreadDefault,
            0.03,
            "All five percentages must share one right-aligned column (maxX spread \(spreadDefault) in \(defaultObs))"
        )

        let ax5Light = captureView(sheet, width: 390, fixedHeight: 1500, scheme: .light, at: .accessibility5)
        let ax5Obs = try ocrObservations(ax5Light)
        let ax5Texts = ax5Obs.map(\.text)
        let joinedAX5 = ax5Texts.joined(separator: " ")
        XCTAssertFalse(joinedAX5.contains("…"), "No ellipsis in SourceMarkSheet AX5 view: \(ax5Texts)")
        XCTAssertTrue(joinedAX5.contains("just now"), "Sportsbooks age must remain visible at AX5: \(ax5Texts)")
        XCTAssertTrue(joinedAX5.contains("69.6%"), "Sportsbooks percentage must stay visible at AX5: \(ax5Texts)")
        XCTAssertTrue(joinedAX5.contains("70.0%"), "Bottom row must be visible at AX5: \(ax5Texts)")

        let outDir = URL(fileURLWithPath: "/tmp/renders-13266", isDirectory: true)
        if FileManager.default.fileExists(atPath: outDir.path) {
            let defaultDark = captureView(sheet, width: 390, fixedHeight: 540, scheme: .dark, at: .large)
            let ax5Dark = captureView(sheet, width: 390, fixedHeight: 1500, scheme: .dark, at: .accessibility5)
            try XCTUnwrap(defaultLight.pngData()).write(to: outDir.appendingPathComponent("13266-source-sheet-default-light-390.png"))
            try XCTUnwrap(defaultDark.pngData()).write(to: outDir.appendingPathComponent("13266-source-sheet-default-dark-390.png"))
            try XCTUnwrap(ax5Light.pngData()).write(to: outDir.appendingPathComponent("13266-source-sheet-ax5-light-390.png"))
            try XCTUnwrap(ax5Dark.pngData()).write(to: outDir.appendingPathComponent("13266-source-sheet-ax5-dark-390.png"))
        }
    }

    func testFinishedCollegeFootballProjectedPointsChartRendersWholeAt390() throws {
        let kickoff = fixedNow.addingTimeInterval(-4 * 3_600)
        let finalAt = fixedNow.addingTimeInterval(-1_800)
        // Finished college football game (Rice 31, Temple 27) where last stored
        // sportsbook projections were Rice 27.5 and Temple 30.0.
        let input = ProjectedFinalPointsSeries.Input(
            sportKey: "americanfootball_ncaaf",
            sourceKey: "draftkings",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [
                .init(at: kickoff.addingTimeInterval(-1_800), home: 24.5, away: 21.5, homeProbability: 0.57, kind: .recorded),
                .init(at: kickoff.addingTimeInterval(3_600), home: 27.5, away: 24.0, homeProbability: 0.61, kind: .recorded),
                .init(at: kickoff.addingTimeInterval(7_200), home: 30.0, away: 27.5, homeProbability: 0.58, kind: .recorded),
            ],
            actuals: [
                .init(at: kickoff, home: 0, away: 0),
                .init(at: kickoff.addingTimeInterval(3_600), home: 14, away: 10),
                .init(at: kickoff.addingTimeInterval(7_200), home: 20, away: 21),
                .init(at: finalAt, home: 27, away: 31),
            ],
            kickoffAt: kickoff,
            scoreObservationStartAt: kickoff,
            finalAt: finalAt,
            asOf: fixedNow,
            windowStartAt: nil,
            requestCutoffAt: nil,
            openingScore: .init(at: kickoff, home: 0, away: 0)
        )

        func chartSurface(scheme: ColorScheme) -> some View {
            let colors = TeamTextContrast.surfaceColors(
                awayHex: "#00205B",
                homeHex: "#9D2235",
                awaySecondaryHex: "#C1C6C8",
                homeSecondaryHex: "#FFFFFF",
                colorScheme: scheme,
                checkHueFamily: true
            )
            return ProjectedFinalPointsChartView(
                input: input,
                homeTeam: "Temple Owls",
                awayTeam: "Rice Owls",
                homeColor: colors.home,
                awayColor: colors.away,
                periodMarkers: nil,
                sportKey: "americanfootball_ncaaf",
                pageProjectedPair: nil
            )
            .padding(16)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
            .padding(16)
            .environment(\.colorScheme, scheme)
        }

        let defaultLight = captureView(chartSurface(scheme: .light), width: 390, scheme: .light, at: .large)
        let defaultObs = try ocrObservations(defaultLight)
        let defaultTexts = defaultObs.map(\.text)
        let joinedDefault = defaultTexts.joined(separator: " ")

        XCTAssertFalse(joinedDefault.contains("27.5"), "Half-point projection must not print on finished football: \(defaultTexts)")
        XCTAssertFalse(joinedDefault.contains("…"), "No ellipsis on finished football chart: \(defaultTexts)")
        XCTAssertTrue(joinedDefault.contains("28 projected"), "Expected rounded '28 projected': \(defaultTexts)")
        XCTAssertTrue(joinedDefault.contains("30 projected"), "Expected '30 projected': \(defaultTexts)")
        XCTAssertTrue(joinedDefault.contains("31 scored"), "Expected '31 scored': \(defaultTexts)")
        XCTAssertTrue(joinedDefault.contains("27 scored"), "Expected '27 scored': \(defaultTexts)")

        let ax5Light = captureView(chartSurface(scheme: .light), width: 390, scheme: .light, at: .accessibility5)
        let ax5Texts = try ocrObservations(ax5Light).map(\.text)
        let joinedAX5 = ax5Texts.joined(separator: " ")
        XCTAssertFalse(joinedAX5.contains("27.5"), "No half-point at AX5: \(ax5Texts)")
        XCTAssertFalse(joinedAX5.contains("…"), "No ellipsis at AX5: \(ax5Texts)")
        XCTAssertTrue(joinedAX5.contains("28 projected"), "Expected '28 projected' at AX5: \(ax5Texts)")

        let outDir = URL(fileURLWithPath: "/tmp/renders-13266", isDirectory: true)
        if FileManager.default.fileExists(atPath: outDir.path) {
            let defaultDark = captureView(chartSurface(scheme: .dark), width: 390, scheme: .dark, at: .large)
            try XCTUnwrap(defaultLight.pngData()).write(to: outDir.appendingPathComponent("13266-finished-football-default-light-390.png"))
            try XCTUnwrap(defaultDark.pngData()).write(to: outDir.appendingPathComponent("13266-finished-football-default-dark-390.png"))
            try XCTUnwrap(ax5Light.pngData()).write(to: outDir.appendingPathComponent("13266-finished-football-ax5-light-390.png"))
        }
    }
}
