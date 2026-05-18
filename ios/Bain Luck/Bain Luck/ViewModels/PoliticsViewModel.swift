import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "politics")

final class PoliticsViewModel: ObservableObject {
    @Published private(set) var data: PoliticsResponse?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchPolitics()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Politics load failed: \(error)")
        }
    }
}
