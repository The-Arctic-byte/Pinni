import Foundation
import Observation

/// App-wide state: who is reading, their profile, the ranked feed and the stories it points to.
@Observable
final class AppModel {
    enum LoadState: Equatable {
        case idle, loading, loaded
        case failed(String)
    }

    private static let onboardingKey = "onboarding.completed"

    private let service: any NewsService
    private let defaults: UserDefaults

    private(set) var persona: Persona
    private(set) var hasCompletedOnboarding: Bool
    private(set) var state: LoadState = .idle
    private(set) var profile: Profile?
    private(set) var places: [String: Place] = [:]
    private(set) var feed: FeedPage?
    private(set) var stories: [String: Story] = [:]

    /// Bumped on every load so a slower, older load cannot overwrite a newer one.
    @ObservationIgnored private var loadGeneration = 0

    /// A fresh install is the anonymous new user; the debug switch in Profile picks other mock readers.
    init(service: any NewsService = MockNewsService(), persona: Persona = .newUser, defaults: UserDefaults = .standard) {
        self.service = service
        #if DEBUG
        // `-persona sara` as a launch argument picks a mock reader (screenshots).
        self.persona = defaults.string(forKey: "persona").flatMap(Persona.init(rawValue:)) ?? persona
        #else
        self.persona = persona
        #endif
        self.defaults = defaults
        self.hasCompletedOnboarding = defaults.bool(forKey: Self.onboardingKey)
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
        loadGeneration += 1
        let generation = loadGeneration
        state = .loading
        do {
            let userId = persona.userId
            async let profile = service.profile(for: userId)
            async let places = service.places()
            async let feed = service.feed(for: userId)
            let page = try await feed
            let loaded = try await service.stories(ids: page.items.map(\.storyId))
            let loadedProfile = try await profile
            let loadedPlaces = try await places
            guard generation == loadGeneration else { return }
            self.profile = loadedProfile
            self.places = Dictionary(uniqueKeysWithValues: loadedPlaces.map { ($0.id, $0) })
            self.feed = page
            self.stories = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
            state = .loaded
        } catch {
            guard generation == loadGeneration else { return }
            state = .failed(String(describing: error))
        }
    }

    func switchPersona(to persona: Persona) async {
        guard persona != self.persona else { return }
        self.persona = persona
        await load()
    }

    /// Saves the onboarding result as the anonymous reader's first profile and logs one event per step.
    func completeOnboarding(with answers: OnboardingAnswers) async {
        let userId = Persona.newUser.userId
        let now = Date()
        do {
            _ = try await service.save(answers.profile(userId: userId, now: now))
            try await service.send(answers.events(userId: userId, now: now) { "ev-" + UUID().uuidString.lowercased() })
        } catch {
            state = .failed(String(describing: error))
            return
        }
        defaults.set(true, forKey: Self.onboardingKey)
        hasCompletedOnboarding = true
        persona = .newUser
        await load()
    }

    #if DEBUG
    func restartOnboarding() {
        defaults.removeObject(forKey: Self.onboardingKey)
        hasCompletedOnboarding = false
    }
    #endif
}
