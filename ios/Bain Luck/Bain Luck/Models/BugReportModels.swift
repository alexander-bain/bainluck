import Foundation

nonisolated struct BugReportSubmission: Encodable, Sendable {
    let description: String?
    let screenshotBase64: String?
    let appState: [String: String]?
    let notifyOnFix: Bool
}

nonisolated struct BugReportResponse: Decodable, Sendable {
    let status: String
    let id: Int
}
