import SwiftUI

/// Four skippable steps: language → who you are → most important categories → place.
/// Each step after the first is pushed on a navigation stack, so iOS shows its own back button.
struct OnboardingView: View {
    typealias Step = OnboardingAnswers.Step

    let places: [Place]
    let onFinish: (OnboardingAnswers) -> Void

    @State private var answers = OnboardingAnswers(language: OnboardingView.defaultLanguage)
    @State private var path: [Step] = OnboardingView.initialPath

    var body: some View {
        NavigationStack(path: $path) {
            page(for: .language)
                .navigationDestination(for: Step.self) { step in
                    page(for: step)
                }
        }
        #if os(macOS)
        .frame(minWidth: 520, minHeight: 640)
        #endif
    }

    private func page(for step: Step) -> some View {
        content(for: step)
            .softScrollEdges()
            .bottomBar { controls(for: step) }
            .toolbar {
                ToolbarItem(placement: .principal) { StepProgress(step: step) }
            }
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
    }

    @ViewBuilder
    private func content(for step: Step) -> some View {
        switch step {
        case .language: LanguageStep(language: $answers.language)
        case .who: WhoStep(selection: $answers.targetGroups)
        case .categories: CategoriesStep(selection: $answers.importantCategories)
        case .place: PlaceStep(answers: $answers, places: places)
        }
    }

    private func controls(for step: Step) -> some View {
        HStack {
            #if os(macOS)
            // macOS sheets have no navigation bar back button.
            if !path.isEmpty {
                Button("Back") { path.removeLast() }
            }
            #endif
            Spacer()
            Button("Skip") {
                answers.skipped.insert(step)
                advance(from: step)
            }
            Button {
                answers.skipped.remove(step)
                advance(from: step)
            } label: {
                Text(step == Step.allCases.last ? "Show my Oulu" : "Continue")
                    .lineLimit(1)
                    .fixedSize()
                    .frame(minWidth: 120)
            }
            .buttonStyle(.borderedProminent)
            .keyboardShortcut(.defaultAction)
        }
        .controlSize(.large)
        .padding()
    }

    private func advance(from step: Step) {
        guard let index = Step.allCases.firstIndex(of: step), index + 1 < Step.allCases.count else {
            onFinish(answers)
            return
        }
        path.append(Step.allCases[index + 1])
    }

    /// The device language if stories exist in it, else English.
    private static var defaultLanguage: String {
        let code = Locale.current.language.languageCode?.identifier ?? "en"
        return LanguageStep.options.contains { $0.code == code } ? code : "en"
    }

    /// Debug builds accept `-onboardingStep <step>` as a launch argument to open a step directly (screenshots).
    private static var initialPath: [Step] {
        #if DEBUG
        guard let raw = UserDefaults.standard.string(forKey: "onboardingStep"),
              let step = Step(rawValue: raw),
              let index = Step.allCases.firstIndex(of: step)
        else { return [] }
        // The first step is the stack's root, so only later steps are pushed.
        return Array(Step.allCases[1..<(index + 1)])
        #else
        []
        #endif
    }
}

extension OnboardingAnswers {
    init(language: String) {
        self.init()
        self.language = language
    }
}

private struct StepProgress: View {
    typealias Step = OnboardingAnswers.Step
    let step: Step

    private var index: Int { Step.allCases.firstIndex(of: step) ?? 0 }

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Step.allCases.indices, id: \.self) { i in
                Capsule()
                    .fill(i <= index ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary))
                    .frame(width: 28, height: 5)
            }
        }
        .accessibilityElement()
        .accessibilityLabel(Text("Step \(index + 1) of \(Step.allCases.count)"))
    }
}

/// Shared title + explanation at the top of each step.
struct StepHeader: View {
    let title: LocalizedStringKey
    let subtitle: LocalizedStringKey

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.largeTitle.bold())
            Text(subtitle)
                .font(.body)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

extension View {
    /// Soft scroll edge effect on every edge where the OS supports it (iOS / macOS 26+).
    @ViewBuilder
    func softScrollEdges() -> some View {
        if #available(iOS 26.0, macOS 26.0, *) {
            scrollEdgeEffectStyle(.soft, for: .all)
        } else {
            self
        }
    }

    /// A bottom bar that takes part in the scroll edge effect on iOS / macOS 26+, with a bar background before that.
    @ViewBuilder
    func bottomBar(@ViewBuilder _ content: () -> some View) -> some View {
        if #available(iOS 26.0, macOS 26.0, *) {
            safeAreaBar(edge: .bottom, content: content)
        } else {
            safeAreaInset(edge: .bottom) { content().background(.bar) }
        }
    }
}

#Preview {
    OnboardingView(places: []) { _ in }
}

#Preview("Persian") {
    OnboardingView(places: []) { _ in }
        .environment(\.locale, Locale(identifier: "fa"))
        .environment(\.layoutDirection, .rightToLeft)
}
