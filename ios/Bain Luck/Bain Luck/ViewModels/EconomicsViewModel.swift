import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "economics")

final class EconomicsViewModel: ObservableObject {
    @Published var data: EconomicsResponse?
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchEconomics()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Economics load failed: \(error)")
        }
    }
}
