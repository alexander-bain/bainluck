import SwiftUI

let DAILY_GOAL = 5

struct NativeDailyChallengeCard: View {
    let guessesToday: Int
    var onStart: (() -> Void)? = nil
    private var completed: Bool { guessesToday >= DAILY_GOAL }
    private var progress: Double { min(Double(guessesToday) / Double(DAILY_GOAL), 1.0) }

    var body: some View {
        HStack(spacing: 12) {
            Text(completed ? "🏆" : "🎯")
                .font(.system(size: 28))

            VStack(alignment: .leading, spacing: 2) {
                Text(completed ? "Daily Challenge Complete!" : "Today's Challenge")
                    .font(.subheadline.weight(.bold))
                Text(completed
                     ? "Come back tomorrow for a new challenge"
                     : "Tap Higher or Lower on \(DAILY_GOAL) cards · \(guessesToday)/\(DAILY_GOAL)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if completed {
                Image(systemName: "checkmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.green)
            } else {
                ZStack {
                    Circle()
                        .stroke(Color.secondary.opacity(0.2), lineWidth: 3)
                    Circle()
                        .trim(from: 0, to: progress)
                        .stroke(Color.orange, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .animation(.easeInOut(duration: 0.5), value: progress)
                    Text("\(guessesToday)")
                        .font(.caption.weight(.bold).monospacedDigit())
                }
                .frame(width: 40, height: 40)

                Button {
                    onStart?()
                } label: {
                    Text("Play")
                        .font(.caption.weight(.heavy))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.orange, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(completed ? Color.green.opacity(0.5) : Color.orange.opacity(0.3), lineWidth: 2))
    }
}

struct NativeChallengeSheet: View {
    let items: [FeedItem]
    @Binding var currentIndex: Int
    @Binding var completed: Bool
    let onClose: () -> Void
    let onGuessCompleted: () -> Void
    let onComplete: () -> Void
    @State private var completionRecorded = false

    private var goal: Int {
        min(DAILY_GOAL, max(items.count, 1))
    }

    private var progress: Double {
        completed ? 1.0 : min(Double(currentIndex) / Double(goal), 1.0)
    }

    private var currentItem: FeedItem? {
        guard currentIndex < items.count else { return nil }
        return items[currentIndex]
    }

    private var isLastQuestion: Bool {
        currentIndex >= goal - 1
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Today's Challenge")
                            .font(.headline.weight(.black))
                        Text(completed ? "Set complete" : "Question \(min(currentIndex + 1, goal)) of \(goal)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Button(action: onClose) {
                        Image(systemName: "xmark")
                            .font(.caption.weight(.heavy))
                            .foregroundStyle(.secondary)
                            .frame(width: 32, height: 32)
                            .background(Color.secondary.opacity(0.10), in: Circle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal)
                .padding(.top, 16)

                ProgressView(value: progress)
                    .tint(.orange)
                    .padding(.horizontal)
                    .padding(.top, 12)
                    .padding(.bottom, 16)

                ScrollView {
                    VStack(spacing: 16) {
                        if completed {
                            VStack(spacing: 14) {
                                Text("🏆")
                                    .font(.system(size: 44))
                                Text("Challenge complete")
                                    .font(.title3.weight(.black))
                                Text("Your predictions are counted. Come back tomorrow for a fresh set.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .multilineTextAlignment(.center)
                                Button("Back to Discover", action: onClose)
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 13)
                                    .background(Color.primary, in: RoundedRectangle(cornerRadius: 14))
                            }
                            .padding(20)
                            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 20))
                        } else if let item = currentItem {
                            challengeCard(for: item)
                        } else {
                            VStack(spacing: 12) {
                                Text("No challenge cards right now")
                                    .font(.headline.weight(.bold))
                                Text("Check back after the feed refreshes.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Button("Back to Discover", action: onClose)
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 13)
                                    .background(Color.primary, in: RoundedRectangle(cornerRadius: 14))
                            }
                            .padding(20)
                            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 20))
                        }
                    }
                    .padding()
                }
            }
            .background(Color.groupedBackground.ignoresSafeArea())
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
    }

    @ViewBuilder
    private func challengeCard(for item: FeedItem) -> some View {
        let label = isLastQuestion ? "Finish" : "Next"
        if item.type == "futures", let futures = item.futures {
            NativeGuessCard(
                data: futures,
                onNextQuestion: advance,
                nextButtonLabel: label,
                onGuessCompleted: onGuessCompleted
            )
        } else if item.type == "event", let event = item.event {
            NativeGuessCard(
                event: event,
                onNextQuestion: advance,
                nextButtonLabel: label,
                onGuessCompleted: onGuessCompleted
            )
        }
    }

    private func advance() {
        let next = currentIndex + 1
        if next >= items.count || next >= DAILY_GOAL {
            completed = true
            if !completionRecorded {
                completionRecorded = true
                onComplete()
            }
            return
        }
        currentIndex = next
    }
}
