import SwiftUI

/// EI score + emoji in a colored pill. Three sizes: `.sm` for cards, `.md` for detail headers, `.lg` for hero sections.
struct EIBadgeView: View {
    let ei: EIData
    var size: BadgeSize = .sm

    enum BadgeSize {
        case sm, md, lg
    }

    var body: some View {
        if size == .lg {
            lgBadge
        } else {
            compactBadge
        }
    }

    // MARK: - Compact (sm/md)

    private var compactBadge: some View {
        HStack(spacing: size == .sm ? 2 : 4) {
            if let emoji = ei.emoji {
                Text(emoji)
                    .font(size == .sm ? .caption2 : .subheadline)
            }
            Text(EIBadgeView.compactText(for: ei))
                .font(size == .sm ? .caption2 : .subheadline)
                .fontWeight(.semibold)
                .lineLimit(1)
        }
        .padding(.horizontal, size == .sm ? 6 : 10)
        .padding(.vertical, size == .sm ? 2 : 4)
        .background(badgeColor.opacity(0.15))
        .foregroundStyle(badgeColor)
        .clipShape(Capsule())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Excitement: \(EIBadgeView.compactText(for: ei))")
    }

    /// What the compact pill says beside the emoji.
    ///
    /// #6444 — **"😴 34".** Alex, on his own phone, scrolling the Red Sox search
    /// results: *"I wasn't sure how to interpret the emoji."* The pill printed a
    /// sleeping face and the number 34, and the row says nothing else about
    /// either: not what is being scored, not what it is out of, not whether 34
    /// is good. The number is the half a reader cannot use — an Excitement
    /// Index has no units on a card and no scale beside it — and the word is
    /// the half the server has been sending all along, unread: the same payload
    /// carries `"label": "Quiet"`, and `"⚡ 72"` one row down carries
    /// `"Exciting"`.
    ///
    /// So the pill prints the served word. It is not a word this tier invents:
    /// `get_ei_label` in `backend/app/utils/excitement_index.py` owns the
    /// vocabulary (Flat · Quiet · Average · Competitive · Engaging · Exciting ·
    /// Must-Watch · Incredible) and the ``lgBadge`` below has printed it under
    /// the score since it was written — this is the compact badge catching up
    /// with the large one, not a new label.
    ///
    /// WHY NOT BOTH. "⚡ 72 Exciting" restores the uninterpretable number for
    /// width the search row and the card top bar do not have, and the number
    /// adds nothing the word has not already said. The `lg` badge keeps it
    /// because it prints `"72 / 100"` — a scale — and has the room.
    ///
    /// THE WEB PILL IS NOT OUT OF STEP BY ACCIDENT: `EIBadge.tsx` prints
    /// `{ei.emoji} {ei.score}` wrapped in a `Tooltip` that spells out
    /// "Excitement Index: 72 (Exciting)" and what it measures. A phone has no
    /// hover, so the tooltip is the explanation this tier cannot have, and the
    /// label is the smallest thing that replaces it.
    ///
    /// The score is the fallback, not the answer: `label` is derived from the
    /// score server-side by a total function, so an absent one means a payload
    /// older or stranger than any we serve, and the pill degrades to what it
    /// printed before rather than to a blank.
    static func compactText(for ei: EIData) -> String {
        if let label = ei.label?.trimmingCharacters(in: .whitespaces), !label.isEmpty {
            return label
        }
        return "\(ei.score ?? ei.rawScore ?? 0)"
    }

    // MARK: - Large (lg)

    private var lgBadge: some View {
        VStack(spacing: 4) {
            HStack(spacing: 6) {
                if let emoji = ei.emoji {
                    Text(emoji).font(.title3)
                }
                Text("\(displayScore) / 100")
                    .font(.title3)
                    .fontWeight(.bold)
                    .monospacedDigit()
            }
            if let label = ei.label {
                Text(label)
                    .font(.caption)
                    .fontWeight(.medium)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(
                colors: [badgeColor.opacity(0.15), badgeColor.opacity(0.05)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .foregroundStyle(badgeColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var displayScore: Int {
        ei.score ?? ei.rawScore ?? 0
    }

    private var badgeColor: Color {
        let s = displayScore
        if s >= 81 { return .red }
        if s >= 61 { return .orange }
        if s >= 41 { return Color(hex: "#d97706") } // amber
        return .gray
    }
}
