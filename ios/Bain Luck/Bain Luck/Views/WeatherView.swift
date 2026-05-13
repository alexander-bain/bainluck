import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "weather")

// MARK: - ViewModel

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

// MARK: - View

struct WeatherView: View {
    @StateObject private var vm = WeatherViewModel()
    @State private var citySearch = ""

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading weather markets...")
            } else if let error = vm.error, vm.featured.isEmpty {
                ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
            } else {
                weatherContent
            }
        }
        .navigationTitle("Weather")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private var weatherContent: some View {
        ScrollView {
            VStack(spacing: 16) {
                if !vm.featured.isEmpty {
                    featuredSection
                }
                if !vm.cities.isEmpty {
                    citiesSection
                }
            }
            .padding(.vertical)
        }
    }

    // MARK: - Featured Markets

    private var featuredSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("🌤")
                Text("Featured")
                    .font(.headline)
                    .fontWeight(.bold)
                Text("\(vm.featured.count)")
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
            .padding(.horizontal)

            ForEach(vm.featured) { item in
                featuredRow(item)
            }
        }
    }

    private func featuredRow(_ item: WeatherFeaturedItem) -> some View {
        HStack(spacing: 10) {
            tagBadge(item.tag)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.q)
                    .font(.subheadline)
                    .lineLimit(2)
                HStack(spacing: 8) {
                    Text(item.src.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text("Closes \(item.closes)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer()
            Text("\(item.prob)%")
                .font(.title3)
                .fontWeight(.black)
                .monospacedDigit()
        }
        .padding(.horizontal)
        .padding(.vertical, 6)
    }

    private func tagBadge(_ tag: String) -> some View {
        let (emoji, color) = tagStyle(tag)
        return Text(emoji)
            .font(.system(size: 20))
            .frame(width: 36, height: 36)
            .background(color.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func tagStyle(_ tag: String) -> (String, Color) {
        switch tag.lowercased() {
        case "temperature": return ("🌡", .orange)
        case "rain", "rainfall", "precipitation": return ("🌧", .blue)
        case "snow": return ("❄️", .cyan)
        case "severe", "hurricane", "storm": return ("⛈", .red)
        case "wind": return ("💨", .teal)
        default: return ("🌤", .secondary)
        }
    }

    // MARK: - Cities

    private var filteredCities: [WeatherCity] {
        if citySearch.trimmingCharacters(in: .whitespaces).isEmpty {
            return vm.cities
        }
        return vm.cities.filter { $0.name.localizedCaseInsensitiveContains(citySearch) }
    }

    private var citiesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("🏙")
                Text("City Forecasts")
                    .font(.headline)
                    .fontWeight(.bold)
                Text("\(filteredCities.count)")
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
            .padding(.horizontal)

            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search cities...", text: $citySearch)
                    .textFieldStyle(.plain)
                    .autocorrectionDisabled()
                if !citySearch.isEmpty {
                    Button {
                        citySearch = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)
            .background(Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal)

            let columns = [GridItem(.adaptive(minimum: 300), spacing: 12)]
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(filteredCities) { city in
                    cityCard(city)
                }
            }
            .padding(.horizontal)
        }
    }

    private func cityCard(_ city: WeatherCity) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(city.name)
                    .font(.headline)
                    .fontWeight(.bold)
                Spacer()
                if let mode = city.high?.mode {
                    Text("\(Int(mode))°\(city.high?.unit ?? "F")")
                        .font(.title3)
                        .fontWeight(.black)
                        .foregroundStyle(.orange)
                }
            }

            if let high = city.high {
                VStack(alignment: .leading, spacing: 2) {
                    Text("HIGH")
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(.secondary)
                        .tracking(0.5)
                    ForEach(high.dist) { bracket in
                        HStack(spacing: 6) {
                            Text(bracket.label)
                                .font(.caption)
                                .frame(width: 90, alignment: .leading)
                            GeometryReader { geo in
                                Capsule()
                                    .fill(Color.secondary.opacity(0.08))
                                    .overlay(alignment: .leading) {
                                        Capsule()
                                            .fill(Color.orange.opacity(0.5))
                                            .frame(width: max(2, geo.size.width * Double(bracket.prob) / 100))
                                    }
                            }
                            .frame(height: 12)
                            Text("\(bracket.prob)%")
                                .font(.caption2)
                                .fontWeight(.bold)
                                .monospacedDigit()
                                .frame(width: 28, alignment: .trailing)
                        }
                    }
                }
            }

            if let low = city.low {
                VStack(alignment: .leading, spacing: 2) {
                    Text("LOW")
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(.secondary)
                        .tracking(0.5)
                    ForEach(low.dist) { bracket in
                        HStack(spacing: 6) {
                            Text(bracket.label)
                                .font(.caption)
                                .frame(width: 90, alignment: .leading)
                            GeometryReader { geo in
                                Capsule()
                                    .fill(Color.secondary.opacity(0.08))
                                    .overlay(alignment: .leading) {
                                        Capsule()
                                            .fill(Color.blue.opacity(0.4))
                                            .frame(width: max(2, geo.size.width * Double(bracket.prob) / 100))
                                    }
                            }
                            .frame(height: 12)
                            Text("\(bracket.prob)%")
                                .font(.caption2)
                                .fontWeight(.bold)
                                .monospacedDigit()
                                .frame(width: 28, alignment: .trailing)
                        }
                    }
                }
            }
        }
        .padding(12)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.secondary.opacity(0.1)))
    }
}
