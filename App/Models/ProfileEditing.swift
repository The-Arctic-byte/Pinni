import Foundation

/// Editing the profile reuses the onboarding steps: a profile becomes onboarding answers,
/// and an edited step is applied back without touching anything else the profile holds.
extension OnboardingAnswers {
    /// Categories at or above this weight count as "most important" when a profile is edited.
    static let importantThreshold = 0.7

    init(profile: Profile) {
        self.init()
        language = profile.language
        targetGroups = Set(profile.targetGroups)
        importantCategories = Set(profile.categoryWeights.filter { $0.value >= Self.importantThreshold }.keys)
        homePlaceId = profile.homePlaceId
        homeCountryCode = profile.homeCountryCode
        residence = profile.residence?.status
        residenceConsent = profile.residence?.consent == true
        housing = profile.housing?.provider
        housingConsent = profile.housing?.consent == true
    }
}

extension Profile {
    /// Applies one edited step. Interests, wanted news, hard filters and notification settings stay as they are.
    mutating func apply(_ answers: OnboardingAnswers, step: OnboardingAnswers.Step, now: Date) {
        switch step {
        case .language:
            language = answers.language
        case .who:
            targetGroups = answers.targetGroups.sorted { $0.rawValue < $1.rawValue }
        case .categories:
            categoryWeights = Dictionary(uniqueKeysWithValues: answers.importantCategories.map { ($0, OnboardingAnswers.importantWeight) })
        case .place:
            if let old = homePlaceId, old != answers.homePlaceId { followedPlaceIds?.removeAll { $0 == old } }
            homePlaceId = answers.homePlaceId
            homeCountryCode = answers.homeCountryCode
            if let home = answers.homePlaceId, followedPlaceIds?.contains(home) != true {
                followedPlaceIds = (followedPlaceIds ?? []) + [home]
            }
            // Sensitive answers are only kept with consent.
            residence = answers.residenceConsent ? answers.residence.map { Residence(status: $0, consent: true) } : nil
            housing = answers.housingConsent ? answers.housing.map { Housing(provider: $0, consent: true) } : nil
        }
        updatedAt = now
    }
}

/// What the recommender has learned, in plain terms (contract: GET /v1/profile/learned).
struct LearnedPreferences: Codable, Hashable, Sendable {
    struct CategoryWeight: Codable, Hashable, Sendable {
        let category: Category
        let weight: Double
    }

    /// 0 = general ranking (new reader), 1 = fully personal.
    let personalization: Double
    let topCategories: [CategoryWeight]
    let topPlaces: [String]
    let topTags: [String]?

    static let none = LearnedPreferences(personalization: 0, topCategories: [], topPlaces: [], topTags: nil)
}
