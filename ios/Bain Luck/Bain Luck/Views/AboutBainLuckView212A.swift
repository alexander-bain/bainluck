import SwiftUI

/// Worked 64% explainer + approved Ruling 189 tagline (`Step 6` of 212-A, #11934).
///
/// Reuses `AboutCopy12672` verbatim so tagline and explanatory copy stay single-source.
/// Publishes NO unverified calibration outcome counts or error figures (ruling D137 / #7580).
struct AboutBainLuckView212A: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme

    var showsBackToDiscoverCTA: Bool = true
    var onBackToDiscover: (() -> Void)? = nil

    private struct TenGameSlot: Identifiable {
        let id: Int
        let label: String
        let style: SlotStyle
        enum SlotStyle { case favoriteWin, swing, underdogWin }
    }

    private let tenGameStrip: [TenGameSlot] = [
        TenGameSlot(id: 0, label: "W", style: .favoriteWin),
        TenGameSlot(id: 1, label: "W", style: .favoriteWin),
        TenGameSlot(id: 2, label: "W", style: .favoriteWin),
        TenGameSlot(id: 3, label: "W", style: .favoriteWin),
        TenGameSlot(id: 4, label: "W", style: .favoriteWin),
        TenGameSlot(id: 5, label: "W", style: .favoriteWin),
        TenGameSlot(id: 6, label: "W?", style: .swing),
        TenGameSlot(id: 7, label: "L", style: .underdogWin),
        TenGameSlot(id: 8, label: "L", style: .underdogWin),
        TenGameSlot(id: 9, label: "L", style: .underdogWin),
    ]

    var body: some View {
        VStack(spacing: 0) {
            headerRow
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 8)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    taglineCard
                    workedExampleCard
                    if showsBackToDiscoverCTA {
                        bottomCTA
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 6)
                .padding(.bottom, 28)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }
        }
        .background(DS.surface)
        .navigationTitle("About Bain Luck")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private var headerRow: some View {
        HStack {
            Text(AboutCopy12672.eyebrow.uppercased())
                .font(.caption.weight(.bold))
                .tracking(0.8)
                .foregroundStyle(DS.blueReadable)
            Spacer()
            Button(showsBackToDiscoverCTA ? "Discover" : "Done") {
                if let onBackToDiscover {
                    onBackToDiscover()
                } else {
                    dismiss()
                }
            }
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DS.blueReadable)
        }
    }

    private var taglineCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("\u{1F340}")
                    .font(.title3)
                Text("Bain Luck")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
            }

            Text(AboutCopy12672.heroTitle)
                .font(.title2.weight(.heavy))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text(AboutCopy12672.heroSubtitle)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)

            Text("Combined from prediction markets and sportsbooks — for games, awards, culture, and the economy, with no betting.")
                .font(.footnote)
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    private var workedExampleCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("What \(AboutCopy12672.examplePercent) means")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("About 2 times out of 3 — not a sure thing.")
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                Text(AboutCopy12672.examplePercent)
                    .font(.title.weight(.heavy).monospacedDigit())
                    .foregroundStyle(DS.blueReadable)
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("Across 10 games where a team starts at 64%:")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 6) {
                        ForEach(tenGameStrip) { slot in
                            slotBadge(slot)
                        }
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 6) {
                            ForEach(tenGameStrip.prefix(5)) { slot in
                                slotBadge(slot)
                            }
                        }
                        HStack(spacing: 6) {
                            ForEach(tenGameStrip.suffix(5)) { slot in
                                slotBadge(slot)
                            }
                        }
                    }
                }

                Text("The 64% favorite wins 6 or 7 times, and the 36% underdog still wins 3 or 4 times. An upset isn\u{2019}t a broken number \u{2014} it\u{2019}s the 36% happening.")
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    private func slotBadge(_ slot: TenGameSlot) -> some View {
        let fg: Color
        let bg: Color
        switch slot.style {
        case .favoriteWin:
            fg = colorScheme == .dark ? Color(hex: "#0F172A") : .white
            bg = DS.blueReadable
        case .swing:
            fg = DS.blueReadable
            bg = DS.blueReadable.opacity(colorScheme == .dark ? 0.22 : 0.12)
        case .underdogWin:
            fg = DS.textSecondaryReadable
            bg = DS.cardBg
        }

        return Text(slot.label)
            .font(.caption.weight(.bold).monospacedDigit())
            .foregroundStyle(fg)
            .frame(minWidth: 26, minHeight: 28)
            .padding(.horizontal, 2)
            .background(bg, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .stroke(
                        slot.style == .swing ? DS.blueReadable : DS.border,
                        style: slot.style == .swing ? StrokeStyle(lineWidth: 1.5, dash: [3, 2]) : StrokeStyle(lineWidth: 1)
                    )
            )
    }

    private var bottomCTA: some View {
        Button {
            if let onBackToDiscover {
                onBackToDiscover()
            } else {
                dismiss()
            }
        } label: {
            Text("Back to Discover")
                .font(.headline)
                .foregroundStyle(colorScheme == .dark ? Color(hex: "#0F172A") : .white)
                .frame(maxWidth: .infinity, minHeight: 50)
                .background(
                    DS.textPrimary,
                    in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("about212A.backToDiscover")
    }
}
