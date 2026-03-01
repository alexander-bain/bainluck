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

    // MARK: - User Identity

    nonisolated static func setUserId(_ userId: String?) {
        Analytics.setUserID(userId)
    }

    nonisolated static func setUserProperty(_ value: String?, forName name: String) {
        Analytics.setUserProperty(value, forName: name)
    }
}
