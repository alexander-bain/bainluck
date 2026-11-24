import Foundation

/// #12304 — the counters behind the rating prompt, kept in UserDefaults beside
/// the app's own visit counters, plus this run's "something went wrong" flag.
///
/// A good moment is a followed game reaching its final (the Live Activity's
/// end) or the reader coming back on a third day of use, and every later day.
@MainActor final class ReviewPromptSignals12304 {
    static let shared = ReviewPromptSignals12304()

    enum Key {
        static let lastAsked = "review_prompt_12304_last_asked"
        static let lastVersion = "review_prompt_12304_last_version"
        static let goodMoments = "review_prompt_12304_good_moments"
        static let activeDays = "review_prompt_12304_active_days"
        static let lastActiveDay = "review_prompt_12304_last_active_day"
        // The app's own counters, written in `Bain_LuckApp.init`.
        static let installDate = "bainluck_install_date"
        static let sessionCount = "bainluck_session_count"
    }

    private let defaults: UserDefaults
    private(set) var sessionHadTrouble = false
    private(set) var askedThisRun = false

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func recordGoodMoment() {
        defaults.set(defaults.integer(forKey: Key.goodMoments) + 1, forKey: Key.goodMoments)
    }

    /// The reader saw something fail ("Update interrupted"); this run never asks.
    func noteTrouble() {
        sessionHadTrouble = true
    }

    /// Counts distinct days of use. The third day, and every one after it, is a
    /// good moment: the reader keeps coming back.
    func recordActiveDay(now: Date, calendar: Calendar = .current) {
        let today = calendar.startOfDay(for: now)
        if let last = defaults.object(forKey: Key.lastActiveDay) as? Date,
           calendar.isDate(last, inSameDayAs: today) { return }
        defaults.set(today, forKey: Key.lastActiveDay)
        let days = defaults.integer(forKey: Key.activeDays) + 1
        defaults.set(days, forKey: Key.activeDays)
        if days >= 3 { recordGoodMoment() }
    }

    func state(currentVersion: String?) -> ReviewPromptState12304 {
        ReviewPromptState12304(
            installDate: defaults.object(forKey: Key.installDate) as? Date,
            sessionCount: defaults.integer(forKey: Key.sessionCount),
            lastAsked: defaults.object(forKey: Key.lastAsked) as? Date,
            lastAskedVersion: defaults.string(forKey: Key.lastVersion),
            currentVersion: currentVersion,
            goodMomentsSinceAsk: defaults.integer(forKey: Key.goodMoments),
            sessionHadTrouble: sessionHadTrouble)
    }

    /// Spends the good moments: the next ask needs a new one.
    func markAsked(now: Date, version: String?) {
        defaults.set(now, forKey: Key.lastAsked)
        defaults.set(version, forKey: Key.lastVersion)
        defaults.set(0, forKey: Key.goodMoments)
        askedThisRun = true
    }
}
