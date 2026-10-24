import SwiftUI

/// Every story in one list, in the order the backend ranked them for this reader.
struct NewsScreen: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .idle, .loading:
                    ProgressView()
                case .failed(let message):
                    ContentUnavailableView("Couldn’t load news", systemImage: "exclamationmark.triangle", description: Text(message))
                case .loaded:
                    list
                }
            }
            .navigationTitle(Text("News"))
            .navigationDestination(for: Story.self) { story in
                StoryDetailPlaceholder(story: story, language: model.contentLanguage)
            }
        }
    }

    private var list: some View {
        List(model.rankedStories, id: \.item.id) { entry in
            NavigationLink(value: entry.story) {
                StoryRow(story: entry.story, item: entry.item, language: model.contentLanguage)
            }
        }
    }
}

/// Stand-in until A7 builds the full story view.
private struct StoryDetailPlaceholder: View {
    let story: Story
    let language: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(story.title.text(for: language))
                    .font(.title2.bold())
                Text(story.explanation.forYou.text(for: language))
                    .font(.body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .environment(\.layoutDirection, language.contentLayoutDirection)
        }
    }
}

#Preview {
    NewsScreen()
        .environment(AppModel())
}
