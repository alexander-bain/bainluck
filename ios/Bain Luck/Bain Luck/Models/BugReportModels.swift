import Foundation

/// Client payload submitted when a user files an in-app bug report.
nonisolated struct BugReportSubmission: Encodable, Sendable {
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
