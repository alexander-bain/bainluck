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
        .onAppear { AnalyticsService.trackScreen(name: "weather", type: "weather") }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    private var weatherContent: some View {
        ScrollView {
            VStack(spacing: 20) {
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
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "\u{1F324}\u{FE0F}", title: "Featured", count: vm.featured.count)
                .padding(.horizontal)

            ForEach(vm.featured) { item in
                featuredCard(item)
            }
            .padding(.horizontal)
        }
    }

    private func featuredCard(_ item: WeatherFeaturedItem) -> some View {
        let (_, accentColor) = tagStyle(item.tag)

        return HStack(spacing: 12) {
            // Colored accent bar on the left
            RoundedRectangle(cornerRadius: 2)
                .fill(accentColor)
                .frame(width: 4)
                .padding(.vertical, 4)

            tagBadge(item.tag)

            VStack(alignment: .leading, spacing: 4) {
                Text(item.q)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(2)
                HStack(spacing: 8) {
                    Label(item.src.capitalized, systemImage: "chart.bar.fill")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Label("Closes \(item.closes)", systemImage: "clock")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Probability pill
            Text("\(item.prob)%")
                .font(.title3)
                .fontWeight(.black)
                .monospacedDigit()
                .foregroundStyle(accentColor)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(accentColor.opacity(0.1))
                .clipShape(Capsule())
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 8, x: 0, y: 3)
    }

    private func tagBadge(_ tag: String) -> some View {
        let (emoji, color) = tagStyle(tag)
        return Text(emoji)
            .font(.system(size: 22))
            .frame(width: 40, height: 40)
            .background(color.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func tagStyle(_ tag: String) -> (String, Color) {
        switch tag.lowercased() {
        case "temperature": return ("\u{1F321}\u{FE0F}", .orange)
        case "rain", "rainfall", "precipitation": return ("\u{1F327}\u{FE0F}", .blue)
        case "snow": return ("\u{2744}\u{FE0F}", .cyan)
        case "severe", "hurricane", "storm": return ("\u{26C8}\u{FE0F}", .red)
        case "wind": return ("\u{1F4A8}", .teal)
        default: return ("\u{1F324}\u{FE0F}", .secondary)
        }
    }

    // MARK: - Section Header

    private func sectionHeader(emoji: String, title: String, count: Int) -> some View {
        HStack(spacing: 6) {
            Text(emoji)
                .font(.title3)
            Text(title)
                .font(.title3)
                .fontWeight(.bold)
            Text("\(count)")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 7)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.12))
                .clipShape(Capsule())
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
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(emoji: "\u{1F3D9}\u{FE0F}", title: "City Forecasts", count: filteredCities.count)
                .padding(.horizontal)

            // Search field
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
            .padding(10)
            .background(Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal)

            let columns = [GridItem(.adaptive(minimum: 300), spacing: 14)]
            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(filteredCities) { city in
                    if let marketId = city.marketId {
                        NavigationLink(value: Route.futuresDetail(id: marketId)) {
                            CityForecastCard(city: city)
                        }
                        .buttonStyle(.plain)
                    } else {
                        CityForecastCard(city: city)
                    }
                }
            }
            .padding(.horizontal)
        }
    }
}

// MARK: - City Forecast Card (Stateful for expand/collapse)

private struct CityForecastCard: View {
    let city: WeatherCity
    @State private var showAllHigh = false
    @State private var showAllLow = false

    /// Number of brackets to show before collapsing
    private let visibleCount = 5

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with city name + temperature badge
            cityHeader

            if let high = city.high {
                distributionSection(
                    title: "HIGH",
                    distribution: high,
                    accentColor: tempColor(for: high.mode),
                    isHigh: true,
                    expanded: showAllHigh,
                    toggleExpand: { showAllHigh.toggle() }
                )
            }

