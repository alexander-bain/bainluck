import FirebaseAnalytics
import Foundation

/// Thin wrapper around Firebase Analytics matching the web GA4 taxonomy.
enum AnalyticsService {
    // MARK: - Screen Tracking

    nonisolated static func trackScreen(name: String, type: String) {
        Analytics.logEvent(AnalyticsEventScreenView, parameters: [
            AnalyticsParameterScreenName: name,
            "page_type": type,
        ])
    }

    // MARK: - Event Card

    nonisolated static func trackEventCardClick(eventId: Int, sport: String?, status: String?) {
        Analytics.logEvent("event_card_click", parameters: [
            "event_id": eventId,
            "sport": sport ?? "unknown",
            "status": status ?? "unknown",
        ])
    }

    // MARK: - Event Detail

    nonisolated static func trackEventDetailView(eventId: Int, sport: String?, entryMethod: String = "tap") {
        Analytics.logEvent("event_detail_view", parameters: [
            "event_id": eventId,
            "sport": sport ?? "unknown",
            "entry_method": entryMethod,
        ])
    }

    // MARK: - Search

    nonisolated static func trackSearch(query: String, resultsCount: Int) {
        Analytics.logEvent(AnalyticsEventSearch, parameters: [
            AnalyticsParameterSearchTerm: query,
            "results_count": resultsCount,
        ])
    }

    // MARK: - Auth

    nonisolated static func trackLogin(method: String) {
        Analytics.logEvent(AnalyticsEventLogin, parameters: [
            AnalyticsParameterMethod: method,
        ])
    }

    nonisolated static func trackSignUp(method: String) {
        Analytics.logEvent(AnalyticsEventSignUp, parameters: [
            AnalyticsParameterMethod: method,
        ])
    }

    nonisolated static func trackLogout() {
        Analytics.logEvent("logout", parameters: nil)
    }

    // MARK: - Onboarding

    nonisolated static func trackOnboardingStep(step: Int, stepName: String) {
        Analytics.logEvent("onboarding_step", parameters: [
            "step": step,
            "step_name": stepName,
        ])
    }

    nonisolated static func trackOnboardingComplete(teamsCount: Int) {
        Analytics.logEvent("onboarding_complete", parameters: [
            "teams_count": teamsCount,
        ])
    }

    // MARK: - Chart

    nonisolated static func trackChartTimeRange(eventId: Int, range: String) {
        Analytics.logEvent("chart_time_range", parameters: [
            "event_id": eventId,
            "range": range,
        ])
    }

    // MARK: - Futures

    nonisolated static func trackFuturesDetailView(marketId: Int, category: String?) {
        Analytics.logEvent("futures_detail_view", parameters: [
            "market_id": marketId,
            "category": category ?? "unknown",
        ])
    }

    // MARK: - Discover (event names match web GA4 taxonomy)

    nonisolated static func trackDiscoverCardImpression(
        itemId: String,
        itemType: String,
        category: String,
        rank: Int,
        score: Int?
    ) {
        Analytics.logEvent("feed_card_impression", parameters: [
            "item_id": itemId,
            "item_type": itemType,
            "category": category,
            "position": rank,
            "score": score ?? 0,
            "surface": "discover",
        ])
    }

    nonisolated static func trackDiscoverCardAction(
        action: String,
        itemId: String,
        itemType: String,
        category: String,
        source: String
    ) {
        Analytics.logEvent("feed_card_action", parameters: [
            "action": action,
            "item_id": itemId,
            "item_type": itemType,
            "category": category,
            "source": source,
            "surface": "discover",
        ])
    }

    nonisolated static func trackDiscoverCategoryFilter(category: String) {
        Analytics.logEvent("filter_category", parameters: [
            "action": "select",
            "category": category,
            "surface": "discover",
        ])
    }

    nonisolated static func trackDiscoverTuningReset(affinityCount: Int) {
        Analytics.logEvent("discover_tuning_reset", parameters: [
            "affinity_count": affinityCount,
            "surface": "discover",
        ])
    }

    /// L2-215 Item 1 (#1486): an empty predictive envelope (concept/bundle/tournament/
    /// futures with neither a renderable probability nor an authoritative result) was
    /// failed closed at the client eligibility boundary. Carries ONLY the card type,
    /// the machine reason, a count, and the surface — no ids, names, sessions, or
    /// market text.
    nonisolated static func trackFeedEnvelopeSuppressed(type: String, reason: String, count: Int, surface: String) {
        Analytics.logEvent("feed_card_suppressed", parameters: [
            "card_type": type,
            "suppression_reason": reason,
            "count": count,
            "surface": surface,
        ])
    }

    // MARK: - Discover Feed Latency (#1465 — stale-while-revalidate last-good cache)

