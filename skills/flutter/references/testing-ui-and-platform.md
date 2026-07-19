# Testing, UI Quality, and Platforms

## Contents

- Test selection and synchronization
- Accessibility, localization, and responsive behavior
- Packages, plugins, and native hosts
- Startup, build, and performance evidence
- Review matrix
- Official references

## Test selection and synchronization

- Use unit tests for pure state transitions, parsing, validation, mapping, and application logic through fakes. Keep Flutter bindings and native plugins out of them.
- Use widget tests for rendering states, lifecycle updates, user input, navigation outcomes, semantics, text scaling, constraints, and key-based state retention.
- Use integration tests for complete flows, cold startup, real navigation, persistence or network wiring, and Dart/native boundaries on a device or emulator.
- Pump the exact frames or duration needed for deterministic transitions. Use `pumpAndSettle` only when all animations and scheduled frames must actually settle; it can hang on perpetual animations and hide timing assumptions.
- Prefer finders based on visible text, semantics, type, or stable domain keys. Do not add opaque test-only keys when the user-facing contract already identifies the element.
- Use fakes at application-owned plugin and repository interfaces. A unit or widget test does not load the native host implementation of a plugin.
- Use golden tests only for a stable visual contract. Pin viewport, pixel ratio, theme, locale, text scale, fonts, Flutter version, and rendering platform, then retain behavior and semantics tests alongside the golden.
- Keep integration coverage focused on critical flows because it is slower and more fragile than unit and widget coverage.

## Accessibility, localization, and responsive behavior

- Preserve accessible names, roles, values, enabled state, focus order, keyboard traversal, and touch targets. Do not communicate state by color alone.
- Prefer semantic native widgets before adding manual `Semantics`. Merge or exclude semantics only after inspecting the resulting accessibility tree.
- Test important screens with large text or display scaling, keyboard navigation where supported, and the repository's accessibility guideline matchers. Manually verify critical flows with TalkBack and VoiceOver when release risk warrants it.
- Keep complete grammatical messages in ARB or the repository's localization source. Use placeholders, plurals, and selects instead of concatenating translated fragments.
- Test at least one long-text locale and RTL layout when supported. Verify clipping, ordering, directional padding, icons, and text alignment.
- Base responsive layout on available constraints and capabilities. Test representative compact and wide widths, resized windows, split view, and large text rather than one device model.

```json
{
  "cartItems": "{count, plural, =0{Cart is empty} one{1 item} other{{count} items}}",
  "@cartItems": {"placeholders": {"count": {"type": "int"}}}
}
```

## Packages, plugins, and native hosts

- Before adding a package, check whether the Flutter or Dart SDK or an existing dependency already covers the need. Verify supported platforms, SDK constraints, maintenance, license, and API documentation.
- Follow the repository's dependency-range and lockfile policy. Applications normally commit a lockfile; reusable packages commonly test an allowed version range.
- Wrap plugin behavior behind an application-owned interface so domain, unit, and widget tests can use a fake and platform changes remain localized.
- Use a basic platform channel for a small stable surface. Use the project's generated channel approach, such as Pigeon, when messages become structured or numerous.
- Update every affected native host: manifests, entitlements, permissions, minimum versions, Gradle or CocoaPods settings, web registration, and desktop configuration.
- Perform a full stop and rebuild after adding or changing native plugin code. Hot reload or hot restart can leave registration stale and produce `MissingPluginException`.
- Test each changed Dart/native channel end to end on every supported platform it affects. Permission dialogs, platform views, notifications, and other host UI may require device or manual coverage beyond Flutter integration tests.
- Never hand-edit generated registrants, localizations, serializers, or channel bindings. Run the owning generator and verify tracked output policy.

## Startup, build, and performance evidence

- Run repository-native format checking, `flutter analyze`, focused tests, and the relevant broader suite. Treat analyzer warnings according to repository policy; do not silently ignore a newly introduced diagnostic.
- Cold-launch after changes to `main`, routes, DI, assets, fonts, localization, `pubspec`, flavors, plugins, native hosts, or initialization.
- Observe the first meaningful screen and critical initialization with no red or grey error UI, uncaught exception, missing asset, or plugin registration failure.
- Build every materially affected deployment target and flavor. For web, serve and open the built output and exercise a direct deep link when routing changed.
- Record the exact command, Flutter version when material, target/device, flavor, exit status, and observed success signal.
- Measure performance claims in profile mode on a representative slower physical device. Capture a trace that identifies build, layout, paint, shader, I/O, or CPU cause before optimizing.
- Recheck accessibility and responsive behavior after a performance refactor; cached or custom-rendered UI must preserve semantics and text/layout adaptation.

## Review matrix

```text
Dart model or state       -> unit tests for every closed state and failure
Widget behavior           -> widget test for rendering, input, update, semantics
Routing                    -> typed result/back/direct-entry tests
Responsive or localized UI-> compact/wide, large text, long locale, RTL
Plugin or native channel  -> fake boundary tests + device integration per platform
Startup/wiring/assets     -> cold full rebuild and first meaningful screen
Performance claim         -> profile-mode trace on representative hardware
```

## Official references

- [Testing Flutter apps](https://docs.flutter.dev/testing/overview)
- [Widget testing](https://docs.flutter.dev/cookbook/testing/widget/introduction)
- [Flutter integration tests](https://docs.flutter.dev/testing/integration-tests)
- [Plugins in Flutter tests](https://docs.flutter.dev/testing/plugins-in-tests)
- [Flutter accessibility](https://docs.flutter.dev/ui/accessibility)
- [Flutter accessibility testing](https://docs.flutter.dev/ui/accessibility/accessibility-testing)
- [Flutter internationalization](https://docs.flutter.dev/ui/internationalization)
- [Adaptive and responsive design](https://docs.flutter.dev/ui/adaptive-responsive/general)
- [Using packages](https://docs.flutter.dev/packages-and-plugins/using-packages)
- [Platform channels](https://docs.flutter.dev/platform-integration/platform-channels)
- [Flutter build modes](https://docs.flutter.dev/testing/build-modes)
