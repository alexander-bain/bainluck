import XCTest
@testable import Bain_Luck

/// Queue 311 Item A3 (ruling 007 / #1632) — the native consent gate.
///
/// These assert what the gate DID to the SDKs, not merely what it decided. A
/// consent test that only checks a computed Bool would have passed against the
/// code this replaced, which decided correctly in exactly zero places because
/// it had no decision to make.
final class TelemetryConsentTests: XCTestCase {

    /// Records every SDK call so a test can assert the gate reached the SDK,
    /// and — more importantly — that it did NOT.
    final class SpySink: TelemetrySink {
        var analyticsEnabled: [Bool] = []
        var crashlyticsEnabled: [Bool] = []
        var resetCount = 0

        func setAnalyticsCollectionEnabled(_ enabled: Bool) { analyticsEnabled.append(enabled) }
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) { crashlyticsEnabled.append(enabled) }
        func resetAnalyticsData() { resetCount += 1 }
    }

    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "TelemetryConsentTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        super.tearDown()
    }

    private func makeConsent(_ sink: SpySink) -> TelemetryConsent {
        TelemetryConsent(defaults: defaults, sink: sink)
    }

    // MARK: - Deny by default

    func testNoChoiceIsADenial() {
        // Not a soft default awaiting an answer: a first launch must behave
        // exactly like an explicit refusal.
        XCTAssertFalse(TelemetryConsent.isAnalyticsGranted(nil))
        XCTAssertEqual(TelemetryConsent.decide(nil), .nothing)
    }

    func testExplicitNoneIsADenial() {
        XCTAssertFalse(TelemetryConsent.isAnalyticsGranted(.none))
        XCTAssertEqual(TelemetryConsent.decide(.none), .nothing)
    }

    func testBothGrantLevelsEnableEveryProvider() {
        for level in [ConsentLevel.all, .analytics] {
            let decision = TelemetryConsent.decide(level)
            XCTAssertTrue(decision.firebaseAnalytics, "\(level) should permit analytics")
            XCTAssertTrue(decision.crashlytics, "\(level) should permit crashlytics")
        }
    }

    func testFirstLaunchDisablesCollectionAtTheSDK() {
        let sink = SpySink()
        let consent = makeConsent(sink)

        consent.initialize()

        XCTAssertEqual(sink.analyticsEnabled, [false])
        XCTAssertEqual(sink.crashlyticsEnabled, [false])
        XCTAssertFalse(consent.isGranted)
        XCTAssertTrue(consent.needsChoice)
    }

    // MARK: - Grant, persistence, revocation

    func testGrantEnablesCollection() {
        let sink = SpySink()
        let consent = makeConsent(sink)
        consent.initialize()

        let persistence = consent.set(.analytics)

        XCTAssertEqual(persistence, .saved)
        XCTAssertTrue(consent.isGranted)
        XCTAssertEqual(sink.analyticsEnabled.last, true)
        XCTAssertEqual(sink.crashlyticsEnabled.last, true)
    }

    func testChoiceSurvivesRelaunch() {
        let first = makeConsent(SpySink())
        first.initialize()
        first.set(.analytics)

        // A brand new authority over the same store — i.e. the next launch.
        let sink = SpySink()
        let relaunched = makeConsent(sink)
        XCTAssertEqual(relaunched.initialize(), .analytics)
        XCTAssertTrue(relaunched.isGranted)
        XCTAssertFalse(relaunched.needsChoice)
        // The grant is re-applied on launch rather than assumed: the SDK flags
        // persist independently, so an unapplied launch could inherit a stale one.
        XCTAssertEqual(sink.analyticsEnabled, [true])
    }

    func testRefusalSurvivesRelaunchAndIsNotReAsked() {
        let first = makeConsent(SpySink())
        first.initialize()
        first.set(.none)

        let relaunched = makeConsent(SpySink())
        XCTAssertEqual(relaunched.initialize(), ConsentLevel.none)
        XCTAssertFalse(relaunched.isGranted)
        // The distinction that matters for the prompt: a refusal is a CHOICE,
        // so it must not re-nag, while no-choice must ask.
        XCTAssertFalse(relaunched.needsChoice)
    }

    func testRevocationDisablesCollectionAndClearsCollectedData() {
        let sink = SpySink()
        let consent = makeConsent(sink)
        consent.initialize()
        consent.set(.analytics)
        let resetsBefore = sink.resetCount

        consent.set(.none)

        XCTAssertFalse(consent.isGranted)
        XCTAssertEqual(sink.analyticsEnabled.last, false)
        XCTAssertEqual(sink.crashlyticsEnabled.last, false)
        // "No" reaches backwards as well as forwards — the identifiers already
        // on device are dropped, not merely frozen.
        XCTAssertEqual(sink.resetCount, resetsBefore + 1)
    }

    func testRegrantAfterRevocationWorks() {
        let sink = SpySink()
        let consent = makeConsent(sink)
        consent.initialize()
        consent.set(.analytics)
        consent.set(.none)
        consent.set(.all)

        XCTAssertTrue(consent.isGranted)
        XCTAssertEqual(sink.analyticsEnabled.last, true)
    }

    // MARK: - Web parity

    func testLevelVocabularyMatchesTheWeb() {
        // `lib/analytics/telemetryConsent.ts` persists exactly these strings. A
        // rename on either side silently desyncs the two surfaces' meaning of a
        // stored value, which is the kind of drift that shows up as a privacy
        // incident rather than a bug.
        XCTAssertEqual(Set(ConsentLevel.allCases.map(\.rawValue)), ["all", "analytics", "none"])
    }

    func testUnparseableStoredValueIsTreatedAsNoChoice() {
        // Web ignores a corrupted value rather than coercing it. Coercing to a
        // grant would be worse, but coercing to a denial would also flip a
        // choice the user never made — so it reads as "not yet asked".
        defaults.set("garbage", forKey: TelemetryConsent.storageKey)

        let consent = makeConsent(SpySink())

        XCTAssertNil(consent.initialize())
        XCTAssertFalse(consent.isGranted)
        XCTAssertTrue(consent.needsChoice)
    }
}