            if let low = city.low {
                distributionSection(
                    title: "LOW",
                    distribution: low,
                    accentColor: .blue,
                    isHigh: false,
                    expanded: showAllLow,
                    toggleExpand: { showAllLow.toggle() }
                )
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(tempColor(for: city.high?.mode).opacity(0.25), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
    }

    // MARK: - City Header

    private var cityHeader: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text(city.name)
                    .font(.headline)
                    .fontWeight(.bold)
                Text(city.region)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let mode = city.high?.mode {
                tempBadge(temp: mode, unit: city.high?.unit ?? "F")
            }
        }
    }

    /// Large temperature badge with color gradient background
    private func tempBadge(temp: Double, unit: String) -> some View {
        let color = tempColor(for: temp)
        return HStack(spacing: 2) {
            Text("\(Int(temp))")
                .font(.system(size: 28, weight: .black, design: .rounded))
            Text("\u{00B0}\(unit)")
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .offset(y: -4)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(color.opacity(0.1))
        )
    }

    // MARK: - Distribution Section

    private func distributionSection(
        title: String,
        distribution: WeatherDistribution,
        accentColor: Color,
        isHigh: Bool,
        expanded: Bool,
        toggleExpand: @escaping () -> Void
    ) -> some View {
        let peakProb = distribution.dist.map(\.prob).max() ?? 0
        let brackets = distribution.dist
        let showToggle = brackets.count > visibleCount
        let visibleBrackets = expanded ? brackets : Array(brackets.prefix(visibleCount))

        return VStack(alignment: .leading, spacing: 6) {
            // Section label
            HStack(spacing: 4) {
                Circle()
                    .fill(accentColor)
                    .frame(width: 6, height: 6)
                Text(title)
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundStyle(.secondary)
                    .tracking(0.5)
                if let mode = distribution.mode {
                    Text("Most likely: \(Int(mode))\u{00B0}\(distribution.unit)")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.tertiary)
                }
            }

            // Bracket bars
            ForEach(visibleBrackets) { bracket in
                bracketRow(
                    bracket: bracket,
                    isPeak: bracket.prob == peakProb && peakProb > 0,
                    accentColor: accentColor,
                    maxProb: peakProb
                )
            }

            // Expand/collapse toggle
            if showToggle {
                Button(action: toggleExpand) {
                    HStack(spacing: 4) {
                        Text(expanded ? "Show less" : "\(brackets.count - visibleCount) more")
                            .font(.caption2)
                            .fontWeight(.medium)
                        Image(systemName: expanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 9, weight: .bold))
                    }
                    .foregroundStyle(.secondary)
                    .padding(.top, 2)
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Bracket Row

    private func bracketRow(
        bracket: WeatherBracket,
        isPeak: Bool,
        accentColor: Color,
        maxProb: Int
    ) -> some View {
        HStack(spacing: 8) {
            Text(bracket.label)
                .font(.caption)
                .fontWeight(isPeak ? .bold : .regular)
                .foregroundStyle(isPeak ? .primary : .secondary)
                .frame(width: 80, alignment: .leading)

            // Visual bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    // Track
                    Capsule()
                        .fill(Color.secondary.opacity(0.08))

                    // Fill
                    Capsule()
                        .fill(
                            isPeak
                                ? accentColor
                                : accentColor.opacity(0.35)
                        )
                        .frame(width: max(2, geo.size.width * Double(bracket.prob) / Double(max(maxProb, 1))))
                }
            }
            .frame(height: isPeak ? 14 : 10)

            // Probability label
            Text("\(bracket.prob)%")
                .font(isPeak ? .caption : .caption2)
                .fontWeight(isPeak ? .black : .semibold)
                .monospacedDigit()
                .foregroundStyle(isPeak ? accentColor : .secondary)
                .frame(width: 32, alignment: .trailing)
        }
    }

    // MARK: - Temperature Color

    /// Returns a color based on temperature value (Fahrenheit assumed)
    private func tempColor(for temp: Double?) -> Color {
        guard let temp else { return .orange }
        switch temp {
        case ..<32:  return .cyan            // Freezing
        case 32..<50: return .blue           // Cold
        case 50..<65: return .teal           // Cool
        case 65..<80: return .orange         // Warm
        case 80..<95: return Color(red: 0.95, green: 0.4, blue: 0.1) // Hot
        default:      return .red            // Very hot
        }
    }
}
