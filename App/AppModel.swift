import Foundation
import Observation

/// App-wide state: who is reading, their profile, the ranked feed and the stories it points to,
/// plus everything the reader tells us back: reactions, hidden stories, reports and the events for the recommender.
@Observable
final class AppModel {
    enum LoadState: Equatable {
        case idle, loading, loaded
        case failed(String)
    }

    enum Reaction: String, Codable {
        case like, dislike
    }

    /// What the reader did that the app shows right away, before the backend re-ranks. Kept per reader.
    private struct LocalFeedback: Codable {
        var reactions: [String: Reaction] = [:]
        var hidden: Set<String> = []
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
    private(set) var reports: [Report] = []
    private var feedback = LocalFeedback()
    /// Events not yet accepted by the backend; sent again on the next change (A8).
    @ObservationIgnored private var pendingEvents: [Event] = []

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

    /// Feed items with their story, in the backend's order, without what the reader hid.
    /// A category the reader turned off never hides must-see stories.
    var rankedStories: [(item: FeedItem, story: Story)] {
        let blocked = Set(profile?.hardFilters.categories ?? [])
        return (feed?.items ?? []).compactMap { item in
            guard !feedback.hidden.contains(item.storyId), let story = stories[item.storyId] else { return nil }
            if blocked.contains(story.category), !item.mustSee { return nil }
            return (item, story)
        }
    }

    func reaction(to storyId: String) -> Reaction? {
        feedback.reactions[storyId]
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
            let loadedReports = try await service.reports(for: userId)
            guard generation == loadGeneration else { return }
            self.feedback = Self.storedFeedback(for: userId, in: defaults)
            self.pendingEvents = Self.storedEvents(in: defaults)
            self.reports = loadedReports
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

    // MARK: Feedback

    /// Like or dislike; the same reaction again takes it back (sent with value 0).
    func react(_ reaction: Reaction, to story: Story) {
        let undo = feedback.reactions[story.id] == reaction
        feedback.reactions[story.id] = undo ? nil : reaction
        saveFeedback()
        record(reaction == .like ? .like : .dislike, storyId: story.id, value: undo ? 0 : 1)
    }

    /// "Not for me": hides the story, or every story in its category (a hard filter in the profile).
    func hide(_ story: Story, wholeCategory: Bool) async {
        feedback.hidden.insert(story.id)
        saveFeedback()
        record(.notForMe, storyId: story.id, detail: ["scope": .string(wholeCategory ? "category" : "story"), "category": .string(story.category.rawValue)])
        guard wholeCategory, var updated = profile, !updated.hardFilters.categories.contains(story.category) else { return }
        updated.hardFilters.categories.append(story.category)
        updated.updatedAt = Date()
        if let saved = try? await service.save(updated) { profile = saved }
    }

    func shared(_ story: Story) {
        record(.share, storyId: story.id)
    }

    func opened(_ story: Story, from screen: Event.Context.Screen) {
        record(.open, storyId: story.id, screen: screen)
    }

    /// Reading time is attention: a story read for a while says more than one opened and closed.
    func read(_ story: Story, for seconds: TimeInterval) {
        guard seconds >= 2 else { return }
        record(.dwell, storyId: story.id, value: seconds.rounded(), screen: .story)
    }

    // MARK: Reports

    /// Sends a report for a human editor (contract/processes/report-review.md). The reader follows it on My reports.
    func submit(_ draft: ReportDraft) async throws -> Report {
        let report = try await service.submit(draft, reporterId: persona.userId)
        reports.insert(report, at: 0)
        record(.report, storyId: draft.kind == .problem ? draft.storyId : nil, detail: ["reportId": .string(report.id)])
        if draft.kind == .problem, let id = draft.storyId { record(.flagWrong, storyId: id) }
        return report
    }

    // MARK: Events

    private func record(_ kind: Event.Kind, storyId: String? = nil, value: Double? = nil,
                        detail: [String: JSONValue]? = nil, screen: Event.Context.Screen? = nil) {
        let event = Event(
            id: "ev-" + UUID().uuidString.lowercased(),
            userId: persona.userId,
            type: kind,
            storyId: storyId,
            value: value,
            detail: detail,
            context: screen.map { .init(screen: $0) },
            occurredAt: Date()
        )
        pendingEvents.append(event)
        Self.store(pendingEvents, in: defaults)
        Task { await flushEvents() }
    }

    /// Sends the queue; on failure the events stay and go with the next one.
    private func flushEvents() async {
        let batch = pendingEvents
        guard !batch.isEmpty else { return }
        do {
            try await service.send(batch)
            pendingEvents.removeFirst(min(batch.count, pendingEvents.count))
            Self.store(pendingEvents, in: defaults)
        } catch {
            // Kept for the next try.
        }
    }

    // MARK: Local storage

    private func saveFeedback() {
        defaults.set(try? JSONEncoder.contract.encode(feedback), forKey: "feedback." + persona.userId)
    }

    private static func storedFeedback(for userId: String, in defaults: UserDefaults) -> LocalFeedback {
        defaults.data(forKey: "feedback." + userId).flatMap { try? JSONDecoder.contract.decode(LocalFeedback.self, from: $0) } ?? LocalFeedback()
    }

    private static func storedEvents(in defaults: UserDefaults) -> [Event] {
        defaults.data(forKey: "events.pending").flatMap { try? JSONDecoder.contract.decode([Event].self, from: $0) } ?? []
    }

    private static func store(_ events: [Event], in defaults: UserDefaults) {
        defaults.set(try? JSONEncoder.contract.encode(events), forKey: "events.pending")
    }

    #if DEBUG
    /// Plays the editor on the mock (Track C's admin page does this for real). The demo has no push:
    /// the outcome shows on My reports, and a published tip appears on the map.
    func simulateEditor(_ report: Report, approve: Bool) async {
        guard let mock = service as? MockNewsService else { return }
        let decided = mock.decide(report, approve: approve, homePlaceId: profile?.homePlaceId)
        if let index = reports.firstIndex(where: { $0.id == report.id }) { reports[index] = decided }
        if decided.status == .published { await load() }
    }

    func restartOnboarding() {
        defaults.removeObject(forKey: Self.onboardingKey)
        hasCompletedOnboarding = false
    }
    #endif
}
