import SwiftUI

/// Verbatim approved About copy (`#12672`, Decision 189; Atlas `#12744` `AboutPage189.tsx` reference).
nonisolated enum AboutCopy12672 {
    static let eyebrow = "About Bain Luck"
    static let heroTitle = "The real score for everything."
    static let heroSubtitle = "What the world thinks will happen, as one clear percentage."
    static let heroLead = "A scoreboard tells you who's ahead. It doesn't tell you who's going to win. Bain Luck does: for tonight's game, next year's election, the Oscars, the weather, the Fed."

    static let oneNumberTitle = "One number."
    static let oneNumberBody = "Every day, thousands of people commit to what they expect will happen. We read the prediction markets and the sportsbooks and blend them into a single chance for each outcome."

    static let howToReadTitle = "How to read it."
    static let howToReadBody = "64% means it happens about two times in three. It's the world's best guess, not a promise. Watch it move; the movement is the story."
    static let examplePercent = "64%"
    static let exampleCaption = "Example: about 2 times in 3"

    static let notBettingTitle = "Not betting."
    static let notBettingBody = "No odds to decode, no bets to place, nothing to buy."

    static let keepScoreTitle = "We keep score on ourselves."
    static let keepScoreBody = "Every finished game and settled market is checked against what we showed."
    static let keepScoreLink = "See how we've done."
    static let keepScoreSparklineCaption = "Forecast % vs what happened"

    static let primaryCTA = "Start exploring"

    static let allCopyStrings: [String] = [
        eyebrow,
        heroTitle,
        heroSubtitle,
        heroLead,
        oneNumberTitle,
        oneNumberBody,
        howToReadTitle,
        howToReadBody,
        examplePercent,
        exampleCaption,
        notBettingTitle,
        notBettingBody,
        keepScoreTitle,
        keepScoreBody,
        keepScoreLink,
        keepScoreSparklineCaption,
        primaryCTA,
    ]
}

