# Dart and Widgets

## Contents

- Dart type and API design
- Widget purity and identity
- Layout and rebuild behavior
- Navigation
- Review examples
- Official references

## Dart type and API design

- Use `Object?` when a value can be any Dart object but must remain type-checked. Use `dynamic` only when deliberately opting out of static checking at an untyped JSON, JavaScript, or platform boundary.
- Parse untyped maps and messages once into validated domain values. Do not pass `Map<String, dynamic>` through the application when a typed record or class is known.
- Prefer `final` fields and `const` constructors for stable values. If equality is overridden, override `hashCode` consistently and never mutate equality fields while the object is a set member or map key.
- Use a sealed hierarchy and exhaustive switch for closed state when supported by the minimum Dart SDK. Avoid a wildcard branch that prevents the compiler from identifying newly unhandled states.
- Use `late final` only when an external lifecycle guarantees one later assignment. Prefer constructor initialization, a nullable type with explicit states, or a stable future created during lifecycle setup.
- Return `Future<void>` for asynchronous work that produces no value but must be awaited. Do not return nullable futures, streams, or collections when absence can be represented by a nullable element or an empty container.
- Await futures by default. Use `unawaited(future)` only when detachment is intentional and the future's failure and lifetime have another owner.
- Use cascades to configure an object instead of returning `this` solely to invent a fluent API.
- Use class modifiers such as `final`, `base`, or `sealed` to express intended subclassing only when the repository's SDK constraint supports them.
- Keep public package APIs explicit and compatible. Changing a parameter from optional to required, narrowing a type, or changing sync to async is a contract change even when all app call sites are local today.

```dart
sealed class LoadState<T> {
  const LoadState();
}

final class Loading<T> extends LoadState<T> {
  const Loading();
}

final class Loaded<T> extends LoadState<T> {
  const Loaded(this.value);
  final T value;
}

final class Failed<T> extends LoadState<T> {
  const Failed(this.error);
  final Object error;
}
```

## Widget purity and identity

- Treat a widget as immutable configuration and a `State` object as owned mutable lifecycle state. Never mutate widget fields.
- Keep `build` referentially boring because the framework may call it every frame. Return a widget tree without starting work or causing external effects.
- Create a small widget rather than a helper method when the subtree needs its own identity, `const` reuse, rebuild boundary, semantics, lifecycle, or focused test. Do not extract every three-line fragment mechanically.
- Use `const` where inputs are compile-time constants. It can let Flutter reuse the same widget instance and stop rebuilding a stable subtree.
- Use a stable `ValueKey(domainId)` for data-backed siblings whose order can change. Use `ObjectKey` only when object identity is the intended identity and `UniqueKey` only to force replacement.
- Avoid a key on a lone stable child that has no identity ambiguity. A key fixes element matching, not arbitrary state bugs.
- Own a `GlobalKey` for the lifetime of the state that needs it; never construct it in `build`. Prefer callbacks, controllers, inherited state, or local context when global state lookup and subtree reparenting are unnecessary.
- Remember that `BuildContext` is one element location. Use a context below the provider, navigator, scaffold, theme, or inherited widget being queried; introduce `Builder` only when a new descendant context is actually required.

## Layout and rebuild behavior

- Start layout debugging from the rule: constraints go down, sizes go up, and parents set positions.
- Use `LayoutBuilder` for the constraints at a local subtree. Use the narrowest `MediaQuery` accessor needed for window properties so unrelated changes do not rebuild consumers.
- Adapt to available space, input capabilities, and platform conventions. Do not classify layout only by OS, orientation, or a guessed phone/tablet breakpoint.
- Use `Expanded` only inside a bounded flex axis and understand that it forces the allocated extent; use `Flexible` when the child may be smaller.
- Avoid nesting a same-axis scrollable under unbounded constraints. Choose one scroll owner or give the inner viewport a real bound.
- Use builder constructors for long lists and grids so only visible children are created.
- Call `setState` at the narrowest owner. Split stable subtrees and pass them as stable children before adding selectors, caches, or repaint boundaries.
- Avoid intrinsic measurement, `saveLayer`, broad `Opacity`, clipping, and custom painting in hot paths unless design requires them and profile evidence justifies the cost.
- Measure rendering in profile mode on a representative slower device. Debug-mode frame timing is not performance evidence.

## Navigation

- Preserve the repository's routing model. Do not add another router for one screen.
- Use typed push and pop results for a small imperative stack. Use the established declarative router when deep links, browser history, restoration, or coordinated nested navigators are product requirements.
- Let a self-contained flow own its inner navigator and let the app navigator own entry and exit. Keep back behavior and deep-link reconstruction explicit.
- Do not retain route-local `BuildContext` or navigator state beyond its mounted lifetime.
- Test direct entry, back behavior, returned values, invalid links, and restoration when the changed route promises them.

## Review examples

Give reordered content semantic identity:

```dart
ListView.builder(
  itemCount: items.length,
  itemBuilder: (context, index) {
    final item = items[index];
    return ItemTile(key: ValueKey(item.id), item: item);
  },
)
```

Adapt from local constraints rather than a device label:

```dart
LayoutBuilder(
  builder: (context, constraints) => constraints.maxWidth >= 700
      ? WideOrderView(order: order)
      : CompactOrderView(order: order),
)
```

## Official references

- [Effective Dart: design](https://dart.dev/effective-dart/design)
- [Dart class modifiers](https://dart.dev/language/class-modifiers)
- [Flutter architectural overview](https://docs.flutter.dev/resources/architectural-overview)
- [Building Flutter user interfaces](https://docs.flutter.dev/ui)
- [Flutter keys](https://api.flutter.dev/flutter/widgets/Widget/key.html)
- [`GlobalKey`](https://api.flutter.dev/flutter/widgets/GlobalKey-class.html)
- [Understanding constraints](https://docs.flutter.dev/ui/layout/constraints)
- [Flutter performance best practices](https://docs.flutter.dev/perf/best-practices)
- [Flutter navigation](https://docs.flutter.dev/ui/navigation)