    /// A stale-while-revalidate cache observation from `DiscoverViewModel`.
    /// Isolates perceived time-to-first-card (cache decode/render) from the server
    /// round-trip so the client win is measurable without implying the backend
    /// cold miss (#1459) is fixed. Carries no PII and no card content.
    nonisolated static func trackDiscoverFeedCache(_ telemetry: DiscoverFeedTelemetry) {
        Analytics.logEvent("discover_feed_cache", parameters: [
            "outcome": telemetry.outcome.rawValue,
            "cache_decode_ms": telemetry.cacheDecodeMs ?? -1,
            "network_ms": telemetry.networkMs ?? -1,
            "item_count": telemetry.itemCount,
            "cache_age_seconds": telemetry.cacheAgeSeconds ?? -1,
            // Latency-attribution milestones (L2-201 / L2-206 · #1472). -1 marks a
            // stage that did not run for this observation. `data_ready_ms` is the
            // model-assignment milestone (NOT the on-screen first render — that is
            // the separate `discover_feed_first_render` event). Opaque status only.
            "auth_ready_ms": telemetry.authReadyMs ?? -1,
            "backend_elapsed_ms": telemetry.backendElapsedMs ?? -1,
            "merge_ms": telemetry.mergeMs ?? -1,
            "data_ready_ms": telemetry.dataReadyMs ?? -1,
            "cache_store_ms": telemetry.cacheStoreMs ?? -1,
            "cache_status": telemetry.cacheStatus ?? "unknown",
            "app_build": appBuild(),
            "surface": "discover",
        ])
    }

    /// The on-screen first-render milestone (L2-206 / #1472, Item 3): the elapsed
    /// time from Discover load start to the FIRST eligible card's `onAppear`. This
    /// is deliberately distinct from `data_ready_ms` (model assignment) so a fast
    /// data-ready can never be mistaken for a fast first paint. Emitted once per
    /// load by the view. Carries no PII, token, or market content.
    nonisolated static func trackDiscoverFirstRender(
        firstRenderMs: Double,
        fromCache: Bool,
        itemCount: Int
    ) {
        Analytics.logEvent("discover_feed_first_render", parameters: [
            "first_render_ms": firstRenderMs,
            "from_cache": fromCache,
            "item_count": itemCount,
            "app_build": appBuild(),
            "surface": "discover",
        ])
    }

