# State, Async, and Lifecycle

## Contents

- State ownership
- Stateful lifecycle
- Futures and async gaps
- Streams and background work
- Review examples
- Official references

## State ownership

- Keep ephemeral visual state, such as one control's focus or animation, in the owning widget. Lift state only to the nearest common owner that must coordinate it.
- Keep persisted or app-wide business state behind the application's established state boundary. Pass immutable values down and typed events up.
- Derive view values from the source of truth instead of storing a second mutable copy. If local editing needs a draft, define when it is initialized, committed, reset, and reconciled with upstream updates.
- Model loading, data, empty, stale, refreshing, and failure explicitly where users observe them. Do not infer them from incompatible combinations of booleans and nullable fields.
- Keep state values equality-safe and immutable when a notifier or state library suppresses equal updates.
- Avoid adding a new state-management package or global service locator for state that one `State` object or the project's current mechanism already owns.

## Stateful lifecycle

- Call `super.initState()` first, then initialize resources that depend on `widget` but not on inherited dependencies.
- Read inherited dependencies in `didChangeDependencies`; the framework calls it after `initState` and again when a dependency changes.
- Subscribe to a notifier, stream, controller, or platform source in `initState`. If its identity can change through widget configuration, unsubscribe from the old source and subscribe to the new one in `didUpdateWidget`.
- Cancel subscriptions, timers, animations, focus nodes, text controllers, and other owned resources in `dispose`, then call the superclass according to the API contract.
- Avoid `setState` in `didUpdateWidget` merely to trigger a rebuild; Flutter invokes `build` afterward. Use it only when an asynchronous consequence later changes state.
- Keep `setState` callbacks synchronous and limited to state assignment. Perform awaited work before the callback, then verify ownership and set the result.
- Do not call `setState` after disposal. A mounted guard prevents the crash but does not decide whether an old result is still semantically current.

```dart
late Future<User> _user;

@override
void initState() {
  super.initState();
  _user = widget.repository.load(widget.userId);
}

@override
void didUpdateWidget(covariant UserPage oldWidget) {
  super.didUpdateWidget(oldWidget);
  if (oldWidget.userId != widget.userId ||
      oldWidget.repository != widget.repository) {
    _user = widget.repository.load(widget.userId);
  }
}
```

## Futures and async gaps

- Obtain a `Future` used by `FutureBuilder` before `build`, such as in `initState`, `didChangeDependencies`, or `didUpdateWidget`. Creating it in `build` restarts the operation on unrelated rebuilds.
- Render `waiting`, data, empty, and error snapshots intentionally. Do not assume snapshot timing is a durable event sequence.
- After an async gap, check `context.mounted` before using that context. When operating through a `State`, also verify the result still matches the current widget input or request generation.
- Treat futures as generally non-cancellable. When a newer request supersedes an older one, ignore stale completion through an ID, generation token, or owned cancellable abstraction already present in the project.
- Make errors observable. Await work where the caller owns failure; use `unawaited` only for intentional detachment with explicit error reporting.
- Move substantial pure CPU work to an isolate only after measuring main-isolate impact. Serialization and isolate startup have cost; ordinary async I/O does not need `compute`.

```dart
final requestedId = widget.userId;
final user = await repository.load(requestedId);
if (!mounted || requestedId != widget.userId) return;
setState(() => _user = user);
```

## Streams and background work

- Create or obtain a stream before `StreamBuilder` construction when recreating it would resubscribe or restart upstream work.
- Choose single-subscription streams for one ordered consumer and broadcast streams for independent listeners. Define replay separately; broadcast does not imply replay.
- Own every manual `StreamSubscription`, handle error and done when meaningful, and cancel it in the matching lifecycle transition.
- Remember that `await for` can terminate on an error. Catch around the loop only when the operation has a real recovery policy.
- Do not use a stream for a single eventual result or a future for an unbounded sequence.
- Keep platform callbacks and timers from updating disposed or superseded state. Remove handlers and cancel timers during disposal.
- Keep isolates, background services, and detached jobs behind explicit application lifecycle owners; a widget rebuild must not spawn them.

## Review examples

Reject work created during rendering:

```dart
// Wrong: every parent rebuild can issue another request.
FutureBuilder<User>(
  future: repository.load(widget.userId),
  builder: buildUser,
)
```

Use context only while it remains mounted:

```dart
final saved = await repository.save(draft);
if (!context.mounted) return;
Navigator.pop<SavedItem>(context, saved);
```

## Official references

- [Ephemeral and app state](https://docs.flutter.dev/data-and-backend/state-mgmt/ephemeral-vs-app)
- [`State` lifecycle](https://api.flutter.dev/flutter/widgets/State-class.html)
- [`initState`](https://api.flutter.dev/flutter/widgets/State/initState.html)
- [`didChangeDependencies`](https://api.flutter.dev/flutter/widgets/State/didChangeDependencies.html)
- [`BuildContext.mounted`](https://api.flutter.dev/flutter/widgets/BuildContext/mounted.html)
- [`FutureBuilder`](https://api.flutter.dev/flutter/widgets/FutureBuilder-class.html)
- [`StreamBuilder`](https://api.flutter.dev/flutter/widgets/StreamBuilder-class.html)
- [Dart streams](https://dart.dev/libraries/async/using-streams)

