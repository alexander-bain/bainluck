import Foundation

/// Client payload submitted when a user files an in-app bug report.
nonisolated struct BugReportSubmission: Codable, Sendable {
    let description: String?
    let screenshotBase64: String?
    let appState: [String: String]?
    let notifyOnFix: Bool
}

/// Backend acknowledgment for a submitted bug report.
nonisolated struct BugReportResponse: Decodable, Sendable {
    let status: String
    let id: Int
}

// MARK: - Local Draft Persistence

/// Manages saving and retrying failed bug report submissions.
enum BugReportDraftStore {
    private static let draftsKey = "bainluck_bug_report_drafts"
    private static let maxDrafts = 5

    /// Save a failed submission locally for later retry.
    static func saveDraft(_ submission: BugReportSubmission) {
        var drafts = loadDrafts()
        drafts.append(submission)
        // Keep only the most recent drafts to avoid unbounded storage growth
        if drafts.count > maxDrafts {
            drafts = Array(drafts.suffix(maxDrafts))
        }
        if let data = try? JSONEncoder().encode(drafts) {
            UserDefaults.standard.set(data, forKey: draftsKey)
        }
    }

    /// Load all saved drafts.
    static func loadDrafts() -> [BugReportSubmission] {
        guard let data = UserDefaults.standard.data(forKey: draftsKey),
              let drafts = try? JSONDecoder().decode([BugReportSubmission].self, from: data) else {
            return []
        }
        return drafts
    }

    /// Remove all saved drafts (after successful retry).
    static func clearDrafts() {
        UserDefaults.standard.removeObject(forKey: draftsKey)
    }

    /// Remove a specific draft by index.
    static func removeDraft(at index: Int) {
        var drafts = loadDrafts()
        guard index < drafts.count else { return }
        drafts.remove(at: index)
        if drafts.isEmpty {
            clearDrafts()
        } else if let data = try? JSONEncoder().encode(drafts) {
            UserDefaults.standard.set(data, forKey: draftsKey)
        }
    }

    /// Whether there are unsent drafts waiting to be retried.
    static var hasPendingDrafts: Bool {
        !loadDrafts().isEmpty
    }

    /// Number of pending drafts.
    static var pendingCount: Int {
        loadDrafts().count
    }
}
