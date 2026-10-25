import SwiftUI

// MARK: - Shimmer Effect

struct ShimmerModifier: ViewModifier {
    /// #11288 — lighter than the old 0.35 so the sweep no longer washes the
    /// darker bars back toward the row colour.
    static let sweepOpacity: Double = 0.25

    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay(
                GeometryReader { geo in
                    LinearGradient(
                        colors: [.clear, .white.opacity(Self.sweepOpacity), .clear],
                        startPoint: .init(x: phase - 0.3, y: phase - 0.3),
                        endPoint: .init(x: phase + 0.3, y: phase + 0.3)
                    )
                    .frame(width: geo.size.width, height: geo.size.height)
                }
                .clipped()
            )
            .onAppear {
                withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    phase = 2
                }
            }
    }
}

extension View {
    func shimmer() -> some View {
        modifier(ShimmerModifier())
    }
}

// MARK: - Skeleton Primitives

extension Color {
    /// #11288 — placeholder bars. `systemGray5` (#E5E5EA) sat at about 1.26:1 on
    /// a white row, so 5–10 s of skeleton read as a blank screen on a phone.
    /// `systemGray3` (#C7C7CC) is about 1.7:1 and still reads as a placeholder,
    /// not content; the caption on `SkeletonFeedView` is what says "loading".
    #if os(iOS)
    static let skeletonFill = Color(.systemGray3)
    #else
    static let skeletonFill = Color.gray.opacity(0.35)
    #endif
}

struct SkeletonShape: View {
    var width: CGFloat? = nil
    var height: CGFloat = 14
    var cornerRadius: CGFloat = 4

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(Color.skeletonFill)
            .frame(width: width, height: height)
    }
}

// MARK: - Skeleton Event Card

struct SkeletonEventCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Top bar
            HStack(spacing: 6) {
                SkeletonShape(width: 36, height: 10)
                SkeletonShape(width: 44, height: 10)
                Spacer()
                SkeletonShape(width: 50, height: 10)
            }

            // Away team row
            HStack(spacing: 8) {
                Circle().fill(Color.skeletonFill).frame(width: 24, height: 24)
                SkeletonShape(width: .random(in: 90...140), height: 14)
                Spacer()
                SkeletonShape(width: 32, height: 14)
            }

            // Probability bar
            SkeletonShape(height: 6, cornerRadius: 3)

            // Home team row
            HStack(spacing: 8) {
                Circle().fill(Color.skeletonFill).frame(width: 24, height: 24)
                SkeletonShape(width: .random(in: 90...140), height: 14)
                Spacer()
                SkeletonShape(width: 32, height: 14)
            }

            // Footer
            HStack {
                SkeletonShape(width: 100, height: 9)
                Spacer()
            }
        }
        .padding(.vertical, 6)
        .shimmer()
    }
}

// MARK: - Skeleton Futures Card

struct SkeletonFuturesCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                SkeletonShape(width: 60, height: 10)
                Spacer()
                SkeletonShape(width: 50, height: 10)
            }

            // Market name
            SkeletonShape(height: 14)

            // Outcome rows
            ForEach(0..<3, id: \.self) { _ in
                HStack(spacing: 8) {
                    SkeletonShape(width: .random(in: 80...130), height: 12)
                    Spacer()
                    SkeletonShape(width: 30, height: 12)
                }
            }
        }
        .padding(.vertical, 6)
        .shimmer()
    }
}

// MARK: - Skeleton Feed (full loading state)

struct SkeletonFeedView: View {
    /// #11288 — a short visible line with a spinner, e.g. "Loading games…". The
    /// bars alone carry no words, so a slow load looked like an empty screen.
    var caption: String? = nil

    var body: some View {
        List {
            if let caption {
                Section {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text(caption)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(caption)
                }
            }

            Section {
                SkeletonEventCard()
                SkeletonEventCard()
                SkeletonEventCard()
            } header: {
                HStack(spacing: 6) {
                    SkeletonShape(width: 80, height: 12)
                    SkeletonShape(width: 18, height: 12, cornerRadius: 6)
                }
            }

            Section {
                SkeletonEventCard()
                SkeletonEventCard()
            } header: {
                HStack(spacing: 6) {
                    SkeletonShape(width: 70, height: 12)
                    SkeletonShape(width: 18, height: 12, cornerRadius: 6)
                }
            }

            Section {
                SkeletonFuturesCard()
                SkeletonFuturesCard()
            } header: {
                HStack(spacing: 6) {
                    SkeletonShape(width: 90, height: 12)
                    SkeletonShape(width: 18, height: 12, cornerRadius: 6)
                }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .disabled(true)
    }
}
