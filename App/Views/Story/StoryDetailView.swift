import AVFoundation
import SwiftUI

/// The explained story: why you see it, what is known and not, what it means for you, context,
/// where to ask, updates, the Finnish original side by side, sources, and the reader's feedback.
/// Logs that it was opened and how long it was read.
struct StoryDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.locale) private var locale
    let story: Story
    @State private var choice: StoryLanguage.Choice = .mine
    @State private var openedAt: Date?

    private var language: StoryLanguage { StoryLanguage(story: story, readerLanguage: model.contentLanguage) }
    private var shown: String { language.shownLanguage(for: choice) }
    private var item: FeedItem? { model.feed?.items.first { $0.storyId == story.id } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                content
                    .environment(\.layoutDirection, shown.contentLayoutDirection)
                SourcesView(story: story, uiLanguage: uiLanguage)
                Divider()
                StoryFeedbackBar(story: story)
            }
            .frame(maxWidth: 700, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .onAppear {
            #if DEBUG
            // `-storyLanguage en|fi` as a launch argument picks the view (screenshots).
            switch UserDefaults.standard.string(forKey: "storyLanguage") {
            case "en": choice = .english
            case "fi": choice = .finnishOriginal
            default: break
            }
            #endif
            if !language.choices.contains(choice) { choice = language.choices.first ?? .english }
            openedAt = Date()
            model.opened(story, from: .story)
        }
        .onDisappear {
            if let openedAt { model.read(story, for: Date().timeIntervalSince(openedAt)) }
            openedAt = nil
        }
    }

    private var uiLanguage: String { locale.language.languageCode?.identifier ?? "en" }

    private var languagePicker: some View {
        Picker("Language", selection: $choice) {
            ForEach(language.choices, id: \.self) { choice in
                switch choice {
                case .mine:
                    Text(verbatim: Locale(identifier: model.contentLanguage).localizedString(forLanguageCode: model.contentLanguage) ?? model.contentLanguage)
                case .english:
                    Text(verbatim: "English")
                case .finnishOriginal:
                    Text("Finnish original ⇄")
                }
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
    }

    @ViewBuilder
    private var content: some View {
        Text(story.title.text(for: shown))
            .font(.title.bold())
            .fixedSize(horizontal: false, vertical: true)

        StoryHeader(story: story, uiLanguage: uiLanguage)

        if let reason = item?.reasons.first {
            Callout(symbol: "sparkles", tint: .accentColor, title: "Why you see this") {
                Text(reason.text(for: shown))
            }
        }

        TrustRow(story: story, language: shown)

        if language.choices.count > 1 {
            languagePicker
        }

        if choice == .mine, language.isTranslationWithheld {
            Callout(symbol: "checkmark.shield", tint: .orange) {
                Text("This story is about residence, health, money, work or safety, so you see the checked English version until a reviewer approves the translation.")
            }
        }

        if choice == .finnishOriginal {
            BilingualView(story: story, language: shown)
        } else {
            ExplanationView(story: story, language: shown)
        }
    }
}

// MARK: Header

private struct StoryHeader: View {
    @Environment(AppModel.self) private var model
    let story: Story
    let uiLanguage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Label(story.category.title, systemImage: story.category.symbolName)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                if let place = model.places[story.placeId] {
                    Text(verbatim: "· " + place.name.text(for: uiLanguage))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            if story.isOpinion {
                Label("Opinion, not news", systemImage: "quote.opening")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.fill.tertiary, in: .capsule)
            }
        }
    }
}

// MARK: Trust

private struct TrustRow: View {
    let story: Story
    let language: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let verification = story.verification {
                Label {
                    Text("Verified by \(verification.verifiedBy) · \(verification.verifiedAt.formatted(.dateTime.day().month()))")
                } icon: {
                    Image(systemName: "checkmark.seal.fill")
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.tint)
            }
            Text(origin)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if language != "en", let translation = story.translations.first(where: { $0.language == language }) {
                Text(tierText(translation))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var origin: LocalizedStringResource {
        story.origin == .community ? "Community report, checked by an editor" : "AI-assisted draft, checked by an editor"
    }

    private func tierText(_ translation: Story.Translation) -> LocalizedStringResource {
        switch translation.tier {
        case 1: "Translation checked by an editor"
        case 2: translation.reviewedBy.map { "Translation checked by \($0), community reviewer" } ?? "Translation checked by a community reviewer"
        default: "Machine translation, not checked"
        }
    }
}

// MARK: Explanation

private struct ExplanationView: View {
    let story: Story
    let language: String

    private var explanation: Story.Explanation { story.explanation }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let known = explanation.known, !known.isEmpty {
                Box(title: "What we know") {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(known.enumerated()), id: \.offset) { _, line in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(verbatim: "•").foregroundStyle(.tint)
                                Text(line.text(for: language))
                            }
                        }
                    }
                }
            }
            if let happened = explanation.happened {
                Box(title: "What happened") { Text(happened.text(for: language)) }
            }
            if let notKnown = explanation.notKnown {
                Box(title: "Not known yet", style: .dashed) {
                    Text(notKnown.text(for: language)).foregroundStyle(.secondary)
                }
            }
            Box(title: "What this means for you", style: .highlighted) {
                Text(explanation.forYou.text(for: language))
            }
            if let action = explanation.actionPlace {
                ActionPlaceView(action: action, language: language)
            }
            if let context = explanation.context {
                ContextCard(context: context, language: language)
            }
            if let timeline = explanation.timeline, !timeline.isEmpty {
                TimelineView(entries: timeline, language: language)
            }
        }
    }
}

