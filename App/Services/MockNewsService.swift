import Foundation

/// Serves the contract's mock data from the app bundle. Behaves like the API: ids in, contract types out.
struct MockNewsService: NewsService {
    enum MockError: Error {
        case missingFile(String)
        case unknown(String)
    }

    let bundle: Bundle
    private let saved: SavedProfiles

    init(bundle: Bundle = .main, defaults: UserDefaults = .standard) {
        self.bundle = bundle
        self.saved = SavedProfiles(defaults: defaults)
    }

    func places() async throws -> [Place] {
        try load("places")
    }

    func feed(for userId: String) async throws -> FeedPage {
        guard let persona = Persona(userId: userId) else { throw MockError.unknown(userId) }
        return try load(persona.feedFile)
    }

    func stories(ids: [String]) async throws -> [Story] {
        let all: [Story] = try load("stories")
        let byId = Dictionary(uniqueKeysWithValues: all.map { ($0.id, $0) })
        return ids.compactMap { byId[$0] }
    }

    func profile(for userId: String) async throws -> Profile {
        if let profile = saved[userId] { return profile }
        let all: [Profile] = try load("profiles")
        guard let profile = all.first(where: { $0.userId == userId }) else { throw MockError.unknown(userId) }
        return profile
    }

    func save(_ profile: Profile) async throws -> Profile {
        saved[profile.userId] = profile
        return profile
    }

    func suggestedChannels(for userId: String) async throws -> [ChannelSuggestion] {
        // Only Sara has suggestions in the mock data; others are new to the community.
        userId == Persona.sara.userId ? try load("channel-suggestions-sara") : []
    }

    func channels() async throws -> [Channel] {
        try load("channels")
    }

    func reports(for userId: String) async throws -> [Report] {
        let all: [Report] = try load("reports")
        return all.filter { $0.reporterId == userId }
    }

    func notifications(for userId: String) async throws -> [AppNotification] {
        let all: [AppNotification] = try load("notifications")
        return all.filter { $0.userId == userId }
    }

    func send(_ events: [Event]) async throws {
        // shortcut: mock drops events; A8 keeps them in a local queue until the API exists.
    }

    private func load<T: Decodable>(_ name: String) throws -> T {
        guard let url = bundle.url(forResource: name, withExtension: "json")
            ?? bundle.url(forResource: name, withExtension: "json", subdirectory: "mock")
        else { throw MockError.missingFile(name) }
        return try JSONDecoder.contract.decode(T.self, from: Data(contentsOf: url))
    }
}

/// Profiles saved through the mock (onboarding, profile edits). Kept in UserDefaults so they survive relaunch.
final class SavedProfiles {
    private let defaults: UserDefaults
    private let key = "mock.savedProfiles"

    init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    subscript(userId: String) -> Profile? {
        get { all[userId] }
        set {
            var profiles = all
            profiles[userId] = newValue
            defaults.set(try? JSONEncoder.contract.encode(profiles), forKey: key)
        }
    }

    private var all: [String: Profile] {
        guard let data = defaults.data(forKey: key) else { return [:] }
        return (try? JSONDecoder.contract.decode([String: Profile].self, from: data)) ?? [:]
    }
}

/// The mock readers from `contract/mock`. Switchable in the Profile tab (debug builds) to compare rankings.
enum Persona: String, CaseIterable, Identifiable, Sendable {
    case sara, matti, newUser

    var id: String { rawValue }

    init?(userId: String) {
        guard let match = Self.allCases.first(where: { $0.userId == userId }) else { return nil }
        self = match
    }

    var userId: String {
        switch self {
        case .sara: "u-sara"
        case .matti: "u-matti"
        case .newUser: "u-new"
        }
    }

    var feedFile: String {
        switch self {
        case .sara: "feed-sara"
        case .matti: "feed-matti"
        case .newUser: "feed-new"
        }
    }

    var displayName: String {
        switch self {
        case .sara: "Sara · new student from Iran"
        case .matti: "Matti · Finnish local"
        case .newUser: "New user · no profile yet"
        }
    }
}
