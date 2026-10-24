import Foundation
import Observation

/// App-wide state: who is reading, their profile, the ranked feed and the stories it points to.
@Observable
final class AppModel {
    enum LoadState: Equatable {
        case idle, loading, loaded
        case failed(String)
    }

    private let service: any NewsService

    private(set) var persona: Persona
    private(set) var state: LoadState = .idle
    private(set) var profile: Profile?
    private(set) var places: [String: Place] = [:]
    private(set) var feed: FeedPage?
    private(set) var stories: [String: Story] = [:]

    init(service: any NewsService = MockNewsService(), persona: Persona = .sara) {
        self.service = service
        self.persona = persona
    }

    /// Language stories are shown in. Falls back to English per text when a translation is missing.
    var contentLanguage: String { profile?.language ?? "en" }

    /// Feed items with their story, in the backend's order.
    var rankedStories: [(item: FeedItem, story: Story)] {
        (feed?.items ?? []).compactMap { item in
            stories[item.storyId].map { (item, $0) }
        }
    }

    func load() async {
        state = .loading
        do {
            let userId = persona.userId
            async let profile = service.profile(for: userId)
            async let places = service.places()
            async let feed = service.feed(for: userId)
            let page = try await feed
            let loaded = try await service.stories(ids: page.items.map(\.storyId))
            self.profile = try await profile
            self.places = Dictionary(uniqueKeysWithValues: try await places.map { ($0.id, $0) })
            self.feed = page
            self.stories = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
            state = .loaded
        } catch {
            state = .failed(String(describing: error))
        }
    }

    func switchPersona(to persona: Persona) async {
        guard persona != self.persona else { return }
        self.persona = persona
        await load()
    }
}
