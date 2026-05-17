import SwiftUI

struct WelcomeView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var currentPage = 0

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $currentPage) {
                welcomePage.tag(0)
                accuracyPage.tag(1)
                discoverPage.tag(2)
                signInPage.tag(3)
            }
            #if os(iOS)
            .tabViewStyle(.page(indexDisplayMode: .always))
            .indexViewStyle(.page(backgroundDisplayMode: .always))
            #endif

            Button {
                if currentPage < 3 {
                    withAnimation { currentPage += 1 }
                } else {
                    dismiss()
                }
            } label: {
                Text(currentPage < 3 ? "Continue" : "Start Exploring")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.orange)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 24)
            .padding(.bottom, 24)

            if currentPage < 3 {
                Button("Skip") { dismiss() }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 16)
            }
        }
        .background(.background)
        .onAppear {
            AnalyticsService.trackScreen(name: "welcome", type: "onboarding")
        }
    }

    private var welcomePage: some View {
        VStack(spacing: 24) {
            Spacer()

            Text("🍀")
                .font(.system(size: 64))

            Text("What the world\nthinks will happen")
                .font(.largeTitle.weight(.black))
                .multilineTextAlignment(.center)

            Text("See what the world thinks will happen — powered by prediction market data, across sports, politics, economics, and more.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            HStack(spacing: 32) {
                VStack(spacing: 4) {
                    Text("60%")
                        .font(.system(size: 36, weight: .black).monospacedDigit())
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Text("Celtics")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text("vs")
                    .font(.subheadline)
                    .foregroundStyle(.tertiary)
                VStack(spacing: 4) {
                    Text("40%")
                        .font(.system(size: 36, weight: .black).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Text("76ers")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(20)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

            Text("Not \"-150 / +130\" — just probabilities.")
                .font(.caption)
                .foregroundStyle(.tertiary)

            Spacer()
            Spacer()
        }
        .padding(.horizontal)
    }

    private var accuracyPage: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "target")
                .font(.system(size: 48))
                .foregroundStyle(.orange)

            Text("Surprisingly\naccurate")
                .font(.largeTitle.weight(.black))
                .multilineTextAlignment(.center)

            Text("Prediction markets are among the most accurate forecasting tools ever measured.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            VStack(spacing: 12) {
                statRow(predicted: "80%", actual: "~80%", label: "events happen")
                statRow(predicted: "20%", actual: "~20%", label: "events happen")
                statRow(predicted: "50%", actual: "~50%", label: "events happen")
            }
            .padding(20)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

            Text("474K resolved outcomes, 5.7pp average calibration error")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)

            Spacer()
            Spacer()
        }
        .padding(.horizontal)
    }

    private var discoverPage: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "hand.draw.fill")
                .font(.system(size: 48))
                .foregroundStyle(.orange)

            Text("Swipe through\nDiscover")
                .font(.largeTitle.weight(.black))
                .multilineTextAlignment(.center)

            Text("Each card is a live prediction. Swipe to tune your feed, tap to explore the full market.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            VStack(spacing: 16) {
                HStack(spacing: 12) {
                    Image(systemName: "arrow.left")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.red)
                        .frame(width: 40)
                    Text("Swipe left for less like this")
                        .font(.subheadline)
                    Spacer()
                }

                HStack(spacing: 12) {
                    Image(systemName: "arrow.right")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.green)
                        .frame(width: 40)
                    Text("Swipe right for more like this")
                        .font(.subheadline)
                    Spacer()
                }

                HStack(spacing: 12) {
                    Image(systemName: "hand.tap.fill")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.blue)
                        .frame(width: 40)
                    Text("Tap to see the full detail page")
                        .font(.subheadline)
                    Spacer()
                }

                HStack(spacing: 12) {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.orange)
                        .frame(width: 40)
                    Text("Play Higher/Lower to test your instincts")
                        .font(.subheadline)
                    Spacer()
                }
            }
            .padding(20)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

            Spacer()
            Spacer()
        }
        .padding(.horizontal)
    }

    private var signInPage: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(.system(size: 48))
                .foregroundStyle(.orange)

            Text("Sign in to\nsave your streak")
                .font(.largeTitle.weight(.black))
                .multilineTextAlignment(.center)

            Text("Your predictions and streaks sync across devices when you sign in. Totally optional — browse freely without an account.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            VStack(spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: "flame.fill")
                        .foregroundStyle(.orange)
                        .frame(width: 24)
                    Text("Track your prediction streak")
                        .font(.subheadline)
                    Spacer()
                }
                HStack(spacing: 12) {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.orange)
                        .frame(width: 24)
                    Text("Follow teams and topics")
                        .font(.subheadline)
                    Spacer()
                }
                HStack(spacing: 12) {
                    Image(systemName: "tv.fill")
                        .foregroundStyle(.orange)
                        .frame(width: 24)
                    Text("Use event pages as a second screen during games")
                        .font(.subheadline)
                    Spacer()
                }
            }
            .padding(20)
            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

            Spacer()
            Spacer()
        }
        .padding(.horizontal)
    }

    private func statRow(predicted: String, actual: String, label: String) -> some View {
        HStack(spacing: 8) {
            Text("Predicted")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 60, alignment: .trailing)
            Text(predicted)
                .font(.headline.weight(.black).monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.75)
                .frame(width: 54, alignment: .trailing)
            Image(systemName: "arrow.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
            Text(actual)
                .font(.headline.weight(.black).monospacedDigit())
                .foregroundStyle(.orange)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
                .frame(width: 62, alignment: .leading)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
    }
}
