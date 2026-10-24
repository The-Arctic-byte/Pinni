import SwiftUI

struct StoryRow: View {
    let story: Story
    let item: FeedItem
    let language: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: story.category.symbolName)
                .font(.title3)
                .foregroundStyle(.secondary)
                .frame(width: 32, height: 32)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 4) {
                if item.mustSee {
                    Text("Must see")
                        .font(.caption.bold())
                        .foregroundStyle(.tint)
                }
                Text(story.title.text(for: language))
                    .font(.headline)
                if let reason = item.reasons.first {
                    Text(reason.text(for: language))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .environment(\.layoutDirection, language.contentLayoutDirection)
            .frame(maxWidth: .infinity, alignment: .leading)

            RelevanceBars(relevance: item.relevance)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

/// Four bars, as in the demo: how much this matters to the reader.
struct RelevanceBars: View {
    let relevance: Double

    private var filled: Int { Int((relevance * 4).rounded()) }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<4, id: \.self) { index in
                Capsule()
                    .fill(index < filled ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary))
                    .frame(width: 4, height: 14)
            }
        }
        .accessibilityElement()
        .accessibilityLabel(Text("Relevance \(filled) of 4"))
    }
}
