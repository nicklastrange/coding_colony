---
name: kotlin
description: Implement, refactor, debug, test, or review idiomatic Kotlin across JVM, Android, multiplatform, and server projects. Use whenever affected source contains Kotlin `.kt` or `.kts` files or the affected module applies a Kotlin plugin. Cover Kotlin type modeling, null safety, collections, API design, Java interop, and kotlinx.coroutines or Flow; combine with a separate framework skill such as `spring-boot` when both stacks match.
---

# Kotlin

Write Kotlin as Kotlin, not as compressed Java. Preserve the repository's architecture while using the language to make invalid states and accidental mutation harder to express.

## Establish the contract

1. Read repository guidance, the affected build files, version catalog, compiler options, static-analysis rules, and nearby Kotlin tests.
2. Identify the Kotlin version, targets, JVM toolchain when present, API stability requirements, Java callers, serialization or persistence boundaries, and the repository's coroutine conventions.
3. Inspect callers before changing nullability, defaults, visibility, variance, suspend behavior, exception behavior, or a public data type. Treat each as an API change even when the JVM signature appears compatible.
4. Load framework-specific skills independently. A Kotlin Spring Boot module requires both `kotlin` and `spring-boot`; a plain Kotlin module requires only this skill.

## Model with the type system

- Represent valid absence with a nullable type. Reject missing required values at the boundary instead of carrying nullable state into the core.
- Represent closed alternatives with an enum or sealed hierarchy and an exhaustive `when`; use a sealed hierarchy when alternatives carry different data or behavior.
- Use a `data class` only for value semantics. Do not use generated structural equality for mutable identity-bearing entities unless the repository deliberately does so.
- Use a value class for a mature, single-value domain distinction only after checking serialization, persistence, reflection, generic boxing, and Java-call-site behavior. A `typealias` improves naming but creates no type safety.
- Prefer `val`, read-only collection interfaces, and immutable state transitions. Confine mutation to the smallest owner; remember that Kotlin read-only collections are views, not a deep immutability guarantee.

## Write idiomatic implementation

- Prefer expressions, named arguments, default parameters, destructuring, collection operators, and top-level or narrowly scoped extensions when they clarify intent. Keep an ordinary loop when control flow, allocation cost, or mutation is clearer.
- Use `require` or `requireNotNull` for caller preconditions and `check` or `checkNotNull` for invalid object state. Preserve domain-specific failure types where callers depend on them.
- Use safe calls and Elvis operators to preserve absence semantics. Use `orEmpty()` only when `null` and empty mean the same thing. Treat `!!` as an assertion that needs a locally visible proof.
- Use scope functions by role: `apply` to configure an object, `also` for a side effect, `let` to transform or scope a nullable value, and `run` to compute with a receiver. Avoid nested or mixed scope-function chains with ambiguous `it` or `this`.
- Keep public return and property types explicit, especially at Java platform-type boundaries. Add `@Jvm*` annotations only for a demonstrated Java interoperability need.
- Prefer constructor initialization or `lazy` to `lateinit`. Reserve `lateinit` for a lifecycle whose initialization-before-read invariant is both unavoidable and testable.
- Catch the narrow failures the code can handle. Never catch `Throwable` as normal control flow; in coroutine code, never swallow cancellation.

## Verify and review

1. Use the checked-in Gradle or Maven wrapper and repository-native formatter and linter.
2. Run the smallest affected test first, then module checks and the plan's broader verification.
3. Test exhaustive state transitions, null and platform boundaries, equality or copy behavior, exception contracts, and Java call sites when changed.
4. Review for Java-shaped residue: utility holder classes, builders that named/default arguments replace, `Optional` in Kotlin-facing APIs, mutable collection leakage, getter-style methods, and unnecessary nullable or `lateinit` state.
5. Review every coroutine change for ownership, cancellation, dispatcher use, failure propagation, backpressure, and deterministic tests.

## Load detailed guidance

- Read [idiomatic-kotlin.md](references/idiomatic-kotlin.md) for any non-trivial Kotlin implementation, public API change, refactor, or review.
- Read [coroutines-and-flow.md](references/coroutines-and-flow.md) whenever affected code uses `suspend`, `CoroutineScope`, `Flow`, channels, dispatchers, or shared concurrent state.

