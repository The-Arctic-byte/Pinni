import Foundation

/// Which language a story is shown in, and the rule that red-risk stories are never shown in an
/// unchecked (tier 3) translation: they fall back to the verified English version.
struct StoryLanguage: Equatable {
    enum Choice: Hashable {
        /// The reader's story language.
        case mine
        case english
        /// Finnish originals next to their translation.
        case finnishOriginal
    }

    let story: Story
    let readerLanguage: String

    /// The switcher's options: the reader's language (if not English), English, and Finnish if originals exist.
    var choices: [Choice] {
        var choices: [Choice] = readerLanguage == "en" ? [] : [.mine]
        choices.append(.english)
        if !(story.originals ?? []).isEmpty { choices.append(.finnishOriginal) }
        return choices
    }

    /// The language the text is shown in for a choice. The bilingual view explains in the reader's language.
    func shownLanguage(for choice: Choice) -> String {
        switch choice {
        case .english: return "en"
        case .mine, .finnishOriginal:
            return isWithheld(readerLanguage) ? "en" : story.title.shownLanguage(for: readerLanguage)
        }
    }

    /// True when the reader's language would be an unchecked translation of a red-risk story.
    var isTranslationWithheld: Bool { isWithheld(readerLanguage) }

    private func isWithheld(_ language: String) -> Bool {
        guard language != "en", story.risk == .red else { return false }
        return (story.tier(for: language) ?? 3) == 3
    }
}
