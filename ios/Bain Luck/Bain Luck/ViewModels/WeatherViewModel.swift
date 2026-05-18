import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "weather")

final class WeatherViewModel: ObservableObject {
    @Published var featured: [WeatherFeaturedItem] = []
    @Published var cities: [WeatherCity] = []
    @Published var loading = true
    @Published var error: String?

    @MainActor
    func load() async {
        loading = featured.isEmpty && cities.isEmpty
        do {
            async let featuredTask = APIClient.shared.fetchWeatherFeatured()
            async let citiesTask = APIClient.shared.fetchWeatherCities()
            featured = try await featuredTask
            cities = try await citiesTask
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Weather load failed: \(error)")
        }
    }
}
