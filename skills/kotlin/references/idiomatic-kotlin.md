# Idiomatic Kotlin

## Contents

- Type and state modeling
- Nullability and contracts
- Classes, functions, and APIs
- Collections and control flow
- Equality, copying, and delegation
- Java interoperability
- Review examples
- Official references

## Type and state modeling

- Choose an enum for a fixed set of stateless identities. Choose a sealed interface or class when each alternative needs different data, behavior, or inheritance.
- Keep `when` exhaustive by matching every sealed subtype or enum entry. Avoid `else` on a closed domain because it hides newly added alternatives from the compiler.
- Use a `data class` for data whose logical identity is all primary-constructor properties. Properties declared in the class body do not participate in generated `equals`, `hashCode`, `toString`, `copy`, or component functions.
- Treat `copy()` as shallow. Mutable lists, maps, arrays, and nested mutable objects remain shared after copying.
- Use `data object` for a singleton alternative that needs value-like `toString` and equality behavior. Use a plain `object` for a singleton service or namespace.
- Use a value class to prevent mixing domain primitives only when its boxing and boundary behavior are acceptable. Do not introduce one casually around ORM entities, reflective serializers, generic APIs, or Java-heavy call sites.
- Use a type alias only to clarify a long type. Never claim that `typealias UserId = String` prevents passing another `String`.
- Keep state transitions explicit. Prefer returning a new immutable value over mutating a data object shared by several owners.

```kotlin
sealed interface PaymentResult {
    data class Accepted(val receiptId: ReceiptId) : PaymentResult
    data class Rejected(val reason: RejectionReason) : PaymentResult
}

fun message(result: PaymentResult): String = when (result) {
    is PaymentResult.Accepted -> "Accepted ${result.receiptId}"
    is PaymentResult.Rejected -> "Rejected: ${result.reason}"
}
```

## Nullability and contracts

- Make a type nullable only when absence is a valid domain state. Parse, validate, and reject invalid external data at its boundary.
- Avoid `Optional` in Kotlin-facing APIs. Use `T?`; preserve `Optional` only where a Java contract requires it.
- Use `requireNotNull(value)` when a caller supplied an invalid argument and `checkNotNull(value)` when the program reached an invalid internal state.
- Use `?.let { ... }` only when the action truly occurs only for a present value. Prefer an early return or named local when a longer block would hide control flow.
- Use `orEmpty()` only when missing and empty are behaviorally identical. Do not turn “unknown” into an empty string or list for convenience.
- Avoid `!!`. If an external framework guarantees non-null after a lifecycle event, isolate the assertion behind one named accessor and test the lifecycle rather than scattering assertions.
- Give public declarations that consume Java platform types explicit Kotlin types. Convert or validate platform values immediately so `T!` does not spread.
- Copy an unstable mutable or open property to a local before relying on a smart cast.

```kotlin
fun register(rawEmail: String?): Email {
    val email = requireNotNull(rawEmail) { "email is required" }
    return Email.parse(email)
}
```

## Classes, functions, and APIs

- Prefer a property over a zero-argument function only when access is cheap, deterministic for unchanged object state, and does not throw.
- Prefer default and named arguments to constructor or method overloads in Kotlin-only APIs. Add `@JvmOverloads` only when Java callers actually need generated overloads.
- Prefer a top-level function over a stateless utility object. Prefer a narrow extension when the operation conceptually belongs with the receiver but cannot be a member.
- Remember that extensions use static dispatch. Never use an extension when callers need polymorphic override behavior.
- Restrict extensions to the narrowest useful visibility to avoid polluting completion and creating ambiguous imports.
- Omit explicit `Unit` and redundant syntax. Use expression bodies for short expressions, not multi-branch logic whose return type or debugging becomes obscure.
- Use factory functions when construction has named semantics, caching, validation, or subtype selection. Do not add a builder when named/default arguments already express construction clearly.
- Keep public library visibility and return types explicit. Preserve binary and source compatibility intentionally; changing a default value or nullability can break callers without changing a familiar-looking signature.
- Use `inline` only for measured allocation/control-flow needs or reified type parameters. Avoid large inline bodies because they increase call-site bytecode and expose implementation to binary compatibility concerns.
- Use `reified` only when runtime type access is required. Pass a `KClass`, serializer, or strategy explicitly when the type must cross a non-inline boundary.

## Collections and control flow