private struct ActionPlaceView: View {
    let action: Story.Explanation.ActionPlace
    let language: String

    var body: some View {
        Box(title: "Where you can ask") {
            VStack(alignment: .leading, spacing: 8) {
                Text(action.name.text(for: language))
                HStack {
                    if let coordinate = action.coordinate, let url = mapsURL(coordinate) {
                        Link(destination: url) { Label("Show on map", systemImage: "map") }
                    }
                    if let url = action.url {
                        Link(destination: url) { Label("Website", systemImage: "safari") }
                    }
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private func mapsURL(_ coordinate: Coordinate) -> URL? {
        var components = URLComponents(string: "https://maps.apple.com/")
        components?.queryItems = [
            URLQueryItem(name: "ll", value: "\(coordinate.lat),\(coordinate.lon)"),
            URLQueryItem(name: "q", value: action.name.text(for: language)),
        ]
        return components?.url
    }
}

/// "To understand": a question a newcomer would ask, answered once and reused across stories.
private struct ContextCard: View {
    let context: Story.Explanation.Context
    let language: String
    @State private var isExpanded = false

    var body: some View {
        Box(title: "To understand") {
            DisclosureGroup(isExpanded: $isExpanded) {
                Text(context.answer.text(for: language))
                    .padding(.top, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } label: {
                Label(context.question.text(for: language), systemImage: "lightbulb")
                    .fontWeight(.semibold)
            }
        }
    }
}

private struct TimelineView: View {
    let entries: [Story.Explanation.TimelineEntry]
    let language: String

    var body: some View {
        Box(title: "Updates") {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(entries.sorted { $0.at > $1.at }.enumerated()), id: \.offset) { index, entry in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Circle()
                            .fill(index == 0 ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary))
                            .frame(width: 9, height: 9)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.at, format: .dateTime.weekday().day().month().hour().minute())
                                .font(.footnote.weight(.semibold))
                            Text(entry.text.text(for: language))
                        }
                    }
                }
            }
        }
    }
}

// MARK: Finnish original

private struct BilingualView: View {
    let story: Story
    let language: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Each sentence next to the Finnish original. Check it yourself.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            ForEach(Array((story.originals ?? []).enumerated()), id: \.offset) { _, original in
                VStack(alignment: .leading, spacing: 0) {
                    Text(verbatim: original.fi)
                        .font(.headline)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.fill.quaternary)
                    Text(verbatim: original.en)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .environment(\.layoutDirection, .leftToRight)
                .clipShape(.rect(cornerRadius: 12))
                .overlay { RoundedRectangle(cornerRadius: 12).strokeBorder(.separator) }
            }
            if let word = story.wordOfDay {
                WordOfDayView(word: word, language: language)
            }
        }
    }
}

private struct WordOfDayView: View {
    let word: Story.WordOfDay
    let language: String
    @State private var speaker = AVSpeechSynthesizer()

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Word of the day")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(verbatim: word.word)
                    .font(.title.bold())
                    .environment(\.layoutDirection, .leftToRight)
                Text(word.meaning.text(for: language))
                    .font(.subheadline)
            }
            Spacer()
            Button("Say it", systemImage: "speaker.wave.2.fill") {
                let utterance = AVSpeechUtterance(string: word.word)
                utterance.voice = AVSpeechSynthesisVoice(language: "fi-FI")
                utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.8
                speaker.speak(utterance)
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(14)
        .background(.fill.quaternary, in: .rect(cornerRadius: 14))
    }
}

// MARK: Sources

private struct SourcesView: View {
    let story: Story
    let uiLanguage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Sources")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(Array(story.sources.enumerated()), id: \.offset) { _, source in
                HStack(spacing: 6) {
                    if let url = source.url {
                        Link(source.name, destination: url)
                    } else {
                        Text(verbatim: source.name)
                    }
                    if let date = source.publishedAt {
                        Text(date, format: .dateTime.day().month())
                            .foregroundStyle(.secondary)
                    }
                }
                .font(.footnote)
            }
            if story.location?.isArea == true {
                Text("Location shown as an area only, never an address.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: Building blocks

private struct Box<Content: View>: View {
    enum Style { case plain, highlighted, dashed }

    let title: LocalizedStringKey
    var style: Style = .plain
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.caption.weight(.bold))
                .textCase(.uppercase)
                .foregroundStyle(style == .highlighted ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
            content
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .background {
            switch style {
            case .plain:
                RoundedRectangle(cornerRadius: 14).fill(.fill.quaternary)
            case .highlighted:
                RoundedRectangle(cornerRadius: 14).fill(Color.accentColor.opacity(0.12))
            case .dashed:
                RoundedRectangle(cornerRadius: 14).strokeBorder(.secondary, style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
            }
        }
        .accessibilityElement(children: .combine)
    }
}

private struct Callout<Content: View>: View {
    let symbol: String
    let tint: Color
    var title: LocalizedStringKey?
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol)
                .foregroundStyle(tint)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                if let title {
                    Text(title)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(tint)
                }
                content
                    .font(.subheadline)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(tint.opacity(0.1), in: .rect(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}
