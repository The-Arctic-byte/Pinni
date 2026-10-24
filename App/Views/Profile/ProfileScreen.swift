import SwiftUI

/// Placeholder until A10. In debug builds it switches between the mock readers to compare rankings.
struct ProfileScreen: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            Form {
                #if DEBUG
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
                } header: {
                    Text(verbatim: "Mock data")
                }
                #endif

                if let profile = model.profile {
                    Section("Your profile") {
                        LabeledContent("Story language", value: Locale.current.localizedString(forLanguageCode: profile.language) ?? profile.language)
                        if let home = profile.homePlaceId.flatMap({ model.places[$0] }) {
                            LabeledContent("Area", value: home.name.text(for: model.contentLanguage))
                        }
                        if let feed = model.feed {
                            LabeledContent("Personalization", value: feed.personalization, format: .percent)
                        }
                    }
                }
            }
            .navigationTitle(Text("Profile"))
        }
    }

    private var personaBinding: Binding<Persona> {
        Binding(
            get: { model.persona },
            set: { persona in Task { await model.switchPersona(to: persona) } }
        )
    }
}

#Preview {
    ProfileScreen()
        .environment(AppModel())
}
