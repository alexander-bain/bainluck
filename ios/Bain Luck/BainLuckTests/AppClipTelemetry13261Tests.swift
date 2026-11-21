import XCTest
@testable import Bain_Luck

/// `#13261` Row 15 — App Clip (`#12307`) telemetry strictly behind consent (`181-C`).
@MainActor
final class AppClipTelemetry13261Tests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!
    private var captured: [(name: String, params: [String: Any])] = []

    override func setUp() {
        super.setUp()
        suiteName = "clip-telemetry-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)!
        captured = []
        ClipTelemetry13261.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params))
        }
    }

    override func tearDown() {
        ClipTelemetry13261.eventEmitterForTests = nil
        if let suiteName {
            defaults?.removePersistentDomain(forName: suiteName)
        }
        defaults = nil
        suiteName = nil
        super.tearDown()
    }

    func testNothingSentWithoutAllowForAppClipEvents() {
        let game = SavedWidgetSubject10875(kind: .game, id: 14780576)

        XCTAssertFalse(ClipTelemetry13261.isConsentGranted(defaults: defaults), "Consent must default OFF")
        XCTAssertFalse(ClipTelemetry13261.recordOpen(subject: game, defaults: defaults))
        XCTAssertFalse(ClipTelemetry13261.recordAlertEnable(subject: game, defaults: defaults))
        XCTAssertFalse(ClipTelemetry13261.recordGetAppTap(subject: game, defaults: defaults))
        XCTAssertTrue(captured.isEmpty, "Must emit zero App Clip events when Allow is unset")

        ClipTelemetry13261.setConsentGranted(false, defaults: defaults)
        XCTAssertFalse(ClipTelemetry13261.recordOpen(subject: game, defaults: defaults))
        XCTAssertFalse(ClipTelemetry13261.recordAlertEnable(subject: game, defaults: defaults))
        XCTAssertFalse(ClipTelemetry13261.recordGetAppTap(subject: game, defaults: defaults))
        XCTAssertTrue(captured.isEmpty, "Must emit zero App Clip events when Allow is explicitly false")
    }

    func testAllThreeAppClipEventsEmitClosedEntryTypesAndPassPrivacySanitizer() throws {
        ClipTelemetry13261.setConsentGranted(true, defaults: defaults)
        let game = SavedWidgetSubject10875(kind: .game, id: 14780576)
        let market = SavedWidgetSubject10875(kind: .market, id: 52755659)

        XCTAssertTrue(ClipTelemetry13261.recordOpen(subject: game, defaults: defaults))
        XCTAssertTrue(ClipTelemetry13261.recordAlertEnable(subject: market, defaults: defaults))
        XCTAssertTrue(ClipTelemetry13261.recordGetAppTap(subject: nil, defaults: defaults))

        XCTAssertEqual(captured.count, 3)
        XCTAssertEqual(captured[0].name, "app_clip_open")
        XCTAssertEqual(captured[0].params["entry_type"] as? String, "game")
        XCTAssertEqual(captured[1].name, "app_clip_alert_enable")
        XCTAssertEqual(captured[1].params["entry_type"] as? String, "market")
        XCTAssertEqual(captured[2].name, "app_clip_get_app_tap")
        XCTAssertEqual(captured[2].params["entry_type"] as? String, "invalid")

        for item in captured {
            var dirty = item.params
            dirty["url"] = "https://www.bainluck.com/events/14780576?ref=secret"
            dirty["name"] = "Alex"
            dirty["query"] = "secret search"
            let clean = try XCTUnwrap(AnalyticsPrivacy.sanitize(event: item.name, parameters: dirty))
            XCTAssertEqual(clean["surface"] as? String, "app_clip")
            XCTAssertEqual(clean["entry_type"] as? String, item.params["entry_type"] as? String)
            XCTAssertNil(clean["url"])
            XCTAssertNil(clean["name"])
            XCTAssertNil(clean["query"])
        }
    }
}
