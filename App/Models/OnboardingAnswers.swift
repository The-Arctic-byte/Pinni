import Foundation

/// Everything the onboarding asks. Every step can be skipped; the result is the first profile and the first events.
struct OnboardingAnswers: Equatable, Sendable {
    enum Step: String, CaseIterable, Sendable {
        case language, who, categories, place
    }

    /// Weight for a category the reader marked as most important. Everything else stays neutral (left out).
    static let importantWeight = 0.9

    var language: String = "en"
    var targetGroups: Set<TargetGroup> = []
    var importantCategories: Set<Category> = []
    var homePlaceId: String?
    var homeCountryCode: String?
    var residence: Profile.Residence.Status?
    var residenceConsent = false
    var housing: Profile.Housing.Provider?
    var housingConsent = false
    var skipped: Set<Step> = []

    func profile(userId: String, now: Date) -> Profile {
        Profile(
            userId: userId,
            language: language,
            targetGroups: answered(.who) ? targetGroups.sorted { $0.rawValue < $1.rawValue } : [],
            homePlaceId: answered(.place) ? homePlaceId : nil,
            homeCountryCode: answered(.place) ? homeCountryCode : nil,
            residence: consentedResidence,
            housing: consentedHousing,
            categoryWeights: answered(.categories) ? categoryWeights : [:],
            followedPlaceIds: answered(.place) ? homePlaceId.map { [$0] } : nil,
            updatedAt: now
        )
    }

    /// One `onboardingAnswer` event per step, skipped steps included, so the recommender knows what was not said.
    func events(userId: String, now: Date, makeId: () -> String) -> [Event] {
        Step.allCases.map { step in
            var detail: [String: JSONValue] = ["question": .string(step.rawValue)]
            if let answer = answered(step) ? answer(for: step) : nil {
                detail["answer"] = answer
            } else {
                detail["skipped"] = .bool(true)
            }
            return Event(
                id: makeId(),
                userId: userId,
                type: .onboardingAnswer,
                detail: detail,
                context: .init(screen: .onboarding),
                occurredAt: now
            )
        }
    }

    private func answered(_ step: Step) -> Bool {
        !skipped.contains(step)
    }

    private var categoryWeights: [Category: Double] {
        Dictionary(uniqueKeysWithValues: importantCategories.map { ($0, Self.importantWeight) })
    }

    private var consentedResidence: Profile.Residence? {
        guard answered(.place), residenceConsent, let residence else { return nil }
        return .init(status: residence, consent: true)
    }

    private var consentedHousing: Profile.Housing? {
        guard answered(.place), housingConsent, let housing else { return nil }
        return .init(provider: housing, consent: true)
    }

    private func answer(for step: Step) -> JSONValue? {
        let strings: ([String]) -> JSONValue = { .array($0.map(JSONValue.string)) }
        switch step {
        case .language:
            return .string(language)
        case .who:
            return strings(targetGroups.map(\.rawValue).sorted())
        case .categories:
            return strings(importantCategories.map(\.rawValue).sorted())
        case .place:
            var place: [String: JSONValue] = [:]
            if let homePlaceId { place["homePlaceId"] = .string(homePlaceId) }
            if let homeCountryCode { place["homeCountryCode"] = .string(homeCountryCode) }
            // Sensitive answers only travel with consent.
            if let r = consentedResidence { place["residence"] = .string(r.status.rawValue) }
            if let h = consentedHousing { place["housing"] = .string(h.provider.rawValue) }
            return place.isEmpty ? nil : .object(place)
        }
    }
}