    /// Non-PII build reachability tag for latency traces (L2-206 Item 3): the
    /// short version + build number (e.g. `1.4.2 (231)`), so a trace can be mapped
    /// to the exact archive/TestFlight build it came from. No user data.
    nonisolated static func appBuild() -> String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(short) (\(build))"
    }

    /// The server-side split of an offset-0 feed fetch, milestone-attributed
    /// (L2-201 / #1472): local auth-token resolution, network round-trip (TTFB +
    /// download), client payload decode, the backend's own build time
    /// (`X-Feed-Elapsed-Ms`), the cache status header (`X-Feed-Cache`), and the
    /// response byte size. Emitted from `APIClient` (#1465). Carries no PII,
    /// token, payload, or market question. Any missing value is reported as -1.
    nonisolated static func trackDiscoverFeedNetwork(
        networkMs: Double,
        decodeMs: Double,
        itemCount: Int,
        authReadyMs: Double? = nil,
        backendElapsedMs: Double? = nil,
        responseBytes: Int? = nil,
        cacheStatus: String? = nil,
        cacheStoreMs: Double? = nil
    ) {
        Analytics.logEvent("discover_feed_network", parameters: [
            "network_ms": networkMs,
            "decode_ms": decodeMs,
            "item_count": itemCount,
            "auth_ready_ms": authReadyMs ?? -1,
            "backend_elapsed_ms": backendElapsedMs ?? -1,
            "response_bytes": responseBytes ?? -1,
            // Cache-store time is measured off the first-card path and reported for
            // observability only (L2-206 Item 2/3); -1 when not yet measured.
            "cache_store_ms": cacheStoreMs ?? -1,
            "cache_status": cacheStatus ?? "unknown",
            "app_build": appBuild(),
            "surface": "discover",
        ])
    }

    // MARK: - Sports Feed Latency (L2-207 / #1480 — progressive first-card)

    /// One progressive-load milestone for the native Sports tab. The Sports tab
    /// issues three independent requests (main fast `mode=sports` feed, events
    /// backfill, grouped futures); each reports its data-ready under a stable
    /// `stage` label (`sports_main` / `sports_events_backfill` / `sports_grouped`)
    /// so first paint (the main stage) can be told apart from the siblings that
    /// merge in afterward. `first_real_card_ms` is only set on the main stage — the
    /// moment the skeleton is removed. Carries no PII, token, session, market text,
    /// or raw query — only opaque timings, a stage label, and a count.
    nonisolated static func trackSportsFeedStage(_ stage: SportsFeedStage) {
        Analytics.logEvent("sports_feed_stage", parameters: [
            "stage": stage.kind.rawValue,
            "data_ready_ms": stage.dataReadyMs,
            "item_count": stage.itemCount,
            "success": stage.success,
            "app_build": appBuild(),
            "surface": "sports",
        ])
    }

    /// The on-screen first-render milestone for the native Sports tab (L2-209 Item 2
    /// / C68). Deliberately distinct from `sports_feed_stage`'s `data_ready_ms`
    /// (model assignment): this fires from the FIRST renderable Sports card's SwiftUI
    /// appearance, once per load, and NEVER for an empty successful main — so it
    /// reflects real first paint rather than a fast model assignment. No PII.
    nonisolated static func trackSportsFirstRender(
        firstRenderMs: Double,
        itemCount: Int
    ) {
        Analytics.logEvent("sports_feed_first_render", parameters: [
            "first_render_ms": firstRenderMs,
            "item_count": itemCount,
            "app_build": appBuild(),
            "surface": "sports",
        ])
    }

    // MARK: - My Stuff Latency (L2-217 / C88 — identity boundary + first team card)

    /// One My Stuff load milestone. `required_data_ready` is the REQUIRED team
    /// feed's model assignment; `optional_merge` is the supplemental team-futures
    /// section landing afterward. Neither is a first render — that is the separate,
    /// view-driven `my_stuff_first_render` event — so a fast model assignment can
    /// never be read as a fast first paint. `-1` marks a stage that did not run or
    /// is not separately measurable. Carries no uid, email, token, session id,
    /// item id, or market text; the outcome class comes from a closed enum.
    nonisolated static func trackMyStuffStage(_ stage: MyStuffLoadStage) {
        Analytics.logEvent("my_stuff_load", parameters: [
            "stage": stage.kind.rawValue,
            "auth_ready_ms": stage.authReadyMs,
            "network_ms": stage.networkMs,
            // Not separately measurable from the view model — reported as -1 rather
            // than guessed, matching the Discover/Sports rails' convention.
            "backend_elapsed_ms": -1,
            "decode_ms": -1,
            "required_data_ready_ms": stage.requiredDataReadyMs,
            "first_render_ms": -1,
            "cache_outcome": stage.cacheOutcome,
            "cache_age_seconds": stage.cacheAgeSeconds,
            "item_count": stage.itemCount,
            "app_build": appBuild(),
            "surface": "my_stuff",
            "outcome_class": stage.outcomeClass.rawValue,
        ])
    }

    /// The on-screen first-render milestone for My Stuff (L2-217 Item 3 / C88):
    /// the FIRST real team card's SwiftUI appearance, once per render generation.
    /// It NEVER fires for a model assignment, an empty success, a cancellation, or
    /// a superseded identity — the view model stamps no render token in those
    /// cases, so there is nothing to emit. No PII.
    nonisolated static func trackMyStuffFirstRender(
        firstRenderMs: Double,
        itemCount: Int,
        fromCache: Bool
    ) {
        Analytics.logEvent("my_stuff_first_render", parameters: [
            "first_render_ms": firstRenderMs,
            "item_count": itemCount,
            "from_cache": fromCache,
            "app_build": appBuild(),
            "surface": "my_stuff",
        ])
    }

    // MARK: - Predictions

    nonisolated static func trackPredictionSubmit(
        marketId: Int,
        guess: String,
        threshold: Int,
        actualProbability: Double,
        correct: Bool,
        contentType: String,
        category: String?
    ) {
        Analytics.logEvent("prediction_submit", parameters: [
            "market_id": marketId,
            "guess": guess,
            "threshold": threshold,
            "actual_probability": actualProbability,
            "correct": correct,
            "content_type": contentType,
            "category": category ?? "unknown",
            "surface": "discover",
        ])
    }

    // MARK: - Onboarding Lifecycle

    nonisolated static func trackOnboardingStart(entryPoint: String) {
        Analytics.logEvent("onboarding_start", parameters: [
            "entry_point": entryPoint,
        ])
    }

    nonisolated static func trackOnboardingSkip(lastStep: Int, lastStepName: String) {
        Analytics.logEvent("onboarding_skip", parameters: [
            "last_step_completed": lastStep,
            "last_step_name": lastStepName,
        ])
    }

    // MARK: - Search

    nonisolated static func trackSearchResultClick(query: String, resultType: String, resultId: String, position: Int) {
        Analytics.logEvent("search_result_click", parameters: [
            "query": query,
            "result_type": resultType,
            "result_id": resultId,
            "position": position,
        ])
    }

    // MARK: - Navigation

    nonisolated static func trackNavigation(fromPage: String, toPage: String) {
        Analytics.logEvent("navigation_click", parameters: [
            "click_type": "nav_tab",
            "from_page": fromPage,
            "to_page": toPage,
        ])
    }

    // MARK: - Return Visit

    nonisolated static func trackReturnVisit(daysSinceLast: Int, sessionNumber: Int) {
        Analytics.logEvent("return_visit", parameters: [
            "days_since_last": daysSinceLast,
            "session_number": sessionNumber,
        ])
    }

    // MARK: - User Identity

    nonisolated static func setUserId(_ userId: String?) {
        Analytics.setUserID(userId)
    }

    nonisolated static func setUserProperty(_ value: String?, forName name: String) {
        Analytics.setUserProperty(value, forName: name)
    }
}
