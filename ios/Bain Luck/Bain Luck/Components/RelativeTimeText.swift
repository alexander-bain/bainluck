import SwiftUI

/// Formats a commence_time string relative to now: "Today 7:30 PM", "Tomorrow 2 PM", "Wed Mar 5".
struct RelativeTimeText: View {
    let dateString: String?

    var body: some View {
        if let text = formattedText {
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var formattedText: String? {
        guard let dateString, let date = dateString.asDate else { return nil }
        let cal = Calendar.current
        let now = Date()

        if cal.isDateInToday(date) {
            return "Today \(timeString(date))"
        } else if cal.isDateInTomorrow(date) {
            return "Tomorrow \(timeString(date))"
        } else if cal.isDateInYesterday(date) {
            return "Yesterday \(timeString(date))"
        } else {
            let days = cal.dateComponents([.day], from: cal.startOfDay(for: now), to: cal.startOfDay(for: date)).day ?? 0
            if days > 0 && days <= 6 {
                return dayOfWeekString(date)
            }
            return dateWithMonthString(date)
        }
    }

    private func timeString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f.string(from: date)
    }

    private func dayOfWeekString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "EEE h:mm a"
        return f.string(from: date)
    }

    private func dateWithMonthString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: date)
    }
}
