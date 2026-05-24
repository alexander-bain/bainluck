import SwiftUI

struct DiscoverLabelingView: View {
    @StateObject private var viewModel = DiscoverLabelingViewModel()
    @State private var selectedLabel: String?
    @State private var selectedTags: Set<String> = []
    @State private var notes = ""
    @State private var betterThanPrevious = false
    @State private var worseThanNext = false

    private let labels = [
        ("love", "Love"),
        ("fine", "Fine"),
        ("bad", "Bad"),
        ("kill", "Kill"),
    ]

    private let reasonTags = [
        "movement", "public_story", "high_stakes", "close_probability",
        "source_disagreement", "celebrity_or_person", "sports_relevance",
        "fun_or_weird", "timely", "surprising_probability", "major_event",
        "finance_ladder", "commodity_ladder", "too_niche", "duplicate",
        "stale", "unclear", "bad_image", "low_stakes", "repetitive",
        "misleading", "generic_hook", "wrong_category", "not_a_real_prediction",
    ]

    var body: some View {
        labelingContent
        .navigationTitle("Discover Labeling")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            if viewModel.items.isEmpty && !viewModel.loading {
                await viewModel.load()
            }
        }
    }

    private var labelingContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if viewModel.loading {
                    ProgressView("Loading debug feed...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else if let error = viewModel.error {
                    errorCard(error)
                }

                if let item = viewModel.currentItem {
                    reviewCard(item)
                    formControls
                } else if !viewModel.loading {
                    completedState
                }
            }
            .padding()
        }
        .refreshable {
            resetForm()
            await viewModel.load()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(viewModel.reviewedCount)/\(viewModel.items.count) reviewed")
                        .font(.subheadline.weight(.semibold))
                    Text("\(viewModel.remainingCount) remaining")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if viewModel.submittedCount > 0 {
                    Text("\(viewModel.submittedCount) saved")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.accentColor.opacity(0.12), in: Capsule())
                }
            }

            ProgressView(
                value: Double(viewModel.reviewedCount),
                total: Double(max(viewModel.items.count, 1))
            )

            if !viewModel.labelCounts.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(viewModel.labelCounts.sorted(by: { $0.key < $1.key }), id: \.key) { label, count in
                        Text("\(count) \(label)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.12), in: Capsule())
                    }
                }
            }
        }
    }

    private func errorCard(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(message, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
            HStack {
                Button("Retry") {
                    Task { await viewModel.load() }
                }
                .buttonStyle(.bordered)
            }
        }
        .font(.subheadline)
        .padding()
        .background(Color.red.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
    }

    private func reviewCard(_ item: DiscoverLabelingDebugItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.name)
                        .font(.headline)
                    if let headline = item.headline, !headline.isEmpty {
                        Text(headline)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("#\(item.rank)")
                        .font(.title3.weight(.bold))
                    Text("score \(Int(item.score.rounded()))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            FlowLayout(spacing: 6) {
                pill(item.category)
                pill(item.archetype ?? "unknown")
                pill(item.source ?? "unknown")
                pill(item.qualityClass ?? "normal")
                if item.hook == true { pill("hook") }
                if item.image == true { pill("image") }
                if let storyKey = item.storyKey { pill(storyKey) }
            }

            if let context = item.context ?? item.reason, !context.isEmpty {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            }

            if let outcomes = item.topOutcomes, !outcomes.isEmpty {
                VStack(spacing: 8) {
                    ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { _, outcome in
                        HStack {
                            Text(outcome.name ?? "Outcome")
                                .font(.subheadline)
                                .lineLimit(1)
                            Spacer()
                            Text(probabilityText(outcome.probability ?? outcome.currentProbability))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.barTrack.opacity(0.35), lineWidth: 0.5))
    }

    private var formControls: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                ForEach(labels, id: \.0) { key, title in
                    Button(title) {
                        selectedLabel = key
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(labelTint(key, selected: selectedLabel == key))
                    .controlSize(.regular)
                }
            }

            FlowLayout(spacing: 6) {
                ForEach(reasonTags, id: \.self) { tag in
                    Button(displayTag(tag)) {
                        toggleTag(tag)
                    }
                    .font(.caption)
                    .buttonStyle(.bordered)
                    .tint(selectedTags.contains(tag) ? .accentColor : .secondary)
                }
            }

            HStack(spacing: 8) {
                Toggle("Should beat previous", isOn: $betterThanPrevious)
                Toggle("Should lose to next", isOn: $worseThanNext)
            }
            .font(.caption)
            .toggleStyle(.button)

            TextField("Notes", text: $notes, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            Button {
                guard let label = selectedLabel else { return }
                Task {
                    let saved = await viewModel.submit(
                        label: label,
                        reasonTags: selectedTags,
                        notes: notes,
                        betterThanPrevious: betterThanPrevious,
                        worseThanNext: worseThanNext
                    )
                    if saved {
                        resetForm()
                    }
                }
            } label: {
                if viewModel.submitting {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Submit & Next")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(selectedLabel == nil || viewModel.submitting)

            Button("Skip") {
                viewModel.skip()
                resetForm()
            }
            .frame(maxWidth: .infinity)
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
    }

    private var completedState: some View {
        VStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.green)
            Text("All reviewed")
                .font(.headline)
            Button("Reload Debug Feed") {
                resetForm()
                Task { await viewModel.load() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    private func toggleTag(_ tag: String) {
        if selectedTags.contains(tag) {
            selectedTags.remove(tag)
        } else {
            selectedTags.insert(tag)
        }
    }

    private func resetForm() {
        selectedLabel = nil
        selectedTags = []
        notes = ""
        betterThanPrevious = false
        worseThanNext = false
    }

    private func pill(_ text: String) -> some View {
        Text(displayTag(text))
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.secondary.opacity(0.12), in: Capsule())
            .lineLimit(1)
    }

    private func probabilityText(_ value: Double?) -> String {
        guard let value else { return "--" }
        return "\(Int((value * 100).rounded()))%"
    }

    private func displayTag(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ")
    }

    private func labelTint(_ label: String, selected: Bool) -> Color {
        guard selected else { return .secondary }
        switch label {
        case "love": return .green
        case "bad": return .orange
        case "kill": return .red
        default: return .accentColor
        }
    }
}
