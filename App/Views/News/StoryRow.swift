import SwiftUI

/// One story in a list: place, why it is here, and a short mark when it matters to this reader.
struct StoryRow: View {
    @Environment(AppModel.self) private var model
    @Environment(\.locale) private var locale
    let story: Story
    let item: FeedItem
    let language: String

    private var uiLanguage: String { locale.language.languageCode?.identifier ?? "en" }
    private var placeName: String? { model.places[story.placeId]?.name.text(for: uiLanguage) }
    private var showsMark: Bool { item.mustSee || item.relevance >= 0.7 }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if placeName != nil || showsMark {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let placeName {
                        Text(verbatim: placeName)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    mark
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(story.title.text(for: language))
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                if let reason = item.reasons.first {
                    Text(reason.text(for: language))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .environment(\.layoutDirection, story.title.shownLanguage(for: language).contentLayoutDirection)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var mark: some View {
        if item.mustSee {
            Text("Must see")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tint)
                .lineLimit(1)
        } else if item.relevance >= 0.7 {
            Text("For you", comment: "Badge on a story that ranks high for this reader.")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tint)
                .lineLimit(1)
        }
    }
}
