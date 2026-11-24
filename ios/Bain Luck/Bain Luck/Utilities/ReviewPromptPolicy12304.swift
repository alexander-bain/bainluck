import Foundation

/// #12304 — what the rating prompt knows when it decides. Read from the app's
/// own visit counters (`bainluck_install_date`, `bainluck_session_count`) and
/// the prompt's keys in `ReviewPromptSignals12304`.
nonisolated struct ReviewPromptState12304: Equatable, Sendable {
    var installDate: Date?
    var sessionCount: Int
    var lastAsked: Date?
    var lastAskedVersion: String?
    var currentVersion: String?
    var goodMomentsSinceAsk: Int
    var sessionHadTrouble: Bool
}

/// #12304 — when the app may ask for an App Store rating. Pure: the clock and
/// the counters come in, a yes or no goes out, and each rule is a test.
///
/// A yes only means "ask". Apple adds its own caps (three times in 365 days)
/// and may show nothing, so nothing here assumes the sheet appeared.
nonisolated struct ReviewPromptPolicy12304: Sendable {
    /// Never in a reader's first days.
    static let quietDaysAfterInstall = 3
    /// Never before the reader has opened the app this many times.
    static let minimumSessions = 5
    /// Never twice in a season.
    static let daysBetweenAsks = 120

    func shouldAsk(_ state: ReviewPromptState12304, now: Date, calendar: Calendar = .current) -> Bool {
        guard let installDate = state.installDate,
              let settled = calendar.date(byAdding: .day, value: Self.quietDaysAfterInstall, to: installDate),
              now >= settled else { return false }
        guard state.sessionCount >= Self.minimumSessions else { return false }
        if let lastAsked = state.lastAsked {
            guard let next = calendar.date(byAdding: .day, value: Self.daysBetweenAsks, to: lastAsked),
                  now >= next else { return false }
        }
        // Never twice for one version of the app, whatever the gap.
        if let version = state.currentVersion, version == state.lastAskedVersion { return false }
        // Only after something went well since the last ask.
        guard state.goodMomentsSinceAsk >= 1 else { return false }
        // Never in a run that showed the reader something going wrong.
        return !state.sessionHadTrouble
    }
}
