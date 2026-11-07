import SwiftUI

/// #11666 Step E5 — Native Event-page Atlas live path:
/// - `resolveHeadlineObservedAt`: selects the observed-at clock for the Atlas
///   headline phase (`"Current win chance"` vs `"Last recorded win chance"`),
///   advancing when the live stream confirms a steady displayed price or admits
///   a one-stream blend preview, and falling back to `freshestSourceStamp` or
///   `currentOddsCapturedAt` when no accepted price clock is present.
/// - `tenthsPair`: formats complement probability pairs in tenths summing to
///   `100.0%` (`EventHeadlineTenths10090.pair`), matching web `tenthsPair`.
/// - `overlaidHeadlinePair`: overlays a one-stream `BlendPreviewState` onto an
///   `EventDetail` headline and resolves the displayed observation clock and
///   tenths pair.
/// - `ekgDraws` & `stepEkgTracker`: gates and steps the live EKG heartbeat trace
///   on confirmations, previews, and venue activity while hiding on final.
nonisolated enum EventAtlasLivePath11666 {

    struct HeadlineObservedAtInput: Equatable, Sendable {
        let acceptedPriceClock: Date?
        let confirmedAtShown: Date?
        var freshestSourceStamp: Date? = nil
        var currentOddsCapturedAt: Date? = nil
    }

    struct OverlaidHeadlineReading: Equatable, Sendable {
        let homeProbability: Double
        let awayProbability: Double?
        let homeTenthsText: String
        let awayTenthsText: String?
        let observedAt: Date?
        let isPreview: Bool
    }

    /// Selects the observed-at timestamp for the Atlas headline phase
    /// (`"Current win chance"` vs `"Last recorded win chance"`), matching web
    /// `resolveAtlasHeadlineObservedAt` (`frontend/lib/event/eventHeadlinePhase.ts`).
    ///
    /// When `acceptedPriceClock` is present, a fresher `confirmedAtShown`
    /// advances the clock (`max(acceptedPriceClock, confirmedAtShown)`). When
    /// `acceptedPriceClock` is nil, falls back to `freshestSourceStamp` and then
    /// `currentOddsCapturedAt`.
    static func resolveHeadlineObservedAt(_ input: HeadlineObservedAtInput) -> Date? {
        if let accepted = input.acceptedPriceClock {
            if let confirmed = input.confirmedAtShown {
                return max(accepted, confirmed)
            }
            return accepted
        }
        return input.freshestSourceStamp ?? input.currentOddsCapturedAt
    }

    /// Extracts the freshest `updatedAt` timestamp across `winProbabilitySources`.
    static func freshestSourceTimestamp(in sources: [String: WinProbSource]?) -> Date? {
        guard let sources else { return nil }
        return sources.values.compactMap { $0.updatedAt?.asDate }.max()
    }

    /// Formats a complement probability pair in tenths of a point summing to
    /// `100.0%` (`EventHeadlineTenths10090.pair`).
    static func tenthsPair(home: Double, away: Double?) -> (home: String, away: String?) {
        EventHeadlineTenths10090.pair(home: home, away: away)
    }

    /// Overlays an optional one-stream `BlendPreviewState` onto `event` and
    /// computes the resulting tenths headline pair (withholding the away
    /// complement on draw-priced sports via `DrawPricedWinner.printablePair`),
    /// observation clock, and whether the preview is actively displayed.
    static func overlaidHeadlineReading(
        event: EventDetail,
        preview: BlendPreviewState?,
        now: TimeInterval
    ) -> OverlaidHeadlineReading? {
        let isPreview = BlendPreview.displayed(preview, held: event, now: now) != nil
        let overlaid = BlendPreview.overlay(event, preview, now: now)
        let rawHome = overlaid.heroProbability ?? overlaid.currentOdds?.homeProbability
        let rawAway = overlaid.heroProbabilityAway ?? overlaid.currentOdds?.awayProbability
        guard let printable = DrawPricedWinner.printablePair(
            away: rawAway,
            home: rawHome,
            sport: event.sport
        ), printable.home.isFinite else {
            return nil
        }
        let pair = tenthsPair(home: printable.home, away: printable.away)
        let observedAt = BlendPreview.displayedObservedAt(
            preview,
            held: event,
            now: now,
            committed: event.heroProbabilityObservedAt?.asDate
        )
        return OverlaidHeadlineReading(
            homeProbability: printable.home,
            awayProbability: printable.away,
            homeTenthsText: pair.home,
            awayTenthsText: pair.away,
            observedAt: observedAt,
            isPreview: isPreview
        )
    }

    /// Overlays a one-stream `BlendPreviewState` onto the chart's live blend
    /// frames (`BlendPreview.chartFrames`).
    static func overlaidChartFrames(
        frames: [LiveBlendPoint],
        history: EventHistoryResponse?,
        preview: BlendPreviewState?,
        event: EventDetail?,
        now: TimeInterval
    ) -> [LiveBlendPoint] {
        BlendPreview.chartFrames(frames, history: history, state: preview, held: event, now: now)
    }

    /// Whether the EKG heartbeat draws on the Atlas headline row: live,
    /// unfinished, not venue-settled, and not an opening-line-only hero.
    static func ekgDraws(
        eventStatus: String?,
        finished: Bool,
        venueSettledVerdict: Bool,
        isOpeningLine: Bool
    ) -> Bool {
        EkgHeartbeat.isVisible(
            eventStatus: eventStatus,
            finished: finished,
            venueSettledVerdict: venueSettledVerdict,
            isOpeningLine: isOpeningLine
        )
    }

    /// Steps the EKG tracker on a live render observation at `now`.
    static func stepEkgTracker(
        _ tracker: EkgTracker,
        observation: EkgTracker.Observation,
        now: Date
    ) -> EkgTracker {
        tracker.stepped(observation, now: now)
    }
}
