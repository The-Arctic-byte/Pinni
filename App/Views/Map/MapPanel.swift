import SwiftUI

/// The news list that goes with the map: the stories under the current scale, ranked for the reader,
/// or the stories of one tapped group pin. Tapping a story pushes it; the map follows `path`.
/// Shown in the map's native sheet on iPhone (with Community and Profile in its header) and in the inspector on Mac.
struct MapPanel: View {
    @Environment(AppModel.self) private var model
    let title: Text
    let entries: [(item: FeedItem, story: Story)]
    let isGroup: Bool
    @Binding var path: [String]
    let onShowAll: () -> Void

    #if os(iOS)
    /// iPhone has no tab bar: the sections that are not the map open from the sheet's header.
    private enum Destination: Identifiable {
        case community, profile
        var id: Self { self }
    }

    @State private var presented: Destination?
    #endif

    var body: some View {
        NavigationStack(path: $path) {
            list
                .navigationTitle(title)
                .toolbar {
                    if isGroup {
                        ToolbarItem(placement: showAllPlacement) {
                            Button("Show all", action: onShowAll)
                        }
                    }
                    #if os(iOS)
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button("Community", systemImage: "person.2") { presented = .community }
                        Button("Profile", systemImage: "person.crop.circle") { presented = .profile }
                    }
                    #endif
                }
                .navigationDestination(for: String.self) { id in
                    if let story = model.stories[id] {
                        StoryPreview(story: story, item: model.feed?.items.first { $0.storyId == id }, language: model.contentLanguage)
                            .panelBackground()
                    }
                }
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
        }
        .panelBackground()
        #if os(iOS)
        .sheet(item: $presented) { destination in
            switch destination {
            case .community: CommunityScreen()
            case .profile: ProfileScreen()
            }
        }
        #endif
    }

    private var showAllPlacement: ToolbarItemPlacement {
        #if os(iOS)
        .topBarLeading
        #else
        .primaryAction
        #endif
    }

    @ViewBuilder
    private var list: some View {
        if entries.isEmpty {
            ContentUnavailableView("No stories here yet", systemImage: "map", description: Text("Try another scale."))
                .panelBackground()
        } else {
            List {
                Section {
                    ForEach(entries, id: \.item.id) { entry in
                        NavigationLink(value: entry.story.id) {
                            StoryRow(story: entry.story, item: entry.item, language: model.contentLanguage)
                        }
                    }
                } footer: {
                    Text("Sorted by how much it matters to you")
                }
            }
            .listStyle(.plain)
            .panelBackground()
        }
    }
}

private extension View {
    /// Lets the panel's material show through the navigation stack and list (iPhone); plain on Mac.
    @ViewBuilder
    func panelBackground() -> some View {
        #if os(iOS)
        scrollContentBackground(.hidden)
            .containerBackground(.clear, for: .navigation)
        #else
        self
        #endif
    }
}
