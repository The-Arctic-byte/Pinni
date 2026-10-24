import SwiftUI

/// Short story view used from the map and the news list until A7 builds the full story.
/// Logs that it was opened and how long it was read, and carries the reader's feedback controls.
struct StoryPreview: View {
    @Environment(AppModel.self) private var model
    let story: Story
    let item: FeedItem?
    let language: String
    @State private var openedAt: Date?

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
                Divider()
                StoryFeedbackBar(story: story)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .environment(\.layoutDirection, story.title.shownLanguage(for: language).contentLayoutDirection)
        }
        .onAppear {
            openedAt = Date()
            model.opened(story, from: .story)
        }
        .onDisappear {
            if let openedAt { model.read(story, for: Date().timeIntervalSince(openedAt)) }
            openedAt = nil
        }
    }
}
