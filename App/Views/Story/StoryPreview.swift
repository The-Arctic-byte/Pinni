import SwiftUI

/// Short story view used from the map and the news list until A7 builds the full story.
struct StoryPreview: View {
    let story: Story
    let item: FeedItem?
    let language: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Label(story.category.title, systemImage: story.category.symbolName)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(story.title.text(for: language))
                    .font(.title2.bold())
                if let reason = item?.reasons.first {
                    Text(reason.text(for: language))
                        .font(.subheadline)
                        .foregroundStyle(.tint)
                }
                Text(story.explanation.forYou.text(for: language))
                    .font(.body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .environment(\.layoutDirection, story.title.shownLanguage(for: language).contentLayoutDirection)
        }
    }
}
