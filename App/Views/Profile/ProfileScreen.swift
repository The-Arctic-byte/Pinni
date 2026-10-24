import SwiftUI

/// The reader's preferences (editable with the onboarding steps), what they hid, what Pinni has learned
/// and their reports. In debug builds it also switches between the mock readers.
struct ProfileScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.locale) private var locale
    @State private var confirmsReset = false
    #if DEBUG
    /// `-profileReports YES` as a launch argument opens My reports directly (screenshots).
    @State private var opensReports = UserDefaults.standard.bool(forKey: "profileReports")
    @State private var apiBaseURL = UserDefaults.standard.string(forKey: DataSource.defaultsKey) ?? ""
    #endif

    private var uiLanguage: String { locale.language.languageCode?.identifier ?? "en" }

    var body: some View {
        NavigationStack {
            Form {
                #if DEBUG
                mockSection
                #endif

                if let profile = model.profile {
                    preferences(profile)
                    hidden(profile)
                }
                learnedSection

                Section {
                    NavigationLink {
                        MyReportsScreen()
                    } label: {
                        LabeledContent {
                            Text(model.reports.count, format: .number)
                        } label: {
                            Label("My reports", systemImage: "exclamationmark.bubble")
                        }
                    }
                } footer: {
                    Text("What you reported and where each report is in the editor’s review.")
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Profile"))
            .navigationDestination(for: OnboardingAnswers.Step.self) { step in
                ProfileStepEditor(step: step)
            }
            // Report ids pushed from My reports.
            .navigationDestination(for: String.self) { id in
                ReportDetailView(reportId: id)
            }
            #if DEBUG
            .navigationDestination(isPresented: $opensReports) { MyReportsScreen() }
            #endif
            .confirmationDialog("Reset what Pinni learned?", isPresented: $confirmsReset, titleVisibility: .visible) {
                Button("Reset", role: .destructive) { Task { await model.resetLearned() } }
            } message: {
                Text("Your reactions and hidden stories are forgotten and your news starts general again. Your preferences above stay.")
            }
        }
    }

    // MARK: Sections

    private func preferences(_ profile: Profile) -> some View {
        Section {
            NavigationLink(value: OnboardingAnswers.Step.language) {
                LabeledContent("Story language") {
                    Text(verbatim: Locale(identifier: profile.language).localizedString(forLanguageCode: profile.language) ?? profile.language)
                }
            }
            NavigationLink(value: OnboardingAnswers.Step.who) {
                LabeledContent("Who you are") {
                    summary(profile.targetGroups.map { Text($0.title) })
                }
            }
            NavigationLink(value: OnboardingAnswers.Step.categories) {
                LabeledContent("Most important") {
                    summary(OnboardingAnswers(profile: profile).importantCategories.sorted { $0.rawValue < $1.rawValue }.map { Text($0.title) })
                }
            }
            NavigationLink(value: OnboardingAnswers.Step.place) {
                LabeledContent("Area") {
                    if let home = profile.homePlaceId.flatMap({ model.places[$0] }) {
                        Text(verbatim: home.name.text(for: uiLanguage))
                    } else {
                        Text("Not set")
                    }
                }
            }
        } header: {
            Text("Your preferences")
        } footer: {
            Text("Changes apply right away. Residence and housing are only kept with your consent.")
        }
    }

    @ViewBuilder
    private func hidden(_ profile: Profile) -> some View {
        if !profile.hardFilters.categories.isEmpty || model.hiddenStoryCount > 0 {
            Section {
                ForEach(profile.hardFilters.categories, id: \.self) { category in
                    HStack {
                        Label(category.title, systemImage: category.symbolName)
                        Spacer()
                        Button("Show again") { Task { await model.unblock(category) } }
                            .buttonStyle(.borderless)
                    }
                }
                if model.hiddenStoryCount > 0 {
                    HStack {
                        Text("\(model.hiddenStoryCount) hidden stories")
                        Spacer()
                        Button("Show again") { model.unhideAllStories() }
                            .buttonStyle(.borderless)
                    }
                }
            } header: {
                Text("Hidden with “Not for me”")
            } footer: {
                Text("Important safety news reaches you even from hidden topics.")
            }
        }
    }

    private var learnedSection: some View {
        Section {
            LabeledContent("How personal your news is") {
                Text(model.learned.personalization, format: .percent)
            }
            ProgressView(value: model.learned.personalization)
                .accessibilityHidden(true)
            if !model.learned.topCategories.isEmpty {
                LabeledContent("Topics you read most") {
                    summary(model.learned.topCategories.map { Text($0.category.title) })
                }
            }
            if !model.learned.topPlaces.isEmpty {
                LabeledContent("Places you follow") {
                    Text(verbatim: model.learned.topPlaces.compactMap { model.places[$0]?.name.text(for: uiLanguage) }.formatted(.list(type: .and)))
                }
            }
            Button("Reset what Pinni learned", role: .destructive) { confirmsReset = true }
        } header: {
            Text("What Pinni has learned")
        } footer: {
            Text("New readers see general news first. It gets more personal the more you read, like, hide and share.")
        }
    }

    // MARK: Helpers

    private func summary(_ parts: [Text]) -> Text {
        guard let first = parts.first else { return Text("None") }
        return parts.dropFirst().reduce(first) { Text("\($0), \($1)") }
    }

    #if DEBUG
    private var mockSection: some View {
        Section {
            Picker("Reader", selection: personaBinding) {
                ForEach(Persona.allCases) { persona in
                    Text(verbatim: persona.displayName).tag(persona)
                }
            }
            Button {
                model.restartOnboarding()
            } label: {
                Text(verbatim: "Restart onboarding")
            }
            TextField(text: $apiBaseURL, prompt: Text(verbatim: "http://localhost:8000")) {
                Text(verbatim: "API URL")
            }
            .autocorrectionDisabled()
            #if os(iOS)
            .textInputAutocapitalization(.never)
            .keyboardType(.URL)
            #endif
            .onSubmit { Task { await model.applyAPIBaseURL(apiBaseURL) } }
        } header: {
            Text(verbatim: "Mock data")
        } footer: {
            Text(verbatim: DataSource.current == .mock
                 ? "Using the sample news. Enter an API URL to use a backend."
                 : "Using the API at \(apiBaseURL). Clear the URL to use the sample news.")
        }
    }

    private var personaBinding: Binding<Persona> {
        Binding(
            get: { model.persona },
            set: { persona in Task { await model.switchPersona(to: persona) } }
        )
    }
    #endif
}

/// One onboarding step as an edit page. Every change is saved to the profile right away.
private struct ProfileStepEditor: View {
    @Environment(AppModel.self) private var model
    let step: OnboardingAnswers.Step
    @State private var answers = OnboardingAnswers()
    @State private var isReady = false

    var body: some View {
        content
            .softScrollEdges()
            .onAppear {
                if let profile = model.profile { answers = OnboardingAnswers(profile: profile) }
                isReady = true
            }
            .onChange(of: answers) {
                guard isReady else { return }
                let edited = answers
                Task { await model.updateProfile(edited, step: step) }
            }
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .language: LanguageStep(language: $answers.language)
        case .who: WhoStep(selection: $answers.targetGroups)
        case .categories: CategoriesStep(selection: $answers.importantCategories)
        case .place: PlaceStep(answers: $answers, places: Array(model.places.values))
        }
    }
}

#Preview {
    ProfileScreen()
        .environment(AppModel(persona: .sara))
}