- Expose `List`, `Set`, or `Map` when callers should not mutate through the API. Copy a mutable backing collection before returning it when a stable snapshot is required.
- Prefer `map`, `filter`, `mapNotNull`, `associate`, and `groupBy` for direct transformations. Use a loop when it avoids several intermediate collections, supports early exit, or makes stateful logic clearer.
- Do not replace a clear `for` loop with `forEach`; labeled and non-local returns are easier to misread.
- Use `Sequence` only for a long transformation pipeline, a large source, or short-circuiting that avoids work. Small collections often become slower and less debuggable when made lazy.
- Remember that `associateBy` and `associateWith` keep the last value for a duplicate key. Detect duplicates explicitly when uniqueness is an invariant.
- Use `..<` or `until` for exclusive upper bounds. Avoid `0..size - 1`; prefer `indices`, `withIndex()`, or direct iteration.
- Keep mutable builders local: build with `buildList`, `buildMap`, or a local mutable collection, then expose a read-only result.
- Use sequences, flows, and collections deliberately: collections are eager in-memory values, sequences are synchronous lazy iteration, and flows are asynchronous streams with cancellation.

## Equality, copying, and delegation

- Use `==` for structural equality and `===` only for intentional reference identity.
- Use `contentEquals` or `contentDeepEquals` for arrays; array `==` compares identity.
- Keep properties that define data-class equality in the primary constructor. Avoid mutable equality keys in hash-based collections.
- Choose a property delegate because it owns a real lifecycle or access policy, not to hide a simple field. Confirm the concurrency mode of `lazy` when several threads can initialize it.
- Avoid `lateinit` for nullable or optional state. `isInitialized` is a diagnostic escape hatch, not a substitute for an explicit state model.
- Do not delegate core business behavior through clever operators or DSLs unless the repository already establishes that language; explicit code is easier to search and review.

## Java interoperability

- Inspect the Java-facing signature, not only the Kotlin source. Default parameters, suspend functions, value classes, companion members, nullability annotations, and `Unit` have distinct JVM representations.
- Use `@JvmStatic`, `@JvmField`, `@JvmName`, `@JvmOverloads`, and wildcard annotations only to satisfy a specific Java call site or framework contract.
- Treat Java collections as capable of mutation and null insertion unless the boundary proves otherwise. Copy or validate before storing them as Kotlin invariants.
- Do not use named arguments with Java methods; Java parameter names are not a stable Kotlin API contract.
- Be explicit about platform nullability at overrides and callbacks. Add boundary tests in Java when a public library promises Java usability.

## Review examples

Replace a builder-shaped DTO when the project has no Java caller:

```kotlin
data class SearchRequest(
    val query: String,
    val limit: Int = 20,
    val cursor: String? = null,
)

val request = SearchRequest(query = "kotlin", limit = 50)
```

Preserve duplicate detection instead of silently overwriting:

```kotlin
fun index(users: List<User>): Map<UserId, User> {
    val grouped = users.groupBy(User::id)
    require(grouped.values.none { it.size > 1 }) { "duplicate user id" }
    return grouped.mapValues { (_, matches) -> matches.single() }
}
```

## Official references

- [Kotlin coding conventions](https://kotlinlang.org/docs/coding-conventions.html)
- [Kotlin idioms](https://kotlinlang.org/docs/idioms.html)
- [Null safety](https://kotlinlang.org/docs/null-safety.html)
- [Scope functions](https://kotlinlang.org/docs/scope-functions.html)
- [Sealed classes and interfaces](https://kotlinlang.org/docs/sealed-classes.html)
- [Inline value classes](https://kotlinlang.org/docs/inline-classes.html)
- [Data classes](https://kotlinlang.org/docs/data-classes.html)
- [Equality](https://kotlinlang.org/docs/equality.html)
- [Collections](https://kotlinlang.org/docs/collections-overview.html)
- [Sequences](https://kotlinlang.org/docs/sequences.html)
- [Generics and variance](https://kotlinlang.org/docs/generics.html)
- [Extensions](https://kotlinlang.org/docs/extensions.html)
- [Inline functions](https://kotlinlang.org/docs/inline-functions.html)
- [Delegation](https://kotlinlang.org/docs/delegation.html)
- [Java interoperability](https://kotlinlang.org/docs/java-interop.html)
- [API backward compatibility](https://kotlinlang.org/docs/api-guidelines-backward-compatibility.html)
