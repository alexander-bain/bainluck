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

extension BugReportSubmission {
    /// Identity used to de-duplicate queued drafts.
    ///
    /// Deliberately NOT the whole payload: `app_state` carries a `timestamp`
    /// regenerated on every build, so two saves of the same report would
    /// otherwise queue twice and submit twice (#1847 defect C's repair path
    /// makes a double-save reachable — Save for Later after a Try Again that
    /// also failed).
    var draftKey: String {
        let page = appState?["current_page"] ?? ""
        return "\(description ?? "")|\(page)|\(screenshotBase64?.count ?? 0)"
    }
}

// MARK: - Local Draft Persistence

/// Manages saving and retrying failed bug report submissions.
enum BugReportDraftStore {
    private static let draftsKey = "bainluck_bug_report_drafts"
    private static let maxDrafts = 5

    /// Injectable for tests; production always uses `.standard`.
    nonisolated(unsafe) static var defaults: UserDefaults = .standard

    /// Save a failed submission locally for later retry.
    ///
    /// De-duplicates on `draftKey` so retrying-then-saving the same report
    /// cannot queue it twice.
    static func saveDraft(_ submission: BugReportSubmission) {
        var drafts = loadDrafts()
        let key = submission.draftKey
        if let existing = drafts.firstIndex(where: { $0.draftKey == key }) {
            drafts[existing] = submission
        } else {
            drafts.append(submission)
        }
        // Keep only the most recent drafts to avoid unbounded storage growth
        if drafts.count > maxDrafts {
            drafts = Array(drafts.suffix(maxDrafts))
        }
        if let data = try? JSONEncoder().encode(drafts) {
            defaults.set(data, forKey: draftsKey)
        }
    }

    /// Load all saved drafts.
    static func loadDrafts() -> [BugReportSubmission] {
        guard let data = defaults.data(forKey: draftsKey),
              let drafts = try? JSONDecoder().decode([BugReportSubmission].self, from: data) else {
            return []
        }
        return drafts
    }

    /// Remove all saved drafts (after successful retry).
    static func clearDrafts() {
        defaults.removeObject(forKey: draftsKey)
    }

    /// Remove a specific draft by index.
    static func removeDraft(at index: Int) {
        var drafts = loadDrafts()
        guard index < drafts.count else { return }
        drafts.remove(at: index)
        if drafts.isEmpty {
            clearDrafts()
        } else if let data = try? JSONEncoder().encode(drafts) {
            defaults.set(data, forKey: draftsKey)
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

// MARK: - Receipts (#1847)

/// A durable local record that a report REACHED THE SERVER, carrying the
/// server-assigned `bug_reports.id`.
///
/// The whole point is that it outlives the 1.5-second success toast. Alex shook
/// twice on 2026-08-13, neither report landed, and there was no artifact
/// anywhere — on the device or in his memory — that could answer "did it send?"
nonisolated struct BugReportReceipt: Codable, Sendable, Identifiable, Equatable {
    /// Server-assigned `bug_reports.id` — the thing you can quote to check.
    let id: Int
    let submittedAt: Date
    /// Short human handle so a list of receipts is readable.
    let summary: String
    let page: String?

    /// What to show when the user wrote no description. A screenshot-only
    /// report is normal and explicitly encouraged by the form's placeholder.
    static let screenshotOnlySummary = "Screenshot only"

    init(id: Int, submittedAt: Date, description: String?, page: String?) {
        self.id = id
        self.submittedAt = submittedAt
        let trimmed = (description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            self.summary = Self.screenshotOnlySummary
        } else if trimmed.count > 80 {
            self.summary = String(trimmed.prefix(79)) + "…"
        } else {
            self.summary = trimmed
        }
        self.page = page
    }
}

/// Durable local log of reports the server acknowledged.
enum BugReportReceiptStore {
    private static let receiptsKey = "bainluck_bug_report_receipts"
    private static let maxReceipts = 20

    /// Injectable for tests; production always uses `.standard`.
    nonisolated(unsafe) static var defaults: UserDefaults = .standard

    /// Record a server acknowledgment. Newest first.
    @discardableResult
    static func record(
        id: Int,
        description: String?,
        page: String?,
        submittedAt: Date = Date()
    ) -> BugReportReceipt {
        let receipt = BugReportReceipt(
            id: id, submittedAt: submittedAt, description: description, page: page
        )
        var receipts = loadReceipts()
        // A retry that duplicates an id must not duplicate the receipt.
        receipts.removeAll { $0.id == id }
        receipts.insert(receipt, at: 0)
        if receipts.count > maxReceipts {
            receipts = Array(receipts.prefix(maxReceipts))
        }
        if let data = try? JSONEncoder().encode(receipts) {
            defaults.set(data, forKey: receiptsKey)
        }
        return receipt
    }

    /// All recorded receipts, newest first.
    static func loadReceipts() -> [BugReportReceipt] {
        guard let data = defaults.data(forKey: receiptsKey),
              let receipts = try? JSONDecoder().decode([BugReportReceipt].self, from: data) else {
            return []
        }
        return receipts
    }

    /// The most recent acknowledged report, if any.
    static var mostRecent: BugReportReceipt? { loadReceipts().first }

    /// Number of acknowledged reports on record.
    static var count: Int { loadReceipts().count }

    static func clear() {
        defaults.removeObject(forKey: receiptsKey)
    }
}
