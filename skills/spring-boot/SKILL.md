---
name: spring-boot
description: Implement, refactor, debug, test, operate, or review Spring Boot applications in any supported JVM language. Use when the affected module applies the Spring Boot plugin, declares Spring Boot starters or auto-configuration, contains a Spring Boot application runtime, or combines Boot dependency management with affected Spring application code; dependency management alone is not enough. Cover container lifecycle, configuration, web boundaries, transactions, persistence, events, security, testing, and startup proof; also load `kotlin` when affected source is Kotlin.
---

# Spring Boot

Treat the application context, proxy boundaries, external configuration, and executable startup as part of the program. Preserve Boot's conventions unless live evidence proves that the application deliberately replaces them.

## Establish the runtime

1. Read repository guidance, wrapper and build files, dependency management, the Spring Boot and Java versions, application entry point, configuration files, migrations, and nearby tests.
2. Identify the affected web stack (Servlet MVC, WebFlux, or neither), persistence technology, transaction manager, security setup, active test profiles, external services, Actuator endpoints, and container or deployment path.
3. Inspect auto-configuration and existing bean definitions before adding infrastructure. Do not recreate a Boot-managed facility or introduce a second framework for the same concern.
4. Load the language skill independently. For Kotlin source, load `kotlin` and follow its nullability, type, coroutine, finality, and Java-interoperability rules in addition to this skill.

## Preserve container semantics

- Use constructor injection for required collaborators and keep singleton beans free of request-specific mutable state. Treat a constructor cycle as a design defect, not a reason for field injection or `@Lazy`.
- Keep constructors and `@PostConstruct` fast and local. Do not perform long I/O or rely on `@Transactional`, `@Async`, caching, or other proxy advice during initialization.
- Use cohesive, typed `@ConfigurationProperties` with validation for related settings. Use `@Value` only for an isolated scalar that does not belong to a configuration object.
- Register configuration properties through the repository's established scanning or enablement path. Make unsafe or required production values fail startup rather than silently defaulting.
- Assume proxy-based annotations apply only to calls entering the Spring-managed proxy. Check self-invocation, object construction outside the container, visibility and proxyability, initialization calls, and newly created threads.
- Prefer starters, managed versions, and auto-configuration. Inspect the condition report before overriding an auto-configured bean and document why the replacement is necessary.

## Preserve application boundaries

- Bind untrusted input to narrow transport types, validate shape at the edge, and enforce business invariants in the application or domain layer. Never bind an HTTP request directly to a persistence entity.
- Keep controllers focused on protocol mapping. Keep complete use-case transaction boundaries in application services, not controllers or a sequence of unrelated repository calls.
- Keep one stable error contract with safe client messages and machine-readable codes. Do not expose stack traces, SQL, class names, secrets, or arbitrary exception messages.
- Enforce authentication and authorization at the server boundary and ownership or domain authorization where the protected operation executes. Do not weaken CSRF, CORS, or method security to satisfy a test.
- Keep blocking, imperative work out of reactive pipelines and keep reactive assumptions out of imperative, thread-bound transactions.
- Use in-process events and `@Async` only with explicit delivery, ordering, failure, executor, and transaction semantics. Do not present an in-memory callback as durable messaging.

## Prove behavior

1. Use the checked-in Gradle or Maven wrapper. Run a focused plain or slice test first, then affected integration tests and the plan's final checks.
2. Test the real boundary that carries risk: serialization and filters for HTTP, mappings and queries for persistence, property binding for configuration, and proxy behavior for transactions or async work.
3. Use `@SpringBootTest` only when full-context wiring is the subject. Use a real embedded server when server startup or the HTTP stack is part of the contract.
4. For changes to beans, dependencies, properties, migrations, security filters, HTTP stack, runtime initialization, or packaging, start the application under safe representative configuration. Observe readiness or a real endpoint, then stop it cleanly.
5. Record the exact command, profile, infrastructure, exit status, and decisive context-loaded, ready, health, or request signal. Compilation and mocked unit tests are not startup proof.

## Load detailed guidance

- Read [runtime-and-configuration.md](references/runtime-and-configuration.md) when changing beans, auto-configuration, dependency wiring, properties, profiles, lifecycle, scheduling, or observability.
- Read [data-transactions-and-events.md](references/data-transactions-and-events.md) when changing repositories, entities, queries, migrations, transactions, application events, async work, or concurrent updates.
- Read [web-testing-and-operations.md](references/web-testing-and-operations.md) when changing HTTP, validation, error handling, security, tests, startup, packaging, or deployment behavior.
