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
                    LoadFailure(message: message) { await model.load() }
                case .loaded:
                    list
                }
            }
            .navigationTitle(Text("News"))
            .navigationDestination(for: Story.self) { story in
                StoryDetailView(story: story)
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

#Preview {
    NewsScreen()
        .environment(AppModel())
}
