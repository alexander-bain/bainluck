import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "entertainment")

final class EntertainmentViewModel: ObservableObject {
    @Published private(set) var data: EntertainmentResponse?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

    private let fetchEntertainment: @MainActor () async throws -> EntertainmentResponse

    init(fetchEntertainment: @escaping @MainActor () async throws -> EntertainmentResponse = {
        try await APIClient.shared.fetchEntertainment()
    }) {
        self.fetchEntertainment = fetchEntertainment
    }

    @MainActor
    func load() async {
        loading = data == nil
        do {
            data = try await fetchEntertainment()
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Entertainment load failed: \(error)")
        }
    }
}
