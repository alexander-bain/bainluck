import Foundation

/// #13773 & #13778 part 1: Shared rules for small Discover card charts.
/// 1. Suppress any loaded chart whose series moves less than 2 percentage points.
/// 2. Always label the horizontal time period beneath every drawn chart.
nonisolated enum DiscoverCardChartRules13773 {
    /// Minimum peak-to-trough probability spread (2 percentage points) before a
    /// small card chart earns screen space.
    static let minimumVisibleSwingProbability: Double = 0.02

    static func hasMovingSpread(_ probabilities: [Double]) -> Bool {
        let finite = probabilities.filter(\.isFinite)
        guard finite.count >= 2,
              let minValue = finite.min(),
              let maxValue = finite.max() else {
            return false
        }
        return (maxValue - minValue) >= (minimumVisibleSwingProbability - 1e-9)
    }

    static func hasMovingThreeWaySpread(_ points: [SoccerThreeLineChart211A.Point]) -> Bool {
        guard points.count >= 2 else { return false }
        return hasMovingSpread(points.map(\.home))
            || hasMovingSpread(points.map(\.draw))
            || hasMovingSpread(points.map(\.away))
    }

    static func hasMovingKitLine(_ points: [KitV1LinePoint]) -> Bool {
        let ys = points.map(\.y).filter(\.isFinite)
        guard ys.count >= 2,
              let minY = ys.min(),
              let maxY = ys.max() else {
            return false
        }
        let spread = maxY - minY
        if maxY <= 1.05 && minY >= -0.05 {
            return spread >= (minimumVisibleSwingProbability - 1e-9)
        }
        return spread >= (minimumVisibleSwingProbability * 100.0 - 1e-9)
    }

    static func axisEndLabels(
        start: Date?,
        end: Date?,
        timeZone: TimeZone = .current
    ) -> (start: String, end: String)? {
        guard let start, let end else { return nil }
        let lo = min(start, end)
        let hi = max(start, end)

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let locale = Locale(identifier: "en_US_POSIX")

        func makeFormatter(_ format: String) -> DateFormatter {
            let f = DateFormatter()
            f.locale = locale
            f.calendar = calendar
            f.timeZone = timeZone
            f.dateFormat = format
            return f
        }

        if calendar.isDate(lo, inSameDayAs: hi) {
            let startFmt = makeFormatter("MMM d, h:mm a")
            let endFmt = makeFormatter("h:mm a")
            return (startFmt.string(from: lo), endFmt.string(from: hi))
        }

        if hi.timeIntervalSince(lo) <= 36 * 3600 {
            let fmt = makeFormatter("MMM d, h:mm a")
            return (fmt.string(from: lo), fmt.string(from: hi))
        }

        let startYear = calendar.component(.year, from: lo)
        let endYear = calendar.component(.year, from: hi)
        if startYear == endYear {
            let fmt = makeFormatter("MMM d")
            return (fmt.string(from: lo), fmt.string(from: hi))
        }

        let yearFmt = makeFormatter("MMM d, yyyy")
        return (yearFmt.string(from: lo), yearFmt.string(from: hi))
    }

    static func axisEndLabels(
        startIso: String,
        endIso: String,
        timeZone: TimeZone = .current
    ) -> (start: String, end: String)? {
        let startDate = parseFlexibleISO(startIso, timeZone: timeZone)
        let endDate = parseFlexibleISO(endIso, timeZone: timeZone)
        return axisEndLabels(start: startDate, end: endDate, timeZone: timeZone)
    }

    private static func parseFlexibleISO(_ raw: String, timeZone: TimeZone) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = fractional.date(from: trimmed) { return d }

        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let d = plain.date(from: trimmed) { return d }

        let normalized = (trimmed.hasSuffix("Z") || trimmed.contains("+")) ? trimmed : (trimmed + "Z")
        if let d = fractional.date(from: normalized) ?? plain.date(from: normalized) {
            return d
        }

        let dateOnly = DateFormatter()
        dateOnly.locale = Locale(identifier: "en_US_POSIX")
        dateOnly.timeZone = timeZone
        dateOnly.dateFormat = "yyyy-MM-dd"
        return dateOnly.date(from: trimmed)
    }
}
