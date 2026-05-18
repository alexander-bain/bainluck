import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "entertainment")

final class EntertainmentViewModel: ObservableObject {
    @Published var data: EntertainmentResponse?
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await APIClient.shared.fetchEntertainment()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Entertainment load failed: \(error)")
        }
    }
}
