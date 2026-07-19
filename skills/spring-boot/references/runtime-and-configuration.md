# Runtime and Configuration

## Contents

- Auto-configuration and bean design
- Proxy and lifecycle boundaries
- External configuration
- Scheduling and observability
- Review examples
- Official references

## Auto-configuration and bean design

- Let starters and Boot dependency management select compatible infrastructure versions. Do not pin a managed library without a demonstrated compatibility or security reason.
- Inspect the `ConditionEvaluationReport` when an expected bean is missing or an unexpected bean is present. Fix the condition, classpath, or property before replacing auto-configuration.
- Override an auto-configured bean only when the application requires different behavior and Boot exposes that extension point. Preserve conditional behavior so tests and alternate deployments do not receive duplicate beans.
- Use constructor injection for mandatory collaborators. A single constructor needs no `@Autowired` on supported Spring versions.
- Treat singleton beans as concurrently accessed. Keep controllers, services, filters, converters, and configuration objects stateless or protect their actual shared mutable state.
- Break constructor cycles by correcting responsibilities or introducing a real boundary. Do not hide the cycle with field injection, mutable setters, or `@Lazy` unless the cycle itself is an intentional framework contract.
- Declare an `@Bean` dependency as a method parameter. Use `@Configuration(proxyBeanMethods = false)` only when bean factory methods are independent; direct calls between bean methods require full proxy semantics or should be removed.
- Keep application package structure compatible with component and entity scanning rooted at the main application class. Add explicit scanning only for a deliberate cross-package boundary.

## Proxy and lifecycle boundaries

- Assume `@Transactional`, `@Async`, `@Cacheable`, method security, retry, and similar advice depends on a Spring-created proxy unless the configured mode proves otherwise.
- Verify that calls enter through the proxy. Self-invocation, calls from a constructor or `@PostConstruct`, and instances created with `new` bypass ordinary proxy advice.
- Verify class and method proxyability for the chosen language and proxy mechanism. In Kotlin, also inspect the Spring compiler plugin or explicit `open` behavior through the separate `kotlin` skill.
- Keep `@PostConstruct` to fast validation or local in-memory preparation. It runs while the context is creating the bean; long remote or database work delays or prevents startup.
- Use an application runner only for work that legitimately happens after context creation and whose startup failure policy is explicit. Use lifecycle callbacks only for resources requiring coordinated start and stop.
- Pair every acquired executor, scheduler, connection, watcher, or client with container-managed shutdown. Confirm graceful shutdown for work that can remain in flight.
- Do not depend on proxy advice inside initialization. If startup must validate transactional behavior, invoke it after the context is ready through a separate Spring-managed collaborator.

## External configuration

- Group related values in a typed `@ConfigurationProperties` object. Keep environment data in that object; inject services elsewhere.
- Validate required configuration during binding with `@Validated` and constraint annotations or explicit constructor invariants. Fail startup with a precise property path.
- Register properties with the project's existing `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` mechanism. A well-shaped class that is never registered provides no binding.
- Use canonical kebab-case property names and preserve relaxed-binding expectations. Do not rename a deployed property without migration or compatibility handling.
- Understand property-source precedence before diagnosing a value. Check command-line arguments, environment variables, system properties, profile-specific files, imports, and test overrides.
- Keep secrets outside committed configuration and logs. Mask sensitive values in configuration diagnostics and Actuator exposure.
- Avoid unsafe defaults for credentials, destructive modes, production endpoints, encryption keys, or tenant identifiers. Defaults should be safe in every environment where they can apply.
- Keep profile activation and profile groups explicit. Avoid a combinatorial profile matrix that silently changes core behavior.
- Test binding with representative valid, missing, malformed, and boundary values when a property controls behavior or startup.

```java
@ConfigurationProperties("payments.gateway")
@Validated
public record GatewayProperties(
    @NotNull URI baseUrl,
    @NotNull Duration timeout
) {
    public GatewayProperties {
        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
```

Express the same contract idiomatically in the affected JVM language; do not copy Java syntax into Kotlin.

## Scheduling and observability

- Give scheduled work an explicit overlap policy. A single-instance scheduler does not prevent two application replicas from running the same job.
- Make retryable scheduled work idempotent and observable. Persist durable progress when missing one run would violate the product contract.
- Configure named executors with bounded capacity and a rejection policy derived from load behavior. Avoid the implicit unbounded or unsuitable executor for production async work.
- Reuse Boot and Micrometer instrumentation. Do not record duplicate spans or metrics around already instrumented clients.
- Keep metric and trace dimensions low-cardinality. Never use user IDs, request IDs, raw URLs, exception messages, or other unbounded values as metric tags.
- Expose only required Actuator endpoints, secure them, and separate liveness from readiness semantics. Liveness must not depend on a failing external service in a way that causes restart loops.
- Log actionable context at a boundary once. Preserve correlation without logging secrets or the same exception at every layer.

## Review examples

Prefer injected bean dependencies to direct configuration calls:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {
    @Bean
    ApiClient apiClient(GatewayProperties properties, HttpClient httpClient) {
        return new ApiClient(properties.baseUrl(), httpClient);
    }
}
```

Reject a hidden lifecycle dependency:

```java
// Wrong: transaction advice is not active during this self-call in initialization.
@PostConstruct
void initialize() {
    rebuildIndexTransactionally();
}

@Transactional
void rebuildIndexTransactionally() { /* ... */ }
```

## Official references

- [Spring Boot auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Framework dependency injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Bean lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot external configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Task execution and scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

