import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresDetail")

final class FuturesDetailViewModel: ObservableObject {
    @Published var market: FuturesMarketDetail?
    @Published var loading = true
    @Published var error: String?

    let marketId: Int

    init(marketId: Int) {
        self.marketId = marketId
    }

    @MainActor
    func load() async {
        loading = market == nil
        do {
            market = try await APIClient.shared.fetchFuturesDetail(id: marketId)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load futures \(self.marketId): \(error)")
        }
    }
}
