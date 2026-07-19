---
name: flutter
description: Implement, refactor, debug, test, optimize, or review Flutter applications, packages, and plugins with idiomatic Dart. Use when an affected `pubspec.yaml` declares the Flutter SDK or affected code belongs to a Flutter app, package, plugin, widget tree, platform host, or Flutter test. Cover Dart type design, widget identity and lifecycle, state and async ownership, navigation, layout, accessibility, localization, performance, platform integration, testing, and cold-start proof.
---

# Flutter

Build from immutable descriptions of current state. Keep widget construction pure, give state and asynchronous work explicit owners, and treat every supported platform as a real runtime rather than a successful Dart compilation target.

## Establish the application contract

1. Read repository guidance, `pubspec.yaml`, the Dart and Flutter SDK constraints, `analysis_options.yaml`, lockfile policy, build flavors, platform folders, generated-code configuration, and nearby tests.
2. Identify supported platforms, application entry points, state-management and dependency-injection conventions, router or Navigator approach, localization pipeline, theming, plugin boundaries, and startup sequence.
3. Preserve the repository's established state, routing, DI, serialization, and code-generation approaches. Do not introduce a second package or architectural pattern for a concern the project already solves.
4. Check the minimum Dart and Flutter versions before using language patterns, class modifiers, APIs, or test features from a newer SDK.

## Model state and widgets

- Keep typed values inside the application. Use `dynamic` only at a truly untyped boundary and decode or cast once into a validated type.
- Represent closed loading, data, empty, and failure states with a sealed hierarchy and exhaustive switch when the project's Dart version supports it. Avoid combinations of nullable values and booleans that express impossible states.
- Prefer `final` fields, immutable state values, and `const` constructors. Treat `late` and `!` as runtime assertions whose lifecycle proof must be local and testable.
- Keep `build` free of I/O, subscriptions, mutation, navigation, analytics, timers, future creation, and expensive parsing. Derive widgets from current inputs only.
- Keep ephemeral state at the narrowest durable widget owner and shared application state at the nearest common owner. Pass values down and events up; do not mirror one source into several mutable fields.
- Use stable local keys for semantic identity during reorder or replacement. Do not add keys indiscriminately, recreate a `GlobalKey` in `build`, or use global lookup when a callback or controller suffices.

## Preserve lifecycle and async ownership

- Acquire subscriptions, controllers, focus nodes, animations, futures, and streams outside `build`; update them when widget dependencies change and release them in `dispose`.
- Use `didChangeDependencies` for work that depends on inherited widgets. Use `didUpdateWidget` to replace resources when constructor inputs change; avoid redundant `setState` there because a rebuild follows.
- Keep `setState` synchronous and limit it to the smallest subtree whose rendered state changed.
- After every `await`, verify that the `BuildContext` or `State` is still mounted and that the result still belongs to the current request, route, or widget input before applying it.
- Return `Future<void>` for awaitable async commands. Mark deliberately detached work with `unawaited` and give its errors and lifetime an explicit owner.
- Define stream subscription, cancellation, error, completion, broadcast, and buffering behavior. Do not treat a stream as an event log unless its replay contract says so.

## Preserve user-facing quality

- Design from parent constraints: constraints go down, sizes go up, and parents position children. Adapt to available width and capabilities rather than guessed phone, tablet, orientation, or platform labels.
- Use lazy builders for large lists and grids. Use `const` widgets and narrow rebuild boundaries before adding caching or custom rendering.
- Preserve semantics, focus order, keyboard access, touch targets, text scaling, contrast, RTL layout, and localization. Keep complete grammatical messages in localization resources instead of concatenating translated fragments.
- Profile performance in profile mode on a representative device. Do not justify `RepaintBoundary`, intrinsic measurement, clipping, opacity, isolates, or custom render objects without evidence.
- Keep plugins behind application-owned boundaries. Verify supported platforms and native setup; do not assume unit or widget tests load host plugin code.
- Never hand-edit generated files. Run the repository's generator and follow its policy on checked-in output.

## Verify and review

1. Format in check mode, run `flutter analyze`, and run the smallest focused unit or widget test before the broader suite.
2. Cover every changed loading, data, empty, failure, lifecycle, navigation, and user-interaction state at the cheapest layer that exercises the real contract.
3. Use integration tests for full application flows and Dart/native boundaries. Use golden tests only for a stable visual contract and never instead of behavior or semantics assertions.
4. When startup, routes, DI, assets, fonts, localization, plugins, native configuration, `pubspec`, or entry points change, perform a cold full rebuild and launch on every materially affected platform or representative required target.
5. Record the exact command, flavor, device or target, exit status, first meaningful screen or health signal, and absence of uncaught framework or plugin errors. Compilation alone is not runtime proof.

## Load detailed guidance

- Read [dart-and-widgets.md](references/dart-and-widgets.md) for any non-trivial Dart model, public API, widget, layout, identity, navigation, or rendering change.
- Read [state-async-and-lifecycle.md](references/state-async-and-lifecycle.md) whenever state, controllers, subscriptions, futures, streams, contexts, or asynchronous UI behavior changes.
- Read [testing-ui-and-platform.md](references/testing-ui-and-platform.md) whenever changing user-visible UI, accessibility, localization, packages, plugins, native hosts, startup, builds, or tests.

