import Foundation
import XCTest
@testable import Bain_Luck

/// Item 6 (Nov 25): `onboarding_step` must emit when **Next** is pressed, reporting
/// the step just finished (matching `frontend/app/onboarding/page.tsx:goNext`),
/// never step 1 on flow open, and strictly gated behind `"Allow"` telemetry consent.
@MainActor
final class OnboardingStepTelemetryOnNextTests: XCTestCase {
    private final class StubTelemetrySink: TelemetrySink {
        func setAnalyticsCollectionEnabled(_ enabled: Bool) {}
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) {}
        func resetAnalyticsData() {}
    }

    private var captured: [(name: String, params: [String: Any])] = []

    override func setUp() {
        super.setUp()
        captured = []
        TelemetryConsent.shared.resetForTests(sink: StubTelemetrySink())
        TelemetryConsent.shared.initialize()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        captured = []
        super.tearDown()
    }

    func testGoNextEmitsFinishedStepBeforeAdvancingAndNothingOnOpen() {
        TelemetryConsent.shared.set(.analytics)
        XCTAssertTrue(TelemetryConsent.shared.isGranted)

        let vm = OnboardingViewModel()
        XCTAssertEqual(vm.currentStep, 1)
        XCTAssertTrue(captured.isEmpty, "Opening the onboarding flow must emit zero onboarding_step events")

        // Step 1 ("location") -> Next -> emits step 1 BEFORE moving to step 2
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 2)
        XCTAssertEqual(captured.count, 1)
        XCTAssertEqual(captured[0].name, "onboarding_step")
        XCTAssertEqual(captured[0].params["step"] as? Int, 1)
        XCTAssertEqual(captured[0].params["step_name"] as? String, "location")

        // Step 2 ("follow") -> Next -> emits step 2
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 3)
        XCTAssertEqual(captured.count, 2)
        XCTAssertEqual(captured[1].params["step"] as? Int, 2)
        XCTAssertEqual(captured[1].params["step_name"] as? String, "follow")

        // Step 3 ("alma_maters") -> Next -> emits step 3
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 4)
        XCTAssertEqual(captured.count, 3)
        XCTAssertEqual(captured[2].params["step"] as? Int, 3)
        XCTAssertEqual(captured[2].params["step_name"] as? String, "alma_maters")

        // Step 4 ("interests") -> Next -> emits step 4
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 5)
        XCTAssertEqual(captured.count, 4)
        XCTAssertEqual(captured[3].params["step"] as? Int, 4)
        XCTAssertEqual(captured[3].params["step_name"] as? String, "interests")

        // Step 5 (terminal step) does not advance or emit again
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 5)
        XCTAssertEqual(captured.count, 4)
    }

    func testStepEventRespectsAllowConsentGate() {
        let vm = OnboardingViewModel()

        // Unanswered (`nil`) and explicit decline (`.none`) must suppress onboarding_step
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 2)
        XCTAssertTrue(captured.isEmpty, "onboarding_step must stay behind Allow before consent is granted")

        TelemetryConsent.shared.set(.none)
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 3)
        XCTAssertTrue(captured.isEmpty, "onboarding_step must stay suppressed after Decline")

        // Once Allowed, Next emits the step just finished (step 3 -> "alma_maters")
        TelemetryConsent.shared.set(.analytics)
        vm.goNext()
        XCTAssertEqual(vm.currentStep, 4)
        XCTAssertEqual(captured.count, 1)
        XCTAssertEqual(captured[0].name, "onboarding_step")
        XCTAssertEqual(captured[0].params["step"] as? Int, 3)
        XCTAssertEqual(captured[0].params["step_name"] as? String, "alma_maters")
    }

    func testNoOnboardingStepIsEmittedOnAppearOrInitAnywhereInAppSources() throws {
        let iosRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let enumerator = try XCTUnwrap(FileManager.default.enumerator(at: iosRoot, includingPropertiesForKeys: nil))
        for case let fileURL as URL in enumerator where fileURL.pathExtension == "swift" {
            let content = try String(contentsOf: fileURL, encoding: .utf8)
            guard content.contains("trackOnboardingStep") || content.contains("\"onboarding_step\"") else { continue }
            let fileName = fileURL.lastPathComponent
            if fileName == "AnalyticsService.swift" || fileName == "AnalyticsPrivacy.swift" {
                continue
            }
            XCTAssertEqual(
                fileName,
                "OnboardingViewModel.swift",
                "Unexpected trackOnboardingStep call site in \(fileName)"
            )
            XCTAssertFalse(
                content.contains(".onAppear"),
                "OnboardingViewModel must not trigger step events in .onAppear"
            )
        }
    }
}
