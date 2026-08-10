import FirebaseAnalytics
import FirebaseCrashlytics
import Foundation

/// The production `TelemetrySink` — the only place a consent decision is
/// translated into Firebase SDK calls (Queue 311 Item A3 / #1632).
///
/// Split out from `TelemetryConsent` so the authority's decision logic can be
/// unit-tested against a spy without linking a live Firebase. Everything here
/// is a one-line SDK forward: if this file needs logic, the logic belongs in
/// the authority instead.
///
/// Both toggles are runtime overrides of the plist defaults
/// (`FIREBASE_ANALYTICS_COLLECTION_ENABLED = NO`,
/// `FirebaseCrashlyticsCollectionEnabled = NO`) and, like those defaults, they
/// persist across launches inside the SDKs. That is why the authority applies
/// the decision on EVERY `initialize()` rather than only on a change: a stale
/// enabled-flag left behind by a previous install state must be corrected at
/// launch, not inherited.
final class FirebaseTelemetrySink: TelemetrySink {
    func setAnalyticsCollectionEnabled(_ enabled: Bool) {
        Analytics.setAnalyticsCollectionEnabled(enabled)
    }

    func setCrashlyticsCollectionEnabled(_ enabled: Bool) {
        Crashlytics.crashlytics().setCrashlyticsCollectionEnabled(enabled)
    }

    func resetAnalyticsData() {
        Analytics.resetAnalyticsData()
    }
}
