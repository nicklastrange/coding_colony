# Coroutines and Flow

## Contents

- Ownership and structured concurrency
- Dispatchers and blocking work
- Cancellation and failure
- Flow semantics and backpressure
- Shared state
- Deterministic tests
- Review examples
- Official references

## Ownership and structured concurrency

- Make every coroutine belong to a scope with a lifecycle. Accept or derive that scope from an application, request, component, or test owner; never use `GlobalScope` for application work.
- Use `coroutineScope` when sibling operations form one unit: one failure cancels the others and the parent waits for all children.
- Use `supervisorScope` only when child failures are intentionally independent. Handle each child failure; supervision does not make errors disappear.
- Do not pass a new `Job`, `SupervisorJob`, or `NonCancellable` context to `launch` or `async`; replacing the inherited job detaches the child from structured parent cancellation.
- Use `launch` for a side effect whose failure is owned by its scope. Use `async` only for a value that will be awaited. Replace `async { work() }.await()` with `work()` when no concurrency exists.
- Keep unbounded fan-out out of collection operators. Limit concurrency with the repository's established semaphore, worker, or batched pattern when input size is not inherently bounded.
- Do not create a new scope inside a suspend function to outlive its caller. If work must outlive the request, hand it to an explicit longer-lived owner or durable job mechanism.

```kotlin
suspend fun loadDashboard(): Dashboard = coroutineScope {
    val profile = async { profiles.load() }
    val orders = async { orders.loadRecent() }
    Dashboard(profile.await(), orders.await())
}
```

## Dispatchers and blocking work

- Remember that `suspend` does not mean background execution. A suspending function can run CPU work or block the current thread unless its implementation changes context.
- Use `withContext(Dispatchers.IO)` around blocking I/O when the called API does not already manage an appropriate dispatcher. Do not wrap non-blocking suspend APIs in `Dispatchers.IO`.
- Use `Dispatchers.Default` for substantial CPU-bound work only when moving it off the caller is part of the function's contract.
- Avoid hard-coded dispatcher changes in pure orchestration code. Follow the repository's injection or test-dispatcher convention when deterministic scheduling is required.
- Do not hold a thread lock or database thread-bound assumption across arbitrary suspension. Confirm that transaction, security, logging, and tracing context supports the coroutine model in use.

## Cancellation and failure

- Preserve cooperative cancellation. Let suspending calls check cancellation and add `ensureActive()` or `yield()` inside long CPU loops.
- Never swallow `CancellationException`. Catch the narrow recoverable exception, or rethrow cancellation before handling a broader failure.
- Avoid broad `runCatching` around suspending work because it catches every `Throwable`, including cancellation. Use a targeted `try`/`catch` or explicitly rethrow cancellation.
- Use `finally` for non-suspending cleanup. Enter `NonCancellable` only for the smallest cleanup that truly must suspend after cancellation.
- Know the failure owner. Child failures propagate to a regular parent; `async` exposes its failure through `await`; `CoroutineExceptionHandler` handles only uncaught root-style failures and is not a general `try`/`catch` replacement.
- Add timeouts only when the product contract has a deadline. Distinguish timeout from domain failure and clean up resources on cancellation.

```kotlin
suspend fun fetch(): Payload = try {
    client.fetch()
} catch (failure: IOException) {
    throw UpstreamUnavailable(failure)
}
```

## Flow semantics and backpressure

- Treat a regular `Flow` as cold unless its concrete type or conversion says otherwise: upstream code runs separately for each collector.
- Keep flow production context-safe. Use `flowOn` to move the upstream portion only; do not assume it changes the collector's context.
- Remember that `catch` handles upstream failures, not exceptions thrown later by the collector. Place it intentionally in the operator chain.
- Choose `StateFlow` for a current state with an initial value and equality-based conflation. Choose `SharedFlow` for broadcast values whose replay and overflow policy are explicit. Choose a channel for point-to-point delivery, not as a default event bus.
- Treat `buffer`, `conflate`, and `collectLatest` as semantic choices: buffering permits producer/consumer overlap, conflation drops intermediate values, and `collectLatest` cancels prior collector work.
- Avoid turning a cold flow hot without an explicit owner, start policy, replay size, and lifecycle. A careless `stateIn` or `shareIn` can keep upstream work alive or retain large values.
- Keep one source of truth. Do not mirror a flow into mutable state unless the state conversion has a clear lifecycle and consumers need it.
- Make completion and error behavior observable. A shared hot stream does not encode terminal completion for late subscribers the same way a cold flow does.

## Shared state

- Prefer confinement or immutable messages over shared mutation.
- Use atomics for one simple atomic value and `Mutex` for a multi-step suspending critical section. Remember that `Mutex` is not reentrant.
- Update a `MutableStateFlow` with `update { ... }` for an atomic read-modify-write; assigning from a separately read `.value` can lose concurrent updates.
- Keep critical sections short and avoid calling unknown code while holding a mutex.
- Make caches and shared maps safe for the actual dispatcher and thread model; coroutine structure alone does not make ordinary mutable collections thread-safe.

## Deterministic tests

- Use `runTest` from `kotlinx-coroutines-test` for suspending tests and virtual time. Do not use real delays as synchronization.
- Inject or expose scheduling only where production code owns a dispatcher or scope. Do not redesign code solely to satisfy a test helper.
- Advance virtual time deliberately and assert pending work, cancellation, failure, and completion—not only the happy result.
- Collect finite flow prefixes with operators such as `first`, `take`, or `toList`; cancel collectors owned by the test. Use an already-installed flow test library when the repository standardizes one.
- Test hot streams with explicit subscription timing, replay expectations, and overflow behavior.
- Use `runBlocking` only to bridge a truly blocking entry point. Never call it from suspend code; use `runTest` for coroutine tests.

## Review examples

Replace detached work with caller-owned concurrency:

```kotlin
// Wrong: caller cannot await, cancel, or observe failure.
GlobalScope.launch { audit.write(event) }

// Better when audit is part of this operation.
suspend fun record(event: Event) = coroutineScope {
    audit.write(event)
}
```

Preserve cancellation while translating an expected failure:

```kotlin
suspend fun loadOrCached(): Value = try {
    remote.load()
} catch (failure: IOException) {
    cache.requireCurrent(failure)
}
```

## Official references

- [Kotlin coroutines guide](https://kotlinlang.org/docs/coroutines-guide.html)
- [Coroutine basics and structured concurrency](https://kotlinlang.org/docs/coroutines-basics.html)
- [Cancellation and timeouts](https://kotlinlang.org/docs/cancellation-and-timeouts.html)
- [Coroutine exception handling](https://kotlinlang.org/docs/exception-handling.html)
- [Kotlin Flow](https://kotlinlang.org/docs/flow.html)
- [`CoroutineScope` API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/-coroutine-scope/)
- [`StateFlow` API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/-state-flow/)
- [`runBlocking` API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/run-blocking.html)
- [`kotlinx-coroutines-test` API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-test/)
