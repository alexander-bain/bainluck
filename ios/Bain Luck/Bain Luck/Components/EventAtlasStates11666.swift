import SwiftUI

/// #11666 (Step E4) — Shared event-page Atlas state vocabulary and helpers on iOS,
/// matching the shipped web E4 contract (#11974 / PR #12143) behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
///
/// Key guarantees:
/// 1. Shared state wording matches the one-settled-language and Ruling 138
///    probability-first contracts:
///    - `"Loading"`, `"Update interrupted"`, `"Postponed"`,
///      `"Ended · no winner"` (`EventState.venueClosedNoWinnerLabel` — never
///      the betting word `"Void"`), `"No recent probability"`,
///      `"No probability yet"` (never the banned `"price"` stem),
///      `"✓ Won"`, `"✗ Lost"`, `"Pending"`.
/// 2. In `AllMarketsCatalogView9483`, a stale live outcome (`absence == .stale`)
///    prints `"No recent probability"` (`EventAtlasStates11666.noRecentPrice`)
///    when Atlas is enabled, while closed periods (`"Period finished"`) and
///    non-stale unavailable rows (`"Probability unavailable"`) keep their
///    non-stale strings.
/// 3. In `SpecialEventMarketsView`, settled outcome verdicts print `"✓ Won"` and
///    `"✗ Lost"` when Atlas is enabled, and multi-venue disagreement resolves to
///    `"Pending"`.
/// 4. In `EventDetailView`, loading and missing probability (`"No recent probability"`
///    once started vs `"No probability yet"` pregame) render the shared Atlas
///    state copy when `ReleaseSurfaces.isEventPageAtlasEnabled()` is true, while
///    states that `StatusBadge` three points above already speaks (`Ended · no winner`,
///    `Postponed`, `Canceled`, `No result reported`) return `nil` so the card
///    never draws two chips making one claim.
nonisolated enum EventAtlasStates11666 {

    static let loading = "Loading"
    static let updateInterrupted = "Update interrupted"
    static let postponed = "Postponed"
    static let voided = EventState.venueClosedNoWinnerLabel
    static let noRecentPrice = "No recent probability"
    static let noPriceYet = "No probability yet"
    static let won = "Won"
    static let lost = "Lost"
    static let wonWithCheck = "✓ Won"
    static let lostWithCross = "✗ Lost"
    static let pending = "Pending"
    static let resultNotConfirmed = "Result not confirmed"
    static let resultUnavailable = "Result unavailable"
    static let independentChancesLabel = "Independent chances · do not add to 100"

    /// Maps `LiveUpdateStatus` to the shared Atlas connection status label.
    static func connectionStatusLabel(
        for status: LiveUpdateStatus,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> String? {
        switch status {
        case .hidden:
            return nil
        case .awaitingUpdate:
            return status.title
        case .interrupted:
            return atlasEnabled ? updateInterrupted : status.title
        case .live, .autoRefresh:
            return status.title
        }
    }

    /// Resolves the hero state label when an event has no printable probability
    /// under `ReleaseSurfaces.isEventPageAtlasEnabled()`.
    ///
    /// Returns `nil` whenever `StatusBadge` three points above already speaks the
    /// event's terminal or stopped state (`isFinished`, `showsVenueSettledVerdict`,
    /// `showsVenueClosedNoWinner`, or `isSuspendedAndStarted`), preventing duplicate
    /// or conflicting state chips on one hero card.
    static func heroStateLabel(
        status: String?,
        commenceTime: Date?,
        authorityPeriod: String?,
        venueSettled: Bool?,
        venueClosedNoWinner: Bool?,
        hasCurrentOdds: Bool,
        now: Date = Date()
    ) -> String? {
        if EventState.isFinished(status) {
            return nil
        }
        if EventState.showsVenueSettledVerdict(
            status,
            venueSettled: venueSettled,
            commenceTime: commenceTime,
            now: now
        ) {
            return nil
        }
        if EventState.showsVenueClosedNoWinner(
            status,
            venueSettled: venueSettled,
            venueClosedNoWinner: venueClosedNoWinner,
            commenceTime: commenceTime,
            now: now
        ) {
            return nil
        }
        if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime, now: now) {
            return nil
        }
        guard !hasCurrentOdds else { return nil }
        let started = status == "live" || EventState.hasStarted(commenceTime: commenceTime, now: now)
        return started ? noRecentPrice : noPriceYet
    }

    /// Formats a single `OutcomeVerdict` in the shared Atlas vocabulary (`"✓ Won"` / `"✗ Lost"`).
    static func verdictLabel(
        _ verdict: OutcomeVerdict,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> String {
        guard atlasEnabled else { return verdict.label }
        switch verdict {
        case .won:
            return wonWithCheck
        case .lost:
            return lostWithCross
        }
    }

    /// Resolves a row's settlement display across one or more authoritative venue verdicts.
    /// When multiple venues disagree on the same outcome (e.g. `.won` and `.lost`),
    /// returns `"Pending"` (`EventAtlasStates11666.pending`).
    static func verdictDisplay(
        verdicts: [OutcomeVerdict],
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> String? {
        guard let first = verdicts.first else { return nil }
        let allAgree = verdicts.allSatisfy { $0 == first }
        guard allAgree else { return pending }
        return verdictLabel(first, atlasEnabled: atlasEnabled)
    }
}

/// Renders the shared Atlas hero state label (`Postponed`, `Void`, `No recent probability`,
/// or `No price yet`) on `EventDetailView` when `ReleaseSurfaces.isEventPageAtlasEnabled()` is true.
struct EventAtlasHeroStateLabelView11666: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DS.textSecondaryReadable)
            .multilineTextAlignment(.center)
            .accessibilityIdentifier(
                label == EventAtlasStates11666.noRecentPrice
                    ? "atlas-no-recent-probability"
                    : "event-atlas-state-label-11666"
            )
    }
}