/// Native About screen (`#12672`, Decision 189; Atlas `#12744` `AboutPage189.tsx` reference),
/// rendered directly in SwiftUI so `1.0.7` readers see the approved story immediately with
/// native Dynamic Type, 1-column phone / 2-column iPad & Mac layout, native Discover CTA
/// handoff (`#12674`), native Calibration navigation, and the single in-flow bottom fine-print
/// row (`bugs@bainluck.com · Privacy Policy · Picture credits`, Ruling `195-A` / `#12735`).
struct AboutView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    static let aboutURL = URL(string: "https://www.bainluck.com/about?embed=1")!
    static let discoverURL = URL(string: "https://www.bainluck.com/discover")!
    static let calibrationURL = URL(string: "https://www.bainluck.com/calibration")!
    static let privacyURL = URL(string: "https://www.bainluck.com/privacy")!
    static let pictureCreditsURL = URL(string: "https://www.bainluck.com/picture-credits")!
    static let bugsMailURL = URL(string: "mailto:bugs@bainluck.com")!

    /// Intercepts `/discover` ("Start exploring") so tapping it switches natively to the
    /// Discover tab (`#12674`) while `/calibration`, `/privacy`, `/picture-credits`, and
    /// `mailto:` leave the About screen cleanly.
    static func handleOutgoingLink(
        _ candidate: URL,
        navigation: NavigationCoordinator,
        dismiss: () -> Void
    ) -> Bool {
        guard InAppWebViewNavigation.opensDiscoverInApp(candidate) else {
            return false
        }
        dismiss()
        navigation.selectedTab = .discover
        return true
    }

    var body: some View {
        GeometryReader { proxy in
            let usesTwoColumnGrid = proxy.size.width >= 680 && !dynamicTypeSize.isAccessibilitySize
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    heroSection

                    if usesTwoColumnGrid {
                        VStack(spacing: 16) {
                            HStack(alignment: .top, spacing: 16) {
                                oneNumberCard
                                howToReadCard
                            }
                            HStack(alignment: .top, spacing: 16) {
                                notBettingCard
                                keepScoreCard
                            }
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 14) {
                            oneNumberCard
                            howToReadCard
                            notBettingCard
                            keepScoreCard
                        }
                    }

                    startExploringButton

                    bottomFinePrintRow
                }
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 32)
            }
            .background(DS.surface)
        }
        .accessibilityIdentifier("about-page-189")
        .navigationTitle("About")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }

    // MARK: - Hero Card

    private var heroSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(AboutCopy12672.eyebrow.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(0.8)
                .foregroundStyle(DS.greenReadable)
                .padding(.horizontal, 11)
                .padding(.vertical, 5)
                .background(DS.trackBg, in: Capsule())
                .overlay(Capsule().strokeBorder(DS.border, lineWidth: 1))

            VStack(alignment: .leading, spacing: 6) {
                Text(AboutCopy12672.heroTitle)
                    .font(.title.weight(.heavy))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(AboutCopy12672.heroSubtitle)
                    .font(.headline.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text(AboutCopy12672.heroLead)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondaryReadable)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            domainPillsRow
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }

    private var domainPillsRow: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) {
                sportsDomainButton
                domainRoutePill("Politics", route: .politics)
                domainRoutePill("Entertainment", route: .entertainment)
                domainRoutePill("Weather", route: .weather)
                domainRoutePill("Economics", route: .economics)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    sportsDomainButton
                    domainRoutePill("Politics", route: .politics)
                    domainRoutePill("Entertainment", route: .entertainment)
                }
                HStack(spacing: 8) {
                    domainRoutePill("Weather", route: .weather)
                    domainRoutePill("Economics", route: .economics)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    sportsDomainButton
                    domainRoutePill("Politics", route: .politics)
                }
                HStack(spacing: 8) {
                    domainRoutePill("Entertainment", route: .entertainment)
                    domainRoutePill("Weather", route: .weather)
                }
                domainRoutePill("Economics", route: .economics)
            }
        }
    }

    private var sportsDomainButton: some View {
        Button {
            dismiss()
            navCoordinator.selectedTab = .feed
        } label: {
            domainPillLabel("Sports")
        }
        .buttonStyle(.plain)
    }

    private func domainRoutePill(_ title: String, route: Route) -> some View {
        NavigationLink(value: route) {
            domainPillLabel(title)
        }
        .buttonStyle(.plain)
    }

    private func domainPillLabel(_ title: String) -> some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DS.textSecondaryReadable)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(DS.trackBg, in: Capsule())
            .overlay(Capsule().strokeBorder(DS.border, lineWidth: 1))
    }

    // MARK: - Body Cards

    private var oneNumberCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                Text(AboutCopy12672.oneNumberTitle)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DS.textPrimary)

                Text(AboutCopy12672.oneNumberBody)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    HStack(spacing: 5) {
                        Text("Prediction markets")
                        Text("+")
                            .foregroundStyle(DS.textMuted)
                        Text("Sportsbooks")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)

                    Spacer(minLength: 4)

                    oneNumberExampleBadge
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Prediction markets + Sportsbooks")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack {
                        Spacer(minLength: 0)
                        oneNumberExampleBadge
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(DS.border, lineWidth: 1)
            )
            .accessibilityHidden(true)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }

    private var oneNumberExampleBadge: some View {
        HStack(spacing: 6) {
            Text("\u{2192}")
                .font(.caption)
                .foregroundStyle(DS.textMuted)
            Text(AboutCopy12672.examplePercent)
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(DS.greenReadable)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(DS.emerald.opacity(0.14), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
    }

    private var howToReadCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(AboutCopy12672.howToReadTitle)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                    Spacer(minLength: 4)
                    Text(AboutCopy12672.examplePercent)
                        .font(.title2.weight(.heavy).monospacedDigit())
                        .foregroundStyle(DS.greenReadable)
                        .accessibilityHidden(true)
                }

                Text(AboutCopy12672.howToReadBody)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Capsule()
                        .fill(DS.emeraldDark)
                        .frame(height: 8)
                    Capsule()
                        .fill(DS.emeraldDark)
                        .frame(height: 8)
                    Capsule()
                        .fill(DS.border)
                        .frame(height: 8)
                }

                HStack {
                    Text(AboutCopy12672.exampleCaption)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                    Spacer(minLength: 4)
                    Text(AboutCopy12672.examplePercent)
                        .font(.caption2.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.greenReadable)
                }
            }
            .padding(12)
            .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(DS.border, lineWidth: 1)
            )
            .accessibilityHidden(true)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }

    private var notBettingCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "bookmark")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.greenReadable)
                    .accessibilityHidden(true)

                Text(AboutCopy12672.notBettingTitle)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
            }

            Text(AboutCopy12672.notBettingBody)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondaryReadable)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }

    private var keepScoreCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                Text(AboutCopy12672.keepScoreTitle)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DS.textPrimary)

                Text(AboutCopy12672.keepScoreBody)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                NavigationLink(value: Route.calibration) {
                    Text(AboutCopy12672.keepScoreLink)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.greenReadable)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("about-calibration-link")
            }

            Spacer(minLength: 0)

            HStack(spacing: 12) {
                calibrationSparkline
                    .frame(width: 96, height: 32)

                Spacer(minLength: 4)

                Text(AboutCopy12672.keepScoreSparklineCaption)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .multilineTextAlignment(.trailing)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(DS.border, lineWidth: 1)
            )
            .accessibilityHidden(true)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }

    private var calibrationSparkline: some View {
        Canvas { context, size in
            let w = size.width
            let h = size.height
            func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
                CGPoint(x: x / 120.0 * w, y: y / 40.0 * h)
            }

            var ref = Path()
            ref.move(to: pt(8, 34))
            ref.addLine(to: pt(112, 6))
            context.stroke(
                ref,
                with: .color(DS.emeraldDark.opacity(0.32)),
                style: StrokeStyle(lineWidth: 1.5, dash: [3, 3])
            )

            let curveCoords: [(CGFloat, CGFloat)] = [
                (8, 33), (29, 28), (50, 21), (71, 17), (92, 11), (112, 6),
            ]
            var line = Path()
            if let first = curveCoords.first {
                line.move(to: pt(first.0, first.1))
                for c in curveCoords.dropFirst() {
                    line.addLine(to: pt(c.0, c.1))
                }
            }
            context.stroke(
                line,
                with: .color(DS.emeraldDark),
                style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round)
            )

            for dot in [(29, 28), (71, 17), (112, 6)] as [(CGFloat, CGFloat)] {
                let p = pt(dot.0, dot.1)
                let rect = CGRect(x: p.x - 2.2, y: p.y - 2.2, width: 4.4, height: 4.4)
                context.fill(Path(ellipseIn: rect), with: .color(DS.emeraldDark))
            }
        }
    }

    // MARK: - Primary CTA & Bottom Fine-Print Row

    private var startExploringButton: some View {
        HStack {
            Spacer(minLength: 0)
            Button {
                _ = Self.handleOutgoingLink(
                    Self.discoverURL,
                    navigation: navCoordinator,
                    dismiss: { dismiss() }
                )
            } label: {
                Text(AboutCopy12672.primaryCTA)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Color.white)
                    .padding(.horizontal, 28)
                    .padding(.vertical, 13)
                    .background(DS.textPrimary, in: Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("about-start-exploring-cta")
            Spacer(minLength: 0)
        }
        .padding(.top, 4)
    }

    /// Ruling 195-A + `#12735`: single final row in page flow (never a pinned bar, never duplicated).
    private var bottomFinePrintRow: some View {
        VStack(spacing: 14) {
            Rectangle()
                .fill(DS.border)
                .frame(height: 1)
                .accessibilityHidden(true)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    Link("bugs@bainluck.com", destination: Self.bugsMailURL)
                    Text("\u{00B7}").foregroundStyle(DS.textMuted).accessibilityHidden(true)
                    Link("Privacy Policy", destination: Self.privacyURL)
                    Text("\u{00B7}").foregroundStyle(DS.textMuted).accessibilityHidden(true)
                    Link("Picture credits", destination: Self.pictureCreditsURL)
                }

                VStack(spacing: 6) {
                    Link("bugs@bainluck.com", destination: Self.bugsMailURL)
                    HStack(spacing: 8) {
                        Link("Privacy Policy", destination: Self.privacyURL)
                        Text("\u{00B7}").foregroundStyle(DS.textMuted).accessibilityHidden(true)
                        Link("Picture credits", destination: Self.pictureCreditsURL)
                    }
                }
            }
            .font(.caption)
            .foregroundStyle(DS.textSecondaryReadable)
            .tint(DS.textSecondaryReadable)
            .frame(maxWidth: .infinity)
        }
        .padding(.top, 4)
        .accessibilityIdentifier("about-bottom-links-row")
    }
}
