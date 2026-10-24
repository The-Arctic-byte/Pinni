import SwiftUI

/// The news list that goes with the map: the stories under the current scale, ranked for the reader,
/// the stories of one tapped group pin, or those of a place chip (city, Finland, home country, EU, world),
/// which is where news without a useful map point lives. Tapping a story pushes it; the map follows `path`.
/// Shown in the map's native sheet on iPhone (with Community and Profile in its header) and in the inspector on Mac.
struct MapPanel: View {
    struct Chip: Identifiable {
        let id: String
        let name: String
        let count: Int
    }

    @Environment(AppModel.self) private var model
    let title: Text
    let entries: [(item: FeedItem, story: Story)]
    /// Must-see stories from other scales, pinned on top so personalization never hides them.
    let mustSee: [(item: FeedItem, story: Story)]
    let chips: [Chip]
    let selectedChip: String?
    let isFiltered: Bool
    @Binding var path: [String]
    let onSelectChip: (String) -> Void
    let onShowAll: () -> Void

    #if os(iOS)
    /// iPhone has no tab bar: the sections that are not the map open from the sheet's header.
    private enum Destination: Identifiable {
        case report, community, profile
        var id: Self { self }
    }

    @State private var presented: Destination? = MapPanel.launchDestination

    /// Debug builds accept `-panelSheet report|community|profile` as a launch argument (screenshots).
    private static var launchDestination: Destination? {
        #if DEBUG
        switch UserDefaults.standard.string(forKey: "panelSheet") {
        case "report": .report
        case "community": .community
        case "profile": .profile
        default: nil
        }
        #else
        nil
        #endif
    }
    #endif

    var body: some View {
        NavigationStack(path: $path) {
            list
                .navigationTitle(title)
                .toolbar {
                    if isFiltered {
                        ToolbarItem(placement: showAllPlacement) {
                            Button("Show all", action: onShowAll)
                        }
                    }
                    #if os(iOS)
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button("Report news", systemImage: "exclamationmark.bubble") { presented = .report }
                        Button("Community", systemImage: "person.2") { presented = .community }
                        Button("Profile", systemImage: "person.crop.circle") { presented = .profile }
                    }
                    #endif
                }
                .navigationDestination(for: String.self) { id in
                    if let story = model.stories[id] {
                        StoryDetailView(story: story)
                            .panelBackground()
                    }
                }
        }
        #if os(iOS)
        .sheet(item: $presented) { destination in
            switch destination {
            case .report: ReportForm(draft: .newsTip())
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

    private var chipRow: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(chips) { chip in
                        ChoiceChip(isSelected: chip.id == selectedChip) {
                            onSelectChip(chip.id)
                        } label: {
                            HStack(spacing: 6) {
                                Text(verbatim: chip.name)
                                Text(chip.count, format: .number)
                                    .opacity(0.7)
                            }
                        }
                        .id(chip.id)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 6)
            }
            .scrollIndicators(.hidden)
            .onChange(of: selectedChip, initial: true) { _, id in
                guard let id else { return }
                withAnimation { proxy.scrollTo(id, anchor: .center) }
            }
        }
    }

    @ViewBuilder
    private var list: some View {
        Group {
            if model.showsUnreachableAPI {
                ContentUnavailableView {
                    Label("Couldn’t load news", systemImage: "exclamationmark.triangle")
                } description: {
                    Text("Open Profile to change the API URL.")
                } actions: {
                    #if os(iOS)
                    Button("Profile") { presented = .profile }
                    #endif
                }
            } else if entries.isEmpty && mustSee.isEmpty {
                // Keep the chips: an empty chip (e.g. the EU) must not trap the reader on it.
                VStack(spacing: 0) {
                    chipRow
                    ContentUnavailableView("No stories here yet", systemImage: "map", description: Text("Try another scale or place."))
                }
            } else {
                storyList
            }
        }
    }

    private var storyList: some View {
        List {
            chipRow
                .listRowSeparator(.hidden)
                .listRowInsets(.init())
            if !mustSee.isEmpty {
                Section {
                    ForEach(mustSee, id: \.item.id) { entry in
                        NavigationLink(value: entry.story.id) {
                            StoryRow(story: entry.story, item: entry.item, language: model.contentLanguage)
                        }
                    }
                } header: {
                    Label("Important for you", systemImage: "exclamationmark.circle")
                }
            }
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
