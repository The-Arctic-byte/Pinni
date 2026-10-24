import Foundation

/// What the reader told us. Learned preferences live in the recommender (contract: profile.schema.json).
struct Profile: Codable, Hashable, Sendable {
    struct Residence: Codable, Hashable, Sendable {
        enum Status: String, Codable, Sendable {
            case finnish, eu, nonEu
        }

        let status: Status
        let consent: Bool
    }

    struct Housing: Codable, Hashable, Sendable {
        enum Provider: String, Codable, Sendable {
            case psoas, other, none
        }

        let provider: Provider
        let consent: Bool
    }

    struct HardFilters: Codable, Hashable, Sendable {
        var categories: [Category]
        var tags: [String]
        var sources: [String]

        static let empty = HardFilters(categories: [], tags: [], sources: [])
    }

    struct Notifications: Codable, Hashable, Sendable {
        var mustSee: Bool?
        var forYou: Bool?
        var myReports: Bool?
        var channels: Bool?
    }

    let userId: String
    var language: String
    var uiLanguage: String?
    var targetGroups: [TargetGroup]
    var homePlaceId: String?
    var homeCountryCode: String?
    var residence: Residence?
    var housing: Housing?
    var categoryWeights: [Category: Double]
    var interests: [String]
    var wantedNews: [String]
    var followedPlaceIds: [String]?
    var hardFilters: HardFilters
    var notifications: Notifications?
    var updatedAt: Date

    init(
        userId: String,
        language: String,
        uiLanguage: String? = nil,
        targetGroups: [TargetGroup] = [],
        homePlaceId: String? = nil,
        homeCountryCode: String? = nil,
        residence: Residence? = nil,
        housing: Housing? = nil,
        categoryWeights: [Category: Double] = [:],
        interests: [String] = [],
        wantedNews: [String] = [],
        followedPlaceIds: [String]? = nil,
        hardFilters: HardFilters = .empty,
        notifications: Notifications? = nil,
        updatedAt: Date
    ) {
        self.userId = userId
        self.language = language
        self.uiLanguage = uiLanguage
        self.targetGroups = targetGroups
        self.homePlaceId = homePlaceId
        self.homeCountryCode = homeCountryCode
        self.residence = residence
        self.housing = housing
        self.categoryWeights = categoryWeights
        self.interests = interests
        self.wantedNews = wantedNews
        self.followedPlaceIds = followedPlaceIds
        self.hardFilters = hardFilters
        self.notifications = notifications
        self.updatedAt = updatedAt
    }

    private enum CodingKeys: String, CodingKey {
        case userId, language, uiLanguage, targetGroups, homePlaceId, homeCountryCode, residence, housing
        case categoryWeights, interests, wantedNews, followedPlaceIds, hardFilters, notifications, updatedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        userId = try c.decode(String.self, forKey: .userId)
        language = try c.decode(String.self, forKey: .language)
        uiLanguage = try c.decodeIfPresent(String.self, forKey: .uiLanguage)
        targetGroups = try c.decode([TargetGroup].self, forKey: .targetGroups)
        homePlaceId = try c.decodeIfPresent(String.self, forKey: .homePlaceId)
        homeCountryCode = try c.decodeIfPresent(String.self, forKey: .homeCountryCode)
        residence = try c.decodeIfPresent(Residence.self, forKey: .residence)
        housing = try c.decodeIfPresent(Housing.self, forKey: .housing)
        // JSON object keyed by category name; Swift only decodes enum-keyed dictionaries from string keys this way.
        let rawWeights = try c.decode([String: Double].self, forKey: .categoryWeights)
        categoryWeights = Dictionary(uniqueKeysWithValues: try rawWeights.map { key, value in
            guard let category = Category(rawValue: key) else {
                throw DecodingError.dataCorruptedError(forKey: .categoryWeights, in: c, debugDescription: "Unknown category '\(key)'")
            }
            return (category, value)
        })
        interests = try c.decode([String].self, forKey: .interests)
        wantedNews = try c.decode([String].self, forKey: .wantedNews)
        followedPlaceIds = try c.decodeIfPresent([String].self, forKey: .followedPlaceIds)
        hardFilters = try c.decode(HardFilters.self, forKey: .hardFilters)
        notifications = try c.decodeIfPresent(Notifications.self, forKey: .notifications)
        updatedAt = try c.decode(Date.self, forKey: .updatedAt)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(userId, forKey: .userId)
        try c.encode(language, forKey: .language)
        try c.encodeIfPresent(uiLanguage, forKey: .uiLanguage)
        try c.encode(targetGroups, forKey: .targetGroups)
        try c.encodeIfPresent(homePlaceId, forKey: .homePlaceId)
        try c.encodeIfPresent(homeCountryCode, forKey: .homeCountryCode)
        try c.encodeIfPresent(residence, forKey: .residence)
        try c.encodeIfPresent(housing, forKey: .housing)
        try c.encode(Dictionary(uniqueKeysWithValues: categoryWeights.map { ($0.key.rawValue, $0.value) }), forKey: .categoryWeights)
        try c.encode(interests, forKey: .interests)
        try c.encode(wantedNews, forKey: .wantedNews)
        try c.encodeIfPresent(followedPlaceIds, forKey: .followedPlaceIds)
        try c.encode(hardFilters, forKey: .hardFilters)
        try c.encodeIfPresent(notifications, forKey: .notifications)
        try c.encode(updatedAt, forKey: .updatedAt)
    }
}
