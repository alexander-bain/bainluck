import XCTest

/// #10543 — the iPhone app must declare `aps-environment`, the iOS key, or
/// the signed app carries no push entitlement: ActivityKit then issues no push
/// token, a Live Activity never registers with the server and goes stale once
/// the app closes. `com.apple.developer.aps-environment` is the macOS spelling;
/// signed into iPhone builds it was dropped (TestFlight 1.0.5 (101) shipped with
/// neither key, though its App Store profile allows `aps-environment = production`).
final class PushEntitlement10543Tests: XCTestCase {

    private func entitlements(_ name: String) throws -> [String: Any] {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/\(name)")
        let data = try Data(contentsOf: url)
        return try XCTUnwrap(PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any])
    }

    func testTheIPhoneAppDeclaresTheIOSPushKey() throws {
        let iOS = try entitlements("Bain Luck.entitlements")
        XCTAssertEqual(iOS["aps-environment"] as? String, "production")
        XCTAssertNil(iOS["com.apple.developer.aps-environment"], "the macOS key is not read on iPhone")
    }

    func testTheMacAppKeepsTheMacPushKey() throws {
        let macOS = try entitlements("Bain Luck-macOS.entitlements")
        XCTAssertEqual(macOS["com.apple.developer.aps-environment"] as? String, "production")
    }
}
